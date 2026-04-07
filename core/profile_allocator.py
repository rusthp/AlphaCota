def getTargetAllocation(perfil_risco: str) -> dict[str, float]:
    """
    Retorna a alocação alvo esperada por classe de ativo com base no perfil de risco do investidor.
    """
    perfil = perfil_risco.lower().strip()

    if perfil == "conservador":
        return {"ETF": 0.60, "FII": 0.30, "ACAO": 0.10}
    elif perfil == "moderado":
        return {"ETF": 0.50, "ACAO": 0.30, "FII": 0.20}
    elif perfil == "agressivo":
        return {"ACAO": 0.70, "ETF": 0.20, "FII": 0.10}
    else:
        raise ValueError("Perfil de risco inválido. Perfis aceitos: 'conservador', 'moderado', 'agressivo'.")
