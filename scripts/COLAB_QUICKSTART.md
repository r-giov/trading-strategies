# Colab Quick Start

Paste these cells at the top of any Colab session:

## Cell 1 — Clone & Setup
```python
!git clone https://github.com/r-giov/trading-strategies.git 2>/dev/null
%cd trading-strategies
!git pull
%run scripts/colab_setup.py
```

## Cell 2 — Run a strategy (pick one)
```python
# Option A: Open a notebook manually in Colab file browser (left sidebar)

# Option B: Auto-run via script
!python scripts/run_strategy.py --strategy MACD --ticker BTC-USD --start 2020-01-01

# Option C: Batch run multiple tickers
!python scripts/run_strategy.py --strategy Donchian --tickers BTC-USD,ETH-USD,SOL-USD

# Option D: See what's available
!python scripts/run_strategy.py --list
```

## After editing locally with Claude Code
Just re-run `!git pull` in Colab to get the latest changes.
