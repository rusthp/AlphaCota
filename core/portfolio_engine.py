from typing import Any, Union


def calculate_portfolio_allocation(ativos: list[dict[str, Union[str, float]]]) -> dict[str, Any]:
    """
    Calcula o valor total da carteira e o percentual de alocação de cada ativo.
    Retorna os valores exatos (sem arredondamento na engine base).

    Args:
        ativos (list[dict[str, Union[str, float]]]): Lista contendo o 'ticker' (str)
                                                     e o 'valor' (float) financeiro de cada ativo.

    Raises:
        ValueError: Se algum valor for negativo ou o ticker for inválido.

    Returns:
        dict[str, Any]: Dicionário contendo o valor total da carteira ('total') e
                        a lista de ativos atualizada com o 'percentual' de alocação.
    """
    total = 0.0
    for ativo in ativos:
        ticker = ativo.get("ticker", "")
        valor = ativo.get("valor", 0.0)

        if not isinstance(ticker, str) or not ticker:
            raise ValueError("Ticker inválido ou ausente.")
        if valor < 0:
            raise ValueError(f"Valor negativo encontrado no ativo {ticker}.")

        total += float(valor)

    allocations = []

    for ativo in ativos:
        ticker = ativo["ticker"]
        valor = float(ativo["valor"])
        percentual = (valor / total * 100) if total > 0 else 0.0

        allocations.append({"ticker": ticker, "valor": valor, "percentual": percentual})

    return {"total": total, "allocations": allocations}


def calculate_rebalance_suggestion(
    ativos_atuais: list[dict[str, Union[str, float]]], alocacao_alvo: dict[str, float], aporte_mensal: float
) -> dict[str, list[dict[str, Union[str, float]]]]:
    """
    Calcula quanto do aporte mensal deve ser investido em cada ativo para
    aproximar a carteira da alocação alvo definida.

    Args:
        ativos_atuais (list[dict[str, Union[str, float]]]): Lista de ativos atuais e seus valores.
        alocacao_alvo (dict[str, float]): Dicionário com ticker e o percentual alvo (ex: 0.50 para 50%).
        aporte_mensal (float): Valor total disponível para o novo aporte.

    Raises:
        ValueError: Se valores forem negativos ou ativo atual não estiver na alocação alvo.

    Returns:
        dict[str, list[dict[str, Union[str, float]]]]: Sugestões de aporte por ativo.
    """
    if aporte_mensal < 0:
        raise ValueError("O aporte mensal não pode ser negativo.")

    total_atual = 0.0

    # Validações iniciais e cálculo do total
    for ativo in ativos_atuais:
        ticker = ativo.get("ticker", "")
        valor = ativo.get("valor", 0.0)

        if not isinstance(ticker, str) or not ticker:
            raise ValueError("Ticker inválido ou ausente.")
        if valor < 0:
            raise ValueError(f"Valor negativo encontrado no ativo {ticker}.")
        if ticker not in alocacao_alvo:
            raise ValueError(f"Ativo {ticker} não encontrado na alocação alvo.")

        total_atual += float(valor)

    # Valida percentuais alvo e soma 1.0 (opcional, dependendo de estratégias parciais, mas bom verificar < 0)
    for ticker_alvo, pct_alvo in alocacao_alvo.items():
        if pct_alvo < 0:
            raise ValueError(f"Alocação alvo do ativo {ticker_alvo} não pode ser negativa.")

    total_futuro = total_atual + aporte_mensal

    distancias = {}
    soma_distancias = 0.0

    # Calcular a distância de cada ativo para o alvo
    for ativo in ativos_atuais:
        ticker = ativo["ticker"]
        valor = float(ativo["valor"])

        # Quanto o ativo DEVERIA ter no total futuro
        valor_alvo = total_futuro * alocacao_alvo[ticker]

        # Só consideramos a distância positiva (não vendemos para rebalancear o aporte)
        distancia = max(0.0, valor_alvo - valor)
        distancias[ticker] = distancia
        soma_distancias += distancia

    sugestao = []

    for ativo in ativos_atuais:
        ticker = ativo["ticker"]

        if soma_distancias > 0:
            proporcao = distancias[ticker] / soma_distancias
            aportar = aporte_mensal * proporcao
        else:
            # Se a carteira já está em equilíbrio ou sem distâncias (ex: aporte num portfólio vazio)
            aportar = aporte_mensal * alocacao_alvo[ticker]

        sugestao.append({"ticker": ticker, "valor_aportar": aportar})

    return {"sugestao": sugestao}
