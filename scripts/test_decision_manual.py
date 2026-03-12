from core.decision_engine import generate_decision_report
import json

def test_decision():
    operacoes = [
        {"ticker": "BBSE3", "tipo": "compra", "quantidade": 100, "preco": 30.0}, # Investido: 3000
        {"ticker": "MXRF11", "tipo": "compra", "quantidade": 200, "preco": 10.0} # Investido: 2000
    ]

    precos_atuais = {
        "BBSE3": 35.0, # Valor atual: 3500
        "MXRF11": 10.5 # Valor atual: 2100
        # Total carteira: 5600
    }

    proventos = [
        {"ticker": "BBSE3", "valor": 35.0},
        {"ticker": "MXRF11", "valor": 20.0}
    ]

    alocacao_alvo = {
        "BBSE3": 0.50,
        "MXRF11": 0.50
    }

    print("Gerando Relatório de Decisão...")
    try:
        report = generate_decision_report(
            operacoes=operacoes,
            precos_atuais=precos_atuais,
            proventos=proventos,
            alocacao_alvo=alocacao_alvo,
            aporte_mensal=500.0,
            taxa_anual_esperada=0.10,
            renda_alvo_anual=120000.0
        )
        print("Saída do Orquestrador (Contrato API):")
        print(json.dumps(report, indent=2))
    except Exception as e:
        print(f"ERRO: {e}")

if __name__ == "__main__":
    test_decision()
