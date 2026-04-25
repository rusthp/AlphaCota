## 1. Pre-flight Module
- [x] 1.1 Write `core/polymarket_preflight.py`: `run_preflight(config, client) -> PreflightResult` — checks USDC balance ≥$20, USDC allowance granted to CTF Exchange (0x4D97DCd97eC945f40cF65F87097ACe5EA0476045), Polygon RPC reachable, CLOB API key valid; returns `PreflightResult(ok, failures: list[str])`
- [x] 1.2 Add `check_alchemy_rpc(url: str) -> bool` — sends `eth_blockNumber` JSON-RPC call; returns True if response is valid hex; timeout 5s

## 2. Live Executor
- [x] 2.1 Write `core/polymarket_executor.py`: `execute_live(decision, ledger, client) -> Order` — builds GTC limit order, signs via EIP-712 with `eth-account`, submits to CLOB `/order`, polls `/order/{id}` until filled or 60s timeout, records in ledger with `mode=live`
- [x] 2.2 Add hard limits guard inside executor (not configurable): `MAX_POSITION_USD = 50.0`, `MAX_DAILY_LOSS_USD = 10.0`; raises `HardLimitExceeded` before signing if either would be breached
- [x] 2.3 Add `close_live_position(position, ledger, client) -> Trade` — submits market sell order, records realized PnL in `pm_trades`; refuses if kill-switch file present

## 3. Observability
- [x] 3.1 Write `core/polymarket_observability.py`: `log_order_event(event_type, payload, mode)` — writes structured JSON line to `logs/polymarket_YYYY-MM-DD.jsonl`; rotates daily; event types: `order_attempt`, `order_filled`, `order_rejected`, `position_closed`, `preflight_failed`, `hard_limit_hit`

## 4. Loop Integration
- [x] 4.1 Update `core/polymarket_loop.py`: on `mode=live`, run `run_preflight()` at startup; abort loop if preflight fails; use `execute_live()` instead of `execute_paper()`; re-run preflight if consecutive fill errors ≥3
- [x] 4.2 Add `--mode` CLI argument to `polymarket_loop.py`: `python -m core.polymarket_loop --mode=live` (default: paper); validate mode against `POLYMARKET_MODE` env var — must match or refuse to start

## 5. API Routes
- [x] 5.1 Add to `api/main.py`: `GET /api/polymarket/live-status` → wallet USDC balance + daily realized PnL + open position count + current mode + preflight last run timestamp
- [x] 5.2 Add `GET /api/polymarket/orders` → last 50 orders from ledger with fields: `order_id`, `market_id`, `direction`, `size_usd`, `fill_price`, `status`, `mode`, `created_at`

## 6. Systemd Update
- [x] 6.1 Update `systemd/alphacota-trader.service`: add `Environment=POLYMARKET_MODE=live`, document that `ALCHEMY_RPC_URL` and `POLYMARKET_PRIVATE_KEY_ENC` must be in `EnvironmentFile=/root/alphacota/.env`; add `ExecStartPre=/usr/bin/python3 -m core.polymarket_preflight` to run preflight before main process starts

## 7. Tail
- [x] 7.1 Write `tests/test_polymarket_preflight.py`: balance-too-low fails, allowance-not-granted fails, bad RPC URL fails, all-pass returns ok=True
- [x] 7.2 Write `tests/test_polymarket_executor.py`: hard limit blocks oversized order, EIP-712 signing produces valid signature structure (use known test key + expected output), kill-switch blocks close_live_position
- [x] 7.3 Write `tests/test_polymarket_observability.py`: log file created with correct date, JSON lines parseable, daily rotation creates new file
- [x] 7.4 Run `ruff check` + `mypy` on all new/modified files — zero errors
- [x] 7.5 Run `pytest tests/test_polymarket_preflight.py tests/test_polymarket_executor.py tests/test_polymarket_observability.py -v` — all pass
- [x] 7.6 Update `docs/` with live trader runbook: how to set env vars, how to verify preflight passes, how to use kill-switch, how to read observability logs
