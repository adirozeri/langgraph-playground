"""Serialise dashboard objects into compact, human-readable dicts for prompts.

Numbers are pre-formatted (percentages, billions, ratios) so Claude reads them
as an analyst would.  Raw Decimal values and audit-trail fields (formula, inputs)
are stripped — Claude does not need them.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from ..data.models import UNAVAILABLE
from ..metrics.models import MaybeDecimal, MetricSeries, TrendResult
from ..dashboards.models import (
    CapitalDashboard,
    IncomeDashboard,
    MomentumDashboard,
    ValuationDashboard,
)

_NA = "UNAVAILABLE"


# ── Number formatters ─────────────────────────────────────────────────────────

def _pct(v: MaybeDecimal, *, sign: bool = False) -> str:
    if v == UNAVAILABLE:
        return _NA
    try:
        d = Decimal(str(v)) * 100
        prefix = "+" if sign and d > 0 else ""
        return f"{prefix}{d:.1f}%"
    except (InvalidOperation, TypeError):
        return _NA


def _usd_b(v: MaybeDecimal) -> str:
    if v == UNAVAILABLE:
        return _NA
    try:
        d = Decimal(str(v)) / Decimal("1_000_000_000")
        prefix = "+" if d > 0 else ""
        return f"{prefix}${d:.1f}B"
    except (InvalidOperation, TypeError):
        return _NA


def _usd(v: MaybeDecimal) -> str:
    if v == UNAVAILABLE:
        return _NA
    try:
        return f"${Decimal(str(v)):.2f}"
    except (InvalidOperation, TypeError):
        return _NA


def _usd_m(v: MaybeDecimal) -> str:
    if v == UNAVAILABLE:
        return _NA
    try:
        d = Decimal(str(v)) / Decimal("1_000_000")
        return f"${d:.2f}M"
    except (InvalidOperation, TypeError):
        return _NA


def _ratio(v: MaybeDecimal) -> str:
    if v == UNAVAILABLE:
        return _NA
    try:
        return f"{Decimal(str(v)):.1f}x"
    except (InvalidOperation, TypeError):
        return _NA


def _trend(t: TrendResult) -> str:
    return t.trend.value  # "ACCELERATING" | "FLAT" | "DECELERATING" | "INSUFFICIENT_DATA"


# ── Series to list ────────────────────────────────────────────────────────────

def _series(
    s: MetricSeries,
    fmt: Callable[[MaybeDecimal], str],
    n: int = 5,
) -> list[dict[str, str]]:
    tail = s[-n:] if len(s) >= n else s
    return [
        {"period": pt.period, "date": str(pt.period_date), "value": fmt(pt.value)}
        for pt in tail
    ]


def _latest(s: MetricSeries, fmt: Callable[[MaybeDecimal], str]) -> str:
    for pt in reversed(s):
        if pt.value != UNAVAILABLE:
            return fmt(pt.value)
    return _NA


def _metric(
    series: MetricSeries,
    fmt: Callable[[MaybeDecimal], str],
    trend: TrendResult | None,
    peer: MaybeDecimal,
    peer_fmt: Callable[[MaybeDecimal], str] | None = None,
    n: int = 5,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "latest": _latest(series, fmt),
        "history": _series(series, fmt, n),
    }
    if trend is not None:
        out["trend"] = _trend(trend)
    out["peer_median"] = (peer_fmt or fmt)(peer)
    return out


# ── Dashboard serialisers ─────────────────────────────────────────────────────

def serialise_income(db: IncomeDashboard, n: int = 5) -> dict[str, Any]:
    return {
        "ticker": db.ticker,
        "revenue": _metric(db.revenue, _usd_b, None, UNAVAILABLE),
        "revenue_growth_yoy": _metric(
            db.revenue_growth_yoy, lambda v: _pct(v, sign=True),
            db.revenue_growth_trend, db.peer_revenue_growth_yoy,
            peer_fmt=lambda v: _pct(v, sign=True), n=n,
        ),
        "gross_margin": _metric(db.gross_margin, _pct, db.gross_margin_trend, db.peer_gross_margin, n=n),
        "operating_margin": _metric(db.operating_margin, _pct, db.operating_margin_trend, db.peer_operating_margin, n=n),
        "net_margin": _metric(db.net_margin, _pct, db.net_margin_trend, db.peer_net_margin, n=n),
        "ebitda_margin": _metric(db.ebitda_margin, _pct, db.ebitda_margin_trend, db.peer_ebitda_margin, n=n),
        "free_cash_flow": _metric(db.free_cash_flow, _usd_b, None, UNAVAILABLE),
        "fcf_margin": _metric(db.fcf_margin, _pct, db.fcf_margin_trend, db.peer_fcf_margin, n=n),
    }


def serialise_momentum(db: MomentumDashboard, n: int = 5) -> dict[str, Any]:
    def _fwd_rev(series: MetricSeries) -> str:
        return _latest(series, _usd_b) if series else _NA

    return {
        "ticker": db.ticker,
        "eps_diluted": _metric(db.eps_annual, _usd, db.eps_trend, UNAVAILABLE),
        "eps_growth_yoy": _metric(
            db.eps_growth_yoy, lambda v: _pct(v, sign=True),
            db.eps_trend, db.peer_eps_growth_yoy,
            peer_fmt=lambda v: _pct(v, sign=True), n=n,
        ),
        "revenue_growth_yoy": _metric(
            db.revenue_growth_yoy, lambda v: _pct(v, sign=True),
            db.revenue_trend, db.peer_revenue_growth_yoy,
            peer_fmt=lambda v: _pct(v, sign=True), n=n,
        ),
        "free_cash_flow": _metric(db.fcf_annual, _usd_b, db.fcf_trend, UNAVAILABLE),
        "forward_revenue_estimate": _fwd_rev(db.forward_revenue),
        "trailing_pe": _latest(db.trailing_pe, _ratio),
        "forward_pe": _latest(db.forward_pe, _ratio),
        "historical_pe": _metric(db.historical_pe, _ratio, db.pe_trend, UNAVAILABLE),
        "peer_trailing_pe": _ratio(db.peer_trailing_pe),
        "peer_forward_pe": _ratio(db.peer_forward_pe),
    }


def serialise_valuation(db: ValuationDashboard, n: int = 5) -> dict[str, Any]:
    def _flag(f: Any) -> str:
        return f.value if f is not None else "INSUFFICIENT_DATA"

    return {
        "ticker": db.ticker,
        "trailing_pe": {
            "current": _latest(db.trailing_pe, _ratio),
            "peer_median": _ratio(db.peer_trailing_pe),
            "vs_own_history": _flag(db.pe_vs_own_history),
        },
        "forward_pe": {
            "current": _latest(db.forward_pe, _ratio),
            "peer_median": _ratio(db.peer_forward_pe),
        },
        "price_to_sales": {
            "current": _latest(db.price_to_sales, _ratio),
            "peer_median": _ratio(db.peer_price_to_sales),
            "vs_own_history": _flag(db.ps_vs_own_history),
        },
        "ev_to_ebitda": {
            "current": _latest(db.ev_to_ebitda, _ratio),
            "peer_median": _ratio(db.peer_ev_to_ebitda),
            "vs_own_history": _flag(db.ev_ebitda_vs_own_history),
        },
        "ev_to_gross_profit": {
            "current": _latest(db.ev_to_gross_profit, _ratio),
        },
        "historical_pe_series": _series(db.historical_pe, _ratio, n),
    }


def serialise_capital(db: CapitalDashboard, n: int = 5) -> dict[str, Any]:
    return {
        "ticker": db.ticker,
        "roic": _metric(db.roic, _pct, db.roic_trend, db.peer_roic, n=n),
        "roe": _metric(db.roe, _pct, db.roe_trend, db.peer_roe, n=n),
        "revenue_per_employee": _latest(db.revenue_per_employee, _usd_m),
        "buybacks": _metric(db.buybacks, _usd_b, None, UNAVAILABLE, n=n),
        "fcf_yield": _metric(db.fcf_yield, _pct, None, db.peer_fcf_yield, n=n),
        "analyst_price_target": {
            "consensus": _usd(db.price_target_consensus),
            "high": _usd(db.price_target_high),
            "low": _usd(db.price_target_low),
            "median": _usd(db.price_target_median),
            "implied_upside": _pct(db.price_upside, sign=True),
        },
    }
