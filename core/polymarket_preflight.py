"""
core/polymarket_preflight.py — Pre-flight checks before live trading.

Public API:
    run_preflight(config, client) -> PreflightResult
    check_alchemy_rpc(url) -> bool
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx

from core.logger import logger

_CTF_EXCHANGE = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
_USDC_POLYGON = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
_MIN_USDC_BALANCE = 20.0
_RPC_TIMEOUT = 5.0


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    failures: list[str]
    checked_at: float = field(default_factory=time.time)


def check_alchemy_rpc(url: str) -> bool:
    """Send eth_blockNumber JSON-RPC call and verify the response is valid hex.

    Args:
        url: Polygon RPC endpoint URL (Alchemy, Infura, or public).

    Returns:
        True if the RPC returns a valid hex block number within 5 seconds.
    """
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_blockNumber",
        "params": [],
        "id": 1,
    }
    try:
        resp = httpx.post(url, json=payload, timeout=_RPC_TIMEOUT)
        resp.raise_for_status()
        result = resp.json().get("result", "")
        return isinstance(result, str) and result.startswith("0x") and len(result) > 2
    except Exception as exc:
        logger.warning("check_alchemy_rpc: %s — %s", url, exc)
        return False


def run_preflight(config: object, client: object | None = None) -> PreflightResult:
    """Run all pre-flight checks required before starting live trading.

    Checks performed:
    1. USDC balance ≥ $20 via web3.
    2. USDC allowance granted to CTF Exchange contract.
    3. Polygon RPC reachable (eth_blockNumber returns valid hex).
    4. CLOB API key valid (GET /auth/apiKey returns 200).

    Args:
        config: OperationalConfig with polymarket_ and polygon_ settings.
        client: Optional py-clob-client ClobClient for CLOB API key check.

    Returns:
        PreflightResult(ok, failures). ok=True only if failures is empty.
    """
    import os

    failures: list[str] = []

    rpc_url = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
    if not check_alchemy_rpc(rpc_url):
        failures.append(f"Polygon RPC unreachable: {rpc_url}")

    private_key = _load_private_key(config)
    if not private_key:
        failures.append("Private key not available (POLYMARKET_PRIVATE_KEY_ENC or POLYMARKET_PRIVATE_KEY)")
        return PreflightResult(ok=False, failures=failures)

    usdc_balance, usdc_allowance = _check_wallet(private_key, rpc_url)

    if usdc_balance < _MIN_USDC_BALANCE:
        failures.append(f"USDC balance too low: ${usdc_balance:.2f} (minimum ${_MIN_USDC_BALANCE:.2f})")

    if usdc_allowance < _MIN_USDC_BALANCE:
        failures.append(
            f"USDC allowance not granted to CTF Exchange: ${usdc_allowance:.2f}"
            f" (run approveERC20 to grant allowance)"
        )

    if client is not None:
        clob_ok = _check_clob_api_key(client)
        if not clob_ok:
            failures.append("CLOB API key invalid or expired")

    return PreflightResult(ok=len(failures) == 0, failures=failures)


def _load_private_key(config: object) -> str:
    """Load private key from vault or env."""
    import os

    enc = os.getenv("POLYMARKET_PRIVATE_KEY_ENC", "")
    if enc:
        password = os.getenv("VAULT_PASSWORD", "")
        if password:
            try:
                from core.secrets_vault import load_secret_with_env_fallback
                return load_secret_with_env_fallback(
                    "polymarket_private_key", password, "POLYMARKET_PRIVATE_KEY"
                )
            except Exception as exc:
                logger.warning("_load_private_key: vault error: %s", exc)

    return os.getenv("POLYMARKET_PRIVATE_KEY", "")


def _check_wallet(private_key: str, rpc_url: str) -> tuple[float, float]:
    """Return (usdc_balance, usdc_allowance) for the wallet."""
    try:
        from eth_account import Account
        from web3 import Web3

        account = Account.from_key(private_key)
        address = account.address

        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not w3.is_connected():
            logger.warning("_check_wallet: RPC not connected")
            return 0.0, 0.0

        abi = [
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function",
            },
            {
                "constant": True,
                "inputs": [
                    {"name": "_owner", "type": "address"},
                    {"name": "_spender", "type": "address"},
                ],
                "name": "allowance",
                "outputs": [{"name": "remaining", "type": "uint256"}],
                "type": "function",
            },
        ]
        usdc = w3.eth.contract(
            address=Web3.to_checksum_address(_USDC_POLYGON), abi=abi
        )
        balance_raw = usdc.functions.balanceOf(address).call()
        allowance_raw = usdc.functions.allowance(
            address, Web3.to_checksum_address(_CTF_EXCHANGE)
        ).call()
        return float(balance_raw) / 1e6, float(allowance_raw) / 1e6
    except Exception as exc:
        logger.warning("_check_wallet: error: %s", exc)
        return 0.0, 0.0


def _check_clob_api_key(client: object) -> bool:
    """Validate CLOB API key by calling get_api_keys() on the client."""
    try:
        client.get_api_keys()  # type: ignore[union-attr]
        return True
    except Exception as exc:
        logger.warning("_check_clob_api_key: %s", exc)
        return False


if __name__ == "__main__":
    import sys

    from core.config import settings
    result = run_preflight(settings)
    if result.ok:
        print("Preflight OK")
        sys.exit(0)
    else:
        print("Preflight FAILED:")
        for f in result.failures:
            print(f"  - {f}")
        sys.exit(1)
