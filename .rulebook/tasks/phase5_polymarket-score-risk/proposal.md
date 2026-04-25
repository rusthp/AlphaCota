# Proposal: Polymarket Scoring + Risk Engine

## Why
A trading system that executes without an explicit, auditable model for "how good is this bet?"
is gambling, not trading. This task builds the quantitative core: a market scorer that combines
five independent signals into a single 0-100 score, a risk engine that computes Kelly fraction
for binary markets and enforces hard position limits, and a decision engine that orchestrates
both into a `TradeDecision` per candidate market.

The existing `core/score_engine.py` (FII alpha score) and `core/risk_engine.py` (volatility)
prove the pattern works — this task replicates the structure for a fundamentally different
payoff structure: binary yes/no resolution with asymmetric risk.

## What Changes
- `core/polymarket_score.py` (new): `score_market(market, context) -> MarketScore` with
  explicit `DEFAULT_WEIGHTS` dict (mirrors `score_engine.py`). Five sub-scores:
  `edge` (AI fair_prob vs market_prob), `liquidity` (volume + spread + book depth),
  `time_decay` (days to resolution — penalizes very long or very short windows),
  `copy_signal` (from phase2 wallet tracker), `news_sentiment` (Groq on market question).
- `core/polymarket_risk.py` (new): `assess_risk(score, wallet_health, open_positions) -> RiskDecision`.
  Implements full Kelly criterion for binary markets (`f* = (p*b - q) / b` where b = odds).
  Caps Kelly at 25%. Enforces `MAX_POSITION_USD`. Checks daily loss headroom. Correlation
  check: skips market if >2 open positions share the same underlying event category.
- `core/polymarket_sizing.py` (new): `size_position(risk_decision, bankroll_usd) -> float`.
  Pure function. Applies both Kelly and hard cap. Returns 0.0 if risk decision is reject.
- `core/polymarket_decision_engine.py` (new): orchestrator (mirrors `decision_engine.py`).
  `generate_trade_decisions(markets, config) -> list[TradeDecision]`. Composes discovery +
  score + risk + sizing. Pure function.
- MCP tools: `score_polymarket_market(condition_id)`, `get_polymarket_trade_decisions()`.

## Impact
- Affected code: `core/polymarket_score.py`, `core/polymarket_risk.py`,
  `core/polymarket_sizing.py`, `core/polymarket_decision_engine.py`, MCP tools
- Breaking change: NO — additive
- User benefit: Every trade decision is explainable with a score breakdown and Kelly
  fraction; hard limits enforced mathematically; copy signal integrated as one of five factors.

Source: docs/analysis/alphacota-polymarket-autonomous-trader/
