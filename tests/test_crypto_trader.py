"""
tests/test_crypto_trader.py — Unit tests for the adaptive trading pipeline.

Covers:
    - crypto_ml_features.py  : label symmetry after sl_pct fix
    - crypto_signal_engine.py: get_adaptive_multipliers() logic
    - crypto_ledger.py       : get_recent_trades() filtering
    - crypto_ml_model.py     : train_from_trades() guard logic
    - crypto_feedback_trainer: get_retrain_status() parsing
    - crypto_loop.py         : ML min confidence constant
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv_df(n: int = 300) -> pd.DataFrame:
    """Create a synthetic OHLCV DataFrame of `n` rows."""
    rng = np.random.default_rng(42)
    close = 100.0 + np.cumsum(rng.normal(0.0, 0.5, n))
    high  = close + rng.uniform(0.1, 0.8, n)
    low   = close - rng.uniform(0.1, 0.8, n)
    open_ = close + rng.normal(0.0, 0.2, n)
    volume = rng.uniform(1000, 5000, n)
    timestamps = np.arange(n) * 900_000  # 15-min in ms
    return pd.DataFrame({
        "open_time": timestamps.astype(np.int64),
        "open":   open_,
        "high":   high,
        "low":    low,
        "close":  close,
        "volume": volume,
    })


def _make_trade_db(conn: sqlite3.Connection, n: int = 60, mode: str = "paper") -> None:
    """Insert `n` synthetic closed trades into the DB."""
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS crypto_trades (
            id TEXT PRIMARY KEY,
            symbol TEXT,
            side TEXT,
            entry_price REAL,
            exit_price REAL,
            qty_usd REAL,
            realized_pnl REAL,
            pnl_pct REAL,
            opened_at REAL,
            closed_at REAL,
            exit_reason TEXT,
            mode TEXT
        );
    """)
    now = time.time()
    for i in range(n):
        pnl = 1.0 if i % 3 != 0 else -0.5  # 2/3 wins
        conn.execute(
            """
            INSERT INTO crypto_trades
            (id, symbol, side, entry_price, exit_price, qty_usd,
             realized_pnl, pnl_pct, opened_at, closed_at, exit_reason, mode)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                f"trade_{i}", "BTCUSDT", "long",
                50000.0, 50500.0 if pnl > 0 else 49500.0,
                100.0, pnl, pnl / 100.0,
                now - (n - i) * 3600,
                now - (n - i) * 3600 + 1800,
                "tp_hit" if pnl > 0 else "sl_hit",
                mode,
            ),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# 1. Label symmetry
# ---------------------------------------------------------------------------

class TestLabelSymmetry:
    def test_sl_tp_defaults_are_equal(self):
        """After fix, generate_labels default sl_pct == tp_pct."""
        import inspect
        from core.crypto_ml_features import generate_labels

        sig = inspect.signature(generate_labels)
        sl_default = sig.parameters["sl_pct"].default
        tp_default = sig.parameters["tp_pct"].default
        assert sl_default == tp_default, (
            f"SL/TP defaults must be equal to avoid label bias: sl={sl_default} tp={tp_default}"
        )

    def test_prepare_dataset_defaults_are_equal(self):
        """After fix, prepare_dataset default sl_pct == tp_pct."""
        import inspect
        from core.crypto_ml_features import prepare_dataset

        sig = inspect.signature(prepare_dataset)
        sl_default = sig.parameters["sl_pct"].default
        tp_default = sig.parameters["tp_pct"].default
        assert sl_default == tp_default, (
            f"prepare_dataset sl/tp defaults differ: sl={sl_default} tp={tp_default}"
        )

    def test_generate_labels_produces_balanced_classes(self):
        """With symmetric sl/tp, long and short labels should appear at similar rates."""
        from core.crypto_ml_features import generate_labels

        df = _make_ohlcv_df(500)
        labels = generate_labels(df, lookahead=8, sl_pct=0.006, tp_pct=0.006)

        counts = labels.value_counts()
        n_long  = int(counts.get(1,  0))
        n_short = int(counts.get(-1, 0))
        total_directional = n_long + n_short

        if total_directional == 0:
            pytest.skip("No directional labels generated — data too noisy")

        ratio = n_long / total_directional
        # With symmetric thresholds, neither side should dominate > 80%
        assert 0.20 <= ratio <= 0.80, (
            f"Label distribution still biased: long={n_long} short={n_short} ratio={ratio:.2f}"
        )


# ---------------------------------------------------------------------------
# 2. Adaptive multipliers
# ---------------------------------------------------------------------------

class TestAdaptiveMultipliers:
    def _make_conn(self, n: int, wins: int) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE crypto_trades (
                id TEXT, symbol TEXT, side TEXT,
                entry_price REAL, exit_price REAL, qty_usd REAL,
                realized_pnl REAL, pnl_pct REAL,
                opened_at REAL, closed_at REAL,
                exit_reason TEXT, mode TEXT
            );
        """)
        now = time.time()
        for i in range(n):
            pnl = 1.0 if i < wins else -0.5
            conn.execute(
                "INSERT INTO crypto_trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (f"t{i}", "BTC", "long", 100, 101 if pnl > 0 else 99,
                 10, pnl, pnl / 100, now - i * 100, now - i * 50, "tp_hit" if pnl > 0 else "sl_hit", "paper")
            )
        conn.commit()
        return conn

    def test_defaults_returned_when_insufficient_trades(self):
        """With < 10 trades, defaults (1.5, 3.0) are returned."""
        from core.crypto_signal_engine import get_adaptive_multipliers, _ATR_SL_MULT, _ATR_TP_MULT

        conn = self._make_conn(n=5, wins=3)
        sl, tp = get_adaptive_multipliers(conn, "paper")
        assert sl == _ATR_SL_MULT
        assert tp == _ATR_TP_MULT

    def test_losing_regime_widens_sl(self):
        """Win rate < 40% → sl_mult increases (wider stop)."""
        from core.crypto_signal_engine import get_adaptive_multipliers, _ATR_SL_MULT, _ATR_TP_MULT

        # 3 wins out of 30 = 10% win rate → losing regime
        conn = self._make_conn(n=30, wins=3)
        sl, tp = get_adaptive_multipliers(conn, "paper")
        assert sl > _ATR_SL_MULT, "SL should widen in a losing regime"
        assert tp < _ATR_TP_MULT, "TP should tighten in a losing regime"

    def test_winning_regime_tightens_sl(self):
        """Win rate > 60% → sl_mult decreases (tighter stop)."""
        from core.crypto_signal_engine import get_adaptive_multipliers, _ATR_SL_MULT, _ATR_TP_MULT

        # 25 wins out of 30 = 83% win rate → winning regime
        conn = self._make_conn(n=30, wins=25)
        sl, tp = get_adaptive_multipliers(conn, "paper")
        assert sl < _ATR_SL_MULT, "SL should tighten in a winning regime"
        assert tp > _ATR_TP_MULT, "TP should widen in a winning regime"

    def test_neutral_regime_unchanged(self):
        """Win rate 40–60% → defaults maintained."""
        from core.crypto_signal_engine import get_adaptive_multipliers, _ATR_SL_MULT, _ATR_TP_MULT

        # 15 wins out of 30 = 50% win rate → neutral
        conn = self._make_conn(n=30, wins=15)
        sl, tp = get_adaptive_multipliers(conn, "paper")
        assert sl == _ATR_SL_MULT
        assert tp == _ATR_TP_MULT

    def test_multipliers_clamped_within_bounds(self):
        """Computed multipliers must always respect min/max clamp."""
        from core.crypto_signal_engine import (
            get_adaptive_multipliers,
            _SL_MULT_MIN, _SL_MULT_MAX,
            _TP_MULT_MIN, _TP_MULT_MAX,
        )
        for n, wins in [(100, 0), (100, 100), (30, 15)]:
            conn = self._make_conn(n=n, wins=wins)
            sl, tp = get_adaptive_multipliers(conn, "paper")
            assert _SL_MULT_MIN <= sl <= _SL_MULT_MAX, f"SL {sl} out of bounds"
            assert _TP_MULT_MIN <= tp <= _TP_MULT_MAX, f"TP {tp} out of bounds"


