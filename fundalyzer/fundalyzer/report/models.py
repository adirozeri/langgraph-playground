from datetime import datetime
from pydantic import BaseModel
from ..dashboards.models import (
    ValuationDashboard,
    GrowthDashboard,
    HealthDashboard,
    CompetitiveDashboard,
)
from ..interpret.models import Interpretation
from ..decide.models import InvestmentDecision


class DeepDiveReport(BaseModel):
    ticker: str
    generated_at: datetime
    valuation: ValuationDashboard
    growth: GrowthDashboard
    health: HealthDashboard
    competitive: CompetitiveDashboard
    interpretation: Interpretation
    decision: InvestmentDecision


class SnapshotReport(BaseModel):
    ticker: str
    generated_at: datetime
    decision: InvestmentDecision
    one_liner: str  # LLM narrative that references decision.scorecard — no invented numbers
