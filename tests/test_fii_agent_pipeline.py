"""
tests/test_fii_agent_pipeline.py

Testes unitários para core/fii_agent_pipeline.py.

Cobre:
- PipelineState initialization
- Cada agente individualmente (happy path + fallback por exceção)
- DDM calculation correctness (deterministic, not AI)
- run_deep_analysis end-to-end (success, partial failure, HAS_GROQ=False)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core.fii_agent_pipeline as pipeline
from core.fii_agent_pipeline import (
    PipelineState,
    decision_agent,
    fundamental_agent,
    macro_agent,
    persona_agent,
    risk_agent,
    run_deep_analysis,
)

# ---------------------------------------------------------------------------
# Fixtures — dados realistas reutilizados entre testes
# ---------------------------------------------------------------------------

def _make_state(
    ticker: str = "HGLG11",
    dy: float = 0.095,
    pvp: float = 0.98,
    price: float = 155.0,
    dividend_monthly: float = 1.22,
    selic: float = 10.75,
) -> PipelineState:
    return PipelineState(
        ticker=ticker,
        fii_data={
            "ticker": ticker,
            "segment": "Logística",
            "price": price,
            "dividend_monthly": dividend_monthly,
            "fundamentals": {
                "dividend_yield": dy,
                "pvp": pvp,
                "vacancia": 0.03,
                "vacancy_rate": 0.03,
                "debt_ratio": 0.22,
                "liquidez_diaria": 8_000_000,
                "dividend_consistency": 85.0,
            },
            "score_breakdown": {
                "total": 82,
                "alpha_score": 82,
            },
            "vol_30d": 12.5,
        },
        macro={
            "selic_anual": selic,
            "cdi_anual": selic - 0.10,
            "ipca_anual": 4.83,
            "premio_risco": selic - 4.83,
        },
        news=[
            {"titulo": "HGLG11 renova contratos por 5 anos", "data": "2025-04-01"},
            {"titulo": "Setor logístico resiliente em 2025", "data": "2025-04-02"},
        ],
    )


def _groq_response(content: str) -> MagicMock:
    """Cria um mock de resposta Groq que retorna `content`."""
    mock_client = MagicMock()
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock()]
    mock_completion.choices[0].message.content = content
    mock_client.return_value.chat.completions.create.return_value = mock_completion
    return mock_client


# ---------------------------------------------------------------------------
# PipelineState
# ---------------------------------------------------------------------------

class TestPipelineState:
    def test_initialization_defaults(self):
        state = _make_state()
        assert state.ticker == "HGLG11"
        assert state.macro_analysis == {}
        assert state.fundamental_analysis == {}
        assert state.risk_analysis == {}
        assert state.persona_analysis == {}
        assert state.final_decision == {}
        assert state.errors == []

    def test_ticker_preserved_as_given(self):
        state = _make_state(ticker="MXRF11")
        assert state.ticker == "MXRF11"

    def test_errors_list_is_independent(self):
        s1 = _make_state()
        s2 = _make_state()
        s1.errors.append("err")
        assert s2.errors == []


# ---------------------------------------------------------------------------
# MacroAgent
# ---------------------------------------------------------------------------

class TestMacroAgent:
    _VALID_RESPONSE = json.dumps({
        "ciclo_juros": "estavel",
        "impacto_fii": "neutro",
        "spread_atrativo": True,
        "dy_real": 4.67,
        "yield_minimo_aceitavel": 11.5,
        "contexto": "SELIC estável. FIIs de tijolo se beneficiam.",
        "alerta": None,
    })

    def test_happy_path_populates_macro_analysis(self):
        state = _make_state()
        mock_client = _groq_response(self._VALID_RESPONSE)

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
        ):
            macro_agent(state, api_key="test-key")

        assert state.macro_analysis["ciclo_juros"] == "estavel"
        assert state.macro_analysis["impacto_fii"] == "neutro"
        assert state.errors == []

    def test_dy_real_overridden_by_deterministic_calculation(self):
        """dy_real deve ser calculado deterministicamente, não vir do LLM."""
        state = _make_state(dy=0.12, selic=10.75)  # DY 12%, IPCA 4.83%
        # LLM retorna um dy_real incorreto de propósito
        bad_response = json.dumps({
            "ciclo_juros": "estavel",
            "impacto_fii": "neutro",
            "spread_atrativo": True,
            "dy_real": 999.0,  # errado
            "yield_minimo_aceitavel": 11.5,
            "contexto": "Contexto.",
            "alerta": None,
        })
        mock_client = _groq_response(bad_response)

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
        ):
            macro_agent(state, api_key="test-key")

        # DY 12% - IPCA 4.83% = 7.17%
        assert abs(state.macro_analysis["dy_real"] - 7.17) < 0.01

    def test_spread_cdi_added(self):
        """spread_cdi deve estar presente após execução."""
        state = _make_state(dy=0.11)
        mock_client = _groq_response(self._VALID_RESPONSE)

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
        ):
            macro_agent(state, api_key="test-key")

        assert "spread_cdi" in state.macro_analysis

    def test_fallback_on_groq_exception(self):
        """Quando Groq lança exceção, macro_analysis deve ter fallback válido."""
        state = _make_state()
        mock_client = MagicMock()
        mock_client.return_value.chat.completions.create.side_effect = Exception("timeout")

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
        ):
            macro_agent(state, api_key="test-key")

        assert len(state.errors) == 1
        assert "MacroAgent" in state.errors[0]
        assert "ciclo_juros" in state.macro_analysis
        assert "dy_real" in state.macro_analysis

    def test_fallback_on_invalid_json(self):
        """Resposta não-JSON deve resultar em fallback sem crash."""
        state = _make_state()
        mock_client = _groq_response("Desculpe, não posso analisar isso.")

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
        ):
            macro_agent(state, api_key="test-key")

        assert len(state.errors) == 1
        assert state.macro_analysis != {}


# ---------------------------------------------------------------------------
# FundamentalAgent
# ---------------------------------------------------------------------------

class TestFundamentalAgent:
    _VALID_RESPONSE = json.dumps({
        "qualidade": "boa",
        "pvp_status": "barato",
        "dy_sustentavel": True,
        "ddm_preco_justo": 160.0,
        "ddm_upside_pct": 3.2,
        "pontos_fortes": ["DY acima do CDI", "Baixa vacância"],
        "pontos_fracos": ["Endividamento moderado"],
        "resumo": "Bons fundamentos. P/VP abaixo da média histórica.",
    })

    def _state_with_macro(self) -> PipelineState:
        state = _make_state(price=155.0, dividend_monthly=1.22)
        state.macro_analysis = {
            "ciclo_juros": "estavel",
            "impacto_fii": "neutro",
            "spread_atrativo": True,
            "dy_real": 4.67,
            "spread_cdi": 1.15,
            "contexto": "SELIC estável.",
            "alerta": None,
        }
        return state

    def test_happy_path_populates_fundamental_analysis(self):
        state = self._state_with_macro()
        mock_client = _groq_response(self._VALID_RESPONSE)

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
        ):
            fundamental_agent(state, api_key="test-key")

        assert state.fundamental_analysis["qualidade"] == "boa"
        assert state.fundamental_analysis["pvp_status"] == "barato"
        assert state.errors == []

    def test_ddm_values_overridden_by_deterministic_calculation(self):
        """ddm_preco_justo e ddm_upside_pct são calculados deterministicamente."""
        state = self._state_with_macro()
        # LLM retorna valores errados
        bad_response = json.dumps({
            "qualidade": "boa",
            "pvp_status": "barato",
            "dy_sustentavel": True,
            "ddm_preco_justo": 9999.0,
            "ddm_upside_pct": 9999.0,
            "pontos_fortes": [],
            "pontos_fracos": [],
            "resumo": "test",
        })
        mock_client = _groq_response(bad_response)

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
        ):
            fundamental_agent(state, api_key="test-key")

        # DDM: div_mensal / ((cdi+2%)/12 mensal)
        # Com CDI=10.65%, taxa desconto anual=12.65%, mensal≈0.9965%
        # ddm = 1.22 / 0.009965 ≈ 122.44 (aproximado)
        ddm = state.fundamental_analysis["ddm_preco_justo"]
        assert ddm is not None
        assert 100 < ddm < 250  # sanity bounds

    def test_ddm_none_when_no_dividend(self):
        """Sem dividendo mensal, DDM deve ser None."""
        state = self._state_with_macro()
        state.fii_data["dividend_monthly"] = 0.0
        mock_client = _groq_response(self._VALID_RESPONSE)

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
        ):
            fundamental_agent(state, api_key="test-key")

        assert state.fundamental_analysis["ddm_preco_justo"] is None
        assert state.fundamental_analysis["ddm_upside_pct"] is None

    def test_fallback_on_groq_exception(self):
        state = self._state_with_macro()
        mock_client = MagicMock()
        mock_client.return_value.chat.completions.create.side_effect = Exception("error")

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
        ):
            fundamental_agent(state, api_key="test-key")

        assert len(state.errors) == 1
        assert "FundamentalAgent" in state.errors[0]
        assert "qualidade" in state.fundamental_analysis


# ---------------------------------------------------------------------------
# RiskAgent
# ---------------------------------------------------------------------------

class TestRiskAgent:
    _VALID_RESPONSE = json.dumps({
        "nivel_risco": "baixo",
        "risco_liquidez": "baixo",
        "risco_credito": "baixo",
        "risco_vacancia": "baixo",
        "risco_juros": "baixo",
        "var_estimado_5pct": "-5% em 30d",
        "cenario_stress": "Queda de 8% com SELIC +2pp",
        "resumo_risco": "FII bem gerido. Risco controlado.",
    })

    def _state_with_prev(self) -> PipelineState:
        state = _make_state()
        state.macro_analysis = {
            "ciclo_juros": "estavel",
            "contexto": "SELIC estável.",
            "alerta": None,
        }
        state.fundamental_analysis = {
            "qualidade": "boa",
            "resumo": "Bons fundamentos.",
        }
        return state

    def test_happy_path(self):
        state = self._state_with_prev()
        mock_client = _groq_response(self._VALID_RESPONSE)

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
        ):
            risk_agent(state, api_key="test-key")

        assert state.risk_analysis["nivel_risco"] == "baixo"
        assert state.errors == []

    def test_papel_fii_marked_as_juros_sensitive(self):
        """FIIs de papel devem ter risco_juros='alto' no fallback."""
        state = self._state_with_prev()
        state.fii_data["segment"] = "Papel (CRI)"
        mock_client = MagicMock()
        mock_client.return_value.chat.completions.create.side_effect = Exception("error")

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
        ):
            risk_agent(state, api_key="test-key")

        assert state.risk_analysis["risco_juros"] == "alto"

    def test_high_vacancy_raises_risk_in_fallback(self):
        """Vacância > 15% deve resultar em risco_vacancia='alto' no fallback."""
        state = self._state_with_prev()
        state.fii_data["fundamentals"]["vacancia"] = 0.20  # 20%
        mock_client = MagicMock()
        mock_client.return_value.chat.completions.create.side_effect = Exception("error")

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
        ):
            risk_agent(state, api_key="test-key")

        assert state.risk_analysis["risco_vacancia"] == "alto"

    def test_fallback_on_groq_exception(self):
        state = self._state_with_prev()
        mock_client = MagicMock()
        mock_client.return_value.chat.completions.create.side_effect = Exception("error")

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
        ):
            risk_agent(state, api_key="test-key")

        assert "RiskAgent" in state.errors[0]
        assert "nivel_risco" in state.risk_analysis


# ---------------------------------------------------------------------------
# PersonaAgent
# ---------------------------------------------------------------------------

class TestPersonaAgent:
    _VALID_RESPONSE = json.dumps({
        "barsi": {
            "opiniao": "comprar",
            "raciocinio": "DY consistente acima da inflação. Margem de segurança presente.",
            "condicao_entrada": "Manter se DY não cair abaixo de 8%.",
        },
        "crescimento": {
            "opiniao": "aguardar",
            "raciocinio": "Upside limitado pelo P/VP próximo de 1.",
            "condicao_entrada": "Comprar se P/VP cair para 0.85.",
        },
    })

    def _state_with_prev(self) -> PipelineState:
        state = _make_state()
        state.macro_analysis = {"ciclo_juros": "estavel", "dy_real": 4.5, "spread_cdi": 1.2}
        state.fundamental_analysis = {
            "qualidade": "boa",
            "pvp_status": "barato",
            "dy_sustentavel": True,
            "ddm_upside_pct": 5.0,
        }
        state.risk_analysis = {
            "nivel_risco": "baixo",
            "cenario_stress": "Queda de 5% com SELIC +2pp",
        }
        return state

    def test_happy_path_returns_both_personas(self):
        state = self._state_with_prev()
        mock_client = _groq_response(self._VALID_RESPONSE)

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
        ):
            persona_agent(state, api_key="test-key")

        assert "barsi" in state.persona_analysis
        assert "crescimento" in state.persona_analysis
        assert state.persona_analysis["barsi"]["opiniao"] == "comprar"
        assert state.errors == []

    def test_fallback_has_both_personas(self):
        state = self._state_with_prev()
        mock_client = MagicMock()
        mock_client.return_value.chat.completions.create.side_effect = Exception("error")

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
        ):
            persona_agent(state, api_key="test-key")

        assert "barsi" in state.persona_analysis
        assert "crescimento" in state.persona_analysis
        assert "PersonaAgent" in state.errors[0]


# ---------------------------------------------------------------------------
# DecisionAgent
# ---------------------------------------------------------------------------

class TestDecisionAgent:
    _VALID_RESPONSE = json.dumps({
        "recomendacao": "COMPRAR",
        "forca_sinal": "moderado",
        "preco_entrada_ideal": 152.0,
        "preco_alvo_12m": 165.0,
        "stop_sugerido": 140.0,
        "dy_alvo_minimo": 9.5,
        "tese": "FII de qualidade com DY atrativo e risco controlado.",
        "gatilhos_compra": ["P/VP cair abaixo de 0.9"],
        "gatilhos_saida": ["Vacância superar 10%"],
        "rating": "B",
    })

    def _state_full(self) -> PipelineState:
        state = _make_state()
        state.macro_analysis = {
            "contexto": "SELIC estável.",
            "spread_cdi": 1.2,
        }
        state.fundamental_analysis = {
            "resumo": "Bons fundamentos.",
            "qualidade": "boa",
            "pvp_status": "barato",
            "ddm_preco_justo": 160.0,
            "ddm_upside_pct": 3.2,
        }
        state.risk_analysis = {
            "resumo_risco": "Risco controlado.",
            "nivel_risco": "baixo",
        }
        state.persona_analysis = {
            "barsi": {"opiniao": "comprar"},
            "crescimento": {"opiniao": "aguardar"},
        }
        return state

    def test_happy_path_returns_recommendation(self):
        state = self._state_full()
        mock_client = _groq_response(self._VALID_RESPONSE)

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
        ):
            decision_agent(state, api_key="test-key")

        assert state.final_decision["recomendacao"] == "COMPRAR"
        assert state.final_decision["rating"] == "B"
        assert state.errors == []

    def test_fallback_returns_aguardar(self):
        state = self._state_full()
        mock_client = MagicMock()
        mock_client.return_value.chat.completions.create.side_effect = Exception("error")

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
        ):
            decision_agent(state, api_key="test-key")

        assert state.final_decision["recomendacao"] == "AGUARDAR"
        assert state.final_decision["rating"] == "C"
        assert "DecisionAgent" in state.errors[0]

    def test_fallback_ddm_preco_alvo(self):
        """No fallback, preco_alvo_12m deve usar ddm_preco_justo dos fundamentos."""
        state = self._state_full()
        mock_client = MagicMock()
        mock_client.return_value.chat.completions.create.side_effect = Exception("error")

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
        ):
            decision_agent(state, api_key="test-key")

        assert state.final_decision["preco_alvo_12m"] == 160.0


# ---------------------------------------------------------------------------
# run_deep_analysis — pipeline completo
# ---------------------------------------------------------------------------

class TestRunDeepAnalysis:
    def _all_agents_response(self) -> MagicMock:
        """Mock que retorna JSON válido para qualquer chamada Groq."""
        responses = [
            json.dumps({
                "ciclo_juros": "estavel", "impacto_fii": "neutro",
                "spread_atrativo": True, "dy_real": 4.5,
                "yield_minimo_aceitavel": 11.0,
                "contexto": "SELIC estável.", "alerta": None,
            }),
            json.dumps({
                "qualidade": "boa", "pvp_status": "barato",
                "dy_sustentavel": True, "ddm_preco_justo": 160.0,
                "ddm_upside_pct": 3.2,
                "pontos_fortes": ["DY bom"], "pontos_fracos": [],
                "resumo": "Fundamentos sólidos.",
            }),
            json.dumps({
                "nivel_risco": "baixo", "risco_liquidez": "baixo",
                "risco_credito": "baixo", "risco_vacancia": "baixo",
                "risco_juros": "baixo", "var_estimado_5pct": "-5%",
                "cenario_stress": "Queda de 5%",
                "resumo_risco": "Risco baixo.",
            }),
            json.dumps({
                "barsi": {"opiniao": "comprar", "raciocinio": "DY consistente.", "condicao_entrada": "N/D"},
                "crescimento": {"opiniao": "aguardar", "raciocinio": "Upside limitado.", "condicao_entrada": "N/D"},
            }),
            json.dumps({
                "recomendacao": "COMPRAR", "forca_sinal": "moderado",
                "preco_entrada_ideal": 152.0, "preco_alvo_12m": 165.0,
                "stop_sugerido": 140.0, "dy_alvo_minimo": 9.5,
                "tese": "FII sólido com DY atrativo.",
                "gatilhos_compra": ["P/VP < 0.9"],
                "gatilhos_saida": ["Vacância > 10%"],
                "rating": "B",
            }),
        ]
        call_count = [0]

        def side_effect(*args, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            mock_completion = MagicMock()
            mock_completion.choices = [MagicMock()]
            mock_completion.choices[0].message.content = responses[idx % len(responses)]
            return mock_completion

        mock_client = MagicMock()
        mock_client.return_value.chat.completions.create.side_effect = side_effect
        return mock_client

    def test_groq_not_installed_returns_error(self):
        with patch.object(pipeline, "HAS_GROQ", False):
            result = run_deep_analysis(
                "HGLG11",
                fii_data={},
                macro={},
                news=[],
                api_key="test-key",
            )
        assert result["success"] is False
        assert "groq" in result["error"].lower()

    def test_full_pipeline_success(self):
        fii_data = _make_state().fii_data
        macro = {"selic_anual": 10.75, "cdi_anual": 10.65, "ipca_anual": 4.83}
        news = [{"titulo": "Notícia positiva", "data": "2025-04-01"}]

        mock_client = self._all_agents_response()

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
            patch("time.sleep"),  # evitar delay nos testes
        ):
            result = run_deep_analysis("HGLG11", fii_data, macro, news, api_key="test-key")

        assert result["success"] is True
        assert result["ticker"] == "HGLG11"
        assert "macro_analysis" in result
        assert "fundamental_analysis" in result
        assert "risk_analysis" in result
        assert "persona_analysis" in result
        assert "final_decision" in result
        assert "pipeline_meta" in result

    def test_pipeline_meta_structure(self):
        fii_data = _make_state().fii_data
        macro = {"selic_anual": 10.75, "cdi_anual": 10.65, "ipca_anual": 4.83}

        mock_client = self._all_agents_response()

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
            patch("time.sleep"),
        ):
            result = run_deep_analysis("HGLG11", fii_data, macro, [], api_key="test-key")

        meta = result["pipeline_meta"]
        assert meta["agents_run"] == 5
        assert "timings_s" in meta
        assert "total_s" in meta
        assert isinstance(meta["errors"], list)

    def test_pipeline_ticker_uppercased(self):
        fii_data = _make_state().fii_data
        macro = {"selic_anual": 10.75, "cdi_anual": 10.65, "ipca_anual": 4.83}

        mock_client = self._all_agents_response()

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
            patch("time.sleep"),
        ):
            result = run_deep_analysis("hglg11", fii_data, macro, [], api_key="test-key")

        assert result["ticker"] == "HGLG11"

    def test_partial_failure_still_returns_success(self):
        """Quando alguns agentes falham (fallback), pipeline retorna success=True com errors listados."""
        fii_data = _make_state().fii_data
        macro = {"selic_anual": 10.75, "cdi_anual": 10.65, "ipca_anual": 4.83}

        # Todos os agentes falham
        mock_client = MagicMock()
        mock_client.return_value.chat.completions.create.side_effect = Exception("rate limit")

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
            patch("time.sleep"),
        ):
            result = run_deep_analysis("HGLG11", fii_data, macro, [], api_key="test-key")

        assert result["success"] is True
        assert len(result["pipeline_meta"]["errors"]) == 5
        # Fallbacks devem estar presentes
        assert result["final_decision"]["recomendacao"] == "AGUARDAR"

    def test_empty_news_handled_gracefully(self):
        fii_data = _make_state().fii_data
        macro = {"selic_anual": 10.75, "cdi_anual": 10.65, "ipca_anual": 4.83}

        mock_client = self._all_agents_response()

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
            patch("time.sleep"),
        ):
            result = run_deep_analysis("HGLG11", fii_data, macro, [], api_key="test-key")

        assert result["success"] is True

    def test_decision_recommendation_is_valid_enum(self):
        fii_data = _make_state().fii_data
        macro = {"selic_anual": 10.75, "cdi_anual": 10.65, "ipca_anual": 4.83}

        mock_client = self._all_agents_response()

        with (
            patch.object(pipeline, "HAS_GROQ", True),
            patch.object(pipeline, "Groq", mock_client),
            patch("time.sleep"),
        ):
            result = run_deep_analysis("HGLG11", fii_data, macro, [], api_key="test-key")

        rec = result["final_decision"]["recomendacao"]
        assert rec in ("COMPRAR", "AGUARDAR", "EVITAR")


# ---------------------------------------------------------------------------
# _parse_json helper
# ---------------------------------------------------------------------------

class TestParseJson:
    def test_valid_json(self):
        data = pipeline._parse_json('{"key": "value"}')
        assert data == {"key": "value"}

    def test_json_embedded_in_text(self):
        text = 'Aqui está a análise: {"resultado": 42} — fim.'
        data = pipeline._parse_json(text)
        assert data["resultado"] == 42

    def test_no_json_raises(self):
        import pytest
        with pytest.raises(ValueError, match="No JSON"):
            pipeline._parse_json("Nenhum JSON aqui.")
