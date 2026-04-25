## 1. Dependencies
- [x] 1.1 Add `py-clob-client>=0.17,<1.0`, `web3>=6.0,<7.0`, `eth-account>=0.11,<1.0` to `requirements.txt`
- [x] 1.2 Add `data/polymarket_ledger.db`, `data/wallet_cache.db`, `data/audit.db`, `data/.vault` to `.gitignore`

## 2. Types
- [x] 2.1 Write `core/polymarket_types.py`: dataclasses `Market`, `OrderBook`, `OrderBookLevel`, `OrderIntent`, `Order`, `Position`, `Trade`, `TradeDecision`, `WalletHealth`, `CopySignal` — no logic, only `@dataclass(frozen=True)` with type hints

## 3. CLOB Client
- [x] 3.1 Write `core/polymarket_client.py`: `discover_markets(min_volume, max_spread, min_days_open) -> list[Market]` — extends `prediction_engine._search_markets` with richer filters and full identifier retention (`condition_id`, `token_id`)
- [x] 3.2 Add `get_order_book(token_id) -> OrderBook` and `get_mid_price(token_id) -> float` using CLOB REST
- [x] 3.3 Add `get_wallet_health() -> WalletHealth` — reads MATIC balance + USDC balance + USDC allowance via web3; returns health dataclass; refuses to load private key when `POLYMARKET_MODE=paper`

## 4. Ledger
- [x] 4.1 Write `core/polymarket_ledger.py`: `init_db()` creates WAL-mode SQLite with tables `pm_markets`, `pm_orders`, `pm_positions`, `pm_trades`, `pm_pnl_snapshots`
- [x] 4.2 Add `insert_order_if_new(client_order_id, market_id, direction, size_usd) -> bool` — idempotent; returns False if already exists
- [x] 4.3 Add `reconcile_pending_orders(client) -> int` — on startup, queries CLOB for all `status=pending` orders and updates ledger to match actual CLOB state

## 5. Tail
- [x] 5.1 Write `tests/test_polymarket_types.py`: dataclass instantiation, frozen enforcement
- [x] 5.2 Write `tests/test_polymarket_client.py`: mock HTTP responses, filter logic, paper-mode refuses key
- [x] 5.3 Write `tests/test_polymarket_ledger.py`: idempotent insert, reconcile updates status, WAL mode enabled
- [x] 5.4 Run `ruff check` + `mypy core/polymarket_types.py core/polymarket_client.py core/polymarket_ledger.py` — zero errors
- [x] 5.5 Run `pytest tests/test_polymarket_*.py -v` — all pass
