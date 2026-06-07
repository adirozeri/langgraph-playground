from .models import DeepDiveReport, SnapshotReport
from ..decide.models import InvestmentDecision
from ..metrics.models import TickerKPIs
from ..peers.models import PeerSet
from ..dashboards.models import (
    IncomeDashboard,
    MomentumDashboard,
    ValuationDashboard,
    CapitalDashboard,
)
from ..interpret.models import Interpretation

__all__ = ["DeepDiveReport", "SnapshotReport", "render_deep_dive", "render_snapshot"]


def render_deep_dive(
    report: DeepDiveReport,
    console=None,
) -> None:
    """Render a full deep-dive report to the terminal using rich."""
    raise NotImplementedError


def render_snapshot(
    report: SnapshotReport,
    console=None,
) -> None:
    """Render a one-page snapshot to the terminal using rich."""
    raise NotImplementedError
