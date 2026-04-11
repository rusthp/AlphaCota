"""
core/prediction_engine.py

Motor de sinais macro via Mercados de Previsão (Prediction Markets).

Usa a API do Polymarket (via REST direto — sem dependência do pmxt CLI)
para buscar probabilidades implícitas de eventos macroeconômicos relevantes
para FIIs brasileiros:

  - Corte/alta de juros do Fed (impacto no câmbio USD/BRL → FIIs de papel)
  - Recessão nos EUA (fuga para renda fixa global)
  - Inflação acima da meta (impacto em FIIs de papel vs. tijolo)
  - Commodities / petróleo (FIIs logísticos e de agro)

Retorna um PredictionSignal com score 0-100 (bullish para FIIs).
Score alto = contexto macro favorável.

Cache local de 6h para evitar chamadas excessivas.
Fallback gracioso se Polymarket estiver indisponível.
"""

import os
import json
import time
import logging
import requests
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_CACHE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "prediction_cache.json")
_CACHE_TTL = 6 * 3600  # 6 horas

def _load_cache() -> dict:
    try:
        if os.path.exists(_CACHE_FILE):
            with open(_CACHE_FILE, "r") as f:
                data = json.load(f)
            if time.time() - data.get("_ts", 0) < _CACHE_TTL:
                return data
    except Exception:
        pass
    return {}

