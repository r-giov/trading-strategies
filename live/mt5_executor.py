"""
MT5 execution module — connects to FTMO demo/live account,
places and manages trades based on aggregated portfolio signals.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from config import CRYPTO_LEVERAGE
from risk_guard import RiskGuard

logger = logging.getLogger("executor")


class MT5Executor:
    """
    Handles all MetaTrader 5 interactions:
    - Connection management
    - Order placement (market orders)
    - Position tracking
    - Account info retrieval
    """

    def __init__(self):
        self.mt5 = None
        self.connected = False
        self.risk_guard = RiskGuard()
        self._today_start_balance = None

    def connect(self, login: int, password: str, server: str,
                path: str = "") -> bool:
        """Initialize and log in to MT5."""
        try:
            import MetaTrader5 as mt5
            self.mt5 = mt5
        except ImportError:
            logger.error(
                "MetaTrader5 package not installed. "
                "Install with: pip install MetaTrader5"
            )
            return False

        init_kwargs = {}
        if path:
            init_kwargs["path"] = path

        if not mt5.initialize(**init_kwargs):
            logger.error(f"MT5 initialize failed: {mt5.last_error()}")
            return False

        if not mt5.login(login, password=password, server=server):
            logger.error(f"MT5 login failed: {mt5.last_error()}")
            mt5.shutdown()
            return False

        info = mt5.account_info()
        if info is None:
            logger.error("Could not retrieve account info")
            mt5.shutdown()
            return False

        self.connected = True
        self._today_start_balance = info.balance
        logger.info(
            f"Connected to {server} | Account: {info.login} | "
            f"Balance: ${info.balance:,.2f} | Equity: ${info.equity:,.2f}"
        )
        return True

    def disconnect(self):
        """Shut down MT5 connection."""
        if self.mt5 and self.connected:
            self.mt5.shutdown()
            self.connected = False
            logger.info("MT5 disconnected")

    def get_account_info(self) -> dict:
        """Get current account state for risk checks."""
        if not self.connected:
            return {"equity": 0, "balance": 0, "profit": 0, "daily_pnl": 0}

        info = self.mt5.account_info()
        if info is None:
            return {"equity": 0, "balance": 0, "profit": 0, "daily_pnl": 0}

        daily_pnl = info.equity - (self._today_start_balance or info.balance)

        return {
            "equity": info.equity,
            "balance": info.balance,
            "profit": info.profit,
            "margin": info.margin,
            "free_margin": info.margin_free,
            "daily_pnl": daily_pnl,
        }

    def get_positions(self) -> list:
        """Get all open positions."""
        if not self.connected:
            return []

        positions = self.mt5.positions_get()
        if positions is None:
            return []

        result = []
        for p in positions:
            result.append({
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == 0 else "SELL",
                "volume": p.volume,
                "open_price": p.price_open,
                "current_price": p.price_current,
                "profit": p.profit,
                "swap": p.swap,
                "time": datetime.fromtimestamp(p.time, tz=timezone.utc),
            })
        return result

    def has_position(self, symbol: str) -> Optional[dict]:
        """Check if we have an open position for a symbol."""
        positions = self.get_positions()
        for p in positions:
            if p["symbol"] == symbol:
                return p
        return None

    def execute_signal(self, symbol: str, action: str, weight: float,
                       dry_run: bool = False) -> dict:
        """
        Execute a trading signal.

        Args:
            symbol: MT5 symbol (e.g. "BTCUSD")
            action: "BUY", "SELL", or "HOLD"
            weight: portfolio weight for position sizing (e.g. 0.333 = 2 components active)
            dry_run: if True, log but don't place orders

        Returns:
            dict with execution result
        """
        if action == "HOLD":
            return {"executed": False, "reason": "HOLD — no action needed"}

        # Risk check first
        account = self.get_account_info()
        risk = self.risk_guard.check(account)
        if not risk["allowed"]:
            return {"executed": False, "reason": risk["reason"]}

        current_pos = self.has_position(symbol)

        if action == "BUY":
            if current_pos and current_pos["type"] == "BUY":
                # Already long — check if we need to resize
                return {"executed": False, "reason": "already long"}
            if current_pos and current_pos["type"] == "SELL":
                # Close short first, then open long
                result = self._close_position(current_pos, dry_run)
                if not result.get("success") and not dry_run:
                    return {"executed": False, "reason": f"failed to close short: {result}"}
            return self._open_position(symbol, "BUY", weight,
                                       account["equity"], dry_run)

        elif action == "SELL":
            # SELL = close long position (we don't short on exit signals)
            if current_pos and current_pos["type"] == "BUY":
                return self._close_position(current_pos, dry_run)
            elif current_pos and current_pos["type"] == "SELL":
                return {"executed": False, "reason": "already short/flat"}
            else:
                return {"executed": False, "reason": "no position to close"}

    def _open_position(self, symbol: str, direction: str, weight: float,
                       equity: float, dry_run: bool) -> dict:
        """Place a market order."""
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"executed": False, "reason": f"no tick data for {symbol}"}

        price = tick.ask if direction == "BUY" else tick.bid
        volume = self.risk_guard.position_size(symbol, price, weight, equity)

        order_type = (self.mt5.ORDER_TYPE_BUY if direction == "BUY"
                      else self.mt5.ORDER_TYPE_SELL)

        request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "deviation": 20,
            "magic": 240308,
            "comment": f"QS_{symbol}",
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }

        if dry_run:
            logger.info(f"[DRY RUN] {direction} {volume} {symbol} @ {price} (weight={weight:.1%})")
            return {
                "executed": False, "dry_run": True,
                "direction": direction, "volume": volume,
                "symbol": symbol, "price": price, "weight": weight,
                "reason": "dry run — no order placed",
            }

        result = self.mt5.order_send(request)
        if result is None:
            return {"executed": False, "reason": f"order_send returned None: {self.mt5.last_error()}"}

        if result.retcode != self.mt5.TRADE_RETCODE_DONE:
            return {"executed": False, "reason": f"order rejected: {result.comment} (code {result.retcode})"}

        logger.info(
            f"OPENED {direction} {volume} {symbol} @ {result.price} "
            f"| weight={weight:.1%} | ticket #{result.order}"
        )
        return {
            "executed": True,
            "ticket": result.order,
            "direction": direction,
            "volume": volume,
            "price": result.price,
            "symbol": symbol,
            "weight": weight,
        }

    def _close_position(self, position: dict, dry_run: bool) -> dict:
        """Close an existing position."""
        symbol = position["symbol"]
        ticket = position["ticket"]
        volume = position["volume"]

        close_type = (self.mt5.ORDER_TYPE_SELL if position["type"] == "BUY"
                      else self.mt5.ORDER_TYPE_BUY)

        tick = self.mt5.symbol_info_tick(symbol)
        price = tick.bid if position["type"] == "BUY" else tick.ask

        request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": 240308,
            "comment": f"QS_CLOSE_{symbol}",
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }

        if dry_run:
            logger.info(
                f"[DRY RUN] CLOSE {position['type']} {volume} {symbol} "
                f"@ {price} (P&L: ${position['profit']:+,.2f})"
            )
            return {"success": True, "dry_run": True}

        result = self.mt5.order_send(request)
        if result is None:
            return {"success": False, "reason": str(self.mt5.last_error())}

        if result.retcode != self.mt5.TRADE_RETCODE_DONE:
            return {"success": False, "reason": f"{result.comment} (code {result.retcode})"}

        logger.info(
            f"CLOSED {position['type']} {volume} {symbol} @ {result.price} "
            f"| P&L: ${position['profit']:+,.2f} | ticket #{ticket}"
        )
        return {"success": True, "price": result.price, "ticket": ticket}
