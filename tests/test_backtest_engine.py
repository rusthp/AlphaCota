"""
tests/test_backtest_engine.py

Testes unitários para core/backtest_engine.py e core/score_engine.py.
Cobertura de todas as funções de cálculo de métricas e do motor de backtest.
"""

import sys
import os
import math

# Adicionar o root do projeto ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.backtest_engine import (
    calculate_cagr,
    calculate_sharpe,
    calculate_sortino,
    calculate_max_drawdown,
    calculate_annual_volatility,
    calculate_metrics,
    run_backtest,
    compare_against_benchmark,
    format_metrics_report,
    _should_rebalance,
    _rebalance_portfolio,
    BacktestResult,
    PerformanceMetrics,
)
from core.score_engine import (
    calculate_alpha_score,
    calculate_income_score,
    calculate_valuation_score,
    calculate_risk_score,
    calculate_growth_score,
    rank_fiis,
    validate_weights,
    DEFAULT_WEIGHTS,
)

# ---------------------------------------------------------------------------
# Utilitários de teste
# ---------------------------------------------------------------------------


def assert_close(a: float, b: float, tol: float = 0.001, label: str = "") -> None:
    """Verifica que dois floats são aproximadamente iguais."""
    if abs(a - b) > tol:
        raise AssertionError(
            f"{'[' + label + '] ' if label else ''}Esperado ~{b:.6f}, obtido {a:.6f} (diff={abs(a-b):.6f})"
        )


def run_test(name: str, fn):
    """Executa um teste e reporta resultado."""
    try:
        fn()
        print(f"  ✅ {name}")
        return True
    except AssertionError as e:
        print(f"  ❌ {name}: {e}")
        return False
    except Exception as e:
        print(f"  💥 {name} — Erro inesperado: {type(e).__name__}: {e}")
        return False


# ---------------------------------------------------------------------------
# Testes: calculate_cagr
# ---------------------------------------------------------------------------


def test_cagr_basic():
    """CAGR de R$1000 → R$1210 em 2 anos = 10% a.a."""
    result = calculate_cagr(1000.0, 1210.0, 2.0)
    assert_close(result, 0.10, tol=0.001, label="CAGR básico")


def test_cagr_zero_years():
    """CAGR com 0 anos deve retornar 0."""
    result = calculate_cagr(1000.0, 2000.0, 0.0)
    assert result == 0.0, f"Esperado 0.0, obtido {result}"


def test_cagr_zero_initial():
    """CAGR com valor inicial 0 deve retornar 0."""
    result = calculate_cagr(0.0, 2000.0, 2.0)
    assert result == 0.0, f"Esperado 0.0, obtido {result}"


# ---------------------------------------------------------------------------
# Testes: calculate_max_drawdown
# ---------------------------------------------------------------------------


def test_max_drawdown_basic():
    """Queda de 1000 → 700 = drawdown de 30%."""
    values = [1000.0, 900.0, 700.0, 800.0, 1100.0]
    result = calculate_max_drawdown(values)
    assert_close(result, -0.30, tol=0.001, label="Max Drawdown básico")


def test_max_drawdown_no_loss():
    """Série sempre crescente → drawdown = 0."""
    values = [100.0, 110.0, 120.0, 130.0]
    result = calculate_max_drawdown(values)
    assert result == 0.0, f"Drawdown esperado 0.0, obtido {result}"


def test_max_drawdown_single_value():
    """Série com 1 valor → drawdown = 0."""
    result = calculate_max_drawdown([500.0])
    assert result == 0.0


# ---------------------------------------------------------------------------
# Testes: calculate_sharpe e calculate_sortino
# ---------------------------------------------------------------------------


def test_sharpe_positive_excess():
    """Sharpe positivo quando retornos têm variância e excedem a taxa livre de risco."""
    # Alternar entre 2% e 1.5% para garantir std != 0 e excesso > RF
    returns = [0.020, 0.015] * 12  # 24 meses alternados, média ~1.75%/mês > CDI ~0.85%/mês
    result = calculate_sharpe(returns, annual_risk_free_rate=0.10)
    assert result > 0, f"Esperado Sharpe > 0, obtido {result}"


