"""
Signal engine — MACD, Donchian, Triple EMA, Supertrend for portfolio components.

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


def compute_triple_ema_signal(close, ema1_period, ema2_period, ema3_period):
    """Compute Triple EMA crossover signal on latest completed bar.

    Entry: any shorter EMA crosses above a longer EMA (with medium > long trend filter).
    Exit: any shorter EMA crosses below a longer EMA.
    Matches _run_ensemble_v3.py crossover logic.
    """
    ema1 = talib.EMA(close.values, timeperiod=ema1_period)
    ema2 = talib.EMA(close.values, timeperiod=ema2_period)
    ema3 = talib.EMA(close.values, timeperiod=ema3_period)

    if len(ema1) < 2 or np.isnan(ema1[-1]) or np.isnan(ema2[-1]) or np.isnan(ema3[-1]):
        return {
            "action": "HOLD", "crossover": False,
            "reason": "insufficient data", "indicators": {},
        }

    # Crossover detection (matches ensemble v3: short x medium, with medium > long filter)
    buy1 = (ema1[-2] <= ema2[-2]) and (ema1[-1] > ema2[-1])
    buy2 = (ema1[-2] <= ema3[-2]) and (ema1[-1] > ema3[-1])
    buy3 = (ema2[-2] <= ema3[-2]) and (ema2[-1] > ema3[-1])
    sell1 = (ema1[-2] >= ema2[-2]) and (ema1[-1] < ema2[-1])
    sell2 = (ema1[-2] >= ema3[-2]) and (ema1[-1] < ema3[-1])
    sell3 = (ema2[-2] >= ema3[-2]) and (ema2[-1] < ema3[-1])

    buy_cross = buy1 or buy2 or buy3
    sell_cross = sell1 or sell2 or sell3

    # Trend context: medium EMA above long EMA = trend OK
    trend_ok = ema2[-1] > ema3[-1]

    if buy_cross and trend_ok:
        action, reason = "BUY", "EMA bullish crossover (trend up)"
    elif buy_cross:
        action, reason = "HOLD", "EMA bullish crossover but trend down"
    elif sell_cross:
        action, reason = "SELL", "EMA bearish crossover"
    else:
        action, reason = "HOLD", "no crossover"

    return {
        "action": action,
        "crossover": buy_cross or sell_cross,
        "reason": reason,
        "indicators": {
            "ema_short": round(float(ema1[-1]), 4),
            "ema_med": round(float(ema2[-1]), 4),
            "ema_long": round(float(ema3[-1]), 4),
            "trend_up": bool(trend_ok),
        },
    }


def _compute_supertrend_direction(high_arr, low_arr, close_arr, atr_period, multiplier):
    """Compute full Supertrend direction array: 1=bullish, -1=bearish.

    Matches _strat_supertrend_portfolio.py compute_supertrend() exactly —
    uses adaptive band narrowing (proper Supertrend, not simplified).
    """
    atr = talib.ATR(high_arr, low_arr, close_arr, timeperiod=atr_period)
    hl2 = (high_arr + low_arr) / 2.0
    upper_basic = hl2 + multiplier * atr
    lower_basic = hl2 - multiplier * atr
    n = len(close_arr)
    upper_band = np.full(n, np.nan)
    lower_band = np.full(n, np.nan)
    direction = np.zeros(n)

    # Find first valid ATR index
    first_valid = -1
    for idx in range(n):
        if not np.isnan(atr[idx]):
            first_valid = idx
            break
    if first_valid < 0:
        return direction, upper_band, lower_band, atr

    upper_band[first_valid] = upper_basic[first_valid]
    lower_band[first_valid] = lower_basic[first_valid]
    if close_arr[first_valid] > hl2[first_valid]:
        direction[first_valid] = 1
    else:
        direction[first_valid] = -1

    for i in range(first_valid + 1, n):
        if np.isnan(atr[i]):
            upper_band[i] = upper_band[i - 1]
            lower_band[i] = lower_band[i - 1]
            direction[i] = direction[i - 1]
            continue
        lower_band[i] = (max(lower_basic[i], lower_band[i - 1])
                         if close_arr[i - 1] >= lower_band[i - 1]
                         else lower_basic[i])
        upper_band[i] = (min(upper_basic[i], upper_band[i - 1])
                         if close_arr[i - 1] <= upper_band[i - 1]
                         else upper_basic[i])
        if direction[i - 1] == 1:
            direction[i] = -1 if close_arr[i] < lower_band[i] else 1
        else:
            direction[i] = 1 if close_arr[i] > upper_band[i] else -1

    return direction, upper_band, lower_band, atr


def compute_supertrend_signal(high, low, close, atr_period, multiplier, trend_sma=0):
    """Compute Supertrend flip signal on latest completed bar.

    Uses the full adaptive-band Supertrend algorithm from the strategy notebook.
    Optional SMA trend filter (trend_sma > 0 means only buy when close > SMA).
    """
    high_arr = high.values.astype(float)
    low_arr = low.values.astype(float)
    close_arr = close.values.astype(float)
    n = len(close_arr)

    if n < atr_period + 5:
        return {
            "action": "HOLD", "crossover": False,
            "reason": "insufficient data", "indicators": {},
        }

    direction, upper_band, lower_band, atr = _compute_supertrend_direction(
        high_arr, low_arr, close_arr, atr_period, multiplier,
    )

    if np.isnan(atr[-1]):
        return {
            "action": "HOLD", "crossover": False,
            "reason": "ATR not ready", "indicators": {},
        }

    # Detect direction flip on latest bar
    flip_up = (direction[-1] == 1) and (direction[-2] == -1) if n >= 2 else False
    flip_down = (direction[-1] == -1) and (direction[-2] == 1) if n >= 2 else False

    # Optional SMA trend filter (matches notebook logic)
    trend_ok = True
    sma_val = None
    if trend_sma > 0:
        sma = talib.SMA(close_arr, timeperiod=trend_sma)
        if not np.isnan(sma[-1]):
            sma_val = float(sma[-1])
            trend_ok = close_arr[-1] > sma[-1]
        if flip_up and not trend_ok:
            flip_up = False  # block entry when trend filter fails

    trend_up = direction[-1] == 1

    if flip_up:
        action, reason = "BUY", "supertrend flipped bullish"
    elif flip_down:
        action, reason = "SELL", "supertrend flipped bearish"
    else:
        action = "HOLD"
        reason = f"trend {'up' if trend_up else 'down'}, no flip"

    indicators = {
        "atr": round(float(atr[-1]), 4),
        "direction": int(direction[-1]),
        "trend_up": bool(trend_up),
    }
    if not np.isnan(upper_band[-1]):
        indicators["upper_band"] = round(float(upper_band[-1]), 4)
    if not np.isnan(lower_band[-1]):
        indicators["lower_band"] = round(float(lower_band[-1]), 4)
    if sma_val is not None:
        indicators["trend_sma"] = round(sma_val, 4)

    return {
        "action": action,
        "crossover": flip_up or flip_down,
        "reason": reason,
        "indicators": indicators,
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
    elif comp["strategy"] == "Triple_EMA":
        return compute_triple_ema_signal(
            close, comp["ema1_period"], comp["ema2_period"], comp["ema3_period"],
        )
    elif comp["strategy"] == "Supertrend":
        if high is None or low is None:
            return {"action": "HOLD", "reason": "Supertrend needs OHLC data",
                    "crossover": False, "indicators": {}}
        return compute_supertrend_signal(
            high, low, close,
            comp["atr_period"], comp["multiplier"], comp.get("trend_sma", 0),
        )
    return {"action": "HOLD", "reason": f"unknown strategy: {comp['strategy']}",
            "crossover": False, "indicators": {}}


def _bars_needed(comp):
    """Calculate how many historical bars a component needs."""
    if comp["strategy"] == "MACD_Crossover":
        return comp["slow_period"] + comp["signal_period"] + 50
    elif comp["strategy"] == "Donchian_Breakout":
        return max(comp["entry_period"], comp["exit_period"], comp["filter_period"]) + 50
    elif comp["strategy"] == "Triple_EMA":
        return comp["ema3_period"] + 50   # longest EMA drives warmup
    elif comp["strategy"] == "Supertrend":
        sma = comp.get("trend_sma", 0)
        return max(comp["atr_period"], sma) + 50
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
