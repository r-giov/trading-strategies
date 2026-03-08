# ════════════════════════════════════════════════════════════════════
# UNIVERSAL STRATEGY EXPORT — Data Files + PDF Tearsheet
# ════════════════════════════════════════════════════════════════════
# INSTRUCTIONS:
#   1. Paste at the END of any strategy notebook
#   2. Edit STRATEGY_NAME and PARAM_COLS below
#   3. Run — exports structured data + a comprehensive PDF report
# ════════════════════════════════════════════════════════════════════

import os, sys, json, datetime, hashlib, platform
from matplotlib.backends.backend_pdf import PdfPages

# ═══ EDIT THESE LINES ═══════════════════════════════════════
STRATEGY_NAME = "MACD_Crossover"                                    # ← EDIT
PARAM_COLS    = ["fast_period", "slow_period", "signal_period"]     # ← EDIT
NOTES         = ""                                                   # ← Optional run notes
# ════════════════════════════════════════════════════════════════

INIT_CASH = 100_000
FEES      = 0.0005
SLIPPAGE  = 0.0005
FREQ      = 'D'

# ── Google Drive mount ──
EXPORT_DIR = "/content/strategy_exports"
IN_COLAB = 'google.colab' in sys.modules
try:
    from google.colab import drive
    if not os.path.exists('/content/drive'):
        drive.mount('/content/drive')
    EXPORT_DIR = "/content/drive/MyDrive/strategy_exports"
    IN_COLAB = True
    print("\u2705 Google Drive mounted")
except:
    print("\u26a0\ufe0f Local mode — exports to ./strategy_exports")

RUN_TIMESTAMP = datetime.datetime.now()
RUN_ID = RUN_TIMESTAMP.strftime("%Y%m%d_%H%M%S")

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
    if STRATEGY_NAME.startswith("MACD"):
        ml, sl, _ = talib.MACD(vals, fastperiod=params['fast_period'], slowperiod=params['slow_period'], signalperiod=params['signal_period'])
        ms, ss = pd.Series(ml, index=idx), pd.Series(sl, index=idx)
        e_raw = (ms.shift(1) <= ss.shift(1)) & (ms > ss)
        x_raw = (ms.shift(1) >= ss.shift(1)) & (ms < ss)
    elif STRATEGY_NAME.startswith("RSI"):
        rsi_s = pd.Series(talib.RSI(vals, timeperiod=params['rsi_len']), index=idx)
        e_raw = (rsi_s.shift(1) <= params['oversold']) & (rsi_s > params['oversold'])
        x_raw = (rsi_s.shift(1) <= params['overbought']) & (rsi_s > params['overbought'])
    elif STRATEGY_NAME.startswith("EMA"):
        fv = pd.Series(talib.EMA(vals, timeperiod=params['fast_ema']), index=idx)
        sv = pd.Series(talib.EMA(vals, timeperiod=params['slow_ema']), index=idx)
        tv = pd.Series(talib.SMA(vals, timeperiod=params['trend_filter']), index=idx)
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
        h_v = high_s.values.astype(float) if high_s is not None else vals
        l_v = low_s.values.astype(float) if low_s is not None else vals
        uc = pd.Series(talib.MAX(h_v, timeperiod=params['entry_period']), index=idx).shift(1)
        lc = pd.Series(talib.MIN(l_v, timeperiod=params['exit_period']), index=idx).shift(1)
        tf = pd.Series(talib.SMA(vals, timeperiod=params['filter_period']), index=idx).shift(1)
        cs = pd.Series(vals, index=idx)
        e_raw = (cs > uc) & (cs > tf); x_raw = (cs < lc)
    else:
        raise ValueError(f"Unknown strategy: {STRATEGY_NAME}")
    entries = pd.Series(np.where(e_raw.shift(1).isna(), False, e_raw.shift(1)), index=idx, dtype=bool)
    exits = pd.Series(np.where(x_raw.shift(1).isna(), False, x_raw.shift(1)), index=idx, dtype=bool)
    return entries, exits

