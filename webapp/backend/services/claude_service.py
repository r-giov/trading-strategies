"""
Claude API integration for in-app stock research analyst.
Family Office architecture: pre-fetches real market data, then calls Claude
with verified numbers injected into the prompt so the AI cannot hallucinate.

Modes:
  - "research": Full S&J Asymmetric Framework report with pre-fetched data
  - "chat":     Quick Q&A with market data context
  - "reevaluate": Update an existing report with fresh data
"""

import sys
import os
import logging
from pathlib import Path
from string import Template

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import deps  # noqa: E402, F401

from dotenv import load_dotenv

from services.market_data import fetch_market_data, format_market_data_block

logger = logging.getLogger("qs-finance.claude")

load_dotenv(deps.REPO_ROOT / "live" / ".env")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ── Prompt template paths ────────────────────────────────────────
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
RESEARCH_TEMPLATE_PATH = PROMPTS_DIR / "research_report.md"

# ── Base system prompt (shared across all modes) ─────────────────
BASE_SYSTEM_PROMPT = """You are the AI Research Analyst for QS Finance. You have web search access — USE IT for qualitative analysis (news, catalysts, sector trends).

## CRITICAL RULES
1. For any ticker analysis, VERIFIED MARKET DATA is injected below — use those numbers as ground truth
2. NEVER override the pre-fetched financial metrics with different numbers
3. Use web search ONLY for qualitative info: news, catalysts, competitor analysis, sector trends
4. If a metric is missing from the verified data, say "NOT AVAILABLE" — do not guess
5. Every claim must be traceable to a source

## S&J Asymmetric Framework
You evaluate stocks using the Three-Legged Stool:
- **LEG 1 — FLOOR**: Low P/S vs peers = compressed valuation = limited downside
- **LEG 2 — CATALYST**: Rapid revenue ramp, EBITDA turn, or product inflection
- **LEG 3 — SECTOR HEAT**: Market cares about this sector NOW (not cold/dead money)

## Anti-Slop Rules
- NO vague language like "historically trades at X" — give the EXACT current number
- NO hedging with "might" or "could" — state the math, let the user decide
- Tables must have REAL numbers, not ranges
- If a stock is boring/obvious (AAPL, MSFT), say so in one line — don't write a lengthy analysis on mega-caps
- Be CONCISE. Data tables > paragraphs

## Output Format
End every analysis with:
```
VERDICT: [ASYMMETRIC / NEUTRAL / NEGATIVE ASYMMETRY]
Floor: X/5 | Catalyst: X/5 | Sector: X/5 | Total: X/15
Key Risk: [one line]
Source: [list of URLs searched]
```"""

# ── Chat mode system prompt ──────────────────────────────────────
CHAT_SYSTEM_PROMPT = BASE_SYSTEM_PROMPT + """

## CHAT MODE
You are in quick Q&A mode. Answer the user's question concisely.
If market data is provided below, reference it. Keep responses focused and direct.
Do not generate a full report unless specifically asked."""

# ── Reevaluate mode system prompt ────────────────────────────────
REEVALUATE_SYSTEM_PROMPT = BASE_SYSTEM_PROMPT + """

## REEVALUATE MODE
You are updating an existing research report with fresh market data.
Compare the new data to what was in the previous report.
Highlight what changed: price movement, valuation shifts, new catalysts, changed risks.
Update the verdict if warranted. Be specific about what changed and why."""


def _load_research_template() -> str:
    """Load the research report prompt template."""
    if RESEARCH_TEMPLATE_PATH.exists():
        return RESEARCH_TEMPLATE_PATH.read_text(encoding="utf-8")
    logger.warning(f"Research template not found at {RESEARCH_TEMPLATE_PATH}, using fallback")
    return (
        "Generate a full equity research report for ${ticker} (${company_name}).\n\n"
        "## VERIFIED MARKET DATA\n${market_data_block}\n\n"
        "Include: Company Overview, Revenue & Growth, Valuation Floor, "
        "Catalyst Assessment, Sector Heat, Risk Assessment, Insider Activity, "
        "Technical Setup, and a final VERDICT with scores /15."
    )


def _build_research_prompt(ticker: str, market_data: dict) -> str:
    """Build the full research prompt with market data injected."""
    template_str = _load_research_template()
    market_block = format_market_data_block(market_data)
    company_name = market_data.get("company_name", ticker)

    # Use string.Template with $ substitution
    tmpl = Template(template_str)
    return tmpl.safe_substitute(
        ticker=ticker,
        company_name=company_name,
        market_data_block=market_block,
    )


