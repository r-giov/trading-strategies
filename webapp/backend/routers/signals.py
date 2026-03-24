"""Signal endpoints — wraps live trading signal engine."""

from fastapi import APIRouter, Query

from services.signal_service import get_signals, get_portfolio_config

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("/portfolio")
def portfolio_signals(refresh: bool = Query(False)):
    """Get current signals for all portfolio components."""
    return get_signals(force_refresh=refresh)


@router.get("/config")
def portfolio_config():
    """Get portfolio configuration (FTMO rules, components)."""
    return get_portfolio_config()
