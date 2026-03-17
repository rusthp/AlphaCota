"""Tests for core/ai_engine.py — Groq/Llama AI analysis with mocks."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core.ai_engine as ai


class TestAnalyzeFiiNews:
    def test_missing_api_key_returns_error(self):
        with patch.dict("os.environ", {}, clear=True), \
             patch.object(ai, "HAS_GROQ", True):
            result = ai.analyze_fii_news("HGLG11", [{"titulo": "test", "data": "today"}])
            assert result["success"] is False
            assert "GROQ_API_KEY" in result["error"]

    def test_groq_not_installed_returns_error(self):
        with patch.object(ai, "HAS_GROQ", False):
            result = ai.analyze_fii_news("HGLG11", [{"titulo": "test"}], api_key="fake-key")
            assert result["success"] is False
            assert "groq" in result["error"].lower()

    def test_empty_news_returns_error(self):
        with patch.object(ai, "HAS_GROQ", True):
            result = ai.analyze_fii_news("HGLG11", [], api_key="fake-key")
            assert result["success"] is False
            assert "noticia" in result["error"].lower()

    def test_successful_analysis(self):
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "POSITIVO\nResumo: Fundo em alta."
        mock_client.return_value.chat.completions.create.return_value = mock_completion

        with patch.object(ai, "HAS_GROQ", True), \
             patch.object(ai, "Groq", mock_client):
            news = [
                {"titulo": "HGLG11 aumenta dividendos", "data": "2025-03-01"},
                {"titulo": "Setor logistico em expansao", "data": "2025-03-02"},
            ]
            result = ai.analyze_fii_news("HGLG11", news, api_key="test-key")
            assert result["success"] is True
            assert result["ticker"] == "HGLG11"
            assert result["news_count"] == 2
            assert "raw_response" in result

    def test_groq_api_exception(self):
        mock_client = MagicMock()
        mock_client.return_value.chat.completions.create.side_effect = Exception("Rate limit")

        with patch.object(ai, "HAS_GROQ", True), \
             patch.object(ai, "Groq", mock_client):
            news = [{"titulo": "test", "data": "today"}]
            result = ai.analyze_fii_news("HGLG11", news, api_key="test-key")
            assert result["success"] is False
            assert "Rate limit" in result["error"]

    def test_uses_env_api_key(self):
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "NEUTRO"
        mock_client.return_value.chat.completions.create.return_value = mock_completion

        with patch.object(ai, "HAS_GROQ", True), \
             patch.object(ai, "Groq", mock_client), \
             patch.dict("os.environ", {"GROQ_API_KEY": "env-key"}):
            result = ai.analyze_fii_news("XPML11", [{"titulo": "test"}])
            assert result["success"] is True
