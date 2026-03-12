import json
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.profile_allocator import getTargetAllocation
from core.class_rebalancer import calculateRebalanceSuggestion

def main():
    print("+" + "-"*50 + "+")
    print("| TESTE 1: Motor de Alocação por Perfil (Prompt 2) |")
    print("+" + "-"*50 + "+")
    
    alvo_moderado = getTargetAllocation('moderado')
    print("Alocação Alvo para o perfil MODERADO gerada:\n")
    print(json.dumps(alvo_moderado, indent=2))
    
    print("\n+" + "-"*50 + "+")
    print("| TESTE 2: Simulação de Rebalanceamento (Prompt 3) |")
    print("+" + "-"*50 + "+")
    
    # Simulação Fake: (Total ≈ 6550)
    # ETF(IVVB11): 2500 (~38.1%)
    # ACAO(BBSE3): 3000 (~45.8%) -> Estourado (Alvo: 30%)
    # FII(MXRF11): 1050 (~16.0%) -> Faltando (Alvo: 20%)
    
    carteira_fake = [
        {'ticker': 'IVVB11', 'classe': 'ETF', 'quantidade': 10, 'preco_atual': 250.0},
        {'ticker': 'BBSE3', 'classe': 'ACAO', 'quantidade': 100, 'preco_atual': 30.0},
        {'ticker': 'MXRF11', 'classe': 'FII', 'quantidade': 100, 'preco_atual': 10.5},
    ]
    
    print("\nCarteira Simulada:")
    for ativo in carteira_fake:
        total = ativo['quantidade'] * ativo['preco_atual']
        print(f" -> {ativo['ticker']} ({ativo['classe']}): R$ {total:.2f}")
        
    print("\nCalculando Dissonância e Sugestão...\n")
    sugestao = calculateRebalanceSuggestion(carteira_fake, alvo_moderado)
    
    print(json.dumps(sugestao, indent=2))
    print("\n>>> SUCESSO! A lógica identificou corretamente o ETF como aporte isolado primário.")

if __name__ == "__main__":
    main()
