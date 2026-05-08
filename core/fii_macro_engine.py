"""
core/fii_macro_engine.py — Brazilian macro context for FII scoring.

Fetches public data from BCB (Banco Central do Brasil) SGS API:
    SELIC Over (série 11)  — daily rate (% a.d.), date-range query for trend
    IPCA monthly (série 433) — % per month, last 13 obs; 12m = sum of last 12

Series limits discovered empirically:
    série 11  (SELIC diária)  — supports date-range, no hard limit on range
    série 433 (IPCA mensal)   — supports limit up to at least 13
    série 4390 / 432          — capped at 20 obs; not used

Computes:
    selic_trend      — "falling" | "stable" | "rising"
    selic_annual     — last daily rate × 252 (trading days) in % a.a.
    ipca_12m         — sum of last 12 monthly IPCA readings
    real_rate        — selic_annual - ipca_12m (NTN-B spread proxy)
    score_modifiers  — per-sector bonus/penalty added to alpha_score

Score modifier logic (additive, caps applied in loop):
    SELIC falling   → Tijolo sectors +5 (leveraged to rate cuts)
    SELIC rising    → Papel(CRI)/Agro +4 (floating-rate receivables)
    IPCA ≥ 6.5%     → Papel(CRI)/Agro +5 (inflation-linked income)
    real_rate ≥ 5%  → global -3 (risk-free competition penalty)

Cache: 6 hours. On any error: available=False, empty modifiers (graceful degrade).

Public API:
    MacroContext         — dataclass
    fetch_macro_context() -> MacroContext
    macro_summary_line(ctx) -> str
"""

from __future__ import annotations

import datetime
import time
from dataclasses import dataclass, field

import httpx

from core.logger import logger

_BCB_BASE  = "https://api.bcb.gov.br/dados/serie/bcdata.sgs"
_TIMEOUT   = 10.0
_CACHE_TTL = 21_600.0   # 6h

_SELIC_SERIES = 11    # Taxa SELIC Over acumulada diária (% a.d.)
_IPCA_SERIES  = 433   # IPCA variação mensal (% no período)

# Trend: 3m avg must diverge from 6m avg by at least this many pp (in % a.d.).
# 0.0004 pp/day ≈ 0.1 pp/year at 252 days.
_TREND_MARGIN_DAILY = 0.0004

_HIGH_IPCA = 6.5   # % a.a. — IPCA 12m above this → inflation-linked bonus
_HIGH_REAL = 5.0   # % a.a. — real rate above this → risk-free competes

_TIJOLO_SECTORS = {"Logística", "Shopping", "Lajes Corp.", "Residencial", "Educacional", "Saúde"}
_PAPEL_SECTORS  = {"Papel (CRI)", "Agro"}

_cache: tuple[float, "MacroContext"] | None = None


@dataclass
class MacroContext:
    selic_annual: float       # % a.a. (last daily rate × 252)
    selic_3m_avg: float       # 3-month rolling avg of daily rate × 252
    selic_6m_avg: float       # 6-month rolling avg of daily rate × 252
    selic_trend: str          # "falling" | "stable" | "rising"
    ipca_12m: float           # % accumulated last 12 months
    real_rate: float          # selic_annual - ipca_12m
    score_modifiers: dict[str, float] = field(default_factory=dict)
    available: bool = True
    fetched_at: float = 0.0


def _date_str(d: datetime.date) -> str:
    return d.strftime("%d/%m/%Y")


def _bcb_date_range(series: int, days_back: int) -> list[dict]:
    """Fetch series data for the last `days_back` calendar days via date range."""
    today = datetime.date.today()
    start = today - datetime.timedelta(days=days_back)
    url = (
        f"{_BCB_BASE}.{series}/dados"
        f"?dataInicial={_date_str(start)}&dataFinal={_date_str(today)}&formato=json"
    )
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.json()


def _bcb_latest(series: int, n: int) -> list[dict]:
    """Fetch last `n` observations from BCB SGS."""
    url = f"{_BCB_BASE}.{series}/dados/ultimos/{n}?formato=json"
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.json()


def _float_val(item: dict) -> float:
    raw = item.get("valor", "0") or "0"
    return float(str(raw).replace(",", "."))