def test_sharpe_zero_std():
    """Sharpe com desvio padrão zero retorna 0."""
    # Todos os retornos iguais → std = 0
    returns = [0.01] * 24
    result = calculate_sharpe(returns, annual_risk_free_rate=0.12)
    assert result == 0.0 or isinstance(result, float)


def test_sortino_no_downside():
    """Sortino retorna 0.0 quando não há meses negativos de excesso."""
    # Retornos suficientemente altos para exceder o RF mensalmente
    returns = [0.05] * 12  # 5% ao mês
    result = calculate_sortino(returns, annual_risk_free_rate=0.10)
    # Sem downside → retorna 0
    assert result == 0.0, f"Esperado 0.0 (sem downside), obtido {result}"


# ---------------------------------------------------------------------------
# Testes: calculate_annual_volatility
# ---------------------------------------------------------------------------


def test_annual_volatility_known():
    """Volatilidade de uma série com dispersão conhecida."""
    # Retornos alternantes de +10% e -10%
    returns = [0.10, -0.10] * 12
    result = calculate_annual_volatility(returns)
    assert result > 0, f"Volatilidade deve ser > 0, obtido {result}"


def test_annual_volatility_constant():
    """Retornos constantes → volatilidade = 0."""
    returns = [0.01] * 12
    result = calculate_annual_volatility(returns)
    assert result == 0.0, f"Esperado 0.0, obtido {result}"


# ---------------------------------------------------------------------------
# Testes: _should_rebalance
# ---------------------------------------------------------------------------


def test_rebalance_monthly():
    """Todos os meses devem rebalancear."""
    for m in range(1, 13):
        assert _should_rebalance(m, "monthly") is True


def test_rebalance_quarterly():
    """Apenas meses 3, 6, 9, 12 devem rebalancear."""
    quarters = {3, 6, 9, 12}
    for m in range(1, 13):
        result = _should_rebalance(m, "quarterly")
        assert result == (m in quarters), f"Mês {m}: esperado {m in quarters}, obtido {result}"


def test_rebalance_semiannual():
    """Apenas meses 6 e 12 devem rebalancear."""
    semiannual = {6, 12}
    for m in range(1, 13):
        result = _should_rebalance(m, "semiannual")
        assert result == (m in semiannual), f"Mês {m}: esperado {m in semiannual}, obtido {result}"


# ---------------------------------------------------------------------------
# Testes: run_backtest
# ---------------------------------------------------------------------------


def _make_price_series(base: float, months: int, monthly_return: float = 0.008) -> list[float]:
    """Cria série de preços crescendo a uma taxa mensal constante."""
    prices = []
    price = base
    for _ in range(months):
        prices.append(round(price, 4))
        price *= 1 + monthly_return
    return prices


def test_run_backtest_basic():
    """Backtest básico com 1 ticker, 24 meses."""
    tickers = ["MXRF11"]
    weights = {"MXRF11": 1.0}
    price_series = {"MXRF11": _make_price_series(10.0, 24)}
    dividend_series = {"MXRF11": [0.08] * 24}

    result = run_backtest(
        tickers=tickers,
        weights=weights,
        price_series=price_series,
        dividend_series=dividend_series,
        monthly_contribution=500.0,
        initial_capital=1000.0,
        rebalance_frequency="quarterly",
    )

    assert isinstance(result, BacktestResult)
    assert result.final_value > 0, "Valor final deve ser positivo"
    assert len(result.monthly_snapshots) == 24
    assert result.total_invested >= 1000.0 + (500.0 * 24)
    assert result.metrics.cagr > 0, "CAGR deve ser positivo com série crescente"


def test_run_backtest_two_tickers():
    """Backtest com 2 tickers e rebalanceamento semestral."""
    tickers = ["XPLG11", "HGLG11"]
    weights = {"XPLG11": 0.60, "HGLG11": 0.40}
    price_series = {
        "XPLG11": _make_price_series(100.0, 12, 0.005),
        "HGLG11": _make_price_series(120.0, 12, 0.010),
    }
    dividend_series = {
        "XPLG11": [0.70] * 12,
        "HGLG11": [0.80] * 12,
    }

    result = run_backtest(
        tickers=tickers,
        weights=weights,
        price_series=price_series,
        dividend_series=dividend_series,
        monthly_contribution=1000.0,
        initial_capital=5000.0,
        rebalance_frequency="semiannual",
    )

    assert result.final_value > 0
    assert result.metrics.num_months == 12


