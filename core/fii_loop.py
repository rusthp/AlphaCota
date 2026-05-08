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
import threading
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
    notify_coverage_health,
    send_message,
)
from core.fii_ledger import connect_fii_db, save_fii_snapshot, get_fii_score_deltas_bulk
from core.fii_macro_engine import fetch_macro_context, macro_summary_line
from core.logger import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_INTERVAL = int(os.getenv("FII_LOOP_INTERVAL_SECONDS", "21600"))  # 6h
_STATE_FILE = Path("data/fii_loop_state.json")

# Hysteresis thresholds — entry and exit are different to prevent flip-flop.
_BUY_ENTRY   = 80.0   # score must reach 80 to trigger BUY alert
_BUY_HYSTER  = 74.0   # BUY state clears only if score falls below 74
_SELL_ENTRY  = 45.0   # score must fall below 45 to trigger SELL alert
_SELL_HYSTER = 50.0   # SELL state clears only if score recovers above 50
_DROP_ALERT  = 15.0   # sharp drop in one cycle — fires regardless of state

# Temporal persistence: require N consecutive cycles before any alert fires.
# At 6h interval: 2 cycles = 12h confirmation before acting.
_PERSIST_CYCLES = 2

# Cooldown: same alert type on same ticker won't re-fire within this window.
_ALERT_COOLDOWN_HOURS = 72.0

# Data quality: alerts suppressed when confidence is below this threshold.
_MIN_DATA_CONFIDENCE = 0.60

# Outlier sanity bounds — values outside these ranges are discarded.
_DY_MIN, _DY_MAX       = 0.001, 0.40    # 0.1% – 40% annual DY
_PVP_MIN, _PVP_MAX     = 0.30, 3.0
_VAC_MIN, _VAC_MAX     = 0.0, 1.0       # 0% – 100% vacancy

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
    return {
        "scores": {},
        "alert_states": {},           # ticker → "neutral" | "buy_active" | "sell_active"
        "consecutive_below": {},      # ticker → int (cycles with score < SELL_ENTRY)
        "consecutive_above": {},      # ticker → int (cycles with score >= BUY_ENTRY)
        "last_alert": {},             # ticker → {"type": str, "ts": float}
        "last_ranking_date": "",
        "last_universe_refresh": "",  # ISO week string "YYYY-Www" of last refresh
    }


def _save_state(state: dict) -> None:
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("fii_loop: state save failed: %s", exc)


# ---------------------------------------------------------------------------
# Data quality helpers
# ---------------------------------------------------------------------------

def _sanitize_fundamentals(fund: dict) -> dict:
    """Return copy of fund dict with outlier values replaced by None.

    Outlier values (HTML scraping artefacts, API errors) produce scores that
    look decisive but are just garbage. Replacing them with None causes the
    scoring engine to use its defaults (neutral), which is safer than acting
    on a DY=83% that doesn't exist.
    """
    cleaned = dict(fund)
    dy = fund.get("dividend_yield") or 0.0
    if not (_DY_MIN <= dy <= _DY_MAX):
        cleaned["dividend_yield"] = None

    pvp = fund.get("pvp") or 0.0
    if pvp and not (_PVP_MIN <= pvp <= _PVP_MAX):
        cleaned["pvp"] = None

    vac = fund.get("vacancy_rate")
    if vac is not None and not (_VAC_MIN <= vac <= _VAC_MAX):
        cleaned["vacancy_rate"] = None

    return cleaned


def _data_confidence(fund: dict, fii: dict) -> float:
    """Return a confidence score in [0, 1] based on data completeness.

    Each missing or defaulted fundamental reduces confidence. Alerts are
    suppressed when confidence falls below _MIN_DATA_CONFIDENCE.
    """
    conf = 1.0
    if not fii.get("dividend_yield"):
        conf -= 0.20
    if fii.get("pvp", 1.0) == 1.0 and fund.get("pvp") is None:
        conf -= 0.10
    if fii.get("dividend_consistency", 50.0) == 50.0 and fund.get("dividend_consistency") is None:
        conf -= 0.10
    if fund.get("vacancy_rate") is None:
        conf -= 0.05
    if fund.get("debt_ratio") is None:
        conf -= 0.05
    return max(0.0, round(conf, 2))


def _cooldown_ok(last_alert: dict, ticker: str, alert_type: str) -> bool:
    """Return True when the cooldown window for this ticker+type has elapsed."""
    entry = last_alert.get(ticker, {})
    if entry.get("type") != alert_type:
        return True
    elapsed_h = (time.time() - entry.get("ts", 0.0)) / 3600.0
    return elapsed_h >= _ALERT_COOLDOWN_HOURS


# ---------------------------------------------------------------------------
# Core iteration
# ---------------------------------------------------------------------------

