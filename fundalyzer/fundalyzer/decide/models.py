# Architecture contract: scores and projections computed in Python; narrative is LLM only.
from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel

from ..data.models import Unavailable

MaybeDecimal = Decimal | Unavailable

# ── Non-removable caveats — always present on every InvestmentDecision ────────
# These are stored as named fields, not in a list, so they cannot be omitted.

CAVEAT_QUALITY_NOT_TIMING = (
    "Fundamentals assess business quality, not market timing. "
    "A high-quality business can remain overvalued for years; a weak business can rally."
)
CAVEAT_PROJECTION_NOT_GUARANTEED = (
    "The 3-year projection models how the market might value this company "
    "on today's data using analyst estimates and current multiples. "
    "It is not a price target and does not account for macro changes or execution risk."
)
CAVEAT_GARBAGE_IN_GARBAGE_OUT = (
    "This analysis is only as reliable as its inputs. "
    "Stale estimates, unrepresentative peers, or erroneous financials "
    "produce confidently wrong output."
)


# ── Enumerations ──────────────────────────────────────────────────────────────

class InvestmentLean(str, Enum):
    INVEST = "INVEST"
    HOLD = "HOLD"
    AVOID = "AVOID"


class PillarVerdict(str, Enum):
    STRONG = "STRONG"            # top quintile vs peers
    ABOVE_PEER = "ABOVE_PEER"   # 60th–80th percentile
    IN_LINE = "IN_LINE"         # 40th–60th percentile
    BELOW_PEER = "BELOW_PEER"   # 20th–40th percentile
    WEAK = "WEAK"               # bottom quintile


class ValuationHistoryPosition(str, Enum):
    CHEAPER = "CHEAPER"                 # current multiple < own historical median
    IN_LINE = "IN_LINE"                 # within 10 % of own historical median
    RICHER = "RICHER"                   # current multiple > own historical median
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class SoftSignalDirection(str, Enum):
    POSITIVE = "POSITIVE"       # supportive of investment thesis
    NEGATIVE = "NEGATIVE"       # cautionary signal
    NEUTRAL = "NEUTRAL"
    UNAVAILABLE = "UNAVAILABLE"


# ── Pillar scoring ────────────────────────────────────────────────────────────

class PillarScore(BaseModel):
    """Score for one of the four business pillars, benchmarked against the peer set.

    score is 0-10, computed in Python from peer percentiles.
    higher_percentile_is_better is respected per-metric before averaging.
    """
    name: str
    score: Decimal                             # 0-10
    verdict: PillarVerdict
    key_metrics_vs_peers: dict[str, str]       # metric_name → "BETTER"/"WORSE"/"IN_LINE"


class ScoreCard(BaseModel):
    income: PillarScore
    momentum: PillarScore
    valuation: PillarScore
    capital: PillarScore
    composite: Decimal  # weighted average 0-10; used to derive InvestmentLean


# ── Valuation self-history positioning ───────────────────────────────────────

class ValuationPosition(BaseModel):
    """Current valuation versus the company's own 5-10 year history.

    Note field is non-negotiable: always states that position alone ≠ buy/sell.
    """
    position: ValuationHistoryPosition
    current_pe: MaybeDecimal
    historical_median_pe: MaybeDecimal
    deviation_from_median_pct: MaybeDecimal   # (current - median) / |median|
    current_ps: MaybeDecimal
    peer_median_ps: MaybeDecimal
    note: str = (
        "Valuation position relative to own history does not by itself "
        "indicate whether to buy or sell."
    )


# ── 3-year projections ────────────────────────────────────────────────────────

class ProjectionCase(BaseModel):
    """Python-computed 3-year projection. LLM adds only the assumption narrative."""
    label: str                               # "base_case" | "bull_case"
    # Revenue trajectory
    base_revenue: MaybeDecimal               # most recent annual revenue (starting point)
    year_1_revenue: MaybeDecimal
    year_2_revenue: MaybeDecimal
    year_3_revenue: MaybeDecimal
    revenue_cagr: MaybeDecimal
    # EPS trajectory
    base_eps: MaybeDecimal
    year_1_eps: MaybeDecimal
    year_2_eps: MaybeDecimal
    year_3_eps: MaybeDecimal
    eps_cagr: MaybeDecimal
    # Implied price
    applied_pe_multiple: MaybeDecimal        # P/E used to derive implied price
    implied_price_year_3: MaybeDecimal       # year_3_eps × applied_pe_multiple
    # LLM narration of how these numbers were constructed
    assumption_narrative: str = ""           # filled by LLM after numbers are computed


class Projection(BaseModel):
    base_case: ProjectionCase
    bull_case: ProjectionCase
    methodology_note: str = (
        "Revenue and EPS computed from analyst consensus estimates where available, "
        "extrapolated at the same YoY rate for subsequent years. "
        "The bull case applies a 15 % growth uplift and 10 % multiple expansion."
    )


# ── Soft signals ──────────────────────────────────────────────────────────────

class SoftSignals(BaseModel):
    """Non-price signals that can confirm or contradict the quantitative lean."""
    insider_activity: SoftSignalDirection
    insider_detail: str                      # e.g. "3 buys ($12.4M) vs 8 sells ($45.1M)"
    estimate_revisions: SoftSignalDirection  # inferred from EPS surprise streak
    revision_detail: str
    buyback_activity: SoftSignalDirection
    buyback_detail: str
    conflict_flag: bool                      # True when signals contradict each other
    conflict_description: str               # non-empty only when conflict_flag is True


# ── Final decision ────────────────────────────────────────────────────────────

class InvestmentDecision(BaseModel):
    ticker: str
    lean: InvestmentLean
    scorecard: ScoreCard
    valuation_position: ValuationPosition
    projection: Projection
    soft_signals: SoftSignals
    justification: str                   # LLM narrative; no invented numbers

    # ── Non-removable caveats — required fields, not Optional ─────────────────
    caveat_quality_not_timing: str = CAVEAT_QUALITY_NOT_TIMING
    caveat_projection_not_guaranteed: str = CAVEAT_PROJECTION_NOT_GUARANTEED
    caveat_garbage_in_garbage_out: str = CAVEAT_GARBAGE_IN_GARBAGE_OUT
