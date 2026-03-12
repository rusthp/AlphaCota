"""
core/score_engine.py

Modelo matemático explícito do Alpha Score para FIIs.

Fórmula:
    score = (w_income × income_score) +
            (w_valuation × valuation_score) +
            (w_risk × risk_score) +
            (w_growth × growth_score)

Os pesos padrão podem ser sobrescritos via parâmetro, permitindo
backtest de diferentes configurações e otimização futura.
"""

import math
from core.logger import logger

# ---------------------------------------------------------------------------
# Pesos padrão — configuração do modelo base
# Devem somar 1.0.
# ---------------------------------------------------------------------------
DEFAULT_WEIGHTS: dict[str, float] = {
    "w_income": 0.40,      # Estabilidade e magnitude de dividendos (pilar FII mais crítico)
    "w_valuation": 0.25,   # P/VP e preço relativo ao valor intrínseco
    "w_risk": 0.20,        # Endividamento, concentração, estrutura de capital
    "w_growth": 0.15,      # Crescimento de receita e lucros recentes
}


def validate_weights(weights: dict[str, float]) -> None:
    """
    Valida que os pesos fornecidos são positivos e somam aproximadamente 1.0.

    Args:
        weights (dict[str, float]): Dicionário de pesos a validar.

    Raises:
        ValueError: Se pesos forem negativos ou a soma estiver fora de [0.99, 1.01].
    """
    required_keys = {"w_income", "w_valuation", "w_risk", "w_growth"}
    missing = required_keys - weights.keys()
    if missing:
        raise ValueError(f"Pesos ausentes: {missing}")

    for key, val in weights.items():
        if val < 0:
            raise ValueError(f"Peso '{key}' não pode ser negativo: {val}")

    total = sum(weights[k] for k in required_keys)
    if not (0.99 <= total <= 1.01):
        raise ValueError(
            f"Pesos devem somar ~1.0, mas somam {total:.4f}. "
            "Ajuste os pesos para manter a consistência do modelo."
        )


def calculate_income_score(
    dividend_yield: float,
    dividend_consistency: float,
) -> float:
    """
    Calcula o score de renda (income) de um FII.

    Args:
        dividend_yield (float): Dividend Yield anual (ex: 0.12 = 12%).
            Normalizado para escala 0-10: excelente ≥ 12%, péssimo ≤ 4%.
        dividend_consistency (float): Consistência histórica de pagamentos,
            nota de 0.0 a 10.0 (ex: 10 = pagou todos os meses nos últimos 24m).

    Returns:
        float: Score de income de 0.0 a 10.0.
    """
    if math.isnan(dividend_yield) or math.isinf(dividend_yield):
        logger.warning(f"dividend_yield inválido ({dividend_yield}), assumindo 0.0")
        dividend_yield = 0.0
    if math.isnan(dividend_consistency) or math.isinf(dividend_consistency):
        logger.warning(f"dividend_consistency inválido ({dividend_consistency}), assumindo 0.0")
        dividend_consistency = 0.0

    # Normalizar DY: 4% → 0, 12% → 10
    dy_score = max(0.0, min(10.0, (dividend_yield - 0.04) / (0.12 - 0.04) * 10.0))
    # Combinar com consistência (peso 60/40)
    return round(0.60 * dy_score + 0.40 * dividend_consistency, 4)


def calculate_valuation_score(pvp: float) -> float:
    """
    Calcula o score de valuation de um FII baseado no P/VP.

    P/VP = 1.0 é considerado justo. Abaixo de 1.0 é desconto.
    Acima de 1.5 começa a ser caro para FIIs.

    Args:
        pvp (float): Preço sobre Valor Patrimonial do FII.
            Normalizado: 0.7 → 10 (muito barato), 1.5 → 0 (caro).

    Returns:
        float: Score de valuation de 0.0 a 10.0.
    """
    if math.isnan(pvp) or math.isinf(pvp) or pvp <= 0:
        logger.warning(f"P/VP inválido ({pvp}), assumindo 1.0 (neutro)")
        pvp = 1.0

    # Inverso: quanto menor o P/VP (até um mínimo saudável de 0.7), maior o score
    score = max(0.0, min(10.0, (1.5 - pvp) / (1.5 - 0.7) * 10.0))
    return round(score, 4)


def calculate_risk_score(
    debt_ratio: float,
    vacancy_rate: float,
) -> float:
    """
    Calcula o score de risco de um FII.

    Args:
        debt_ratio (float): Relação Dívida/PL.
            Normalizado: 0.0 → 10, 1.0 → 0 (muito endividado).
        vacancy_rate (float): Taxa de vacância física do fundo (ex: 0.05 = 5%).
            Normalizado: 0.0 → 10, 0.30 → 0 (30% de vacância = alto risco).

    Returns:
        float: Score de risco de 0.0 a 10.0 (10 = baixo risco).
    """
    if math.isnan(debt_ratio) or math.isinf(debt_ratio):
        logger.warning(f"debt_ratio inválido ({debt_ratio}), assumindo 0.5")
        debt_ratio = 0.5
    if math.isnan(vacancy_rate) or math.isinf(vacancy_rate):
        logger.warning(f"vacancy_rate inválida ({vacancy_rate}), assumindo 0.15")
        vacancy_rate = 0.15

    debt_score = max(0.0, min(10.0, (1.0 - debt_ratio) * 10.0))
    vacancy_score = max(0.0, min(10.0, (1.0 - vacancy_rate / 0.30) * 10.0))
    return round(0.50 * debt_score + 0.50 * vacancy_score, 4)


