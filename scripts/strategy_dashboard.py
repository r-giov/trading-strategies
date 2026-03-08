#!/usr/bin/env python3
"""
Strategy Dashboard — Master Comparison of All Strategy Runs
============================================================

Scans strategy_exports/ for all summary.json files and builds a rich
terminal report comparing every strategy run across all tickers.

Usage (terminal / Claude Code):
    python scripts/strategy_dashboard.py
    python scripts/strategy_dashboard.py --csv results.csv
    python scripts/strategy_dashboard.py --export-dir /path/to/strategy_exports

Usage (Colab):
    !python scripts/strategy_dashboard.py
    !python scripts/strategy_dashboard.py --export-dir /content/drive/MyDrive/strategy_exports

Options:
    --export-dir DIR    Override the strategy_exports directory
    --csv FILE          Output master table to a CSV file
    --top N             Show top N in leaderboard (default: 20)
    --min-trades N      Exclude runs with fewer than N trades (default: 5)
    --corr-threshold F  Correlation warning threshold (default: 0.70)

Sections:
    1. Sharpe Ratio Leaderboard (ranked, color-coded)
    2. IS vs OOS Degradation Analysis (flags >50% Sharpe drop)
    3. Best Strategy Per Asset Class
    4. FTMO Viability Assessment (Monte Carlo pass rates)
    5. Correlation Warnings (if daily_returns.csv files exist)
"""

import os
import sys
import json
import argparse
from pathlib import Path
from collections import defaultdict

import pandas as pd
import numpy as np


# ════════════════════════════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════════════════════════════

ASSET_CLASS_MAP = {
    # Crypto
    "BTC-USD": "crypto", "ETH-USD": "crypto", "SOL-USD": "crypto",
    "LTC-USD": "crypto", "XRP-USD": "crypto", "ADA-USD": "crypto",
    "DOT-USD": "crypto", "DOGE-USD": "crypto", "AVAX-USD": "crypto",
    "BNB-USD": "crypto", "LINK-USD": "crypto", "AAVE-USD": "crypto",
    "DASH-USD": "crypto", "EOS-USD": "crypto", "XLM-USD": "crypto",
    # Indices
    "^DJI": "indices", "^GSPC": "indices", "^IXIC": "indices",
    "^GDAXI": "indices", "^FTSE": "indices", "^N225": "indices",
    "YM=F": "indices", "NQ=F": "indices", "ES=F": "indices",
    # Forex (yfinance format)
    "EURUSD=X": "forex", "GBPUSD=X": "forex", "USDJPY=X": "forex",
    "AUDUSD=X": "forex", "USDCAD=X": "forex", "NZDUSD=X": "forex",
    "USDCHF=X": "forex",
    # Commodities
    "GC=F": "commodities", "CL=F": "commodities", "SI=F": "commodities",
    "NG=F": "commodities",
}


def detect_asset_class(ticker, instrument_type=None):
    """Detect asset class from ticker or metadata instrument_type."""
    if ticker in ASSET_CLASS_MAP:
        return ASSET_CLASS_MAP[ticker]
    if instrument_type:
        it = instrument_type.lower()
        if "crypto" in it:
            return "crypto"
        if "forex" in it:
            return "forex"
        if "equit" in it or "etf" in it:
            return "equity"
    # Heuristics
    if "-USD" in ticker and ticker.replace("-USD", "").isalpha():
        return "crypto"
    if "=X" in ticker:
        return "forex"
    if "=F" in ticker or ticker.startswith("^"):
        return "indices/commodities"
    return "other"


# ════════════════════════════════════════════════════════════════
# SCAN & LOAD
# ════════════════════════════════════════════════════════════════

def find_export_dir():
    """Find the strategy_exports directory (Colab Drive or local)."""
    candidates = [
        "/content/drive/MyDrive/strategy_exports",  # Colab
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "strategy_exports"),  # Relative to script
        "./strategy_exports",  # CWD
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return None


