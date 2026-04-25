# Proposal: Polymarket Calibration & Learning Engine

## Why
A trading system that never looks back is permanently blind to its own mistakes. After
phases 1-7 produce real trades with real outcomes, the system has ground truth: we predicted
X%, the market settled YES or NO. A calibration engine closes the loop — it measures how
accurate our AI probability estimates are, detects which market categories we consistently
over or under-estimate, adjusts scorer weights automatically based on observed edge, and
flags when the copy-signal wallets we follow are degrading in quality. Without this, the
system runs the same flawed model forever. With it, every resolved market makes the next
prediction more accurate.

## What Changes

- `core/polymarket_calibration.py` (new): `record_outcome(position, resolved_yes: bool, ledger)`
  — on market resolution, reads our entry probability, the AI estimate, and the actual outcome;
  writes a calibration record to `pm_calibration` table. `compute_calibration_stats(lookback_days)
  -> CalibrationReport` — Brier score per category, reliability diagram data points, win rate
  by category, average edge vs actual outcome.

- `core/polymarket_weight_tuner.py` (new): `tune_weights(calibration_report, current_weights)
  -> WeightUpdate` — adjusts `DEFAULT_WEIGHTS` in polymarket_score.py based on which sub-scores
  predicted well. If `copy_signal` is consistently wrong (wallets we copy losing), reduce its
  weight. If `edge` (AI estimate) is consistently right, increase it. Changes are bounded:
  ±5pp per tuning cycle, written to `data/learned_weights.json`, loaded at scorer startup.

- `core/polymarket_wallet_ranker.py` (new): `rerank_wallets(ledger, tracker) -> list[WalletRank]`
  — periodically re-scores copy-signal wallets by their recent win rate (last 30 days, min 5
  resolved markets). Wallets whose win rate drops below 55% are demoted; new wallets breaking
  above 65% are promoted. Updates `wallet_cache.db` alpha scores in place.

- `core/polymarket_discovery.py` (new): enhanced market discovery consolidating what was
  scattered across `prediction_engine.py` and `polymarket_client.py`. Adds:
  (1) trending endpoint: `GET /markets?order=volumeNum&ascending=false&limit=20` for
  volume-ranked discovery independent of keywords;
  (2) quality filter: volume_24h ≥ $5k, spread ≤ 5pp, 2-180 days to resolution;
  (3) volume-weighted probability: `Σ(prob_i × vol_i) / Σ(vol_i)` instead of naive average;
  (4) deduplication by `condition_id` across keyword + trending results.

- `api/main.py` (updated): `GET /api/polymarket/calibration` → Brier score + win rate +
  category breakdown + weight history; `GET /api/polymarket/wallets` → ranked wallet list
  with current alpha score + win rate + recent activity.

- Ledger: new `pm_calibration` table (outcome records) and `pm_weight_history` table
  (one row per tuning cycle with before/after weights and trigger stats).

## Impact
- Affected code: `core/polymarket_calibration.py`, `core/polymarket_weight_tuner.py`,
  `core/polymarket_wallet_ranker.py`, `core/polymarket_discovery.py`, `api/main.py`,
  `core/polymarket_ledger.py` (new tables), `core/polymarket_score.py` (load learned weights)
- Breaking change: NO — additive; existing scorer falls back to DEFAULT_WEIGHTS if
  `learned_weights.json` absent
- User benefit: System improves automatically after each resolved market; degrading copy
  wallets are demoted before they cause losses; discovery finds high-volume markets that
  keyword search misses; Brier score gives an objective measure of prediction quality.

Source: docs/analysis/alphacota-polymarket-autonomous-trader/

