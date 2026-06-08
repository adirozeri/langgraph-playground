# Architecture contract: projections computed from analyst estimates and API data — no LLM figures.
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from ..data.models import UNAVAILABLE
from ..metrics.models import MaybeDecimal, MetricSeries, TickerKPIs
from .models import Projection, ProjectionCase

BULL_GROWTH_UPLIFT = Decimal("0.15")   # +15 pp to annual growth rate in bull case
BULL_PE_EXPANSION = Decimal("0.10")    # +10% to trailing P/E multiple in bull case


def _latest_valid(series: MetricSeries) -> MaybeDecimal:
    for pt in reversed(series):
        if pt.value != UNAVAILABLE:
            return pt.value
    return UNAVAILABLE


def _last_yoy_growth(series: MetricSeries) -> MaybeDecimal:
    """Year-over-year growth implied by the last two valid values in an oldest-first series."""
    valid = [Decimal(str(p.value)) for p in series if p.value != UNAVAILABLE]
    if len(valid) < 2:
        return UNAVAILABLE
    prev, curr = valid[-2], valid[-1]
    if prev == 0:
        return UNAVAILABLE
    return (curr - prev) / abs(prev)


def _grow_3yr(
    base: Decimal, annual_rate: MaybeDecimal
) -> tuple[MaybeDecimal, MaybeDecimal, MaybeDecimal, MaybeDecimal]:
    """Compound *base* at *annual_rate* for 3 years.  Returns (yr1, yr2, yr3, cagr)."""
    if annual_rate == UNAVAILABLE:
        return UNAVAILABLE, UNAVAILABLE, UNAVAILABLE, UNAVAILABLE
    try:
        g = Decimal(str(annual_rate))
        y1 = base * (1 + g)
        y2 = y1 * (1 + g)
        y3 = y2 * (1 + g)
        return y1, y2, y3, g
    except (InvalidOperation, TypeError):
        return UNAVAILABLE, UNAVAILABLE, UNAVAILABLE, UNAVAILABLE


def _implied_price(eps_yr3: MaybeDecimal, pe_multiple: MaybeDecimal) -> MaybeDecimal:
    if eps_yr3 == UNAVAILABLE or pe_multiple == UNAVAILABLE:
        return UNAVAILABLE
    try:
        return Decimal(str(eps_yr3)) * Decimal(str(pe_multiple))
    except (InvalidOperation, TypeError):
        return UNAVAILABLE


_RevTuple = tuple[MaybeDecimal, MaybeDecimal, MaybeDecimal, MaybeDecimal, MaybeDecimal]


def _base_revenue_growth(kpis: TickerKPIs) -> _RevTuple:
    """Compute (base_revenue, yr1, yr2, yr3, cagr) for the base case revenue projection."""
    pa = kpis.profitability_annual
    val = kpis.valuation

    base_rev = _latest_valid(pa.revenue)
    if base_rev == UNAVAILABLE:
        return UNAVAILABLE, UNAVAILABLE, UNAVAILABLE, UNAVAILABLE, UNAVAILABLE

    base_d = Decimal(str(base_rev))

    # Prefer analyst consensus forward revenue for year 1 when available.
    fwd_rev = _latest_valid(val.forward_revenue)
    if fwd_rev != UNAVAILABLE:
        y1 = Decimal(str(fwd_rev))
        if base_d != 0:
            growth = (y1 - base_d) / abs(base_d)
        else:
            growth = UNAVAILABLE
    else:
        growth = _last_yoy_growth(pa.revenue)
        y1 = base_d * (1 + Decimal(str(growth))) if growth != UNAVAILABLE else UNAVAILABLE

    if y1 == UNAVAILABLE or growth == UNAVAILABLE:
        return base_rev, UNAVAILABLE, UNAVAILABLE, UNAVAILABLE, UNAVAILABLE

    try:
        g = Decimal(str(growth))
        y2 = Decimal(str(y1)) * (1 + g)
        y3 = y2 * (1 + g)
        return base_rev, y1, y2, y3, g
    except (InvalidOperation, TypeError):
        return base_rev, UNAVAILABLE, UNAVAILABLE, UNAVAILABLE, UNAVAILABLE


