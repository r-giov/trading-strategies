"""
Donchian Breakout Energy/Value Portfolio — FTMO Strategy
Donchian Channel breakout with SMA trend filter, long only.
Universe: Energy, Industrials & Financials (value/cyclical).
Dynamic allocation: 100% capital among instruments with open positions.
"""
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import yfinance as yf
import talib
import time
from datetime import datetime

# ============================================================
# CONFIGURATION
# ============================================================
UNIVERSE = {
    'XOM':  {'ftmo': 'XOM',  'sector': 'energy',      'name': 'Exxon Mobil'},
    'CVX':  {'ftmo': 'CVX',  'sector': 'energy',      'name': 'Chevron'},
    'COP':  {'ftmo': 'COP',  'sector': 'energy',      'name': 'ConocoPhillips'},
    'JPM':  {'ftmo': 'JPM',  'sector': 'financials',  'name': 'JPMorgan'},
    'GS':   {'ftmo': 'GS',   'sector': 'financials',  'name': 'Goldman Sachs'},
    'CAT':  {'ftmo': 'CAT',  'sector': 'industrials', 'name': 'Caterpillar'},
    'DE':   {'ftmo': 'DE',   'sector': 'industrials', 'name': 'Deere & Co'},
    'HON':  {'ftmo': 'HON',  'sector': 'industrials', 'name': 'Honeywell'},
}

START_DATE = '2015-01-01'
TRAIN_RATIO = 0.60
INIT_CASH = 100_000
FEES = 0.0005
SLIPPAGE = 0.0005
FREQ = 'D'

# Grid search — Donchian parameters
ENTRY_PERIOD_RANGE  = list(range(10, 51, 2))   # 10-50 step 2
EXIT_PERIOD_RANGE   = list(range(5, 26, 2))     # 5-25 step 2
FILTER_PERIOD_RANGE = [30, 50, 75, 100, 150, 200]

MIN_TRADES_IS = 15
TOP_N = 10

# FTMO
ACCOUNT_SIZE = 100_000
PROFIT_TARGET = 0.10
MAX_DAILY_DD = 0.05
MAX_TOTAL_DD = 0.10

n_combos = len(ENTRY_PERIOD_RANGE) * len(EXIT_PERIOD_RANGE) * len(FILTER_PERIOD_RANGE)
print(f'Universe: {len(UNIVERSE)} instruments')
print(f'Combos per instrument: {n_combos:,}')
print(f'Total backtests: {n_combos * len(UNIVERSE):,}')

# ============================================================
# DOWNLOAD DATA (full OHLC needed for Donchian)
# ============================================================
print('\nDOWNLOADING DATA')
print('=' * 60)

data = {}
for ticker, info in UNIVERSE.items():
    df = yf.download(ticker, start=START_DATE, progress=False)
    if df.empty:
        print(f'  WARNING: No data for {info["ftmo"]}')
        continue
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)
    data[ticker] = df
    print(f'  {info["ftmo"]:<8s} {len(df):>5d} bars  '
          f'[{df.index[0].strftime("%Y-%m-%d")} to {df.index[-1].strftime("%Y-%m-%d")}]')

print(f'Loaded {len(data)}/{len(UNIVERSE)} instruments.')

