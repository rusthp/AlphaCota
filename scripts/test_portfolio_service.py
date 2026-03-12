import os
import sys

# Corrige o path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from services.portfolio_service import run_full_cycle
from infra.database import get_portfolio_snapshots
import json

def test_service_cycle():
    print("Iniciando Teste do Portfolio Service...")
    
    # Simula dados externos (o banco já está com BBSE3 e MXRF11 que inserimos no DB manual teste)
    precos_atuais = {
        "BBSE3": 35.0,
        "MXRF11": 10.5
    }

    alocacao_alvo = {
        "BBSE3": 0.50,
        "MXRF11": 0.50
    }
    
    try:
        report = run_full_cycle(
            precos_atuais=precos_atuais,
            alocacao_alvo=alocacao_alvo,
            aporte_mensal=500.0,
            taxa_anual_esperada=0.10,
            renda_alvo_anual=120000.0
        )
        print("\n--- RETORNO DO SERVICE (PAYLOAD) ---")
        print(json.dumps(report, indent=2))
        
        print("\n--- CONFIRMANDO GRAVAÇÃO DO SNAPSHOT AUTOMATICO ---")
        snapshots = get_portfolio_snapshots()
        # O snapshot salvo agora deverá ser o último da lista
        print(snapshots[-1] if snapshots else "Nenhum snapshot encontrado.")
        
    except Exception as e:
        print(f"ERRO: {e}")

if __name__ == "__main__":
    test_service_cycle()
