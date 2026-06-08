# Architecture contract: position computed from provider data only — no LLM-generated figures.
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from ..data.models import UNAVAILABLE
from ..metrics.models import MaybeDecimal, MetricSeries, TickerKPIs
from ..peers._stats import median
from ..peers.models import PeerSet
from .models import ValuationHistoryPosition, ValuationPosition

_IN_LINE_BAND = Decimal("0.10")  # ±10% of historical median → IN_LINE


_HIST_PE_WINDOW = 5  # years of history to use; avoids old low-EPS periods inflating median

def _series_median_excluding_latest(series: MetricSeries) -> Decimal | None:
    """Median of the most recent HIST_PE_WINDOW prior values (oldest-first, latest excluded).

    Capping the window prevents years with very low EPS (common for growth companies
    before scale) from producing artificially high shadow P/Es that make today's
    multiple look cheap by comparison.
    """
    prior = series[:-1]  # exclude the most recent (current)
    # Take only the most recent HIST_PE_WINDOW years so the median reflects
    # the company at a comparable earnings scale.
    window = prior[-_HIST_PE_WINDOW:] if len(prior) > _HIST_PE_WINDOW else prior
    valid = [Decimal(str(p.value)) for p in window if p.value != UNAVAILABLE]
    return median(valid)


def _latest_valid(series: MetricSeries) -> MaybeDecimal:
    for pt in reversed(series):
        if pt.value != UNAVAILABLE:
            return pt.value
    return UNAVAILABLE


_ClassifyResult = tuple[ValuationHistoryPosition, MaybeDecimal]


def _classify(current: Decimal, hist_median: Decimal) -> _ClassifyResult:
    if hist_median == 0:
        return ValuationHistoryPosition.INSUFFICIENT_DATA, UNAVAILABLE
    try:
        deviation = (current - hist_median) / abs(hist_median)
        if deviation < -_IN_LINE_BAND:
            return ValuationHistoryPosition.CHEAPER, deviation
        if deviation > _IN_LINE_BAND:
            return ValuationHistoryPosition.RICHER, deviation
        return ValuationHistoryPosition.IN_LINE, deviation
    except (InvalidOperation, TypeError):
        return ValuationHistoryPosition.INSUFFICIENT_DATA, UNAVAILABLE


def build_valuation_position(kpis: TickerKPIs, peer_set: PeerSet) -> ValuationPosition:
    """Compare current P/E and P/S against the company's own 5-10 year history.

    Uses the shadow historical_pe series (oldest-first) already computed by the
    metrics layer.  The note field is fixed — valuation position alone ≠ buy/sell.
    """
    hist_pe = kpis.valuation.historical_pe
    current_pe = _latest_valid(kpis.valuation.trailing_pe)

    hist_median_pe: MaybeDecimal = UNAVAILABLE
    deviation_pct: MaybeDecimal = UNAVAILABLE
    position = ValuationHistoryPosition.INSUFFICIENT_DATA

    # Need at least 3 historical points so the median is meaningful.
    if len(hist_pe) >= 3 and current_pe != UNAVAILABLE:
        hist_med = _series_median_excluding_latest(hist_pe)
        if hist_med is not None:
            hist_median_pe = hist_med
            try:
                current_d = Decimal(str(current_pe))
                position, deviation_pct = _classify(current_d, hist_med)
            except (InvalidOperation, TypeError):
                pass

    current_ps = _latest_valid(kpis.valuation.price_to_sales)
    peer_median_ps = peer_set.sector_medians.price_to_sales

    return ValuationPosition(
        position=position,
        current_pe=current_pe,
        historical_median_pe=hist_median_pe,
        deviation_from_median_pct=deviation_pct,
        current_ps=current_ps,
        peer_median_ps=peer_median_ps,
    )
