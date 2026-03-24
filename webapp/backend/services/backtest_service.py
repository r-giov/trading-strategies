"""
Backtest service — runs single-ticker backtests using vectorbt.
Mirrors signal logic from the strategy notebooks with 1-bar execution delay.
"""

import os
import sys
import time
import itertools
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import deps  # noqa: E402, F401 — triggers sys.path setup

import logging
from typing import Any

import numpy as np
import pandas as pd
import talib
import yfinance as yf

# Lazy import vectorbt — it's heavy (~3s) and blocks server startup
vbt = None

def _get_vbt():
    global vbt
    if vbt is None:
        import vectorbt as _vbt
        vbt = _vbt
    return vbt

logger = logging.getLogger("qs-finance.backtest")

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_INIT_CASH = 100_000
DEFAULT_FEES = 0.0005
DEFAULT_FREQ = "D"
DEFAULT_TRAIN_RATIO = 0.60

# ---------------------------------------------------------------------------
# Data download helpers
# ---------------------------------------------------------------------------

def _download_yfinance(ticker: str, start_date: str) -> pd.DataFrame:
    """Download OHLCV data from yfinance."""
    df = yf.download(ticker, start=start_date, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No data returned for ticker '{ticker}' from {start_date}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def _download_alpaca(ticker: str, start_date: str) -> pd.DataFrame:
    """Download OHLCV data from Alpaca Markets API."""
    try:
        from alpaca_trade_api.rest import REST, TimeFrame
    except ImportError:
        raise ImportError(
            "alpaca-trade-api is not installed. "
            "Install it with: pip install alpaca-trade-api"
        )

    api_key = os.environ.get("ALPACA_API_KEY", "")
    secret_key = os.environ.get("ALPACA_SECRET_KEY", "")
    base_url = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    if not api_key or not secret_key:
        raise ValueError(
            "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in environment variables"
        )

    api = REST(api_key, secret_key, base_url)

    # Alpaca uses different symbol format — strip yfinance suffixes
    alpaca_symbol = ticker.replace("-USD", "USD").replace("=X", "").replace("^", "")

    bars = api.get_bars(
        alpaca_symbol,
        TimeFrame.Day,
        start=start_date,
        adjustment="raw",
    ).df

    if bars.empty:
        raise ValueError(f"No data returned from Alpaca for '{alpaca_symbol}' from {start_date}")

    # Rename columns to match yfinance convention
    bars = bars.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    })

    # Alpaca returns timezone-aware index; strip tz for consistency
    if bars.index.tz is not None:
        bars.index = bars.index.tz_localize(None)

    return bars[["Open", "High", "Low", "Close", "Volume"]]


# ---------------------------------------------------------------------------
# Sanitization helpers
# ---------------------------------------------------------------------------

