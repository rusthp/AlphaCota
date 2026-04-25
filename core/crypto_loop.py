"""
core/crypto_loop.py — Autonomous crypto trading loop.

Run as:
    python -m core.crypto_loop [--mode paper|live] [--iterations N]

Iteration flow:
    1. Check kill-switch (data/CRYPTO_KILL) and exit if present.
    2. Scan top pairs by 24h quote volume (top-10 cut).
    3. For each pair: fetch candles + order book + news then generate a signal.
    4. Risk check, Kelly-size position, then execute (paper) if signal is strong.
    5. Monitor all open positions and exit on SL / TP / signal-flip.
    6. Generate chart PNGs to data/charts/ for each non-flat signal.
    7. Every 12 iterations, write a PnL snapshot.
    8. Sleep CRYPTO_LOOP_INTERVAL_SECONDS (default 300) and loop.

Graceful SIGTERM handling converts to an in-loop exception so open paper
orders are reconciled and the connection is closed cleanly.

Live trading is not wired in this module: the live executor is implemented
separately. If --mode=live is passed while no live executor is installed,
this loop logs an error and takes no exchange actions for that cycle.
"""

from __future__ import annotations

import argparse
import os
import signal
import time
from pathlib import Path
from types import FrameType

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from core.crypto_chart_engine import generate_ohlcv_chart
from core.crypto_data_engine import (
    fetch_candles,
    fetch_order_book_imbalance,
    fetch_ticker_price,
    get_top_pairs,
)
from core.logger import logger
from core.crypto_executor import close_paper_position, execute_paper
try:
    from core.crypto_live_executor import close_live_position, execute_live
except Exception as _live_import_err:  # missing Binance SDK or key
    logger.warning("crypto_loop: live executor unavailable — %s", _live_import_err)

    def execute_live(*_a, **_kw):  # type: ignore[misc]
        raise RuntimeError("Live executor not installed")

    def close_live_position(*_a, **_kw):  # type: ignore[misc]
        raise RuntimeError("Live executor not installed")
from core.crypto_ledger import (
    connect_default,
    get_balance_estimate,
    get_daily_pnl,
    get_open_positions,
    write_pnl_snapshot,
)
from core.crypto_news_engine import fetch_news, score_news_sentiment
from core.crypto_risk_engine import (
    check_risk_limits,
    should_exit_position,
    validate_signal_risk,
)
from core.crypto_signal_engine import generate_signal, get_adaptive_multipliers
from core.crypto_sizing_engine import size_position
from core.crypto_types import CryptoPosition, CryptoSignal

try:
    from core.crypto_ml_model import get_confidence as _ml_get_confidence
    _ML_AVAILABLE = True
except Exception as _ml_import_err:
    logger.warning("crypto_loop: ML model unavailable — %s", _ml_import_err)
    _ML_AVAILABLE = False

_ML_MIN_CONFIDENCE = float(os.getenv("CRYPTO_ML_MIN_CONFIDENCE", "0.60"))
from core.crypto_telegram import (
    notify_position_opened,
    notify_position_closed,
    notify_circuit_breaker,
    notify_daily_summary,
)

_KILL_FILE = Path("data/CRYPTO_KILL")
_CHART_DIR = Path("data/charts")
_CONFIG_FILE = Path("data/crypto_bot_config.json")
_LOOP_INTERVAL = int(os.getenv("CRYPTO_LOOP_INTERVAL_SECONDS", "300"))
_INITIAL_BALANCE = float(os.getenv("CRYPTO_INITIAL_BALANCE_USD", "1000.0"))
_TOP_PAIRS_LIMIT = 10
_PNL_SNAPSHOT_EVERY = 12
_CANDLE_INTERVAL = "15m"
_CANDLE_LIMIT = 100
_NEWS_LIMIT = 20
# Trigger a feedback re-train every N iterations (≈ 7 days at 5-min candles).
_FEEDBACK_RETRAIN_EVERY = int(os.getenv("CRYPTO_FEEDBACK_RETRAIN_EVERY", "2016"))

