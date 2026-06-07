# Architecture contract: all values derived from real API data — no LLM-generated figures.
from __future__ import annotations

from datetime import date

from ..data.models import RawFinancials
from ._cashflow import compute_cashflow
from ._profitability import compute_profitability
from ._strength import compute_strength
from ._valuation import compute_valuation
from .models import TickerKPIs


def compute(raw: RawFinancials) -> TickerKPIs:
    """Compute all KPI pillars deterministically from raw financial data.

    Sorting: FMP returns newest-first; we reverse to oldest-first so
    MetricSeries are chronological and the trend classifier can treat
    index 0 as the earliest observation.
    """

    def by_date(seq: list) -> list:
        return sorted(seq, key=lambda s: s.report_date)

    ann_inc = by_date(raw.income_statements_annual)
    ann_bal = by_date(raw.balance_sheets_annual)
    ann_cf = by_date(raw.cash_flow_statements_annual)

    qtr_inc = by_date(raw.income_statements_quarterly)
    qtr_bal = by_date(raw.balance_sheets_quarterly)
    qtr_cf = by_date(raw.cash_flow_statements_quarterly)

    latest_annual_balance = ann_bal[-1] if ann_bal else None

    return TickerKPIs(
        ticker=raw.ticker,
        as_of=date.today(),
        profitability_annual=compute_profitability(ann_inc),
        profitability_quarterly=compute_profitability(qtr_inc),
        valuation=compute_valuation(
            profile=raw.profile,
            quarterly_income=qtr_inc,
            annual_income=ann_inc,
            latest_balance=latest_annual_balance,
            estimates=raw.analyst_estimates,
        ),
        cash_flow_annual=compute_cashflow(ann_cf, ann_inc, raw.profile),
        cash_flow_quarterly=compute_cashflow(qtr_cf, qtr_inc, raw.profile),
        financial_strength_annual=compute_strength(ann_inc, ann_bal),
        financial_strength_quarterly=compute_strength(qtr_inc, qtr_bal),
    )
