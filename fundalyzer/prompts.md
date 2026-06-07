Treating this as a build spec. The single decision that makes this app meaningful instead of a hallucination engine comes straight from the videos: the mechanical work goes to code, the conceptual work goes to the model. So in software terms, every number that lands in a dashboard is computed deterministically in Python from a real data API, and the LLM (Claude, via the Anthropic SDK) only interprets, compares, and synthesizes. The model never produces a figure that gets displayed. That mirrors the video's "connect real data or it invents numbers" warning, enforced at the architecture level.

Assumptions I am baking in, change them in the first prompt if you disagree: Financial Modeling Prep as the data provider (free tier has statements, ratios, analyst estimates, insider trades; yfinance as fallback), a CLI app first, Claude as the interpretation model, input is one ticker plus an optional peer list.

Here are the prompts I would feed Claude Code, in order. Each one builds on the last and ends with a test gate so you do not stack layers on a broken foundation.

**Prompt 1, scaffold and the core contract**

```
Build the skeleton of a Python CLI app called fundalyzer that runs a
fundamental analysis pipeline on a stock ticker.

Hard architectural rule, enforce it everywhere: all numeric values come
from a real financial data API and are computed in Python. The LLM is
only ever used to interpret numbers it is given. The LLM must never
generate a figure that appears in output. Write this rule as a comment
at the top of the package and design the module boundaries around it.

Layers, one module each:
  data        fetch raw financial data from a provider
  metrics     compute all KPIs deterministically from raw data
  peers       aggregate metrics across a peer set and a sector median
  dashboards  assemble four typed dashboard objects
  interpret   LLM narrative over computed numbers
  decide      synthesis and final investment lean
  report      render deep dive and snapshot outputs

Use pydantic for every data structure that crosses a module boundary so
schemas are explicit. Use typer for the CLI and rich for terminal output.
Provider is Financial Modeling Prep, with an adapter interface so a
second provider can be added later. Read API keys from a .env file.
Set up pytest, a Makefile with lint and test targets, and a pyproject.

Do not implement logic yet. Produce the directory tree, the pydantic
schemas as stubs, the provider adapter interface, and a passing smoke
test that imports every module.
```

**Prompt 2, the data layer**

```
Implement the data module against Financial Modeling Prep.

Fetch and normalize into the pydantic schemas: income statement, balance
sheet, and cash flow statement for the last 12 quarters and last 10
years; current price and market cap; shares outstanding history; analyst
estimates and price targets; earnings estimate revisions; and insider
transactions.

Add a yfinance fallback adapter that fills whatever FMP free tier does
not return. Every fetch is cached to disk keyed by ticker and date so we
do not burn API calls during development. If a field is unavailable from
all providers, return an explicit "unavailable" marker, never a guess or
a zero.

Write tests using a recorded fixture response for one ticker. No live
calls in the test suite.
```

**Prompt 3, the metrics engine, fully deterministic**

```
Implement the metrics module. Compute every KPI in pure Python from the
raw statements. No LLM, no API ratio endpoints, compute from primitives
so the numbers are reproducible and auditable.

Profitability: revenue growth rate per period, gross margin, operating
margin, net margin, EPS, EBITDA.
Valuation: trailing P/E, forward P/E from analyst estimates, P/S,
EV/EBITDA, PEG, P/B.
Cash flow: operating cash flow, free cash flow, free cash flow margin,
free cash flow yield.
Financial strength: debt to equity, net cash versus net debt, current
ratio, ROE, ROIC.

For each metric produce a time series, not a single value, so trend and
rate of change are available downstream. Add a helper that classifies a
series as accelerating, flat, or decelerating, because rate of change
matters more than level.

Every metric carries its formula and the raw inputs used, attached to
the result object, so output is traceable to source. Write unit tests
with hand checked expected values for at least one full pillar.
```

**Prompt 4, peers and sector context**

```
Implement the peers module. Given a target ticker and a peer list, run
the data and metrics layers for every peer, then compute the sector
median for each KPI across the set.

For the target, attach a relative position for each metric: better,
worse, or in line versus the peer median, with the percentile. This is
the comparison backbone, the whole point is that no company is judged in
isolation.

If no peer list is given, derive a default peer set from the provider's
sector and industry classification, capped at a sensible number. Cache
peer pulls. Test the median and percentile math on a small synthetic set.
```

**Prompt 5, the four dashboards**

```
Implement the dashboards module as four typed objects assembled purely
from already computed metrics. No new computation, no LLM here.

Income, the foundation: revenue, profitability stack, free cash flow,
and whether the pace is satisfactory.
Momentum, the engine: yearly EPS, revenue, free cash flow, sales versus
guidance, P/E history versus forward, with rate of change emphasized.
Valuation, the price: P/E, P/S, EV/EBITDA, EV/gross profit plotted over
5 to 10 years, flagged as cheaper or richer than the company's own
history.
Capital, the allocation: ROIC, revenue per employee trend, buyback
activity, and analyst view on current price.

Each dashboard exposes both the target values and the peer median beside
them. Test that a fully populated metrics set produces four complete
dashboards.
```