def _compute_selic_trend(
    daily_vals: list[float],
) -> tuple[float, float, float, str]:
    """Return (annual_current, avg3m_annual, avg6m_annual, trend).

    Input is ordered oldest→newest list of daily SELIC rates in % a.d.
    Converts to % a.a. (× 252) for all outputs.
    3m window ≈ 63 trading days; 6m window ≈ 126 trading days.
    """
    if not daily_vals:
        return (0.0, 0.0, 0.0, "stable")

    annual = [v * 252 for v in daily_vals]
    current = annual[-1]

    n3 = min(63, len(annual))
    n6 = min(126, len(annual))
    avg3 = sum(annual[-n3:]) / n3
    avg6 = sum(annual[-n6:]) / n6

    # Trend threshold in % a.a.
    margin = _TREND_MARGIN_DAILY * 252
    if avg3 < avg6 - margin:
        trend = "falling"
    elif avg3 > avg6 + margin:
        trend = "rising"
    else:
        trend = "stable"

    return (round(current, 4), round(avg3, 4), round(avg6, 4), trend)


def _build_modifiers(
    selic_trend: str,
    ipca_12m: float,
    real_rate: float,
) -> dict[str, float]:
    mods: dict[str, float] = {}

    if selic_trend == "falling":
        for sec in _TIJOLO_SECTORS:
            mods[sec] = mods.get(sec, 0.0) + 5.0

    if selic_trend == "rising":
        for sec in _PAPEL_SECTORS:
            mods[sec] = mods.get(sec, 0.0) + 4.0

    if ipca_12m >= _HIGH_IPCA:
        for sec in _PAPEL_SECTORS:
            mods[sec] = mods.get(sec, 0.0) + 5.0

    if real_rate >= _HIGH_REAL:
        mods["global"] = mods.get("global", 0.0) - 3.0

    return mods


def fetch_macro_context() -> MacroContext:
    """Fetch and cache Brazilian macro context. Never raises."""
    global _cache
    now = time.time()

    if _cache is not None and (now - _cache[0]) < _CACHE_TTL:
        return _cache[1]

    try:
        # SELIC: ~180 calendar days gives ~126 trading days (6 months)
        selic_raw = _bcb_date_range(_SELIC_SERIES, 180)
        selic_vals = [_float_val(r) for r in selic_raw if r.get("valor") not in (None, "")]
        annual, avg3, avg6, trend = _compute_selic_trend(selic_vals)

        # IPCA monthly: last 13 obs → sum last 12 for 12-month accumulated %
        ipca_raw = _bcb_latest(_IPCA_SERIES, 13)
        ipca_vals = [_float_val(r) for r in ipca_raw if r.get("valor") not in (None, "")]
        ipca_12m = round(sum(ipca_vals[-12:]), 4) if len(ipca_vals) >= 12 else 0.0

        real_rate = round(annual - ipca_12m, 4)
        modifiers = _build_modifiers(trend, ipca_12m, real_rate)

        ctx = MacroContext(
            selic_annual=annual,
            selic_3m_avg=avg3,
            selic_6m_avg=avg6,
            selic_trend=trend,
            ipca_12m=ipca_12m,
            real_rate=real_rate,
            score_modifiers=modifiers,
            available=True,
            fetched_at=now,
        )
        logger.info(
            "macro: SELIC=%.2f%% trend=%s IPCA12m=%.2f%% real=%.2f%% mods=%s",
            annual, trend, ipca_12m, real_rate, modifiers,
        )
        _cache = (now, ctx)
        return ctx

    except Exception as exc:
        logger.warning("macro: fetch failed (%s) — macro overlay disabled", exc)
        ctx = MacroContext(
            selic_annual=0.0, selic_3m_avg=0.0, selic_6m_avg=0.0,
            selic_trend="stable", ipca_12m=0.0, real_rate=0.0,
            score_modifiers={}, available=False, fetched_at=now,
        )
        _cache = (now, ctx)
        return ctx


def macro_summary_line(ctx: MacroContext) -> str:
    """One-line macro summary for Telegram messages."""
    if not ctx.available:
        return ""
    trend_icon = {"falling": "📉", "rising": "📈", "stable": "➡️"}.get(ctx.selic_trend, "➡️")
    return (
        f"🏦 SELIC {ctx.selic_annual:.2f}% {trend_icon} | "
        f"IPCA {ctx.ipca_12m:.2f}% | "
        f"Juro real {ctx.real_rate:.2f}%"
    )
