"""
core/markowitz_engine.py

Otimização de portfólio baseada em Mean-Variance (Markowitz, 1952).

Implementado em Python puro (stdlib + math/statistics) sem dependências externas.

Estratégias disponíveis:
- Max Sharpe Ratio  → melhor retorno ajustado ao risco
- Min Volatility    → menor volatilidade possível
- Fronteira Eficiente via Monte Carlo de pesos

Funções puras, sem classes. Compatível com correlation_engine.py.
"""

import math
import random
import statistics
from typing import Optional


# ---------------------------------------------------------------------------
# Primitivas de retorno e risco
# ---------------------------------------------------------------------------

def calculate_expected_return(
    returns: list[float],
    annualize: bool = True,
) -> float:
    """
    Calcula o retorno esperado anualizado de uma série de retornos mensais.

    Args:
        returns (list[float]): Retornos mensais (ex: 0.012 = 1.2%).
        annualize (bool): Se True, converte retorno mensal para anual. Default: True.

    Returns:
        float: Retorno esperado (mensal ou anual).
    """
    if not returns:
        return 0.0
    mean_monthly = sum(returns) / len(returns)
    if annualize:
        return (1 + mean_monthly) ** 12 - 1
    return mean_monthly


def calculate_annual_volatility(returns: list[float]) -> float:
    """
    Calcula a volatilidade anualizada de uma série de retornos mensais.

    Args:
        returns (list[float]): Retornos mensais.

    Returns:
        float: Volatilidade anualizada. 0.0 se menos de 2 pontos.
    """
    if len(returns) < 2:
        return 0.0
    return statistics.stdev(returns) * math.sqrt(12)


def calculate_portfolio_return(
    weights: dict[str, float],
    expected_returns: dict[str, float],
) -> float:
    """
    Calcula o retorno esperado do portfólio ponderado pelos pesos.

    Args:
        weights (dict[str, float]): Peso de cada ativo (somam 1.0).
        expected_returns (dict[str, float]): Retorno esperado de cada ativo.

    Returns:
        float: Retorno esperado do portfólio.
    """
    return sum(weights.get(t, 0.0) * expected_returns.get(t, 0.0) for t in weights)


def calculate_portfolio_vol(
    weights: dict[str, float],
    volatilities: dict[str, float],
    correlation_matrix: dict[str, dict[str, float]],
) -> float:
    """
    Calcula a volatilidade do portfólio usando a fórmula matricial de Markowitz.

    σ_p = sqrt(Σ_i Σ_j w_i * w_j * σ_i * σ_j * ρ_ij)

    Args:
        weights (dict[str, float]): Pesos dos ativos.
        volatilities (dict[str, float]): Volatilidade anual de cada ativo.
        correlation_matrix (dict): Matriz de correlação de Pearson.

    Returns:
        float: Volatilidade anualizada do portfólio.
    """
    tickers = list(weights.keys())
    variance = 0.0

    for t1 in tickers:
        for t2 in tickers:
            w1   = weights.get(t1, 0.0)
            w2   = weights.get(t2, 0.0)
            s1   = volatilities.get(t1, 0.0)
            s2   = volatilities.get(t2, 0.0)
            corr = correlation_matrix.get(t1, {}).get(t2, 1.0 if t1 == t2 else 0.0)
            variance += w1 * w2 * s1 * s2 * corr

    return math.sqrt(max(variance, 0.0))


def calculate_sharpe(
    portfolio_return: float,
    portfolio_vol: float,
    risk_free_rate: float = 0.1075,
) -> float:
    """
    Calcula o Sharpe Ratio de um portfólio.

    Args:
        portfolio_return (float): Retorno anual esperado do portfólio.
        portfolio_vol (float): Volatilidade anual do portfólio.
        risk_free_rate (float): Taxa livre de risco anual (Selic default: 10.75%).

    Returns:
        float: Sharpe Ratio. 0.0 se volatilidade for zero.
    """
    if portfolio_vol <= 0:
        return 0.0
    return (portfolio_return - risk_free_rate) / portfolio_vol


# ---------------------------------------------------------------------------
# Geração aleatória de pesos (base do Monte Carlo de portfólio)
# ---------------------------------------------------------------------------

