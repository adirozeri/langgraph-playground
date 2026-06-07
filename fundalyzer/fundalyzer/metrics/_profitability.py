# Architecture contract: pure Python arithmetic on API values — no LLM involvement.
from __future__ import annotations

from decimal import Decimal

from ..data.models import IncomeStatement
from ._helpers import passthrough, ratio, yoy
from .models import MetricPoint, MetricSeries, ProfitabilityKPIs


def _period(stmt: IncomeStatement) -> str:
    return stmt.period


def _kw(stmt: IncomeStatement) -> dict:
    return dict(period=_period(stmt), period_date=stmt.report_date)


def compute_profitability(
    statements: list[IncomeStatement],  # oldest-first
    employees: int | None = None,
) -> ProfitabilityKPIs:
    """Compute all profitability KPIs for an ordered list of statements.

    ``statements`` must be sorted oldest-first; the caller (compute.py)
    is responsible for that ordering.
    """
    revenue: MetricSeries = []
    revenue_growth_yoy: MetricSeries = []
    gross_margin: MetricSeries = []
    operating_margin: MetricSeries = []
    net_margin: MetricSeries = []
    ebitda_margin: MetricSeries = []
    eps_diluted: MetricSeries = []
    eps_growth_yoy: MetricSeries = []

    for i, stmt in enumerate(statements):
        kw = _kw(stmt)

        # --- Revenue (raw passthrough, still needs provenance) ---
        revenue.append(passthrough(
            stmt.revenue,
            formula="revenue",
            revenue=stmt.revenue,
            **kw,
        ))

        # --- Margins ---
        gross_margin.append(ratio(
            stmt.gross_profit, stmt.revenue,
            formula="gross_profit / revenue",
            gross_profit=stmt.gross_profit,
            revenue=stmt.revenue,
            **kw,
        ))
        operating_margin.append(ratio(
            stmt.operating_income, stmt.revenue,
            formula="operating_income / revenue",
            operating_income=stmt.operating_income,
            revenue=stmt.revenue,
            **kw,
        ))
        net_margin.append(ratio(
            stmt.net_income, stmt.revenue,
            formula="net_income / revenue",
            net_income=stmt.net_income,
            revenue=stmt.revenue,
            **kw,
        ))
        ebitda_margin.append(ratio(
            stmt.ebitda, stmt.revenue,
            formula="ebitda / revenue",
            ebitda=stmt.ebitda,
            revenue=stmt.revenue,
            **kw,
        ))

        # --- EPS (passthrough) ---
        eps_diluted.append(passthrough(
            stmt.eps_diluted,
            formula="eps_diluted",
            eps_diluted=stmt.eps_diluted,
            **kw,
        ))

        # --- YoY growth rates — only computable from i ≥ 1 ---
        if i == 0:
            # Sentinel: no prior period available
            from .models import UNAVAILABLE
            from ._helpers import make_point
            revenue_growth_yoy.append(make_point(
                UNAVAILABLE,
                formula="(revenue - prior_revenue) / |prior_revenue|",
                period=_period(stmt),
                period_date=stmt.report_date,
                revenue=stmt.revenue,
                prior_revenue="no_prior_period",
            ))
            eps_growth_yoy.append(make_point(
                UNAVAILABLE,
                formula="(eps_diluted - prior_eps_diluted) / |prior_eps_diluted|",
                period=_period(stmt),
                period_date=stmt.report_date,
                eps_diluted=stmt.eps_diluted,
                prior_eps_diluted="no_prior_period",
            ))
        else:
            prior = statements[i - 1]
            revenue_growth_yoy.append(yoy(
                stmt.revenue, prior.revenue,
                formula="(revenue - prior_revenue) / |prior_revenue|",
                revenue=stmt.revenue,
                prior_revenue=prior.revenue,
                **kw,
            ))
            eps_growth_yoy.append(yoy(
                stmt.eps_diluted, prior.eps_diluted,
                formula="(eps_diluted - prior_eps_diluted) / |prior_eps_diluted|",
                eps_diluted=stmt.eps_diluted,
                prior_eps_diluted=prior.eps_diluted,
                **kw,
            ))

    # Revenue per employee — single point using current employee count.
    # Only the latest annual revenue is used; historical headcount is unavailable
    # without a dedicated workforce-history endpoint.
    rev_per_emp: MetricSeries = []
    if statements and employees:
        latest = statements[-1]
        from .models import UNAVAILABLE as _U
        from ._helpers import ratio as _ratio
        rev_per_emp = [_ratio(
            latest.revenue,
            Decimal(str(employees)),
            formula="revenue / employees",
            period=_period(latest),
            period_date=latest.report_date,
            revenue=latest.revenue,
            employees=employees,
        )]

    return ProfitabilityKPIs(
        revenue=revenue,
        revenue_growth_yoy=revenue_growth_yoy,
        gross_margin=gross_margin,
        operating_margin=operating_margin,
        net_margin=net_margin,
        ebitda_margin=ebitda_margin,
        eps_diluted=eps_diluted,
        eps_growth_yoy=eps_growth_yoy,
        revenue_per_employee=rev_per_emp,
    )
