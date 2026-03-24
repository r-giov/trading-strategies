"""
Monte Carlo FTMO challenge simulation service.
Runs bootstrap simulations of daily returns against FTMO pass/fail constraints.

FTMO rules (current):
  - Profit target: 10% ($10K on $100K)
  - Max daily loss: 5% ($5K)
  - Max total loss: 10% ($10K)
  - NO time limit (removed by FTMO)
  - Sim caps at max_days to prevent infinite loops
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import deps  # noqa: E402, F401

import csv
import random
import statistics

EXPORTS_DIR = deps.EXPORTS_DIR

# FTMO Challenge constants
ACCOUNT = 100_000
PROFIT_TARGET = 0.10
MAX_DAILY_LOSS = 0.05
MAX_TOTAL_LOSS = 0.10
DEFAULT_MAX_DAYS = 365  # safety cap — no FTMO challenge lasts a year


def run_monte_carlo(daily_returns: list[float], n_sims: int = 5000, max_days: int = DEFAULT_MAX_DAYS) -> dict:
    """Run Monte Carlo simulation of FTMO challenge.

    No time limit — each simulation runs until the strategy either:
      1. Hits +10% profit target (PASS)
      2. Breaches -5% daily loss (BLOWN daily)
      3. Breaches -10% total loss (BLOWN total)
      4. Reaches max_days without resolution (STILL TRADING)
    """
    results = []
    paths = []  # store first 150 paths for visualization
    days_to_pass = []  # track how long passing sims take

    for s in range(n_sims):
        eq = ACCOUNT
        passed = blown_total = blown_daily = False
        path = [ACCOUNT]
        end_day = max_days

        for d in range(max_days):
            day_start = eq
            idx = random.randint(0, len(daily_returns) - 1)
            eq = eq * (1 + daily_returns[idx])
            path.append(eq)

            if (eq - day_start) / ACCOUNT < -MAX_DAILY_LOSS:
                blown_daily = True
                end_day = d + 1
                break
            if (eq - ACCOUNT) / ACCOUNT < -MAX_TOTAL_LOSS:
                blown_total = True
                end_day = d + 1
                break
            if (eq - ACCOUNT) / ACCOUNT >= PROFIT_TARGET:
                passed = True
                end_day = d + 1
                days_to_pass.append(d + 1)
                break

        results.append({
            "final": eq,
            "passed": passed,
            "blown_total": blown_total,
            "blown_daily": blown_daily,
            "days": end_day,
        })

        # For visualization, cap paths at 90 days for readability
        viz_path = path[:91]
        while len(viz_path) < 91:
            viz_path.append(viz_path[-1])
        if s < 150:
            paths.append(viz_path)

    n_passed = sum(1 for r in results if r["passed"])
    n_blown_t = sum(1 for r in results if r["blown_total"])
    n_blown_d = sum(1 for r in results if r["blown_daily"])
    n_still = n_sims - n_passed - n_blown_t - n_blown_d

    return {
        "n_passed": n_passed,
        "n_blown_total": n_blown_t,
        "n_blown_daily": n_blown_d,
        "n_still_trading": n_still,
        "n_sims": n_sims,
        "max_days": max_days,
        "pass_rate": n_passed / n_sims * 100,
        "blow_rate": (n_blown_t + n_blown_d) / n_sims * 100,
        "median_days_to_pass": statistics.median(days_to_pass) if days_to_pass else None,
        "avg_days_to_pass": sum(days_to_pass) / len(days_to_pass) if days_to_pass else None,
        "paths": paths,
        "chart_days": 90,
        "verdict": (
            "FAVORABLE" if n_passed / n_sims >= 0.5
            else "POSSIBLE" if n_passed / n_sims >= 0.25
            else "CHALLENGING" if n_passed / n_sims >= 0.1
            else "UNLIKELY"
        ),
        "rules": {
            "account": ACCOUNT,
            "profit_target_pct": PROFIT_TARGET * 100,
            "max_daily_loss_pct": MAX_DAILY_LOSS * 100,
            "max_total_loss_pct": MAX_TOTAL_LOSS * 100,
            "time_limit": "None (unlimited)",
        },
    }


def read_daily_returns_from_exports(strategy: str, ticker: str) -> list[float]:
    """Read daily_returns.csv from strategy_exports/{strategy}/{ticker}/latest/
    and extract the strategy_return column."""
    csv_path = EXPORTS_DIR / strategy / ticker / "latest" / "daily_returns.csv"

    if not csv_path.exists():
        raise FileNotFoundError(
            f"daily_returns.csv not found at {csv_path}"
        )

    daily_returns = []
    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            raise ValueError("CSV file is empty or has no header")

        if "strategy_return" not in reader.fieldnames:
            raise ValueError(
                f"'strategy_return' column not found. "
                f"Available columns: {reader.fieldnames}"
            )

        for row in reader:
            val = row["strategy_return"]
            if val and val.strip():
                try:
                    daily_returns.append(float(val))
                except ValueError:
                    continue

    if not daily_returns:
        raise ValueError("No valid daily returns found in CSV")

    return daily_returns
