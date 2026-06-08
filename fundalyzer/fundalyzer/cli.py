"""fundalyzer CLI — fundamental analysis pipeline.

All numbers originate from a real financial data API and are computed in
Python.  The LLM is invoked only for narrative text.

Examples
--------
  fundalyzer analyze AAPL
  fundalyzer analyze AAPL --peers MSFT,GOOGL --years 10 --format snapshot
  fundalyzer analyze AAPL --dry-run --format json
  fundalyzer analyze AAPL --format deep-dive --output-dir ./reports --pdf
  fundalyzer analyze AAPL --log-level debug --log-format json
"""
from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ._logging import configure_logging
from .config import load_config
from .data.cache import DiskCache, ReadonlyCache
from .data.composite import CompositeProvider
from .data.errors import NoCachedDataError, ProviderUnavailableError
from .data.fmp import FMPProvider
from .data.yfinance_provider import YFinanceProvider
from .group import rank_group
from .peers._aggregator import build_comparisons
from .peers.build import build as build_peer_set
from .peers.models import PeerMetrics, PeerSet
from .pipeline import run_analysis
from .report import render_deep_dive, render_group_ranking, render_group_ranking_md, render_group_report_md, render_snapshot
from .settings import settings

log = logging.getLogger(__name__)

app = typer.Typer(
    name="fundalyzer",
    help="Fundamental analysis pipeline — all numbers from API, LLM interprets only.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()


class OutputFormat(str, Enum):
    snapshot = "snapshot"
    deep_dive = "deep-dive"
    json = "json"


class LogLevel(str, Enum):
    debug = "debug"
    info = "info"
    warning = "warning"
    error = "error"


class LogFormat(str, Enum):
    text = "text"
    json = "json"


@app.command()
def analyze(
    ticker: str = typer.Argument(..., help="Stock ticker symbol, e.g. AAPL"),
    peers: Optional[str] = typer.Option(
        None, "--peers", "-p",
        help="Comma-separated peer tickers, e.g. MSFT,GOOGL. "
             "Omit to use config file defaults or provider-derived peers.",
    ),
    years: Optional[int] = typer.Option(
        None, "--years", "-y",
        help="Years of annual history to fetch.  Default: config file or 5.",
    ),
    fmt: OutputFormat = typer.Option(
        OutputFormat.snapshot, "--format", "-f",
        help="Output format: snapshot (terminal) | deep-dive (Markdown) | json.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Use only cached data — no live API calls.  Fails if data is not cached.",
    ),
    output_dir: Path = typer.Option(
        Path("."), "--output-dir", "-o",
        help="Directory for deep-dive Markdown / PDF output.",
    ),
    pdf: bool = typer.Option(
        False, "--pdf",
        help="Export deep-dive to PDF (requires pandoc).  Only with --format deep-dive.",
    ),
    config_path: Optional[Path] = typer.Option(
        None, "--config",
        help="Path to fundalyzer.toml.  Default: ./fundalyzer.toml or ~/.config/fundalyzer/config.toml.",
    ),
    log_level: LogLevel = typer.Option(
        LogLevel.warning, "--log-level",
        help="Logging verbosity.",
    ),
    log_fmt: LogFormat = typer.Option(
        LogFormat.text, "--log-format",
        help="Log output format: text | json.",
    ),
) -> None:
    """Run the full fundamental analysis pipeline on TICKER.

    Layers: data → metrics → peers → dashboards → interpret → decide → report.
    """
    configure_logging(level=log_level.value, fmt=log_fmt.value)

    # ── API key checks ────────────────────────────────────────────────────────
    if not settings.anthropic_api_key:
        console.print(
            "[red]Error:[/red] ANTHROPIC_API_KEY is not set.\n"
            "Copy [bold].env.example[/bold] to [bold].env[/bold] and add your key:\n"
            "  ANTHROPIC_API_KEY=sk-ant-..."
        )
        raise typer.Exit(1)

    # ── Config ────────────────────────────────────────────────────────────────
    cfg = load_config(config_path)
    annual_years = years if years is not None else cfg.default_years

    # ── Peer list ─────────────────────────────────────────────────────────────
    peer_list: list[str] | None = None
    if peers:
        peer_list = [p.strip().upper() for p in peers.split(",") if p.strip()]
    elif cfg.peers_for(ticker):
        peer_list = cfg.peers_for(ticker)
        log.info("Using config-file peers for %s: %s", ticker, peer_list)

    # ── Provider ──────────────────────────────────────────────────────────────
    disk_cache = DiskCache()
    cache = ReadonlyCache(disk_cache) if dry_run else disk_cache

    if not settings.fmp_api_key and not dry_run:
        console.print(
            "[yellow]Warning:[/yellow] FMP_API_KEY is not set. "
            "Data quality will be limited to yfinance only.\n"
            "Copy .env.example to .env and add your key."
        )

    yf = YFinanceProvider(cache=cache)
    if settings.fmp_api_key:
        fmp = FMPProvider(api_key=settings.fmp_api_key, cache=cache)
        provider = CompositeProvider(fmp=fmp, yf=yf, cache=cache)
    else:
        # No FMP key — yfinance only (limited data, no analyst estimates)
        provider = yf

    # ── Run pipeline ──────────────────────────────────────────────────────────
    ticker = ticker.upper()
    console.print(
        f"[bold]fundalyzer[/bold] · analyzing [cyan]{ticker}[/cyan] "
        f"· {annual_years}yr · peers: {peer_list or 'auto'} "
        f"{'[dim](dry-run)[/dim]' if dry_run else ''}"
    )

    try:
        result = run_analysis(
            ticker,
            provider,
            peers=peer_list,
            annual_years=annual_years,
        )
    except NoCachedDataError as exc:
        console.print(f"[red]Dry-run error:[/red] {exc}")
        raise typer.Exit(1) from exc
    except ProviderUnavailableError as exc:
        console.print(
            f"[red]Provider error:[/red] {exc}\n"
            "Check your network connection and API key.  "
            "Use [bold]--dry-run[/bold] to work from cached data."
        )
        raise typer.Exit(1) from exc
    except Exception as exc:
        log.exception("Unexpected pipeline failure for %s", ticker)
        console.print(f"[red]Pipeline error:[/red] {exc}")
        raise typer.Exit(1) from exc

    # ── Output ────────────────────────────────────────────────────────────────
    if fmt == OutputFormat.snapshot:
        render_snapshot(result.snapshot, console=console)

    elif fmt == OutputFormat.deep_dive:
        path = render_deep_dive(
            result.deep_dive, output_dir=output_dir, pdf=pdf, console=console
        )
        console.print(f"\n[green]✓[/green] Deep dive written to [bold]{path}[/bold]")

    elif fmt == OutputFormat.json:
        console.print_json(
            result.decision.model_dump_json(indent=2)
        )


@app.command()
def snapshot(
    ticker: str = typer.Argument(..., help="Stock ticker symbol, e.g. AAPL"),
    peers: Optional[str] = typer.Option(
        None, "--peers", "-p", help="Comma-separated peer tickers.",
    ),
    years: Optional[int] = typer.Option(
        None, "--years", "-y", help="Years of annual history to fetch.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run"),
    config_path: Optional[Path] = typer.Option(None, "--config"),
    log_level: LogLevel = typer.Option(LogLevel.warning, "--log-level"),
    log_fmt: LogFormat = typer.Option(LogFormat.text, "--log-format"),
) -> None:
    """Shorthand for [bold]analyze --format snapshot[/bold]."""
    # Delegate to analyze with snapshot format pinned
    ctx = typer.get_current_context()
    ctx.invoke(
        analyze,
        ticker=ticker,
        peers=peers,
        years=years,
        fmt=OutputFormat.snapshot,
        dry_run=dry_run,
        output_dir=Path("."),
        pdf=False,
        config_path=config_path,
        log_level=log_level,
        log_fmt=log_fmt,
    )


class RankFormat(str, Enum):
    table = "table"
    markdown = "markdown"


class GroupAnalyzeFormat(str, Enum):
    per_company = "per-company"   # one deep-dive file per ticker (original behaviour)
    group_report = "group-report" # single consolidated report for the whole group


@app.command()
def rank(
    group: str = typer.Argument(
        ...,
        help="Named group from config [groups] section (e.g. big_tech) "
             "or a comma-separated ticker list (e.g. AAPL,MSFT,GOOGL,META).",
    ),
    years: Optional[int] = typer.Option(
        None, "--years", "-y",
        help="Years of annual history to fetch.",
    ),
    fmt: RankFormat = typer.Option(
        RankFormat.table, "--format", "-f",
        help="Output format: table (rich terminal) | markdown (write .md file).",
    ),
    output_dir: Path = typer.Option(
        Path("."), "--output-dir", "-o",
        help="Directory for the Markdown file.  Only used with --format markdown.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run"),
    config_path: Optional[Path] = typer.Option(None, "--config"),
    log_level: LogLevel = typer.Option(LogLevel.warning, "--log-level"),
    log_fmt: LogFormat = typer.Option(LogFormat.text, "--log-format"),
) -> None:
    """Rank all companies in a peer group by fundamental quality.

    Scores every member against the rest — no LLM calls, no API key required.
    To do a full analysis on the top-ranked company, run:
      fundalyzer analyze TICKER --peers ...
    """
    configure_logging(level=log_level.value, fmt=log_fmt.value)

    cfg = load_config(config_path)
    annual_years = years if years is not None else cfg.default_years

    # Resolve the group: named config group takes priority, else parse as CSV tickers.
    group_tickers = cfg.group(group)
    group_name = group
    if group_tickers is None:
        group_tickers = [t.strip().upper() for t in group.split(",") if t.strip()]
        if len(group_tickers) < 2:
            console.print(
                f"[red]Error:[/red] '{group}' is not a named group in config and is not a "
                "comma-separated ticker list.  Provide at least 2 tickers, e.g. AAPL,MSFT,GOOGL."
            )
            raise typer.Exit(1)

    seed = group_tickers[0]
    rest = group_tickers[1:]

    # Provider (same setup as analyze; no Anthropic key needed for rank).
    disk_cache = DiskCache()
    cache = ReadonlyCache(disk_cache) if dry_run else disk_cache
    yf = YFinanceProvider(cache=cache)
    if settings.fmp_api_key:
        fmp = FMPProvider(api_key=settings.fmp_api_key, cache=cache)
        provider = CompositeProvider(fmp=fmp, yf=yf, cache=cache)
    else:
        if not dry_run:
            console.print(
                "[yellow]Warning:[/yellow] FMP_API_KEY is not set. "
                "Using yfinance only — analyst estimates and price targets will be unavailable."
            )
        provider = yf

    console.print(
        f"[bold]fundalyzer[/bold] · ranking [cyan]{group_name}[/cyan] "
        f"· {len(group_tickers)} companies · {annual_years}yr "
        f"{'[dim](dry-run)[/dim]' if dry_run else ''}"
    )

    try:
        peer_set = build_peer_set(
            seed, provider, peers=rest, annual_years=annual_years,
        )
    except NoCachedDataError as exc:
        console.print(f"[red]Dry-run error:[/red] {exc}")
        raise typer.Exit(1) from exc
    except ProviderUnavailableError as exc:
        console.print(
            f"[red]Provider error:[/red] {exc}\n"
            "Check your network connection and API key.  "
            "Use [bold]--dry-run[/bold] to work from cached data."
        )
        raise typer.Exit(1) from exc
    except Exception as exc:
        log.exception("Unexpected failure ranking group %s", group_name)
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc

    ranking = rank_group(peer_set)

    if fmt == RankFormat.markdown:
        output_dir.mkdir(parents=True, exist_ok=True)
        from datetime import date
        filename = f"{group_name.replace(',', '_')}_leaderboard_{date.today().isoformat()}.md"
        path = output_dir / filename
        path.write_text(render_group_ranking_md(ranking, group_name), encoding="utf-8")
        console.print(f"\n[green]✓[/green] Leaderboard written to [bold]{path}[/bold]")
    else:
        render_group_ranking(ranking, console=console)


@app.command(name="analyze-group")
def analyze_group(
    group: str = typer.Argument(
        ...,
        help="Named group from config [groups] section (e.g. big_tech) "
             "or a comma-separated ticker list (e.g. AAPL,MSFT,GOOGL,META).",
    ),
    years: Optional[int] = typer.Option(None, "--years", "-y"),
    fmt: GroupAnalyzeFormat = typer.Option(
        GroupAnalyzeFormat.group_report, "--format", "-f",
        help="group-report: one consolidated Markdown for the whole group (default). "
             "per-company: one deep-dive Markdown per ticker.",
    ),
    output_dir: Path = typer.Option(
        Path("."), "--output-dir", "-o",
        help="Directory for output files.",
    ),
    pdf: bool = typer.Option(False, "--pdf", help="Export to PDF (per-company only)."),
    dry_run: bool = typer.Option(False, "--dry-run"),
    config_path: Optional[Path] = typer.Option(None, "--config"),
    log_level: LogLevel = typer.Option(LogLevel.warning, "--log-level"),
    log_fmt: LogFormat = typer.Option(LogFormat.text, "--log-format"),
) -> None:
    """Run the full analysis pipeline for every company in a peer group.

    Data is fetched once and reused across all members — no redundant API calls.
    Each member is scored against every other member of the group.

    Default (--format group-report) writes one consolidated Markdown with a
    leaderboard, side-by-side KPI comparison, and a summary per company.
    Use --format per-company for one deep-dive file per ticker instead.
    """
    configure_logging(level=log_level.value, fmt=log_fmt.value)

    if not settings.anthropic_api_key:
        console.print(
            "[red]Error:[/red] ANTHROPIC_API_KEY is not set.\n"
            "Copy [bold].env.example[/bold] to [bold].env[/bold] and add your key."
        )
        raise typer.Exit(1)

    cfg = load_config(config_path)
    annual_years = years if years is not None else cfg.default_years

    group_tickers = cfg.group(group)
    group_name = group
    if group_tickers is None:
        group_tickers = [t.strip().upper() for t in group.split(",") if t.strip()]
        if len(group_tickers) < 2:
            console.print(
                f"[red]Error:[/red] '{group}' is not a named group in config and is not a "
                "comma-separated ticker list.  Provide at least 2 tickers."
            )
            raise typer.Exit(1)

    seed, rest = group_tickers[0], group_tickers[1:]

    disk_cache = DiskCache()
    cache = ReadonlyCache(disk_cache) if dry_run else disk_cache
    yf = YFinanceProvider(cache=cache)
    if settings.fmp_api_key:
        fmp = FMPProvider(api_key=settings.fmp_api_key, cache=cache)
        provider = CompositeProvider(fmp=fmp, yf=yf, cache=cache)
    else:
        if not dry_run:
            console.print(
                "[yellow]Warning:[/yellow] FMP_API_KEY is not set. "
                "Using yfinance only."
            )
        provider = yf

    console.print(
        f"[bold]fundalyzer[/bold] · analyzing group [cyan]{group_name}[/cyan] "
        f"· {len(group_tickers)} companies · {annual_years}yr "
        f"{'[dim](dry-run)[/dim]' if dry_run else ''}"
    )

    # ── Fetch all data once ───────────────────────────────────────────────────
    try:
        base_peer_set = build_peer_set(seed, provider, peers=rest, annual_years=annual_years)
    except NoCachedDataError as exc:
        console.print(f"[red]Dry-run error:[/red] {exc}")
        raise typer.Exit(1) from exc
    except ProviderUnavailableError as exc:
        console.print(f"[red]Provider error:[/red] {exc}")
        raise typer.Exit(1) from exc
    except Exception as exc:
        log.exception("Failed to fetch group data for %s", group_name)
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc

    all_members = [
        PeerMetrics(ticker=base_peer_set.target, kpis=base_peer_set.target_kpis),
        *base_peer_set.peers,
    ]
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Run full pipeline for each member ─────────────────────────────────────
    completed_results: list = []
    for i, member in enumerate(all_members, 1):
        others = [m for m in all_members if m.ticker != member.ticker]
        sm, comparisons = build_comparisons(member.ticker, member.kpis, others)
        member_peer_set = PeerSet(
            target=member.ticker,
            target_kpis=member.kpis,
            peers=others,
            sector_medians=sm,
            comparisons=comparisons,
        )

        console.print(
            f"\n[dim][{i}/{len(all_members)}][/dim] "
            f"Analyzing [cyan]{member.ticker}[/cyan] …"
        )
        try:
            result = run_analysis(
                member.ticker,
                provider,
                annual_years=annual_years,
                peer_set=member_peer_set,
            )
            completed_results.append(result)
        except Exception as exc:
            log.warning("Analysis failed for %s: %s", member.ticker, exc)
            console.print(f"  [yellow]Skipped {member.ticker}:[/yellow] {exc}")
            continue

        if fmt == GroupAnalyzeFormat.per_company:
            path = render_deep_dive(result.deep_dive, output_dir=output_dir, pdf=pdf, console=console)
            console.print(f"  [green]✓[/green] {member.ticker} → [bold]{path.name}[/bold]")

    # ── Write consolidated report ─────────────────────────────────────────────
    if fmt == GroupAnalyzeFormat.group_report and completed_results:
        from datetime import date as _date
        ranking = rank_group(base_peer_set)
        filename = f"{group_name.replace(',', '_')}_group_report_{_date.today().isoformat()}.md"
        path = output_dir / filename
        path.write_text(render_group_report_md(completed_results, ranking, group_name), encoding="utf-8")
        console.print(f"\n[green]✓[/green] Group report written to [bold]{path}[/bold]")

    console.print(f"\n[bold green]Done.[/bold green] Analyzed {len(completed_results)}/{len(all_members)} companies in {group_name}.")


if __name__ == "__main__":
    app()
