# Fundalyzer Web App — Steps Progress

Tracks what was done at each step, what decisions were made, and anything left open.
See `WEBAPP_PLAN.md` for the full plan.

---

## Phase 1 — Existing code changes

### Step 1 ✅ — Add `progress_callback` to `pipeline.py`

**Done:** Added optional `progress_callback: ProgressCallback | None = None` parameter
to `run_analysis()` in `fundalyzer/pipeline.py`.

- Defined `ProgressCallback = Callable[[str, str], None]` (ticker, step) type alias
  with a docstring listing all 7 step values emitted during a run.
- Added a local `_emit(step)` helper inside `run_analysis()` that calls the
  callback when it is not None — zero overhead when omitted.
- Callback fires after each of the 7 layers: `fetching_data`, `computing_kpis`,
  `building_peers`, `building_dashboards`, `interpreting`, `deciding`, `done`.
- CLI passes nothing — no behaviour change. FastAPI SSE route will pass a
  function that calls `loop.call_soon_threadsafe(queue.put_nowait, event)`.
- All 361 tests pass.

**Nothing left to do for this step.**
### Step 2 ✅ — Add write methods to `config.py`

**Done:** Added four mutator methods to `FundalyzerConfig` in `fundalyzer/config.py`,
plus a soft dependency on `tomli-w` for TOML serialisation.

- `add_group(name, tickers)` — upserts a group (in-memory until `save()`).
- `remove_group(name)` — removes a group; no-op if missing.
- `set_default_years(years)` — updates the `[defaults] years` field.
- `save(path)` — writes the full in-memory config back to disk as TOML
  via `tomli-w`; raises `RuntimeError` with install instructions if the
  package is absent.

**Thread safety note:** `save()` itself is not locked — the FastAPI routes
that call it will wrap it in a `filelock.FileLock` (added in Step 3 with
the other API dependencies). Lock lives at the call site, not in config.

`tomli-w` installed into the project venv. Will be added to `pyproject.toml`
in Step 3 alongside the other new dependencies.

All 361 tests pass.

**Nothing left to do for this step.**

---

## Phase 2 — FastAPI backend

### Step 3 ✅ — Project structure + dependencies

**Done:** Created `fundalyzer/api/` package with full skeleton.

New files: `__init__.py`, `main.py`, `dependencies.py`, `store.py`,
`runner.py`, `_running.py`, `scheduler.py`, `routes/__init__.py`,
`routes/groups.py`, `routes/results.py`, `routes/analysis.py`,
`routes/settings.py`.

Added `[api]` extras to `pyproject.toml`: `fastapi`, `uvicorn[standard]`,
`apscheduler`, `tomli-w`, `filelock`. All installed.

`runner.py` is a shared module called by both the API routes and the
scheduler — avoids duplicating pipeline logic.

`_running.py` uses `threading.Lock` (not asyncio) so it works from both
async FastAPI routes and APScheduler background threads.

API imports verified clean. All 361 tests still pass.

**Nothing left to do for this step.**

---

### Step 4 ✅ — Result store (`api/store.py`)

**Done:** `GroupReportData` Pydantic model (`group_name`, `run_date`,
`ranking: GroupRanking`, `decisions: dict[str, InvestmentDecision]`).

Storage layout: `~/.local/share/fundalyzer/results/{group}/{date}.json`.
One JSON file per group per calendar day.

Public API: `save_result`, `load_result`, `latest_result`, `list_dates`,
`list_groups_with_results`. All use `os.scandir` equivalent (`Path.iterdir`)
— no manifest file needed.

**Nothing left to do for this step.**

---

### Step 5 ✅ — Groups API (`routes/groups.py`)

**Done:** Four endpoints under `/api/groups`:
- `GET /api/groups` — all groups dict
- `GET /api/groups/{name}` — tickers + available result dates
- `POST /api/groups` — create/update (writes `fundalyzer.toml` with FileLock)
- `DELETE /api/groups/{name}` — remove (writes with FileLock)

