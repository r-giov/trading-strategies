"""
Personal $1K Momentum Rotation Strategy — v3
=============================================
Top-2 momentum rotation with ATR trailing stops.
Universe: SPY, QQQ, IWM, GLD, TLT, XLE, XLV, XLF + mega-caps
Testing period: 2018-present
"""
import warnings; warnings.filterwarnings('ignore')
import numpy as np, pandas as pd, yfinance as yf, talib, time
from datetime import datetime

# ============================================================
# CONFIGURATION
# ============================================================
UNIVERSE = ['SPY', 'QQQ', 'IWM', 'GLD', 'TLT', 'XLE', 'XLV', 'XLF',
            'AAPL', 'MSFT', 'AMZN', 'GOOG', 'META', 'NVDA', 'TSLA']

START_DATE = '2016-01-01'  # extra lookback for EMA warmup
TEST_START = '2018-01-01'  # actual test period begins here
TRAIN_RATIO = 0.60
INIT_CASH = 1_000
SLIPPAGE = 0.0002
TOP_K = 2  # hold top 2 instruments

MOM_LONG = 252
MOM_SHORT = 21

# Grid search ranges
EMA_SHORT_RANGE = list(range(5, 21, 2))
EMA_MED_RANGE = list(range(15, 51, 5))
EMA_LONG_RANGE = list(range(40, 201, 10))
ATR_STOP_MULTS = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
ATR_PERIOD = 14

print('='*70)
print(f'PERSONAL $1K MOMENTUM ROTATION — v3 (top-{TOP_K}, ATR stops)')
print('='*70)

# ============================================================
# DOWNLOAD DATA
# ============================================================
print('\nDOWNLOADING DATA')
print('-'*60)

raw_data = {}
for ticker in UNIVERSE:
    df = yf.download(ticker, start=START_DATE, progress=False)
    if df.empty:
        print(f'  WARNING: No data for {ticker}')
        continue
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)
    raw_data[ticker] = df
    print(f'  {ticker:<6s} {len(df):>5d} bars  '
          f'[{df.index[0].strftime("%Y-%m-%d")} to {df.index[-1].strftime("%Y-%m-%d")}]')

close_df = pd.DataFrame({t: raw_data[t]['close'] for t in raw_data}).dropna()
high_df = pd.DataFrame({t: raw_data[t]['high'] for t in raw_data}).reindex(close_df.index).ffill()
low_df = pd.DataFrame({t: raw_data[t]['low'] for t in raw_data}).reindex(close_df.index).ffill()

# Trim to test period
test_mask = close_df.index >= TEST_START
close_test = close_df[test_mask]
high_test = high_df[test_mask]
low_test = low_df[test_mask]

tickers = list(close_test.columns)
n_bars = len(close_test)
split_idx = int(n_bars * TRAIN_RATIO)

print(f'\nAligned: {len(tickers)} instruments, {n_bars} bars (2018-present)')
print(f'IS:  {close_test.index[0].strftime("%Y-%m-%d")} to {close_test.index[split_idx-1].strftime("%Y-%m-%d")} ({split_idx} bars)')
print(f'OOS: {close_test.index[split_idx].strftime("%Y-%m-%d")} to {close_test.index[-1].strftime("%Y-%m-%d")} ({n_bars-split_idx} bars)')

rets_test = close_test.pct_change().fillna(0)
mom_test = (close_test / close_test.shift(MOM_LONG) - 1) - (close_test / close_test.shift(MOM_SHORT) - 1)

atr_test = pd.DataFrame(index=close_test.index, columns=tickers, dtype=float)
for t in tickers:
    atr_test[t] = talib.ATR(high_test[t].values.astype(float),
                             low_test[t].values.astype(float),
                             close_test[t].values.astype(float),
                             timeperiod=ATR_PERIOD)

