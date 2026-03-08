#!/usr/bin/env python3
"""
Quick Backtest — Fast Single-Parameter Screening Tool
======================================================

Downloads data via yfinance and runs a single-parameter-set backtest
(no grid search) using known-good defaults for each strategy type.
Prints a concise terminal summary for quick ticker screening.

Usage (terminal / Claude Code):
    python scripts/quick_backtest.py --strategy MACD --ticker BTC-USD
    python scripts/quick_backtest.py --strategy RSI --ticker EURUSD=X --start 2020-01-01
    python scripts/quick_backtest.py --strategy Donchian --ticker GC=F --start 2019-01-01
    python scripts/quick_backtest.py --strategy EMA --ticker ^DJI
    python scripts/quick_backtest.py --strategy TripleEMA --ticker ETH-USD

Usage (Colab):
    !python scripts/quick_backtest.py --strategy MACD --ticker SOL-USD

Options:
    --strategy STR   Strategy type: MACD, RSI, EMA, TripleEMA, Donchian
    --ticker STR     yfinance ticker symbol (e.g. BTC-USD, EURUSD=X, ^GSPC)
    --start DATE     Start date for data download (default: 2020-01-01)
    --params JSON    Override default params as JSON string
                     e.g. '{"fast_period": 8, "slow_period": 21, "signal_period": 9}'
    --cash FLOAT     Initial cash (default: 100000)
    --train-ratio F  IS/OOS split ratio (default: 0.60)
    --no-plot        Suppress matplotlib equity curve plot

Supported Strategies & Default Params:
    MACD       fast_period=12, slow_period=26, signal_period=9
    RSI        rsi_len=14, oversold=30, overbought=70
    EMA        fast_ema=12, slow_ema=26, trend_filter=50
    TripleEMA  ema1_period=5, ema2_period=13, ema3_period=34
    Donchian   entry_period=20, exit_period=10, filter_period=50

Output:
    Sharpe | Return | MaxDD | Win Rate | Trades | Profit Factor
    Plus IS vs OOS comparison and quick FTMO viability estimate
"""

import os
import sys
import json
import argparse
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ════════════════════════════════════════════════════════════════
# DEFAULT PARAMETERS (known-good starting points)
# ════════════════════════════════════════════════════════════════

DEFAULT_PARAMS = {
    "MACD": {"fast_period": 12, "slow_period": 26, "signal_period": 9},
    "RSI": {"rsi_len": 14, "oversold": 30, "overbought": 70},
    "EMA": {"fast_ema": 12, "slow_ema": 26, "trend_filter": 50},
    "TripleEMA": {"ema1_period": 5, "ema2_period": 13, "ema3_period": 34},
    "Donchian": {"entry_period": 20, "exit_period": 10, "filter_period": 50},
}

# Strategy name mapping (what the user types -> what the signal function expects)
STRATEGY_ALIASES = {
    "MACD": "MACD_Crossover",
    "RSI": "RSI_MeanReversion",
    "EMA": "EMA_Crossover",
    "TripleEMA": "TripleEMA_Crossover",
    "TEMA": "TripleEMA_Crossover",
    "Donchian": "Donchian_Breakout",
    "DC": "Donchian_Breakout",
}

# Backtest constants (matching CLAUDE.md spec)
FEES = 0.0005
SLIPPAGE = 0.0005
FREQ = "D"


# ════════════════════════════════════════════════════════════════
# SIGNAL GENERATION
# ════════════════════════════════════════════════════════════════

