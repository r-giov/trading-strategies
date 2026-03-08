"""
Alpaca Market Data Helper
─────────────────────────
Drop-in replacement for yfinance with better historical data.
Free tier: 5+ years of 1-min bars, unlimited daily data.

Usage (in notebooks):
    from lib.alpaca_data import get_bars, get_multi_bars

    # Single ticker — returns same DataFrame format as yfinance
    df = get_bars('QQQ', '2018-01-01', timeframe='1Day')

    # Multiple tickers
    all_data = get_multi_bars(['QQQ', 'SPY', 'NVDA'], '2018-01-01')

    # Intraday (1-min bars, up to 5+ years)
    df_1m = get_bars('QQQ', '2024-01-01', timeframe='1Min')
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ── Load API keys from .env ──
def _load_env():
    """Load .env file from repo root or parent directories."""
    env_paths = [
        os.path.join(os.path.dirname(__file__), '..', '.env'),     # trading-strategies/.env
        os.path.join(os.getcwd(), '.env'),                          # cwd
        '/content/trading-strategies/.env',                         # Colab
    ]
    for p in env_paths:
        p = os.path.abspath(p)
        if os.path.exists(p):
            with open(p, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, val = line.split('=', 1)
                        os.environ.setdefault(key.strip(), val.strip())
            return True
    return False

_load_env()

API_KEY    = os.environ.get('ALPACA_API_KEY', '')
SECRET_KEY = os.environ.get('ALPACA_SECRET_KEY', '')
BASE_URL   = os.environ.get('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')

# Data API is separate from trading API
DATA_URL = 'https://data.alpaca.markets'

# ── Timeframe mapping ──
TIMEFRAME_MAP = {
    '1Min': '1Min', '1m': '1Min', '1min': '1Min',
    '5Min': '5Min', '5m': '5Min', '5min': '5Min',
    '15Min': '15Min', '15m': '15Min', '15min': '15Min',
    '30Min': '30Min', '30m': '30Min', '30min': '30Min',
    '1Hour': '1Hour', '1h': '1Hour', '1hour': '1Hour',
    '1Day': '1Day', '1d': '1Day', '1day': '1Day', 'D': '1Day', 'daily': '1Day',
    '1Week': '1Week', '1w': '1Week', 'W': '1Week',
    '1Month': '1Month', '1M': '1Month', 'M': '1Month',
}


def _get_headers():
    """Auth headers for Alpaca API."""
    if not API_KEY or not SECRET_KEY:
        raise ValueError(
            "Alpaca API keys not found. Set ALPACA_API_KEY and ALPACA_SECRET_KEY "
            "in .env file or environment variables."
        )
    return {
        'APCA-API-KEY-ID': API_KEY,
        'APCA-API-SECRET-KEY': SECRET_KEY,
    }


def get_bars(ticker, start_date, end_date=None, timeframe='1Day', limit=None):
    """
    Fetch historical bars from Alpaca.

    Args:
        ticker: Symbol (e.g., 'QQQ', 'AAPL')
        start_date: Start date string 'YYYY-MM-DD'
        end_date: End date string (default: today)
        timeframe: '1Min', '5Min', '15Min', '1Hour', '1Day', '1Week', '1Month'
                   Also accepts shortcuts: '1m', '5m', '1h', '1d', 'D', etc.
        limit: Max bars per request (default: 10000, max: 10000)

    Returns:
        DataFrame with columns: Open, High, Low, Close, Volume
        Index: DatetimeIndex (timezone-naive, same as yfinance)
    """
    import requests

    tf = TIMEFRAME_MAP.get(timeframe, timeframe)
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')

    # Use SIP for historical data (pre-2020), IEX for recent data
    # Free tier: SIP blocked for recent data, IEX only goes back to ~mid-2020
    # Strategy: try SIP first for old data, fall back to IEX on permission error
    sip_cutoff = '2020-06-01'
    feeds_to_try = ['sip', 'iex'] if start_date < sip_cutoff else ['iex']

    all_bars = []

    for feed in feeds_to_try:
        page_token = None
        feed_start = start_date
        feed_end = end_date

        # If using SIP for old data + IEX for recent, split the ranges
        if len(feeds_to_try) == 2:
            if feed == 'sip':
                feed_end = sip_cutoff
            elif feed == 'iex':
                feed_start = sip_cutoff

        while True:
            params = {
                'start': f'{feed_start}T00:00:00Z',
                'end': f'{feed_end}T23:59:59Z',
                'timeframe': tf,
                'limit': limit or 10000,
                'adjustment': 'split',
                'feed': feed,
            }
            if page_token:
                params['page_token'] = page_token

            url = f'{DATA_URL}/v2/stocks/{ticker}/bars'
            resp = requests.get(url, headers=_get_headers(), params=params)

            if resp.status_code == 403 and 'subscription' in resp.text.lower():
                # SIP not available — skip to IEX
                break
            elif resp.status_code != 200:
                error_msg = resp.text
                if resp.status_code == 403:
                    raise PermissionError(f"Alpaca API auth failed. Check your API keys. ({error_msg})")
                elif resp.status_code == 422:
                    raise ValueError(f"Invalid request params for {ticker}: {error_msg}")
                else:
                    raise RuntimeError(f"Alpaca API error {resp.status_code}: {error_msg}")

            data = resp.json()
            bars = data.get('bars', [])
            if not bars:
                break

            all_bars.extend(bars)
            page_token = data.get('next_page_token')
            if not page_token:
                break

    if not all_bars:
        print(f"  {ticker}: No data returned from Alpaca")
        return pd.DataFrame()

    df = pd.DataFrame(all_bars)
    df = df.rename(columns={
        't': 'Date', 'o': 'Open', 'h': 'High', 'l': 'Low',
        'c': 'Close', 'v': 'Volume', 'n': 'TradeCount', 'vw': 'VWAP'
    })

    df['Date'] = pd.to_datetime(df['Date'])
    df = df.set_index('Date')
    df.index = df.index.tz_localize(None)  # strip timezone to match yfinance
    df = df.sort_index()

    # Keep only standard OHLCV columns (+ VWAP as bonus)
    keep_cols = [c for c in ['Open', 'High', 'Low', 'Close', 'Volume', 'VWAP'] if c in df.columns]
    df = df[keep_cols]

    # Ensure numeric types
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    print(f"  {ticker}: {len(df)} bars ({df.index[0].date()} to {df.index[-1].date()}) via Alpaca")
    return df


def get_multi_bars(tickers, start_date, end_date=None, timeframe='1Day'):
    """
    Fetch bars for multiple tickers.

    Returns:
        dict of {ticker: DataFrame} — same format as the all_data dict
        used in v2 notebooks.
    """
    all_data = {}
    for t in tickers:
        try:
            df = get_bars(t, start_date, end_date, timeframe)
            if not df.empty:
                all_data[t] = df
        except Exception as e:
            print(f"  {t}: FAILED — {e}")
    return all_data


def compare_with_yfinance(ticker, start_date):
    """
    Quick comparison of Alpaca vs yfinance data for a ticker.
    Useful for validating the data source switch.
    """
    try:
        import yfinance as yf
    except ImportError:
        print("yfinance not installed, skipping comparison")
        return

    print(f"\nComparing {ticker} from {start_date}:")
    print("-" * 50)

    # Alpaca
    df_a = get_bars(ticker, start_date)
    # yfinance
    df_y = yf.download(ticker, start=start_date, interval='1d')
    if isinstance(df_y.columns, pd.MultiIndex):
        df_y.columns = [c[0] for c in df_y.columns]

    print(f"  Alpaca:   {len(df_a)} bars")
    print(f"  yfinance: {len(df_y)} bars")

    # Compare overlapping dates
    common = df_a.index.intersection(df_y.index)
    if len(common) > 0:
        close_diff = (df_a.loc[common, 'Close'] - df_y.loc[common, 'Close']).abs()
        print(f"  Overlapping days: {len(common)}")
        print(f"  Mean Close diff:  ${close_diff.mean():.4f}")
        print(f"  Max Close diff:   ${close_diff.max():.4f}")
        pct_diff = (close_diff / df_y.loc[common, 'Close'] * 100)
        print(f"  Mean % diff:      {pct_diff.mean():.4f}%")
    else:
        print("  No overlapping dates found")