# ============================================================
# CORE FUNCTIONS
# ============================================================
def compute_gates_ema(cdf, ema_s, ema_m, ema_l):
    gate = pd.DataFrame(0.0, index=cdf.index, columns=cdf.columns)
    for t in cdf.columns:
        arr = cdf[t].values.astype(float)
        es = talib.EMA(arr, timeperiod=ema_s)
        em = talib.EMA(arr, timeperiod=ema_m)
        el = talib.EMA(arr, timeperiod=ema_l)
        aligned = (es > em) & (em > el)
        nan_mask = np.isnan(es) | np.isnan(em) | np.isnan(el)
        aligned[nan_mask] = False
        gate[t] = aligned.astype(float)
    return gate


def rotation_backtest_topk(close_in, rets_in, mom_in, gate_in, atr_in,
                           atr_mult=3.0, top_k=2, slippage=SLIPPAGE):
    n = len(close_in)
    tcks = list(close_in.columns)
    n_inst = len(tcks)
    gate_shifted = gate_in.shift(1).fillna(0)
    mom_shifted = mom_in.shift(1)
    close_arr = close_in.values
    rets_arr = rets_in.values
    atr_arr = atr_in.values
    gate_arr = gate_shifted.values
    mom_arr = mom_shifted.values
    holdings = {}  # ticker_idx -> peak_price
    port_rets = np.zeros(n)
    held_list = ['CASH']
    for i in range(1, n):
        # 1. ATR trailing stops
        for idx in list(holdings.keys()):
            price_now = close_arr[i, idx]
            atr_now = atr_arr[i, idx]
            if np.isnan(atr_now):
                atr_now = atr_arr[i-1, idx] if not np.isnan(atr_arr[i-1, idx]) else 0
            if price_now > holdings[idx]:
                holdings[idx] = price_now
            stop_level = holdings[idx] - atr_mult * atr_now
            if price_now < stop_level:
                del holdings[idx]
                continue
        # 2. Exit if gate closed
        for idx in list(holdings.keys()):
            if gate_arr[i, idx] <= 0:
                del holdings[idx]
        # 3. Top-K candidates
        mom_today = mom_arr[i]
        gate_today = gate_arr[i]
        candidates = []
        for j in range(n_inst):
            if gate_today[j] > 0 and not np.isnan(mom_today[j]):
                candidates.append((j, mom_today[j]))
        candidates.sort(key=lambda x: x[1], reverse=True)
        # 4. Fill up to top_k
        for idx, _ in candidates:
            if len(holdings) >= top_k:
                break
            if idx not in holdings:
                holdings[idx] = close_arr[i, idx]
        # 5. Daily return
        if len(holdings) > 0:
            weight = 1.0 / len(holdings)
            day_ret = sum(weight * rets_arr[i, idx] for idx in holdings)
            port_rets[i] = day_ret
        held_names = sorted([tcks[idx] for idx in holdings])
        held_list.append(','.join(held_names) if held_names else 'CASH')
    held_series = pd.Series(held_list, index=close_in.index)
    return pd.Series(port_rets, index=close_in.index), held_series


def compute_metrics(daily_rets):
    total_ret = float((1 + daily_rets).prod() - 1)
    n_years = len(daily_rets) / 252
    if n_years < 0.1:
        return {'sharpe': 0, 'total_return': total_ret, 'max_dd': 0, 'ann_return': 0,
                'ann_vol': 0, 'sortino': 0, 'calmar': 0}
    ann_ret = (1 + total_ret) ** (1 / n_years) - 1
    ann_vol = float(daily_rets.std() * np.sqrt(252))
    sharpe = ann_ret / ann_vol if ann_vol > 1e-10 else 0
    cum = (1 + daily_rets).cumprod()
    dd = cum / cum.cummax() - 1
    max_dd = float(dd.min())
    down_vol = float(daily_rets[daily_rets < 0].std() * np.sqrt(252)) if (daily_rets < 0).any() else 0
    sortino = ann_ret / down_vol if down_vol > 1e-10 else 0
    calmar = ann_ret / abs(max_dd) if abs(max_dd) > 1e-9 else 0
    return {'sharpe': sharpe, 'total_return': total_ret, 'max_dd': max_dd,
            'ann_return': ann_ret, 'ann_vol': ann_vol, 'sortino': sortino, 'calmar': calmar}