def _maybe_refresh_universe(state: dict) -> dict:
    """Run the universe discovery pipeline at most once per calendar week."""
    this_week = datetime.date.today().strftime("%G-W%V")  # ISO week, e.g. "2026-W19"
    if state.get("last_universe_refresh") == this_week:
        return state
    try:
        from data.refresh_universe import run_refresh
        from data.universe_registry import connect_registry, get_registry_stats, get_active_universe
        logger.info("fii_loop: weekly universe refresh starting")
        n = run_refresh()
        logger.info("fii_loop: universe refresh done — %d FIIs upserted", n)
        state["last_universe_refresh"] = this_week

        # Send coverage health dashboard after refresh
        try:
            reg_conn = connect_registry()
            stats = get_registry_stats(reg_conn)
            rows = get_active_universe(reg_conn, ifix_only=False)
            reg_conn.close()
            sector_breakdown: dict[str, int] = {}
            for r in rows:
                s = r["setor"]
                sector_breakdown[s] = sector_breakdown.get(s, 0) + 1
            notify_coverage_health(stats, sector_breakdown)
        except Exception as exc:
            logger.warning("fii_loop: coverage dashboard failed: %s", exc)

    except Exception as exc:
        logger.warning("fii_loop: universe refresh failed (non-fatal): %s", exc)
    return state


