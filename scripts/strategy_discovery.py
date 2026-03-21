#!/usr/bin/env python3
"""
Strategy Discovery Engine — Autonomous Strategy Search
========================================================

Generates, backtests, and filters strategy variants automatically.
Run it and walk away — it prints winners as it finds them.

Usage:
    python scripts/strategy_discovery.py
    python scripts/strategy_discovery.py --tickers QQQ,SPY,BTC-USD
    python scripts/strategy_discovery.py --target-winners 20 --min-sharpe 1.5
    python scripts/strategy_discovery.py --start 2015-01-01 --batch-size 200

Options:
    --tickers STR        Comma-separated tickers (default: QQQ,SPY,BTC-USD,GC=F,EURUSD=X)
    --start DATE         Start date (default: 2018-01-01)
    --target-winners N   Stop after N winners (default: 50, 0=infinite)
    --batch-size N       Recipes per batch (default: 100)
    --min-sharpe F       Min OOS Sharpe (default: 1.0)
    --max-dd F           Max OOS drawdown fraction (default: 0.15)
    --min-trades N       Min OOS trades (default: 30)
    --min-pf F           Min OOS profit factor (default: 1.2)
    --seed N             Random seed for reproducibility
"""

import os
import sys
import json
import argparse
import hashlib
import warnings
import time
from datetime import datetime
from itertools import product as iterproduct

import numpy as np
import pandas as pd
import talib
import vectorbt as vbt
import matplotlib
matplotlib.use("Agg")  # non-interactive backend for PDF generation
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")

# Add repo root to path
_repo = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _repo not in sys.path:
    sys.path.insert(0, _repo)


# ════════════════════════════════════════════════════════════════
# INDICATOR REGISTRY — the gene pool
# ════════════════════════════════════════════════════════════════

INDICATOR_REGISTRY = {
    "EMA": {
        "fn": talib.EMA, "input": "close",
        "params": {"timeperiod": [5, 8, 10, 12, 13, 15, 20, 21, 26, 30, 34, 50, 100, 200]},
    },
    "SMA": {
        "fn": talib.SMA, "input": "close",
        "params": {"timeperiod": [10, 20, 30, 50, 100, 200]},
    },
    "RSI": {
        "fn": talib.RSI, "input": "close",
        "params": {"timeperiod": [7, 9, 14, 21]},
    },
    "MACD": {
        "fn": talib.MACD, "input": "close",
        "params": {"fastperiod": [8, 10, 12], "slowperiod": [21, 26, 30], "signalperiod": [7, 9, 12]},
    },
    "BBANDS": {
        "fn": talib.BBANDS, "input": "close",
        "params": {"timeperiod": [14, 20, 30], "nbdevup": [1.5, 2.0, 2.5], "nbdevdn": [1.5, 2.0, 2.5]},
    },
    "STOCH": {
        "fn": talib.STOCH, "input": "hlc",
        "params": {"fastk_period": [5, 9, 14], "slowk_period": [3, 5], "slowd_period": [3, 5]},
    },
    "CCI": {
        "fn": talib.CCI, "input": "hlc",
        "params": {"timeperiod": [14, 20, 30]},
    },
    "ADX": {
        "fn": talib.ADX, "input": "hlc",
        "params": {"timeperiod": [14, 21]},
    },
    "ATR": {
        "fn": talib.ATR, "input": "hlc",
        "params": {"timeperiod": [14, 21]},
    },
    "DC_UPPER": {
        "fn": talib.MAX, "input": "high",
        "params": {"timeperiod": [10, 20, 30, 55]},
    },
    "DC_LOWER": {
        "fn": talib.MIN, "input": "low",
        "params": {"timeperiod": [5, 10, 20]},
    },
    "WILLR": {
        "fn": talib.WILLR, "input": "hlc",
        "params": {"timeperiod": [14, 21]},
    },
    "MOM": {
        "fn": talib.MOM, "input": "close",
        "params": {"timeperiod": [10, 14, 21]},
    },
}

# Strategy families and their compatible rules
STRATEGY_FAMILIES = {
    "ma_crossover": {
        "desc": "Moving average crossover",
        "indicators": ["EMA", "SMA"],
        "needs": 2,  # two MAs with different periods
    },
    "triple_ma": {
        "desc": "Triple MA crossover",
        "indicators": ["EMA"],
        "needs": 3,
    },
    "macd_crossover": {
        "desc": "MACD line crosses signal line",
        "indicators": ["MACD"],
        "needs": 1,
    },
    "rsi_mean_revert": {
        "desc": "RSI oversold/overbought mean reversion",
        "indicators": ["RSI"],
        "needs": 1,
    },
    "bollinger_mean_revert": {
        "desc": "Bollinger Band mean reversion",
        "indicators": ["BBANDS"],
        "needs": 1,
    },
    "donchian_breakout": {
        "desc": "Donchian channel breakout",
        "indicators": ["DC_UPPER", "DC_LOWER"],
        "needs": 2,
    },
    "cci_threshold": {
        "desc": "CCI threshold crossover",
        "indicators": ["CCI"],
        "needs": 1,
    },
    "stoch_mean_revert": {
        "desc": "Stochastic oscillator mean reversion",
        "indicators": ["STOCH"],
        "needs": 1,
    },
    "momentum_breakout": {
        "desc": "Momentum + trend filter breakout",
        "indicators": ["MOM", "SMA"],
        "needs": 2,
    },
}

# Optional filters that can be added to any strategy
OPTIONAL_FILTERS = [
    None,  # no filter
    {"type": "trend_sma", "period": 50},
    {"type": "trend_sma", "period": 100},
    {"type": "trend_sma", "period": 200},
    {"type": "adx_min", "period": 14, "threshold": 20},
    {"type": "adx_min", "period": 14, "threshold": 25},
]

