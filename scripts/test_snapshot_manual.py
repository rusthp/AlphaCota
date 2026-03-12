import os
import sys

# Corrige o path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from infra.database import init_db, save_portfolio_snapshot, get_portfolio_snapshots

def test_snapshot():
    print("Iniciando banco de dados para snapshots...")
    init_db()

    # Simulando um report JSON retornado pelo decision_engine
    mock_report = {
        "resumo_carteira": {
            "valor_total": 5600.0,
            "lucro_prejuizo_total": 600.0,
            "lucro_prejuizo_percentual_total": 12.0
        },
        "renda_passiva": {
            "renda_total": 55.0,
            "yield_percentual": 0.98
        },
        "fogo_financeiro": {
            "patrimonio_necessario": 1200000.0,
            "anos_estimados": 30.7
        },
        "rebalanceamento": {
            "sugestao": [
                {"ticker": "MXRF11", "valor_aportar": 500.0}
            ]
        }
    }

    print("Salvando snapshot mockado...")
    save_portfolio_snapshot(mock_report)

    print("\n--- SNAPSHOTS SALVOS NO HISTÓRICO ---")
    snapshots = get_portfolio_snapshots()
    for s in snapshots:
        print(s)

if __name__ == "__main__":
    test_snapshot()
