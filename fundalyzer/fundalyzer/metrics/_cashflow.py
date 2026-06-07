# Architecture contract: pure Python arithmetic on API values — no LLM involvement.
from __future__ import annotations

from ..data.models import CashFlowStatement, CompanyProfile, IncomeStatement
from ._helpers import make_point, passthrough, ratio
from .models import UNAVAILABLE, MetricSeries, CashFlowKPIs


def _revenue_by_date(income: list[IncomeStatement]) -> dict:
    return {s.report_date: s.revenue for s in income}


def compute_cashflow(
    cashflow: list[CashFlowStatement],  # oldest-first
    income: list[IncomeStatement],       # oldest-first, for revenue lookup
    profile: CompanyProfile,
) -> CashFlowKPIs:
    rev_map = _revenue_by_date(income)
    market_cap = profile.market_cap

    operating_cf: MetricSeries = []
    free_cf: MetricSeries = []
    fcf_margin: MetricSeries = []
    fcf_yield: MetricSeries = []

    for stmt in cashflow:
        kw = dict(period=stmt.period, period_date=stmt.report_date)
        revenue = rev_map.get(stmt.report_date, UNAVAILABLE)

        operating_cf.append(passthrough(
            stmt.operating_cash_flow,
            formula="operating_cash_flow",
            operating_cash_flow=stmt.operating_cash_flow,
            **kw,
        ))
        free_cf.append(passthrough(
            stmt.free_cash_flow,
            formula="free_cash_flow",
            free_cash_flow=stmt.free_cash_flow,
            **kw,
        ))
        fcf_margin.append(ratio(
            stmt.free_cash_flow, revenue,
            formula="free_cash_flow / revenue",
            free_cash_flow=stmt.free_cash_flow,
            revenue=revenue,
            **kw,
        ))
        # FCF yield: use most-recent market_cap for all periods
        # (historical market_cap not available without a separate price endpoint)
        fcf_yield.append(ratio(
            stmt.free_cash_flow, market_cap,
            formula="free_cash_flow / market_cap",
            free_cash_flow=stmt.free_cash_flow,
            market_cap=market_cap,
            **kw,
        ))

    return CashFlowKPIs(
        operating_cash_flow=operating_cf,
        free_cash_flow=free_cf,
        fcf_margin=fcf_margin,
        fcf_yield=fcf_yield,
    )