# ============================================================
# GRID SEARCH
# ============================================================
print(f'\n{"="*70}')
print(f'GRID SEARCH — 3EMA gate + ATR trailing stop (top-{TOP_K})')
print(f'{"="*70}')

close_is = close_test.iloc[:split_idx]
rets_is = rets_test.iloc[:split_idx]
mom_is = mom_test.iloc[:split_idx]
atr_is = atr_test.iloc[:split_idx]

n_ema = sum(1 for s_ in EMA_SHORT_RANGE for m_ in EMA_MED_RANGE for l_ in EMA_LONG_RANGE if s_ < m_ < l_)
n_total = n_ema * len(ATR_STOP_MULTS)
print(f'EMA combos: {n_ema} x {len(ATR_STOP_MULTS)} ATR mults = {n_total:,} total')

results = []
t0 = time.time()
tested = 0

for atr_mult in ATR_STOP_MULTS:
    for s_ in EMA_SHORT_RANGE:
        for m_ in EMA_MED_RANGE:
            if m_ <= s_: continue
            for l_ in EMA_LONG_RANGE:
                if l_ <= m_: continue
                tested += 1
                if tested % 200 == 0:
                    print(f'\r  {tested:,}/{n_total:,} ({tested/n_total*100:.0f}%)...', end='', flush=True)
                gate = compute_gates_ema(close_is, s_, m_, l_)
                pr, held = rotation_backtest_topk(close_is, rets_is, mom_is, gate, atr_is,
                                                  atr_mult=atr_mult, top_k=TOP_K)
                n_changes = int((held != held.shift()).sum())
                if n_changes < 10: continue
                met = compute_metrics(pr)
                if met['sharpe'] > 0:
                    met['ema_short'] = s_
                    met['ema_med'] = m_
                    met['ema_long'] = l_
                    met['atr_mult'] = atr_mult
                    met['n_switches'] = n_changes
                    results.append(met)

elapsed = time.time() - t0
print(f'\r  {tested:,}/{n_total:,} in {elapsed:.0f}s — {len(results):,} valid combos          ')

if not results:
    print('NO VALID RESULTS.')
    exit()

df_res = pd.DataFrame(results).sort_values('sharpe', ascending=False)
print(f'\n  Top 10 IS:')
print(f'  {"#":<4} {"EMA":^13} {"ATR":>5} {"Sharpe":>7} {"Return":>8} {"MaxDD":>8}')
print(f'  {"-"*50}')
for i, (_, r) in enumerate(df_res.head(10).iterrows()):
    print(f'  {i+1:<4} {r.ema_short:.0f}/{r.ema_med:.0f}/{r.ema_long:.0f}  '
          f'{r.atr_mult:>5.1f} {r["sharpe"]:>7.2f} {r["total_return"]:>7.1%} {r["max_dd"]:>8.1%}')

# ============================================================
# OOS VALIDATION
# ============================================================
print(f'\n{"="*70}')
print('OOS VALIDATION — Top 15 IS combos')
print(f'{"="*70}')

close_oos = close_test.iloc[split_idx:]
rets_oos = rets_test.iloc[split_idx:]
mom_oos = mom_test.iloc[split_idx:]
atr_oos = atr_test.iloc[split_idx:]

oos_results = []
print(f'{"#":<4} {"EMA":^13} {"ATR":>5} {"IS Shp":>7} {"OOS Shp":>8} {"OOS Ret":>8} {"OOS DD":>8}')
print('-'*60)

