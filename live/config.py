"""
Live trading configuration for FTMO crypto portfolio.
Best params sourced from grid search + OOS validation.

Portfolio: 6 components (equal-weighted per Carver's principle)
  - Donchian Breakout: XRP, BTC, SOL
  - MACD Crossover: BTC, XRP, ETH
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
# Equal-weighted (1/6 each) — Carver: equal weighting beats "picking the best"
# Each component generates independent BUY/SELL/HOLD signals.
# Components on the same symbol are aggregated before execution.

PORTFOLIO = [
    {
        "id": "DONCHIAN_XRPUSD",
        "symbol": "XRPUSD",
        "yf_ticker": "XRP-USD",
        "strategy": "Donchian_Breakout",
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
        "weight": 1/6,
        "entry_period": 15,
        "exit_period": 7,
        "filter_period": 55,
        "oos_sharpe": None,
        "ftmo_pass_rate": 48.4,
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
