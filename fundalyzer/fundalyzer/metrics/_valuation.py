# Architecture contract: current-price valuations computed from real data — no LLM figures.
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from ..data.models import (
    AnalystEstimate,
    BalanceSheet,
    CompanyProfile,
    IncomeStatement,
    PriceTargetConsensus,
)
from ._helpers import _unavailable, make_point, ratio
from .models import UNAVAILABLE, MaybeDecimal, MetricPoint, MetricSeries, ValuationKPIs


def _ttm_sum(quarterly: list[IncomeStatement], attr: str, n: int = 4) -> MaybeDecimal:
    """Sum the last *n* quarters of *attr*, propagating UNAVAILABLE if any quarter is missing."""
    tail = quarterly[-n:] if len(quarterly) >= n else quarterly
    if not tail:
        return UNAVAILABLE
    total = Decimal("0")
    for stmt in tail:
        v = getattr(stmt, attr)
        if v == UNAVAILABLE:
            return UNAVAILABLE
        try:
            total += Decimal(str(v))
        except (InvalidOperation, TypeError):
            return UNAVAILABLE
    return total


def compute_valuation(
    profile: CompanyProfile,
    quarterly_income: list[IncomeStatement],   # oldest-first; used for TTM
    annual_income: list[IncomeStatement],       # oldest-first; used for EPS history
    latest_balance: BalanceSheet | None,
    estimates: list[AnalystEstimate] | None,
    price_target: PriceTargetConsensus | None = None,
) -> ValuationKPIs:
    """All valuation KPIs are point-in-time, anchored to current price / market_cap.

    Returns single-element MetricSeries for point-in-time metrics and
    oldest-first MetricSeries for historical series (e.g. historical_pe).
    """
    price = profile.price
    market_cap = profile.market_cap

    today = date.today()
    snap_date = quarterly_income[-1].report_date if quarterly_income else today
    snap_period = quarterly_income[-1].period if quarterly_income else "snapshot"
    kw = dict(period=snap_period, period_date=snap_date)

    # ── TTM aggregates ────────────────────────────────────────────────────────
    ttm_eps = _ttm_sum(quarterly_income, "eps_diluted")
    ttm_revenue = _ttm_sum(quarterly_income, "revenue")
    ttm_ebitda = _ttm_sum(quarterly_income, "ebitda")
    ttm_gross_profit = _ttm_sum(quarterly_income, "gross_profit")

    # ── Enterprise Value ──────────────────────────────────────────────────────
    ev: MaybeDecimal
    total_debt: MaybeDecimal
    cash: MaybeDecimal
    if latest_balance is not None:
        total_debt = latest_balance.total_debt
        cash = latest_balance.cash_and_equivalents
        if market_cap == UNAVAILABLE or total_debt == UNAVAILABLE or cash == UNAVAILABLE:
            ev = UNAVAILABLE
        else:
            try:
                ev = Decimal(str(market_cap)) + Decimal(str(total_debt)) - Decimal(str(cash))
            except (InvalidOperation, TypeError):
                ev = UNAVAILABLE
    else:
        ev = UNAVAILABLE
        total_debt = UNAVAILABLE
        cash = UNAVAILABLE

    # ── Trailing P/E ──────────────────────────────────────────────────────────
    trailing_pe = [ratio(
        price, ttm_eps,
        formula="price / ttm_eps_diluted",
        price=price, ttm_eps_diluted=ttm_eps,
        **kw,
    )]

    # ── Forward P/E ───────────────────────────────────────────────────────────
    forward_eps: MaybeDecimal = UNAVAILABLE
    forward_rev_avg: MaybeDecimal = UNAVAILABLE
    if estimates:
        annual_ests = [e for e in estimates if e.period == "annual"]
        if annual_ests:
            forward_eps = annual_ests[0].eps_avg
            forward_rev_avg = annual_ests[0].revenue_avg

    forward_pe = [ratio(
        price, forward_eps,
        formula="price / forward_eps_avg",
        price=price, forward_eps_avg=forward_eps,
        **kw,
    )]

    # ── Forward Revenue ───────────────────────────────────────────────────────
    forward_revenue: MetricSeries = []
    if forward_rev_avg != UNAVAILABLE:
        forward_revenue = [make_point(
            forward_rev_avg,
            formula="analyst_consensus_revenue_avg",
            period=snap_period,
            period_date=snap_date,
            forward_revenue_avg=forward_rev_avg,
        )]

    # ── Price / Sales ─────────────────────────────────────────────────────────
    price_to_sales = [ratio(
        market_cap, ttm_revenue,
        formula="market_cap / ttm_revenue",
        market_cap=market_cap, ttm_revenue=ttm_revenue,
        **kw,
    )]

    # ── EV / EBITDA ───────────────────────────────────────────────────────────
    ev_to_ebitda = [ratio(
        ev, ttm_ebitda,
        formula="(market_cap + total_debt - cash) / ttm_ebitda",
        enterprise_value=ev, ttm_ebitda=ttm_ebitda,
        market_cap=market_cap, total_debt=total_debt, cash=cash,
        **kw,
    )]

    # ── EV / Gross Profit ─────────────────────────────────────────────────────
    ev_to_gross_profit = [ratio(
        ev, ttm_gross_profit,
        formula="(market_cap + total_debt - cash) / ttm_gross_profit",
        enterprise_value=ev, ttm_gross_profit=ttm_gross_profit,
        market_cap=market_cap, total_debt=total_debt, cash=cash,
        **kw,
    )]

    # ── PEG ───────────────────────────────────────────────────────────────────
    eps_growth: MaybeDecimal = UNAVAILABLE
    if len(annual_income) >= 2:
        last, prior = annual_income[-1], annual_income[-2]
        if last.eps_diluted != UNAVAILABLE and prior.eps_diluted != UNAVAILABLE:
            try:
                p = Decimal(str(prior.eps_diluted))
                if p != 0:
                    eps_growth = (Decimal(str(last.eps_diluted)) - p) / abs(p)
            except (InvalidOperation, TypeError):
                pass

    if trailing_pe[0].value == UNAVAILABLE or eps_growth == UNAVAILABLE:
        peg_val = UNAVAILABLE
    else:
        try:
            g = Decimal(str(eps_growth)) * 100
            peg_val = Decimal(str(trailing_pe[0].value)) / g if g != 0 else UNAVAILABLE
        except (InvalidOperation, TypeError, ZeroDivisionError):
            peg_val = UNAVAILABLE

    peg_series = [make_point(
        peg_val,
        formula="trailing_pe / (eps_growth_yoy × 100)",
        period=snap_period, period_date=snap_date,
        trailing_pe=trailing_pe[0].value, eps_growth_yoy=eps_growth,
    )]

    # ── Price / Book ──────────────────────────────────────────────────────────
    equity = latest_balance.total_equity if latest_balance else UNAVAILABLE
    price_to_book = [ratio(
        market_cap, equity,
        formula="market_cap / total_equity",
        market_cap=market_cap, total_equity=equity,
        **kw,
    )]

    # ── Historical P/E (oldest-first per annual period) ───────────────────────
    # current_price / period_eps_diluted for each annual year.
    # Shows what P/E you'd pay today for each historical earnings level —
    # useful for comparing current multiple to the company's own history.
    # NOTE: uses today's price as numerator; historical prices unavailable without
    # a price-history endpoint.
    historical_pe: MetricSeries = []
    for stmt in annual_income:
        historical_pe.append(ratio(
            price, stmt.eps_diluted,
            formula="current_price / annual_eps_diluted",
            period=stmt.period, period_date=stmt.report_date,
            current_price=price, annual_eps_diluted=stmt.eps_diluted,
        ))

    # ── Analyst Price Targets ─────────────────────────────────────────────────
    pt_consensus: MaybeDecimal = UNAVAILABLE
    pt_high: MaybeDecimal = UNAVAILABLE
    pt_low: MaybeDecimal = UNAVAILABLE
    pt_median: MaybeDecimal = UNAVAILABLE
    if price_target is not None:
        pt_consensus = price_target.target_consensus
        pt_high = price_target.target_high
        pt_low = price_target.target_low
        pt_median = price_target.target_median

    # Price upside vs consensus
    price_upside: MaybeDecimal = UNAVAILABLE
    if pt_consensus != UNAVAILABLE and price != UNAVAILABLE:
        try:
            p_dec = Decimal(str(price))
            if p_dec != 0:
                price_upside = (Decimal(str(pt_consensus)) - p_dec) / abs(p_dec)
        except (InvalidOperation, TypeError):
            pass

    return ValuationKPIs(
        trailing_pe=trailing_pe,
        forward_pe=forward_pe,
        forward_revenue=forward_revenue,
        price_to_sales=price_to_sales,
        ev_to_ebitda=ev_to_ebitda,
        ev_to_gross_profit=ev_to_gross_profit,
        peg=peg_series,
        price_to_book=price_to_book,
        historical_pe=historical_pe,
        price_target_consensus=pt_consensus,
        price_target_high=pt_high,
        price_target_low=pt_low,
        price_target_median=pt_median,
        price_upside=price_upside,
    )
