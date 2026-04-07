"""
core/backtest_engine.py

Motor de backtest quantitativo para carteiras de FIIs.

Simula aportes mensais, rebalanceamento periódico e calcula métricas
de performance (CAGR, Sharpe, Sortino, Max Drawdown, Volatilidade)
comparando contra o benchmark IFIX.

Segue as regras do projeto: funções puras, type hints, sem classes,
sem frameworks externos além de math/statistics da stdlib.
"""

import math
import statistics
from typing import Optional
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Data containers (dataclasses simples, sem lógica)
# ---------------------------------------------------------------------------


@dataclass
class BacktestResult:
    """Resultado completo de um backtest."""

    ticker_list: list[str]
    start_date: str
    end_date: str
    monthly_contribution: float
    initial_value: float
    final_value: float
    total_invested: float
    metrics: "PerformanceMetrics"
    monthly_snapshots: list[dict] = field(default_factory=list)
    benchmark_metrics: Optional["PerformanceMetrics"] = None


@dataclass
class PerformanceMetrics:
    """Conjunto de métricas de performance de uma série de retornos."""

    cagr: float  # Crescimento Anual Composto
    sharpe_ratio: float  # Relação retorno/risco total
    sortino_ratio: float  # Relação retorno/risco downside
    max_drawdown: float  # Maior queda pico-a-fundo (negativo)
    annual_volatility: float  # Volatilidade anualizada
    total_return: float  # Retorno total percentual
    num_months: int  # Número de meses simulados


# ---------------------------------------------------------------------------
# Funções de métricas puras
# ---------------------------------------------------------------------------


def calculate_cagr(
    initial_value: float,
    final_value: float,
    num_years: float,
) -> float:
    """
    Calcula o CAGR (Compound Annual Growth Rate).

    Args:
        initial_value (float): Valor inicial do portfólio.
        final_value (float): Valor final do portfólio.
        num_years (float): Número de anos do período.

    Returns:
        float: CAGR como decimal (ex: 0.12 = 12% ao ano). 0.0 se inválido.
    """
    if initial_value <= 0 or final_value <= 0 or num_years <= 0:
        return 0.0
    return (final_value / initial_value) ** (1.0 / num_years) - 1.0


def calculate_sharpe(
    monthly_returns: list[float],
    annual_risk_free_rate: float = 0.1075,  # CDI ~10.75% a.a. (referência Brasil)
) -> float:
    """
    Calcula o Sharpe Ratio anualizado.

    Args:
        monthly_returns (list[float]): Retornos mensais da série.
        annual_risk_free_rate (float): Taxa livre de risco anual. Default CDI ~10.75%.

    Returns:
        float: Sharpe Ratio. 0.0 se desvio padrão for zero.
    """
    if len(monthly_returns) < 2:
        return 0.0

    monthly_rf = (1 + annual_risk_free_rate) ** (1 / 12) - 1
    excess_returns = [r - monthly_rf for r in monthly_returns]

    mean_excess = sum(excess_returns) / len(excess_returns)
    std_dev = statistics.stdev(excess_returns)

    if std_dev == 0:
        return 0.0

    # Anualizar: sharpe mensal × sqrt(12)
    return (mean_excess / std_dev) * math.sqrt(12)


def calculate_sortino(
    monthly_returns: list[float],
    annual_risk_free_rate: float = 0.1075,
) -> float:
    """
    Calcula o Sortino Ratio anualizado (penaliza apenas volatilidade negativa).

    Args:
        monthly_returns (list[float]): Retornos mensais da série.
        annual_risk_free_rate (float): Taxa livre de risco anual.

    Returns:
        float: Sortino Ratio. 0.0 se desvio downside for zero.
    """
    if len(monthly_returns) < 2:
        return 0.0

    monthly_rf = (1 + annual_risk_free_rate) ** (1 / 12) - 1
    excess_returns = [r - monthly_rf for r in monthly_returns]
    mean_excess = sum(excess_returns) / len(excess_returns)

    # Apenas retornos abaixo do target (downside)
    downside = [r for r in excess_returns if r < 0]
    if not downside:
        return 0.0  # Sem meses negativos → Sortino indefinido

    downside_variance = sum(r**2 for r in downside) / len(downside)
    downside_std = math.sqrt(downside_variance)

    if downside_std == 0:
        return 0.0

    return (mean_excess / downside_std) * math.sqrt(12)