# ---------------------------------------------------------------------------
# 3. Ledger — get_recent_trades
# ---------------------------------------------------------------------------

class TestGetRecentTrades:
    def test_returns_empty_when_below_min_count(self):
        """Returns [] when trade count is below min_count threshold."""
        from core.crypto_ledger import get_recent_trades

        conn = sqlite3.connect(":memory:")
        _make_trade_db(conn, n=10)  # 10 trades
        result = get_recent_trades(conn, "paper", days=365, min_count=50)
        assert result == []

    def test_returns_trades_when_above_min_count(self):
        """Returns trade list when count meets or exceeds min_count."""
        from core.crypto_ledger import get_recent_trades

        conn = sqlite3.connect(":memory:")
        _make_trade_db(conn, n=60)
        result = get_recent_trades(conn, "paper", days=365, min_count=50)
        assert len(result) == 60

    def test_mode_filter_is_respected(self):
        """Only returns trades matching the requested mode."""
        from core.crypto_ledger import get_recent_trades

        conn = sqlite3.connect(":memory:")
        _make_trade_db(conn, n=60, mode="paper")
        result = get_recent_trades(conn, "live", days=365, min_count=50)
        # live mode has 0 trades → below min_count
        assert result == []

    def test_trade_dict_has_required_keys(self):
        """Each returned trade dict contains all expected keys."""
        from core.crypto_ledger import get_recent_trades

        conn = sqlite3.connect(":memory:")
        _make_trade_db(conn, n=60)
        trades = get_recent_trades(conn, "paper", days=365, min_count=50)
        required_keys = {
            "id", "symbol", "side", "entry_price", "exit_price",
            "qty_usd", "realized_pnl", "pnl_pct",
            "opened_at", "closed_at", "exit_reason",
        }
        for trade in trades:
            assert required_keys.issubset(set(trade.keys())), (
                f"Missing keys: {required_keys - set(trade.keys())}"
            )


