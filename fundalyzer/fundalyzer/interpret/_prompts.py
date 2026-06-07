"""Prompt builders for each dashboard interpretation.

Each builder implements the "smart question pattern":
  - Name the KPI and the time window explicitly
  - Ask whether the metric is improving or deteriorating
  - Ask what the trend implies about the business
  - Require comparison to the peer median
  - Forbid vague verdicts

The system prompt is shared and enforces the no-invention contract.
"""
from __future__ import annotations

import json
from typing import Any

# ── Shared system prompt ──────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a quantitative financial analyst interpreting pre-computed metrics for investment assessment.

STRICT RULES — apply all of them exactly:

1. You are given numbers. Never invent, estimate, recompute, or extrapolate any figure.
2. If a value is "UNAVAILABLE", write "not available for this period" — do not estimate it.
3. Every sentence in your narrative must trace to a specific value in the provided JSON.
4. Do not use vague verdicts: "good stock", "strong company", "looks promising", "solid", \
"healthy", "bullish", or "bearish" are prohibited. State the specific direction and magnitude.
5. Do not describe the company in general terms. Describe only what the specific numbers show.
6. Trend verdicts are defined as:
   IMPROVING   — values moving in a favourable direction over the measured window
   DETERIORATING — values moving in an unfavourable direction
   STABLE      — ≤1 % per-period change across all metrics in the dashboard
   MIXED       — some metrics improving, others deteriorating
7. The claims array must list every specific value your narrative references, \
formatted as "metric=value" (e.g. "gross_margin_2024=46.2%").\
"""

# ── Tool definition (shared across all four calls) ────────────────────────────

NARRATIVE_TOOL: dict[str, Any] = {
    "name": "narrative",
    "description": "Structured financial dashboard narrative.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {
                "type": "string",
                "description": (
                    "One sentence that includes at least one specific value from the data. "
                    "No vague praise. Example: 'Gross margin expanded 2.9pp to 46.2% in FY2024, "
                    "above the 41.5% peer median.'"
                ),
            },
            "body": {
                "type": "string",
                "description": (
                    "2-3 sentences of directional analysis. Every claim must cite a provided value. "
                    "Do not invent figures."
                ),
            },
            "claims": {
                "type": "array",
                "description": "Every factual assertion in the narrative, each with its cited values.",
                "items": {
                    "type": "object",
                    "properties": {
                        "statement": {
                            "type": "string",
                            "description": "A single factual assertion.",
                        },
                        "data_points": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Exact values cited, formatted as 'metric_name=value'. "
                                "Example: [\"gross_margin_2024=46.2%\", \"peer_gross_margin=41.5%\"]"
                            ),
                        },
                    },
                    "required": ["statement", "data_points"],
                },
            },
            "trend_verdict": {
                "type": "string",
                "enum": ["IMPROVING", "DETERIORATING", "STABLE", "MIXED"],
                "description": (
                    "Overall directional verdict for this dashboard. "
                    "Must be one of the four allowed values. Never use GOOD or BAD."
                ),
            },
        },
        "required": ["headline", "body", "claims", "trend_verdict"],
    },
}

# ── Dashboard-specific user prompts ───────────────────────────────────────────

def build_income_prompt(data: dict[str, Any]) -> str:
    ticker = data["ticker"]
    n = max(len(data.get("gross_margin", {}).get("history", [])), 1)
    return f"""\
INCOME DASHBOARD for {ticker}
Time window: {n} annual periods

DATA (pre-computed; do not modify or invent values):
{json.dumps(data, indent=2)}

QUESTIONS — answer each using only the provided values:

1. Profitability stack (gross → operating → net → EBITDA margin):
   - State the most recent value for each margin and its direction over the {n}-year window.
   - Compare each margin to its peer median. Is the company above or below, and by how much?
   - Is each margin improving, deteriorating, or stable?
   - What does the spread between gross and operating margin imply about cost control?

2. Revenue growth:
   - State the most recent growth rate and whether it is accelerating or decelerating.
   - Compare to the peer revenue growth median.

3. Free cash flow:
   - State FCF margin and whether it tracks net margin (high divergence = accrual risk).
   - Is FCF margin above or below the peer median?

TREND VERDICT: consider all margin trends and FCF margin collectively to pick one of \
IMPROVING / DETERIORATING / STABLE / MIXED.\
"""


def build_momentum_prompt(data: dict[str, Any]) -> str:
    ticker = data["ticker"]
    n = max(len(data.get("eps_growth_yoy", {}).get("history", [])), 1)
    return f"""\
MOMENTUM DASHBOARD for {ticker}
Time window: {n} annual periods

DATA (pre-computed; do not modify or invent values):
{json.dumps(data, indent=2)}

