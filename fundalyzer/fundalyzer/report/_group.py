from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from rich import box
from rich.console import Console
from rich.table import Table

from ..data.models import UNAVAILABLE
from ..decide.models import InvestmentLean, SoftSignalDirection
from ..group.models import GroupRanking
from ..peers._extract import extract_kpi_values

if TYPE_CHECKING:
    from ..pipeline import AnalysisResult

_FOOTER = (
    "Scores are 0–10, benchmarked within this group. "
    "Lean is rule-derived from composite score only — no soft signals. "
    "Run `fundalyzer analyze TICKER --peers ...` for a full single-stock analysis."
)


def _score_style(score: Decimal) -> str:
    if score >= Decimal("6"):
        return "green"
    if score >= Decimal("4"):
        return "yellow"
    return "red"


_LEAN_STYLE: dict[InvestmentLean, str] = {
    InvestmentLean.INVEST: "bold green",
    InvestmentLean.HOLD: "bold yellow",
    InvestmentLean.AVOID: "bold red",
}


def render_group_ranking(ranking: GroupRanking, *, console: Console | None = None) -> None:
    con = console or Console()

    table = Table(
        title=f"Peer Group Leaderboard — {len(ranking.members)} companies",
        box=box.ROUNDED,
        show_lines=True,
        title_style="bold",
    )
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Ticker", style="bold cyan")
    table.add_column("Composite", justify="right")
    table.add_column("Income", justify="right")
    table.add_column("Momentum", justify="right")
    table.add_column("Valuation", justify="right")
    table.add_column("Capital", justify="right")
    table.add_column("Lean", justify="center")

    for m in ranking.members:
        table.add_row(
            str(m.rank),
            m.ticker,
            f"[{_score_style(m.composite)}]{m.composite:.2f}[/]",
            f"[{_score_style(m.income)}]{m.income:.2f}[/]",
            f"[{_score_style(m.momentum)}]{m.momentum:.2f}[/]",
            f"[{_score_style(m.valuation)}]{m.valuation:.2f}[/]",
            f"[{_score_style(m.capital)}]{m.capital:.2f}[/]",
            f"[{_LEAN_STYLE[m.lean]}]{m.lean.value}[/]",
        )

    con.print()
    con.print(table)
    con.print(f"\n[dim]{_FOOTER}[/dim]")


# ── KPI display spec for the comparison table ─────────────────────────────────
# (name, label, format: "pct" | "mult" | "ratio")
_COMPARISON_KPIS: list[tuple[str, str, str]] = [
    ("revenue_growth_yoy", "Revenue Growth",   "pct"),
    ("gross_margin",       "Gross Margin",      "pct"),
    ("operating_margin",   "Operating Margin",  "pct"),
    ("net_margin",         "Net Margin",        "pct"),
    ("fcf_margin",         "FCF Margin",        "pct"),
    ("trailing_pe",        "Trailing P/E",      "mult"),
    ("ev_to_ebitda",       "EV/EBITDA",         "mult"),
    ("roic",               "ROIC",              "pct"),
    ("roe",                "ROE",               "pct"),
    ("fcf_yield",          "FCF Yield",         "pct"),
    ("debt_to_equity",     "Debt/Equity",       "ratio"),
]

_SIGNAL_ARROW = {
    SoftSignalDirection.POSITIVE:    "↑",
    SoftSignalDirection.NEGATIVE:    "↓",
    SoftSignalDirection.NEUTRAL:     "→",
    SoftSignalDirection.UNAVAILABLE: "—",
}


def _fmt_kpi(value: object, fmt: str) -> str:
    if value == UNAVAILABLE or value is None:
        return "—"
    d = Decimal(str(value))
    if fmt == "pct":
        return f"{d * 100:.1f}%"
    if fmt in ("mult", "ratio"):
        return f"{d:.2f}×"
    return str(d)


