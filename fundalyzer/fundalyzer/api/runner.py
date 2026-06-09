"""Shared group analysis runner — called by both the API routes and the scheduler."""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date

from ..data.cache import DiskCache
from ..data.composite import CompositeProvider
from ..data.fmp import FMPProvider
from ..data.yfinance_provider import YFinanceProvider
from ..group.rank import rank_group
from ..peers._aggregator import build_comparisons
from ..peers._extract import extract_kpi_values
from ..peers.build import build as build_peer_set
from ..peers.models import PeerMetrics, PeerSet
from ..pipeline import run_analysis
from ..settings import settings
from .store import GroupReportData

log = logging.getLogger(__name__)

# (ticker, step, index, total) → None
GroupProgressCallback = Callable[[str, str, int, int], None]


def execute_group_analysis(
    group_name: str,
    tickers: list[str],
    annual_years: int = 5,
    progress_callback: GroupProgressCallback | None = None,
) -> GroupReportData:
    """Run the full pipeline for every member of a group synchronously.

    Designed to be called from a thread pool (anyio.to_thread.run_sync or
    APScheduler background thread) — never call directly from the event loop.

    Args:
        group_name:        Display name for the group (stored in result).
        tickers:           All member tickers.
        annual_years:      Years of history to fetch.
        progress_callback: Called after each pipeline step per member.
                           Signature: (ticker, step, index, total) → None.
    """
    cache = DiskCache()
    yf = YFinanceProvider(cache=cache)
    if settings.fmp_api_key:
        fmp = FMPProvider(api_key=settings.fmp_api_key, cache=cache)
        provider = CompositeProvider(fmp=fmp, yf=yf, cache=cache)
    else:
        provider = yf

    seed, rest = tickers[0], tickers[1:]
    log.info("Building peer set for group %s (seed=%s)", group_name, seed)
    base_peer_set = build_peer_set(seed, provider, peers=rest, annual_years=annual_years)

    all_members = [
        PeerMetrics(ticker=base_peer_set.target, kpis=base_peer_set.target_kpis),
        *base_peer_set.peers,
    ]
    total = len(all_members)
    decisions: dict = {}

    for i, member in enumerate(all_members):
        others = [m for m in all_members if m.ticker != member.ticker]
        sm, comparisons = build_comparisons(member.ticker, member.kpis, others)
        member_peer_set = PeerSet(
            target=member.ticker,
            target_kpis=member.kpis,
            peers=others,
            sector_medians=sm,
            comparisons=comparisons,
        )

        idx = i  # capture for closure

        def make_cb(captured_idx: int) -> Callable[[str, str], None]:
            def cb(ticker: str, step: str) -> None:
                if progress_callback:
                    progress_callback(ticker, step, captured_idx + 1, total)
            return cb

        try:
            log.info("[%d/%d] Analyzing %s", i + 1, total, member.ticker)
            result = run_analysis(
                member.ticker,
                provider,
                annual_years=annual_years,
                peer_set=member_peer_set,
                progress_callback=make_cb(idx),
            )
            decisions[member.ticker] = result.decision
        except Exception as exc:
            log.warning("Skipping %s — analysis failed: %s", member.ticker, exc)

    ranking = rank_group(base_peer_set)

    # Collect raw KPI values for the comparison table in the UI
    kpi_values: dict[str, dict[str, str]] = {}
    for member in all_members:
        raw = extract_kpi_values(member.kpis)
        kpi_values[member.ticker] = {
            k: str(v) for k, v in raw.items()
        }

    return GroupReportData(
        group_name=group_name,
        run_date=date.today().isoformat(),
        ranking=ranking,
        decisions=decisions,
        kpi_values=kpi_values,
    )