**Prompt 6, the interpretation layer, this is where the smart prompt pattern lives**

```
Implement the interpret module using the Anthropic SDK.

For each of the four dashboards, send Claude the computed numbers as
structured JSON and ask for a short narrative. The system prompt must
state: you are given numbers, never invent or recompute any figure,
every sentence must trace to a provided value, and if a value is marked
unavailable say so rather than estimating.

Encode the smart question pattern from the method: each interpretation
request specifies the KPI, the time window, and the peer comparison, and
asks whether the metric is improving or deteriorating and what that
implies about the business. Forbid vague verdicts like "good stock".

Return narrative plus a list of the specific data points each claim
relied on, so we can verify the model did not drift from the numbers.
Add a test using a mocked Claude response, no live model calls in CI.
```

**Prompt 7, the synthesis and decision engine** - this is where i am now

```
Implement the decide module. This turns four dashboards plus their
narratives into an investment lean.

Steps:
1 Score each of the four pillars relative to the peer median, not in a
  vacuum. Output a per pillar verdict.
2 Place current valuation against the company's own 5 to 10 year range
  and state cheaper, in line, or richer, explicitly noting this alone
  does not mean buy or sell.
3 Build a base case and a bull case three year projection. Construct it
  in Python from analyst estimates already fetched, then ask Claude only
  to narrate the assumptions, not to produce the numbers.
4 Read the soft signals: insider buying versus selling, estimate
  revisions up or down, buyback activity. Flag any conflict, for example
  rising estimates but heavy insider selling.
5 Produce a final lean of invest, hold, or avoid, justified by the
  combination: a healthy business improving versus peers at a non
  stretched valuation with aligned soft signals argues to invest, the
  inverse argues to avoid.

The output object must always carry three fixed caveats: fundamentals
give quality not timing, the projection is how the market would value
the company on today's data and not a guaranteed target, and bad input
assumptions produce confident wrong output. These are non removable
fields, not optional text.
```

**Prompt 8, reporting**

```
Implement the report module with two outputs from the same analysis run.

Snapshot: the four dashboards rendered to the terminal with rich, target
beside peer median, color coded by relative position, plus the final
lean and the caveats. This is the fast read.

Deep dive: a full document, every KPI with its time series, formula,
source inputs, peer comparison, narrative, the base and bull cases, and
the decision rationale. Render to Markdown and offer a PDF export.

The deep dive must be auditable end to end: a reader can trace any number
back to the raw statement line it came from.
```

**Prompt 9, wire the CLI and harden**

```
Wire the full pipeline into the typer CLI:
  fundalyzer analyze TICKER --peers AAPL,MSFT --years 10 --format snapshot

Add: graceful handling when a provider is down, a dry run mode that uses
only cached data, structured logging, and a config file for default peer
sets per sector. Add an end to end test on recorded fixtures that runs
the whole chain and asserts a complete report with no missing or model
generated numbers.

Finally, add a guardrail test that scans every displayed number and
fails if any value did not originate from the data layer. This is the
test that protects the core architectural rule.
```

A few notes on why it is ordered this way. You build and test the deterministic spine (prompts 2 through 5) before the model touches anything, so when the LLM layer goes in you can prove its output never contradicts the computed numbers. Prompt 9's final guardrail test is the one I would not skip: it is the automated enforcement of the whole thesis, that the model interprets and the code computes.

Two extensions worth holding for later rather than asking Claude Code to build now: Phase 0 of the method (experiencing the product, watching the CEO) does not automate cleanly, so leave it as a manual checklist the report prints rather than faking it; and a LangGraph orchestration layer would fit naturally on top once the modules are stable, with each layer as a node, which given your LangGraph background would be a small lift if you want retries, human in the loop checkpoints, or multi ticker fan out.

This is an educational tool by design, and the decision output should keep the video's honest framing: it tells you whether a business is healthy and how it is priced relative to itself and peers, not when to buy and not a guaranteed outcome. I am not a financial advisor.



MORE
Here's how the app comes together, prompt by prompt. Think of it as building a spine first (pure Python, fully testable), then attaching the brain (Claude) only after the spine is proven solid.

The one rule that drives everything: numbers are computed by code from a real data source, and Claude only ever interprets numbers it's handed. Claude never invents a figure that shows up in output. Every prompt below protects that rule.

**Prompt 1, the skeleton**

