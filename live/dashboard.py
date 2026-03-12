"""
Terminal dashboard — real-time view of portfolio components, positions, and risk.
"""

import os
from datetime import datetime, timezone

from config import (
    PORTFOLIO, SYMBOLS, ACCOUNT_SIZE, MAX_DAILY_LOSS, MAX_TOTAL_LOSS,
    PROFIT_TARGET,
)


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def render(account, positions, agg_signals, comp_signals, risk):
    """
    Render full dashboard to terminal.

    Args:
        account: from executor.get_account_info()
        positions: from executor.get_positions()
        agg_signals: from aggregate_signals() — {symbol: {...}}
        comp_signals: from get_portfolio_signals_*() — {comp_id: {...}}
        risk: from risk_guard.check()
    """
    clear_screen()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    equity = account.get("equity", ACCOUNT_SIZE)
    balance = account.get("balance", ACCOUNT_SIZE)
    daily_pnl = account.get("daily_pnl", 0)
    total_pnl = equity - ACCOUNT_SIZE

    # ── Header
    print("=" * 78)
    print("  QS FINANCE — FTMO CRYPTO PORTFOLIO DASHBOARD")
    print(f"  {now}    |    {len(PORTFOLIO)} components across {len(SYMBOLS)} symbols")
    print("=" * 78)

    # ── Account Summary
    print()
    print("  ACCOUNT")
    print(f"  {'Equity:':<20} ${equity:>12,.2f}")
    print(f"  {'Balance:':<20} ${balance:>12,.2f}")
    print(f"  {'Unrealized P&L:':<20} ${account.get('profit', 0):>+12,.2f}")
    print(f"  {'Total P&L:':<20} ${total_pnl:>+12,.2f}  "
          f"({total_pnl/ACCOUNT_SIZE*100:+.2f}%)")

    # ── FTMO Progress
    print()
    print("  FTMO CHALLENGE PROGRESS")
    bar_len = 40

    profit_pct = max(total_pnl / PROFIT_TARGET * 100, 0)
    filled = int(min(profit_pct / 100, 1.0) * bar_len)
    bar = "#" * filled + "-" * (bar_len - filled)
    target_status = "TARGET HIT!" if total_pnl >= PROFIT_TARGET else ""
    print(f"  Profit:  [{bar}] {profit_pct:5.1f}%  "
          f"(${total_pnl:+,.0f} / ${PROFIT_TARGET:,})  {target_status}")

    daily_used = abs(min(daily_pnl, 0)) / MAX_DAILY_LOSS * 100
    filled_d = int(min(daily_used / 100, 1.0) * bar_len)
    bar_d = "#" * filled_d + "-" * (bar_len - filled_d)
    daily_warn = "!! DANGER !!" if daily_used > 80 else ""
    print(f"  Day Risk:[{bar_d}] {daily_used:5.1f}%  "
          f"(${abs(min(daily_pnl, 0)):,.0f} / ${MAX_DAILY_LOSS:,})  {daily_warn}")

    dd_used = max(ACCOUNT_SIZE - equity, 0) / MAX_TOTAL_LOSS * 100
    filled_t = int(min(dd_used / 100, 1.0) * bar_len)
    bar_t = "#" * filled_t + "-" * (bar_len - filled_t)
    total_warn = "!! DANGER !!" if dd_used > 80 else ""
    print(f"  Tot Risk:[{bar_t}] {dd_used:5.1f}%  "
          f"(${max(ACCOUNT_SIZE - equity, 0):,.0f} / ${MAX_TOTAL_LOSS:,})  {total_warn}")

    # ── Risk Guard Status
    print()
    if risk.get("allowed", True):
        print("  RISK STATUS: [  OK  ] Trading allowed")
    else:
        print(f"  RISK STATUS: [BLOCKED] {risk.get('reason', 'unknown')}")

    # ── Open Positions
    print()
    print("  OPEN POSITIONS")
    print(f"  {'Symbol':<10} {'Dir':<5} {'Volume':>8} {'Entry':>12} "
          f"{'Current':>12} {'P&L':>10} {'Swap':>8}")
    print("  " + "-" * 67)

    if not positions:
        print("  (no open positions)")
    else:
        total_pos_pnl = 0
        for p in positions:
            pnl = p.get("profit", 0)
            total_pos_pnl += pnl
            print(
                f"  {p['symbol']:<10} {p['type']:<5} {p['volume']:>8.2f} "
                f"${p['open_price']:>11,.2f} ${p['current_price']:>11,.2f} "
                f"${pnl:>+9,.2f} ${p.get('swap', 0):>7,.2f}"
            )
        print("  " + "-" * 67)
        print(f"  {'TOTAL':<10} {'':5} {'':>8} {'':>12} {'':>12} "
              f"${total_pos_pnl:>+9,.2f}")

    # ── Component Signals
    print()
    print("  PORTFOLIO COMPONENTS")
    print(f"  {'Component':<22} {'Symbol':<8} {'Action':<8} {'Wt':>5} {'Close':>12}  {'Reason'}")
    print("  " + "-" * 78)

    for comp in PORTFOLIO:
        sig = comp_signals.get(comp["id"], {})
        action = sig.get("action", "N/A")
        close_v = sig.get("last_close")
        reason = sig.get("reason", "")
        weight = comp["weight"]

        marker = ">>" if action in ("BUY", "SELL") else "  "
        close_s = f"${close_v:>11,.2f}" if close_v is not None else f"{'n/a':>12}"
        print(f"  {comp['id']:<22} {comp['symbol']:<8} {marker}{action:<6} "
              f"{weight:>4.0%} {close_s}  {reason}")

    # ── Aggregated Actions
    print()
    print("  AGGREGATED POSITIONS (net per symbol)")
    print(f"  {'Symbol':<10} {'Action':<8} {'Net Wt':>8}  {'Breakdown'}")
    print("  " + "-" * 50)

    for sym in SYMBOLS:
        agg = agg_signals.get(sym, {})
        action = agg.get("action", "N/A")
        weight = agg.get("weight", 0)
        summary = agg.get("summary", "")
        marker = ">>" if action in ("BUY", "SELL") else "  "
        print(f"  {sym:<10} {marker}{action:<6} {weight:>7.1%}   {summary}")

    # ── Footer
    print()
    print("=" * 78)
    print("  [r] Refresh  [s] Run signals  [t] Execute trades  "
          "[d] Dry run  [q] Quit")
    print("=" * 78)


