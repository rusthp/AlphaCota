import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.simulador_service import simulate_with_growth_and_shock
from core.profile_allocator import getTargetAllocation

def main():
    target_allocation = getTargetAllocation('moderado') 
    # Perfil Moderado -> ETF: 50%, ACAO: 30%, FII: 20%
    
    asset_universe = [
        {'ticker': 'IVVB11', 'classe': 'ETF',  'ativo': True, 'preco_atual': 250.0},
        {'ticker': 'BNDX11', 'classe': 'ETF',  'ativo': True, 'preco_atual': 100.0},
        {'ticker': 'BBSE3',  'classe': 'ACAO', 'ativo': True, 'preco_atual': 30.0},
        {'ticker': 'WEGE3',  'classe': 'ACAO', 'ativo': True, 'preco_atual': 40.0},
        {'ticker': 'MXRF11', 'classe': 'FII',  'ativo': True, 'preco_atual': 10.0},
        {'ticker': 'HGLG11', 'classe': 'FII',  'ativo': True, 'preco_atual': 160.0},
    ]
    
    portfolio_inicial = [
        {'ticker': 'IVVB11', 'classe': 'ETF', 'quantidade': 10, 'preco_atual': 250.0}, # R$ 2500
        {'ticker': 'BBSE3',  'classe': 'ACAO','quantidade': 50, 'preco_atual': 30.0},  # R$ 1500
    ]
    
    growth_rates = {
        "ETF": 0.08,   # 8% a.a. normalidade
        "ACAO": 0.12,  # 12% a.a. 
        "FII": 0.06    # 6% a.a. 
    }
    
    shock_event = {
        "mes": 6,
        "impacto": {
            "ETF": -0.10,
            "ACAO": -0.20,
            "FII": -0.05
        }
    }
    
    print("Iniciando Simulador de Choque de Mercado (-20% Ações no Mês 6)...")
    
    resultado = simulate_with_growth_and_shock(
        portfolio_inicial=portfolio_inicial,
        asset_universe=asset_universe,
        target_allocation=target_allocation,
        aporte_mensal=1000.0,
        growth_rates=growth_rates,
        shock_event=shock_event,
        meses=12
    )

    print("\n[MÊS 5 - PRÉ-CHOQUE] (Distribuição da Carteira Plácida):")
    snap5 = resultado['historico_mensal'][4]
    print(json.dumps(snap5['distribuicao_percentual'], indent=2))
    
    print("\n[MÊS 6 - CHOQUE] (Distribuição Após Derretimento):")
    snap6 = resultado['historico_mensal'][5]
    print(json.dumps(snap6['distribuicao_percentual'], indent=2))
    print(f">> Aporte do Mês 6 Foi Direcionado Para: {snap6['classe_prioritaria']} (ticker: {snap6['operacao']['ticker']})")
    
    print("\n[MÊS 7 - REAÇÃO PÓS CRISE] (Distribuição no Início do Rebote):")
    snap7 = resultado['historico_mensal'][6]
    print(json.dumps(snap7['distribuicao_percentual'], indent=2))
    
    print("\n" + "-"*60)
    # Analyze the dominance during the path
    priorities_count = {"ETF": 0, "ACAO": 0, "FII": 0}
    for snap in resultado['historico_mensal']:
         priorities_count[snap["classe_prioritaria"]] += 1
         
    print(f"VALOR FINAL ALCANÇADO: R$ {resultado['valor_final']:.2f}")
    print("\nComportamento Disciplinar Final (Classes priorizadas nos 12 meses):")
    print(json.dumps(priorities_count, indent=2))

if __name__ == "__main__":
    main()
