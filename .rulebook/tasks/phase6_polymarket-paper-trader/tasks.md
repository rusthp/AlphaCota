## 1. Paper Executor
- [x] 1.1 Write `core/polymarket_paper_executor.py`: `execute_paper(decision, ledger, client) -> Order` — reads real mid-price, applies half-spread slippage, inserts order + position into ledger with `mode=paper`
- [x] 1.2 Add `close_paper_position(position, ledger, client) -> Trade` — reads current mid-price, records realized PnL in `pm_trades`

## 2. Monitor + Exit Engine
- [x] 2.1 Write `core/polymarket_monitor.py`: `monitor_positions(ledger, client) -> list[PositionStatus]` — refreshes mid-price, computes unrealized PnL, flags breach of take-profit (default +50%) or stop-loss (default -30%)
- [x] 2.2 Write `core/polymarket_exit_engine.py`: `should_exit(position, market, config) -> ExitDecision` — five rules: take-profit, stop-loss, time-stop (<2 days to resolution + no movement), AI-sentiment-inversion (re-runs scorer, score drops >30 points), resolution-hold (let settle if still edge)

## 3. Main Loop
- [x] 3.1 Write `core/polymarket_loop.py`: `run_loop(config, mode="paper")` — iterates: check kill-switch → discover → decide → execute → persist → monitor → exit; sleeps `LOOP_INTERVAL_SECONDS` (default 300)
- [x] 3.2 Add SIGTERM handler: on signal, cancel all open CLOB orders (paper: just mark cancelled in ledger), write final PnL snapshot, exit 0
- [x] 3.3 Kill-switch file check: `_is_killed() -> bool` reads `data/POLYMARKET_KILL` existence; if present, loop exits immediately

## 4. API Routes
- [x] 4.1 Add to `api/main.py`: `GET /api/polymarket/status` → loop running/stopped + mode + uptime
- [x] 4.2 Add `GET /api/polymarket/positions` → open positions with unrealized PnL from ledger
- [x] 4.3 Add `GET /api/polymarket/pnl` → realized PnL history from `pm_pnl_snapshots`
- [x] 4.4 Add `POST /api/polymarket/kill` (auth required) → creates `data/POLYMARKET_KILL` file

## 5. Systemd Unit
- [x] 5.1 Write `systemd/alphacota-trader.service` with `Restart=on-failure`, `RestartSec=30`, `EnvironmentFile=/root/alphacota/.env`, `ExecStart=python -m core.polymarket_loop`

## 6. Tail
- [x] 6.1 Write `tests/test_polymarket_paper_executor.py`: fill at mid+spread, ledger insert, close records PnL
- [x] 6.2 Write `tests/test_polymarket_exit_engine.py`: each exit rule fires at correct threshold, resolution-hold does not exit early when edge remains
- [x] 6.3 Write `tests/test_polymarket_loop.py`: kill-switch file halts loop, SIGTERM triggers graceful shutdown
- [x] 6.4 Run `ruff check` + `mypy` on all new files — zero errors
- [x] 6.5 Run `pytest tests/test_polymarket_paper_executor.py tests/test_polymarket_exit_engine.py tests/test_polymarket_loop.py -v` — all pass
- [x] 6.6 Run full paper loop for 3 iterations in CI (`python -m core.polymarket_loop --mode=paper --iterations=3`) — exits cleanly with no exceptions