# ════════════════════════════════════════════════════════════════
# Build portfolios
# ════════════════════════════════════════════════════════════════
results_df = pd.DataFrame(grid_search_results)
best = results_df.loc[results_df['sharpe_ratio'].idxmax()]
best_params = {col: int(best[col]) for col in PARAM_COLS}
param_str = ", ".join([f"{k}={v}" for k, v in best_params.items()])

if isinstance(stock_data.columns, pd.MultiIndex):
    full_close = stock_data[('Close', TICKER)].astype(float).squeeze()
else:
    full_close = stock_data['Close'].astype(float).squeeze()
full_close.name = 'price'

split_idx = int(len(full_close) * 0.60)
train_close = full_close.iloc[:split_idx].copy()
val_close = full_close.iloc[split_idx:].copy()

# High/Low for Donchian
high_s, low_s = None, None
if STRATEGY_NAME.startswith("Donchian") or STRATEGY_NAME.startswith("DC"):
    if isinstance(stock_data.columns, pd.MultiIndex):
        high_s = stock_data[('High', TICKER)].astype(float).squeeze()
        low_s = stock_data[('Low', TICKER)].astype(float).squeeze()
    else:
        high_s = stock_data['High'].astype(float).squeeze()
        low_s = stock_data['Low'].astype(float).squeeze()

# Full sample
e_full, x_full = _compute_signals(full_close, best_params, high_s, low_s)
pf_full = vbt.Portfolio.from_signals(close=full_close, entries=e_full, exits=x_full,
                                      init_cash=INIT_CASH, fees=FEES, slippage=SLIPPAGE, freq=FREQ)
# IS
e_is, x_is = _compute_signals(train_close, best_params,
                                high_s.iloc[:split_idx] if high_s is not None else None,
                                low_s.iloc[:split_idx] if low_s is not None else None)
pf_is = vbt.Portfolio.from_signals(close=train_close, entries=e_is, exits=x_is,
                                    init_cash=INIT_CASH, fees=FEES, slippage=SLIPPAGE, freq=FREQ)
# OOS
e_oos, x_oos = _compute_signals(val_close, best_params,
                                  high_s.iloc[split_idx:] if high_s is not None else None,
                                  low_s.iloc[split_idx:] if low_s is not None else None)
pf_oos = vbt.Portfolio.from_signals(close=val_close, entries=e_oos, exits=x_oos,
                                     init_cash=INIT_CASH, fees=FEES, slippage=SLIPPAGE, freq=FREQ)
# Buy & Hold
bh_e = pd.Series(False, index=full_close.index, dtype=bool); bh_e.iloc[0] = True
bh_x = pd.Series(False, index=full_close.index, dtype=bool)
pf_bh = vbt.Portfolio.from_signals(close=full_close, entries=bh_e, exits=bh_x,
                                    init_cash=INIT_CASH, fees=FEES, slippage=SLIPPAGE, freq=FREQ)

# ── Extract metrics ──
trades_obj = pf_full.trades
tr = np.asarray(trades_obj.returns.values if hasattr(trades_obj.returns, 'values') else trades_obj.returns).ravel()
pnl = np.asarray(trades_obj.pnl.values if hasattr(trades_obj.pnl, 'values') else trades_obj.pnl).ravel()
pos, neg = tr[tr > 0], tr[tr < 0]
years_full = max((full_close.index[-1] - full_close.index[0]).days / 365.25, 1e-9)
daily_rets = pf_full.returns()

def safe(fn, default=None):
    try: return float(fn())
    except: return default

