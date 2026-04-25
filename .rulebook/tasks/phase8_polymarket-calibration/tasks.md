## 1. Enhanced Discovery
- [x] 1.1 Write `core/polymarket_discovery.py`: `discover_markets(config) -> list[Market]` — combines keyword search + trending endpoint (`GET /markets?order=volumeNum&ascending=false&limit=20`); deduplicates by `condition_id`; applies quality filter: `volume_24h >= 5000`, `spread_pct <= 0.05`, `2 <= days_to_resolution <= 180`, `active=true`, `closed=false`
- [x] 1.2 Add `volume_weighted_probability(markets: list[Market]) -> float` — computes `Σ(prob_i × vol_i) / Σ(vol_i)`; falls back to simple average if all volumes are zero
- [x] 1.3 Update `core/polymarket_client.py` to delegate discovery to `polymarket_discovery.py` — remove inline keyword logic from client, keep only raw HTTP methods

## 2. Ledger Tables
- [x] 2.1 Add to `core/polymarket_ledger.py`: `pm_calibration` table — columns: `id`, `condition_id`, `entry_prob`, `ai_estimate`, `resolved_yes` (bool), `category`, `edge_at_entry`, `created_at`; `init_db()` creates it alongside existing tables
- [x] 2.2 Add `pm_weight_history` table — columns: `id`, `tuned_at`, `trigger_markets`, `weights_before` (JSON), `weights_after` (JSON), `brier_score`, `win_rate`
- [x] 2.3 Add `insert_calibration_record(condition_id, entry_prob, ai_estimate, resolved_yes, category, edge_at_entry)` — idempotent on `condition_id`

## 3. Calibration Engine
- [x] 3.1 Write `core/polymarket_calibration.py`: `record_outcome(position, resolved_yes, ledger)` — reads entry probability + AI estimate from ledger, writes calibration record; `compute_calibration_stats(lookback_days=90) -> CalibrationReport` — returns Brier score per category, win rate per category, mean edge vs actual outcome, total resolved count
- [x] 3.2 Implement Brier score: `brier = mean((forecast - outcome)^2)` where `outcome` is 1.0 for YES, 0.0 for NO — lower is better (0.0 = perfect, 0.25 = random)
- [x] 3.3 Add `reliability_bins(lookback_days=90) -> list[ReliabilityPoint]` — groups predictions into 10 probability bins (0-10%, 10-20%, …) and computes actual win rate per bin; used for reliability diagram in API response

## 4. Weight Tuner
- [x] 4.1 Write `core/polymarket_weight_tuner.py`: `tune_weights(report: CalibrationReport, current_weights: dict) -> WeightUpdate` — for each sub-score, if its category Brier score is worse than baseline (0.25), reduce weight by up to 5pp; if better, increase by up to 5pp; total weights always sum to 1.0
- [x] 4.2 Add `save_learned_weights(weights: dict, history_entry: dict, ledger)` — writes to `data/learned_weights.json` and inserts row in `pm_weight_history`
- [x] 4.3 Update `core/polymarket_score.py`: at module load, try to read `data/learned_weights.json`; if present and valid, use as `ACTIVE_WEIGHTS` instead of `DEFAULT_WEIGHTS`; log which weights are in use

## 5. Wallet Ranker
- [x] 5.1 Write `core/polymarket_wallet_ranker.py`: `rerank_wallets(ledger, tracker) -> list[WalletRank]` — for each tracked wallet, queries last 30 days of resolved positions from `wallet_cache.db`; computes win rate (min 5 resolved markets to qualify); promotes wallets >65% win rate, demotes <55%
- [x] 5.2 Add `update_wallet_alpha_scores(rankings: list[WalletRank], db_path)` — updates `alpha_score` column in `wallet_cache.db` in place; logs promotions and demotions
- [x] 5.3 Register `rerank_wallets` call in main loop (`polymarket_loop.py`) — runs once per day (every 288 iterations at 5min cadence)

## 6. API Routes
- [x] 6.1 Add to `api/main.py`: `GET /api/polymarket/calibration` → `CalibrationReport` JSON with Brier score, win rate, category breakdown, reliability bins, weight history (last 5 tuning cycles)
- [x] 6.2 Add `GET /api/polymarket/wallets` → ranked wallet list with fields: `address`, `alpha_score`, `win_rate`, `resolved_count`, `last_active`, `rank_change` (promoted/demoted/stable)

## 7. Tail
- [x] 7.1 Write `tests/test_polymarket_discovery.py`: quality filter rejects low-volume + expired + wide-spread markets; volume-weighted prob weights by volume correctly; dedup removes duplicate condition_ids
- [x] 7.2 Write `tests/test_polymarket_calibration.py`: Brier score formula correct (0.0 for perfect, 0.25 for random 50/50); reliability bins sum to 10; record_outcome is idempotent
- [x] 7.3 Write `tests/test_polymarket_weight_tuner.py`: weights always sum to 1.0 after tuning; bad-performing category loses weight; change bounded at ±5pp; learned_weights.json loaded at scorer startup
- [x] 7.4 Write `tests/test_polymarket_wallet_ranker.py`: wallet below 55% win rate demoted; wallet above 65% promoted; wallet with <5 resolved markets excluded from ranking
- [x] 7.5 Run `ruff check` + `mypy` on all new/modified files — zero errors
- [x] 7.6 Run `pytest tests/test_polymarket_discovery.py tests/test_polymarket_calibration.py tests/test_polymarket_weight_tuner.py tests/test_polymarket_wallet_ranker.py -v` — all pass