# Stop-loss options (ATR multiplier, None = no stop)
SL_OPTIONS = [None, 1.5, 2.0, 2.5, 3.0]
TP_OPTIONS = [None, 2.0, 3.0, 4.0]

# RSI thresholds
RSI_OVERSOLD = [20, 25, 30, 35]
RSI_OVERBOUGHT = [65, 70, 75, 80]

# CCI thresholds
CCI_OVERSOLD = [-150, -100, -75]
CCI_OVERBOUGHT = [75, 100, 150]

# Stoch thresholds
STOCH_OVERSOLD = [15, 20, 25, 30]
STOCH_OVERBOUGHT = [70, 75, 80, 85]


# ════════════════════════════════════════════════════════════════
# STRATEGY GENERATOR
# ════════════════════════════════════════════════════════════════

class StrategyGenerator:
    def __init__(self, rng=None):
        self.rng = rng or np.random.default_rng()
        self.seen = set()

    def _recipe_hash(self, recipe):
        s = json.dumps(recipe, sort_keys=True, default=str)
        return hashlib.md5(s.encode()).hexdigest()[:12]

    def _pick_params(self, indicator_name):
        reg = INDICATOR_REGISTRY[indicator_name]
        params = {}
        for k, vals in reg["params"].items():
            params[k] = self.rng.choice(vals)
        return params

    def generate(self, n):
        recipes = []
        attempts = 0
        max_attempts = n * 10

        while len(recipes) < n and attempts < max_attempts:
            attempts += 1
            family_name = self.rng.choice(list(STRATEGY_FAMILIES.keys()))
            family = STRATEGY_FAMILIES[family_name]

            try:
                recipe = self._build_recipe(family_name, family)
            except Exception:
                continue

            h = self._recipe_hash(recipe)
            if h in self.seen:
                continue
            self.seen.add(h)

            recipe["id"] = f"{family_name}_{h}"
            recipe["family"] = family_name
            recipes.append(recipe)

        return recipes

    def _build_recipe(self, family_name, family):
        recipe = {"family": family_name, "desc": family["desc"]}

        if family_name == "ma_crossover":
            ma_type = self.rng.choice(["EMA", "SMA"])
            periods = sorted(self.rng.choice(
                INDICATOR_REGISTRY[ma_type]["params"]["timeperiod"], size=2, replace=False
            ))
            recipe["indicators"] = [
                {"name": ma_type, "col": "fast_ma", "params": {"timeperiod": int(periods[0])}},
                {"name": ma_type, "col": "slow_ma", "params": {"timeperiod": int(periods[1])}},
            ]
            recipe["entry"] = {"type": "crossover_above", "fast": "fast_ma", "slow": "slow_ma"}
            recipe["exit"] = {"type": "crossover_below", "fast": "fast_ma", "slow": "slow_ma"}

        elif family_name == "triple_ma":
            all_periods = sorted(self.rng.choice(
                INDICATOR_REGISTRY["EMA"]["params"]["timeperiod"], size=3, replace=False
            ))
            recipe["indicators"] = [
                {"name": "EMA", "col": f"ema_{i}", "params": {"timeperiod": int(p)}}
                for i, p in enumerate(all_periods)
            ]
            recipe["entry"] = {"type": "triple_cross_up", "cols": ["ema_0", "ema_1", "ema_2"]}
            recipe["exit"] = {"type": "triple_cross_down", "cols": ["ema_0", "ema_1", "ema_2"]}

        elif family_name == "macd_crossover":
            p = self._pick_params("MACD")
            if p["fastperiod"] >= p["slowperiod"]:
                p["slowperiod"] = p["fastperiod"] + 8
            recipe["indicators"] = [{"name": "MACD", "col": "macd", "params": {
                "fastperiod": int(p["fastperiod"]),
                "slowperiod": int(p["slowperiod"]),
                "signalperiod": int(p["signalperiod"]),
            }}]
            recipe["entry"] = {"type": "macd_cross_up"}
            recipe["exit"] = {"type": "macd_cross_down"}

        elif family_name == "rsi_mean_revert":
            p = self._pick_params("RSI")
            oversold = int(self.rng.choice(RSI_OVERSOLD))
            overbought = int(self.rng.choice(RSI_OVERBOUGHT))
            if oversold >= overbought:
                overbought = oversold + 30
            recipe["indicators"] = [{"name": "RSI", "col": "rsi", "params": {
                "timeperiod": int(p["timeperiod"])
            }}]
            recipe["entry"] = {"type": "threshold_cross_up", "col": "rsi", "threshold": oversold}
            recipe["exit"] = {"type": "threshold_cross_up", "col": "rsi", "threshold": overbought}

        elif family_name == "bollinger_mean_revert":
            p = self._pick_params("BBANDS")
            recipe["indicators"] = [{"name": "BBANDS", "col": "bbands", "params": {
                "timeperiod": int(p["timeperiod"]),
                "nbdevup": float(p["nbdevup"]),
                "nbdevdn": float(p["nbdevdn"]),
            }}]
            recipe["entry"] = {"type": "bb_lower_bounce"}
            recipe["exit"] = {"type": "bb_upper_touch"}

        elif family_name == "donchian_breakout":
            entry_p = int(self.rng.choice(INDICATOR_REGISTRY["DC_UPPER"]["params"]["timeperiod"]))
            exit_p = int(self.rng.choice(INDICATOR_REGISTRY["DC_LOWER"]["params"]["timeperiod"]))
            recipe["indicators"] = [
                {"name": "DC_UPPER", "col": "dc_upper", "params": {"timeperiod": entry_p}},
                {"name": "DC_LOWER", "col": "dc_lower", "params": {"timeperiod": exit_p}},
            ]
            recipe["entry"] = {"type": "breakout_above", "col": "dc_upper"}
            recipe["exit"] = {"type": "breakout_below", "col": "dc_lower"}

        elif family_name == "cci_threshold":
            p = self._pick_params("CCI")
            oversold = int(self.rng.choice(CCI_OVERSOLD))
            overbought = int(self.rng.choice(CCI_OVERBOUGHT))
            recipe["indicators"] = [{"name": "CCI", "col": "cci", "params": {
                "timeperiod": int(p["timeperiod"])
            }}]
            recipe["entry"] = {"type": "threshold_cross_up", "col": "cci", "threshold": oversold}
            recipe["exit"] = {"type": "threshold_cross_up", "col": "cci", "threshold": overbought}

        elif family_name == "stoch_mean_revert":
            p = self._pick_params("STOCH")
            oversold = int(self.rng.choice(STOCH_OVERSOLD))
            overbought = int(self.rng.choice(STOCH_OVERBOUGHT))
            recipe["indicators"] = [{"name": "STOCH", "col": "stoch", "params": {
                "fastk_period": int(p["fastk_period"]),
                "slowk_period": int(p["slowk_period"]),
                "slowd_period": int(p["slowd_period"]),
            }}]
            recipe["entry"] = {"type": "threshold_cross_up", "col": "stoch_k", "threshold": oversold}
            recipe["exit"] = {"type": "threshold_cross_up", "col": "stoch_k", "threshold": overbought}

        elif family_name == "momentum_breakout":
            mom_p = self._pick_params("MOM")
            sma_p = self._pick_params("SMA")
            recipe["indicators"] = [
                {"name": "MOM", "col": "mom", "params": {"timeperiod": int(mom_p["timeperiod"])}},
                {"name": "SMA", "col": "trend_sma", "params": {"timeperiod": int(sma_p["timeperiod"])}},
            ]
            recipe["entry"] = {"type": "mom_positive_trend", "mom_col": "mom", "trend_col": "trend_sma"}
            recipe["exit"] = {"type": "mom_negative"}

        # Add optional filter
        filt = self.rng.choice(OPTIONAL_FILTERS)
        recipe["filter"] = filt

        # Add optional stop-loss / take-profit
        recipe["sl_atr_mult"] = self.rng.choice(SL_OPTIONS)
        recipe["tp_atr_mult"] = self.rng.choice(TP_OPTIONS)

        return recipe


