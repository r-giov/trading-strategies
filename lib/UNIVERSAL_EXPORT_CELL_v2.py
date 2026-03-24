# ════════════════════════════════════════════════════════════════════
# UNIVERSAL STRATEGY EXPORT — Data Files + Professional PDF Tearsheet
# ════════════════════════════════════════════════════════════════════
# USAGE: Set STRATEGY_NAME and PARAM_COLS before exec'ing this file.
#
#   STRATEGY_NAME = "MACD_Crossover"
#   PARAM_COLS = ["fast_period", "slow_period", "signal_period"]
#   exec(open(os.path.join('lib', 'UNIVERSAL_EXPORT_CELL_v2.py'), encoding='utf-8').read())
#
# Expected notebook variables: TICKER, stock_data (or df), results_df
#   (or grid_search_results or grid_results)
# ════════════════════════════════════════════════════════════════════

import os, sys, json, datetime, hashlib, platform, shutil
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch, Rectangle

# ═══ CONFIG — use notebook values if set, else defaults ═══
try: STRATEGY_NAME
except NameError: STRATEGY_NAME = "UNKNOWN_STRATEGY"
try: PARAM_COLS
except NameError: PARAM_COLS = []
try: NOTES
except NameError: NOTES = ""
try: INIT_CASH
except NameError: INIT_CASH = 100_000
try: FEES
except NameError: FEES = 0.0005
try: SLIPPAGE
except NameError: SLIPPAGE = 0.0005
try: FREQ
except NameError: FREQ = 'D'

# ── Google Drive mount ──
EXPORT_DIR = "./strategy_exports"
IN_COLAB = 'google.colab' in sys.modules
try:
    from google.colab import drive
    if not os.path.exists('/content/drive'):
        drive.mount('/content/drive')
    EXPORT_DIR = "/content/drive/MyDrive/strategy_exports"
    IN_COLAB = True
    print("[OK] Google Drive mounted")
except:
    print("[i] Local mode - exports to ./strategy_exports")

RUN_TIMESTAMP = datetime.datetime.now()
RUN_ID = RUN_TIMESTAMP.strftime("%Y%m%d_%H%M%S")

# ── Variable compatibility ──
# Accept results_df (DataFrame) or grid_search_results / grid_results (list)
try: results_df
except NameError:
    try: results_df = pd.DataFrame(grid_search_results)
    except NameError:
        try: results_df = pd.DataFrame(grid_results)
        except NameError: raise RuntimeError("No grid results. Expected: results_df, grid_search_results, or grid_results")
if not isinstance(results_df, pd.DataFrame):
    results_df = pd.DataFrame(results_df)

# Accept stock_data (DataFrame) or df
try: stock_data
except NameError:
    try: stock_data = df
    except NameError: pass  # Will fail later with clear error

# ── Folder structure ──
STRAT_DIR   = os.path.join(EXPORT_DIR, STRATEGY_NAME, TICKER)
LATEST_DIR  = os.path.join(STRAT_DIR, "latest")
ARCHIVE_DIR = os.path.join(STRAT_DIR, "archive")
os.makedirs(LATEST_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)

