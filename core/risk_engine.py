import statistics
import math


def calculate_volatility(lista_retornos_diarios: list[float]) -> float:
    """
    Calcula a volatilidade (risco) anualizada de um ativo.

    A medida de risco é o desvio padrão dos retornos diários
    escalada (multiplicada pela raiz quadrada de 252 dias úteis)
    para apresentar um dado anual.

    Args:
        lista_retornos_diarios (list[float]): Retornos diários (em percentual
        ou valores absolutos).

    Returns:
        float: Volatilidade anualizada.
    """
    if len(lista_retornos_diarios) < 2:
        return 0.0

    desvio_padrao_diario = statistics.stdev(lista_retornos_diarios)
    volatilidade_anualizada = desvio_padrao_diario * math.sqrt(252)

    return volatilidade_anualizada
