# Architecture contract: the LLM receives only pre-computed figures passed explicitly.
# It must not generate or invent any number that appears in output.
from __future__ import annotations

from typing import Any

from .models import Claim, DashboardNarrative, Interpretation
from ._client import MessagesAPI, call_text, call_with_tool, get_client, DEFAULT_MODEL
from ._prompts import (
    NARRATIVE_TOOL,
    SYSTEM_PROMPT,
    build_capital_prompt,
    build_income_prompt,
    build_momentum_prompt,
    build_synthesis_prompt,
    build_valuation_prompt,
)
from ._serialise import (
    serialise_capital,
    serialise_income,
    serialise_momentum,
    serialise_valuation,
)
from ..dashboards.models import (
    CapitalDashboard,
    IncomeDashboard,
    MomentumDashboard,
    ValuationDashboard,
)

__all__ = [
    "interpret",
    "Interpretation",
    "DashboardNarrative",
    "Claim",
]


def _parse_narrative(raw: dict[str, Any]) -> DashboardNarrative:
    claims = [
        Claim(
            statement=c.get("statement", ""),
            data_points=c.get("data_points", []),
        )
        for c in raw.get("claims", [])
        if isinstance(c, dict)
    ]
    # trend_verdict may be absent if the model skipped it; default to STABLE.
    verdict = raw.get("trend_verdict", "STABLE")
    if verdict not in ("IMPROVING", "DETERIORATING", "STABLE", "MIXED"):
        verdict = "STABLE"
    return DashboardNarrative(
        headline=raw.get("headline", ""),
        body=raw.get("body", ""),
        claims=claims,
        trend_verdict=verdict,
    )


def interpret(
    income: IncomeDashboard,
    momentum: MomentumDashboard,
    valuation: ValuationDashboard,
    capital: CapitalDashboard,
    *,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    messages_api: MessagesAPI | None = None,
) -> Interpretation:
    """Call Claude once per dashboard and once for the synthesis summary.

    Args:
        income, momentum, valuation, capital: assembled dashboard objects.
        api_key:      Anthropic API key (overrides settings).
        model:        Claude model ID.
        messages_api: Inject a pre-built messages API object (for testing).
                      When None, a real Anthropic client is created.

    Returns:
        Interpretation with four DashboardNarrative objects and an overall_summary.
        Every DashboardNarrative.claims entry cites the exact values used.
    """
    if messages_api is None:
        messages_api = get_client(api_key).messages

    def _call(prompt: str) -> DashboardNarrative:
        raw = call_with_tool(
            messages_api,
            system=SYSTEM_PROMPT,
            user_message=prompt,
            tool=NARRATIVE_TOOL,
            model=model,
        )
        return _parse_narrative(raw)

    income_narrative = _call(build_income_prompt(serialise_income(income)))
    momentum_narrative = _call(build_momentum_prompt(serialise_momentum(momentum)))
    valuation_narrative = _call(build_valuation_prompt(serialise_valuation(valuation)))
    capital_narrative = _call(build_capital_prompt(serialise_capital(capital)))

    overall_summary = call_text(
        messages_api,
        system=SYSTEM_PROMPT,
        user_message=build_synthesis_prompt(
            income_verdict=income_narrative.trend_verdict,
            momentum_verdict=momentum_narrative.trend_verdict,
            valuation_verdict=valuation_narrative.trend_verdict,
            capital_verdict=capital_narrative.trend_verdict,
            ticker=income.ticker,
        ),
        model=model,
    )

    return Interpretation(
        income=income_narrative,
        momentum=momentum_narrative,
        valuation=valuation_narrative,
        capital=capital_narrative,
        overall_summary=overall_summary,
    )
