# Architecture contract: lean derived by rule from Python-computed scores — no LLM involvement.
from __future__ import annotations

from decimal import Decimal

from .models import (
    InvestmentLean,
    ScoreCard,
    SoftSignalDirection,
    SoftSignals,
    ValuationHistoryPosition,
    ValuationPosition,
)

_INVEST_THRESHOLD = Decimal("6")
_AVOID_THRESHOLD = Decimal("4")


def _signal_counts(soft: SoftSignals) -> tuple[int, int]:
    """(positive_count, negative_count) among actionable (non-neutral, non-unavailable) signals."""
    dirs = [soft.insider_activity, soft.estimate_revisions, soft.buyback_activity]
    _skip = (SoftSignalDirection.UNAVAILABLE, SoftSignalDirection.NEUTRAL)
    actionable = [d for d in dirs if d not in _skip]
    pos = actionable.count(SoftSignalDirection.POSITIVE)
    neg = actionable.count(SoftSignalDirection.NEGATIVE)
    return pos, neg


def derive_lean(
    scorecard: ScoreCard,
    valuation_position: ValuationPosition,
    soft_signals: SoftSignals,
) -> InvestmentLean:
    """Rule-based investment lean.

    INVEST — composite >= 6, valuation not stretched against the backdrop of
             predominantly negative soft signals.
    AVOID  — composite < 4, OR composite 4-6 with RICHER valuation AND
             majority negative signals.
    HOLD   — everything else.

    Note: valuation position alone does not change the lean — it modulates
    whether soft signals are sufficient to push over the INVEST/AVOID thresholds.
    """
    comp = scorecard.composite
    pos_signals, neg_signals = _signal_counts(soft_signals)
    majority_negative = neg_signals > pos_signals and neg_signals >= 2
    val_pos = valuation_position.position

    # INVEST: good business, not stretched + signals don't warn clearly against it.
    if comp >= _INVEST_THRESHOLD and not majority_negative:
        return InvestmentLean.INVEST
    # Edge: strong business but richer than own history AND most signals negative.
    richer = val_pos == ValuationHistoryPosition.RICHER
    if comp >= _INVEST_THRESHOLD and majority_negative and richer:
        return InvestmentLean.HOLD

    # AVOID: weak business on fundamentals.
    if comp < _AVOID_THRESHOLD:
        return InvestmentLean.AVOID
    # AVOID: mediocre business, expensive, and signals warn against.
    if _AVOID_THRESHOLD <= comp < _INVEST_THRESHOLD and richer and majority_negative:
        return InvestmentLean.AVOID

    return InvestmentLean.HOLD
