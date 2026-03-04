"""
core/momentum_engine.py

Motor de Momentum para FIIs.

Calcula retorno acumulado em janelas de 1, 3, 6 e 12 meses,
gera ranking de momentum e classifica ativos por força de tendência.

Funções puras, sem dependências externas.
"""

import statistics
import math


# ---------------------------------------------------------------------------
# Cálculo de retorno acumulado
# ---------------------------------------------------------------------------

def cumulative_return(monthly_returns: list[float], n_months: int) -> float:
    """
    Retorno acumulado dos últimos N meses.

    Args:
        monthly_returns: Série de retornos mensais (ex: [0.01, -0.02, 0.015]).
        n_months: Janela em meses.

    Returns:
        float: Retorno acumulado decimal (ex: 0.12 = 12%).
             Retorna 0.0 se dados insuficientes.
    """
    if len(monthly_returns) < n_months:
        window = monthly_returns  # usa o que tem
    else:
        window = monthly_returns[-n_months:]

    if not window:
        return 0.0

    accumulated = 1.0
    for r in window:
        accumulated *= (1 + r)
    return round(accumulated - 1.0, 6)


def annualized_return(monthly_returns: list[float]) -> float:
    """
    Retorno anualizado a partir da série completa de retornos mensais.

    Usa: (1 + r_media_mensal)^12 - 1

    Returns:
        float: Retorno anualizado decimal.
    """
    if not monthly_returns:
        return 0.0
    avg_monthly = sum(monthly_returns) / len(monthly_returns)
    return round((1 + avg_monthly) ** 12 - 1, 6)


def momentum_score(
    monthly_returns: list[float],
    weights: dict[str, float] | None = None,
) -> dict:
    """
    Calcula o score de momentum composto de um ativo.

    Combina retornos ponderados em janelas de 1m, 3m, 6m e 12m.
    Default: maior peso para 6m e 12m (tendência mais robusta).

    Args:
        monthly_returns: Série de retornos mensais.
        weights: Pesos por janela {'1m': w1, '3m': w3, '6m': w6, '12m': w12}.

    Returns:
        dict com retorno por janela, score composto e classificação.
    """
    w = weights or {"1m": 0.10, "3m": 0.20, "6m": 0.30, "12m": 0.40}

    r1m  = cumulative_return(monthly_returns, 1)
    r3m  = cumulative_return(monthly_returns, 3)
    r6m  = cumulative_return(monthly_returns, 6)
    r12m = cumulative_return(monthly_returns, 12)

    total_w = sum(w.values())
    score = (
        r1m  * w.get("1m",  0) +
        r3m  * w.get("3m",  0) +
        r6m  * w.get("6m",  0) +
        r12m * w.get("12m", 0)
    ) / total_w if total_w > 0 else 0.0

    if score >= 0.12:
        classification = "🔥 Forte Alta"
    elif score >= 0.06:
        classification = "📈 Alta Moderada"
    elif score >= 0.0:
        classification = "➡️ Neutro"
    elif score >= -0.06:
        classification = "📉 Queda Moderada"
    else:
        classification = "❄️ Forte Queda"

    return {
        "retorno_1m":    round(r1m * 100, 2),
        "retorno_3m":    round(r3m * 100, 2),
        "retorno_6m":    round(r6m * 100, 2),
        "retorno_12m":   round(r12m * 100, 2),
        "score":         round(score * 100, 4),
        "classificacao": classification,
    }


# ---------------------------------------------------------------------------
# Ranking de momentum
# ---------------------------------------------------------------------------

def rank_by_momentum(
    return_series: dict[str, list[float]],
    weights: dict[str, float] | None = None,
) -> list[dict]:
    """
    Gera ranking de todos os ativos por score de momentum.

    Args:
        return_series (dict): Mapa ticker → lista de retornos mensais.
        weights (dict): Pesos por janela temporal.

    Returns:
        list[dict]: Lista ordenada (maior momentum primeiro) com:
            ticker, score, retorno_1m, retorno_3m, retorno_6m, retorno_12m, classificacao.
    """
    results = []
    for ticker, returns in return_series.items():
        ms = momentum_score(returns, weights)
        results.append({
            "ticker":        ticker,
            "score":         ms["score"],
            "retorno_1m_%":  ms["retorno_1m"],
            "retorno_3m_%":  ms["retorno_3m"],
            "retorno_6m_%":  ms["retorno_6m"],
            "retorno_12m_%": ms["retorno_12m"],
            "classificacao": ms["classificacao"],
        })

    return sorted(results, key=lambda x: x["score"], reverse=True)


def top_momentum(
    return_series: dict[str, list[float]],
    n: int = 5,
) -> list[dict]:
    """
    Retorna os N melhores ativos por momentum.

    Args:
        return_series: Mapa ticker → retornos.
        n: Quantos retornar.

    Returns:
        list[dict]: Top N com maior score de momentum.
    """
    ranking = rank_by_momentum(return_series)
    return ranking[:n]


def filter_positive_momentum(
    return_series: dict[str, list[float]],
    min_score: float = 0.0,
) -> list[str]:
    """
    Filtra ativos com momentum positivo acima de um limiar.

    Args:
        return_series: Mapa ticker → retornos.
        min_score: Score mínimo em % (ex: 0.0 = qualquer positivo, 5.0 = acima de 5%).

    Returns:
        list[str]: Tickers com momentum positivo.
    """
    ranking = rank_by_momentum(return_series)
    return [r["ticker"] for r in ranking if r["score"] >= min_score]


def momentum_vs_benchmark(
    ticker_returns: list[float],
    benchmark_returns: list[float],
    n_months: int = 12,
) -> dict:
    """
    Compara o momentum de um ativo contra um benchmark no mesmo período.

    Args:
        ticker_returns: Retornos mensais do ativo.
        benchmark_returns: Retornos mensais do benchmark (ex: IFIX).
        n_months: Janela de comparação.

    Returns:
        dict com retorno do ativo, benchmark e alpha de momentum.
    """
    r_ticker    = cumulative_return(ticker_returns, n_months)
    r_benchmark = cumulative_return(benchmark_returns, n_months)
    alpha       = round(r_ticker - r_benchmark, 6)

    sinal = "+" if alpha >= 0 else ""
    return {
        "retorno_ativo_%":     round(r_ticker * 100, 2),
        "retorno_benchmark_%": round(r_benchmark * 100, 2),
        "alpha_%":             round(alpha * 100, 2),
        "result":              f"Superou benchmark em {sinal}{alpha*100:.2f}%" if alpha >= 0
                               else f"Abaixo do benchmark em {alpha*100:.2f}%",
    }
