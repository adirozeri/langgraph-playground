# Architecture contract: scores computed from peer comparison data — no LLM calls.
from __future__ import annotations

from decimal import Decimal

from ..decide._scoring import score_pillars
from ..decide.models import InvestmentLean
from ..peers._aggregator import build_comparisons
from ..peers.models import PeerMetrics, PeerSet
from .models import GroupMemberRank, GroupRanking


def _simple_lean(composite: Decimal) -> InvestmentLean:
    if composite >= Decimal("6"):
        return InvestmentLean.INVEST
    if composite >= Decimal("4"):
        return InvestmentLean.HOLD
    return InvestmentLean.AVOID


def rank_group(peer_set: PeerSet) -> GroupRanking:
    """Score every member of a peer group against the rest and return a ranked leaderboard.

    For each member, the remaining members act as its peer set.
    All data is already computed in peer_set — no API calls are made here.
    Lean is rule-derived from composite score only (no soft signals).
    """
    all_members = [
        PeerMetrics(ticker=peer_set.target, kpis=peer_set.target_kpis),
        *peer_set.peers,
    ]

    ranked: list[GroupMemberRank] = []
    for member in all_members:
        others = [m for m in all_members if m.ticker != member.ticker]
        _, comparisons = build_comparisons(member.ticker, member.kpis, others)
        sc = score_pillars(comparisons)
        ranked.append(GroupMemberRank(
            rank=0,
            ticker=member.ticker,
            composite=sc.composite,
            income=sc.income.score,
            momentum=sc.momentum.score,
            valuation=sc.valuation.score,
            capital=sc.capital.score,
            lean=_simple_lean(sc.composite),
        ))

    ranked.sort(key=lambda r: r.composite, reverse=True)
    for i, r in enumerate(ranked):
        r.rank = i + 1

    return GroupRanking(
        members=ranked,
        group_tickers=[m.ticker for m in all_members],
    )
