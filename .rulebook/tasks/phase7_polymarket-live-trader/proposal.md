# Proposal: Polymarket Live Trader (Real Money — Guarded First Week)

## Why
Paper trading proves the loop works. Live trading is the actual goal: placing real USDC bets
on Polygon using the CLOB, collecting real PnL, and validating the full pipeline under
real market conditions. This phase must not be rushed — it requires EIP-712 cryptographic
signing, wallet health pre-flight checks, hard position limits for the first week ($50 max
per position, $10 max daily loss), and full observability so any anomaly is caught before
capital is burned. The kill-switch from phase 6 must remain in force throughout.

## What Changes
- `core/polymarket_executor.py` (new): live executor wrapping py-clob-client. Signs GTC limit
  orders via EIP-712 (`eth-account`), submits via CLOB `/order` endpoint, polls for fill
  status, records filled orders in ledger with `mode=live`. Refuses to load private key
  when `POLYMARKET_MODE != live` — paper mode uses the paper executor.
- `core/polymarket_preflight.py` (new): startup validation. Checks wallet USDC balance
  (≥$20 required), USDC allowance granted to CTF Exchange contract, Polygon RPC reachable
  (via Alchemy/Infura endpoint), CLOB API key valid. Refuses to start live loop if any
  check fails.
- `core/polymarket_loop.py` (updated): branch on `mode=live` → use live executor; re-run
  preflight on each loop iteration if previous iteration had a fill error.
- Hard limits enforced in executor (not configurable via env, hardcoded for first week):
  `MAX_POSITION_USD = 50.0`, `MAX_DAILY_LOSS_USD = 10.0`. After first-week review these
  can be promoted to env vars.
- `core/polymarket_observability.py` (new): structured JSON logging for every order attempt,
  fill, rejection, and exit. Rotates daily. Separate from application logs.
- `api/main.py` (updated): `GET /api/polymarket/live-status` — wallet balance + daily PnL
  + open position count + mode; `GET /api/polymarket/orders` — recent order history with
  status (pending/filled/cancelled/rejected).
- `systemd/alphacota-trader.service` (updated): `Environment=POLYMARKET_MODE=live` and
  `ALCHEMY_RPC_URL` injection via EnvironmentFile.

## Impact
- Affected code: `core/polymarket_executor.py`, `core/polymarket_preflight.py`,
  `core/polymarket_loop.py`, `core/polymarket_observability.py`, `api/main.py`,
  `systemd/alphacota-trader.service`
- Breaking change: NO — additive; paper mode is unchanged
- User benefit: Real USDC bets on Polygon with hard capital guardrails; kill-switch
  preserved; full audit trail; wallet health validated on every startup.

Source: docs/analysis/alphacota-polymarket-autonomous-trader/

