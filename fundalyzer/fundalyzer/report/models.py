from datetime import datetime
from pydantic import BaseModel
from ..dashboards.models import (
    IncomeDashboard,
    MomentumDashboard,
    ValuationDashboard,
    CapitalDashboard,
)
from ..interpret.models import Interpretation
from ..decide.models import InvestmentDecision


class DeepDiveReport(BaseModel):
    ticker: str
    generated_at: datetime
    income: IncomeDashboard
    momentum: MomentumDashboard
    valuation: ValuationDashboard
    capital: CapitalDashboard
    interpretation: Interpretation
    decision: InvestmentDecision


class SnapshotReport(BaseModel):
    ticker: str
    generated_at: datetime
    decision: InvestmentDecision
    one_liner: str  # LLM narrative that references decision.scorecard — no invented numbers
