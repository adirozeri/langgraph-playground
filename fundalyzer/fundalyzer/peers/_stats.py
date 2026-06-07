"""Pure-Python statistics used for peer comparison.

All functions operate on plain Decimal lists so they are trivially testable
without touching any API or schema layer.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from .models import RelativePosition

# A deviation within this band of the peer median counts as IN_LINE.
# 5 % means: if the sector median gross margin is 30 %, anything in
# [28.5 %, 31.5 %] is considered in line.
DEFAULT_IN_LINE_BAND: Decimal = Decimal("0.05")


def median(values: list[Decimal]) -> Decimal | None:
    """Standard median of a Decimal list.

    Returns None for an empty list.
    Returns the average of the two middle elements when len is even.
    Input order does not matter.
    """
    if not values:
        return None
    sv = sorted(values)
    n = len(sv)
    mid = n // 2
    if n % 2 == 1:
        return sv[mid]
    return (sv[mid - 1] + sv[mid]) / Decimal("2")


def percentile_rank(value: Decimal, population: list[Decimal]) -> Decimal:
    """Exclusive percentile rank: fraction of population strictly below *value*.

    Result is in [0, 100].  Ties are counted as "not below", which means
    co-equal peers all receive the same percentile — the conventional
    definition used in academic finance.

    Examples:
        population = [1, 2, 3, 4, 5], value = 5  →  80.0
        population = [1, 2, 3, 4, 5], value = 1  →   0.0
        population = [1, 2, 3, 4, 5], value = 3  →  40.0
    """
    if not population:
        return Decimal("0")
    count_below = sum(1 for v in population if v < value)
    return Decimal(count_below) / Decimal(len(population)) * Decimal("100")


def relative_position(
    value: Decimal,
    peer_median: Decimal,
    *,
    higher_is_better: bool,
    in_line_band: Decimal = DEFAULT_IN_LINE_BAND,
) -> RelativePosition:
    """Classify a value as BETTER / WORSE / IN_LINE relative to the peer median.

    The band is applied symmetrically as a fraction of |peer_median|.
    When the absolute deviation from the median is within the band, the
    result is IN_LINE regardless of direction.

    Args:
        value:             Target company's metric value.
        peer_median:       Median of the peer group (target excluded).
        higher_is_better:  True for margins, ROE, etc.; False for P/E, D/E.
        in_line_band:      Fractional tolerance, default 5 %.
    """
    if peer_median == 0:
        # Cannot normalise by zero; treat any non-zero value as in-line to
        # avoid spurious BETTER/WORSE classifications.
        return RelativePosition.IN_LINE

    deviation = (value - peer_median) / abs(peer_median)

    if abs(deviation) <= in_line_band:
        return RelativePosition.IN_LINE

    outperforms_median = deviation > 0
    if higher_is_better:
        return RelativePosition.BETTER if outperforms_median else RelativePosition.WORSE
    else:
        return RelativePosition.WORSE if outperforms_median else RelativePosition.BETTER
