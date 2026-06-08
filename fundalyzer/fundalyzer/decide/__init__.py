# Architecture contract: scores and projections computed in Python; narrative is LLM only.
from __future__ import annotations

from ..data.models import RawFinancials
from ..interpret._client import DEFAULT_MODEL, MessagesAPI, get_client
from ..interpret.models import Interpretation
from ..metrics.models import TickerKPIs
from ..peers.models import PeerSet
from ._client import call_for_assumption_narrative, call_for_justification
from ._lean import derive_lean
from ._projection import build_projection
from ._scoring import score_pillars
from ._soft_signals import build_soft_signals
from ._valuation_position import build_valuation_position
from .models import InvestmentDecision, InvestmentLean, ScoreCard

__all__ = [
    "decide",
    "InvestmentDecision",
    "InvestmentLean",
    "ScoreCard",
]


def decide(
    kpis: TickerKPIs,
    peer_set: PeerSet,
    interpretation: Interpretation,
    raw: RawFinancials,
    *,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    messages_api: MessagesAPI | None = None,
) -> InvestmentDecision:
    """Turn dashboards, narratives, and peer comparisons into an investment lean.

    Steps (all Python-computed before any LLM call):
      1. Score each of the four pillars vs peer percentiles → ScoreCard.
      2. Place current valuation vs own 5-10 year history → ValuationPosition.
      3. Build a base-case and bull-case 3-year projection → Projection.
      4. Read soft signals (insider, revisions, buybacks) → SoftSignals.
      5. Derive INVEST / HOLD / AVOID by rule from the above → InvestmentLean.
      6. Ask the LLM to narrate projection assumptions (numbers fixed, words only).
      7. Ask the LLM to write the lean justification (numbers fixed, words only).

    Args:
        kpis:            computed KPIs for the target ticker.
        peer_set:        peer comparisons and sector medians.
        interpretation:  LLM narratives from the dashboards layer.
        raw:             raw provider data for insider and revision signals.
        api_key:         Anthropic API key (overrides settings.py).
        model:           Claude model ID.
        messages_api:    injectable Anthropic messages object (for testing).

    Returns:
        InvestmentDecision with all scores, signals, projections, and non-removable
        caveats attached as named fields.
    """
    if messages_api is None:
        messages_api = get_client(api_key).messages

    scorecard = score_pillars(peer_set.comparisons)
    valuation_position = build_valuation_position(kpis, peer_set)
    projection = build_projection(kpis)
    soft_signals = build_soft_signals(raw, kpis)
    lean = derive_lean(scorecard, valuation_position, soft_signals)

    # LLM call 1: narrate projection assumptions (numbers are already fixed).
    base_narr, bull_narr = call_for_assumption_narrative(
        messages_api, ticker=kpis.ticker, projection=projection, model=model
    )
    projection.base_case.assumption_narrative = base_narr
    projection.bull_case.assumption_narrative = bull_narr

    # LLM call 2: write the lean justification (numbers are already fixed).
    justification = call_for_justification(
        messages_api,
        ticker=kpis.ticker,
        lean=lean.value,
        scorecard=scorecard,
        valuation_position=valuation_position,
        soft_signals=soft_signals,
        interpretation_summary=interpretation.overall_summary,
        model=model,
    )

    return InvestmentDecision(
        ticker=kpis.ticker,
        lean=lean,
        scorecard=scorecard,
        valuation_position=valuation_position,
        projection=projection,
        soft_signals=soft_signals,
        justification=justification,
    )
