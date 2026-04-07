def calculateRebalanceSuggestion(portfolio: list[dict], target_allocation: dict[str, float]) -> dict:
    """
    Identifica qual classe de ativo necessita de aporte prioritário baseado no alvo do perfil do usuário.

    Args:
        portfolio: Lista contendo dicionários dos ativos (ex: {'classe': 'ETF', 'quantidade': 10, 'preco_atual': 100})
        target_allocation: Dicionário contendo os percentuais alvos por classe.
    """
    # 1. Calcular valor total da carteira e agregar valor por classe
    valor_total = 0.0
    valor_por_classe = {classe: 0.0 for classe in target_allocation.keys()}

    for ativo in portfolio:
        classe = ativo["classe"]
        valor_posicao = ativo["quantidade"] * ativo["preco_atual"]

        valor_total += valor_posicao
        if classe in valor_por_classe:
            valor_por_classe[classe] += valor_posicao
        else:
            valor_por_classe[classe] = valor_posicao

    # Variáveis para rastrear 4. Identificar qual classe está mais abaixo do alvo
    resultado = {}
    maior_distorcao = -float("inf")
    classe_prioritaria = None

    for classe, alvo in target_allocation.items():
        # 2. Calcular peso atual por classe
        peso_atual = (valor_por_classe.get(classe, 0.0) / valor_total) if valor_total > 0 else 0.0

        # 3. Calcular distorção
        distorcao = alvo - peso_atual

        resultado[classe] = {"peso_atual": round(peso_atual, 4), "distorcao": round(distorcao, 4)}

        # 4. Avaliar se é a prioridade
        if distorcao > maior_distorcao:
            maior_distorcao = distorcao
            classe_prioritaria = classe

    # 5. Retornar
    return {"pesos_e_distorcoes": resultado, "classe_prioritaria_para_aporte": classe_prioritaria}
