"""tests/test_polymarket_preflight.py — Tests for preflight checks."""

from unittest.mock import MagicMock, patch

import pytest

from core.polymarket_preflight import (
    PreflightResult,
    check_alchemy_rpc,
    run_preflight,
)


class _Config:
    polymarket_mode = "live"


class TestCheckAlchemyRpc:
    def test_returns_true_on_valid_hex(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"result": "0x12345678", "id": 1}
        mock_resp.raise_for_status = MagicMock()
        with patch("httpx.post", return_value=mock_resp):
            assert check_alchemy_rpc("https://polygon-rpc.com") is True

    def test_returns_false_on_non_hex_result(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"result": "notahex"}
        mock_resp.raise_for_status = MagicMock()
        with patch("httpx.post", return_value=mock_resp):
            assert check_alchemy_rpc("https://polygon-rpc.com") is False

    def test_returns_false_on_connection_error(self):
        with patch("httpx.post", side_effect=Exception("connection refused")):
            assert check_alchemy_rpc("https://bad-rpc.invalid") is False

    def test_returns_false_on_empty_result(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"result": ""}
        mock_resp.raise_for_status = MagicMock()
        with patch("httpx.post", return_value=mock_resp):
            assert check_alchemy_rpc("https://polygon-rpc.com") is False

    def test_returns_false_on_0x_only(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"result": "0x"}
        mock_resp.raise_for_status = MagicMock()
        with patch("httpx.post", return_value=mock_resp):
            assert check_alchemy_rpc("https://polygon-rpc.com") is False


class TestRunPreflight:
    def test_all_pass_returns_ok(self):
        with (
            patch("core.polymarket_preflight.check_alchemy_rpc", return_value=True),
            patch("core.polymarket_preflight._load_private_key", return_value="0xdeadbeef"),
            patch("core.polymarket_preflight._check_wallet", return_value=(500.0, 500.0)),
        ):
            result = run_preflight(_Config())
        assert result.ok is True
        assert result.failures == []

    def test_fails_when_rpc_unreachable(self):
        with (
            patch("core.polymarket_preflight.check_alchemy_rpc", return_value=False),
            patch("core.polymarket_preflight._load_private_key", return_value="0xdeadbeef"),
            patch("core.polymarket_preflight._check_wallet", return_value=(500.0, 500.0)),
        ):
            result = run_preflight(_Config())
        assert result.ok is False
        assert any("RPC" in f for f in result.failures)

    def test_fails_when_balance_too_low(self):
        with (
            patch("core.polymarket_preflight.check_alchemy_rpc", return_value=True),
            patch("core.polymarket_preflight._load_private_key", return_value="0xdeadbeef"),
            patch("core.polymarket_preflight._check_wallet", return_value=(5.0, 500.0)),
        ):
            result = run_preflight(_Config())
        assert result.ok is False
        assert any("balance" in f.lower() for f in result.failures)

    def test_fails_when_allowance_not_granted(self):
        with (
            patch("core.polymarket_preflight.check_alchemy_rpc", return_value=True),
            patch("core.polymarket_preflight._load_private_key", return_value="0xdeadbeef"),
            patch("core.polymarket_preflight._check_wallet", return_value=(500.0, 0.0)),
        ):
            result = run_preflight(_Config())
        assert result.ok is False
        assert any("allowance" in f.lower() for f in result.failures)

    def test_fails_when_no_private_key(self):
        with (
            patch("core.polymarket_preflight.check_alchemy_rpc", return_value=True),
            patch("core.polymarket_preflight._load_private_key", return_value=""),
        ):
            result = run_preflight(_Config())
        assert result.ok is False
        assert any("key" in f.lower() for f in result.failures)

    def test_fails_when_clob_api_key_invalid(self):
        mock_client = MagicMock()
        with (
            patch("core.polymarket_preflight.check_alchemy_rpc", return_value=True),
            patch("core.polymarket_preflight._load_private_key", return_value="0xdeadbeef"),
            patch("core.polymarket_preflight._check_wallet", return_value=(500.0, 500.0)),
            patch("core.polymarket_preflight._check_clob_api_key", return_value=False),
        ):
            result = run_preflight(_Config(), client=mock_client)
        assert result.ok is False
        assert any("CLOB" in f for f in result.failures)

    def test_multiple_failures_accumulated(self):
        with (
            patch("core.polymarket_preflight.check_alchemy_rpc", return_value=False),
            patch("core.polymarket_preflight._load_private_key", return_value="0xdeadbeef"),
            patch("core.polymarket_preflight._check_wallet", return_value=(5.0, 0.0)),
        ):
            result = run_preflight(_Config())
        assert len(result.failures) >= 2

    def test_result_has_checked_at_timestamp(self):
        import time
        before = time.time()
        with (
            patch("core.polymarket_preflight.check_alchemy_rpc", return_value=True),
            patch("core.polymarket_preflight._load_private_key", return_value="0xkey"),
            patch("core.polymarket_preflight._check_wallet", return_value=(500.0, 500.0)),
        ):
            result = run_preflight(_Config())
        assert result.checked_at >= before
