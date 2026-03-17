"""Tests for core/profile_allocator.py — Risk profile target allocations."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from core.profile_allocator import getTargetAllocation


class TestGetTargetAllocation:
    def test_conservador(self):
        result = getTargetAllocation("conservador")
        assert result == {"ETF": 0.60, "FII": 0.30, "ACAO": 0.10}
        assert sum(result.values()) == pytest.approx(1.0)

    def test_moderado(self):
        result = getTargetAllocation("moderado")
        assert result == {"ETF": 0.50, "ACAO": 0.30, "FII": 0.20}
        assert sum(result.values()) == pytest.approx(1.0)

    def test_agressivo(self):
        result = getTargetAllocation("agressivo")
        assert result == {"ACAO": 0.70, "ETF": 0.20, "FII": 0.10}
        assert sum(result.values()) == pytest.approx(1.0)

    def test_case_insensitive(self):
        result = getTargetAllocation("CONSERVADOR")
        assert result["ETF"] == 0.60

    def test_whitespace_trimmed(self):
        result = getTargetAllocation("  moderado  ")
        assert result["ETF"] == 0.50

    def test_invalid_profile_raises(self):
        with pytest.raises(ValueError, match="inválido"):
            getTargetAllocation("ultra_agressivo")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="inválido"):
            getTargetAllocation("")

    def test_all_profiles_sum_to_one(self):
        for perfil in ["conservador", "moderado", "agressivo"]:
            result = getTargetAllocation(perfil)
            assert sum(result.values()) == pytest.approx(1.0)
