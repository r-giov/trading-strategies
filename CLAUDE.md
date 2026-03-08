# QS Finance — Quantitative Strategy Research Platform

## Project Overview
This is a systematic trading strategy research platform for passing FTMO prop firm challenges. The owner is building, testing, and comparing indicator-based strategies across multiple asset classes (crypto, forex, indices, commodities) using a rigorous IS/OOS validation framework.

## Architecture
- `notebooks/` — Strategy template notebooks (Jupyter/Colab compatible)
- `lib/` — Shared Python modules (signals, export, metrics)
- `config/` — Ticker lists, FTMO rules, backtest settings
- `exports/` — Local output (gitignored). On Colab, exports to Google Drive.
- `docs/` — Research papers and references

## Strategy Notebooks — Standard Structure (12+ cells)
Every strategy notebook follows this exact cell structure (based on Rick's TEMA template from the trading bootcamp):

1. **Cell 1**: Commented-out pip installs
2. **Cell 2**: Imports (yfinance, talib, numpy, pandas, vectorbt, scipy, matplotlib) + `warnings.filterwarnings('ignore')`
3. **Cell 3**: Download data via yfinance. Config: `TICKER` and `START_DATE` at top. Print count/range/head. Handle MultiIndex.
4. **Cell 4**: Technical indicators using TA-Lib: SMA_20, SMA_50, EMA_12, EMA_26, MACD, RSI(14), StochRSI_K/D, VWAP, STC_K/D. Build `indicators_df`, show `.tail(5)`.
5. **Cell 5**: Prepare price series. `select_close_series()` helper. `TRAIN_RATIO = 0.60`. Print both split date ranges.
6. **Cell 6**: Markdown describing the strategy and grid search.
7. **Cell 7**: Define parameter ranges. Print each value. Print total combo count + "First 10 combinations preview."
8. **Cell 8**: Initialize results collection. Print the full 31-metric list.
9. **Cell 9**: Run grid search on `train_close` only. Skip combos with < 10 trades. Progress every 1000 combos with 🔄. Print top 10 by Sharpe.
10. **Cell 10**: Validate top 5 IS performers on `val_close`. Print IS vs OOS comparison table. Plot equity curves.
11. **Cell 11**: Markdown for sensitivity analysis.
12. **Cell 12**: Sensitivity analysis — 2×3 bar chart grid (IS row, OOS row). Color: dark green >+10%, light green 0–10%, orange -10–0%, red <-10%. Blue dashed vertical at base value. Print SENSITIVITY SUMMARY table with ✅ LOW / ⚠️ HIGH flag.
13. **Cell 13+**: (MACD v2 only) Full-sample eval + B&H comparison + annotated equity curve with stats box + drawdown plot.
14. **Cell 14+**: (MACD v2 only) Trade-by-trade P&L analysis (2×2 grid).
15. **Cell 15+**: (MACD v2 only) Monte Carlo FTMO simulation (10,000 paths).
16. **Last Cell**: Universal export — JSON summary + CSVs + PDF tearsheet to Google Drive.

## Strategy Signal Logic — CRITICAL (1-bar execution delay on all)
All strategies shift raw signals by 1 bar before passing to vectorbt. This prevents lookahead bias.

### MACD Crossover
```python
entries_raw = (macd_s.shift(1) <= signal_s.shift(1)) & (macd_s > signal_s)
exits_raw = (macd_s.shift(1) >= signal_s.shift(1)) & (macd_s < signal_s)
# Then shift 1 more bar for execution delay
```
Params: fast_period, slow_period, signal_period

### RSI Mean-Reversion
```python
entries_raw = (rsi_s.shift(1) <= oversold) & (rsi_s > oversold)  # crosses UP through oversold
exits_raw = (rsi_s.shift(1) <= overbought) & (rsi_s > overbought)  # crosses UP through overbought
```
Params: rsi_len, oversold, overbought

### EMA Crossover + Trend Filter
```python
entries_raw = ((fast_ema.shift(1) <= slow_ema.shift(1)) & (fast_ema > slow_ema) & (close > trend_sma))
exits_raw = ((fast_ema.shift(1) >= slow_ema.shift(1)) & (fast_ema < slow_ema))
```
Params: fast_ema, slow_ema, trend_filter

### Triple EMA Crossover
```python
entries_raw = (ema1.crossed_above(ema2) | ema1.crossed_above(ema3) | ema2.crossed_above(ema3))
exits_raw = (ema1.crossed_below(ema2) | ema1.crossed_below(ema3) | ema2.crossed_below(ema3))
```
Params: ema1_period, ema2_period, ema3_period

### Donchian Channel Breakout
```python
upper_channel = talib.MAX(high, entry_period).shift(1)  # previous bar's channel
lower_channel = talib.MIN(low, exit_period).shift(1)
trend_filter = talib.SMA(close, filter_period).shift(1)
entries_raw = (close > upper_channel) & (close > trend_filter)
exits_raw = (close < lower_channel)
```
Params: entry_period, exit_period, filter_period

## Backtesting Settings (standard across all notebooks)
- `init_cash = 100_000`
- `fees = 0.0005` (0.05%)
- `slippage = 0.0005` (0.05%)
- `freq = 'D'` (daily)
- All vectorbt Sharpe uses `freq='D'`

## FTMO Challenge Rules (for Monte Carlo simulation)
- Account: $100,000
- Profit Target: 10% ($10,000)
- Max Daily Loss: 5% ($5,000)
- Max Total Loss: 10% ($10,000)
- Challenge window: ~30 trading days
- Crypto leverage: 1:3 (standard), 1:1 (swing)

## FTMO Tradeable Crypto (confirmed as of July 2025 — 32 total)
Original: BTCUSD, ETHUSD, LTCUSD, XRPUSD, ADAUSD, DOTUSD, DOGEUSD, DASHUSD, EOSUSD, XLMUSD
July 2025 additions: SOLUSD, AVAXUSD, BNBUSD, LINKUSD, AAVEUSD + 17 more altcoins (need to confirm exact list from FTMO platform)
yfinance format: BTC-USD, ETH-USD, SOL-USD, etc.

## FTMO Asset-Strategy Mapping (research-backed recommendations)
- **Indices (US30, US100, US500, DAX)**: MACD Crossover, Triple EMA — strongest trend persistence
- **Forex Majors (EURUSD, GBPUSD, USDJPY)**: RSI Mean-Reversion — mean-reverting on daily timeframes
- **Commodities (Gold, Crude Oil)**: Donchian Breakout — classic breakout behavior, supply shocks
- **Crypto (BTC, ETH, SOL)**: Donchian + Triple EMA — strongest trends AND heaviest tails
- **Forex Minors/Exotics**: MACD Crossover — trades less frequently, handles wider spreads

## Key Principles from Research Papers (Project Knowledge)

### Carver — Systematic Trading
- Equal-weighting all rule variations beats picking "the best" (SR 0.33 vs 0.07)
- With 5 years of data, need Sharpe cutoff of 2.3 to avoid picking bad rules from a pool of 5
- Correlation between subsystem returns ≈ 0.70 × correlation of instrument returns
- Pessimism factor for backtested returns: handcrafted weights ~70% of backtest, optimized ~25%
- Use EWMAC (Exponentially Weighted Moving Average Crossover) as primary trend rule

### Cont — Empirical Properties of Asset Returns (Stylized Facts)
1. Absence of autocorrelations (returns uncorrelated except < 20min)
2. Heavy tails (power-law, tail index 2-5)
3. Gain/loss asymmetry (large drops, not equally large rises)
4. Aggregational Gaussianity (longer timeframes → more normal)
5. Volatility clustering (high-vol events cluster in time)
6. Slow decay of autocorrelation in absolute returns (β ∈ [0.2, 0.4])
7. Leverage effect (volatility negatively correlated with returns)
Implications: Mean-reversion strategies have negative skew in heavy-tailed assets. Trend-following has positive skew. Volatility clustering makes regime filters valuable.

### Trend Following Research (SG Trend Index)
- Trend following provides "crisis alpha" — performs well when other assets have large swings
- Positive skewness: winners run, losers cut
- Struggles in range-bound markets
- Works across equities, bonds, commodities, FX

### Quantitative Momentum (Wiley)
- Moving average trend overlay limits max drawdown (60% → 26%) at cost of 1.5% annual return
- "Buy 'em cheap, buy 'em strong, hold 'em long — but only when the trend is your friend"
- Trend following enhances tracking error vs index (career risk consideration)

## Export System
Each notebook's final cell exports to Google Drive (Colab) or local (Claude Code):
```
strategy_exports/
├── run_log.csv                     ← Master journal (appends every run)
└── {STRATEGY_NAME}/
    └── {TICKER}/
        ├── latest/
        │   ├── summary.json        ← Full metrics + metadata + Monte Carlo
        │   ├── daily_returns.csv   ← For correlation/ensemble analysis
        │   ├── trades.csv          ← Trade-by-trade log
        │   ├── grid_results.csv    ← Full grid search
        │   └── tearsheet.pdf       ← 4-page visual report
        └── archive/
            ├── {RUN_ID}_summary.json
            └── {RUN_ID}_tearsheet.pdf
```

## Boruta Ensemble Validation (from bootcamp)
For multi-indicator ensemble strategies:
- Compute every combination of indicator signals using OR logic
- Take top 25 ensembles by IS Sharpe per asset
- Boruta validation: shuffle OOS returns 50+ times, count how often real Sharpe beats shadow
- Boruta Score > 80% = statistically significant
- WARNING: Multiple testing bias is severe — need 500+ shuffles for large search spaces

## Meta Prompts (for code review)
- META_PROMPT_1: Financial ML Sanity, Bias & Coherence Audit (check for lookahead, leakage, overfitting)
- META_PROMPT_2: Single-Cell Fracture & Logic Audit (check individual cell correctness)

## Development Notes
- Owner uses Windows (C:\Users\trg\Desktop\QS Finance)
- Colab Pro available for heavy grid searches
- GitHub repo for version control and templates
- This project is in the claude.ai "Quant Finance" project with PDFs attached as knowledge