def calculate_growth_score(
    revenue_growth_12m: float,
    earnings_growth_12m: float,
) -> float:
    """
    Calcula o score de crescimento de um FII baseado nos últimos 12 meses.

    Args:
        revenue_growth_12m (float): Crescimento de receita em 12m (ex: 0.10 = 10%).
            Normalizado: 0.0 → 5.0, 0.20 → 10.0.
        earnings_growth_12m (float): Crescimento de lucros em 12m.
            Mesma escala.

    Returns:
        float: Score de crescimento de 0.0 a 10.0.
    """
    if math.isnan(revenue_growth_12m) or math.isinf(revenue_growth_12m):
        revenue_growth_12m = 0.0
    if math.isnan(earnings_growth_12m) or math.isinf(earnings_growth_12m):
        earnings_growth_12m = 0.0

    rev_score = max(0.0, min(10.0, revenue_growth_12m / 0.20 * 10.0))
    earn_score = max(0.0, min(10.0, earnings_growth_12m / 0.20 * 10.0))
    return round(0.50 * rev_score + 0.50 * earn_score, 4)


def calculate_alpha_score(
    dividend_yield: float,
    dividend_consistency: float,
    pvp: float,
    debt_ratio: float,
    vacancy_rate: float,
    revenue_growth_12m: float,
    earnings_growth_12m: float,
    weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """
    Calcula o Alpha Score unificado de um FII usando modelo matemático explícito.

    Fórmula:
        score = (w_income × income_score) +
                (w_valuation × valuation_score) +
                (w_risk × risk_score) +
                (w_growth × growth_score)

    Args:
        dividend_yield (float): DY anual do FII (ex: 0.12 = 12% a.a.).
        dividend_consistency (float): Consistência de dividendos de 0 a 10.
        pvp (float): Preço / Valor Patrimonial atual.
        debt_ratio (float): Dívida / Patrimônio Líquido.
        vacancy_rate (float): Taxa de vacância física (0.0 a 1.0).
        revenue_growth_12m (float): Crescimento de receita nos últimos 12 meses.
        earnings_growth_12m (float): Crescimento de lucros nos últimos 12 meses.
        weights (dict[str, float] | None): Pesos do modelo. Se None, usa DEFAULT_WEIGHTS.

    Returns:
        dict[str, float]: Dicionário com 'alpha_score' (0-10), os sub-scores
            individuais e os pesos utilizados.

    Raises:
        ValueError: Se os pesos fornecidos forem inválidos.
    """
    w = weights if weights is not None else DEFAULT_WEIGHTS.copy()
    validate_weights(w)

    income_score = calculate_income_score(dividend_yield, dividend_consistency)
    valuation_score = calculate_valuation_score(pvp)
    risk_score = calculate_risk_score(debt_ratio, vacancy_rate)
    growth_score = calculate_growth_score(revenue_growth_12m, earnings_growth_12m)

    alpha = (
        w["w_income"] * income_score
        + w["w_valuation"] * valuation_score
        + w["w_risk"] * risk_score
        + w["w_growth"] * growth_score
    )

    return {
        "alpha_score": round(alpha, 2),
        "income_score": income_score,
        "valuation_score": valuation_score,
        "risk_score": risk_score,
        "growth_score": growth_score,
        "weights_used": w,
    }


def rank_fiis(
    fiis: list[dict],
    weights: dict[str, float] | None = None,
) -> list[dict]:
    """
    Aplica o cálculo de Alpha Score a uma lista de FIIs e os ordena por score.

    Cada FII no input deve ter as chaves compatíveis com calculate_alpha_score.

    Args:
        fiis (list[dict]): Lista de FIIs com os indicadores necessários.
            Campos esperados: 'ticker', 'dividend_yield', 'dividend_consistency',
            'pvp', 'debt_ratio', 'vacancy_rate', 'revenue_growth_12m',
            'earnings_growth_12m'.
        weights (dict[str, float] | None): Pesos do modelo. Default: DEFAULT_WEIGHTS.

    Returns:
        list[dict]: Lista de FIIs com 'alpha_score' adicionado, ordenada
            decrescentemente por score.
    """
    results = []
    for fii in fiis:
        score_data = calculate_alpha_score(
            dividend_yield=fii.get("dividend_yield", 0.0),
            dividend_consistency=fii.get("dividend_consistency", 5.0),
            pvp=fii.get("pvp", 1.0),
            debt_ratio=fii.get("debt_ratio", 0.5),
            vacancy_rate=fii.get("vacancy_rate", 0.0),
            revenue_growth_12m=fii.get("revenue_growth_12m", 0.0),
            earnings_growth_12m=fii.get("earnings_growth_12m", 0.0),
            weights=weights,
        )
        results.append({**fii, **score_data})

    return sorted(results, key=lambda x: x["alpha_score"], reverse=True)