# ════════════════════════════════════════════════════════════════
# Signal function — auto-detects strategy type
# ════════════════════════════════════════════════════════════════
def _compute_signals(price_s, params, high_s=None, low_s=None):
    idx = price_s.index; vals = price_s.values.astype(float)
    h_v = high_s.values.astype(float) if high_s is not None else vals
    l_v = low_s.values.astype(float) if low_s is not None else vals

    if STRATEGY_NAME.startswith("MACD"):
        ml, sl, _ = talib.MACD(vals, fastperiod=params['fast_period'], slowperiod=params['slow_period'], signalperiod=params['signal_period'])
        ms, ss = pd.Series(ml, index=idx), pd.Series(sl, index=idx)
        e_raw = (ms.shift(1) <= ss.shift(1)) & (ms > ss)
        x_raw = (ms.shift(1) >= ss.shift(1)) & (ms < ss)

    elif STRATEGY_NAME.startswith("RSI"):
        rsi_s = pd.Series(talib.RSI(vals, timeperiod=params['rsi_len']), index=idx)
        e_raw = (rsi_s.shift(1) <= params['oversold']) & (rsi_s > params['oversold'])
        x_raw = (rsi_s.shift(1) <= params['overbought']) & (rsi_s > params['overbought'])

    elif STRATEGY_NAME == "EMA_HL_Channel":
        close_s = pd.Series(vals, index=idx)
        ema_h = pd.Series(talib.EMA(h_v, timeperiod=params['channel']), index=idx)
        ema_l = pd.Series(talib.EMA(l_v, timeperiod=params['channel']), index=idx)
        ema_t = pd.Series(talib.EMA(vals, timeperiod=params['trend']), index=idx)
        bullish = (close_s > ema_t) & (close_s > ema_h) & (close_s > ema_l)
        bearish = (close_s < ema_t) | (close_s < ema_l)
        e_raw = bullish & (~bullish.shift(1).fillna(False))
        x_raw = bearish & (~bearish.shift(1).fillna(False))

    elif STRATEGY_NAME.startswith("Supertrend"):
        atr = pd.Series(talib.ATR(h_v, l_v, vals, timeperiod=params['atr_period']), index=idx)
        hl2 = (pd.Series(h_v, index=idx) + pd.Series(l_v, index=idx)) / 2
        mult = params['multiplier']
        upper_band = hl2 + mult * atr
        lower_band = hl2 - mult * atr
        close_s = pd.Series(vals, index=idx)
        st = pd.Series(np.nan, index=idx)
        direction = pd.Series(1, index=idx)
        ap = params['atr_period']
        for ii in range(ap, len(vals)):
            if ii > ap:
                if not (lower_band.iloc[ii] > lower_band.iloc[ii-1] or close_s.iloc[ii-1] < lower_band.iloc[ii-1]):
                    lower_band.iloc[ii] = lower_band.iloc[ii-1]
                if not (upper_band.iloc[ii] < upper_band.iloc[ii-1] or close_s.iloc[ii-1] > upper_band.iloc[ii-1]):
                    upper_band.iloc[ii] = upper_band.iloc[ii-1]
            if ii > ap:
                if st.iloc[ii-1] == upper_band.iloc[ii-1]:
                    direction.iloc[ii] = -1 if close_s.iloc[ii] <= upper_band.iloc[ii] else 1
                else:
                    direction.iloc[ii] = 1 if close_s.iloc[ii] >= lower_band.iloc[ii] else -1
            st.iloc[ii] = lower_band.iloc[ii] if direction.iloc[ii] == 1 else upper_band.iloc[ii]
        e_raw = (direction == 1) & (direction.shift(1) == -1)
        x_raw = (direction == -1) & (direction.shift(1) == 1)

    elif STRATEGY_NAME.startswith("Schaff"):
        fast_ema = talib.EMA(vals, timeperiod=params['fast'])
        slow_ema = talib.EMA(vals, timeperiod=params['slow'])
        macd_line = fast_ema - slow_ema
        cyc = params['cycle']
        macd_low = pd.Series(macd_line).rolling(cyc).min()
        macd_high = pd.Series(macd_line).rolling(cyc).max()
        stoch1 = np.where((macd_high - macd_low) > 0, (macd_line - macd_low) / (macd_high - macd_low) * 100, 50.0)
        pf1 = talib.EMA(pd.Series(stoch1, index=idx).values.astype(float), timeperiod=3)
        pf1_s = pd.Series(pf1, index=idx)
        pf1_low = pf1_s.rolling(cyc).min()
        pf1_high = pf1_s.rolling(cyc).max()
        stoch2 = np.where((pf1_high - pf1_low) > 0, (pf1_s - pf1_low) / (pf1_high - pf1_low) * 100, 50.0)
        stc = pd.Series(talib.EMA(stoch2.astype(float), timeperiod=3), index=idx).clip(0, 100)
        oversold = params.get('oversold', 25)
        overbought = params.get('overbought', 75)
        e_raw = (stc > oversold) & (stc.shift(1) <= oversold)
        x_raw = (stc < overbought) & (stc.shift(1) >= overbought)

    elif STRATEGY_NAME.startswith("EMA"):
        fv = pd.Series(talib.EMA(vals, timeperiod=params['fast_ema']), index=idx)
        sv = pd.Series(talib.EMA(vals, timeperiod=params['slow_ema']), index=idx)
        tf_period = params.get('trend_filter', params.get('trend_period', 200))
        tv = pd.Series(talib.SMA(vals, timeperiod=tf_period), index=idx)
        cs = pd.Series(vals, index=idx)
        e_raw = ((fv.shift(1) <= sv.shift(1)) & (fv > sv) & (cs > tv))
        x_raw = ((fv.shift(1) >= sv.shift(1)) & (fv < sv))

    elif STRATEGY_NAME.startswith("Triple") or STRATEGY_NAME.startswith("TEMA"):
        e1 = pd.Series(vbt.MA.run(price_s, params['ema1_period'], ewm=True).ma.values.flatten(), index=idx)
        e2 = pd.Series(vbt.MA.run(price_s, params['ema2_period'], ewm=True).ma.values.flatten(), index=idx)
        e3 = pd.Series(vbt.MA.run(price_s, params['ema3_period'], ewm=True).ma.values.flatten(), index=idx)
        e_raw = (e1.vbt.crossed_above(e2) | e1.vbt.crossed_above(e3) | e2.vbt.crossed_above(e3))
        x_raw = (e1.vbt.crossed_below(e2) | e1.vbt.crossed_below(e3) | e2.vbt.crossed_below(e3))

    elif STRATEGY_NAME.startswith("Donchian") or STRATEGY_NAME.startswith("DC"):
        uc = pd.Series(talib.MAX(h_v, timeperiod=params['entry_period']), index=idx).shift(1)
        lc = pd.Series(talib.MIN(l_v, timeperiod=params['exit_period']), index=idx).shift(1)
        tf = pd.Series(talib.SMA(vals, timeperiod=params['filter_period']), index=idx).shift(1)
        cs = pd.Series(vals, index=idx)
        e_raw = (cs > uc) & (cs > tf); x_raw = (cs < lc)

    elif STRATEGY_NAME.startswith("Momentum"):
        mom = pd.Series(talib.MOM(vals, timeperiod=params['mom_period']), index=idx)
        trend = pd.Series(talib.SMA(vals, timeperiod=params['trend_period']), index=idx)
        price = pd.Series(vals, index=idx)
        e_raw = (mom.shift(1) <= 0) & (mom > 0) & (price > trend)
        adx_t = params.get('adx_threshold', 0)
        if adx_t and adx_t > 0:
            adx = pd.Series(talib.ADX(h_v, l_v, vals, timeperiod=14), index=idx)
            e_raw = e_raw & (adx > adx_t)
        x_raw = (mom.shift(1) >= 0) & (mom < 0)

    elif STRATEGY_NAME.startswith("Stochastic"):
        slowk_vals, _ = talib.STOCH(h_v, l_v, vals,
                                     fastk_period=params.get('fastk', 5),
                                     slowk_period=params.get('slowk', 3),
                                     slowd_period=params.get('slowd', 5))
        stoch_k = pd.Series(slowk_vals, index=idx)
        trend = pd.Series(talib.SMA(vals, timeperiod=params.get('trend_period', 100)), index=idx)
        price = pd.Series(vals, index=idx)
        os_t = params.get('oversold', 30); ob_t = params.get('overbought', 80)
        e_raw = (stoch_k.shift(1) <= os_t) & (stoch_k > os_t) & (price > trend)
        x_raw = (stoch_k.shift(1) <= ob_t) & (stoch_k > ob_t)

    elif STRATEGY_NAME.startswith("Bollinger"):
        bb_period = params.get('bb_period', 20)
        bb_std = float(params.get('bb_std', 2))
        upper, middle, lower = talib.BBANDS(vals, timeperiod=bb_period, nbdevup=bb_std, nbdevdn=bb_std)
        upper_s = pd.Series(upper, index=idx); lower_s = pd.Series(lower, index=idx); middle_s = pd.Series(middle, index=idx)
        price = pd.Series(vals, index=idx)
        e_raw = (price.shift(1) >= lower_s.shift(1)) & (price < lower_s)
        exit_type = params.get('exit_type', 'middle')
        if exit_type in ('upper', 'band'):
            x_raw = (price.shift(1) <= upper_s.shift(1)) & (price > upper_s)
        else:
            x_raw = (price.shift(1) <= middle_s.shift(1)) & (price > middle_s)

    elif STRATEGY_NAME.startswith("ATR") or STRATEGY_NAME.startswith("Volatility"):
        atr = pd.Series(talib.ATR(h_v, l_v, vals, timeperiod=params.get('atr_period', 14)), index=idx)
        atr_ma = atr.rolling(params.get('atr_ma', 20)).mean()
        price = pd.Series(vals, index=idx)
        trend = pd.Series(talib.SMA(vals, timeperiod=params.get('trend_period', 50)), index=idx)
        mult = params.get('breakout_mult', 1.5)
        e_raw = (atr > atr_ma * mult) & (price > trend)
        x_raw = (atr < atr_ma) | (price < trend)

    else:
        raise ValueError(f"Unknown strategy: {STRATEGY_NAME}. Define _compute_signals before exec'ing.")

    entries = pd.Series(np.where(e_raw.shift(1).isna(), False, e_raw.shift(1)), index=idx, dtype=bool)
    exits = pd.Series(np.where(x_raw.shift(1).isna(), False, x_raw.shift(1)), index=idx, dtype=bool)
    return entries, exits

# ════════════════════════════════════════════════════════════════
# ATR stops helper + portfolio builder
# ════════════════════════════════════════════════════════════════
def _compute_atr_stops_export(close_s, high_s, low_s, sl_mult=None, tp_mult=None, atr_period=14):
    if high_s is None or low_s is None or (sl_mult is None and tp_mult is None):
        return None, None
    c = close_s.values.astype(float)
    h = high_s.values.astype(float)
    l = low_s.values.astype(float)
    atr = pd.Series(talib.ATR(h, l, c, timeperiod=atr_period), index=close_s.index)
    sl_stop = (atr * sl_mult / close_s).fillna(0.02) if sl_mult else None
    tp_stop = (atr * tp_mult / close_s).fillna(0.04) if tp_mult else None
    return sl_stop, tp_stop

def _make_pf(close_s, ent, ext, h_s=None, l_s=None, params=None):
    """Build portfolio with optional ATR stops."""
    kw = dict(init_cash=INIT_CASH, fees=FEES, slippage=SLIPPAGE, freq=FREQ)
    p = params if params is not None else best_params
    sl_m = p.get('sl_atr_mult'); tp_m = p.get('tp_atr_mult')
    if (sl_m or tp_m) and h_s is not None:
        sl, tp = _compute_atr_stops_export(close_s, h_s, l_s, sl_mult=sl_m, tp_mult=tp_m)
        if sl is not None: kw['sl_stop'] = sl
        if tp is not None: kw['tp_stop'] = tp
    return vbt.Portfolio.from_signals(close=close_s, entries=ent, exits=ext, **kw)

# ════════════════════════════════════════════════════════════════
# Build portfolios
# ════════════════════════════════════════════════════════════════
best = results_df.loc[results_df['sharpe_ratio'].idxmax()]
best_params = {}
for col in PARAM_COLS:
    val = best[col]
    try:
        fv = float(val)
        best_params[col] = int(fv) if fv == int(fv) else fv
    except (ValueError, TypeError):
        best_params[col] = val
param_str = ", ".join([f"{k}={v}" for k, v in best_params.items()])

if isinstance(stock_data.columns, pd.MultiIndex):
    full_close = stock_data[('Close', TICKER)].astype(float).squeeze()
    high_s = stock_data[('High', TICKER)].astype(float).squeeze() if ('High', TICKER) in stock_data.columns else None
    low_s = stock_data[('Low', TICKER)].astype(float).squeeze() if ('Low', TICKER) in stock_data.columns else None
