"""
data/refresh_universe.py — Weekly FII universe discovery and validation pipeline.

Fetches the complete IFIX composition from B3, validates each ticker via
yfinance, classifies sectors, assigns tiers, and upserts results into the
fii_registry SQLite table.

Run as:
    python -m data.refresh_universe [--force] [--min-volume 300000]

Or called from fii_loop on a weekly cadence via run_refresh().

Pipeline steps per ticker:
    1. Fetch IFIX composition from B3 (full list, ~100–120 FIIs)
    2. Validate yfinance: has recent price, compute 3-month avg daily liquidity
    3. Classify sector: known map → keyword heuristic → "Outros"
    4. Assign tier: based on IFIX membership + daily liquidity
    5. Upsert into fii_registry
    6. Mark previously-active tickers no longer in IFIX as inactive
"""

from __future__ import annotations

import argparse
import datetime
import time
from typing import TYPE_CHECKING

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from core.logger import logger
from data.universe_registry import (
    connect_registry,
    upsert_fii,
    mark_inactive,
    get_registry_stats,
)
from data.cvm_b3_client import fetch_ifix_composition
from data.sector_enricher import classify_sector, enrich_registry_sectors, KNOWN_SECTORS

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Tier thresholds
# ---------------------------------------------------------------------------

_TIER1_MIN_LIQUIDITY = 1_000_000.0   # R$1M/day → Tier 1
_TIER2_MIN_LIQUIDITY = 300_000.0     # R$300k/day → Tier 2
_MIN_VALID_PRICE     = 0.01          # below this → invalid (ghost trade)
_STALE_DAYS          = 10            # price older than this → yahoo_ok = False


# ---------------------------------------------------------------------------
# Tier assignment
# ---------------------------------------------------------------------------

def _assign_tier(ifix: bool, daily_liquidity: float) -> int:
    """Assign coverage tier based on IFIX membership and daily liquidity."""
    if ifix and daily_liquidity >= _TIER1_MIN_LIQUIDITY:
        return 1
    if ifix:
        return 2   # IFIX regardless of liquidity (low-liq IFIX still Tier 2)
    if daily_liquidity >= _TIER1_MIN_LIQUIDITY:
        return 2   # High-liquidity non-IFIX → Tier 2
    return 3


# ---------------------------------------------------------------------------
# yfinance validation
# ---------------------------------------------------------------------------

def _validate_yahoo(ticker: str) -> dict:
    """Test yfinance coverage and extract price and daily liquidity.

    Returns a dict with keys:
        yahoo_ok (bool), last_price (float), daily_liquidity (float)
    """
    try:
        import yfinance as yf

        t = yf.Ticker(f"{ticker}.SA")
        fi = t.fast_info

        price = float(fi.last_price or 0)
        volume = float(getattr(fi, "three_month_average_volume", None) or 0)

        if price < _MIN_VALID_PRICE:
            return {"yahoo_ok": False, "last_price": 0.0, "daily_liquidity": 0.0}

        # Check for stale price (last_volume == 0 or no recent trade)
        # fast_info doesn't expose last_trade_date reliably, so we use a recent
        # 1-day history query to confirm the ticker is still active.
        hist = t.history(period="10d", auto_adjust=True)
        if hist.empty or len(hist) == 0:
            return {"yahoo_ok": False, "last_price": price, "daily_liquidity": 0.0}

        last_date = hist.index[-1]
        last_date_py = last_date.date() if hasattr(last_date, "date") else last_date
        days_stale = (datetime.date.today() - last_date_py).days
        if days_stale > _STALE_DAYS:
            return {"yahoo_ok": False, "last_price": price, "daily_liquidity": 0.0}

        # Daily liquidity in BRL = avg 3m volume × last price
        daily_liq = volume * price if volume > 0 else 0.0

        # If fast_info volume is zero, try computing from history
        if daily_liq == 0.0 and not hist.empty and "Volume" in hist.columns:
            hist_vol = hist["Volume"].tail(60).mean()
            daily_liq = float(hist_vol) * price if hist_vol > 0 else 0.0

        return {
            "yahoo_ok": True,
            "last_price": round(price, 4),
            "daily_liquidity": round(daily_liq, 0),
        }

    except Exception as exc:
        logger.debug("yahoo validate %s: %s", ticker, exc)
        return {"yahoo_ok": False, "last_price": 0.0, "daily_liquidity": 0.0}