M = {  # Master metrics dict
    'total_return': safe(pf_full.total_return), 'ann_return': safe(lambda: pf_full.annualized_return(freq=FREQ)),
    'sharpe': safe(lambda: pf_full.sharpe_ratio(freq=FREQ)), 'sortino': safe(lambda: pf_full.sortino_ratio(freq=FREQ)),
    'max_dd': safe(pf_full.max_drawdown), 'volatility': safe(lambda: pf_full.annualized_volatility(freq=FREQ)),
    'calmar': safe(lambda: pf_full.annualized_return(freq=FREQ)) / abs(safe(pf_full.max_drawdown)) if abs(safe(pf_full.max_drawdown, 0)) > 1e-9 else None,
    'trades': len(trades_obj), 'trades_yr': len(trades_obj) / years_full,
    'win_rate': float(len(pos) / len(tr) * 100) if len(tr) > 0 else None,
    'pf': float(pos.sum() / abs(neg.sum())) if len(neg) > 0 and abs(neg.sum()) > 0 else None,
    'expectancy': float(tr.mean()) if len(tr) > 0 else None,
    'avg_win': float(pos.mean()) if len(pos) > 0 else None, 'avg_loss': float(neg.mean()) if len(neg) > 0 else None,
    'largest_win': float(pos.max()) if len(pos) > 0 else None, 'largest_loss': float(neg.min()) if len(neg) > 0 else None,
    'payoff': float(abs(pos.mean() / neg.mean())) if len(pos) > 0 and len(neg) > 0 else None,
    'is_sharpe': safe(lambda: pf_is.sharpe_ratio(freq=FREQ)), 'is_return': safe(pf_is.total_return),
    'is_dd': safe(pf_is.max_drawdown), 'is_trades': len(pf_is.trades),
    'oos_sharpe': safe(lambda: pf_oos.sharpe_ratio(freq=FREQ)), 'oos_return': safe(pf_oos.total_return),
    'oos_dd': safe(pf_oos.max_drawdown), 'oos_trades': len(pf_oos.trades),
    'bh_return': safe(pf_bh.total_return), 'bh_sharpe': safe(lambda: pf_bh.sharpe_ratio(freq=FREQ)),
    'bh_dd': safe(pf_bh.max_drawdown),
}

# ════════════════════════════════════════════════════════════════
# 1. SAVE STRUCTURED DATA FILES
# ════════════════════════════════════════════════════════════════
export_json = {
    "metadata": {
        "run_id": RUN_ID, "export_timestamp": RUN_TIMESTAMP.isoformat(),
        "export_date_human": RUN_TIMESTAMP.strftime("%B %d, %Y at %I:%M %p"),
        "strategy_name": STRATEGY_NAME, "strategy_family": STRATEGY_NAME.split("_")[0],
        "ticker": TICKER,
        "instrument_type": ("crypto" if "-USD" in TICKER and TICKER.replace("-USD","").isalpha()
                           else "forex" if "/" in TICKER or (len(TICKER) == 6 and TICKER.isalpha())
                           else "equity/etf"),
        "data_source": "yfinance", "data_interval": "1d", "currency": "USD",
        "start_date": str(full_close.index[0].date()), "end_date": str(full_close.index[-1].date()),
        "total_bars": len(full_close), "total_years": round(years_full, 2),
        "train_start": str(train_close.index[0].date()), "train_end": str(train_close.index[-1].date()),
        "train_bars": len(train_close), "val_start": str(val_close.index[0].date()),
        "val_end": str(val_close.index[-1].date()), "val_bars": len(val_close), "train_ratio": 0.60,
        "init_cash": INIT_CASH, "fees_pct": FEES, "slippage_pct": SLIPPAGE, "frequency": FREQ,
        "first_close": round(float(full_close.iloc[0]), 4), "last_close": round(float(full_close.iloc[-1]), 4),
        "python_version": sys.version.split()[0], "environment": "colab_pro" if IN_COLAB else "local",
        "grid_combos_tested": len(results_df), "param_columns": PARAM_COLS, "notes": NOTES,
    },
    "best_params": best_params,
    "metrics_full_sample": {k: v for k, v in M.items() if not k.startswith('is_') and not k.startswith('oos_') and not k.startswith('bh_')},
    "metrics_in_sample": {k.replace('is_',''): v for k, v in M.items() if k.startswith('is_')},
    "metrics_out_of_sample": {k.replace('oos_',''): v for k, v in M.items() if k.startswith('oos_')},
    "metrics_buy_hold": {k.replace('bh_',''): v for k, v in M.items() if k.startswith('bh_')},
    "grid_search_summary": {
        "top5": results_df.nlargest(5, 'sharpe_ratio')[PARAM_COLS + ['sharpe_ratio','total_return','max_drawdown']].to_dict('records'),
    }
}

# Save JSON
with open(os.path.join(LATEST_DIR, "summary.json"), 'w') as f:
    json.dump(export_json, f, indent=2, default=str)
