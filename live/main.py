"""
QS Finance — Live Trading Orchestrator

Usage:
    python main.py                  # Interactive dashboard (MT5 required)
    python main.py --signals        # Check signals only (yfinance, no MT5)
    python main.py --dry-run        # Full pipeline with dry-run execution
    python main.py --execute        # Full pipeline with live execution
    python main.py --once           # Single signal check + execute, then exit
"""

import argparse
import logging
import sys
import csv
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import PORTFOLIO, SYMBOLS, MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_PATH, LOG_DIR
from signals import (
    get_portfolio_signals_yfinance,
    get_portfolio_signals_mt5,
    aggregate_signals,
)
from risk_guard import RiskGuard
from dashboard import render, render_simple
from alerter import alert_signals_portfolio, alert_execution, alert_risk_warning, is_configured

# ── Logging Setup ───────────────────────────────────────────────
log_file = LOG_DIR / f"trading_{datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("main")


def log_trade(symbol: str, agg_signal: dict, result: dict):
    """Append trade to CSV log."""
    log_path = LOG_DIR / "trade_log.csv"
    is_new = not log_path.exists()

    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "action": agg_signal.get("action"),
        "net_weight": agg_signal.get("weight", 0),
        "components_summary": agg_signal.get("summary", ""),
        "close": agg_signal.get("last_close"),
        "executed": result.get("executed", False),
        "direction": result.get("direction", ""),
        "volume": result.get("volume", ""),
        "price": result.get("price", ""),
        "ticket": result.get("ticket", ""),
        "reason": result.get("reason", ""),
    }

    with open(log_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def run_signals_only():
    """Check signals using yfinance — no MT5 needed."""
    logger.info("Signal check (yfinance mode)")
    comp_signals = get_portfolio_signals_yfinance()
    agg_signals = aggregate_signals(comp_signals)

    render_simple(agg_signals, comp_signals)

    # Log component signals
    for comp_id, sig in comp_signals.items():
        action = sig.get("action", "HOLD")
        close = sig.get("last_close", "?")
        logger.info(f"  {comp_id}: {action} @ {close} — {sig.get('reason', '')}")

    # Log aggregated
    for sym, agg in agg_signals.items():
        logger.info(f"  >> {sym}: {agg['action']} (weight={agg['weight']:.1%}) — {agg['summary']}")

    if is_configured():
        alert_signals_portfolio(comp_signals, agg_signals)

    return agg_signals, comp_signals


def run_with_mt5(dry_run: bool = True, once: bool = False):
    """Full pipeline: connect to MT5, check signals, execute trades."""
    from mt5_executor import MT5Executor

    executor = MT5Executor()

    if not executor.connect(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_PATH):
        logger.error("Failed to connect to MT5. Check credentials in .env")
        logger.info("Falling back to signal-only mode (yfinance)...")
        return run_signals_only()

    try:
        risk_guard = RiskGuard()

        while True:
            account = executor.get_account_info()
            positions = executor.get_positions()
            risk = risk_guard.check(account)

            # Get signals
            try:
                comp_signals = get_portfolio_signals_mt5()
            except Exception:
                logger.warning("MT5 signal fetch failed, falling back to yfinance")
                comp_signals = get_portfolio_signals_yfinance()

            agg_signals = aggregate_signals(comp_signals)

            render(account, positions, agg_signals, comp_signals, risk)

            if once:
                # Execute aggregated signals and exit
                for symbol, agg in agg_signals.items():
                    action = agg.get("action", "HOLD")
                    if action != "HOLD":
                        result = executor.execute_signal(
                            symbol, action, weight=agg["weight"], dry_run=dry_run,
                        )
                        log_trade(symbol, agg, result)
                        alert_execution(symbol, result)
                        logger.info(f"  {symbol}: {action} (wt={agg['weight']:.1%}) -> {result}")
                    else:
                        log_trade(symbol, agg, {"executed": False, "reason": "HOLD"})

                if is_configured():
                    alert_signals_portfolio(comp_signals, agg_signals)
                    if risk.get("daily_limit_pct", 0) > 60:
                        alert_risk_warning(risk)
                break

            # Interactive mode
            print()
            cmd = input("  > ").strip().lower()

            if cmd == "q":
                break
            elif cmd == "r":
                continue
            elif cmd == "s":
                comp_signals = get_portfolio_signals_yfinance()
                agg_signals = aggregate_signals(comp_signals)
                render(account, positions, agg_signals, comp_signals, risk)
            elif cmd == "d":
                any_action = False
                for symbol, agg in agg_signals.items():
                    action = agg.get("action", "HOLD")
                    if action != "HOLD":
                        any_action = True
                        result = executor.execute_signal(
                            symbol, action, weight=agg["weight"], dry_run=True,
                        )
                        log_trade(symbol, agg, result)
                        print(f"  [DRY RUN] {symbol}: {action} wt={agg['weight']:.1%} "
                              f"-> {result.get('reason', 'OK')}")
                    else:
                        print(f"  {symbol}: HOLD — no action ({agg['summary']})")
                if not any_action:
                    print("\n  No signals to execute. All assets are HOLD.")
                input("\n  Press Enter to continue...")
            elif cmd == "t":
                any_action = False
                for symbol, agg in agg_signals.items():
                    if agg.get("action", "HOLD") != "HOLD":
                        any_action = True
                        break
                if not any_action:
                    print("\n  No signals to execute. All assets are HOLD.")
                    input("\n  Press Enter to continue...")
                    continue
                confirm = input("  Confirm live execution? (yes/no): ").strip()
                if confirm == "yes":
                    for symbol, agg in agg_signals.items():
                        action = agg.get("action", "HOLD")
                        if action != "HOLD":
                            result = executor.execute_signal(
                                symbol, action, weight=agg["weight"], dry_run=False,
                            )
                            log_trade(symbol, agg, result)
                            alert_execution(symbol, result)
                            print(f"  EXECUTED: {symbol}: {result}")
                else:
                    print("  Cancelled.")

    finally:
        executor.disconnect()


def main():
    parser = argparse.ArgumentParser(description="QS Finance Live Trading")
    parser.add_argument("--signals", action="store_true",
                        help="Signal check only (yfinance, no MT5)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Full pipeline with simulated execution")
    parser.add_argument("--execute", action="store_true",
                        help="Full pipeline with LIVE execution")
    parser.add_argument("--once", action="store_true",
                        help="Single run then exit (for cron/scheduler)")

    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("QS Finance Live Trading — Starting")
    logger.info(f"Mode: {'signals' if args.signals else 'dry-run' if args.dry_run else 'execute' if args.execute else 'interactive'}")
    logger.info(f"Portfolio: {len(PORTFOLIO)} components across {len(SYMBOLS)} symbols")
    logger.info(f"Symbols: {', '.join(SYMBOLS)}")
    logger.info(f"Telegram: {'configured' if is_configured() else 'not configured'}")
    logger.info("=" * 50)

    if args.signals:
        run_signals_only()
    elif args.execute:
        run_with_mt5(dry_run=False, once=args.once)
    elif args.dry_run:
        run_with_mt5(dry_run=True, once=args.once)
    else:
        if MT5_LOGIN:
            run_with_mt5(dry_run=True)
        else:
            logger.info("No MT5 credentials — running signal-only mode")
            run_signals_only()


if __name__ == "__main__":
    main()
