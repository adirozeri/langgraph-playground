# Architecture contract: the LLM receives only pre-computed figures passed explicitly.
# It must not generate or invent any number that appears in output.
from .models import Interpretation, DashboardNarrative
from ..dashboards.models import (
    ValuationDashboard,
    GrowthDashboard,
    HealthDashboard,
    CompetitiveDashboard,
)

__all__ = ["Interpretation", "DashboardNarrative", "interpret"]


def interpret(
    valuation: ValuationDashboard,
    growth: GrowthDashboard,
    health: HealthDashboard,
    competitive: CompetitiveDashboard,
) -> Interpretation:
    """Call the LLM with computed dashboard data and return structured narrative.

    The prompt must include all relevant numeric fields explicitly.
    The LLM response is parsed and validated; any invented figures are a bug.
    """
    raise NotImplementedError
