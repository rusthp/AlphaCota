import json
import os
import sys
from fastapi.testclient import TestClient

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.main import app

client = TestClient(app)

def run_auth_tests():
    print("Testando Endpoint POST /register...")
    resp_register = client.post("/register", json={"email": "test@alphacota.com", "password": "supersecret"})
    print(f"Status: {resp_register.status_code}")
    print(resp_register.json())
    print("\n" + "="*40 + "\n")

    print("Testando Endpoint POST /login...")
    resp_login = client.post("/login", data={"username": "test@alphacota.com", "password": "supersecret"})
    print(f"Status: {resp_login.status_code}")
    print(resp_login.json())
    print("\n" + "="*40 + "\n")
    
    token = resp_login.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    print("Testando Endpoint POST /report (COM TOKEN)...")
    payload = {
        "precos_atuais": {"BBSE3": 32.0, "MXRF11": 10.5},
        "alocacao_alvo": {"BBSE3": 0.5, "MXRF11": 0.5},
        "aporte_mensal": 500.0,
        "taxa_anual_esperada": 0.10,
        "renda_alvo_anual": 120000.0
    }
    resp_report = client.post("/report", json=payload, headers=headers)
    print(f"Status: {resp_report.status_code}")
    print(json.dumps(resp_report.json(), indent=2))
    print("\n" + "="*40 + "\n")
    
    print("Testando /report (SEM TOKEN) pra validar o 401...")
    resp_unauth = client.post("/report", json=payload)
    print(f"Status: {resp_unauth.status_code} (Esperado 401)")
    print(resp_unauth.json())

if __name__ == "__main__":
    run_auth_tests()
