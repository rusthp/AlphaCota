import json
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.smart_aporte import generateAporteSuggestion

def main():
    print("+" + "-"*50 + "+")
    print("| TESTE: Aporte Estratégico & Universo de Ativos |")
    print("+" + "-"*50 + "+")
    
    asset_universe = [
        {'ticker': 'IVVB11', 'classe': 'ETF', 'nome': 'iShares S&P 500', 'ativo': True, 'preco_atual': 250.0},
        {'ticker': 'BNDX11', 'classe': 'ETF', 'nome': 'Bonds Globais', 'ativo': True, 'preco_atual': 100.0},
        {'ticker': 'BBSE3', 'classe': 'ACAO', 'nome': 'BB Seguridade', 'ativo': True, 'preco_atual': 30.0},
        {'ticker': 'ITUB4', 'classe': 'ACAO', 'nome': 'Itau', 'ativo': True, 'preco_atual': 35.0},
        {'ticker': 'WEGE3', 'classe': 'ACAO', 'nome': 'WEG S.A.', 'ativo': True, 'preco_atual': 40.0},
        {'ticker': 'MXRF11', 'classe': 'FII', 'nome': 'Maxi Renda', 'ativo': True, 'preco_atual': 10.5},
        {'ticker': 'HGLG11', 'classe': 'FII', 'nome': 'CSHG Logistica', 'ativo': True, 'preco_atual': 160.0},
    ]

    # Cenário 1: ZERO ativos na classe FII
    carteira_1 = [
        {'ticker': 'IVVB11', 'classe': 'ETF', 'quantidade': 10, 'preco_atual': 250.0},
        {'ticker': 'BBSE3', 'classe': 'ACAO', 'quantidade': 100, 'preco_atual': 30.0},
    ]
    print("\n--- Cenário 1: Subalocado em FII (nenhum ativo na carteira) ---")
    sugestao_1 = generateAporteSuggestion('FII', carteira_1, asset_universe, valor_aporte=500.0)
    print(json.dumps(sugestao_1, indent=2))

    # Cenário 2: 1 ativo na classe FII
    carteira_2 = [
        {'ticker': 'MXRF11', 'classe': 'FII', 'quantidade': 100, 'preco_atual': 10.5},
    ]
    print("\n--- Cenário 2: Subalocado em FII (apenas 1 ativo na carteira) ---")
    sugestao_2 = generateAporteSuggestion('FII', carteira_2, asset_universe, valor_aporte=500.0)
    print(json.dumps(sugestao_2, indent=2))
    
    # Cenário 3: 2 ativos na classe ACAO (precisa reforçar o mais fraco)
    carteira_3 = [
        {'ticker': 'BBSE3', 'classe': 'ACAO', 'quantidade': 100, 'preco_atual': 30.0}, # R$ 3000
        {'ticker': 'WEGE3', 'classe': 'ACAO', 'quantidade': 20, 'preco_atual': 40.0},  # R$ 800
    ]
    print("\n--- Cenário 3: Subalocado em ACAO (2 ativos, reforçar o menor peso) ---")
    sugestao_3 = generateAporteSuggestion('ACAO', carteira_3, asset_universe, valor_aporte=500.0)
    print(json.dumps(sugestao_3, indent=2))


if __name__ == "__main__":
    main()
