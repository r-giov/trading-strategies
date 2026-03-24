"""
Wraps live/signals.py for the web API.
Caches yfinance calls to avoid hammering the API on every request.
"""

import time
import json
from typing import Any

import numpy as np
import deps  # noqa: F401 — triggers sys.path setup

from signals import get_portfolio_signals_yfinance, aggregate_signals
from config import PORTFOLIO, ACCOUNT_SIZE, PROFIT_TARGET, MAX_DAILY_LOSS, MAX_TOTAL_LOSS, SYMBOLS

# Simple TTL cache for signals (5 min)
_cache: dict[str, Any] = {"data": None, "ts": 0}
CACHE_TTL = 300  # seconds


def _sanitize(obj):
    """Convert numpy types to native Python for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def get_signals(force_refresh: bool = False) -> dict:
    """Get portfolio signals, cached for 5 minutes."""
    now = time.time()
    if not force_refresh and _cache["data"] and (now - _cache["ts"]) < CACHE_TTL:
        return _cache["data"]

    component_signals = get_portfolio_signals_yfinance()
    aggregated = aggregate_signals(component_signals)

    result = _sanitize({
        "components": list(component_signals.values()),
        "aggregated": {
            sym: agg for sym, agg in aggregated.items()
        },
        "timestamp": component_signals[next(iter(component_signals))]["timestamp"]
        if component_signals else None,
    })

    _cache["data"] = result
    _cache["ts"] = now
    return result


def get_portfolio_config() -> dict:
    """Return portfolio configuration for the frontend."""
    components = []
    for comp in PORTFOLIO:
        components.append({
            "id": comp["id"],
            "symbol": comp["symbol"],
            "yf_ticker": comp["yf_ticker"],
            "strategy": comp["strategy"],
            "weight": comp["weight"],
            "oos_sharpe": comp.get("oos_sharpe"),
            "ftmo_pass_rate": comp.get("ftmo_pass_rate"),
        })

    return {
        "account_size": ACCOUNT_SIZE,
        "profit_target": PROFIT_TARGET,
        "max_daily_loss": MAX_DAILY_LOSS,
        "max_total_loss": MAX_TOTAL_LOSS,
        "symbols": SYMBOLS,
        "components": components,
    }