with open(os.path.join(ARCHIVE_DIR, f"{RUN_ID}_summary.json"), 'w') as f:
    json.dump(export_json, f, indent=2, default=str)
print(f"\u2705 summary.json")

# Save CSVs
pd.DataFrame({'date': full_close.index.strftime('%Y-%m-%d'), 'strategy_return': daily_rets.values,
              'close': full_close.values, 'portfolio_value': pf_full.value().values
}).to_csv(os.path.join(LATEST_DIR, "daily_returns.csv"), index=False)
print(f"\u2705 daily_returns.csv")

pd.DataFrame({'trade_num': range(1, len(tr)+1), 'return_pct': tr*100, 'pnl_usd': pnl,
              'cumulative_pnl': np.cumsum(pnl), 'is_winner': tr > 0
}).to_csv(os.path.join(LATEST_DIR, "trades.csv"), index=False)
print(f"\u2705 trades.csv")

results_df.to_csv(os.path.join(LATEST_DIR, "grid_results.csv"), index=False)
print(f"\u2705 grid_results.csv")

# Run log
log_path = os.path.join(EXPORT_DIR, "run_log.csv")
log_entry = pd.DataFrame([{
    "run_id": RUN_ID, "timestamp": RUN_TIMESTAMP.isoformat(), "strategy": STRATEGY_NAME,
    "ticker": TICKER, "best_params": str(best_params),
    "sharpe_full": round(M['sharpe'] or 0, 4), "sharpe_is": round(M['is_sharpe'] or 0, 4),
    "sharpe_oos": round(M['oos_sharpe'] or 0, 4), "total_return": round(M['total_return'] or 0, 4),
    "max_drawdown": round(M['max_dd'] or 0, 4), "total_trades": M['trades'],
    "win_rate": round(M['win_rate'] or 0, 1), "profit_factor": round(M['pf'] or 0, 2) if M['pf'] else None,
    "notes": NOTES, "export_path": STRAT_DIR,
}])
if os.path.exists(log_path):
    log_combined = pd.concat([pd.read_csv(log_path), log_entry], ignore_index=True)
else:
    log_combined = log_entry
log_combined.to_csv(log_path, index=False)
print(f"\u2705 run_log.csv ({len(log_combined)} runs)")

# ════════════════════════════════════════════════════════════════
# 2. GENERATE PDF TEARSHEET
# ════════════════════════════════════════════════════════════════
pdf_path = os.path.join(LATEST_DIR, "tearsheet.pdf")
pdf_archive = os.path.join(ARCHIVE_DIR, f"{RUN_ID}_tearsheet.pdf")

fmt = lambda v, d=2: f"{v:.{d}f}" if v is not None and not np.isnan(v) else "N/A"
fmtp = lambda v: f"{v:.2%}" if v is not None and not np.isnan(v) else "N/A"

