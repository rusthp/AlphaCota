"""
core/ai_engine.py

Motor de analise de sentimento via Groq/Llama para FIIs.
Migrado de cota_ai/ai_service.py com melhorias:
- Import defensivo (HAS_GROQ flag)
- Sem side effects (load_dotenv removido, key via parametro)
- Funcao pura com retorno estruturado
- RAG via Vectorizer para contexto enriquecido
- OpenRouter integration para DeepSeek-R1 e Qwen (Polymarket)
"""

import json
import os

import httpx

from core.ai_cache import get_cached_sentiment, save_cached_sentiment
from core.logger import logger

try:
    from groq import Groq

    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False

try:
    from data.vectorizer_client import VectorizerClient

    _vectorizer = VectorizerClient()
except ImportError:
    _vectorizer = None


def get_vectorizer_context(query: str, limit: int = 3) -> str:
    """Busca contexto relevante no vectorizer para enriquecer prompts (RAG).

    Args:
        query: Texto de busca.
        limit: Máximo de trechos retornados.

    Returns:
        String com trechos relevantes do codebase ou vazio se indisponível.
    """
    if _vectorizer is None:
        return ""
    try:
        return _vectorizer.get_context_for_query(query, limit=limit)
    except Exception as e:
        logger.debug("Vectorizer context unavailable: %s", e)
        return ""


def analyze_fii_news(ticker: str, news_list: list[dict], api_key: str | None = None) -> dict:
    """Analisa noticias de um FII usando Groq/Llama e retorna sentimento estruturado.

    Args:
        ticker: Codigo do FII (ex: HGLG11)
        news_list: Lista de dicts com keys 'titulo', 'data', 'link'
        api_key: Groq API key. Se None, usa env var GROQ_API_KEY.

    Returns:
        Dict com keys: success, sentiment, summary, dividend_impact, raw_response
    """
    key = api_key or os.getenv("GROQ_API_KEY")

    cached = get_cached_sentiment(ticker)
    if cached:
        logger.info(f"Usando sentimento em cache para {ticker}")
        cached["news"] = news_list # anexando
        return cached

    if not key:
        return {"success": False, "error": "GROQ_API_KEY nao configurada"}

    if not HAS_GROQ:
        return {"success": False, "error": "Biblioteca groq nao instalada (pip install groq)"}

    if not news_list:
        return {"success": False, "error": "Nenhuma noticia fornecida para analise"}

    texto_noticias = "\n".join([f"- {n['titulo']} ({n.get('data', 'sem data')})" for n in news_list])

    # RAG: buscar contexto relevante no vectorizer
    rag_context = get_vectorizer_context(f"{ticker} FII análise dividendos", limit=3)
    rag_section = ""
    if rag_context:
        rag_section = f"""

    Contexto adicional da base de conhecimento:
    {rag_context}
    """

    prompt = f"""
    Voce e um analista senior de Fundos Imobiliarios (FIIs) do Brasil.
    Leia as seguintes manchetes recentes sobre o fundo {ticker}:

    {texto_noticias}
    {rag_section}
    Com base nessas noticias, forneca:
    1. Sentimento do Mercado: (Responda apenas POSITIVO, NEGATIVO ou NEUTRO)
    2. Resumo Executivo: Um paragrafo de ate 3 linhas resumindo o que esta acontecendo com o fundo.
    3. Impacto nos Dividendos: Ha algum risco ou chance de aumento de dividendos citado?

    Responda em Portugues do Brasil.
    """

    try:
        client = Groq(api_key=key)
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Voce e um analista financeiro especializado em FIIs."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
            max_tokens=1024,
        )
        raw = completion.choices[0].message.content

        # Extrair sentiment_score estruturado a partir da resposta textual
        raw_upper = raw.upper()
        if "POSITIVO" in raw_upper:
            sentiment_score = 1.0
        elif "NEGATIVO" in raw_upper:
            sentiment_score = -1.0
        else:
            sentiment_score = 0.0

        response_dict = {
            "success": True,
            "raw_response": raw,
            "ticker": ticker,
            "news_count": len(news_list),
            "sentiment_score": sentiment_score,
        }

        # Save to SQLite
        save_cached_sentiment(response_dict)

        return response_dict
    except Exception as e:
        return {"success": False, "error": f"Erro ao acionar Groq: {e!s}"}


# ---------------------------------------------------------------------------
# OpenRouter integration — Polymarket AI functions
# ---------------------------------------------------------------------------

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_DEEPSEEK_R1 = "deepseek/deepseek-r1:free"
_QWEN_CODER = "qwen/qwen3-coder:free"


