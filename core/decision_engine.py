from typing import Union, Any
from core.position_engine import calculate_position_metrics
from core.income_engine import calculate_income_metrics
from core.fire_engine import calculate_required_capital, calculate_years_to_fire
from core.portfolio_engine import calculate_rebalance_suggestion

def generate_decision_report(
    operacoes: list[dict[str, Union[str, float, int]]],
    precos_atuais: dict[str, float],
    proventos: list[dict[str, Union[str, float]]],
    alocacao_alvo: dict[str, float],
    aporte_mensal: float,
    taxa_anual_esperada: float,
    renda_alvo_anual: float
) -> dict[str, Any]:
    """
    Orquestrador financeiro que consolida os dados de todos os motores
    e gera um relatório único de decisão.

    Args:
        operacoes (list[dict]): Histórico de operações de compra/venda.
        precos_atuais (dict): Mapeamento de tickers para preços atuais.
        proventos (list[dict]): Histórico de proventos recebidos.
        alocacao_alvo (dict): Percentuais alvo de cada ticker na carteira.
        aporte_mensal (float): Valor mensal disponível para novos aportes.
        taxa_anual_esperada (float): Taxa de rentabilidade anual esperada.
        renda_alvo_anual (float): Renda passiva anual desejada (FIRE).

    Returns:
        dict: Relatório estruturado contendo o resumo da carteira,
              renda passiva, fogo financeiro e sugestão de rebalanceamento.
    """
    # 1. Posição Atual
    posicoes_metricas = calculate_position_metrics(operacoes, precos_atuais)
    
    valor_total_carteira = 0.0
    lucro_prejuizo_total = 0.0
    valor_investido_total = 0.0
    ativos_atuais_para_rebalance = []
    
    for ticker, metadas_pos in posicoes_metricas.items():
        v_atual = metadas_pos["valor_atual"]
        v_investido = metadas_pos["valor_investido"]
        
        valor_total_carteira += v_atual
        valor_investido_total += v_investido
        lucro_prejuizo_total += metadas_pos["lucro_prejuizo"]
        
        ativos_atuais_para_rebalance.append({
            "ticker": ticker,
            "valor": v_atual
        })
        
    lucro_prejuizo_percentual_total = 0.0
    if valor_investido_total > 0:
        lucro_prejuizo_percentual_total = (lucro_prejuizo_total / valor_investido_total) * 100

    # 2. Renda Passiva
    # Em um cenário onde a carteira está recém-comprada e totalizando zero, o cálculo
    # de yield dispararia um ValueError. Vamos proteger isso em nível de orquestrador.
    if valor_total_carteira > 0 and proventos:
        renda_metricas = calculate_income_metrics(proventos, valor_total_carteira)
        renda_total = renda_metricas["renda_total"]
        yield_percentual = renda_metricas["yield_percentual"]
    else:
        renda_total = sum(float(p.get("valor", 0)) for p in proventos)
        yield_percentual = 0.0

    # 3. Fogo Financeiro (FIRE)
    patrimonio_necessario = calculate_required_capital(renda_alvo_anual, taxa_anual_esperada)
    
    anos_estimados = 0.0
    try:
        anos_estimados = calculate_years_to_fire(
            patrimonio_atual=valor_total_carteira,
            aporte_mensal=aporte_mensal,
            taxa_anual=taxa_anual_esperada,
            renda_alvo_anual=renda_alvo_anual
        )
    except ValueError:
        # Repassa um limite superior ou indicação caso os parâmetros inviabilizem o FIRE em "vida útil"
        anos_estimados = -1.0 

    # 4. Rebalanceamento
    try:
        rebalanceamento_res = calculate_rebalance_suggestion(
            ativos_atuais=ativos_atuais_para_rebalance,
            alocacao_alvo=alocacao_alvo,
            aporte_mensal=aporte_mensal
        )
        sugestao = rebalanceamento_res.get("sugestao", [])
    except ValueError:
        sugestao = []

    # 5. Entrega do Relatório (JSON Contract)
    return {
        "resumo_carteira": {
            "valor_total": valor_total_carteira,
            "lucro_prejuizo_total": lucro_prejuizo_total,
            "lucro_prejuizo_percentual_total": lucro_prejuizo_percentual_total
        },
        "renda_passiva": {
            "renda_total": renda_total,
            "yield_percentual": yield_percentual
        },
        "fogo_financeiro": {
            "patrimonio_necessario": patrimonio_necessario,
            "anos_estimados": anos_estimados
        },
        "rebalanceamento": {
            "sugestao": sugestao
        }
    }
