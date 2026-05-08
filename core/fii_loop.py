"""
core/fii_loop.py — Autonomous FII scoring and alert loop.

Run as:
    python -m core.fii_loop [--interval SECONDS]

Iteration flow:
    1. Fetch fundamentals for all FIIs in universe (StatusInvest + cache).
    2. Load last price and monthly dividend via yfinance.
    3. Calculate Alpha Score for each FII via score_engine.
    4. Compare against previous cycle scores (persisted in fii_loop_state.json).
    5. Fire Telegram alerts for:
         - BUY:   score >= 72 and was < 72 in previous cycle
         - SELL:  score <  45 and was >= 45 in previous cycle
         - DROP:  score fell >= 15 points in one cycle (regardless of threshold)
    6. At first iteration each day: send Top-5 ranking summary.
    7. Sleep INTERVAL seconds (default 21600 = 6h) and repeat.

State file: data/fii_loop_state.json
"""

from __future__ import annotations

import argparse
import json
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

import datetime

from data.fundamentals_scraper import fetch_fundamentals_bulk
from data.data_bridge import load_last_price, load_monthly_dividend
from data.universe import get_universe, get_sector_map
from core.score_engine import rank_fiis
from core.fii_telegram import (
    notify_fii_buy,
    notify_fii_sell,
    notify_fii_ranking,
    notify_fii_loop_error,
    send_message,
)
from core.fii_ledger import connect_fii_db, save_fii_snapshot
from core.logger import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_INTERVAL = int(os.getenv("FII_LOOP_INTERVAL_SECONDS", "21600"))  # 6h
_STATE_FILE = Path("data/fii_loop_state.json")

_BUY_THRESHOLD  = 72.0   # score >= 72 → BUY alert
_SELL_THRESHOLD = 45.0   # score <  45 → SELL/exit alert
_DROP_ALERT     = 15.0   # drop >= 15 pts in one cycle → deterioration alert

# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    """Load previous scores and metadata from state file."""
    try:
        if _STATE_FILE.exists():
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("fii_loop: state load failed: %s", exc)
    return {"scores": {}, "last_ranking_date": ""}


def _save_state(state: dict) -> None:
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("fii_loop: state save failed: %s", exc)


# ---------------------------------------------------------------------------
# Core iteration
# ---------------------------------------------------------------------------

