---
name: investment-personas
description: Investment philosophy lenses for crypto trade analysis. Applies Buffett (value), Dalio (macro/risk), Tudor Jones (trend/momentum), and Livermore (volume/tape) frameworks to crypto signals. Use when explaining trade rationale or validating strategy fit.
allowed-tools: Read, Grep, Glob
---

# Investment Personas Skill

> Think like legendary investors. Apply timeless principles to crypto markets.

## The Four Lenses

### Warren Buffett — Value & Quality

**Core principle**: "Price is what you pay, value is what you get."

In crypto context:
- Prefer assets with real utility and adoption (BTC, ETH, BNB) over speculative memes
- Only enter when the price is clearly below intrinsic trend value (strong RSI oversold + EMA support)
- Never chase. Miss the trade rather than overpay.
- **Best strategy fit**: RSI reversal at major support levels, Bollinger Band lower touch

**Buffett checklist for a trade:**
- [ ] Is this asset a market leader with a real use case?
- [ ] Is price below the 200-period EMA (buying the dip, not the peak)?
- [ ] Is RSI below 35 (value territory)?
- [ ] Is there a clear catalyst or is this just random noise?

### Ray Dalio — Macro & Risk Parity

**Core principle**: "Diversify across uncorrelated assets and always know your risk."

In crypto context:
- Crypto is one risk-on asset class — treat all 12 pairs as correlated during risk-off events
- Reduce position size when BTC is breaking major support (systemic risk)
- Balance long exposure across uncorrelated pairs (BTC + SOL + XRP are less correlated than BTC + ETH)
- **Best strategy fit**: Combined strategy with diversified pair exposure, ADX trend with conservative sizing

**Dalio checklist for a trade:**
- [ ] Is the macro environment risk-on or risk-off? (BTC above/below 200 EMA)
- [ ] Are we at max position count already? (Dalio would limit to 15 uncorrelated positions)
- [ ] Is position sized according to volatility? (Kelly criterion applies here)
- [ ] If this trade fails, does it breach the daily loss cap? (Dalio's loss limits)

### Paul Tudor Jones — Trend & Momentum

**Core principle**: "The trend is your friend until the bend at the end."

In crypto context:
- Trade WITH the trend, not against it — RSI reversal only at genuine exhaustion
- Cut losses quickly; let winners run (asymmetric TP/SL ratios like 3:1)
- Volume confirms trend: a move without volume is a fake
- **Best strategy fit**: Supertrend, Triple EMA, MACD momentum, Volume breakout

**Tudor Jones checklist for a trade:**
- [ ] Is price above/below all major EMAs? (EMA9/21/55 alignment)
- [ ] Is ADX > 25? (Trend is real, not noise)
- [ ] Is the volume expanding in the direction of the trade?
- [ ] Is the TP at least 2× the SL distance? (Risk/reward discipline)

### Jesse Livermore — Tape Reading & Volume

**Core principle**: "The market is never wrong; opinions often are."

In crypto context:
- Price action + volume tell the truth; indicators lag — use them to confirm, not lead
- Patience: wait for the breakout, then follow immediately
- Don't average down on a losing position
- **Best strategy fit**: Volume breakout, ATR breakout, CCI momentum

**Livermore checklist for a trade:**
- [ ] Is there a volume spike (>2× average) confirming the price move?
- [ ] Has price cleared a clear resistance/support level with conviction?
- [ ] Is this a fresh breakout or a failed retest?
- [ ] Is the stop loss below the breakout level (logical stop, not arbitrary)?

## Applying Personas in Practice

Use multiple lenses to stress-test a signal:

```
Signal: SOL/USDT LONG — Supertrend flipped bullish, ADX=32, Volume=2.3× avg

Buffett: ✓ SOL has real utility; price near 50EMA support
Dalio:   ✓ Macro risk-on; BTC above 200EMA; position count = 1/3
Jones:   ✓ All EMAs aligned bullish; ADX > 25; strong trend
Livermore: ✓ Volume spike confirms; clear breakout above resistance

Verdict: 4/4 lenses agree → HIGH CONFIDENCE ENTRY
```

If fewer than 3 lenses agree → reduce size or skip the trade.