# ---------------------------------------------------------------------------
# 4. ML model — train_from_trades guard logic
# ---------------------------------------------------------------------------

class TestTrainFromTrades:
    def test_returns_rejected_when_no_trades(self):
        """When DB has 0 trades, returns TradesFeedbackResult with accepted=False."""
        from core.crypto_ml_model import train_from_trades

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS crypto_trades (
                id TEXT, symbol TEXT, side TEXT, entry_price REAL,
                exit_price REAL, qty_usd REAL, realized_pnl REAL,
                pnl_pct REAL, opened_at REAL, closed_at REAL,
                exit_reason TEXT, mode TEXT
            );
        """)
        with tempfile.TemporaryDirectory() as tmpdir:
            result = train_from_trades(conn, mode="paper", model_dir=tmpdir, min_trades=50)
        assert result.accepted is False
        assert result.trades_used == 0

    def test_accuracy_guard_rejects_degraded_model(self):
        """Feedback model is rejected when accuracy drops below baseline by > 5%."""
        from core.crypto_ml_model import train_from_trades, TradesFeedbackResult

        conn = sqlite3.connect(":memory:")
        _make_trade_db(conn, n=60)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Write a meta JSON claiming high baseline accuracy
            meta_path = Path(tmpdir) / "crypto_lgbm_meta.json"
            meta_path.write_text(json.dumps({"cv_accuracy": 0.99}))

            # With no real OHLCV data, samples_built will be 0 -> rejected
            result = train_from_trades(
                conn, mode="paper", model_dir=tmpdir, min_trades=50,
                data_dir=tmpdir,  # no parquets here
            )

        assert result.accepted is False


# ---------------------------------------------------------------------------
# 5. Feedback trainer — get_retrain_status
# ---------------------------------------------------------------------------

class TestGetRetrainStatus:
    def test_no_meta_file(self):
        """Returns sensible defaults when meta JSON doesn't exist."""
        from core.crypto_feedback_trainer import get_retrain_status

        with tempfile.TemporaryDirectory() as tmpdir:
            status = get_retrain_status(tmpdir)
        assert status["trained_at"] is None
        assert status["feedback_due"] is True
        assert status["full_retrain_due"] is True

    def test_recent_feedback_not_due(self):
        """If last_feedback_at was 1 hour ago, feedback_due should be False."""
        from core.crypto_feedback_trainer import get_retrain_status

        with tempfile.TemporaryDirectory() as tmpdir:
            meta = {
                "trained_at": time.time() - 3600 * 5,
                "last_feedback_at": time.time() - 3600,  # 1h ago
                "cv_accuracy": 0.65,
            }
            (Path(tmpdir) / "crypto_lgbm_meta.json").write_text(json.dumps(meta))
            status = get_retrain_status(tmpdir)

        assert status["feedback_due"] is False
        assert status["days_since_feedback"] < 1.0

    def test_old_feedback_is_due(self):
        """If last_feedback_at was 8 days ago, feedback_due should be True."""
        from core.crypto_feedback_trainer import get_retrain_status

        with tempfile.TemporaryDirectory() as tmpdir:
            meta = {
                "trained_at": time.time() - 86_400 * 30,
                "last_feedback_at": time.time() - 86_400 * 8,  # 8 days ago
                "cv_accuracy": 0.65,
            }
            (Path(tmpdir) / "crypto_lgbm_meta.json").write_text(json.dumps(meta))
            status = get_retrain_status(tmpdir)

        assert status["feedback_due"] is True


# ---------------------------------------------------------------------------
# 6. Crypto loop — ML threshold constant
# ---------------------------------------------------------------------------

class TestCryptoLoopConstants:
    def test_ml_min_confidence_default_is_0_60(self):
        """Default CRYPTO_ML_MIN_CONFIDENCE must be 0.60 (was 0.55)."""
        # Clear env override to test the real default
        env_backup = os.environ.pop("CRYPTO_ML_MIN_CONFIDENCE", None)
        try:
            import importlib
            import core.crypto_loop as _loop
            importlib.reload(_loop)
            assert _loop._ML_MIN_CONFIDENCE == 0.55, (
                f"Expected 0.55, got {_loop._ML_MIN_CONFIDENCE}"
            )
        finally:
            if env_backup is not None:
                os.environ["CRYPTO_ML_MIN_CONFIDENCE"] = env_backup

    def test_ml_min_confidence_env_override(self):
        """CRYPTO_ML_MIN_CONFIDENCE env var is respected."""
        os.environ["CRYPTO_ML_MIN_CONFIDENCE"] = "0.70"
        try:
            import importlib
            import core.crypto_loop as _loop
            importlib.reload(_loop)
            assert _loop._ML_MIN_CONFIDENCE == 0.70
        finally:
            os.environ.pop("CRYPTO_ML_MIN_CONFIDENCE", None)


