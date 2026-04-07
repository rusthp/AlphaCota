"""
core/correlation_engine.py

Calcula e analisa correlações entre FIIs para evitar concentração
em ativos altamente correlacionados, melhorando a diversificação real
da carteira além da diversificação por classe.

Funções puras, sem classes, sem frameworks externos além de math/statistics.
"""

import math
import statistics
from typing import Optional

# ---------------------------------------------------------------------------
# Correlação
# ---------------------------------------------------------------------------


def calculate_pearson(a: list[float], b: list[float]) -> float:
    """
    Calcula o coeficiente de correlação de Pearson entre duas séries.

    Args:
        a (list[float]): Primeira série de retornos mensais.
        b (list[float]): Segunda série de retornos mensais.

    Returns:
        float: Correlação entre -1.0 e 1.0.
               0.0 se séries insuficientes ou desvio padrão zero.
    """
    n = min(len(a), len(b))
    if n < 2:
        return 0.0

    a, b = a[:n], b[:n]
    mean_a = sum(a) / n
    mean_b = sum(b) / n

    num = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n))
    den_a = math.sqrt(sum((a[i] - mean_a) ** 2 for i in range(n)))
    den_b = math.sqrt(sum((b[i] - mean_b) ** 2 for i in range(n)))

    if den_a == 0 or den_b == 0:
        return 0.0

    return round(num / (den_a * den_b), 4)


def build_correlation_matrix(
    tickers: list[str],
    return_series: dict[str, list[float]],
) -> dict[str, dict[str, float]]:
    """
    Constrói a matriz de correlação entre todos os pares de tickers.

    Args:
        tickers (list[str]): Lista de tickers a incluir.
        return_series (dict[str, list[float]]): Dicionário com série de retornos
            mensais por ticker.

    Returns:
        dict[str, dict[str, float]]: Matriz simétrica de correlações.
            Exemplo: matrix["MXRF11"]["HGLG11"] = 0.72
    """
    matrix: dict[str, dict[str, float]] = {}

    for t1 in tickers:
        matrix[t1] = {}
        for t2 in tickers:
            if t1 == t2:
                matrix[t1][t2] = 1.0
            elif t2 in matrix and t1 in matrix[t2]:
                # Reutilizar simétrico já calculado
                matrix[t1][t2] = matrix[t2][t1]
            else:
                s1 = return_series.get(t1, [])
                s2 = return_series.get(t2, [])
                matrix[t1][t2] = calculate_pearson(s1, s2)

    return matrix


def classify_correlation(corr: float) -> str:
    """
    Classifica a força de uma correlação em linguagem natural.

    Args:
        corr (float): Valor de correlação entre -1.0 e 1.0.

    Returns:
        str: Classificação textual da correlação.
    """
    abs_c = abs(corr)
    if abs_c >= 0.85:
        return "Muito Alta"
    elif abs_c >= 0.65:
        return "Alta"
    elif abs_c >= 0.40:
        return "Moderada"
    elif abs_c >= 0.20:
        return "Baixa"
    else:
        return "Desprezível"


def find_high_correlation_pairs(
    matrix: dict[str, dict[str, float]],
    threshold: float = 0.75,
) -> list[dict]:
    """
    Identifica pares de ativos com correlação acima do limiar.

    Args:
        matrix (dict): Matriz de correlação gerada por build_correlation_matrix.
        threshold (float): Limiar mínimo de correlação (em valor absoluto). Default: 0.75.

    Returns:
        list[dict]: Lista de pares com correlação alta, ordenada decrescentemente.
            Cada item contém: 'ticker_a', 'ticker_b', 'correlation', 'classification'.
    """
    pairs = []
    tickers = list(matrix.keys())

    for i, t1 in enumerate(tickers):
        for t2 in tickers[i + 1 :]:
            corr = matrix[t1].get(t2, 0.0)
            if abs(corr) >= threshold:
                pairs.append(
                    {
                        "ticker_a": t1,
                        "ticker_b": t2,
                        "correlation": corr,
                        "classification": classify_correlation(corr),
                    }
                )

    return sorted(pairs, key=lambda x: abs(x["correlation"]), reverse=True)