def scan_summaries(export_dir):
    """Walk the export tree and collect all summary.json data."""
    records = []
    export_path = Path(export_dir)

    for summary_path in export_path.rglob("summary.json"):
        # Only pick up files in 'latest/' subdirectories, skip archive
        if "archive" in str(summary_path):
            continue
        try:
            with open(summary_path, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        meta = data.get("metadata", {})
        full_m = data.get("metrics_full_sample", {})
        is_m = data.get("metrics_in_sample", {})
        oos_m = data.get("metrics_out_of_sample", {})
        bh_m = data.get("metrics_buy_hold", {})
        mc = data.get("monte_carlo_ftmo", {})
        params = data.get("best_params", {})

        ticker = meta.get("ticker", summary_path.parent.parent.name)
        strategy = meta.get("strategy_name", summary_path.parent.parent.parent.name)
        instrument_type = meta.get("instrument_type", "")

        # Check for daily_returns.csv alongside summary.json
        returns_path = summary_path.parent / "daily_returns.csv"
        has_returns = returns_path.exists()

        rec = {
            "strategy": strategy,
            "ticker": ticker,
            "asset_class": detect_asset_class(ticker, instrument_type),
            "run_id": meta.get("run_id", ""),
            "date": meta.get("export_date_human", ""),
            "data_range": f"{meta.get('start_date','')} to {meta.get('end_date','')}",
            "total_bars": meta.get("total_bars"),
            "params": str(params),
            # Full sample metrics
            "sharpe": full_m.get("sharpe"),
            "sortino": full_m.get("sortino"),
            "total_return": full_m.get("total_return"),
            "max_dd": full_m.get("max_dd"),
            "calmar": full_m.get("calmar"),
            "volatility": full_m.get("volatility"),
            "trades": full_m.get("trades"),
            "trades_yr": full_m.get("trades_yr"),
            "win_rate": full_m.get("win_rate"),
            "profit_factor": full_m.get("pf"),
            "expectancy": full_m.get("expectancy"),
            # IS/OOS
            "is_sharpe": is_m.get("sharpe"),
            "is_return": is_m.get("return"),
            "oos_sharpe": oos_m.get("sharpe"),
            "oos_return": oos_m.get("return"),
            # Buy & Hold
            "bh_sharpe": bh_m.get("sharpe"),
            "bh_return": bh_m.get("return"),
            # Monte Carlo
            "mc_pass_rate": mc.get("pass_rate"),
            "mc_verdict": mc.get("verdict"),
            "mc_median_equity": mc.get("median_final_equity"),
            # Paths
            "returns_csv": str(returns_path) if has_returns else None,
            "summary_path": str(summary_path),
        }
        records.append(rec)

    return pd.DataFrame(records)


# ════════════════════════════════════════════════════════════════
# TERMINAL OUTPUT HELPERS
# ════════════════════════════════════════════════════════════════

def _c(text, code):
    """ANSI color wrapper."""
    return f"\033[{code}m{text}\033[0m"

def green(t):  return _c(t, "32")
def red(t):    return _c(t, "31")
def yellow(t): return _c(t, "33")
def cyan(t):   return _c(t, "36")
def bold(t):   return _c(t, "1")
def dim(t):    return _c(t, "2")

def fmt_pct(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "   N/A"
    return f"{v*100:+7.2f}%"

def fmt_f(v, decimals=3):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "  N/A"
    return f"{v:{decimals+5}.{decimals}f}"

def sharpe_color(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return dim("  N/A")
    s = f"{v:6.3f}"
    if v >= 1.5:
        return green(s)
    elif v >= 0.5:
        return cyan(s)
    elif v >= 0.0:
        return yellow(s)
    else:
        return red(s)


# ════════════════════════════════════════════════════════════════
# REPORT SECTIONS
# ════════════════════════════════════════════════════════════════

def section_header(title):
    w = 78
    print()
    print(bold("=" * w))
    print(bold(f"  {title}"))
    print(bold("=" * w))


def print_leaderboard(df, top_n=20):
    """Section 1: Sharpe Ratio Leaderboard."""
    section_header("SHARPE RATIO LEADERBOARD")

    ranked = df.dropna(subset=["sharpe"]).sort_values("sharpe", ascending=False).head(top_n)
    if ranked.empty:
        print("  No strategies with valid Sharpe ratios found.")
        return

    header = (f"{'#':>3}  {'Strategy':<20} {'Ticker':<10} {'Sharpe':>7} "
              f"{'Return':>9} {'MaxDD':>9} {'WR%':>6} {'Trades':>6} {'PF':>6}")
    print(dim(header))
    print(dim("-" * len(header)))

    for i, (_, row) in enumerate(ranked.iterrows(), 1):
        sharpe_str = sharpe_color(row["sharpe"])
        ret_str = fmt_pct(row["total_return"])
        dd_str = fmt_pct(row["max_dd"])
        wr = f"{row['win_rate']:5.1f}%" if pd.notna(row.get("win_rate")) else "  N/A"
        tr = f"{int(row['trades']):5d}" if pd.notna(row.get("trades")) else "  N/A"
        pf = fmt_f(row.get("profit_factor"), 2) if pd.notna(row.get("profit_factor")) else "  N/A"
        strat = row["strategy"][:20]
        tick = row["ticker"][:10]

        print(f"{i:3d}  {strat:<20} {tick:<10} {sharpe_str} {ret_str} {dd_str} {wr} {tr} {pf}")

    print()
    total = len(df)
    pos = len(df[df["sharpe"] > 0]) if "sharpe" in df.columns else 0
    print(dim(f"  {total} total runs  |  {pos} positive Sharpe  |  "
              f"{total - pos} negative/missing"))


def print_is_oos_degradation(df):
    """Section 2: IS vs OOS Sharpe Degradation."""
    section_header("IS vs OOS SHARPE DEGRADATION")

    subset = df.dropna(subset=["is_sharpe", "oos_sharpe"]).copy()
    if subset.empty:
        print("  No strategies with both IS and OOS Sharpe data found.")
        return

    subset["sharpe_drop_pct"] = np.where(
        subset["is_sharpe"].abs() > 1e-6,
        (1 - subset["oos_sharpe"] / subset["is_sharpe"]) * 100,
        np.nan
    )
    subset = subset.sort_values("sharpe_drop_pct", ascending=False)

    header = (f"{'Strategy':<20} {'Ticker':<10} {'IS Sharpe':>10} {'OOS Sharpe':>11} "
              f"{'Drop %':>8} {'Flag':>8}")
    print(dim(header))
    print(dim("-" * len(header)))

    flagged = 0
    for _, row in subset.iterrows():
        is_s = fmt_f(row["is_sharpe"])
        oos_s = fmt_f(row["oos_sharpe"])
        drop = row["sharpe_drop_pct"]
        drop_str = f"{drop:+7.1f}%" if pd.notna(drop) else "    N/A"

        if pd.notna(drop) and drop > 50:
            flag = red("OVERFIT")
            flagged += 1
        elif pd.notna(drop) and drop > 25:
            flag = yellow("  WARN")
        elif pd.notna(drop) and drop < -10:
            flag = green("  GOOD")  # OOS better than IS
        else:
            flag = dim("    OK")

        strat = row["strategy"][:20]
        tick = row["ticker"][:10]
        print(f"{strat:<20} {tick:<10} {is_s:>10} {oos_s:>11} {drop_str} {flag}")

    print()
    if flagged > 0:
        print(red(f"  WARNING: {flagged} strategies show >50% OOS Sharpe degradation "
                  f"(likely overfitting)"))
    else:
        print(green("  All strategies show acceptable IS->OOS degradation."))


def print_best_per_asset(df):
    """Section 3: Best Strategy Per Asset Class."""
    section_header("BEST STRATEGY PER ASSET CLASS")

    if df.empty or "asset_class" not in df.columns:
        print("  No data available.")
        return

    asset_classes = sorted(df["asset_class"].dropna().unique())
    if not asset_classes:
        print("  No asset class data found.")
        return

    header = (f"{'Asset Class':<20} {'Best Strategy':<20} {'Ticker':<10} "
              f"{'Sharpe':>7} {'OOS Sharpe':>11} {'FTMO':>10}")
    print(dim(header))
    print(dim("-" * len(header)))

    for ac in asset_classes:
        ac_df = df[df["asset_class"] == ac].dropna(subset=["sharpe"])
        if ac_df.empty:
            print(f"{ac:<20} {'(no valid runs)':<20}")
            continue

        best = ac_df.loc[ac_df["sharpe"].idxmax()]
        strat = best["strategy"][:20]
        tick = best["ticker"][:10]
        sharpe_str = sharpe_color(best["sharpe"])
        oos_str = fmt_f(best.get("oos_sharpe"))
        ftmo = best.get("mc_verdict", "N/A")
        if ftmo == "FAVORABLE":
            ftmo = green(ftmo)
        elif ftmo == "POSSIBLE":
            ftmo = cyan(ftmo)
        elif ftmo == "CHALLENGING":
            ftmo = yellow(ftmo)
        elif ftmo == "UNLIKELY":
            ftmo = red(ftmo)

        print(f"{ac:<20} {strat:<20} {tick:<10} {sharpe_str} {oos_str:>11} {ftmo:>10}")

        # Show runner-ups
        others = ac_df.nlargest(3, "sharpe")
        for _, r in others.iloc[1:].iterrows():
            s2 = r["strategy"][:20]
            t2 = r["ticker"][:10]
            print(dim(f"{'':20} {s2:<20} {t2:<10} {fmt_f(r['sharpe']):>7}"))


def print_ftmo_assessment(df):
    """Section 4: FTMO Viability Assessment."""
    section_header("FTMO VIABILITY ASSESSMENT (Monte Carlo)")

    subset = df.dropna(subset=["mc_pass_rate"]).sort_values("mc_pass_rate", ascending=False)
    if subset.empty:
        print("  No Monte Carlo FTMO data found in any exports.")
        return

    header = (f"{'Strategy':<20} {'Ticker':<10} {'Pass Rate':>10} "
              f"{'Verdict':<12} {'Med. Equity':>12} {'Sharpe':>7}")
    print(dim(header))
    print(dim("-" * len(header)))

    for _, row in subset.iterrows():
        strat = row["strategy"][:20]
        tick = row["ticker"][:10]
        pr = row["mc_pass_rate"]
        pr_str = f"{pr:6.1f}%"

        if pr >= 50:
            pr_str = green(pr_str)
        elif pr >= 25:
            pr_str = cyan(pr_str)
        elif pr >= 10:
            pr_str = yellow(pr_str)
        else:
            pr_str = red(pr_str)

        verdict = row.get("mc_verdict", "N/A")
        vcolor = {"FAVORABLE": green, "POSSIBLE": cyan,
                  "CHALLENGING": yellow, "UNLIKELY": red}.get(verdict, dim)
        verdict_str = vcolor(f"{verdict:<12}")

        med_eq = row.get("mc_median_equity")
        med_str = f"${med_eq:>10,.0f}" if pd.notna(med_eq) else "       N/A"
        sharpe_str = sharpe_color(row.get("sharpe"))

        print(f"{strat:<20} {tick:<10} {pr_str:>10} {verdict_str} {med_str} {sharpe_str}")

    # Summary stats
    viable = len(subset[subset["mc_pass_rate"] >= 25])
    print()
    print(f"  {viable}/{len(subset)} strategies have FTMO pass rate >= 25% "
          f"(POSSIBLE or better)")


def print_correlation_warnings(df, threshold=0.70):
    """Section 5: Correlation Warnings between strategy pairs."""
    section_header(f"CORRELATION WARNINGS (threshold > {threshold:.0%})")

    returns_files = df.dropna(subset=["returns_csv"])
    if len(returns_files) < 2:
        print("  Need at least 2 strategies with daily_returns.csv for correlation analysis.")
        print(dim("  Run more backtests with the universal export cell to enable this."))
        return

    # Load daily returns
    returns_dict = {}
    for _, row in returns_files.iterrows():
        label = f"{row['strategy']}|{row['ticker']}"
        try:
            ret_df = pd.read_csv(row["returns_csv"])
            if "strategy_return" in ret_df.columns and "date" in ret_df.columns:
                series = pd.Series(
                    ret_df["strategy_return"].values,
                    index=pd.to_datetime(ret_df["date"]),
                    name=label,
                )
                returns_dict[label] = series
        except Exception:
            continue

    if len(returns_dict) < 2:
        print("  Could not load enough daily_returns.csv files for correlation.")
        return

    # Build correlation matrix on overlapping dates
    combined = pd.DataFrame(returns_dict)
    corr = combined.corr()

    # Find high correlations
    pairs = []
    labels = list(corr.columns)
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            c = corr.iloc[i, j]
            if pd.notna(c) and abs(c) > threshold:
                pairs.append((labels[i], labels[j], c))

    pairs.sort(key=lambda x: abs(x[2]), reverse=True)

    if not pairs:
        print(green(f"  No highly correlated pairs found (all below {threshold:.0%})."))
        print(f"  Checked {len(returns_dict)} strategy-ticker combinations.")
        return

    header = f"{'Strategy A':<30} {'Strategy B':<30} {'Corr':>7}"
    print(dim(header))
    print(dim("-" * len(header)))

    for a, b, c in pairs:
        c_str = f"{c:+.3f}"
        if abs(c) > 0.9:
            c_str = red(c_str)
        elif abs(c) > 0.8:
            c_str = yellow(c_str)
        else:
            c_str = cyan(c_str)
        print(f"{a:<30} {b:<30} {c_str}")

    print()
    print(yellow(f"  WARNING: {len(pairs)} highly correlated pairs detected."))
    print(dim("  Consider diversifying — correlated strategies provide redundant exposure."))
    print(dim("  (Carver: correlation between subsystem returns ~ 0.70 * instrument correlation)"))


# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Strategy Dashboard — Master comparison of all strategy runs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--export-dir", type=str, default=None,
                        help="Path to strategy_exports directory")
    parser.add_argument("--csv", type=str, default=None,
                        help="Output master table to CSV file")
    parser.add_argument("--top", type=int, default=20,
                        help="Number of strategies in leaderboard (default: 20)")
    parser.add_argument("--min-trades", type=int, default=5,
                        help="Minimum trades to include a run (default: 5)")
    parser.add_argument("--corr-threshold", type=float, default=0.70,
                        help="Correlation warning threshold (default: 0.70)")
    args = parser.parse_args()

    # Find export directory
    export_dir = args.export_dir or find_export_dir()
    if export_dir is None or not os.path.isdir(export_dir):
        print(red("ERROR: Cannot find strategy_exports directory."))
        print("Searched:")
        print("  - /content/drive/MyDrive/strategy_exports  (Colab)")
        print("  - ./strategy_exports                       (local)")
        print()
        print("Use --export-dir to specify the path, or run a strategy notebook")
        print("with the universal export cell first.")
        sys.exit(1)

    print(bold(f"\n{'='*78}"))
    print(bold(f"  QS FINANCE — STRATEGY DASHBOARD"))
    print(bold(f"{'='*78}"))
    print(dim(f"  Export dir: {export_dir}"))

    # Scan
    df = scan_summaries(export_dir)
    if df.empty:
        print(red("\n  No summary.json files found in the export directory."))
        print("  Run at least one strategy notebook with the universal export cell.")
        sys.exit(1)

    # Filter by min trades
    if args.min_trades > 0:
        before = len(df)
        df = df[df["trades"].fillna(0) >= args.min_trades]
        filtered = before - len(df)
        if filtered > 0:
            print(dim(f"  Filtered out {filtered} runs with < {args.min_trades} trades"))

    n_strats = df["strategy"].nunique()
    n_tickers = df["ticker"].nunique()
    print(f"  Found {bold(str(len(df)))} runs across "
          f"{bold(str(n_strats))} strategies and {bold(str(n_tickers))} tickers")

    # Print all sections
    print_leaderboard(df, top_n=args.top)
    print_is_oos_degradation(df)
    print_best_per_asset(df)
    print_ftmo_assessment(df)
    print_correlation_warnings(df, threshold=args.corr_threshold)

    # Optional CSV export
    if args.csv:
        csv_cols = [
            "strategy", "ticker", "asset_class", "run_id", "date", "params",
            "sharpe", "sortino", "total_return", "max_dd", "calmar",
            "win_rate", "profit_factor", "trades", "trades_yr",
            "is_sharpe", "oos_sharpe", "is_return", "oos_return",
            "bh_sharpe", "bh_return",
            "mc_pass_rate", "mc_verdict", "mc_median_equity",
        ]
        out_cols = [c for c in csv_cols if c in df.columns]
        df[out_cols].to_csv(args.csv, index=False)
        print(f"\n{green('CSV exported:')} {args.csv}")

    print(bold(f"\n{'='*78}\n"))


if __name__ == "__main__":
    main()
