# Fundalyzer Web App — Build Plan

Full-stack web application: FastAPI backend + React (Vite) frontend.
Runs daily, serves results in Chrome, supports operations from the UI.

**Status legend:** ⬜ not started · 🔄 in progress · ✅ done

---

## Overview

```
Browser (React)
    │
    │  REST + SSE
    ▼
FastAPI  ─── calls ───► existing pipeline (data → metrics → peers → … → decide)
    │
    └── reads/writes ──► result store (JSON files, one per group per date)
    └── reads/writes ──► fundalyzer.toml (group config)
    └── schedules ──────► daily analysis job (APScheduler)
```

No database required. Results are JSON files on disk, same pattern as the
existing cache. Can be upgraded to SQLite later without touching the frontend.

---

## Phase 1 — Existing code changes (2 files)

These are the only modifications to files that already exist.
Everything in Phase 2+ is purely additive.

### Step 1 ⬜ — Add `progress_callback` to `pipeline.py`

**File:** `fundalyzer/pipeline.py`

Add an optional `progress_callback: Callable[[str], None] | None = None`
parameter to `run_analysis()`. Call it at each layer transition:

```
"fetching_data"       after layer 1 (data)
"computing_kpis"      after layer 2 (metrics)
"building_peers"      after layer 3 (peers)
"building_dashboards" after layer 4 (dashboards)
"interpreting"        after layer 5 (interpret)
"deciding"            after layer 6 (decide)
"done"                at the end
```

The CLI passes `None` — no behaviour change.
The FastAPI SSE endpoint passes a function that pushes events to the browser.

---

### Step 2 ⬜ — Add write methods to `config.py`

**File:** `fundalyzer/config.py`

Add to `FundalyzerConfig`:

- `add_group(name: str, tickers: list[str])` — upsert a group
- `remove_group(name: str)` — delete a group (no-op if missing)
- `save(path: Path)` — serialise the current state back to TOML

The read-only accessors (`group()`, `all_groups()`, etc.) are unchanged.

---

## Phase 2 — FastAPI backend

New directory: `fundalyzer/api/`

### Step 3 ⬜ — Project structure + dependencies

Create the `api/` package skeleton and add dependencies to `pyproject.toml`:

```
fundalyzer/api/
  __init__.py
  main.py          ← FastAPI app, mounts all routers, configures CORS
  dependencies.py  ← shared provider / config setup (reused across routes)
  store.py         ← result persistence (read/write JSON files)
  scheduler.py     ← APScheduler daily job
  routes/
    __init__.py
    groups.py      ← /api/groups endpoints
    analysis.py    ← /api/analyze endpoints + SSE stream
    results.py     ← /api/results endpoints
    settings.py    ← /api/settings endpoints
```

New dependencies:
- `fastapi`
- `uvicorn[standard]`
- `apscheduler`

---

### Step 4 ⬜ — Result store (`api/store.py`)

Persist analysis results so the UI reads cached data without re-running
the pipeline on every page load.

**Storage layout:**
```
~/.local/share/fundalyzer/results/
  big_tech/
    2026-06-08.json    ← GroupReportData for that date
    2026-06-09.json
  financials/
    2026-06-08.json
```

**`GroupReportData` model** (new Pydantic model in `api/store.py`):
```python
class GroupReportData(BaseModel):
    group_name: str
    run_date: str               # ISO date
    ranking: GroupRanking
    decisions: dict[str, InvestmentDecision]  # ticker → decision
```

**Public API:**
- `save_result(group_name, data: GroupReportData)`
- `load_result(group_name, date) -> GroupReportData | None`
- `latest_result(group_name) -> GroupReportData | None`
- `list_dates(group_name) -> list[str]`
- `list_groups_with_results() -> list[str]`

---

### Step 5 ⬜ — Groups API (`routes/groups.py`)

Endpoints to read and manage peer groups from `fundalyzer.toml`.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/groups` | List all named groups with their tickers |
| `POST` | `/api/groups` | Create or update a group `{name, tickers}` |
| `DELETE` | `/api/groups/{name}` | Remove a group |
| `GET` | `/api/groups/{name}` | Get one group's tickers + latest result metadata |

---

### Step 6 ⬜ — Results API (`routes/results.py`)

Endpoints to read stored analysis results.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/results/{group}` | Latest result for a group (full `GroupReportData`) |
| `GET` | `/api/results/{group}/{date}` | Result for a specific date |
| `GET` | `/api/results/{group}/dates` | List available dates for a group |
| `GET` | `/api/results/{group}/company/{ticker}` | Single company decision from latest result |

---

### Step 7 ⬜ — Analysis API + SSE stream (`routes/analysis.py`)

Trigger pipeline runs and stream progress to the browser in real time.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/analyze/{group}` | Run full group analysis, save result, return `GroupReportData` |
| `GET` | `/api/analyze/{group}/stream` | SSE stream — same run but pushes progress events |

**SSE event format:**
```
event: progress
data: {"ticker": "AAPL", "step": "interpreting", "index": 2, "total": 6}

event: done
data: {"group": "big_tech", "date": "2026-06-08"}