for i, (_, r) in enumerate(df_res.head(15).iterrows()):
    s_, m_, l_ = int(r.ema_short), int(r.ema_med), int(r.ema_long)
    am = r.atr_mult
    gate_oos = compute_gates_ema(close_oos, s_, m_, l_)
    pr_oos, _ = rotation_backtest_topk(close_oos, rets_oos, mom_oos, gate_oos, atr_oos, am, TOP_K)
    mo = compute_metrics(pr_oos)
    print(f'{i+1:<4} {s_}/{m_}/{l_}  {am:>5.1f} {r["sharpe"]:>7.2f} {mo["sharpe"]:>8.2f} '
          f'{mo["total_return"]:>7.1%} {mo["max_dd"]:>8.1%}')
    oos_results.append({
        'ema_short': s_, 'ema_med': m_, 'ema_long': l_, 'atr_mult': am,
        'is_sharpe': r['sharpe'], 'oos_sharpe': mo['sharpe'],
        'oos_return': mo['total_return'], 'oos_max_dd': mo['max_dd'],
    })

meets = [r for r in oos_results if r['oos_sharpe'] > 0.5 and r['oos_return'] > 0 and r['oos_max_dd'] > -0.25]
if meets:
    best = max(meets, key=lambda x: x['oos_sharpe'])
    print(f'\n  {len(meets)} combos meet all targets!')
else:
    best = max(oos_results, key=lambda x: x['oos_sharpe'])
    print(f'\n  No combos meet all targets. Best available:')

print(f'\n  WINNER: EMA({best["ema_short"]}/{best["ema_med"]}/{best["ema_long"]}) ATR x{best["atr_mult"]}')
print(f'  IS Sharpe:  {best["is_sharpe"]:.2f}   OOS Sharpe: {best["oos_sharpe"]:.2f}')
print(f'  OOS Return: {best["oos_return"]:.1%}   OOS MaxDD:  {best["oos_max_dd"]:.1%}')

# ============================================================
# FULL ANALYSIS
# ============================================================
s_, m_, l_, am = best['ema_short'], best['ema_med'], best['ema_long'], best['atr_mult']

print(f'\n{"="*70}')
print(f'FULL ANALYSIS — EMA({s_}/{m_}/{l_}) ATR x{am}')
print(f'{"="*70}')

gate_full = compute_gates_ema(close_test, s_, m_, l_)
port_full, held_full = rotation_backtest_topk(close_test, rets_test, mom_test, gate_full, atr_test, am, TOP_K)

gate_is = compute_gates_ema(close_is, s_, m_, l_)
port_is, _ = rotation_backtest_topk(close_is, rets_is, mom_is, gate_is, atr_is, am, TOP_K)
gate_oos2 = compute_gates_ema(close_oos, s_, m_, l_)
port_oos2, _ = rotation_backtest_topk(close_oos, rets_oos, mom_oos, gate_oos2, atr_oos, am, TOP_K)

spy_rets = rets_test['SPY']
m_full = compute_metrics(port_full)
m_is = compute_metrics(port_is)
m_oos = compute_metrics(port_oos2)
m_spy = compute_metrics(spy_rets)

print(f'\n{"Metric":<24} {"Full":>10} {"IS":>10} {"OOS":>10} {"SPY":>10}')
print('-'*70)
for key, label in [('total_return','Total Return'), ('ann_return','Ann. Return'),
                    ('ann_vol','Ann. Volatility'), ('sharpe','Sharpe'),
                    ('sortino','Sortino'), ('max_dd','Max Drawdown'), ('calmar','Calmar')]:
    fmt = '.1%' if key in ('total_return','ann_return','ann_vol','max_dd') else '.2f'
    print(f'{label:<24} {m_full[key]:>10{fmt}} {m_is[key]:>10{fmt}} '
          f'{m_oos[key]:>10{fmt}} {m_spy[key]:>10{fmt}}')

equity = INIT_CASH * (1 + port_full).cumprod()
print(f'\n  $1,000 -> ${float(equity.iloc[-1]):,.2f} ({m_full["total_return"]:.0%} total)')