try:
    from core.crypto_feedback_trainer import retrain_if_due as _retrain_if_due
    _FEEDBACK_TRAINER_AVAILABLE = True
except Exception as _fb_import_err:
    logger.debug("crypto_loop: feedback trainer unavailable — %s", _fb_import_err)
    _FEEDBACK_TRAINER_AVAILABLE = False


def _load_bot_config() -> dict:
    """Load TP/SL multipliers and strategy from the shared config file."""
    defaults: dict = {"tp_mult": 3.0, "sl_mult": 1.5, "strategy": "combined"}
    if _CONFIG_FILE.exists():
        import json as _json
        try:
            raw = _json.loads(_CONFIG_FILE.read_text())
            return {
                "tp_mult": float(raw.get("tp_mult", defaults["tp_mult"])),
                "sl_mult": float(raw.get("sl_mult", defaults["sl_mult"])),
                "strategy": str(raw.get("strategy", defaults["strategy"])),
            }
        except Exception:
            pass
    return defaults


def _is_killed() -> bool:
    """Return True if the kill-switch file exists on disk."""
    return _KILL_FILE.exists()


class _GracefulStop(Exception):
    """Raised to convert SIGTERM into a controlled loop exit."""


def _handle_sigterm(signum: int, _frame: FrameType | None) -> None:
    """Signal handler: raise inside the loop so finally-blocks run."""
    raise _GracefulStop(f"signal {signum} received")


def _monitor_and_exit_positions(
    positions: list[CryptoPosition],
    signals_by_symbol: dict[str, CryptoSignal],
    price_by_symbol: dict[str, float],
    conn: object,
    mode: str,
) -> int:
    """Check each open position against SL/TP/signal-flip and close as needed.

    Positions whose symbol has no fresh signal this tick use a standalone
    ticker-price fetch. The number of closed positions is returned.
    """
    if mode not in ("paper", "live"):
        return 0

    closed = 0
    for pos in positions:
        price = price_by_symbol.get(pos.symbol)
        if price is None or price <= 0.0:
            try:
                price = fetch_ticker_price(pos.symbol)
            except Exception as exc:
                logger.warning(
                    "monitor: cannot price %s (%s) — skipping", pos.symbol, exc
                )
                continue
            price_by_symbol[pos.symbol] = price

        sig = signals_by_symbol.get(pos.symbol)
        if sig is None:
            sig = CryptoSignal(
                symbol=pos.symbol,
                direction="flat",
                confidence=0.0,
                reason="no_fresh_signal",
                entry_price=price,
                stop_loss=0.0,
                take_profit=0.0,
                timestamp=time.time(),
            )

        should_exit, reason = should_exit_position(pos, price, sig)
        if should_exit:
            try:
                if mode == "live":
                    trade = close_live_position(pos.id, price, reason, conn)  # type: ignore[arg-type]
                else:
                    trade = close_paper_position(pos.id, price, reason, conn)  # type: ignore[arg-type]
                closed += 1
                notify_position_closed(trade, "", mode)
            except Exception as exc:
                logger.error(
                    "monitor: failed to close %s (%s): %s",
                    pos.symbol, pos.id[:8], exc,
                )
    return closed


