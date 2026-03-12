import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.simulador_service import simulate_12_months
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
    
    # Iniciamos com carteira sem FII, forçando o sistema a corrigir as proporções
    portfolio_inicial = [
        {'ticker': 'IVVB11', 'classe': 'ETF', 'quantidade': 10, 'preco_atual': 250.0}, # R$ 2500 (62.5%)
        {'ticker': 'BBSE3',  'classe': 'ACAO','quantidade': 50, 'preco_atual': 30.0},  # R$ 1500 (37.5%)
    ]
    
    print("Iniciando Simulador de 12 Meses (Disciplina: Moderado, Aporte Mensal: R$ 1000,00)...\n")
    resultado = simulate_12_months(
        portfolio_inicial=portfolio_inicial,
        asset_universe=asset_universe,
        target_allocation=target_allocation,
        aporte_mensal=1000.0,
        meses=12
    )
    
    print("="*60)
    print(f"VALOR INICIAL: R$ 4000.00 -> VALOR FINAL: R$ {resultado['valor_final']:.2f}")
    print("="*60)
    
    print("\nComposição Final Após 12 Meses de Aportes Disciplinados:")
    for ativo in resultado['composicao_final']:
        print(f"  - {ativo['ticker']} ({ativo['classe']:<4}): {ativo['quantidade']:>3} cotas -> R$ {ativo['quantidade'] * ativo['preco_atual']:.2f}")
        
    print("\n" + "-"*60)
    print("Snapshot Mensal de Exemplo (MÊS 1 - Detecção da falta de FIIs):")
    print(json.dumps(resultado['historico_mensal'][0], indent=2))
    
    print("\n" + "-"*60)
    print("Snapshot Mensal de Exemplo (MÊS 12 - Equilíbrio atingido):")
    print(json.dumps(resultado['historico_mensal'][-1], indent=2))

if __name__ == "__main__":
    main()