# ════════════════════════════════════════════════════════════════
# SIGNAL ENGINE — computes entries/exits from a recipe
# ════════════════════════════════════════════════════════════════

def compute_indicator(name, params, close, high=None, low=None):
    reg = INDICATOR_REGISTRY[name]
    inp = reg["input"]

    if inp == "close":
        return reg["fn"](close, **params)
    elif inp == "high":
        return reg["fn"](high, **params)
    elif inp == "low":
        return reg["fn"](low, **params)
    elif inp == "hlc":
        if name == "STOCH":
            return reg["fn"](high, low, close, **params)
        elif name in ("CCI", "ADX", "ATR", "WILLR"):
            return reg["fn"](high, low, close, **params)
    return None


def compute_signals(recipe, df):
    """
    Compute entry/exit signals from a recipe dict and OHLCV DataFrame.
    Returns (entries, exits) as boolean pd.Series with 1-bar execution delay.
    """
    close = df["Close"].values.astype(float)
    high = df["High"].values.astype(float)
    low = df["Low"].values.astype(float)
    idx = df.index
    n = len(close)

    # Compute all indicators
    computed = {}
    for ind in recipe.get("indicators", []):
        name = ind["name"]
        col = ind["col"]
        p = ind["params"]

        result = compute_indicator(name, p, close, high, low)

        if name == "MACD":
            macd_line, signal_line, hist = result
            computed["macd_line"] = pd.Series(macd_line, index=idx)
            computed["macd_signal"] = pd.Series(signal_line, index=idx)
        elif name == "BBANDS":
            upper, middle, lower = result
            computed["bb_upper"] = pd.Series(upper, index=idx)
            computed["bb_middle"] = pd.Series(middle, index=idx)
            computed["bb_lower"] = pd.Series(lower, index=idx)
        elif name == "STOCH":
            slowk, slowd = result
            computed["stoch_k"] = pd.Series(slowk, index=idx)
            computed["stoch_d"] = pd.Series(slowd, index=idx)
        else:
            computed[col] = pd.Series(result, index=idx)

    close_s = pd.Series(close, index=idx)

    # Entry logic
    entry_rule = recipe["entry"]
    etype = entry_rule["type"]

    if etype == "crossover_above":
        fast = computed[entry_rule["fast"]]
        slow = computed[entry_rule["slow"]]
        e_raw = (fast.shift(1) <= slow.shift(1)) & (fast > slow)
    elif etype == "crossover_below":
        fast = computed[entry_rule["fast"]]
        slow = computed[entry_rule["slow"]]
        e_raw = (fast.shift(1) >= slow.shift(1)) & (fast < slow)
    elif etype == "triple_cross_up":
        cols = [computed[c] for c in entry_rule["cols"]]
        e_raw = (
            ((cols[0].shift(1) <= cols[1].shift(1)) & (cols[0] > cols[1]))
            | ((cols[0].shift(1) <= cols[2].shift(1)) & (cols[0] > cols[2]))
            | ((cols[1].shift(1) <= cols[2].shift(1)) & (cols[1] > cols[2]))
        )
    elif etype == "macd_cross_up":
        ml = computed["macd_line"]
        sl = computed["macd_signal"]
        e_raw = (ml.shift(1) <= sl.shift(1)) & (ml > sl)
    elif etype == "threshold_cross_up":
        col = computed[entry_rule["col"]]
        thr = entry_rule["threshold"]
        e_raw = (col.shift(1) <= thr) & (col > thr)
    elif etype == "bb_lower_bounce":
        e_raw = (close_s.shift(1) <= computed["bb_lower"].shift(1)) & (close_s > computed["bb_lower"])
    elif etype == "breakout_above":
        channel = computed[entry_rule["col"]].shift(1)
        e_raw = close_s > channel
    elif etype == "mom_positive_trend":
        mom = computed[entry_rule["mom_col"]]
        trend = computed[entry_rule["trend_col"]]
        e_raw = (mom.shift(1) <= 0) & (mom > 0) & (close_s > trend)
    else:
        raise ValueError(f"Unknown entry type: {etype}")

    # Exit logic
    exit_rule = recipe["exit"]
    xtype = exit_rule["type"]

    if xtype == "crossover_below":
        fast = computed[exit_rule["fast"]]
        slow = computed[exit_rule["slow"]]
        x_raw = (fast.shift(1) >= slow.shift(1)) & (fast < slow)
    elif xtype == "crossover_above":
        fast = computed[exit_rule["fast"]]
        slow = computed[exit_rule["slow"]]
        x_raw = (fast.shift(1) <= slow.shift(1)) & (fast > slow)
    elif xtype == "triple_cross_down":
        cols = [computed[c] for c in exit_rule["cols"]]
        x_raw = (
            ((cols[0].shift(1) >= cols[1].shift(1)) & (cols[0] < cols[1]))
            | ((cols[0].shift(1) >= cols[2].shift(1)) & (cols[0] < cols[2]))
            | ((cols[1].shift(1) >= cols[2].shift(1)) & (cols[1] < cols[2]))
        )
    elif xtype == "macd_cross_down":
        ml = computed["macd_line"]
        sl = computed["macd_signal"]
        x_raw = (ml.shift(1) >= sl.shift(1)) & (ml < sl)
    elif xtype == "threshold_cross_up":
        col = computed[exit_rule["col"]]
        thr = exit_rule["threshold"]
        x_raw = (col.shift(1) <= thr) & (col > thr)
    elif xtype == "bb_upper_touch":
        x_raw = (close_s.shift(1) <= computed["bb_upper"].shift(1)) & (close_s > computed["bb_upper"])
    elif xtype == "breakout_below":
        channel = computed[exit_rule["col"]].shift(1)
        x_raw = close_s < channel
    elif xtype == "mom_negative":
        mom = computed.get("mom", pd.Series(0, index=idx))
        x_raw = (mom.shift(1) >= 0) & (mom < 0)
    else:
        raise ValueError(f"Unknown exit type: {xtype}")

    # Apply optional filter
    filt = recipe.get("filter")
    if filt:
        if filt["type"] == "trend_sma":
            trend = pd.Series(talib.SMA(close, timeperiod=filt["period"]), index=idx)
            e_raw = e_raw & (close_s > trend)
        elif filt["type"] == "adx_min":
            adx = pd.Series(talib.ADX(high, low, close, timeperiod=filt["period"]), index=idx)
            e_raw = e_raw & (adx > filt["threshold"])

    # 1-bar execution delay (anti-lookahead)
    entries = e_raw.shift(1).fillna(False).astype(bool)
    exits = x_raw.shift(1).fillna(False).astype(bool)

    return entries, exits


