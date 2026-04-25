"""
core/polymarket_client.py — Polymarket CLOB client and market discovery facade.

Discovery is delegated to polymarket_discovery.py. This module exposes the
same public interface for backward compatibility and handles wallet/order-book
operations directly.

Public functions:
    discover_markets(min_volume, max_spread, min_days_open, max_days_open, limit) -> list[Market]
    get_order_book(token_id) -> OrderBook
    get_mid_price(token_id) -> float
    get_wallet_health(rpc_url) -> WalletHealth
"""

from __future__ import annotations

import os
import time

import httpx

from core.logger import logger
from core.polymarket_types import Market, OrderBook, OrderBookLevel, WalletHealth

_CLOB_BASE = "https://clob.polymarket.com"

_USDC_POLYGON = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
_CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"

_ERC20_ABI = [
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


def discover_markets(
    min_volume: float = 1_000.0,
    max_spread: float = 0.10,
    min_days_open: float = 1.0,
    max_days_open: float = 90.0,
    limit: int = 20,
) -> list[Market]:
    """Return quality-filtered Polymarket binary markets ordered by 24 h volume.

    Delegates to polymarket_discovery.discover_markets with the provided
    filter parameters. This function is kept for backward compatibility with
    callers that pass explicit filter values.

    Args:
        min_volume: Minimum 24-hour USD volume.
        max_spread: Maximum bid/ask spread as a fraction (0.10 = 10%).
        min_days_open: Minimum days remaining until resolution.
        max_days_open: Maximum days remaining until resolution.
        limit: Maximum number of markets to return.

    Returns:
        List of Market dataclasses, deduplicated by condition_id.
    """
    from core.polymarket_discovery import DiscoveryConfig
    from core.polymarket_discovery import discover_markets as _discover

    cfg = DiscoveryConfig(
        min_volume_24h=min_volume,
        max_spread_pct=max_spread,
        min_days_to_resolution=min_days_open,
        max_days_to_resolution=max_days_open,
        limit=limit,
        trending_fetch_size=min(limit * 5, 200),
    )
    return _discover(cfg)


def get_order_book(token_id: str) -> OrderBook:
    """Fetch live order book for a YES token from the Polymarket CLOB API.

    Args:
        token_id: The YES token_id for a market.

    Returns:
        OrderBook dataclass with bids, asks, mid_price, spread_pct.

    Raises:
        RuntimeError: If the API call fails or the response is malformed.
    """
    url = f"{_CLOB_BASE}/book"
    params = {"token_id": token_id}
    try:
        resp = httpx.get(url, params=params, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        raise RuntimeError(f"CLOB API error for token {token_id}: {exc}") from exc

    def _parse_levels(raw_levels: list[dict]) -> tuple[OrderBookLevel, ...]:
        levels = []
        for lvl in raw_levels:
            try:
                price = float(lvl.get("price") or 0.0)
                size = float(lvl.get("size") or 0.0)
                if price > 0 and size > 0:
                    levels.append(OrderBookLevel(price=price, size=size))
            except (TypeError, ValueError):
                continue
        return tuple(levels)

    bids = _parse_levels(data.get("bids") or [])
    asks = _parse_levels(data.get("asks") or [])

    best_bid = bids[0].price if bids else 0.0
    best_ask = asks[0].price if asks else 1.0
    mid_price = (best_bid + best_ask) / 2.0
    spread_pct = best_ask - best_bid if best_ask > best_bid else 0.0

    return OrderBook(
        token_id=token_id,
        bids=bids,
        asks=asks,
        mid_price=mid_price,
        spread_pct=spread_pct,
    )


def get_mid_price(token_id: str) -> float:
    """Return the mid-price (0–1) for a YES token.

    Args:
        token_id: The YES token_id.

    Returns:
        Mid-price as a float in [0, 1].
    """
    book = get_order_book(token_id)
    return book.mid_price


def get_wallet_health(rpc_url: str = "") -> WalletHealth:
    """Return wallet health for the configured trading wallet.

    In paper mode (no private key configured), returns a synthetic healthy
    wallet with $10,000 USDC balance and full allowance.

    In live mode, queries the Polygon network via web3 for:
    - MATIC balance (gas)
    - USDC balance (ERC-20 balanceOf)
    - USDC allowance granted to the CTF Exchange contract

    Args:
        rpc_url: Polygon RPC URL. Falls back to POLYGON_RPC_URL env var.

    Returns:
        WalletHealth dataclass.
    """
    from core.config import settings

    mode = getattr(settings, "polymarket_mode", "paper")
    private_key_enc = os.getenv("POLYMARKET_PRIVATE_KEY_ENC", "")

    if mode == "paper" or not private_key_enc:
        return WalletHealth(
            address="0x0000000000000000000000000000000000000000",
            matic_balance=10.0,
            usdc_balance=10_000.0,
            usdc_allowance=10_000.0,
            is_healthy=True,
            checked_at=time.time(),
        )

    rpc = rpc_url or os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")

    try:
        from eth_account import Account

        password = os.getenv("VAULT_PASSWORD", "")
        if password:
            from core.secrets_vault import load_secret_with_env_fallback
            private_key = load_secret_with_env_fallback(
                "polymarket_private_key", password, "POLYMARKET_PRIVATE_KEY"
            )
        else:
            private_key = os.getenv("POLYMARKET_PRIVATE_KEY", "")

        if not private_key:
            logger.error("get_wallet_health: private key unavailable in live mode")
            return WalletHealth(
                address="0x0000000000000000000000000000000000000000",
                matic_balance=0.0,
                usdc_balance=0.0,
                usdc_allowance=0.0,
                is_healthy=False,
                checked_at=time.time(),
            )

        account = Account.from_key(private_key)
        address = account.address

        from web3 import Web3

        w3 = Web3(Web3.HTTPProvider(rpc))
        if not w3.is_connected():
            raise RuntimeError(f"Cannot connect to RPC: {rpc}")

        matic_wei = w3.eth.get_balance(address)
        matic_balance = float(w3.from_wei(matic_wei, "ether"))

        usdc_contract = w3.eth.contract(
            address=Web3.to_checksum_address(_USDC_POLYGON),
            abi=_ERC20_ABI,
        )
        usdc_raw = usdc_contract.functions.balanceOf(address).call()
        usdc_balance = float(usdc_raw) / 1e6

        allowance_raw = usdc_contract.functions.allowance(
            address, Web3.to_checksum_address(_CTF_EXCHANGE)
        ).call()
        usdc_allowance = float(allowance_raw) / 1e6

        is_healthy = usdc_balance >= 20.0 and usdc_allowance >= 20.0

        return WalletHealth(
            address=address,
            matic_balance=matic_balance,
            usdc_balance=usdc_balance,
            usdc_allowance=usdc_allowance,
            is_healthy=is_healthy,
            checked_at=time.time(),
        )
    except Exception as exc:
        logger.error("get_wallet_health live error: %s", exc)
        return WalletHealth(
            address="0x0000000000000000000000000000000000000000",
            matic_balance=0.0,
            usdc_balance=0.0,
            usdc_allowance=0.0,
            is_healthy=False,
            checked_at=time.time(),
        )
