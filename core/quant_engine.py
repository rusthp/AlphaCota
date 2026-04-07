# core/quant_engine.py
import math
from core.logger import logger


def normalize_positive(value: float, min_val: float, max_val: float) -> float:
    """
    Normaliza um indicador financeiro (onde maior é melhor) para uma escala de 0.0 a 1.0.

    Args:
        value (float): O valor atual do indicador (ex: ROE, ROA).
        min_val (float): O valor mínimo aceitável.
        max_val (float): O valor máximo esperado.

    Returns:
        float: Valor normalizado entre 0.0 e 1.0.
    """
    if math.isnan(value) or math.isinf(value):
        logger.warning(f"Valor inválido em normalize_positive: {value}")
        return 0.0

    if max_val <= min_val:
        return 0.0
    return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))


def normalize_inverse(value: float, min_val: float, max_val: float) -> float:
    """
    Normaliza um indicador financeiro (onde menor é melhor) para uma escala de 0.0 a 1.0.

    Args:
        value (float): O valor atual do indicador (ex: P/L, Dívida).
        min_val (float): O valor mínimo esperado.
        max_val (float): O valor máximo aceitável.

    Returns:
        float: Valor normalizado entre 0.0 e 1.0 invertido.
    """
    return 1.0 - normalize_positive(value, min_val, max_val)


def calculate_quality_score(data: dict[str, float]) -> float:
    """
    Calcula um score de qualidade (0 a 100) baseado em valuation, rentabilidade,
    crescimento e solidez financeira.

    Args:
        data (dict[str, float]): Dicionário com os indicadores fundamentalistas.

    Returns:
        float: Score de qualidade da empresa (0.0 a 100.0).
    """
    # Valuation (25%) - Menor é melhor
    score_pl = normalize_inverse(data.get("pl", 15.0), 5.0, 30.0)
    score_pvp = normalize_inverse(data.get("pvp", 2.0), 0.5, 5.0)
    valuation_score = (score_pl + score_pvp) / 2.0

    # Rentabilidade (30%) - Maior é melhor
    score_roe = normalize_positive(data.get("roe", 10.0), 5.0, 30.0)
    score_roa = normalize_positive(data.get("roa", 5.0), 2.0, 20.0)
    profitability_score = (score_roe + score_roa) / 2.0

    # Crescimento (20%) - Maior é melhor
    score_rev_growth = normalize_positive(data.get("revenue_growth", 5.0), 0.0, 20.0)
    score_earn_growth = normalize_positive(data.get("earnings_growth", 5.0), 0.0, 25.0)
    growth_score = (score_rev_growth + score_earn_growth) / 2.0

    # Solidez (25%) - Dívida (menor melhor), Liquidez (maior melhor)
    score_debt = normalize_inverse(data.get("debt_to_equity", 1.0), 0.0, 2.0)
    score_liquidity = normalize_positive(data.get("current_ratio", 1.5), 1.0, 3.0)
    stability_score = (score_debt + score_liquidity) / 2.0

    total_score = 0.25 * valuation_score + 0.30 * profitability_score + 0.20 * growth_score + 0.25 * stability_score

    return round(total_score * 100, 2)


def calculate_altman_z(data: dict[str, float]) -> float:
    """
    Calcula o Altman Z-Score Clássico para estimar o risco de falência.

    Args:
        data (dict[str, float]): Dicionário com os dados do balanço e DRE.

    Returns:
        float: O valor do Altman Z-Score. Retorna 0.0 se os dados forem inválidos.
    """
    total_assets = data.get("total_assets", 0.0)
    total_liabilities = data.get("total_liabilities", 0.0)

    # Proteção contra divisão por zero (empresas sem ativos ou passivos reportados)
    if total_assets <= 0 or total_liabilities <= 0:
        return 0.0

    a = data.get("working_capital", 0.0) / total_assets
    b = data.get("retained_earnings", 0.0) / total_assets
    c = data.get("ebit", 0.0) / total_assets
    d = data.get("market_value_equity", 0.0) / total_liabilities
    e = data.get("revenue", 0.0) / total_assets

    # Prevenir que campos NaN (gerados por data sources ruins) corrompam o Z-Score
    for val in [a, b, c, d, e]:
        if math.isnan(val) or math.isinf(val):
            logger.warning(f"Campo NaN/Inf detectado no cálculo de Altman Z: {data}")
            return 0.0

    z = (1.2 * a) + (1.4 * b) + (3.3 * c) + (0.6 * d) + (1.0 * e)

    return round(float(z), 3)


def classify_bankruptcy_risk(z_score: float) -> str:
    """
    Classifica o risco de falência com base no valor do Altman Z-Score.

    Args:
        z_score (float): O valor calculado do Altman Z-Score.

    Returns:
        str: Classificação textual do risco ('Zona Segura', 'Zona Cinzenta', 'Alto Risco de Falência').
    """
    if z_score > 2.99:
        return "Zona Segura"
    elif z_score > 1.81:
        return "Zona Cinzenta"
    else:
        return "Alto Risco de Falência"


def calculate_moving_average(prices: list[float], window: int) -> float:
    """
    Calcula a média móvel simples de uma lista de preços.

    Args:
        prices (list[float]): Lista de preços históricos mensais.
        window (int): Tamanho da janela da média móvel.

    Returns:
        float: Valor da média móvel.

    Raises:
        ValueError: Se a quantidade de preços for menor que a janela solicitada.
    """
    if len(prices) < window:
        raise ValueError(f"Dados insuficientes para média móvel de {window} períodos.")

    return sum(prices[-window:]) / window


