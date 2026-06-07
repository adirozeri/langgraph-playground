import typer
from rich.console import Console

app = typer.Typer(
    name="fundalyzer",
    help="Fundamental analysis pipeline — all numbers from API, LLM interprets only.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def analyze(
    ticker: str = typer.Argument(..., help="Stock ticker symbol, e.g. AAPL"),
    years: int = typer.Option(5, "--years", "-y", help="Years of historical data to fetch"),
    output: str = typer.Option("rich", "--output", "-o", help="Output format: rich | json"),
) -> None:
    """Run the full fundamental analysis pipeline and emit a deep-dive report."""
    console.print(f"[bold]fundalyzer[/bold] · analyzing [cyan]{ticker.upper()}[/cyan] …")
    raise NotImplementedError("Pipeline not yet implemented")


@app.command()
def snapshot(
    ticker: str = typer.Argument(..., help="Stock ticker symbol"),
) -> None:
    """Emit a one-page snapshot for quick review."""
    console.print(f"[bold]fundalyzer[/bold] · snapshot [cyan]{ticker.upper()}[/cyan] …")
    raise NotImplementedError("Snapshot not yet implemented")


if __name__ == "__main__":
    app()
