# Architecture contract: signals read from provider data only — no LLM-generated figures.
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from ..data.models import UNAVAILABLE, RawFinancials
from ..metrics.models import MetricSeries, TickerKPIs
from .models import SoftSignalDirection, SoftSignals


def _latest_valid(series: MetricSeries) -> Decimal | None:
    for pt in reversed(series):
        if pt.value != UNAVAILABLE:
            try:
                return Decimal(str(pt.value))
            except (InvalidOperation, TypeError):
                pass
    return None


# ── Individual signal readers ─────────────────────────────────────────────────

# When corporate buybacks exceed insider selling by this multiple, executive
# sales are treated as routine 10b5-1 diversification, not a bearish signal.
_BUYBACK_MUTE_RATIO = Decimal("20")


def _read_insider(
    raw: RawFinancials,
    annual_buybacks: Decimal | None = None,
) -> tuple[SoftSignalDirection, str]:
    if not raw.insider_transactions:
        return SoftSignalDirection.UNAVAILABLE, "No insider transaction data available."

    buys = [t for t in raw.insider_transactions if t.transaction_type.lower() == "buy"]
    sells = [t for t in raw.insider_transactions if t.transaction_type.lower() == "sell"]

    buy_val = sum((t.value for t in buys if t.value is not None), Decimal("0"))
    sell_val = sum((t.value for t in sells if t.value is not None), Decimal("0"))

    n_buy = len(buys)
    n_sell = len(sells)
    buy_m = buy_val / Decimal("1_000_000")
    sell_m = sell_val / Decimal("1_000_000")
    detail = f"{n_buy} buy(s) (${buy_m:.1f}M) vs {n_sell} sell(s) (${sell_m:.1f}M)"

    if buy_val > sell_val * Decimal("1.5"):
        return SoftSignalDirection.POSITIVE, detail

    if sell_val > buy_val * Decimal("1.5") and sell_val > 0:
        # Mute negative insider signal when corporate buybacks dwarf insider selling.
        # Mega-cap executives routinely liquidate under pre-planned 10b5-1 schedules
        # that have no informational content when the company simultaneously buys
        # back far more stock than insiders sell.
        if (annual_buybacks is not None
                and annual_buybacks > sell_val * _BUYBACK_MUTE_RATIO):
            bb_b = annual_buybacks / Decimal("1_000_000_000")
            detail += (
                f" — muted: corporate buybacks (${bb_b:.1f}B) "
                f"exceed insider selling >{int(_BUYBACK_MUTE_RATIO)}× "
                "(routine 10b5-1 diversification)"
            )
            return SoftSignalDirection.NEUTRAL, detail
        return SoftSignalDirection.NEGATIVE, detail

    return SoftSignalDirection.NEUTRAL, detail


def _read_revisions(raw: RawFinancials) -> tuple[SoftSignalDirection, str]:
    if not raw.earnings_revisions:
        return SoftSignalDirection.UNAVAILABLE, "No earnings revision data available."

    recent = sorted(raw.earnings_revisions, key=lambda r: r.date, reverse=True)[:4]
    beats = [
        r for r in recent
        if r.surprise != UNAVAILABLE and Decimal(str(r.surprise)) > 0
    ]
    misses = [
        r for r in recent
        if r.surprise != UNAVAILABLE and Decimal(str(r.surprise)) < 0
    ]

    if not beats and not misses:
        return SoftSignalDirection.NEUTRAL, "EPS surprise data unavailable in recent quarters."

    detail = (
        f"{len(beats)} positive EPS surprise(s) vs {len(misses)} miss(es) "
        f"over the last {len(recent)} quarter(s)"
    )

    if len(beats) > len(misses) + 1:
        return SoftSignalDirection.POSITIVE, detail
    if len(misses) > len(beats) + 1:
        return SoftSignalDirection.NEGATIVE, detail
    return SoftSignalDirection.NEUTRAL, detail


def _read_buybacks(kpis: TickerKPIs) -> tuple[SoftSignalDirection, str]:
    buybacks = kpis.cash_flow_annual.buybacks
    val = _latest_valid(buybacks)

    if val is None:
        return SoftSignalDirection.UNAVAILABLE, "No buyback data available."

    # Cash flow convention: buybacks appear as negative outflows.
    abs_b = abs(val)
    detail = f"Most recent annual buybacks: ${abs_b / Decimal('1_000_000_000'):.1f}B"

    # Signal is POSITIVE when buybacks are meaningful (>$500M outflow).
    if val < Decimal("-500_000_000"):
        return SoftSignalDirection.POSITIVE, detail
    if val == 0:
        return SoftSignalDirection.NEUTRAL, detail + " (no buybacks)"
    return SoftSignalDirection.NEUTRAL, detail


# ── Conflict detection ────────────────────────────────────────────────────────

def _detect_conflict(
    insider: SoftSignalDirection,
    revisions: SoftSignalDirection,
    buybacks: SoftSignalDirection,
) -> tuple[bool, str]:
    actionable = [
        ("insider", insider),
        ("revisions", revisions),
        ("buybacks", buybacks),
    ]
    actionable = [
        (name, sig) for name, sig in actionable
        if sig not in (SoftSignalDirection.UNAVAILABLE, SoftSignalDirection.NEUTRAL)
    ]

    if len(actionable) < 2:
        return False, ""

    pos = [(n, s) for n, s in actionable if s == SoftSignalDirection.POSITIVE]
    neg = [(n, s) for n, s in actionable if s == SoftSignalDirection.NEGATIVE]

    if pos and neg:
        pos_names = ", ".join(n for n, _ in pos)
        neg_names = ", ".join(n for n, _ in neg)
        return True, (
            f"Conflicting signals: {pos_names} positive vs {neg_names} negative. "
            f"Insider: {insider.value}, Revisions: {revisions.value}, Buybacks: {buybacks.value}."
        )

    return False, ""


# ── Public entry point ────────────────────────────────────────────────────────

def build_soft_signals(raw: RawFinancials, kpis: TickerKPIs) -> SoftSignals:
    # Pass the most recent annual buyback amount so insider reading can be
    # contextualised relative to corporate capital return scale.
    annual_buybacks = _latest_valid(kpis.cash_flow_annual.buybacks)
    buyback_abs: Decimal | None = None
    if annual_buybacks is not None:
        try:
            buyback_abs = abs(Decimal(str(annual_buybacks)))
        except Exception:
            pass

    insider_dir, insider_detail = _read_insider(raw, annual_buybacks=buyback_abs)
    revision_dir, revision_detail = _read_revisions(raw)
    buyback_dir, buyback_detail = _read_buybacks(kpis)

    conflict_flag, conflict_description = _detect_conflict(insider_dir, revision_dir, buyback_dir)

    return SoftSignals(
        insider_activity=insider_dir,
        insider_detail=insider_detail,
        estimate_revisions=revision_dir,
        revision_detail=revision_detail,
        buyback_activity=buyback_dir,
        buyback_detail=buyback_detail,
        conflict_flag=conflict_flag,
        conflict_description=conflict_description,
    )
