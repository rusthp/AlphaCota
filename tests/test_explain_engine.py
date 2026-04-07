"""Tests for services/explain_engine.py — Portfolio explanation generator."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from services.explain_engine import generate_portfolio_explanation


def _allocations():
    return [
        {
            "ticker": "HGLG11",
            "classe": "FII",
            "final_score": 85.0,
            "momentum_score": 60.0,
            "altman_z_score": 3.5,
            "peso_alvo": 0.40,
        },
        {
            "ticker": "XPML11",
            "classe": "FII",
            "final_score": 70.0,
            "momentum_score": 25.0,
            "altman_z_score": 2.5,
            "peso_alvo": 0.30,
        },
    ]


class TestGeneratePortfolioExplanation:
    def test_returns_all_sections(self):
        result = generate_portfolio_explanation(
            _allocations(),
            "moderado",
            150000.0,
            8.5,
            {"FII": 0.70, "ETF": 0.30},
        )
        assert "investor_profile" in result
        assert "class_constraints_enforced" in result
        assert "selection_logic" in result
        assert "risk_summary" in result
        assert "fire_projection" in result

    def test_selection_logic_per_asset(self):
        result = generate_portfolio_explanation(
            _allocations(),
            "moderado",
            150000.0,
            8.5,
            {"FII": 0.70},
        )
        assert len(result["selection_logic"]) == 2
        assert result["selection_logic"][0]["ticker"] == "HGLG11"
        assert result["selection_logic"][1]["ticker"] == "XPML11"

    def test_momentum_penalty_noted(self):
        result = generate_portfolio_explanation(
            _allocations(),
            "moderado",
            150000.0,
            8.5,
            {"FII": 0.70},
        )
        # XPML11 has momentum < 30, should have penalty note
        xpml_reasons = result["selection_logic"][1]["reason"]
        has_penalty = any("PENALTY" in r for r in xpml_reasons)
        assert has_penalty

    def test_safe_altman_noted(self):
        result = generate_portfolio_explanation(
            _allocations(),
            "moderado",
            150000.0,
            8.5,
            {"FII": 0.70},
        )
        hglg_reasons = result["selection_logic"][0]["reason"]
        has_safe = any("Segura" in r for r in hglg_reasons)
        assert has_safe

    def test_gray_altman_noted(self):
        result = generate_portfolio_explanation(
            _allocations(),
            "moderado",
            150000.0,
            8.5,
            {"FII": 0.70},
        )
        xpml_reasons = result["selection_logic"][1]["reason"]
        has_gray = any("Cinzenta" in r for r in xpml_reasons)
        assert has_gray

    def test_fire_green_status(self):
        result = generate_portfolio_explanation(
            _allocations(),
            "moderado",
            150000.0,
            8.5,
            {"FII": 0.70},
        )
        assert "GREEN" in result["fire_projection"]["fire_status"]

    def test_fire_red_status_string_input(self):
        result = generate_portfolio_explanation(
            _allocations(),
            "moderado",
            150000.0,
            "inalcançável",
            {"FII": 0.70},
        )
        assert "RED" in result["fire_projection"]["fire_status"]

    def test_empty_allocations(self):
        result = generate_portfolio_explanation([], "conservador", 0.0, 10.0, {})
        assert result["selection_logic"] == []

    def test_weight_pct_rounded(self):
        result = generate_portfolio_explanation(
            _allocations(),
            "moderado",
            150000.0,
            8.5,
            {"FII": 0.70},
        )
        assert result["selection_logic"][0]["weight_pct"] == 40.0
