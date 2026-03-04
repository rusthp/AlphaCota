# services/allocation_pipeline.py
from core.quant_engine import evaluate_company, calculate_altman_z, classify_bankruptcy_risk
from core.score_engine import calculate_alpha_score, DEFAULT_WEIGHTS
from core.profile_allocator import getTargetAllocation


def build_elite_universe(
    assets_data: list[dict],
    score_threshold: float = 5.0,
    weights: dict[str, float] | None = None,
) -> list[dict]:
    """
    Filtra o universo de ativos mantendo apenas aqueles com Alpha Score
    suficiente e fora de risco iminente de falência (Altman Z > 1.81).

    Usa o novo score_engine (fórmula matemática explícita com pesos configuráveis)
    para o ranking, e o quant_engine apenas para o filtro de falência via Altman Z.

    Args:
        assets_data (list[dict]): Lista de ativos com indicadores fundamentalistas.
            Campos esperados: 'ticker', 'classe', 'preco_atual', 'dividend_yield',
            'dividend_consistency', 'pvp', 'debt_ratio', 'vacancy_rate',
            'revenue_growth_12m', 'earnings_growth_12m', e dados do Altman Z.
        score_threshold (float): Alpha Score mínimo (escala 0–10). Default: 5.0.
        weights (dict | None): Pesos do score engine. Default: DEFAULT_WEIGHTS.

    Returns:
        list[dict]: Ativos que passaram no filtro, com 'alpha_score' e sub-scores injetados.
    """
    elite = []

    for asset in assets_data:
        ticker = asset.get("ticker", "UNKNOWN")

        # ── Filtro 1: Risco de falência via Altman Z (proteção fundamental) ──
        z_score = calculate_altman_z(asset)
        risk_class = classify_bankruptcy_risk(z_score)
        if risk_class == "Alto Risco de Falência":
            continue

        # ── Filtro 2: Alpha Score pelo novo score_engine ──
        score_result = calculate_alpha_score(
            dividend_yield=asset.get("dividend_yield", 0.0),
            dividend_consistency=asset.get("dividend_consistency", 5.0),
            pvp=asset.get("pvp", 1.0),
            debt_ratio=asset.get("debt_ratio", 0.5),
            vacancy_rate=asset.get("vacancy_rate", 0.0),
            revenue_growth_12m=asset.get("revenue_growth_12m", 0.0),
            earnings_growth_12m=asset.get("earnings_growth_12m", 0.0),
            weights=weights,
        )

        if score_result["alpha_score"] >= score_threshold:
            asset_elite = asset.copy()
            asset_elite["alpha_score"]      = score_result["alpha_score"]
            asset_elite["income_score"]     = score_result["income_score"]
            asset_elite["valuation_score"]  = score_result["valuation_score"]
            asset_elite["risk_score"]       = score_result["risk_score"]
            asset_elite["growth_score"]     = score_result["growth_score"]
            asset_elite["altman_z_score"]   = round(z_score, 3)
            asset_elite["risk_classification"] = risk_class
            # Mantém compatibilidade com código legado que usa final_score
            asset_elite["final_score"]      = score_result["alpha_score"] * 10
            elite.append(asset_elite)

    return elite


def optimize_with_constraints(elite_universe: list[dict], class_constraints: dict[str, float]) -> dict[str, float]:
    """
    Distribui os pesos percentuais proporcionalmente aos Scores dos ativos,
    garantindo rigidamente que a soma final de cada Classe respeite o Perfil do Investidor.
    """
    allocation = {}
    
    # Agrupa os ativos de elite por classe
    assets_by_class = {}
    for asset in elite_universe:
        cls = asset.get("classe", "UNKNOWN")
        if cls not in assets_by_class:
            assets_by_class[cls] = []
        assets_by_class[cls].append(asset)
        
    # Aplica o calculo hibrido (peso_i = (score_i / sum(score)) * peso_classe)
    for cls, target_weight in class_constraints.items():
        class_assets = assets_by_class.get(cls, [])
        
        if not class_assets:
            continue
            
        total_class_score = sum(a["final_score"] for a in class_assets)
        
        # Se por alguma anomalia o score total for 0, dividimos igualmente
        if total_class_score <= 0:
            equal_weight = target_weight / len(class_assets)
            for a in class_assets:
                allocation[a["ticker"]] = round(equal_weight, 4)
            continue
            
        for asset in class_assets:
            ticker = asset["ticker"]
            score = asset["final_score"]
            asset_weight = (score / total_class_score) * target_weight
            allocation[ticker] = round(asset_weight, 4)
            
    return allocation

import datetime

