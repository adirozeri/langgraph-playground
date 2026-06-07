# Architecture contract: build() only fetches real data and computes in Python.
from __future__ import annotations

import logging
from decimal import Decimal

from ..data.base import FinancialDataProvider
from ..data.cache import DiskCache
from ..metrics.compute import compute
from ._aggregator import build_comparisons
from ._selector import MAX_PEERS, derive_peers
from ._stats import DEFAULT_IN_LINE_BAND
from .models import PeerMetrics, PeerSet

log = logging.getLogger(__name__)


def build(
    target: str,
    provider: FinancialDataProvider,
    peers: list[str] | None = None,
    quarters: int = 12,
    annual_years: int = 10,
    max_peers: int = MAX_PEERS,
    in_line_band: Decimal = DEFAULT_IN_LINE_BAND,
) -> PeerSet:
    """Fetch, compute, and compare metrics for a target ticker and its peers.

    Args:
        target:       Subject ticker (e.g. "AAPL").
        provider:     Financial data provider (FMP, Composite, etc.).
        peers:        Explicit peer list.  When None, derived from the provider's
                      sector/industry classification (capped at *max_peers*).
        quarters:     Quarters of history to fetch per ticker.
        annual_years: Annual years of history to fetch per ticker.
        max_peers:    Hard cap on peer set size (prevents runaway API calls).
        in_line_band: Fractional deviation from median that classifies as IN_LINE.

    Returns:
        PeerSet with sector medians and per-KPI comparisons for the target.
        Peers that fail to fetch are logged and skipped; the PeerSet is still
        returned with however many peers succeeded.
    """
    target = target.upper()

    # ── Derive peer list ──────────────────────────────────────────────────────
    if peers is None:
        peer_tickers = derive_peers(target, provider, max_peers)
    else:
        peer_tickers = [t.upper() for t in peers if t.upper() != target][:max_peers]

    log.info("Building peer set for %s with %d peers: %s", target, len(peer_tickers), peer_tickers)

    # ── Fetch and compute target ───────────────────────────────────────────────
    target_raw = provider.get_raw_financials(target, quarters, annual_years)
    target_kpis = compute(target_raw)

    # ── Fetch and compute each peer (skip on failure) ─────────────────────────
    peer_metrics: list[PeerMetrics] = []
    for ticker in peer_tickers:
        try:
            raw = provider.get_raw_financials(ticker, quarters, annual_years)
            kpis = compute(raw)
            peer_metrics.append(PeerMetrics(ticker=ticker, kpis=kpis))
        except Exception as exc:
            log.warning("Skipping peer %s — fetch/compute failed: %s", ticker, exc)

    # ── Aggregate ─────────────────────────────────────────────────────────────
    sector_medians, comparisons = build_comparisons(
        target,
        target_kpis,
        peer_metrics,
        in_line_band=in_line_band,
    )

    return PeerSet(
        target=target,
        target_kpis=target_kpis,
        peers=peer_metrics,
        sector_medians=sector_medians,
        comparisons=comparisons,
    )
