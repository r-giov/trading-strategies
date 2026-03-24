"""
Live trading configuration — multi-strategy FTMO portfolio.
Best params sourced from grid search + OOS validation in strategy notebooks.

Portfolio groups (5 strategy sleeves):
  - ftmo_crypto:          6 components — Donchian + MACD on BTC, ETH, XRP, SOL
  - 3ema_ensemble:        8 components — Triple EMA on NASDAQ + FANG mega-caps
  - macd_portfolio:       5 components — MACD on healthcare/defensive
  - donchian_portfolio:   8 components — Donchian on energy/value/industrials
  - supertrend_portfolio: 8 components — Supertrend on indices + blue-chip stocks
"""

import os
from pathlib import Path
from dotenv import load_dotenv

_live_dir = Path(__file__).resolve().parent
_root = _live_dir.parent
load_dotenv(_live_dir / ".env")
load_dotenv(_root / ".env")

# ── MT5 Connection ──────────────────────────────────────────────────
MT5_LOGIN    = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER   = os.getenv("MT5_SERVER", "")
MT5_PATH     = os.getenv("MT5_PATH", "")

# ── Telegram Alerts (optional) ──────────────────────────────────────
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID   = os.getenv("TG_CHAT_ID", "")

# ── FTMO Rules ──────────────────────────────────────────────────────
ACCOUNT_SIZE      = 100_000
PROFIT_TARGET     = 10_000   # 10%
MAX_DAILY_LOSS    = 5_000    # 5%
MAX_TOTAL_LOSS    = 10_000   # 10%
CRYPTO_LEVERAGE   = 3
CHALLENGE_DAYS    = 30

# Safety buffers — stop trading before hitting hard limits
DAILY_LOSS_BUFFER = 0.80     # stop at 80% of daily limit ($4,000)
TOTAL_LOSS_BUFFER = 0.80     # stop at 80% of total limit ($8,000)

# ── Portfolio Components ─────────────────────────────────────────────
# Each component generates independent BUY/SELL/HOLD signals.
# Components on the same symbol are aggregated before execution.
# Weights are equal within each group (Carver: equal weighting beats optimized).

