"""Export endpoints — reads strategy_exports/ directory."""

from fastapi import APIRouter, HTTPException

from services.export_reader import list_strategies, get_strategy_detail

router = APIRouter(prefix="/api/exports", tags=["exports"])


@router.get("/strategies")
def strategies():
    """List all strategies with their latest metrics."""
    return list_strategies()


@router.get("/strategies/{strategy}/{ticker}")
def strategy_detail(strategy: str, ticker: str):
    """Get full detail for a specific strategy-ticker pair."""
    detail = get_strategy_detail(strategy, ticker)
    if detail is None:
        raise HTTPException(status_code=404, detail="Strategy-ticker not found")
    return detail