def _process_symbol(
    symbol: str,
    conn: object,
    mode: str,
    news_cache: list,
    balance_usd: float,
    bot_config: dict | None = None,
) -> tuple[CryptoSignal | None, float, bool]:
    """Run the full per-symbol pipeline and, when allowed, open a new position.

    Returns:
        (signal, last_price, opened):
            - signal: generated CryptoSignal (may be flat) or None on fetch failure.
            - last_price: most recent close price (0.0 on fetch failure).
            - opened: True when a new paper position was opened this tick.
    """
    try:
        candles = fetch_candles(symbol, interval=_CANDLE_INTERVAL, limit=_CANDLE_LIMIT)
    except Exception as exc:
        logger.warning("process: fetch_candles(%s) failed: %s", symbol, exc)
        return (None, 0.0, False)

    if len(candles) < 50:
        logger.info("process: %s — only %d candles, skipping", symbol, len(candles))
        return (None, 0.0, False)

    last_price = candles[-1].close

    # Higher-timeframe trend filter: 4H candles for EMA50/EMA200 trend bias.
    htf_candles = None
    try:
        htf_candles = fetch_candles(symbol, interval="4h", limit=210)
    except Exception as exc:
        logger.debug("process: 4H fetch(%s) failed: %s — skipping HTF filter", symbol, exc)

    try:
        obi = fetch_order_book_imbalance(symbol)
    except Exception as exc:
        logger.debug("process: OBI(%s) failed: %s — using 0.0", symbol, exc)
        obi = 0.0

    news_score = score_news_sentiment(news_cache, symbol)
    cfg = bot_config or {}

    # Adaptive SL/TP multipliers — computed from recent win rate.
    # Falls back gracefully to static config or module defaults when
    # there are fewer than 10 trades in the DB.
    try:
        adap_sl, adap_tp = get_adaptive_multipliers(conn, mode)  # type: ignore[arg-type]
    except Exception as exc:
        logger.debug("process: adaptive multipliers unavailable (%s) — using config", exc)
        adap_sl = cfg.get("sl_mult")
        adap_tp = cfg.get("tp_mult")

    logger.debug(
        "process: %s adaptive multipliers sl=%.3f tp=%.3f",
        symbol, adap_sl or 1.5, adap_tp or 3.0,
    )

    signal_obj = generate_signal(
        symbol, candles, news_score, obi,
        sl_mult=adap_sl,
        tp_mult=adap_tp,
        htf_candles=htf_candles,
    )

    if signal_obj.direction != "flat":
        ts = int(time.time())
        chart_path = _CHART_DIR / f"{symbol}_{ts}.png"
        try:
            generate_ohlcv_chart(candles, symbol, str(chart_path))
        except Exception as exc:
            logger.warning("process: chart failed for %s: %s", symbol, exc)

    if signal_obj.direction == "flat":
        logger.info("process: %s flat — %s", symbol, signal_obj.reason)
        return (signal_obj, last_price, False)

    if _ML_AVAILABLE:
        try:
            ml_sig = _ml_get_confidence(symbol, _CANDLE_INTERVAL)
            if ml_sig.direction != signal_obj.direction:
                logger.info(
                    "process: %s ML disagrees (tech=%s ml=%s conf=%.2f) — skipping",
                    symbol, signal_obj.direction, ml_sig.direction, ml_sig.confidence,
                )
                return (signal_obj, last_price, False)
            if ml_sig.confidence < _ML_MIN_CONFIDENCE:
                logger.info(
                    "process: %s ML confidence too low (%.2f < %.2f) — skipping",
                    symbol, ml_sig.confidence, _ML_MIN_CONFIDENCE,
                )
                return (signal_obj, last_price, False)
            logger.info(
                "process: %s ML confirms %s (conf=%.2f)",
                symbol, ml_sig.direction, ml_sig.confidence,
            )
        except Exception as exc:
            logger.debug("process: ML check skipped for %s: %s", symbol, exc)

    if not validate_signal_risk(signal_obj, balance_usd):
        logger.info(
            "process: %s signal rejected by validate_signal_risk (conf=%.3f)",
            symbol, signal_obj.confidence,
        )
        return (signal_obj, last_price, False)

    ok, reason = check_risk_limits(conn, mode)  # type: ignore[arg-type]
    if not ok:
        logger.info("process: risk limits block new position — %s", reason)
        if reason.startswith("daily_loss_cap_hit"):
            daily_loss = get_daily_pnl(conn, mode)  # type: ignore[arg-type]
            notify_circuit_breaker(reason, daily_loss)
        return (signal_obj, last_price, False)

    size_usd = size_position(signal_obj, balance_usd)
    if size_usd <= 0.0:
        logger.info("process: %s sized to 0 — skipping", symbol)
        return (signal_obj, last_price, False)

    if mode == "paper":
        try:
            execute_paper(signal_obj, size_usd, conn)  # type: ignore[arg-type]
            notify_position_opened(signal_obj, size_usd, signal_obj.reason, mode)
            return (signal_obj, last_price, True)
        except Exception as exc:
            logger.error("process: execute_paper(%s) failed: %s", symbol, exc)
            return (signal_obj, last_price, False)

    try:
        execute_live(signal_obj, size_usd, conn)  # type: ignore[arg-type]
        notify_position_opened(signal_obj, size_usd, signal_obj.reason, mode)
        return (signal_obj, last_price, True)
    except Exception as exc:
        logger.error("process: execute_live(%s) failed: %s", symbol, exc)
        return (signal_obj, last_price, False)


