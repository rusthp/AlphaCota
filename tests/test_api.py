"""Tests for api/main.py — FastAPI endpoints with mocked database."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient
from api.main import app
from core.security import hash_password, create_access_token


client = TestClient(app)


class TestHealthCheck:
    def test_health(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestRegister:
    def test_register_success(self):
        with patch("api.main.create_user", return_value=1):
            response = client.post("/register", json={"email": "test@test.com", "password": "secret"})
            assert response.status_code == 200
            assert response.json()["user_id"] == 1

    def test_register_duplicate(self):
        with patch("api.main.create_user", return_value=None):
            response = client.post("/register", json={"email": "dup@test.com", "password": "secret"})
            assert response.status_code == 400
            assert "registrado" in response.json()["detail"]


class TestLogin:
    def test_login_success(self):
        hashed = hash_password("correct")
        mock_user = {"id": 1, "email": "user@test.com", "hashed_password": hashed}
        with patch("api.main.get_user_by_email", return_value=mock_user):
            response = client.post("/login", data={"username": "user@test.com", "password": "correct"})
            assert response.status_code == 200
            assert "access_token" in response.json()
            assert response.json()["token_type"] == "bearer"

    def test_login_wrong_password(self):
        hashed = hash_password("correct")
        mock_user = {"id": 1, "email": "user@test.com", "hashed_password": hashed}
        with patch("api.main.get_user_by_email", return_value=mock_user):
            response = client.post("/login", data={"username": "user@test.com", "password": "wrong"})
            assert response.status_code == 401

    def test_login_user_not_found(self):
        with patch("api.main.get_user_by_email", return_value=None):
            response = client.post("/login", data={"username": "noone@test.com", "password": "any"})
            assert response.status_code == 401


class TestReport:
    def _auth_header(self):
        token = create_access_token({"user_id": 1})
        return {"Authorization": f"Bearer {token}"}

    def test_report_unauthorized(self):
        response = client.post("/report", json={})
        assert response.status_code == 401

    def test_report_success(self):
        mock_report = {"resumo_carteira": {"valor_total": 10000}, "renda_passiva": {}}
        with patch("api.main.run_full_cycle", return_value=mock_report):
            response = client.post(
                "/report",
                json={
                    "precos_atuais": {"HGLG11": 160.0},
                    "alocacao_alvo": {"HGLG11": 1.0},
                    "aporte_mensal": 1000.0,
                    "taxa_anual_esperada": 0.10,
                    "renda_alvo_anual": 60000.0,
                },
                headers=self._auth_header(),
            )
            assert response.status_code == 200
            assert "resumo_carteira" in response.json()


class TestHistory:
    def _auth_header(self):
        token = create_access_token({"user_id": 1})
        return {"Authorization": f"Bearer {token}"}

    def test_history_unauthorized(self):
        response = client.get("/history")
        assert response.status_code == 401

    def test_history_success(self):
        mock_snapshots = [{"date": "2025-01-01", "total": 10000}]
        with patch("api.main.get_portfolio_snapshots", return_value=mock_snapshots):
            response = client.get("/history", headers=self._auth_header())
            assert response.status_code == 200
            assert len(response.json()) == 1
