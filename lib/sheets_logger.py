"""
Google Sheets Logger -- Auto-log backtest results to a master Google Sheet.

Usage (in any notebook):
    from lib.sheets_logger import SheetsLogger
    logger = SheetsLogger()  # creates or opens "Trading Strategy Results" sheet
    logger.log_result(summary_dict)  # appends a row from summary.json-style dict
    logger.log_boruta(boruta_results)  # appends Boruta validation results
"""

import json
import pandas as pd
from datetime import datetime

# Sheet name constant
SPREADSHEET_NAME = "QS Finance \u2014 Strategy Results"

# Column headers for the main results sheet
RESULTS_COLUMNS = [
    'timestamp', 'run_id', 'ticker', 'strategy', 'strategy_family',
    'fast_param', 'slow_param', 'filter_param',
    'is_sharpe', 'is_return', 'is_max_dd', 'is_trades',
    'oos_sharpe', 'oos_return', 'oos_max_dd', 'oos_trades',
    'full_sharpe', 'full_return', 'full_max_dd', 'full_trades',
    'win_rate', 'profit_factor', 'expectancy', 'payoff_ratio',
    'sharpe_degradation',  # (IS - OOS) / IS -- flags overfitting
    'bh_sharpe', 'bh_return',
    'mc_ftmo_pass_rate', 'mc_verdict',
    'data_start', 'data_end', 'total_bars',
    'notes'
]

# Column headers for Boruta sheet
BORUTA_COLUMNS = [
    'timestamp', 'ticker', 'ensemble_name', 'strategies_included',
    'is_sharpe', 'oos_sharpe', 'sharpe_degradation',
    'boruta_score', 'boruta_verdict', 'n_shuffles',
    'is_return', 'oos_return', 'is_max_dd', 'oos_max_dd',
    'notes'
]

# Column headers for trade log sheet
TRADES_COLUMNS = [
    'timestamp', 'ticker', 'strategy', 'run_id',
    'entry_date', 'exit_date', 'direction', 'return_pct',
    'holding_days', 'is_winner'
]


def _authenticate():
    """Authenticate with Google and return gspread client. Only works in Colab."""
    try:
        from google.colab import auth
        import gspread
        from google.auth import default

        auth.authenticate_user()
        creds, _ = default()
        gc = gspread.authorize(creds)
        return gc
    except ImportError:
        print("\u26a0\ufe0f  Google Sheets logger only works in Google Colab.")
        print("   Results will be saved locally instead.")
        return None