def render_simple(agg_signals, comp_signals):
    """Signal-only display (no MT5 connection needed)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print()
    print("=" * 78)
    print("  QS FINANCE — PORTFOLIO SIGNAL CHECK")
    print(f"  {now}")
    print("=" * 78)

    # Component detail
    print()
    print(f"  {'Component':<22} {'Symbol':<8} {'Action':<8} {'Wt':>5} {'Close':>12}  {'Reason'}")
    print("  " + "-" * 78)

    for comp in PORTFOLIO:
        sig = comp_signals.get(comp["id"], {})
        action = sig.get("action", "N/A")
        close_v = sig.get("last_close")
        reason = sig.get("reason", "")

        marker = ">>" if action in ("BUY", "SELL") else "  "
        close_s = f"${close_v:>11,.2f}" if close_v is not None else f"{'n/a':>12}"
        print(f"  {comp['id']:<22} {comp['symbol']:<8} {marker}{action:<6} "
              f"{comp['weight']:>4.0%} {close_s}  {reason}")

    # Aggregated
    print()
    print(f"  {'AGGREGATED':<22} {'Symbol':<8} {'Action':<8} {'Net Wt':>5}  {'Breakdown'}")
    print("  " + "-" * 60)

    for sym in SYMBOLS:
        agg = agg_signals.get(sym, {})
        action = agg.get("action", "N/A")
        weight = agg.get("weight", 0)
        summary = agg.get("summary", "")
        marker = ">>" if action in ("BUY", "SELL") else "  "
        print(f"  {'':<22} {sym:<8} {marker}{action:<6} {weight:>4.0%}   {summary}")

    print()
    print("=" * 78)