else:
    full_close = stock_data['Close'].astype(float).squeeze()
    high_s = stock_data['High'].astype(float).squeeze() if 'High' in stock_data.columns else None
    low_s = stock_data['Low'].astype(float).squeeze() if 'Low' in stock_data.columns else None
full_close.name = 'price'

split_idx = int(len(full_close) * 0.60)
train_close = full_close.iloc[:split_idx].copy()
val_close = full_close.iloc[split_idx:].copy()

_h_is = high_s.iloc[:split_idx] if high_s is not None else None
_h_oos = high_s.iloc[split_idx:] if high_s is not None else None
_l_is = low_s.iloc[:split_idx] if low_s is not None else None
_l_oos = low_s.iloc[split_idx:] if low_s is not None else None

# Full sample
e_full, x_full = _compute_signals(full_close, best_params, high_s, low_s)
pf_full = _make_pf(full_close, e_full, x_full, high_s, low_s)
# IS
e_is, x_is = _compute_signals(train_close, best_params, _h_is, _l_is)
pf_is = _make_pf(train_close, e_is, x_is, _h_is, _l_is)
# OOS
e_oos, x_oos = _compute_signals(val_close, best_params, _h_oos, _l_oos)
pf_oos = _make_pf(val_close, e_oos, x_oos, _h_oos, _l_oos)
# Buy & Hold
bh_e = pd.Series(False, index=full_close.index, dtype=bool); bh_e.iloc[0] = True
bh_x = pd.Series(False, index=full_close.index, dtype=bool)
pf_bh = vbt.Portfolio.from_signals(close=full_close, entries=bh_e, exits=bh_x,
                                    init_cash=INIT_CASH, fees=FEES, slippage=SLIPPAGE, freq=FREQ)
# B&H IS / OOS
bh_e_is = pd.Series(False, index=train_close.index, dtype=bool); bh_e_is.iloc[0] = True
bh_x_is = pd.Series(False, index=train_close.index, dtype=bool)
pf_bh_is = vbt.Portfolio.from_signals(close=train_close, entries=bh_e_is, exits=bh_x_is,
                                       init_cash=INIT_CASH, fees=FEES, slippage=SLIPPAGE, freq=FREQ)
bh_e_oos = pd.Series(False, index=val_close.index, dtype=bool); bh_e_oos.iloc[0] = True
bh_x_oos = pd.Series(False, index=val_close.index, dtype=bool)
pf_bh_oos = vbt.Portfolio.from_signals(close=val_close, entries=bh_e_oos, exits=bh_x_oos,
                                        init_cash=INIT_CASH, fees=FEES, slippage=SLIPPAGE, freq=FREQ)

# ════════════════════════════════════════════════════════════════
# Extract metrics — ALL columns filled for FULL / IS / OOS / B&H
# ════════════════════════════════════════════════════════════════
def safe(fn, default=None):
    try:
        v = float(fn())
        return v if not np.isnan(v) else default
    except:
        return default

def _extract_metrics(pf, label=""):
    """Extract a full metrics dict from a portfolio object."""
    trades_obj = pf.trades
    n_trades = len(trades_obj)
    tr = np.asarray(trades_obj.returns.values if hasattr(trades_obj.returns, 'values') else trades_obj.returns).ravel() if n_trades > 0 else np.array([])
    pnl_arr = np.asarray(trades_obj.pnl.values if hasattr(trades_obj.pnl, 'values') else trades_obj.pnl).ravel() if n_trades > 0 else np.array([])
    pos, neg = tr[tr > 0], tr[tr < 0]
    idx = pf.wrapper.index
    years = max((idx[-1] - idx[0]).days / 365.25, 1e-9) if len(idx) > 1 else 1e-9

    ann_ret = safe(lambda: pf.annualized_return(freq=FREQ))
    max_dd = safe(pf.max_drawdown)
    calmar = ann_ret / abs(max_dd) if ann_ret is not None and max_dd is not None and abs(max_dd) > 1e-9 else None

    return {
        'total_return': safe(pf.total_return),
        'ann_return': ann_ret,
        'sharpe': safe(lambda: pf.sharpe_ratio(freq=FREQ)),
        'sortino': safe(lambda: pf.sortino_ratio(freq=FREQ)),
        'max_dd': max_dd,
        'volatility': safe(lambda: pf.annualized_volatility(freq=FREQ)),
        'calmar': calmar,
        'trades': n_trades,
        'trades_yr': n_trades / years if years > 0 else 0,
        'win_rate': float(len(pos) / len(tr) * 100) if len(tr) > 0 else None,
        'pf': float(pos.sum() / abs(neg.sum())) if len(neg) > 0 and abs(neg.sum()) > 0 else None,
        'expectancy': float(tr.mean()) if len(tr) > 0 else None,
        'avg_win': float(pos.mean()) if len(pos) > 0 else None,
        'avg_loss': float(neg.mean()) if len(neg) > 0 else None,
        'largest_win': float(pos.max()) if len(pos) > 0 else None,
        'largest_loss': float(neg.min()) if len(neg) > 0 else None,
        'payoff': float(abs(pos.mean() / neg.mean())) if len(pos) > 0 and len(neg) > 0 else None,
        '_trades_arr': tr,
        '_pnl_arr': pnl_arr,
    }

M_full = _extract_metrics(pf_full)
M_is = _extract_metrics(pf_is)
M_oos = _extract_metrics(pf_oos)
M_bh = _extract_metrics(pf_bh)
M_bh_is = _extract_metrics(pf_bh_is)
M_bh_oos = _extract_metrics(pf_bh_oos)

# Shorthand for legacy references
M = M_full
years_full = max((full_close.index[-1] - full_close.index[0]).days / 365.25, 1e-9)
daily_rets = pf_full.returns()
tr = M_full['_trades_arr']
pnl = M_full['_pnl_arr']

# ════════════════════════════════════════════════════════════════
# 1. SAVE STRUCTURED DATA FILES
# ════════════════════════════════════════════════════════════════
_freq_label = "1h" if FREQ == 'h' else "1d"
export_json = {
    "metadata": {
        "run_id": RUN_ID, "export_timestamp": RUN_TIMESTAMP.isoformat(),
        "export_date_human": RUN_TIMESTAMP.strftime("%B %d, %Y at %I:%M %p"),
        "strategy_name": STRATEGY_NAME, "strategy_family": STRATEGY_NAME.split("_")[0],
        "ticker": TICKER,
        "instrument_type": ("crypto" if "-USD" in TICKER and TICKER.replace("-USD","").isalpha()
                           else "forex" if "/" in TICKER or (len(TICKER) == 6 and TICKER.isalpha())
                           else "equity/etf"),
        "data_source": "yfinance", "data_interval": _freq_label, "currency": "USD",
        "start_date": str(full_close.index[0].date() if hasattr(full_close.index[0], 'date') else full_close.index[0]),
        "end_date": str(full_close.index[-1].date() if hasattr(full_close.index[-1], 'date') else full_close.index[-1]),
        "total_bars": len(full_close), "total_years": round(years_full, 2),
        "train_start": str(train_close.index[0].date() if hasattr(train_close.index[0], 'date') else train_close.index[0]),
        "train_end": str(train_close.index[-1].date() if hasattr(train_close.index[-1], 'date') else train_close.index[-1]),
        "train_bars": len(train_close),
        "val_start": str(val_close.index[0].date() if hasattr(val_close.index[0], 'date') else val_close.index[0]),
        "val_end": str(val_close.index[-1].date() if hasattr(val_close.index[-1], 'date') else val_close.index[-1]),
        "val_bars": len(val_close), "train_ratio": 0.60,
        "init_cash": INIT_CASH, "fees_pct": FEES, "slippage_pct": SLIPPAGE, "frequency": FREQ,
        "first_close": round(float(full_close.iloc[0]), 4), "last_close": round(float(full_close.iloc[-1]), 4),
        "python_version": sys.version.split()[0], "environment": "colab_pro" if IN_COLAB else "local",
        "grid_combos_tested": len(results_df), "param_columns": PARAM_COLS, "notes": NOTES,
    },
    "best_params": best_params,
    "metrics_full_sample": {k: v for k, v in M_full.items() if not k.startswith('_')},
    "metrics_in_sample": {k: v for k, v in M_is.items() if not k.startswith('_')},
    "metrics_out_of_sample": {k: v for k, v in M_oos.items() if not k.startswith('_')},
    "metrics_buy_hold": {k: v for k, v in M_bh.items() if not k.startswith('_')},
    "grid_search_summary": {
        "top5": results_df.nlargest(5, 'sharpe_ratio')[PARAM_COLS + ['sharpe_ratio','total_return','max_drawdown']].to_dict('records'),
    }
}