# ============================================================
# FAST BACKTEST — Donchian Channel Breakout
# ============================================================
def fast_backtest(close_arr, high_arr, low_arr, entry_period, exit_period, filter_period, min_trades=15):
    """Vectorized Donchian Channel breakout backtest."""
    n = len(close_arr)
    if n < max(entry_period, exit_period, filter_period) + 10:
        return None

    upper = talib.MAX(high_arr, entry_period)
    lower = talib.MIN(low_arr, exit_period)
    sma   = talib.SMA(close_arr, filter_period)

    # Shift by 1 bar — use previous bar's channel (no lookahead)
    upper_shifted = np.roll(upper, 1); upper_shifted[0] = np.nan
    lower_shifted = np.roll(lower, 1); lower_shifted[0] = np.nan
    sma_shifted   = np.roll(sma, 1);   sma_shifted[0]   = np.nan

    # Raw signals
    entry_raw = (close_arr > upper_shifted) & (close_arr > sma_shifted)
    exit_raw  = (close_arr < lower_shifted)

    # NaN mask
    nan_mask = np.isnan(upper_shifted) | np.isnan(lower_shifted) | np.isnan(sma_shifted)
    entry_raw[nan_mask] = False
    exit_raw[nan_mask]  = False

    # 1-bar execution delay
    entry_delayed = np.zeros(n, dtype=bool)
    exit_delayed  = np.zeros(n, dtype=bool)
    entry_delayed[1:] = entry_raw[:-1]
    exit_delayed[1:]  = exit_raw[:-1]

    # Position series (1=long, 0=flat)
    raw_signal = np.where(entry_delayed, 1.0, np.where(exit_delayed, -1.0, 0.0))
    pos = pd.Series(raw_signal).replace(0.0, np.nan).ffill().fillna(0.0).values
    pos = np.clip(pos, 0.0, 1.0)

    n_trades = int(np.sum((pos[1:] > 0) & (pos[:-1] <= 0)))
    if n_trades < min_trades:
        return None

    price_rets = np.diff(close_arr) / close_arr[:-1]
    strat_rets = pos[1:] * price_rets

    mean_r = np.mean(strat_rets)
    std_r  = np.std(strat_rets)
    if std_r < 1e-10:
        return None

    sharpe = (mean_r / std_r) * np.sqrt(252)
    total_ret = float(np.prod(1 + strat_rets) - 1)
    cum = np.cumprod(1 + strat_rets)
    peak = np.maximum.accumulate(cum)
    max_dd = float(np.min(cum / peak - 1))

    # Trade stats
    diffs = np.diff(pos)
    entries_idx = np.where(diffs > 0)[0]
    exits_idx   = np.where(diffs < 0)[0]
    hold_periods = []
    trade_returns = []
    for ei in entries_idx:
        ex = exits_idx[exits_idx > ei]
        if len(ex) > 0:
            hold_periods.append(ex[0] - ei)
            trade_ret = np.prod(1 + strat_rets[ei:ex[0]]) - 1
            trade_returns.append(trade_ret)

    avg_hold = float(np.mean(hold_periods)) if hold_periods else 0.0
    win_rate = float(np.mean([r > 0 for r in trade_returns]) * 100) if trade_returns else 0.0
    time_in_market = float(np.mean(pos) * 100)

    return {
        'sharpe': float(sharpe), 'total_ret': total_ret, 'max_dd': max_dd,
        'n_trades': n_trades, 'win_rate': win_rate, 'avg_hold_days': avg_hold,
        'ann_ret': float(mean_r * 252), 'ann_vol': float(std_r * np.sqrt(252)),
        'trades_per_year': round(n_trades / (len(close_arr) / 252), 1),
        'time_in_market': round(time_in_market, 1),
    }


# ============================================================
# GRID SEARCH
# ============================================================
print('\n' + '=' * 60)
print('GRID SEARCH — Donchian Breakout + SMA trend filter')
print('=' * 60)

all_results = {}
total_t0 = time.time()

for ticker, info in UNIVERSE.items():
    if ticker not in data:
        continue
    print(f'\n  {info["ftmo"]} ({info["name"]})', end='', flush=True)
    df = data[ticker]
    split_idx = int(len(df) * TRAIN_RATIO)

    close_is = df['close'].values.astype(float)[:split_idx]
    high_is  = df['high'].values.astype(float)[:split_idx]
    low_is   = df['low'].values.astype(float)[:split_idx]

    results = []
    t0 = time.time()

    for ep in ENTRY_PERIOD_RANGE:
        for xp in EXIT_PERIOD_RANGE:
            for fp in FILTER_PERIOD_RANGE:
                r = fast_backtest(close_is, high_is, low_is, ep, xp, fp, MIN_TRADES_IS)
                if r is not None:
                    r['entry_period'] = ep
                    r['exit_period']  = xp
                    r['filter_period'] = fp
                    results.append(r)

    elapsed = time.time() - t0
    df_res = pd.DataFrame(results)
    if len(df_res) > 0:
        df_res = df_res.sort_values('sharpe', ascending=False).reset_index(drop=True)
        all_results[ticker] = df_res
        top = df_res.iloc[0]
        print(f' — {len(df_res):,} valid ({elapsed:.0f}s)')
        print(f'    BEST: DC({int(top.entry_period)}/{int(top.exit_period)}/SMA{int(top.filter_period)}) '
              f'Sharpe={top.sharpe:.2f} Trades={int(top.n_trades)} '
              f'Tr/yr={top.trades_per_year} Hold={top.avg_hold_days:.0f}d '
              f'Win={top.win_rate:.0f}% DD={top.max_dd:.1%} InMkt={top.time_in_market:.0f}%')
    else:
        all_results[ticker] = pd.DataFrame()
        print(f' — 0 valid ({elapsed:.0f}s)')

