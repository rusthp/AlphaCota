import copy
import random
from core.class_rebalancer import calculateRebalanceSuggestion
from core.smart_aporte import generateAporteSuggestion
from core.profile_allocator import getTargetAllocation


def simulate_12_months(
    portfolio_inicial: list[dict],
    asset_universe: list[dict],
    target_allocation: dict[str, float],
    aporte_mensal: float,
    meses: int = 12,
) -> dict:

    # Trabalhar com uma cópia profunda para não mutar o estado inicial da aplicação
    portfolio = copy.deepcopy(portfolio_inicial)
    historico_mensal = []

    for mes in range(1, meses + 1):
        # 1) Identificar classe prioritária (baseado na nossa disciplina do motor de rebalanceamento)
        if not portfolio:
            # Se carteira vazia, pega a classe com maior peso alvo
            classe_prioritaria = max(target_allocation.items(), key=lambda x: x[1])[0]
        else:
            rebalanceamento = calculateRebalanceSuggestion(portfolio, target_allocation)
            classe_prioritaria = rebalanceamento.get("classe_prioritaria_para_aporte")

        # 2) Chamar gerar_aporte_suggestion
        sugestao = generateAporteSuggestion(
            classe_prioritaria=classe_prioritaria,
            portfolio_ativo=portfolio,
            asset_universe=asset_universe,
            valor_aporte=aporte_mensal,
        )

        # 3) Atualizar quantidade do ativo na carteira
        operacao_realizada = False
        if "erro" not in sugestao and sugestao.get("quantidade", 0) > 0:
            ticker_alvo = sugestao["ticker"]
            qtd_comprada = sugestao["quantidade"]

            # Buscar ativo na carteira
            ativo_existente = next((a for a in portfolio if a["ticker"] == ticker_alvo), None)

            if ativo_existente:
                ativo_existente["quantidade"] += qtd_comprada
            else:
                # Buscar no universo para adicionar novo ativo
                ativo_universo = next((a for a in asset_universe if a["ticker"] == ticker_alvo), None)
                if ativo_universo:
                    novo_ativo = {
                        "ticker": ticker_alvo,
                        "classe": ativo_universo["classe"],
                        "quantidade": qtd_comprada,
                        "preco_atual": ativo_universo["preco_atual"],
                    }
                    portfolio.append(novo_ativo)
            operacao_realizada = True

        # 4) Recalcular valor total da carteira e proporcoes
        valor_total = sum(a["quantidade"] * a.get("preco_atual", 0) for a in portfolio)

        distribuicao = {}
        for a in portfolio:
            cls = a["classe"]
            valor_posicao = a["quantidade"] * a.get("preco_atual", 0)
            distribuicao[cls] = distribuicao.get(cls, 0) + valor_posicao

        for cls in distribuicao:
            distribuicao[cls] = round((distribuicao[cls] / valor_total) if valor_total > 0 else 0, 4)

        # 5) Salvar snapshot mensal
        snapshot = {
            "mes": mes,
            "classe_prioritaria": classe_prioritaria,
            "operacao": (
                sugestao if operacao_realizada else {"erro": sugestao.get("erro", "Saldo insuficiente ou sem operacao")}
            ),
            "valor_total": round(valor_total, 2),
            "distribuicao_percentual": distribuicao,
        }
        historico_mensal.append(snapshot)

    return {
        "historico_mensal": historico_mensal,
        "valor_final": round(sum(a["quantidade"] * a.get("preco_atual", 0) for a in portfolio), 2),
        "composicao_final": portfolio,
    }