def _save_cache(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        data["_ts"] = time.time()
        with open(_CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log.warning(f"[prediction_engine] Falha ao salvar cache: {e}")


# ---------------------------------------------------------------------------
# Polymarket REST client (sem SDK — usa gamma-api pública)
# ---------------------------------------------------------------------------

POLYMARKET_GAMMA = "https://gamma-api.polymarket.com"
POLYMARKET_CLOB = "https://clob.polymarket.com"

_HEADERS = {
    "User-Agent": "AlphaCota/1.0 FII-Quant-Engine",
    "Accept": "application/json",
}

# Slugs e keywords de mercados relevantes para FIIs brasileiros
# Polymarket usa slugs em inglês — mapeamos para categorias internas
_MARKET_QUERIES = [
    # Fed/juros globais — impacto direto em FIIs de papel (CRI/CRA)
    {"keywords": ["fed rate cut", "federal reserve rate", "fed funds"], "category": "fed_cut"},
    # Recessão EUA — fuga para safe haven, queda no câmbio afeta FIIs
    {"keywords": ["us recession", "usa recession 2025", "usa recession 2026"], "category": "us_recession"},
    # Inflação EUA — Fed hawkish = dólar forte = BRL fraco = FIIs de papel sofrem
    {"keywords": ["us cpi", "inflation above", "pce above"], "category": "us_inflation"},
    # Commodities — FIIs de logística/agro/mineração
    {"keywords": ["oil price", "brent above", "wti above"], "category": "oil_bullish"},
    # Brazil / emerging — sinal direto
    {"keywords": ["brazil", "selic", "ipca brazil"], "category": "brazil_macro"},
]

def _search_markets(keywords: list[str], limit: int = 3) -> list[dict]:
    """Busca mercados no Polymarket por keywords."""
    results = []
    for kw in keywords:
        try:
            resp = requests.get(
                f"{POLYMARKET_GAMMA}/markets",
                params={"q": kw, "limit": limit, "active": "true", "closed": "false"},
                headers=_HEADERS,
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                markets = data if isinstance(data, list) else data.get("markets", [])
                results.extend(markets[:limit])
        except Exception as e:
            log.debug(f"[prediction_engine] Search error for '{kw}': {e}")
    return results


def _get_best_yes_prob(market: dict) -> Optional[float]:
    """Extrai probabilidade YES (0-1) de um mercado Polymarket."""
    # outcomePrices é uma lista de strings ["0.72", "0.28"]
    prices = market.get("outcomePrices")
    outcomes = market.get("outcomes")

    if prices and outcomes:
        try:
            prices_f = [float(p) for p in prices]
            outcomes_l = outcomes if isinstance(outcomes, list) else json.loads(outcomes)
            for i, outcome in enumerate(outcomes_l):
                if str(outcome).lower() in ("yes", "sim", "true"):
                    return prices_f[i] if i < len(prices_f) else None
        except Exception:
            pass

    # Fallback: bestBid / lastTradePrice
    lp = market.get("lastTradePrice") or market.get("bestBid")
    if lp is not None:
        try:
            return float(lp)
        except Exception:
            pass

    return None


# ---------------------------------------------------------------------------
# Lógica de scoring para FIIs
# ---------------------------------------------------------------------------

def _compute_fii_signal(signals: dict) -> dict:
    """
    Converte probabilidades brutas em score 0-100 favorável para FIIs.

    Lógica:
    - Fed cortando juros → bullish FIIs (capital estrangeiro volta para EM)
    - Recessão EUA → bearish (aversão a risco global)
    - Inflação alta EUA → bearish (Fed hawkish)
    - Petróleo subindo → bullish FIIs de logística/agro
    - Brazil macro positivo → bullish
    """
    score = 50.0  # neutro base
    factors = []

    fed_cut = signals.get("fed_cut")
    if fed_cut is not None:
        # Alta prob de corte = bullish (+15 pontos máx)
        contribution = (fed_cut - 0.5) * 30
        score += contribution
        factors.append({
            "factor": "Fed Rate Cut",
            "probability": round(fed_cut * 100, 1),
            "impact": round(contribution, 1),
            "direction": "bullish" if fed_cut > 0.5 else "bearish",
        })

    recession = signals.get("us_recession")
    if recession is not None:
        # Alta prob de recessão = bearish (-20 pontos máx)
        contribution = (0.5 - recession) * 40
        score += contribution
        factors.append({
            "factor": "US Recession",
            "probability": round(recession * 100, 1),
            "impact": round(contribution, 1),
            "direction": "bearish" if recession > 0.3 else "neutral",
        })

    inflation = signals.get("us_inflation")
    if inflation is not None:
        # Inflação alta = Fed hawkish = bearish (-15 pontos máx)
        contribution = (0.5 - inflation) * 30
        score += contribution
        factors.append({
            "factor": "US Inflation High",
            "probability": round(inflation * 100, 1),
            "impact": round(contribution, 1),
            "direction": "bearish" if inflation > 0.5 else "bullish",
        })

    oil = signals.get("oil_bullish")
    if oil is not None:
        # Petróleo alto = neutro/levemente bullish para FIIs de logística (+5 max)
        contribution = (oil - 0.5) * 10
        score += contribution
        factors.append({
            "factor": "Oil Price Bullish",
            "probability": round(oil * 100, 1),
            "impact": round(contribution, 1),
            "direction": "bullish" if oil > 0.5 else "neutral",
        })

    brazil = signals.get("brazil_macro")
    if brazil is not None:
        contribution = (brazil - 0.5) * 20
        score += contribution
        factors.append({
            "factor": "Brazil Macro",
            "probability": round(brazil * 100, 1),
            "impact": round(contribution, 1),
            "direction": "bullish" if brazil > 0.5 else "bearish",
        })

    score = max(0.0, min(100.0, score))

    if score >= 65:
        interpretation = "Contexto macro favorável para FIIs"
        sentiment = "bullish"
    elif score <= 35:
        interpretation = "Contexto macro desfavorável para FIIs"
        sentiment = "bearish"
    else:
        interpretation = "Contexto macro neutro para FIIs"
        sentiment = "neutral"

    return {
        "score": round(score, 1),
        "sentiment": sentiment,
        "interpretation": interpretation,
        "factors": factors,
        "markets_found": len(factors),
    }


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------

def get_prediction_signal() -> dict:
    """
    Retorna sinal macro de mercados de previsão para FIIs.

    Retorno:
        {
          "score": 0-100,           # score bullish para FIIs
          "sentiment": "bullish" | "neutral" | "bearish",
          "interpretation": str,
          "factors": [...],          # detalhes por fator
          "markets_found": int,
          "source": "polymarket" | "cache" | "fallback",
          "cached_at": float | None,
        }
    """
    # Tenta cache primeiro
    cached = _load_cache()
    if cached and "score" in cached:
        log.debug("[prediction_engine] Retornando sinal do cache")
        cached["source"] = "cache"
        return cached

    log.info("[prediction_engine] Buscando sinais no Polymarket...")

    raw_signals: dict[str, Optional[float]] = {}

    for query in _MARKET_QUERIES:
        category = query["category"]
        markets = _search_markets(query["keywords"], limit=2)

        probs = []
        for market in markets:
            p = _get_best_yes_prob(market)
            if p is not None:
                probs.append(p)
                log.debug(
                    f"[prediction_engine] {category}: '{market.get('question', '')[:60]}' → {p:.2%}"
                )

        if probs:
            raw_signals[category] = sum(probs) / len(probs)  # média das probabilidades encontradas

    if not raw_signals:
        log.warning("[prediction_engine] Nenhum mercado encontrado — usando fallback neutro")
        result = {
            "score": 50.0,
            "sentiment": "neutral",
            "interpretation": "Dados de mercados de previsão indisponíveis",
            "factors": [],
            "markets_found": 0,
            "source": "fallback",
            "cached_at": None,
        }
        return result

    result = _compute_fii_signal(raw_signals)
    result["source"] = "polymarket"
    result["cached_at"] = time.time()

    _save_cache(result)

    log.info(
        f"[prediction_engine] Score={result['score']} | {result['sentiment']} | "
        f"{result['markets_found']} fatores"
    )
    return result