def calculate_max_drawdown(portfolio_values: list[float]) -> float:
    """
    Calcula o Max Drawdown (maior queda pico-a-fundo) de uma série de valores.

    Args:
        portfolio_values (list[float]): Série de valores do portfólio mês a mês.

    Returns:
        float: Max Drawdown como decimal negativo (ex: -0.25 = queda de 25%).
               0.0 se a série tiver menos de 2 valores.
    """
    if len(portfolio_values) < 2:
        return 0.0

    peak = portfolio_values[0]
    max_dd = 0.0

    for value in portfolio_values:
        if value > peak:
            peak = value
        elif peak > 0:
            drawdown = (value - peak) / peak
            if drawdown < max_dd:
                max_dd = drawdown

    return round(max_dd, 6)


def calculate_annual_volatility(monthly_returns: list[float]) -> float:
    """
    Calcula a volatilidade anualizada a partir de retornos mensais.

    Args:
        monthly_returns (list[float]): Série de retornos mensais.

    Returns:
        float: Volatilidade anualizada como decimal. 0.0 se dados insuficientes.
    """
    if len(monthly_returns) < 2:
        return 0.0

    std_monthly = statistics.stdev(monthly_returns)
    return std_monthly * math.sqrt(12)


def calculate_metrics(
    portfolio_values: list[float],
    initial_value: float,
    annual_risk_free_rate: float = 0.1075,
) -> PerformanceMetrics:
    """
    Calcula o conjunto completo de métricas de performance a partir
    de uma série de valores mensais do portfólio.

    Args:
        portfolio_values (list[float]): Valores mensais do portfólio.
        initial_value (float): Capital inicial antes da simulação.
        annual_risk_free_rate (float): Taxa livre de risco anual.

    Returns:
        PerformanceMetrics: Objeto com todas as métricas calculadas.
    """
    num_months = len(portfolio_values)
    num_years = num_months / 12.0

    final_value = portfolio_values[-1] if portfolio_values else 0.0

    # Retornos mensais a partir da série de valores
    monthly_returns: list[float] = []
    for i in range(1, num_months):
        prev = portfolio_values[i - 1]
        curr = portfolio_values[i]
        monthly_returns.append((curr / prev - 1.0) if prev > 0 else 0.0)

    cagr = calculate_cagr(initial_value, final_value, num_years)
    total_return = (final_value / initial_value - 1.0) if initial_value > 0 else 0.0
    sharpe = calculate_sharpe(monthly_returns, annual_risk_free_rate)
    sortino = calculate_sortino(monthly_returns, annual_risk_free_rate)
    max_dd = calculate_max_drawdown(portfolio_values)
    vol = calculate_annual_volatility(monthly_returns)

    return PerformanceMetrics(
        cagr=round(cagr, 6),
        sharpe_ratio=round(sharpe, 4),
        sortino_ratio=round(sortino, 4),
        max_drawdown=round(max_dd, 6),
        annual_volatility=round(vol, 6),
        total_return=round(total_return, 6),
        num_months=num_months,
    )


# ---------------------------------------------------------------------------
# Motor de rebalanceamento
# ---------------------------------------------------------------------------


def _should_rebalance(month: int, frequency: str) -> bool:
    """
    Determina se o mês corrente é um mês de rebalanceamento.

    Args:
        month (int): Mês atual da simulação (1-based).
        frequency (str): 'monthly', 'quarterly' ou 'semiannual'.

    Returns:
        bool: True se deve rebalancear neste mês.
    """
    if frequency == "monthly":
        return True
    elif frequency == "quarterly":
        return month % 3 == 0
    elif frequency == "semiannual":
        return month % 6 == 0
    return False