def simulate_with_growth(
    portfolio_inicial: list[dict],
    asset_universe: list[dict],
    target_allocation: dict[str, float],
    aporte_mensal: float,
    growth_rates: dict[str, float],
    meses: int = 12,
) -> dict:

    portfolio = copy.deepcopy(portfolio_inicial)
    historico_mensal = []

    # Pre-calculating compound monthly growth rate for each class
    # taxa_mensal = (1 + taxa_anual) ** (1/12) - 1
    monthly_growth = {}
    for cls, annual_rate in growth_rates.items():
        monthly_growth[cls] = (1 + annual_rate) ** (1 / 12) - 1

    for mes in range(1, meses + 1):

        # 1) Atualizar preco_atual de cada ativo aplicando crescimento mensal
        for ativo in portfolio:
            cls = ativo["classe"]
            if cls in monthly_growth:
                ativo["preco_atual"] = ativo["preco_atual"] * (1 + monthly_growth[cls])

        for ativo in asset_universe:
            cls = ativo["classe"]
            if cls in monthly_growth:
                ativo["preco_atual"] = ativo["preco_atual"] * (1 + monthly_growth[cls])

        # 2) Recalcular valor total
        valor_total = sum(a["quantidade"] * a.get("preco_atual", 0) for a in portfolio)

        # 3) Executar logica normal de aporte - identificando classe prioritaria
        if not portfolio:
            classe_prioritaria = max(target_allocation.items(), key=lambda x: x[1])[0]
        else:
            rebalanceamento = calculateRebalanceSuggestion(portfolio, target_allocation)
            classe_prioritaria = rebalanceamento.get("classe_prioritaria_para_aporte")

        sugestao = generateAporteSuggestion(
            classe_prioritaria=classe_prioritaria,
            portfolio_ativo=portfolio,
            asset_universe=asset_universe,
            valor_aporte=aporte_mensal,
        )

        operacao_realizada = False
        if "erro" not in sugestao and sugestao.get("quantidade", 0) > 0:
            ticker_alvo = sugestao["ticker"]
            qtd_comprada = sugestao["quantidade"]

            ativo_existente = next((a for a in portfolio if a["ticker"] == ticker_alvo), None)

            if ativo_existente:
                ativo_existente["quantidade"] += qtd_comprada
            else:
                ativo_universo = next((a for a in asset_universe if a["ticker"] == ticker_alvo), None)
                if ativo_universo:
                    novo_ativo = {
                        "ticker": ticker_alvo,
                        "classe": ativo_universo["classe"],
                        "quantidade": qtd_comprada,
                        "preco_atual": ativo_universo["preco_atual"],  # already updated pricing
                    }
                    portfolio.append(novo_ativo)
            operacao_realizada = True

        # Re-evaluating distribution metrics after aporte
        valor_total = sum(a["quantidade"] * a.get("preco_atual", 0) for a in portfolio)
        distribuicao = {}
        for a in portfolio:
            cls = a["classe"]
            valor_posicao = a["quantidade"] * a.get("preco_atual", 0)
            distribuicao[cls] = distribuicao.get(cls, 0) + valor_posicao

        for cls in distribuicao:
            distribuicao[cls] = round((distribuicao[cls] / valor_total) if valor_total > 0 else 0, 4)

        # 4) Salvar snapshot incluindo preços atualizados
        snapshot = {
            "mes": mes,
            "classe_prioritaria": classe_prioritaria,
            "operacao": (
                sugestao if operacao_realizada else {"erro": sugestao.get("erro", "Saldo insuficiente ou sem operacao")}
            ),
            "valor_total": round(valor_total, 2),
            "distribuicao_percentual": distribuicao,
            "precos_atuais": {a["ticker"]: round(a.get("preco_atual", 0), 2) for a in portfolio},
        }
        historico_mensal.append(snapshot)

    return {
        "historico_mensal": historico_mensal,
        "valor_final": round(sum(a["quantidade"] * a.get("preco_atual", 0) for a in portfolio), 2),
        "composicao_final": portfolio,
    }


