---
name: crypto-analysis
description: Technical analysis toolkit for crypto markets. Covers indicator interpretation, strategy selection by market regime, signal confluence scoring, backtest evaluation, and pair correlation. Use when analyzing signals, evaluating strategies, or debugging trade logic.
allowed-tools: Read, Grep, Glob, Bash
---

# Crypto Analysis Skill

> Systematic framework for reading crypto market signals and evaluating strategy performance.

## Content Map

| File | When to Read |
|------|-------------|
| indicators.md | Interpreting RSI, MACD, Bollinger, Stochastic, ADX, Supertrend, CCI, Williams %R |
| strategies.md | Choosing the right strategy for market conditions |
| backtest-eval.md | Reading BacktestResult metrics |
| confluence.md | Combining signals from multiple strategies |
| pairs.md | Pair selection, correlation, and 12-pair reference |

## Core Principle

**No single indicator is reliable alone.** Signal confluence — multiple independent indicators agreeing — is the foundation of high-confidence entries. A combined confidence score above 0.75 with 3+ confirming indicators is the gold standard.

## Quick Reference: Indicator States

```
RSI:      <30=oversold  30-70=neutral  >70=overbought
Stoch %K: <20=oversold  20-80=neutral  >80=overbought
Williams: <-80=oversold -80..-20=neutral  >-20=overbought
CCI:      <-100=oversold  -100..100=neutral  >100=overbought
ADX:      <20=ranging  20-25=weak  >25=trending  >40=strong
Supertrend: direction=-1 bullish, direction=1 bearish
```

## Market Regime → Strategy Map

```
Trending (ADX>25 + EMA aligned):
  → trend_follow, triple_ema, adx_trend, supertrend

Ranging (ADX<20 + BB flat):
  → bollinger_band, stochastic, rsi_reversal, williams_r

Breakout (ATR spike + volume):
  → breakout, volume_breakout, cci_momentum

Unknown / Mixed:
  → combined (weighted ensemble)
```

## Backtest Quality Gates

Reject a strategy if ANY of these fail:
- Sharpe < 0.8 on 200+ candle backtest
- Max drawdown > 25%
- Profit factor < 1.1
- Win rate < 40% (unless profit factor > 2.0)
- Fewer than 10 trades (insufficient sample)

## Signal Confluence Scoring

Score each active signal -1 (short), 0 (flat), +1 (long):
- EMA20 vs EMA50 position
- MACD histogram sign
- RSI zone (>70 = -1, <30 = +1, else 0)
- Supertrend direction (-1 = +1 score, 1 = -1 score)
- Stochastic zone

Sum / count of non-zero signals = confluence ratio.
Confluence > 0.6 → long. < -0.6 → short. Else → flat.
