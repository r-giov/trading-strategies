"""
Reads strategy_exports/ directory tree and returns structured data.
"""

import json
from pathlib import Path

import deps  # noqa: F401

EXPORTS_DIR = deps.EXPORTS_DIR


def list_strategies() -> list[dict]:
    """Walk strategy_exports/ and read all latest/summary.json files."""
    strategies = []

    if not EXPORTS_DIR.exists():
        return strategies

    for strategy_dir in sorted(EXPORTS_DIR.iterdir()):
        if not strategy_dir.is_dir() or strategy_dir.name.startswith("."):
            continue

        for ticker_dir in sorted(strategy_dir.iterdir()):
            if not ticker_dir.is_dir():
                continue

            summary_path = ticker_dir / "latest" / "summary.json"
            if not summary_path.exists():
                continue

            try:
                with open(summary_path, "r") as f:
                    data = json.load(f)
                strategies.append({
                    "strategy": strategy_dir.name,
                    "ticker": ticker_dir.name,
                    "summary": data,
                })
            except (json.JSONDecodeError, OSError):
                continue

    return strategies


def get_strategy_detail(strategy: str, ticker: str) -> dict | None:
    """Get full detail for a specific strategy-ticker pair."""
    base = EXPORTS_DIR / strategy / ticker / "latest"
    if not base.exists():
        return None

    result = {"strategy": strategy, "ticker": ticker}

    summary_path = base / "summary.json"
    if summary_path.exists():
        with open(summary_path, "r") as f:
            result["summary"] = json.load(f)

    return result