# ---------------------------------------------------------------------------
# StatusInvest probe (lightweight — just HEAD check, no full parse)
# ---------------------------------------------------------------------------

def _probe_status_invest(ticker: str) -> bool:
    """Return True if StatusInvest returns HTTP 200 for this ticker."""
    try:
        import requests
        url = f"https://statusinvest.com.br/fundos-imobiliarios/{ticker.lower()}"
        resp = requests.head(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8,
            allow_redirects=True,
        )
        return resp.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_refresh(
    force: bool = False,
    min_volume: float = 0.0,
    probe_si: bool = False,
) -> int:
    """Discover, validate, and register all IFIX FIIs.

    Args:
        force:      Re-validate every ticker even if recently validated.
        min_volume: Minimum daily liquidity (R$) for a FII to be marked active.
                    0 = no filter (all IFIX FIIs kept).
        probe_si:   Whether to probe StatusInvest for each ticker (slower).

    Returns:
        Number of FIIs upserted into the registry.
    """
    today = datetime.date.today().isoformat()
    conn = connect_registry()

    # Already-known tickers so we can detect removals from IFIX
    existing_ifix: set[str] = {
        r["ticker"]
        for r in conn.execute(
            "SELECT ticker FROM fii_registry WHERE ifix = 1 AND ativo = 1"
        ).fetchall()
    }

    # --- Fetch IFIX composition ---
    logger.info("refresh_universe: fetching IFIX composition from B3")
    ifix_items = fetch_ifix_composition()

    if not ifix_items:
        logger.warning("refresh_universe: B3 IFIX returned 0 items — aborting")
        conn.close()
        return 0

    logger.info("refresh_universe: B3 returned %d IFIX FIIs", len(ifix_items))

    # Check whether the current cycle needs validation (skip if validated today)
    skip_validation = not force
    upserted = 0
    seen_tickers: set[str] = set()

    for item in ifix_items:
        ticker = item["ticker"].upper().strip()
        if not ticker or len(ticker) < 5:
            continue

        # Skip recently-validated tickers unless --force
        if skip_validation:
            row = conn.execute(
                "SELECT last_validated FROM fii_registry WHERE ticker = ?",
                (ticker,),
            ).fetchone()
            if row and row["last_validated"] == today:
                seen_tickers.add(ticker)
                upserted += 1   # count as processed
                continue

        nome = item.get("nome", "")
        participacao = float(item.get("participacao", 0.0))
        setor = classify_sector(ticker, nome)

        logger.info("refresh_universe: validating %s (%s)", ticker, setor)
        yahoo_data = _validate_yahoo(ticker)

        si_ok = _probe_status_invest(ticker) if probe_si else False

        daily_liq = yahoo_data["daily_liquidity"]
        tier = _assign_tier(ifix=True, daily_liquidity=daily_liq)

        # Mark active only when liquidity passes filter (if filter set)
        ativo = daily_liq >= min_volume if min_volume > 0 else True
        # IFIX FIIs with no valid Yahoo data are kept but flagged
        if not yahoo_data["yahoo_ok"]:
            logger.info(
                "refresh_universe: %s yahoo_ok=False price=%.2f — kept, flagged",
                ticker, yahoo_data["last_price"],
            )

        entry = {
            "ticker":            ticker,
            "nome":              nome,
            "setor":             setor,
            "ifix":              True,
            "tier":              tier,
            "ativo":             ativo,
            "yahoo_ok":          yahoo_data["yahoo_ok"],
            "si_ok":             si_ok,
            "last_price":        yahoo_data["last_price"],
            "daily_liquidity":   daily_liq,
            "participacao_ifix": participacao,
            "cnpj":              "",
            "administrador":     "",
            "last_validated":    today,
        }

        upsert_fii(conn, entry)
        seen_tickers.add(ticker)
        upserted += 1

        # Rate-limit between yfinance calls to avoid hammering servers
        time.sleep(0.5)

    # --- Detect IFIX removals: mark no-longer-present IFIX FIIs as inactive ---
    removed = existing_ifix - seen_tickers
    for ticker in removed:
        logger.info("refresh_universe: %s removed from IFIX — marking inactive", ticker)
        mark_inactive(conn, ticker)

    # --- Sector enrichment: resolve remaining 'Outros' via SI JSON-LD ---
    enriched = enrich_registry_sectors(conn, force=False, use_si=True)
    logger.info("refresh_universe: sector enrichment updated %d rows", enriched)

    stats = get_registry_stats(conn)
    conn.close()

    logger.info(
        "refresh_universe: done — upserted=%d removed=%d enriched=%d "
        "active=%s ifix=%s yahoo_ok=%s",
        upserted,
        len(removed),
        enriched,
        stats.get("ativos"),
        stats.get("ifix_count"),
        stats.get("yahoo_ok"),
    )
    return upserted