with PdfPages(pdf_path) as pdf:

    # ── PAGE 1: Summary Metrics ──
    fig, ax = plt.subplots(figsize=(11, 8.5))
    ax.axis('off')
    fig.patch.set_facecolor('#0d0d1a')

    # Title
    ax.text(0.5, 0.95, f"STRATEGY TEARSHEET", ha='center', va='top', fontsize=22,
            fontweight='bold', color='white', transform=ax.transAxes)
    ax.text(0.5, 0.90, f"{STRATEGY_NAME}  |  {TICKER}  |  {param_str}", ha='center', va='top',
            fontsize=13, color='#8888cc', transform=ax.transAxes, family='monospace')
    ax.text(0.5, 0.86, f"{full_close.index[0].date()} to {full_close.index[-1].date()}  |  {len(full_close)} bars  |  Run: {RUN_ID}",
            ha='center', va='top', fontsize=10, color='#6a6a8a', transform=ax.transAxes)

    # Metrics table
    rows = [
        ["METRIC", "FULL SAMPLE", "IN-SAMPLE", "OUT-OF-SAMPLE", "BUY & HOLD"],
        ["Total Return", fmtp(M['total_return']), fmtp(M['is_return']), fmtp(M['oos_return']), fmtp(M['bh_return'])],
        ["Sharpe Ratio", fmt(M['sharpe'], 3), fmt(M['is_sharpe'], 3), fmt(M['oos_sharpe'], 3), fmt(M['bh_sharpe'], 3)],
        ["Sortino Ratio", fmt(M['sortino'], 3), "—", "—", "—"],
        ["Max Drawdown", fmtp(M['max_dd']), fmtp(M['is_dd']), fmtp(M['oos_dd']), fmtp(M['bh_dd'])],
        ["Calmar Ratio", fmt(M['calmar'], 3), "—", "—", "—"],
        ["Volatility", fmtp(M['volatility']), "—", "—", "—"],
        ["Win Rate", f"{M['win_rate']:.1f}%" if M['win_rate'] else "N/A", "—", "—", "—"],
        ["Profit Factor", fmt(M['pf']), "—", "—", "—"],
        ["Expectancy", fmt(M['expectancy'], 4), "—", "—", "—"],
        ["Payoff Ratio", fmt(M['payoff']), "—", "—", "—"],
        ["Total Trades", str(M['trades']), str(M['is_trades']), str(M['oos_trades']), "1"],
        ["Trades/Year", fmt(M['trades_yr'], 1), "—", "—", "—"],
        ["Avg Win", fmtp(M['avg_win']), "—", "—", "—"],
        ["Avg Loss", fmtp(M['avg_loss']), "—", "—", "—"],
        ["Largest Win", fmtp(M['largest_win']), "—", "—", "—"],
        ["Largest Loss", fmtp(M['largest_loss']), "—", "—", "—"],
    ]

    table = ax.table(cellText=rows[1:], colLabels=rows[0], cellLoc='center', loc='center',
                     bbox=[0.02, 0.03, 0.96, 0.78])
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor('#2a2a4a')
        if row == 0:
            cell.set_facecolor('#1a1a3e')
            cell.set_text_props(color='white', fontweight='bold', fontsize=8)
        else:
            cell.set_facecolor('#111128' if row % 2 == 0 else '#0d0d1a')
            cell.set_text_props(color='#d0d0e8', fontsize=8, family='monospace')
        cell.set_height(0.055)

    pdf.savefig(fig, facecolor='#0d0d1a')
    plt.close(fig)

    # ── PAGE 2: Equity Curve + Drawdown ──
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8.5), gridspec_kw={'height_ratios': [3, 1]})
    fig.patch.set_facecolor('#0d0d1a')
    fig.suptitle(f'{STRATEGY_NAME} on {TICKER} — Equity & Drawdown', fontsize=14, fontweight='bold', color='white')

    eq_strat = pf_full.value(); eq_bh = pf_bh.value()
    ax1.plot(full_close.index[:split_idx], eq_strat.iloc[:split_idx].values, color='#3498db', linewidth=1.5, label='Strategy (IS)')
    ax1.plot(full_close.index[split_idx:], eq_strat.iloc[split_idx:].values, color='#e67e22', linewidth=1.5, label='Strategy (OOS)')
    ax1.plot(full_close.index, eq_bh.values, color='gray', linewidth=1, alpha=0.5, linestyle='--', label='Buy & Hold')
    ax1.axvline(x=full_close.index[split_idx], color='red', linestyle=':', alpha=0.4)
    ax1.set_facecolor('#0d0d1a'); ax1.tick_params(colors='#8888aa'); ax1.grid(True, alpha=0.15, color='#333')
    ax1.set_ylabel('Portfolio Value ($)', color='#8888aa'); ax1.legend(fontsize=8, facecolor='#111128', edgecolor='#333', labelcolor='#d0d0e8')
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))
    for spine in ax1.spines.values(): spine.set_color('#2a2a4a')

    # Stats box on equity chart
    stats_text = f"Sharpe: {fmt(M['sharpe'],3)}  |  Return: {fmtp(M['total_return'])}  |  MaxDD: {fmtp(M['max_dd'])}  |  WR: {M['win_rate']:.1f}%  |  PF: {fmt(M['pf'])}"
    ax1.text(0.5, 0.02, stats_text, transform=ax1.transAxes, fontsize=8, ha='center', color='#aaa', family='monospace',
             bbox=dict(boxstyle='round,pad=0.4', facecolor='#111128', edgecolor='#2a2a4a', alpha=0.9))

    dd = pf_full.drawdown() * 100
    ax2.fill_between(full_close.index, dd.values, 0, color='#e74c3c', alpha=0.5)
    ax2.set_facecolor('#0d0d1a'); ax2.tick_params(colors='#8888aa'); ax2.grid(True, alpha=0.15, color='#333')
    ax2.set_ylabel('Drawdown %', color='#8888aa'); ax2.set_xlabel('Date', color='#8888aa')
    for spine in ax2.spines.values(): spine.set_color('#2a2a4a')

    plt.tight_layout()
    pdf.savefig(fig, facecolor='#0d0d1a')
    plt.close(fig)

    # ── PAGE 3: Trade Analysis ──
    if len(tr) > 0:
        fig, axes = plt.subplots(2, 2, figsize=(11, 8.5))
        fig.patch.set_facecolor('#0d0d1a')
        fig.suptitle(f'Trade-by-Trade Analysis — {len(tr)} Trades', fontsize=14, fontweight='bold', color='white')

        n = len(tr)
        colors_bar = ['#2ca02c' if r > 0 else '#e74c3c' for r in tr]
        colors_pnl = ['#2ca02c' if p > 0 else '#e74c3c' for p in pnl]

        for a in axes.flat:
            a.set_facecolor('#0d0d1a'); a.tick_params(colors='#8888aa'); a.grid(True, alpha=0.15, color='#333')
            for spine in a.spines.values(): spine.set_color('#2a2a4a')

        axes[0,0].bar(range(n), tr*100, color=colors_bar, edgecolor='none', width=0.8)
        axes[0,0].axhline(np.mean(tr)*100, color='#3498db', linestyle='--', linewidth=1.5)
        axes[0,0].set_title('Trade Returns (%)', color='white', fontsize=10); axes[0,0].set_xlabel('Trade #', color='#8888aa')

        axes[0,1].bar(range(n), pnl, color=colors_pnl, edgecolor='none', width=0.8)
        axes[0,1].axhline(np.mean(pnl), color='#3498db', linestyle='--', linewidth=1.5)
        axes[0,1].set_title('Trade P&L ($)', color='white', fontsize=10); axes[0,1].yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))

        cum_pnl = np.cumsum(pnl)
        axes[1,0].plot(range(1, n+1), cum_pnl, color='#3498db', linewidth=2, marker='o', markersize=3)
        axes[1,0].fill_between(range(1, n+1), cum_pnl, 0, where=cum_pnl>=0, alpha=0.15, color='green')
        axes[1,0].fill_between(range(1, n+1), cum_pnl, 0, where=cum_pnl<0, alpha=0.15, color='red')
        axes[1,0].set_title('Cumulative P&L', color='white', fontsize=10); axes[1,0].yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))

        axes[1,1].hist(tr*100, bins=min(30, max(10, n//3)), color='#3498db', edgecolor='#1a1a2e', alpha=0.8)
        axes[1,1].axvline(np.mean(tr)*100, color='#e74c3c', linestyle='--', linewidth=2)
        axes[1,1].set_title('Return Distribution', color='white', fontsize=10); axes[1,1].set_xlabel('Return %', color='#8888aa')

        plt.tight_layout()
        pdf.savefig(fig, facecolor='#0d0d1a')
        plt.close(fig)

    # ── PAGE 4: Monte Carlo FTMO ──
    dr = daily_rets.values.ravel(); dr = dr[~np.isnan(dr)]
    N_SIM = 5000; DAYS = 30; ACCOUNT = 100000
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
        if s < 150: sample_paths.append(path)

    n_still = N_SIM - n_passed - n_blown_t - n_blown_d
    pass_rate = n_passed / N_SIM * 100

    fig, ax = plt.subplots(figsize=(11, 8.5))
    fig.patch.set_facecolor('#0d0d1a'); ax.set_facecolor('#0d0d1a')
    for spine in ax.spines.values(): spine.set_color('#2a2a4a')
    ax.tick_params(colors='#8888aa'); ax.grid(True, alpha=0.15, color='#333')

    for path in sample_paths:
        c = '#2ca02c' if path[-1] >= 110000 else ('#e74c3c' if path[-1] <= 90000 else '#555555')
        ax.plot(range(DAYS+1), path, color=c, alpha=0.25, linewidth=0.5)
    ax.axhline(110000, color='#2ca02c', linestyle='--', linewidth=2.5, label=f'10% Target ($110k)')
    ax.axhline(90000, color='#e74c3c', linestyle='--', linewidth=2.5, label=f'10% Max Loss ($90k)')
    ax.axhline(100000, color='white', linestyle='-', linewidth=0.5, alpha=0.3)

    verdict = "FAVORABLE" if pass_rate >= 50 else "POSSIBLE" if pass_rate >= 25 else "CHALLENGING" if pass_rate >= 10 else "UNLIKELY"
    emoji = "\U0001f7e2" if pass_rate >= 50 else "\U0001f7e1" if pass_rate >= 25 else "\U0001f7e0" if pass_rate >= 10 else "\U0001f534"

    ax.set_title(f'FTMO Monte Carlo — {N_SIM:,} Simulations  |  Pass Rate: {pass_rate:.1f}% ({verdict})', fontsize=14, fontweight='bold', color='white')
    ax.set_xlabel('Trading Day', color='#8888aa'); ax.set_ylabel('Equity ($)', color='#8888aa')
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))
    ax.legend(fontsize=10, facecolor='#111128', edgecolor='#333', labelcolor='#d0d0e8')

    mc_text = (f"Passed: {n_passed:,} ({n_passed/N_SIM*100:.1f}%)  |  "
               f"Blown Total: {n_blown_t:,}  |  Blown Daily: {n_blown_d:,}  |  "
               f"Still Trading: {n_still:,}  |  Median Final: ${np.median(final_eqs):,.0f}")
    ax.text(0.5, 0.02, mc_text, transform=ax.transAxes, fontsize=8, ha='center', color='#aaa', family='monospace',
            bbox=dict(boxstyle='round,pad=0.4', facecolor='#111128', edgecolor='#2a2a4a', alpha=0.9))

    plt.tight_layout()
    pdf.savefig(fig, facecolor='#0d0d1a')
    plt.close(fig)

# Copy PDF to archive
import shutil
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
print(f"\U0001f4e6 EXPORT COMPLETE — {STRATEGY_NAME} on {TICKER}")
print(f"{'='*70}")
print(f"  Run ID:       {RUN_ID}")
print(f"  Timestamp:    {RUN_TIMESTAMP.strftime('%B %d, %Y at %I:%M:%S %p')}")
print(f"  Instrument:   {TICKER} ({export_json['metadata']['instrument_type']})")
print(f"  Params:       {param_str}")
print(f"  Sharpe:       {fmt(M['sharpe'],3)} (IS: {fmt(M['is_sharpe'],3)} -> OOS: {fmt(M['oos_sharpe'],3)})")
print(f"  FTMO Verdict: {verdict} ({pass_rate:.1f}% pass rate)")
print(f"{'='*70}")
print(f"\n\U0001f4c2 {STRAT_DIR}/")
print(f"  \u251c\u2500\u2500 latest/")
print(f"  \u2502   \u251c\u2500\u2500 summary.json")
print(f"  \u2502   \u251c\u2500\u2500 daily_returns.csv")
print(f"  \u2502   \u251c\u2500\u2500 trades.csv")
print(f"  \u2502   \u251c\u2500\u2500 grid_results.csv")
print(f"  \u2502   \u2514\u2500\u2500 tearsheet.pdf       \u2190 Share this with Claude!")
print(f"  \u2514\u2500\u2500 archive/")
print(f"      \u251c\u2500\u2500 {RUN_ID}_summary.json")
print(f"      \u2514\u2500\u2500 {RUN_ID}_tearsheet.pdf")
print(f"\n\U0001f4cb run_log.csv ({len(log_combined)} total runs)")
print(f"\n\U0001f4a1 To get my analysis: upload the tearsheet.pdf to our chat.")
print(f"   For deeper analysis: also upload summary.json + daily_returns.csv")
