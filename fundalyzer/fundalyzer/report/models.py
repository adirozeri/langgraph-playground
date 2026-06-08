from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from ..dashboards.models import (
    CapitalDashboard,
    IncomeDashboard,
    MomentumDashboard,
    ValuationDashboard,
)
from ..decide.models import InvestmentDecision
from ..interpret.models import Interpretation


class SnapshotReport(BaseModel):
    """All data needed for the fast one-page terminal snapshot."""

    ticker: str
    generated_at: datetime
    income: IncomeDashboard
    momentum: MomentumDashboard
    valuation: ValuationDashboard
    capital: CapitalDashboard
    decision: InvestmentDecision


class DeepDiveReport(BaseModel):
    """Full analysis — every KPI with provenance, narrative, and decision rationale."""

    ticker: str
    generated_at: datetime
    income: IncomeDashboard
    momentum: MomentumDashboard
    valuation: ValuationDashboard
    capital: CapitalDashboard
    interpretation: Interpretation
    decision: InvestmentDecision
