from typing import Union


def calculate_income_metrics(
    proventos: list[dict[str, Union[str, float]]], valor_total_carteira: float
) -> dict[str, float]:
    """
    Calcula as métricas reais de renda passiva (dividendos/proventos).

    Args:
        proventos (list[dict[str, Union[str, float]]]): Lista contendo o histórico recente ou mensal
                                                        de proventos recebidos por ticker.
        valor_total_carteira (float): O saldo ou valor de mercado total atual da carteira.

    Raises:
        ValueError: Se o valor da carteira for nulo/negativo, ou se
                    algum provento registrado tiver valor financeiro negativo.

    Returns:
        dict[str, float]: Dicionário com:
            - renda_total: Soma pura de todos os proventos
            - yield_percentual: Relação percentual da renda sobre o valor_total_carteira
    """
    if valor_total_carteira <= 0:
        raise ValueError("O valor total da carteira deve ser maior que zero para o cálculo de yield.")

    renda_total = 0.0

    for provento in proventos:
        ticker = provento.get("ticker", "")
        valor = provento.get("valor", 0.0)

        if not isinstance(ticker, str) or not ticker:
            raise ValueError("Provento contém ticker inválido ou ausente.")

        if valor < 0:
            raise ValueError(f"Valor de provento negativo encontrado no ativo {ticker}.")

        renda_total += float(valor)

    yield_percentual = (renda_total / valor_total_carteira) * 100

    return {"renda_total": renda_total, "yield_percentual": yield_percentual}