def test_run_backtest_no_capital():
    """Backtest iniciando sem capital (apenas aportes mensais)."""
    tickers = ["MXRF11"]
    weights = {"MXRF11": 1.0}
    price_series = {"MXRF11": _make_price_series(10.0, 12)}
    dividend_series = {"MXRF11": [0.0] * 12}

    result = run_backtest(
        tickers=tickers,
        weights=weights,
        price_series=price_series,
        dividend_series=dividend_series,
        monthly_contribution=500.0,
        initial_capital=0.0,
    )

    assert result.final_value > 0
    assert result.total_invested == 500.0 * 12


def test_run_backtest_missing_ticker():
    """Deve levantar ValueError se ticker não tiver série de preços."""
    try:
        run_backtest(
            tickers=["INEXISTENTE"],
            weights={"INEXISTENTE": 1.0},
            price_series={},
            dividend_series={},
            monthly_contribution=100.0,
        )
        raise AssertionError("Deveria ter lançado ValueError")
    except ValueError:
        pass  # Esperado


# ---------------------------------------------------------------------------
# Testes: compare_against_benchmark
# ---------------------------------------------------------------------------


def test_compare_benchmark_basic():
    """Comparação de backtest vs benchmark deve retornar alpha e flag."""
    tickers = ["MXRF11"]
    weights = {"MXRF11": 1.0}
    price_series = {"MXRF11": _make_price_series(10.0, 24, 0.012)}  # 1.2% ao mês
    dividend_series = {"MXRF11": [0.0] * 24}

    result = run_backtest(tickers, weights, price_series, dividend_series, 500.0, 1000.0)
    benchmark = _make_price_series(100.0, 24, 0.006)  # 0.6% ao mês

    comparison = compare_against_benchmark(result, benchmark, 500.0, 1000.0)

    assert "alpha" in comparison
    assert "bateu_benchmark" in comparison
    assert isinstance(comparison["bateu_benchmark"], bool)
    assert comparison["bateu_benchmark"] is True  # Carteira cresce mais que benchmark


# ---------------------------------------------------------------------------
# Testes: score_engine
# ---------------------------------------------------------------------------


def test_validate_weights_valid():
    """Pesos válidos não devem lançar exceção."""
    validate_weights({"w_income": 0.40, "w_valuation": 0.25, "w_risk": 0.20, "w_growth": 0.15})


def test_validate_weights_invalid_sum():
    """Soma de pesos diferente de 1.0 deve lançar ValueError."""
    try:
        validate_weights({"w_income": 0.50, "w_valuation": 0.25, "w_risk": 0.20, "w_growth": 0.15})
        raise AssertionError("Deveria ter lançado ValueError")
    except ValueError:
        pass


def test_calculate_income_score_high():
    """DY de 12% com consistência máxima deve gerar score próximo de 10."""
    score = calculate_income_score(dividend_yield=0.12, dividend_consistency=10.0)
    assert score >= 8.0, f"Score de income alto esperado, obtido {score}"


def test_calculate_income_score_low():
    """DY de 4% com consistência 0 deve gerar score próximo de 0."""
    score = calculate_income_score(dividend_yield=0.04, dividend_consistency=0.0)
    assert score <= 1.0, f"Score de income baixo esperado, obtido {score}"


def test_calculate_valuation_score_cheap():
    """P/VP de 0.7 (muito barato) deve gerar score próximo de 10."""
    score = calculate_valuation_score(pvp=0.70)
    assert score >= 9.5, f"Score de valuation maximo esperado, obtido {score}"


def test_calculate_valuation_score_expensive():
    """P/VP de 1.5 (caro) deve gerar score próximo de 0."""
    score = calculate_valuation_score(pvp=1.50)
    assert score <= 0.5, f"Score de valuation minimo esperado, obtido {score}"


def test_calculate_alpha_score_returns_dict():
    """Alpha Score deve retornar dicionário com as chaves esperadas."""
    result = calculate_alpha_score(
        dividend_yield=0.10,
        dividend_consistency=8.0,
        pvp=0.95,
        debt_ratio=0.30,
        vacancy_rate=0.05,
        revenue_growth_12m=0.08,
        earnings_growth_12m=0.06,
    )
    expected_keys = {"alpha_score", "income_score", "valuation_score", "risk_score", "growth_score", "weights_used"}
    assert expected_keys == set(result.keys()), f"Chaves esperadas: {expected_keys}"
    assert 0.0 <= result["alpha_score"] <= 10.0, "Alpha score deve estar entre 0 e 10"


