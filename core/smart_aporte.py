import math


def generateAporteSuggestion(
    classe_prioritaria: str, portfolio_ativo: list[dict], asset_universe: list[dict], valor_aporte: float
) -> dict:

    ativos_na_classe = [ativo for ativo in portfolio_ativo if ativo["classe"] == classe_prioritaria]

    universo_da_classe = [
        ativo for ativo in asset_universe if ativo["classe"] == classe_prioritaria and ativo.get("ativo", True)
    ]

    if valor_aporte <= 0:
        return {"erro": "Valor de aporte inválido"}

    # -------- CASO 1: Nenhum ativo na classe → expandir
    if len(ativos_na_classe) == 0:

        if not universo_da_classe:
            return {"erro": "Nenhum ativo disponível no universo"}

        candidato = universo_da_classe[0]
        preco = candidato.get("preco_atual")
        if not preco or preco <= 0:
            return {"erro": "Preço do ativo selecionado é inválido"}

        quantidade = math.floor(valor_aporte / preco)

        if quantidade <= 0:
            return {"erro": "Valor insuficiente para comprar 1 unidade"}

        valor_utilizado = quantidade * preco

        return {
            "tipo_operacao": "novo_ativo",
            "ticker": candidato["ticker"],
            "quantidade": quantidade,
            "valor_utilizado": valor_utilizado,
            "valor_restante": valor_aporte - valor_utilizado,
        }

    # -------- CASO 2: 1 ativo → expandir controlado
    if len(ativos_na_classe) == 1:

        tickers_existentes = {a["ticker"] for a in ativos_na_classe}

        candidato = next((a for a in universo_da_classe if a["ticker"] not in tickers_existentes), None)

        if candidato:
            preco = candidato.get("preco_atual")
            if not preco or preco <= 0:
                pass  # Pula pro Caso 3 se der problema no preço do universo
            else:
                quantidade = math.floor(valor_aporte / preco)

                if quantidade > 0:
                    valor_utilizado = quantidade * preco
                    return {
                        "tipo_operacao": "novo_ativo",
                        "ticker": candidato["ticker"],
                        "quantidade": quantidade,
                        "valor_utilizado": valor_utilizado,
                        "valor_restante": valor_aporte - valor_utilizado,
                    }

    # -------- CASO 3: 2 ou mais (ou fallback do Caso 2) → reforçar menor posição
    if not ativos_na_classe:
        return {"erro": "Não foi possível reforçar nem alocar"}

    ativo_menor = min(ativos_na_classe, key=lambda x: x["quantidade"] * x.get("preco_atual", float("inf")))

    preco = ativo_menor.get("preco_atual")
    if not preco or preco <= 0:
        return {"erro": "Preço do ativo na carteira é inválido"}

    quantidade = math.floor(valor_aporte / preco)

    if quantidade <= 0:
        return {"erro": "Valor insuficiente para reforço"}

    valor_utilizado = quantidade * preco

    return {
        "tipo_operacao": "reforco",
        "ticker": ativo_menor["ticker"],
        "quantidade": quantidade,
        "valor_utilizado": valor_utilizado,
        "valor_restante": valor_aporte - valor_utilizado,
    }
