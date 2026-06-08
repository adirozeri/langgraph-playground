"""Rich terminal rendering for the one-page snapshot."""
from __future__ import annotations

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..decide.models import SoftSignalDirection
from ..peers.models import RelativePosition
from ._format import (
    DASH,
    fmt_num,
    fmt_pct,
    fmt_ratio,
    fmt_val,
    lean_color,
    position_arrow,
    position_color,
    verdict_color,
)
from .models import SnapshotReport

_SIGNAL_ICON = {
    SoftSignalDirection.POSITIVE: ("↑", "green"),
    SoftSignalDirection.NEGATIVE: ("↓", "red"),
    SoftSignalDirection.NEUTRAL: ("→", "yellow"),
    SoftSignalDirection.UNAVAILABLE: (DASH, "dim"),
}


def _pillar_panel(
    name: str,
    score: str,
    verdict: str,
    metrics: dict[str, str],
) -> Panel:
    t = Table.grid(padding=(0, 1))
    t.add_column(style="dim", no_wrap=True)
    t.add_column()

    for kpi, pos_str in metrics.items():
        try:
            pos = RelativePosition(pos_str)
        except ValueError:
            pos = None
        color = position_color(pos)
        arrow = position_arrow(pos)
        t.add_row(kpi.replace("_", " "), Text(arrow, style=color))

    vcolor = verdict_color(verdict)
    header = Text()
    header.append(f"{score}/10  ", style="bold")
    header.append(verdict, style=vcolor)

    return Panel(
        t,
        title=f"[bold]{name.upper()}[/bold]",
        subtitle=header,
        border_style="bright_black",
        padding=(0, 1),
    )


def _metric_row(
    table: Table,
    label: str,
    value: str,
    peer: str,
    pos: RelativePosition | None,
) -> None:
    color = position_color(pos)
    arrow = position_arrow(pos)
    table.add_row(
        label,
        value,
        peer,
        Text(arrow, style=color),
    )