def simulate_with_growth_and_shock(
    portfolio_inicial: list[dict],
    asset_universe: list[dict],
    target_allocation: dict[str, float],
    aporte_mensal: float,
    growth_rates: dict[str, float],
    shock_event: dict,
    meses: int = 12,
) -> dict:

    portfolio = copy.deepcopy(portfolio_inicial)
    historico_mensal = []

    monthly_growth = {}
    for cls, annual_rate in growth_rates.items():
        monthly_growth[cls] = (1 + annual_rate) ** (1 / 12) - 1

    for mes in range(1, meses + 1):

        shock_aplicado = False

        # 1) Atualizar precos (Crescimento mensal normal)
        for ativo in portfolio:
            cls = ativo["classe"]
            if cls in monthly_growth:
                ativo["preco_atual"] = ativo["preco_atual"] * (1 + monthly_growth[cls])

        for ativo in asset_universe:
            cls = ativo["classe"]
            if cls in monthly_growth:
                ativo["preco_atual"] = ativo["preco_atual"] * (1 + monthly_growth[cls])

        # 2) Evento de Choque de Mercado (Sobrescrevendo a flutuação do cenário)
        if mes == shock_event.get("mes"):
            shock_aplicado = True
            impactos = shock_event.get("impacto", {})

            for ativo in portfolio:
                cls = ativo["classe"]
                if cls in impactos:
                    ativo["preco_atual"] = ativo["preco_atual"] * (1 + impactos[cls])

            for ativo in asset_universe:
                cls = ativo["classe"]
                if cls in impactos:
                    ativo["preco_atual"] = ativo["preco_atual"] * (1 + impactos[cls])

        # 3) Recalcular valor total
        valor_total = sum(a["quantidade"] * a.get("preco_atual", 0) for a in portfolio)

        # 4) Executar logica normal de aporte - identificando classe prioritaria
        if not portfolio:
            classe_prioritaria = max(target_allocation.items(), key=lambda x: x[1])[0]
        else:
            rebalanceamento = calculateRebalanceSuggestion(portfolio, target_allocation)
            classe_prioritaria = rebalanceamento.get("classe_prioritaria_para_aporte")

        sugestao = generateAporteSuggestion(
            classe_prioritaria=classe_prioritaria,
            portfolio_ativo=portfolio,
            asset_universe=asset_universe,
            valor_aporte=aporte_mensal,
        )

        operacao_realizada = False
        if "erro" not in sugestao and sugestao.get("quantidade", 0) > 0:
            ticker_alvo = sugestao["ticker"]
            qtd_comprada = sugestao["quantidade"]

            ativo_existente = next((a for a in portfolio if a["ticker"] == ticker_alvo), None)

            if ativo_existente:
                ativo_existente["quantidade"] += qtd_comprada
            else:
                ativo_universo = next((a for a in asset_universe if a["ticker"] == ticker_alvo), None)
                if ativo_universo:
                    novo_ativo = {
                        "ticker": ticker_alvo,
                        "classe": ativo_universo["classe"],
                        "quantidade": qtd_comprada,
                        "preco_atual": ativo_universo["preco_atual"],
                    }
                    portfolio.append(novo_ativo)
            operacao_realizada = True

        # Re-evaluating distribution metrics after aporte
        valor_total = sum(a["quantidade"] * a.get("preco_atual", 0) for a in portfolio)
        distribuicao = {}
        for a in portfolio:
            cls = a["classe"]
            valor_posicao = a["quantidade"] * a.get("preco_atual", 0)
            distribuicao[cls] = distribuicao.get(cls, 0) + valor_posicao

        for cls in distribuicao:
            distribuicao[cls] = round((distribuicao[cls] / valor_total) if valor_total > 0 else 0, 4)

        # 5) Salvar snapshot incluindo choque e novos cenários
        snapshot = {
            "mes": mes,
            "shock_aplicado": shock_aplicado,
            "classe_prioritaria": classe_prioritaria,
            "operacao": (
                sugestao if operacao_realizada else {"erro": sugestao.get("erro", "Saldo insuficiente ou sem operacao")}
            ),
            "valor_total": round(valor_total, 2),
            "distribuicao_percentual": distribuicao,
            "precos_atuais": {a["ticker"]: round(a.get("preco_atual", 0), 2) for a in portfolio},
        }
        historico_mensal.append(snapshot)

    return {
        "historico_mensal": historico_mensal,
        "valor_final": round(sum(a["quantidade"] * a.get("preco_atual", 0) for a in portfolio), 2),
        "composicao_final": portfolio,
    }


