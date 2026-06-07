# Architecture contract: dashboards are assembled from computed metrics only.
# No new computation, no LLM involvement, no API calls.
from __future__ import annotations

from pydantic import BaseModel

from ..metrics.models import MaybeDecimal, MetricSeries, TrendResult
from ..peers.models import RelativePosition


class IncomeDashboard(BaseModel):
    """Foundation view: revenue trajectory, full profitability stack, and FCF.

    Every series is the annual time series (oldest-first) from the metrics layer.
    Trend classifications answer "is the pace improving?"
    Peer medians sit beside each metric so no number is read in isolation.
    """

    ticker: str

    # ── Revenue ───────────────────────────────────────────────────────────────
    revenue: MetricSeries
    revenue_growth_yoy: MetricSeries
    revenue_growth_trend: TrendResult

    # ── Profitability stack ───────────────────────────────────────────────────
    gross_margin: MetricSeries
    gross_margin_trend: TrendResult
    operating_margin: MetricSeries
    operating_margin_trend: TrendResult
    net_margin: MetricSeries
    net_margin_trend: TrendResult
    ebitda_margin: MetricSeries
    ebitda_margin_trend: TrendResult

    # ── Cash flow ─────────────────────────────────────────────────────────────
    free_cash_flow: MetricSeries
    fcf_margin: MetricSeries
    fcf_margin_trend: TrendResult

    # ── Peer medians (from SectorMedian) ─────────────────────────────────────
    peer_revenue_growth_yoy: MaybeDecimal
    peer_gross_margin: MaybeDecimal
    peer_operating_margin: MaybeDecimal
    peer_net_margin: MaybeDecimal
    peer_ebitda_margin: MaybeDecimal
    peer_fcf_margin: MaybeDecimal


class MomentumDashboard(BaseModel):
    """Engine view: rate of change for the key growth drivers.

    Every metric has a TrendResult attached.  The P/E section shows trailing
    vs forward vs historical so changes in market expectations are visible.
    Sales vs guidance compares actual revenue to analyst consensus.
    """

    ticker: str

    # ── EPS trajectory ────────────────────────────────────────────────────────
    eps_annual: MetricSeries
    eps_growth_yoy: MetricSeries
    eps_trend: TrendResult

    # ── Revenue momentum ──────────────────────────────────────────────────────
    revenue_annual: MetricSeries
    revenue_growth_yoy: MetricSeries
    revenue_trend: TrendResult

    # ── FCF momentum ──────────────────────────────────────────────────────────
    fcf_annual: MetricSeries
    fcf_trend: TrendResult

    # ── Sales vs guidance ─────────────────────────────────────────────────────
    forward_revenue: MetricSeries     # analyst consensus estimate; empty if unavailable

    # ── P/E: history vs forward ───────────────────────────────────────────────
    trailing_pe: MetricSeries         # current snapshot
    forward_pe: MetricSeries          # analyst-based
    historical_pe: MetricSeries       # current_price / annual_eps per historical year
    pe_trend: TrendResult             # is the shadow-P/E series expanding or contracting?

    # ── Peer medians ──────────────────────────────────────────────────────────
    peer_eps_growth_yoy: MaybeDecimal
    peer_revenue_growth_yoy: MaybeDecimal
    peer_trailing_pe: MaybeDecimal
    peer_forward_pe: MaybeDecimal


class ValuationDashboard(BaseModel):
    """Price view: multiples over a 5-10 year window, flagged vs own history and peers.

    pe_vs_own_history / ps_vs_own_history / ev_ebitda_vs_own_history are
    BETTER when the current multiple is below the company's own historical
    median (i.e. cheaper than usual).
    """

    ticker: str

    # ── Current multiples ─────────────────────────────────────────────────────
    trailing_pe: MetricSeries
    forward_pe: MetricSeries
    price_to_sales: MetricSeries
    ev_to_ebitda: MetricSeries
    ev_to_gross_profit: MetricSeries

    # ── Self-history view (oldest-first; latest point ≈ current multiple) ─────
    # Series: current_price / period_eps_diluted for each annual year.
    historical_pe: MetricSeries

    # ── Self-history flags ────────────────────────────────────────────────────
    pe_vs_own_history: RelativePosition | None    # BETTER = cheaper than own median
    ps_vs_own_history: RelativePosition | None
    ev_ebitda_vs_own_history: RelativePosition | None

    # ── Peer medians ──────────────────────────────────────────────────────────
    peer_trailing_pe: MaybeDecimal
    peer_forward_pe: MaybeDecimal
    peer_price_to_sales: MaybeDecimal
    peer_ev_to_ebitda: MaybeDecimal


class CapitalDashboard(BaseModel):
    """Allocation view: how efficiently is capital deployed, returned, and priced?

    ROIC and ROE measure deployment quality.
    Buybacks and FCF yield measure capital return.
    Revenue per employee measures workforce efficiency.
    Price target fields give analyst consensus on whether the current price is fair.
    """

    ticker: str

    # ── Deployment quality ────────────────────────────────────────────────────
    roic: MetricSeries
    roic_trend: TrendResult
    roe: MetricSeries
    roe_trend: TrendResult

    # ── Workforce efficiency ──────────────────────────────────────────────────
    revenue_per_employee: MetricSeries   # single point unless historical headcount available

    # ── Capital return ────────────────────────────────────────────────────────
    buybacks: MetricSeries      # share repurchase outflows (negative = cash out)
    fcf_yield: MetricSeries     # free cash flow as % of market cap

    # ── Analyst view on current price ─────────────────────────────────────────
    price_target_consensus: MaybeDecimal
    price_target_high: MaybeDecimal
    price_target_low: MaybeDecimal
    price_target_median: MaybeDecimal
    price_upside: MaybeDecimal    # (consensus − current_price) / |current_price|

    # ── Peer medians ──────────────────────────────────────────────────────────
    peer_roic: MaybeDecimal
    peer_roe: MaybeDecimal
    peer_fcf_yield: MaybeDecimal