def _send_daily_summary(conn: object, mode: str) -> None:
    """Fetch today's stats and fire a Telegram daily summary."""
    try:
        pnl = get_daily_pnl(conn, mode)  # type: ignore[arg-type]
        rows = conn.execute(  # type: ignore[union-attr]
            "SELECT COUNT(*) AS n, "
            "SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) AS wins "
            "FROM crypto_trades WHERE mode = ? "
            "AND date(closed_at, 'unixepoch') = date('now')",
            (mode,),
        ).fetchone()
        total = int(rows["n"]) if rows and rows["n"] else 0
        wins = int(rows["wins"]) if rows and rows["wins"] else 0
        win_rate = (wins / total * 100.0) if total > 0 else 0.0
        balance = get_balance_estimate(conn, _INITIAL_BALANCE, mode)  # type: ignore[arg-type]
        notify_daily_summary(pnl, total, win_rate, balance, mode)
    except Exception as exc:
        logger.warning("_send_daily_summary: %s", exc)


def _cancel_pending_paper_orders(conn: object, mode: str) -> None:
    """On shutdown, mark any pending paper orders as cancelled."""
    if mode != "paper":
        return
    try:
        conn.execute(  # type: ignore[union-attr]
            "UPDATE crypto_orders SET status='cancelled' WHERE status='pending' AND mode='paper'"
        )
        conn.commit()  # type: ignore[union-attr]
    except Exception as exc:
        logger.warning("_cancel_pending_paper_orders: %s", exc)


