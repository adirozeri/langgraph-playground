# Architecture contract: all scores computed from peer comparison data — no LLM-generated figures.
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from ..decide.models import InvestmentLean


class GroupMemberRank(BaseModel):
    rank: int
    ticker: str
    composite: Decimal
    income: Decimal
    momentum: Decimal
    valuation: Decimal
    capital: Decimal
    lean: InvestmentLean


class GroupRanking(BaseModel):
    """All members of a peer group, ranked best-to-worst by composite score."""
    members: list[GroupMemberRank]  # sorted by composite desc, rank=1 is best
    group_tickers: list[str]        # original group in input order