def _run_iteration(state: dict, iteration: int) -> dict:
    """Run one scoring cycle. Returns updated state."""
    logger.info("fii_loop: iteration %d start", iteration)

    # --- Weekly universe refresh (non-blocking: failure just skips) ---
    state = _maybe_refresh_universe(state)

    # --- Universe ---
    universe = get_universe(ifix_only=True)
    sector_map = get_sector_map()
    tickers = [fii["ticker"] for fii in universe]
    name_map = {fii["ticker"]: fii["nome"] for fii in universe}

    # --- Fundamentals (cached 24h, rate-limited internally) ---
    logger.info("fii_loop: fetching fundamentals for %d FIIs", len(tickers))
    fundamentals = fetch_fundamentals_bulk(tickers)

    # --- Prices + build scoring payload (with outlier sanitation) ---
    fiis_for_ranking: list[dict] = []
    sanitized_funds: dict[str, dict] = {}
    for ticker in tickers:
        raw_fund = fundamentals.get(ticker, {})
        fund = _sanitize_fundamentals(raw_fund)
        sanitized_funds[ticker] = fund

        price, _ = load_last_price(ticker)
        monthly_div, _ = load_monthly_dividend(ticker)

        # Prefer scraper DY; fall back to yfinance-derived DY; validate result
        dy = fund.get("dividend_yield") or 0.0
        if dy == 0.0 and price > 0 and monthly_div > 0:
            derived = (monthly_div * 12) / price
            dy = derived if (_DY_MIN <= derived <= _DY_MAX) else 0.0

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
            "_price": price,
            "_monthly_div": monthly_div,
        })

    # --- Score ---
    ranked = rank_fiis(fiis_for_ranking)
    logger.info("fii_loop: scored %d FIIs", len(ranked))

    # --- Macro context (BCB SELIC + IPCA) — cached 6h, never raises ---
    macro = fetch_macro_context()
    m_line = macro_summary_line(macro)
    logger.info("fii_loop: %s", m_line)

    # --- Apply macro score modifiers ---
    for fii in ranked:
        sec = sector_map.get(fii["ticker"], "Outros")
        bonus = macro.score_modifiers.get(sec, 0.0) + macro.score_modifiers.get("global", 0.0)
        if bonus != 0.0:
            fii["alpha_score"] = round(max(0.0, min(100.0, fii["alpha_score"] + bonus)), 2)
            fii["_macro_bonus"] = bonus

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

    # --- Score deltas (30d momentum) — single bulk query ---
    score_deltas = get_fii_score_deltas_bulk(connect_fii_db(), tickers, days=30)

    prev_scores: dict[str, float] = state.get("scores", {})
    new_scores: dict[str, float] = {}
    alerted: list[str] = []

    alert_states   = state.setdefault("alert_states", {})
    consec_below   = state.setdefault("consecutive_below", {})
    consec_above   = state.setdefault("consecutive_above", {})
    last_alert_map = state.setdefault("last_alert", {})

    for fii in ranked:
        ticker  = fii["ticker"]
        score   = fii["alpha_score"]
        prev    = prev_scores.get(ticker)
        fund    = sanitized_funds.get(ticker, {})
        conf    = _data_confidence(fund, fii)
        dy      = fii["dividend_yield"]
        pvp     = fii["pvp"]
        price   = fii.get("_price", 0.0)
        setor   = sector_map.get(ticker, "Outros")
        nome    = name_map.get(ticker) or ticker
        i_score = fii.get("income_score", 0.0)
        v_score = fii.get("valuation_score", 0.0)
        r_score = fii.get("risk_score", 50.0)
        d30     = score_deltas.get(ticker.upper())

        new_scores[ticker] = score

        if prev is None:
            alert_states[ticker] = "neutral"
            consec_below[ticker] = 0
            consec_above[ticker] = 0
            logger.info("fii_loop: %s first-seen score=%.1f conf=%.2f", ticker, score, conf)
            continue

        delta = score - prev

        # Update consecutive-cycle counters
        if score < _SELL_ENTRY:
            consec_below[ticker] = consec_below.get(ticker, 0) + 1
            consec_above[ticker] = 0
        elif score >= _BUY_ENTRY:
            consec_above[ticker] = consec_above.get(ticker, 0) + 1
            consec_below[ticker] = 0
        else:
            consec_below[ticker] = 0
            consec_above[ticker] = 0

        cur_state = alert_states.get(ticker, "neutral")

        # BUY: persistent above entry, not already buy_active, confidence OK
        if (score >= _BUY_ENTRY
                and consec_above.get(ticker, 0) >= _PERSIST_CYCLES
                and cur_state != "buy_active"
                and conf >= _MIN_DATA_CONFIDENCE
                and _cooldown_ok(last_alert_map, ticker, "buy")):
            trigger = (
                f"score {score:.1f} ≥ {_BUY_ENTRY:.0f} "
                f"por {_PERSIST_CYCLES} ciclos consecutivos"
            )
            logger.info("fii_loop: BUY alert %s score=%.1f conf=%.2f", ticker, score, conf)
            notify_fii_buy(
                ticker=ticker, nome=nome, setor=setor,
                score=score, score_prev=prev,
                dy=dy, pvp=pvp, price=price,
                income_score=i_score, valuation_score=v_score, risk_score=r_score,
                trigger=trigger, score_delta_30d=d30, macro_line=m_line,
            )
            alert_states[ticker]   = "buy_active"
            last_alert_map[ticker] = {"type": "buy", "ts": time.time()}
            alerted.append(ticker)
        elif cur_state == "buy_active" and score < _BUY_HYSTER:
            alert_states[ticker] = "neutral"
            consec_above[ticker] = 0

        # SELL: persistent below entry, not already sell_active, confidence OK
        if (score < _SELL_ENTRY
                and consec_below.get(ticker, 0) >= _PERSIST_CYCLES
                and cur_state != "sell_active"
                and conf >= _MIN_DATA_CONFIDENCE
                and _cooldown_ok(last_alert_map, ticker, "sell")):
            trigger = (
                f"score {score:.1f} < {_SELL_ENTRY:.0f} "
                f"por {_PERSIST_CYCLES} ciclos consecutivos"
            )
            logger.info("fii_loop: SELL alert %s score=%.1f conf=%.2f", ticker, score, conf)
            notify_fii_sell(
                ticker=ticker, nome=nome, setor=setor,
                score=score, score_prev=prev,
                dy=dy, pvp=pvp, price=price,
                trigger=trigger, score_delta_30d=d30, macro_line=m_line,
            )
            alert_states[ticker]   = "sell_active"
            last_alert_map[ticker] = {"type": "sell", "ts": time.time()}
            alerted.append(ticker)
        elif cur_state == "sell_active" and score >= _SELL_HYSTER:
            alert_states[ticker] = "neutral"
            consec_below[ticker] = 0

        # DROP: sharp fall in one cycle — fires regardless of state
        if (delta <= -_DROP_ALERT
                and cur_state != "sell_active"
                and conf >= _MIN_DATA_CONFIDENCE
                and _cooldown_ok(last_alert_map, ticker, "drop")):
            trigger = f"queda de {abs(delta):.1f} pts em um ciclo (era {prev:.1f})"
            logger.info("fii_loop: DROP alert %s Δ=%.1f conf=%.2f", ticker, delta, conf)
            notify_fii_sell(
                ticker=ticker, nome=nome, setor=setor,
                score=score, score_prev=prev,
                dy=dy, pvp=pvp, price=price,
                trigger=trigger, score_delta_30d=d30, macro_line=m_line,
            )
            last_alert_map[ticker] = {"type": "drop", "ts": time.time()}
            alerted.append(ticker)

    state["alert_states"]      = alert_states
    state["consecutive_below"] = consec_below
    state["consecutive_above"] = consec_above
    state["last_alert"]        = last_alert_map

    # --- Daily ranking (once per day at first iteration) ---
    today = time.strftime("%Y-%m-%d")
    if state.get("last_ranking_date") != today:
        logger.info("fii_loop: sending daily ranking top-5")
        notify_fii_ranking(
            ranked, top_n=5,
            sector_map=sector_map,
            score_deltas=score_deltas,
            macro_line=m_line,
        )
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
_stop_event = threading.Event()


def _handle_sigterm(_sig: int, _frame: FrameType | None) -> None:
    global _running
    logger.info("fii_loop: SIGTERM received — shutting down")
    _running = False
    _stop_event.set()   # wake the interruptible sleep immediately


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
        _stop_event.wait(timeout=args.interval)
        _stop_event.clear()

    logger.info("fii_loop: stopped at iteration %d", iteration)


if __name__ == "__main__":
    main()
