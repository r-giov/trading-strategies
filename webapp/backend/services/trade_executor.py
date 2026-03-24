"""
Trade executor — connects signals to actual execution on MT5 (crypto/forex/indices)
and Alpaca (US stocks). Sends Telegram alerts for every trade.
"""

import sys
import os
import logging
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import deps  # noqa: F401

from dotenv import load_dotenv
load_dotenv(deps.REPO_ROOT / "live" / ".env")

logger = logging.getLogger("qs-finance.executor")

# MT5 symbols that trade on FTMO
MT5_SYMBOLS = {
    "BTCUSD", "ETHUSD", "XRPUSD", "SOLUSD",  # crypto
    "US100.cash", "US30.cash", "US500.cash", "GER40.cash", "UK100.cash",  # indices
}

# Everything else goes to Alpaca
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")


def execute_signal(symbol: str, mt5_symbol: str, action: str, weight: float,
                   equity: float, reason: str, dry_run: bool = False) -> dict:
    """Route a trade to the correct broker and execute."""
    if action == "HOLD":
        return {"executed": False, "reason": "HOLD — no action"}

    if mt5_symbol in MT5_SYMBOLS:
        return _execute_mt5(mt5_symbol, action, weight, equity, reason, dry_run)
    else:
        return _execute_alpaca(symbol, action, weight, equity, reason, dry_run)


def _execute_mt5(symbol: str, action: str, weight: float, equity: float,
                 reason: str, dry_run: bool) -> dict:
    """Execute on MT5 (FTMO account)."""
    try:
        import MetaTrader5 as mt5
        from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_PATH
        from risk_guard import RiskGuard
    except ImportError as e:
        return {"executed": False, "broker": "mt5", "error": str(e)}

    guard = RiskGuard()

    init_kwargs = {}
    if MT5_PATH:
        init_kwargs["path"] = MT5_PATH
    if not mt5.initialize(**init_kwargs):
        return {"executed": False, "broker": "mt5", "error": f"init failed: {mt5.last_error()}"}
    if not mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        mt5.shutdown()
        return {"executed": False, "broker": "mt5", "error": f"login failed: {mt5.last_error()}"}

    try:
        # Enable symbol
        mt5.symbol_select(symbol, True)

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"executed": False, "broker": "mt5", "error": f"no tick for {symbol}"}

        price = tick.ask if action == "BUY" else tick.bid
        if price <= 0:
            return {"executed": False, "broker": "mt5", "error": f"invalid price {price}"}

        lots = guard.position_size(symbol, price, weight, equity)

        result_info = {
            "broker": "mt5",
            "symbol": symbol,
            "action": action,
            "lots": lots,
            "price": price,
            "notional": round(lots * price, 2),
            "weight": weight,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if dry_run:
            result_info["executed"] = False
            result_info["dry_run"] = True
            logger.info(f"[DRY RUN] MT5 {action} {lots} {symbol} @ {price}")
            return result_info

        # Check existing position
        positions = mt5.positions_get(symbol=symbol)
        if action == "BUY" and positions:
            for p in positions:
                if p.type == 0:  # already long
                    return {"executed": False, "broker": "mt5", "reason": "already long", **result_info}

        if action == "SELL" and positions:
            # Close long position
            for p in positions:
                if p.type == 0:
                    close_request = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": symbol,
                        "volume": p.volume,
                        "type": mt5.ORDER_TYPE_SELL,
                        "position": p.ticket,
                        "price": tick.bid,
                        "deviation": 20,
                        "magic": 240308,
                        "comment": f"QS_CLOSE_{symbol}",
                        "type_filling": mt5.ORDER_FILLING_IOC,
                    }
                    res = mt5.order_send(close_request)
                    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                        result_info["executed"] = True
                        result_info["ticket"] = res.order
                        result_info["close_price"] = res.price
                        result_info["pnl"] = p.profit
                        logger.info(f"MT5 CLOSED {symbol} @ {res.price} P&L: ${p.profit:.2f}")
                    else:
                        result_info["executed"] = False
                        result_info["error"] = f"close failed: {res.comment if res else mt5.last_error()}"
                    return result_info
            return {"executed": False, "broker": "mt5", "reason": "no position to close"}

        if action == "BUY":
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": lots,
                "type": mt5.ORDER_TYPE_BUY,
                "price": price,
                "deviation": 20,
                "magic": 240308,
                "comment": f"QS_{symbol}",
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            res = mt5.order_send(request)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                result_info["executed"] = True
                result_info["ticket"] = res.order
                logger.info(f"MT5 OPENED BUY {lots} {symbol} @ {res.price}")
            else:
                result_info["executed"] = False
                result_info["error"] = f"order failed: {res.comment if res else mt5.last_error()}"
            return result_info

        return {"executed": False, "broker": "mt5", "reason": f"unhandled action: {action}"}

    finally:
        mt5.shutdown()


def _execute_alpaca(symbol: str, action: str, weight: float, equity: float,
                    reason: str, dry_run: bool) -> dict:
    """Execute on Alpaca (US stocks paper trading)."""
    result_info = {
        "broker": "alpaca",
        "symbol": symbol,
        "action": action,
        "weight": weight,
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if not ALPACA_API_KEY:
        result_info["executed"] = False
        result_info["error"] = "ALPACA_API_KEY not configured"
        return result_info

    try:
        from alpaca_trade_api import REST
        api = REST(ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL)

        account = api.get_account()
        buying_power = float(account.buying_power)
        target_notional = equity * weight

        if dry_run:
            result_info["executed"] = False
            result_info["dry_run"] = True
            result_info["target_notional"] = round(target_notional, 2)
            result_info["buying_power"] = round(buying_power, 2)
            logger.info(f"[DRY RUN] Alpaca {action} ${target_notional:.2f} of {symbol}")
            return result_info

        if action == "BUY":
            order = api.submit_order(
                symbol=symbol,
                notional=round(min(target_notional, buying_power * 0.95), 2),
                side="buy",
                type="market",
                time_in_force="day",
            )
            result_info["executed"] = True
            result_info["order_id"] = order.id
            result_info["notional"] = round(target_notional, 2)
            logger.info(f"Alpaca BUY ${target_notional:.2f} of {symbol}")

        elif action == "SELL":
            try:
                position = api.get_position(symbol)
                api.close_position(symbol)
                result_info["executed"] = True
                result_info["qty_closed"] = position.qty
                result_info["pnl"] = float(position.unrealized_pl)
                logger.info(f"Alpaca CLOSED {symbol} P&L: ${float(position.unrealized_pl):.2f}")
            except Exception:
                result_info["executed"] = False
                result_info["reason"] = "no position to close"

        return result_info

    except ImportError:
        result_info["executed"] = False
        result_info["error"] = "alpaca-trade-api not installed"
        return result_info
    except Exception as e:
        result_info["executed"] = False
        result_info["error"] = str(e)
        return result_info


def send_telegram_alert(message: str) -> bool:
    """Send trade alert via Telegram."""
    bot_token = os.getenv("TG_BOT_TOKEN", "")
    chat_id = os.getenv("TG_CHAT_ID", "")

    if not bot_token or not chat_id:
        logger.warning("Telegram not configured")
        return False

    try:
        import urllib.request
        import urllib.parse
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": message, "parse_mode": "HTML"}).encode()
        urllib.request.urlopen(url, data, timeout=10)
        return True
    except Exception as e:
        logger.error(f"Telegram failed: {e}")
        return False