def run_allocation_pipeline(
    connection,
    user_profile: str, 
    assets_data: list[dict], 
    current_portfolio: dict[str, float] | None = None,
    aporte_mensal: float = 1000.0, 
    meses_simulacao: int = 60, 
    score_threshold: float = 60.0
) -> dict:
    """
    Orquestra o screening quantamental, alocação de portfólio,
    decisão de rebalanceamento, persistência e auditoria.
    """
    from services.simulador_service import simulate_monte_carlo
    from core.fire_engine import calculate_years_to_fire
    from core.state_repository import save_snapshot, save_allocations, save_scores, get_last_snapshot
    from services.rebalance_engine import calculate_weight_drift, detect_universe_change, should_rebalance
    from services.explain_engine import generate_portfolio_explanation
    
    # 1. Obter Restrições do Perfil e Filtrar Universo (Etapa 1 - Quantamental Screening)
    class_constraints = getTargetAllocation(user_profile)
    elite_universe = build_elite_universe(assets_data, score_threshold)
    
    if not elite_universe:
        return {"error": "Nenhum ativo sobreviveu ao Screening Quantamental (Threshold ou Falencia)."}
    
    # 2. Otimizar Proporcionalmente (Etapa 2 - Class-Constrained Optimizer)
    allocation = optimize_with_constraints(elite_universe, class_constraints)
    
    # Formatação estendida para o Simulador Monte Carlo
    selected_assets_structured = []
    valor_total_hipotetico = 10000.0
    
    for asset in elite_universe:
        ticker = asset["ticker"]
        if ticker in allocation:
            peso_alvo = allocation[ticker]
            preco = asset.get("preco_atual", 10.0)
            qtd = (valor_total_hipotetico * peso_alvo) / preco
            selected_assets_structured.append({
                "ticker": ticker,
                "classe": asset["classe"],
                "quantidade": max(1, int(qtd)),
                "preco_atual": preco
            })
            
    # 3. Risk Simulation Layer (Etapa 3 - Monte Carlo)
    growth_rates = {"ETF": 0.08, "ACAO": 0.12, "FII": 0.06}
    volatilities = {"ETF": 0.15, "ACAO": 0.30, "FII": 0.10}
    
    risk_metrics = simulate_monte_carlo(
        portfolio_inicial=selected_assets_structured,
        asset_universe=elite_universe,
        target_allocation=class_constraints,
        aporte_mensal=aporte_mensal,
        growth_rates=growth_rates,
        volatilities=volatilities,
        meses=meses_simulacao,
        simulacoes=500
    )
    
    # 4. FIRE Projection (Etapa 4 - Tempo ate Independencia)
    mediana = risk_metrics["mediana_valor_final"]
    meta_exemplo_anual = 60000.0
    
    try:
        fire_status = calculate_years_to_fire(
            patrimonio_atual=valor_total_hipotetico, 
            aporte_mensal=aporte_mensal, 
            taxa_anual=risk_metrics["retorno_anualizado_medio"], 
            renda_alvo_anual=meta_exemplo_anual
        )
    except ValueError:
        fire_status = "> 200 Anos (Inalcançável)"
        
    # 5. Rebalance Decision (Etapa 5 - Derivação de Pesos e Quebra de Universo)
    rebalance_flag = True
    drift = {}
    
    if current_portfolio is not None:
        drift = calculate_weight_drift(current_portfolio, allocation)
        
        old_tickers = set(current_portfolio.keys())
        new_tickers = set(allocation.keys())
        
        rebalance_flag = (
            detect_universe_change(old_tickers, new_tickers) or
            should_rebalance(drift, threshold=0.05)
        )
        
    # 6. Persistência de Estado (Etapa 6 - Commit Relacional SQLite)
    if rebalance_flag and connection:
        timestamp = datetime.datetime.now().isoformat()
        
        snap_data = {
            "timestamp": timestamp,
            "investor_profile": user_profile,
            "expected_return": risk_metrics["retorno_anualizado_medio"],
            "monte_carlo_median": mediana
        }
        snapshot_id = save_snapshot(connection, snap_data)
        
        allocs_to_save, scores_to_save = [], []
        for asset in elite_universe:
            ticker = asset["ticker"]
            
            # Scores da varredura geral
            scores_to_save.append({
                "timestamp": timestamp,
                "ticker": ticker,
                "fundamental_score": asset.get("quality_score", 0.0),
                "momentum_score": asset.get("momentum_score", 0.0),
                "final_score": asset["final_score"],
                "altman_z": asset.get("altman_z_score", 0.0)
            })
            
            # Alocações do portfólio reduzido
            if ticker in allocation:
                allocs_to_save.append({
                    "ticker": ticker,
                    "asset_class": asset["classe"],
                    "weight": allocation[ticker],
                    "score": asset["final_score"]
                })
                
        save_scores(connection, scores_to_save)
        save_allocations(connection, snapshot_id, allocs_to_save)
        
    # 7. Explain Engine (Etapa 7 - Auditoria Determinística)
    explain_allocs = []
    for asset in elite_universe:
        ticker = asset["ticker"]
        if ticker in allocation:
            explain_allocs.append({
                "ticker": ticker,
                "classe": asset["classe"],
                "final_score": asset["final_score"],
                "momentum_score": asset.get("momentum_score", 0.0),
                "altman_z_score": asset.get("altman_z_score", 0.0),
                "peso_alvo": allocation[ticker]
            })
            
    explanation = generate_portfolio_explanation(
        allocations=explain_allocs,
        user_profile=user_profile,
        monte_carlo_median=mediana,
        years_to_fire=fire_status,
        class_constraints=class_constraints
    )
            
    return {
        "rebalance_executed": rebalance_flag,
        "allocations": allocation,
        "weight_drift": drift,
        "risk_projection": {
            "expected_return": risk_metrics["retorno_anualizado_medio"],
            "median_projection": mediana,
            "probability_of_profit": 1.0 - risk_metrics["probabilidade_prejuizo"],
            "avg_drawdown": risk_metrics["drawdown_medio"]
        },
        "fire_projection": {"years_to_fire": fire_status},
        "explanation": explanation
    }