def _build_chat_prompt(ticker: str, query: str, market_data: dict | None) -> str:
    """Build a chat prompt with optional market data context."""
    parts = []
    if ticker and market_data:
        market_block = format_market_data_block(market_data)
        parts.append(f"## VERIFIED MARKET DATA for {ticker}\n{market_block}\n")
    parts.append(query)
    return "\n".join(parts)


def _build_reevaluate_prompt(ticker: str, query: str, market_data: dict) -> str:
    """Build a reevaluation prompt with fresh data."""
    market_block = format_market_data_block(market_data)
    company_name = market_data.get("company_name", ticker)
    return (
        f"## REEVALUATION REQUEST for {ticker} ({company_name})\n\n"
        f"## FRESH MARKET DATA (just fetched)\n{market_block}\n\n"
        f"## USER REQUEST\n{query}\n\n"
        "Compare this fresh data against the previous report (in conversation context). "
        "What changed? Update the verdict if needed."
    )


def analyze_stock(
    ticker: str,
    query: str,
    context: list[dict] | None = None,
    mode: str = "chat",
) -> dict:
    """
    Send a research query to Claude with pre-fetched market data and web search.

    Args:
        ticker: Stock ticker symbol (e.g. "CRDO", "AAPL")
        query: User's question or research request
        context: Previous conversation messages
        mode: "research" (full report), "chat" (quick Q&A), "reevaluate" (update existing)

    Returns:
        dict with response, citations, market_data, model, usage — or error
    """
    import anthropic

    if not ANTHROPIC_API_KEY:
        return {"error": "ANTHROPIC_API_KEY not configured in live/.env"}

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # ── Pre-fetch market data ────────────────────────────────────
    market_data = None
    if ticker:
        try:
            logger.info(f"Fetching market data for {ticker}...")
            market_data = fetch_market_data(ticker)
            logger.info(f"Market data fetched: {len(market_data)} fields for {ticker}")
        except Exception as e:
            logger.warning(f"Market data fetch failed for {ticker}: {e}")
            market_data = {"ticker": ticker, "error": str(e)}

    # ── Build messages ───────────────────────────────────────────
    messages = []
    if context:
        for msg in context:
            if msg.get("role") in ("user", "assistant") and msg.get("content"):
                messages.append({"role": msg["role"], "content": msg["content"]})

    # ── Select system prompt and build user message by mode ──────
    if mode == "research":
        system_prompt = BASE_SYSTEM_PROMPT
        if ticker and market_data:
            user_msg = _build_research_prompt(ticker, market_data)
            if query and query.strip():
                user_msg += f"\n\n## ADDITIONAL CONTEXT FROM USER\n{query}"
        else:
            user_msg = query
        max_tokens = 16000
        web_search_uses = 5

    elif mode == "reevaluate":
        system_prompt = REEVALUATE_SYSTEM_PROMPT
        if ticker and market_data:
            user_msg = _build_reevaluate_prompt(ticker, query, market_data)
        else:
            user_msg = query
        max_tokens = 12000
        web_search_uses = 3

    else:  # mode == "chat"
        system_prompt = CHAT_SYSTEM_PROMPT
        user_msg = _build_chat_prompt(ticker, query, market_data)
        max_tokens = 8000
        web_search_uses = 3

    messages.append({"role": "user", "content": user_msg})

    # ── Call Claude ───────────────────────────────────────────────
    try:
        # Try with web search first, fall back to without if rate limited
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                system=system_prompt,
                tools=[{
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": web_search_uses,
                }],
                messages=messages,
            )
        except Exception as ws_err:
            if "429" in str(ws_err) or "rate" in str(ws_err).lower():
                logger.warning(f"Web search rate limited, falling back: {ws_err}")
                fallback_note = (
                    "\n\nNOTE: Web search is temporarily unavailable due to rate limits. "
                    "Use the pre-fetched VERIFIED MARKET DATA for all numbers. "
                    "Mark any qualitative claims as UNVERIFIED if you cannot search."
                )
                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=max_tokens,
                    system=system_prompt + fallback_note,
                    messages=messages,
                )
            else:
                raise

        # ── Extract text and citations from response ─────────────
        text_parts = []
        citations = []
        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
            if hasattr(block, "citations"):
                for cite in (block.citations or []):
                    if hasattr(cite, "url"):
                        citations.append(cite.url)

        result = {
            "response": "\n".join(text_parts),
            "citations": list(set(citations)),
            "model": response.model,
            "mode": mode,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        }

        # Include the pre-fetched market data in response so frontend can use it
        if market_data:
            result["market_data"] = market_data

        return result

    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return {"error": str(e)}
