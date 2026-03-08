"""
Regime Filter — Classify market regimes using backward-looking data only.

No lookahead bias: every regime label on day T uses only data from T-1 and earlier.

Regimes are classified on two dimensions:
  1. TREND:      Bull / Bear  (price vs SMA)
  2. VOLATILITY: High / Low   (realized vol vs its rolling median)

Combined into 4 regimes:
  - BULL_CALM:   Trending up, low vol   → Best for trend-following (MACD, EMA, Donchian)
  - BULL_WILD:   Trending up, high vol  → Trend-following works but size down
  - BEAR_CALM:   Trending down, low vol → Mean-reversion or stay flat
  - BEAR_WILD:   Crisis mode, high vol  → Stay out or crisis alpha strategies only

Usage:
    from lib.regime_filter import classify_regimes, regime_summary

    regimes = classify_regimes(close_series, trend_period=200, vol_window=21, vol_lookback=126)
    regime_summary(regimes)

    # Filter your signals:
    entries = entries & (regimes['regime'].shift(1) == 'BULL_CALM')  # only trade in bull+calm
"""

import numpy as np
import pandas as pd


def realized_volatility(close, window=21):
    """Annualized realized volatility over trailing window. Uses log returns."""
    log_rets = np.log(close / close.shift(1))
    return log_rets.rolling(window=window).std() * np.sqrt(252)


def classify_regimes(close, trend_period=200, vol_window=21, vol_lookback=126):
    """
    Classify each day into a regime using ONLY backward-looking data.

    All indicators are shifted by 1 so the regime on day T is computed from day T-1's close.
    This means you can safely use regime[T] to filter signals on day T with zero lookahead.

    Parameters:
    -----------
    close : pd.Series
        Daily close prices with DatetimeIndex
    trend_period : int
        SMA period for trend classification (default 200 = ~1 year)
    vol_window : int
        Rolling window for realized volatility (default 21 = ~1 month)
    vol_lookback : int
        Rolling window for vol median (default 126 = ~6 months)
        Vol is "high" if current > rolling median of vol

    Returns:
    --------
    pd.DataFrame with columns:
        close, sma, trend ('BULL'/'BEAR'),
        realized_vol, vol_median, vol_regime ('HIGH'/'LOW'),
        regime ('BULL_CALM'/'BULL_WILD'/'BEAR_CALM'/'BEAR_WILD'),
        regime_code (0-3 int)
    """
    close = close.astype(float).squeeze()
    close.name = 'close'

    # Trend: price vs SMA (shifted 1 bar — use yesterday's close vs yesterday's SMA)
    sma = close.rolling(window=trend_period).mean()

    # Use previous day's values for classification
    prev_close = close.shift(1)
    prev_sma = sma.shift(1)
    trend = pd.Series(np.where(prev_close > prev_sma, 'BULL', 'BEAR'),
                       index=close.index, name='trend')

    # Volatility: realized vol vs its own rolling median (all shifted 1 bar)
    rvol = realized_volatility(close, window=vol_window).shift(1)
    vol_median = rvol.rolling(window=vol_lookback).median()
    vol_regime = pd.Series(np.where(rvol > vol_median, 'HIGH', 'LOW'),
                            index=close.index, name='vol_regime')

    # Combined regime
    regime = pd.Series(
        np.where(
            (trend == 'BULL') & (vol_regime == 'LOW'), 'BULL_CALM',
            np.where(
                (trend == 'BULL') & (vol_regime == 'HIGH'), 'BULL_WILD',
                np.where(
                    (trend == 'BEAR') & (vol_regime == 'LOW'), 'BEAR_CALM',
                    'BEAR_WILD'
                )
            )
        ),
        index=close.index,
        name='regime'
    )

    regime_code = regime.map({
        'BULL_CALM': 0, 'BULL_WILD': 1,
        'BEAR_CALM': 2, 'BEAR_WILD': 3
    }).astype(float)

    return pd.DataFrame({
        'close': close,
        'sma': sma,
        'trend': trend,
        'realized_vol': rvol,
        'vol_median': vol_median,
        'vol_regime': vol_regime,
        'regime': regime,
        'regime_code': regime_code
    })