# ════════════════════════════════════════════════════════════════
# BACKTEST RUNNER
# ════════════════════════════════════════════════════════════════

FEES = 0.0005
SLIPPAGE = 0.0005
FREQ = "D"


def safe(fn, default=np.nan):
    try:
        v = float(fn())
        return v if not np.isinf(v) else default
    except Exception:
        return default


def run_backtest(close, entries, exits, recipe, init_cash=100_000, train_ratio=0.60,
                 high=None, low=None):
    """Run IS/OOS backtest, return metrics dict."""
    split_idx = int(len(close) * train_ratio)

    # Compute ATR-based stops as fraction of price
    sl_stop = None
    tp_stop = None

    if (recipe.get("sl_atr_mult") or recipe.get("tp_atr_mult")) and high is not None and low is not None:
        atr = pd.Series(
            talib.ATR(high.values.astype(float), low.values.astype(float),
                      close.values.astype(float), timeperiod=14),
            index=close.index
        )
        if recipe.get("sl_atr_mult"):
            sl_stop = (atr * recipe["sl_atr_mult"] / close).fillna(0.02)
        if recipe.get("tp_atr_mult"):
            tp_stop = (atr * recipe["tp_atr_mult"] / close).fillna(0.04)

    # Common kwargs
    def _pf_kwargs(slc):
        kw = dict(init_cash=init_cash, fees=FEES, slippage=SLIPPAGE, freq=FREQ)
        if sl_stop is not None:
            kw["sl_stop"] = sl_stop.iloc[slc]
        if tp_stop is not None:
            kw["tp_stop"] = tp_stop.iloc[slc]
        return kw

    is_slc = slice(0, split_idx)
    oos_slc = slice(split_idx, None)

    # IS
    pf_is = vbt.Portfolio.from_signals(
        close=close.iloc[is_slc],
        entries=entries.iloc[is_slc],
        exits=exits.iloc[is_slc],
        **_pf_kwargs(is_slc),
    )

    # OOS
    pf_oos = vbt.Portfolio.from_signals(
        close=close.iloc[oos_slc],
        entries=entries.iloc[oos_slc],
        exits=exits.iloc[oos_slc],
        **_pf_kwargs(oos_slc),
    )

    def extract_metrics(pf, prefix):
        trades_obj = pf.trades
        n_trades = trades_obj.count()
        tr = np.asarray(
            trades_obj.returns.values if hasattr(trades_obj.returns, "values")
            else trades_obj.returns
        ).ravel()
        pos = tr[tr > 0]
        neg = tr[tr < 0]

        return {
            f"{prefix}_sharpe": safe(lambda: pf.sharpe_ratio(freq=FREQ)),
            f"{prefix}_sortino": safe(lambda: pf.sortino_ratio(freq=FREQ)),
            f"{prefix}_return": safe(pf.total_return),
            f"{prefix}_max_dd": safe(pf.max_drawdown),
            f"{prefix}_trades": int(n_trades),
            f"{prefix}_win_rate": float(len(pos) / len(tr) * 100) if len(tr) > 0 else np.nan,
            f"{prefix}_profit_factor": float(pos.sum() / abs(neg.sum())) if len(neg) > 0 and abs(neg.sum()) > 0 else np.nan,
            f"{prefix}_expectancy": float(tr.mean()) if len(tr) > 0 else np.nan,
        }

    is_m = extract_metrics(pf_is, "is")
    oos_m = extract_metrics(pf_oos, "oos")

    result = {**is_m, **oos_m}
    result["_pf_is"] = pf_is
    result["_pf_oos"] = pf_oos
    result["_split_idx"] = split_idx
    return result