def render_group_report_md(
    results: list[AnalysisResult],
    ranking: GroupRanking,
    group_name: str,
) -> str:
    today = date.today().isoformat()
    tickers_by_rank = [m.ticker for m in ranking.members]
    results_by_ticker = {r.ticker: r for r in results}

    # Only include tickers that successfully completed analysis
    ordered = [(m, results_by_ticker[m.ticker]) for m in ranking.members if m.ticker in results_by_ticker]

    lines: list[str] = [
        f"# Peer Group Analysis — {group_name}",
        "",
        f"_Generated {today} · {len(ordered)} companies · each member benchmarked against the rest_",
        "",
        "> **Architecture contract:** Every number in this report originates from a real"
        " financial data API and was computed deterministically in Python."
        " The LLM produced narrative text only.",
        "",
        "---",
        "",
        "## Leaderboard",
        "",
        "| # | Ticker | Composite | Income | Momentum | Valuation | Capital | Lean |",
        "|---|--------|-----------|--------|----------|-----------|---------|------|",
    ]
    for m, _ in ordered:
        lines.append(
            f"| {m.rank} | {m.ticker} | {m.composite:.2f} | {m.income:.2f}"
            f" | {m.momentum:.2f} | {m.valuation:.2f} | {m.capital:.2f} | {m.lean.value} |"
        )
    lines += ["", "---", "", "## Key Metrics Comparison", ""]

    # Header row: Metric | TICKER1 | TICKER2 | ...
    header_tickers = [t for t in tickers_by_rank if t in results_by_ticker]
    lines.append("| Metric | " + " | ".join(header_tickers) + " |")
    lines.append("|--------|" + "|".join("--------" for _ in header_tickers) + "|")

    for kpi_name, label, fmt in _COMPARISON_KPIS:
        row_vals = []
        for ticker in header_tickers:
            kpi_vals = extract_kpi_values(results_by_ticker[ticker].kpis)
            row_vals.append(_fmt_kpi(kpi_vals.get(kpi_name, UNAVAILABLE), fmt))
        lines.append(f"| {label} | " + " | ".join(row_vals) + " |")

    lines += ["", "---", "", "## Company Summaries", ""]

    for m, result in ordered:
        dec = result.decision
        sc = dec.scorecard
        vp = dec.valuation_position
        ss = dec.soft_signals

        lines += [
            f"### #{m.rank} {m.ticker} — {dec.lean.value} · {sc.composite:.2f}/10",
            "",
            "**Scorecard**",
            "",
            "| Pillar | Score | Verdict |",
            "|--------|-------|---------|",
            f"| Income | {sc.income.score:.2f}/10 | {sc.income.verdict.value} |",
            f"| Momentum | {sc.momentum.score:.2f}/10 | {sc.momentum.verdict.value} |",
            f"| Valuation | {sc.valuation.score:.2f}/10 | {sc.valuation.verdict.value} |",
            f"| Capital | {sc.capital.score:.2f}/10 | {sc.capital.verdict.value} |",
            "",
        ]

        # Valuation vs own history
        pe_curr = _fmt_kpi(vp.current_pe, "mult")
        pe_hist = _fmt_kpi(vp.historical_median_pe, "mult")
        lines += [
            f"**Valuation vs Own History:** {vp.position.value} "
            f"(current P/E {pe_curr} · hist. median {pe_hist})",
            "",
        ]

        # Soft signals
        lines += [
            "**Soft Signals**",
            "",
            "| Signal | Direction | Detail |",
            "|--------|-----------|--------|",
            f"| Insider Activity | {_SIGNAL_ARROW[ss.insider_activity]} {ss.insider_activity.value} | {ss.insider_detail} |",
            f"| EPS Revisions | {_SIGNAL_ARROW[ss.estimate_revisions]} {ss.estimate_revisions.value} | {ss.revision_detail} |",
            f"| Buybacks | {_SIGNAL_ARROW[ss.buyback_activity]} {ss.buyback_activity.value} | {ss.buyback_detail} |",
            "",
        ]
        if ss.conflict_flag:
            lines += [f"> ⚠ **Signal conflict:** {ss.conflict_description}", ""]

        lines += ["**Rationale**", "", dec.justification, "", "---", ""]

    lines += [
        "_Scores are 0–10, benchmarked within this group._",
        "_Lean per company includes soft signals; lean in the leaderboard is composite-only._",
        "",
    ]
    return "\n".join(lines)


def render_group_ranking_md(ranking: GroupRanking, group_name: str) -> str:
    today = date.today().isoformat()
    lines: list[str] = [
        f"# Peer Group Leaderboard — {group_name}",
        "",
        f"_Generated {today} · {len(ranking.members)} companies · scores benchmarked within group_",
        "",
        "| # | Ticker | Composite | Income | Momentum | Valuation | Capital | Lean |",
        "|---|--------|-----------|--------|----------|-----------|---------|------|",
    ]
    for m in ranking.members:
        lines.append(
            f"| {m.rank} | {m.ticker} | {m.composite:.2f} | {m.income:.2f} "
            f"| {m.momentum:.2f} | {m.valuation:.2f} | {m.capital:.2f} | {m.lean.value} |"
        )
    lines += ["", f"> {_FOOTER}", ""]
    return "\n".join(lines)
