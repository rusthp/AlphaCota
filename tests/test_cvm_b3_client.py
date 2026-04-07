"""Tests for data/cvm_b3_client.py — CVM and B3 official data client."""

import datetime
import json
import os
import sqlite3
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from data.cvm_b3_client import (
    _init_cache,
    _get_cached,
    _save_cache,
    fetch_cvm_fii_registry,
    fetch_cvm_proventos,
    fetch_ifix_composition,
    enrich_with_cvm_data,
)

# ---------------------------------------------------------------------------
# Cache tests
# ---------------------------------------------------------------------------


class TestCache:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()

    def teardown_method(self):
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_init_cache_creates_table(self):
        conn = _init_cache(self.db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cvm_cache'")
        assert cursor.fetchone() is not None
        conn.close()

    def test_save_and_get_cached(self):
        conn = _init_cache(self.db_path)
        _save_cache(conn, "test_key", '{"foo": "bar"}')
        result = _get_cached(conn, "test_key", ttl_hours=1)
        assert result == '{"foo": "bar"}'
        conn.close()

    def test_get_cached_returns_none_for_missing_key(self):
        conn = _init_cache(self.db_path)
        result = _get_cached(conn, "nonexistent", ttl_hours=1)
        assert result is None
        conn.close()

    def test_get_cached_returns_none_for_expired(self):
        conn = _init_cache(self.db_path)
        # Insert with old timestamp
        old_time = (datetime.datetime.now() - datetime.timedelta(hours=10)).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO cvm_cache (key, fetched_at, data_json) VALUES (?, ?, ?)",
            ("old_key", old_time, '{"old": true}'),
        )
        conn.commit()
        result = _get_cached(conn, "old_key", ttl_hours=1)
        assert result is None
        conn.close()

    def test_save_cache_overwrites(self):
        conn = _init_cache(self.db_path)
        _save_cache(conn, "key1", '"v1"')
        _save_cache(conn, "key1", '"v2"')
        result = _get_cached(conn, "key1", ttl_hours=1)
        assert result == '"v2"'
        conn.close()


# ---------------------------------------------------------------------------
# CVM Registry tests
# ---------------------------------------------------------------------------

_REGISTRY_CSV = (
    "TP_FUNDO;CNPJ_FUNDO;DENOM_SOCIAL;DT_REG;DT_CONST;CD_CVM;DT_CANCEL;SIT;DT_INI_SIT;DT_INI_ATIV\n"
    "FII;12345;Fundo A;;;001;;EM FUNCIONAMENTO NORMAL;;2010-01-01\n"
    "FII;67890;Fundo B;;;002;;CANCELADO;;2015-06-01\n"
    "FII;11111;Fundo C;;;003;;EM FUNCIONAMENTO NORMAL;;2012-03-15\n"
    "FIM;99999;Fundo Multimercado;;;004;;EM FUNCIONAMENTO NORMAL;;2018-01-01\n"
)


