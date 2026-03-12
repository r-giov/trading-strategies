"""
Alert module — sends trade signals and risk warnings via Telegram.
Optional: only active if TG_BOT_TOKEN and TG_CHAT_ID are set in .env.
"""

import logging
import urllib.request
import urllib.parse
from datetime import datetime, timezone

from config import TG_BOT_TOKEN, TG_CHAT_ID, PORTFOLIO

logger = logging.getLogger("alerter")


def is_configured() -> bool:
    return bool(TG_BOT_TOKEN and TG_CHAT_ID)


def send_telegram(message: str) -> bool:
    """Send a message via Telegram Bot API (no dependencies needed)."""
    if not is_configured():
        logger.debug("Telegram not configured, skipping alert")
        return False

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": TG_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }).encode()

    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


def alert_signals_portfolio(comp_signals: dict, agg_signals: dict):
    """Send portfolio signal summary to Telegram."""
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    lines = [f"*QS Finance Portfolio Signal Check* — {now}\n"]

    # Component breakdown
    has_action = False
    for comp in PORTFOLIO:
        sig = comp_signals.get(comp["id"], {})
        action = sig.get("action", "HOLD")
        close = sig.get("last_close", 0)
        reason = sig.get("reason", "")

        if action in ("BUY", "SELL"):
            has_action = True
            lines.append(f">> *{comp['id']}*: {action} @ ${close:,.2f} ({reason})")
        else:
            lines.append(f"   {comp['id']}: hold")

    # Aggregated
    lines.append("\n*Aggregated:*")
    for sym, agg in agg_signals.items():
        action = agg["action"]
        weight = agg["weight"]
        summary = agg["summary"]
        if action in ("BUY", "SELL"):
            lines.append(f">> *{sym}*: {action} wt={weight:.0%} ({summary})")
        else:
            lines.append(f"   {sym}: hold ({summary})")

    if not has_action:
        lines.append("\n_No signals today._")

    send_telegram("\n".join(lines))


def alert_execution(symbol: str, result: dict):
    """Send trade execution confirmation."""
    if result.get("executed"):
        msg = (
            f"*TRADE EXECUTED*\n"
            f"Symbol: {symbol}\n"
            f"Direction: {result['direction']}\n"
            f"Volume: {result['volume']}\n"
            f"Price: ${result['price']:,.2f}\n"
            f"Weight: {result.get('weight', 0):.0%}\n"
            f"Ticket: #{result.get('ticket', 'n/a')}"
        )
    elif result.get("dry_run"):
        msg = (
            f"*DRY RUN*\n"
            f"Symbol: {symbol}\n"
            f"Direction: {result.get('direction', 'n/a')}\n"
            f"Volume: {result.get('volume', 'n/a')}\n"
            f"Price: ${result.get('price', 0):,.2f}\n"
            f"Weight: {result.get('weight', 0):.0%}"
        )
    else:
        msg = f"*{symbol}*: No action — {result.get('reason', 'unknown')}"

    send_telegram(msg)


def alert_risk_warning(risk: dict):
    """Send risk warning if we're near limits."""
    daily_pct = risk.get("daily_limit_pct", 0)
    total_pct = risk.get("total_limit_pct", 0)

    if daily_pct > 60 or total_pct > 60:
        msg = (
            f"*RISK WARNING*\n"
            f"Daily loss: {daily_pct:.0f}% of limit\n"
            f"Total drawdown: {total_pct:.0f}% of limit\n"
            f"Equity: ${risk.get('equity', 0):,.2f}\n"
        )
        if not risk.get("allowed"):
            msg += "\n*TRADING BLOCKED*"
        send_telegram(msg)