class SheetsLogger:
    def __init__(self, spreadsheet_name=None):
        """Initialize and connect to Google Sheets. Creates spreadsheet if it doesn't exist."""
        self.spreadsheet_name = spreadsheet_name or SPREADSHEET_NAME
        self.gc = _authenticate()
        self.spreadsheet = None

        if self.gc is None:
            return

        import gspread

        # Try to open existing, or create new
        try:
            self.spreadsheet = self.gc.open(self.spreadsheet_name)
            print(f"\U0001f4ca Connected to existing sheet: {self.spreadsheet_name}")
        except gspread.SpreadsheetNotFound:
            self.spreadsheet = self.gc.create(self.spreadsheet_name)
            print(f"\U0001f4ca Created new sheet: {self.spreadsheet_name}")

        # Ensure all worksheets exist with headers
        self._ensure_worksheet('Results', RESULTS_COLUMNS)
        self._ensure_worksheet('Boruta', BORUTA_COLUMNS)
        self._ensure_worksheet('Trades', TRADES_COLUMNS)

        # Remove default Sheet1 if our sheets were just created
        try:
            default_sheet = self.spreadsheet.worksheet('Sheet1')
            if len(self.spreadsheet.worksheets()) > 1:
                self.spreadsheet.del_worksheet(default_sheet)
        except gspread.WorksheetNotFound:
            pass

        url = self.spreadsheet.url
        print(f"\U0001f517 Sheet URL: {url}")

    def _ensure_worksheet(self, name, columns):
        """Create worksheet with headers if it doesn't exist."""
        import gspread

        try:
            ws = self.spreadsheet.worksheet(name)
            # Check if headers are there
            if not ws.row_values(1):
                ws.append_row(columns)
        except gspread.WorksheetNotFound:
            ws = self.spreadsheet.add_worksheet(title=name, rows=1000, cols=len(columns))
            ws.append_row(columns)
            # Bold header row
            ws.format('1', {'textFormat': {'bold': True}})
        return ws

    def log_result(self, summary):
        """
        Log a backtest result from a summary.json-style dict.

        Parameters
        ----------
        summary : dict
            The summary dict from any strategy notebook export.
            Expected keys: metadata, best_params, metrics_in_sample,
            metrics_out_of_sample, metrics_full_sample, metrics_buy_hold,
            monte_carlo_ftmo
        """
        if self.spreadsheet is None:
            print("\u26a0\ufe0f  Not connected to Google Sheets. Skipping log.")
            return

        meta = summary.get('metadata', {})
        params = summary.get('best_params', {})
        is_m = summary.get('metrics_in_sample', {})
        oos_m = summary.get('metrics_out_of_sample', {})
        full_m = summary.get('metrics_full_sample', {})
        bh = summary.get('metrics_buy_hold', {})
        mc = summary.get('monte_carlo_ftmo', {})

        # Extract param values (generic -- works for any strategy)
        param_values = list(params.values())
        fast_p = param_values[0] if len(param_values) > 0 else ''
        slow_p = param_values[1] if len(param_values) > 1 else ''
        filter_p = param_values[2] if len(param_values) > 2 else ''

        # Sharpe degradation
        is_sharpe = is_m.get('sharpe', 0)
        oos_sharpe = oos_m.get('sharpe', 0)
        degradation = (is_sharpe - oos_sharpe) / is_sharpe if is_sharpe != 0 else 0

        row = [
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            meta.get('run_id', ''),
            meta.get('ticker', ''),
            meta.get('strategy_name', ''),
            meta.get('strategy_family', ''),
            fast_p, slow_p, filter_p,
            round(is_sharpe, 4),
            round(is_m.get('return', 0), 4),
            round(is_m.get('dd', 0), 4),
            is_m.get('trades', 0),
            round(oos_sharpe, 4),
            round(oos_m.get('return', 0), 4),
            round(oos_m.get('dd', 0), 4),
            oos_m.get('trades', 0),
            round(full_m.get('sharpe', 0), 4),
            round(full_m.get('total_return', 0), 4),
            round(full_m.get('max_dd', 0), 4),
            full_m.get('trades', 0),
            round(full_m.get('win_rate', 0), 2),
            round(full_m.get('pf', 0), 4),
            round(full_m.get('expectancy', 0), 6),
            round(full_m.get('payoff', 0), 4),
            round(degradation, 4),
            round(bh.get('sharpe', 0), 4),
            round(bh.get('return', 0), 4),
            round(mc.get('pass_rate', 0), 4),
            mc.get('verdict', ''),
            meta.get('start_date', ''),
            meta.get('end_date', ''),
            meta.get('total_bars', 0),
            meta.get('notes', '')
        ]

        ws = self.spreadsheet.worksheet('Results')
        ws.append_row(row, value_input_option='USER_ENTERED')
        print(f"\u2705 Logged: {meta.get('strategy_name', '?')} on {meta.get('ticker', '?')} \u2192 IS Sharpe {is_sharpe:.2f} / OOS Sharpe {oos_sharpe:.2f}")

    def log_boruta(self, ticker, ensemble_results):
        """
        Log Boruta validation results.

        Parameters
        ----------
        ticker : str
        ensemble_results : list of dicts with keys:
            ensemble_name, strategies, is_sharpe, oos_sharpe,
            boruta_score, verdict, n_shuffles, is_return, oos_return,
            is_max_dd, oos_max_dd
        """
        if self.spreadsheet is None:
            return

        ws = self.spreadsheet.worksheet('Boruta')

        for r in ensemble_results:
            is_s = r.get('is_sharpe', 0)
            oos_s = r.get('oos_sharpe', 0)
            degradation = (is_s - oos_s) / is_s if is_s != 0 else 0

            row = [
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                ticker,
                r.get('ensemble_name', ''),
                r.get('strategies', ''),
                round(is_s, 4),
                round(oos_s, 4),
                round(degradation, 4),
                round(r.get('boruta_score', 0), 4),
                r.get('verdict', ''),
                r.get('n_shuffles', 500),
                round(r.get('is_return', 0), 4),
                round(r.get('oos_return', 0), 4),
                round(r.get('is_max_dd', 0), 4),
                round(r.get('oos_max_dd', 0), 4),
                r.get('notes', '')
            ]
            ws.append_row(row, value_input_option='USER_ENTERED')

        confirmed = sum(1 for r in ensemble_results if r.get('verdict') == 'CONFIRMED')
        print(f"\u2705 Logged {len(ensemble_results)} Boruta results for {ticker} ({confirmed} confirmed)")

    def log_trades(self, ticker, strategy, run_id, trades_df):
        """
        Log individual trades from a trades DataFrame.

        Parameters
        ----------
        trades_df : pd.DataFrame
            With columns: entry_date, exit_date, return, holding_days (or similar)
        """
        if self.spreadsheet is None:
            return

        ws = self.spreadsheet.worksheet('Trades')
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        rows = []
        for _, trade in trades_df.iterrows():
            entry = str(trade.get('entry_date', trade.get('Entry Timestamp', '')))
            exit_d = str(trade.get('exit_date', trade.get('Exit Timestamp', '')))
            ret = trade.get('return', trade.get('Return', trade.get('PnL', 0)))
            days = trade.get('holding_days', trade.get('Duration', ''))

            rows.append([
                ts, ticker, strategy, run_id,
                entry, exit_d, 'LONG',
                round(float(ret), 6) if ret else 0,
                str(days),
                'YES' if float(ret) > 0 else 'NO'
            ])

        # Batch append
        for row in rows:
            ws.append_row(row, value_input_option='USER_ENTERED')

        print(f"\u2705 Logged {len(rows)} trades for {strategy} on {ticker}")

    def import_summary_json(self, filepath):
        """Import a summary.json file directly."""
        with open(filepath, 'r') as f:
            summary = json.load(f)
        self.log_result(summary)

    def import_all_exports(self, exports_dir):
        """
        Scan an exports directory and import all summary.json files found.

        Expected structure:
            exports_dir/STRATEGY/TICKER/latest/summary.json
            or exports_dir/STRATEGY/TICKER/archive/*.json
        """
        from pathlib import Path

        export_path = Path(exports_dir)
        summaries = list(export_path.rglob('summary.json'))

        if not summaries:
            print(f"No summary.json files found in {exports_dir}")
            return

        print(f"Found {len(summaries)} summary files to import...")

        for s in summaries:
            try:
                self.import_summary_json(str(s))
            except Exception as e:
                print(f"\u26a0\ufe0f  Failed to import {s}: {e}")

        print(f"\n\u2705 Import complete: {len(summaries)} results logged to Google Sheets")

    def get_results_df(self):
        """Download the Results sheet as a pandas DataFrame."""
        if self.spreadsheet is None:
            return pd.DataFrame()
        ws = self.spreadsheet.worksheet('Results')
        data = ws.get_all_records()
        return pd.DataFrame(data)

    def get_boruta_df(self):
        """Download the Boruta sheet as a pandas DataFrame."""
        if self.spreadsheet is None:
            return pd.DataFrame()
        ws = self.spreadsheet.worksheet('Boruta')
        data = ws.get_all_records()
        return pd.DataFrame(data)