print(f'\nGrid search done in {time.time()-total_t0:.0f}s')


# ============================================================
# POSITION SERIES — for OOS and dynamic allocation
# ============================================================
def get_position_series(close_series, high_series, low_series, entry_period, exit_period, filter_period):
    """Return binary position series (1=long, 0=flat) for dynamic allocation."""
    close_arr = close_series.values.astype(float)
    high_arr  = high_series.values.astype(float)
    low_arr   = low_series.values.astype(float)
    n = len(close_arr)

    upper = talib.MAX(high_arr, entry_period)
    lower = talib.MIN(low_arr, exit_period)
    sma   = talib.SMA(close_arr, filter_period)

    upper_shifted = np.roll(upper, 1); upper_shifted[0] = np.nan
    lower_shifted = np.roll(lower, 1); lower_shifted[0] = np.nan
    sma_shifted   = np.roll(sma, 1);   sma_shifted[0]   = np.nan

    entry_raw = (close_arr > upper_shifted) & (close_arr > sma_shifted)
    exit_raw  = (close_arr < lower_shifted)

    nan_mask = np.isnan(upper_shifted) | np.isnan(lower_shifted) | np.isnan(sma_shifted)
    entry_raw[nan_mask] = False
    exit_raw[nan_mask]  = False

    entry_delayed = np.zeros(n, dtype=bool)
    exit_delayed  = np.zeros(n, dtype=bool)
    entry_delayed[1:] = entry_raw[:-1]
    exit_delayed[1:]  = exit_raw[:-1]

    raw_signal = np.where(entry_delayed, 1.0, np.where(exit_delayed, -1.0, 0.0))
    pos = pd.Series(raw_signal, index=close_series.index).replace(0.0, np.nan).ffill().fillna(0.0)
    pos = pos.clip(0.0, 1.0)
    return pos


# ============================================================
# OOS VALIDATION
# ============================================================
print(f'\n{"="*100}')
print('OOS VALIDATION — Top-10 IS combos per instrument')
print(f'{"="*100}')

oos_results = {}
final_params = {}