QUESTIONS — answer each using only the provided values:

1. EPS momentum:
   - State the specific growth rates from the history. Is the trend accelerating or decelerating?
   - Compare to the peer EPS growth median.
   - What does the trajectory imply about earnings quality?

2. Revenue momentum:
   - Is revenue growth accelerating or decelerating? State the specific rates.
   - Compare to the peer revenue growth median.

3. FCF momentum:
   - Is FCF growing faster or slower than earnings? Divergence (FCF growing faster) implies \
higher quality; convergence or reversal implies potential accrual issues.

4. P/E: history vs forward:
   - Compare trailing P/E to forward P/E. Is the market pricing in earnings growth or contraction?
   - State the specific values for trailing and forward P/E.
   - From the historical_pe_series, is the P/E multiple expanding or compressing over time?
   - If forward_revenue_estimate is available, compare it to the most recent actual revenue.

5. Peer comparison:
   - Is the trailing P/E above or below the peer_trailing_pe?
   - Is the growth rate above or below peers?

TREND VERDICT: assess EPS growth rate, revenue growth rate, and FCF growth collectively.\
"""


def build_valuation_prompt(data: dict[str, Any]) -> str:
    ticker = data["ticker"]
    return f"""\
VALUATION DASHBOARD for {ticker}

DATA (pre-computed; do not modify or invent values):
{json.dumps(data, indent=2)}

QUESTIONS — answer each using only the provided values:

1. P/E:
   - Is trailing P/E above or below (a) the peer_median and (b) the company's own history \
(vs_own_history flag)?
   - Does forward P/E imply the market expects earnings to grow or shrink?

2. P/S and EV/EBITDA:
   - Are these above or below their peer medians?
   - Does vs_own_history indicate the stock is cheaper or richer than usual?
   - Are the three self-history flags (trailing P/E, P/S, EV/EBITDA) consistent or contradictory?

3. EV/Gross Profit:
   - How does EV/GP compare to EV/EBITDA? A significantly higher EV/GP vs EV/EBITDA indicates \
the market ascribes value to the revenue stream before operating costs — characterise whether \
this premium appears justified given the provided margins.

4. Historical P/E series:
   - From the historical_pe_series, describe the direction of the multiple over time. \
Is it expanding (market paying more per dollar of historical earnings) or compressing?

TREND VERDICT: across the multiple set, is the valuation cheaper or richer than \
(a) peers and (b) own history? Use IMPROVING for cheaper, DETERIORATING for richer, \
STABLE if within 5 %, MIXED if peer and own-history signals conflict.\
"""


def build_capital_prompt(data: dict[str, Any]) -> str:
    ticker = data["ticker"]
    n = max(len(data.get("roic", {}).get("history", [])), 1)
    return f"""\
CAPITAL DASHBOARD for {ticker}
Time window: {n} annual periods

DATA (pre-computed; do not modify or invent values):
{json.dumps(data, indent=2)}

QUESTIONS — answer each using only the provided values:

1. Capital deployment quality (ROIC, ROE):
   - State the most recent ROIC and its direction over the {n}-year window.
   - Compare to the peer_roic median. A company earning above the peer median is allocating \
capital more efficiently — characterise this from the data only.
   - Repeat for ROE, noting that very high ROE can result from leverage rather than returns.
   - Is ROIC above or below ROE? If ROIC << ROE, leverage is amplifying returns.

2. Revenue per employee:
   - State the revenue per employee. If only one data point is available, note the limitation.

3. Capital return (buybacks, FCF yield):
   - Are buybacks increasing or decreasing? State the absolute values.
   - Is FCF yield above or below the peer median?

4. Analyst price target:
   - State the consensus target, high, and low.
   - State the implied upside or downside from current price.
   - Do not form an opinion on whether the target is achievable — state only the numbers.

TREND VERDICT: based on ROIC direction and capital return trend collectively.\
"""


def build_synthesis_prompt(
    income_verdict: str,
    momentum_verdict: str,
    valuation_verdict: str,
    capital_verdict: str,
    ticker: str,
) -> str:
    return f"""\
OVERALL SYNTHESIS for {ticker}

The four dashboard verdicts are:
  Income (profitability & FCF): {income_verdict}
  Momentum (growth rates):      {momentum_verdict}
  Valuation (price multiples):  {valuation_verdict}
  Capital (ROIC & allocation):  {capital_verdict}

Write a 2-3 sentence overall_summary that:
1. States each verdict explicitly.
2. Identifies whether the verdicts are consistent or contradictory.
3. Does not introduce any new numbers or use any vague praise/criticism.
4. Does not make a buy/sell recommendation.

Return only the summary text (plain string, no JSON).\
"""
