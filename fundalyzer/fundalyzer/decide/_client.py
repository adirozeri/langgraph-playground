"""LLM client for the decide module.

Two calls only:
  1. call_for_justification   — overall 2-4 sentence lean rationale.
  2. call_for_assumption_narrative — narrate the projection assumptions.

Both use forced tool_use so output is always schema-compliant.
Numbers in the prompts are pre-formatted strings — the LLM must cite them,
never invent or recalculate them.
"""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation

from ..interpret._client import (
    DEFAULT_MODEL,
    MessagesAPI,
    call_with_tool,
)
from .models import Projection, ScoreCard, SoftSignals, ValuationPosition

DECIDE_SYSTEM_PROMPT = (
    "You are a financial analysis assistant providing investment rationale. "
    "Rules you must follow without exception:\n"
    "1. NEVER invent, estimate, or compute any number. Every figure you cite must "
    "appear in the data you are given.\n"
    "2. If a value is marked UNAVAILABLE, say so explicitly — do not substitute or estimate.\n"
    "3. Do not use phrases like 'strong buy', 'strong sell', 'bullish', 'bearish'.\n"
    "4. Every claim must reference a specific metric from the provided data.\n"
    "5. Your role is to narrate what the numbers say, not to generate numbers."
)

_JUSTIFICATION_TOOL: dict = {
    "name": "justification",
    "description": "Investment lean justification that cites only provided scorecard values.",
    "input_schema": {
        "type": "object",
        "properties": {
            "justification": {
                "type": "string",
                "description": (
                    "2-4 sentences. Each sentence must reference at least one provided value. "
                    "Explain the lean in terms of the composite score, valuation position, "
                    "and soft signal direction."
                ),
            }
        },
        "required": ["justification"],
    },
}

_ASSUMPTION_TOOL: dict = {
    "name": "assumption_narrative",
    "description": "Narrative for projection assumptions — cites only provided projection values.",
    "input_schema": {
        "type": "object",
        "properties": {
            "base_narrative": {
                "type": "string",
                "description": (
                    "1-2 sentences narrating what growth rate was assumed and "
                    "what data source underpins it (analyst estimate or historical extrapolation)."
                ),
            },
            "bull_narrative": {
                "type": "string",
                "description": (
                    "1-2 sentences narrating what uplift was applied to growth and multiple, "
                    "and what implied price that produces."
                ),
            },
        },
        "required": ["base_narrative", "bull_narrative"],
    },
}


def _fmt(v) -> str:
    if v == "UNAVAILABLE":
        return "UNAVAILABLE"
    try:
        d = Decimal(str(v))
        if abs(d) >= Decimal("1_000_000_000"):
            return f"${d / Decimal('1_000_000_000'):.1f}B"
        if abs(d) >= Decimal("1_000_000"):
            return f"${d / Decimal('1_000_000'):.1f}M"
        if abs(d) < 1 and d != 0:
            return f"{d * 100:.1f}%"
        return str(round(d, 2))
    except (InvalidOperation, TypeError):
        return str(v)


def call_for_justification(
    messages_api: MessagesAPI,
    *,
    ticker: str,
    lean: str,
    scorecard: ScoreCard,
    valuation_position: ValuationPosition,
    soft_signals: SoftSignals,
    interpretation_summary: str,
    model: str = DEFAULT_MODEL,
) -> str:
    data = {
        "ticker": ticker,
        "lean": lean,
        "scorecard": {
            "income": {
                "score": str(scorecard.income.score),
                "verdict": scorecard.income.verdict.value,
            },
            "momentum": {
                "score": str(scorecard.momentum.score),
                "verdict": scorecard.momentum.verdict.value,
            },
            "valuation": {
                "score": str(scorecard.valuation.score),
                "verdict": scorecard.valuation.verdict.value,
            },
            "capital": {
                "score": str(scorecard.capital.score),
                "verdict": scorecard.capital.verdict.value,
            },
            "composite": str(scorecard.composite),
        },
        "valuation_vs_own_history": valuation_position.position.value,
        "current_pe": _fmt(valuation_position.current_pe),
        "historical_median_pe": _fmt(valuation_position.historical_median_pe),
        "soft_signals": {
            "insider": soft_signals.insider_activity.value,
            "insider_detail": soft_signals.insider_detail,
            "revisions": soft_signals.estimate_revisions.value,
            "revision_detail": soft_signals.revision_detail,
            "buybacks": soft_signals.buyback_activity.value,
            "conflict": soft_signals.conflict_flag,
            "conflict_description": soft_signals.conflict_description,
        },
        "interpretation_summary": interpretation_summary,
    }

    user_message = (
        f"Provide a 2-4 sentence investment justification for {ticker}.\n\n"
        f"Lean: {lean}\n\n"
        f"Data:\n{json.dumps(data, indent=2)}\n\n"
        "Cite specific scores and signals from the data above. Do not invent numbers."
    )

    result = call_with_tool(
        messages_api,
        system=DECIDE_SYSTEM_PROMPT,
        user_message=user_message,
        tool=_JUSTIFICATION_TOOL,
        model=model,
    )
    return result.get("justification", "")


def call_for_assumption_narrative(
    messages_api: MessagesAPI,
    *,
    ticker: str,
    projection: Projection,
    model: str = DEFAULT_MODEL,
) -> tuple[str, str]:
    bc = projection.base_case
    bull = projection.bull_case
    data = {
        "ticker": ticker,
        "methodology": projection.methodology_note,
        "base_case": {
            "revenue_cagr": _fmt(bc.revenue_cagr),
            "eps_cagr": _fmt(bc.eps_cagr),
            "applied_pe": _fmt(bc.applied_pe_multiple),
            "year_3_implied_price": _fmt(bc.implied_price_year_3),
        },
        "bull_case": {
            "revenue_cagr": _fmt(bull.revenue_cagr),
            "eps_cagr": _fmt(bull.eps_cagr),
            "applied_pe": _fmt(bull.applied_pe_multiple),
            "year_3_implied_price": _fmt(bull.implied_price_year_3),
        },
    }

    user_message = (
        f"Narrate the projection assumptions for {ticker}.\n\n"
        f"Data:\n{json.dumps(data, indent=2)}\n\n"
        "Base narrative: 1-2 sentences on growth rate assumed and its source.\n"
        "Bull narrative: 1-2 sentences on the uplift applied and the implied price.\n"
        "Do not invent figures — cite only values from the data above."
    )

    result = call_with_tool(
        messages_api,
        system=DECIDE_SYSTEM_PROMPT,
        user_message=user_message,
        tool=_ASSUMPTION_TOOL,
        model=model,
    )
    return result.get("base_narrative", ""), result.get("bull_narrative", "")
