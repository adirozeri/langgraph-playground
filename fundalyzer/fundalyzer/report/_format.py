"""Shared formatting helpers for terminal and Markdown renderers."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from ..data.models import UNAVAILABLE
from ..metrics.models import MaybeDecimal
from ..peers.models import RelativePosition

DASH = "—"


def fmt_val(v: MaybeDecimal, *, pct: bool = False, ratio: bool = False) -> str:
    """Format a MaybeDecimal for display.

    pct=True  → multiply by 100 and append '%'
    ratio=True → show as X.Xx
    default   → abbreviated dollar amount ($1.2B, $345M)
    """
    if v == UNAVAILABLE or v is None:
        return DASH
    try:
        d = Decimal(str(v))
        if pct:
            return f"{d * 100:.1f}%"
        if ratio:
            return f"{d:.2f}×"
        abs_d = abs(d)
        sign = "-" if d < 0 else ""
        if abs_d >= Decimal("1_000_000_000"):
            return f"{sign}${abs_d / Decimal('1_000_000_000'):.1f}B"
        if abs_d >= Decimal("1_000_000"):
            return f"{sign}${abs_d / Decimal('1_000_000'):.0f}M"
        if abs_d >= Decimal("1_000"):
            return f"{sign}${abs_d / Decimal('1_000'):.1f}K"
        return f"{sign}${abs_d:.2f}"
    except (InvalidOperation, TypeError):
        return DASH


def fmt_pct(v: MaybeDecimal) -> str:
    return fmt_val(v, pct=True)


def fmt_ratio(v: MaybeDecimal) -> str:
    return fmt_val(v, ratio=True)


def fmt_num(v: MaybeDecimal, decimals: int = 2) -> str:
    """Plain number, no units."""
    if v == UNAVAILABLE or v is None:
        return DASH
    try:
        return f"{Decimal(str(v)):.{decimals}f}"
    except (InvalidOperation, TypeError):
        return DASH


def position_color(pos: RelativePosition | None) -> str:
    """Rich markup color for a relative position."""
    if pos is None:
        return "dim"
    return {"BETTER": "green", "WORSE": "red", "IN_LINE": "yellow"}.get(pos.value, "dim")


def position_arrow(pos: RelativePosition | None) -> str:
    if pos is None:
        return " "
    return {"BETTER": "↑", "WORSE": "↓", "IN_LINE": "→"}.get(pos.value, " ")


def lean_color(lean: str) -> str:
    return {"INVEST": "bold green", "HOLD": "bold yellow", "AVOID": "bold red"}.get(lean, "white")


def verdict_color(verdict: str) -> str:
    mapping = {
        "STRONG": "bright_green",
        "ABOVE_PEER": "green",
        "IN_LINE": "yellow",
        "BELOW_PEER": "red",
        "WEAK": "bright_red",
    }
    return mapping.get(verdict, "white")