# ---------------------------------------------------------------------------
# Concentração por setor
# ---------------------------------------------------------------------------


def calculate_sector_concentration(
    portfolio: list[dict],
    sector_map: dict[str, str],
) -> dict[str, float]:
    """
    Calcula a concentração percentual por setor da carteira.

    Args:
        portfolio (list[dict]): Lista de ativos com 'ticker', 'quantidade' e 'preco_atual'.
        sector_map (dict[str, str]): Mapeamento de ticker → setor.
            Exemplo: {"MXRF11": "Papel (CRI)", "HGLG11": "Logística"}

    Returns:
        dict[str, float]: Percentual de capital alocado por setor (0.0 a 1.0).
    """
    valor_por_setor: dict[str, float] = {}
    valor_total = 0.0

    for ativo in portfolio:
        ticker = ativo.get("ticker", "")
        valor = ativo.get("quantidade", 0) * ativo.get("preco_atual", 0.0)
        setor = sector_map.get(ticker, "Outros")

        valor_por_setor[setor] = valor_por_setor.get(setor, 0.0) + valor
        valor_total += valor

    if valor_total <= 0:
        return {}

    return {setor: round(valor / valor_total, 4) for setor, valor in valor_por_setor.items()}


def calculate_herfindahl_index(concentrations: dict[str, float]) -> float:
    """
    Calcula o Índice de Herfindahl-Hirschman (HHI) de concentração.

    HHI é a soma dos quadrados das participações de mercado.
    Valores próximos de 1.0 indicam alta concentração (monopólio).
    Valores abaixo de 0.15 indicam portfólio bem diversificado.

    Args:
        concentrations (dict[str, float]): Participação por setor (somam 1.0).

    Returns:
        float: HHI entre 0.0 e 1.0.
    """
    return round(sum(c**2 for c in concentrations.values()), 4)


def classify_concentration_risk(hhi: float) -> str:
    """
    Classifica o risco de concentração com base no HHI.

    Args:
        hhi (float): Índice de Herfindahl-Hirschman.

    Returns:
        str: Classificação do risco de concentração.
    """
    if hhi < 0.15:
        return "Diversificado"
    elif hhi < 0.25:
        return "Moderado"
    elif hhi < 0.40:
        return "Concentrado"
    else:
        return "Altamente Concentrado"


# ---------------------------------------------------------------------------
# Risco sistêmico
# ---------------------------------------------------------------------------


def calculate_portfolio_volatility(
    weights: dict[str, float],
    return_series: dict[str, list[float]],
    correlation_matrix: dict[str, dict[str, float]],
) -> float:
    """
    Calcula a volatilidade anualizada do portfólio considerando correlações.

    Usa a fórmula matricial: σ_p = sqrt(Σ_i Σ_j w_i * w_j * σ_i * σ_j * ρ_ij)

    Args:
        weights (dict[str, float]): Pesos dos ativos na carteira.
        return_series (dict[str, list[float]]): Retornos mensais por ticker.
        correlation_matrix (dict): Matriz de correlação.

    Returns:
        float: Volatilidade anualizada do portfólio (0.0 a N).
    """
    tickers = list(weights.keys())

    # Volatilidades mensais individuais
    vols: dict[str, float] = {}
    for t in tickers:
        rets = return_series.get(t, [])
        if len(rets) >= 2:
            vols[t] = statistics.stdev(rets)
        else:
            vols[t] = 0.0

    # Variância do portfólio: Σ_i Σ_j w_i * w_j * σ_i * σ_j * ρ_ij
    port_variance = 0.0
    for t1 in tickers:
        for t2 in tickers:
            w1 = weights.get(t1, 0.0)
            w2 = weights.get(t2, 0.0)
            s1 = vols.get(t1, 0.0)
            s2 = vols.get(t2, 0.0)
            corr = correlation_matrix.get(t1, {}).get(t2, 0.0)
            port_variance += w1 * w2 * s1 * s2 * corr

    port_vol_monthly = math.sqrt(max(port_variance, 0.0))
    return round(port_vol_monthly * math.sqrt(12), 6)  # Anualizar


