import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.simulador_service import simulate_with_growth
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
        "ETF": 0.08,   # 8% a.a.
        "ACAO": 0.12,  # 12% a.a. (Crescimento Agressivo do Valor)
        "FII": 0.06    # 6% a.a.  (Crescimento Baixo no Principal)
    }
    
    print("Iniciando Simulador c/ Distorção Temporal de Preços (12 Meses)...")
    print(f"Taxas Anuais: ETF 8%, ACAO 12%, FII 6%\n")
    
    resultado = simulate_with_growth(
        portfolio_inicial=portfolio_inicial,
        asset_universe=asset_universe,
        target_allocation=target_allocation,
        aporte_mensal=1000.0,
        growth_rates=growth_rates,
        meses=12
    )
    
    print("="*60)
    print(f"VALOR INICIAL: R$ 4000.00 -> VALOR FINAL: R$ {resultado['valor_final']:.2f}")
    print("="*60)
    
    print("\nComposição Final Após 12 Meses (Qtd x Novo Preço):")
    for ativo in resultado['composicao_final']:
        print(f"  - {ativo['ticker']} ({ativo['classe']:<4}): {ativo['quantidade']:>3} cotas -> R$ {ativo['quantidade'] * ativo['preco_atual']:.2f} (Preço Cota: R$ {ativo['preco_atual']:.2f})")
        
    print("\n" + "-"*60)
    print("Snapshot Mensal de Exemplo (MÊS 6 - Ponto Médio da Distorção):")
    print(json.dumps(resultado['historico_mensal'][5], indent=2))
    
    print("\n" + "-"*60)
    print("Snapshot Mensal de Exemplo (MÊS 12 - Equilíbrio vs Assimetria):")
    print(json.dumps(resultado['historico_mensal'][-1], indent=2))
    
    # Analyze the dominance during the path
    priorities_count = {"ETF": 0, "ACAO": 0, "FII": 0}
    for snap in resultado['historico_mensal']:
         priorities_count[snap["classe_prioritaria"]] += 1
         
    print("\nComportamento Disciplinar (Contagem de Meses que cada classe foi alvo de aporte):")
    print(json.dumps(priorities_count, indent=2))

if __name__ == "__main__":
    main()
