def calculate_years_to_fire(
    patrimonio_atual: float,
    aporte_mensal: float,
    taxa_anual: float,
    renda_alvo_anual: float,
) -> float:
    """
    Calcula o tempo estimado (em anos) para atingir a independência financeira.

    Considera o patrimônio atual, os aportes mensais e uma taxa de juros
    composta mensalmente até que o patrimônio necessário (renda alvo / taxa)
    seja alcançado. A simulação é feita mês a mês.

    Args:
        patrimonio_atual (float): Valor atual já investido.
        aporte_mensal (float): Valor investido todos os meses.
        taxa_anual (float): Taxa de retorno anual esperada (ex: 0.10 para 10%).
        renda_alvo_anual (float): Renda passiva anual desejada.

    Raises:
        ValueError: Se a meta for inalcançável (mais de 200 anos ou parâmetros inválidos).

    Returns:
        float: Quantidade de anos para atingir o objetivo financeiro.
    """
    if taxa_anual <= 0 or renda_alvo_anual < 0 or aporte_mensal < 0 or patrimonio_atual < 0:
        raise ValueError("Parâmetros inválidos. Valores devem ser positivos.")

    patrimonio_necessario = renda_alvo_anual / taxa_anual
    taxa_mensal = (1 + taxa_anual) ** (1 / 12) - 1

    meses = 0
    patrimonio = patrimonio_atual

    while patrimonio < patrimonio_necessario:
        # Applica o rendimento do mês e soma o novo aporte
        patrimonio = (patrimonio * (1 + taxa_mensal)) + aporte_mensal
        meses += 1
        
        # Trava de segurança para evitar loops infinitos irreais (ex: 200 anos)
        if meses > 2400:
            raise ValueError("Meta inalcançável com os parâmetros atuais (mais de 200 anos).")

    return round(meses / 12, 1)


def calculate_required_capital(renda_alvo_anual: float, taxa_anual: float) -> float:
    """
    Calcula o capital total necessário para gerar uma renda alvo anual.

    Args:
        renda_alvo_anual (float): Renda passiva anual desejada.
        taxa_anual (float): Taxa de retorno anual esperada (ex: 0.10 para 10%).

    Returns:
        float: Capital total necessário.
    """
    if taxa_anual <= 0:
        return 0.0
    return renda_alvo_anual / taxa_anual
