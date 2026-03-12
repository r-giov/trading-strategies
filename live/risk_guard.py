"""
FTMO risk guard — checks account state before allowing any trade.
This is the safety net that prevents blowing the challenge.
"""

import logging
from datetime import datetime, timezone
from config import (
    ACCOUNT_SIZE, MAX_DAILY_LOSS, MAX_TOTAL_LOSS,
    DAILY_LOSS_BUFFER, TOTAL_LOSS_BUFFER,
)

logger = logging.getLogger("risk_guard")


class RiskGuard:
    """
    Checks FTMO risk limits before every trade.
    Blocks execution if we're too close to daily or total loss limits.
    """

    def __init__(self):
        self.starting_equity = ACCOUNT_SIZE
        self.daily_loss_limit = MAX_DAILY_LOSS * DAILY_LOSS_BUFFER
        self.total_loss_limit = MAX_TOTAL_LOSS * TOTAL_LOSS_BUFFER

    def check(self, account_info: dict) -> dict:
        """
        Evaluate whether trading is allowed.

        Args:
            account_info: dict with keys:
                equity: current account equity
                balance: current account balance
                profit: unrealized P&L
                daily_pnl: today's realized + unrealized P&L

        Returns:
            dict with:
                allowed: bool
                reason: str
                daily_pnl: float
                total_drawdown: float
                daily_remaining: float
                total_remaining: float
        """
        equity = account_info.get("equity", self.starting_equity)
        daily_pnl = account_info.get("daily_pnl", 0)
        total_drawdown = self.starting_equity - equity

        daily_remaining = self.daily_loss_limit - abs(min(daily_pnl, 0))
        total_remaining = self.total_loss_limit - total_drawdown

        result = {
            "allowed": True,
            "reason": "OK",
            "equity": equity,
            "daily_pnl": daily_pnl,
            "total_drawdown": total_drawdown,
            "daily_remaining": daily_remaining,
            "total_remaining": total_remaining,
            "daily_limit_pct": abs(min(daily_pnl, 0)) / MAX_DAILY_LOSS * 100,
            "total_limit_pct": total_drawdown / MAX_TOTAL_LOSS * 100,
        }

        # Check daily loss
        if abs(min(daily_pnl, 0)) >= self.daily_loss_limit:
            result["allowed"] = False
            result["reason"] = (
                f"BLOCKED: Daily loss ${abs(daily_pnl):,.0f} near limit "
                f"${MAX_DAILY_LOSS:,.0f} (buffer at {DAILY_LOSS_BUFFER:.0%})"
            )
            logger.warning(result["reason"])
            return result

        # Check total drawdown
        if total_drawdown >= self.total_loss_limit:
            result["allowed"] = False
            result["reason"] = (
                f"BLOCKED: Total drawdown ${total_drawdown:,.0f} near limit "
                f"${MAX_TOTAL_LOSS:,.0f} (buffer at {TOTAL_LOSS_BUFFER:.0%})"
            )
            logger.warning(result["reason"])
            return result

        logger.info(
            f"Risk OK — Daily PnL: ${daily_pnl:+,.0f} "
            f"(${daily_remaining:,.0f} remaining) | "
            f"Drawdown: ${total_drawdown:,.0f} "
            f"(${total_remaining:,.0f} remaining)"
        )
        return result

    def position_size(self, symbol: str, price: float, weight: float,
                      equity: float) -> float:
        """
        Calculate position size (volume/lots) for a symbol.

        For FTMO crypto:
          - 1 lot = 1 unit of base currency (1 BTC, 1 ETH, etc.)
          - Position value = lots * price
          - Target notional = equity * weight

        Returns volume in lots.
        """
        target_notional = equity * weight
        if price <= 0:
            return 0.0

        lots = target_notional / price

        # FTMO minimum lot sizes for crypto
        min_lots = {
            "BTCUSD": 0.01,
            "ETHUSD": 0.01,
            "XRPUSD": 1.0,
            "SOLUSD": 0.1,
        }
        min_lot = min_lots.get(symbol, 0.01)

        # Round down to minimum lot increment
        lots = max(round(lots / min_lot) * min_lot, min_lot)

        return round(lots, 2)
