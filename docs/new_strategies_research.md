# New Strategy Research — Candidates for Implementation

## Priority Order for FTMO Challenge

| # | Strategy | Params | Best For | Status |
|---|---|---|---|---|
| 1 | Bollinger Squeeze (Vol Breakout) | bb_period, atr_period, squeeze_lookback | Crypto, commodities | BUILDING |
| 2 | ADX + DI Crossover | adx_period, adx_threshold, exit_threshold | Indices, forex | TODO |
| 3 | ATR Volatility Breakout | atr_period, sma_period, atr_mult | Universal | BUILDING |
| 4 | Keltner Channel Breakout | kc_period, atr_period, kc_mult | Commodities, crypto | TODO |
| 5 | Bollinger Band Mean Reversion | bb_period, bb_std, exit_type | Forex, indices | BUILDING |
| 6 | CCI Trend | cci_period, entry_level, exit_level | Commodities | TODO |
| 7 | Parabolic SAR | af_start, af_max, trend_filter | Trending assets | TODO |
| 8 | Stochastic Oscillator | k_period, d_period, oversold, overbought | Forex, indices | TODO |

## Strategy Details

### 1. Bollinger Band Squeeze (Volatility Breakout)
Catches explosive moves after quiet periods. BB inside KC = squeeze. Release + breakout = entry.
```python
squeeze = (bb_lower > kc_lower) & (bb_upper < kc_upper)
squeeze_release = squeeze.shift(1) & ~squeeze
entries_raw = squeeze_release & (close > bb_upper)
exits_raw = (close.shift(1) >= bb_mid.shift(1)) & (close < bb_mid)
```
Source: John Carter "Mastering the Trade", Bollinger squeeze pattern

### 2. ADX + DI Crossover
Only enters when trend is STRONG. Unique — nothing else measures trend strength.
```python
entries_raw = ((plus_di.shift(1) <= minus_di.shift(1)) & (plus_di > minus_di) & (adx > adx_threshold))
exits_raw = ((plus_di.shift(1) >= minus_di.shift(1)) & (plus_di < minus_di)) | (adx < exit_threshold)
```
Source: Wilder "New Concepts in Technical Trading Systems" (1978)

### 3. ATR Volatility Breakout
Adaptive bands that widen in high vol, tighten in low vol. Smarter Donchian.
```python
entries_raw = (close > sma + atr_mult * atr)
exits_raw = (close < sma - exit_mult * atr)
```
Source: Kaufman "Trading Systems and Methods", Kestner "Quantitative Trading Strategies"

### 4. Keltner Channel Breakout
EMA + ATR bands. Less whipsaw than Donchian in choppy markets.
```python
entries_raw = (close.shift(1) <= kc_upper.shift(1)) & (close > kc_upper)
exits_raw = (close.shift(1) >= kc_mid.shift(1)) & (close < kc_mid)
```
Source: Chester Keltner (1960), Linda Bradford Raschke modernized version

### 5. Bollinger Band Mean Reversion
Buy below lower band, exit at middle. Volatility-adjusted mean reversion.
```python
entries_raw = (close.shift(1) >= bb_lower.shift(1)) & (close < bb_lower)
exits_raw = (close.shift(1) <= bb_mid.shift(1)) & (close > bb_mid)
```
Source: Bollinger "Bollinger on Bollinger Bands" (2001)

### 6. CCI Trend
Uses typical price (H+L+C)/3 normalized by mean absolute deviation. Unique math.
```python
entries_raw = (cci.shift(1) <= entry_level) & (cci > entry_level)
exits_raw = (cci.shift(1) >= exit_level) & (cci < exit_level)
```
Source: Donald Lambert (1980), Kaufman validation

### 7. Parabolic SAR
Accelerating trailing stop. Only 2 core params = fast grid search.
```python
entries_raw = (close.shift(1) <= sar.shift(1)) & (close > sar)
exits_raw = (close.shift(1) >= sar.shift(1)) & (close < sar)
```
Source: Wilder (1978)

### 8. Stochastic Oscillator
Range-based oversold vs RSI's momentum-based. ~0.5 correlation with RSI signals.
```python
entries_raw = ((slowk.shift(1) <= slowd.shift(1)) & (slowk > slowd) & (slowk < oversold))
exits_raw = ((slowk.shift(1) >= slowd.shift(1)) & (slowk < slowd) & (slowk > overbought))
```
Source: George Lane (1950s), Brock/Lakonishok/LeBaron (1992) Journal of Finance

## Correlation Gap Analysis
Existing strategies cover: MA crossovers (MACD, EMA), oscillator MR (RSI), price breakout (Donchian)

New strategies fill:
- **Volatility regime change**: Bollinger Squeeze (unique)
- **Trend strength filtering**: ADX (unique)
- **Volatility-normalized breakout**: ATR, Keltner (adaptive vs fixed Donchian)
- **Alternative mean reversion**: BB MR, CCI, Stochastic (different math from RSI)
- **Adaptive trailing**: Parabolic SAR (accelerating stops)
