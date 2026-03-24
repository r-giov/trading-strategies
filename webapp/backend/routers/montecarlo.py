"""Monte Carlo FTMO simulation endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.montecarlo_service import run_monte_carlo, read_daily_returns_from_exports

router = APIRouter(prefix="/api/montecarlo", tags=["montecarlo"])


class MonteCarloRequest(BaseModel):
    strategy: str | None = None
    ticker: str | None = None
    daily_returns: list[float] | None = None
    n_sims: int = 5000


@router.post("/run")
def monte_carlo_run(req: MonteCarloRequest):
    """Run Monte Carlo FTMO simulation.

    Accepts either:
      - { strategy, ticker } to load returns from exports
      - { daily_returns: [...] } to use provided returns directly
    """
    if req.daily_returns and len(req.daily_returns) > 0:
        returns = req.daily_returns
    elif req.strategy and req.ticker:
        try:
            returns = read_daily_returns_from_exports(req.strategy, req.ticker)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either {strategy, ticker} or {daily_returns: [...]}",
        )

    if len(returns) < 5:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least 5 daily returns, got {len(returns)}",
        )

    result = run_monte_carlo(returns, n_sims=req.n_sims)
    return result


@router.get("/from-exports/{strategy}/{ticker}")
def monte_carlo_from_exports(strategy: str, ticker: str, n_sims: int = 5000):
    """Read daily_returns.csv from strategy_exports and run Monte Carlo."""
    try:
        returns = read_daily_returns_from_exports(strategy, ticker)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = run_monte_carlo(returns, n_sims=n_sims)
    result["strategy"] = strategy
    result["ticker"] = ticker
    result["n_returns"] = len(returns)
    return result