**Nothing left to do for this step.**

---

### Step 6 ✅ — Results API (`routes/results.py`)

**Done:** Four endpoints under `/api/results`:
- `GET /api/results/{group}` — latest `GroupReportData`
- `GET /api/results/{group}/dates` — available dates
- `GET /api/results/{group}/{date}` — specific date
- `GET /api/results/{group}/company/{ticker}` — single company decision

**Nothing left to do for this step.**

---

### Step 7 ✅ — Analysis API + SSE stream (`routes/analysis.py`)

**Done:**
- `POST /api/analyze/{group}` — fire-and-wait (used by scheduler), returns
  full `GroupReportData`.
- `GET /api/analyze/{group}/stream` — SSE stream; starts analysis in thread
  pool via `anyio.to_thread.run_sync`, pushes `progress` events via
  `loop.call_soon_threadsafe(queue.put_nowait, event)`, emits `done` on
  completion, handles client disconnect gracefully (pipeline continues).
- `GET /api/analyze/running` — list of currently running group names.

SSE event format: `{ticker, step, index, total}` for `progress` events;
`{group, date}` for `done`; `{message}` for `error`.

Both endpoints return 409 if the group is already running.

**Nothing left to do for this step.**

---

### Step 8 ✅ — Scheduler (`api/scheduler.py`)

**Done:** `APScheduler BackgroundScheduler` with `CronTrigger`.

- Default schedule: 07:00 local time (override with `SCHEDULER_HOUR` /
  `SCHEDULER_MINUTE` env vars).
- Enable/disable with `SCHEDULER_ENABLED=true/false` (default true).
- `get_scheduler_status()` returns hour, minute, next_run ISO timestamp.
- `update_schedule(hour, minute)` hot-reschedules without restart.
- Registered via FastAPI `lifespan` context manager in `main.py`.

**Nothing left to do for this step.**

---

### Step 9 ✅ — Settings API (`routes/settings.py`)

**Done:**
- `GET /api/settings` — returns API key status (masked), default_years,
  schedule time, scheduler enabled flag.
- `PATCH /api/settings` — updates default_years (saves to toml) and/or
  schedule time (hot-reschedules).

API keys never returned in plain text — only `"set"` / `"not set"`.

**Nothing left to do for this step.**

---

## Phase 3 — React frontend

### Step 10 ✅ — Vite project setup + dev proxy

**Done:** Created `webapp/` with full Vite + React scaffold (no `npm create vite`
scaffolding needed — all files written directly).

Files: `package.json`, `vite.config.js`, `index.html`, `src/main.jsx`, `src/App.jsx`,
`src/api/client.js`, `src/styles/global.css`.

Vite proxy configured: `/api/*` → `http://localhost:8000` in dev.
`@tanstack/react-query` for data fetching, `react-router-dom` for routing,
`recharts` for charts. Dark theme CSS variables in `global.css`.

`npm install` succeeded. `npm run build` produces clean `webapp/dist/`.

**Nothing left to do for this step.**

---

### Step 11 ✅ — Dashboard page

**Done:** `src/pages/Dashboard.jsx` + `Dashboard.module.css`.

- Sidebar lists all configured groups; clicking selects it.
- Main area shows leaderboard for the selected group with "last updated" date.
- **Run now** button opens the ProgressPanel (SSE stream).
- Empty state when no results yet.
- After run completes, React Query cache is invalidated and leaderboard refreshes.

**Nothing left to do for this step.**

---

### Step 12 ✅ — Group report page

**Done:** `src/pages/GroupReport.jsx` + `GroupReport.module.css`.

Three tabs:
1. **Leaderboard** — clickable rows navigate to CompanyDetail.
2. **KPI Comparison** — side-by-side values + horizontal mini bar chart per metric
   (Revenue Growth, Gross/Operating/Net/FCF Margin, P/E, EV/EBITDA, ROIC, ROE,
   FCF Yield, Debt/Equity) using `kpi_values` from the stored result.
