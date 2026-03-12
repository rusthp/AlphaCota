from core.income_engine import calculate_income_metrics
import json

def test_income():
    proventos = [
        {"ticker": "BBSE3", "valor": 50.0},
        {"ticker": "MXRF11", "valor": 80.0},
    ]

    valor_total_carteira = 10000.0

    print("Testando Income Engine")
    try:
        resultado = calculate_income_metrics(
            proventos=proventos,
            valor_total_carteira=valor_total_carteira
        )
        print("Métricas de Renda:")
        print(json.dumps(resultado, indent=2))
    except Exception as e:
        print(f"ERRO: {e}")

if __name__ == "__main__":
    test_income()
