import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def run_tests():
    print("Testando Endpoint GET /health...")
    resp_health = client.get("/health")
    print(f"Status: {resp_health.status_code}")
    print(resp_health.json())
    print("\n" + "="*40 + "\n")

    print("Testando Endpoint POST /report...")
    payload = {
        "precos_atuais": {"BBSE3": 32.0, "MXRF11": 10.5},
        "alocacao_alvo": {"BBSE3": 0.5, "MXRF11": 0.5},
        "aporte_mensal": 500.0,
        "taxa_anual_esperada": 0.10,
        "renda_alvo_anual": 120000.0
    }
    resp_report = client.post("/report", json=payload)
    print(f"Status: {resp_report.status_code}")
    print(json.dumps(resp_report.json(), indent=2))
    print("\n" + "="*40 + "\n")

    print("Testando Endpoint GET /history...")
    resp_history = client.get("/history")
    print(f"Status: {resp_history.status_code}")
    print(json.dumps(resp_history.json(), indent=2))

if __name__ == "__main__":
    run_tests()