# Save JSON
with open(os.path.join(LATEST_DIR, "summary.json"), 'w') as f:
    json.dump(export_json, f, indent=2, default=str)
with open(os.path.join(ARCHIVE_DIR, f"{RUN_ID}_summary.json"), 'w') as f:
    json.dump(export_json, f, indent=2, default=str)
print(f"  [OK] summary.json")

# Save CSVs
_date_col = full_close.index.strftime('%Y-%m-%d %H:%M') if FREQ == 'h' else full_close.index.strftime('%Y-%m-%d')
pd.DataFrame({'date': _date_col, 'strategy_return': daily_rets.values,
              'close': full_close.values, 'portfolio_value': pf_full.value().values
}).to_csv(os.path.join(LATEST_DIR, "daily_returns.csv"), index=False)
print(f"  [OK] daily_returns.csv")

if len(tr) > 0:
    pd.DataFrame({'trade_num': range(1, len(tr)+1), 'return_pct': tr*100, 'pnl_usd': pnl,
                  'cumulative_pnl': np.cumsum(pnl), 'is_winner': tr > 0
    }).to_csv(os.path.join(LATEST_DIR, "trades.csv"), index=False)
    print(f"  [OK] trades.csv ({len(tr)} trades)")

results_df.to_csv(os.path.join(LATEST_DIR, "grid_results.csv"), index=False)
print(f"  [OK] grid_results.csv")

# Run log
log_path = os.path.join(EXPORT_DIR, "run_log.csv")
log_entry = pd.DataFrame([{
    "run_id": RUN_ID, "timestamp": RUN_TIMESTAMP.isoformat(), "strategy": STRATEGY_NAME,
    "ticker": TICKER, "best_params": str(best_params),
    "sharpe_full": round(M['sharpe'] or 0, 4), "sharpe_is": round(M_is['sharpe'] or 0, 4),
    "sharpe_oos": round(M_oos['sharpe'] or 0, 4), "total_return": round(M['total_return'] or 0, 4),
    "max_drawdown": round(M['max_dd'] or 0, 4), "total_trades": M['trades'],
    "win_rate": round(M['win_rate'] or 0, 1), "profit_factor": round(M['pf'] or 0, 2) if M['pf'] else None,
    "notes": NOTES, "export_path": STRAT_DIR,
}])
if os.path.exists(log_path):
    log_combined = pd.concat([pd.read_csv(log_path), log_entry], ignore_index=True)
else:
    log_combined = log_entry
log_combined.to_csv(log_path, index=False)
print(f"  [OK] run_log.csv ({len(log_combined)} runs)")

# ════════════════════════════════════════════════════════════════
# 2. GENERATE PROFESSIONAL PDF TEARSHEET
# ════════════════════════════════════════════════════════════════
_ticker_clean = TICKER.replace("=", "").replace("-", "").replace("/", "")
_date_str = RUN_TIMESTAMP.strftime("%Y%m%d")
pdf_filename = f"{STRATEGY_NAME}_{_ticker_clean}_{_date_str}_tearsheet.pdf"
pdf_path = os.path.join(LATEST_DIR, pdf_filename)
pdf_archive = os.path.join(ARCHIVE_DIR, f"{RUN_ID}_{STRATEGY_NAME}_{_ticker_clean}_tearsheet.pdf")

# ── Formatting helpers ──
def fmt(v, d=2):
    if v is None: return "N/A"
    try:
        if np.isnan(v): return "N/A"
    except (TypeError, ValueError):
        pass
    return f"{v:.{d}f}"

def fmtp(v):
    if v is None: return "N/A"
    try:
        if np.isnan(v): return "N/A"
    except (TypeError, ValueError):
        pass
    return f"{v:.2%}"

def fmt_dollar(v):
    if v is None: return "N/A"
    try:
        if np.isnan(v): return "N/A"
    except (TypeError, ValueError):
        pass
    return f"${v:,.0f}"

def _val_color(v, higher_is_better=True):
    if v is None: return TEXT_SEC
    try:
        if np.isnan(v): return TEXT_SEC
        if higher_is_better:
            return GREEN if v > 0 else RED
        else:
            return RED if v < -0.15 else (ORANGE if v < -0.05 else GREEN)
    except:
        return TEXT_SEC

# ── Design tokens ──
BG       = '#FFFFFF'
CARD_BG  = '#F7F8FA'
CARD_BRD = '#E2E5EB'
TEXT_PRI = '#1A1D23'
TEXT_SEC = '#5A6270'
TEXT_MUT = '#8C95A3'
ACCENT   = '#1E3A5F'   # Dark navy
ACCENT2  = '#2563EB'   # Bright blue
GREEN    = '#059669'
RED      = '#DC2626'
ORANGE   = '#D97706'
GRID_CLR = '#E5E7EB'
HEADER_BG = '#1E3A5F'

def _draw_card(ax_fig, x, y, w, h, label, value, color=ACCENT2, fontsize_val=22):
    rect = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.008",
                           facecolor=CARD_BG, edgecolor=CARD_BRD, linewidth=1.2,
                           transform=ax_fig.transAxes, zorder=2)
    ax_fig.add_patch(rect)
    ax_fig.text(x + w/2, y + h*0.65, value, ha='center', va='center',
                fontsize=fontsize_val, fontweight='bold', color=color,
                transform=ax_fig.transAxes, zorder=3)
    ax_fig.text(x + w/2, y + h*0.22, label, ha='center', va='center',
                fontsize=7, color=TEXT_SEC, fontweight='bold',
                transform=ax_fig.transAxes, zorder=3)

def _style_ax(ax, title=None):
    ax.set_facecolor(BG)
    ax.tick_params(colors=TEXT_SEC, labelsize=8)
    ax.grid(True, alpha=0.4, color=GRID_CLR, linewidth=0.6)
    for spine in ax.spines.values():
        spine.set_color(CARD_BRD)
        spine.set_linewidth(0.6)
    if title:
        ax.set_title(title, color=TEXT_PRI, fontsize=11, fontweight='bold', pad=10)


