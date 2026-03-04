"""
core/stress_engine.py

Motor de Stress Testing para carteiras de FIIs.

Aplica cenários de choque sobre uma carteira existente e mede o impacto
em patrimônio, dividendos e Sharpe. Sem dependências externas.

Cenários disponíveis:
- Alta de Juros     : choque na taxa Selic → queda no valor dos FIIs de Papel
- Queda de Mercado  : crash geral de mercado → todos os FIIs caem
- Corte de Dividendos: redução de proventos → impacto na renda passiva
- Vacância Setorial  : aumento de vacância em FIIs de Tijolo → queda de DY

Funções puras, sem classes.
"""

import math
import statistics


# ---------------------------------------------------------------------------
# Definições de cenários
# ---------------------------------------------------------------------------

# Cada cenário define:
# - name: nome amigável
# - description: descrição do evento
# - price_shock: percentual de queda de preços (negativo = queda)
# - dividend_shock: percentual de redução de dividendos
# Segmentados por tipo de FII (papel, tijolo, fundo_de_fundos, geral)

STRESS_SCENARIOS: dict[str, dict] = {
    "alta_juros_moderada": {
        "name": "Alta de Juros Moderada (+2%)",
        "description": "Selic sobe 2pp. FIIs de Papel sobem levemente, Tijolo caem.",
        "price_shock": {
            "Papel (CRI)":      +0.02,  # CRI se beneficia levemente
            "Logística":        -0.07,
            "Shopping":         -0.08,
            "Lajes Corp.":      -0.09,
            "Fundo de Fundos":  -0.06,
            "Outros":           -0.06,
        },
        "dividend_shock": {
            "Papel (CRI)":      +0.03,
            "Logística":        -0.03,
            "Shopping":         -0.03,
            "Lajes Corp.":      -0.04,
            "Fundo de Fundos":  -0.02,
            "Outros":           -0.02,
        },
    },
    "alta_juros_severa": {
        "name": "Alta de Juros Severa (+4%)",
        "description": "Ciclo agressivo de aperto monetário. Ativos reais se desvalorizam.",
        "price_shock": {
            "Papel (CRI)":      +0.03,
            "Logística":        -0.15,
            "Shopping":         -0.18,
            "Lajes Corp.":      -0.20,
            "Fundo de Fundos":  -0.13,
            "Outros":           -0.12,
        },
        "dividend_shock": {
            "Papel (CRI)":      +0.05,
            "Logística":        -0.06,
            "Shopping":         -0.08,
            "Lajes Corp.":      -0.09,
            "Fundo de Fundos":  -0.05,
            "Outros":           -0.05,
        },
    },
    "queda_mercado_20": {
        "name": "Queda de Mercado (-20%)",
        "description": "Crash abrupto: todos os ativos caem proporcionalmente.",
        "price_shock": {
            "Papel (CRI)":      -0.12,
            "Logística":        -0.20,
            "Shopping":         -0.22,
            "Lajes Corp.":      -0.18,
            "Fundo de Fundos":  -0.20,
            "Outros":           -0.20,
        },
        "dividend_shock": {
            "Papel (CRI)":      -0.05,
            "Logística":        -0.10,
            "Shopping":         -0.15,
            "Lajes Corp.":      -0.10,
            "Fundo de Fundos":  -0.10,
            "Outros":           -0.10,
        },
    },
    "queda_mercado_40": {
        "name": "Queda de Mercado (-40%)",
        "description": "Crise severa estilo 2008/2020. Liquidez colapsa.",
        "price_shock": {
            "Papel (CRI)":      -0.20,
            "Logística":        -0.38,
            "Shopping":         -0.45,
            "Lajes Corp.":      -0.40,
            "Fundo de Fundos":  -0.38,
            "Outros":           -0.38,
        },
        "dividend_shock": {
            "Papel (CRI)":      -0.10,
            "Logística":        -0.20,
            "Shopping":         -0.35,
            "Lajes Corp.":      -0.25,
            "Fundo de Fundos":  -0.20,
            "Outros":           -0.20,
        },
    },
    "corte_dividendos_30": {
        "name": "Corte de Dividendos (-30%)",
        "description": "Gestores cortam distribuições por inadimplência ou vacância.",
        "price_shock": {
            "Papel (CRI)":      -0.10,
            "Logística":        -0.10,
            "Shopping":         -0.12,
            "Lajes Corp.":      -0.11,
            "Fundo de Fundos":  -0.10,
            "Outros":           -0.10,
        },
        "dividend_shock": {
            "Papel (CRI)":      -0.30,
            "Logística":        -0.30,
            "Shopping":         -0.30,
            "Lajes Corp.":      -0.30,
            "Fundo de Fundos":  -0.30,
            "Outros":           -0.30,
        },
    },
    "corte_dividendos_50": {
        "name": "Corte de Dividendos (-50%)",
        "description": "Crise de caixa generalizada. Dividend Yield cai pela metade.",
        "price_shock": {
            "Papel (CRI)":      -0.18,
            "Logística":        -0.20,
            "Shopping":         -0.25,
            "Lajes Corp.":      -0.22,
            "Fundo de Fundos":  -0.20,
            "Outros":           -0.20,
        },
        "dividend_shock": {
            "Papel (CRI)":      -0.50,
            "Logística":        -0.50,
            "Shopping":         -0.50,
            "Lajes Corp.":      -0.50,
            "Fundo de Fundos":  -0.50,
            "Outros":           -0.50,
        },
    },
    "vacancia_tijolo": {
        "name": "Vacância em Alta (+15pp)",
        "description": "FIIs de Tijolo sofrem aumento abrupto de vacância. CRI resistem.",
        "price_shock": {
            "Papel (CRI)":      +0.00,
            "Logística":        -0.12,
            "Shopping":         -0.20,
            "Lajes Corp.":      -0.25,
            "Fundo de Fundos":  -0.08,
            "Outros":           -0.08,
        },
        "dividend_shock": {
            "Papel (CRI)":      +0.00,
            "Logística":        -0.20,
            "Shopping":         -0.30,
            "Lajes Corp.":      -0.35,
            "Fundo de Fundos":  -0.10,
            "Outros":           -0.10,
        },
    },
}


