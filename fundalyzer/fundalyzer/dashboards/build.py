# Architecture contract: assemble metrics into dashboards — no new computation, no LLM.
from __future__ import annotations

from decimal import Decimal

from ..data.models import UNAVAILABLE
from ..metrics._trend import classify_trend
from ..metrics.models import MaybeDecimal, MetricSeries, TickerKPIs
from ..peers._stats import median, relative_position
from ..peers.models import PeerSet, RelativePosition
from .models import (
    CapitalDashboard,
    IncomeDashboard,
    MomentumDashboard,
    ValuationDashboard,
)


def _self_history_position(
    series: MetricSeries,
    higher_is_better: bool,
) -> RelativePosition | None:
    """Compare the latest value in a series to the median of all prior values.

    Returns None when fewer than 2 valid data points exist.
    For valuation multiples (higher_is_better=False), BETTER means cheaper
    than the company's own historical average.
    """
    valid = [Decimal(str(p.value)) for p in series if p.value != UNAVAILABLE]
    if len(valid) < 2:
        return None
    current = valid[-1]
    hist_med = median(valid[:-1])
    if hist_med is None:
        return None
    return relative_position(current, hist_med, higher_is_better=higher_is_better)


def build(
    kpis: TickerKPIs,
    peer_set: PeerSet,
) -> tuple[IncomeDashboard, MomentumDashboard, ValuationDashboard, CapitalDashboard]:
    """Assemble four typed dashboard objects from computed metrics.

    Pure assembly: every field is copied from *kpis* or *peer_set*.
    The only arithmetic here is the self-history comparison (current vs own
    historical median) using functions already in the peers._stats module.
    """
    sm = peer_set.sector_medians   # sector medians for peer columns
    pa = kpis.profitability_annual
    val = kpis.valuation
    cfa = kpis.cash_flow_annual
    fsa = kpis.financial_strength_annual

    # ── IncomeDashboard ───────────────────────────────────────────────────────
    income = IncomeDashboard(
        ticker=kpis.ticker,
        revenue=pa.revenue,
        revenue_growth_yoy=pa.revenue_growth_yoy,
        revenue_growth_trend=classify_trend(pa.revenue_growth_yoy),
        gross_margin=pa.gross_margin,
        gross_margin_trend=classify_trend(pa.gross_margin),
        operating_margin=pa.operating_margin,
        operating_margin_trend=classify_trend(pa.operating_margin),
        net_margin=pa.net_margin,
        net_margin_trend=classify_trend(pa.net_margin),
        ebitda_margin=pa.ebitda_margin,
        ebitda_margin_trend=classify_trend(pa.ebitda_margin),
        free_cash_flow=cfa.free_cash_flow,
        fcf_margin=cfa.fcf_margin,
        fcf_margin_trend=classify_trend(cfa.fcf_margin),
        # Peer medians
        peer_revenue_growth_yoy=sm.revenue_growth_yoy,
        peer_gross_margin=sm.gross_margin,
        peer_operating_margin=sm.operating_margin,
        peer_net_margin=sm.net_margin,
        peer_ebitda_margin=sm.ebitda_margin,
        peer_fcf_margin=sm.fcf_margin,
    )

    # ── MomentumDashboard ─────────────────────────────────────────────────────
    momentum = MomentumDashboard(
        ticker=kpis.ticker,
        eps_annual=pa.eps_diluted,
        eps_growth_yoy=pa.eps_growth_yoy,
        eps_trend=classify_trend(pa.eps_growth_yoy),
        revenue_annual=pa.revenue,
        revenue_growth_yoy=pa.revenue_growth_yoy,
        revenue_trend=classify_trend(pa.revenue_growth_yoy),
        fcf_annual=cfa.free_cash_flow,
        fcf_trend=classify_trend(cfa.free_cash_flow),
        forward_revenue=val.forward_revenue,
        trailing_pe=val.trailing_pe,
        forward_pe=val.forward_pe,
        historical_pe=val.historical_pe,
        pe_trend=classify_trend(val.historical_pe),
        # Peer medians
        peer_eps_growth_yoy=sm.eps_growth_yoy,
        peer_revenue_growth_yoy=sm.revenue_growth_yoy,
        peer_trailing_pe=sm.trailing_pe,
        peer_forward_pe=sm.forward_pe,
    )

    # ── ValuationDashboard ────────────────────────────────────────────────────
    valuation = ValuationDashboard(
        ticker=kpis.ticker,
        trailing_pe=val.trailing_pe,
        forward_pe=val.forward_pe,
        price_to_sales=val.price_to_sales,
        ev_to_ebitda=val.ev_to_ebitda,
        ev_to_gross_profit=val.ev_to_gross_profit,
        historical_pe=val.historical_pe,
        # Self-history flags: lower multiple = cheaper = BETTER
        pe_vs_own_history=_self_history_position(val.historical_pe, higher_is_better=False),
        ps_vs_own_history=_self_history_position(val.price_to_sales, higher_is_better=False),
        ev_ebitda_vs_own_history=_self_history_position(val.ev_to_ebitda, higher_is_better=False),
        # Peer medians
        peer_trailing_pe=sm.trailing_pe,
        peer_forward_pe=sm.forward_pe,
        peer_price_to_sales=sm.price_to_sales,
        peer_ev_to_ebitda=sm.ev_to_ebitda,
    )

    # ── CapitalDashboard ──────────────────────────────────────────────────────
    capital = CapitalDashboard(
        ticker=kpis.ticker,
        roic=fsa.roic,
        roic_trend=classify_trend(fsa.roic),
        roe=fsa.roe,
        roe_trend=classify_trend(fsa.roe),
        revenue_per_employee=pa.revenue_per_employee,
        buybacks=cfa.buybacks,
        fcf_yield=cfa.fcf_yield,
        # Analyst price target (from ValuationKPIs; populated by metrics layer)
        price_target_consensus=val.price_target_consensus,
        price_target_high=val.price_target_high,
        price_target_low=val.price_target_low,
        price_target_median=val.price_target_median,
        price_upside=val.price_upside,
        # Peer medians
        peer_roic=sm.roic,
        peer_roe=sm.roe,
        peer_fcf_yield=sm.fcf_yield,
    )

    return income, momentum, valuation, capital
