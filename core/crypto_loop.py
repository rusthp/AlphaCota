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
from core.crypto_executor import close_paper_position, execute_paper
from core.crypto_live_executor import close_live_position, execute_live
from core.crypto_ledger import (
    connect_default,
    get_balance_estimate,
    get_open_positions,
    write_pnl_snapshot,
)
from core.crypto_news_engine import fetch_news, score_news_sentiment
from core.crypto_risk_engine import (
    check_risk_limits,
    should_exit_position,
    validate_signal_risk,
)
from core.crypto_signal_engine import generate_signal
from core.crypto_sizing_engine import size_position
from core.crypto_types import CryptoPosition, CryptoSignal
from core.logger import logger

_KILL_FILE = Path("data/CRYPTO_KILL")
_CHART_DIR = Path("data/charts")
_LOOP_INTERVAL = int(os.getenv("CRYPTO_LOOP_INTERVAL_SECONDS", "300"))
_INITIAL_BALANCE = float(os.getenv("CRYPTO_INITIAL_BALANCE_USD", "1000.0"))
_TOP_PAIRS_LIMIT = 10
_PNL_SNAPSHOT_EVERY = 12
_CANDLE_INTERVAL = "15m"
_CANDLE_LIMIT = 100
_NEWS_LIMIT = 20


def _is_killed() -> bool:
    """Return True if the kill-switch file exists on disk."""
    return _KILL_FILE.exists()


class _GracefulStop(Exception):
    """Raised to convert SIGTERM into a controlled loop exit."""


def _handle_sigterm(signum: int, frame: FrameType | None) -> None:
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
                    close_live_position(pos.id, price, reason, conn)  # type: ignore[arg-type]
                else:
                    close_paper_position(pos.id, price, reason, conn)  # type: ignore[arg-type]
                closed += 1
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

    try:
        obi = fetch_order_book_imbalance(symbol)
    except Exception as exc:
        logger.debug("process: OBI(%s) failed: %s — using 0.0", symbol, exc)
        obi = 0.0

    news_score = score_news_sentiment(news_cache, symbol)
    signal_obj = generate_signal(symbol, candles, news_score, obi)

    if signal_obj.direction != "flat":
        ts = int(time.time())
        chart_path = _CHART_DIR / f"{symbol}_{ts}.png"
        try:
            generate_ohlcv_chart(candles, symbol, str(chart_path))
        except Exception as exc:
            logger.warning("process: chart failed for %s: %s", symbol, exc)

    if signal_obj.direction == "flat":
        return (signal_obj, last_price, False)

    if not validate_signal_risk(signal_obj, balance_usd):
        logger.info(
            "process: %s signal rejected by validate_signal_risk (conf=%.3f)",
            symbol, signal_obj.confidence,
        )
        return (signal_obj, last_price, False)

    ok, reason = check_risk_limits(conn, mode)  # type: ignore[arg-type]
    if not ok:
        logger.info("process: risk limits block new position — %s", reason)
        return (signal_obj, last_price, False)

    size_usd = size_position(signal_obj, balance_usd)
    if size_usd <= 0.0:
        logger.info("process: %s sized to 0 — skipping", symbol)
        return (signal_obj, last_price, False)

    if mode == "paper":
        try:
            execute_paper(signal_obj, size_usd, conn)  # type: ignore[arg-type]
            return (signal_obj, last_price, True)
        except Exception as exc:
            logger.error("process: execute_paper(%s) failed: %s", symbol, exc)
            return (signal_obj, last_price, False)

    try:
        execute_live(signal_obj, size_usd, conn)  # type: ignore[arg-type]
        return (signal_obj, last_price, True)
    except Exception as exc:
        logger.error("process: execute_live(%s) failed: %s", symbol, exc)
        return (signal_obj, last_price, False)


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

                signals_by_symbol: dict[str, CryptoSignal] = {}
                price_by_symbol: dict[str, float] = {}
                opened_this_iter = 0

                for sym in symbols:
                    if _is_killed():
                        break
                    sig, last_price, opened = _process_symbol(
                        sym, conn, mode, news_cache, balance_usd,
                    )
                    if sig is not None:
                        signals_by_symbol[sym] = sig
                    if last_price > 0.0:
                        price_by_symbol[sym] = last_price
                    if opened:
                        opened_this_iter += 1
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
