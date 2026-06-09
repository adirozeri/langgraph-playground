"""Full analysis pipeline orchestrator.

Data flow (strictly downward — no layer imports from above):

    data → metrics → peers → dashboards → interpret → decide → report

run_analysis() is the single entry point for the CLI and tests.
It wraps every layer in structured error handling and returns a typed
AnalysisResult that carries all intermediate outputs for debugging.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from .dashboards.build import build as build_dashboards
from .dashboards.models import (
    CapitalDashboard,
    IncomeDashboard,
    MomentumDashboard,
    ValuationDashboard,
)
from .data.base import FinancialDataProvider
from .data.errors import ProviderUnavailableError
from .data.models import RawFinancials
from .decide import decide
from .decide.models import InvestmentDecision
from .interpret import interpret
from .interpret._client import DEFAULT_MODEL, MessagesAPI
from .interpret.models import Interpretation
from .metrics.compute import compute
from .metrics.models import TickerKPIs
from .peers.build import build as build_peers
from .peers.models import PeerSet
from .report import (
    build_deep_dive_report,
    build_snapshot_report,
)
from .report.models import DeepDiveReport, SnapshotReport

log = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """All outputs from a complete analysis run."""

    ticker: str
    raw: RawFinancials
    kpis: TickerKPIs
    peer_set: PeerSet
    income: IncomeDashboard
    momentum: MomentumDashboard
    valuation: ValuationDashboard
    capital: CapitalDashboard
    interpretation: Interpretation
    decision: InvestmentDecision
    snapshot: SnapshotReport
    deep_dive: DeepDiveReport


ProgressCallback = Callable[[str, str], None]
"""Callback type: (ticker, step) → None.

step values emitted during a run:
  "fetching_data"       layer 1 complete
  "computing_kpis"      layer 2 complete
  "building_peers"      layer 3 complete
  "building_dashboards" layer 4 complete
  "interpreting"        layer 5 complete
  "deciding"            layer 6 complete
  "done"                all layers complete
"""


def run_analysis(
    ticker: str,
    provider: FinancialDataProvider,
    peers: list[str] | None = None,
    annual_years: int = 10,
    quarters: int = 12,
    *,
    peer_set: PeerSet | None = None,
    model: str = DEFAULT_MODEL,
    messages_api: MessagesAPI | None = None,
    progress_callback: ProgressCallback | None = None,
) -> AnalysisResult:
    """Run the full fundalyzer pipeline for *ticker*.

    Args:
        ticker:            Target ticker symbol (case-insensitive).
        provider:          Financial data provider (FMP, Composite, etc.).
        peers:             Explicit peer list.  None → derive from provider.
        annual_years:      Years of annual statement history to fetch.
        quarters:          Quarters of history to fetch.
        peer_set:          Pre-built peer set; skips layer 3 when supplied.
        model:             Claude model ID for the interpret/decide LLM calls.
        messages_api:      Injectable Anthropic messages object (for testing).
        progress_callback: Optional (ticker, step) → None called after each
                           layer.  The CLI passes None; the FastAPI SSE route
                           passes a function that pushes events to the browser.

    Returns:
        AnalysisResult containing every intermediate output.

    Raises:
        ProviderUnavailableError: if the primary provider fails for the target
            ticker and no cached data is available.
        NoCachedDataError: if --dry-run was requested and data is not cached.
    """
    def _emit(step: str) -> None:
        if progress_callback is not None:
            progress_callback(ticker, step)

    ticker = ticker.upper()
    log.info("Starting analysis for %s (years=%d, peers=%s)", ticker, annual_years, peers)

    # ── Layer 1: data ─────────────────────────────────────────────────────────
    log.debug("Fetching raw financials for %s", ticker)
    try:
        raw = provider.get_raw_financials(ticker, quarters=quarters, annual_years=annual_years)
    except httpx.HTTPStatusError as exc:
        raise ProviderUnavailableError(
            ticker, type(provider).__name__, f"HTTP {exc.response.status_code}"
        ) from exc
    except httpx.ConnectError as exc:
        raise ProviderUnavailableError(
            ticker, type(provider).__name__, f"Connection failed: {exc}"
        ) from exc
    _emit("fetching_data")

    # ── Layer 2: metrics ──────────────────────────────────────────────────────
    log.debug("Computing KPIs for %s", ticker)
    kpis = compute(raw)
    _emit("computing_kpis")

    # ── Layer 3: peers ────────────────────────────────────────────────────────
    if peer_set is not None:
        log.debug("Using pre-built peer set for %s (%d peers)", ticker, len(peer_set.peers))
    else:
        log.debug("Building peer set for %s", ticker)
        try:
            peer_set = build_peers(
                ticker,
                provider,
                peers=peers,
                annual_years=annual_years,
                quarters=quarters,
            )
        except (httpx.HTTPStatusError, httpx.ConnectError) as exc:
            log.warning(
                "Peer fetch failed for %s (%s); continuing with no peers", ticker, exc
            )
            from .peers._aggregator import build_comparisons

            sm, cmp = build_comparisons(ticker, kpis, [])
            peer_set = PeerSet(
                target=ticker,
                target_kpis=kpis,
                peers=[],
                sector_medians=sm,
                comparisons=cmp,
            )
    _emit("building_peers")

    # ── Layer 4: dashboards ───────────────────────────────────────────────────
    log.debug("Assembling dashboards for %s", ticker)
    income, momentum, valuation, capital = build_dashboards(kpis, peer_set)
    _emit("building_dashboards")

    # ── Layer 5: interpret ────────────────────────────────────────────────────
    log.info("Calling LLM for interpretations (4 structured + 1 synthesis)")
    interpretation = interpret(
        income, momentum, valuation, capital,
        model=model,
        messages_api=messages_api,
    )
    _emit("interpreting")

    # ── Layer 6: decide ───────────────────────────────────────────────────────
    log.info("Computing investment decision for %s", ticker)
    decision = decide(
        kpis, peer_set, interpretation, raw,
        model=model,
        messages_api=messages_api,
    )
    _emit("deciding")

    # ── Layer 7: report ───────────────────────────────────────────────────────
    snapshot = build_snapshot_report(income, momentum, valuation, capital, decision)
    deep_dive = build_deep_dive_report(
        income, momentum, valuation, capital, interpretation, decision
    )

    log.info("Analysis complete for %s — lean: %s", ticker, decision.lean.value)
    _emit("done")

    return AnalysisResult(
        ticker=ticker,
        raw=raw,
        kpis=kpis,
        peer_set=peer_set,
        income=income,
        momentum=momentum,
        valuation=valuation,
        capital=capital,
        interpretation=interpretation,
        decision=decision,
        snapshot=snapshot,
        deep_dive=deep_dive,
    )
