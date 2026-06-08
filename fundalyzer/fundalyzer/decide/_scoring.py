# Architecture contract: all scores computed from peer comparison data — no LLM-generated figures.
from __future__ import annotations

from decimal import Decimal

from ..peers.models import PeerComparisons
from .models import PillarScore, PillarVerdict, ScoreCard

# KPIs that belong to each pillar.  Ordered from highest to lowest priority.
_INCOME_KPIS = ["gross_margin", "operating_margin", "net_margin", "ebitda_margin", "fcf_margin"]
_MOMENTUM_KPIS = ["revenue_growth_yoy", "eps_growth_yoy"]
_VALUATION_KPIS = ["trailing_pe", "forward_pe", "price_to_sales", "ev_to_ebitda", "price_to_book"]
_CAPITAL_KPIS = ["roe", "roic", "debt_to_equity", "current_ratio", "fcf_yield"]

# Mirrors KPI_CATALOG in peers/_extract.py — used to invert percentile for lower-is-better metrics.
_HIGHER_IS_BETTER: dict[str, bool] = {
    "gross_margin": True, "operating_margin": True, "net_margin": True,
    "ebitda_margin": True, "fcf_margin": True,
    "revenue_growth_yoy": True, "eps_growth_yoy": True,
    "trailing_pe": False, "forward_pe": False, "price_to_sales": False,
    "ev_to_ebitda": False, "price_to_book": False,
    "roe": True, "roic": True, "debt_to_equity": False,
    "current_ratio": True, "fcf_yield": True,
}

_HUNDRED = Decimal("100")
_TEN = Decimal("10")


def _verdict(score: Decimal) -> PillarVerdict:
    if score >= Decimal("8"):
        return PillarVerdict.STRONG
    if score >= Decimal("6"):
        return PillarVerdict.ABOVE_PEER
    if score >= Decimal("4"):
        return PillarVerdict.IN_LINE
    if score >= Decimal("2"):
        return PillarVerdict.BELOW_PEER
    return PillarVerdict.WEAK


def _pillar_score(name: str, kpi_names: list[str], comparisons: PeerComparisons) -> PillarScore:
    """Score one pillar from 0-10 based on effective peer percentiles.

    For lower-is-better KPIs (e.g. P/E), we invert the raw percentile so that
    a cheaper-than-peers company scores high.  Skips KPIs without percentile data.
    """
    # If no KPI in this pillar has actual peer values OR a non-None position,
    # the target is being compared only against itself (1-element population).
    # Percentiles are 0 for every higher-is-better metric, which produces
    # artificially 0.00 scores. Return neutral instead.
    has_real_peers = any(
        bool(getattr(comparisons, k).peer_values)
        or getattr(comparisons, k).position is not None
        for k in kpi_names
    )
    if not has_real_peers:
        return PillarScore(
            name=name,
            score=Decimal("5.00"),
            verdict=PillarVerdict.IN_LINE,
            key_metrics_vs_peers={},
        )

    effective_percentiles: list[Decimal] = []
    metrics_vs_peers: dict[str, str] = {}

    for kpi_name in kpi_names:
        comparison = getattr(comparisons, kpi_name)
        if comparison.percentile is not None:
            hib = _HIGHER_IS_BETTER[kpi_name]
            effective = comparison.percentile if hib else (_HUNDRED - comparison.percentile)
            effective_percentiles.append(effective)
        if comparison.position is not None:
            metrics_vs_peers[kpi_name] = comparison.position.value

    if effective_percentiles:
        avg = sum(effective_percentiles) / Decimal(str(len(effective_percentiles)))
        score = (avg / _TEN).quantize(Decimal("0.01"))
    else:
        score = Decimal("5.00")  # neutral when no peer data available

    return PillarScore(
        name=name,
        score=score,
        verdict=_verdict(score),
        key_metrics_vs_peers=metrics_vs_peers,
    )


def score_pillars(comparisons: PeerComparisons) -> ScoreCard:
    """Compute a ScoreCard from peer percentile data.

    Composite weights: income 3, momentum 2, valuation 2, capital 3 —
    business quality and capital efficiency are weighted above growth and price.
    """
    income = _pillar_score("income", _INCOME_KPIS, comparisons)
    momentum = _pillar_score("momentum", _MOMENTUM_KPIS, comparisons)
    valuation = _pillar_score("valuation", _VALUATION_KPIS, comparisons)
    capital = _pillar_score("capital", _CAPITAL_KPIS, comparisons)

    w_income = Decimal("3")
    w_momentum = Decimal("2")
    w_valuation = Decimal("2")
    w_capital = Decimal("3")
    total_w = w_income + w_momentum + w_valuation + w_capital

    composite = (
        income.score * w_income
        + momentum.score * w_momentum
        + valuation.score * w_valuation
        + capital.score * w_capital
    ) / total_w

    return ScoreCard(
        income=income,
        momentum=momentum,
        valuation=valuation,
        capital=capital,
        composite=composite.quantize(Decimal("0.01")),
    )
