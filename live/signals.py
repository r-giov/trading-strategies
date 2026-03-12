"""
Signal engine — MACD Crossover + Donchian Breakout for portfolio components.

In live trading the 1-bar execution delay is inherent:
  - Daily bar closes -> we compute signal -> execute on next bar's open.
  - No need to .shift(1) like in backtesting.
"""

import numpy as np
import pandas as pd
import talib
from datetime import datetime, timezone

from config import PORTFOLIO


def compute_macd_signal(close, fast_period, slow_period, signal_period):
    """Compute MACD crossover signal on latest completed bar."""
    macd, signal, hist = talib.MACD(
        close.values,
        fastperiod=fast_period,
        slowperiod=slow_period,
        signalperiod=signal_period,
    )

    if len(macd) < 2 or np.isnan(macd[-1]) or np.isnan(macd[-2]):
        return {
            "action": "HOLD",
            "crossover": False,
            "reason": "insufficient data",
            "indicators": {},
        }

    prev_macd, curr_macd = macd[-2], macd[-1]
    prev_signal, curr_signal = signal[-2], signal[-1]

    buy_cross = (prev_macd <= prev_signal) and (curr_macd > curr_signal)
    sell_cross = (prev_macd >= prev_signal) and (curr_macd < curr_signal)

    if buy_cross:
        action = "BUY"
    elif sell_cross:
        action = "SELL"
    else:
        action = "HOLD"

    return {
        "action": action,
        "crossover": buy_cross or sell_cross,
        "reason": ("bullish crossover" if buy_cross
                   else "bearish crossover" if sell_cross
                   else "no crossover"),
        "indicators": {
            "macd": round(curr_macd, 6),
            "signal": round(curr_signal, 6),
            "histogram": round(hist[-1], 6),
        },
    }


def compute_donchian_signal(high, low, close, entry_period, exit_period, filter_period):
    """
    Compute Donchian Channel breakout signal on latest completed bar.

    Uses previous bar's channels (replicates .shift(1) from backtest):
      - BUY: close breaks above upper channel AND above trend filter
      - SELL: close breaks below lower channel
    """
    upper = talib.MAX(high.values, entry_period)
    lower = talib.MIN(low.values, exit_period)
    trend = talib.SMA(close.values, filter_period)

    if len(upper) < 2 or np.isnan(upper[-2]) or np.isnan(lower[-2]) or np.isnan(trend[-2]):
        return {
            "action": "HOLD",
            "crossover": False,
            "reason": "insufficient data",
            "indicators": {},
        }

    # Previous bar's channels — replicates .shift(1) from backtest
    prev_upper = upper[-2]
    prev_lower = lower[-2]
    prev_trend = trend[-2]
    curr_close = float(close.iloc[-1])

    buy = curr_close > prev_upper and curr_close > prev_trend
    sell = curr_close < prev_lower

    if buy:
        action = "BUY"
        reason = f"breakout above {prev_upper:.2f} (trend {prev_trend:.2f})"
    elif sell:
        action = "SELL"
        reason = f"breakdown below {prev_lower:.2f}"
    else:
        action = "HOLD"
        reason = f"in channel [{prev_lower:.2f}, {prev_upper:.2f}]"

    return {
        "action": action,
        "crossover": buy or sell,
        "reason": reason,
        "indicators": {
            "upper_channel": round(prev_upper, 6),
            "lower_channel": round(prev_lower, 6),
            "trend_filter": round(prev_trend, 6),
        },
    }


def _compute_component_signal(comp, close, high=None, low=None):
    """Route to the right signal function based on strategy type."""
    if comp["strategy"] == "MACD_Crossover":
        return compute_macd_signal(
            close, comp["fast_period"], comp["slow_period"], comp["signal_period"],
        )
    elif comp["strategy"] == "Donchian_Breakout":
        if high is None or low is None:
            return {"action": "HOLD", "reason": "Donchian needs OHLC data",
                    "crossover": False, "indicators": {}}
        return compute_donchian_signal(
            high, low, close,
            comp["entry_period"], comp["exit_period"], comp["filter_period"],
        )
    return {"action": "HOLD", "reason": f"unknown strategy: {comp['strategy']}",
            "crossover": False, "indicators": {}}


def _bars_needed(comp):
    """Calculate how many historical bars a component needs."""
    if comp["strategy"] == "MACD_Crossover":
        return comp["slow_period"] + comp["signal_period"] + 50
    elif comp["strategy"] == "Donchian_Breakout":
        return max(comp["entry_period"], comp["exit_period"], comp["filter_period"]) + 50
    return 200


# ── Portfolio signal functions ───────────────────────────────────────