def compare_profiles_under_scenario(
    perfis: list[str],
    portfolio_inicial: list[dict],
    asset_universe: list[dict],
    aporte_mensal: float,
    growth_rates: dict[str, float],
    shock_event: dict,
    meses: int = 12,
) -> dict:

    comparativo = {}

    for perfil in perfis:
        target_allocation = getTargetAllocation(perfil)

        simulacao = simulate_with_growth_and_shock(
            portfolio_inicial=portfolio_inicial,
            asset_universe=asset_universe,
            target_allocation=target_allocation,
            aporte_mensal=aporte_mensal,
            growth_rates=growth_rates,
            shock_event=shock_event,
            meses=meses,
        )

        # Calcular metricas
        valor_final = simulacao["valor_final"]

        peak = 0.0
        max_dd = 0.0
        in_drawdown = False
        meses_recuperacao = 0
        mes_inicio_dd = 0

        max_desvio = 0.0

        for snap in simulacao["historico_mensal"]:
            val = snap["valor_total"]

            # Drawdown and Recovery
            if val > peak:
                if in_drawdown:
                    rec_time = snap["mes"] - mes_inicio_dd
                    if rec_time > meses_recuperacao:
                        meses_recuperacao = rec_time
                    in_drawdown = False
                peak = val
            elif val < peak:
                if not in_drawdown:
                    in_drawdown = True
                    mes_inicio_dd = snap["mes"] - 1  # Month before the drop

                dd = (peak - val) / peak
                if dd > max_dd:
                    max_dd = dd

            # Desvio maximo
            dist = snap["distribuicao_percentual"]
            for cls, target in target_allocation.items():
                atual = dist.get(cls, 0.0)
                desvio = abs(atual - target)
                if desvio > max_desvio:
                    max_desvio = desvio

        # Check if still in drawdown at the end
        if in_drawdown:
            rec_time = meses - mes_inicio_dd
            if rec_time > meses_recuperacao:
                meses_recuperacao = rec_time

        comparativo[perfil] = {
            "valor_final": round(valor_final, 2),
            "maior_drawdown_percentual": round(max_dd, 4),
            "meses_para_recuperacao": meses_recuperacao,
            "desvio_maximo_da_meta": round(max_desvio, 4),
        }

    return comparativo