event: error
data: {"ticker": "NVDA", "message": "provider timeout"}
```

The `progress_callback` added in Step 1 feeds these events.

---

### Step 8 ⬜ — Scheduler (`api/scheduler.py`)

APScheduler job that runs `analyze-group` for every configured group
at a scheduled time each day.

- Default schedule: **07:00 local time**, configurable via `.env`
- On startup, FastAPI registers the scheduler and starts it
- Endpoint `GET /api/scheduler/status` returns next run time + last run per group
- Endpoint `POST /api/scheduler/run-now/{group}` triggers an immediate run

---

### Step 9 ⬜ — Settings API (`routes/settings.py`)

Read and write the `.env` / `fundalyzer.toml` settings that the UI
needs to expose.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/settings` | Return current settings (API keys masked, schedule time, default years) |
| `PATCH` | `/api/settings` | Update schedule time, default years |

API keys are never returned in plain text — only a masked indicator
(`"set"` / `"not set"`).

---

## Phase 3 — React frontend (Vite)

New directory: `webapp/`

Bootstrap: `npm create vite@latest webapp -- --template react`

Dependencies: `react-router-dom`, `recharts` (charts), `@tanstack/react-query`
(data fetching + caching).

No UI component library — plain CSS modules to keep it lean and avoid
dependency churn.

---

### Step 10 ⬜ — Vite project setup + dev proxy

Set up the Vite project and configure the dev proxy so
`/api/*` in the browser forwards to `localhost:8000` during development.

```
webapp/
  src/
    main.jsx
    App.jsx
    api/          ← fetch helpers (one file per resource)
    pages/
    components/
    styles/
  vite.config.js  ← proxy: /api → http://localhost:8000
```

---

### Step 11 ⬜ — Dashboard page

**Route:** `/`

The landing page. Shows:

- Group selector (tabs or sidebar — one tab per configured group)
- For the selected group:
  - "Last updated" timestamp + "Run now" button
  - Leaderboard table (rank, ticker, composite, income, momentum,
    valuation, capital, lean) — color-coded scores
  - If no result yet: empty state with a "Run analysis" button

---

### Step 12 ⬜ — Group report page

**Route:** `/groups/:name`

The full consolidated group report rendered in the browser:

- Leaderboard table (same as dashboard but with clickable rows)
- Key Metrics Comparison — horizontal bar chart per KPI, one bar per company,
  sorted by the metric value
- Company summary cards — lean badge, scorecard, valuation position,
  soft signal indicators, rationale text

---

### Step 13 ⬜ — Company detail page

**Route:** `/groups/:name/company/:ticker`

Drill-down for one company within a group result:

- Full scorecard with pillar breakdown
- Valuation vs own history
- 3-year projection table (base + bull)
- Soft signals with detail text
- Full rationale paragraph
- KPI positions vs peers (BETTER / WORSE / IN_LINE per metric)

---

### Step 14 ⬜ — Live progress UI

When a user clicks "Run now" or "Run analysis":

- A progress panel slides in (or modal opens)
- SSE connection to `/api/analyze/:group/stream`
- Shows per-company progress: `[2/6] MSFT — interpreting…`
- Progress bar fills as tickers complete
- On `done` event: refreshes the group report automatically
- On `error` event: shows which ticker failed with the reason

---

### Step 15 ⬜ — Group management UI

**Route:** `/settings/groups`

- List all configured groups with their tickers
- "Add group" form: name + comma-separated tickers
- Edit a group: add/remove individual tickers
- Delete a group (with confirmation)
- Changes call the groups API which writes back to `fundalyzer.toml`

---

### Step 16 ⬜ — Scheduler settings UI

**Route:** `/settings`

- Show next scheduled run time per group
- Show last run time + outcome (success / N tickers failed)
- Change the daily schedule time
- "Run all groups now" button

---

## Phase 4 — Integration & launch

### Step 17 ⬜ — Startup script

A single command to start the whole stack for development:

```bash
make dev
# starts: uvicorn fundalyzer.api.main:app --reload
#       + vite dev server (proxied)
```

And for production (serving the built React bundle from FastAPI):

```bash
make build   # npm run build inside webapp/
make start   # uvicorn only — FastAPI serves the built static files
```

---

### Step 18 ⬜ — Update tutorial

Add a "Web App" section to `fundalyzer-tutorial.md` covering:

- Prerequisites (Node.js for building the frontend)
- `make dev` for local development
- `make start` for production mode
- How the daily scheduler works
- How to add groups from the UI

---

## Dependency summary

### Python (add to `pyproject.toml`)
```
fastapi >= 0.111
uvicorn[standard] >= 0.29
apscheduler >= 3.10
tomli-w >= 1.0      # for writing TOML (config save)
```

### Node (webapp only, not shipped)
```
react, react-dom, react-router-dom
@tanstack/react-query
recharts
vite
```

---

## What is NOT changing

- `data/`, `metrics/`, `peers/`, `dashboards/`, `interpret/`, `decide/` — untouched
- `report/` — untouched
- `cli.py` — untouched (CLI continues to work independently)
- All existing tests — untouched
- Disk cache (`~/.cache/fundalyzer/`) — untouched, API reuses it

The web app is a new surface on top of the existing pipeline, not a rewrite.
