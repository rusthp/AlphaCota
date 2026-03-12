from typing import Any, Union

def calculate_position_metrics(
    operacoes: list[dict[str, Union[str, float, int]]],
    precos_atuais: dict[str, float]
) -> dict[str, dict[str, float]]:
    """
    Agrupa operações por ticker e calcula as métricas reais da posição atual.

    Args:
        operacoes (list[dict[str, Union[str, float, int]]]): Lista contendo histórico de operações.
            Cada dict deve possuir: 'ticker' (str), 'tipo' ('compra' ou 'venda'), 
            'quantidade' (float/int) e 'preco' (float).
        precos_atuais (dict[str, float]): Dicionário mapeando ticker para preço atual no mercado.

    Raises:
        ValueError: Se quantidades/preços forem negativos, tipo de operação for inválido 
                    ou ocorrer venda a descoberto (vender mais do que possui).

    Returns:
        dict[str, dict[str, float]]: Dicionário com as métricas consolidadas por ticker, contendo:
            - quantidade_total
            - preco_medio
            - valor_investido
            - valor_atual
            - lucro_prejuizo
            - lucro_prejuizo_percentual
    """
    posicoes = {}

    for op in operacoes:
        ticker = op.get("ticker")
        tipo = op.get("tipo")
        qtd = float(op.get("quantidade", 0))
        preco = float(op.get("preco", 0.0))

        if not isinstance(ticker, str) or not ticker:
            raise ValueError("Operação contém ticker inválido ou ausente.")
        if qtd < 0 or preco < 0:
            raise ValueError(f"Quantidade ou preço negativo na operação do ativo {ticker}.")
        if tipo not in ["compra", "venda"]:
            raise ValueError(f"Tipo de operação inválido ('{tipo}') para o ativo {ticker}. Use 'compra' ou 'venda'.")

        if ticker not in posicoes:
            posicoes[ticker] = {
                "quantidade_total": 0.0,
                "valor_total_investido": 0.0  # Usado para compor o preço médio
            }
        
        pos = posicoes[ticker]

        if tipo == "compra":
            pos["quantidade_total"] += qtd
            pos["valor_total_investido"] += (qtd * preco)
        elif tipo == "venda":
            if qtd > pos["quantidade_total"]:
                raise ValueError(f"Venda a descoberto não permitida para o ativo {ticker}. Tentou vender {qtd} possuindo {pos['quantidade_total']}.")
            
            # Subtrai a quantidade, mas o preço médio da posição restante se mantém o mesmo
            # Ou seja, o valor_total_investido retrai proporcionalmente ao preço médio atual
            preco_medio_atual = pos["valor_total_investido"] / pos["quantidade_total"]
            pos["quantidade_total"] -= qtd
            pos["valor_total_investido"] -= (qtd * preco_medio_atual)

    resultado = {}

    for ticker, pos in posicoes.items():
        qtd_total = pos["quantidade_total"]
        
        # Ignora posições completamente zeradas
        if qtd_total == 0:
            continue
            
        valor_investido = pos["valor_total_investido"]
        preco_medio = valor_investido / qtd_total
        
        preco_atual = precos_atuais.get(ticker, 0.0)
        valor_atual = qtd_total * preco_atual
        
        lucro_prejuizo = valor_atual - valor_investido
        lucro_prejuizo_percentual = (lucro_prejuizo / valor_investido * 100) if valor_investido > 0 else 0.0

        resultado[ticker] = {
            "quantidade_total": qtd_total,
            "preco_medio": preco_medio,
            "valor_investido": valor_investido,
            "valor_atual": valor_atual,
            "lucro_prejuizo": lucro_prejuizo,
            "lucro_prejuizo_percentual": lucro_prejuizo_percentual
        }

    return resultado
