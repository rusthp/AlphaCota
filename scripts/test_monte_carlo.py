import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.simulador_service import simulate_monte_carlo
from core.profile_allocator import getTargetAllocation

def main():
    perfis = ["conservador", "moderado", "agressivo"]
    
    portfolio_inicial = [
        {'ticker': 'IVVB11', 'classe': 'ETF', 'quantidade': 10, 'preco_atual': 250.0}, # R$ 2500
        {'ticker': 'BBSE3',  'classe': 'ACAO','quantidade': 50, 'preco_atual': 30.0},  # R$ 1500
    ]
    # Total inicial = R$ 4000
    
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
    
    # Adicionando desvio padrao como volatilidade anual das classes
    volatilities = {
        "ETF": 0.15,  # 15% a.a de vol
        "ACAO": 0.30, # 30% a.a de vol (Eixo critico)
        "FII": 0.10   # 10% a.a de vol
    }
    
    simulations_count = 500
    meses_simulacao = 60 # Ampliando pra 5 anos para as forças gaussianas atuarem pesadamente

    print(f"Iniciando Engenharia de Risco: Monte Carlo ({simulations_count} Simulações / {meses_simulacao} Meses)...\n")
    print(f"Total Investido Projetado: R$ {4000 + (1000 * meses_simulacao):.2f}\n")
    
    for perfil in perfis:
        target_allocation = getTargetAllocation(perfil)
        
        resultado = simulate_monte_carlo(
            portfolio_inicial=portfolio_inicial,
            asset_universe=asset_universe,
            target_allocation=target_allocation,
            aporte_mensal=1000.0,
            growth_rates=growth_rates,
            volatilities=volatilities,
            meses=meses_simulacao,
            simulacoes=simulations_count
        )
        
        print(f"[{perfil.upper()}]")
        print(f"  - Média de Valor Final: R$ {resultado['media_valor_final']:.2f}")
        print(f"  - Mediana (Cenário Central): R$ {resultado['mediana_valor_final']:.2f}")
        print(f"  - P90 (Otimista 10%): R$ {resultado['percentil_90']:.2f}")
        print(f"  - P10 (Pessimista 10%): R$ {resultado['percentil_10']:.2f}")
        print(f"  - Probabilidade de Prejuízo Absoluto: {resultado['probabilidade_prejuizo']*100:.2f}%")
        print(f"  - Drawdown Médio Suportado: {resultado['drawdown_medio']*100:.2f}%")
        print(f"  - Retorno Anual. Médio (CAGR): {resultado['retorno_anualizado_medio']*100:.2f}%")
        print(f"  - Volatilidade Anual. Média: {resultado['volatilidade_anualizada_media']*100:.2f}%")
        print(f"  - Sharpe Ratio Médio (Rf=4%): {resultado['sharpe_ratio_medio']:.4f}")
        print("-" * 50)
        
if __name__ == "__main__":
    main()
