from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

from ..dashboards.models import (
    CapitalDashboard,
    IncomeDashboard,
    MomentumDashboard,
    ValuationDashboard,
)
from ..decide.models import InvestmentDecision
from ..interpret.models import Interpretation
from ._group import render_group_ranking, render_group_ranking_md, render_group_report_md
from ._markdown import render_deep_dive_md
from ._pdf import export_pdf
from ._snapshot import render_snapshot as _render_snapshot
from .models import DeepDiveReport, SnapshotReport

__all__ = [
    "DeepDiveReport",
    "SnapshotReport",
    "build_snapshot_report",
    "build_deep_dive_report",
    "render_snapshot",
    "render_deep_dive",
    "render_group_ranking",
    "render_group_ranking_md",
    "render_group_report_md",
    "export_pdf",
]


def build_snapshot_report(
    income: IncomeDashboard,
    momentum: MomentumDashboard,
    valuation: ValuationDashboard,
    capital: CapitalDashboard,
    decision: InvestmentDecision,
) -> SnapshotReport:
    return SnapshotReport(
        ticker=decision.ticker,
        generated_at=datetime.now(tz=timezone.utc),
        income=income,
        momentum=momentum,
        valuation=valuation,
        capital=capital,
        decision=decision,
    )


def build_deep_dive_report(
    income: IncomeDashboard,
    momentum: MomentumDashboard,
    valuation: ValuationDashboard,
    capital: CapitalDashboard,
    interpretation: Interpretation,
    decision: InvestmentDecision,
) -> DeepDiveReport:
    return DeepDiveReport(
        ticker=decision.ticker,
        generated_at=datetime.now(tz=timezone.utc),
        income=income,
        momentum=momentum,
        valuation=valuation,
        capital=capital,
        interpretation=interpretation,
        decision=decision,
    )


def render_snapshot(report: SnapshotReport, console: Console | None = None) -> None:
    """Render the one-page snapshot to the terminal using rich."""
    _render_snapshot(report, console)


def render_deep_dive(
    report: DeepDiveReport,
    *,
    output_dir: Path | str = ".",
    pdf: bool = False,
    console: Console | None = None,
) -> Path:
    """Write the deep-dive Markdown to *output_dir* and optionally convert to PDF.

    Returns the path of the written Markdown file (or PDF if pdf=True and
    conversion succeeded).

    The filename is ``{ticker}_deep_dive_{date}.md``.
    """
    if console is None:
        console = Console()

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    date_str = report.generated_at.strftime("%Y-%m-%d")
    md_path = output_dir / f"{report.ticker}_deep_dive_{date_str}.md"
    md_path.write_text(render_deep_dive_md(report), encoding="utf-8")
    console.print(f"[dim]Markdown written to:[/dim] [bold]{md_path}[/bold]")

    if pdf:
        try:
            pdf_path = export_pdf(md_path)
            console.print(f"[dim]PDF written to:[/dim] [bold]{pdf_path}[/bold]")
            return pdf_path
        except RuntimeError as exc:
            console.print(f"[yellow]PDF export skipped:[/yellow] {exc}")

    return md_path
