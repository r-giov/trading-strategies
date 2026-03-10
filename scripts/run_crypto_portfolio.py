"""
Crypto Portfolio FTMO — Headless runner.
Runs the portfolio backtest and sends results to Telegram.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

# ── Imports ──
import yfinance as yf
import talib
from scipy import stats
import urllib.request
import urllib.parse
import json

# ── Config ──
START_DATE = '2018-01-01'
TRAIN_RATIO = 0.60
INIT_CASH = 100_000
FEES = 0.0005
SLIPPAGE = 0.0005

PORTFOLIO = [
    ('donchian', 'XRP-USD', 0.30, {'entry': 10, 'exit': 3, 'filter': 20}),
    ('macd',     'BTC-USD', 0.20, {'fast': 30, 'slow': 59, 'signal': 6}),
    ('macd',     'XRP-USD', 0.20, {'fast': 22, 'slow': 39, 'signal': 3}),
    ('macd',     'ETH-USD', 0.15, {'fast': 29, 'slow': 44, 'signal': 5}),
    ('donchian', 'BTC-USD', 0.15, {'entry': 31, 'exit': 17, 'filter': 70}),
]

TG_BOT_TOKEN = '8691594427:AAGKbcObikmFxr3yJk5kVkIFkIDAuVyqeoo'
TG_CHAT_ID = '6451760231'


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        'chat_id': TG_CHAT_ID, 'text': message, 'parse_mode': 'Markdown',
    }).encode()
    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"Telegram send failed: {e}")
        return False


def macd_signals(close, fast, slow, signal):
    ml, sl, _ = talib.MACD(close.values.astype(float),
                           fastperiod=fast, slowperiod=slow, signalperiod=signal)
    macd_s = pd.Series(ml, index=close.index)
    sig_s = pd.Series(sl, index=close.index)
    entries_raw = (macd_s.shift(1) <= sig_s.shift(1)) & (macd_s > sig_s)
    exits_raw = (macd_s.shift(1) >= sig_s.shift(1)) & (macd_s < sig_s)
    entries = pd.Series(np.where(entries_raw.shift(1).isna(), False, entries_raw.shift(1)),
                        index=close.index, dtype=bool)
    exits = pd.Series(np.where(exits_raw.shift(1).isna(), False, exits_raw.shift(1)),
                      index=close.index, dtype=bool)
    return entries, exits


def donchian_signals(close, high, low, entry_period, exit_period, filter_period):
    upper = pd.Series(talib.MAX(high.values, entry_period), index=close.index).shift(1)
    lower = pd.Series(talib.MIN(low.values, exit_period), index=close.index).shift(1)
    trend = pd.Series(talib.SMA(close.values, filter_period), index=close.index).shift(1)
    entries_raw = (close > upper) & (close > trend)
    exits_raw = (close < lower)
    entries = pd.Series(np.where(entries_raw.shift(1).isna(), False, entries_raw.shift(1)),
                        index=close.index, dtype=bool)
    exits = pd.Series(np.where(exits_raw.shift(1).isna(), False, exits_raw.shift(1)),
                      index=close.index, dtype=bool)
    return entries, exits


def compute_metrics(daily_rets, label):
    total_ret = (1 + daily_rets).prod() - 1
    n_years = len(daily_rets) / 252
    ann_ret = (1 + total_ret) ** (1 / n_years) - 1 if n_years > 0 else 0
    ann_vol = daily_rets.std() * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
    cum = (1 + daily_rets).cumprod()
    dd = cum / cum.cummax() - 1
    max_dd = dd.min()
    calmar = ann_ret / abs(max_dd) if abs(max_dd) > 1e-9 else np.nan
    return {'label': label, 'total_return': total_ret, 'ann_return': ann_ret,
            'ann_vol': ann_vol, 'sharpe': sharpe, 'max_dd': max_dd, 'calmar': calmar}


def main():
    print("Downloading data...")
    tickers = list(set(t for _, t, _, _ in PORTFOLIO))
    data = {}
    for ticker in tickers:
        df = yf.download(ticker, start=START_DATE, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            close = df[('Close', ticker)].astype(float).squeeze()
            high = df[('High', ticker)].astype(float).squeeze()
            low = df[('Low', ticker)].astype(float).squeeze()
        else:
            close = df['Close'].astype(float).squeeze()
            high = df['High'].astype(float).squeeze()
            low = df['Low'].astype(float).squeeze()
        close.name = 'price'
        data[ticker] = {'close': close, 'high': high, 'low': low}
        print(f"  {ticker}: {len(close)} bars")

    # Align
    common_start = max(d['close'].index[0] for d in data.values())
    common_end = min(d['close'].index[-1] for d in data.values())
    for ticker in tickers:
        mask = (data[ticker]['close'].index >= common_start) & (data[ticker]['close'].index <= common_end)
        for k in ['close', 'high', 'low']:
            data[ticker][k] = data[ticker][k][mask]

    n_bars = len(data[tickers[0]]['close'])
    split_idx = int(n_bars * TRAIN_RATIO)
    print(f"Common: {common_start.date()} to {common_end.date()} ({n_bars} bars)")

    # Run components (without vectorbt — pure pandas for headless)
    print("\nRunning portfolio components...")
    component_daily_returns = []
    component_results = []

    for strat, ticker, weight, params in PORTFOLIO:
        close = data[ticker]['close']
        high = data[ticker]['high']
        low = data[ticker]['low']

        if strat == 'macd':
            entries, exits = macd_signals(close, params['fast'], params['slow'], params['signal'])
            label = f"MACD({params['fast']},{params['slow']},{params['signal']})"
        elif strat == 'donchian':
            entries, exits = donchian_signals(close, high, low,
                                              params['entry'], params['exit'], params['filter'])
            label = f"Donchian({params['entry']},{params['exit']},{params['filter']})"

        # Simple backtest: enter on entry signal, exit on exit signal
        position = pd.Series(0.0, index=close.index)
        in_position = False
        for i in range(len(close)):
            if not in_position and entries.iloc[i]:
                in_position = True
            elif in_position and exits.iloc[i]:
                in_position = False
            position.iloc[i] = 1.0 if in_position else 0.0

        daily_ret = close.pct_change().fillna(0) * position.shift(1).fillna(0)
        # Apply fees on trades
        trades_mask = position.diff().abs()
        daily_ret = daily_ret - trades_mask * FEES

        component_daily_returns.append(daily_ret * weight)

        # Metrics
        val_ret = daily_ret.iloc[split_idx:]
        m_oos = compute_metrics(val_ret, 'OOS')
        m_full = compute_metrics(daily_ret, 'Full')

        # Win rate from trades
        trade_starts = (position.diff() == 1)
        trade_ends = (position.diff() == -1)
        trade_rets = []
        cum_ret = 0
        in_trade = False
        for i in range(len(close)):
            if trade_starts.iloc[i]:
                in_trade = True
                cum_ret = 0
            if in_trade:
                cum_ret += daily_ret.iloc[i]
            if trade_ends.iloc[i] and in_trade:
                trade_rets.append(cum_ret)
                in_trade = False
        trade_rets = np.array(trade_rets)
        n_trades = len(trade_rets)
        win_rate = (trade_rets > 0).sum() / n_trades * 100 if n_trades > 0 else 0

        result = {
            'component': f"{strat.upper()} {ticker}",
            'label': label, 'weight': weight,
            'full_sharpe': m_full['sharpe'], 'oos_sharpe': m_oos['sharpe'],
            'full_return': m_full['total_return'], 'oos_return': m_oos['total_return'],
            'oos_maxdd': m_oos['max_dd'], 'trades': n_trades, 'win_rate': win_rate,
        }
        component_results.append(result)
        print(f"  {result['component']:25s} | OOS Sharpe={m_oos['sharpe']:.3f} | "
              f"Return={m_oos['total_return']:.1%} | DD={m_oos['max_dd']:.1%} | "
              f"Trades={n_trades} | WR={win_rate:.0f}%")

    # Combined portfolio
    port_rets = pd.concat(component_daily_returns, axis=1).sum(axis=1)
    port_rets_oos = port_rets.iloc[split_idx:]

    m_port_full = compute_metrics(port_rets, 'Full')
    m_port_oos = compute_metrics(port_rets_oos, 'OOS')

    print(f"\nPORTFOLIO COMBINED:")
    print(f"  Full  — Sharpe={m_port_full['sharpe']:.3f} Return={m_port_full['total_return']:.1%} DD={m_port_full['max_dd']:.1%}")
    print(f"  OOS   — Sharpe={m_port_oos['sharpe']:.3f} Return={m_port_oos['total_return']:.1%} DD={m_port_oos['max_dd']:.1%}")

    # Monte Carlo
    print("\nRunning Monte Carlo (10,000 sims)...")
    daily_arr = port_rets.values
    daily_arr = daily_arr[~np.isnan(daily_arr)]
    np.random.seed(42)
    n_sims = 10_000
    n_passed = 0
    n_blown_total = 0
    n_blown_daily = 0
    finals = []

    for _ in range(n_sims):
        sim_rets = np.random.choice(daily_arr, size=30, replace=True)
        eq = 100_000.0
        done = False
        for r in sim_rets:
            day_start = eq
            eq *= (1 + r)
            if (eq - day_start) / 100_000 < -0.05:
                n_blown_daily += 1; done = True; break
            if (eq - 100_000) / 100_000 < -0.10:
                n_blown_total += 1; done = True; break
            if (eq - 100_000) / 100_000 >= 0.10:
                n_passed += 1; done = True; break
        finals.append(eq)

    pass_rate = n_passed / n_sims * 100
    if pass_rate >= 50: verdict = f"FAVORABLE -- {pass_rate:.1f}%"
    elif pass_rate >= 25: verdict = f"POSSIBLE -- {pass_rate:.1f}%"
    elif pass_rate >= 10: verdict = f"CHALLENGING -- {pass_rate:.1f}%"
    else: verdict = f"UNLIKELY -- {pass_rate:.1f}%"

    print(f"  Passed: {n_passed} ({pass_rate:.1f}%)")
    print(f"  Blown (total): {n_blown_total} | Blown (daily): {n_blown_daily}")
    print(f"  Verdict: {verdict}")
    print(f"  Median final: ${np.median(finals):,.0f}")

    # Correlation
    ret_df = pd.concat([r.rename(f"{s}_{t}") for (s,t,_,_), r in zip(PORTFOLIO, component_daily_returns)], axis=1)
    corr = ret_df.corr()
    avg_corr = corr.values[np.triu_indices(len(corr), k=1)].mean()

    # Send Telegram
    msg = (
        f"*Crypto Portfolio FTMO -- Backtest Complete*\n\n"
        f"Period: {common_start.date()} to {common_end.date()}\n"
        f"Components: {len(PORTFOLIO)}\n\n"
        f"*Portfolio (OOS):*\n"
        f"  Sharpe: {m_port_oos['sharpe']:.3f}\n"
        f"  Return: {m_port_oos['total_return']:.1%}\n"
        f"  Max DD: {m_port_oos['max_dd']:.1%}\n"
        f"  Calmar: {m_port_oos['calmar']:.3f}\n\n"
        f"*Full Sample:*\n"
        f"  Sharpe: {m_port_full['sharpe']:.3f}\n"
        f"  Return: {m_port_full['total_return']:.1%}\n"
        f"  Max DD: {m_port_full['max_dd']:.1%}\n\n"
        f"*FTMO Monte Carlo:*\n"
        f"  Pass Rate: {pass_rate:.1f}%\n"
        f"  Verdict: {verdict}\n"
        f"  Median Equity: ${np.median(finals):,.0f}\n\n"
        f"*Components:*\n"
    )
    for r in component_results:
        msg += f"  {r['component']}: OOS={r['oos_sharpe']:.2f}, WR={r['win_rate']:.0f}%\n"
    msg += f"\nAvg Correlation: {avg_corr:.3f}"

    if send_telegram(msg):
        print("\nResults sent to Telegram!")
    else:
        print("\nTelegram send failed. Message:")
        print(msg)

    # Save results
    export_dir = os.path.join(os.path.dirname(__file__), '..', 'strategy_exports',
                              'Crypto_Portfolio_FTMO', 'PORTFOLIO', 'latest')
    os.makedirs(export_dir, exist_ok=True)
    summary = {
        'strategy': 'Crypto_Portfolio_FTMO',
        'full_sample': m_port_full,
        'out_of_sample': m_port_oos,
        'monte_carlo': {'pass_rate': pass_rate, 'verdict': verdict,
                        'median_equity': float(np.median(finals))},
        'components': component_results,
        'avg_correlation': float(avg_corr),
    }
    with open(os.path.join(export_dir, 'summary.json'), 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    port_rets.to_csv(os.path.join(export_dir, 'daily_returns.csv'))
    print(f"Exported to {export_dir}")


if __name__ == '__main__':
    main()