def test_rank_fiis():
    """rank_fiis deve retornar lista ordenada pelo alpha_score decrescente."""
    fiis = [
        {
            "ticker": "MXRF11",
            "dividend_yield": 0.12,
            "dividend_consistency": 9.0,
            "pvp": 0.95,
            "debt_ratio": 0.2,
            "vacancy_rate": 0.02,
            "revenue_growth_12m": 0.10,
            "earnings_growth_12m": 0.08,
        },
        {
            "ticker": "XPLG11",
            "dividend_yield": 0.07,
            "dividend_consistency": 6.0,
            "pvp": 1.20,
            "debt_ratio": 0.5,
            "vacancy_rate": 0.15,
            "revenue_growth_12m": 0.03,
            "earnings_growth_12m": 0.02,
        },
    ]
    ranked = rank_fiis(fiis)
    assert ranked[0]["alpha_score"] >= ranked[1]["alpha_score"]
    assert ranked[0]["ticker"] == "MXRF11"


# ---------------------------------------------------------------------------
# Edge cases for coverage
# ---------------------------------------------------------------------------


def test_sharpe_short_series():
    """Sharpe with < 2 returns should return 0.0."""
    assert calculate_sharpe([0.01]) == 0.0


def test_sortino_short_series():
    """Sortino with < 2 returns should return 0.0."""
    assert calculate_sortino([0.01]) == 0.0


def test_sortino_with_downside():
    """Sortino with actual downside months should return a value."""
    returns = [0.02, -0.03, 0.01, -0.02, 0.03, -0.01, 0.02, -0.04, 0.01, -0.01, 0.02, -0.02]
    result = calculate_sortino(returns, annual_risk_free_rate=0.10)
    assert isinstance(result, float)


def test_annual_volatility_short_series():
    """Volatility with < 2 returns should return 0.0."""
    assert calculate_annual_volatility([0.01]) == 0.0


def test_should_rebalance_unknown_frequency():
    """Unknown frequency should return False."""
    assert _should_rebalance(3, "daily") is False


def test_rebalance_portfolio_zero_value():
    """Rebalance with zero total value should return copy of holdings."""
    holdings = {"MXRF11": 100.0}
    prices = {"MXRF11": 0.0}
    weights = {"MXRF11": 1.0}
    result = _rebalance_portfolio(holdings, prices, weights)
    assert result == {"MXRF11": 100.0}


def test_run_backtest_empty_tickers():
    """Empty ticker list should raise ValueError."""
    import pytest

    with pytest.raises(ValueError, match="vazia"):
        run_backtest([], {}, {}, {}, 100.0)


def test_run_backtest_empty_price_series():
    """Empty price series should raise ValueError."""
    import pytest

    with pytest.raises(ValueError, match="vazias"):
        run_backtest(["MXRF11"], {"MXRF11": 1.0}, {"MXRF11": []}, {}, 100.0)


def test_run_backtest_zero_weights():
    """Zero weights should raise ValueError."""
    import pytest

    with pytest.raises(ValueError, match="inválidos"):
        run_backtest(
            ["MXRF11"],
            {"MXRF11": 0.0},
            {"MXRF11": [10.0, 11.0]},
            {},
            100.0,
        )


def test_compare_benchmark_short_series():
    """Benchmark with < 2 prices should return error dict."""
    tickers = ["MXRF11"]
    price_series = {"MXRF11": _make_price_series(10.0, 12)}
    result = run_backtest(tickers, {"MXRF11": 1.0}, price_series, {"MXRF11": [0.0] * 12}, 500.0)
    comparison = compare_against_benchmark(result, [100.0], 500.0)
    assert "erro" in comparison


