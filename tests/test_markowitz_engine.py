"""
tests/test_markowitz_engine.py

Testes unitários para core/markowitz_engine.py.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.markowitz_engine import (
    calculate_expected_return,
    calculate_annual_volatility,
    calculate_portfolio_return,
    calculate_portfolio_vol,
    calculate_sharpe,
    simulate_portfolio_frontier,
    find_max_sharpe,
    find_min_volatility,
    find_equal_weight,
    compare_strategies,
    format_strategy_report,
)
from core.correlation_engine import build_correlation_matrix


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
TICKERS = ["MXRF11", "HGLG11", "KNCR11"]

RETURNS = {
    "MXRF11": [0.010, 0.012, -0.005, 0.008, 0.015, 0.011,
               0.009, 0.013, -0.003, 0.007, 0.014, 0.010] * 2,
    "HGLG11": [0.008, 0.009, -0.010, 0.012, 0.007, 0.010,
               0.006, 0.011, -0.008, 0.009, 0.008, 0.007] * 2,
    "KNCR11": [0.006, 0.007,  0.006, 0.006, 0.007, 0.006,
               0.006, 0.007,  0.006, 0.006, 0.007, 0.006] * 2,  # Baixa vol
}

CORR_MATRIX = build_correlation_matrix(TICKERS, RETURNS)

WEIGHTS_EQUAL = {"MXRF11": 1/3, "HGLG11": 1/3, "KNCR11": 1/3}


# ---------------------------------------------------------------------------
# Retorno esperado
# ---------------------------------------------------------------------------

def test_expected_return_positive():
    """Retorno deve ser positivo com retornos mensais positivos."""
    r = calculate_expected_return([0.01] * 12)
    assert r > 0, f"Esperado > 0, obtido {r}"


def test_expected_return_annualized():
    """Retorno mensal constante de 1% → ~12.68% ao ano."""
    r = calculate_expected_return([0.01] * 12, annualize=True)
    assert_close(r, 0.1268, tol=0.01, label="CAGR 1%/mês")


def test_expected_return_not_annualized():
    """Sem anualização, retorna média mensal."""
    r = calculate_expected_return([0.01, 0.02, 0.03], annualize=False)
    assert_close(r, 0.02, tol=0.001)


def test_expected_return_empty():
    """Série vazia retorna 0.0."""
    assert calculate_expected_return([]) == 0.0


# ---------------------------------------------------------------------------
# Volatilidade
# ---------------------------------------------------------------------------

def test_vol_positive():
    """Volatilidade deve ser positiva com retornos variados."""
    v = calculate_annual_volatility(RETURNS["MXRF11"])
    assert v > 0, f"Esperado > 0, obtido {v}"


def test_vol_constant_returns():
    """Retorno constante → volatilidade quase zero."""
    v = calculate_annual_volatility([0.007] * 24)
    assert_close(v, 0.0, tol=1e-9)


def test_vol_empty():
    """Série vazia → 0.0."""
    assert calculate_annual_volatility([]) == 0.0


# ---------------------------------------------------------------------------
# Retorno do portfólio
# ---------------------------------------------------------------------------

def test_portfolio_return_equal_weights():
    """Com pesos iguais, retorno é média dos retornos individuais."""
    exp = {t: calculate_expected_return(RETURNS[t]) for t in TICKERS}
    port_ret = calculate_portfolio_return(WEIGHTS_EQUAL, exp)
    manual = sum(exp.values()) / len(TICKERS)
    assert_close(port_ret, manual, tol=0.001)


def test_portfolio_return_single_asset():
    """Portfólio com 1 ativo 100% = retorno do ativo."""
    exp = {"MXRF11": 0.12}
    r = calculate_portfolio_return({"MXRF11": 1.0}, exp)
    assert_close(r, 0.12)


# ---------------------------------------------------------------------------
# Volatilidade do portfólio
# ---------------------------------------------------------------------------

def test_portfolio_vol_positive():
    """Volatilidade do portfólio deve ser positiva."""
    vols = {t: calculate_annual_volatility(RETURNS[t]) for t in TICKERS}
    v = calculate_portfolio_vol(WEIGHTS_EQUAL, vols, CORR_MATRIX)
    assert v > 0, f"Vol deve ser > 0, obtido {v}"


def test_portfolio_vol_single():
    """Portfólio single-asset: vol do portfólio = vol do ativo."""
    vols = {"MXRF11": 0.20}
    matrix = {"MXRF11": {"MXRF11": 1.0}}
    v = calculate_portfolio_vol({"MXRF11": 1.0}, vols, matrix)
    assert_close(v, 0.20, tol=0.001)


def test_portfolio_vol_diversification():
    """Portfólio com activos decorr. tem vol < média ponderada individual."""
    # Retornos perfeitamente opostos → correlação negativa
    ret_a = [0.02, -0.01] * 12
    ret_b = [-0.02, 0.01] * 12
    matrix = build_correlation_matrix(["A", "B"], {"A": ret_a, "B": ret_b})
    vols = {
        "A": calculate_annual_volatility(ret_a),
        "B": calculate_annual_volatility(ret_b),
    }
    w = {"A": 0.5, "B": 0.5}
    port_vol = calculate_portfolio_vol(w, vols, matrix)
    avg_vol = 0.5 * vols["A"] + 0.5 * vols["B"]
    assert port_vol < avg_vol, f"Vol portfólio {port_vol:.4f} >= média {avg_vol:.4f}"


# ---------------------------------------------------------------------------
# Sharpe
# ---------------------------------------------------------------------------

def test_sharpe_positive():
    """Retorno > RF → Sharpe positivo."""
    s = calculate_sharpe(0.15, 0.20, risk_free_rate=0.10)
    assert s > 0, f"Esperado > 0, obtido {s}"


def test_sharpe_zero_vol():
    """Vol = 0 → Sharpe = 0.0 (sem divisão por zero)."""
    s = calculate_sharpe(0.15, 0.0)
    assert s == 0.0


def test_sharpe_below_rf():
    """Retorno < RF → Sharpe negativo."""
    s = calculate_sharpe(0.05, 0.20, risk_free_rate=0.10)
    assert s < 0, f"Esperado < 0, obtido {s}"


# ---------------------------------------------------------------------------
# Monte Carlo + Fronteira
# ---------------------------------------------------------------------------

def test_frontier_count():
    """Fronteira deve conter exatamente n_simulations portfólios."""
    frontier = simulate_portfolio_frontier(
        TICKERS, RETURNS, CORR_MATRIX, n_simulations=50, seed=0
    )
    assert len(frontier) == 50, f"Esperado 50, obtido {len(frontier)}"


def test_frontier_portfolio_keys():
    """Cada portfólio deve ter 'weights', 'return', 'volatility', 'sharpe'."""
    frontier = simulate_portfolio_frontier(
        TICKERS, RETURNS, CORR_MATRIX, n_simulations=10, seed=0
    )
    for p in frontier:
        for key in ("weights", "return", "volatility", "sharpe"):
            assert key in p, f"Chave '{key}' ausente"


def test_frontier_weights_sum_one():
    """Pesos de cada portfólio devem somar ~1.0."""
    frontier = simulate_portfolio_frontier(
        TICKERS, RETURNS, CORR_MATRIX, n_simulations=20, seed=0
    )
    for p in frontier:
        total = sum(p["weights"].values())
        assert_close(total, 1.0, tol=0.01, label="Soma pesos")


def test_frontier_return_positive():
    """Retornos esperados devem ser positivos com dados positivos."""
    frontier = simulate_portfolio_frontier(
        TICKERS, RETURNS, CORR_MATRIX, n_simulations=20, seed=0
    )
    assert all(p["return"] > 0 for p in frontier), "Algum portfólio com retorno <= 0"


# ---------------------------------------------------------------------------
# Max Sharpe e Min Volatility
# ---------------------------------------------------------------------------

def test_max_sharpe_is_best():
    """Max Sharpe deve ter maior Sharpe que todos os outros."""
    frontier = simulate_portfolio_frontier(
        TICKERS, RETURNS, CORR_MATRIX, n_simulations=200, seed=42
    )
    best = find_max_sharpe(frontier)
    max_sharpe_val = max(p["sharpe"] for p in frontier)
    assert_close(best["sharpe"], max_sharpe_val, tol=0.001)


def test_min_vol_is_lowest():
    """Min Volatility deve ter menor vol que todos os outros."""
    frontier = simulate_portfolio_frontier(
        TICKERS, RETURNS, CORR_MATRIX, n_simulations=200, seed=42
    )
    best = find_min_volatility(frontier)
    min_vol_val = min(p["volatility"] for p in frontier)
    assert_close(best["volatility"], min_vol_val, tol=0.001)


def test_max_sharpe_strategy_key():
    """max_sharpe deve ter strategy='max_sharpe'."""
    frontier = simulate_portfolio_frontier(
        TICKERS, RETURNS, CORR_MATRIX, n_simulations=50, seed=0
    )
    best = find_max_sharpe(frontier)
    assert best.get("strategy") == "max_sharpe"


def test_equal_weight_sums_one():
    """Equal weight: todos os pesos devem somar 1.0."""
    ew = find_equal_weight(TICKERS, RETURNS, CORR_MATRIX)
    total = sum(ew["weights"].values())
    assert_close(total, 1.0, tol=0.001)


def test_equal_weight_each_third():
    """Equal weight com 3 ativos: cada peso ≈ 1/3."""
    ew = find_equal_weight(TICKERS, RETURNS, CORR_MATRIX)
    for w in ew["weights"].values():
        assert_close(w, 1/3, tol=0.01)


# ---------------------------------------------------------------------------
# Compare strategies
# ---------------------------------------------------------------------------

def test_compare_strategies_keys():
    """compare_strategies deve retornar as 4 chaves esperadas."""
    result = compare_strategies(
        TICKERS, RETURNS, CORR_MATRIX, n_simulations=100, seed=0
    )
    for key in ("frontier", "max_sharpe", "min_volatility", "equal_weight"):
        assert key in result, f"Chave '{key}' ausente"


def test_format_report_str():
    """format_strategy_report deve retornar uma string não-vazia."""
    result = compare_strategies(
        TICKERS, RETURNS, CORR_MATRIX, n_simulations=100, seed=0
    )
    report = format_strategy_report(result)
    assert isinstance(report, str) and len(report) > 50


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> bool:
    tests = [
        ("Retorno esperado positivo", test_expected_return_positive),
        ("Retorno anualizado 1%/mês", test_expected_return_annualized),
        ("Retorno não anualizado", test_expected_return_not_annualized),
        ("Retorno série vazia", test_expected_return_empty),
        ("Volatilidade positiva", test_vol_positive),
        ("Volatilidade constante", test_vol_constant_returns),
        ("Volatilidade série vazia", test_vol_empty),
        ("Return portfólio pesos iguais", test_portfolio_return_equal_weights),
        ("Return portfólio ativo único", test_portfolio_return_single_asset),
        ("Vol portfólio positivo", test_portfolio_vol_positive),
        ("Vol portfólio ativo único", test_portfolio_vol_single),
        ("Vol portfólio: diversificação", test_portfolio_vol_diversification),
        ("Sharpe positivo", test_sharpe_positive),
        ("Sharpe vol=0", test_sharpe_zero_vol),
        ("Sharpe abaixo do RF", test_sharpe_below_rf),
        ("Fronteira: qtd correta", test_frontier_count),
        ("Fronteira: chaves dos portfólios", test_frontier_portfolio_keys),
        ("Fronteira: pesos somam 1", test_frontier_weights_sum_one),
        ("Fronteira: retorno positivo", test_frontier_return_positive),
        ("Max Sharpe: é o melhor", test_max_sharpe_is_best),
        ("Min Volatility: é o menor", test_min_vol_is_lowest),
        ("Max Sharpe: strategy key", test_max_sharpe_strategy_key),
        ("Equal Weight: soma 1", test_equal_weight_sums_one),
        ("Equal Weight: cada 1/3", test_equal_weight_each_third),
        ("Compare Strategies: chaves", test_compare_strategies_keys),
        ("Format Report: string", test_format_report_str),
    ]

    print("\n" + "=" * 55)
    print("  ALPHACOTA — TEST SUITE: Markowitz Engine")
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
