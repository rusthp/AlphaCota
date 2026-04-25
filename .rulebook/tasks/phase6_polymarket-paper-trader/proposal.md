# Proposal: Polymarket Paper Trader (Full Loop — No Real Money)

## Why
Before a single real dollar is committed on-chain, the complete end-to-end trading loop must
run against real market data in simulation mode and prove it works without errors, without
crashes on recovery, and without the kill-switch being bypassable. Paper trading is not an
optional step — it is the gate that separates a prototype from a deployable system.

Phases 1-5 build isolated modules. This phase wires them together into a running process,
adds the paper executor (fills against real order book without signing), the position monitor,
exit engine, and the crash-recovery reconciliation flow. It also adds the triple kill-switch
(file + API + SIGTERM) and the systemd unit for the VM.

## What Changes
- `core/polymarket_paper_executor.py` (new): simulates fills by reading real order book mid-price
  and applying a configurable slippage model (default: half-spread). Writes to the same ledger
  as the live executor will, tagged `mode=paper`. No private key required.
- `core/polymarket_monitor.py` (new): `monitor_positions(ledger, client) -> list[PositionStatus]`.
  Refreshes mid-price every 60s, computes unrealized PnL, flags positions breaching take-profit
  or stop-loss thresholds.
- `core/polymarket_exit_engine.py` (new): `should_exit(position, market, config) -> ExitDecision`.
  Encodes five exit rules: take-profit, stop-loss, time-stop, AI-sentiment-inversion, resolution-hold.
- `core/polymarket_loop.py` (new): main autonomous loop. Cadence: discover → decide → execute →
  monitor → exit. Checks kill-switch file on every iteration. Configurable interval (default 5min).
- Kill-switch: file `data/POLYMARKET_KILL` checked every iteration; `POST /api/polymarket/kill`
  route creates the file; SIGTERM handler cancels open orders and halts.
- `systemd/alphacota-trader.service` (new): systemd unit for VM deployment.
- `api/main.py` (updated): new routes `GET /api/polymarket/positions`, `GET /api/polymarket/pnl`,
  `POST /api/polymarket/kill`, `GET /api/polymarket/status`.

## Impact
- Affected code: `core/polymarket_paper_executor.py`, `core/polymarket_monitor.py`,
  `core/polymarket_exit_engine.py`, `core/polymarket_loop.py`, `api/main.py`,
  `systemd/alphacota-trader.service`
- Breaking change: NO — additive
- User benefit: Complete autonomous loop running safely without real money; verified kill-switch;
  real PnL tracking in paper mode; ready-to-deploy systemd unit for VM.

Source: docs/analysis/alphacota-polymarket-autonomous-trader/