def _random_weights(
    n: int,
    seed: Optional[int] = None,
    min_weight: float = 0.0,
    max_weight: float = 1.0,
) -> list[float]:
    """
    Gera n pesos aleatórios que somam 1.0, respeitando limites por ativo.

    Args:
        n (int): Número de ativos.
        seed (int | None): Semente para reprodutibilidade.
        min_weight (float): Peso mínimo permitido por ativo.
        max_weight (float): Peso máximo permitido por ativo (ex: 0.40 = 40%).

    Returns:
        list[float]: Pesos normalizados somando 1.0.
    """
    if seed is not None:
        random.seed(seed)

    for _ in range(1000):  # Tentativas para respeitar os limites
        raw = [random.random() for _ in range(n)]
        total = sum(raw)
        if total == 0:
            continue
        weights = [r / total for r in raw]

        if all(min_weight <= w <= max_weight for w in weights):
            return weights

    # Fallback: equally weighted se não convergir
    return [1.0 / n] * n


# ---------------------------------------------------------------------------
# Monte Carlo de portfólio (fronteira eficiente simulada)
# ---------------------------------------------------------------------------

def simulate_portfolio_frontier(
    tickers: list[str],
    return_series: dict[str, list[float]],
    correlation_matrix: dict[str, dict[str, float]],
    n_simulations: int = 3000,
    risk_free_rate: float = 0.1075,
    min_weight: float = 0.02,
    max_weight: float = 0.50,
    seed: int = 42,
) -> list[dict]:
    """
    Simula N portfólios aleatórios e retorna seus resultados para traçar
    a fronteira eficiente.

    Args:
        tickers (list[str]): Lista de tickers incluídos.
        return_series (dict[str, list[float]]): Retornos mensais por ticker.
        correlation_matrix (dict): Matriz de correlação pré-calculada.
        n_simulations (int): Número de portfólios simulados. Default: 3000.
        risk_free_rate (float): Taxa livre de risco anual.
        min_weight (float): Peso mínimo por ativo. Default: 2%.
        max_weight (float): Peso máximo por ativo. Default: 50%.
        seed (int): Semente base para reprodutibilidade.

    Returns:
        list[dict]: Lista de portfólios simulados, cada um com:
            'weights', 'return', 'volatility', 'sharpe'.
    """
    n = len(tickers)

    # Pré-calcular retornos e volatilidades esperadas
    exp_returns   = {t: calculate_expected_return(return_series.get(t, [])) for t in tickers}
    annual_vols   = {t: calculate_annual_volatility(return_series.get(t, [])) for t in tickers}

    portfolios = []
    random.seed(seed)

    for i in range(n_simulations):
        raw = _random_weights(n, seed=None, min_weight=min_weight, max_weight=max_weight)
        weights = dict(zip(tickers, raw))

        port_ret = calculate_portfolio_return(weights, exp_returns)
        port_vol = calculate_portfolio_vol(weights, annual_vols, correlation_matrix)
        sharpe   = calculate_sharpe(port_ret, port_vol, risk_free_rate)

        portfolios.append({
            "weights":    {t: round(w, 4) for t, w in weights.items()},
            "return":     round(port_ret, 6),
            "volatility": round(port_vol, 6),
            "sharpe":     round(sharpe, 4),
        })

    return portfolios


# ---------------------------------------------------------------------------
# Otimizações: Max Sharpe e Min Volatility
# ---------------------------------------------------------------------------

def find_max_sharpe(portfolios: list[dict]) -> dict:
    """
    Encontra o portfólio com maior Sharpe Ratio entre os simulados.

    Args:
        portfolios (list[dict]): Lista de portfólios de simulate_portfolio_frontier.

    Returns:
        dict: Portfólio de Max Sharpe com chave 'strategy' = 'max_sharpe'.
    """
    if not portfolios:
        return {}
    best = max(portfolios, key=lambda p: p["sharpe"])
    return {**best, "strategy": "max_sharpe"}


def find_min_volatility(portfolios: list[dict]) -> dict:
    """
    Encontra o portfólio com menor volatilidade entre os simulados.

    Args:
        portfolios (list[dict]): Lista de portfólios de simulate_portfolio_frontier.

    Returns:
        dict: Portfólio de Min Volatility com chave 'strategy' = 'min_volatility'.
    """
    if not portfolios:
        return {}
    best = min(portfolios, key=lambda p: p["volatility"])
    return {**best, "strategy": "min_volatility"}


