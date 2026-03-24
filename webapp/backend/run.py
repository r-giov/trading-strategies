"""QS Finance API — single-file entry point."""
import json
import sys
import os
import logging
import traceback
from pathlib import Path

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
os.chdir(_dir)

import deps  # noqa: E402, F401

from fastapi import FastAPI, Request, Query, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("qs-finance")

app = FastAPI(title="QS Finance API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(Exception)
async def exc_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    logger.error(f"{request.url}: {exc}\n{tb}")
    return JSONResponse(status_code=500, content={"error": str(exc), "traceback": tb})


# ── Health ──────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok", "service": "qs-finance"}


# ── Tickers ─────────────────────────────────────────────────────
@app.get("/api/data/tickers")
def data_tickers():
    """Return all tickers grouped by category, plus a flat sorted list."""
    tickers_path = deps.CONFIG_DIR / "tickers.json"
    if not tickers_path.exists():
        raise HTTPException(404, f"tickers.json not found at {tickers_path}")

    with open(tickers_path, "r") as f:
        raw = json.load(f)

    categories = {}

    # FTMO categories — extract yfinance tickers from nested structure
    ftmo = raw.get("ftmo", {})
    for subcategory, data in ftmo.items():
        if isinstance(data, dict) and "yfinance" in data:
            key = f"FTMO_{subcategory.replace('_', ' ').title().replace(' ', '_')}"
            categories[key] = data["yfinance"]

    # Rotation 30 categories
    rotation = raw.get("rotation_30", {})
    for subcategory, tickers in rotation.items():
        if isinstance(tickers, list):
            key = f"Rotation_{subcategory.replace('_', ' ').title().replace(' ', '_')}"
            categories[key] = tickers

    # Flat lists
    if "ftmo_flat" in raw:
        categories["FTMO_All"] = raw["ftmo_flat"]
    if "rotation_30_flat" in raw:
        categories["Rotation_30"] = raw["rotation_30_flat"]

    # Build deduplicated sorted flat list of all tickers
    all_tickers = sorted(set(
        t for tlist in categories.values() for t in tlist
    ))

    return {"categories": categories, "all_tickers": all_tickers}


# ── Signals ─────────────────────────────────────────────────────
from services.signal_service import get_signals, get_portfolio_config  # noqa: E402

@app.get("/api/signals/portfolio")
def signals_portfolio(refresh: bool = Query(False)):
    return get_signals(force_refresh=refresh)

@app.get("/api/signals/config")
def signals_config():
    return get_portfolio_config()


# ── Exports ─────────────────────────────────────────────────────
from services.export_reader import list_strategies, get_strategy_detail  # noqa: E402

@app.get("/api/exports/strategies")
def exports_list():
    return list_strategies()

@app.get("/api/exports/strategies/{strategy}/{ticker}")
def exports_detail(strategy: str, ticker: str):
    detail = get_strategy_detail(strategy, ticker)
    if detail is None:
        raise HTTPException(404, "Not found")
    return detail


# ── Monte Carlo ─────────────────────────────────────────────────
from services.montecarlo_service import run_monte_carlo, read_daily_returns_from_exports  # noqa: E402

@app.get("/api/montecarlo/from-exports/{strategy}/{ticker}")
def mc_from_exports(strategy: str, ticker: str, n_sims: int = 5000):
    try:
        returns = read_daily_returns_from_exports(strategy, ticker)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    result = run_monte_carlo(returns, n_sims=n_sims)
    result["strategy"] = strategy
    result["ticker"] = ticker
    result["n_returns"] = len(returns)
    return result


class MCRequest(BaseModel):
    daily_returns: list[float] | None = None
    strategy: str | None = None
    ticker: str | None = None
    n_sims: int = 5000

@app.post("/api/montecarlo/run")
def mc_run(req: MCRequest):
    if req.daily_returns and len(req.daily_returns) > 0:
        returns = req.daily_returns
    elif req.strategy and req.ticker:
        returns = read_daily_returns_from_exports(req.strategy, req.ticker)
    else:
        raise HTTPException(400, "Provide daily_returns or strategy+ticker")
    return run_monte_carlo(returns, n_sims=req.n_sims)


# ── Backtest ────────────────────────────────────────────────────
from services.backtest_service import run_backtest, run_grid_search  # noqa: E402

class BacktestRequest(BaseModel):
    strategy: str
    ticker: str
    start_date: str = "2015-01-01"
    params: dict = Field(default_factory=dict)
    init_cash: float = 100_000
    fees: float = 0.0005
    train_ratio: float = 0.60
    data_source: str = "yfinance"

@app.post("/api/backtest/run")
def backtest_run(req: BacktestRequest):
    result = run_backtest(
        strategy=req.strategy, ticker=req.ticker, start_date=req.start_date,
        params=req.params, init_cash=req.init_cash, fees=req.fees,
        train_ratio=req.train_ratio, data_source=req.data_source,
    )
    if "error" in result:
        return {"status": "error", **result}
    return {"status": "ok", **result}


class GridSearchRequest(BaseModel):
    strategy: str
    ticker: str
    start_date: str = "2015-01-01"
    param_ranges: dict = Field(default_factory=dict)
    init_cash: float = 100_000
    fees: float = 0.0005
    train_ratio: float = 0.60
    data_source: str = "yfinance"
    min_trades: int = 10

@app.post("/api/backtest/grid")
def grid_search(req: GridSearchRequest):
    result = run_grid_search(
        strategy=req.strategy, ticker=req.ticker, start_date=req.start_date,
        param_ranges=req.param_ranges, init_cash=req.init_cash, fees=req.fees,
        train_ratio=req.train_ratio, data_source=req.data_source,
        min_trades=req.min_trades,
    )
    if "error" in result:
        return {"status": "error", **result}
    return {"status": "ok", **result}


# ── Claude AI Analyst ────────────────────────────────────────
from services.claude_service import analyze_stock  # noqa: E402

class ChatRequest(BaseModel):
    ticker: str = ""
    message: str
    context: list[dict] = Field(default_factory=list)
    mode: str = "chat"  # "research", "chat", "reevaluate"

@app.post("/api/chat")
def chat(req: ChatRequest):
    result = analyze_stock(ticker=req.ticker, query=req.message, context=req.context, mode=req.mode)
    if "error" in result:
        raise HTTPException(500, result["error"])
    return result


# ── MT5 Live Account ───────────────────────────────────────────
from config import (  # noqa: E402
    MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_PATH,
    ACCOUNT_SIZE, PROFIT_TARGET, MAX_DAILY_LOSS, MAX_TOTAL_LOSS,
)
from datetime import datetime, timezone, timedelta  # noqa: E402

@app.get("/api/mt5/account")
def mt5_account():
    """Return live MT5 account state, FTMO status, positions, and recent trades."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        raise HTTPException(500, "MetaTrader5 package not installed")

    # ── Connect ────────────────────────────────────────────────
    init_kwargs = {}
    if MT5_PATH:
        init_kwargs["path"] = MT5_PATH
    if not mt5.initialize(**init_kwargs):
        error = mt5.last_error()
        return JSONResponse(status_code=503, content={
            "connected": False,
            "error": f"MT5 initialize failed: {error}",
        })

    if not mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        error = mt5.last_error()
        mt5.shutdown()
        return JSONResponse(status_code=503, content={
            "connected": False,
            "error": f"MT5 login failed: {error}",
        })

    try:
        # ── Account info ───────────────────────────────────────
        info = mt5.account_info()
        if info is None:
            raise HTTPException(500, "Failed to retrieve account info")

        account = {
            "login": info.login,
            "balance": info.balance,
            "equity": info.equity,
            "profit": info.profit,
            "margin": info.margin,
            "free_margin": info.margin_free,
        }

        # ── FTMO status ───────────────────────────────────────
        daily_pnl = info.equity - info.balance  # unrealised
        total_pnl = info.balance - ACCOUNT_SIZE + daily_pnl  # realised + unrealised vs starting

        ftmo_status = {
            "profit_progress": total_pnl,
            "profit_target": PROFIT_TARGET,
            "profit_pct": round(total_pnl / PROFIT_TARGET, 6) if PROFIT_TARGET else 0,
            "daily_pnl": daily_pnl,
            "daily_limit": MAX_DAILY_LOSS,
            "daily_pct": round(daily_pnl / MAX_DAILY_LOSS, 6) if MAX_DAILY_LOSS else 0,
            "total_pnl": total_pnl,
            "total_limit": MAX_TOTAL_LOSS,
            "total_pct": round(total_pnl / MAX_TOTAL_LOSS, 6) if MAX_TOTAL_LOSS else 0,
        }

        # ── Open positions ────────────────────────────────────
        raw_positions = mt5.positions_get()
        positions = []
        if raw_positions:
            for p in raw_positions:
                positions.append({
                    "ticket": p.ticket,
                    "symbol": p.symbol,
                    "type": "BUY" if p.type == 0 else "SELL",
                    "volume": p.volume,
                    "price_open": p.price_open,
                    "price_current": p.price_current,
                    "profit": p.profit,
                    "swap": p.swap,
                    "comment": p.comment,
                    "time": datetime.fromtimestamp(p.time, tz=timezone.utc).isoformat(),
                })

        # ── Recent trade history (last 7 days) ────────────────
        now = datetime.now(tz=timezone.utc)
        from_date = now - timedelta(days=7)
        deals = mt5.history_deals_get(from_date, now)
        recent_trades = []
        if deals:
            for d in deals:
                recent_trades.append({
                    "ticket": d.ticket,
                    "order": d.order,
                    "symbol": d.symbol,
                    "type": d.type,
                    "volume": d.volume,
                    "price": d.price,
                    "profit": d.profit,
                    "swap": d.swap,
                    "fee": d.fee,
                    "comment": d.comment,
                    "time": datetime.fromtimestamp(d.time, tz=timezone.utc).isoformat(),
                })

        return {
            "connected": True,
            "account": account,
            "ftmo_status": ftmo_status,
            "positions": positions,
            "recent_trades": recent_trades,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"MT5 account endpoint error: {e}\n{traceback.format_exc()}")
        raise HTTPException(500, f"MT5 error: {e}")
    finally:
        mt5.shutdown()


# ── Price History (for charts) ──────────────────────────────────
@app.get("/api/data/price/{ticker}")
def price_history(ticker: str, period: str = "1y"):
    """Get OHLCV price history for charting."""
    import yfinance as yf
    try:
        df = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=True)
        if df.empty:
            raise HTTPException(404, f"No data for {ticker}")
        if hasattr(df.columns, 'levels'):
            df.columns = df.columns.get_level_values(0)
        return {
            "ticker": ticker,
            "period": period,
            "dates": [d.isoformat()[:10] for d in df.index],
            "close": [round(float(v), 2) for v in df["Close"]],
            "high": [round(float(v), 2) for v in df["High"]],
            "low": [round(float(v), 2) for v in df["Low"]],
            "volume": [int(v) for v in df["Volume"]],
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Trade Tickets (Position Sizing) ────────────────────────────
from services.signal_service import get_signals, get_portfolio_config  # noqa: already imported above
from live.risk_guard import RiskGuard  # noqa: E402

@app.get("/api/signals/tickets")
def signal_tickets():
    """
    Generate full trade tickets for every active signal.
    Includes position sizing, entry price, stop level, and risk metrics.
    """
    import MetaTrader5 as mt5

    # Get signals
    sig_data = get_signals()
    config = get_portfolio_config()
    components = sig_data.get("components", [])
    aggregated = sig_data.get("aggregated", {})

    # Try to get live account equity from MT5
    equity = ACCOUNT_SIZE
    try:
        init_kwargs = {}
        if MT5_PATH:
            init_kwargs["path"] = MT5_PATH
        if mt5.initialize(**init_kwargs) and mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
            info = mt5.account_info()
            if info:
                equity = info.equity
            mt5.shutdown()
    except:
        pass

    guard = RiskGuard()

    # Build tickets for aggregated positions
    tickets = []
    for symbol, agg in aggregated.items():
        if agg["action"] == "HOLD":
            tickets.append({
                "symbol": symbol,
                "action": "HOLD",
                "reason": "No signal change",
                "components": agg["summary"],
            })
            continue

        weight = agg["weight"]
        last_close = agg.get("last_close", 0)

        if last_close and last_close > 0:
            lots = guard.position_size(symbol, last_close, weight, equity)
            notional = lots * last_close
            risk_pct = notional / equity * 100

            ticket = {
                "symbol": symbol,
                "action": agg["action"],
                "direction": "LONG" if agg["action"] == "BUY" else "CLOSE",
                "entry_price": last_close,
                "lots": lots,
                "notional_value": round(notional, 2),
                "portfolio_weight": round(weight * 100, 1),
                "risk_pct_of_equity": round(risk_pct, 2),
                "equity_used": round(equity, 2),
                "components_voting": agg["summary"],
                "component_details": [
                    {
                        "id": c["component_id"],
                        "strategy": c["strategy"],
                        "action": c["action"],
                        "reason": c["reason"],
                    }
                    for c in agg.get("components", [])
                ],
            }

            # FTMO min lot sizes
            min_lots = {"BTCUSD": 0.01, "ETHUSD": 0.01, "XRPUSD": 1.0, "SOLUSD": 0.1}
            ticket["min_lot"] = min_lots.get(symbol, 0.01)
            ticket["lot_step"] = min_lots.get(symbol, 0.01)

            tickets.append(ticket)
        else:
            tickets.append({
                "symbol": symbol,
                "action": agg["action"],
                "error": "No price data available",
            })

    # Risk check
    risk_check = guard.check({
        "equity": equity,
        "balance": equity,
        "profit": 0,
        "daily_pnl": 0,
    })

    return {
        "tickets": tickets,
        "account_equity": round(equity, 2),
        "risk_status": risk_check,
        "timestamp": sig_data.get("timestamp"),
        "total_buy_signals": sum(1 for t in tickets if t.get("action") == "BUY"),
        "total_exposure": round(sum(t.get("notional_value", 0) for t in tickets if t.get("action") == "BUY"), 2),
    }


# ── Trade Execution ────────────────────────────────────────────
from services.trade_executor import execute_signal, send_telegram_alert  # noqa: E402

@app.post("/api/trading/execute")
def execute_trades(dry_run: bool = Query(True)):
    """
    Execute ALL active signals. Set dry_run=false to place real trades.
    Routes to MT5 for crypto/indices, skips Alpaca symbols for now.
    """
    sig_data = get_signals(force_refresh=True)
    aggregated = sig_data.get("aggregated", {})
    components = sig_data.get("components", [])

    # Get equity from MT5
    equity = ACCOUNT_SIZE
    try:
        import MetaTrader5 as mt5
        init_kwargs = {}
        if MT5_PATH:
            init_kwargs["path"] = MT5_PATH
        if mt5.initialize(**init_kwargs) and mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
            info = mt5.account_info()
            if info:
                equity = info.equity
            mt5.shutdown()
    except:
        pass

    results = []
    for symbol, agg in aggregated.items():
        if agg["action"] == "HOLD":
            results.append({"symbol": symbol, "action": "HOLD", "executed": False})
            continue

        # Find the MT5 symbol name from components
        mt5_sym = symbol  # default
        for c in components:
            if c["symbol"] == symbol:
                mt5_sym = c["symbol"]
                break

        result = execute_signal(
            symbol=symbol,
            mt5_symbol=mt5_sym,
            action=agg["action"],
            weight=agg["weight"],
            equity=equity,
            reason=f'{agg["summary"]} | {agg["action"]}',
            dry_run=dry_run,
        )
        results.append(result)

        # Telegram alert for executed trades
        if result.get("executed") and not dry_run:
            msg = (
                f"{'🟢' if agg['action'] == 'BUY' else '🔴'} <b>QS TRADE</b>\n"
                f"<b>{agg['action']} {symbol}</b>\n"
                f"Lots: {result.get('lots', '?')} @ ${result.get('price', '?')}\n"
                f"Reason: {agg['summary']}\n"
                f"Equity: ${equity:,.2f}"
            )
            send_telegram_alert(msg)

    return {
        "dry_run": dry_run,
        "equity": round(equity, 2),
        "results": results,
        "executed_count": sum(1 for r in results if r.get("executed")),
        "timestamp": sig_data.get("timestamp"),
    }


@app.post("/api/trading/execute-one")
def execute_one_trade(symbol: str = Query(...), action: str = Query(...), dry_run: bool = Query(True)):
    """Execute a single trade on a specific symbol."""
    # Get equity
    equity = ACCOUNT_SIZE
    try:
        import MetaTrader5 as mt5
        init_kwargs = {}
        if MT5_PATH:
            init_kwargs["path"] = MT5_PATH
        if mt5.initialize(**init_kwargs) and mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
            info = mt5.account_info()
            if info:
                equity = info.equity
            mt5.shutdown()
    except:
        pass

    result = execute_signal(
        symbol=symbol,
        mt5_symbol=symbol,
        action=action,
        weight=1/6,  # default equal weight
        equity=equity,
        reason=f"Manual {action} from dashboard",
        dry_run=dry_run,
    )

    if result.get("executed") and not dry_run:
        msg = f"{'🟢' if action == 'BUY' else '🔴'} <b>QS MANUAL TRADE</b>\n<b>{action} {symbol}</b>\n${equity:,.2f} equity"
        send_telegram_alert(msg)

    return result


@app.post("/api/trading/stop")
def kill_switch():
    """EMERGENCY: Close all open positions immediately."""
    try:
        import MetaTrader5 as mt5
        init_kwargs = {}
        if MT5_PATH:
            init_kwargs["path"] = MT5_PATH
        if not mt5.initialize(**init_kwargs):
            return {"error": "MT5 init failed"}
        if not mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
            mt5.shutdown()
            return {"error": "MT5 login failed"}

        positions = mt5.positions_get()
        closed = []
        if positions:
            for p in positions:
                close_type = mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY
                tick = mt5.symbol_info_tick(p.symbol)
                price = tick.bid if p.type == 0 else tick.ask
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": p.symbol,
                    "volume": p.volume,
                    "type": close_type,
                    "position": p.ticket,
                    "price": price,
                    "deviation": 30,
                    "magic": 240308,
                    "comment": "QS_KILL_SWITCH",
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                res = mt5.order_send(request)
                closed.append({
                    "symbol": p.symbol,
                    "volume": p.volume,
                    "pnl": p.profit,
                    "closed": res.retcode == mt5.TRADE_RETCODE_DONE if res else False,
                })

        mt5.shutdown()

        send_telegram_alert("🚨 <b>KILL SWITCH ACTIVATED</b>\nAll positions closed.")

        return {"positions_closed": len(closed), "details": closed}

    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