# ════════════════════════════════════════════════════════════════
# WINNER DETECTION
# ════════════════════════════════════════════════════════════════

def is_winner(metrics, min_sharpe=1.0, max_dd=0.15, min_trades=30, min_pf=1.2):
    oos_sr = metrics.get("oos_sharpe", np.nan)
    is_sr = metrics.get("is_sharpe", np.nan)
    oos_dd = metrics.get("oos_max_dd", np.nan)
    oos_trades = metrics.get("oos_trades", 0)
    oos_pf = metrics.get("oos_profit_factor", np.nan)

    if np.isnan(oos_sr) or np.isnan(is_sr):
        return False

    # Core criteria (all OOS-based)
    if oos_sr < min_sharpe:
        return False
    if abs(oos_dd) > max_dd:
        return False
    if oos_trades < min_trades:
        return False
    if np.isnan(oos_pf) or oos_pf < min_pf:
        return False

    # IS must also be decent
    if is_sr < 0.5:
        return False

    # Overfit check: OOS shouldn't drop more than 60% from IS
    if is_sr > 0.01:
        degradation = (is_sr - oos_sr) / abs(is_sr)
        if degradation > 0.60:
            return False

    return True


# ════════════════════════════════════════════════════════════════
# DISPLAY HELPERS
# ════════════════════════════════════════════════════════════════

def _c(text, code):
    return f"\033[{code}m{text}\033[0m"

def green(t):  return _c(t, "32")
def red(t):    return _c(t, "31")
def yellow(t): return _c(t, "33")
def cyan(t):   return _c(t, "36")
def bold(t):   return _c(t, "1")
def dim(t):    return _c(t, "2")


def describe_recipe(recipe):
    """Human-readable description of a strategy recipe."""
    parts = []

    # Indicators
    for ind in recipe.get("indicators", []):
        name = ind["name"]
        p = ind["params"]
        p_str = ",".join(f"{v}" for v in p.values())
        parts.append(f"{name}({p_str})")

    # Entry
    entry = recipe["entry"]
    etype = entry["type"]
    if "threshold" in entry:
        parts.append(f"entry:{etype}@{entry['threshold']}")
    else:
        parts.append(f"entry:{etype}")

    # Filter
    filt = recipe.get("filter")
    if filt:
        parts.append(f"filter:{filt['type']}({filt.get('period', '')})")

    # Stops
    sl = recipe.get("sl_atr_mult")
    tp = recipe.get("tp_atr_mult")
    if sl:
        parts.append(f"SL:{sl}xATR")
    if tp:
        parts.append(f"TP:{tp}xATR")

    return " | ".join(parts)


def print_winner(num, recipe, metrics, ticker):
    desc = describe_recipe(recipe)
    print(f"\n  {green(f'WINNER #{num}')} on {bold(ticker)}")
    print(f"    {dim(recipe['id'])}")
    print(f"    {desc}")
    print(f"    IS  Sharpe={metrics['is_sharpe']:.3f}  "
          f"Return={metrics['is_return']:+.1%}  "
          f"MaxDD={metrics['is_max_dd']:.1%}  "
          f"Trades={metrics['is_trades']}  "
          f"PF={metrics['is_profit_factor']:.2f}")
    print(f"    OOS Sharpe={metrics['oos_sharpe']:.3f}  "
          f"Return={metrics['oos_return']:+.1%}  "
          f"MaxDD={metrics['oos_max_dd']:.1%}  "
          f"Trades={metrics['oos_trades']}  "
          f"PF={metrics['oos_profit_factor']:.2f}")


