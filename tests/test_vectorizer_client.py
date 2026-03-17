"""Tests for data/vectorizer_client.py — Vectorizer REST client."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import data.vectorizer_client as vc
from data.vectorizer_client import VectorizerClient


class TestVectorizerClientInit:
    def test_defaults(self):
        client = VectorizerClient()
        assert "localhost" in client.base_url
        assert client.collection == "semantic_code"
        assert client._token is None

    def test_custom_params(self):
        client = VectorizerClient(
            base_url="http://example.com:9999",
            username="user1",
            password="pass1",
            collection="my_col",
        )
        assert client.base_url == "http://example.com:9999"
        assert client.username == "user1"
        assert client.collection == "my_col"


class TestAuthenticate:
    def test_success(self, monkeypatch):
        monkeypatch.setattr(vc, "HAS_REQUESTS", True)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "tok123"}
        mock_requests = MagicMock()
        mock_requests.post.return_value = mock_resp
        monkeypatch.setattr(vc, "requests", mock_requests, raising=False)

        client = VectorizerClient()
        assert client._authenticate() is True
        assert client._token == "tok123"

    def test_fail_status(self, monkeypatch):
        monkeypatch.setattr(vc, "HAS_REQUESTS", True)
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_requests = MagicMock()
        mock_requests.post.return_value = mock_resp
        monkeypatch.setattr(vc, "requests", mock_requests, raising=False)

        client = VectorizerClient()
        assert client._authenticate() is False

    def test_no_requests(self, monkeypatch):
        monkeypatch.setattr(vc, "HAS_REQUESTS", False)
        client = VectorizerClient()
        assert client._authenticate() is False

    def test_network_error(self, monkeypatch):
        monkeypatch.setattr(vc, "HAS_REQUESTS", True)
        mock_requests = MagicMock()
        mock_requests.post.side_effect = ConnectionError("refused")
        monkeypatch.setattr(vc, "requests", mock_requests, raising=False)

        client = VectorizerClient()
        assert client._authenticate() is False


class TestHealth:
    def test_healthy(self, monkeypatch):
        monkeypatch.setattr(vc, "HAS_REQUESTS", True)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "healthy"}
        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_resp
        monkeypatch.setattr(vc, "requests", mock_requests, raising=False)

        client = VectorizerClient()
        assert client.health()["status"] == "healthy"

    def test_no_requests(self, monkeypatch):
        monkeypatch.setattr(vc, "HAS_REQUESTS", False)
        client = VectorizerClient()
        assert client.health()["status"] == "unavailable"

    def test_connection_error(self, monkeypatch):
        monkeypatch.setattr(vc, "HAS_REQUESTS", True)
        mock_requests = MagicMock()
        mock_requests.get.side_effect = ConnectionError("refused")
        monkeypatch.setattr(vc, "requests", mock_requests, raising=False)

        client = VectorizerClient()
        assert client.health()["status"] == "unavailable"


class TestSearch:
    def _make_client(self, monkeypatch):
        monkeypatch.setattr(vc, "HAS_REQUESTS", True)
        mock_requests = MagicMock()
        monkeypatch.setattr(vc, "requests", mock_requests, raising=False)
        client = VectorizerClient()
        client._token = "valid_token"
        return client, mock_requests

    def test_returns_results(self, monkeypatch):
        client, mock_requests = self._make_client(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "id": "abc",
                    "score": 0.95,
                    "payload": {
                        "content": "def calc_yield():",
                        "file_path": "core/income_engine.py",
                        "metadata": {"chunk_index": 0},
                    },
                }
            ]
        }
        mock_requests.post.return_value = mock_resp

        results = client.search("dividend yield")
        assert len(results) == 1
        assert results[0]["score"] == 0.95
        assert results[0]["file_path"] == "core/income_engine.py"

    def test_empty_on_no_auth(self, monkeypatch):
        monkeypatch.setattr(vc, "HAS_REQUESTS", False)
        client = VectorizerClient()
        assert client.search("anything") == []

    def test_reauth_on_401(self, monkeypatch):
        client, mock_requests = self._make_client(monkeypatch)
        resp_401 = MagicMock()
        resp_401.status_code = 401
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {"results": []}
        mock_requests.post.side_effect = [resp_401, MagicMock(status_code=200, json=MagicMock(return_value={"access_token": "new"})), resp_200]

        # Re-auth attempt: post is called for search, then login, then search again
        # But _authenticate uses requests.post directly, so side_effect order matters
        results = client.search("test")
        assert results == []

    def test_error_returns_empty(self, monkeypatch):
        client, mock_requests = self._make_client(monkeypatch)
        mock_requests.post.side_effect = ConnectionError("down")

        assert client.search("test") == []

    def test_non_200_returns_empty(self, monkeypatch):
        client, mock_requests = self._make_client(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_requests.post.return_value = mock_resp

        assert client.search("test") == []


class TestListCollections:
    def test_returns_collections(self, monkeypatch):
        monkeypatch.setattr(vc, "HAS_REQUESTS", True)
        mock_requests = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"collections": [{"name": "code"}, {"name": "semantic_code"}]}
        mock_requests.get.return_value = mock_resp
        monkeypatch.setattr(vc, "requests", mock_requests, raising=False)

        client = VectorizerClient()
        client._token = "tok"
        cols = client.list_collections()
        assert len(cols) == 2

    def test_empty_on_failure(self, monkeypatch):
        monkeypatch.setattr(vc, "HAS_REQUESTS", False)
        client = VectorizerClient()
        assert client.list_collections() == []


class TestGetContextForQuery:
    def test_formats_results(self, monkeypatch):
        monkeypatch.setattr(vc, "HAS_REQUESTS", True)
        mock_requests = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "id": "1",
                    "score": 0.9,
                    "payload": {
                        "content": "def calc(): pass",
                        "file_path": "core/calc.py",
                        "metadata": {},
                    },
                },
                {
                    "id": "2",
                    "score": 0.8,
                    "payload": {
                        "content": "def helper(): pass",
                        "file_path": "core/helper.py",
                        "metadata": {},
                    },
                },
            ]
        }
        mock_requests.post.return_value = mock_resp
        monkeypatch.setattr(vc, "requests", mock_requests, raising=False)

        client = VectorizerClient()
        client._token = "tok"
        ctx = client.get_context_for_query("calcular")
        assert "core/calc.py" in ctx
        assert "core/helper.py" in ctx
        assert "def calc(): pass" in ctx

    def test_empty_when_no_results(self, monkeypatch):
        monkeypatch.setattr(vc, "HAS_REQUESTS", True)
        mock_requests = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": []}
        mock_requests.post.return_value = mock_resp
        monkeypatch.setattr(vc, "requests", mock_requests, raising=False)

        client = VectorizerClient()
        client._token = "tok"
        assert client.get_context_for_query("nada") == ""
