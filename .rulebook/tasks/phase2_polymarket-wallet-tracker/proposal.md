# Proposal: Polymarket Wallet Tracker (Copy-Trading Foundation)

## Why
Polymarket is a public blockchain — every trade by every participant is permanently visible
on-chain. Professional traders ("whales") with verified positive edge can be identified by
their on-chain track record: hit rate above 55%, consistent volume, diversified market
selection, no obvious insider patterns. Copying the position direction of wallets with
proven edge — even partially — provides a second, independent alpha signal that requires
no proprietary model, only fast data ingestion and statistical validation.

This is the copy-trading foundation. No order execution happens here — this task is
purely read-only intelligence: discover wallets, score their historical edge, expose the
signal for use by the scoring engine in phase5.

## What Changes
- `core/polymarket_wallet_tracker.py` (new): given a Polygon wallet address, fetches full
  trade history via Polygonscan API (free tier, public) and Polymarket gamma-api positions
  endpoint. Computes: total trades, win rate, avg position size, avg holding period, preferred
  market categories, realized PnL estimate.
- `core/polymarket_alpha_detector.py` (new): given a list of wallets, ranks them by statistical
  edge (win rate with minimum sample size filter, Sharpe of resolved trades, recency weight).
  Returns top-N "alpha wallets" worth tracking.
- `core/polymarket_copy_signal.py` (new): given alpha wallets + a candidate market, returns
  a `CopySignal` (direction, confidence 0-1, wallet consensus ratio). Pure function, no I/O.
- `data/wallet_cache.db` (new, gitignored): SQLite cache of wallet history with 1h TTL to
  avoid Polygonscan rate limits.
- New MCP tool `get_polymarket_alpha_wallets` registered in `alphacota_mcp/financial_data/tools/`.

## Impact
- Affected code: `core/polymarket_wallet_tracker.py`, `core/polymarket_alpha_detector.py`,
  `core/polymarket_copy_signal.py`, `data/wallet_cache.db`, `alphacota_mcp/financial_data/tools/`
- Breaking change: NO — purely additive
- User benefit: Copy-trading signal from on-chain whale wallets; second independent alpha
  source requiring no model training; fully transparent and auditable.

Source: docs/analysis/alphacota-polymarket-autonomous-trader/