def generate_tearsheet(recipe, metrics, ticker, close, pdf_path):
    """Generate a 2-page PDF tearsheet for a winning strategy."""
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    pf_is = metrics["_pf_is"]
    pf_oos = metrics["_pf_oos"]
    split_idx = metrics["_split_idx"]
    desc = describe_recipe(recipe)

    with PdfPages(pdf_path) as pdf:
        # ── PAGE 1: Equity curves + metrics summary ──
        fig = plt.figure(figsize=(11, 8.5))
        fig.suptitle(f"Strategy Tearsheet — {recipe['id']}", fontsize=14, fontweight="bold", y=0.98)

        # Header info
        fig.text(0.05, 0.93, f"Ticker: {ticker}  |  Family: {recipe['family']}  |  {desc}",
                 fontsize=9, fontstyle="italic")

        # Equity curve (full width, top)
        ax1 = fig.add_axes([0.07, 0.58, 0.88, 0.30])
        eq_is = pf_is.value()
        eq_oos = pf_oos.value()
        ax1.plot(eq_is.index, eq_is.values, color="#3498db", linewidth=1.5, label="In-Sample")
        ax1.plot(eq_oos.index, eq_oos.values, color="#e67e22", linewidth=1.5, label="Out-of-Sample")
        ax1.axhline(100_000, color="gray", linestyle=":", alpha=0.5)
        ax1.set_ylabel("Portfolio Value ($)", fontsize=9)
        ax1.set_title("Equity Curve — IS vs OOS", fontsize=11, fontweight="bold")
        ax1.legend(fontsize=8)
        ax1.grid(alpha=0.3)
        ax1.tick_params(labelsize=8)

        # Drawdown (full width, middle)
        ax2 = fig.add_axes([0.07, 0.35, 0.88, 0.18])
        dd_is = pf_is.drawdown() * 100
        dd_oos = pf_oos.drawdown() * 100
        ax2.fill_between(dd_is.index, dd_is.values, 0, color="#3498db", alpha=0.4, label="IS")
        ax2.fill_between(dd_oos.index, dd_oos.values, 0, color="#e67e22", alpha=0.4, label="OOS")
        ax2.set_ylabel("Drawdown %", fontsize=9)
        ax2.set_title("Drawdown", fontsize=10, fontweight="bold")
        ax2.legend(fontsize=7)
        ax2.grid(alpha=0.3)
        ax2.tick_params(labelsize=8)

        # Metrics table (bottom)
        ax3 = fig.add_axes([0.07, 0.03, 0.88, 0.26])
        ax3.axis("off")

        col_labels = ["Metric", "In-Sample", "Out-of-Sample"]
        table_data = [
            ["Sharpe Ratio", f"{metrics['is_sharpe']:.3f}", f"{metrics['oos_sharpe']:.3f}"],
            ["Sortino Ratio", f"{metrics['is_sortino']:.3f}", f"{metrics['oos_sortino']:.3f}"],
            ["Total Return", f"{metrics['is_return']:+.2%}", f"{metrics['oos_return']:+.2%}"],
            ["Max Drawdown", f"{metrics['is_max_dd']:.2%}", f"{metrics['oos_max_dd']:.2%}"],
            ["Total Trades", f"{metrics['is_trades']}", f"{metrics['oos_trades']}"],
            ["Win Rate", f"{metrics['is_win_rate']:.1f}%", f"{metrics['oos_win_rate']:.1f}%"],
            ["Profit Factor", f"{metrics['is_profit_factor']:.2f}", f"{metrics['oos_profit_factor']:.2f}"],
            ["Expectancy", f"{metrics['is_expectancy']:.4f}", f"{metrics['oos_expectancy']:.4f}"],
        ]

        table = ax3.table(cellText=table_data, colLabels=col_labels, loc="center",
                          cellLoc="center", colWidths=[0.3, 0.25, 0.25])
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1.0, 1.4)

        # Style header
        for j in range(3):
            table[0, j].set_facecolor("#2c3e50")
            table[0, j].set_text_props(color="white", fontweight="bold")

        # Color OOS cells green/red based on performance
        for i in range(1, len(table_data) + 1):
            table[i, 0].set_facecolor("#f0f0f0")

        pdf.savefig(fig, dpi=150)
        plt.close(fig)

        # ── PAGE 2: Trade analysis ──
        fig2 = plt.figure(figsize=(11, 8.5))
        fig2.suptitle(f"Trade Analysis — {ticker} {recipe['family']}", fontsize=14, fontweight="bold", y=0.98)

        # OOS trade returns histogram
        ax4 = fig2.add_axes([0.07, 0.55, 0.40, 0.35])
        try:
            tr_oos = np.asarray(
                pf_oos.trades.returns.values if hasattr(pf_oos.trades.returns, "values")
                else pf_oos.trades.returns
            ).ravel()
            if len(tr_oos) > 0:
                colors = ["#2ecc71" if r > 0 else "#e74c3c" for r in tr_oos]
                ax4.bar(range(len(tr_oos)), tr_oos * 100, color=colors, alpha=0.7, width=1.0)
                ax4.axhline(0, color="black", linewidth=0.5)
                ax4.set_xlabel("Trade #", fontsize=9)
                ax4.set_ylabel("Return %", fontsize=9)
                ax4.set_title("OOS Trade Returns", fontsize=10, fontweight="bold")
                ax4.grid(alpha=0.3, axis="y")
                ax4.tick_params(labelsize=8)
        except Exception:
            ax4.text(0.5, 0.5, "No trade data", ha="center", va="center")
            ax4.set_title("OOS Trade Returns", fontsize=10)

        # OOS return distribution
        ax5 = fig2.add_axes([0.55, 0.55, 0.40, 0.35])
        try:
            if len(tr_oos) > 2:
                ax5.hist(tr_oos * 100, bins=min(30, len(tr_oos)), color="steelblue",
                         edgecolor="white", alpha=0.8)
                ax5.axvline(np.mean(tr_oos) * 100, color="red", linestyle="--",
                            label=f"Mean: {np.mean(tr_oos)*100:.2f}%")
                ax5.axvline(0, color="black", linewidth=0.5)
                ax5.set_xlabel("Return %", fontsize=9)
                ax5.set_ylabel("Frequency", fontsize=9)
                ax5.set_title("OOS Return Distribution", fontsize=10, fontweight="bold")
                ax5.legend(fontsize=8)
                ax5.grid(alpha=0.3)
                ax5.tick_params(labelsize=8)
        except Exception:
            ax5.text(0.5, 0.5, "No trade data", ha="center", va="center")
            ax5.set_title("OOS Return Distribution", fontsize=10)

        # Cumulative OOS returns
        ax6 = fig2.add_axes([0.07, 0.10, 0.40, 0.35])
        try:
            if len(tr_oos) > 0:
                cum_ret = np.cumprod(1 + tr_oos) - 1
                ax6.plot(range(len(cum_ret)), cum_ret * 100, color="#2c3e50", linewidth=1.5)
                ax6.fill_between(range(len(cum_ret)), cum_ret * 100, 0,
                                 where=cum_ret >= 0, color="#2ecc71", alpha=0.3)
                ax6.fill_between(range(len(cum_ret)), cum_ret * 100, 0,
                                 where=cum_ret < 0, color="#e74c3c", alpha=0.3)
                ax6.axhline(0, color="black", linewidth=0.5)
                ax6.set_xlabel("Trade #", fontsize=9)
                ax6.set_ylabel("Cumulative Return %", fontsize=9)
                ax6.set_title("OOS Cumulative Trade Returns", fontsize=10, fontweight="bold")
                ax6.grid(alpha=0.3)
                ax6.tick_params(labelsize=8)
        except Exception:
            ax6.text(0.5, 0.5, "No trade data", ha="center", va="center")
            ax6.set_title("OOS Cumulative Returns", fontsize=10)

        # Strategy recipe text box
        ax7 = fig2.add_axes([0.55, 0.10, 0.40, 0.35])
        ax7.axis("off")
        recipe_text = (
            f"Strategy: {recipe['family']}\n"
            f"ID: {recipe['id']}\n\n"
            f"Indicators:\n"
        )
        for ind in recipe.get("indicators", []):
            p_str = ", ".join(f"{k}={v}" for k, v in ind["params"].items())
            recipe_text += f"  {ind['name']}({p_str})\n"

        recipe_text += f"\nEntry: {recipe['entry']['type']}"
        if "threshold" in recipe["entry"]:
            recipe_text += f" @ {recipe['entry']['threshold']}"
        recipe_text += f"\nExit: {recipe['exit']['type']}"
        if "threshold" in recipe["exit"]:
            recipe_text += f" @ {recipe['exit']['threshold']}"

        filt = recipe.get("filter")
        if filt:
            recipe_text += f"\nFilter: {filt['type']}({filt.get('period', '')})"
        if recipe.get("sl_atr_mult"):
            recipe_text += f"\nStop Loss: {recipe['sl_atr_mult']}x ATR"
        if recipe.get("tp_atr_mult"):
            recipe_text += f"\nTake Profit: {recipe['tp_atr_mult']}x ATR"

        recipe_text += f"\n\nData: {ticker} ({close.index[0].date()} to {close.index[-1].date()})"
        recipe_text += f"\nBars: {len(close)} | Split: 60/40"
        recipe_text += f"\nFees: 0.05% | Slippage: 0.05%"

        ax7.text(0.05, 0.95, recipe_text, transform=ax7.transAxes,
                 fontsize=9, verticalalignment="top", fontfamily="monospace",
                 bbox=dict(boxstyle="round,pad=0.5", facecolor="#f8f9fa", edgecolor="#dee2e6"))

        pdf.savefig(fig2, dpi=150)
        plt.close(fig2)