def compute_signals(strategy_name, price_s, params, high_s=None, low_s=None):
    """
    Generate entry/exit signals with 1-bar execution delay.
    Mirrors the logic in UNIVERSAL_EXPORT_CELL_v2.py exactly.
    """
    import talib

    idx = price_s.index
    vals = price_s.values.astype(float)

    if strategy_name.startswith("MACD"):
        ml, sl, _ = talib.MACD(
            vals,
            fastperiod=params["fast_period"],
            slowperiod=params["slow_period"],
            signalperiod=params["signal_period"],
        )
        ms = pd.Series(ml, index=idx)
        ss = pd.Series(sl, index=idx)
        e_raw = (ms.shift(1) <= ss.shift(1)) & (ms > ss)
        x_raw = (ms.shift(1) >= ss.shift(1)) & (ms < ss)

    elif strategy_name.startswith("RSI"):
        rsi_s = pd.Series(talib.RSI(vals, timeperiod=params["rsi_len"]), index=idx)
        e_raw = (rsi_s.shift(1) <= params["oversold"]) & (rsi_s > params["oversold"])
        x_raw = (rsi_s.shift(1) <= params["overbought"]) & (rsi_s > params["overbought"])

    elif strategy_name.startswith("EMA") and not strategy_name.startswith("Triple"):
        fv = pd.Series(talib.EMA(vals, timeperiod=params["fast_ema"]), index=idx)
        sv = pd.Series(talib.EMA(vals, timeperiod=params["slow_ema"]), index=idx)
        tv = pd.Series(talib.SMA(vals, timeperiod=params["trend_filter"]), index=idx)
        cs = pd.Series(vals, index=idx)
        e_raw = (fv.shift(1) <= sv.shift(1)) & (fv > sv) & (cs > tv)
        x_raw = (fv.shift(1) >= sv.shift(1)) & (fv < sv)

    elif strategy_name.startswith("Triple") or strategy_name.startswith("TEMA"):
        e1 = pd.Series(talib.EMA(vals, timeperiod=params["ema1_period"]), index=idx)
        e2 = pd.Series(talib.EMA(vals, timeperiod=params["ema2_period"]), index=idx)
        e3 = pd.Series(talib.EMA(vals, timeperiod=params["ema3_period"]), index=idx)
        e_raw = (
            ((e1.shift(1) <= e2.shift(1)) & (e1 > e2))
            | ((e1.shift(1) <= e3.shift(1)) & (e1 > e3))
            | ((e2.shift(1) <= e3.shift(1)) & (e2 > e3))
        )
        x_raw = (
            ((e1.shift(1) >= e2.shift(1)) & (e1 < e2))
            | ((e1.shift(1) >= e3.shift(1)) & (e1 < e3))
            | ((e2.shift(1) >= e3.shift(1)) & (e2 < e3))
        )

    elif strategy_name.startswith("Donchian") or strategy_name.startswith("DC"):
        h_v = high_s.values.astype(float) if high_s is not None else vals
        l_v = low_s.values.astype(float) if low_s is not None else vals
        uc = pd.Series(talib.MAX(h_v, timeperiod=params["entry_period"]), index=idx).shift(1)
        lc = pd.Series(talib.MIN(l_v, timeperiod=params["exit_period"]), index=idx).shift(1)
        tf = pd.Series(talib.SMA(vals, timeperiod=params["filter_period"]), index=idx).shift(1)
        cs = pd.Series(vals, index=idx)
        e_raw = (cs > uc) & (cs > tf)
        x_raw = cs < lc

    else:
        raise ValueError(f"Unknown strategy: {strategy_name}")

    # 1-bar execution delay
    entries = pd.Series(
        np.where(e_raw.shift(1).isna(), False, e_raw.shift(1)),
        index=idx, dtype=bool,
    )
    exits = pd.Series(
        np.where(x_raw.shift(1).isna(), False, x_raw.shift(1)),
        index=idx, dtype=bool,
    )
    return entries, exits


# ════════════════════════════════════════════════════════════════
# TERMINAL OUTPUT HELPERS
# ════════════════════════════════════════════════════════════════

def _c(text, code):
    return f"\033[{code}m{text}\033[0m"

def green(t):  return _c(t, "32")
def red(t):    return _c(t, "31")
def yellow(t): return _c(t, "33")
def cyan(t):   return _c(t, "36")
def bold(t):   return _c(t, "1")
def dim(t):    return _c(t, "2")


