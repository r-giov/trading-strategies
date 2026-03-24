"""
Market Data Pre-Fetcher for QS Finance Research AI.
Fetches real market data from Yahoo Finance BEFORE calling Claude,
so the AI cannot hallucinate numbers.
"""

import logging

import pandas as pd
import yfinance as yf

logger = logging.getLogger("qs-finance.market-data")


def fetch_market_data(ticker: str) -> dict:
    """Pre-fetch comprehensive market data for a ticker."""
    stock = yf.Ticker(ticker)

    data = {"ticker": ticker}

    # Current price info
    try:
        info = stock.info
        data["price"] = info.get("currentPrice") or info.get("regularMarketPrice")
        data["market_cap"] = info.get("marketCap")
        data["pe_ratio"] = info.get("trailingPE")
        data["forward_pe"] = info.get("forwardPE")
        data["ps_ratio"] = info.get("priceToSalesTrailing12Months")
        data["pb_ratio"] = info.get("priceToBook")
        data["ev_ebitda"] = info.get("enterpriseToEbitda")
        data["revenue"] = info.get("totalRevenue")
        data["revenue_growth"] = info.get("revenueGrowth")
        data["gross_margins"] = info.get("grossMargins")
        data["operating_margins"] = info.get("operatingMargins")
        data["profit_margins"] = info.get("profitMargins")
        data["free_cashflow"] = info.get("freeCashflow")
        data["total_cash"] = info.get("totalCash")
        data["total_debt"] = info.get("totalDebt")
        data["short_ratio"] = info.get("shortRatio")
        data["short_pct"] = info.get("shortPercentOfFloat")
        data["insider_pct"] = info.get("heldPercentInsiders")
        data["institution_pct"] = info.get("heldPercentInstitutions")
        data["sector"] = info.get("sector")
        data["industry"] = info.get("industry")
        data["company_name"] = info.get("longName") or info.get("shortName") or ticker
        data["description"] = info.get("longBusinessSummary", "")[:500]
        data["52w_high"] = info.get("fiftyTwoWeekHigh")
        data["52w_low"] = info.get("fiftyTwoWeekLow")
        data["50d_ma"] = info.get("fiftyDayAverage")
        data["200d_ma"] = info.get("twoHundredDayAverage")
        data["beta"] = info.get("beta")
        data["dividend_yield"] = info.get("dividendYield")
        data["target_price"] = info.get("targetMeanPrice")
        data["recommendation"] = info.get("recommendationKey")
        data["num_analysts"] = info.get("numberOfAnalystOpinions")
    except Exception as e:
        data["error"] = f"Failed to fetch info: {e}"
        logger.warning(f"Failed to fetch info for {ticker}: {e}")

    # Quarterly financials (last 4 quarters revenue)
    try:
        qf = stock.quarterly_financials
        if qf is not None and not qf.empty:
            rev_row = qf.loc["Total Revenue"] if "Total Revenue" in qf.index else None
            if rev_row is not None:
                data["quarterly_revenue"] = {
                    str(d.date()): float(v) for d, v in rev_row.items() if not pd.isna(v)
                }
    except Exception:
        pass

    # Remove None values
    data = {k: v for k, v in data.items() if v is not None}

    return data


def format_market_data_block(data: dict) -> str:
    """Format market data into a human-readable block for prompt injection."""

    def fmt_number(val, prefix="", suffix="", decimals=2):
        if val is None:
            return "N/A"
        if isinstance(val, (int, float)):
            if abs(val) >= 1_000_000_000_000:
                return f"{prefix}{val / 1_000_000_000_000:.{decimals}f}T{suffix}"
            if abs(val) >= 1_000_000_000:
                return f"{prefix}{val / 1_000_000_000:.{decimals}f}B{suffix}"
            if abs(val) >= 1_000_000:
                return f"{prefix}{val / 1_000_000:.{decimals}f}M{suffix}"
            return f"{prefix}{val:.{decimals}f}{suffix}"
        return str(val)

    def fmt_pct(val):
        if val is None:
            return "N/A"
        return f"{val * 100:.1f}%"

    lines = [
        f"TICKER: {data.get('ticker', 'N/A')}",
        f"COMPANY: {data.get('company_name', 'N/A')}",
        f"PRICE: {fmt_number(data.get('price'), prefix='$')}",
        f"MARKET_CAP: {fmt_number(data.get('market_cap'), prefix='$')}",
        f"P/S_RATIO: {fmt_number(data.get('ps_ratio'))}",
        f"P/E_RATIO: {fmt_number(data.get('pe_ratio'))}",
        f"FORWARD_P/E: {fmt_number(data.get('forward_pe'))}",
        f"P/B_RATIO: {fmt_number(data.get('pb_ratio'))}",
        f"EV/EBITDA: {fmt_number(data.get('ev_ebitda'))}",
        f"REVENUE_TTM: {fmt_number(data.get('revenue'), prefix='$')}",
        f"REVENUE_GROWTH: {fmt_pct(data.get('revenue_growth'))}",
        f"GROSS_MARGIN: {fmt_pct(data.get('gross_margins'))}",
        f"OPERATING_MARGIN: {fmt_pct(data.get('operating_margins'))}",
        f"PROFIT_MARGIN: {fmt_pct(data.get('profit_margins'))}",
        f"FREE_CASHFLOW: {fmt_number(data.get('free_cashflow'), prefix='$')}",
        f"CASH: {fmt_number(data.get('total_cash'), prefix='$')}",
        f"DEBT: {fmt_number(data.get('total_debt'), prefix='$')}",
        f"SHORT_RATIO: {fmt_number(data.get('short_ratio'))}",
        f"SHORT_INTEREST: {fmt_pct(data.get('short_pct'))}",
        f"INSIDER_OWNERSHIP: {fmt_pct(data.get('insider_pct'))}",
        f"INSTITUTIONAL: {fmt_pct(data.get('institution_pct'))}",
        f"SECTOR: {data.get('sector', 'N/A')}",
        f"INDUSTRY: {data.get('industry', 'N/A')}",
        f"BETA: {fmt_number(data.get('beta'))}",
        f"DIVIDEND_YIELD: {fmt_pct(data.get('dividend_yield'))}",
        f"52W_HIGH: {fmt_number(data.get('52w_high'), prefix='$')}",
        f"52W_LOW: {fmt_number(data.get('52w_low'), prefix='$')}",
        f"50D_MA: {fmt_number(data.get('50d_ma'), prefix='$')}",
        f"200D_MA: {fmt_number(data.get('200d_ma'), prefix='$')}",
        f"ANALYST_TARGET: {fmt_number(data.get('target_price'), prefix='$')}",
        f"RECOMMENDATION: {data.get('recommendation', 'N/A')}",
        f"NUM_ANALYSTS: {data.get('num_analysts', 'N/A')}",
    ]

    # Add quarterly revenue if available
    qr = data.get("quarterly_revenue")
    if qr:
        lines.append("")
        lines.append("QUARTERLY_REVENUE:")
        for date, rev in sorted(qr.items()):
            lines.append(f"  {date}: {fmt_number(rev, prefix='$')}")

    # Add description snippet
    desc = data.get("description")
    if desc:
        lines.append("")
        lines.append(f"DESCRIPTION: {desc}")

    return "\n".join(lines)
