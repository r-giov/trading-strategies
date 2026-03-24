"""
MACD Healthcare & Defensive Portfolio — FTMO Strategy
Dynamic allocation + Monte Carlo + OOS validation
Universe: Healthcare + Consumer Defensive (uncorrelated with tech)
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
    'JNJ':  {'ftmo': 'JNJ',  'sector': 'healthcare', 'name': 'Johnson & Johnson'},
    # 'UNH':  {'ftmo': 'UNH',  'sector': 'healthcare', 'name': 'UnitedHealth'},  # iter1: negative OOS
    'LLY':  {'ftmo': 'LLY',  'sector': 'healthcare', 'name': 'Eli Lilly'},
    # 'PFE':  {'ftmo': 'PFE',  'sector': 'healthcare', 'name': 'Pfizer'},  # iter1: negative OOS
    'MRK':  {'ftmo': 'MRK',  'sector': 'healthcare', 'name': 'Merck'},
    'ABBV': {'ftmo': 'ABBV', 'sector': 'healthcare', 'name': 'AbbVie'},
    # 'PG':   {'ftmo': 'PG',   'sector': 'consumer',   'name': 'Procter & Gamble'},  # iter2: weak OOS
    'WMT':  {'ftmo': 'WMT',  'sector': 'consumer',   'name': 'Walmart'},
}

START_DATE = '2015-01-01'
TRAIN_RATIO = 0.60
INIT_CASH = 100_000
FEES = 0.0005
SLIPPAGE = 0.0005
FREQ = 'D'

# Grid search ranges — MACD params (iteration 3: shorter SMA options for more time in market)
FAST_RANGE   = list(range(5, 21, 2))    # 5,7,9,...,19
SLOW_RANGE   = list(range(20, 61, 3))   # 20,23,26,...,59 (wider for longer holds)
SIGNAL_RANGE = list(range(5, 16, 2))    # 5,7,9,...,15
TREND_SMA_RANGE = [50, 100, 150, 200]

MIN_TRADES_IS = 15
TOP_N = 10

# FTMO
ACCOUNT_SIZE = 100_000
PROFIT_TARGET = 0.10
MAX_DAILY_DD = 0.05
MAX_TOTAL_DD = 0.10

n_valid = sum(1 for f in FAST_RANGE for s in SLOW_RANGE for sig in SIGNAL_RANGE
              for t in TREND_SMA_RANGE if f < s)
print(f'Universe: {len(UNIVERSE)} instruments')
print(f'Valid combos per instrument: {n_valid:,}')
print(f'Total backtests: {n_valid * len(UNIVERSE):,}')

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
    print(f'  {info["ftmo"]:<8s} {len(df):>5d} bars  '
          f'[{df.index[0].strftime("%Y-%m-%d")} to {df.index[-1].strftime("%Y-%m-%d")}]')

print(f'Loaded {len(data)}/{len(UNIVERSE)} instruments.')

# ============================================================
# FAST BACKTEST — MACD crossover + SMA trend filter
# ============================================================
def fast_backtest(close_arr, fast_p, slow_p, signal_p, trend_sma_p, min_trades=25):
    """Backtest MACD crossover with SMA trend filter. 1-bar execution delay."""
    n = len(close_arr)
    if n < max(slow_p, trend_sma_p) + 50:
        return None

    macd_line, signal_line, _ = talib.MACD(close_arr,
                                            fastperiod=fast_p,
                                            slowperiod=slow_p,
                                            signalperiod=signal_p)
    sma_trend = talib.SMA(close_arr, timeperiod=trend_sma_p)

    # Raw signals: MACD crosses above signal AND close > SMA trend
    macd_prev = np.roll(macd_line, 1)
    sig_prev = np.roll(signal_line, 1)

    cross_up   = (macd_prev <= sig_prev) & (macd_line > signal_line)
    cross_down = (macd_prev >= sig_prev) & (macd_line < signal_line)
    trend_ok   = close_arr > sma_trend

    entry_raw = cross_up & trend_ok
    exit_raw  = cross_down

    # Clean up edges and NaNs
    entry_raw[0] = False
    exit_raw[0]  = False
    nan_mask = np.isnan(macd_line) | np.isnan(signal_line) | np.isnan(sma_trend)
    entry_raw[nan_mask] = False
    exit_raw[nan_mask]  = False

    # 1-bar execution delay
    entry_delayed = np.zeros(n, dtype=bool)
    exit_delayed  = np.zeros(n, dtype=bool)
    entry_delayed[1:] = entry_raw[:-1]
    exit_delayed[1:]  = exit_raw[:-1]

    raw_signal = np.where(entry_delayed, 1.0, np.where(exit_delayed, -1.0, 0.0))
    pos = pd.Series(raw_signal).replace(0.0, np.nan).ffill().fillna(0.0).values
    pos = np.clip(pos, 0.0, 1.0)

    n_trades = int(np.sum((pos[1:] > 0) & (pos[:-1] <= 0)))
    if n_trades < min_trades:
        return None

    price_rets = np.diff(close_arr) / close_arr[:-1]
    strat_rets = pos[1:] * price_rets
    # Apply fees/slippage on entry/exit
    trade_costs = np.abs(np.diff(pos)) * (FEES + SLIPPAGE)
    strat_rets[:-1] -= trade_costs[1:]  # costs on position changes

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
print('GRID SEARCH — MACD crossover + SMA trend filter')
print('=' * 60)

all_results = {}
total_t0 = time.time()

for ticker, info in UNIVERSE.items():
    if ticker not in data:
        continue
    print(f'\n  {info["ftmo"]} ({info["name"]})', end='', flush=True)
    close_full = data[ticker]['close'].values.astype(float)
    split_idx = int(len(close_full) * TRAIN_RATIO)
    close_is = close_full[:split_idx]

    results = []
    tested = 0
    t0 = time.time()

    for fast_p in FAST_RANGE:
        for slow_p in SLOW_RANGE:
            if fast_p >= slow_p:
                continue
            for signal_p in SIGNAL_RANGE:
                for trend_sma in TREND_SMA_RANGE:
                    tested += 1
                    r = fast_backtest(close_is, fast_p, slow_p, signal_p, trend_sma, MIN_TRADES_IS)
                    if r is not None:
                        r['fast'] = fast_p
                        r['slow'] = slow_p
                        r['signal'] = signal_p
                        r['trend_sma'] = trend_sma
                        results.append(r)

    elapsed = time.time() - t0
    df_res = pd.DataFrame(results)
    if len(df_res) > 0:
        df_res = df_res.sort_values('sharpe', ascending=False).reset_index(drop=True)
        all_results[ticker] = df_res
        top = df_res.iloc[0]
        print(f' -- {len(df_res):,} valid / {tested:,} tested ({elapsed:.0f}s)')
        print(f'    BEST: MACD({int(top.fast)}/{int(top.slow)}/{int(top.signal)}) SMA({int(top.trend_sma)}) '
              f'Sharpe={top.sharpe:.2f} Trades={int(top.n_trades)} '
              f'Tr/yr={top.trades_per_year} Hold={top.avg_hold_days:.0f}d '
              f'Win={top.win_rate:.0f}% DD={top.max_dd:.1%} InMkt={top.time_in_market:.0f}%')
    else:
        all_results[ticker] = pd.DataFrame()
        print(f' -- 0 valid / {tested:,} tested ({elapsed:.0f}s)')

print(f'\nGrid search done in {time.time()-total_t0:.0f}s')

# ============================================================
# OOS VALIDATION
# ============================================================
print(f'\n{"="*100}')
print('OOS VALIDATION')
print(f'{"="*100}')

def get_position_series(close_series, fast_p, slow_p, signal_p, trend_sma_p):
    """Return binary position series (1=long, 0=flat) for dynamic allocation."""
    close_arr = close_series.values.astype(float)
    macd_line, signal_line, _ = talib.MACD(close_arr,
                                            fastperiod=fast_p,
                                            slowperiod=slow_p,
                                            signalperiod=signal_p)
    sma_trend = talib.SMA(close_arr, timeperiod=trend_sma_p)

    n = len(close_arr)
    macd_prev = np.roll(macd_line, 1)
    sig_prev = np.roll(signal_line, 1)

    cross_up   = (macd_prev <= sig_prev) & (macd_line > signal_line)
    cross_down = (macd_prev >= sig_prev) & (macd_line < signal_line)
    trend_ok   = close_arr > sma_trend

    entry_raw = cross_up & trend_ok
    exit_raw  = cross_down
    entry_raw[0] = False
    exit_raw[0]  = False
    nan_mask = np.isnan(macd_line) | np.isnan(signal_line) | np.isnan(sma_trend)
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

oos_results = {}
final_params = {}

for ticker, info in UNIVERSE.items():
    if ticker not in all_results or all_results[ticker].empty:
        print(f'\n--- {info["ftmo"]} --- SKIPPED (no valid IS combos)')
        continue
    close = data[ticker]['close']
    split_idx = int(len(close) * TRAIN_RATIO)
    close_is  = close.iloc[:split_idx]
    close_oos = close.iloc[split_idx:]

    top_combos = all_results[ticker].head(TOP_N)
    results_list = []

    print(f'\n--- {info["ftmo"]} ---')
    print(f'{"#":<4} {"MACD":^15} {"SMA":>5} {"IS Shp":>7} {"OOS Shp":>8} {"IS Tr":>6} {"OOS Tr":>7} {"OOS Ret":>8} {"OOS DD":>8}')
    print('-' * 80)

    for rank, (_, row) in enumerate(top_combos.iterrows(), 1):
        fp, sp, sigp, tsma = int(row.fast), int(row.slow), int(row.signal), int(row.trend_sma)

        # IS backtest with position series
        pos_is = get_position_series(close_is, fp, sp, sigp, tsma)
        rets_is = close_is.pct_change().fillna(0)
        strat_rets_is = pos_is * rets_is
        is_mean = strat_rets_is.mean()
        is_std = strat_rets_is.std()
        is_sharpe = (is_mean / is_std * np.sqrt(252)) if is_std > 0 else 0
        is_trades = int(((pos_is > 0) & (pos_is.shift(1) <= 0)).sum())

        # OOS backtest
        pos_oos = get_position_series(close_oos, fp, sp, sigp, tsma)
        rets_oos = close_oos.pct_change().fillna(0)
        strat_rets_oos = pos_oos * rets_oos
        oos_mean = strat_rets_oos.mean()
        oos_std = strat_rets_oos.std()
        oos_sharpe = (oos_mean / oos_std * np.sqrt(252)) if oos_std > 0 else 0
        oos_trades = int(((pos_oos > 0) & (pos_oos.shift(1) <= 0)).sum())
        oos_ret = float((1 + strat_rets_oos).prod() - 1)
        oos_cum = (1 + strat_rets_oos).cumprod()
        oos_dd = float((oos_cum / oos_cum.cummax() - 1).min())

        macd_str = f'{fp}/{sp}/{sigp}'
        print(f'  {rank:<3} {macd_str:^15} {tsma:>5} {is_sharpe:>7.2f} {oos_sharpe:>8.2f} '
              f'{is_trades:>6} {oos_trades:>7} {oos_ret:>7.1%} {oos_dd:>8.1%}')

        results_list.append({
            'rank': rank, 'fast': fp, 'slow': sp, 'signal': sigp, 'trend_sma': tsma,
            'is_sharpe': float(is_sharpe), 'oos_sharpe': float(oos_sharpe),
            'is_trades': is_trades, 'oos_trades': oos_trades,
            'oos_return': oos_ret, 'oos_max_dd': oos_dd,
        })

    oos_results[ticker] = results_list
    best = max(results_list, key=lambda x: x['oos_sharpe'])
    final_params[ticker] = {
        'fast': best['fast'], 'slow': best['slow'],
        'signal': best['signal'], 'trend_sma': best['trend_sma'],
    }

print(f'\n{"="*80}')
print('FINAL PARAMS (best OOS Sharpe from top-10 IS)')
print(f'{"="*80}')
for ticker, info in UNIVERSE.items():
    if ticker not in final_params:
        continue
    p = final_params[ticker]
    best = max(oos_results[ticker], key=lambda x: x['oos_sharpe'])
    print(f'  {info["ftmo"]:<8} MACD({p["fast"]}/{p["slow"]}/{p["signal"]}) SMA({p["trend_sma"]})  '
          f'IS={best["is_sharpe"]:.2f}  OOS={best["oos_sharpe"]:.2f}  OOS Trades={best["oos_trades"]}')

# ============================================================
# DYNAMIC PORTFOLIO — 100% capital split among active positions
# ============================================================
print(f'\n{"="*70}')
print('DYNAMIC PORTFOLIO -- Capital concentrated into active gates')
print(f'{"="*70}')

positions = {}
instrument_rets = {}

for ticker, params in final_params.items():
    close = data[ticker]['close']
    pos = get_position_series(close, params['fast'], params['slow'],
                               params['signal'], params['trend_sma'])
    positions[ticker] = pos
    instrument_rets[ticker] = close.pct_change().fillna(0)

# Align all series to common dates
pos_df = pd.DataFrame(positions).fillna(0)
rets_df = pd.DataFrame(instrument_rets).reindex(pos_df.index).fillna(0)

# Dynamic allocation: equal weight among active instruments
n_active = pos_df.sum(axis=1)
n_active_safe = n_active.replace(0, 1)
weights = pos_df.div(n_active_safe, axis=0)

# Portfolio daily return
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

# Total trades
total_trades = 0
for ticker in final_params:
    pos = positions[ticker]
    trades_count = int(((pos > 0) & (pos.shift(1) <= 0)).sum())
    total_trades += trades_count
years = len(portfolio_rets) / 252
print(f'Total trades: {total_trades} ({total_trades/years:.0f}/year)')

# Per-instrument stats
print(f'\nPer-instrument:')
print(f'{"Instrument":<10} {"MACD":^15} {"SMA":>5} {"Sharpe":>7} {"Return":>8} {"MaxDD":>8} {"Trades":>7} {"Tr/yr":>7} {"InMkt":>6}')
print('-' * 85)
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
    macd_str = f'{params["fast"]}/{params["slow"]}/{params["signal"]}'
    print(f'{info["ftmo"]:<10} {macd_str:^15} {params["trend_sma"]:>5} {shp:>7.2f} {total_r:>7.0%} {md:>8.1%} '
          f'{ind_trades:>7} {ind_trades/years:>6.1f} {in_mkt:>5.0f}%')

# Correlations
strat_rets_df = pd.DataFrame({UNIVERSE[t]['ftmo']: positions[t] * rets_df[t] for t in final_params})
print(f'\nStrategy Return Correlations:')
print(strat_rets_df.corr().round(2).to_string())

# ============================================================
# 2025 MONTHLY BREAKDOWN ($100K starting equity)
# ============================================================
print(f'\n{"="*70}')
print('2025 MONTHLY BREAKDOWN ($100K starting equity)')
print(f'{"="*70}')

# Get 2025 returns
mask_2025 = portfolio_rets.index.year == 2025
rets_2025 = portfolio_rets[mask_2025]

if len(rets_2025) > 0:
    equity_2025 = INIT_CASH * (1 + rets_2025).cumprod()
    monthly_2025 = rets_2025.resample('ME').apply(lambda x: (1 + x).prod() - 1)

    print(f'\n{"Month":<12} {"Return":>8} {"Equity":>12} {"Trades":>8}')
    print('-' * 45)

    running_equity = INIT_CASH
    for month_end, ret in monthly_2025.items():
        running_equity *= (1 + ret)
        month_str = month_end.strftime('%Y-%m')
        # Count trades in this month
        month_mask = (portfolio_rets.index.year == month_end.year) & (portfolio_rets.index.month == month_end.month)
        month_trades = 0
        for ticker in final_params:
            pos = positions[ticker]
            pos_month = pos[month_mask]
            month_trades += int(((pos_month > 0) & (pos_month.shift(1) <= 0)).sum())
        print(f'{month_str:<12} {ret:>7.1%} ${running_equity:>10,.0f} {month_trades:>8}')

    total_2025 = float((1 + rets_2025).prod() - 1)
    print(f'\n2025 YTD: {total_2025:.1%}  Final equity: ${running_equity:,.0f}')
else:
    print('No 2025 data available yet.')

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
print(f'  5th-95th:      ${np.percentile(final_equities,5):,.0f} -- ${np.percentile(final_equities,95):,.0f}')

# ============================================================
# TODAY'S SIGNALS
# ============================================================
print(f'\n{"="*70}')
today_str = datetime.now().strftime('%A, %B %d, %Y')
print(f'TODAY\'S SIGNALS -- {today_str}')
print(f'{"="*70}')

actions = []
for ticker, params in final_params.items():
    info = UNIVERSE[ticker]
    fp, sp, sigp, tsma = params['fast'], params['slow'], params['signal'], params['trend_sma']
    df_fresh = yf.download(ticker, period='2y', progress=False)
    if isinstance(df_fresh.columns, pd.MultiIndex):
        df_fresh.columns = df_fresh.columns.get_level_values(0)
    df_fresh = df_fresh.rename(columns=str.lower)
    close_arr = df_fresh['close'].values.astype(float)
    macd_line, signal_line, _ = talib.MACD(close_arr, fastperiod=fp, slowperiod=sp, signalperiod=sigp)
    sma_trend = talib.SMA(close_arr, timeperiod=tsma)
    price = close_arr[-1]

    macd_now, sig_now = macd_line[-1], signal_line[-1]
    macd_prev, sig_prev = macd_line[-2], signal_line[-2]
    sma_now = sma_trend[-1]

    gate_open = (macd_now > sig_now) and (price > sma_now)
    cross_up = (macd_prev <= sig_prev) and (macd_now > sig_now) and (price > sma_now)
    cross_down = (macd_prev >= sig_prev) and (macd_now < sig_now)

    if cross_up:
        action, status = 'BUY', 'ENTRY SIGNAL'
    elif cross_down:
        action, status = 'EXIT', 'EXIT SIGNAL'
    elif gate_open:
        action, status = 'HOLD', f'Trending (MACD:{macd_now:.2f} > Sig:{sig_now:.2f}, P>{sma_now:.0f})'
    else:
        action, status = 'FLAT', 'Gate closed'

    actions.append({'ftmo': info['ftmo'], 'action': action, 'status': status,
                    'price': price, 'params': f'MACD({fp}/{sp}/{sigp}) SMA({tsma})', 'gate': gate_open})

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
    print(f'  All gates closed -- 100% CASH')

print(f'\n  FLAT/EXIT ({len(inactive)}/{len(actions)})')
print(f'  {"-"*75}')
for a in inactive:
    m = '<<<' if a['action'] == 'EXIT' else '   '
    print(f'  {m} {a["action"]:<6} {a["ftmo"]:<8} @ ${a["price"]:>10,.2f}  {a["params"]}  {a["status"]}')

# ============================================================
# FINAL SUMMARY
# ============================================================
print(f'\n{"="*70}')
print('FINAL SUMMARY')
print(f'{"="*70}')
print(f'  Strategy:       MACD Healthcare & Defensive Portfolio')
print(f'  Universe:       {len(final_params)} instruments ({", ".join(UNIVERSE[t]["ftmo"] for t in final_params)})')
print(f'  OOS Sharpe:     {m_oos["sharpe"]:.2f}')
print(f'  OOS Return:     {m_oos["total_return"]:.1%}')
print(f'  OOS Max DD:     {m_oos["max_dd"]:.1%}')
print(f'  FTMO Pass Rate: {pass_rate:.1f}%')
print(f'  FTMO Blow Rate: {blow_rate:.1f}%')
target_met = m_oos['sharpe'] > 0.7 and pass_rate > 15
print(f'  Targets Met:    {"YES" if target_met else "NO"} (OOS Sharpe > 0.7: {m_oos["sharpe"]:.2f}, FTMO Pass > 15%: {pass_rate:.1f}%)')
print(f'\n{"="*70}')
print('DONE.')
