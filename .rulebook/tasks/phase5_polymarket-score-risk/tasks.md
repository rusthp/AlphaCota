## 1. Market Scorer
- [x] 1.1 Write `core/polymarket_score.py`: `DEFAULT_WEIGHTS` dict (`w_edge=0.35`, `w_liquidity=0.25`, `w_time=0.15`, `w_copy=0.15`, `w_news=0.10`); `validate_weights()` reused from `score_engine`; `score_market(market, context, weights=None) -> MarketScore`
- [x] 1.2 Implement `_edge_score(fair_prob, market_prob) -> float` — calls `ai_engine.estimate_market_probability`; returns 0 if AI returns None (no AI = no edge signal, not a blocker)
- [x] 1.3 Implement `_liquidity_score(order_book, volume_24h) -> float` — penalizes spread >5pp and volume <$5k/day
- [x] 1.4 Implement `_time_decay_score(days_to_resolution) -> float` — peaks at 7-30 days; penalizes <2 days and >180 days

## 2. Risk Engine
- [x] 2.1 Write `core/polymarket_risk.py`: `kelly_fraction(fair_prob, market_prob) -> float` — full Kelly formula for binary markets; clamped to [0, 0.25]
- [x] 2.2 Add `assess_risk(score, wallet_health, open_positions, config) -> RiskDecision` — enforces daily loss cap, max positions, category correlation check; returns `RiskDecision(approved, kelly, reason)`

## 3. Sizing + Decision Engine
- [x] 3.1 Write `core/polymarket_sizing.py`: `size_position(risk_decision, bankroll_usd, max_position_usd) -> float` — returns 0.0 on reject; applies min($kelly*bankroll, max_position_usd)
- [x] 3.2 Write `core/polymarket_decision_engine.py`: `generate_trade_decisions(markets, config) -> list[TradeDecision]` — pure orchestrator, no I/O; calls score → risk → sizing per market

## 4. MCP Tools
- [x] 4.1 Register `score_polymarket_market(condition_id: str)` in MCP tools — fetches market, runs scorer, returns MarketScore dict
- [x] 4.2 Register `get_polymarket_trade_decisions(limit: int = 5)` — runs full decision engine on top discovered markets

## 5. Tail
- [x] 5.1 Write `tests/test_polymarket_score.py`: weight validation, each sub-score function, AI-None fallback
- [x] 5.2 Write `tests/test_polymarket_risk.py`: Kelly formula correctness, daily cap enforcement, category correlation blocks third position
- [x] 5.3 Write `tests/test_polymarket_decision_engine.py`: end-to-end with mocked sub-engines, reject propagates to size=0
- [x] 5.4 Run `ruff check` + `mypy` on new files — zero errors
- [x] 5.5 Run `pytest tests/test_polymarket_score.py tests/test_polymarket_risk.py tests/test_polymarket_decision_engine.py -v` — all pass
