from .models import PeerSet, PeerMetrics, SectorMedian
from ..data.base import FinancialDataProvider

__all__ = ["PeerSet", "PeerMetrics", "SectorMedian", "aggregate"]


def aggregate(tickers: list[str], provider: FinancialDataProvider, years: int = 5) -> PeerSet:
    """Fetch raw financials for each peer, compute their KPIs, and derive sector medians."""
    raise NotImplementedError