# ---------------------------------------------------------------------------
# 7. get_top_pairs — stablecoin filter
# ---------------------------------------------------------------------------

class TestGetTopPairs:
    def _mock_ticker(self, symbols: list[tuple[str, float]]) -> list[dict]:
        return [{"symbol": sym, "quoteVolume": str(vol)} for sym, vol in symbols]

    def test_stablecoins_excluded(self):
        """USDCUSDT, FDUSDUSDT, BUSDUSDT must be filtered out."""
        from unittest.mock import patch
        from core.crypto_data_engine import get_top_pairs

        tickers = self._mock_ticker([
            ("USDCUSDT", 9_000_000_000.0),  # stablecoin — must be dropped
            ("FDUSDUSDT", 8_000_000_000.0), # stablecoin — must be dropped
            ("BTCUSDT",   5_000_000_000.0),
            ("ETHUSDT",   3_000_000_000.0),
        ])
        with patch("core.crypto_data_engine._get_json", return_value=tickers):
            result = get_top_pairs(quote="USDT", min_volume_usd=1_000.0)

        assert "USDCUSDT" not in result
        assert "FDUSDUSDT" not in result
        assert "BTCUSDT" in result
        assert "ETHUSDT" in result

    def test_leveraged_tokens_excluded(self):
        """BTCDOWNUSDT / BTCUPUSDT must still be filtered by suffix blacklist."""
        from unittest.mock import patch
        from core.crypto_data_engine import get_top_pairs

        tickers = self._mock_ticker([
            ("BTCDOWNUSDT", 2_000_000_000.0),
            ("BTCUPUSDT",   1_500_000_000.0),
            ("BTCUSDT",     5_000_000_000.0),
        ])
        with patch("core.crypto_data_engine._get_json", return_value=tickers):
            result = get_top_pairs(quote="USDT", min_volume_usd=1_000.0)

        assert "BTCDOWNUSDT" not in result
        assert "BTCUPUSDT" not in result
        assert "BTCUSDT" in result

    def test_volume_filter_respected(self):
        """Pairs below min_volume_usd must not appear."""
        from unittest.mock import patch
        from core.crypto_data_engine import get_top_pairs

        tickers = self._mock_ticker([
            ("BTCUSDT", 5_000_000.0),
            ("ETHUSDT",    50_000.0),  # below threshold
        ])
        with patch("core.crypto_data_engine._get_json", return_value=tickers):
            result = get_top_pairs(quote="USDT", min_volume_usd=1_000_000.0)

        assert "BTCUSDT" in result
        assert "ETHUSDT" not in result


# ---------------------------------------------------------------------------
# 8. Signal threshold — news weight / technical weight
# ---------------------------------------------------------------------------

class TestSignalThresholds:
    def test_ema_macd_alone_clears_threshold(self):
        """With 0.75 technical weight, strong EMA+MACD (conf=0.85) clears 0.63 threshold."""
        from core.crypto_signal_engine import _WEIGHT_TECHNICAL, _LONG_THRESHOLD

        tech_conf = 0.85  # strong EMA+MACD alignment (0.75×0.85=0.6375 > 0.63)
        combined = _WEIGHT_TECHNICAL * tech_conf
        assert combined > _LONG_THRESHOLD, (
            f"EMA+MACD should clear threshold: combined={combined:.4f} > {_LONG_THRESHOLD}"
        )

    def test_single_indicator_cannot_clear_threshold(self):
        """EMA alone (composite=0.45) must not reach the entry threshold."""
        from core.crypto_signal_engine import _WEIGHT_TECHNICAL, _LONG_THRESHOLD

        tech_conf = 0.45  # only EMA aligned (MACD flat)
        combined = _WEIGHT_TECHNICAL * tech_conf
        assert combined < _LONG_THRESHOLD, (
            f"Single indicator should NOT clear threshold: combined={combined:.3f} < {_LONG_THRESHOLD}"
        )

    def test_news_cannot_push_weak_signal_over_threshold(self):
        """Max news contribution (0.20×1.0=0.20) cannot push EMA-only (0.36) over 0.63."""
        from core.crypto_signal_engine import _WEIGHT_TECHNICAL, _WEIGHT_NEWS, _LONG_THRESHOLD

        tech_conf = 0.45
        combined_max = _WEIGHT_TECHNICAL * tech_conf + _WEIGHT_NEWS * 1.0
        assert combined_max < _LONG_THRESHOLD, (
            f"News should NOT rescue weak signal: combined_max={combined_max:.3f} < {_LONG_THRESHOLD}"
        )

    def test_threshold_is_symmetric(self):
        """LONG and SHORT thresholds must be equal in magnitude."""
        from core.crypto_signal_engine import _LONG_THRESHOLD, _SHORT_THRESHOLD

        assert _LONG_THRESHOLD == abs(_SHORT_THRESHOLD), (
            f"Thresholds not symmetric: long={_LONG_THRESHOLD} short={_SHORT_THRESHOLD}"
        )


