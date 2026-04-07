"""Tests for core/ai_engine.py — Groq/Llama AI analysis with mocks."""

import sys
import importlib
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core.ai_engine as ai


class TestAnalyzeFiiNews:
    def test_missing_api_key_returns_error(self):
        with patch.dict("os.environ", {}, clear=True), patch.object(ai, "HAS_GROQ", True):
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

        with patch.object(ai, "HAS_GROQ", True), patch.object(ai, "Groq", mock_client):
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

        with patch.object(ai, "HAS_GROQ", True), patch.object(ai, "Groq", mock_client):
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

        with (
            patch.object(ai, "HAS_GROQ", True),
            patch.object(ai, "Groq", mock_client),
            patch.dict("os.environ", {"GROQ_API_KEY": "env-key"}),
        ):
            result = ai.analyze_fii_news("XPML11", [{"titulo": "test"}])
            assert result["success"] is True

    def test_news_without_date_field(self):
        """Covers news items that omit the 'data' key (falls back to 'sem data')."""
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "NEUTRO"
        mock_client.return_value.chat.completions.create.return_value = mock_completion

        with patch.object(ai, "HAS_GROQ", True), patch.object(ai, "Groq", mock_client):
            result = ai.analyze_fii_news("HGLG11", [{"titulo": "sem data aqui"}], api_key="key")
            assert result["success"] is True
            assert result["news_count"] == 1


class TestGetVectorizerContext:
    def test_returns_empty_string_when_vectorizer_is_none(self):
        with patch.object(ai, "_vectorizer", None):
            result = ai.get_vectorizer_context("query text")
            assert result == ""

    def test_returns_context_when_vectorizer_available(self):
        mock_vec = MagicMock()
        mock_vec.get_context_for_query.return_value = "relevant context snippet"
        with patch.object(ai, "_vectorizer", mock_vec):
            result = ai.get_vectorizer_context("HGLG11 FII dividendos", limit=2)
            assert result == "relevant context snippet"
            mock_vec.get_context_for_query.assert_called_once_with(
                "HGLG11 FII dividendos", limit=2
            )

    def test_returns_empty_string_on_vectorizer_exception(self):
        mock_vec = MagicMock()
        mock_vec.get_context_for_query.side_effect = RuntimeError("connection failed")
        with patch.object(ai, "_vectorizer", mock_vec):
            result = ai.get_vectorizer_context("some query")
            assert result == ""

    def test_rag_context_included_in_prompt_when_available(self):
        """When vectorizer returns content, the RAG section is included in the Groq prompt."""
        mock_vec = MagicMock()
        mock_vec.get_context_for_query.return_value = "extra rag context"

        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "POSITIVO"
        mock_client.return_value.chat.completions.create.return_value = mock_completion

        with (
            patch.object(ai, "HAS_GROQ", True),
            patch.object(ai, "Groq", mock_client),
            patch.object(ai, "_vectorizer", mock_vec),
        ):
            result = ai.analyze_fii_news(
                "MXRF11", [{"titulo": "Dividendo alto", "data": "2025-01"}], api_key="key"
            )
            assert result["success"] is True
            # Verify the prompt passed to Groq contains the RAG context
            call_args = mock_client.return_value.chat.completions.create.call_args
            messages = call_args.kwargs["messages"]
            user_msg = messages[1]["content"]
            assert "extra rag context" in user_msg


class TestModuleImportGuards:
    """Cover the except ImportError branches at module load time (lines 19-20, 26-27)."""

    def test_has_groq_false_when_groq_not_importable(self):
        """Reload core.ai_engine with 'groq' blocked — HAS_GROQ must be False."""
        # Remove cached module so reload re-executes top-level code
        sys.modules.pop("core.ai_engine", None)
        # Block the groq package so the try/except ImportError fires
        sys.modules["groq"] = None  # type: ignore[assignment]
        try:
            reloaded = importlib.import_module("core.ai_engine")
            assert reloaded.HAS_GROQ is False
        finally:
            # Restore original state so other tests are unaffected
            sys.modules.pop("groq", None)
            sys.modules.pop("core.ai_engine", None)
            importlib.import_module("core.ai_engine")

    def test_vectorizer_none_when_vectorizer_client_not_importable(self):
        """Reload core.ai_engine with 'data.vectorizer_client' blocked — _vectorizer must be None."""
        sys.modules.pop("core.ai_engine", None)
        # Block the vectorizer_client module so the try/except ImportError fires
        sys.modules["data.vectorizer_client"] = None  # type: ignore[assignment]
        try:
            reloaded = importlib.import_module("core.ai_engine")
            assert reloaded._vectorizer is None
        finally:
            sys.modules.pop("data.vectorizer_client", None)
            sys.modules.pop("core.ai_engine", None)
            importlib.import_module("core.ai_engine")
