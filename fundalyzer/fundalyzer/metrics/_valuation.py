# Architecture contract: current-price valuations computed from real data — no LLM figures.
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from ..data.models import AnalystEstimate, BalanceSheet, CompanyProfile, IncomeStatement
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
    quarterly_income: list[IncomeStatement],  # oldest-first; used for TTM
    annual_income: list[IncomeStatement],      # oldest-first; used for EPS growth
    latest_balance: BalanceSheet | None,
    estimates: list[AnalystEstimate] | None,
) -> ValuationKPIs:
    """All valuation KPIs are point-in-time, anchored to current price / market_cap.

    Returns single-element MetricSeries for each metric so the series interface
    is uniform with profitability / strength pillars.
    """
    price = profile.price
    market_cap = profile.market_cap

    today = date.today()
    # Use the latest quarterly period date as the snapshot date if available
    snap_date = quarterly_income[-1].report_date if quarterly_income else today
    snap_period = quarterly_income[-1].period if quarterly_income else "snapshot"

    kw = dict(period=snap_period, period_date=snap_date)

    # ── TTM aggregates ────────────────────────────────────────────────────────
    ttm_eps = _ttm_sum(quarterly_income, "eps_diluted")
    ttm_revenue = _ttm_sum(quarterly_income, "revenue")
    ttm_ebitda = _ttm_sum(quarterly_income, "ebitda")

    # ── Enterprise Value ──────────────────────────────────────────────────────
    if latest_balance is not None:
        ev: MaybeDecimal
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
        price=price,
        ttm_eps_diluted=ttm_eps,
        **kw,
    )]

    # ── Forward P/E ───────────────────────────────────────────────────────────
    forward_eps: MaybeDecimal = UNAVAILABLE
    if estimates:
        # Use the nearest future annual estimate
        annual_ests = [e for e in estimates if e.period == "annual"]
        if annual_ests:
            forward_eps = annual_ests[0].eps_avg

    forward_pe = [ratio(
        price, forward_eps,
        formula="price / forward_eps_avg",
        price=price,
        forward_eps_avg=forward_eps,
        **kw,
    )]

    # ── Price / Sales ─────────────────────────────────────────────────────────
    price_to_sales = [ratio(
        market_cap, ttm_revenue,
        formula="market_cap / ttm_revenue",
        market_cap=market_cap,
        ttm_revenue=ttm_revenue,
        **kw,
    )]

    # ── EV / EBITDA ───────────────────────────────────────────────────────────
    ev_to_ebitda = [ratio(
        ev, ttm_ebitda,
        formula="(market_cap + total_debt - cash) / ttm_ebitda",
        enterprise_value=ev,
        ttm_ebitda=ttm_ebitda,
        market_cap=market_cap,
        total_debt=total_debt,
        cash=cash,
        **kw,
    )]

    # ── PEG — trailing_pe / most-recent annual eps_growth ────────────────────
    eps_growth: MaybeDecimal = UNAVAILABLE
    if len(annual_income) >= 2:
        last = annual_income[-1]
        prior = annual_income[-2]
        if last.eps_diluted != UNAVAILABLE and prior.eps_diluted != UNAVAILABLE:
            try:
                p = Decimal(str(prior.eps_diluted))
                if p != 0:
                    eps_growth = (Decimal(str(last.eps_diluted)) - p) / abs(p)
            except (InvalidOperation, TypeError):
                pass

    peg: MaybeDecimal
    if trailing_pe[0].value == UNAVAILABLE or eps_growth == UNAVAILABLE:
        peg_val = UNAVAILABLE
    else:
        try:
            g = Decimal(str(eps_growth)) * 100  # PEG uses % growth in denominator
            peg_val = Decimal(str(trailing_pe[0].value)) / g if g != 0 else UNAVAILABLE
        except (InvalidOperation, TypeError, ZeroDivisionError):
            peg_val = UNAVAILABLE

    peg_series = [make_point(
        peg_val,
        formula="trailing_pe / (eps_growth_yoy × 100)",
        period=snap_period,
        period_date=snap_date,
        trailing_pe=trailing_pe[0].value,
        eps_growth_yoy=eps_growth,
    )]

    # ── Price / Book ──────────────────────────────────────────────────────────
    equity = latest_balance.total_equity if latest_balance else UNAVAILABLE
    price_to_book = [ratio(
        market_cap, equity,
        formula="market_cap / total_equity",
        market_cap=market_cap,
        total_equity=equity,
        **kw,
    )]

    return ValuationKPIs(
        trailing_pe=trailing_pe,
        forward_pe=forward_pe,
        price_to_sales=price_to_sales,
        ev_to_ebitda=ev_to_ebitda,
        peg=peg_series,
        price_to_book=price_to_book,
    )