def calculate_diversification_ratio(
    weights: dict[str, float],
    return_series: dict[str, list[float]],
    correlation_matrix: dict[str, dict[str, float]],
) -> float:
    """
    Calcula o Diversification Ratio (DR) da carteira.

    DR = (média ponderada das volatilidades individuais) / volatilidade do portfólio
    DR > 1 significa que o portfólio é mais estável que a soma das partes.
    DR = 1 significa correlação perfeita (sem ganho de diversificação).

    Args:
        weights (dict[str, float]): Pesos dos ativos.
        return_series (dict[str, list[float]]): Retornos mensais por ticker.
        correlation_matrix (dict): Matriz de correlação.

    Returns:
        float: Diversification Ratio. 0.0 se denominador for zero.
    """
    # Volatilidades individuais anualizadas
    weighted_vol = 0.0
    for t, w in weights.items():
        rets = return_series.get(t, [])
        if len(rets) >= 2:
            vol_annual = statistics.stdev(rets) * math.sqrt(12)
        else:
            vol_annual = 0.0
        weighted_vol += w * vol_annual

    port_vol = calculate_portfolio_volatility(weights, return_series, correlation_matrix)

    if port_vol <= 0:
        return 0.0

    return round(weighted_vol / port_vol, 4)


def analyse_portfolio_risk(
    portfolio: list[dict],
    return_series: dict[str, list[float]],
    sector_map: dict[str, str],
    high_corr_threshold: float = 0.75,
) -> dict:
    """
    Análise completa de risco sistêmico e concentração de uma carteira.

    Agrega: correlações, concentração setorial, HHI, volatilidade do portfólio
    e Diversification Ratio em um único relatório estruturado.

    Args:
        portfolio (list[dict]): Ativos com 'ticker', 'quantidade', 'preco_atual'.
        return_series (dict[str, list[float]]): Retornos mensais por ticker.
        sector_map (dict[str, str]): Mapeamento ticker → setor.
        high_corr_threshold (float): Limiar para alertas de alta correlação.

    Returns:
        dict: Relatório completo com matriz de correlação, pares problemáticos,
              concentração setorial, HHI e métricas de volatilidade.
    """
    tickers = [a["ticker"] for a in portfolio]
    valor_total = sum(a["quantidade"] * a.get("preco_atual", 0.0) for a in portfolio)

    # Pesos da carteira
    weights: dict[str, float] = {}
    for a in portfolio:
        valor = a["quantidade"] * a.get("preco_atual", 0.0)
        weights[a["ticker"]] = (valor / valor_total) if valor_total > 0 else 0.0

    # Matriz de correlação
    corr_matrix = build_correlation_matrix(tickers, return_series)
    high_corr = find_high_correlation_pairs(corr_matrix, high_corr_threshold)

    # Concentração setorial
    sector_conc = calculate_sector_concentration(portfolio, sector_map)
    hhi = calculate_herfindahl_index(sector_conc)
    conc_risk = classify_concentration_risk(hhi)

    # Volatilidade e diversificação
    port_vol = calculate_portfolio_volatility(weights, return_series, corr_matrix)
    div_ratio = calculate_diversification_ratio(weights, return_series, corr_matrix)

    return {
        "correlation_matrix": corr_matrix,
        "high_correlation_pairs": high_corr,
        "sector_concentration": sector_conc,
        "herfindahl_index": hhi,
        "concentration_risk": conc_risk,
        "portfolio_annual_volatility": port_vol,
        "diversification_ratio": div_ratio,
        "warnings": _generate_warnings(high_corr, hhi, div_ratio),
    }


