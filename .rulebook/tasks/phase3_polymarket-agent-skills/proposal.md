# Proposal: Polymarket AI Agent Skills

## Why
The current `core/ai_engine.py` uses Groq/Llama only for FII news sentiment — a single generic
prompt that asks "is this news good or bad for this stock?". This is far too blunt for Polymarket
trading, which requires structured probabilistic reasoning: estimating calibrated probabilities,
detecting market inefficiencies, evaluating liquidity risks, and reasoning about resolution
criteria. A generic LLM without domain-specific prompting and structured output validation will
produce uncalibrated outputs that look plausible but have no predictive value.

The project's `.agent/agents/` directory has 20 agent definitions but none are specific to
prediction markets or quantitative trading. This task fills that gap with purpose-built agents
and the `core/ai_engine.py` extensions they depend on.

## What Changes
- `.agent/agents/polymarket-analyst.md` (new): specialist agent that evaluates individual
  Polymarket markets — reads question, resolution criteria, time to close, order book depth,
  and estimates fair probability with explicit reasoning chain. Uses DeepSeek-R1 via OpenRouter
  for chain-of-thought (free tier, better calibration than Llama for structured reasoning).
- `.agent/agents/polymarket-risk-manager.md` (new): agent focused exclusively on risk —
  given a proposed trade (market, size, direction), produces a structured risk report:
  Kelly fraction, max loss scenario, correlation with open positions, confidence interval.
- `.agent/agents/polymarket-calibrator.md` (new): agent that compares the LLM's probability
  estimate against market-implied price and quantifies the edge. Requires structured JSON output
  with `fair_prob`, `market_prob`, `edge`, `confidence`, `reasoning`.
- `core/ai_engine.py` (updated): add `estimate_market_probability(market, context) -> dict`
  function using the calibrator agent pattern — structured JSON output with numeric validation
  guardrails (rejects non-numeric output, retries once, returns None on second failure).
- `core/ai_engine.py` (updated): add `assess_trade_risk_ai(trade_intent) -> dict` using the
  risk-manager agent pattern.
- OpenRouter integration: add `OPENROUTER_API_KEY` to config; use `qwen/qwen3-coder:free` for
  standard tasks and `deepseek/deepseek-r1:free` for probability estimation (chain-of-thought).

## Impact
- Affected code: `.agent/agents/` (3 new files), `core/ai_engine.py`, `core/config.py`
- Breaking change: NO — additive only
- User benefit: Calibrated probability estimates with explicit reasoning; structured risk
  assessment per trade; better models (DeepSeek R1) for reasoning tasks without added cost.

Source: docs/analysis/alphacota-polymarket-autonomous-trader/