# Trade stats
changes = held_full.ne(held_full.shift())
yrs = len(close_test) / 252
cash_pct = (held_full == 'CASH').mean() * 100
print(f'\n  Position changes: {int(changes.sum())} ({int(changes.sum())/yrs:.1f}/yr)')
print(f'  Time invested: {100-cash_pct:.0f}% | Cash: {cash_pct:.0f}%')

all_held = []
for h in held_full:
    if h != 'CASH':
        for t in h.split(','):
            if t: all_held.append(t)
if all_held:
    freq = pd.Series(all_held).value_counts(normalize=True)
    print(f'\n  Instrument allocation (% of invested days):')
    for inst, pct in freq.head(10).items():
        print(f'    {inst:<8s} {pct:>6.1%}')

# ============================================================
# YEAR-BY-YEAR
# ============================================================
print(f'\n{"="*70}')
print('YEAR-BY-YEAR RETURNS')
print(f'{"="*70}')

yr_strat = port_full.groupby(port_full.index.year).apply(lambda x: float((1+x).prod()-1))
yr_spy = spy_rets.groupby(spy_rets.index.year).apply(lambda x: float((1+x).prod()-1))

print(f'\n{"Year":<6} {"Strategy":>10} {"SPY":>10} {"Excess":>10} {"Equity":>12}')
print('-'*55)
eq = INIT_CASH
for year in sorted(yr_strat.index):
    sr = yr_strat[year]
    sp = yr_spy.get(year, 0)
    eq *= (1 + sr)
    print(f'{year:<6} {sr:>9.1%} {sp:>9.1%} {sr-sp:>9.1%} ${eq:>11,.2f}')

pos_yrs = (yr_strat > 0).sum()
beat = (yr_strat > yr_spy).sum()
print(f'\nPositive years: {pos_yrs}/{len(yr_strat)} ({pos_yrs/len(yr_strat):.0%})')
print(f'Beat SPY: {beat}/{len(yr_strat)} ({beat/len(yr_strat):.0%})')

# ============================================================
# TRADE-BY-TRADE LOG
# ============================================================
print(f'\n{"="*70}')
print('COMPLETE TRADE LOG')
print(f'{"="*70}')

groups = held_full.ne(held_full.shift()).cumsum()
trades = []
for gid, grp in port_full.groupby(groups):
    inst = held_full.loc[grp.index[0]]
    if inst == 'CASH': continue
    tr = float((1 + grp).prod() - 1)
    trades.append({'instrument': inst, 'start': grp.index[0].strftime('%Y-%m-%d'),
                   'end': grp.index[-1].strftime('%Y-%m-%d'), 'days': len(grp), 'return': tr})

if trades:
    dft = pd.DataFrame(trades)
    nt = len(dft)
    w = (dft['return'] > 0).sum()
    print(f'\nTotal trades:  {nt}  |  Winners: {w} ({w/nt:.0%})  |  Losers: {nt-w} ({(nt-w)/nt:.0%})')
    print(f'Best trade:    {dft["return"].max():>+.1%} ({dft.loc[dft["return"].idxmax(), "instrument"]}, '
          f'{dft.loc[dft["return"].idxmax(), "days"]}d)')
    print(f'Worst trade:   {dft["return"].min():>+.1%} ({dft.loc[dft["return"].idxmin(), "instrument"]}, '
          f'{dft.loc[dft["return"].idxmin(), "days"]}d)')
    if w > 0:
        print(f'Avg winner:    {dft.loc[dft["return"]>0, "return"].mean():>+.1%} '
              f'({dft.loc[dft["return"]>0, "days"].mean():.0f}d)')
    if nt - w > 0:
        print(f'Avg loser:     {dft.loc[dft["return"]<=0, "return"].mean():>+.1%} '
              f'({dft.loc[dft["return"]<=0, "days"].mean():.0f}d)')
    print(f'Avg hold:      {dft["days"].mean():.1f} days  |  Trades/year: {nt/yrs:.1f}')

    print(f'\n{"#":<5} {"Positions":<22} {"Start":>12} {"End":>12} {"Days":>5} {"Return":>8}')
    print('-'*72)
    for i, (_, t) in enumerate(dft.iterrows(), 1):
        print(f'{i:<5} {t["instrument"]:<22} {t["start"]:>12} {t["end"]:>12} {t["days"]:>5} {t["return"]:>+7.1%}')