def print_progress(batch_num, total_tested, n_winners, elapsed_s):
    rate = total_tested / max(elapsed_s, 0.01)
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] "
          f"Batch {batch_num} | "
          f"Tested: {total_tested:,} | "
          f"Winners: {green(str(n_winners))} | "
          f"Rate: {rate:.0f}/sec | "
          f"Hit rate: {n_winners/max(total_tested,1)*100:.2f}%",
          flush=True)


# ════════════════════════════════════════════════════════════════
# MAIN DISCOVERY LOOP
# ════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Autonomous Strategy Discovery Engine")
    parser.add_argument("--tickers", type=str, default="QQQ,SPY,BTC-USD,GC=F,EURUSD=X")
    parser.add_argument("--start", type=str, default="2018-01-01")
    parser.add_argument("--target-winners", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--min-sharpe", type=float, default=1.0)
    parser.add_argument("--max-dd", type=float, default=0.15)
    parser.add_argument("--min-trades", type=int, default=30)
    parser.add_argument("--min-pf", type=float, default=1.2)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",")]
    rng = np.random.default_rng(args.seed)
    generator = StrategyGenerator(rng=rng)

    # Output paths
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_dir = os.path.join(_repo, "exports", "discovery")
    os.makedirs(export_dir, exist_ok=True)
    results_path = os.path.join(export_dir, f"results_{ts}.csv")
    winners_path = os.path.join(export_dir, f"winners_{ts}.csv")
    recipes_dir = os.path.join(export_dir, f"winner_recipes_{ts}")

    # Banner
    print(bold(f"\n{'='*65}"))
    print(bold(f"  STRATEGY DISCOVERY ENGINE"))
    print(bold(f"{'='*65}"))
    print(f"  Tickers:  {', '.join(tickers)}")
    print(f"  Period:   {args.start} to present")
    print(f"  Criteria: Sharpe>{args.min_sharpe} MaxDD<{args.max_dd:.0%} "
          f"Trades>{args.min_trades} PF>{args.min_pf}")
    print(f"  Target:   {args.target_winners} winners")
    print(f"  Output:   {export_dir}")
    print(bold(f"{'='*65}\n"))

    # Download all data upfront
    print("  Downloading data...", flush=True)
    import yfinance as yf

    all_data = {}
    for ticker in tickers:
        try:
            df = yf.download(ticker, start=args.start, progress=False)
            if df is not None and not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = [c[0] for c in df.columns]
                df = df.dropna()
                all_data[ticker] = df
                print(f"    {ticker}: {len(df)} bars "
                      f"({df.index[0].date()} to {df.index[-1].date()})")
        except Exception as e:
            print(f"    {ticker}: FAILED — {e}")

    if not all_data:
        print(red("\n  No data downloaded. Check tickers and internet connection."))
        sys.exit(1)

    print(f"\n  Loaded {len(all_data)} tickers. Starting discovery...\n")
    print(f"  {'-'*65}")

    # Discovery loop
    all_results = []
    winners = []
    winner_signatures = set()
    batch_num = 0
    total_tested = 0
    start_time = time.time()

    target = args.target_winners if args.target_winners > 0 else float("inf")

    try:
        while len(winners) < target:
            batch_num += 1
            batch = generator.generate(args.batch_size)

            for recipe in batch:
                for ticker, df in all_data.items():
                    try:
                        close = df["Close"].astype(float)
                        close.name = "price"
                        high_s = df["High"].astype(float)
                        low_s = df["Low"].astype(float)

                        entries, exits = compute_signals(recipe, df)

                        # Quick skip: not enough signals
                        if entries.sum() < 10:
                            continue

                        metrics = run_backtest(close, entries, exits, recipe,
                                               high=high_s, low=low_s)
                        metrics["recipe_id"] = recipe["id"]
                        metrics["family"] = recipe["family"]
                        metrics["ticker"] = ticker
                        metrics["desc"] = describe_recipe(recipe)

                        # Strip internal objects before storing
                        metrics_clean = {k: v for k, v in metrics.items()
                                         if not k.startswith("_")}
                        all_results.append(metrics_clean)
                        total_tested += 1

                        if is_winner(metrics, args.min_sharpe, args.max_dd,
                                     args.min_trades, args.min_pf):
                            # Deduplicate: skip if same ticker + same OOS metrics
                            dedup_key = (
                                ticker,
                                round(metrics["oos_sharpe"], 3),
                                round(metrics["oos_return"], 4),
                                metrics["oos_trades"],
                            )
                            if dedup_key in winner_signatures:
                                continue
                            winner_signatures.add(dedup_key)

                            winners.append(metrics_clean)
                            print_winner(len(winners), recipe, metrics, ticker)

                            # Save recipe JSON + PDF tearsheet
                            os.makedirs(recipes_dir, exist_ok=True)
                            rpath = os.path.join(recipes_dir, f"{recipe['id']}_{ticker}.json")
                            with open(rpath, "w") as f:
                                json.dump(recipe, f, indent=2, default=str)

                            try:
                                pdf_path = os.path.join(
                                    recipes_dir,
                                    f"tearsheet_{len(winners):02d}_{recipe['id']}_{ticker}.pdf"
                                )
                                generate_tearsheet(recipe, metrics, ticker, close, pdf_path)
                                print(f"    {dim(f'PDF: {os.path.basename(pdf_path)}')}")
                            except Exception as e:
                                print(f"    {dim(f'(PDF skipped: {e})')}")

                            if len(winners) >= target:
                                break

                    except Exception:
                        total_tested += 1
                        continue

                if len(winners) >= target:
                    break

            # Progress update every batch
            elapsed = time.time() - start_time
            print_progress(batch_num, total_tested, len(winners), elapsed)

            # Save checkpoint
            if all_results:
                pd.DataFrame(all_results).to_csv(results_path, index=False)
            if winners:
                pd.DataFrame(winners).to_csv(winners_path, index=False)

    except KeyboardInterrupt:
        print(yellow("\n\n  Stopped by user (Ctrl+C)"))

    # Final summary
    elapsed = time.time() - start_time
    print(bold(f"\n{'='*65}"))
    print(bold(f"  DISCOVERY COMPLETE"))
    print(bold(f"{'='*65}"))
    print(f"  Total tested:  {total_tested:,}")
    print(f"  Winners found: {green(str(len(winners)))}")
    print(f"  Hit rate:      {len(winners)/max(total_tested,1)*100:.2f}%")
    print(f"  Time elapsed:  {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"  Speed:         {total_tested/max(elapsed,0.01):.0f} strategies/sec")

    if winners:
        print(f"\n  Results:  {results_path}")
        print(f"  Winners:  {winners_path}")
        print(f"  Recipes:  {recipes_dir}/")

        # Top winners summary
        wdf = pd.DataFrame(winners).sort_values("oos_sharpe", ascending=False)
        print(f"\n  {'Top Winners by OOS Sharpe':=^65}")
        print(f"  {'Ticker':<8} {'Family':<20} {'OOS SR':>8} {'OOS Ret':>9} "
              f"{'OOS DD':>8} {'OOS PF':>7} {'Trades':>7}")
        print(f"  {'-'*65}")
        for _, w in wdf.head(10).iterrows():
            print(f"  {w['ticker']:<8} {w['family']:<20} "
                  f"{w['oos_sharpe']:>8.3f} {w['oos_return']:>+9.1%} "
                  f"{w['oos_max_dd']:>8.1%} {w['oos_profit_factor']:>7.2f} "
                  f"{int(w['oos_trades']):>7}")

    print(bold(f"\n{'='*65}\n"))


if __name__ == "__main__":
    main()