- Lays out the folder structure and the module boundaries, nothing else.
- Each stage of the pipeline gets its own module: `data`, `metrics`, `peers`, `dashboards`, `interpret`, `decide`, `report`.
- Defines the data shapes (pydantic schemas) as empty stubs so modules have a contract to talk through.
- Ends with a smoke test: can every module be imported without crashing.

Example of what exists after this prompt: a `MetricResult` schema with fields like `name`, `series`, `formula`, but no logic filling it yet. Running the app does nothing useful, but the shape is there.

**Prompt 2, the data layer**

- Connects to the financial data provider (Financial Modeling Prep, with yfinance as backup).
- Pulls the raw material: income statement, balance sheet, cash flow, prices, analyst estimates, insider trades.
- Caches every response to disk so you don't burn API calls re-running during development.
- If a field is genuinely missing, it returns an explicit "unavailable" marker rather than a zero or a guess.

Example: you ask for NVDA's last 12 quarters of revenue and get back a clean list of real reported numbers, saved locally so the next run is instant.

**Prompt 3, the metrics engine**

- Turns raw statements into the KPIs, all in plain Python, no model involved.
- Computes each metric as a time series, not a single number, so you can see the trend.
- Adds a classifier that labels a series accelerating, flat, or decelerating, because rate of change matters more than the level.
- Attaches the formula and source numbers to each result so any figure is traceable.

Example: revenue of 100, 110, 130 gets labeled "accelerating," while 100, 110, 120 gets "decelerating." That label is computed, not opinion.

**Prompt 4, peers and sector context**

- Runs the data and metrics layers across a list of competitors.
- Computes the sector median for every KPI.
- Tags the target company on each metric: better, worse, or in line versus peers, with a percentile.

Example: NVDA's free cash flow margin comes back as "better than peers, 90th percentile" when compared against AMD, Broadcom, and Intel. This is the comparison backbone, no company is judged alone.

**Prompt 5, the four dashboards**

- Assembles the computed metrics into four views, no new math, no model.
- Income (is it making money), Momentum (rate of change), Valuation (cheap or expensive vs its own history), Capital (using money well).
- Each dashboard shows the target's number next to the peer median.

Example: the Valuation dashboard shows NVDA's P/E plotted over 10 years with a flag like "currently richer than its own historical average."

**Prompt 6, the interpretation layer (Claude enters here)**

- Hands Claude the computed numbers as structured data and asks for a short narrative per dashboard.
- The system prompt forbids inventing or recomputing any figure, and bans vague verdicts like "good stock."
- Encodes the smart-question pattern: every request names the KPI, the time window, and the peer comparison, then asks "improving or deteriorating, and what does that imply."
- Claude returns its narrative plus the exact data points each sentence leaned on, so you can verify it didn't drift.

Example prompt sent to Claude internally: "NVDA free cash flow margin over 8 quarters versus sector median, here are the numbers, is it improving and what does it mean for the business." It answers in prose grounded in those numbers.

**Prompt 7, the decision engine**

- Scores each of the four pillars relative to peers, not in a vacuum.
- Places valuation against the company's own 5 to 10 year range.
- Builds a base case and a bull case for three years, the numbers computed in Python from analyst estimates, with Claude only narrating the assumptions.
- Reads soft signals (insider buying vs selling, estimate revisions, buybacks) and flags conflicts.
- Produces a final lean: invest, hold, or avoid, with three fixed caveats that can't be removed (quality not timing, projection isn't a guarantee, bad inputs give confident wrong answers).

Example conflict it would flag: analyst estimates rising but insiders selling heavily, which is a hole in the bullish story worth surfacing.

**Prompt 8, reporting**

- Produces two outputs from one run.
- Snapshot: the four dashboards in the terminal, target beside peer median, color-coded, plus the final lean. The fast read.
- Deep dive: the full document, every KPI with its series, formula, source, comparison, narrative, and the decision rationale, exported to Markdown or PDF.
- The deep dive is auditable end to end, any number traces back to the statement line it came from.

Example: the snapshot is a one-screen verdict, while the deep dive is the 37-page equivalent the videos described.

**Prompt 9, wiring and hardening**

- Connects the whole chain to one CLI command, for example `fundalyzer analyze NVDA --peers AMD,AVGO,INTC`.
- Adds graceful failure when a provider is down, a cached-only dry-run mode, and logging.
- Ends with the most important test: a guardrail that scans every displayed number and fails the build if any value didn't come from the data layer.

That last test is the whole philosophy turned into code, it mechanically proves Claude never slipped a made-up number into your output.

Why this order matters: prompts 2 through 5 give you a fully tested calculator that works with zero AI. Only then does Claude get attached, and because the numbers already exist and are verified, you can always check the model's words against hard figures. You're never trusting the model for facts, only for reading them.

This is an educational tool, and the output tells you whether a business is healthy and how it's priced, not when to buy or what will happen. Not financial advice.