for ticker, info in UNIVERSE.items():
    if ticker not in all_results or all_results[ticker].empty:
        continue

    df = data[ticker]
    split_idx = int(len(df) * TRAIN_RATIO)
    close_is  = df['close'].iloc[:split_idx]
    close_oos = df['close'].iloc[split_idx:]
    high_is   = df['high'].iloc[:split_idx]
    high_oos  = df['high'].iloc[split_idx:]
    low_is    = df['low'].iloc[:split_idx]
    low_oos   = df['low'].iloc[split_idx:]

    top_combos = all_results[ticker].head(TOP_N)
    results_list = []

    print(f'\n--- {info["ftmo"]} ---')
    print(f'{"#":<4} {"Params":^18} {"IS Shp":>7} {"OOS Shp":>8} {"IS Tr":>6} {"OOS Tr":>7} {"OOS Ret":>8} {"OOS DD":>8}')
    print('-' * 75)

    for rank, (_, row) in enumerate(top_combos.iterrows(), 1):
        ep, xp, fp = int(row.entry_period), int(row.exit_period), int(row.filter_period)

        # IS backtest (for verification)
        r_is = fast_backtest(close_is.values.astype(float), high_is.values.astype(float),
                             low_is.values.astype(float), ep, xp, fp, min_trades=1)
        # OOS backtest
        r_oos = fast_backtest(close_oos.values.astype(float), high_oos.values.astype(float),
                              low_oos.values.astype(float), ep, xp, fp, min_trades=1)

        is_sharpe  = r_is['sharpe'] if r_is else 0.0
        oos_sharpe = r_oos['sharpe'] if r_oos else 0.0
        is_trades  = r_is['n_trades'] if r_is else 0
        oos_trades = r_oos['n_trades'] if r_oos else 0
        oos_ret    = r_oos['total_ret'] if r_oos else 0.0
        oos_dd     = r_oos['max_dd'] if r_oos else 0.0

        param_str = f'{ep}/{xp}/SMA{fp}'
        print(f'  {rank:<3} {param_str:^18} {is_sharpe:>7.2f} {oos_sharpe:>8.2f} '
              f'{is_trades:>6} {oos_trades:>7} {oos_ret:>7.1%} {oos_dd:>8.1%}')

        results_list.append({
            'rank': rank, 'entry_period': ep, 'exit_period': xp, 'filter_period': fp,
            'is_sharpe': is_sharpe, 'oos_sharpe': oos_sharpe,
            'is_trades': is_trades, 'oos_trades': oos_trades,
            'oos_return': oos_ret, 'oos_max_dd': oos_dd,
        })

    oos_results[ticker] = results_list
    best = max(results_list, key=lambda x: x['oos_sharpe'])
    final_params[ticker] = {
        'entry_period': best['entry_period'],
        'exit_period': best['exit_period'],
        'filter_period': best['filter_period'],
    }

print(f'\n{"="*80}')
print('FINAL PARAMS (best OOS Sharpe from top-10 IS)')
print(f'{"="*80}')
for ticker, info in UNIVERSE.items():
    if ticker not in final_params:
        continue
    p = final_params[ticker]
    best = max(oos_results[ticker], key=lambda x: x['oos_sharpe'])
    print(f'  {info["ftmo"]:<8} DC({p["entry_period"]}/{p["exit_period"]}/SMA{p["filter_period"]})  '
          f'IS={best["is_sharpe"]:.2f}  OOS={best["oos_sharpe"]:.2f}  OOS Trades={best["oos_trades"]}')


# ============================================================
# DYNAMIC PORTFOLIO — Capital concentrated into active gates
# ============================================================
print(f'\n{"="*70}')
print('DYNAMIC PORTFOLIO — Capital concentrated into active gates')
print(f'{"="*70}')

positions = {}
instrument_rets = {}

for ticker, params in final_params.items():
    df = data[ticker]
    pos = get_position_series(
        df['close'], df['high'], df['low'],
        params['entry_period'], params['exit_period'], params['filter_period']
    )
    positions[ticker] = pos
    instrument_rets[ticker] = df['close'].pct_change().fillna(0)

# Align all series to common dates
pos_df = pd.DataFrame(positions).fillna(0)
rets_df = pd.DataFrame(instrument_rets).reindex(pos_df.index).fillna(0)

# Dynamic allocation: split capital equally among active instruments
n_active = pos_df.sum(axis=1)
n_active_safe = n_active.replace(0, 1)
weights = pos_df.div(n_active_safe, axis=0)

portfolio_rets = (weights * rets_df).sum(axis=1)
portfolio_equity = INIT_CASH * (1 + portfolio_rets).cumprod()

# Buy & hold benchmark
bh_portfolio_rets = rets_df.mean(axis=1)
bh_equity = INIT_CASH * (1 + bh_portfolio_rets).cumprod()

# IS/OOS split
split_idx = int(len(portfolio_rets) * TRAIN_RATIO)
port_rets_is = portfolio_rets.iloc[:split_idx]
port_rets_oos = portfolio_rets.iloc[split_idx:]


