"""Shared primitives for metric computation.

Every public function returns a MetricPoint so provenance is never lost.
UNAVAILABLE propagates automatically: any UNAVAILABLE input produces an
UNAVAILABLE output — callers must not substitute 0 or None.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from .models import UNAVAILABLE, MaybeDecimal, MetricPoint


def _str(v: Any) -> str:
    return str(v)


def make_point(
    value: MaybeDecimal,
    *,
    period: str,
    period_date: date,
    formula: str,
    **inputs: Any,
) -> MetricPoint:
    return MetricPoint(
        value=value,
        period=period,
        period_date=period_date,
        formula=formula,
        inputs={k: _str(v) for k, v in inputs.items()},
    )


def _unavailable(*, period: str, period_date: date, formula: str, **inputs: Any) -> MetricPoint:
    return make_point(UNAVAILABLE, period=period, period_date=period_date, formula=formula, **inputs)


def ratio(
    numerator: MaybeDecimal,
    denominator: MaybeDecimal,
    *,
    period: str,
    period_date: date,
    formula: str,
    allow_negative_denom: bool = False,
    **inputs: Any,
) -> MetricPoint:
    """numerator / denominator with full UNAVAILABLE propagation."""
    kw = dict(period=period, period_date=period_date, formula=formula, **inputs)
    if numerator == UNAVAILABLE or denominator == UNAVAILABLE:
        return _unavailable(**kw)
    try:
        d = Decimal(str(denominator))
        if d == 0:
            return _unavailable(**kw)
        if not allow_negative_denom and d < 0:
            return _unavailable(**kw)
        return make_point(Decimal(str(numerator)) / d, **kw)
    except (InvalidOperation, TypeError):
        return _unavailable(**kw)


def yoy(
    current: MaybeDecimal,
    prior: MaybeDecimal,
    *,
    period: str,
    period_date: date,
    formula: str,
    **inputs: Any,
) -> MetricPoint:
    """(current − prior) / |prior|.  Uses absolute value of prior to handle
    sign changes without producing a meaningless negative-divided-by-negative."""
    kw = dict(period=period, period_date=period_date, formula=formula, **inputs)
    if current == UNAVAILABLE or prior == UNAVAILABLE:
        return _unavailable(**kw)
    try:
        c, p = Decimal(str(current)), Decimal(str(prior))
        if p == 0:
            return _unavailable(**kw)
        return make_point((c - p) / abs(p), **kw)
    except (InvalidOperation, TypeError):
        return _unavailable(**kw)


def passthrough(
    value: MaybeDecimal,
    *,
    period: str,
    period_date: date,
    formula: str,
    **inputs: Any,
) -> MetricPoint:
    """Wrap a raw statement value in a MetricPoint without any arithmetic."""
    return make_point(value, period=period, period_date=period_date, formula=formula, **inputs)
