# ETF Research for Systematic Trading (FTMO Context)

## Top 10 FTMO Instruments Ranked by Strategy Compatibility

1. **US100 (Nasdaq/QQQ)** — MACD Crossover: Strongest trend persistence of any index
2. **XAUUSD (Gold)** — Donchian Breakout: Cleanest commodity trends, no contango
3. **BTCUSD** — Donchian + EMA: Fat tails + persistent trends
4. **EURUSD** — RSI Mean Reversion: Most liquid FX pair, textbook mean reversion on daily
5. **US500 (S&P)** — MACD Crossover: Broad market (NOTE: EMA Crossover failed OOS on SPY — IS Sharpe 1.27 → OOS -0.38)
6. **DAX** — MACD Crossover: Export-driven, trending
7. **ETHUSD** — Donchian: Similar to BTC but higher vol, wider parameters needed
8. **Crude Oil** — Donchian: Supply shock breakouts, no contango on CFD
9. **USDJPY** — MACD Crossover (not RSI): JPY trending due to BOJ policy divergence
10. **GBPUSD** — RSI Mean Reversion: Range-bound, reliable oversold/overbought reversals

## Parameter Scaling by Volatility

| Instrument Vol | MACD | RSI | EMA | Donchian |
|---|---|---|---|---|
| **Low** (0.5-1.0%): Indices, Gold | 12/26/9 | 14, 30/70 | 12/26/50 | 20/10/50 |
| **Medium** (1.0-2.0%): Sectors, FX, Oil | 16/32/12 | 14, 25/75 | 16/32/100 | 25/12/75 |
| **High** (2.0-4.0%): Crypto, EM | 20/40/14 | 21, 20/80 | 20/50/200 | 30/15/100 |

## Alpha Architect Key Insights

1. **Concentration > diversification**: Trade 2-3 instruments per strategy well, not 10 mediocrely
2. **Trend overlay everything**: Even RSI mean-reversion should have SMA(200) filter. Reduces drawdowns 30-50%
3. **Smooth momentum > gappy momentum**: Prefer instruments that trend gradually (US100, XAUUSD, EURUSD) over gappy ones (crypto weekends, crude around OPEC)
4. **Equal-weight rule variations**: Run 3-5 param sets and average signals rather than picking "the best"
5. **12-1 momentum sweet spot**: Instruments trending for weeks but not just last 1-2 days. MACD naturally captures this

## Sector ETF Behavior

### Trending (MACD, EMA, Donchian)
- XLK (Tech), XLE (Energy), XLB (Materials), XLC (Comms), XBI (Biotech)

### Mean-Reverting (RSI)
- XLF (Financials), XLU (Utilities), XLP (Staples), XLRE (Real Estate), XLV (Healthcare)

## Commodity ETFs

| Ticker | Behavior | Strategy | Warning |
|---|---|---|---|
| GLD | Trending | Donchian, MACD | Best commodity for systematic trading |
| SLV | Trending but noisy | Donchian | More volatile than gold |
| USO | Strongly trending | Donchian | Contango drag on ETF (not on FTMO CFD) |
| UNG | Mean-reverting spikes | AVOID | Extreme vol, contango destroys longs |
| DBA | Mild trending | MACD (slow) | Low vol, seasonal |

## Bond ETFs (for broader context)

- **TLT** (20yr Treasury): Strongly trending, great for MACD. -0.3 to -0.5 correlation with SPY
- **HYG** (High Yield): Mean-reverting, RSI works. Equity-lite behavior
- **EMB** (EM Bonds): Trending with crashes, Donchian

## Volatility Products — AVOID
- VXX, UVXY lose 60-80%/year from structural decay
- Standard strategies fail completely on these
- FTMO doesn't offer them anyway

## International Indices for FTMO

- **DAX, Nikkei**: Trending — use MACD/EMA
- **FTSE**: Range-bound — use RSI
- **EM indices**: Trending with gaps — use Donchian cautiously
