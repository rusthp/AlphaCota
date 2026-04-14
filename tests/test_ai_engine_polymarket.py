"""Tests for Polymarket AI functions in core/ai_engine.py"""

import json
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _openrouter_response(content: str) -> dict:
    """Build a minimal OpenRouter API response dict."""
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "model": "deepseek/deepseek-r1:free",
    }


def _valid_prob_json(**overrides) -> str:
    base = {
        "fair_prob": 0.72,
        "market_prob": 0.65,
        "edge": 0.07,
        "confidence": 0.80,
        "reasoning": "Strong macro signal supports YES.",
    }
    base.update(overrides)
    return json.dumps(base)


def _valid_risk_json(**overrides) -> str:
    base = {
        "kelly_fraction": 0.18,
        "max_loss_usd": 9.0,
        "recommendation": "approve",
        "reasoning": "Edge exceeds threshold.",
    }
    base.update(overrides)
    return json.dumps(base)


MOCK_MARKET = {
    "question": "Will the Fed cut rates in 2025?",
    "outcomePrices": ["0.65", "0.35"],
    "outcomes": ["Yes", "No"],
    "endDate": "2025-12-31",
}


# ---------------------------------------------------------------------------
# call_openrouter
# ---------------------------------------------------------------------------


def test_call_openrouter_requires_api_key(monkeypatch):
    from core.ai_engine import call_openrouter
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY not configured"):
        call_openrouter("model", [{"role": "user", "content": "hi"}])


def test_call_openrouter_raises_on_http_error(monkeypatch):
    from core.ai_engine import call_openrouter
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.text = "Rate limited"

    with patch("core.ai_engine.httpx.post", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="OpenRouter error 429"):
            call_openrouter("model", [])


def test_call_openrouter_returns_parsed_json(monkeypatch):
    from core.ai_engine import call_openrouter
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _openrouter_response("hello")

    with patch("core.ai_engine.httpx.post", return_value=mock_resp):
        result = call_openrouter("model", [])

    assert "choices" in result


# ---------------------------------------------------------------------------
# estimate_market_probability — valid response
# ---------------------------------------------------------------------------


def test_estimate_market_probability_valid():
    from core.ai_engine import estimate_market_probability

    mock_resp = _openrouter_response(_valid_prob_json())

    with patch("core.ai_engine.call_openrouter", return_value=mock_resp):
        result = estimate_market_probability(MOCK_MARKET, api_key="test")

    assert result is not None
    assert result["fair_prob"] == pytest.approx(0.72)
    assert result["confidence"] == pytest.approx(0.80)
    assert "reasoning" in result


def test_estimate_market_probability_with_markdown_fence():
    from core.ai_engine import estimate_market_probability

    content = "```json\n" + _valid_prob_json() + "\n```"
    mock_resp = _openrouter_response(content)

    with patch("core.ai_engine.call_openrouter", return_value=mock_resp):
        result = estimate_market_probability(MOCK_MARKET, api_key="test")

    assert result is not None
    assert result["fair_prob"] == pytest.approx(0.72)


# ---------------------------------------------------------------------------
# estimate_market_probability — JSON validation guardrails
# ---------------------------------------------------------------------------


def test_estimate_rejects_out_of_range_fair_prob():
    from core.ai_engine import estimate_market_probability

    bad_json = json.dumps({"fair_prob": 1.5, "market_prob": 0.5, "edge": 1.0, "confidence": 0.8, "reasoning": "x"})
    mock_resp = _openrouter_response(bad_json)

    with patch("core.ai_engine.call_openrouter", return_value=mock_resp):
        result = estimate_market_probability(MOCK_MARKET, api_key="test")

    assert result is None  # both attempts fail → None


def test_estimate_rejects_non_numeric_fair_prob():
    from core.ai_engine import estimate_market_probability

    bad_json = json.dumps({"fair_prob": "very likely", "market_prob": 0.5, "edge": 0, "confidence": 0.8, "reasoning": "x"})
    mock_resp = _openrouter_response(bad_json)

    with patch("core.ai_engine.call_openrouter", return_value=mock_resp):
        result = estimate_market_probability(MOCK_MARKET, api_key="test")

    assert result is None


def test_estimate_rejects_pure_text_response():
    from core.ai_engine import estimate_market_probability

    mock_resp = _openrouter_response("The probability is probably around 70% or so.")

    with patch("core.ai_engine.call_openrouter", return_value=mock_resp):
        result = estimate_market_probability(MOCK_MARKET, api_key="test")

    assert result is None


# ---------------------------------------------------------------------------
# estimate_market_probability — retry logic
# ---------------------------------------------------------------------------


def test_estimate_retries_once_on_bad_json():
    from core.ai_engine import estimate_market_probability

    bad = _openrouter_response("not json")
    good = _openrouter_response(_valid_prob_json())
    responses = [bad, good]

    with patch("core.ai_engine.call_openrouter", side_effect=responses):
        result = estimate_market_probability(MOCK_MARKET, api_key="test")

    assert result is not None
    assert result["fair_prob"] == pytest.approx(0.72)


def test_estimate_returns_none_on_second_failure():
    from core.ai_engine import estimate_market_probability

    bad = _openrouter_response("still not json")

    with patch("core.ai_engine.call_openrouter", return_value=bad):
        result = estimate_market_probability(MOCK_MARKET, api_key="test")

    assert result is None


def test_estimate_returns_none_on_network_exception():
    from core.ai_engine import estimate_market_probability

    with patch("core.ai_engine.call_openrouter", side_effect=ConnectionError("timeout")):
        result = estimate_market_probability(MOCK_MARKET, api_key="test")

    assert result is None


# ---------------------------------------------------------------------------
# assess_trade_risk_ai — valid response
# ---------------------------------------------------------------------------


def test_assess_trade_risk_valid():
    from core.ai_engine import assess_trade_risk_ai

    mock_resp = _openrouter_response(_valid_risk_json())

    with patch("core.ai_engine.call_openrouter", return_value=mock_resp):
        result = assess_trade_risk_ai(MOCK_MARKET, "yes", 25.0, api_key="test")

    assert result is not None
    assert result["recommendation"] == "approve"
    assert result["kelly_fraction"] <= 0.25


def test_assess_trade_risk_kelly_capped_at_025():
    from core.ai_engine import assess_trade_risk_ai

    high_kelly = _valid_risk_json(kelly_fraction=0.9)
    mock_resp = _openrouter_response(high_kelly)

    with patch("core.ai_engine.call_openrouter", return_value=mock_resp):
        result = assess_trade_risk_ai(MOCK_MARKET, "yes", 25.0, api_key="test")

    assert result is not None
    assert result["kelly_fraction"] == pytest.approx(0.25)


def test_assess_trade_risk_returns_none_on_failure():
    from core.ai_engine import assess_trade_risk_ai

    with patch("core.ai_engine.call_openrouter", return_value=_openrouter_response("bad")):
        result = assess_trade_risk_ai(MOCK_MARKET, "yes", 25.0, api_key="test")

    assert result is None


def test_assess_trade_risk_retries_once():
    from core.ai_engine import assess_trade_risk_ai

    responses = [
        _openrouter_response("garbage"),
        _openrouter_response(_valid_risk_json()),
    ]

    with patch("core.ai_engine.call_openrouter", side_effect=responses):
        result = assess_trade_risk_ai(MOCK_MARKET, "yes", 25.0, api_key="test")

    assert result is not None
    assert result["recommendation"] == "approve"
