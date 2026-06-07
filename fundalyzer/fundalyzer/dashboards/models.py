# Architecture contract: all fields are Python-computed from API data — no LLM-generated figures.
from decimal import Decimal
from pydantic import BaseModel
from ..metrics.models import (
    MetricSeries,
    ProfitabilityKPIs,
    ValuationKPIs,
    CashFlowKPIs,
    FinancialStrengthKPIs,
)
from ..peers.models import SectorMedian


class ValuationDashboard(BaseModel):
    ticker: str
    valuation: ValuationKPIs
    vs_sector_median: SectorMedian


class GrowthDashboard(BaseModel):
    ticker: str
    profitability: ProfitabilityKPIs


class HealthDashboard(BaseModel):
    ticker: str
    financial_strength: FinancialStrengthKPIs
    cash_flow: CashFlowKPIs


class CompetitiveDashboard(BaseModel):
    ticker: str
    gross_margin_vs_peers: dict[str, MetricSeries]
    net_margin_vs_peers: dict[str, MetricSeries]
    revenue_growth_vs_peers: dict[str, MetricSeries]
    roe_vs_peers: dict[str, MetricSeries]
