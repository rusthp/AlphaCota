"""
core/fii_macro_engine.py — Brazilian macro context for FII scoring.

Fetches public data from BCB (Banco Central do Brasil) SGS API:
    SELIC Over (série 432)   — daily rate, last 90 days for trend
    IPCA 12m  (série 13522)  — accumulated 12-month inflation

Computes:
    selic_trend      — "falling" | "stable" | "rising"
    real_rate        — selic_current - ipca_12m (proxy for NTN-B spread)
    score_modifiers  — per-sector bonus/penalty to add on top of alpha_score

Score modifier logic (additive, caps applied in loop):
    SELIC falling   → Tijolo/Logística/Shopping  +5 (leveraged to rate cuts)
    SELIC rising    → Papel(CRI)/Agro            +4 (floating-rate receivables)
    IPCA ≥ 6.5%     → Papel(CRI)/Agro            +5 (inflation-linked income)
    real_rate ≥ 5%  → global                      -3 (risk-free competition)

Cache: 6 hours (matches FII loop interval). BCB API rarely updates intraday.

Public API:
    MacroContext         — dataclass with all macro fields + modifiers
    fetch_macro_context() -> MacroContext   (cached, never raises)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx

from core.logger import logger

_BCB_BASE   = "https://api.bcb.gov.br/dados/serie/bcdata.sgs"
_TIMEOUT    = 10.0
_CACHE_TTL  = 21_600.0   # 6h — matches FII loop interval

_SELIC_SERIES = 432      # SELIC Over diária (% a.a.)
_IPCA_SERIES  = 13522    # IPCA acumulado 12 meses (%)

# Trend detection: 3-month avg must diverge from 6-month avg by ≥ this margin.
_TREND_MARGIN = 0.10     # 0.10 pp

# Thresholds for modifier activation.
_HIGH_IPCA    = 6.5      # % — IPCA above this → inflation-linked bonus
_HIGH_REAL    = 5.0      # % — real rate above this → risk-free competes

# Sector names must match get_sector_map() output exactly.
_TIJOLO_SECTORS = {"Logística", "Shopping", "Lajes Corp.", "Residencial", "Educacional", "Saúde"}
_PAPEL_SECTORS  = {"Papel (CRI)", "Agro"}

_cache: tuple[float, "MacroContext"] | None = None


@dataclass
class MacroContext:
    selic_current: float     # % a.a., last observed value
    selic_3m_avg: float      # 3-month rolling average
    selic_6m_avg: float      # 6-month rolling average
    selic_trend: str         # "falling" | "stable" | "rising"
    ipca_12m: float          # % acumulado 12 meses
    real_rate: float         # selic_current - ipca_12m
    score_modifiers: dict[str, float] = field(default_factory=dict)
    available: bool = True
    fetched_at: float = 0.0


def _bcb_fetch(series: int, n_obs: int) -> list[dict]:
    """Return last n_obs observations from BCB SGS."""
    url = f"{_BCB_BASE}.{series}/dados/ultimos/{n_obs}?formato=json"
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.json()


def _float_val(item: dict) -> float:
    raw = item.get("valor", "0") or "0"
    return float(str(raw).replace(",", "."))


def _compute_trend(series: list[float], n3: int, n6: int) -> tuple[float, float, str]:
    """Return (avg_3m, avg_6m, trend) from a list of values ordered oldest→newest."""
    if not series:
        return (0.0, 0.0, "stable")
    window6 = series[-n6:] if len(series) >= n6 else series
    window3 = series[-n3:] if len(series) >= n3 else series
    avg3 = sum(window3) / len(window3)
    avg6 = sum(window6) / len(window6)
    if avg3 < avg6 - _TREND_MARGIN:
        trend = "falling"
    elif avg3 > avg6 + _TREND_MARGIN:
        trend = "rising"
    else:
        trend = "stable"
    return (round(avg3, 4), round(avg6, 4), trend)


def _build_modifiers(
    selic_trend: str,
    ipca_12m: float,
    real_rate: float,
) -> dict[str, float]:
    """Return per-sector additive score bonuses/penalties."""
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
    """Fetch and cache Brazilian macro context. Never raises.

    Cache TTL is 6 hours — BCB updates SELIC daily, IPCA monthly.
    On any error returns MacroContext with available=False and empty modifiers,
    so the FII loop degrades gracefully without macro adjustments.
    """
    global _cache
    now = time.time()

    if _cache is not None and (now - _cache[0]) < _CACHE_TTL:
        return _cache[1]

    try:
        # Fetch ~130 trading days of SELIC (≈6 calendar months)
        selic_raw = _bcb_fetch(_SELIC_SERIES, 130)
        selic_vals = [_float_val(r) for r in selic_raw if r.get("valor") not in (None, "")]
        selic_current = selic_vals[-1] if selic_vals else 0.0
        # ~63 obs = 3 months of trading days; ~126 = 6 months
        avg3, avg6, trend = _compute_trend(selic_vals, n3=63, n6=126)

        # Fetch last 2 IPCA 12m values (updated monthly)
        ipca_raw = _bcb_fetch(_IPCA_SERIES, 2)
        ipca_12m = _float_val(ipca_raw[-1]) if ipca_raw else 0.0

        real_rate = round(selic_current - ipca_12m, 4)
        modifiers = _build_modifiers(trend, ipca_12m, real_rate)

        ctx = MacroContext(
            selic_current=round(selic_current, 4),
            selic_3m_avg=avg3,
            selic_6m_avg=avg6,
            selic_trend=trend,
            ipca_12m=round(ipca_12m, 4),
            real_rate=real_rate,
            score_modifiers=modifiers,
            available=True,
            fetched_at=now,
        )
        logger.info(
            "macro: SELIC=%.2f%% trend=%s IPCA12m=%.2f%% real=%.2f%% mods=%s",
            selic_current, trend, ipca_12m, real_rate, modifiers,
        )
        _cache = (now, ctx)
        return ctx

    except Exception as exc:
        logger.warning("macro: fetch failed (%s) — macro overlay disabled", exc)
        ctx = MacroContext(
            selic_current=0.0, selic_3m_avg=0.0, selic_6m_avg=0.0,
            selic_trend="stable", ipca_12m=0.0, real_rate=0.0,
            score_modifiers={}, available=False, fetched_at=now,
        )
        _cache = (now, ctx)
        return ctx


def macro_summary_line(ctx: MacroContext) -> str:
    """One-line macro summary for Telegram messages."""
    if not ctx.available:
        return "Macro: dados indisponíveis"
    trend_icon = {"falling": "📉", "rising": "📈", "stable": "➡️"}.get(ctx.selic_trend, "➡️")
    return (
        f"🏦 SELIC {ctx.selic_current:.2f}% {trend_icon} | "
        f"IPCA {ctx.ipca_12m:.2f}% | "
        f"Juro real {ctx.real_rate:.2f}%"
    )