def call_openrouter(
    model: str,
    messages: list[dict],
    response_format: dict | None = None,
    api_key: str | None = None,
    timeout: float = 30.0,
) -> dict:
    """Call OpenRouter API (OpenAI-compatible) and return the raw response dict.

    Args:
        model: OpenRouter model ID (e.g. "deepseek/deepseek-r1:free").
        messages: List of {role, content} dicts.
        response_format: Optional {"type": "json_object"} for JSON mode.
        api_key: OpenRouter API key. Falls back to OPENROUTER_API_KEY env var.
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON response dict from OpenRouter.

    Raises:
        RuntimeError: On HTTP error or missing API key.
    """
    key = api_key or os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not configured")

    payload: dict = {"model": model, "messages": messages}
    if response_format:
        payload["response_format"] = response_format

    resp = httpx.post(
        f"{_OPENROUTER_BASE}/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/alphacota",
            "X-Title": "AlphaCota Polymarket Trader",
        },
        json=payload,
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"OpenRouter error {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def _extract_content(response: dict) -> str:
    """Pull assistant message content from OpenRouter response."""
    try:
        return response["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError):
        return ""


def _parse_prob_json(content: str) -> dict | None:
    """Parse and validate probability estimation JSON from AI response.

    Expected keys: fair_prob, market_prob, edge, confidence, reasoning.
    fair_prob and confidence must be floats in [0, 1].
    Returns None if validation fails.
    """
    # Strip markdown code fences if present
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object inside the text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        try:
            data = json.loads(text[start:end])
        except json.JSONDecodeError:
            return None

    fair_prob = data.get("fair_prob")
    confidence = data.get("confidence")

    if not isinstance(fair_prob, (int, float)) or not (0.0 <= float(fair_prob) <= 1.0):
        return None
    if confidence is not None and not (0.0 <= float(confidence) <= 1.0):
        return None

    return {
        "fair_prob": float(fair_prob),
        "market_prob": float(data.get("market_prob") or 0.5),
        "edge": float(data.get("edge") or (float(fair_prob) - float(data.get("market_prob") or 0.5))),
        "confidence": float(confidence) if confidence is not None else 0.5,
        "reasoning": str(data.get("reasoning") or ""),
    }


def estimate_market_probability(market: dict, context: str = "", api_key: str | None = None) -> dict | None:
    """Estimate fair probability for a Polymarket binary market using DeepSeek-R1.

    Calls OpenRouter with deepseek/deepseek-r1:free. Validates that the response
    is numeric JSON with fair_prob in [0, 1]. Retries once on parse failure.
    Returns None on second failure (no AI signal rather than bad signal).

    Args:
        market: Polymarket market dict with at least 'question' key.
        context: Optional additional context (news, macro data) to include.
        api_key: OpenRouter API key. Falls back to env var.

    Returns:
        Dict with fair_prob, market_prob, edge, confidence, reasoning — or None.
    """
    question = market.get("question", "")
    market_prob = None
    prices = market.get("outcomePrices")
    outcomes = market.get("outcomes")
    if prices and outcomes:
        try:
            prices_f = [float(p) for p in prices]
            outcomes_l = outcomes if isinstance(outcomes, list) else json.loads(outcomes)
            for i, o in enumerate(outcomes_l):
                if str(o).lower() in ("yes", "sim", "true") and i < len(prices_f):
                    market_prob = prices_f[i]
                    break
        except Exception:
            pass
    if market_prob is None:
        market_prob = float(market.get("lastTradePrice") or market.get("bestBid") or 0.5)

    system_prompt = (
        "You are a calibrated forecaster specialising in prediction markets. "
        "You must output ONLY a JSON object — no markdown, no prose. "
        'Format: {"fair_prob": <float 0-1>, "market_prob": <float 0-1>, '
        '"edge": <float>, "confidence": <float 0-1>, "reasoning": "<one sentence>"}'
    )
    user_prompt = (
        f"Market question: {question}\n"
        f"Current market probability (YES): {market_prob:.2%}\n"
    )
    if context:
        user_prompt += f"\nAdditional context:\n{context}\n"
    user_prompt += (
        "\nEstimate the TRUE probability of YES resolution. "
        "Account for base rates, resolution criteria, and any asymmetric information. "
        "Output JSON only."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    for attempt in range(2):
        try:
            response = call_openrouter(_DEEPSEEK_R1, messages, api_key=api_key)
            content = _extract_content(response)
            result = _parse_prob_json(content)
            if result is not None:
                return result
            logger.warning("estimate_market_probability: invalid JSON on attempt %d", attempt + 1)
        except Exception as exc:
            logger.warning("estimate_market_probability attempt %d failed: %s", attempt + 1, exc)

    return None


def assess_trade_risk_ai(
    market: dict,
    direction: str,
    size_usd: float,
    api_key: str | None = None,
) -> dict | None:
    """AI-powered trade risk assessment using Qwen3-Coder via OpenRouter.

    Args:
        market: Polymarket market dict.
        direction: "yes" or "no".
        size_usd: Proposed position size in USD.
        api_key: OpenRouter API key.

    Returns:
        Dict with kelly_fraction, max_loss_usd, recommendation, reasoning — or None.
    """
    question = market.get("question", "")
    end_date = market.get("endDate") or market.get("endDateIso") or "unknown"

    system_prompt = (
        "You are a quantitative risk manager for a prediction market trading system. "
        "Output ONLY a JSON object with these keys: "
        '{"kelly_fraction": <float 0-1>, "max_loss_usd": <float>, '
        '"recommendation": "approve"|"reject"|"reduce", "reasoning": "<one sentence>"}'
    )
    user_prompt = (
        f"Market: {question}\n"
        f"Direction: {direction.upper()}\n"
        f"Proposed size: ${size_usd:.2f} USD\n"
        f"Resolution date: {end_date}\n"
        "\nAssess risk. Apply full Kelly criterion for binary markets "
        "(f* = (p*b - q) / b). Cap Kelly at 0.25. "
        "Reject if size > kelly * bankroll assumption of $500. Output JSON only."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    for attempt in range(2):
        try:
            response = call_openrouter(_QWEN_CODER, messages, api_key=api_key)
            content = _extract_content(response)
            text = content.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > 0:
                data = json.loads(text[start:end])
                kelly = float(data.get("kelly_fraction") or 0.0)
                if 0.0 <= kelly <= 1.0 and "recommendation" in data:
                    return {
                        "kelly_fraction": min(kelly, 0.25),
                        "max_loss_usd": float(data.get("max_loss_usd") or size_usd),
                        "recommendation": str(data.get("recommendation", "reject")),
                        "reasoning": str(data.get("reasoning", "")),
                    }
            logger.warning("assess_trade_risk_ai: invalid JSON on attempt %d", attempt + 1)
        except Exception as exc:
            logger.warning("assess_trade_risk_ai attempt %d failed: %s", attempt + 1, exc)

    return None