with PdfPages(pdf_path) as pdf:

    # ══════════════════════════════════════════════════════════
    # PAGE 1: Executive Summary — KPI Cards + Full Metrics Table
    # ══════════════════════════════════════════════════════════
    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')

    # ── Header bar (dark navy) ──
    header = Rectangle((0, 0.915), 1, 0.085, facecolor=HEADER_BG, transform=ax.transAxes, zorder=1)
    ax.add_patch(header)
    display_name = STRATEGY_NAME.replace("_", " ")
    ax.text(0.04, 0.965, display_name.upper(), ha='left', va='center', fontsize=18,
            fontweight='bold', color='white', transform=ax.transAxes, zorder=2)
    _idx_fmt = lambda i: str(i.date()) if hasattr(i, 'date') else str(i)
    ax.text(0.04, 0.935, f"{TICKER}  |  {_idx_fmt(full_close.index[0])} to {_idx_fmt(full_close.index[-1])}  |  {len(full_close):,} bars  |  freq={FREQ}",
            ha='left', va='center', fontsize=9, color=(1, 1, 1, 0.70),
            transform=ax.transAxes, zorder=2)
    ax.text(0.96, 0.955, f"{param_str}", ha='right', va='center',
            fontsize=9, color=(1, 1, 1, 0.80), transform=ax.transAxes, zorder=2, family='monospace')

    ax.plot([0.03, 0.97], [0.908, 0.908], color=CARD_BRD, linewidth=0.8, transform=ax.transAxes, zorder=1)

    # ── KPI Cards Row ──
    card_w, card_h = 0.138, 0.085
    card_y = 0.81
    sharpe_v = M['sharpe']; ret_v = M['total_return']; dd_v = M['max_dd']
    wr_v = M['win_rate']; pf_v = M['pf']

    cards_data = [
        ("SHARPE", fmt(sharpe_v, 3), ACCENT2 if (sharpe_v or 0) > 1 else (ORANGE if (sharpe_v or 0) > 0.5 else RED)),
        ("TOTAL RETURN", fmtp(ret_v), GREEN if (ret_v or 0) > 0 else RED),
        ("MAX DRAWDOWN", fmtp(dd_v), RED if (dd_v or 0) < -0.20 else (ORANGE if (dd_v or 0) < -0.10 else GREEN)),
        ("WIN RATE", f"{wr_v:.1f}%" if wr_v else "N/A", GREEN if (wr_v or 0) >= 50 else ORANGE),
        ("TRADES", str(M['trades']), TEXT_PRI),
        ("PROFIT FACTOR", fmt(pf_v, 2), GREEN if (pf_v or 0) > 1.5 else (ORANGE if (pf_v or 0) > 1 else RED)),
    ]
    x_start = 0.03
    gap = (0.94 - len(cards_data) * card_w) / max(len(cards_data) - 1, 1)
    for i, (label, value, color) in enumerate(cards_data):
        cx = x_start + i * (card_w + gap)
        _draw_card(ax, cx, card_y, card_w, card_h, label, value, color, fontsize_val=18)

    # ── Full Comparison Table ──
    table_rows = [
        ["", "FULL SAMPLE", "IN-SAMPLE", "OUT-OF-SAMPLE", "BUY & HOLD"],
        ["Total Return",      fmtp(M_full['total_return']),  fmtp(M_is['total_return']),  fmtp(M_oos['total_return']),  fmtp(M_bh['total_return'])],
        ["Ann. Return",       fmtp(M_full['ann_return']),    fmtp(M_is['ann_return']),    fmtp(M_oos['ann_return']),    fmtp(M_bh['ann_return'])],
        ["Sharpe Ratio",      fmt(M_full['sharpe'], 3),      fmt(M_is['sharpe'], 3),      fmt(M_oos['sharpe'], 3),      fmt(M_bh['sharpe'], 3)],
        ["Sortino Ratio",     fmt(M_full['sortino'], 3),     fmt(M_is['sortino'], 3),     fmt(M_oos['sortino'], 3),     fmt(M_bh['sortino'], 3)],
        ["Max Drawdown",      fmtp(M_full['max_dd']),        fmtp(M_is['max_dd']),        fmtp(M_oos['max_dd']),        fmtp(M_bh['max_dd'])],
        ["Calmar Ratio",      fmt(M_full['calmar'], 2),      fmt(M_is['calmar'], 2),      fmt(M_oos['calmar'], 2),      fmt(M_bh['calmar'], 2)],
        ["Ann. Volatility",   fmtp(M_full['volatility']),    fmtp(M_is['volatility']),    fmtp(M_oos['volatility']),    fmtp(M_bh['volatility'])],
        ["Win Rate",
         f"{M_full['win_rate']:.1f}%" if M_full['win_rate'] else "N/A",
         f"{M_is['win_rate']:.1f}%" if M_is['win_rate'] else "N/A",
         f"{M_oos['win_rate']:.1f}%" if M_oos['win_rate'] else "N/A",
         "N/A"],
        ["Profit Factor",     fmt(M_full['pf'], 2),          fmt(M_is['pf'], 2),          fmt(M_oos['pf'], 2),          "N/A"],
        ["Total Trades",      str(M_full['trades']),         str(M_is['trades']),          str(M_oos['trades']),          "1"],
        ["Trades / Year",     fmt(M_full['trades_yr'], 1),   fmt(M_is['trades_yr'], 1),   fmt(M_oos['trades_yr'], 1),   "N/A"],
        ["Expectancy",        fmtp(M_full['expectancy']),    fmtp(M_is['expectancy']),    fmtp(M_oos['expectancy']),    "N/A"],
        ["Payoff Ratio",      fmt(M_full['payoff'], 2),      fmt(M_is['payoff'], 2),      fmt(M_oos['payoff'], 2),      "N/A"],
        ["Avg Win",           fmtp(M_full['avg_win']),       fmtp(M_is['avg_win']),       fmtp(M_oos['avg_win']),       "N/A"],
        ["Avg Loss",          fmtp(M_full['avg_loss']),      fmtp(M_is['avg_loss']),      fmtp(M_oos['avg_loss']),      "N/A"],
        ["Largest Win",       fmtp(M_full['largest_win']),   fmtp(M_is['largest_win']),   fmtp(M_oos['largest_win']),   "N/A"],
        ["Largest Loss",      fmtp(M_full['largest_loss']),  fmtp(M_is['largest_loss']),  fmtp(M_oos['largest_loss']),  "N/A"],
    ]

    table_y = 0.03
    table_h = 0.745
    table = ax.table(cellText=table_rows[1:], colLabels=table_rows[0],
                     cellLoc='center', loc='center',
                     bbox=[0.03, table_y, 0.94, table_h])
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)

    n_rows = len(table_rows) - 1
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor('#D1D5DB')
        cell.set_linewidth(0.4)
        cell.set_height(1.0 / (n_rows + 1))

        if row == 0:
            cell.set_facecolor(HEADER_BG)
            cell.set_text_props(color='white', fontweight='bold', fontsize=8)
        else:
            cell.set_facecolor('#FAFBFC' if row % 2 == 0 else BG)
            if col == 0:
                cell.set_text_props(color=TEXT_PRI, fontsize=8.5, fontweight='bold')
                cell._loc = 'left'
            else:
                cell.set_text_props(color=TEXT_PRI, fontsize=8.5, family='monospace')
                text = cell.get_text().get_text()
                metric_name = table_rows[row][0] if row < len(table_rows) else ""
                if text not in ("N/A", "1", ""):
                    try:
                        if "%" in text and metric_name in ["Total Return", "Ann. Return"]:
                            val = float(text.replace("%", "")) / 100
                            cell.get_text().set_color(GREEN if val > 0 else RED)
                        elif metric_name == "Max Drawdown" and "%" in text:
                            val = float(text.replace("%", "")) / 100
                            cell.get_text().set_color(RED if val < -0.15 else (ORANGE if val < -0.05 else GREEN))
                        elif metric_name == "Sharpe Ratio":
                            val = float(text)
                            cell.get_text().set_color(GREEN if val > 1 else (ORANGE if val > 0.5 else RED))
                    except:
                        pass

    ax.text(0.5, 0.008, f"Run {RUN_ID}  |  QS Finance  |  {STRATEGY_NAME} on {TICKER}",
            ha='center', va='bottom', fontsize=7, color=TEXT_MUT, transform=ax.transAxes)

    pdf.savefig(fig, facecolor=BG)
    plt.close(fig)

    # ══════════════════════════════════════════════════════════
    # PAGE 2: Equity Curve + Drawdown + Stats Box
    # ══════════════════════════════════════════════════════════
    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor(BG)
    fig.text(0.5, 0.97, f'{display_name} on {TICKER} -- Equity & Drawdown',
             ha='center', fontsize=14, fontweight='bold', color=TEXT_PRI)
    fig.text(0.5, 0.945, f'{_idx_fmt(full_close.index[0])} to {_idx_fmt(full_close.index[-1])}  |  {param_str}',
             ha='center', fontsize=9, color=TEXT_SEC)

    ax1 = fig.add_axes([0.08, 0.38, 0.86, 0.53])
    ax2 = fig.add_axes([0.08, 0.08, 0.86, 0.25])

    eq_strat = pf_full.value(); eq_bh = pf_bh.value()

    _style_ax(ax1)
    ax1.plot(full_close.index[:split_idx], eq_strat.iloc[:split_idx].values,
             color=ACCENT2, linewidth=2, label='Strategy (IS)', solid_capstyle='round')
    ax1.plot(full_close.index[split_idx:], eq_strat.iloc[split_idx:].values,
             color=ORANGE, linewidth=2, label='Strategy (OOS)', solid_capstyle='round')
    ax1.plot(full_close.index, eq_bh.values, color=TEXT_MUT, linewidth=1.2,
             alpha=0.5, linestyle='--', label='Buy & Hold')
    ax1.axvline(x=full_close.index[split_idx], color=RED, linestyle=':', alpha=0.3, linewidth=1,
                label=f'IS/OOS Split')
    ax1.fill_between(full_close.index[:split_idx], eq_strat.iloc[:split_idx].values,
                      INIT_CASH, alpha=0.04, color=ACCENT2)
    ax1.fill_between(full_close.index[split_idx:], eq_strat.iloc[split_idx:].values,
                      eq_strat.iloc[split_idx].item(), alpha=0.04, color=ORANGE)
    ax1.set_ylabel('Portfolio Value ($)', color=TEXT_SEC, fontsize=9)
    ax1.legend(fontsize=8, facecolor=BG, edgecolor=CARD_BRD, labelcolor=TEXT_PRI,
               framealpha=0.95, loc='upper left')
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))

    stats_items = [
        f"Sharpe: {fmt(M['sharpe'],3)}",
        f"Return: {fmtp(M['total_return'])}",
        f"MaxDD: {fmtp(M['max_dd'])}",
        f"WR: {M['win_rate']:.1f}%" if M['win_rate'] else "WR: N/A",
        f"PF: {fmt(M['pf'])}",
        f"Trades: {M['trades']}",
    ]
    stats_text = "   |   ".join(stats_items)
    ax1.text(0.5, 0.03, stats_text, transform=ax1.transAxes, fontsize=7.5, ha='center',
             color=TEXT_SEC, family='monospace',
             bbox=dict(boxstyle='round,pad=0.4', facecolor=CARD_BG, edgecolor=CARD_BRD, alpha=0.95))

    _style_ax(ax2)
    dd = pf_full.drawdown() * 100
    ax2.fill_between(full_close.index, dd.values, 0, color=RED, alpha=0.15)
    ax2.plot(full_close.index, dd.values, color=RED, linewidth=0.8, alpha=0.7)
    ax2.axvline(x=full_close.index[split_idx], color=RED, linestyle=':', alpha=0.3, linewidth=1)
    ax2.set_ylabel('Drawdown (%)', color=TEXT_SEC, fontsize=9)
    ax2.set_xlabel('Date', color=TEXT_SEC, fontsize=9)

    fig.text(0.5, 0.01, f"Run {RUN_ID}  |  QS Finance", ha='center', fontsize=7, color=TEXT_MUT)
    pdf.savefig(fig, facecolor=BG)
    plt.close(fig)

    # ══════════════════════════════════════════════════════════
    # PAGE 3: Trade Analysis — 2x2 Grid
    # ══════════════════════════════════════════════════════════
    if len(tr) > 0:
        fig, axes = plt.subplots(2, 2, figsize=(11, 8.5))
        fig.patch.set_facecolor(BG)
        fig.suptitle(f'Trade Analysis -- {len(tr)} Trades  |  {display_name} on {TICKER}',
                     fontsize=14, fontweight='bold', color=TEXT_PRI, y=0.97)

        n = len(tr)
        colors_bar = [GREEN if r > 0 else RED for r in tr]
        colors_pnl = [GREEN if p > 0 else RED for p in pnl]

        for a in axes.flat:
            _style_ax(a)

        axes[0,0].bar(range(n), tr*100, color=colors_bar, edgecolor='none', width=0.8, alpha=0.85)
        axes[0,0].axhline(np.mean(tr)*100, color=ACCENT2, linestyle='--', linewidth=1.5,
                          label=f'Avg: {np.mean(tr)*100:.2f}%')
        axes[0,0].axhline(0, color=TEXT_MUT, linewidth=0.5)
        axes[0,0].set_title('Trade Returns (%)', color=TEXT_PRI, fontsize=11, fontweight='bold')
        axes[0,0].set_xlabel('Trade #', color=TEXT_SEC, fontsize=8)
        axes[0,0].legend(fontsize=7, facecolor=BG, edgecolor=CARD_BRD)

        axes[0,1].bar(range(n), pnl, color=colors_pnl, edgecolor='none', width=0.8, alpha=0.85)
        axes[0,1].axhline(np.mean(pnl), color=ACCENT2, linestyle='--', linewidth=1.5,
                          label=f'Avg: ${np.mean(pnl):,.0f}')
        axes[0,1].axhline(0, color=TEXT_MUT, linewidth=0.5)
        axes[0,1].set_title('Trade P&L ($)', color=TEXT_PRI, fontsize=11, fontweight='bold')
        axes[0,1].yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))
        axes[0,1].legend(fontsize=7, facecolor=BG, edgecolor=CARD_BRD)

        cum_pnl = np.cumsum(pnl)
        axes[1,0].plot(range(1, n+1), cum_pnl, color=ACCENT2, linewidth=2.5, solid_capstyle='round')
        axes[1,0].fill_between(range(1, n+1), cum_pnl, 0, where=cum_pnl>=0, alpha=0.08, color=GREEN)
        axes[1,0].fill_between(range(1, n+1), cum_pnl, 0, where=cum_pnl<0, alpha=0.08, color=RED)
        axes[1,0].axhline(0, color=TEXT_MUT, linewidth=0.5)
        axes[1,0].set_title('Cumulative P&L', color=TEXT_PRI, fontsize=11, fontweight='bold')
        axes[1,0].set_xlabel('Trade #', color=TEXT_SEC, fontsize=8)
        axes[1,0].yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))

        axes[1,1].hist(tr*100, bins=min(30, max(10, n//3)), color=ACCENT2, edgecolor='white',
                       alpha=0.75, linewidth=0.5)
        axes[1,1].axvline(np.mean(tr)*100, color=RED, linestyle='--', linewidth=2,
                          label=f'Mean: {np.mean(tr)*100:.2f}%')
        axes[1,1].axvline(0, color=TEXT_MUT, linewidth=0.8, alpha=0.5)
        axes[1,1].set_title('Return Distribution', color=TEXT_PRI, fontsize=11, fontweight='bold')
        axes[1,1].set_xlabel('Return (%)', color=TEXT_SEC, fontsize=8)
        axes[1,1].legend(fontsize=7, facecolor=BG, edgecolor=CARD_BRD)

        plt.tight_layout(rect=[0, 0.02, 1, 0.95])
        fig.text(0.5, 0.005, f"Run {RUN_ID}  |  QS Finance", ha='center', fontsize=7, color=TEXT_MUT)
        pdf.savefig(fig, facecolor=BG)
        plt.close(fig)

    # ══════════════════════════════════════════════════════════
    # PAGE 4: Parameter Sensitivity — Line Charts + Summary Table
    # ══════════════════════════════════════════════════════════
    if len(PARAM_COLS) > 0 and len(results_df) > 1:
        _param_ranges = {}
        for pc in PARAM_COLS:
            if pc in results_df.columns:
                unique_vals = sorted(results_df[pc].dropna().unique().tolist())
                if len(unique_vals) > 1:
                    # Cap at 15 evenly-spaced values to keep charts readable
                    if len(unique_vals) > 15:
                        step = max(1, len(unique_vals) // 15)
                        unique_vals = unique_vals[::step]
                        # Ensure best value is included
                        bv = best_params.get(pc)
                        if bv is not None and bv not in unique_vals:
                            unique_vals.append(bv)
                            unique_vals = sorted(unique_vals)
                    _param_ranges[pc] = unique_vals

        if _param_ranges:
            n_params = len(_param_ranges)
            # 2x2 grid layout (max 4 params shown as line charts)
            n_chart = min(n_params, 4)
            n_cols_chart = 2 if n_chart > 1 else 1
            n_rows_chart = (n_chart + n_cols_chart - 1) // n_cols_chart

            fig = plt.figure(figsize=(11, 8.5))
            fig.patch.set_facecolor(BG)

            # Header
            fig.text(0.5, 0.97, f'Parameter Sensitivity  |  {display_name} on {TICKER}',
                     ha='center', fontsize=14, fontweight='bold', color=TEXT_PRI)
            fig.text(0.5, 0.945,
                     'Each parameter swept independently (others held at best). Flat lines = robust. Diverging IS/OOS = overfit.',
                     ha='center', fontsize=8.5, color=TEXT_SEC)

            sensitivity_data = []

            # Create subplots for line charts in top portion
            chart_axes = []
            for ci in range(n_chart):
                r = ci // n_cols_chart
                c = ci % n_cols_chart
                # Position: top ~60% of page for charts, bottom for summary table
                left = 0.08 + c * 0.48
                bottom = 0.58 - r * 0.27 if n_rows_chart <= 2 else 0.65 - r * 0.22
                width = 0.40
                height = 0.22 if n_rows_chart <= 2 else 0.18
                ax = fig.add_axes([left, bottom, width, height])
                chart_axes.append(ax)

            for ci, (pname, pvals) in enumerate(_param_ranges.items()):
                if ci >= n_chart:
                    break
                base_val = best_params.get(pname)

                is_sharpes = []
                oos_sharpes = []

                for val in pvals:
                    test_params = best_params.copy()
                    test_params[pname] = val
                    try:
                        e_t, x_t = _compute_signals(train_close, test_params, _h_is, _l_is)
                        pf_t = _make_pf(train_close, e_t, x_t, _h_is, _l_is, params=test_params)
                        is_sr = float(pf_t.sharpe_ratio(freq=FREQ))
                        is_sharpes.append(is_sr if not np.isnan(is_sr) else 0.0)
                    except:
                        is_sharpes.append(0.0)

                    try:
                        e_v, x_v = _compute_signals(val_close, test_params, _h_oos, _l_oos)
                        pf_v = _make_pf(val_close, e_v, x_v, _h_oos, _l_oos, params=test_params)
                        oos_sr = float(pf_v.sharpe_ratio(freq=FREQ))
                        oos_sharpes.append(oos_sr if not np.isnan(oos_sr) else 0.0)
                    except:
                        oos_sharpes.append(0.0)

                # Compute sensitivity metrics
                is_range = max(is_sharpes) - min(is_sharpes) if is_sharpes else 0
                oos_range = max(oos_sharpes) - min(oos_sharpes) if oos_sharpes else 0
                avg_sr = np.mean(is_sharpes + oos_sharpes) if (is_sharpes + oos_sharpes) else 0.01
                sens_score = (is_range + oos_range) / 2 / max(abs(avg_sr), 0.01)
                # IS-OOS correlation (do they agree?)
                if len(is_sharpes) > 2:
                    try:
                        from scipy.stats import pearsonr
                        corr, _ = pearsonr(is_sharpes, oos_sharpes)
                    except:
                        corr = 0.0
                else:
                    corr = 0.0
                flag = "ROBUST" if sens_score < 0.5 and corr > 0.3 else ("MODERATE" if sens_score < 1.5 else "FRAGILE")
                sensitivity_data.append((pname, base_val, is_range, oos_range, sens_score, corr, flag))

                # ── Line chart: IS and OOS Sharpe on same axes ──
                ax = chart_axes[ci]
                _style_ax(ax)

                # Convert pvals to numeric x-axis positions
                try:
                    x_vals = [float(v) for v in pvals]
                    x_numeric = True
                except (ValueError, TypeError):
                    x_vals = list(range(len(pvals)))
                    x_numeric = False

                ax.plot(x_vals, is_sharpes, color=ACCENT2, linewidth=2.5, marker='o',
                        markersize=5, label='IS', solid_capstyle='round', zorder=3)
                ax.plot(x_vals, oos_sharpes, color=ORANGE, linewidth=2.5, marker='s',
                        markersize=5, label='OOS', solid_capstyle='round', zorder=3)

                # Shade area between IS and OOS to highlight divergence
                ax.fill_between(x_vals, is_sharpes, oos_sharpes, alpha=0.08,
                                color=GREEN if corr > 0.3 else RED)

                # Mark best value
                if base_val is not None:
                    try:
                        bx = float(base_val) if x_numeric else pvals.index(base_val)
                        ax.axvline(bx, color=GREEN, linestyle='--', linewidth=1.5, alpha=0.5, zorder=1)
                        ax.annotate(f'Best: {base_val}', xy=(bx, max(max(is_sharpes), max(oos_sharpes))),
                                    fontsize=7, color=GREEN, ha='center', va='bottom',
                                    fontweight='bold')
                    except:
                        pass

                ax.axhline(0, color=TEXT_MUT, linewidth=0.5, alpha=0.5)
                ax.set_xlabel(pname, fontsize=9, color=TEXT_PRI, fontweight='bold')
                ax.set_ylabel('Sharpe', fontsize=8, color=TEXT_SEC)
                ax.legend(fontsize=7, facecolor=BG, edgecolor=CARD_BRD, loc='best', framealpha=0.9)

                if not x_numeric:
                    ax.set_xticks(x_vals)
                    ax.set_xticklabels([str(v) for v in pvals], fontsize=7)
                else:
                    ax.tick_params(axis='x', labelsize=7)

                # Flag badge in top-right
                badge_color = GREEN if flag == "ROBUST" else (ORANGE if flag == "MODERATE" else RED)
                ax.text(0.97, 0.95, flag, transform=ax.transAxes, fontsize=8, fontweight='bold',
                        color='white', ha='right', va='top',
                        bbox=dict(boxstyle='round,pad=0.3', facecolor=badge_color, alpha=0.9))

            # ── Summary table at bottom ──
            if sensitivity_data:
                tbl_data = []
                tbl_headers = ["Parameter", "Best Value", "IS Range", "OOS Range",
                               "IS/OOS Corr", "Sensitivity", "Verdict"]
                for pname, bv, isr, osr, sc, cr, fl in sensitivity_data:
                    tbl_data.append([
                        pname, str(bv),
                        f"{isr:.3f}", f"{osr:.3f}",
                        f"{cr:.2f}", f"{sc:.2f}", fl
                    ])

                tbl_ax = fig.add_axes([0.08, 0.04, 0.84, 0.04 + len(tbl_data) * 0.028])
                tbl_ax.axis('off')
                tbl = tbl_ax.table(cellText=tbl_data, colLabels=tbl_headers,
                                   cellLoc='center', loc='center',
                                   bbox=[0, 0, 1, 1])
                tbl.auto_set_font_size(False)
                tbl.set_fontsize(8.5)

                for (row, col), cell in tbl.get_celld().items():
                    cell.set_edgecolor('#D1D5DB')
                    cell.set_linewidth(0.4)
                    if row == 0:
                        cell.set_facecolor(HEADER_BG)
                        cell.set_text_props(color='white', fontweight='bold', fontsize=8)
                    else:
                        cell.set_facecolor('#FAFBFC' if row % 2 == 0 else BG)
                        cell.set_text_props(fontsize=8.5, family='monospace')
                        # Color the Verdict column
                        if col == len(tbl_headers) - 1:
                            txt = cell.get_text().get_text()
                            c = GREEN if txt == "ROBUST" else (ORANGE if txt == "MODERATE" else RED)
                            cell.get_text().set_color(c)
                            cell.get_text().set_fontweight('bold')
                        # Color the IS/OOS Corr column
                        if col == 4 and row > 0:
                            try:
                                cv = float(cell.get_text().get_text())
                                cell.get_text().set_color(GREEN if cv > 0.5 else (ORANGE if cv > 0 else RED))
                            except:
                                pass

            fig.text(0.5, 0.005, f"Run {RUN_ID}  |  QS Finance", ha='center', fontsize=7, color=TEXT_MUT)
            pdf.savefig(fig, facecolor=BG)
            plt.close(fig)

    # ══════════════════════════════════════════════════════════
    # PAGE 5: FTMO Monte Carlo Simulation
    # ══════════════════════════════════════════════════════════
    dr = daily_rets.values.ravel(); dr = dr[~np.isnan(dr)]
    N_SIM = 10_000; DAYS = 30; ACCOUNT = 100_000
    np.random.seed(42)
    n_passed = n_blown_t = n_blown_d = 0
    final_eqs = np.zeros(N_SIM); sample_paths = []

    for s in range(N_SIM):
        eq = ACCOUNT; path = [ACCOUNT]
        sim_rets = np.random.choice(dr, size=DAYS, replace=True)
        blown = False
        for d in range(DAYS):
            day_start = eq; eq *= (1 + sim_rets[d]); path.append(eq)
            if (eq - day_start)/ACCOUNT < -0.05: n_blown_d += 1; blown = True; break
            if (eq - ACCOUNT)/ACCOUNT < -0.10: n_blown_t += 1; blown = True; break
            if (eq - ACCOUNT)/ACCOUNT >= 0.10: n_passed += 1; blown = True; break
        while len(path) < DAYS + 1: path.append(path[-1])
        final_eqs[s] = path[-1]
        if s < 200: sample_paths.append(path)

    n_still = N_SIM - n_passed - n_blown_t - n_blown_d
    pass_rate = n_passed / N_SIM * 100

    verdict = "FAVORABLE" if pass_rate >= 50 else "POSSIBLE" if pass_rate >= 25 else "CHALLENGING" if pass_rate >= 10 else "UNLIKELY"
    verdict_color = GREEN if pass_rate >= 50 else ORANGE if pass_rate >= 25 else (ORANGE if pass_rate >= 10 else RED)

    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor(BG)
    fig.text(0.5, 0.96, f'FTMO Challenge Simulation  |  {display_name} on {TICKER}',
             ha='center', fontsize=14, fontweight='bold', color=TEXT_PRI)
    fig.text(0.5, 0.935, f'{N_SIM:,} Monte Carlo paths  |  {DAYS}-day challenge window  |  $100K account',
             ha='center', fontsize=9, color=TEXT_SEC)

    ax_top = fig.add_axes([0, 0.82, 1, 0.10])
    ax_top.set_xlim(0, 1); ax_top.set_ylim(0, 1); ax_top.axis('off')

    mc_cards = [
        ("PASS RATE", f"{pass_rate:.1f}%", verdict_color),
        ("VERDICT", verdict, verdict_color),
        ("PASSED", f"{n_passed:,}", GREEN),
        ("BLOWN (TOTAL DD)", f"{n_blown_t:,}", RED),
        ("BLOWN (DAILY DD)", f"{n_blown_d:,}", RED),
        ("TIMED OUT", f"{n_still:,}", TEXT_SEC),
    ]
    mc_cw = 0.135
    mc_gap = (0.92 - len(mc_cards) * mc_cw) / max(len(mc_cards) - 1, 1)
    for i, (label, value, color) in enumerate(mc_cards):
        cx = 0.04 + i * (mc_cw + mc_gap)
        _draw_card(ax_top, cx, 0.0, mc_cw, 0.95, label, value, color, fontsize_val=16)

    ax_mc1 = fig.add_axes([0.08, 0.38, 0.86, 0.40])
    _style_ax(ax_mc1)
    for path in sample_paths:
        c = GREEN if path[-1] >= 110000 else (RED if path[-1] <= 90000 else '#B0B8C4')
        ax_mc1.plot(range(DAYS+1), path, color=c, alpha=0.12, linewidth=0.5)
    ax_mc1.axhline(110000, color=GREEN, linestyle='--', linewidth=2, label='10% Target ($110K)')
    ax_mc1.axhline(90000, color=RED, linestyle='--', linewidth=2, label='10% Max Loss ($90K)')
    ax_mc1.axhline(100000, color=TEXT_MUT, linestyle='-', linewidth=0.8, alpha=0.4)
    ax_mc1.set_xlabel('Trading Day', color=TEXT_SEC, fontsize=9)
    ax_mc1.set_ylabel('Equity ($)', color=TEXT_SEC, fontsize=9)
    ax_mc1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))
    ax_mc1.legend(fontsize=8, facecolor=BG, edgecolor=CARD_BRD, labelcolor=TEXT_PRI, framealpha=0.95)

    ax_mc2 = fig.add_axes([0.08, 0.06, 0.86, 0.26])
    _style_ax(ax_mc2)
    ax_mc2.hist(final_eqs, bins=80, color=ACCENT2, edgecolor='white', alpha=0.75, linewidth=0.3)
    ax_mc2.axvline(110000, color=GREEN, linestyle='--', linewidth=2)
    ax_mc2.axvline(90000, color=RED, linestyle='--', linewidth=2)
    ax_mc2.axvline(np.median(final_eqs), color=ORANGE, linestyle='-', linewidth=1.5,
                   label=f'Median: ${np.median(final_eqs):,.0f}')
    ax_mc2.set_xlabel('Final Equity ($)', color=TEXT_SEC, fontsize=9)
    ax_mc2.set_ylabel('Frequency', color=TEXT_SEC, fontsize=8)
    ax_mc2.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))
    ax_mc2.legend(fontsize=8, facecolor=BG, edgecolor=CARD_BRD, labelcolor=TEXT_PRI)

    fig.text(0.5, 0.005, f"Run {RUN_ID}  |  QS Finance", ha='center', fontsize=7, color=TEXT_MUT)
    pdf.savefig(fig, facecolor=BG)
    plt.close(fig)

