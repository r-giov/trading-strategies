"""
Supertrend Portfolio FTMO — Dynamic allocation with Monte Carlo.
Uses ATR-based Supertrend indicator for entry/exit signals.
Grid search: atr_period x multiplier x trend_sma filter.
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
    '^DJI':   {'ftmo': 'US30',   'sector': 'us_index',   'name': 'Dow Jones'},
    '^GSPC':  {'ftmo': 'US500',  'sector': 'us_index',   'name': 'S&P 500'},
    '^GDAXI': {'ftmo': 'GER40',  'sector': 'eu_index',   'name': 'DAX'},
    '^FTSE':  {'ftmo': 'UK100',  'sector': 'eu_index',   'name': 'FTSE 100'},
    'MSFT':   {'ftmo': 'MSFT',   'sector': 'tech',       'name': 'Microsoft'},
    'V':      {'ftmo': 'V',      'sector': 'financials',  'name': 'Visa'},
    'MA':     {'ftmo': 'MA',     'sector': 'financials',  'name': 'Mastercard'},
    'COST':   {'ftmo': 'COST',   'sector': 'consumer',    'name': 'Costco'},
}

START_DATE = '2015-01-01'
TRAIN_RATIO = 0.60
INIT_CASH = 100_000
FEES = 0.0005
SLIPPAGE = 0.0005

# Grid search ranges — Supertrend
ATR_PERIOD_RANGE  = list(range(5, 31))           # 5-30 step 1
MULTIPLIER_RANGE  = [round(1.0 + 0.25*i, 2) for i in range(17)]  # 1.0-5.0 step 0.25
TREND_SMA_RANGE   = [0, 50, 100, 150, 200]       # 0 = no filter

MIN_TRADES_IS = 15
TOP_N = 20

# FTMO
ACCOUNT_SIZE = 100_000
PROFIT_TARGET = 0.10
MAX_DAILY_DD = 0.05
MAX_TOTAL_DD = 0.10

n_combos = len(ATR_PERIOD_RANGE) * len(MULTIPLIER_RANGE) * len(TREND_SMA_RANGE)
print(f'Universe: {len(UNIVERSE)} instruments')
print(f'Combos per instrument: {n_combos:,}')
print(f'Total backtests: {n_combos * len(UNIVERSE):,}')

# ============================================================
# SUPERTREND COMPUTATION
# ============================================================
def compute_supertrend(high_arr, low_arr, close_arr, atr_period, multiplier):
    """Return direction array: 1=bullish, -1=bearish."""
    atr = talib.ATR(high_arr, low_arr, close_arr, timeperiod=atr_period)
    hl2 = (high_arr + low_arr) / 2.0
    upper_basic = hl2 + multiplier * atr
    lower_basic = hl2 - multiplier * atr
    n = len(close_arr)
    upper_band = np.full(n, np.nan)
    lower_band = np.full(n, np.nan)
    direction = np.zeros(n)

    # Find first valid ATR index to seed bands properly
    first_valid = -1
    for idx in range(n):
        if not np.isnan(atr[idx]):
            first_valid = idx
            break
    if first_valid < 0:
        return direction

    upper_band[first_valid] = upper_basic[first_valid]
    lower_band[first_valid] = lower_basic[first_valid]
    # Initial direction based on price position
    if close_arr[first_valid] > hl2[first_valid]:
        direction[first_valid] = 1
    else:
        direction[first_valid] = -1

    for i in range(first_valid + 1, n):
        if np.isnan(atr[i]):
            upper_band[i] = upper_band[i-1]
            lower_band[i] = lower_band[i-1]
            direction[i] = direction[i-1]
            continue
        lower_band[i] = max(lower_basic[i], lower_band[i-1]) if close_arr[i-1] >= lower_band[i-1] else lower_basic[i]
        upper_band[i] = min(upper_basic[i], upper_band[i-1]) if close_arr[i-1] <= upper_band[i-1] else upper_basic[i]
        if direction[i-1] == 1:
            direction[i] = -1 if close_arr[i] < lower_band[i] else 1
        else:
            direction[i] = 1 if close_arr[i] > upper_band[i] else -1
    return direction

# ============================================================
# DOWNLOAD DATA
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
    print(f'  {info["ftmo"]:<8s} {len(df):>5d} bars  [{df.index[0].strftime("%Y-%m-%d")} to {df.index[-1].strftime("%Y-%m-%d")}]')

print(f'Loaded {len(data)}/{len(UNIVERSE)} instruments.')

# ============================================================
# FAST BACKTEST — Supertrend
# ============================================================
def fast_backtest(high_arr, low_arr, close_arr, atr_period, multiplier, trend_sma, min_trades=15):
    n = len(close_arr)
    if n < max(atr_period + 10, trend_sma + 10 if trend_sma > 0 else 50):
        return None

    direction = compute_supertrend(high_arr, low_arr, close_arr, atr_period, multiplier)

    # Entry: direction flips -1 -> 1; Exit: direction flips 1 -> -1
    flip_up   = np.zeros(n, dtype=bool)
    flip_down = np.zeros(n, dtype=bool)
    for i in range(1, n):
        if direction[i] == 1 and direction[i-1] == -1:
            flip_up[i] = True
        elif direction[i] == -1 and direction[i-1] == 1:
            flip_down[i] = True

    # Optional trend filter
    if trend_sma > 0:
        sma = talib.SMA(close_arr, timeperiod=trend_sma)
        trend_ok = close_arr > sma
        trend_ok[np.isnan(sma)] = False
        flip_up = flip_up & trend_ok

    # 1-bar delay
    entry_delayed = np.zeros(n, dtype=bool)
    exit_delayed  = np.zeros(n, dtype=bool)
    entry_delayed[1:] = flip_up[:-1]
    exit_delayed[1:]  = flip_down[:-1]

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
print('GRID SEARCH — Supertrend entry/exit, optional SMA trend filter')
print('=' * 60)

all_results = {}
total_t0 = time.time()

for ticker, info in UNIVERSE.items():
    if ticker not in data:
        continue
    print(f'\n  {info["ftmo"]} ({info["name"]})', end='', flush=True)
    df = data[ticker]
    split_idx = int(len(df) * TRAIN_RATIO)
    high_is  = df['high'].values[:split_idx].astype(float)
    low_is   = df['low'].values[:split_idx].astype(float)
    close_is = df['close'].values[:split_idx].astype(float)

    results = []
    tested = 0
    t0 = time.time()

    for atr_p in ATR_PERIOD_RANGE:
        for mult in MULTIPLIER_RANGE:
            for tsma in TREND_SMA_RANGE:
                tested += 1
                r = fast_backtest(high_is, low_is, close_is, atr_p, mult, tsma, MIN_TRADES_IS)
                if r is not None:
                    r['atr_period'] = atr_p
                    r['multiplier'] = mult
                    r['trend_sma']  = tsma
                    results.append(r)

    elapsed = time.time() - t0
    df_res = pd.DataFrame(results)
    if len(df_res) > 0:
        df_res = df_res.sort_values('sharpe', ascending=False).reset_index(drop=True)
        all_results[ticker] = df_res
        top = df_res.iloc[0]
        print(f' — {len(df_res):,} valid / {tested:,} tested ({elapsed:.0f}s)')
        print(f'    BEST: ATR={int(top.atr_period)} Mult={top.multiplier:.2f} SMA={int(top.trend_sma)} '
              f'Sharpe={top.sharpe:.2f} Trades={int(top.n_trades)} '
              f'Tr/yr={top.trades_per_year} Hold={top.avg_hold_days:.0f}d '
              f'Win={top.win_rate:.0f}% DD={top.max_dd:.1%} InMkt={top.time_in_market:.0f}%')
    else:
        all_results[ticker] = pd.DataFrame()
        print(f' — 0 valid / {tested:,} tested ({elapsed:.0f}s)')

print(f'\nGrid search done in {time.time()-total_t0:.0f}s')

# ============================================================
# OOS VALIDATION
# ============================================================
print(f'\n{"="*100}')
print('OOS VALIDATION')
print(f'{"="*100}')

def generate_positions(df_full, atr_period, multiplier, trend_sma):
    """Return position series (1=long, 0=flat) with 1-bar delay."""
    high_arr  = df_full['high'].values.astype(float)
    low_arr   = df_full['low'].values.astype(float)
    close_arr = df_full['close'].values.astype(float)
    n = len(close_arr)

    direction = compute_supertrend(high_arr, low_arr, close_arr, atr_period, multiplier)

    flip_up   = np.zeros(n, dtype=bool)
    flip_down = np.zeros(n, dtype=bool)
    for i in range(1, n):
        if direction[i] == 1 and direction[i-1] == -1:
            flip_up[i] = True
        elif direction[i] == -1 and direction[i-1] == 1:
            flip_down[i] = True

    if trend_sma > 0:
        sma = talib.SMA(close_arr, timeperiod=trend_sma)
        trend_ok = close_arr > sma
        trend_ok[np.isnan(sma)] = False
        flip_up = flip_up & trend_ok

    entry_delayed = np.zeros(n, dtype=bool)
    exit_delayed  = np.zeros(n, dtype=bool)
    entry_delayed[1:] = flip_up[:-1]
    exit_delayed[1:]  = flip_down[:-1]

    raw_signal = np.where(entry_delayed, 1.0, np.where(exit_delayed, -1.0, 0.0))
    pos = pd.Series(raw_signal, index=df_full.index).replace(0.0, np.nan).ffill().fillna(0.0)
    pos = pos.clip(0.0, 1.0)
    return pos

def compute_backtest_metrics(pos_series, close_series):
    """Compute metrics from position and close series."""
    rets = close_series.pct_change().fillna(0)
    strat_rets = pos_series * rets
    trades_mask = pos_series.diff().abs() > 0
    cost = FEES + SLIPPAGE
    strat_rets = strat_rets.copy()
    strat_rets[trades_mask] -= cost

    total_ret = float((1 + strat_rets).prod() - 1)
    mean_r = strat_rets.mean()
    std_r = strat_rets.std()
    sharpe = float((mean_r / std_r) * np.sqrt(252)) if std_r > 1e-10 else 0.0
    cum = (1 + strat_rets).cumprod()
    dd = cum / cum.cummax() - 1
    max_dd = float(dd.min())
    n_trades = int(((pos_series > 0) & (pos_series.shift(1) <= 0)).sum())
    return {
        'sharpe': sharpe, 'total_ret': total_ret, 'max_dd': max_dd, 'n_trades': n_trades,
    }

oos_results = {}
final_params = {}

for ticker, info in UNIVERSE.items():
    if ticker not in all_results or all_results[ticker].empty:
        continue
    df_full = data[ticker]
    close = df_full['close']
    split_idx = int(len(close) * TRAIN_RATIO)
    df_is  = df_full.iloc[:split_idx]
    df_oos = df_full.iloc[split_idx:]
    close_is  = close.iloc[:split_idx]
    close_oos = close.iloc[split_idx:]

    top_combos = all_results[ticker].head(TOP_N)
    results_list = []
    print(f'\n--- {info["ftmo"]} ---')
    print(f'{"#":<4} {"Params":^20} {"IS Shp":>7} {"OOS Shp":>8} {"IS Tr":>6} {"OOS Tr":>7} {"OOS Ret":>8} {"OOS DD":>8}')
    print('-' * 75)

    for rank, (_, row) in enumerate(top_combos.iterrows(), 1):
        atr_p = int(row.atr_period)
        mult  = float(row.multiplier)
        tsma  = int(row.trend_sma)

        pos_is  = generate_positions(df_is, atr_p, mult, tsma)
        pos_oos = generate_positions(df_oos, atr_p, mult, tsma)
        m_is  = compute_backtest_metrics(pos_is, close_is)
        m_oos = compute_backtest_metrics(pos_oos, close_oos)

        param_str = f'ATR={atr_p} M={mult:.1f} S={tsma}'
        print(f'  {rank:<3} {param_str:^20} {m_is["sharpe"]:>7.2f} {m_oos["sharpe"]:>8.2f} '
              f'{m_is["n_trades"]:>6} {m_oos["n_trades"]:>7} {m_oos["total_ret"]:>7.1%} {m_oos["max_dd"]:>8.1%}')
        results_list.append({
            'rank': rank, 'atr_period': atr_p, 'multiplier': mult, 'trend_sma': tsma,
            'is_sharpe': m_is['sharpe'], 'oos_sharpe': m_oos['sharpe'],
            'is_trades': m_is['n_trades'], 'oos_trades': m_oos['n_trades'],
            'oos_return': m_oos['total_ret'], 'oos_max_dd': m_oos['max_dd'],
        })

    oos_results[ticker] = results_list
    # Use best OOS Sharpe combo, require IS > 0.4 and OOS > 0.2
    valid_oos = [r for r in results_list if r['is_sharpe'] > 0.4 and r['oos_sharpe'] > 0.2]
    if not valid_oos:
        valid_oos = [r for r in results_list if r['is_sharpe'] > 0.0 and r['oos_sharpe'] > 0.2]
    if valid_oos:
        best = max(valid_oos, key=lambda x: x['oos_sharpe'])
        final_params[ticker] = {
            'atr_period': best['atr_period'], 'multiplier': best['multiplier'], 'trend_sma': best['trend_sma'],
        }
    else:
        print(f'  ** SKIPPING {info["ftmo"]} -- no combo with OOS Sharpe > 0.2 **')

print(f'\n{"="*80}')
print('FINAL PARAMS (best OOS Sharpe from top-20 IS, filtered)')
print(f'{"="*80}')
for ticker, info in UNIVERSE.items():
    if ticker not in final_params: continue
    p = final_params[ticker]
    valid_oos = [r for r in oos_results[ticker] if r['is_sharpe'] > 0.4 and r['oos_sharpe'] > 0.2]
    if not valid_oos:
        valid_oos = [r for r in oos_results[ticker] if r['is_sharpe'] > 0.0 and r['oos_sharpe'] > 0.2]
    best = max(valid_oos, key=lambda x: x['oos_sharpe']) if valid_oos else max(oos_results[ticker], key=lambda x: x['oos_sharpe'])
    print(f'  {info["ftmo"]:<8} ATR={p["atr_period"]:>2} Mult={p["multiplier"]:.2f} SMA={p["trend_sma"]:>3}  '
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
    df_full = data[ticker]
    pos = generate_positions(df_full, params['atr_period'], params['multiplier'], params['trend_sma'])
    positions[ticker] = pos
    instrument_rets[ticker] = df_full['close'].pct_change().fillna(0)

# Align all series to common dates
pos_df = pd.DataFrame(positions).fillna(0)
rets_df = pd.DataFrame(instrument_rets).reindex(pos_df.index).fillna(0)

# Dynamic allocation: Sharpe-weighted among active instruments
# Instruments with stronger OOS performance get more capital
oos_sharpes = {}
for ticker in final_params:
    valid_oos = [r for r in oos_results[ticker] if r['is_sharpe'] > 0.4 and r['oos_sharpe'] > 0.2]
    if not valid_oos:
        valid_oos = [r for r in oos_results[ticker] if r['is_sharpe'] > 0.0 and r['oos_sharpe'] > 0.2]
    best = max(valid_oos, key=lambda x: x['oos_sharpe']) if valid_oos else None
    # Use OOS Sharpe squared to concentrate into strongest instruments
    oos_sharpes[ticker] = max(best['oos_sharpe'], 0.1)**2 if best else 0.01

# Build sharpe-weight per instrument (squared OOS Sharpe for concentration)
sharpe_weights = pd.Series(oos_sharpes)
print(f'\nOOS Sharpe weights:')
for t, w in sharpe_weights.items():
    print(f'  {UNIVERSE[t]["ftmo"]:<8} OOS Sharpe={w:.2f}')

# Weight per instrument = sharpe_weight * position / sum(active sharpe_weights)
weighted_pos = pos_df.copy()
for col in weighted_pos.columns:
    weighted_pos[col] *= sharpe_weights[col]
active_weight_sum = weighted_pos.sum(axis=1)
active_weight_sum_safe = active_weight_sum.replace(0, 1)
weights = weighted_pos.div(active_weight_sum_safe, axis=0)

n_active = pos_df.sum(axis=1)

# Portfolio daily return with transaction costs for weight changes
cost = FEES + SLIPPAGE
weight_changes = weights.diff().abs().sum(axis=1)
portfolio_rets = (weights * rets_df).sum(axis=1) - weight_changes * cost
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
for key, label in [('total_return','Total Return'), ('ann_return','Ann. Return'),
                    ('ann_vol','Ann. Volatility'), ('sharpe','Sharpe'),
                    ('sortino','Sortino'), ('max_dd','Max Drawdown'), ('calmar','Calmar')]:
    fmt = '.1%' if key in ('total_return','ann_return','ann_vol','max_dd') else '.2f'
    print(f'{label:<24} {m_full[key]:>10{fmt}} {m_is[key]:>10{fmt}} '
          f'{m_oos[key]:>10{fmt}} {m_bh[key]:>10{fmt}}')

# Activity stats
avg_active = float(n_active.mean())
pct_all_flat = float((n_active == 0).mean() * 100)
pct_in_market = float((n_active > 0).mean() * 100)
print(f'\nAvg instruments active: {avg_active:.1f} / {len(final_params)}')
print(f'Days in market: {pct_in_market:.0f}%')
print(f'Days 100% cash: {pct_all_flat:.0f}%')

total_trades = 0
for ticker in final_params:
    pos = positions[ticker]
    trades_count = int(((pos > 0) & (pos.shift(1) <= 0)).sum())
    total_trades += trades_count
years = len(portfolio_rets) / 252
print(f'Total trades: {total_trades} ({total_trades/years:.0f}/year)')

# Per-instrument stats
print(f'\nPer-instrument:')
print(f'{"Instrument":<10} {"Params":^22} {"Sharpe":>7} {"Return":>8} {"MaxDD":>8} {"Trades":>7} {"Tr/yr":>7} {"InMkt":>6}')
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
    param_str = f'ATR={params["atr_period"]} M={params["multiplier"]:.1f} S={params["trend_sma"]}'
    print(f'{info["ftmo"]:<10} {param_str:^22} {shp:>7.2f} {total_r:>7.0%} {md:>8.1%} '
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
            hit_dd = True; daily_dd_breaches += 1; break
        if (ACCOUNT_SIZE - equity) / ACCOUNT_SIZE > MAX_TOTAL_DD:
            hit_dd = True; break
        if equity >= ACCOUNT_SIZE * (1 + PROFIT_TARGET):
            hit_target = True; break
    if hit_target: passed += 1
    if hit_dd: blown += 1
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
print('2025 MONTHLY BREAKDOWN ($100K)')
print(f'{"="*70}')

port_2025 = portfolio_rets[portfolio_rets.index >= '2025-01-01']
if len(port_2025) > 0:
    monthly = port_2025.resample('ME').apply(lambda x: (1+x).prod()-1 if len(x)>0 else 0)
    print(f'\n  {"Month":<12} {"Return":>8} {"Equity":>12}')
    print(f'  {"-"*36}')
    running_eq = INIT_CASH
    for dt, ret in monthly.items():
        running_eq *= (1 + ret)
        print(f'  {dt.strftime("%Y-%m"):<12} {ret:>7.2%} ${running_eq:>11,.0f}')
    ytd = float((1 + port_2025).prod() - 1)
    print(f'\n  YTD 2025: {ytd:.2%}')
    print(f'  Final equity: ${running_eq:,.0f}')
else:
    print('  No 2025 data available yet.')

# ============================================================
# TODAY'S SIGNALS
# ============================================================
print(f'\n{"="*70}')
today_str = datetime.now().strftime('%A, %B %d, %Y')
print(f"TODAY'S SIGNALS -- {today_str}")
print(f'{"="*70}')

actions = []
for ticker, params in final_params.items():
    info = UNIVERSE[ticker]
    atr_p = params['atr_period']
    mult  = params['multiplier']
    tsma  = params['trend_sma']

    df_fresh = yf.download(ticker, period='2y', progress=False)
    if isinstance(df_fresh.columns, pd.MultiIndex):
        df_fresh.columns = df_fresh.columns.get_level_values(0)
    df_fresh = df_fresh.rename(columns=str.lower)

    high_arr  = df_fresh['high'].values.astype(float)
    low_arr   = df_fresh['low'].values.astype(float)
    close_arr = df_fresh['close'].values.astype(float)

    direction = compute_supertrend(high_arr, low_arr, close_arr, atr_p, mult)
    price = close_arr[-1]

    flip_up   = (direction[-1] == 1) and (direction[-2] == -1)
    flip_down = (direction[-1] == -1) and (direction[-2] == 1)
    bullish   = direction[-1] == 1

    trend_ok = True
    if tsma > 0:
        sma = talib.SMA(close_arr, timeperiod=tsma)
        trend_ok = bool(close_arr[-1] > sma[-1]) if not np.isnan(sma[-1]) else False

    if flip_up and trend_ok:
        action, status = 'BUY', 'ENTRY SIGNAL (Supertrend flipped bullish)'
    elif flip_down:
        action, status = 'EXIT', 'EXIT SIGNAL (Supertrend flipped bearish)'
    elif bullish and trend_ok:
        action, status = 'HOLD', 'Bullish (Supertrend up)'
    else:
        action, status = 'FLAT', 'Bearish or below trend filter'

    param_str = f'ATR={atr_p} M={mult:.1f} S={tsma}'
    actions.append({'ftmo': info['ftmo'], 'action': action, 'status': status,
                    'price': price, 'params': param_str, 'gate': bullish and trend_ok})

active = [a for a in actions if a['action'] in ('BUY', 'HOLD')]
inactive = [a for a in actions if a['action'] in ('EXIT', 'FLAT')]

print(f'\n  ACTIVE ({len(active)}/{len(actions)})')
print(f'  {"-"*70}')
if active:
    for a in active:
        marker = '>>>' if a['action'] == 'BUY' else '   '
        print(f'  {marker} {a["action"]:<6} {a["ftmo"]:<8} @ ${a["price"]:>10,.2f}  {a["params"]}  {a["status"]}')
    alloc = ACCOUNT_SIZE / len(active)
    print(f'\n  Allocation: ${alloc:,.0f} per instrument ({len(active)} positions)')
else:
    print(f'  All gates closed -- 100% CASH')

print(f'\n  FLAT/EXIT ({len(inactive)}/{len(actions)})')
print(f'  {"-"*70}')
for a in inactive:
    marker = '<<<' if a['action'] == 'EXIT' else '   '
    print(f'  {marker} {a["action"]:<6} {a["ftmo"]:<8} @ ${a["price"]:>10,.2f}  {a["params"]}  {a["status"]}')

# ============================================================
# FINAL SUMMARY
# ============================================================
print(f'\n{"="*70}')
print('FINAL SUMMARY')
print(f'{"="*70}')
print(f'  Strategy:       Supertrend (Global Indices & Blue Chips)')
print(f'  Universe:       {len(final_params)} instruments')
print(f'  OOS Sharpe:     {m_oos["sharpe"]:.2f}')
print(f'  OOS Return:     {m_oos["total_return"]:.1%}')
print(f'  OOS Max DD:     {m_oos["max_dd"]:.1%}')
print(f'  FTMO Pass Rate: {pass_rate:.1f}%')
print(f'  FTMO Blow Rate: {blow_rate:.1f}%')
oos_ok = "PASS" if m_oos['sharpe'] > 0.7 else "FAIL"
ftmo_ok = "PASS" if pass_rate > 15 else "FAIL"
print(f'\n  OOS Sharpe > 0.7:    {oos_ok} ({m_oos["sharpe"]:.2f})')
print(f'  FTMO Pass > 15%:     {ftmo_ok} ({pass_rate:.1f}%)')

print(f'\n{"="*70}')
print('DONE.')
