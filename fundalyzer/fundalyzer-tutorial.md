# Fundalyzer — User Guide

## Table of Contents

1. [What is Fundalyzer?](#what-is-fundalyzer)
2. [What Fundalyzer is NOT](#what-fundalyzer-is-not)
3. [Installation & Setup](#installation--setup)
4. [Configuration](#configuration)
5. [Running Your First Analysis](#running-your-first-analysis)
6. [Commands Reference](#commands-reference)
7. [Peer Group Leaderboard (rank)](#peer-group-leaderboard-rank)
8. [Full Group Analysis (analyze-group)](#full-group-analysis-analyze-group)
9. [Reading the Snapshot Output](#reading-the-snapshot-output)
10. [Reading the Deep-Dive Report](#reading-the-deep-dive-report)
11. [Understanding the Scores](#understanding-the-scores)
12. [Peer Comparisons — Why They Matter](#peer-comparisons--why-they-matter)
13. [Data Providers](#data-providers)
14. [Advanced Usage](#advanced-usage)
15. [Config File](#config-file)
16. [Dry-Run Mode](#dry-run-mode)
17. [Troubleshooting](#troubleshooting)
18. [Architectural Contract](#architectural-contract)

---

## What is Fundalyzer?

Fundalyzer is a command-line tool that runs a **fundamental analysis pipeline** on any publicly traded stock ticker. It fetches real financial data, computes key performance indicators (KPIs) in Python, compares them against a peer group, and uses an LLM (Claude) to write narrative interpretations of the numbers.

The pipeline runs in seven sequential layers:

```
data → metrics → peers → dashboards → interpret → decide → report
```

| Layer | What it does |
|---|---|
| **data** | Fetches income statements, balance sheets, cash flows, analyst estimates, insider transactions from FMP and yfinance |
| **metrics** | Computes margins, growth rates, valuation multiples, cash flow metrics, and capital efficiency ratios |
| **peers** | Runs the same computation for each peer ticker and calculates sector medians and percentile rankings |
| **dashboards** | Assembles four typed views: Income, Momentum, Valuation, Capital |
| **interpret** | Sends computed numbers to Claude; receives narrative analysis |
| **decide** | Scores each pillar, positions valuation vs history, reads soft signals, produces INVEST / HOLD / AVOID |
| **report** | Renders to terminal (snapshot) or writes Markdown / PDF (deep dive) |

---

## What Fundalyzer is NOT

Understanding the limits is as important as understanding the capabilities.

**Not a trading system.** Fundalyzer produces a lean (INVEST / HOLD / AVOID) based on fundamental quality and relative value — not timing. A fundamentally excellent company can be overvalued for years; a weak one can rally sharply. The lean is a quality assessment, not a buy or sell trigger.

**Not a price target.** The 3-year projection shown in the output is a mechanical extrapolation of analyst consensus estimates at the current P/E multiple. It illustrates what the market *might* value the company at on today's data. It is explicitly labelled as not a guaranteed target.

**Not financial advice.** Nothing produced by Fundalyzer constitutes investment advice. It is an analytical tool to assist your own research. The three caveats printed at the bottom of every run are non-removable by design.

**Not a replacement for qualitative judgment.** Fundalyzer scores businesses on quantitative metrics visible in financial statements. It does not know about management changes, regulatory risk, product pipeline, competitive moats that aren't yet visible in numbers, or macro conditions.

**Not reliable without peers.** Pillar scores only have meaning relative to a peer group. Without peers, all scores default to a neutral 5.00/10. Always supply `--peers` or configure a default peer list.

**Not infallible with bad data.** The third caveat says it directly: stale estimates, unrepresentative peers, or erroneous source data produce confidently wrong output. Always verify key numbers against source filings.

---

## Installation & Setup

### Prerequisites

- Python 3.11 or later
- An Anthropic API key (required — Claude powers the interpret and decide layers)
- An FMP API key (optional but recommended — improves data quality significantly)

### Install

```bash
cd fundalyzer
pip install -e ".[dev]"   # installs fundalyzer + dev tools
```

Or just the package:

```bash
pip install -e .
```

### Verify the install

```bash
fundalyzer --help
```

### Create your .env file

```bash
cp .env.example .env
```

Then open `.env` and fill in your keys:

```
ANTHROPIC_API_KEY=sk-ant-...your-key...
FMP_API_KEY=...your-fmp-key...
```

**Where to get keys:**
- Anthropic: https://console.anthropic.com/ — free trial available
- FMP: https://financialmodelingprep.com/developer/docs/ — free tier available; paid tiers unlock more data

Without `FMP_API_KEY`, Fundalyzer falls back to yfinance for all data. yfinance covers the core financial statements but does not provide analyst estimates, price targets, or earnings revision history. Results will show `—` for those fields.

---

## Configuration

### Settings (`.env`)

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | — | Claude API key for LLM layers |
| `FMP_API_KEY` | No | — | Financial Modeling Prep key; falls back to yfinance if absent |

### Config file (`fundalyzer.toml`)

An optional TOML file lets you set persistent defaults so you don't need to pass flags every run. Fundalyzer looks for it in:
1. `./fundalyzer.toml` (current directory)
2. `~/.config/fundalyzer/config.toml` (user-wide)

See the [Config File](#config-file) section for the full format.

---

## Running Your First Analysis

### Quickest possible run

```bash
fundalyzer analyze AAPL
```

This runs the full pipeline on Apple with yfinance data (if no FMP key) and no peer comparison. You get a terminal snapshot with neutral pillar scores.

### Meaningful run with peers

```bash
fundalyzer analyze AAPL --peers MSFT,GOOGL,META,NVDA
```

Now pillar scores reflect Apple's actual percentile rank within big tech. This is the recommended minimum — without peers, pillar scores default to 5.00.

### Ten-year history with peers

```bash
fundalyzer analyze AAPL --peers MSFT,GOOGL,META --years 10
```

More historical data produces better trend analysis and a more meaningful historical P/E comparison window.

### Save a deep-dive report

```bash
fundalyzer analyze AAPL --peers MSFT,GOOGL,META --format deep-dive --output-dir ./reports
```

Writes `./reports/AAPL_deep_dive_2026-06-08.md` — a complete document with every KPI, source inputs, narratives, audit trail, and decision rationale.

### Export to PDF

```bash
fundalyzer analyze AAPL --peers MSFT,GOOGL,META --format deep-dive --pdf
```

Requires `pandoc` and a LaTeX engine (`xelatex` or `pdflatex`). If pandoc is not installed, the Markdown file is still written with a clear message about how to install it.

### Get structured JSON output

```bash
fundalyzer analyze AAPL --peers MSFT,GOOGL --format json
```

Outputs the full `InvestmentDecision` object as JSON — useful for piping into other tools or saving for later processing.

### Use the `snapshot` shorthand

```bash
fundalyzer snapshot AAPL --peers MSFT,GOOGL,META
```

Identical to `fundalyzer analyze AAPL --peers MSFT,GOOGL,META --format snapshot`.

---

## Commands Reference

### `fundalyzer analyze TICKER [OPTIONS]`

Runs the full pipeline and outputs in the chosen format.

| Flag | Short | Default | Description |
|---|---|---|---|
| `--peers` | `-p` | auto | Comma-separated peer tickers. When omitted, uses config-file defaults or the provider's sector/industry list. Without any peers, scores are neutral. |
| `--years` | `-y` | 5 | Years of annual financial history to fetch. More years give better trend data and a wider historical P/E window. |
| `--format` | `-f` | `snapshot` | Output format: `snapshot` (rich terminal), `deep-dive` (Markdown file), or `json` (decision object). |
| `--dry-run` | | off | Use only cached data — makes no live API calls. Fails with a clear message if data is not cached. |
| `--output-dir` | `-o` | `.` | Directory to write the deep-dive Markdown or PDF. Created automatically if it doesn't exist. |
| `--pdf` | | off | Also export the deep-dive to PDF via pandoc. Only applies with `--format deep-dive`. |
| `--config` | | auto | Path to a custom `fundalyzer.toml`. Overrides the default search path. |
| `--log-level` | | `warning` | Verbosity: `debug`, `info`, `warning`, `error`. Use `info` to see pipeline progress; `debug` for full HTTP traces. |
| `--log-format` | | `text` | Log output format: `text` (human-readable) or `json` (one JSON object per line, for log aggregators). |

### `fundalyzer snapshot TICKER [OPTIONS]`

Shorthand for `analyze --format snapshot`. Accepts all the same flags except `--format`, `--output-dir`, and `--pdf`.

### `fundalyzer rank GROUP [OPTIONS]`

Ranks every member of a peer group by composite score — no LLM calls. See [Peer Group Leaderboard](#peer-group-leaderboard-rank) for full details.

### `fundalyzer analyze-group GROUP [OPTIONS]`

Runs the full pipeline (including LLM) for every member of a peer group. See [Full Group Analysis](#full-group-analysis-analyze-group) for full details.

| Flag | Short | Default | Description |
|---|---|---|---|
| `--years` | `-y` | 5 | Years of annual history to fetch. |
| `--format` | `-f` | `group-report` | `group-report`: one consolidated Markdown for the whole group. `per-company`: one deep-dive Markdown per ticker. |
| `--output-dir` | `-o` | `.` | Directory for output files. |
| `--pdf` | | off | Export to PDF. Only with `--format per-company`. |
| `--dry-run` | | off | Use only cached data. |
| `--config` | | auto | Path to a custom `fundalyzer.toml`. |
| `--log-level` | | `warning` | Verbosity. |
| `--log-format` | | `text` | Log format: `text` or `json`. |

---

## Peer Group Leaderboard (rank)

### Why rank instead of analyze one-by-one?

The `analyze` command is **target-centric**: you pick one company and ask how it compares to its peers. But the more natural question when screening a sector is **which company in this group is the best opportunity right now?**

`fundalyzer rank` answers that directly. It fetches and scores every member of a peer group at the same time, then ranks them all on the same scorecard. The output is a leaderboard — no manual assembly required.

Because all members are computed from a single data-fetch run, it is also more efficient than running `analyze` once per ticker: data is fetched for every member exactly once and cached immediately.

### Basic usage

```bash
# Rank a named group defined in your config file
fundalyzer rank big_tech

# Rank an ad-hoc list without touching the config
fundalyzer rank AAPL,MSFT,GOOGL,META,AMZN,NVDA

# Use more history for better trend data
fundalyzer rank big_tech --years 10

# Re-run instantly from cache (no API calls)
fundalyzer rank big_tech --dry-run
```

### What the leaderboard shows

```
  Peer Group Leaderboard — 6 companies
┌───┬────────┬───────────┬────────┬──────────┬───────────┬─────────┬─────────┐
│ # │ Ticker │ Composite │ Income │ Momentum │ Valuation │ Capital │  Lean   │
├───┼────────┼───────────┼────────┼──────────┼───────────┼─────────┼─────────┤
│ 1 │ MSFT   │   7.41    │  7.80  │   7.10   │   6.20    │  8.30   │ INVEST  │
│ 2 │ AAPL   │   6.88    │  7.40  │   6.50   │   5.90    │  7.80   │ INVEST  │
│ 3 │ GOOGL  │   6.21    │  6.90  │   6.10   │   6.40    │  5.90   │  INVEST │
│ 4 │ META   │   5.74    │  6.30  │   5.80   │   5.60    │  5.30   │  HOLD   │
│ 5 │ AMZN   │   4.98    │  5.10  │   5.40   │   4.20    │  5.30   │  HOLD   │
│ 6 │ NVDA   │   3.82    │  4.10  │   4.20   │   3.10    │  3.90   │  AVOID  │
└───┴────────┴───────────┴────────┴──────────┴───────────┴─────────┴─────────┘
```

Each score is 0–10, benchmarked **within the group** using the same percentile-ranking logic as `analyze`. Green ≥ 6, yellow 4–6, red < 4.

> **Lean in rank vs analyze:** The lean shown in the leaderboard is derived from the composite score alone — it does not include soft signals (insider activity, EPS revisions, buybacks). Those require raw transaction data that the rank command does not fetch in order to stay fast. Use `fundalyzer analyze` on the top-ranked company for a full lean with soft signals.

### Following up on a top pick

```bash
# See who ranks first, then drill in
fundalyzer rank big_tech

# Full analysis on the winner with the same peer group
fundalyzer analyze MSFT --peers AAPL,GOOGL,META,AMZN,NVDA --format deep-dive
```

### Defining named groups in the config file

Instead of typing a long ticker list every time, add a `[groups]` section to `fundalyzer.toml`:

```toml
[groups]
big_tech    = ["AAPL", "MSFT", "GOOGL", "META", "AMZN", "NVDA"]
financials  = ["JPM", "BAC", "WFC", "GS", "MS", "C"]
pharma      = ["JNJ", "MRK", "PFE", "ABT", "LLY", "AMGN"]
ev          = ["TSLA", "RIVN", "NIO", "LCID", "GM", "F"]
```

Then:

```bash
fundalyzer rank big_tech
fundalyzer rank financials
fundalyzer rank pharma
```

Group names are case-insensitive. The `[groups]` and `[peers]` sections are independent — a group name does not need to match any ticker in `[peers]`.

### `fundalyzer rank GROUP [OPTIONS]`

| Flag | Short | Default | Description |
|---|---|---|---|
| `--years` | `-y` | 5 | Years of annual history to fetch per ticker. |
| `--dry-run` | | off | Use only cached data — no live API calls. |
| `--config` | | auto | Path to a custom `fundalyzer.toml`. |
| `--log-level` | | `warning` | Verbosity: `debug`, `info`, `warning`, `error`. |
| `--log-format` | | `text` | Log output format: `text` or `json`. |

> **No Anthropic API key required.** `rank` makes no LLM calls — it is purely numeric.

---

## Full Group Analysis (analyze-group)

### When to use it

`fundalyzer rank` tells you who wins — `fundalyzer analyze-group` tells you *why*. It runs the complete pipeline (data → metrics → peers → dashboards → interpret → decide → report) for every member of a peer group, with three key advantages over running `fundalyzer analyze` per ticker:

- **Data is fetched once.** All member data is fetched in a single pass and reused. No redundant API calls.
- **Peers are consistent.** Each member is benchmarked against exactly the other members — not auto-derived peers that differ per ticker.
- **One file, whole picture.** The default output is a single consolidated report covering all companies.

### Output formats

| Format | Flag | What you get |
|--------|------|--------------|
| `group-report` | default | One Markdown file with leaderboard, side-by-side KPI comparison, and a summary per company |
| `per-company` | `--format per-company` | One deep-dive Markdown file per ticker (same structure as `fundalyzer analyze --format deep-dive`) |

### Group report (default)

```bash
# Write big_tech_group_report_2026-06-08.md to ./reports/
fundalyzer analyze-group big_tech --output-dir ./reports
```

The consolidated report contains:

1. **Leaderboard** — all companies ranked by composite score with pillar breakdown and lean
2. **Key Metrics Comparison** — side-by-side table across all members: Revenue Growth, Gross/Operating/Net/FCF Margin, P/E, EV/EBITDA, ROIC, ROE, FCF Yield, Debt/Equity
3. **Company Summaries** — one section per company (sorted by rank): scorecard table, valuation vs own history, soft signals table, and the LLM-written rationale paragraph

This is the answer to "give me the full picture on this sector in one document."

### Per-company reports

```bash
# One deep-dive file per ticker
fundalyzer analyze-group big_tech --format per-company --output-dir ./reports

# With PDF export
fundalyzer analyze-group big_tech --format per-company --output-dir ./reports --pdf
```

Output:
```
reports/
  AAPL_deep_dive_2026-06-08.md
  MSFT_deep_dive_2026-06-08.md
  GOOGL_deep_dive_2026-06-08.md
  META_deep_dive_2026-06-08.md
  AMZN_deep_dive_2026-06-08.md
  NVDA_deep_dive_2026-06-08.md
```

Each file is the full deep-dive format: KPI time-series tables, source inputs, trend summaries, LLM narratives, audit trail, and caveats.

### Ad-hoc group

```bash
fundalyzer analyze-group AAPL,MSFT,GOOGL,META --output-dir ./reports
```

### Typical workflow

```bash
# 1. Quick numeric screen — who ranks where?
fundalyzer rank big_tech

# 2. Full group report in one file
fundalyzer analyze-group big_tech --output-dir ./reports

# 3. Drill into the top pick with 10 years of history
fundalyzer analyze MSFT --peers AAPL,GOOGL,META,AMZN,NVDA --years 10 --format deep-dive
```

### Progress output

```
fundalyzer · analyzing group big_tech · 6 companies · 5yr

[1/6] Analyzing AAPL …
[2/6] Analyzing MSFT …
...
✓ Group report written to reports/big_tech_group_report_2026-06-08.md

Done. Analyzed 6/6 companies in big_tech.
```

If one ticker fails, it is skipped with a warning and the rest continue. The group report is still written with the successful results.

---

## Reading the Snapshot Output

The snapshot is the default output — a full terminal view that fits in a single scroll.

### Header bar

```
│  INVEST   AAPL  composite 7.2/10  2026-06-08 11:34  │
```

| Element | Meaning |
|---|---|
| `INVEST` / `HOLD` / `AVOID` | The final lean, color-coded: green, yellow, red |
| Composite score | Weighted average of the four pillar scores (0–10) |
| Date/time | When the analysis was generated |

### Pillar panels

```
╭────── INCOME ──────╮
╰── 7.4/10  ABOVE_PEER ──╯
```

Four panels appear side by side: Income, Momentum, Valuation, Capital. Each shows:
- **Score** (0–10) relative to the peer group
- **Verdict**: STRONG / ABOVE_PEER / IN_LINE / BELOW_PEER / WEAK
- **KPI arrows** (↑ BETTER / ↓ WORSE / → IN_LINE) for the individual metrics in each pillar

> ⚠ **If scores are all 5.00/10 IN_LINE** and you see "No peer group loaded", it means no peers were supplied. Add `--peers` to get real scores.

### Key Metrics table

Eleven core metrics, each showing:
- **Target**: the company's actual value
- **Peer Median**: median across the peer set (— when no peers loaded)
- **Arrow**: ↑ better than peers, ↓ worse, → roughly in line

### Valuation vs Own History

```
│ CHEAPER  current P/E 37.16×  vs hist. median 50.30×  │
```

Compares the current trailing P/E against the company's own median P/E over the last 5 years. Readings:
- **CHEAPER** — current multiple is more than 10% below historical median (green)
- **IN_LINE** — within ±10% of historical median (yellow)
- **RICHER** — current multiple is more than 10% above historical median (red)
- **INSUFFICIENT_DATA** — fewer than 3 years of history available

> This is self-referential, not vs peers. A company can be CHEAPER vs its own history while still being expensive vs peers. Read both sections together.

### Soft Signals

Three non-price signals that confirm or contradict the quantitative lean:

| Signal | Positive means | Negative means |
|---|---|---|
| **Insider activity** | Buys exceed sells by value | Sells exceed buys by value |
| **EPS revisions** | More positive EPS surprises than misses in recent quarters | More misses than beats |
| **Buybacks** | Company is returning significant capital via repurchases | Little or no buyback activity |

**Important nuance on insider selling:** When corporate buybacks exceed insider selling by more than 20×, insider sales are treated as NEUTRAL (routine 10b5-1 diversification) rather than NEGATIVE. A company buying back $90B of stock while executives sell $0.4B is not signalling insider pessimism.

**Conflict flag:** If any two signals point in opposite directions (e.g., EPS revisions POSITIVE but insider activity NEGATIVE), a ⚠ Conflict row appears explaining the contradiction.

### 3-Year Projection

```
│ Base │  6.4%  │  22.7% │  37.16×  │  $512.10  │
│ Bull │ 21.4%  │  37.7% │  40.88×  │  $796.10  │
```

**Base case**: extrapolates revenue at the analyst consensus forward growth rate (or last YoY if no analyst data), EPS at the last YoY EPS growth rate, applied at the current trailing P/E.

**Bull case**: adds 15 percentage points to both growth CAGRs and expands the P/E multiple by 10%.

**Implied price** = Year-3 EPS × Applied P/E. This is what the market *might* value the stock at in 3 years **if the growth rate holds and the multiple doesn't re-rate**. Neither assumption is guaranteed.

### Rationale

2–4 sentences written by Claude citing only the numbers from the scorecard, valuation position, and soft signals above it. Claude cannot invent numbers — every figure in the rationale must trace to a value you can see in the output.

### Caveats

Three non-removable warnings appear at the bottom of every run. They are stored as named fields, not optional text — they cannot be accidentally dropped.

---

## Reading the Deep-Dive Report

Run with `--format deep-dive` to generate a Markdown file. The document has six major sections:

### 1. Investment Decision

All the scorecard data in table form: pillar scores, individual KPI positions, valuation position, 3-year projection with both cases, soft signals, justification, and caveats.

### 2–5. Dashboard sections (Income, Momentum, Valuation, Capital)

Each dashboard section contains:

**Peer medians table** — sector median for each KPI in that pillar.

**Time-series tables** — every KPI as a time series with three columns:

| Period | Value | Formula |
|---|---|---|
| 2024-09-28 (annual) | 46.9% | `gross_profit / revenue` |
| 2023-09-30 (annual) | 44.1% | `gross_profit / revenue` |

**Source inputs (collapsible block)** — the exact raw statement fields used for the most recent period:

```
| revenue     | 391035000000 |
| gross_profit | 180683000000 |
```

This is the audit trail. Any number in the report can be traced back to the raw API response that produced it.

**Trend summary** — whether each metric is ACCELERATING, FLAT, or DECELERATING, with the OLS slope and number of data points.

**Narrative** — the LLM's interpretation of that dashboard, including the claim trail (every assertion with the specific data points it cited).

### 6. Audit Trail

Two sections:
- Instructions for tracing any number back to source
- **Claim Citation Coverage** table: every LLM assertion with its cited `metric=value` data points

This table lets you verify the LLM did not drift from the provided numbers. If a citation cannot be found in the dashboard tables, it was invented.

---

## Understanding the Scores

### Pillar scores (0–10)

Each pillar score is derived from the target company's **percentile rank** within its peer group on the KPIs belonging to that pillar.

For higher-is-better metrics (margins, growth, ROIC):
- A company at the 80th percentile → effective score 8.0

For lower-is-better metrics (P/E, debt-to-equity):
- A company at the 20th percentile (cheapest in the group) → effective score 8.0 (inverted)

Pillar weights in the composite:
- Income: 3 (quality of the business)
- Capital: 3 (efficiency of capital deployment)
- Momentum: 2 (growth trajectory)
- Valuation: 2 (price paid)

### Verdicts

| Score range | Verdict | Meaning |
|---|---|---|
| 8.0 – 10.0 | STRONG | Top quintile vs peers |
| 6.0 – 7.9 | ABOVE_PEER | 60th–80th percentile |
| 4.0 – 5.9 | IN_LINE | Middle of the pack |
| 2.0 – 3.9 | BELOW_PEER | 20th–40th percentile |
| 0.0 – 1.9 | WEAK | Bottom quintile |

### Investment lean logic

| Condition | Lean |
|---|---|
| Composite ≥ 6, not majority-negative signals | INVEST |
| Composite ≥ 6, but RICHER valuation AND majority-negative signals | HOLD |
| Composite < 4 | AVOID |
| Composite 4–5.9, RICHER AND majority-negative signals | AVOID |
| Everything else | HOLD |

---

## Peer Comparisons — Why They Matter

The core design principle: **no company should be judged in isolation**. A 25% net margin is elite in retail but ordinary in software. An 82% ROIC sounds extraordinary, but is it best-in-class for mega-cap technology or merely average?

**Always use peers.** The output is significantly more informative with a peer group.

### Choosing a good peer group

Good peers share:
- Same **sector and industry** (software vs hardware vs hardware-enabled services matter)
- Comparable **scale** (revenue order of magnitude) — a $5B company is not a peer for Apple
- Similar **business model** (recurring subscription revenue vs one-time hardware vs services mix)

**Examples:**

| Ticker | Suggested peers |
|---|---|
| AAPL | MSFT, GOOGL, META, AMZN, NVDA |
| MSFT | AAPL, GOOGL, ORCL, SAP, CRM |
| TSLA | F, GM, RIVN, BMW (note: TSLA comps are contested) |
| JPM | BAC, WFC, GS, C |
| JNJ | MRK, PFE, ABT, LLY |
| AMZN | MSFT, GOOGL, BABA, META |

### Saving default peers in the config file

Instead of typing `--peers` every time, save defaults in `fundalyzer.toml`:

```toml
[peers]
AAPL = ["MSFT", "GOOGL", "META", "AMZN", "NVDA"]
MSFT = ["AAPL", "GOOGL", "ORCL", "SAP", "CRM"]
```

Now `fundalyzer analyze AAPL` automatically uses the configured peers.

---

## Data Providers

Fundalyzer uses two data sources, merged in order of priority:

### Financial Modeling Prep (FMP) — primary

- Income statements, balance sheets, cash flow statements (annual and quarterly)
- Company profile (sector, industry, market cap, price)
- Analyst estimates and price targets
- Earnings revision history (EPS surprises)
- Insider transaction filings
- Peer ticker lists by sector/industry

FMP free tier covers most endpoints. Some premium endpoints (analyst estimates, insider data) may require a paid plan. When an endpoint is unavailable, Fundalyzer marks those fields as `UNAVAILABLE` rather than substituting zero.

### yfinance — fallback

- All financial statements (same data, different source)
- Insider transactions
- Basic price and market cap

yfinance fills any fields that FMP's free tier doesn't return. It does **not** provide analyst estimates or earnings revision data.

### Caching

All API responses are cached to disk at `~/.cache/fundalyzer/{TICKER}/{DATE}/{endpoint}.json`. One cache entry per calendar day per endpoint. This means:
- The second run of the day is instant (no API calls)
- Running `--dry-run` on a fresh ticker fails because nothing is cached yet

---

## Advanced Usage

### Analyze with 10 years of history

```bash
fundalyzer analyze AAPL --peers MSFT,GOOGL,META --years 10
```

More history produces more reliable trend analysis and a better historical P/E comparison window. Recommended for any serious analysis.

### Write a deep-dive with PDF

```bash
fundalyzer analyze TSLA --peers F,GM,RIVN \
  --format deep-dive \
  --output-dir ./reports/TSLA \
  --pdf \
  --years 10
```

### Structured JSON for programmatic use

```bash
fundalyzer analyze AAPL --peers MSFT,GOOGL,META --format json | jq '.lean'
```

The JSON output is the full `InvestmentDecision` object. All fields are typed — scores are Decimals, LLM text is in string fields only.

### Debug mode

```bash
fundalyzer analyze AAPL --log-level debug
```

Shows every HTTP request, cache hit/miss, and LLM call with token counts.

### Structured JSON logs (for log aggregation)

```bash
fundalyzer analyze AAPL --log-level info --log-format json 2>analysis.log
```

Each log entry is a JSON object with `ts`, `level`, `logger`, and `msg` fields.

### Dry-run (offline, cached data only)

```bash
fundalyzer analyze AAPL --dry-run
```

Makes zero API calls. Uses whatever is in `~/.cache/fundalyzer/`. Useful for:
- Re-running an analysis offline
- Testing without burning API credits
- CI environments without API access

Fails with a clear error if the cache is empty for the requested ticker.

### Shell completion

```bash
fundalyzer --install-completion    # install tab completion for your shell
```

After running this, `fundalyzer ana<TAB>` completes to `analyze`, etc.

---

## Config File

Create `fundalyzer.toml` in your project directory or at `~/.config/fundalyzer/config.toml`.

```toml
# Default number of years of history to fetch (overridden by --years)
[defaults]
years = 10

# Default peer groups per ticker.
# These are used when --peers is not passed on the command line.
# Keys are case-insensitive.
[peers]
AAPL  = ["MSFT", "GOOGL", "META", "AMZN", "NVDA"]
MSFT  = ["AAPL", "GOOGL", "ORCL", "SAP",  "CRM"]
GOOGL = ["META", "MSFT", "AAPL", "SNAP",  "PINS"]
META  = ["GOOGL", "SNAP", "PINS", "TWTR",  "MSFT"]
TSLA  = ["F", "GM", "RIVN", "NIO", "LCID"]
JPM   = ["BAC", "WFC", "GS", "C",  "MS"]
JNJ   = ["MRK", "PFE", "ABT", "LLY", "AMGN"]

# Sector-level fallback: used when a ticker is not listed in [peers]
# and the provider cannot derive peers automatically.
[sector_peers]
Technology = ["AAPL", "MSFT", "GOOGL", "META", "AMZN", "NVDA"]
Healthcare = ["JNJ",  "MRK",  "PFE",   "ABT",  "AMGN", "LLY"]
Financials = ["JPM",  "BAC",  "WFC",   "GS",   "MS",   "C"]

# Named groups for `fundalyzer rank`.
# Every member is scored against every other member.
# Names are case-insensitive. Independent of the [peers] section.
[groups]
big_tech   = ["AAPL", "MSFT", "GOOGL", "META", "AMZN", "NVDA"]
financials = ["JPM",  "BAC",  "WFC",   "GS",   "MS",   "C"]
pharma     = ["JNJ",  "MRK",  "PFE",   "ABT",  "LLY",  "AMGN"]
ev         = ["TSLA", "RIVN", "NIO",   "LCID", "GM",   "F"]
```

With this file in place:

```bash
fundalyzer analyze AAPL          # uses MSFT, GOOGL, META, AMZN, NVDA automatically
fundalyzer analyze MSFT          # uses its own configured peer list
fundalyzer analyze AAPL --peers SAMSUNG  # overrides the config with an explicit list
fundalyzer rank big_tech         # ranks all 6 big_tech members against each other
fundalyzer rank financials       # ranks all 6 financials members
```

---

## Dry-Run Mode

Use `--dry-run` to run purely from the disk cache, making zero network or API calls.

```bash
# First run — fetches and caches
fundalyzer analyze AAPL --peers MSFT,GOOGL

# Later runs — instant, no API calls
fundalyzer analyze AAPL --peers MSFT,GOOGL --dry-run
```

The cache lives at `~/.cache/fundalyzer/`. Each ticker gets its own directory, organized by date:

```
~/.cache/fundalyzer/
└── AAPL/
    └── 2026-06-08/
        ├── profile.json
        ├── income_annual_5.json
        ├── income_quarter_12.json
        ├── balance_annual_5.json
        └── ...
```

Cache entries expire naturally: the next calendar day generates a new path, so stale data is never silently served. Old entries can be cleaned manually.

**When dry-run fails:** If you run `--dry-run` before ever fetching data, you'll see:

```
Dry-run error: No cached data for 'AAPL' endpoint 'profile'. Remove --dry-run to fetch live data.
```

---

## Troubleshooting

### "ANTHROPIC_API_KEY is not set"

Create a `.env` file in the `fundalyzer/` directory:
```
ANTHROPIC_API_KEY=sk-ant-...
```

### "FMP failed for AAPL (No FMP profile data); falling back to yfinance"

This appears as a warning, not an error. The analysis continues with yfinance data. It typically means:
- Your FMP API key has insufficient tier for the profile endpoint
- A temporary FMP outage

The analysis still runs with full yfinance data. You lose analyst estimates and earnings revision data.

### All peer medians show `—`

You haven't supplied peers. Add `--peers MSFT,GOOGL,META` or configure defaults in `fundalyzer.toml`. Without peers, pillar scores default to neutral (5.00/10) and no comparison arrows appear.

### All pillar scores are 5.00/10

Same cause as above — no peers means no percentile ranking means neutral scores. This is intentional: the tool refuses to pretend it can score a company in isolation.

### "Dry-run error: No cached data"

You're running `--dry-run` but the data isn't cached yet. Run once without `--dry-run` first.

### "Provider error: HTTP 401"

Your FMP API key is invalid or expired. Check your `.env` file. If you have no FMP key at all, remove `FMP_API_KEY` from `.env` — the tool will use yfinance automatically.

### PDF export fails

```
pandoc is not installed. Install it with:
  macOS:   brew install pandoc
  Ubuntu:  sudo apt install pandoc texlive-xetex
```

The Markdown file is always written regardless — the PDF step is additive.

### Numbers look wrong or inconsistent

Remember the third caveat: garbage in, garbage out. Check:
1. Is the FMP API returning data? (run with `--log-level info` to see)
2. Are the peers appropriate for this company?
3. Is the historical P/E window meaningful given the company's earnings history?

For maximum transparency, run `--format deep-dive` and open the `<details>Source inputs</details>` blocks in any KPI table — every number traces back to a specific API field value.

---

## Architectural Contract

The single most important rule in Fundalyzer:

> **ALL numeric values originate from a real financial data API and are computed deterministically in Python. The LLM is only ever used to interpret numbers it is given. The LLM must never generate or invent a figure that appears in output.**

This means:
- Every number you see in the output was computed by Python from a real API response
- Claude writes the narrative text (headline, body, rationale, projection assumptions)
- Claude cannot invent or compute a number — it can only cite numbers from the data it was given
- The audit trail in the deep-dive lets you verify any claim traces to a real source value

The `UNAVAILABLE` marker (shown as `—` in the output) is used whenever a field returned no data from any provider. It is never substituted with zero, a guess, or an LLM estimate.

The guardrail tests in `tests/test_guardrail.py` enforce this rule in the test suite:
- LLM output is stored only in `str` fields — it can never populate a `Decimal` field
- Every number in the rendered Markdown is traced to the data corpus within display-rounding tolerance
- A "rogue number" test verifies that an LLM hallucinating a fake number cannot contaminate any Python-computed field in the report
