"""
Run a strategy notebook from the command line or Colab.

Usage:
    # From Colab or terminal:
    !python scripts/run_strategy.py --strategy MACD --ticker BTC-USD --start 2020-01-01

    # Run all crypto tickers through Donchian:
    !python scripts/run_strategy.py --strategy Donchian --tickers BTC-USD,ETH-USD,SOL-USD

    # Just pull latest and open a notebook (no auto-run):
    !python scripts/run_strategy.py --pull-only
"""

import argparse, subprocess, sys, os, json

NOTEBOOK_MAP = {
    "MACD":     "notebooks/MACD_Crossover_Strategy_v2.ipynb",
    "RSI":      "notebooks/RSI_Mean_Reversion_Strategy.ipynb",
    "EMA":      "notebooks/EMA_Crossover_Strategy.ipynb",
    "Donchian": "notebooks/Donchian_Channel_Breakout_Strategy.ipynb",
}

def pull_latest():
    """Pull latest from GitHub."""
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(repo_dir)
    result = subprocess.run(["git", "pull"], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Repo up to date: {result.stdout.strip()}")
    else:
        print(f"Git pull issue: {result.stderr.strip()}")
    return repo_dir

def run_notebook(notebook_path, ticker, start_date, output_dir=None):
    """Execute a notebook with papermill, injecting parameters."""
    try:
        import papermill as pm
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "papermill"])
        import papermill as pm

    out_path = output_dir or os.path.dirname(notebook_path)
    nb_name = os.path.basename(notebook_path).replace(".ipynb", "")
    output_nb = os.path.join(out_path, f"{nb_name}_{ticker.replace('-','_')}_run.ipynb")

    print(f"\nRunning: {nb_name}")
    print(f"  Ticker: {ticker}")
    print(f"  Start:  {start_date}")
    print(f"  Output: {output_nb}")

    pm.execute_notebook(
        notebook_path,
        output_nb,
        parameters={"TICKER": ticker, "START_DATE": start_date},
    )
    print(f"Done: {output_nb}")
    return output_nb

def main():
    parser = argparse.ArgumentParser(description="Run trading strategy notebooks")
    parser.add_argument("--strategy", "-s", choices=list(NOTEBOOK_MAP.keys()),
                        help="Strategy to run")
    parser.add_argument("--ticker", "-t", default="BTC-USD",
                        help="Single ticker (default: BTC-USD)")
    parser.add_argument("--tickers", help="Comma-separated list of tickers")
    parser.add_argument("--start", default="2020-01-01",
                        help="Start date (default: 2020-01-01)")
    parser.add_argument("--pull-only", action="store_true",
                        help="Just pull latest, don't run anything")
    parser.add_argument("--no-pull", action="store_true",
                        help="Skip git pull")
    parser.add_argument("--list", action="store_true",
                        help="List available strategies")
    args = parser.parse_args()

    if args.list:
        print("Available strategies:")
        for key, path in NOTEBOOK_MAP.items():
            print(f"  {key:10s} → {path}")
        # Load recommended asset mapping
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                   "config", "tickers.json")
        if os.path.exists(config_path):
            with open(config_path) as f:
                cfg = json.load(f)
            print("\nRecommended asset-strategy mapping:")
            for asset_class, strategies in cfg.get("asset_strategy_map", {}).items():
                print(f"  {asset_class:15s} → {', '.join(strategies)}")
        return

    if not args.no_pull:
        pull_latest()

    if args.pull_only:
        print("Pull complete. Open notebooks manually.")
        return

    if not args.strategy:
        parser.print_help()
        return

    notebook = NOTEBOOK_MAP[args.strategy]
    tickers = args.tickers.split(",") if args.tickers else [args.ticker]

    for ticker in tickers:
        ticker = ticker.strip()
        print(f"\n{'='*50}")
        run_notebook(notebook, ticker, args.start)

if __name__ == "__main__":
    main()
