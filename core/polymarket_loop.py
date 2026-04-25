"""
core/polymarket_loop.py — Main Polymarket trading loop.

Run as: python -m core.polymarket_loop [--mode paper|live] [--iterations N]

Iteration flow:
    1. Check kill-switch file → exit if present
    2. Check wallet health → skip cycle if unhealthy
    3. Discover markets
    4. Generate trade decisions
    5. Execute approved trades
    6. Persist ledger
    7. Monitor open positions → exit ones that trigger rules
    8. Sleep LOOP_INTERVAL_SECONDS (default 300)
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

from core.logger import logger

_KILL_FILE = Path("data/POLYMARKET_KILL")
_LOOP_INTERVAL = int(os.getenv("LOOP_INTERVAL_SECONDS", "300"))
_MAX_ITERATIONS = 0


def _is_killed() -> bool:
    """Return True if the kill-switch file exists."""
    return _KILL_FILE.exists()


class _GracefulStop(Exception):
    pass


def _handle_sigterm(signum: int, frame: FrameType | None) -> None:
    raise _GracefulStop("SIGTERM received")


def _write_pnl_snapshot(conn: object, mode: str) -> None:
    """Write a PnL snapshot to pm_pnl_snapshots."""
    from datetime import date

    today = date.today().isoformat()
    try:
        open_count = conn.execute("SELECT COUNT(*) FROM pm_positions").fetchone()[0]  # type: ignore[union-attr]
        realized = conn.execute(  # type: ignore[union-attr]
            "SELECT COALESCE(SUM(realized_pnl), 0) FROM pm_trades WHERE date(closed_at, 'unixepoch') = ?",
            (today,),
        ).fetchone()[0]

        usdc = conn.execute(  # type: ignore[union-attr]
            "SELECT COALESCE(SUM(size_usd), 0) FROM pm_positions"
        ).fetchone()[0]

        conn.execute(  # type: ignore[union-attr]
            """
            INSERT OR REPLACE INTO pm_pnl_snapshots
                (snapshot_date, equity_usd, open_positions, daily_pnl, mode, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (today, float(usdc), int(open_count), float(realized), mode, time.time()),
        )
        conn.commit()  # type: ignore[union-attr]
    except Exception as exc:
        logger.warning("_write_pnl_snapshot failed: %s", exc)


def _cancel_all_pending(conn: object, mode: str) -> None:
    """On shutdown, mark pending paper orders as cancelled."""
    if mode != "paper":
        return
    try:
        now = time.time()
        conn.execute(  # type: ignore[union-attr]
            "UPDATE pm_orders SET status='cancelled', updated_at=? WHERE status='pending' AND mode='paper'",
            (now,),
        )
        conn.commit()  # type: ignore[union-attr]
        logger.info("_cancel_all_pending: paper orders cancelled")
    except Exception as exc:
        logger.warning("_cancel_all_pending failed: %s", exc)