def _sanitize(obj):
    """Convert numpy / pandas types to native Python for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        if np.isinf(v) or np.isnan(v):
            return 0.0
        return v
    if isinstance(obj, float):
        if np.isinf(obj) or np.isnan(obj):
            return 0.0
        return obj
    if isinstance(obj, np.ndarray):
        return [_sanitize(x) for x in obj.tolist()]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


# ---------------------------------------------------------------------------
# Signal generators — one per strategy
# ---------------------------------------------------------------------------

def _macd_signals(close: pd.Series, params: dict) -> tuple[pd.Series, pd.Series]:
    """MACD Crossover signal logic with 1-bar execution delay."""
    fast = params.get("fast_period", 12)
    slow = params.get("slow_period", 26)
    signal_p = params.get("signal_period", 9)

    macd_s, signal_s, _ = talib.MACD(close, fastperiod=fast, slowperiod=slow, signalperiod=signal_p)

    entries_raw = (macd_s.shift(1) <= signal_s.shift(1)) & (macd_s > signal_s)
    exits_raw = (macd_s.shift(1) >= signal_s.shift(1)) & (macd_s < signal_s)

    entries = entries_raw.shift(1).fillna(False)
    exits = exits_raw.shift(1).fillna(False)
    return entries, exits


def _donchian_signals(close: pd.Series, high: pd.Series, low: pd.Series, params: dict) -> tuple[pd.Series, pd.Series]:
    """Donchian Breakout signal logic with 1-bar execution delay."""
    entry_period = params.get("entry_period", 20)
    exit_period = params.get("exit_period", 10)
    filter_period = params.get("filter_period", 50)

    upper = talib.MAX(high, timeperiod=entry_period).shift(1)
    lower = talib.MIN(low, timeperiod=exit_period).shift(1)
    trend = talib.SMA(close, timeperiod=filter_period).shift(1)

    entries_raw = (close > upper) & (close > trend)
    exits_raw = close < lower

    entries = entries_raw.shift(1).fillna(False)
    exits = exits_raw.shift(1).fillna(False)
    return entries, exits


def _ema_crossover_signals(close: pd.Series, params: dict) -> tuple[pd.Series, pd.Series]:
    """EMA Crossover + Trend Filter signal logic with 1-bar execution delay."""
    fast_p = params.get("fast_ema", 12)
    slow_p = params.get("slow_ema", 26)
    trend_p = params.get("trend_filter", 200)

    fast_ema = talib.EMA(close, timeperiod=fast_p)
    slow_ema = talib.EMA(close, timeperiod=slow_p)
    trend_sma = talib.SMA(close, timeperiod=trend_p)

    entries_raw = (
        (fast_ema.shift(1) <= slow_ema.shift(1))
        & (fast_ema > slow_ema)
        & (close > trend_sma)
    )
    exits_raw = (fast_ema.shift(1) >= slow_ema.shift(1)) & (fast_ema < slow_ema)

    entries = entries_raw.shift(1).fillna(False)
    exits = exits_raw.shift(1).fillna(False)
    return entries, exits


def _supertrend_signals(close: pd.Series, high: pd.Series, low: pd.Series, params: dict) -> tuple[pd.Series, pd.Series]:
    """Supertrend signal logic with 1-bar execution delay."""
    period = params.get("atr_period", 10)
    multiplier = params.get("multiplier", 3.0)

    atr = talib.ATR(high, low, close, timeperiod=period)
    hl2 = (high + low) / 2.0

    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    supertrend = pd.Series(np.nan, index=close.index)
    direction = pd.Series(1, index=close.index)  # 1 = up, -1 = down

    for i in range(1, len(close)):
        # Adjust bands based on prior values
        if lower_band.iloc[i] > 0 and not np.isnan(supertrend.iloc[i - 1]):
            if close.iloc[i - 1] > supertrend.iloc[i - 1] and lower_band.iloc[i] < supertrend.iloc[i - 1]:
                lower_band.iloc[i] = supertrend.iloc[i - 1]
            if close.iloc[i - 1] < supertrend.iloc[i - 1] and upper_band.iloc[i] > supertrend.iloc[i - 1]:
                upper_band.iloc[i] = supertrend.iloc[i - 1]

        if np.isnan(supertrend.iloc[i - 1]):
            supertrend.iloc[i] = lower_band.iloc[i]
            direction.iloc[i] = 1
        elif supertrend.iloc[i - 1] == lower_band.iloc[i - 1]:
            if close.iloc[i] >= lower_band.iloc[i]:
                supertrend.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1
            else:
                supertrend.iloc[i] = upper_band.iloc[i]
                direction.iloc[i] = -1
        else:
            if close.iloc[i] <= upper_band.iloc[i]:
                supertrend.iloc[i] = upper_band.iloc[i]
                direction.iloc[i] = -1
            else:
                supertrend.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1

    # Direction change signals
    entries_raw = (direction.shift(1) == -1) & (direction == 1)
    exits_raw = (direction.shift(1) == 1) & (direction == -1)

    entries = entries_raw.shift(1).fillna(False)
    exits = exits_raw.shift(1).fillna(False)
    return entries, exits


def _rsi_signals(close: pd.Series, params: dict) -> tuple[pd.Series, pd.Series]:
    """RSI Mean Reversion signal logic with 1-bar execution delay."""
    rsi_len = params.get("rsi_len", 14)
    oversold = params.get("oversold", 30)
    overbought = params.get("overbought", 70)
    rsi_s = talib.RSI(close, timeperiod=rsi_len)
    entries_raw = (rsi_s.shift(1) <= oversold) & (rsi_s > oversold)
    exits_raw = (rsi_s.shift(1) <= overbought) & (rsi_s > overbought)
    entries = entries_raw.shift(1).fillna(False)
    exits = exits_raw.shift(1).fillna(False)
    return entries, exits


def _triple_ema_signals(close: pd.Series, params: dict) -> tuple[pd.Series, pd.Series]:
    """Triple EMA Crossover signal logic with 1-bar execution delay."""
    p1 = params.get("ema1_period", 8)
    p2 = params.get("ema2_period", 21)
    p3 = params.get("ema3_period", 55)
    ema1 = talib.EMA(close, p1)
    ema2 = talib.EMA(close, p2)
    ema3 = talib.EMA(close, p3)
    # Crossed above patterns
    e1_above_e2 = (ema1.shift(1) <= ema2.shift(1)) & (ema1 > ema2)
    e1_above_e3 = (ema1.shift(1) <= ema3.shift(1)) & (ema1 > ema3)
    e2_above_e3 = (ema2.shift(1) <= ema3.shift(1)) & (ema2 > ema3)
    entries_raw = e1_above_e2 | e1_above_e3 | e2_above_e3
    # Crossed below patterns
    e1_below_e2 = (ema1.shift(1) >= ema2.shift(1)) & (ema1 < ema2)
    e1_below_e3 = (ema1.shift(1) >= ema3.shift(1)) & (ema1 < ema3)
    e2_below_e3 = (ema2.shift(1) >= ema3.shift(1)) & (ema2 < ema3)
    exits_raw = e1_below_e2 | e1_below_e3 | e2_below_e3
    entries = entries_raw.shift(1).fillna(False)
    exits = exits_raw.shift(1).fillna(False)
    return entries, exits


def _schaff_signals(close: pd.Series, params: dict) -> tuple[pd.Series, pd.Series]:
    """Schaff Trend Cycle signal logic with 1-bar execution delay."""
    fast = params.get("fast_period", 23)
    slow = params.get("slow_period", 50)
    cycle = params.get("cycle_period", 10)
    macd_line, _, _ = talib.MACD(close, fastperiod=fast, slowperiod=slow, signalperiod=1)
    # Stochastic of MACD
    stoch_k = talib.STOCH(
        macd_line, macd_line, macd_line,
        fastk_period=cycle, slowk_period=3, slowd_period=3,
    )[0]
    # Second stochastic
    stc = talib.STOCH(
        stoch_k, stoch_k, stoch_k,
        fastk_period=cycle, slowk_period=3, slowd_period=3,
    )[0]
    entries_raw = (stc.shift(1) <= 25) & (stc > 25)
    exits_raw = (stc.shift(1) >= 75) & (stc < 75)
    entries = entries_raw.shift(1).fillna(False)
    exits = exits_raw.shift(1).fillna(False)
    return entries, exits


# ---------------------------------------------------------------------------
# Metric extraction
# ---------------------------------------------------------------------------

STRATEGY_MAP = {
    "MACD_Crossover": "macd",
    "Donchian_Breakout": "donchian",
    "EMA_Crossover": "ema",
    "Supertrend": "supertrend",
    "RSI_Mean_Reversion": "rsi",
    "Triple_EMA": "triple_ema",
    "Schaff_Trend_Cycle": "schaff",
}


def _extract_metrics(pf) -> dict:
    """Pull standard metrics from a vectorbt Portfolio object."""
    stats = pf.stats()
    total_return = pf.total_return()
    sharpe = pf.sharpe_ratio(freq="D")
    max_dd = pf.max_drawdown()
    trades = pf.trades.records_readable if len(pf.trades) > 0 else None
    n_trades = int(pf.trades.count()) if trades is not None else 0
    win_rate = float(pf.trades.win_rate()) if n_trades > 0 else 0.0
    profit_factor = float(pf.trades.profit_factor()) if n_trades > 0 else 0.0

    return {
        "sharpe": float(sharpe) if not np.isnan(sharpe) else 0.0,
        "total_return": float(total_return),
        "total_return_pct": round(float(total_return) * 100, 2),
        "max_drawdown": float(max_dd),
        "max_drawdown_pct": round(float(max_dd) * 100, 2),
        "win_rate": round(float(win_rate) * 100, 2),
        "profit_factor": round(float(profit_factor), 3),
        "total_trades": n_trades,
    }


def _build_trade_log(pf) -> list[dict]:
    """Extract trade-by-trade log from vectorbt Portfolio."""
    if len(pf.trades) == 0:
        return []

    records = pf.trades.records_readable
    log = []
    for _, row in records.iterrows():
        log.append({
            "entry_date": row.get("Entry Timestamp", row.get("Entry Index", "")),
            "exit_date": row.get("Exit Timestamp", row.get("Exit Index", "")),
            "pnl": row.get("PnL", 0.0),
            "return_pct": row.get("Return", 0.0),
            "direction": row.get("Direction", "Long"),
            "status": row.get("Status", ""),
        })
    return log


# ---------------------------------------------------------------------------
# Main backtest runner
# ---------------------------------------------------------------------------

def _describe_signal_logic(strategy_key: str, params: dict) -> str:
    """Return a human-readable description of the signal logic for audit purposes."""
    if strategy_key == "macd":
        fast = params.get("fast_period", 12)
        slow = params.get("slow_period", 26)
        sig = params.get("signal_period", 9)
        return f"MACD({fast},{slow},{sig}) crossover with 1-bar delay"
    elif strategy_key == "donchian":
        entry = params.get("entry_period", 20)
        exit_ = params.get("exit_period", 10)
        filt = params.get("filter_period", 50)
        return f"Donchian({entry}/{exit_}) breakout + SMA({filt}) trend filter with 1-bar delay"
    elif strategy_key == "ema":
        fast = params.get("fast_ema", 12)
        slow = params.get("slow_ema", 26)
        trend = params.get("trend_filter", 200)
        return f"EMA({fast}/{slow}) crossover + SMA({trend}) trend filter with 1-bar delay"
    elif strategy_key == "supertrend":
        period = params.get("atr_period", 10)
        mult = params.get("multiplier", 3.0)
        return f"Supertrend(ATR={period}, mult={mult}) with 1-bar delay"
    elif strategy_key == "rsi":
        length = params.get("rsi_len", 14)
        os_ = params.get("oversold", 30)
        ob = params.get("overbought", 70)
        return f"RSI({length}) mean reversion (oversold={os_}, overbought={ob}) with 1-bar delay"
    elif strategy_key == "triple_ema":
        p1 = params.get("ema1_period", 8)
        p2 = params.get("ema2_period", 21)
        p3 = params.get("ema3_period", 55)
        return f"Triple EMA({p1},{p2},{p3}) crossover with 1-bar delay"
    elif strategy_key == "schaff":
        fast = params.get("fast_period", 23)
        slow = params.get("slow_period", 50)
        cyc = params.get("cycle_period", 10)
        return f"Schaff Trend Cycle(fast={fast}, slow={slow}, cycle={cyc}) with 1-bar delay"
    return "Unknown"


def run_backtest(
    strategy: str,
    ticker: str,
    start_date: str = "2015-01-01",
    params: dict | None = None,
    init_cash: float = DEFAULT_INIT_CASH,
    fees: float = DEFAULT_FEES,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
    data_source: str = "yfinance",
) -> dict[str, Any]:
    """
    Download data, compute signals, run vectorbt backtest, split IS/OOS.
    Returns equity curve, metrics, trade log, IS/OOS splits, and audit trail.
    """
    params = params or {}
    strategy_key = STRATEGY_MAP.get(strategy)
    if strategy_key is None:
        return {"error": f"Unknown strategy '{strategy}'. Supported: {list(STRATEGY_MAP.keys())}"}

    audit_steps = []

    # ------------------------------------------------------------------
    # 1. Download data
    # ------------------------------------------------------------------
    t0_download = time.time()
    try:
        if data_source == "alpaca":
            df = _download_alpaca(ticker, start_date)
        else:
            df = _download_yfinance(ticker, start_date)
    except ImportError as e:
        return {"error": str(e)}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"{data_source} download failed: {e}"}
    download_ms = round((time.time() - t0_download) * 1000)

    close = df["Close"].squeeze()
    high = df["High"].squeeze()
    low = df["Low"].squeeze()

    bars_count = len(close)
    first_bar = close.index[0].isoformat() if bars_count > 0 else None
    last_bar = close.index[-1].isoformat() if bars_count > 0 else None
    audit_steps.append(f"Downloaded {bars_count:,} daily bars from {data_source}")

    # ------------------------------------------------------------------
    # 2. Compute signals
    # ------------------------------------------------------------------
    t0_signals = time.time()
    try:
        if strategy_key == "macd":
            entries, exits = _macd_signals(close, params)
        elif strategy_key == "donchian":
            entries, exits = _donchian_signals(close, high, low, params)
        elif strategy_key == "ema":
            entries, exits = _ema_crossover_signals(close, params)
        elif strategy_key == "supertrend":
            entries, exits = _supertrend_signals(close, high, low, params)
        elif strategy_key == "rsi":
            entries, exits = _rsi_signals(close, params)
        elif strategy_key == "triple_ema":
            entries, exits = _triple_ema_signals(close, params)
        elif strategy_key == "schaff":
            entries, exits = _schaff_signals(close, params)
        else:
            return {"error": f"Strategy '{strategy}' not implemented"}
    except Exception as e:
        logger.exception("Signal computation failed")
        return {"error": f"Signal computation failed: {e}"}
    signal_ms = round((time.time() - t0_signals) * 1000)

    entries_count = int(entries.sum())
    exits_count = int(exits.sum())
    signals_generated = entries_count + exits_count
    signal_logic = _describe_signal_logic(strategy_key, params)

    audit_steps.append(f"Computed {signal_logic}")
    audit_steps.append(f"Generated {entries_count} entry signals, {exits_count} exit signals")
    audit_steps.append("Applied 1-bar execution delay")

    # ------------------------------------------------------------------
    # 3. Run full-sample backtest
    # ------------------------------------------------------------------
    fees_pct = f"{fees * 100:.2f}%"
    audit_steps.append(
        f"Ran vectorbt Portfolio.from_signals(init_cash={init_cash:,.0f}, fees={fees_pct})"
    )

    try:
        pf = _get_vbt().Portfolio.from_signals(
            close,
            entries=entries,
            exits=exits,
            init_cash=init_cash,
            fees=fees,
            freq=DEFAULT_FREQ,
        )
    except Exception as e:
        logger.exception("vectorbt backtest failed")
        return {"error": f"Backtest execution failed: {e}"}

    # ------------------------------------------------------------------
    # 4. Equity curve
    # ------------------------------------------------------------------
    equity = pf.value()
    equity_dates = [ts.isoformat() for ts in equity.index]
    equity_values = equity.tolist()

    # ------------------------------------------------------------------
    # 5. Full-sample metrics + trade log
    # ------------------------------------------------------------------
    full_metrics = _extract_metrics(pf)
    trade_log = _build_trade_log(pf)

    # ------------------------------------------------------------------
    # 6. IS / OOS split
    # ------------------------------------------------------------------
    split_idx = int(len(close) * train_ratio)
    train_close = close.iloc[:split_idx]
    val_close = close.iloc[split_idx:]
    train_entries = entries.iloc[:split_idx]
    train_exits = exits.iloc[:split_idx]
    val_entries = entries.iloc[split_idx:]
    val_exits = exits.iloc[split_idx:]

    audit_steps.append(
        f"Split at bar {split_idx:,} ({int(train_ratio * 100)}% IS / {int((1 - train_ratio) * 100)}% OOS)"
    )

    is_metrics = {}
    oos_metrics = {}

    try:
        if len(train_close) > 0:
            pf_is = _get_vbt().Portfolio.from_signals(
                train_close,
                entries=train_entries,
                exits=train_exits,
                init_cash=init_cash,
                fees=fees,
                freq=DEFAULT_FREQ,
            )
            is_metrics = _extract_metrics(pf_is)
    except Exception as e:
        logger.warning(f"IS backtest failed: {e}")
        is_metrics = {"error": str(e)}

    try:
        if len(val_close) > 0:
            pf_oos = _get_vbt().Portfolio.from_signals(
                val_close,
                entries=val_entries,
                exits=val_exits,
                init_cash=init_cash,
                fees=fees,
                freq=DEFAULT_FREQ,
            )
            oos_metrics = _extract_metrics(pf_oos)
    except Exception as e:
        logger.warning(f"OOS backtest failed: {e}")
        oos_metrics = {"error": str(e)}

    # ------------------------------------------------------------------
    # 7. Build audit trail
    # ------------------------------------------------------------------
    try:
        import vectorbt as _vbt_version
        vbt_version = getattr(_vbt_version, "__version__", "unknown")
    except Exception:
        vbt_version = "unknown"

    audit = {
        "data_source": data_source,
        "download_time_ms": download_ms,
        "signal_compute_time_ms": signal_ms,
        "bars_downloaded": bars_count,
        "first_bar": first_bar,
        "last_bar": last_bar,
        "signals_generated": signals_generated,
        "entries_count": entries_count,
        "exits_count": exits_count,
        "execution_delay": "1 bar (no lookahead)",
        "fees_applied": fees_pct,
        "engine": f"vectorbt {vbt_version}",
        "signal_logic": signal_logic,
        "steps": audit_steps,
    }

    # ------------------------------------------------------------------
    # 8. Assemble response
    # ------------------------------------------------------------------
    split_date = close.index[split_idx].isoformat() if split_idx < len(close) else None

    result = {
        "ticker": ticker,
        "strategy": strategy,
        "params": params,
        "start_date": start_date,
        "data_points": len(close),
        "split_date": split_date,
        "train_ratio": train_ratio,
        "equity_curve": {
            "dates": equity_dates,
            "values": equity_values,
        },
        "metrics": full_metrics,
        "trade_log": trade_log,
        "is_metrics": is_metrics,
        "oos_metrics": oos_metrics,
        "audit": audit,
    }

    return _sanitize(result)


# ---------------------------------------------------------------------------
# Grid search runner
# ---------------------------------------------------------------------------

def _compute_signals(strategy_key: str, close: pd.Series, high: pd.Series, low: pd.Series, params: dict):
    """Dispatch to the correct signal function based on strategy key."""
    if strategy_key == "macd":
        return _macd_signals(close, params)
    elif strategy_key == "donchian":
        return _donchian_signals(close, high, low, params)
    elif strategy_key == "ema":
        return _ema_crossover_signals(close, params)
    elif strategy_key == "supertrend":
        return _supertrend_signals(close, high, low, params)
    elif strategy_key == "rsi":
        return _rsi_signals(close, params)
    elif strategy_key == "triple_ema":
        return _triple_ema_signals(close, params)
    elif strategy_key == "schaff":
        return _schaff_signals(close, params)
    else:
        raise ValueError(f"Unknown strategy key: {strategy_key}")


def run_grid_search(
    strategy: str,
    ticker: str,
    start_date: str = "2015-01-01",
    param_ranges: dict | None = None,
    init_cash: float = DEFAULT_INIT_CASH,
    fees: float = DEFAULT_FEES,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
    data_source: str = "yfinance",
    min_trades: int = 10,
) -> dict[str, Any]:
    """
    Run a grid search over parameter combinations for a given strategy.
    Downloads data once, tests all combos on the IS portion, ranks by Sharpe,
    and validates the top 5 on OOS data.
    """
    param_ranges = param_ranges or {}
    strategy_key = STRATEGY_MAP.get(strategy)
    if strategy_key is None:
        return {"error": f"Unknown strategy '{strategy}'. Supported: {list(STRATEGY_MAP.keys())}"}

    if not param_ranges:
        return {"error": "param_ranges must contain at least one parameter with values to search"}

    audit_steps = []
    t0_total = time.time()

    # ------------------------------------------------------------------
    # 1. Download data ONCE
    # ------------------------------------------------------------------
    t0_download = time.time()
    try:
        if data_source == "alpaca":
            df = _download_alpaca(ticker, start_date)
        else:
            df = _download_yfinance(ticker, start_date)
    except ImportError as e:
        return {"error": str(e)}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"{data_source} download failed: {e}"}
    download_ms = round((time.time() - t0_download) * 1000)

    close = df["Close"].squeeze()
    high = df["High"].squeeze()
    low = df["Low"].squeeze()

    bars_count = len(close)
    audit_steps.append(f"Downloaded {bars_count:,} daily bars from {data_source} in {download_ms}ms")

    # ------------------------------------------------------------------
    # 2. IS/OOS split
    # ------------------------------------------------------------------
    split_idx = int(len(close) * train_ratio)
    train_close = close.iloc[:split_idx]
    train_high = high.iloc[:split_idx]
    train_low = low.iloc[:split_idx]
    val_close = close.iloc[split_idx:]
    val_high = high.iloc[split_idx:]
    val_low = low.iloc[split_idx:]
    split_date = close.index[split_idx].isoformat() if split_idx < len(close) else None

    audit_steps.append(
        f"Split at bar {split_idx:,} ({int(train_ratio * 100)}% IS / {int((1 - train_ratio) * 100)}% OOS) — split date: {split_date}"
    )

    # ------------------------------------------------------------------
    # 3. Generate all parameter combinations
    # ------------------------------------------------------------------
    param_names = sorted(param_ranges.keys())
    param_values = [param_ranges[k] for k in param_names]
    combos = list(itertools.product(*param_values))
    total_combos = len(combos)
    audit_steps.append(f"Generated {total_combos:,} parameter combinations from {len(param_names)} parameters")

    # ------------------------------------------------------------------
    # 4. Run IS backtest for each combo
    # ------------------------------------------------------------------
    t0_grid = time.time()
    all_results = []
    combos_with_trades = 0
    errors = 0

    for combo in combos:
        params = dict(zip(param_names, combo))
        try:
            entries, exits = _compute_signals(strategy_key, close, high, low, params)

            # Slice to IS portion
            train_entries = entries.iloc[:split_idx]
            train_exits = exits.iloc[:split_idx]

            pf_is = _get_vbt().Portfolio.from_signals(
                train_close,
                entries=train_entries,
                exits=train_exits,
                init_cash=init_cash,
                fees=fees,
                freq=DEFAULT_FREQ,
            )

            is_metrics = _extract_metrics(pf_is)
            n_trades = is_metrics["total_trades"]

            result_entry = {
                "params": params,
                "is_sharpe": is_metrics["sharpe"],
                "is_return": is_metrics["total_return"],
                "is_max_dd": is_metrics["max_drawdown"],
                "is_trades": n_trades,
                "is_win_rate": is_metrics["win_rate"],
                "has_min_trades": n_trades >= min_trades,
            }
            all_results.append(result_entry)

            if n_trades >= min_trades:
                combos_with_trades += 1

        except Exception as e:
            errors += 1
            logger.warning(f"Grid combo {params} failed: {e}")
            all_results.append({
                "params": params,
                "is_sharpe": 0.0,
                "is_return": 0.0,
                "is_max_dd": 0.0,
                "is_trades": 0,
                "is_win_rate": 0.0,
                "has_min_trades": False,
                "error": str(e),
            })

    grid_ms = round((time.time() - t0_grid) * 1000)
    audit_steps.append(
        f"Tested {total_combos:,} combos in {grid_ms}ms — {combos_with_trades} had >= {min_trades} trades, {errors} errors"
    )

    # ------------------------------------------------------------------
    # 5. Rank by IS Sharpe, take top 20
    # ------------------------------------------------------------------
    valid_results = [r for r in all_results if r["has_min_trades"]]
    valid_results.sort(key=lambda r: r["is_sharpe"], reverse=True)
    top_20 = valid_results[:20]

    # ------------------------------------------------------------------
    # 6. Validate top 5 on OOS
    # ------------------------------------------------------------------
    t0_oos = time.time()
    top_results = []

    for rank, result in enumerate(top_20, 1):
        entry = {
            "rank": rank,
            "params": result["params"],
            "is_sharpe": result["is_sharpe"],
            "is_return": result["is_return"],
            "is_max_dd": result["is_max_dd"],
            "is_trades": result["is_trades"],
            "is_win_rate": result["is_win_rate"],
        }

        # OOS validation for top 5
        if rank <= 5:
            try:
                entries, exits = _compute_signals(strategy_key, close, high, low, result["params"])
                val_entries = entries.iloc[split_idx:]
                val_exits = exits.iloc[split_idx:]

                pf_oos = _get_vbt().Portfolio.from_signals(
                    val_close,
                    entries=val_entries,
                    exits=val_exits,
                    init_cash=init_cash,
                    fees=fees,
                    freq=DEFAULT_FREQ,
                )
                oos_metrics = _extract_metrics(pf_oos)
                entry["oos_sharpe"] = oos_metrics["sharpe"]
                entry["oos_return"] = oos_metrics["total_return"]
                entry["oos_max_dd"] = oos_metrics["max_drawdown"]
                entry["oos_trades"] = oos_metrics["total_trades"]
                entry["oos_win_rate"] = oos_metrics["win_rate"]

                # Degradation: how much OOS Sharpe degrades vs IS Sharpe
                if result["is_sharpe"] != 0:
                    entry["degradation_pct"] = round(
                        (oos_metrics["sharpe"] - result["is_sharpe"]) / abs(result["is_sharpe"]) * 100, 1
                    )
                else:
                    entry["degradation_pct"] = 0.0

            except Exception as e:
                logger.warning(f"OOS validation for rank {rank} failed: {e}")
                entry["oos_sharpe"] = None
                entry["oos_return"] = None
                entry["oos_max_dd"] = None
                entry["oos_trades"] = None
                entry["oos_win_rate"] = None
                entry["degradation_pct"] = None

        top_results.append(entry)

    oos_ms = round((time.time() - t0_oos) * 1000)
    total_ms = round((time.time() - t0_total) * 1000)
    audit_steps.append(f"Validated top 5 on OOS in {oos_ms}ms")
    audit_steps.append(f"Total grid search time: {total_ms}ms")

    # ------------------------------------------------------------------
    # 7. Build response
    # ------------------------------------------------------------------
    # Strip has_min_trades from all_results (internal flag)
    for r in all_results:
        r.pop("has_min_trades", None)
        r.pop("error", None)

    response = {
        "ticker": ticker,
        "strategy": strategy,
        "total_combos": total_combos,
        "combos_tested": total_combos,
        "combos_with_trades": combos_with_trades,
        "data_points": bars_count,
        "split_date": split_date,
        "top_results": top_results,
        "all_results": all_results,
        "audit": {
            "data_source": data_source,
            "download_time_ms": download_ms,
            "grid_time_ms": grid_ms,
            "oos_time_ms": oos_ms,
            "total_time_ms": total_ms,
            "min_trades_filter": min_trades,
            "train_ratio": train_ratio,
            "init_cash": init_cash,
            "fees": fees,
            "steps": audit_steps,
        },
    }

    return _sanitize(response)
