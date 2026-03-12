import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.allocation_pipeline import run_allocation_pipeline

def main():
    
    # Simula um Dicionario de Ativos (3 Acoes, 2 ETFs, 2 FIIs)
    # Alguns com "faca caindo", risco de falencia e excelente momento tecnico.
    
    mock_assets = [
        # OTIMOS FUNDAMENTOS, MOMENTO ALTA (VAI SER PESO PESADO NAS ACOES)
        {
            "ticker": "WEGE3",
            "classe": "ACAO",
            "preco_atual": 50.0,
            "pl": 15.0, "pvp": 3.0, "roe": 25.0, "roa": 15.0,
            "revenue_growth": 15.0, "earnings_growth": 20.0,
            "debt_to_equity": 0.5, "current_ratio": 2.5,
            "total_assets": 10000.0, "total_liabilities": 4000.0,
            "working_capital": 3000.0, "retained_earnings": 5000.0,
            "ebit": 1500.0, "market_value_equity": 6000.0, "revenue": 8000.0,
            "historical_prices": [30, 32, 35, 38, 40, 42, 45, 46, 48, 48, 49, 50]
        },
        # EXCELENTES FUNDAMENTOS, FACA CAINDO (VAI SOFRER PENALTI DE -20%)
        {
            "ticker": "VALE3",
            "classe": "ACAO",
            "preco_atual": 60.0,
            "pl": 5.0, "pvp": 1.1, "roe": 30.0, "roa": 18.0,
            "revenue_growth": 10.0, "earnings_growth": 5.0,
            "debt_to_equity": 0.4, "current_ratio": 2.0,
            "total_assets": 50000.0, "total_liabilities": 20000.0,
            "working_capital": 10000.0, "retained_earnings": 20000.0,
            "ebit": 8000.0, "market_value_equity": 30000.0, "revenue": 40000.0,
            "historical_prices": [90, 88, 85, 80, 78, 75, 70, 68, 65, 62, 61, 60]
        },
        # FALENCIA EMINENTE (VAI SER ELIMINADO PELO ALTMAN Z <= 1.81)
        {
            "ticker": "OIBR3",
            "classe": "ACAO",
            "preco_atual": 1.0,
            "pl": -5.0, "pvp": -0.5, "roe": -50.0, "roa": -20.0,
            "revenue_growth": -30.0, "earnings_growth": -80.0,
            "debt_to_equity": 5.0, "current_ratio": 0.5,
            "total_assets": 1000.0, "total_liabilities": 5000.0, # Z-Score negativo e falido
            "working_capital": -1000.0, "retained_earnings": -4000.0,
            "ebit": -500.0, "market_value_equity": 200.0, "revenue": 500.0,
            "historical_prices": [5, 4, 3, 2, 1, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 1.0] # Agrupamento falso
        },
        # ETFs PARA BALANCEAR RENDIMENTO
        {
            "ticker": "IVVB11",
            "classe": "ETF",
            "preco_atual": 250.0,
            "pl": 15.0, "pvp": 2.0, "roe": 20.0, "roa": 12.0,
            "revenue_growth": 10.0, "earnings_growth": 12.0,
            "debt_to_equity": 0.5, "current_ratio": 2.5,
            "total_assets": 50000.0, "total_liabilities": 10000.0,
            "working_capital": 5000.0, "retained_earnings": 10000.0,
            "ebit": 4000.0, "market_value_equity": 60000.0, "revenue": 10000.0,
            "historical_prices": [200, 205, 210, 215, 220, 225, 230, 235, 240, 245, 248, 250]
        },
        # FII EXCELENTE
        {
            "ticker": "HGLG11",
            "classe": "FII",
            "preco_atual": 160.0,
            "pl": 10.0, "pvp": 1.0, "roe": 12.0, "roa": 10.0,
            "revenue_growth": 8.0, "earnings_growth": 8.0,
            "debt_to_equity": 0.1, "current_ratio": 5.0,
            "total_assets": 5000.0, "total_liabilities": 500.0,
            "working_capital": 1000.0, "retained_earnings": 1000.0,
            "ebit": 800.0, "market_value_equity": 6000.0, "revenue": 1000.0,
            "historical_prices": [150, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 160] # Constante (Momentum morno mas positivo)
        }
    ]

    # Simula um Dicionario de Ativos (3 Acoes, 2 ETFs, 2 FIIs)
    # Alguns com "faca caindo", risco de falencia e excelente momento tecnico.
    
    import sqlite3
    from core.state_repository import init_db
    
    # Inicia Banco em Memoria para o Teste
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    
    # Carteira Hipotetica Atual de Investidor (Perto do alvo mas com ruido)
    current_portfolio = {
        "IVVB11": 0.50,
        "WEGE3": 0.23, # O Alvo sera 30%, temos um Drift > 5% (Gatilho de Rebalance)
        "HGLG11": 0.27 # O Alvo sera 20%, Drift > 5%
    }
    
    # Testando o Orquestrador para um Perfil "Moderado"
    # Onde ETF=0.5, ACAO=0.3, FII=0.2
    print("\n--- INICIANDO PIPELINE DE ALOCACAO MAESTRO (PERFIL MODERADO) ---")
    
    pipeline_res = run_allocation_pipeline(
        connection=conn,
        user_profile="moderado", 
        assets_data=mock_assets,
        current_portfolio=current_portfolio, 
        score_threshold=60.0
    )
    
    print(f"\n[ESTATISTICAS GERAIS E OPERACIONAIS]")
    print(f"Ativos Analisados (Mercado Total): {len(mock_assets)}")
    print(f"Sistema Disparou Rebalanceamento Automatico? {'[SIM] Rebalanceamento Ativado' if pipeline_res['rebalance_executed'] else '[NAO] Ruido Ignorado'}")
    print(f"Desvios de Carteira Identificados: {pipeline_res['weight_drift']}")
    
    print("\n[ALOCACAO OTIMIZADA POR SCORE (Etapa 2)]")
    for ticker, peso in pipeline_res['allocations'].items():
        print(f"Ticker: {ticker} -> Alvo Direcionado: {peso * 100}% da Carteira Total")
    
    print("\n[RISK SIMULATION E PROJETO FIRE (Etapas 3 e 4)]")
    risk = pipeline_res['risk_projection']
    print(f"Valor Mediano Esperado (5 Anos): R$ {risk['median_projection']:.2f}")
    print(f"Probabilidade de Lucro Final Absoluto: {risk['probability_of_profit']*100:.1f}%")
    print(f"Drawdown Medio durante a Caminhada: {risk['avg_drawdown']*100:.1f}%")
    print(f"Tempo Projetado ate a Meta FIRE (Independencia): {pipeline_res['fire_projection']['years_to_fire']} Anos")
    
    print("\n[AUDITORIA INSTITUCIONAL E EXPLICABILIDADE MATEMATICA (Etapa 7)]")
    import json
    print(json.dumps(pipeline_res['explanation'], indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