PORTFOLIO = [
    # ── FTMO Crypto (existing 6) ─────────────────────────────────────
    {
        "id": "DONCHIAN_XRPUSD",
        "symbol": "XRPUSD",
        "yf_ticker": "XRP-USD",
        "strategy": "Donchian_Breakout",
        "group": "ftmo_crypto",
        "weight": 1/6,
        "entry_period": 10,
        "exit_period": 3,
        "filter_period": 20,
        "oos_sharpe": 1.282,
        "ftmo_pass_rate": 37.4,
    },
    {
        "id": "MACD_BTCUSD",
        "symbol": "BTCUSD",
        "yf_ticker": "BTC-USD",
        "strategy": "MACD_Crossover",
        "group": "ftmo_crypto",
        "weight": 1/6,
        "fast_period": 30,
        "slow_period": 59,
        "signal_period": 6,
        "oos_sharpe": 0.961,
        "ftmo_pass_rate": 35.8,
    },
    {
        "id": "MACD_XRPUSD",
        "symbol": "XRPUSD",
        "yf_ticker": "XRP-USD",
        "strategy": "MACD_Crossover",
        "group": "ftmo_crypto",
        "weight": 1/6,
        "fast_period": 22,
        "slow_period": 39,
        "signal_period": 3,
        "oos_sharpe": 0.573,
        "ftmo_pass_rate": 39.8,
    },
    {
        "id": "MACD_ETHUSD",
        "symbol": "ETHUSD",
        "yf_ticker": "ETH-USD",
        "strategy": "MACD_Crossover",
        "group": "ftmo_crypto",
        "weight": 1/6,
        "fast_period": 29,
        "slow_period": 44,
        "signal_period": 5,
        "oos_sharpe": 0.600,
        "ftmo_pass_rate": 44.1,
    },
    {
        "id": "DONCHIAN_BTCUSD",
        "symbol": "BTCUSD",
        "yf_ticker": "BTC-USD",
        "strategy": "Donchian_Breakout",
        "group": "ftmo_crypto",
        "weight": 1/6,
        "entry_period": 31,
        "exit_period": 17,
        "filter_period": 70,
        "oos_sharpe": 0.418,
        "ftmo_pass_rate": 34.0,
    },
    {
        "id": "DONCHIAN_SOLUSD",
        "symbol": "SOLUSD",
        "yf_ticker": "SOL-USD",
        "strategy": "Donchian_Breakout",
        "group": "ftmo_crypto",
        "weight": 1/6,
        "entry_period": 15,
        "exit_period": 7,
        "filter_period": 55,
        "oos_sharpe": None,
        "ftmo_pass_rate": 48.4,
    },

    # ── 3EMA Ensemble — Tech/Growth (8 instruments) ──────────────────
    # Source: _run_ensemble_v3.py — Triple EMA crossover with trend filter
    # Params: grid-searched EMA short/med/long; defaults from ensemble v3
    {
        "id": "3EMA_US100",
        "symbol": "US100.cash",
        "yf_ticker": "^IXIC",
        "strategy": "Triple_EMA",
        "group": "3ema_ensemble",
        "weight": 1/8,
        "ema1_period": 8,
        "ema2_period": 21,
        "ema3_period": 55,
    },
    {
        "id": "3EMA_META",
        "symbol": "META",
        "yf_ticker": "META",
        "strategy": "Triple_EMA",
        "group": "3ema_ensemble",
        "weight": 1/8,
        "ema1_period": 8,
        "ema2_period": 21,
        "ema3_period": 55,
    },
    {
        "id": "3EMA_GOOG",
        "symbol": "GOOG",
        "yf_ticker": "GOOG",
        "strategy": "Triple_EMA",
        "group": "3ema_ensemble",
        "weight": 1/8,
        "ema1_period": 8,
        "ema2_period": 21,
        "ema3_period": 55,
    },
    {
        "id": "3EMA_NFLX",
        "symbol": "NFLX",
        "yf_ticker": "NFLX",
        "strategy": "Triple_EMA",
        "group": "3ema_ensemble",
        "weight": 1/8,
        "ema1_period": 8,
        "ema2_period": 21,
        "ema3_period": 55,
    },
    {
        "id": "3EMA_TSLA",
        "symbol": "TSLA",
        "yf_ticker": "TSLA",
        "strategy": "Triple_EMA",
        "group": "3ema_ensemble",
        "weight": 1/8,
        "ema1_period": 8,
        "ema2_period": 21,
        "ema3_period": 55,
    },
    {
        "id": "3EMA_AAPL",
        "symbol": "AAPL",
        "yf_ticker": "AAPL",
        "strategy": "Triple_EMA",
        "group": "3ema_ensemble",
        "weight": 1/8,
        "ema1_period": 8,
        "ema2_period": 21,
        "ema3_period": 55,
    },
    {
        "id": "3EMA_AMZN",
        "symbol": "AMZN",
        "yf_ticker": "AMZN",
        "strategy": "Triple_EMA",
        "group": "3ema_ensemble",
        "weight": 1/8,
        "ema1_period": 8,
        "ema2_period": 21,
        "ema3_period": 55,
    },
    {
        "id": "3EMA_NVDA",
        "symbol": "NVDA",
        "yf_ticker": "NVDA",
        "strategy": "Triple_EMA",
        "group": "3ema_ensemble",
        "weight": 1/8,
        "ema1_period": 8,
        "ema2_period": 21,
        "ema3_period": 55,
    },

    # ── MACD Portfolio — Healthcare/Defensive (5 instruments) ─────────
    # Source: _strat_macd_portfolio.py — MACD crossover + SMA trend filter
    # Params: MACD fast/slow/signal, default 12/26/9 (grid-searched in notebook)
    # ── MACD Portfolio — MT5-available only (JNJ, WMT) ──────────────
    {
        "id": "MACDP_JNJ",
        "symbol": "JNJ",
        "yf_ticker": "JNJ",
        "strategy": "MACD_Crossover",
        "group": "macd_portfolio",
        "weight": 1/2,
        "fast_period": 12,
        "slow_period": 26,
        "signal_period": 9,
    },
    {
        "id": "MACDP_WMT",
        "symbol": "WMT",
        "yf_ticker": "WMT",
        "strategy": "MACD_Crossover",
        "group": "macd_portfolio",
        "weight": 1/2,
        "fast_period": 12,
        "slow_period": 26,
        "signal_period": 9,
    },

    # ── Donchian Portfolio — MT5-available only (XOM, CVX, JPM) ──────
    {
        "id": "DONCP_XOM",
        "symbol": "XOM",
        "yf_ticker": "XOM",
        "strategy": "Donchian_Breakout",
        "group": "donchian_portfolio",
        "weight": 1/3,
        "entry_period": 20,
        "exit_period": 10,
        "filter_period": 50,
    },
    {
        "id": "DONCP_CVX",
        "symbol": "CVX",
        "yf_ticker": "CVX",
        "strategy": "Donchian_Breakout",
        "group": "donchian_portfolio",
        "weight": 1/3,
        "entry_period": 20,
        "exit_period": 10,
        "filter_period": 50,
    },
    {
        "id": "DONCP_JPM",
        "symbol": "JPM",
        "yf_ticker": "JPM",
        "strategy": "Donchian_Breakout",
        "group": "donchian_portfolio",
        "weight": 1/3,
        "entry_period": 20,
        "exit_period": 10,
        "filter_period": 50,
    },

    # ── Supertrend Portfolio — MT5-available only (6 instruments) ─────
    {
        "id": "SUPER_US30",
        "symbol": "US30.cash",
        "yf_ticker": "^DJI",
        "strategy": "Supertrend",
        "group": "supertrend_portfolio",
        "weight": 1/6,
        "atr_period": 14,
        "multiplier": 3.0,
        "trend_sma": 0,
    },
    {
        "id": "SUPER_US500",
        "symbol": "US500.cash",
        "yf_ticker": "^GSPC",
        "strategy": "Supertrend",
        "group": "supertrend_portfolio",
        "weight": 1/6,
        "atr_period": 14,
        "multiplier": 3.0,
        "trend_sma": 0,
    },
    {
        "id": "SUPER_GER40",
        "symbol": "GER40.cash",
        "yf_ticker": "^GDAXI",
        "strategy": "Supertrend",
        "group": "supertrend_portfolio",
        "weight": 1/6,
        "atr_period": 14,
        "multiplier": 3.0,
        "trend_sma": 0,
    },
    {
        "id": "SUPER_UK100",
        "symbol": "UK100.cash",
        "yf_ticker": "^FTSE",
        "strategy": "Supertrend",
        "group": "supertrend_portfolio",
        "weight": 1/6,
        "atr_period": 14,
        "multiplier": 3.0,
        "trend_sma": 0,
    },
    {
        "id": "SUPER_MSFT",
        "symbol": "MSFT",
        "yf_ticker": "MSFT",
        "strategy": "Supertrend",
        "group": "supertrend_portfolio",
        "weight": 1/6,
        "atr_period": 14,
        "multiplier": 3.0,
        "trend_sma": 0,
    },
    {
        "id": "SUPER_V",
        "symbol": "V",
        "yf_ticker": "V",
        "strategy": "Supertrend",
        "group": "supertrend_portfolio",
        "weight": 1/6,
        "atr_period": 14,
        "multiplier": 3.0,
        "trend_sma": 0,
    },
]

# Derived lookups
SYMBOLS = sorted(set(c["symbol"] for c in PORTFOLIO))

STRATEGIES_BY_SYMBOL = {}
for _comp in PORTFOLIO:
    _sym = _comp["symbol"]
    if _sym not in STRATEGIES_BY_SYMBOL:
        STRATEGIES_BY_SYMBOL[_sym] = []
    STRATEGIES_BY_SYMBOL[_sym].append(_comp)

# ── Timing ──────────────────────────────────────────────────────────
# Crypto daily bar closes at midnight UTC
SIGNAL_CHECK_HOUR_UTC = 0
SIGNAL_CHECK_MINUTE_UTC = 5

# ── Logging ─────────────────────────────────────────────────────────
LOG_DIR = _root / "live" / "logs"
LOG_DIR.mkdir(exist_ok=True)