def run_loop(mode: str = "paper", max_iterations: int = 0) -> None:
    """Main autonomous loop entry point.

    Args:
        mode: "paper" or "live". Live mode requires an installed live
              executor module; without it, this loop logs an error and
              takes no exchange actions for the cycle.
        max_iterations: 0 = run forever, otherwise stop after N iterations.
    """
    if mode not in ("paper", "live"):
        logger.error("run_loop: invalid mode '%s' — refusing to start", mode)
        return

    _CHART_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect_default()
    signal.signal(signal.SIGTERM, _handle_sigterm)

    iteration = 0
    start_time = time.time()
    logger.info(
        "run_loop: starting mode=%s interval=%ds max_iter=%d init_balance=%.2f",
        mode, _LOOP_INTERVAL, max_iterations, _INITIAL_BALANCE,
    )

    try:
        while True:
            if _is_killed():
                logger.warning("run_loop: kill-switch present — stopping")
                break
            if max_iterations > 0 and iteration >= max_iterations:
                logger.info("run_loop: reached max_iterations=%d", max_iterations)
                break

            iteration += 1
            logger.info("run_loop: iteration %d start", iteration)

            try:
                top = get_top_pairs(quote="USDT")
                if not top:
                    logger.info("run_loop: no pairs discovered — sleeping")
                    time.sleep(_LOOP_INTERVAL)
                    continue
                symbols = top[:_TOP_PAIRS_LIMIT]

                base_tickers: list[str] = []
                for s in symbols:
                    base = s.replace("USDT", "") if s.endswith("USDT") else s
                    if base:
                        base_tickers.append(base)
                try:
                    news_cache = fetch_news(currencies=base_tickers, limit=_NEWS_LIMIT)
                except Exception as exc:
                    logger.warning("run_loop: fetch_news failed: %s", exc)
                    news_cache = []

                balance_usd = get_balance_estimate(conn, _INITIAL_BALANCE, mode)
                bot_config = _load_bot_config()

                # Build set of symbols that already have an open position so
                # _process_symbol never opens a second position for the same pair.
                existing_positions = get_open_positions(conn, mode)
                open_symbols: set[str] = {p.symbol for p in existing_positions}

                signals_by_symbol: dict[str, CryptoSignal] = {}
                price_by_symbol: dict[str, float] = {}
                opened_this_iter = 0

                for sym in symbols:
                    if _is_killed():
                        break
                    if sym in open_symbols:
                        logger.debug("run_loop: %s already has open position — skipping entry", sym)
                        continue
                    sig, last_price, opened = _process_symbol(
                        sym, conn, mode, news_cache, balance_usd, bot_config,
                    )
                    if sig is not None:
                        signals_by_symbol[sym] = sig
                    if last_price > 0.0:
                        price_by_symbol[sym] = last_price
                    if opened:
                        opened_this_iter += 1
                        open_symbols.add(sym)
                        balance_usd = get_balance_estimate(conn, _INITIAL_BALANCE, mode)

                open_positions = get_open_positions(conn, mode)
                closed_this_iter = _monitor_and_exit_positions(
                    open_positions, signals_by_symbol, price_by_symbol, conn, mode,
                )

                logger.info(
                    "run_loop: iter=%d symbols=%d opened=%d closed=%d balance=%.2f",
                    iteration, len(symbols), opened_this_iter, closed_this_iter,
                    get_balance_estimate(conn, _INITIAL_BALANCE, mode),
                )

                if iteration % _PNL_SNAPSHOT_EVERY == 0:
                    write_pnl_snapshot(conn, mode)
                    _send_daily_summary(conn, mode)

                # Periodic feedback re-training (weekly by default).
                if (
                    _FEEDBACK_TRAINER_AVAILABLE
                    and _FEEDBACK_RETRAIN_EVERY > 0
                    and iteration % _FEEDBACK_RETRAIN_EVERY == 0
                ):
                    logger.info("run_loop: triggering scheduled feedback re-train (iter=%d)", iteration)
                    try:
                        retrained = _retrain_if_due(conn, mode=mode)  # type: ignore[arg-type]
                        if retrained:
                            logger.info("run_loop: feedback re-train completed at iter=%d", iteration)
                    except Exception as _fb_exc:
                        logger.warning("run_loop: feedback re-train failed: %s", _fb_exc)

            except _GracefulStop:
                raise
            except Exception as exc:
                logger.error("run_loop: iteration %d unhandled: %s", iteration, exc)

            if max_iterations == 0 or iteration < max_iterations:
                logger.info("run_loop: sleeping %ds", _LOOP_INTERVAL)
                time.sleep(_LOOP_INTERVAL)

    except _GracefulStop as exc:
        logger.info("run_loop: graceful stop — %s", exc)
    finally:
        _cancel_pending_paper_orders(conn, mode)
        write_pnl_snapshot(conn, mode)
        try:
            conn.close()
        except Exception:
            pass
        logger.info(
            "run_loop: stopped after %d iterations (%.1fs)",
            iteration, time.time() - start_time,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AlphaCota autonomous crypto trading loop")
    parser.add_argument("--mode", choices=["paper", "live"], default="paper")
    parser.add_argument(
        "--iterations",
        type=int,
        default=0,
        help="Max iterations (0 = run forever)",
    )
    args = parser.parse_args()
    run_loop(mode=args.mode, max_iterations=args.iterations)