def find_equal_weight(
    tickers: list[str],
    return_series: dict[str, list[float]],
    correlation_matrix: dict[str, dict[str, float]],
    risk_free_rate: float = 0.1075,
) -> dict:
    """
    Retorna o portfólio igualmente ponderado (naive baseline).

    Args:
        tickers (list[str]): Lista de tickers.
        return_series (dict): Retornos mensais por ticker.
        correlation_matrix (dict): Matriz de correlação.
        risk_free_rate (float): Selic anual.

    Returns:
        dict: Portfólio equally weighted com 'strategy' = 'equal_weight'.
    """
    n = len(tickers)
    w = 1.0 / n if n > 0 else 0.0
    weights = {t: round(w, 4) for t in tickers}

    exp_returns = {t: calculate_expected_return(return_series.get(t, [])) for t in tickers}
    annual_vols = {t: calculate_annual_volatility(return_series.get(t, [])) for t in tickers}

    port_ret = calculate_portfolio_return(weights, exp_returns)
    port_vol = calculate_portfolio_vol(weights, annual_vols, correlation_matrix)
    sharpe   = calculate_sharpe(port_ret, port_vol, risk_free_rate)

    return {
        "weights":    weights,
        "return":     round(port_ret, 6),
        "volatility": round(port_vol, 6),
        "sharpe":     round(sharpe, 4),
        "strategy":   "equal_weight",
    }


# ---------------------------------------------------------------------------
# Resumo comparativo das estratégias
# ---------------------------------------------------------------------------

def compare_strategies(
    tickers: list[str],
    return_series: dict[str, list[float]],
    correlation_matrix: dict[str, dict[str, float]],
    n_simulations: int = 3000,
    risk_free_rate: float = 0.1075,
    min_weight: float = 0.02,
    max_weight: float = 0.50,
    seed: int = 42,
) -> dict:
    """
    Roda a simulação Monte Carlo e retorna todas as estratégias comparadas.

    Args:
        tickers (list[str]): Tickers do universo de ativos.
        return_series (dict): Retornos mensais por ticker.
        correlation_matrix (dict): Matriz de correlação.
        n_simulations (int): Portfólios simulados.
        risk_free_rate (float): Selic anual.
        min_weight (float): Peso mínimo por ativo.
        max_weight (float): Peso máximo por ativo.
        seed (int): Semente.

    Returns:
        dict: Resultado completo com:
            'frontier': lista de todos os portfólios,
            'max_sharpe': melhor Sharpe,
            'min_volatility': menor volatilidade,
            'equal_weight': baseling igualmente ponderado.
    """
    frontier = simulate_portfolio_frontier(
        tickers, return_series, correlation_matrix,
        n_simulations, risk_free_rate, min_weight, max_weight, seed,
    )

    return {
        "frontier":       frontier,
        "max_sharpe":     find_max_sharpe(frontier),
        "min_volatility": find_min_volatility(frontier),
        "equal_weight":   find_equal_weight(
            tickers, return_series, correlation_matrix, risk_free_rate
        ),
        "n_simulations":  len(frontier),
    }


def format_strategy_report(result: dict) -> str:
    """
    Formata um relatório textual comparando as estratégias de Markowitz.

    Args:
        result (dict): Resultado de compare_strategies.

    Returns:
        str: Relatório formatado em ASCII.
    """
    lines = [
        "=" * 60,
        "  ALPHACOTA — MARKOWITZ: COMPARAÇÃO DE ESTRATÉGIAS",
        "=" * 60,
    ]

    for key, label in [
        ("max_sharpe",     "Max Sharpe Ratio"),
        ("min_volatility", "Min Volatility"),
        ("equal_weight",   "Equally Weighted (baseline)"),
    ]:
        p = result.get(key, {})
        if not p:
            continue
        lines += [
            f"\n  📊 {label}",
            f"     Retorno  : {p.get('return', 0)*100:.2f}% a.a.",
            f"     Risco    : {p.get('volatility', 0)*100:.2f}% a.a.",
            f"     Sharpe   : {p.get('sharpe', 0):.3f}",
            "     Pesos    :"
        ]
        for ticker, w in sorted(p.get("weights", {}).items(), key=lambda x: -x[1]):
            lines.append(f"       {ticker:<10} {w*100:>6.2f}%")

    lines += [
        "",
        f"  Simulações : {result.get('n_simulations', 0):,}",
        "=" * 60,
    ]
    return "\n".join(lines)