def calculate_momentum_score(prices: list[float]) -> float:
    """
    Calcula o score de momentum (0 a 100) baseado em tendências e inclinações de médias móveis.

    Args:
        prices (list[float]): Lista de preços históricos mensais (mínimo de 12 meses,
                              sendo o último item o preço atual).

    Returns:
        float: Score normalizado de momentum (0.0 a 100.0).

    Raises:
        ValueError: Se a lista contiver menos de 12 meses de histórico.
    """
    if len(prices) < 12:
        raise ValueError("Necessário pelo menos 12 meses de preços históricos.")

    current_price = prices[-1]

    ma_6 = calculate_moving_average(prices, 6)
    ma_12 = calculate_moving_average(prices, 12)

    if ma_6 == 0.0 or ma_12 == 0.0:
        return 0.0

    trend_6 = (current_price - ma_6) / ma_6
    trend_12 = (current_price - ma_12) / ma_12

    previous_ma6 = sum(prices[-7:-1]) / 6
    slope_6 = (ma_6 - previous_ma6) / previous_ma6 if previous_ma6 != 0.0 else 0.0

    raw_score = (0.4 * trend_6) + (0.4 * trend_12) + (0.2 * slope_6)

    # Normalização sigmoidal simples
    normalized = 1.0 / (1.0 + math.exp(-10.0 * raw_score))

    return round(normalized * 100.0, 2)


def calculate_final_score(fundamental_score: float, momentum_score: float) -> float:
    """
    Calcula o score final combinando a análise fundamentalista e o momentum técnico.
    Aplica uma penalidade caso o ativo esteja em tendência de colapso.

    Args:
        fundamental_score (float): Score de qualidade fundamentalista (0 a 100).
        momentum_score (float): Score técnico de momentum (0 a 100).

    Returns:
        float: Score final ajustado.
    """
    # Proteção contra "faca caindo": reduz o score total em 20% se o momentum for péssimo
    penalty = 0.8 if momentum_score < 30.0 else 1.0

    final_score = (0.8 * fundamental_score) + (0.2 * momentum_score)

    return round(final_score * penalty, 2)


def calculate_fii_score(data: dict[str, float]) -> dict[str, float]:
    """
    Calcula o score de qualidade de um FII (0-100) usando métricas específicas de FIIs.

    Quatro dimensões, cada uma valendo até 25 pontos:
      - Fundamentos : P/VP (15pts) + endividamento (10pts)
      - Rendimento  : DY (15pts) + consistência de dividendos (10pts)
      - Risco       : vacância física (25pts)
      - Liquidez    : liquidez diária negociada (25pts)

    Args:
        data (dict): Chaves relevantes:
            pvp, debt_ratio, dividend_yield, dividend_consistency,
            vacancy_rate (ou vacancia), daily_liquidity (ou liquidez_diaria)

    Returns:
        dict com fundamentos, rendimento, risco, liquidez (cada 0–25) e total (0–100).
    """
    # --- Fundamentos (max 25): P/VP (15pts) + endividamento (10pts) ---
    pvp = float(data.get("pvp", 1.0))
    debt_ratio = float(data.get("debt_ratio", 0.3))
    score_pvp = normalize_inverse(pvp, 0.5, 1.5) * 15.0
    score_debt = normalize_inverse(debt_ratio, 0.0, 0.8) * 10.0
    fundamentos = round(min(25.0, score_pvp + score_debt), 2)

    # --- Rendimento (max 25): DY (15pts) + consistência (10pts) ---
    dy = float(data.get("dividend_yield", 0.08))
    consistency = min(1.0, max(0.0, float(data.get("dividend_consistency", 0.5))))
    score_dy = normalize_positive(dy, 0.04, 0.13) * 15.0
    score_consistency = consistency * 10.0
    rendimento = round(min(25.0, score_dy + score_consistency), 2)

    # --- Risco (max 25): vacância ---
    vacancy = float(data.get("vacancy_rate", data.get("vacancia", 0.1)))
    score_vacancy = normalize_inverse(vacancy, 0.0, 0.30) * 25.0
    risco = round(min(25.0, score_vacancy), 2)

    # --- Liquidez (max 25): liquidez diária ---
    liquidity = float(data.get("daily_liquidity", data.get("liquidez_diaria", 500_000)))
    score_liquidity = normalize_positive(liquidity, 100_000, 5_000_000) * 25.0
    liquidez = round(min(25.0, score_liquidity), 2)

    total = round(fundamentos + rendimento + risco + liquidez, 2)

    return {
        "fundamentos": fundamentos,
        "rendimento": rendimento,
        "risco": risco,
        "liquidez": liquidez,
        "total": total,
    }


def evaluate_company(
    ticker: str, data: dict[str, float], historical_prices: list[float] = None
) -> dict[str, float | str]:
    """
    Agrega as análises quantitativas de uma empresa retornando seu score fundamentalista,
    score de momentum e análise de risco de falência.

    Args:
        ticker (str): O código de negociação do ativo (ex: 'WEGE3').
        data (dict[str, float]): Dicionário contendo todos os indicadores financeiros.
        historical_prices (list[float], optional): Lista de preços dos últimos 12 meses. Defaults to None.

    Returns:
        dict[str, float | str]: Resultado da avaliação contendo o ticker, scores e risco.
    """
    quality_score = calculate_quality_score(data)
    z_score = calculate_altman_z(data)
    risk_classification = classify_bankruptcy_risk(z_score)

    momentum_score = 0.0
    if historical_prices and len(historical_prices) >= 12:
        momentum_score = calculate_momentum_score(historical_prices)

    final_score = calculate_final_score(quality_score, momentum_score) if momentum_score > 0 else quality_score

    return {
        "ticker": ticker,
        "quality_score": quality_score,
        "momentum_score": momentum_score,
        "final_score": final_score,
        "altman_z_score": z_score,
        "risk_classification": risk_classification,
    }
