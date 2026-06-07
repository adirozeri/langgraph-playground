"""Aggregation: sector medians and per-KPI comparisons for the target ticker."""
from __future__ import annotations

from decimal import Decimal

from ..data.models import UNAVAILABLE
from ..metrics.models import MaybeDecimal, TickerKPIs
from ._extract import KPI_CATALOG, extract_kpi_values
from ._stats import DEFAULT_IN_LINE_BAND, median, percentile_rank, relative_position
from .models import KPIComparison, PeerComparisons, PeerMetrics, RelativePosition, SectorMedian


def _to_decimal(v: MaybeDecimal) -> Decimal | None:
    if v == UNAVAILABLE:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def build_comparisons(
    target_ticker: str,
    target_kpis: TickerKPIs,
    peer_metrics: list[PeerMetrics],
    in_line_band: Decimal = DEFAULT_IN_LINE_BAND,
) -> tuple[SectorMedian, PeerComparisons]:
    """Derive SectorMedian and PeerComparisons from the full peer set.

    Algorithm per KPI:
      1. Extract latest annual value for target and each peer.
      2. Compute peer-only median (target excluded).
      3. Compute target's percentile rank in the combined population.
      4. Classify target as BETTER / WORSE / IN_LINE vs peer median.
    """
    target_values = extract_kpi_values(target_kpis)
    peer_value_maps: dict[str, dict[str, MaybeDecimal]] = {
        pm.ticker: extract_kpi_values(pm.kpis) for pm in peer_metrics
    }

    sector_medians_dict: dict[str, MaybeDecimal] = {}
    comparisons_dict: dict[str, KPIComparison] = {}

    for spec in KPI_CATALOG:
        name = spec.name
        target_raw = target_values[name]
        target_dec = _to_decimal(target_raw)

        # Peer values for this KPI (may include UNAVAILABLE)
        peer_vals: dict[str, MaybeDecimal] = {
            t: vals[name] for t, vals in peer_value_maps.items()
        }

        # Valid peer Decimals (UNAVAILABLE peers silently excluded from stats)
        valid_peer_decs: list[Decimal] = [
            d for d in (_to_decimal(v) for v in peer_vals.values()) if d is not None
        ]

        # Peer-only median
        peer_med_dec = median(valid_peer_decs)
        peer_median: MaybeDecimal = peer_med_dec if peer_med_dec is not None else UNAVAILABLE
        sector_medians_dict[name] = peer_median

        # Combined population (peers + target) for percentile
        combined: list[Decimal] = list(valid_peer_decs)
        if target_dec is not None:
            combined.append(target_dec)

        percentile: Decimal | None = None
        if target_dec is not None and combined:
            percentile = percentile_rank(target_dec, combined)

        # Relative position
        position: RelativePosition | None = None
        if target_dec is not None and peer_med_dec is not None:
            position = relative_position(
                target_dec,
                peer_med_dec,
                higher_is_better=spec.higher_is_better,
                in_line_band=in_line_band,
            )

        comparisons_dict[name] = KPIComparison(
            target_value=target_raw,
            peer_median=peer_median,
            peer_values=peer_vals,
            percentile=percentile,
            position=position,
            higher_is_better=spec.higher_is_better,
        )

    return SectorMedian(**sector_medians_dict), PeerComparisons(**comparisons_dict)
