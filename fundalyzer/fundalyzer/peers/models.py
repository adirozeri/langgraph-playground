# Architecture contract: peer aggregates computed from API data — no LLM-generated figures.
from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel

from ..data.models import UNAVAILABLE, Unavailable
from ..metrics.models import MaybeDecimal, TickerKPIs


class RelativePosition(str, Enum):
    BETTER = "BETTER"
    WORSE = "WORSE"
    IN_LINE = "IN_LINE"


class KPIComparison(BaseModel):
    """Target ticker vs peer set on a single named KPI.

    peer_median  — median of peers only (target excluded), so the benchmark
                   is not self-referential.
    peer_values  — {ticker: latest_annual_value} for each peer.
    percentile   — target's rank in the combined (peers + target) population,
                   expressed as 0-100.  None if target_value is UNAVAILABLE.
    position     — BETTER / WORSE / IN_LINE.  None when either side is UNAVAILABLE.
    higher_is_better — documents the interpretation direction.
    """

    target_value: MaybeDecimal
    peer_median: MaybeDecimal
    peer_values: dict[str, MaybeDecimal]
    percentile: Decimal | None = None
    position: RelativePosition | None = None
    higher_is_better: bool


class PeerComparisons(BaseModel):
    """Target's relative position on every tracked KPI."""

    # Profitability
    gross_margin: KPIComparison
    operating_margin: KPIComparison
    net_margin: KPIComparison
    ebitda_margin: KPIComparison
    revenue_growth_yoy: KPIComparison
    eps_growth_yoy: KPIComparison
    # Valuation
    trailing_pe: KPIComparison
    forward_pe: KPIComparison
    price_to_sales: KPIComparison
    ev_to_ebitda: KPIComparison
    price_to_book: KPIComparison
    # Cash flow
    fcf_margin: KPIComparison
    fcf_yield: KPIComparison
    # Financial strength
    debt_to_equity: KPIComparison
    current_ratio: KPIComparison
    roe: KPIComparison
    roic: KPIComparison


class SectorMedian(BaseModel):
    """Median of each KPI across the peer-only set (target excluded)."""

    gross_margin: MaybeDecimal = UNAVAILABLE
    operating_margin: MaybeDecimal = UNAVAILABLE
    net_margin: MaybeDecimal = UNAVAILABLE
    ebitda_margin: MaybeDecimal = UNAVAILABLE
    revenue_growth_yoy: MaybeDecimal = UNAVAILABLE
    eps_growth_yoy: MaybeDecimal = UNAVAILABLE
    trailing_pe: MaybeDecimal = UNAVAILABLE
    forward_pe: MaybeDecimal = UNAVAILABLE
    price_to_sales: MaybeDecimal = UNAVAILABLE
    ev_to_ebitda: MaybeDecimal = UNAVAILABLE
    price_to_book: MaybeDecimal = UNAVAILABLE
    fcf_margin: MaybeDecimal = UNAVAILABLE
    fcf_yield: MaybeDecimal = UNAVAILABLE
    debt_to_equity: MaybeDecimal = UNAVAILABLE
    current_ratio: MaybeDecimal = UNAVAILABLE
    roe: MaybeDecimal = UNAVAILABLE
    roic: MaybeDecimal = UNAVAILABLE


class PeerMetrics(BaseModel):
    ticker: str
    kpis: TickerKPIs


class PeerSet(BaseModel):
    target: str
    target_kpis: TickerKPIs
    peers: list[PeerMetrics]
    sector_medians: SectorMedian
    comparisons: PeerComparisons