# ---------------------------------------------------------------------------
# Impacto sobre ativo individual
# ---------------------------------------------------------------------------

def apply_price_shock(
    preco_atual: float,
    sector: str,
    price_shock_map: dict[str, float],
) -> float:
    """
    Aplica o choque de preço de um cenário sobre um ativo.

    Args:
        preco_atual (float): Preço atual do ativo.
        sector (str): Setor do ativo (ex: 'Papel (CRI)', 'Logística').
        price_shock_map (dict): Mapa de choque por setor do cenário.

    Returns:
        float: Preço após o choque (nunca negativo).
    """
    shock = price_shock_map.get(sector, price_shock_map.get("Outros", 0.0))
    return max(0.0, preco_atual * (1 + shock))


def apply_dividend_shock(
    dividend_mensal: float,
    sector: str,
    dividend_shock_map: dict[str, float],
) -> float:
    """
    Aplica o choque de dividendo de um cenário sobre um ativo.

    Args:
        dividend_mensal (float): Dividendo mensal atual em R$.
        sector (str): Setor do ativo.
        dividend_shock_map (dict): Mapa de choque por setor.

    Returns:
        float: Dividendo após o choque (nunca negativo).
    """
    shock = dividend_shock_map.get(sector, dividend_shock_map.get("Outros", 0.0))
    return max(0.0, dividend_mensal * (1 + shock))


# ---------------------------------------------------------------------------
# Análise de um cenário sobre a carteira completa
# ---------------------------------------------------------------------------

def apply_stress_scenario(
    portfolio: list[dict],
    scenario_key: str,
    sector_map: dict[str, str],
) -> dict:
    """
    Aplica um cenário de stress à carteira e retorna o impacto.

    Args:
        portfolio (list[dict]): Lista de ativos com:
            'ticker', 'quantidade', 'preco_atual', 'dividend_mensal'.
        scenario_key (str): Chave do cenário em STRESS_SCENARIOS.
        sector_map (dict[str, str]): Mapeamento ticker → setor.

    Returns:
        dict: Resultado do stress com patrimônio antes/depois, dividendos,
              impacto por ativo e drawdown estimado.

    Raises:
        KeyError: Se scenario_key não existir em STRESS_SCENARIOS.
    """
    if scenario_key not in STRESS_SCENARIOS:
        raise KeyError(f"Cenário '{scenario_key}' não encontrado. "
                       f"Opções: {list(STRESS_SCENARIOS.keys())}")

    scenario = STRESS_SCENARIOS[scenario_key]
    price_shock_map   = scenario["price_shock"]
    dividend_shock_map = scenario["dividend_shock"]

    total_before     = 0.0
    total_after      = 0.0
    dividends_before = 0.0
    dividends_after  = 0.0
    asset_results    = []

    for asset in portfolio:
        ticker    = asset.get("ticker", "?")
        qty       = asset.get("quantidade", 0)
        price     = asset.get("preco_atual", 0.0)
        div_month = asset.get("dividend_mensal", 0.0)
        sector    = sector_map.get(ticker, "Outros")

        val_before  = qty * price
        price_after = apply_price_shock(price, sector, price_shock_map)
        val_after   = qty * price_after
        div_after   = apply_dividend_shock(div_month, sector, dividend_shock_map)

        total_before     += val_before
        total_after      += val_after
        dividends_before += div_month
        dividends_after  += div_after

        asset_results.append({
            "ticker":          ticker,
            "sector":          sector,
            "valor_antes":     round(val_before, 2),
            "valor_depois":    round(val_after, 2),
            "impacto_R$":      round(val_after - val_before, 2),
            "impacto_%":       round((val_after - val_before) / val_before * 100, 2) if val_before > 0 else 0.0,
            "dividendo_antes": round(div_month, 2),
            "dividendo_depois": round(div_after, 2),
        })

    # Ordenar por maior impacto negativo
    asset_results.sort(key=lambda x: x["impacto_R$"])

    patrimonio_drawdown = ((total_after - total_before) / total_before) if total_before > 0 else 0.0
    dividendos_delta    = ((dividends_after - dividends_before) / dividends_before) if dividends_before > 0 else 0.0

    return {
        "scenario_key":   scenario_key,
        "scenario_name":  scenario["name"],
        "description":    scenario["description"],
        "total_antes":    round(total_before, 2),
        "total_depois":   round(total_after, 2),
        "impacto_total":  round(total_after - total_before, 2),
        "drawdown":       round(patrimonio_drawdown, 4),
        "dividendos_antes":  round(dividends_before, 2),
        "dividendos_depois": round(dividends_after, 2),
        "dividendos_delta":  round(dividendos_delta, 4),
        "assets":         asset_results,
    }