class TestFetchCvmFiiRegistry:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()

    def teardown_method(self):
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    @patch("data.cvm_b3_client.requests")
    def test_fetch_registry_success(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = _REGISTRY_CSV.encode("latin-1")
        mock_requests.get.return_value = mock_resp

        results = fetch_cvm_fii_registry(db_path=self.db_path)

        assert len(results) == 2  # Only FII type + "EM FUNCIONAMENTO NORMAL" (FIM excluded, CANCELADO excluded)
        assert results[0]["cnpj"] == "12345"
        assert results[0]["nome"] == "Fundo A"
        assert results[0]["situacao"] == "EM FUNCIONAMENTO NORMAL"
        assert results[0]["tipo"] == "FII"
        assert results[1]["cnpj"] == "11111"

    @patch("data.cvm_b3_client.requests")
    def test_fetch_registry_uses_cache(self, mock_requests):
        # Pre-populate cache
        conn = _init_cache(self.db_path)
        cached_data = [{"cnpj": "cached", "nome": "Cached Fund"}]
        _save_cache(conn, "cvm_registry", json.dumps(cached_data))
        conn.close()

        results = fetch_cvm_fii_registry(db_path=self.db_path)
        assert results[0]["cnpj"] == "cached"
        mock_requests.get.assert_not_called()

    @patch("data.cvm_b3_client.requests")
    def test_fetch_registry_http_error(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_requests.get.return_value = mock_resp

        results = fetch_cvm_fii_registry(db_path=self.db_path)
        assert results == []

    @patch("data.cvm_b3_client.requests")
    def test_fetch_registry_exception(self, mock_requests):
        mock_requests.get.side_effect = Exception("Network error")

        results = fetch_cvm_fii_registry(db_path=self.db_path)
        assert results == []

    @patch("data.cvm_b3_client.HAS_DEPS", False)
    def test_fetch_registry_no_deps(self):
        results = fetch_cvm_fii_registry(db_path=self.db_path)
        assert results == []


# ---------------------------------------------------------------------------
# CVM Proventos tests
# ---------------------------------------------------------------------------

_PROVENTO_CSV = (
    "CNPJ_FUNDO;DENOM_SOCIAL;DT_COMPTC;DT_PAGTO;VL_PROVENTO;TP_PROVENTO\n"
    "12345;Fundo A;2025-01-31;2025-02-15;1,50;RENDIMENTO\n"
    "67890;Fundo B;2025-01-31;2025-02-15;0,80;RENDIMENTO\n"
    "11111;Fundo C;2025-01-31;2025-02-15;0;RENDIMENTO\n"
)


class TestFetchCvmProventos:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()

    def teardown_method(self):
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    @patch("data.cvm_b3_client.requests")
    def test_fetch_proventos_success(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = _PROVENTO_CSV.encode("latin-1")
        mock_requests.get.return_value = mock_resp

        results = fetch_cvm_proventos(year=2025, month=1, db_path=self.db_path)

        assert len(results) == 2  # Zero-value provento filtered out
        assert results[0]["valor_provento"] == 1.50
        assert results[0]["tipo"] == "RENDIMENTO"
        assert results[1]["valor_provento"] == 0.80

    @patch("data.cvm_b3_client.requests")
    def test_fetch_proventos_default_date(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = _PROVENTO_CSV.encode("latin-1")
        mock_requests.get.return_value = mock_resp

        # Should not raise with default year/month
        results = fetch_cvm_proventos(db_path=self.db_path)
        assert isinstance(results, list)

    @patch("data.cvm_b3_client.requests")
    def test_fetch_proventos_january_wraps_to_december(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = _PROVENTO_CSV.encode("latin-1")
        mock_requests.get.return_value = mock_resp

        with patch("data.cvm_b3_client.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = datetime.datetime(2025, 1, 15)
            mock_dt.datetime.fromisoformat = datetime.datetime.fromisoformat
            results = fetch_cvm_proventos(db_path=self.db_path)
            assert isinstance(results, list)

    @patch("data.cvm_b3_client.requests")
    def test_fetch_proventos_404_fallback(self, mock_requests):
        mock_resp_404 = MagicMock()
        mock_resp_404.status_code = 404

        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.content = _PROVENTO_CSV.encode("latin-1")

        mock_requests.get.side_effect = [mock_resp_404, mock_resp_ok]

        results = fetch_cvm_proventos(year=2025, month=1, db_path=self.db_path)
        assert len(results) == 2
        assert mock_requests.get.call_count == 2

    @patch("data.cvm_b3_client.requests")
    def test_fetch_proventos_http_error(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_requests.get.return_value = mock_resp

        results = fetch_cvm_proventos(year=2025, month=1, db_path=self.db_path)
        assert results == []

    @patch("data.cvm_b3_client.requests")
    def test_fetch_proventos_uses_cache(self, mock_requests):
        conn = _init_cache(self.db_path)
        cached = [{"valor_provento": 2.0}]
        _save_cache(conn, "cvm_proventos_2025_01", json.dumps(cached))
        conn.close()

        results = fetch_cvm_proventos(year=2025, month=1, db_path=self.db_path)
        assert results[0]["valor_provento"] == 2.0
        mock_requests.get.assert_not_called()

    @patch("data.cvm_b3_client.HAS_DEPS", False)
    def test_fetch_proventos_no_deps(self):
        results = fetch_cvm_proventos(db_path=self.db_path)
        assert results == []

    @patch("data.cvm_b3_client.requests")
    def test_fetch_proventos_exception(self, mock_requests):
        mock_requests.get.side_effect = Exception("Timeout")
        results = fetch_cvm_proventos(year=2025, month=1, db_path=self.db_path)
        assert results == []

    @patch("data.cvm_b3_client.requests")
    def test_fetch_proventos_invalid_valor(self, mock_requests):
        csv_data = (
            "CNPJ_FUNDO;DENOM_SOCIAL;DT_COMPTC;DT_PAGTO;VL_PROVENTO;TP_PROVENTO\n"
            "12345;Fundo A;2025-01-31;2025-02-15;abc;RENDIMENTO\n"
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = csv_data.encode("latin-1")
        mock_requests.get.return_value = mock_resp

        results = fetch_cvm_proventos(year=2025, month=1, db_path=self.db_path)
        assert results == []  # Invalid value filtered


# ---------------------------------------------------------------------------
# B3 IFIX Composition tests
# ---------------------------------------------------------------------------


class TestFetchIfixComposition:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()

    def teardown_method(self):
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    @patch("data.cvm_b3_client.requests")
    def test_fetch_ifix_success_list_format(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"cod": "HGLG11", "asset": "CGHG Logistica", "part": 5.2, "theoricalQty": 1000},
            {"cod": "MXRF11", "asset": "Maxi Renda", "part": 3.1, "theoricalQty": 2000},
        ]
        mock_requests.get.return_value = mock_resp

        results = fetch_ifix_composition(db_path=self.db_path)
        assert len(results) == 2
        assert results[0]["ticker"] == "HGLG11"
        assert results[0]["participacao"] == 5.2

    @patch("data.cvm_b3_client.requests")
    def test_fetch_ifix_success_dict_format(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {"cod": "KNRI11", "asset": "Kinea Renda", "part": 4.0, "theoricalQty": 500},
            ]
        }
        mock_requests.get.return_value = mock_resp

        results = fetch_ifix_composition(db_path=self.db_path)
        assert len(results) == 1
        assert results[0]["ticker"] == "KNRI11"

    @patch("data.cvm_b3_client.requests")
    def test_fetch_ifix_empty_ticker_skipped(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"cod": "", "asset": "Empty", "part": 1.0, "theoricalQty": 100},
            {"cod": "XPML11", "asset": "XP Malls", "part": 2.5, "theoricalQty": 300},
        ]
        mock_requests.get.return_value = mock_resp

        results = fetch_ifix_composition(db_path=self.db_path)
        assert len(results) == 1
        assert results[0]["ticker"] == "XPML11"

    @patch("data.cvm_b3_client.requests")
    def test_fetch_ifix_http_error(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_requests.get.return_value = mock_resp

        results = fetch_ifix_composition(db_path=self.db_path)
        assert results == []

    @patch("data.cvm_b3_client.requests")
    def test_fetch_ifix_uses_cache(self, mock_requests):
        conn = _init_cache(self.db_path)
        cached = [{"ticker": "CACHED11", "participacao": 99.0}]
        _save_cache(conn, "b3_ifix", json.dumps(cached))
        conn.close()

        results = fetch_ifix_composition(db_path=self.db_path)
        assert results[0]["ticker"] == "CACHED11"
        mock_requests.get.assert_not_called()

    @patch("data.cvm_b3_client.HAS_DEPS", False)
    def test_fetch_ifix_no_deps(self):
        results = fetch_ifix_composition(db_path=self.db_path)
        assert results == []

    @patch("data.cvm_b3_client.requests")
    def test_fetch_ifix_exception(self, mock_requests):
        mock_requests.get.side_effect = Exception("Connection refused")
        results = fetch_ifix_composition(db_path=self.db_path)
        assert results == []


# ---------------------------------------------------------------------------
# Enrich tests
# ---------------------------------------------------------------------------


class TestEnrichWithCvmData:
    @patch("data.cvm_b3_client.fetch_ifix_composition")
    def test_enrich_fii_in_ifix(self, mock_ifix):
        mock_ifix.return_value = [
            {"ticker": "HGLG11", "participacao": 5.2, "quantidade_teorica": 1000},
        ]

        result = enrich_with_cvm_data("HGLG11", {"price": 155.0})
        assert result["price"] == 155.0
        assert result["ifix_participacao"] == 5.2
        assert result["_in_ifix"] is True

    @patch("data.cvm_b3_client.fetch_ifix_composition")
    def test_enrich_fii_not_in_ifix(self, mock_ifix):
        mock_ifix.return_value = [
            {"ticker": "HGLG11", "participacao": 5.2, "quantidade_teorica": 1000},
        ]

        result = enrich_with_cvm_data("XYZZ11", {"price": 10.0})
        assert result["_in_ifix"] is False
        assert "ifix_participacao" not in result

    @patch("data.cvm_b3_client.fetch_ifix_composition")
    def test_enrich_does_not_overwrite_existing(self, mock_ifix):
        mock_ifix.return_value = [
            {"ticker": "HGLG11", "participacao": 5.2, "quantidade_teorica": 1000},
        ]

        result = enrich_with_cvm_data("HGLG11", {"ifix_participacao": 99.0})
        assert result["ifix_participacao"] == 99.0  # Not overwritten
