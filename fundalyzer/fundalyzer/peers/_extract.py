"""KPI catalog and value extraction from TickerKPIs.

KPI_CATALOG is the single source of truth for which metrics enter the
peer comparison.  Adding a KPI here automatically propagates it to
SectorMedian and PeerComparisons — but you must also add the matching
field to those models in models.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..data.models import UNAVAILABLE
from ..metrics.models import MaybeDecimal, MetricSeries, TickerKPIs


def _latest(series: MetricSeries) -> MaybeDecimal:
    """Most recent non-UNAVAILABLE value in an oldest-first MetricSeries."""
    for pt in reversed(series):
        if pt.value != UNAVAILABLE:
            return pt.value
    return UNAVAILABLE


@dataclass(frozen=True)
class KPISpec:
    name: str
    getter: Callable[[TickerKPIs], MetricSeries]
    higher_is_better: bool


KPI_CATALOG: list[KPISpec] = [
    # ── Profitability ──────────────────────────────────────────────────────
    KPISpec("gross_margin",       lambda k: k.profitability_annual.gross_margin,       True),
    KPISpec("operating_margin",   lambda k: k.profitability_annual.operating_margin,   True),
    KPISpec("net_margin",         lambda k: k.profitability_annual.net_margin,         True),
    KPISpec("ebitda_margin",      lambda k: k.profitability_annual.ebitda_margin,      True),
    KPISpec("revenue_growth_yoy", lambda k: k.profitability_annual.revenue_growth_yoy, True),
    KPISpec("eps_growth_yoy",     lambda k: k.profitability_annual.eps_growth_yoy,     True),
    # ── Valuation (lower multiple = better relative value) ─────────────────
    KPISpec("trailing_pe",        lambda k: k.valuation.trailing_pe,        False),
    KPISpec("forward_pe",         lambda k: k.valuation.forward_pe,         False),
    KPISpec("price_to_sales",     lambda k: k.valuation.price_to_sales,     False),
    KPISpec("ev_to_ebitda",       lambda k: k.valuation.ev_to_ebitda,       False),
    KPISpec("price_to_book",      lambda k: k.valuation.price_to_book,      False),
    # ── Cash flow ──────────────────────────────────────────────────────────
    KPISpec("fcf_margin",         lambda k: k.cash_flow_annual.fcf_margin,  True),
    KPISpec("fcf_yield",          lambda k: k.cash_flow_annual.fcf_yield,   True),
    # ── Financial strength ─────────────────────────────────────────────────
    KPISpec("debt_to_equity",     lambda k: k.financial_strength_annual.debt_to_equity, False),
    KPISpec("current_ratio",      lambda k: k.financial_strength_annual.current_ratio,  True),
    KPISpec("roe",                lambda k: k.financial_strength_annual.roe,            True),
    KPISpec("roic",               lambda k: k.financial_strength_annual.roic,          True),
]

# Fast lookup by name
KPI_BY_NAME: dict[str, KPISpec] = {s.name: s for s in KPI_CATALOG}


def extract_kpi_values(kpis: TickerKPIs) -> dict[str, MaybeDecimal]:
    """Flat dict of {kpi_name: latest_annual_value} for all catalog entries."""
    return {spec.name: _latest(spec.getter(kpis)) for spec in KPI_CATALOG}
