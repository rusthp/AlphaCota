from core.portfolio_engine import calculate_rebalance_suggestion
import json

def test_rebalance():
    ativos = [
        {"ticker": "BBSE3", "valor": 5000},
        {"ticker": "MXRF11", "valor": 3000},
    ]

    alvo = {
        "BBSE3": 0.50,
        "MXRF11": 0.50
    }

    print("Testando rebalanceamento com aporte de 300")
    try:
        resultado = calculate_rebalance_suggestion(
            ativos_atuais=ativos,
            alocacao_alvo=alvo,
            aporte_mensal=300.0
        )
        print("Saída do Motor de Rebalanço:")
        print(json.dumps(resultado, indent=2))
    except Exception as e:
        print(f"ERRO: {e}")

if __name__ == "__main__":
    test_rebalance()
