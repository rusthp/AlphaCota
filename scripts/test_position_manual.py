from core.position_engine import calculate_position_metrics
import json

def test_position():
    operacoes = [
        {"ticker": "BBSE3", "tipo": "compra", "quantidade": 10, "preco": 30.0},
        {"ticker": "BBSE3", "tipo": "compra", "quantidade": 5, "preco": 35.0},
        {"ticker": "MXRF11", "tipo": "compra", "quantidade": 100, "preco": 10.0},
        {"ticker": "MXRF11", "tipo": "venda", "quantidade": 50, "preco": 11.0}
    ]

    precos_atuais = {
        "BBSE3": 40.0,
        "MXRF11": 10.50
    }

    print("Testando Position Engine (sem arredondamentos na engine)")
    try:
        resultado = calculate_position_metrics(
            operacoes=operacoes,
            precos_atuais=precos_atuais
        )
        print("Métricas da Posição Atual:")
        print(json.dumps(resultado, indent=2))
    except Exception as e:
        print(f"ERRO: {e}")

if __name__ == "__main__":
    test_position()
