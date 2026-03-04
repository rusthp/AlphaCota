"""
tests/test_stress_engine.py

Testes unitários para core/stress_engine.py.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.stress_engine import (
    STRESS_SCENARIOS,
    apply_price_shock,
    apply_dividend_shock,
    apply_stress_scenario,
    run_stress_suite,
    format_stress_report,
    summarize_stress_suite,
)


def assert_close(a: float, b: float, tol: float = 0.01, label: str = "") -> None:
    if abs(a - b) > tol:
        raise AssertionError(f"{'['+label+'] ' if label else ''}Esperado ~{b:.4f}, obtido {a:.4f}")


def run_test(name: str, fn) -> bool:
    try:
        fn()
        print(f"  ✅ {name}")
        return True
    except AssertionError as e:
        print(f"  ❌ {name}: {e}")
        return False
    except Exception as e:
        print(f"  💥 {name}: {type(e).__name__}: {e}")
        return False


# --- Dados comuns ---
PORTFOLIO = [
    {"ticker": "MXRF11", "quantidade": 200, "preco_atual": 10.0,  "dividend_mensal": 0.09},
    {"ticker": "HGLG11", "quantidade": 10,  "preco_atual": 155.0, "dividend_mensal": 1.10},
    {"ticker": "XPML11", "quantidade": 50,  "preco_atual": 90.0,  "dividend_mensal": 0.65},
]

SECTOR_MAP = {
    "MXRF11": "Papel (CRI)",
    "HGLG11": "Logística",
    "XPML11": "Shopping",
}


# ---------------------------------------------------------------------------
# STRESS_SCENARIOS (estrutura)
# ---------------------------------------------------------------------------

def test_scenarios_defined():
    """Deve haver ao menos 5 cenários definidos."""
    assert len(STRESS_SCENARIOS) >= 5, f"Esperado >= 5, obtido {len(STRESS_SCENARIOS)}"


def test_scenarios_have_required_fields():
    """Cada cenário deve ter name, description, price_shock, dividend_shock."""
    for key, s in STRESS_SCENARIOS.items():
        for field in ("name", "description", "price_shock", "dividend_shock"):
            assert field in s, f"Cenário '{key}' sem campo '{field}'"


# ---------------------------------------------------------------------------
# apply_price_shock
# ---------------------------------------------------------------------------

def test_price_shock_negative():
    """Choque negativo deve reduzir o preço."""
    shock_map = {"Logística": -0.15, "Outros": -0.10}
    result = apply_price_shock(100.0, "Logística", shock_map)
    assert_close(result, 85.0, tol=0.01)


def test_price_shock_positive():
    """Choque positivo (Papel em alta de juros) deve aumentar o preço."""
    shock_map = {"Papel (CRI)": +0.02, "Outros": 0.0}
    result = apply_price_shock(100.0, "Papel (CRI)", shock_map)
    assert_close(result, 102.0, tol=0.01)


def test_price_shock_never_negative():
    """Preço após choque nunca deve ser negativo."""
    shock_map = {"Logística": -2.0}  # -200% = absurdo
    result = apply_price_shock(100.0, "Logística", shock_map)
    assert result == 0.0


def test_price_shock_unknown_sector():
    """Setor desconhecido deve usar 'Outros' como fallback."""
    shock_map = {"Outros": -0.10}
    result = apply_price_shock(100.0, "Setor Inexistente", shock_map)
    assert_close(result, 90.0, tol=0.01)


# ---------------------------------------------------------------------------
# apply_dividend_shock
# ---------------------------------------------------------------------------

def test_dividend_shock_cut():
    """Corte de 30% nos dividendos."""
    shock_map = {"Papel (CRI)": -0.30, "Outros": -0.30}
    result = apply_dividend_shock(1.00, "Papel (CRI)", shock_map)
    assert_close(result, 0.70, tol=0.001)


def test_dividend_shock_never_negative():
    """Dividendo após choque nunca deve ser negativo."""
    shock_map = {"Shopping": -2.0}
    result = apply_dividend_shock(1.00, "Shopping", shock_map)
    assert result == 0.0


# ---------------------------------------------------------------------------
# apply_stress_scenario
# ---------------------------------------------------------------------------

def test_stress_result_keys():
    """Resultado deve conter todas as chaves esperadas."""
    result = apply_stress_scenario(PORTFOLIO, "alta_juros_moderada", SECTOR_MAP)
    for key in ("scenario_name", "total_antes", "total_depois", "drawdown",
                "dividendos_antes", "dividendos_depois", "assets"):
        assert key in result, f"Chave '{key}' ausente"


def test_stress_total_antes_correto():
    """total_antes deve ser qtd × preco para todos os ativos."""
    result = apply_stress_scenario(PORTFOLIO, "queda_mercado_20", SECTOR_MAP)
    expected = sum(a["quantidade"] * a["preco_atual"] for a in PORTFOLIO)
    assert_close(result["total_antes"], expected, tol=0.01)


def test_stress_queda_mercado_drawdown_negative():
    """Queda de mercado deve gerar drawdown negativo."""
    result = apply_stress_scenario(PORTFOLIO, "queda_mercado_40", SECTOR_MAP)
    assert result["drawdown"] < 0, f"Drawdown deveria ser negativo: {result['drawdown']}"


def test_stress_alta_juros_papel_melhor():
    """No cenário de alta de juros, CRI deve ter impacto menos negativo que Shopping."""
    result = apply_stress_scenario(PORTFOLIO, "alta_juros_severa", SECTOR_MAP)
    cri   = next(a for a in result["assets"] if a["ticker"] == "MXRF11")
    shop  = next(a for a in result["assets"] if a["ticker"] == "XPML11")
    # CRI tem preço positivo (benefício) ou menor queda que Shopping
    assert cri["impacto_%"] > shop["impacto_%"], (
        f"CRI deveria ser > Shopping em alta de juros: {cri['impacto_%']} vs {shop['impacto_%']}"
    )


def test_stress_corte_dividendos():
    """Corte de dividendos deve reduzir dividendos_depois < dividendos_antes."""
    result = apply_stress_scenario(PORTFOLIO, "corte_dividendos_50", SECTOR_MAP)
    assert result["dividendos_depois"] < result["dividendos_antes"]


def test_stress_assets_count():
    """Resultado deve ter 1 item em assets por ativo na carteira."""
    result = apply_stress_scenario(PORTFOLIO, "vacancia_tijolo", SECTOR_MAP)
    assert len(result["assets"]) == len(PORTFOLIO)


def test_stress_invalid_scenario():
    """Cenário inválido deve levantar KeyError."""
    try:
        apply_stress_scenario(PORTFOLIO, "cenario_inexistente", SECTOR_MAP)
        raise AssertionError("Deveria ter levantado KeyError")
    except KeyError:
        pass


# ---------------------------------------------------------------------------
# run_stress_suite
# ---------------------------------------------------------------------------

def test_suite_all_scenarios():
    """Suite sem filtro deve rodar todos os cenários disponíveis."""
    results = run_stress_suite(PORTFOLIO, SECTOR_MAP)
    assert len(results) == len(STRESS_SCENARIOS)


def test_suite_sorted_ascending():
    """Suite deve estar ordenada do maior drawdown (mais negativo) ao menor."""
    results = run_stress_suite(PORTFOLIO, SECTOR_MAP)
    for i in range(len(results) - 1):
        assert results[i]["drawdown"] <= results[i + 1]["drawdown"], "Não está ordenado"


def test_suite_filtered():
    """Suite com filtro deve rodar apenas os cenários indicados."""
    results = run_stress_suite(PORTFOLIO, SECTOR_MAP,
                               scenario_keys=["queda_mercado_20", "corte_dividendos_30"])
    assert len(results) == 2


# ---------------------------------------------------------------------------
# summarize_stress_suite
# ---------------------------------------------------------------------------

def test_summary_keys():
    """Sumário deve ter as chaves esperadas."""
    suite = run_stress_suite(PORTFOLIO, SECTOR_MAP)
    summary = summarize_stress_suite(suite)
    for key in ("worst_scenario", "worst_drawdown", "avg_drawdown", "ranking"):
        assert key in summary, f"Chave '{key}' ausente"


def test_summary_worst_is_most_negative():
    """Pior cenário deve ter drawdown mais negativo que a média."""
    suite = run_stress_suite(PORTFOLIO, SECTOR_MAP)
    summary = summarize_stress_suite(suite)
    assert summary["worst_drawdown"] <= summary["avg_drawdown"]


def test_format_report_str():
    """Relatório deve ser string não-vazia."""
    result = apply_stress_scenario(PORTFOLIO, "queda_mercado_20", SECTOR_MAP)
    report = format_stress_report(result)
    assert isinstance(report, str) and len(report) > 100


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> bool:
    tests = [
        ("Cenários definidos", test_scenarios_defined),
        ("Campos obrigatórios nos cenários", test_scenarios_have_required_fields),
        ("Choque de preço negativo", test_price_shock_negative),
        ("Choque de preço positivo", test_price_shock_positive),
        ("Choque de preço nunca negativo", test_price_shock_never_negative),
        ("Choque setor desconhecido", test_price_shock_unknown_sector),
        ("Corte de dividendos 30%", test_dividend_shock_cut),
        ("Dividendo nunca negativo", test_dividend_shock_never_negative),
        ("Resultado: chaves corretas", test_stress_result_keys),
        ("Total antes correto", test_stress_total_antes_correto),
        ("Queda de mercado: drawdown negativo", test_stress_queda_mercado_drawdown_negative),
        ("Alta juros: CRI > Shopping", test_stress_alta_juros_papel_melhor),
        ("Corte dividendos: depois < antes", test_stress_corte_dividendos),
        ("Assets: 1 por ativo", test_stress_assets_count),
        ("Cenário inválido levanta KeyError", test_stress_invalid_scenario),
        ("Suite: todos os cenários", test_suite_all_scenarios),
        ("Suite: ordenada ascending", test_suite_sorted_ascending),
        ("Suite: filtrada", test_suite_filtered),
        ("Sumário: chaves corretas", test_summary_keys),
        ("Sumário: pior <= médio", test_summary_worst_is_most_negative),
        ("Format report: string", test_format_report_str),
    ]

    print("\n" + "=" * 55)
    print("  ALPHACOTA — TEST SUITE: Stress Engine")
    print("=" * 55)

    passed = sum(run_test(n, f) for n, f in tests)
    total = len(tests)
    failed = total - passed

    print("=" * 55)
    print(f"  Resultado: {passed}/{total} testes passaram")
    print("  🎉 TODOS PASSARAM!" if failed == 0 else f"  ⚠️  {failed} falhas.")
    print("=" * 55 + "\n")
    return failed == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
