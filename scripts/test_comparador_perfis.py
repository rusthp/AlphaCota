import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.simulador_service import compare_profiles_under_scenario

def main():
    perfis = ["conservador", "moderado", "agressivo"]
    
    portfolio_inicial = [
        {'ticker': 'IVVB11', 'classe': 'ETF', 'quantidade': 10, 'preco_atual': 250.0}, # R$ 2500
        {'ticker': 'BBSE3',  'classe': 'ACAO','quantidade': 50, 'preco_atual': 30.0},  # R$ 1500
    ]
    # Total = R$ 4000
    
    asset_universe = [
        {'ticker': 'IVVB11', 'classe': 'ETF',  'ativo': True, 'preco_atual': 250.0},
        {'ticker': 'BNDX11', 'classe': 'ETF',  'ativo': True, 'preco_atual': 100.0},
        {'ticker': 'BBSE3',  'classe': 'ACAO', 'ativo': True, 'preco_atual': 30.0},
        {'ticker': 'WEGE3',  'classe': 'ACAO', 'ativo': True, 'preco_atual': 40.0},
        {'ticker': 'MXRF11', 'classe': 'FII',  'ativo': True, 'preco_atual': 10.0},
        {'ticker': 'HGLG11', 'classe': 'FII',  'ativo': True, 'preco_atual': 160.0},
    ]
    
    growth_rates = {
        "ETF": 0.08,   
        "ACAO": 0.12,  
        "FII": 0.06    
    }
    
    shock_event = {
        "mes": 6,
        "impacto": {
            "ETF": -0.10,
            "ACAO": -0.20,
            "FII": -0.05
        }
    }
    
    print("Iniciando Laboratório Estratégico de Perfis sob Choque...\n")
    print(f"Cenário: Ações caindo -20%, ETFs caindo -10%, FIIs caindo -5% no Mês 6.")
    
    resultado = compare_profiles_under_scenario(
        perfis=perfis,
        portfolio_inicial=portfolio_inicial,
        asset_universe=asset_universe,
        aporte_mensal=1000.0,
        growth_rates=growth_rates,
        shock_event=shock_event,
        meses=12
    )

    print("="*60)
    print("RELATÓRIO COMPARATIVO DE RESILIÊNCIA:")
    print("="*60)
    
    for perfil, metricas in resultado.items():
        print(f"\n[{perfil.upper()}]")
        print(f"  - Valor Final (12m): R$ {metricas['valor_final']:.2f}")
        print(f"  - Maior Queda (Drawdown): {metricas['maior_drawdown_percentual']*100:.2f}%")
        print(f"  - Meses p/ Recuperação: {metricas['meses_para_recuperacao']} meses")
        print(f"  - Desvio Máximo da Meta: {metricas['desvio_maximo_da_meta']*100:.2f} p.p.")
        
    print("\n" + "="*60)

if __name__ == "__main__":
    main()