# ---------------------------------------------------------------------------
# Múltiplos cenários de uma só vez
# ---------------------------------------------------------------------------

def run_stress_suite(
    portfolio: list[dict],
    sector_map: dict[str, str],
    scenario_keys: list[str] | None = None,
) -> list[dict]:
    """
    Roda múltiplos cenários de stress sobre a carteira.

    Args:
        portfolio (list[dict]): Carteira conforme apply_stress_scenario.
        sector_map (dict[str, str]): Setor por ticker.
        scenario_keys (list[str] | None): Cenários a rodar.
            Se None, roda todos os cenários disponíveis.

    Returns:
        list[dict]: Lista de resultados, ordenados do maior para menor drawdown.
    """
    keys = scenario_keys or list(STRESS_SCENARIOS.keys())
    results = [apply_stress_scenario(portfolio, k, sector_map) for k in keys]
    return sorted(results, key=lambda r: r["drawdown"])


# ---------------------------------------------------------------------------
# Formatação do relatório
# ---------------------------------------------------------------------------

def format_stress_report(result: dict) -> str:
    """
    Formata um relatório de stress testing em ASCII.

    Args:
        result (dict): Resultado de apply_stress_scenario.

    Returns:
        str: Relatório formatado.
    """
    lines = [
        "=" * 62,
        f"  CENÁRIO: {result['scenario_name']}",
        f"  {result['description']}",
        "=" * 62,
        f"  Patrimônio Antes : R$ {result['total_antes']:>12,.2f}",
        f"  Patrimônio Depois: R$ {result['total_depois']:>12,.2f}",
        f"  Impacto Total    : R$ {result['impacto_total']:>12,.2f}  ({result['drawdown']*100:+.2f}%)",
        f"  Dividendos/mês → : R$ {result['dividendos_antes']:>8,.2f} → R$ {result['dividendos_depois']:>8,.2f}  ({result['dividendos_delta']*100:+.1f}%)",
        "-" * 62,
        "  Impacto por Ativo:",
    ]

    for a in result["assets"]:
        lines.append(
            f"  {a['ticker']:<10} ({a['sector']:<14}) "
            f"  {a['impacto_%']:>+7.2f}%  R$ {a['impacto_R$']:>10,.2f}"
        )

    lines.append("=" * 62)
    return "\n".join(lines)


def summarize_stress_suite(suite_results: list[dict]) -> dict:
    """
    Resume os resultados de múltiplos cenários num quadro comparativo.

    Args:
        suite_results (list[dict]): Saída de run_stress_suite.

    Returns:
        dict: Resumo com pior cenário, drawdown médio e ranking por impacto.
    """
    if not suite_results:
        return {}

    worst = min(suite_results, key=lambda r: r["drawdown"])
    best  = max(suite_results, key=lambda r: r["drawdown"])
    avg_drawdown = sum(r["drawdown"] for r in suite_results) / len(suite_results)
    avg_div_cut  = sum(r["dividendos_delta"] for r in suite_results) / len(suite_results)

    return {
        "worst_scenario":   worst["scenario_name"],
        "worst_drawdown":   worst["drawdown"],
        "best_scenario":    best["scenario_name"],
        "best_drawdown":    best["drawdown"],
        "avg_drawdown":     round(avg_drawdown, 4),
        "avg_div_cut":      round(avg_div_cut, 4),
        "n_scenarios":      len(suite_results),
        "ranking":          [
            {"scenario": r["scenario_name"], "drawdown": r["drawdown"],
             "div_delta": r["dividendos_delta"]}
            for r in suite_results
        ],
    }