def simulate_stochastic(
    portfolio_inicial: list[dict],
    asset_universe: list[dict],
    target_allocation: dict[str, float],
    aporte_mensal: float,
    growth_rates: dict[str, float],
    volatilities: dict[str, float],
    meses: int = 12,
    override_initial_capital: float = None,
) -> dict:

    portfolio = copy.deepcopy(portfolio_inicial)
    
    if override_initial_capital is not None:
        current_val = sum(a["quantidade"] * a.get("preco_atual", 0) for a in portfolio)
        if current_val > 0:
            ratio = override_initial_capital / current_val
            for a in portfolio:
                a["quantidade"] *= ratio
        elif override_initial_capital > 0:
            pass # We could force-insert an asset but better to rely on aporte_mensal
            
    asset_universe_sim = copy.deepcopy(asset_universe)

    monthly_mu = {}
    monthly_sigma = {}
    for cls, annual_rate in growth_rates.items():
        monthly_mu[cls] = (1 + annual_rate) ** (1 / 12) - 1
        vol_anual = volatilities.get(cls, 0.0)
        monthly_sigma[cls] = vol_anual / (12**0.5)

    peak = 0.0
    max_dd = 0.0
    retornos_mensais = []
    caminho_patrimonio = []

    valor_anterior = sum(a["quantidade"] * a.get("preco_atual", 0) for a in portfolio)

    for mes in range(1, meses + 1):
        retorno_do_mes = {}
        for cls in monthly_mu:
            retorno_do_mes[cls] = random.gauss(monthly_mu[cls], monthly_sigma[cls])

        for ativo in portfolio:
            cls = ativo.get("classe") or ativo.get("segment") or "Outros"
            if cls in retorno_do_mes:
                ativo["preco_atual"] = ativo["preco_atual"] * (1 + retorno_do_mes[cls])
                if ativo["preco_atual"] < 0.01:
                    ativo["preco_atual"] = 0.01

        for ativo in asset_universe_sim:
            cls = ativo.get("classe") or ativo.get("segment") or "Outros"
            if cls in retorno_do_mes:
                ativo["preco_atual"] = ativo["preco_atual"] * (1 + retorno_do_mes[cls])
                if ativo["preco_atual"] < 0.01:
                    ativo["preco_atual"] = 0.01

        valor_antes_aporte = sum(a["quantidade"] * a.get("preco_atual", 0) for a in portfolio)

        if valor_anterior > 0:
            retorno_mensal = (valor_antes_aporte / valor_anterior) - 1.0
        else:
            retorno_mensal = 0.0

        retornos_mensais.append(retorno_mensal)

        if not portfolio:
            classe_prioritaria = max(target_allocation.items(), key=lambda x: x[1])[0]
        else:
            rebalanceamento = calculateRebalanceSuggestion(portfolio, target_allocation)
            classe_prioritaria = rebalanceamento.get("classe_prioritaria_para_aporte")

        sugestao = generateAporteSuggestion(
            classe_prioritaria=classe_prioritaria,
            portfolio_ativo=portfolio,
            asset_universe=asset_universe_sim,
            valor_aporte=aporte_mensal,
        )

        if "erro" not in sugestao and sugestao.get("quantidade", 0) > 0:
            ticker_alvo = sugestao["ticker"]
            qtd_comprada = sugestao["quantidade"]

            ativo_existente = next((a for a in portfolio if a["ticker"] == ticker_alvo), None)

            if ativo_existente:
                ativo_existente["quantidade"] += qtd_comprada
            else:
                ativo_universo = next((a for a in asset_universe_sim if a["ticker"] == ticker_alvo), None)
                if ativo_universo:
                    novo_ativo = {
                        "ticker": ticker_alvo,
                        "classe": ativo_universo["classe"],
                        "quantidade": qtd_comprada,
                        "preco_atual": ativo_universo["preco_atual"],
                    }
                    portfolio.append(novo_ativo)

        valor_total = sum(a["quantidade"] * a.get("preco_atual", 0) for a in portfolio)

        if valor_total > peak:
            peak = valor_total
        elif peak > 0:
            dd = (peak - valor_total) / peak
            if dd > max_dd:
                max_dd = dd

        valor_anterior = valor_total
        caminho_patrimonio.append(valor_total)

    return {
        "valor_final": round(valor_total, 2),
        "drawdown_maximo": max_dd,
        "retornos_mensais": retornos_mensais,
        "caminho_patrimonio": caminho_patrimonio,
    }