def _rebalance_portfolio(
    holdings: dict[str, float],
    prices: dict[str, float],
    weights: dict[str, float],
) -> dict[str, float]:
    """
    Rebalanceia o portfólio comprando/vendendo cotas para atingir os pesos alvo.
    Operação simulada: não há custo de transação nesta versão.

    Args:
        holdings (dict[str, float]): Quantidade de cotas por ticker.
        prices (dict[str, float]): Preço atual por ticker.
        weights (dict[str, float]): Pesos alvo (somam 1.0) por ticker.

    Returns:
        dict[str, float]: Novo holdings rebalanceado.
    """
    total_value = sum(holdings.get(t, 0.0) * prices.get(t, 0.0) for t in prices)
    if total_value <= 0:
        return holdings.copy()

    new_holdings = {}
    for ticker, price in prices.items():
        target_weight = weights.get(ticker, 0.0)
        target_value = total_value * target_weight
        new_holdings[ticker] = (target_value / price) if price > 0 else 0.0

    return new_holdings


# ---------------------------------------------------------------------------
# Motor principal de backtest
# ---------------------------------------------------------------------------


def run_backtest(
    tickers: list[str],
    weights: dict[str, float],
    price_series: dict[str, list[float]],
    dividend_series: dict[str, list[float]],
    monthly_contribution: float,
    initial_capital: float = 0.0,
    rebalance_frequency: str = "quarterly",
    annual_risk_free_rate: float = 0.1075,
) -> BacktestResult:
    """
    Executa o backtest de uma carteira de FIIs com aportes mensais.

    Os pesos alvo são usados tanto para alocação inicial quanto para
    rebalanceamento periódico. Dividendos são reinvestidos automaticamente.

    Args:
        tickers (list[str]): Lista de tickers da carteira.
        weights (dict[str, float]): Pesos alvo por ticker (devem somar 1.0).
        price_series (dict[str, list[float]]): Série de preços mensais por ticker.
            Todas as séries devem ter o mesmo comprimento.
        dividend_series (dict[str, list[float]]): Série de dividendos mensais por ticker.
            Pode ser lista de zeros se não disponível.
        monthly_contribution (float): Valor aporteado mensalmente em reais.
        initial_capital (float): Capital inicial para compra de cotas no mês 0.
        rebalance_frequency (str): Frequência de rebalanceamento:
            'monthly', 'quarterly' ou 'semiannual'.
        annual_risk_free_rate (float): Taxa livre de risco anual para métricas.

    Returns:
        BacktestResult: Resultado completo com métricas e snapshots mensais.

    Raises:
        ValueError: Se tickers não tiverem dados de preço ou séries de
                    comprimento diferente.
    """
    # Validações
    if not tickers:
        raise ValueError("Lista de tickers não pode ser vazia.")
    for t in tickers:
        if t not in price_series:
            raise ValueError(
                f"Ticker '{t}' não possui série de preços. " f"Verifique os dados em data/historical_prices/."
            )

    # Garantir que todos têm o mesmo número de meses
    lengths = {t: len(price_series[t]) for t in tickers}
    num_months = min(lengths.values())
    if num_months == 0:
        raise ValueError("Séries de preços vazias. Não é possível executar backtest.")

    # Normalizar pesos para somar 1.0
    total_weight = sum(weights.get(t, 0.0) for t in tickers)
    if total_weight <= 0:
        raise ValueError("Pesos da carteira inválidos (soma = 0).")
    norm_weights = {t: weights.get(t, 0.0) / total_weight for t in tickers}

    # Inicializar holdings com capital inicial
    holdings: dict[str, float] = {}
    month_0_prices = {t: price_series[t][0] for t in tickers}

    if initial_capital > 0:
        for ticker in tickers:
            target_value = initial_capital * norm_weights.get(ticker, 0.0)
            price = month_0_prices[ticker]
            holdings[ticker] = (target_value / price) if price > 0 else 0.0
    else:
        holdings = {t: 0.0 for t in tickers}

    portfolio_values: list[float] = []
    monthly_snapshots: list[dict] = []

    total_invested = initial_capital

    for month_idx in range(num_months):
        current_prices = {t: price_series[t][month_idx] for t in tickers}

        # 1) Receber dividendos do mês e reinvestir proporcionalmente
        dividend_cash = 0.0
        for ticker in tickers:
            div_series = dividend_series.get(ticker, [])
            monthly_div = div_series[month_idx] if month_idx < len(div_series) else 0.0
            dividend_cash += holdings.get(ticker, 0.0) * monthly_div

        # 2) Adicionar aporte mensal ao caixa disponível
        cash_to_invest = monthly_contribution + dividend_cash
        total_invested += monthly_contribution

        # 3) Investir o caixa proporcionalmente aos pesos
        for ticker in tickers:
            price = current_prices.get(ticker, 0.0)
            if price > 0:
                alloc_cash = cash_to_invest * norm_weights.get(ticker, 0.0)
                new_cotas = alloc_cash / price
                holdings[ticker] = holdings.get(ticker, 0.0) + new_cotas

        # 4) Rebalancear se necessário (mês 1-based)
        month_num = month_idx + 1
        if month_idx > 0 and _should_rebalance(month_num, rebalance_frequency):
            holdings = _rebalance_portfolio(holdings, current_prices, norm_weights)

        # 5) Calcular valor total do portfólio
        portfolio_value = sum(holdings.get(t, 0.0) * current_prices.get(t, 0.0) for t in tickers)
        portfolio_values.append(portfolio_value)

        # 6) Snapshot do mês
        snapshot = {
            "month": month_num,
            "portfolio_value": round(portfolio_value, 2),
            "holdings": {t: round(holdings.get(t, 0.0), 4) for t in tickers},
            "prices": {t: round(current_prices.get(t, 0.0), 2) for t in tickers},
            "dividend_cash": round(dividend_cash, 2),
            "rebalanced": month_idx > 0 and _should_rebalance(month_num, rebalance_frequency),
        }
        monthly_snapshots.append(snapshot)

    # Calcular métricas
    initial_value = initial_capital if initial_capital > 0 else monthly_contribution
    metrics = calculate_metrics(portfolio_values, initial_value, annual_risk_free_rate)

    return BacktestResult(
        ticker_list=tickers,
        start_date="",  # Preenchido pelo caller com string de data
        end_date="",  # Preenchido pelo caller com string de data
        monthly_contribution=monthly_contribution,
        initial_value=initial_capital,
        final_value=portfolio_values[-1] if portfolio_values else 0.0,
        total_invested=round(total_invested, 2),
        metrics=metrics,
        monthly_snapshots=monthly_snapshots,
    )