def render_snapshot(report: SnapshotReport, console: Console | None = None) -> None:
    """Render the one-page snapshot to the terminal.

    Layout:
      Header  — ticker + date + lean badge
      Pillars — four pillar panels side by side
      Metrics — key metric table with peer medians and position arrows
      Signals — insider / revisions / buybacks
      Valuation — vs own history
      Caveats — three fixed warnings
    """
    if console is None:
        console = Console()

    d = report.decision
    sc = d.scorecard
    vp = d.valuation_position
    ss = d.soft_signals
    proj = d.projection
    inc = report.income
    mom = report.momentum
    val = report.valuation
    cap = report.capital

    # ── Header ────────────────────────────────────────────────────────────────
    lean_txt = Text()
    lean_txt.append(f" {d.lean.value} ", style=lean_color(d.lean.value))
    lean_txt.append(f"  {d.ticker}", style="bold")
    lean_txt.append(
        f"  composite {sc.composite}/10", style="dim"
    )
    lean_txt.append(
        f"  {report.generated_at.strftime('%Y-%m-%d %H:%M')}", style="dim"
    )
    console.print(Panel(lean_txt, border_style=lean_color(d.lean.value).replace("bold ", "")))

    # ── No-peer notice ────────────────────────────────────────────────────────
    from ..data.models import UNAVAILABLE as _U
    if all(v == _U for v in [
        inc.peer_gross_margin, inc.peer_operating_margin,
        inc.peer_net_margin, inc.peer_fcf_margin,
    ]):
        console.print(
            "[yellow]⚠ No peer group loaded.[/yellow] "
            "Pillar scores default to neutral (5.00/10). "
            "Use [bold]--peers MSFT,GOOGL,META[/bold] for a meaningful comparison."
        )

    # ── Four pillar panels ────────────────────────────────────────────────────
    pillars = [
        _pillar_panel("Income", str(sc.income.score), sc.income.verdict.value,
                      sc.income.key_metrics_vs_peers),
        _pillar_panel("Momentum", str(sc.momentum.score), sc.momentum.verdict.value,
                      sc.momentum.key_metrics_vs_peers),
        _pillar_panel("Valuation", str(sc.valuation.score), sc.valuation.verdict.value,
                      sc.valuation.key_metrics_vs_peers),
        _pillar_panel("Capital", str(sc.capital.score), sc.capital.verdict.value,
                      sc.capital.key_metrics_vs_peers),
    ]
    console.print(Columns(pillars, equal=True, expand=True))

    # ── Key metrics table ─────────────────────────────────────────────────────
    mt = Table(
        "Metric", "Target", "Peer Median", "",
        title="Key Metrics vs Peer Median",
        show_header=True,
        header_style="bold dim",
        border_style="bright_black",
        expand=True,
    )
    mt.columns[1].justify = "right"
    mt.columns[2].justify = "right"
    mt.columns[3].justify = "center"

    cmp = d.scorecard  # comparisons are implicit via peer_set, use dashboard peer medians
    peer = report.income  # peer medians are in each dashboard

    _metric_row(mt, "Revenue (latest)", _latest_val_str(inc.revenue), DASH, None)

    def _cmp_pos(kpi: str):
        try:
            from ..peers.models import RelativePosition as RP
            v = d.scorecard.income.key_metrics_vs_peers.get(
                kpi,
                d.scorecard.momentum.key_metrics_vs_peers.get(
                    kpi,
                    d.scorecard.valuation.key_metrics_vs_peers.get(
                        kpi,
                        d.scorecard.capital.key_metrics_vs_peers.get(kpi),
                    ),
                ),
            )
            return RP(v) if v else None
        except ValueError:
            return None

    _metric_row(mt, "Gross Margin", _latest_pct_str(inc.gross_margin),
                fmt_pct(inc.peer_gross_margin), _cmp_pos("gross_margin"))
    _metric_row(mt, "Operating Margin", _latest_pct_str(inc.operating_margin),
                fmt_pct(inc.peer_operating_margin), _cmp_pos("operating_margin"))
    _metric_row(mt, "Net Margin", _latest_pct_str(inc.net_margin),
                fmt_pct(inc.peer_net_margin), _cmp_pos("net_margin"))
    _metric_row(mt, "FCF Margin", _latest_pct_str(inc.fcf_margin),
                fmt_pct(inc.peer_fcf_margin), _cmp_pos("fcf_margin"))
    _metric_row(mt, "Rev Growth YoY", _latest_pct_str(inc.revenue_growth_yoy),
                fmt_pct(inc.peer_revenue_growth_yoy), _cmp_pos("revenue_growth_yoy"))
    _metric_row(mt, "Trailing P/E", _latest_ratio_str(val.trailing_pe),
                fmt_ratio(val.peer_trailing_pe), _cmp_pos("trailing_pe"))
    _metric_row(mt, "Forward P/E", _latest_ratio_str(val.forward_pe),
                fmt_ratio(val.peer_forward_pe), _cmp_pos("forward_pe"))
    _metric_row(mt, "EV/EBITDA", _latest_ratio_str(val.ev_to_ebitda),
                fmt_ratio(val.peer_ev_to_ebitda), _cmp_pos("ev_to_ebitda"))
    _metric_row(mt, "ROIC", _latest_pct_str(cap.roic),
                fmt_pct(cap.peer_roic), _cmp_pos("roic"))
    _metric_row(mt, "ROE", _latest_pct_str(cap.roe),
                fmt_pct(cap.peer_roe), _cmp_pos("roe"))
    _metric_row(mt, "FCF Yield", _latest_pct_str(cap.fcf_yield),
                fmt_pct(cap.peer_fcf_yield), _cmp_pos("fcf_yield"))
    console.print(mt)

    # ── Valuation position ────────────────────────────────────────────────────
    vt = Table(
        "Valuation vs Own History",
        show_header=False,
        border_style="bright_black",
        expand=True,
    )
    pos_color = {
        "CHEAPER": "green", "IN_LINE": "yellow",
        "RICHER": "red", "INSUFFICIENT_DATA": "dim",
    }.get(vp.position.value, "dim")
    vt.add_row(
        Text(vp.position.value, style=f"bold {pos_color}") +
        Text(
            f"  current P/E {fmt_num(vp.current_pe)}×  "
            f"vs hist. median {fmt_num(vp.historical_median_pe)}×",
            style="dim",
        )
    )
    vt.add_row(Text(vp.note, style="dim italic"))
    console.print(vt)

    # ── Soft signals ──────────────────────────────────────────────────────────
    st = Table(
        "Signal", "Direction", "Detail",
        title="Soft Signals",
        border_style="bright_black",
        expand=True,
    )
    for label, direction, detail in [
        ("Insider activity", ss.insider_activity, ss.insider_detail),
        ("EPS revisions", ss.estimate_revisions, ss.revision_detail),
        ("Buybacks", ss.buyback_activity, ss.buyback_detail),
    ]:
        icon, color = _SIGNAL_ICON.get(direction, (DASH, "dim"))
        st.add_row(label, Text(f"{icon} {direction.value}", style=color), detail)
    if ss.conflict_flag:
        st.add_row(
            Text("⚠ Conflict", style="bold yellow"),
            "",
            ss.conflict_description,
        )
    console.print(st)

    # ── 3-year projection summary ─────────────────────────────────────────────
    bc = proj.base_case
    bull = proj.bull_case
    pt = Table(
        "Case", "Rev CAGR", "EPS CAGR", "Applied P/E", "Implied Price Yr 3",
        title="3-Year Projection",
        border_style="bright_black",
        expand=True,
    )
    pt.columns[1].justify = "right"
    pt.columns[2].justify = "right"
    pt.columns[3].justify = "right"
    pt.columns[4].justify = "right"
    pt.add_row("Base",
               fmt_pct(bc.revenue_cagr), fmt_pct(bc.eps_cagr),
               fmt_num(bc.applied_pe_multiple) + "×",
               fmt_val(bc.implied_price_year_3))
    pt.add_row("Bull",
               fmt_pct(bull.revenue_cagr), fmt_pct(bull.eps_cagr),
               fmt_num(bull.applied_pe_multiple) + "×",
               fmt_val(bull.implied_price_year_3))
    console.print(pt)
    console.print(Text(f"  {proj.methodology_note}", style="dim italic"))

    # ── Justification ─────────────────────────────────────────────────────────
    console.print(Panel(
        Text(d.justification, style="default"),
        title="Rationale",
        border_style="bright_black",
    ))

    # ── Caveats ───────────────────────────────────────────────────────────────
    caveats = [
        d.caveat_quality_not_timing,
        d.caveat_projection_not_guaranteed,
        d.caveat_garbage_in_garbage_out,
    ]
    caveat_text = Text()
    for c in caveats:
        caveat_text.append("⚠ ", style="yellow")
        caveat_text.append(c, style="dim")
        caveat_text.append("\n")
    console.print(Panel(caveat_text, title="Caveats", border_style="yellow"))


# ── Internal helpers ──────────────────────────────────────────────────────────

def _latest_val_str(series) -> str:
    for pt in reversed(series):
        if pt.value != "UNAVAILABLE":
            return fmt_val(pt.value)
    return DASH


def _latest_pct_str(series) -> str:
    for pt in reversed(series):
        if pt.value != "UNAVAILABLE":
            return fmt_pct(pt.value)
    return DASH


def _latest_ratio_str(series) -> str:
    for pt in reversed(series):
        if pt.value != "UNAVAILABLE":
            return fmt_ratio(pt.value)
    return DASH
