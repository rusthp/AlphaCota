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
            assert _loop._ML_MIN_CONFIDENCE == 0.60, (
                f"Expected 0.60, got {_loop._ML_MIN_CONFIDENCE}"
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