def _run_iteration(state: dict, iteration: int) -> dict:
    """Run one scoring cycle. Returns updated state."""
    logger.info("fii_loop: iteration %d start", iteration)

    # --- Universe ---
    universe = get_universe(ifix_only=True)
    sector_map = get_sector_map()
    tickers = [fii["ticker"] for fii in universe]
    name_map = {fii["ticker"]: fii["nome"] for fii in universe}

    # --- Fundamentals (cached 24h, rate-limited internally) ---
    logger.info("fii_loop: fetching fundamentals for %d FIIs", len(tickers))
    fundamentals = fetch_fundamentals_bulk(tickers)

    # --- Prices + build scoring payload ---
    fiis_for_ranking: list[dict] = []
    for ticker in tickers:
        fund = fundamentals.get(ticker, {})
        price, _ = load_last_price(ticker)
        monthly_div, _ = load_monthly_dividend(ticker)

        # Prefer scraper DY; fall back to yfinance-derived DY
        dy = fund.get("dividend_yield") or 0.0
        if dy == 0.0 and price > 0 and monthly_div > 0:
            dy = (monthly_div * 12) / price

        fiis_for_ranking.append({
            "ticker": ticker,
            "dividend_yield": dy,
            "dividend_consistency": fund.get("dividend_consistency") or 50.0,
            "pvp": fund.get("pvp") or 1.0,
            "debt_ratio": fund.get("debt_ratio"),
            "vacancy_rate": fund.get("vacancy_rate"),
            "revenue_growth_12m": fund.get("revenue_growth_12m") or 0.0,
            "earnings_growth_12m": fund.get("earnings_growth_12m") or 0.0,
            "news_sentiment": fund.get("news_sentiment") or 0.0,
            # Pass-through for alert messages
            "_price": price,
            "_monthly_div": monthly_div,
        })

    # --- Score ---
    ranked = rank_fiis(fiis_for_ranking)
    logger.info("fii_loop: scored %d FIIs", len(ranked))

    # --- Snapshot warehouse: persist raw + scores for every FII every day ---
    today_str = datetime.date.today().isoformat()
    snap_conn = connect_fii_db()
    now_ts = time.time()
    for fii in ranked:
        fund = fundamentals.get(fii["ticker"], {})
        save_fii_snapshot(snap_conn, {
            "ticker": fii["ticker"],
            "date": today_str,
            "price": fii.get("_price", 0.0),
            "monthly_div": fii.get("_monthly_div", 0.0),
            "dividend_yield": fii.get("dividend_yield", 0.0),
            "pvp": fii.get("pvp", 1.0),
            "dividend_consistency": fii.get("dividend_consistency", 50.0),
            "debt_ratio": fii.get("debt_ratio"),
            "vacancy_rate": fii.get("vacancy_rate"),
            "revenue_growth_12m": fii.get("revenue_growth_12m", 0.0),
            "earnings_growth_12m": fii.get("earnings_growth_12m", 0.0),
            "daily_liquidity": fund.get("daily_liquidity", 0.0),
            "news_sentiment": fii.get("news_sentiment", 0.0),
            "alpha_score": fii.get("alpha_score", 0.0),
            "income_score": fii.get("income_score", 0.0),
            "valuation_score": fii.get("valuation_score", 0.0),
            "risk_score": fii.get("risk_score", 50.0),
            "growth_score": fii.get("growth_score", 0.0),
            "news_sentiment_score": fii.get("news_sentiment_score", 50.0),
            "data_source": fund.get("_source", "unknown"),
            "created_at": now_ts,
        })
    snap_conn.close()
    logger.info("fii_loop: snapshots saved for %d FIIs (%s)", len(ranked), today_str)

    prev_scores: dict[str, float] = state.get("scores", {})
    new_scores: dict[str, float] = {}
    alerted: list[str] = []

    for fii in ranked:
        ticker   = fii["ticker"]
        score    = fii["alpha_score"]
        prev     = prev_scores.get(ticker)
        dy       = fii["dividend_yield"]
        pvp      = fii["pvp"]
        price    = fii.get("_price", 0.0)
        setor    = sector_map.get(ticker, "Outros")
        nome     = name_map.get(ticker, ticker)
        i_score  = fii.get("income_score", 0.0)
        v_score  = fii.get("valuation_score", 0.0)
        r_score  = fii.get("risk_score", 50.0)

        new_scores[ticker] = score

        if prev is None:
            # First time seeing this ticker — no alert, just record
            logger.info("fii_loop: %s first-seen score=%.1f", ticker, score)
            continue

        delta = score - prev

        # BUY: crossed above threshold
        if score >= _BUY_THRESHOLD and prev < _BUY_THRESHOLD:
            trigger = f"score cruzou {_BUY_THRESHOLD:.0f} (era {prev:.1f})"
            logger.info("fii_loop: BUY alert %s score=%.1f", ticker, score)
            notify_fii_buy(
                ticker=ticker, nome=nome, setor=setor,
                score=score, score_prev=prev,
                dy=dy, pvp=pvp, price=price,
                income_score=i_score, valuation_score=v_score, risk_score=r_score,
                trigger=trigger,
            )
            alerted.append(ticker)
            continue

        # SELL: crossed below exit threshold
        if score < _SELL_THRESHOLD and prev >= _SELL_THRESHOLD:
            trigger = f"score caiu abaixo de {_SELL_THRESHOLD:.0f} (era {prev:.1f})"
            logger.info("fii_loop: SELL alert %s score=%.1f", ticker, score)
            notify_fii_sell(
                ticker=ticker, nome=nome, setor=setor,
                score=score, score_prev=prev,
                dy=dy, pvp=pvp, price=price,
                trigger=trigger,
            )
            alerted.append(ticker)
            continue

        # DETERIORATION: sharp drop regardless of threshold crossing
        if delta <= -_DROP_ALERT:
            trigger = f"queda de {abs(delta):.1f} pts em um ciclo (era {prev:.1f})"
            logger.info("fii_loop: DROP alert %s Δ=%.1f", ticker, delta)
            notify_fii_sell(
                ticker=ticker, nome=nome, setor=setor,
                score=score, score_prev=prev,
                dy=dy, pvp=pvp, price=price,
                trigger=trigger,
            )
            alerted.append(ticker)

    # --- Daily ranking (once per day at first iteration) ---
    today = time.strftime("%Y-%m-%d")
    if state.get("last_ranking_date") != today:
        logger.info("fii_loop: sending daily ranking top-5")
        notify_fii_ranking(ranked, top_n=5)
        state["last_ranking_date"] = today

    logger.info(
        "fii_loop: iter=%d fiis=%d alerted=%d",
        iteration, len(ranked), len(alerted),
    )

    state["scores"] = new_scores
    return state


# ---------------------------------------------------------------------------
# Signal handling
# ---------------------------------------------------------------------------

_running = True


def _handle_sigterm(sig: int, frame: FrameType | None) -> None:
    global _running
    logger.info("fii_loop: SIGTERM received — shutting down")
    _running = False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    global _running

    parser = argparse.ArgumentParser(description="AlphaCota FII scoring loop")
    parser.add_argument("--interval", type=int, default=_DEFAULT_INTERVAL,
                        help="Sleep interval in seconds (default 21600 = 6h)")
    parser.add_argument("--once", action="store_true",
                        help="Run a single iteration and exit")
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, _handle_sigterm)

    logger.info("fii_loop: starting (interval=%ds)", args.interval)
    send_message("📊 <b>AlphaCota FII loop iniciado</b> — monitorando FIIs a cada 6h.")

    state = _load_state()
    iteration = 1
    consecutive_errors = 0

    while _running:
        try:
            state = _run_iteration(state, iteration)
            _save_state(state)
            consecutive_errors = 0
        except KeyboardInterrupt:
            logger.info("fii_loop: KeyboardInterrupt — stopping")
            break
        except Exception as exc:
            consecutive_errors += 1
            logger.error("fii_loop: iteration %d failed: %s", iteration, exc)
            if consecutive_errors >= 3:
                notify_fii_loop_error(str(exc))
                consecutive_errors = 0

        if args.once:
            break

        iteration += 1
        logger.info("fii_loop: sleeping %ds", args.interval)
        time.sleep(args.interval)

    logger.info("fii_loop: stopped at iteration %d", iteration)


if __name__ == "__main__":
    main()
