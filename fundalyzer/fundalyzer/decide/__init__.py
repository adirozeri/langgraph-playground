# Architecture contract: scores computed in Python; lean derived from scores; rationale is LLM narrative only.
from .models import InvestmentDecision, InvestmentLean, ScoreCard
from ..metrics.models import TickerKPIs
from ..peers.models import PeerSet
from ..interpret.models import Interpretation

__all__ = ["InvestmentDecision", "InvestmentLean", "ScoreCard", "decide"]


def decide(
    kpis: TickerKPIs,
    peer_set: PeerSet,
    interpretation: Interpretation,
) -> InvestmentDecision:
    """Compute a scorecard from API-derived metrics, then ask the LLM for rationale only."""
    raise NotImplementedError
