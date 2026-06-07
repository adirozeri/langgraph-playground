"""Trend classifier: classify a MetricSeries as ACCELERATING, FLAT, or DECELERATING.

Algorithm: ordinary least-squares slope on the sequence of valid values,
normalised by the absolute mean so the threshold is scale-invariant.
A 1 % per-period change (normalised) is the default flat band.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from .models import UNAVAILABLE, MetricSeries, Trend, TrendResult

_FLAT_BAND = Decimal("0.01")  # 1 % per period is considered flat


def classify_trend(
    series: MetricSeries,
    threshold: Decimal = _FLAT_BAND,
) -> TrendResult:
    """Return ACCELERATING / FLAT / DECELERATING based on OLS slope.

    Requires at least 3 valid (non-UNAVAILABLE) data points.
    Series must be oldest-first (index 0 = earliest).
    """
    values = [p.value for p in series if p.value != UNAVAILABLE]
    n = len(values)
    if n < 3:
        return TrendResult(trend=Trend.INSUFFICIENT_DATA, normalized_slope=None, n_periods=n)

    xs = [Decimal(i) for i in range(n)]
    ys: list[Decimal] = [Decimal(str(v)) for v in values]

    n_d = Decimal(n)
    x_mean = sum(xs) / n_d
    y_mean = sum(ys) / n_d

    try:
        numer = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
        denom = sum((x - x_mean) ** 2 for x in xs)

        if denom == 0:
            return TrendResult(trend=Trend.FLAT, normalized_slope=Decimal("0"), n_periods=n)

        slope = numer / denom
        abs_mean = abs(y_mean)
        norm = slope / abs_mean if abs_mean != 0 else slope
    except (InvalidOperation, ZeroDivisionError):
        return TrendResult(trend=Trend.INSUFFICIENT_DATA, normalized_slope=None, n_periods=n)

    if norm > threshold:
        trend = Trend.ACCELERATING
    elif norm < -threshold:
        trend = Trend.DECELERATING
    else:
        trend = Trend.FLAT

    return TrendResult(trend=trend, normalized_slope=norm, n_periods=n)