# ---------------------------------------------------------------------------
# Seed from hardcoded universe (bootstrap without B3 API)
# ---------------------------------------------------------------------------

def seed_from_hardcoded() -> int:
    """Seed the registry from the hardcoded universe list.

    Use this as a bootstrap when B3 is unreachable or for initial setup.
    Does not validate via yfinance — sets yahoo_ok=False for all entries.
    Run run_refresh() afterward to validate.
    """
    from data.universe import _UNIVERSE_RAW  # noqa: PLC0415

    conn = connect_registry()
    today = datetime.date.today().isoformat()
    count = 0

    for ticker, setor, nome, ifix in _UNIVERSE_RAW:
        entry = {
            "ticker":            ticker,
            "nome":              nome,
            "setor":             setor,
            "ifix":              ifix,
            "tier":              1 if ifix else 3,
            "ativo":             True,
            "yahoo_ok":          False,
            "si_ok":             False,
            "last_price":        0.0,
            "daily_liquidity":   0.0,
            "participacao_ifix": 0.0,
            "cnpj":              "",
            "administrador":     "",
            "last_validated":    today,
        }
        upsert_fii(conn, entry)
        count += 1

    conn.close()
    logger.info("seed_from_hardcoded: %d FIIs seeded", count)
    return count


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="AlphaCota FII universe refresh")
    parser.add_argument(
        "--force", action="store_true",
        help="Re-validate all tickers even if validated today",
    )
    parser.add_argument(
        "--min-volume", type=float, default=0.0, metavar="BRL",
        help="Minimum daily liquidity in BRL to mark FII active (default: 0 = all IFIX)",
    )
    parser.add_argument(
        "--probe-si", action="store_true",
        help="Probe StatusInvest for each ticker (adds ~0.5s per ticker)",
    )
    parser.add_argument(
        "--seed", action="store_true",
        help="Seed registry from hardcoded list (bootstrap, no yfinance)",
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Print registry stats and exit",
    )
    args = parser.parse_args()

    if args.stats:
        conn = connect_registry()
        stats = get_registry_stats(conn)
        conn.close()
        for k, v in stats.items():
            print(f"  {k}: {v}")
        return

    if args.seed:
        n = seed_from_hardcoded()
        print(f"Seeded {n} FIIs from hardcoded list")
        return

    n = run_refresh(force=args.force, min_volume=args.min_volume, probe_si=args.probe_si)
    print(f"Refresh complete: {n} FIIs processed")


if __name__ == "__main__":
    main()
