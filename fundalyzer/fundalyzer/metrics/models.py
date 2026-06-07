# Architecture contract: all values computed from API data in Python — no LLM-generated figures.
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from ..data.models import UNAVAILABLE, Unavailable  # re-export for internal modules

MaybeDecimal = Decimal | Unavailable


class Trend(str, Enum):
    ACCELERATING = "ACCELERATING"
    FLAT = "FLAT"
    DECELERATING = "DECELERATING"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class TrendResult(BaseModel):
    trend: Trend
    # Slope divided by |mean| — i.e., fractional change per period.
    # None when there are fewer than 3 valid data points.
    normalized_slope: Decimal | None = None
    n_periods: int


class MetricPoint(BaseModel):
    """A single KPI observation with full provenance.

    .value   — use this for all downstream computation.
    .formula — human-readable formula for audit and display.
    .inputs  — exact source values used; keys match formula variable names.
    """

    value: MaybeDecimal
    period: str        # "annual" | "Q1" | "Q2" | "Q3" | "Q4"
    period_date: date
    formula: str
    inputs: dict[str, str]  # stored as strings so serialisation is unambiguous


# Oldest-first: series[0] = earliest period, series[-1] = most recent.
MetricSeries = list[MetricPoint]


class ProfitabilityKPIs(BaseModel):
    revenue: MetricSeries
    revenue_growth_yoy: MetricSeries   # (rev_t − rev_t-1) / |rev_t-1|
    gross_margin: MetricSeries         # gross_profit / revenue
    operating_margin: MetricSeries     # operating_income / revenue
    net_margin: MetricSeries           # net_income / revenue
    ebitda_margin: MetricSeries        # ebitda / revenue
    eps_diluted: MetricSeries          # directly from statements
    eps_growth_yoy: MetricSeries       # (eps_t − eps_t-1) / |eps_t-1|
    # Single-point series; only current employee count available without a headcount endpoint
    revenue_per_employee: MetricSeries = Field(default_factory=list)


class ValuationKPIs(BaseModel):
    # All valuation metrics anchor to current price / market_cap.
    # Each series contains a single point (latest-period snapshot).
    trailing_pe: MetricSeries     # price / ttm_eps_diluted
    forward_pe: MetricSeries      # price / forward_eps_avg
    price_to_sales: MetricSeries  # market_cap / ttm_revenue
    ev_to_ebitda: MetricSeries    # (market_cap + total_debt − cash) / ttm_ebitda
    peg: MetricSeries             # trailing_pe / eps_growth_yoy (most recent annual)
    price_to_book: MetricSeries   # market_cap / total_equity (latest balance sheet)
    # Additional multiples
    ev_to_gross_profit: MetricSeries = Field(default_factory=list)  # EV / ttm_gross_profit
    forward_revenue: MetricSeries = Field(default_factory=list)     # analyst revenue consensus
    # Shadow P/E per historical year: current_price / period_eps_diluted (oldest-first)
    # Useful for self-comparison: is today cheaper or richer than own earnings history?
    historical_pe: MetricSeries = Field(default_factory=list)
    # Analyst price target scalars (from PriceTargetConsensus)
    price_target_consensus: MaybeDecimal = UNAVAILABLE
    price_target_high: MaybeDecimal = UNAVAILABLE
    price_target_low: MaybeDecimal = UNAVAILABLE
    price_target_median: MaybeDecimal = UNAVAILABLE
    price_upside: MaybeDecimal = UNAVAILABLE  # (consensus − current_price) / |current_price|


class CashFlowKPIs(BaseModel):
    operating_cash_flow: MetricSeries
    free_cash_flow: MetricSeries
    fcf_margin: MetricSeries   # fcf / revenue
    fcf_yield: MetricSeries    # fcf / market_cap  (single-point, current price)
    buybacks: MetricSeries = Field(default_factory=list)  # share repurchase amounts (negative = outflow)


class FinancialStrengthKPIs(BaseModel):
    debt_to_equity: MetricSeries       # total_debt / total_equity
    net_cash_position: MetricSeries    # cash − total_debt; >0 = net cash
    current_ratio: MetricSeries        # current_assets / current_liabilities
    roe: MetricSeries                  # net_income / avg_total_equity
    roic: MetricSeries                 # nopat / invested_capital


class TickerKPIs(BaseModel):
    ticker: str
    as_of: date
    profitability_annual: ProfitabilityKPIs
    profitability_quarterly: ProfitabilityKPIs
    valuation: ValuationKPIs
    cash_flow_annual: CashFlowKPIs
    cash_flow_quarterly: CashFlowKPIs
    financial_strength_annual: FinancialStrengthKPIs
    financial_strength_quarterly: FinancialStrengthKPIs