def compute_metrics(daily_rets, label):
    total_ret = float((1 + daily_rets).prod() - 1)
    n_years = len(daily_rets) / 252
    ann_ret = (1 + total_ret) ** (1 / n_years) - 1 if n_years > 0 else 0
    ann_vol = float(daily_rets.std() * np.sqrt(252))
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
    cum = (1 + daily_rets).cumprod()
    dd = cum / cum.cummax() - 1
    max_dd = float(dd.min())
    calmar = ann_ret / abs(max_dd) if abs(max_dd) > 1e-9 else np.nan
    down_vol = float(daily_rets[daily_rets < 0].std() * np.sqrt(252))
    sortino = ann_ret / down_vol if down_vol > 0 else np.nan
    return {
        'label': label, 'total_return': total_ret, 'ann_return': ann_ret,
        'ann_vol': ann_vol, 'sharpe': sharpe, 'sortino': sortino,
        'max_dd': max_dd, 'calmar': calmar,
    }


m_full = compute_metrics(portfolio_rets, 'Full')
m_is   = compute_metrics(port_rets_is, 'IS')
m_oos  = compute_metrics(port_rets_oos, 'OOS')
m_bh   = compute_metrics(bh_portfolio_rets, 'B&H')

print(f'\n{"Metric":<24} {"Full":>10} {"IS":>10} {"OOS":>10} {"B&H":>10}')
print('-' * 70)
for key, label in [('total_return', 'Total Return'), ('ann_return', 'Ann. Return'),
                    ('ann_vol', 'Ann. Volatility'), ('sharpe', 'Sharpe'),
                    ('sortino', 'Sortino'), ('max_dd', 'Max Drawdown'), ('calmar', 'Calmar')]:
    fmt = '.1%' if key in ('total_return', 'ann_return', 'ann_vol', 'max_dd') else '.2f'
    print(f'{label:<24} {m_full[key]:>10{fmt}} {m_is[key]:>10{fmt}} '
          f'{m_oos[key]:>10{fmt}} {m_bh[key]:>10{fmt}}')

# Activity stats
avg_active = float(n_active.mean())
pct_all_flat = float((n_active == 0).mean() * 100)
pct_in_market = float((n_active > 0).mean() * 100)
print(f'\nAvg instruments active: {avg_active:.1f} / {len(final_params)}')
print(f'Days in market: {pct_in_market:.0f}%')
print(f'Days 100% cash: {pct_all_flat:.0f}%')

# Total trades across portfolio
total_trades = 0
for ticker in final_params:
    pos = positions[ticker]
    trades_count = int(((pos > 0) & (pos.shift(1) <= 0)).sum())
    total_trades += trades_count
years = len(portfolio_rets) / 252
print(f'Total trades: {total_trades} ({total_trades/years:.0f}/year)')

# Per-instrument stats
print(f'\nPer-instrument:')
print(f'{"Instrument":<10} {"Params":^18} {"Sharpe":>7} {"Return":>8} {"MaxDD":>8} {"Trades":>7} {"Tr/yr":>7} {"InMkt":>6}')
print('-' * 80)
for ticker, params in final_params.items():
    info = UNIVERSE[ticker]
    pos = positions[ticker]
    ind_rets = pos * rets_df[ticker]
    ind_trades = int(((pos > 0) & (pos.shift(1) <= 0)).sum())
    total_r = float((1 + ind_rets).prod() - 1)
    cum = (1 + ind_rets).cumprod()
    peak = cum.cummax()
    md = float((cum / peak - 1).min())
    ann_r = float(ind_rets.mean() * 252)
    ann_v = float(ind_rets.std() * np.sqrt(252))
    shp = ann_r / ann_v if ann_v > 0 else 0
    in_mkt = float(pos.mean() * 100)
    param_str = f'{params["entry_period"]}/{params["exit_period"]}/SMA{params["filter_period"]}'
    print(f'{info["ftmo"]:<10} {param_str:^18} {shp:>7.2f} {total_r:>7.0%} {md:>8.1%} '
          f'{ind_trades:>7} {ind_trades/years:>6.1f} {in_mkt:>5.0f}%')