# Copy PDF to archive
shutil.copy2(pdf_path, pdf_archive)

# Add MC results to JSON
mc_data = {"pass_rate": round(pass_rate, 1), "n_simulations": N_SIM, "n_passed": n_passed,
           "n_blown_total": n_blown_t, "n_blown_daily": n_blown_d, "n_still_trading": n_still,
           "median_final_equity": round(float(np.median(final_eqs)), 2), "verdict": verdict}
export_json["monte_carlo_ftmo"] = mc_data
with open(os.path.join(LATEST_DIR, "summary.json"), 'w') as f:
    json.dump(export_json, f, indent=2, default=str)

# ════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print(f"  EXPORT COMPLETE -- {STRATEGY_NAME} on {TICKER}")
print(f"{'='*70}")
print(f"  Run ID:       {RUN_ID}")
print(f"  Timestamp:    {RUN_TIMESTAMP.strftime('%B %d, %Y at %I:%M:%S %p')}")
print(f"  Instrument:   {TICKER} ({export_json['metadata']['instrument_type']})")
print(f"  Params:       {param_str}")
print(f"  Sharpe:       {fmt(M['sharpe'],3)} (IS: {fmt(M_is['sharpe'],3)} -> OOS: {fmt(M_oos['sharpe'],3)})")
print(f"  FTMO Verdict: {verdict} ({pass_rate:.1f}% pass rate)")
print(f"{'='*70}")
print(f"\n  {STRAT_DIR}/")
print(f"  +-- latest/")
print(f"  |   +-- summary.json")
print(f"  |   +-- daily_returns.csv")
print(f"  |   +-- trades.csv")
print(f"  |   +-- grid_results.csv")
print(f"  |   +-- {pdf_filename}")
print(f"  +-- archive/")
print(f"      +-- {RUN_ID}_summary.json")
print(f"      +-- {RUN_ID}_{STRATEGY_NAME}_{_ticker_clean}_tearsheet.pdf")
print(f"\n  run_log.csv ({len(log_combined)} total runs)")
print(f"\n  To get my analysis: upload the tearsheet.pdf to our chat.")
print(f"  For deeper analysis: also upload summary.json + daily_returns.csv")