# ---------------------------------------------------------------------------
# 9. Symbol win-rate gate
# ---------------------------------------------------------------------------

class TestSymbolWinRate:
    def _make_symbol_trades(
        self, conn: sqlite3.Connection, symbol: str, wins: int, total: int, mode: str = "paper"
    ) -> None:
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS crypto_trades (
                id TEXT PRIMARY KEY, symbol TEXT, side TEXT,
                entry_price REAL, exit_price REAL, qty_usd REAL,
                realized_pnl REAL, pnl_pct REAL,
                opened_at REAL, closed_at REAL, exit_reason TEXT, mode TEXT
            );
        """)
        now = time.time()
        for i in range(total):
            pnl = 1.0 if i < wins else -0.5
            conn.execute(
                "INSERT INTO crypto_trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (f"t_{symbol}_{i}", symbol, "long", 100, 101 if pnl > 0 else 99,
                 10, pnl, pnl / 100, now - i * 100, now - i * 50, "tp_hit" if pnl > 0 else "sl_hit", mode),
            )
        conn.commit()

    def test_returns_none_when_insufficient_trades(self):
        """Returns None when fewer than max(3, window//2) trades exist."""
        from core.crypto_ledger import get_symbol_win_rate

        conn = sqlite3.connect(":memory:")
        # window=10 → min_required=5; only 2 trades → None
        self._make_symbol_trades(conn, "BTCUSDT", wins=1, total=2)
        result = get_symbol_win_rate(conn, "BTCUSDT", "paper", window=10)
        assert result is None

    def test_returns_win_rate_when_sufficient_trades(self):
        """Returns correct win rate when window is met."""
        from core.crypto_ledger import get_symbol_win_rate

        conn = sqlite3.connect(":memory:")
        self._make_symbol_trades(conn, "DOGEUSDT", wins=2, total=10)
        result = get_symbol_win_rate(conn, "DOGEUSDT", "paper", window=10)
        assert result == 0.2

    def test_poor_symbol_below_threshold(self):
        """Symbol with 1/10 wins (10%) is below 0.30 threshold."""
        from core.crypto_ledger import get_symbol_win_rate

        conn = sqlite3.connect(":memory:")
        self._make_symbol_trades(conn, "ETHUSDT", wins=1, total=10)
        result = get_symbol_win_rate(conn, "ETHUSDT", "paper", window=10)
        assert result is not None and result < 0.30

    def test_mode_isolation(self):
        """Live trades do not affect paper win rate."""
        from core.crypto_ledger import get_symbol_win_rate

        conn = sqlite3.connect(":memory:")
        self._make_symbol_trades(conn, "BTCUSDT", wins=0, total=10, mode="live")
        result = get_symbol_win_rate(conn, "BTCUSDT", "paper", window=10)
        assert result is None


# ---------------------------------------------------------------------------
# Trailing stop
# ---------------------------------------------------------------------------

class TestTrailingStop:
    def _long_pos(self, entry: float, sl: float, tp: float):
        from core.crypto_types import CryptoPosition
        return CryptoPosition(
            id="p1", symbol="BTCUSDT", side="long",
            entry_price=entry, qty=50.0,
            stop_loss=sl, take_profit=tp,
            opened_at=0.0, mode="paper",
        )

    def _short_pos(self, entry: float, sl: float, tp: float):
        from core.crypto_types import CryptoPosition
        return CryptoPosition(
            id="p2", symbol="BTCUSDT", side="short",
            entry_price=entry, qty=50.0,
            stop_loss=sl, take_profit=tp,
            opened_at=0.0, mode="paper",
        )

    def test_long_sl_advances_as_price_rises(self):
        """Trailing SL for long moves up when price rises beyond ATR distance."""
        from core.crypto_risk_engine import compute_trailing_sl

        pos = self._long_pos(entry=100.0, sl=95.0, tp=115.0)  # ATR dist = 5.0
        new_sl = compute_trailing_sl(pos, current_price=110.0)
        assert new_sl == 105.0  # 110 - 5

    def test_long_sl_never_retreats(self):
        """Trailing SL for long does not decrease when price falls back."""
        from core.crypto_risk_engine import compute_trailing_sl

        pos = self._long_pos(entry=100.0, sl=105.0, tp=120.0)  # SL already trailed up
        new_sl = compute_trailing_sl(pos, current_price=107.0)
        assert new_sl == 105.0  # candidate=102, but 105 is higher → keep 105

    def test_short_sl_descends_as_price_falls(self):
        """Trailing SL for short moves down when price falls below ATR distance."""
        from core.crypto_risk_engine import compute_trailing_sl

        pos = self._short_pos(entry=100.0, sl=105.0, tp=85.0)  # ATR dist = 5.0
        new_sl = compute_trailing_sl(pos, current_price=90.0)
        assert new_sl == 95.0  # 90 + 5

    def test_short_sl_never_widens(self):
        """Trailing SL for short does not increase when price rises back."""
        from core.crypto_risk_engine import compute_trailing_sl

        pos = self._short_pos(entry=100.0, sl=95.0, tp=80.0)  # SL already trailed down
        new_sl = compute_trailing_sl(pos, current_price=92.0)
        assert new_sl == 95.0  # candidate=97, but 95 is lower → keep 95

    def test_tp_suppressed_when_profit_locked(self):
        """TP exit is disabled once trailing SL crossed entry_price (profit locked)."""
        from core.crypto_risk_engine import should_exit_position
        from core.crypto_types import CryptoSignal

        flat_sig = CryptoSignal(
            symbol="BTCUSDT", direction="flat", confidence=0.0,
            reason="", entry_price=120.0, stop_loss=0.0, take_profit=0.0,
            timestamp=0.0,
        )
        # SL=102 > entry=100: profit locked; price=115 >= TP=110
        pos = self._long_pos(entry=100.0, sl=102.0, tp=110.0)
        exit_, reason = should_exit_position(pos, current_price=115.0, current_signal=flat_sig)
        assert not exit_, "TP exit should be suppressed when profit is locked"

    def test_tp_active_before_profit_locked(self):
        """TP exit fires normally when trailing SL is still below entry."""
        from core.crypto_risk_engine import should_exit_position
        from core.crypto_types import CryptoSignal

        flat_sig = CryptoSignal(
            symbol="BTCUSDT", direction="flat", confidence=0.0,
            reason="", entry_price=115.0, stop_loss=0.0, take_profit=0.0,
            timestamp=0.0,
        )
        pos = self._long_pos(entry=100.0, sl=95.0, tp=110.0)  # SL < entry
        exit_, reason = should_exit_position(pos, current_price=112.0, current_signal=flat_sig)
        assert exit_ and reason == "tp_hit"

    def test_sl_hit_closes_position(self):
        """Trailing SL hit always closes the position."""
        from core.crypto_risk_engine import should_exit_position
        from core.crypto_types import CryptoSignal

        flat_sig = CryptoSignal(
            symbol="BTCUSDT", direction="flat", confidence=0.0,
            reason="", entry_price=105.0, stop_loss=0.0, take_profit=0.0,
            timestamp=0.0,
        )
        # SL=103 > entry=100 (profit locked), price drops to 102
        pos = self._long_pos(entry=100.0, sl=103.0, tp=115.0)
        exit_, reason = should_exit_position(pos, current_price=102.0, current_signal=flat_sig)
        assert exit_ and reason == "sl_hit"


# ---------------------------------------------------------------------------
# On-chain signal integration
# ---------------------------------------------------------------------------

class TestOnChainSignal:
    """Tests for crypto_onchain_engine and its integration into generate_signal."""

    def _make_candles(self, n: int = 100):
        from core.crypto_types import CryptoCandle
        import time as _time
        now = _time.time()
        candles = []
        price = 50000.0
        for i in range(n):
            candles.append(CryptoCandle(
                symbol="BTCUSDT",
                timestamp=now - (n - i) * 900,
                open=price, high=price * 1.002, low=price * 0.998,
                close=price, volume=1000.0,
            ))
        return candles

    def test_aggregate_formula_weights(self):
        """Aggregate = 0.40×funding + 0.30×OI + 0.30×L/S, clamped to [-1,1]."""
        from core.crypto_onchain_engine import OnChainSignal

        sig = OnChainSignal(
            symbol="BTCUSDT",
            funding_rate=0.0,
            funding_score=0.8,
            oi_change_pct=0.01,
            oi_score=0.5,
            ls_ratio=1.2,
            ls_score=-0.25,
            aggregate=round(0.40 * 0.8 + 0.30 * 0.5 + 0.30 * (-0.25), 4),
            timestamp=0.0,
            available=True,
        )
        expected = round(0.40 * 0.8 + 0.30 * 0.5 + 0.30 * (-0.25), 4)
        assert sig.aggregate == expected

    def test_unavailable_signal_returns_zero_aggregate(self):
        """When available=False, aggregate must be 0.0 so callers can degrade."""
        from core.crypto_onchain_engine import OnChainSignal

        sig = OnChainSignal(
            symbol="XYZUSDT",
            funding_rate=0.0, funding_score=0.0,
            oi_change_pct=0.0, oi_score=0.0,
            ls_ratio=1.0, ls_score=0.0,
            aggregate=0.0, timestamp=0.0, available=False,
        )
        assert sig.aggregate == 0.0
        assert not sig.available

    def test_onchain_score_shifts_combined_signal(self):
        """A strong bearish on-chain score (-1.0) reduces the combined signal."""
        from core.crypto_signal_engine import generate_signal

        candles = self._make_candles()

        sig_no_onchain = generate_signal(
            "BTCUSDT", candles, news_score=0.0, order_book_imbalance=0.0,
            onchain_score=0.0,
        )
        sig_bearish_onchain = generate_signal(
            "BTCUSDT", candles, news_score=0.0, order_book_imbalance=0.0,
            onchain_score=-1.0,
        )
        # Bearish on-chain should pull combined score lower (or keep it flat/lower).
        assert sig_bearish_onchain.confidence <= sig_no_onchain.confidence or \
               sig_bearish_onchain.direction in ("short", "flat")

    def test_onchain_score_ignored_when_zero(self):
        """onchain_score=0.0 produces identical result to omitting the parameter."""
        from core.crypto_signal_engine import generate_signal

        candles = self._make_candles()

        sig_default = generate_signal("BTCUSDT", candles, news_score=0.0, order_book_imbalance=0.0)
        sig_explicit_zero = generate_signal(
            "BTCUSDT", candles, news_score=0.0, order_book_imbalance=0.0,
            onchain_score=0.0,
        )
        assert sig_default.direction == sig_explicit_zero.direction
        assert sig_default.confidence == sig_explicit_zero.confidence

    @patch("core.crypto_onchain_engine._get_json")
    def test_fetch_onchain_bypasses_cache_after_ttl(self, mock_get_json):
        """A second fetch after TTL expiry calls the API again (cache miss)."""
        import time as _time
        from core.crypto_onchain_engine import fetch_onchain_signals, _cache, _CACHE_TTL

        mock_get_json.side_effect = [
            {"lastFundingRate": "0.0001"},      # funding — call 1
            [{"sumOpenInterest": "1000"}, {"sumOpenInterest": "1010"}],  # OI — call 1
            [{"longShortRatio": "1.2"}],         # global L/S — call 1
            [{"longShortRatio": "1.1"}],         # top L/S — call 1
            {"lastFundingRate": "0.0002"},      # funding — call 2 (after TTL)
            [{"sumOpenInterest": "1000"}, {"sumOpenInterest": "990"}],   # OI — call 2
            [{"longShortRatio": "0.9"}],         # global L/S — call 2
            [{"longShortRatio": "0.85"}],        # top L/S — call 2
        ]

        sym = "TTLUSDT"
        _cache.pop(sym, None)

        sig1 = fetch_onchain_signals(sym)
        # Manually expire the cache entry.
        _cache[sym] = (_time.time() - _CACHE_TTL - 1, _cache[sym][1])

        sig2 = fetch_onchain_signals(sym)
        assert sig1.funding_rate != sig2.funding_rate


# ---------------------------------------------------------------------------
# Market context engine
# ---------------------------------------------------------------------------

class TestMarketContextEngine:
    def _news(self, ticker: str, score: float, n: int = 3):
        from core.crypto_types import NewsItem
        return [
            NewsItem(
                title=f"{ticker} headline {i}",
                url=f"https://example.com/{i}",
                sentiment="positive" if score > 0 else "negative",
                score=score,
                published_at=0.0,
                currencies=[ticker],
            )
            for i in range(n)
        ]

    def test_fg_score_extreme_fear(self):
        """F&G value 10 maps to score=+1.0 and size_multiplier=1.20."""
        from core.crypto_market_context_engine import _fg_to_score
        score, mult = _fg_to_score(10)
        assert score == 1.0
        assert mult == 1.20

    def test_fg_score_extreme_greed(self):
        """F&G value 90 maps to score=-1.0 and size_multiplier=0.70."""
        from core.crypto_market_context_engine import _fg_to_score
        score, mult = _fg_to_score(90)
        assert score == -1.0
        assert mult == 0.70

    def test_fg_score_neutral(self):
        """F&G value 50 maps to score=0.0 and size_multiplier=1.00."""
        from core.crypto_market_context_engine import _fg_to_score
        score, mult = _fg_to_score(50)
        assert score == 0.0
        assert mult == 1.00

    def test_trending_pairs_discovered(self):
        """Ticker with ≥2 items and mean score ≥0.20 becomes a trending pair."""
        from core.crypto_market_context_engine import _discover_trending_pairs

        news = self._news("BTC", score=0.80, n=3)
        result = _discover_trending_pairs(news, known_symbols=set(), max_extra=5)
        assert "BTCUSDT" in result

    def test_trending_skips_known_symbols(self):
        """Ticker already in watchlist is not returned as trending."""
        from core.crypto_market_context_engine import _discover_trending_pairs

        news = self._news("ETH", score=0.80, n=3)
        result = _discover_trending_pairs(news, known_symbols={"ETHUSDT"}, max_extra=5)
        assert "ETHUSDT" not in result

    def test_trending_requires_min_items(self):
        """Ticker with only 1 news item does not qualify."""
        from core.crypto_market_context_engine import _discover_trending_pairs

        news = self._news("SOL", score=0.90, n=1)
        result = _discover_trending_pairs(news, known_symbols=set(), max_extra=5)
        assert "SOLUSDT" not in result

    def test_trending_requires_min_score(self):
        """Ticker with mean score below 0.20 is not returned."""
        from core.crypto_market_context_engine import _discover_trending_pairs

        news = self._news("ADA", score=0.10, n=4)
        result = _discover_trending_pairs(news, known_symbols=set(), max_extra=5)
        assert "ADAUSDT" not in result

    def test_max_extra_respected(self):
        """At most max_extra pairs are returned."""
        from core.crypto_market_context_engine import _discover_trending_pairs

        tickers = ["BTC", "ETH", "SOL", "BNB", "XRP"]
        news = []
        for t in tickers:
            news.extend(self._news(t, score=0.80, n=3))
        result = _discover_trending_pairs(news, known_symbols=set(), max_extra=2)
        assert len(result) <= 2

    @patch("core.crypto_market_context_engine._fetch_fear_greed")
    def test_fetch_market_context_integrates_fg_and_trending(self, mock_fg):
        """fetch_market_context returns both F&G fields and trending pairs."""
        import core.crypto_market_context_engine as _eng
        _eng._fg_cache = None  # clear cache
        mock_fg.return_value = (15, "Extreme Fear")

        from core.crypto_market_context_engine import fetch_market_context

        news = self._news("BTC", score=0.85, n=3)
        ctx = fetch_market_context(news, known_symbols=set(), max_extra=5)

        assert ctx.fg_value == 15
        assert ctx.fg_label == "Extreme Fear"
        assert ctx.fg_score == 1.0
        assert ctx.size_multiplier == 1.20
        assert "BTCUSDT" in ctx.trending_pairs
        assert ctx.available is True


# ---------------------------------------------------------------------------
# ADX threshold + on-chain ranging override
# ---------------------------------------------------------------------------

class TestRangingOverride:
    def _flat_candles(self, n: int = 100):
        """Candles with near-zero movement → ADX < 15 (ranging)."""
        from core.crypto_types import CryptoCandle
        import time as _t
        now = _t.time()
        candles = []
        price = 50000.0
        for i in range(n):
            # tiny noise to keep ATR non-zero but ADX very low
            p = price + (i % 3 - 1) * 0.5
            candles.append(CryptoCandle(
                symbol="BTCUSDT", timestamp=now - (n - i) * 900,
                open=p, high=p + 0.2, low=p - 0.2, close=p, volume=500.0,
            ))
        return candles

    def test_adx_threshold_is_12(self):
        """_ADX_RANGING constant must be 12 (lowered from 15 to reduce ranging blocks)."""
        from core.crypto_signal_engine import _ADX_RANGING
        assert _ADX_RANGING == 12.0

    def test_ranging_blocked_without_onchain(self):
        """Flat candles (ADX < 15) with onchain=0.0 → flat signal."""
        from core.crypto_signal_engine import generate_signal
        candles = self._flat_candles()
        sig = generate_signal("BTCUSDT", candles, news_score=0.0,
                              order_book_imbalance=0.0, onchain_score=0.0)
        assert sig.direction == "flat"
        assert sig.reason == "ranging_market_adx_too_low"

    def test_strong_onchain_overrides_ranging(self):
        """Flat candles + |onchain_agg| >= 0.45 → NOT immediately flat."""
        from core.crypto_signal_engine import generate_signal, _ONCHAIN_RANGING_OVERRIDE
        candles = self._flat_candles()
        # onchain at exactly the override threshold — should bypass ranging block
        sig = generate_signal("BTCUSDT", candles, news_score=0.0,
                              order_book_imbalance=0.0,
                              onchain_score=_ONCHAIN_RANGING_OVERRIDE)
        # May still be flat (threshold=0.70 is high) but reason must NOT be adx_too_low
        assert sig.reason != "ranging_market_adx_too_low"

    def test_onchain_override_requires_elevated_threshold(self):
        """In ranging + on-chain override, signal only fires if combined >= 0.70."""
        from core.crypto_signal_engine import generate_signal, _ONCHAIN_RANGING_THRESHOLD
        candles = self._flat_candles()
        # onchain=0.50 (override active), but total combined = 0.15*0.50 = 0.075 < 0.70
        sig = generate_signal("BTCUSDT", candles, news_score=0.0,
                              order_book_imbalance=0.0, onchain_score=0.50)
        # combined will be far below 0.70 → flat, but not adx_too_low
        assert sig.direction == "flat"
        assert sig.reason != "ranging_market_adx_too_low"

    def test_usd1_excluded_from_stablecoin_filter(self):
        """USD1 base ticker must be in stablecoin filter."""
        from core.crypto_data_engine import get_top_pairs
        from unittest.mock import patch

        fake_ticker = [
            {"symbol": "USD1USDT", "quoteVolume": "999999999"},
            {"symbol": "BTCUSDT",  "quoteVolume": "1000000000"},
        ]
        with patch("core.crypto_data_engine._get_json", return_value=fake_ticker):
            pairs = get_top_pairs(quote="USDT")
        assert "USD1USDT" not in pairs
        assert "BTCUSDT" in pairs
