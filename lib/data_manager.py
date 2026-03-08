"""
QS Finance — Unified Data Manager
──────────────────────────────────
Smart data fetching: yfinance for daily, Alpaca for intraday.
Works seamlessly in Colab (secrets) and local (.env).

Usage (in notebooks — just replace yf.download):
    from lib.data_manager import download, download_multi

    # Daily data — uses yfinance (20+ years of history)
    df = download('QQQ', '2018-01-01')

    # Intraday — uses Alpaca (months of 1-min data)
    df = download('QQQ', '2024-01-01', timeframe='1h')
    df = download('QQQ', '2025-01-01', timeframe='1m')

    # Multi-ticker
    all_data = download_multi(['QQQ', 'SPY', 'NVDA'], '2018-01-01')

Setup (one-time):
    Local:  API keys in trading-strategies/.env
    Colab:  Add ALPACA_API_KEY and ALPACA_SECRET_KEY in Colab Secrets
            (left sidebar key icon), then run setup_colab_secrets()
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime

# ═══════════════════════════════════════════════════════
# API Key Loading — supports .env, Colab Secrets, env vars
# ═══════════════════════════════════════════════════════

def _load_dotenv():
    """Load .env file from repo root."""
    env_paths = [
        os.path.join(os.path.dirname(__file__), '..', '.env'),
        os.path.join(os.getcwd(), '.env'),
        '/content/trading-strategies/.env',
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


def _load_colab_secrets():
    """Load API keys from Google Colab Secrets (built-in feature)."""
    try:
        from google.colab import userdata
        key = userdata.get('ALPACA_API_KEY')
        secret = userdata.get('ALPACA_SECRET_KEY')
        if key and secret:
            os.environ.setdefault('ALPACA_API_KEY', key)
            os.environ.setdefault('ALPACA_SECRET_KEY', secret)
            return True
    except (ImportError, Exception):
        pass
    return False


def setup_keys():
    """
    Load API keys from all sources (in priority order):
    1. Environment variables (already set)
    2. Google Colab Secrets
    3. .env file
    """
    if os.environ.get('ALPACA_API_KEY') and os.environ.get('ALPACA_SECRET_KEY'):
        return True
    if _load_colab_secrets():
        return True
    if _load_dotenv():
        return True
    return False


# Auto-load on import
_keys_loaded = setup_keys()

# ═══════════════════════════════════════════════════════
# Colab setup helper
# ═══════════════════════════════════════════════════════

def setup_colab_secrets():
    """
    Interactive setup for Google Colab.
    Call this once — it tells you exactly what to do.
    """
    in_colab = 'google.colab' in __import__('sys').modules

    if not in_colab:
        print("Not in Colab. Use .env file instead.")
        print("Your .env is at: trading-strategies/.env")
        return

    # Check if secrets already work
    try:
        from google.colab import userdata
        key = userdata.get('ALPACA_API_KEY')
        if key:
            print("Alpaca keys already configured in Colab Secrets!")
            return
    except Exception:
        pass

    print("=" * 60)
    print("COLAB SECRETS SETUP")
    print("=" * 60)
    print()
    print("1. Click the KEY icon in the left sidebar")
    print("2. Add two secrets:")
    print("   Name: ALPACA_API_KEY")
    print("   Value: (your Alpaca API key)")
    print()
    print("   Name: ALPACA_SECRET_KEY")
    print("   Value: (your Alpaca secret key)")
    print()
    print("3. Toggle 'Notebook access' ON for both")
    print("4. Re-run this cell")
    print("=" * 60)


# ═══════════════════════════════════════════════════════
# Smart Download — picks best source automatically
# ═══════════════════════════════════════════════════════

# Timeframes that need Alpaca (intraday)
_INTRADAY_TFS = {'1m', '1min', '1Min', '5m', '5min', '5Min',
                 '15m', '15min', '15Min', '30m', '30min', '30Min',
                 '1h', '1hour', '1Hour'}

# Alpaca timeframe normalization
_TF_MAP = {
    '1m': '1Min', '1min': '1Min', '1Min': '1Min',
    '5m': '5Min', '5min': '5Min', '5Min': '5Min',
    '15m': '15Min', '15min': '15Min', '15Min': '15Min',
    '30m': '30Min', '30min': '30Min', '30Min': '30Min',
    '1h': '1Hour', '1hour': '1Hour', '1Hour': '1Hour',
    '1d': '1Day', '1day': '1Day', '1Day': '1Day', 'D': '1Day', 'daily': '1Day',
}


def download(ticker, start_date, end_date=None, timeframe='1d'):
    """
    Smart download — yfinance for daily, Alpaca for intraday.

    Args:
        ticker: Symbol (e.g., 'QQQ', 'AAPL', 'BTC-USD')
        start_date: 'YYYY-MM-DD'
        end_date: 'YYYY-MM-DD' (default: today)
        timeframe: '1d' (daily, yfinance), '1h'/'1m'/'5m' (intraday, Alpaca)

    Returns:
        DataFrame with Open, High, Low, Close, Volume columns.
        Index: DatetimeIndex (timezone-naive).
    """
    if timeframe in _INTRADAY_TFS:
        return _download_alpaca(ticker, start_date, end_date, timeframe)
    else:
        return _download_yfinance(ticker, start_date, end_date)


def download_multi(tickers, start_date, end_date=None, timeframe='1d'):
    """
    Download multiple tickers. Returns dict of {ticker: DataFrame}.

    For daily data: uses yfinance (best history).
    For intraday: uses Alpaca.
    """
    all_data = {}
    for t in tickers:
        try:
            df = download(t, start_date, end_date, timeframe)
            if df is not None and not df.empty:
                all_data[t] = df
        except Exception as e:
            print(f"  {t}: FAILED — {e}")
    return all_data


# ═══════════════════════════════════════════════════════
# yfinance backend (daily data)
# ═══════════════════════════════════════════════════════

def _download_yfinance(ticker, start_date, end_date=None):
    """Fetch daily bars via yfinance."""
    import yfinance as yf

    df = yf.download(ticker, start=start_date, end=end_date, interval='1d')

    if df.empty:
        print(f"  {ticker}: No data from yfinance")
        return pd.DataFrame()

    # Flatten MultiIndex columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]

    print(f"  {ticker}: {len(df)} daily bars ({df.index[0].date()} to {df.index[-1].date()}) via yfinance")
    return df


# ═══════════════════════════════════════════════════════
# Alpaca backend (intraday data)
# ═══════════════════════════════════════════════════════

_DATA_URL = 'https://data.alpaca.markets'


def _get_alpaca_headers():
    """Auth headers for Alpaca API."""
    api_key = os.environ.get('ALPACA_API_KEY', '')
    secret = os.environ.get('ALPACA_SECRET_KEY', '')
    if not api_key or not secret:
        raise ValueError(
            "Alpaca API keys not found.\n"
            "  Local: add them to trading-strategies/.env\n"
            "  Colab: run setup_colab_secrets() for instructions"
        )
    return {
        'APCA-API-KEY-ID': api_key,
        'APCA-API-SECRET-KEY': secret,
    }


def _download_alpaca(ticker, start_date, end_date=None, timeframe='1Hour'):
    """Fetch bars via Alpaca REST API."""
    import requests

    tf = _TF_MAP.get(timeframe, timeframe)
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')

    # Alpaca uses different ticker format than yfinance for crypto
    # yfinance: BTC-USD, Alpaca: BTCUSD
    alpaca_ticker = ticker.replace('-', '')

    all_bars = []
    page_token = None

    while True:
        params = {
            'start': f'{start_date}T00:00:00Z',
            'end': f'{end_date}T23:59:59Z',
            'timeframe': tf,
            'limit': 10000,
            'adjustment': 'split',
            'feed': 'iex',
        }
        if page_token:
            params['page_token'] = page_token

        url = f'{_DATA_URL}/v2/stocks/{alpaca_ticker}/bars'
        resp = requests.get(url, headers=_get_alpaca_headers(), params=params)

        if resp.status_code != 200:
            msg = resp.text
            if resp.status_code == 403:
                raise PermissionError(f"Alpaca auth failed: {msg}")
            elif resp.status_code == 422:
                raise ValueError(f"Bad params for {ticker}: {msg}")
            else:
                raise RuntimeError(f"Alpaca error {resp.status_code}: {msg}")

        data = resp.json()
        bars = data.get('bars', [])
        if not bars:
            break

        all_bars.extend(bars)
        page_token = data.get('next_page_token')
        if not page_token:
            break

    if not all_bars:
        print(f"  {ticker}: No data from Alpaca")
        return pd.DataFrame()

    df = pd.DataFrame(all_bars)
    df = df.rename(columns={
        't': 'Date', 'o': 'Open', 'h': 'High', 'l': 'Low',
        'c': 'Close', 'v': 'Volume', 'n': 'TradeCount', 'vw': 'VWAP'
    })
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.set_index('Date')
    df.index = df.index.tz_localize(None)
    df = df.sort_index()

    keep = [c for c in ['Open', 'High', 'Low', 'Close', 'Volume', 'VWAP'] if c in df.columns]
    df = df[keep]
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    tf_label = timeframe.lower()
    print(f"  {ticker}: {len(df)} {tf_label} bars ({df.index[0]} to {df.index[-1]}) via Alpaca")
    return df