def run_loop(
    config: object | None = None,
    mode: str = "paper",
    max_iterations: int = 0,
) -> None:
    """Run the Polymarket trading loop.

    Args:
        config: OperationalConfig (loaded from env if None).
        mode: "paper" or "live".
        max_iterations: Maximum iterations (0 = run forever).
    """
    from core.config import settings
    from core.polymarket_client import discover_markets, get_wallet_health
    from core.polymarket_decision_engine import generate_trade_decisions
    from core.polymarket_exit_engine import should_exit
    from core.polymarket_ledger import init_db
    from core.polymarket_monitor import monitor_positions
    from core.polymarket_paper_executor import close_paper_position, execute_paper

    env_mode = os.getenv("POLYMARKET_MODE", "paper")
    if mode != env_mode and env_mode in ("paper", "live"):
        logger.error(
            "run_loop: --mode=%s conflicts with POLYMARKET_MODE=%s — refusing to start",
            mode, env_mode,
        )
        return

    cfg = config or settings
    conn = init_db()
    start_time = time.time()
    iteration = 0
    consecutive_errors = 0
    clob_client: object | None = None
    _WALLET_RERANK_EVERY = 288  # once per day at 5-min cadence

    if mode == "live":
        from core.polymarket_preflight import run_preflight
        preflight = run_preflight(cfg)
        if not preflight.ok:
            logger.error("run_loop: preflight failed — %s", preflight.failures)
            conn.close()  # type: ignore[union-attr]
            return

    signal.signal(signal.SIGTERM, _handle_sigterm)

    logger.info("run_loop: starting mode=%s max_iterations=%d", mode, max_iterations)

    try:
        while True:
            if _is_killed():
                logger.warning("run_loop: kill-switch file detected — stopping")
                break

            if max_iterations > 0 and iteration >= max_iterations:
                logger.info("run_loop: reached max_iterations=%d — stopping", max_iterations)
                break

            if consecutive_errors >= 3 and mode == "live":
                from core.polymarket_preflight import run_preflight
                pf = run_preflight(cfg, clob_client)
                if not pf.ok:
                    logger.error("run_loop: preflight re-check failed — stopping: %s", pf.failures)
                    break
                consecutive_errors = 0

            iteration += 1
            logger.info("run_loop: iteration %d start", iteration)

            try:
                wallet = get_wallet_health()
                if not wallet.is_healthy:
                    logger.warning("run_loop: wallet unhealthy — skipping cycle")
                    time.sleep(min(_LOOP_INTERVAL, 60))
                    continue

                markets = discover_markets(limit=5)
                if not markets:
                    logger.info("run_loop: no markets discovered — sleeping")
                    time.sleep(_LOOP_INTERVAL)
                    continue

                decisions = generate_trade_decisions(
                    markets=markets,
                    config=cfg,
                    wallet_health=wallet,
                )

                for decision in decisions:
                    if _is_killed():
                        break
                    try:
                        if mode == "live" and clob_client is not None:
                            from core.polymarket_executor import execute_live
                            execute_live(decision, conn, clob_client)
                        else:
                            execute_paper(decision, conn)
                        consecutive_errors = 0
                    except Exception as exc:
                        consecutive_errors += 1
                        logger.error("run_loop: execute failed: %s", exc)

                statuses = monitor_positions(conn)
                for status in statuses:
                    exit_dec = should_exit(
                        position=None,  # type: ignore[arg-type]
                        status=status,
                        config=cfg,
                    )
                    if exit_dec.should_exit:
                        try:
                            if mode == "live" and clob_client is not None:
                                from core.polymarket_executor import close_live_position
                                close_live_position(status.position_id, conn, clob_client)
                            else:
                                close_paper_position(status.position_id, conn)
                        except Exception as exc:
                            logger.error("run_loop: close failed %s: %s", status.position_id, exc)

                _write_pnl_snapshot(conn, mode)

                if iteration % _WALLET_RERANK_EVERY == 0:
                    try:
                        from core.polymarket_wallet_ranker import (
                            rerank_wallets,
                            update_wallet_alpha_scores,
                        )
                        from core.polymarket_wallet_tracker import WalletTracker
                        tracker = WalletTracker()
                        rankings = rerank_wallets(conn, tracker)
                        update_wallet_alpha_scores(rankings)
                        logger.info("run_loop: wallet rerank complete (%d wallets)", len(rankings))
                    except Exception as exc:
                        logger.warning("run_loop: wallet rerank failed: %s", exc)

            except _GracefulStop:
                raise
            except Exception as exc:
                logger.error("run_loop: iteration %d error: %s", iteration, exc)

            if max_iterations == 0 or iteration < max_iterations:
                logger.info("run_loop: sleeping %ds", _LOOP_INTERVAL)
                time.sleep(_LOOP_INTERVAL)

    except _GracefulStop as exc:
        logger.info("run_loop: graceful stop — %s", exc)
    finally:
        _cancel_all_pending(conn, mode)
        _write_pnl_snapshot(conn, mode)
        conn.close()  # type: ignore[union-attr]
        logger.info("run_loop: stopped after %d iterations (%.1fs)", iteration, time.time() - start_time)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Polymarket paper/live trading loop")
    parser.add_argument("--mode", choices=["paper", "live"], default="paper")
    parser.add_argument("--iterations", type=int, default=0,
                        help="Max iterations (0 = run forever)")
    args = parser.parse_args()
    run_loop(mode=args.mode, max_iterations=args.iterations)