def regime_summary(df):
    """Print a summary of regime distribution and per-regime return stats."""
    # Daily returns
    rets = df['close'].pct_change()
    df = df.copy()
    df['daily_return'] = rets

    valid = df.dropna(subset=['regime', 'daily_return'])

    print("=" * 70)
    print("REGIME DISTRIBUTION")
    print("=" * 70)
    counts = valid['regime'].value_counts()
    total = len(valid)
    for regime in ['BULL_CALM', 'BULL_WILD', 'BEAR_CALM', 'BEAR_WILD']:
        n = counts.get(regime, 0)
        pct = n / total * 100 if total > 0 else 0
        bar = '#' * int(pct / 2)
        print(f"  {regime:12s}  {n:5d} days ({pct:5.1f}%)  {bar}")

    print(f"\n  Total classified: {total} days")
    print(f"  Date range: {valid.index[0].date()} to {valid.index[-1].date()}")

    print("\n" + "=" * 70)
    print("PER-REGIME RETURN STATISTICS (annualized)")
    print("=" * 70)
    print(f"  {'Regime':12s} {'Ann Return':>12s} {'Ann Vol':>10s} {'Sharpe':>8s} {'MaxDD':>8s} {'Days':>6s}")
    print("  " + "-" * 58)

    for regime in ['BULL_CALM', 'BULL_WILD', 'BEAR_CALM', 'BEAR_WILD']:
        subset = valid[valid['regime'] == regime]['daily_return']
        if len(subset) < 5:
            print(f"  {regime:12s}  {'insufficient data':>50s}")
            continue
        ann_ret = subset.mean() * 252
        ann_vol = subset.std() * np.sqrt(252)
        sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
        cum = (1 + subset).cumprod()
        max_dd = ((cum / cum.cummax()) - 1).min()
        print(f"  {regime:12s} {ann_ret:>11.1%} {ann_vol:>9.1%} {sharpe:>7.2f} {max_dd:>7.1%} {len(subset):>6d}")

    print("\n  INTERPRETATION:")
    print("  - BULL_CALM:  Best regime for trend-following. Go full size.")
    print("  - BULL_WILD:  Trends work but expect whipsaws. Reduce size.")
    print("  - BEAR_CALM:  Grinding down. Mean-reversion or flat.")
    print("  - BEAR_WILD:  Crisis. Stay out or use crisis-alpha strategies.")

    return valid


def strategy_returns_by_regime(strategy_returns, regimes_df):
    """
    Break down strategy performance by regime.

    Parameters:
    -----------
    strategy_returns : pd.Series
        Daily strategy returns (from vectorbt pf.returns())
    regimes_df : pd.DataFrame
        Output of classify_regimes()

    Returns:
    --------
    pd.DataFrame with per-regime performance
    """
    combined = pd.DataFrame({
        'strategy_return': strategy_returns,
        'regime': regimes_df['regime']
    }).dropna()

    results = []
    for regime in ['BULL_CALM', 'BULL_WILD', 'BEAR_CALM', 'BEAR_WILD']:
        subset = combined[combined['regime'] == regime]['strategy_return']
        if len(subset) < 5:
            continue
        ann_ret = subset.mean() * 252
        ann_vol = subset.std() * np.sqrt(252)
        sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
        cum = (1 + subset).cumprod()
        max_dd = ((cum / cum.cummax()) - 1).min()
        win_rate = (subset > 0).mean() * 100
        results.append({
            'regime': regime, 'days': len(subset),
            'ann_return': ann_ret, 'ann_vol': ann_vol,
            'sharpe': sharpe, 'max_dd': max_dd, 'win_rate': win_rate
        })

    return pd.DataFrame(results)