# Correlations
strat_rets_df = pd.DataFrame({UNIVERSE[t]['ftmo']: positions[t] * rets_df[t] for t in final_params})
print(f'\nStrategy Return Correlations:')
print(strat_rets_df.corr().round(2).to_string())


# ============================================================
# MONTE CARLO FTMO SIMULATION
# ============================================================
print(f'\n{"="*70}')
print('MONTE CARLO FTMO SIMULATION')
print(f'{"="*70}')

N_SIMULATIONS = 10_000
CHALLENGE_DAYS = 30

mc_returns = port_rets_oos.values
mc_returns = mc_returns[~np.isnan(mc_returns)]

print(f'Simulations: {N_SIMULATIONS:,}')
print(f'OOS daily returns: mean={np.mean(mc_returns)*100:.4f}%/day  std={np.std(mc_returns)*100:.3f}%/day')
print(f'Expected 30-day return: {np.mean(mc_returns)*30*100:.2f}%')

passed = blown = daily_dd_breaches = 0
final_equities = []
np.random.seed(42)

for _ in range(N_SIMULATIONS):
    sim_rets = np.random.choice(mc_returns, size=CHALLENGE_DAYS, replace=True)
    equity = ACCOUNT_SIZE
    hit_target = hit_dd = False
    for r in sim_rets:
        day_start = equity
        equity *= (1 + r)
        if (day_start - equity) / day_start > MAX_DAILY_DD:
            hit_dd = True
            daily_dd_breaches += 1
            break
        if (ACCOUNT_SIZE - equity) / ACCOUNT_SIZE > MAX_TOTAL_DD:
            hit_dd = True
            break
        if equity >= ACCOUNT_SIZE * (1 + PROFIT_TARGET):
            hit_target = True
            break
    if hit_target:
        passed += 1
    if hit_dd:
        blown += 1
    final_equities.append(equity)

pass_rate = passed / N_SIMULATIONS * 100
blow_rate = blown / N_SIMULATIONS * 100

print(f'\n  Pass rate:     {pass_rate:>6.1f}%  ({passed:,}/{N_SIMULATIONS:,})')
print(f'  Blow rate:     {blow_rate:>6.1f}%  ({blown:,}/{N_SIMULATIONS:,})')
print(f'  Neutral:       {100-pass_rate-blow_rate:>6.1f}%')
print(f'  Median equity: ${np.median(final_equities):,.0f}')
print(f'  5th-95th:      ${np.percentile(final_equities,5):,.0f} — ${np.percentile(final_equities,95):,.0f}')


# ============================================================
# 2025 MONTHLY BREAKDOWN ($100K)
# ============================================================
print(f'\n{"="*70}')
print('2025 MONTHLY BREAKDOWN ($100K account)')
print(f'{"="*70}')

port_eq_series = INIT_CASH * (1 + portfolio_rets).cumprod()
port_eq_series.index = pd.to_datetime(port_eq_series.index)

# Filter to 2025
eq_2025 = port_eq_series[port_eq_series.index.year == 2025]
rets_2025 = portfolio_rets[portfolio_rets.index.year == 2025]

if len(eq_2025) > 0:
    print(f'\n{"Month":<12} {"Start":>12} {"End":>12} {"P&L":>10} {"Return":>8} {"MaxDD":>8}')
    print('-' * 70)
    for month in range(1, 13):
        month_mask = (rets_2025.index.month == month)
        month_rets = rets_2025[month_mask]
        if len(month_rets) == 0:
            continue
        month_eq = eq_2025[eq_2025.index.month == month]
        start_eq = float(month_eq.iloc[0])
        end_eq   = float(month_eq.iloc[-1])
        pnl = end_eq - start_eq
        ret = pnl / start_eq
        cum_m = (1 + month_rets).cumprod()
        dd_m = float((cum_m / cum_m.cummax() - 1).min())
        month_name = datetime(2025, month, 1).strftime('%b %Y')
        print(f'{month_name:<12} ${start_eq:>10,.0f} ${end_eq:>10,.0f} '
              f'{"+" if pnl>=0 else ""}{pnl:>9,.0f} {ret:>7.1%} {dd_m:>8.1%}')

    total_2025_ret = float((1 + rets_2025).prod() - 1)
    start_2025 = float(eq_2025.iloc[0])
    end_2025 = float(eq_2025.iloc[-1])
    print(f'\n  2025 YTD: ${start_2025:,.0f} -> ${end_2025:,.0f}  '
          f'Return: {total_2025_ret:.1%}  P&L: ${end_2025-start_2025:+,.0f}')
