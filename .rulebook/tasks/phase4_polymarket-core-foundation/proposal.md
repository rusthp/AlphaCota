# Proposal: Polymarket Core Foundation (Types + CLOB Client + Ledger)

## Why
Before any scoring, risk, or execution logic can exist, there must be a clean type system,
a reliable CLOB API wrapper, and a persistent position ledger. Without these, every subsequent
module would embed its own ad-hoc HTTP calls and local state, creating untestable spaghetti.

The existing `core/prediction_engine.py` uses raw `requests` calls with no type safety and
no ledger — fine for read-only signals, but completely insufficient for trading. This task
builds the foundation that all execution phases (5, 6, 7) depend on.

## What Changes
- `core/polymarket_types.py` (new): dataclasses only, no logic. `Market`, `OrderBook`,
  `OrderBookLevel`, `OrderIntent`, `Order`, `Position`, `Trade`, `TradeDecision`, `WalletHealth`.
- `core/polymarket_client.py` (new): thin wrapper around gamma-api + CLOB REST. Functions:
  `discover_markets(filters) -> list[Market]`, `get_order_book(token_id) -> OrderBook`,
  `get_mid_price(token_id) -> float`, `get_wallet_health() -> WalletHealth`. Read-only.
  Refuses to import wallet key if `POLYMARKET_MODE=paper`.
- `core/polymarket_ledger.py` (new): SQLite position ledger (`data/polymarket_ledger.db`).
  WAL mode. Tables: `pm_markets`, `pm_orders`, `pm_positions`, `pm_trades`, `pm_pnl_snapshots`.
  Idempotent `insert_order_if_new(client_order_id)`. `reconcile_pending_orders()` on startup.
- Add `py-clob-client>=0.17`, `web3>=6.0`, `eth-account>=0.11` to `requirements.txt`.

## Impact
- Affected code: `core/polymarket_types.py`, `core/polymarket_client.py`,
  `core/polymarket_ledger.py`, `requirements.txt`, `.gitignore` (add `data/polymarket_ledger.db`)
- Breaking change: NO — purely additive
- User benefit: Type-safe foundation; persistent ledger survives crashes; CLOB client
  isolated and mockable for all downstream tests.

Source: docs/analysis/alphacota-polymarket-autonomous-trader/
