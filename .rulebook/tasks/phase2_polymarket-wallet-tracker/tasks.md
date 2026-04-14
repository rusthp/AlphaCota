## 1. Wallet History Fetcher
- [x] 1.1 Implement `core/polymarket_wallet_tracker.py`: `get_wallet_history(address) -> WalletHistory` — fetches resolved positions from gamma-api `/positions?user=<addr>&closed=true`, computes win_rate, total_trades, avg_size_usd, preferred_categories
- [x] 1.2 Add SQLite cache in `data/wallet_cache.db` (1h TTL); `load_cached_history(address)` / `save_history(address, data)`

## 2. Alpha Detector
- [x] 2.1 Implement `core/polymarket_alpha_detector.py`: `rank_wallets(addresses, min_trades=20) -> list[WalletScore]` — filters by min sample size, scores by win_rate + recency weight + market diversity; returns sorted list
- [x] 2.2 Add `detect_top_alpha_wallets(limit=10) -> list[WalletScore]` — seeds from a configurable watchlist in `.env` (`POLYMARKET_WATCH_WALLETS=addr1,addr2,...`)

## 3. Copy Signal
- [x] 3.1 Implement `core/polymarket_copy_signal.py`: `get_copy_signal(market_question, alpha_wallets) -> CopySignal` — checks if tracked wallets have open positions on this market, returns direction + consensus ratio + confidence
- [x] 3.2 `CopySignal` dataclass: `direction` (yes/no/none), `confidence` (0-1), `wallet_count` (int), `consensus_ratio` (float)

## 4. MCP Tool
- [x] 4.1 Register `get_polymarket_alpha_wallets(limit=10)` tool in `alphacota_mcp/financial_data/tools/market.py` — returns ranked wallet list with scores

## 5. Tail
- [x] 5.1 Write `tests/test_polymarket_wallet_tracker.py`: mock gamma-api responses, verify WalletHistory fields, cache hit/miss
- [x] 5.2 Write `tests/test_polymarket_alpha_detector.py`: min_trades filter, ranking order, empty list edge case
- [x] 5.3 Write `tests/test_polymarket_copy_signal.py`: consensus calculation, no-positions returns none direction
- [x] 5.4 Run `ruff check` + `mypy` on new files — zero errors
- [x] 5.5 Run `pytest tests/test_polymarket_wallet_tracker.py tests/test_polymarket_alpha_detector.py tests/test_polymarket_copy_signal.py -v` — all pass