def fmt_pct(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "N/A"
    return f"{v*100:+.2f}%"


def sharpe_verdict(s):
    if s is None or np.isnan(s):
        return dim("N/A")
    if s >= 1.5:
        return green(f"{s:.3f}")
    elif s >= 0.5:
        return cyan(f"{s:.3f}")
    elif s >= 0.0:
        return yellow(f"{s:.3f}")
    else:
        return red(f"{s:.3f}")


# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Quick Backtest — fast single-parameter screening",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--strategy", type=str, required=True,
                        choices=list(DEFAULT_PARAMS.keys()) + ["TEMA", "DC"],
                        help="Strategy type")
    parser.add_argument("--ticker", type=str, required=True,
                        help="yfinance ticker (e.g. BTC-USD, EURUSD=X)")
    parser.add_argument("--start", type=str, default="2020-01-01",
                        help="Start date (default: 2020-01-01)")
    parser.add_argument("--params", type=str, default=None,
                        help='Override params as JSON: \'{"fast_period": 8}\'')
    parser.add_argument("--cash", type=float, default=100_000,
                        help="Initial cash (default: 100000)")
    parser.add_argument("--train-ratio", type=float, default=0.60,
                        help="IS/OOS train ratio (default: 0.60)")
    parser.add_argument("--no-plot", action="store_true",
                        help="Suppress equity curve plot")
    args = parser.parse_args()

    # Resolve strategy name
    strat_key = args.strategy
    if strat_key in ("TEMA", "DC"):
        strat_key = {"TEMA": "TripleEMA", "DC": "Donchian"}[strat_key]
    strategy_name = STRATEGY_ALIASES[strat_key]

    # Build params
    params = DEFAULT_PARAMS[strat_key].copy()
    if args.params:
        overrides = json.loads(args.params)
        params.update(overrides)

    param_str = ", ".join(f"{k}={v}" for k, v in params.items())

    # ── Download data ──
    print(bold(f"\n{'='*65}"))
    print(bold(f"  QUICK BACKTEST — {strategy_name} on {args.ticker}"))
    print(bold(f"{'='*65}"))
    print(dim(f"  Params: {param_str}"))
    print(dim(f"  Period: {args.start} to present  |  Cash: ${args.cash:,.0f}"))
    print()

    try:
        import yfinance as yf
    except ImportError:
        print(red("ERROR: yfinance not installed. Run: pip install yfinance"))
        sys.exit(1)

    print("  Downloading data...", end=" ", flush=True)
    stock_data = yf.download(args.ticker, start=args.start, progress=False)

    if stock_data is None or stock_data.empty:
        print(red("FAILED"))
        print(red(f"  Could not download data for {args.ticker}"))
        sys.exit(1)

    # Handle MultiIndex columns from yfinance
    if isinstance(stock_data.columns, pd.MultiIndex):
        close = stock_data[("Close", args.ticker)].astype(float).squeeze()
        high_s = stock_data[("High", args.ticker)].astype(float).squeeze()
        low_s = stock_data[("Low", args.ticker)].astype(float).squeeze()
    else:
        close = stock_data["Close"].astype(float).squeeze()
        high_s = stock_data["High"].astype(float).squeeze()
        low_s = stock_data["Low"].astype(float).squeeze()

    close = close.dropna()
    close.name = "price"
    print(green(f"OK ({len(close)} bars, {close.index[0].date()} to {close.index[-1].date()})"))

    # ── IS/OOS split ──
    split_idx = int(len(close) * args.train_ratio)
    train_close = close.iloc[:split_idx].copy()
    val_close = close.iloc[split_idx:].copy()
    print(dim(f"  IS: {len(train_close)} bars ({train_close.index[0].date()} to "
              f"{train_close.index[-1].date()})"))
    print(dim(f"  OOS: {len(val_close)} bars ({val_close.index[0].date()} to "
              f"{val_close.index[-1].date()})"))

    # ── Import heavy libs after data download ──
    try:
        import talib  # noqa: F401 — used inside compute_signals
    except ImportError:
        print(red("ERROR: TA-Lib not installed. See: https://github.com/TA-Lib/ta-lib-python"))
        sys.exit(1)

    try:
        import vectorbt as vbt
    except ImportError:
        print(red("ERROR: vectorbt not installed. Run: pip install vectorbt"))
        sys.exit(1)

    # ── Compute signals & run backtest ──
    print("  Running backtest...", end=" ", flush=True)

    needs_hl = strategy_name.startswith("Donchian") or strategy_name.startswith("DC")

    # Full sample
    e_full, x_full = compute_signals(
        strategy_name, close, params,
        high_s if needs_hl else None,
        low_s if needs_hl else None,
    )
    pf_full = vbt.Portfolio.from_signals(
        close=close, entries=e_full, exits=x_full,
        init_cash=args.cash, fees=FEES, slippage=SLIPPAGE, freq=FREQ,
    )

    # IS
    e_is, x_is = compute_signals(
        strategy_name, train_close, params,
        high_s.iloc[:split_idx] if needs_hl else None,
        low_s.iloc[:split_idx] if needs_hl else None,
    )
    pf_is = vbt.Portfolio.from_signals(
        close=train_close, entries=e_is, exits=x_is,
        init_cash=args.cash, fees=FEES, slippage=SLIPPAGE, freq=FREQ,
    )

    # OOS
    e_oos, x_oos = compute_signals(
        strategy_name, val_close, params,
        high_s.iloc[split_idx:] if needs_hl else None,
        low_s.iloc[split_idx:] if needs_hl else None,
    )
    pf_oos = vbt.Portfolio.from_signals(
        close=val_close, entries=e_oos, exits=x_oos,
        init_cash=args.cash, fees=FEES, slippage=SLIPPAGE, freq=FREQ,
    )

    print(green("DONE"))

    # ── Extract metrics ──
    def safe(fn, default=None):
        try:
            return float(fn())
        except Exception:
            return default

    trades_obj = pf_full.trades
    tr = np.asarray(
        trades_obj.returns.values if hasattr(trades_obj.returns, "values")
        else trades_obj.returns
    ).ravel()
    pnl = np.asarray(
        trades_obj.pnl.values if hasattr(trades_obj.pnl, "values")
        else trades_obj.pnl
    ).ravel()
    pos = tr[tr > 0]
    neg = tr[tr < 0]

    sharpe = safe(lambda: pf_full.sharpe_ratio(freq=FREQ))
    sortino = safe(lambda: pf_full.sortino_ratio(freq=FREQ))
    total_ret = safe(pf_full.total_return)
    max_dd = safe(pf_full.max_drawdown)
    n_trades = len(trades_obj)
    win_rate = float(len(pos) / len(tr) * 100) if len(tr) > 0 else None
    pf_ratio = float(pos.sum() / abs(neg.sum())) if len(neg) > 0 and abs(neg.sum()) > 0 else None

    is_sharpe = safe(lambda: pf_is.sharpe_ratio(freq=FREQ))
    oos_sharpe = safe(lambda: pf_oos.sharpe_ratio(freq=FREQ))
    is_ret = safe(pf_is.total_return)
    oos_ret = safe(pf_oos.total_return)

    # ── Print results ──
    print(bold(f"\n  {'RESULTS':=^61}"))
    print()

    # Main metrics row
    print(f"  {'Sharpe':<12} {'Return':<12} {'MaxDD':<12} {'WinRate':<10} "
          f"{'Trades':<8} {'PF':<8}")
    print(f"  {'-'*12} {'-'*12} {'-'*12} {'-'*10} {'-'*8} {'-'*8}")

    sharpe_str = sharpe_verdict(sharpe)
    ret_str = fmt_pct(total_ret)
    dd_str = fmt_pct(max_dd)
    wr_str = f"{win_rate:.1f}%" if win_rate is not None else "N/A"
    pf_str = f"{pf_ratio:.2f}" if pf_ratio is not None else "N/A"

    print(f"  {sharpe_str:<21} {ret_str:<12} {dd_str:<12} {wr_str:<10} "
          f"{n_trades:<8} {pf_str:<8}")

    # IS vs OOS
    print(bold(f"\n  {'IS vs OOS':=^61}"))
    print(f"  {'':12} {'Sharpe':>10} {'Return':>12}")
    print(f"  {'In-Sample':<12} {sharpe_verdict(is_sharpe):>19} {fmt_pct(is_ret):>12}")
    print(f"  {'Out-of-Sample':<12} {sharpe_verdict(oos_sharpe):>19} {fmt_pct(oos_ret):>12}")

    if is_sharpe and oos_sharpe and abs(is_sharpe) > 1e-6:
        drop = (1 - oos_sharpe / is_sharpe) * 100
        if drop > 50:
            print(red(f"\n  OVERFIT WARNING: OOS Sharpe dropped {drop:.0f}% from IS"))
        elif drop > 25:
            print(yellow(f"\n  CAUTION: OOS Sharpe dropped {drop:.0f}% from IS"))
        elif drop < -10:
            print(green(f"\n  STRONG: OOS Sharpe improved {-drop:.0f}% over IS"))

    # Quick FTMO estimate
    print(bold(f"\n  {'FTMO QUICK ESTIMATE':=^61}"))
    daily_rets = pf_full.returns().values.ravel()
    daily_rets = daily_rets[~np.isnan(daily_rets)]

    if len(daily_rets) > 10:
        np.random.seed(42)
        n_sim = 2000
        n_days = 30
        account = 100_000
        n_passed = 0

        for _ in range(n_sim):
            eq = account
            sim_rets = np.random.choice(daily_rets, size=n_days, replace=True)
            blown = False
            for d in range(n_days):
                day_start = eq
                eq *= (1 + sim_rets[d])
                if (eq - day_start) / account < -0.05:
                    blown = True
                    break
                if (eq - account) / account < -0.10:
                    blown = True
                    break
                if (eq - account) / account >= 0.10:
                    n_passed += 1
                    blown = True
                    break

        pass_rate = n_passed / n_sim * 100
        if pass_rate >= 50:
            verdict = green(f"FAVORABLE ({pass_rate:.1f}%)")
        elif pass_rate >= 25:
            verdict = cyan(f"POSSIBLE ({pass_rate:.1f}%)")
        elif pass_rate >= 10:
            verdict = yellow(f"CHALLENGING ({pass_rate:.1f}%)")
        else:
            verdict = red(f"UNLIKELY ({pass_rate:.1f}%)")

        print(f"  Monte Carlo ({n_sim} sims, 30 days): {verdict}")
    else:
        print(dim("  Not enough daily returns for Monte Carlo estimate."))

    # Recommendation
    print(bold(f"\n  {'VERDICT':=^61}"))
    proceed = True
    reasons = []

    if sharpe is not None and sharpe < 0:
        proceed = False
        reasons.append("Negative Sharpe ratio")
    if n_trades < 10:
        proceed = False
        reasons.append(f"Only {n_trades} trades (need 10+ for significance)")
    if max_dd is not None and abs(max_dd) > 0.30:
        reasons.append(f"High drawdown ({fmt_pct(max_dd)})")
    if win_rate is not None and win_rate < 30:
        reasons.append(f"Low win rate ({win_rate:.0f}%)")
    if is_sharpe and oos_sharpe and abs(is_sharpe) > 1e-6:
        drop = (1 - oos_sharpe / is_sharpe) * 100
        if drop > 50:
            reasons.append("Heavy OOS degradation (likely overfit)")

    if proceed and not reasons:
        print(green(f"  PROCEED to full grid search on {args.ticker}"))
        print(dim(f"  This ticker shows promise with {strategy_name} default params."))
    elif proceed and reasons:
        print(yellow(f"  PROCEED WITH CAUTION on {args.ticker}"))
        for r in reasons:
            print(yellow(f"    - {r}"))
    else:
        print(red(f"  SKIP {args.ticker} for {strategy_name}"))
        for r in reasons:
            print(red(f"    - {r}"))
        print(dim("  Try a different strategy or ticker."))

    print(bold(f"\n{'='*65}\n"))

    # ── Optional plot ──
    if not args.no_plot:
        try:
            import matplotlib
            # Use non-interactive backend if no display available
            if not os.environ.get("DISPLAY") and sys.platform != "win32":
                matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 6),
                                            gridspec_kw={"height_ratios": [3, 1]})
            fig.suptitle(f"{strategy_name} on {args.ticker} — Quick Backtest",
                         fontsize=13, fontweight="bold")

            eq = pf_full.value()
            ax1.plot(close.index[:split_idx], eq.iloc[:split_idx], color="#3498db",
                     linewidth=1.5, label="IS")
            ax1.plot(close.index[split_idx:], eq.iloc[split_idx:], color="#e67e22",
                     linewidth=1.5, label="OOS")
            ax1.axvline(x=close.index[split_idx], color="red", linestyle=":", alpha=0.5)
            ax1.set_ylabel("Portfolio Value ($)")
            ax1.legend(fontsize=8)
            ax1.grid(True, alpha=0.3)

            dd = pf_full.drawdown() * 100
            ax2.fill_between(close.index, dd.values, 0, color="#e74c3c", alpha=0.4)
            ax2.set_ylabel("Drawdown %")
            ax2.set_xlabel("Date")
            ax2.grid(True, alpha=0.3)

            plt.tight_layout()
            plt.show()
        except Exception as e:
            print(dim(f"  (Plot skipped: {e})"))


if __name__ == "__main__":
    main()