def get_portfolio_signals_yfinance():
    """
    Compute signals for all portfolio components using yfinance.
    Groups by ticker to avoid duplicate downloads.

    Returns:
        dict of {component_id: signal_dict}
    """
    import yfinance as yf

    # Group components by yf_ticker
    ticker_groups = {}
    for comp in PORTFOLIO:
        ticker = comp["yf_ticker"]
        if ticker not in ticker_groups:
            ticker_groups[ticker] = {"components": [], "bars_needed": 0}
        ticker_groups[ticker]["components"].append(comp)
        ticker_groups[ticker]["bars_needed"] = max(
            ticker_groups[ticker]["bars_needed"], _bars_needed(comp)
        )

    signals = {}
    for ticker, group in ticker_groups.items():
        n_bars = group["bars_needed"]

        try:
            data = yf.download(
                ticker, period=f"{n_bars + 30}d", interval="1d",
                progress=False, auto_adjust=True,
            )
            if data.empty:
                raise ValueError("empty dataframe")

            close = data["Close"].squeeze()
            high = data["High"].squeeze()
            low = data["Low"].squeeze()
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
                high = high.iloc[:, 0]
                low = low.iloc[:, 0]

        except Exception as e:
            for comp in group["components"]:
                signals[comp["id"]] = {
                    "component_id": comp["id"],
                    "symbol": comp["symbol"],
                    "strategy": comp["strategy"],
                    "weight": comp["weight"],
                    "action": "HOLD",
                    "crossover": False,
                    "reason": f"yfinance error: {e}",
                    "indicators": {},
                }
            continue

        for comp in group["components"]:
            sig = _compute_component_signal(comp, close, high, low)
            sig["component_id"] = comp["id"]
            sig["symbol"] = comp["symbol"]
            sig["strategy"] = comp["strategy"]
            sig["weight"] = comp["weight"]
            sig["last_close"] = round(float(close.iloc[-1]), 2)
            sig["bar_time"] = str(close.index[-1])
            sig["timestamp"] = datetime.now(timezone.utc).isoformat()
            signals[comp["id"]] = sig

    return signals


def get_portfolio_signals_mt5():
    """
    Compute signals for all portfolio components using MT5 data.

    Returns:
        dict of {component_id: signal_dict}
    """
    import MetaTrader5 as mt5

    # Group components by MT5 symbol
    symbol_groups = {}
    for comp in PORTFOLIO:
        sym = comp["symbol"]
        if sym not in symbol_groups:
            symbol_groups[sym] = {"components": [], "bars_needed": 0}
        symbol_groups[sym]["components"].append(comp)
        symbol_groups[sym]["bars_needed"] = max(
            symbol_groups[sym]["bars_needed"], _bars_needed(comp)
        )

    signals = {}
    for symbol, group in symbol_groups.items():
        n_bars = group["bars_needed"]
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, n_bars)

        if rates is None or len(rates) == 0:
            for comp in group["components"]:
                signals[comp["id"]] = {
                    "component_id": comp["id"],
                    "symbol": symbol,
                    "strategy": comp["strategy"],
                    "weight": comp["weight"],
                    "action": "HOLD",
                    "crossover": False,
                    "reason": f"no MT5 data for {symbol}",
                    "indicators": {},
                }
            continue

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)

        for comp in group["components"]:
            sig = _compute_component_signal(comp, close, high, low)
            sig["component_id"] = comp["id"]
            sig["symbol"] = symbol
            sig["strategy"] = comp["strategy"]
            sig["weight"] = comp["weight"]
            sig["last_close"] = round(float(close.iloc[-1]), 2)
            sig["bar_time"] = df["time"].iloc[-1].isoformat()
            sig["timestamp"] = datetime.now(timezone.utc).isoformat()
            signals[comp["id"]] = sig

    return signals


def aggregate_signals(component_signals):
    """
    Aggregate component signals into per-symbol actions.

    Logic per symbol:
      - Sum weights of components with BUY signal -> that's our long weight
      - If any component says SELL and none says BUY -> close position
      - All HOLD -> no action

    Returns:
        dict of {symbol: {"action", "weight", "components": [...]}}
    """
    by_symbol = {}
    for comp_id, sig in component_signals.items():
        sym = sig["symbol"]
        if sym not in by_symbol:
            by_symbol[sym] = []
        by_symbol[sym].append(sig)

    result = {}
    for sym, components in by_symbol.items():
        buy_weight = sum(c["weight"] for c in components if c["action"] == "BUY")
        n_sell = sum(1 for c in components if c["action"] == "SELL")
        last_close = components[0].get("last_close")

        if buy_weight > 0:
            action = "BUY"
            weight = buy_weight
        elif n_sell > 0:
            action = "SELL"
            weight = 0
        else:
            action = "HOLD"
            weight = 0

        n_buy = sum(1 for c in components if c["action"] == "BUY")
        result[sym] = {
            "action": action,
            "weight": weight,
            "last_close": last_close,
            "summary": f"{n_buy}/{len(components)} BUY, {n_sell}/{len(components)} SELL",
            "components": components,
        }

    return result