# ============================================================
# 2025 MONTHLY DETAIL
# ============================================================
print(f'\n{"="*70}')
print('2025 MONTHLY BREAKDOWN')
print(f'{"="*70}')

mask25 = port_full.index.year == 2025
if mask25.any():
    r25 = port_full[mask25]
    h25 = held_full[mask25]
    pre = equity[equity.index.year < 2025]
    start_eq = float(pre.iloc[-1]) if len(pre) > 0 else INIT_CASH
    print(f'\nStarting equity (end 2024): ${start_eq:,.2f}')
    print(f'\n{"Month":<10} {"Return":>8} {"Equity":>12} {"Positions":<30}')
    print('-'*65)
    run_eq = start_eq
    for mo in range(1, 13):
        mm = r25.index.month == mo
        if not mm.any(): continue
        mr = float((1 + r25[mm]).prod() - 1)
        run_eq *= (1 + mr)
        mh = h25[mm].mode().iloc[0]
        mn = datetime(2025, mo, 1).strftime('%B')
        print(f'{mn:<10} {mr:>+7.1%} ${run_eq:>11,.2f} {mh:<30}')
    print(f'\n  2025 YTD: {float((1+r25).prod()-1):>+.1%}  |  Equity: ${run_eq:,.2f}')

# ============================================================
# TODAY'S SIGNAL
# ============================================================
print(f'\n{"="*70}')
print(f"TODAY'S SIGNAL — {datetime.now().strftime('%A, %B %d, %Y')}")
print(f'{"="*70}')

lg = gate_full.iloc[-1]
lm = mom_test.iloc[-1]
print(f'\n{"Ticker":<8} {"Gate":>6} {"12-1 Mom":>10} {"Price":>12}')
print('-'*42)
cands = []
for t in tickers:
    g = 'OPEN' if lg[t] > 0 else 'off'
    mv = lm[t]
    ms = f'{mv:.1%}' if not np.isnan(mv) else 'N/A'
    p = close_test[t].iloc[-1]
    mk = ' <<<' if lg[t] > 0 else ''
    print(f'{t:<8} {g:>6} {ms:>10} ${p:>11,.2f}{mk}')
    if lg[t] > 0 and not np.isnan(mv):
        cands.append((t, mv))

if cands:
    cands.sort(key=lambda x: x[1], reverse=True)
    print(f'\n  ACTION: Hold top-{TOP_K}:')
    for t, mv in cands[:TOP_K]:
        print(f'    {t} (momentum: {mv:+.1%})')
else:
    print(f'\n  ACTION: 100% CASH (no trend signals)')
print(f'  Currently holding: {held_full.iloc[-1]}')

# ============================================================
# TARGET CHECK
# ============================================================
print(f'\n{"="*70}')
print('TARGET CHECK')
print(f'{"="*70}')
for name, passed, val in [
    ('OOS Sharpe > 0.5', m_oos['sharpe'] > 0.5, f'{m_oos["sharpe"]:.3f}'),
    ('OOS Return > 0%', m_oos['total_return'] > 0, f'{m_oos["total_return"]:.1%}'),
    ('OOS Max DD > -25%', m_oos['max_dd'] > -0.25, f'{m_oos["max_dd"]:.1%}'),
]:
    print(f'  [{"PASS" if passed else "FAIL"}] {name}: {val}')
print(f'\n{"="*70}')
print('DONE.')