def _generate_warnings(
    high_corr_pairs: list[dict],
    hhi: float,
    div_ratio: float,
) -> list[str]:
    """
    Gera alertas legíveis sobre riscos de concentração e correlação.

    Args:
        high_corr_pairs (list[dict]): Pares com alta correlação.
        hhi (float): Índice de Herfindahl.
        div_ratio (float): Diversification Ratio.

    Returns:
        list[str]: Lista de alertas em português.
    """
    warnings = []

    for pair in high_corr_pairs[:3]:  # Top 3 mais correlacionados
        warnings.append(
            f"⚠️ {pair['ticker_a']} e {pair['ticker_b']} têm correlação "
            f"{pair['correlation']:.2f} ({pair['classification']}). "
            "Considere reduzir a exposição combinada."
        )

    if hhi >= 0.40:
        warnings.append(
            f"🔴 Concentração setorial muito alta (HHI={hhi:.2f}). " "Distribua melhor entre setores diferentes."
        )
    elif hhi >= 0.25:
        warnings.append(f"🟡 Concentração setorial moderada (HHI={hhi:.2f}). " "Avalie diversificação entre setores.")

    if div_ratio < 1.1:
        warnings.append(
            f"⚠️ Diversification Ratio baixo ({div_ratio:.2f}). "
            "Os ativos estão se movendo muito juntos — pouca proteção real."
        )

    return warnings


# ---------------------------------------------------------------------------
# Rebalanceamento ciente de correlação
# ---------------------------------------------------------------------------


def suggest_rebalance_with_correlation(
    portfolio: list[dict],
    target_weights: dict[str, float],
    return_series: dict[str, list[float]],
    correlation_matrix: dict[str, dict[str, float]],
    high_corr_threshold: float = 0.80,
) -> dict:
    """
    Sugere ajustes de rebalanceamento priorizando redução de correlação.

    Além de corrigir desvios de peso, penaliza pares de ativos altamente
    correlacionados para evitar que o rebalanceamento reforce concentração.

    Args:
        portfolio (list[dict]): Ativos com 'ticker', 'quantidade', 'preco_atual'.
        target_weights (dict[str, float]): Pesos alvo por ticker.
        return_series (dict[str, list[float]]): Retornos mensais por ticker.
        correlation_matrix (dict): Matriz de correlação pré-calculada.
        high_corr_threshold (float): Correlação acima deste nível é penalizada.

    Returns:
        dict: Sugestões de rebalanceamento com prioridade e justificativa.
    """
    valor_total = sum(a["quantidade"] * a.get("preco_atual", 0.0) for a in portfolio)
    current_weights: dict[str, float] = {}

    for a in portfolio:
        valor = a["quantidade"] * a.get("preco_atual", 0.0)
        current_weights[a["ticker"]] = (valor / valor_total) if valor_total > 0 else 0.0

    high_corr_pairs = find_high_correlation_pairs(correlation_matrix, high_corr_threshold)
    # Tickers em pares problemáticos
    high_corr_tickers: set[str] = set()
    for pair in high_corr_pairs:
        high_corr_tickers.add(pair["ticker_a"])
        high_corr_tickers.add(pair["ticker_b"])

    suggestions = []
    for ticker, target_w in target_weights.items():
        current_w = current_weights.get(ticker, 0.0)
        drift = target_w - current_w

        # Penalidade: se o ativo está em par de alta correlação,
        # aumentar prioridade de redução
        corr_penalty = 0.0
        if ticker in high_corr_tickers and drift > 0:
            corr_penalty = 0.05  # Penalizar compras em ativos muito correlacionados

        priority_score = abs(drift) - corr_penalty

        action = "manter"
        if drift > 0.02:
            action = "comprar"
        elif drift < -0.02:
            action = "reduzir"

        suggestions.append(
            {
                "ticker": ticker,
                "current_weight": round(current_w, 4),
                "target_weight": round(target_w, 4),
                "drift": round(drift, 4),
                "action": action,
                "priority_score": round(priority_score, 4),
                "high_correlation_warning": ticker in high_corr_tickers,
            }
        )

    # Ordenar por prioridade: maiores desvios primeiro
    suggestions.sort(key=lambda x: abs(x["drift"]), reverse=True)

    return {
        "suggestions": suggestions,
        "high_correlation_pairs": high_corr_pairs,
        "total_drift": round(sum(abs(s["drift"]) for s in suggestions), 4),
    }
