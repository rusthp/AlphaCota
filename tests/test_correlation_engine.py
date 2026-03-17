"""
tests/test_correlation_engine.py

Testes unitários para core/correlation_engine.py.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.correlation_engine import (
    calculate_pearson,
    build_correlation_matrix,
    classify_correlation,
    find_high_correlation_pairs,
    calculate_sector_concentration,
    calculate_herfindahl_index,
    classify_concentration_risk,
    calculate_portfolio_volatility,
    calculate_diversification_ratio,
    analyse_portfolio_risk,
    suggest_rebalance_with_correlation,
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


# --- Dados de teste ---
TICKER_A = "MXRF11"
TICKER_B = "HGLG11"
TICKER_C = "KNCR11"

# Série perfeitamente correlacionada
RETURNS_A = [0.01, 0.02, -0.01, 0.03, -0.02, 0.01, 0.02, -0.01, 0.01, 0.02, -0.01, 0.01]
RETURNS_B = [0.01, 0.02, -0.01, 0.03, -0.02, 0.01, 0.02, -0.01, 0.01, 0.02, -0.01, 0.01]
# Série negativamente correlacionada
RETURNS_C = [-r for r in RETURNS_A]
# Série descorrelacionada
RETURNS_D = [0.01, -0.01, 0.01, -0.01, 0.01, -0.01, 0.01, -0.01, 0.01, -0.01, 0.01, -0.01]

RETURN_SERIES = {
    TICKER_A: RETURNS_A,
    TICKER_B: RETURNS_B,
    TICKER_C: RETURNS_C,
}

PORTFOLIO = [
    {"ticker": TICKER_A, "quantidade": 100, "preco_atual": 10.0},
    {"ticker": TICKER_B, "quantidade": 10,  "preco_atual": 155.0},
    {"ticker": TICKER_C, "quantidade": 50,  "preco_atual": 97.0},
]

SECTOR_MAP = {
    TICKER_A: "Papel (CRI)",
    TICKER_B: "Logística",
    TICKER_C: "Papel (CRI)",
}


# ---------------------------------------------------------------------------
# Pearson
# ---------------------------------------------------------------------------

def test_pearson_perfect():
    """Correlação perfeita deve retornar 1.0."""
    r = calculate_pearson(RETURNS_A, RETURNS_B)
    assert_close(r, 1.0, tol=0.001, label="Pefect corr")


def test_pearson_negative():
    """Correlação negativa perfeita deve retornar -1.0."""
    r = calculate_pearson(RETURNS_A, RETURNS_C)
    assert_close(r, -1.0, tol=0.001, label="Negative corr")


def test_pearson_short_series():
    """Série com menos de 2 pontos retorna 0.0."""
    r = calculate_pearson([0.01], [0.01])
    assert r == 0.0


def test_pearson_bounds():
    """Correlação deve estar sempre entre -1 e 1."""
    r = calculate_pearson(RETURNS_A, RETURNS_D)
    assert -1.0 <= r <= 1.0, f"Fora dos limites: {r}"


# ---------------------------------------------------------------------------
# Matriz de correlação
# ---------------------------------------------------------------------------

def test_matrix_diagonal():
    """Diagonal deve ser 1.0 (autocorrelação)."""
    matrix = build_correlation_matrix([TICKER_A, TICKER_B, TICKER_C], RETURN_SERIES)
    for t in [TICKER_A, TICKER_B, TICKER_C]:
        assert_close(matrix[t][t], 1.0, tol=0.001, label=f"Diagonal {t}")


def test_matrix_symmetry():
    """Matriz deve ser simétrica."""
    matrix = build_correlation_matrix([TICKER_A, TICKER_B, TICKER_C], RETURN_SERIES)
    assert_close(matrix[TICKER_A][TICKER_B], matrix[TICKER_B][TICKER_A], label="Simetria")


def test_matrix_full():
    """Todos os pares devem estar presentes."""
    tickers = [TICKER_A, TICKER_B, TICKER_C]
    matrix = build_correlation_matrix(tickers, RETURN_SERIES)
    for t1 in tickers:
        for t2 in tickers:
            assert t2 in matrix[t1], f"Par ({t1}, {t2}) ausente"


# ---------------------------------------------------------------------------
# Classificação
# ---------------------------------------------------------------------------

def test_classify_very_high():
    assert classify_correlation(0.90) == "Muito Alta"

def test_classify_high():
    assert classify_correlation(0.70) == "Alta"

def test_classify_moderate():
    assert classify_correlation(0.50) == "Moderada"

def test_classify_low():
    assert classify_correlation(0.25) == "Baixa"

def test_classify_negligible():
    assert classify_correlation(0.05) == "Desprezível"

def test_classify_negative_high():
    assert classify_correlation(-0.90) == "Muito Alta"


# ---------------------------------------------------------------------------
# Alta correlação
# ---------------------------------------------------------------------------

def test_find_high_corr():
    """MXRF11 e HGLG11 (correlação 1.0) devem aparecer como par problemático."""
    matrix = build_correlation_matrix([TICKER_A, TICKER_B], RETURN_SERIES)
    pairs = find_high_correlation_pairs(matrix, threshold=0.75)
    assert len(pairs) >= 1, "Deve encontrar ao menos 1 par acima de 0.75"
    assert pairs[0]["ticker_a"] == TICKER_A or pairs[0]["ticker_b"] == TICKER_A


def test_find_high_corr_threshold_one():
    """Com threshold=1.0, apenas correlação perfeita deve aparecer."""
    matrix = build_correlation_matrix([TICKER_A, TICKER_B, TICKER_C], RETURN_SERIES)
    pairs = find_high_correlation_pairs(matrix, threshold=1.0)
    # MXRF11-HGLG11 têm correlação exatamente 1.0
    assert all(abs(p["correlation"]) >= 1.0 for p in pairs)


# ---------------------------------------------------------------------------
# Concentração setorial
# ---------------------------------------------------------------------------

def test_sector_concentration_sums_one():
    """Soma das concentrações deve ser ~1.0."""
    conc = calculate_sector_concentration(PORTFOLIO, SECTOR_MAP)
    total = sum(conc.values())
    assert_close(total, 1.0, tol=0.01, label="Soma concentração")


def test_sector_concentration_values():
    """'Papel (CRI)' deve ter maior concentração que 'Logística' neste portfólio."""
    conc = calculate_sector_concentration(PORTFOLIO, SECTOR_MAP)
    assert conc.get("Papel (CRI)", 0) > conc.get("Logística", 0)


def test_hhi_two_equal_sectors():
    """HHI para 2 setores iguais (50-50) deve ser 0.50."""
    conc = {"Setor A": 0.5, "Setor B": 0.5}
    hhi = calculate_herfindahl_index(conc)
    assert_close(hhi, 0.50, tol=0.01)


def test_hhi_monopoly():
    """HHI para 1 setor (100%) deve ser 1.0."""
    hhi = calculate_herfindahl_index({"Setor Único": 1.0})
    assert_close(hhi, 1.0, tol=0.001)


def test_classify_diversified():
    assert classify_concentration_risk(0.10) == "Diversificado"

def test_classify_concentrated():
    assert classify_concentration_risk(0.45) == "Altamente Concentrado"


# ---------------------------------------------------------------------------
# Volatilidade e diversificação
# ---------------------------------------------------------------------------

def test_portfolio_volatility_positive():
    """Volatilidade do portfólio deve ser positiva com dados válidos."""
    matrix = build_correlation_matrix([TICKER_A, TICKER_B], RETURN_SERIES)
    weights = {TICKER_A: 0.6, TICKER_B: 0.4}
    rs = {TICKER_A: RETURNS_A, TICKER_B: RETURNS_B}
    vol = calculate_portfolio_volatility(weights, rs, matrix)
    assert vol > 0, f"Volatilidade deve ser > 0, obtido {vol}"


def test_diversification_ratio_perfect_corr():
    """DR deve ser ~1.0 com correlação perfeita (sem ganho de diversificação)."""
    matrix = build_correlation_matrix([TICKER_A, TICKER_B], RETURN_SERIES)
    weights = {TICKER_A: 0.5, TICKER_B: 0.5}
    rs = {TICKER_A: RETURNS_A, TICKER_B: RETURNS_B}
    dr = calculate_diversification_ratio(weights, rs, matrix)
    assert_close(dr, 1.0, tol=0.05, label="DR corr perfeita")


# ---------------------------------------------------------------------------
# Análise completa
# ---------------------------------------------------------------------------

def test_analyse_portfolio_risk_keys():
    """Resultado deve conter todas as chaves esperadas."""
    matrix = build_correlation_matrix([TICKER_A, TICKER_B, TICKER_C], RETURN_SERIES)
    result = analyse_portfolio_risk(PORTFOLIO, RETURN_SERIES, SECTOR_MAP)
    expected = {"correlation_matrix", "high_correlation_pairs", "sector_concentration",
                "herfindahl_index", "concentration_risk", "portfolio_annual_volatility",
                "diversification_ratio", "warnings"}
    assert expected == set(result.keys()), f"Chaves faltando: {expected - set(result.keys())}"


def test_analyse_warnings_generated():
    """Deve gerar warnings com correlação 1.0 entre tickers."""
    result = analyse_portfolio_risk(PORTFOLIO, RETURN_SERIES, SECTOR_MAP)
    assert isinstance(result["warnings"], list)
    # Com correlação perfeita, deve ter ao menos 1 warning
    assert len(result["warnings"]) >= 1


# ---------------------------------------------------------------------------
# Edge cases para cobertura
# ---------------------------------------------------------------------------

def test_pearson_zero_stdev():
    """Constant series (zero stdev) should return 0.0."""
    constant = [0.05] * 12
    assert calculate_pearson(constant, RETURNS_A) == 0.0


def test_sector_concentration_empty_portfolio():
    """Empty or zero-value portfolio should return empty dict."""
    result = calculate_sector_concentration([], SECTOR_MAP)
    assert result == {}


def test_sector_concentration_zero_values():
    """Portfolio with zero quantity should return empty dict."""
    p = [{"ticker": "MXRF11", "quantidade": 0, "preco_atual": 10.0}]
    assert calculate_sector_concentration(p, SECTOR_MAP) == {}


def test_classify_concentration_moderado():
    assert classify_concentration_risk(0.20) == "Moderado"


def test_classify_concentration_concentrado():
    assert classify_concentration_risk(0.30) == "Concentrado"


def test_portfolio_volatility_short_series():
    """Ticker with < 2 returns should have vol = 0."""
    matrix = {TICKER_A: {TICKER_A: 1.0}}
    weights = {TICKER_A: 1.0}
    rs = {TICKER_A: [0.01]}  # Only 1 return
    vol = calculate_portfolio_volatility(weights, rs, matrix)
    assert vol == 0.0


def test_diversification_ratio_short_series():
    """Short series (< 2 returns) → vol = 0 → DR = 0.0."""
    matrix = {TICKER_A: {TICKER_A: 1.0}}
    weights = {TICKER_A: 1.0}
    rs = {TICKER_A: [0.01]}
    dr = calculate_diversification_ratio(weights, rs, matrix)
    assert dr == 0.0


def test_generate_warnings_moderate_hhi():
    """HHI between 0.25 and 0.40 should produce moderate concentration warning."""
    from core.correlation_engine import _generate_warnings
    warnings = _generate_warnings([], 0.30, 1.5)
    assert any("Moderada" in w or "moderada" in w for w in warnings)


def test_generate_warnings_low_div_ratio():
    """Diversification ratio < 1.1 should produce warning."""
    from core.correlation_engine import _generate_warnings
    warnings = _generate_warnings([], 0.10, 0.9)
    assert any("Diversification Ratio" in w for w in warnings)


def test_suggest_rebalance_with_correlation():
    """Full rebalance suggestion with high-corr pair."""
    tickers = [TICKER_A, TICKER_B, TICKER_C]
    matrix = build_correlation_matrix(tickers, RETURN_SERIES)
    target_weights = {TICKER_A: 0.40, TICKER_B: 0.30, TICKER_C: 0.30}
    result = suggest_rebalance_with_correlation(
        PORTFOLIO, target_weights, RETURN_SERIES, matrix, high_corr_threshold=0.80,
    )
    assert "suggestions" in result
    assert "high_correlation_pairs" in result
    assert "total_drift" in result
    assert len(result["suggestions"]) == 3
    for s in result["suggestions"]:
        assert "ticker" in s
        assert "action" in s
        assert "drift" in s
        assert "high_correlation_warning" in s


def test_suggest_rebalance_corr_penalty():
    """Ticker in high-corr pair with positive drift gets penalized priority."""
    tickers = [TICKER_A, TICKER_B]
    matrix = build_correlation_matrix(tickers, RETURN_SERIES)
    # Set target so TICKER_A needs buying (positive drift) and is in high-corr pair
    target_weights = {TICKER_A: 0.90, TICKER_B: 0.10}
    result = suggest_rebalance_with_correlation(
        PORTFOLIO[:2], target_weights, RETURN_SERIES, matrix, high_corr_threshold=0.80,
    )
    # Both tickers are perfectly correlated, so both should be flagged
    for s in result["suggestions"]:
        if s["ticker"] == TICKER_A:
            assert s["high_correlation_warning"] is True


def test_suggest_rebalance_manter_action():
    """When drift is within tolerance, action should be 'manter'."""
    tickers = [TICKER_A, TICKER_B]
    matrix = build_correlation_matrix(tickers, RETURN_SERIES)
    # Set target close to current weights so drift is small
    valor_a = 100 * 10.0
    valor_b = 10 * 155.0
    total = valor_a + valor_b
    target_weights = {
        TICKER_A: round(valor_a / total, 4),
        TICKER_B: round(valor_b / total, 4),
    }
    result = suggest_rebalance_with_correlation(
        PORTFOLIO[:2], target_weights, RETURN_SERIES, matrix,
    )
    for s in result["suggestions"]:
        assert s["action"] == "manter"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> bool:
    tests = [
        ("Pearson perfeito", test_pearson_perfect),
        ("Pearson negativo", test_pearson_negative),
        ("Pearson série curta", test_pearson_short_series),
        ("Pearson limites", test_pearson_bounds),
        ("Matriz diagonal", test_matrix_diagonal),
        ("Matriz simetria", test_matrix_symmetry),
        ("Matriz completa", test_matrix_full),
        ("Classificar Muito Alta", test_classify_very_high),
        ("Classificar Alta", test_classify_high),
        ("Classificar Moderada", test_classify_moderate),
        ("Classificar Baixa", test_classify_low),
        ("Classificar Desprezível", test_classify_negligible),
        ("Classificar negativa alta", test_classify_negative_high),
        ("Encontrar alta corr", test_find_high_corr),
        ("Alta corr threshold 1.0", test_find_high_corr_threshold_one),
        ("Concentração soma 1", test_sector_concentration_sums_one),
        ("Concentração por setor", test_sector_concentration_values),
        ("HHI 50-50", test_hhi_two_equal_sectors),
        ("HHI monopólio", test_hhi_monopoly),
        ("Concentração: diversificado", test_classify_diversified),
        ("Concentração: concentrado", test_classify_concentrated),
        ("Volatilidade positiva", test_portfolio_volatility_positive),
        ("DR correlação perfeita", test_diversification_ratio_perfect_corr),
        ("Analyse: chaves corretas", test_analyse_portfolio_risk_keys),
        ("Analyse: warnings gerados", test_analyse_warnings_generated),
    ]

    print("\n" + "=" * 55)
    print("  ALPHACOTA — TEST SUITE: Correlation Engine")
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