def build_projection(kpis: TickerKPIs) -> Projection:
    """Build base case and bull case 3-year projections from TickerKPIs.

    Revenue year 1 comes from the analyst consensus forward_revenue field when
    available; otherwise the most recent YoY growth rate is extrapolated.
    EPS growth is extrapolated from the most recent annual EPS growth rate.
    Applied P/E is the current trailing P/E (what the market is currently paying).
    Bull case adds BULL_GROWTH_UPLIFT to both revenue and EPS CAGRs and
    BULL_PE_EXPANSION to the applied multiple.

    The assumption_narrative fields start empty — filled by the LLM after the
    numbers are fixed.
    """
    pa = kpis.profitability_annual
    val = kpis.valuation

    base_eps = _latest_valid(pa.eps_diluted)
    trailing_pe = _latest_valid(val.trailing_pe)

    # ── Revenue trajectory ────────────────────────────────────────────────────
    base_rev, y1_rev, y2_rev, y3_rev, rev_cagr = _base_revenue_growth(kpis)

    # ── EPS trajectory — extrapolate from last YoY growth ────────────────────
    eps_growth = _last_yoy_growth(pa.eps_diluted)
    if base_eps != UNAVAILABLE and eps_growth != UNAVAILABLE:
        y1_eps, y2_eps, y3_eps, eps_cagr = _grow_3yr(Decimal(str(base_eps)), eps_growth)
    else:
        y1_eps = y2_eps = y3_eps = eps_cagr = UNAVAILABLE

    base_case = ProjectionCase(
        label="base_case",
        base_revenue=base_rev,
        year_1_revenue=y1_rev,
        year_2_revenue=y2_rev,
        year_3_revenue=y3_rev,
        revenue_cagr=rev_cagr,
        base_eps=base_eps,
        year_1_eps=y1_eps,
        year_2_eps=y2_eps,
        year_3_eps=y3_eps,
        eps_cagr=eps_cagr,
        applied_pe_multiple=trailing_pe,
        implied_price_year_3=_implied_price(y3_eps, trailing_pe),
    )

    # ── Bull case: uplift growth rates, expand multiple ───────────────────────
    bull_rev_cagr: MaybeDecimal
    bull_eps_cagr: MaybeDecimal

    if base_rev != UNAVAILABLE and rev_cagr != UNAVAILABLE:
        bull_r = Decimal(str(rev_cagr)) + BULL_GROWTH_UPLIFT
        b1r, b2r, b3r, bull_rev_cagr = _grow_3yr(Decimal(str(base_rev)), bull_r)
    else:
        b1r = b2r = b3r = bull_rev_cagr = UNAVAILABLE

    if base_eps != UNAVAILABLE and eps_cagr != UNAVAILABLE:
        bull_e = Decimal(str(eps_cagr)) + BULL_GROWTH_UPLIFT
        b1e, b2e, b3e, bull_eps_cagr = _grow_3yr(Decimal(str(base_eps)), bull_e)
    else:
        b1e = b2e = b3e = bull_eps_cagr = UNAVAILABLE

    bull_pe: MaybeDecimal
    if trailing_pe != UNAVAILABLE:
        bull_pe = Decimal(str(trailing_pe)) * (1 + BULL_PE_EXPANSION)
    else:
        bull_pe = UNAVAILABLE

    bull_case = ProjectionCase(
        label="bull_case",
        base_revenue=base_rev,
        year_1_revenue=b1r,
        year_2_revenue=b2r,
        year_3_revenue=b3r,
        revenue_cagr=bull_rev_cagr,
        base_eps=base_eps,
        year_1_eps=b1e,
        year_2_eps=b2e,
        year_3_eps=b3e,
        eps_cagr=bull_eps_cagr,
        applied_pe_multiple=bull_pe,
        implied_price_year_3=_implied_price(b3e, bull_pe),
    )

    return Projection(base_case=base_case, bull_case=bull_case)