else:
    print('  No 2025 data available yet.')


# ============================================================
# TODAY'S SIGNALS
# ============================================================
print(f'\n{"="*70}')
today_str = datetime.now().strftime('%A, %B %d, %Y')
print(f'TODAY\'S SIGNALS — {today_str}')
print(f'{"="*70}')

actions = []
for ticker, params in final_params.items():
    info = UNIVERSE[ticker]
    ep, xp, fp = params['entry_period'], params['exit_period'], params['filter_period']

    df_fresh = yf.download(ticker, period='2y', progress=False)
    if isinstance(df_fresh.columns, pd.MultiIndex):
        df_fresh.columns = df_fresh.columns.get_level_values(0)
    df_fresh = df_fresh.rename(columns=str.lower)

    close_arr = df_fresh['close'].values.astype(float)
    high_arr  = df_fresh['high'].values.astype(float)
    low_arr   = df_fresh['low'].values.astype(float)

    upper = talib.MAX(high_arr, ep)
    lower = talib.MIN(low_arr, xp)
    sma   = talib.SMA(close_arr, fp)

    price = close_arr[-1]
    # Previous bar's channel values (what we'd use for today's signal)
    upper_prev = upper[-2] if len(upper) > 1 else np.nan
    lower_prev = lower[-2] if len(lower) > 1 else np.nan
    sma_prev   = sma[-2] if len(sma) > 1 else np.nan

    # Use full position series to check current state
    pos = get_position_series(df_fresh['close'], df_fresh['high'], df_fresh['low'], ep, xp, fp)
    currently_long = pos.iloc[-1] > 0

    is_entry = (price > upper_prev) and (price > sma_prev) if not np.isnan(upper_prev) else False
    is_exit  = (price < lower_prev) if not np.isnan(lower_prev) else False

    if is_entry and not currently_long:
        action, status = 'BUY', f'BREAKOUT (>{upper_prev:.2f}) + SMA({fp})={sma_prev:.2f}'
    elif is_exit and currently_long:
        action, status = 'EXIT', f'BREAKDOWN (<{lower_prev:.2f})'
    elif currently_long:
        action, status = 'HOLD', f'Long (Upper={upper_prev:.2f} Lower={lower_prev:.2f})'
    else:
        action, status = 'FLAT', f'No breakout (need >{upper_prev:.2f})'

    actions.append({'ftmo': info['ftmo'], 'action': action, 'status': status,
                    'price': price, 'params': f'DC({ep}/{xp}/SMA{fp})', 'gate': currently_long})

active = [a for a in actions if a['action'] in ('BUY', 'HOLD')]
inactive = [a for a in actions if a['action'] in ('EXIT', 'FLAT')]

print(f'\n  ACTIVE ({len(active)}/{len(actions)})')
print(f'  {"-"*75}')
if active:
    for a in active:
        m = '>>>' if a['action'] == 'BUY' else '   '
        print(f'  {m} {a["action"]:<6} {a["ftmo"]:<8} @ ${a["price"]:>10,.2f}  {a["params"]}  {a["status"]}')
    alloc = ACCOUNT_SIZE / len(active)
    print(f'\n  Allocation: ${alloc:,.0f} per instrument ({len(active)} positions)')
else:
    print(f'  All gates closed — 100% CASH')

print(f'\n  FLAT/EXIT ({len(inactive)}/{len(actions)})')
print(f'  {"-"*75}')
for a in inactive:
    m = '<<<' if a['action'] == 'EXIT' else '   '
    print(f'  {m} {a["action"]:<6} {a["ftmo"]:<8} @ ${a["price"]:>10,.2f}  {a["params"]}  {a["status"]}')

print(f'\n{"="*70}')
print('DONE.')
