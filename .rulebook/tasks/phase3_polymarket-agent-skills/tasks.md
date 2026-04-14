## 1. OpenRouter Integration
- [x] 1.1 Add `openrouter_api_key: str = ""` to `OperationalConfig` in `core/config.py`; add `OPENROUTER_API_KEY` to `.env.example`
- [x] 1.2 Add `call_openrouter(model, messages, response_format) -> dict` helper in `core/ai_engine.py` — OpenAI-compatible client pointed at `https://openrouter.ai/api/v1`

## 2. Agent Files
- [x] 2.1 Write `.agent/agents/polymarket-analyst.md`: system prompt specializing in market evaluation, resolution criteria parsing, probability estimation with explicit calibration checklist
- [x] 2.2 Write `.agent/agents/polymarket-risk-manager.md`: system prompt for structured risk reports — Kelly fraction, max loss, correlation check, confidence interval; always outputs JSON
- [x] 2.3 Write `.agent/agents/polymarket-calibrator.md`: system prompt enforcing structured JSON output `{fair_prob, market_prob, edge, confidence, reasoning}`; numeric validation rules explicit in prompt

## 3. AI Engine Extensions
- [x] 3.1 Add `estimate_market_probability(market: dict, context: str) -> dict | None` to `core/ai_engine.py` — uses DeepSeek-R1 via OpenRouter; validates JSON output is numeric in [0,1]; retries once on failure; returns None on second failure
- [x] 3.2 Add `assess_trade_risk_ai(market: dict, direction: str, size_usd: float) -> dict | None` to `core/ai_engine.py` — uses `qwen/qwen3-coder:free`; structured JSON output with Kelly, max_loss, recommendation

## 4. Tail
- [x] 4.1 Write `tests/test_ai_engine_polymarket.py`: mock OpenRouter responses, test JSON validation guardrail rejects bad output, test retry on first failure, test None on second failure
- [x] 4.2 Run `ruff check` + `mypy core/ai_engine.py` — zero errors
- [x] 4.3 Run `pytest tests/test_ai_engine_polymarket.py -v` — all pass