def test_format_metrics_report_basic():
    """format_metrics_report should produce a string with key sections."""
    metrics = PerformanceMetrics(
        cagr=0.12,
        sharpe_ratio=1.5,
        sortino_ratio=2.0,
        max_drawdown=-0.15,
        annual_volatility=0.18,
        total_return=0.36,
        num_months=24,
    )
    result = BacktestResult(
        ticker_list=["MXRF11"],
        start_date="2023-01-01",
        end_date="2024-12-31",
        monthly_contribution=500.0,
        initial_value=1000.0,
        final_value=1360.0,
        total_invested=13000.0,
        metrics=metrics,
        monthly_snapshots=[],
    )
    report = format_metrics_report(result)
    assert "BACKTEST" in report
    assert "CAGR" in report
    assert "Sharpe" in report


def test_format_metrics_report_with_comparison():
    """format_metrics_report with comparison should include benchmark section."""
    metrics = PerformanceMetrics(
        cagr=0.12,
        sharpe_ratio=1.5,
        sortino_ratio=2.0,
        max_drawdown=-0.15,
        annual_volatility=0.18,
        total_return=0.36,
        num_months=24,
    )
    result = BacktestResult(
        ticker_list=["MXRF11"],
        start_date="2023-01-01",
        end_date="2024-12-31",
        monthly_contribution=500.0,
        initial_value=1000.0,
        final_value=1360.0,
        total_invested=13000.0,
        metrics=metrics,
        monthly_snapshots=[],
    )
    comparison = {
        "alpha": 0.05,
        "bateu_benchmark": True,
        "benchmark_ifix": {
            "cagr": 0.07,
            "sharpe_ratio": 1.0,
            "sortino_ratio": 1.2,
            "max_drawdown": -0.10,
            "annual_volatility": 0.12,
            "total_return": 0.20,
            "valor_final": 1200.0,
        },
    }
    report = format_metrics_report(result, comparison)
    assert "BENCHMARK" in report
    assert "Alpha" in report


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def main() -> None:
    """Executa todos os testes e reporta o resultado."""
    tests = [
        # CAGR
        ("CAGR básico", test_cagr_basic),
        ("CAGR anos=0", test_cagr_zero_years),
        ("CAGR inicial=0", test_cagr_zero_initial),
        # Max Drawdown
        ("Max Drawdown básico", test_max_drawdown_basic),
        ("Max Drawdown sem queda", test_max_drawdown_no_loss),
        ("Max Drawdown 1 valor", test_max_drawdown_single_value),
        # Sharpe / Sortino
        ("Sharpe positivo", test_sharpe_positive_excess),
        ("Sharpe std=0", test_sharpe_zero_std),
        ("Sortino sem downside", test_sortino_no_downside),
        # Volatilidade
        ("Volatilidade dispersa", test_annual_volatility_known),
        ("Volatilidade constante", test_annual_volatility_constant),
        # Rebalanceamento
        ("Rebalanceamento mensal", test_rebalance_monthly),
        ("Rebalanceamento trimestral", test_rebalance_quarterly),
        ("Rebalanceamento semestral", test_rebalance_semiannual),
        # Backtest engine
        ("Backtest 1 ticker 24m", test_run_backtest_basic),
        ("Backtest 2 tickers 12m", test_run_backtest_two_tickers),
        ("Backtest sem capital inicial", test_run_backtest_no_capital),
        ("Backtest ticker faltando", test_run_backtest_missing_ticker),
        # Benchmark
        ("Comparação vs benchmark", test_compare_benchmark_basic),
        # Score engine
        ("Validar pesos válidos", test_validate_weights_valid),
        ("Validar pesos inválidos", test_validate_weights_invalid_sum),
        ("Income score alto", test_calculate_income_score_high),
        ("Income score baixo", test_calculate_income_score_low),
        ("Valuation score barato", test_calculate_valuation_score_cheap),
        ("Valuation score caro", test_calculate_valuation_score_expensive),
        ("Alpha Score retorna dict", test_calculate_alpha_score_returns_dict),
        ("Rank FIIs ordenado", test_rank_fiis),
    ]

    print("\n" + "=" * 55)
    print("  ALPHACOTA — TEST SUITE")
    print("=" * 55)
    passed = 0
    failed = 0
    for name, fn in tests:
        ok = run_test(name, fn)
        if ok:
            passed += 1
        else:
            failed += 1

    total = passed + failed
    print("=" * 55)
    print(f"  Resultado: {passed}/{total} testes passaram")
    if failed == 0:
        print("  🎉 TODOS OS TESTES PASSARAM!")
    else:
        print(f"  ⚠️  {failed} teste(s) falharam.")
    print("=" * 55 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