def compare_against_benchmark(
    portfolio_result: BacktestResult,
    benchmark_prices: list[float],
    monthly_contribution: float,
    initial_capital: float = 0.0,
    annual_risk_free_rate: float = 0.1075,
) -> dict:
    """
    Compara o resultado do backtest da carteira contra o benchmark (ex: IFIX).

    Simula o mesmo padrão de aportes mensais no benchmark para comparação direta.

    Args:
        portfolio_result (BacktestResult): Resultado do backtest da carteira.
        benchmark_prices (list[float]): Série de preços mensais do benchmark.
        monthly_contribution (float): Mesmo aporte mensal usado na carteira.
        initial_capital (float): Mesmo capital inicial usado na carteira.
        annual_risk_free_rate (float): Taxa livre de risco anual.

    Returns:
        dict: Comparativo com métricas de ambos e indicadores de alpha.
    """
    if len(benchmark_prices) < 2:
        return {"erro": "Série do benchmark muito curta para comparação."}

    num_months = min(len(benchmark_prices), portfolio_result.metrics.num_months)
    benchmark_prices = benchmark_prices[:num_months]

    # Simular aportes mensais no benchmark (buy & hold proporcional)
    benchmark_holdings: float = (initial_capital / benchmark_prices[0]) if benchmark_prices[0] > 0 else 0.0
    benchmark_values: list[float] = []

    for month_idx, price in enumerate(benchmark_prices):
        # Aporte mensal no benchmark
        if price > 0:
            benchmark_holdings += monthly_contribution / price
        bv = benchmark_holdings * price
        benchmark_values.append(bv)

    initial_bv = initial_capital if initial_capital > 0 else monthly_contribution
    benchmark_metrics = calculate_metrics(benchmark_values, initial_bv, annual_risk_free_rate)

    portfolio_metrics = portfolio_result.metrics

    # Alpha simples: CAGR da carteira - CAGR do benchmark
    alpha = portfolio_metrics.cagr - benchmark_metrics.cagr

    return {
        "carteira": {
            "cagr": portfolio_metrics.cagr,
            "sharpe_ratio": portfolio_metrics.sharpe_ratio,
            "sortino_ratio": portfolio_metrics.sortino_ratio,
            "max_drawdown": portfolio_metrics.max_drawdown,
            "annual_volatility": portfolio_metrics.annual_volatility,
            "total_return": portfolio_metrics.total_return,
            "valor_final": round(portfolio_result.final_value, 2),
        },
        "benchmark_ifix": {
            "cagr": benchmark_metrics.cagr,
            "sharpe_ratio": benchmark_metrics.sharpe_ratio,
            "sortino_ratio": benchmark_metrics.sortino_ratio,
            "max_drawdown": benchmark_metrics.max_drawdown,
            "annual_volatility": benchmark_metrics.annual_volatility,
            "total_return": benchmark_metrics.total_return,
            "valor_final": round(benchmark_values[-1], 2) if benchmark_values else 0.0,
        },
        "alpha": round(alpha, 6),
        "bateu_benchmark": alpha > 0,
        "num_months": num_months,
    }