3. **Summaries** — accordion cards (one per company, sorted by rank).

**Note:** `GroupReportData` was extended with `kpi_values: dict[str, dict[str, str]]`
(ticker → raw KPI values from `extract_kpi_values`) so the KPI comparison table has
the underlying numbers, not just pillar scores.

**Nothing left to do for this step.**

---

### Step 13 ✅ — Company detail page

**Done:** `src/pages/CompanyDetail.jsx` + `CompanyDetail.module.css`.

Shows full `InvestmentDecision` for one ticker within a group result:
- Scorecard grid with score bars per pillar + composite
- Valuation vs own history (position, current P/E, historical median, deviation)
- 3-year projection table (base + bull: revenue CAGR, EPS CAGR, P/E, implied price)
- Soft signals (insider, revisions, buybacks) with arrows and detail text
- Conflict flag when signals contradict
- Rationale paragraph
- Three non-removable caveats at the bottom

**Nothing left to do for this step.**

---

### Step 14 ✅ — Live progress UI

**Done:** `src/components/ProgressPanel.jsx` + `ProgressPanel.module.css`.

- Opens as a modal overlay.
- Connects to `GET /api/analyze/{group}/stream` via `EventSource`.
- Shows a progress bar (index/total), current ticker + step label.
- Logs all completed steps in a scrollable list.
- On `done`: calls `onDone()` which triggers React Query cache invalidation.
- On `error`: shows the error message.
- On client close (onClose button): EventSource is cleaned up via `useEffect` return.

**Nothing left to do for this step.**

---

### Step 15 ✅ — Group management UI

**Done:** `src/components/GroupManager.jsx` + `GroupManager.module.css`, embedded
in the Settings page.

- Lists all configured groups with their tickers.
- Remove button (calls `DELETE /api/groups/{name}`, invalidates cache).
- Add/update form: name + comma-separated tickers → `POST /api/groups`.
- Validation: name required, ≥2 tickers.
- Mutations use React Query `useMutation` with automatic invalidation on success.

**Nothing left to do for this step.**

---

### Step 16 ✅ — Scheduler settings UI

**Done:** `src/pages/Settings.jsx` + `Settings.module.css`.

Three cards:
1. **API Keys** — shows "set" / "not set" badges for ANTHROPIC and FMP keys.
2. **Daily Scheduler** — current schedule, default years; editable fields for
   hour/minute/years → `PATCH /api/settings`. Hot-reschedules without restart.
3. **Peer Groups** — embeds `GroupManager` component.

**Nothing left to do for this step.**

---

## Phase 4 — Integration & launch

### Step 17 ✅ — Startup script (`make dev` / `make start`)

**Done:** Updated `Makefile` with:

- `make install` — `pip install -e ".[dev,api]"` + `npm install`
- `make dev` — runs uvicorn (port 8000, `--reload`) and Vite dev server (port 5173)
  in parallel; `trap 'kill 0' INT` ensures both processes die on Ctrl-C.
- `make build` — `npm run build` (outputs to `webapp/dist/`)
- `make start` — builds then runs uvicorn only; FastAPI serves the static bundle
  via `StaticFiles` mount (already wired in `api/main.py`).

Build verified: `npm run build` completes cleanly in 6.6s.

**Nothing left to do for this step.**

---

### Step 18 ✅ — Update tutorial

**Done:** Added **Web App** section at the end of `fundalyzer-tutorial.md` covering:
prerequisites, `make install` / `make dev` / `make start`, page descriptions,
how to run from the UI, daily scheduler behavior, API docs URL, and webapp-specific
env vars (`SCHEDULER_ENABLED`, `SCHEDULER_HOUR`, `SCHEDULER_MINUTE`,
`FUNDALYZER_RESULTS_DIR`).

**Nothing left to do for this step.**

---

## All 18 steps complete ✅

The web app is fully built. To start it:

```bash
cd fundalyzer
make install   # first time
make dev       # open http://localhost:5173
```
