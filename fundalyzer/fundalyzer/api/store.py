"""Result persistence — one JSON file per group per date.

Storage layout:
    ~/.local/share/fundalyzer/results/
        big_tech/
            2026-06-08.json
            2026-06-09.json
        financials/
            2026-06-08.json
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

from ..decide.models import InvestmentDecision
from ..group.models import GroupRanking

STORE_DIR = Path(os.environ.get("FUNDALYZER_RESULTS_DIR", "")) or (
    Path.home() / ".local" / "share" / "fundalyzer" / "results"
)


class GroupReportData(BaseModel):
    group_name: str
    run_date: str                               # ISO date e.g. "2026-06-08"
    ranking: GroupRanking
    decisions: dict[str, InvestmentDecision]    # ticker → full decision
    kpi_values: dict[str, dict[str, str]]       # ticker → {kpi_name → raw value string}


# ── Write ─────────────────────────────────────────────────────────────────────

def save_result(group_name: str, data: GroupReportData) -> Path:
    group_dir = STORE_DIR / group_name
    group_dir.mkdir(parents=True, exist_ok=True)
    path = group_dir / f"{data.run_date}.json"
    path.write_text(data.model_dump_json(), encoding="utf-8")
    return path


# ── Read ──────────────────────────────────────────────────────────────────────

def load_result(group_name: str, date: str) -> GroupReportData | None:
    path = STORE_DIR / group_name / f"{date}.json"
    if not path.exists():
        return None
    return GroupReportData.model_validate_json(path.read_text(encoding="utf-8"))


def latest_result(group_name: str) -> GroupReportData | None:
    dates = list_dates(group_name)
    if not dates:
        return None
    return load_result(group_name, max(dates))


def list_dates(group_name: str) -> list[str]:
    group_dir = STORE_DIR / group_name
    if not group_dir.exists():
        return []
    return sorted(p.stem for p in group_dir.iterdir() if p.suffix == ".json")


def list_groups_with_results() -> list[str]:
    if not STORE_DIR.exists():
        return []
    return sorted(p.name for p in STORE_DIR.iterdir() if p.is_dir())