def format_metrics_report(result: BacktestResult, comparison: Optional[dict] = None) -> str:
    """
    Formata um relatório textual das métricas do backtest.

    Args:
        result (BacktestResult): Resultado do backtest.
        comparison (dict, optional): Resultado de compare_against_benchmark.

    Returns:
        str: Relatório formatado em texto.
    """
    m = result.metrics
    lines = [
        "=" * 55,
        "  ALPHACOTA — RELATÓRIO DE BACKTEST",
        "=" * 55,
        f"  Tickers          : {', '.join(result.ticker_list)}",
        f"  Capital Inicial  : R$ {result.initial_value:,.2f}",
        f"  Aporte Mensal    : R$ {result.monthly_contribution:,.2f}",
        f"  Total Investido  : R$ {result.total_invested:,.2f}",
        f"  Valor Final      : R$ {result.final_value:,.2f}",
        f"  Período          : {m.num_months} meses ({m.num_months/12:.1f} anos)",
        "-" * 55,
        "  MÉTRICAS DE PERFORMANCE",
        "-" * 55,
        f"  CAGR             : {m.cagr * 100:.2f}% a.a.",
        f"  Retorno Total    : {m.total_return * 100:.2f}%",
        f"  Sharpe Ratio     : {m.sharpe_ratio:.3f}",
        f"  Sortino Ratio    : {m.sortino_ratio:.3f}",
        f"  Max Drawdown     : {m.max_drawdown * 100:.2f}%",
        f"  Volatilidade a.a.: {m.annual_volatility * 100:.2f}%",
    ]

    if comparison and "alpha" in comparison:
        bm = comparison["benchmark_ifix"]
        lines += [
            "-" * 55,
            "  VS BENCHMARK (IFIX)",
            "-" * 55,
            f"  IFIX CAGR        : {bm['cagr'] * 100:.2f}% a.a.",
            f"  Alpha            : {comparison['alpha'] * 100:+.2f}% a.a.",
            f"  Bateu Benchmark  : {'✅ SIM' if comparison['bateu_benchmark'] else '❌ NÃO'}",
        ]

    lines.append("=" * 55)
    return "\n".join(lines)
