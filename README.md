# Trading Strategies

Systematic trading strategy research platform for FTMO prop firm challenges. Strategies are backtested with IS/OOS validation, sensitivity analysis, and Monte Carlo simulation.

## Strategies

| Strategy | Signal Type | Best For |
|---|---|---|
| MACD Crossover | Trend following | Indices, Forex minors |
| RSI Mean Reversion | Mean reversion | Forex majors |
| EMA Crossover + Trend Filter | Trend following | Multi-asset |
| Donchian Channel Breakout | Breakout | Commodities, Crypto |

## Repo Structure

```
notebooks/    — Strategy notebooks (Jupyter/Colab compatible)
lib/          — Shared modules (universal export, command center)
config/       — Ticker lists, FTMO rules, backtest settings
exports/      — Local output (gitignored)
docs/         — Research references
```

## Backtest Settings

- Initial cash: $100,000
- Fees: 0.05% | Slippage: 0.05%
- Frequency: Daily
- Train/Val split: 60/40
- All signals use 1-bar execution delay (no lookahead)

## Setup

```bash
pip install yfinance ta-lib numpy pandas vectorbt scipy matplotlib
```

Run any notebook in Jupyter or Google Colab. The universal export cell saves structured output (JSON + CSV + PDF tearsheet) to Google Drive or local `exports/`.
