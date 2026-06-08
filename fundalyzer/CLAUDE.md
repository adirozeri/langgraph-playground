# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (editable + dev deps)
make install          # pip install -e ".[dev]"

# Test
make test             # pytest -v
pytest tests/test_metrics.py          # single file
pytest tests/test_metrics.py::TestProfitabilityAnnual  # single class
pytest -k "test_gross_margin"         # by name pattern

# Lint
make lint             # ruff check . && ruff format --check .
ruff check . --fix    # auto-fix
ruff format .         # auto-format

# CLI (once installed)
fundalyzer analyze AAPL
fundalyzer snapshot AAPL
```

## Architecture contract

The hardest rule — enforced everywhere:

> **ALL numeric values originate from a real financial data API and are computed deterministically in Python. The LLM is only ever used to interpret numbers it is given. The LLM must never generate or invent a figure that appears in output.**

The string sentinel `UNAVAILABLE: Literal["UNAVAILABLE"]` (defined in `data/models.py`) marks fields that no provider returned. Never substitute `0` or `None` for missing data.

## Pipeline layers

Data flows strictly downward; no layer imports from a layer above it.

```
data  →  metrics  →  peers  →  dashboards  →  interpret  →  decide  →  report
```

| Layer | Entry point | What it does |
|---|---|---|
| `data` | `CompositeProvider.get_raw_financials(ticker)` | Fetches FMP (primary) + yfinance (fallback), merges, disk-caches by ticker+date |
| `metrics` | `metrics.compute(raw)` | Pure-Python KPI computation; returns `TickerKPIs` with `MetricSeries` per pillar |
| `peers` | `peers.build(target, provider, peers)` | Runs data+metrics for each peer; computes sector medians and per-KPI comparisons |
| `dashboards` | `dashboards.build(kpis, peer_set)` | Assembles four typed dashboard objects — no computation, no LLM |
| `interpret` | `interpret.interpret(income, momentum, valuation, capital)` | One tool-use Claude call per dashboard + one synthesis call |
| `decide` | stub | Investment lean from scorecard |
| `report` | stub | Rich terminal rendering |

## Key types

- **`MaybeDecimal`** (`Decimal | Literal["UNAVAILABLE"]`) — every numeric field in schemas is this type.
- **`MetricSeries`** (`list[MetricPoint]`) — **oldest-first**. `series[-1]` is most recent. Each `MetricPoint` carries `.value`, `.formula`, and `.inputs` for full auditability.
- **`TrendResult`** — OLS slope normalised by `|mean|`; `Trend` enum: `ACCELERATING | FLAT | DECELERATING | INSUFFICIENT_DATA`.
- **`KPIComparison`** — target value, peer-only median, percentile (0-100), `RelativePosition` (`BETTER | WORSE | IN_LINE`).

## Data layer specifics

- `FinancialDataProvider` ABC (`data/base.py`) — subclass and implement `get_raw_financials()` to add a provider; optionally override `get_peer_tickers()`.
- `FMPProvider` uses v3 for financials, v4 (`/stock_peers`) for peer lists.
- `DiskCache` stores JSON at `~/.cache/fundalyzer/{ticker}/{date}/{endpoint}.json`; one entry per calendar day.
- Use `NullCache` in tests to bypass disk I/O.
- Fixture responses for tests live in `tests/fixtures/fmp/` as JSON; tests patch `FMPProvider._get` to return them — no live API calls.

## Metrics layer specifics

- `metrics/compute.py` orchestrates all pillars; sorts statements **oldest-first** before passing to submodules (FMP returns newest-first).
- Private modules `_profitability`, `_valuation`, `_cashflow`, `_strength` each return one KPI pillar.
- `_helpers.py`: `ratio()`, `yoy()`, `passthrough()` — all return `MetricPoint` with UNAVAILABLE propagation baked in.
- `classify_trend(series)` in `metrics/_trend.py` takes an oldest-first `MetricSeries`.

## Peers layer specifics

- `KPI_CATALOG` in `peers/_extract.py` is the single source of truth for which 17 KPIs enter peer comparison. Adding a KPI here automatically propagates to `SectorMedian` and `PeerComparisons`, but you must also add the field to those pydantic models.
- Peer-only median excludes the target (no self-referential benchmark).
- `DEFAULT_IN_LINE_BAND = 5%` of the peer median.

## Interpret layer specifics

- `_client.py` exposes `call_with_tool()` (forces `tool_choice` for structured JSON) and `call_text()` (synthesis). Inject `messages_api` for testing — the parameter accepts anything with a `.create()` method.
- `SYSTEM_PROMPT` and all four prompt builders are in `_prompts.py`; serialisers (dashboard → human-readable dict) in `_serialise.py`.
- Forbidden response words: "good stock", "strong company", "bullish", "bearish". Allowed `trend_verdict` values: `IMPROVING | DETERIORATING | STABLE | MIXED`.

## Settings

`fundalyzer/settings.py` reads from `.env` via pydantic-settings:
```
FMP_API_KEY=...
ANTHROPIC_API_KEY=...
```
Copy `.env.example` to `.env` to get started.
