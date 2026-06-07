from .models import (
    ValuationDashboard,
    GrowthDashboard,
    HealthDashboard,
    CompetitiveDashboard,
)
from ..metrics.models import TickerKPIs
from ..peers.models import PeerSet

__all__ = [
    "ValuationDashboard",
    "GrowthDashboard",
    "HealthDashboard",
    "CompetitiveDashboard",
    "build",
]


def build(
    kpis: TickerKPIs,
    peer_set: PeerSet,
) -> tuple[ValuationDashboard, GrowthDashboard, HealthDashboard, CompetitiveDashboard]:
    """Assemble all four typed dashboard objects from computed metrics."""
    raise NotImplementedError