def simulate_monte_carlo(
    portfolio_inicial: list[dict],
    asset_universe: list[dict],
    target_allocation: dict[str, float],
    aporte_mensal: float,
    growth_rates: dict[str, float],
    volatilities: dict[str, float],
    meses: int = 12,
    simulacoes: int = 500,
    override_initial_capital: float = None,
) -> dict:

    valores_finais = []
    drawdowns = []
    cagrs = []
    volatilidades_anuais = []
    sharpes = []
    todos_caminhos = []

    anos = meses / 12.0
    risk_free_rate = 0.04

    temp_port = copy.deepcopy(portfolio_inicial)
    if override_initial_capital is not None:
        c_val = sum(a["quantidade"] * a.get("preco_atual", 0) for a in temp_port)
        if c_val > 0:
            ratio = override_initial_capital / c_val
            for a in temp_port:
                a["quantidade"] *= ratio

    valor_inicial = sum(a["quantidade"] * a.get("preco_atual", 0) for a in temp_port)
    total_investido = valor_inicial + (aporte_mensal * meses)

    for _ in range(simulacoes):
        resultado = simulate_stochastic(
            portfolio_inicial=portfolio_inicial,
            asset_universe=asset_universe,
            target_allocation=target_allocation,
            aporte_mensal=aporte_mensal,
            growth_rates=growth_rates,
            volatilities=volatilities,
            meses=meses,
            override_initial_capital=override_initial_capital,
        )

        vf = resultado["valor_final"]
        dd = resultado["drawdown_maximo"]
        rets_mensais = resultado["retornos_mensais"]
        caminho = resultado["caminho_patrimonio"]

        valores_finais.append(vf)
        drawdowns.append(dd)
        todos_caminhos.append(caminho)

        # CAGR approach corrected for performance over Initial Value or basic TWR approximation
        # Since we use DCA (Contributions), a pure CAGR on Total Invested dilutes the actual return.
        # Following Architect's prompt: calculate CAGR purely based on the Initial Value to isolate Time-Weighed Return,
        # OR use an adjusted metric. We will use the explicit formula suggested: (vf / valor_inicial) ** (1 / anos) - 1.
        # If valor_inicial is 0 (all from contributions), we default back to total_investido to avoid DivisionByZero.

        base_cagr = valor_inicial if valor_inicial > 0 else total_investido
        cagr = (vf / base_cagr) ** (1 / anos) - 1 if base_cagr > 0 and anos > 0 else 0.0
        cagrs.append(cagr)

        std_dev = 0.0
        if len(rets_mensais) > 1:
            media_matematica = sum(rets_mensais) / len(rets_mensais)
            var = sum((r - media_matematica) ** 2 for r in rets_mensais) / (len(rets_mensais) - 1)
            std_dev = var**0.5

        vol_anual = std_dev * (12**0.5)
        volatilidades_anuais.append(vol_anual)

        sharpe = (cagr - risk_free_rate) / vol_anual if vol_anual > 0 else 0.0
        sharpes.append(sharpe)

    valores_finais.sort()

    if simulacoes == 0:
        return {}

    media_valor_final = sum(valores_finais) / simulacoes
    mediana_valor_final = valores_finais[simulacoes // 2]
    percentil_10 = valores_finais[int(simulacoes * 0.1)]
    percentil_90 = valores_finais[int(simulacoes * 0.9)]

    prejuizos = sum(1 for v in valores_finais if v < total_investido)
    prob_prejuizo = prejuizos / simulacoes

    drawdown_medio = sum(drawdowns) / simulacoes
    media_cagr = sum(cagrs) / simulacoes
    media_vol = sum(volatilidades_anuais) / simulacoes
    media_sharpe = sum(sharpes) / simulacoes

    # Processar trajectory (caminhos agrupados por ano para o chart)
    trajectory = []
    if simulacoes > 0 and meses > 0:
        for m in range(meses):
            valores_mes = sorted([c[m] for c in todos_caminhos if len(c) > m])
            if not valores_mes:
                continue
            
            p10 = valores_mes[int(simulacoes * 0.1)]
            p50 = valores_mes[int(simulacoes * 0.5)]
            p90 = valores_mes[int(simulacoes * 0.9)]
            
            # Record yearly points or every 12th month
            if (m + 1) % 12 == 0:
                year = (m + 1) // 12
                # Calculate absolute invested capital up to this month
                invested = valor_inicial + (aporte_mensal * (m + 1))
                trajectory.append({
                    "year": year,
                    "p10": round(p10, 2),
                    "p50": round(p50, 2),
                    "p90": round(p90, 2),
                    "invested": round(invested, 2)
                })

    # Prefix with year 0
    trajectory.insert(0, {
        "year": 0,
        "p10": valor_inicial,
        "p50": valor_inicial,
        "p90": valor_inicial,
        "invested": valor_inicial
    })

    return {
        "media_valor_final": round(media_valor_final, 2),
        "mediana_valor_final": round(mediana_valor_final, 2),
        "percentil_10": round(percentil_10, 2),
        "percentil_90": round(percentil_90, 2),
        "probabilidade_prejuizo": round(prob_prejuizo, 4),
        "drawdown_medio": round(drawdown_medio, 4),
        "retorno_anualizado_medio": round(media_cagr, 4),
        "volatilidade_anualizada_media": round(media_vol, 4),
        "sharpe_ratio_medio": round(media_sharpe, 4),
        "trajectory": trajectory,
        "valores_finais_lista": valores_finais,
        "cagrs_lista": cagrs,
        "volatilidades_lista": volatilidades_anuais,
        "drawdowns_lista": drawdowns,
    }
