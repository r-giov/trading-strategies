"""Backtest endpoints — run single-ticker backtests via the web API."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.backtest_service import run_backtest

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    strategy: str = Field(..., description="Strategy name: MACD_Crossover, Donchian_Breakout, EMA_Crossover, Supertrend")
    ticker: str = Field(..., description="yfinance ticker symbol, e.g. SPY, BTC-USD")
    start_date: str = Field("2015-01-01", description="Start date for data download (YYYY-MM-DD)")
    params: dict = Field(default_factory=dict, description="Strategy-specific parameters")
    init_cash: float = Field(100_000, description="Initial cash for backtest")
    fees: float = Field(0.0005, description="Commission/fees as decimal")
    train_ratio: float = Field(0.60, ge=0.1, le=0.95, description="IS/OOS split ratio")


@router.post("/run")
def run_backtest_endpoint(req: BacktestRequest):
    """Run a single-ticker backtest and return equity curve, metrics, and trade log."""
    result = run_backtest(
        strategy=req.strategy,
        ticker=req.ticker,
        start_date=req.start_date,
        params=req.params,
        init_cash=req.init_cash,
        fees=req.fees,
        train_ratio=req.train_ratio,
    )

    if "error" in result:
        return {"status": "error", **result}

    return {"status": "ok", **result}
