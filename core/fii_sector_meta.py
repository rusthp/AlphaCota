"""
core/fii_sector_meta.py — Sector weight profiles, regime adaptation, and
rotation signal detection.

Two distinct layers:

1. Sector weight profiles (scoring-time):
   Each FII sector has a base weight configuration that reflects its structural
   characteristics. Papel (CRI) is an income play → w_income heavier.
   Logística has long contracts → w_risk heavier. Applied via get_weights_for_sector().

2. Sector rotation meta-score (post-scoring):
   After ranking, aggregate score velocity per sector to detect which sectors
   are leading vs lagging. Apply a bounded ±4 pts rotation bonus/penalty to
   individual FII scores. Applied via compute_sector_meta() + apply_rotation_bonus().

Public API:
    SECTOR_WEIGHT_PROFILES       dict — base weights by sector
    get_weights_for_sector(sector, macro_ctx) -> dict[str, float]
    compute_sector_meta(ranked, sector_map, analytics) -> dict[str, SectorMeta]
    apply_rotation_bonus(ranked, sector_meta, sector_map) -> list[dict]
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.fii_macro_engine import MacroContext

from core.logger import logger
from core.score_engine import DEFAULT_WEIGHTS

# ---------------------------------------------------------------------------
# Sector weight profiles
# Weights must sum to 1.0 in each profile.
# Designed to reflect the structural risk/income profile of each sector.
# ---------------------------------------------------------------------------

SECTOR_WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    # Pure receivables income play — P/VP less informative for CRI portfolios
    "Papel (CRI)": {
        "w_income": 0.50, "w_valuation": 0.15,
        "w_risk": 0.20, "w_growth": 0.05, "w_news": 0.10,
    },
    # IPCA-linked receivables — similar to CRI, income dominant
    "Agro": {
        "w_income": 0.48, "w_valuation": 0.17,
        "w_risk": 0.20, "w_growth": 0.05, "w_news": 0.10,
    },
    # Long-term logistics contracts, vacancy is key risk
    "Logística": {
        "w_income": 0.38, "w_valuation": 0.22,
        "w_risk": 0.28, "w_growth": 0.05, "w_news": 0.07,
    },
    # Mall occupancy and same-store-sales growth matter
    "Shopping": {
        "w_income": 0.35, "w_valuation": 0.23,
        "w_risk": 0.20, "w_growth": 0.12, "w_news": 0.10,
    },
    # Office vacancy + tenant quality — growth signals relevant
    "Lajes Corp.": {
        "w_income": 0.35, "w_valuation": 0.23,
        "w_risk": 0.22, "w_growth": 0.12, "w_news": 0.08,
    },
    # Diversified exposure — slightly more weight on risk (diversification quality)
    "Fundo de Fundos": {
        "w_income": 0.40, "w_valuation": 0.20,
        "w_risk": 0.28, "w_growth": 0.04, "w_news": 0.08,
    },
    # Healthcare is a growth story with stable income floor
    "Saúde": {
        "w_income": 0.32, "w_valuation": 0.25,
        "w_risk": 0.20, "w_growth": 0.15, "w_news": 0.08,
    },
    # Residential rental — income + risk (default rates)
    "Residencial": {
        "w_income": 0.42, "w_valuation": 0.23,
        "w_risk": 0.22, "w_growth": 0.05, "w_news": 0.08,
    },
    # Hotel/Hotelaria — highly cyclical, growth matters more
    "Hotel": {
        "w_income": 0.30, "w_valuation": 0.25,
        "w_risk": 0.20, "w_growth": 0.18, "w_news": 0.07,
    },
}

# Sectors that benefit from rate cuts (brick-and-mortar, leveraged to lower cost of debt)
_TIJOLO_SECTORS = {"Logística", "Shopping", "Lajes Corp.", "Residencial", "Educacional", "Saúde"}
# Sectors where floating-rate income rises with SELIC/IPCA
_PAPEL_SECTORS  = {"Papel (CRI)", "Agro"}

# Maximum rotation bonus/penalty applied to alpha_score post-scoring
_ROTATION_MAX_BONUS  =  4.0
_ROTATION_MAX_PENALTY = -4.0

# Velocity threshold (pts/day averaged across sector) to qualify as leading/lagging
_ROTATION_LEAD_THRESHOLD  =  0.3
_ROTATION_LAG_THRESHOLD   = -0.3


# ---------------------------------------------------------------------------
# Sector data container
# ---------------------------------------------------------------------------

@dataclass
class SectorMeta:
    sector: str
    count: int
    avg_score: float
    top_score: float
    score_std: float                # std-dev of scores within sector
    avg_velocity_7d: float | None   # average pts/day across sector constituents
    rotation_signal: str            # "leading" | "lagging" | "neutral"
    rotation_bonus: float           # additive pts applied to all constituents


# ---------------------------------------------------------------------------
# Adaptive weight selection
# ---------------------------------------------------------------------------

def get_weights_for_sector(
    sector: str,
    macro_ctx: "MacroContext | None" = None,
) -> dict[str, float]:
    """Return scoring weights adapted for this sector + current macro regime.

    Base weights come from SECTOR_WEIGHT_PROFILES (or DEFAULT_WEIGHTS for
    unrecognised sectors). Macro regime adjustments are applied on top:

    - SELIC falling: Tijolo sectors → shift 0.05 from w_growth to w_income
      (income stability rewarded more in rate-cut cycles)
    - SELIC rising: Papel/Agro sectors → shift 0.03 from w_valuation to w_income
      (floating-rate income even more critical)
    - IPCA ≥ 6.5%: Papel/Agro sectors → further shift 0.02 from w_growth to w_income
    """
    base = SECTOR_WEIGHT_PROFILES.get(sector, DEFAULT_WEIGHTS).copy()

    if macro_ctx is None or not macro_ctx.available:
        return base

    adjusted = dict(base)

    if macro_ctx.selic_trend == "falling" and sector in _TIJOLO_SECTORS:
        shift = min(0.05, adjusted.get("w_growth", 0.0))
        adjusted["w_income"] = round(adjusted["w_income"] + shift, 4)
        adjusted["w_growth"] = round(adjusted["w_growth"] - shift, 4)

    if macro_ctx.selic_trend == "rising" and sector in _PAPEL_SECTORS:
        shift = min(0.03, adjusted.get("w_valuation", 0.0))
        adjusted["w_income"]    = round(adjusted["w_income"] + shift, 4)
        adjusted["w_valuation"] = round(adjusted["w_valuation"] - shift, 4)

    if macro_ctx.ipca_12m >= 6.5 and sector in _PAPEL_SECTORS:
        shift = min(0.02, adjusted.get("w_growth", 0.0))
        adjusted["w_income"] = round(adjusted["w_income"] + shift, 4)
        adjusted["w_growth"] = round(adjusted["w_growth"] - shift, 4)

    return adjusted


# ---------------------------------------------------------------------------
# Sector rotation meta-score
# ---------------------------------------------------------------------------

def compute_sector_meta(
    ranked: list[dict],
    sector_map: dict[str, str],
    analytics: dict[str, dict] | None = None,
) -> dict[str, SectorMeta]:
    """Compute sector-level aggregate metrics from the current scoring cycle.

    Args:
        ranked:     Scored FII list (output of rank_fiis).
        sector_map: ticker → sector string.
        analytics:  Output of get_universe_analytics (ticker → analytics dict).
                    If None, velocity is treated as unavailable.

    Returns:
        Dict mapping sector_name → SectorMeta.
    """
    # Group FIIs by sector
    by_sector: dict[str, list[dict]] = {}
    for fii in ranked:
        sec = sector_map.get(fii["ticker"], "Outros")
        by_sector.setdefault(sec, []).append(fii)

    result: dict[str, SectorMeta] = {}
    for sec, fiis in by_sector.items():
        scores = [f["alpha_score"] for f in fiis]
        avg_sc = round(statistics.mean(scores), 2) if scores else 0.0
        top_sc = round(max(scores), 2) if scores else 0.0
        std_sc = round(statistics.stdev(scores), 2) if len(scores) >= 2 else 0.0

        # Average 7d velocity across sector constituents
        avg_vel: float | None = None
        if analytics:
            vels = [
                analytics[f["ticker"].upper()]["velocity_7d"]
                for f in fiis
                if analytics.get(f["ticker"].upper(), {}).get("velocity_7d") is not None
            ]
            if vels:
                avg_vel = round(statistics.mean(vels), 3)

        signal = "neutral"
        bonus  = 0.0
        if avg_vel is not None:
            if avg_vel >= _ROTATION_LEAD_THRESHOLD:
                signal = "leading"
                # Scale bonus linearly: 0.3 pts/day → +1 pt, 1.0+ pts/day → +4 pts
                raw    = avg_vel / _ROTATION_LEAD_THRESHOLD
                bonus  = round(min(_ROTATION_MAX_BONUS, raw), 2)
            elif avg_vel <= _ROTATION_LAG_THRESHOLD:
                signal = "lagging"
                raw    = avg_vel / abs(_ROTATION_LAG_THRESHOLD)
                bonus  = round(max(_ROTATION_MAX_PENALTY, raw), 2)

        result[sec] = SectorMeta(
            sector=sec,
            count=len(fiis),
            avg_score=avg_sc,
            top_score=top_sc,
            score_std=std_sc,
            avg_velocity_7d=avg_vel,
            rotation_signal=signal,
            rotation_bonus=bonus,
        )

    return result


def apply_rotation_bonus(
    ranked: list[dict],
    sector_meta: dict[str, "SectorMeta"],
    sector_map: dict[str, str],
) -> list[dict]:
    """Apply sector rotation bonus/penalty to each FII's alpha_score.

    Returns a new list (sorted) with adjusted scores.
    The adjustment is stored in fii["_sector_bonus"] for transparency.
    """
    adjusted = []
    for fii in ranked:
        sec  = sector_map.get(fii["ticker"], "Outros")
        meta = sector_meta.get(sec)
        bonus = meta.rotation_bonus if meta else 0.0
        if bonus == 0.0:
            adjusted.append({**fii, "_sector_bonus": 0.0})
            continue
        new_score = round(max(0.0, min(100.0, fii["alpha_score"] + bonus)), 2)
        adjusted.append({**fii, "alpha_score": new_score, "_sector_bonus": bonus})

    adjusted.sort(key=lambda x: x["alpha_score"], reverse=True)
    return adjusted


def apply_zscore_normalization(
    ranked: list[dict],
    sector_meta: dict[str, "SectorMeta"],
    sector_map: dict[str, str],
) -> list[dict]:
    """Add sector_zscore and sector_percentile to each FII dict.

    sector_zscore   = (alpha_score - sector_mean) / sector_std
    sector_percentile = fraction of sector peers with lower score (0..1)

    FIIs in single-member sectors get zscore=0.0, percentile=1.0.
    Mutates in-place and returns the same list.
    """
    # Pre-group scores per sector for percentile computation
    by_sector: dict[str, list[float]] = {}
    for fii in ranked:
        sec = sector_map.get(fii["ticker"], "Outros")
        by_sector.setdefault(sec, []).append(fii["alpha_score"])

    for fii in ranked:
        sec  = sector_map.get(fii["ticker"], "Outros")
        meta = sector_meta.get(sec)
        sc   = fii["alpha_score"]

        if meta is None:
            logger.warning("apply_zscore_normalization: no SectorMeta for sector '%s' (ticker %s)",
                           sec, fii.get("ticker"))
            fii["sector_zscore"]     = 0.0
            fii["sector_percentile"] = None
            continue
        if meta.score_std == 0.0:
            # Single-member or perfectly homogeneous sector — z-score undefined.
            fii["sector_zscore"]     = 0.0
            fii["sector_percentile"] = None
            continue

        fii["sector_zscore"] = round((sc - meta.avg_score) / meta.score_std, 3)

        peers = by_sector[sec]
        below = sum(1 for p in peers if p < sc)
        fii["sector_percentile"] = round(below / len(peers), 3)

    return ranked


def format_sector_summary(sector_meta: dict[str, SectorMeta]) -> str:
    """Return a compact text summary of sector rotation state."""
    lines = ["Setor              Avg   Top  Ops  Vel/d  Sinal"]
    lines.append("-" * 52)
    for sec, m in sorted(sector_meta.items(), key=lambda x: -x[1].avg_score):
        vel_str = f"{m.avg_velocity_7d:+.2f}" if m.avg_velocity_7d is not None else "   —"
        icon = {"leading": "↑", "lagging": "↓", "neutral": "→"}.get(m.rotation_signal, "→")
        lines.append(
            f"{sec:<18} {m.avg_score:5.1f} {m.top_score:5.1f} "
            f"{m.count:3}  {vel_str:>6}  {icon} {m.rotation_signal}"
        )
    return "\n".join(lines)
