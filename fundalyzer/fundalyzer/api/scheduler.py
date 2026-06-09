"""APScheduler daily analysis job.

Runs execute_group_analysis for every configured group at the scheduled
time.  Schedule defaults to 07:00 local time; override with
SCHEDULER_HOUR / SCHEDULER_MINUTE env vars.
"""
from __future__ import annotations

import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

log = logging.getLogger(__name__)

_scheduler = BackgroundScheduler()
_JOB_ID = "daily_group_analysis"

_schedule_hour = int(os.environ.get("SCHEDULER_HOUR", "7"))
_schedule_minute = int(os.environ.get("SCHEDULER_MINUTE", "0"))
_scheduler_enabled = os.environ.get("SCHEDULER_ENABLED", "true").lower() == "true"


def _run_all_groups() -> None:
    from .dependencies import get_config
    from .runner import execute_group_analysis
    from .store import save_result
    from ._running import try_acquire, release

    cfg = get_config()
    groups = cfg.all_groups()
    log.info("Scheduler: running analysis for %d groups", len(groups))

    for name, tickers in groups.items():
        if not try_acquire(name):
            log.warning("Scheduler: skipping %s — already running", name)
            continue
        try:
            result = execute_group_analysis(name, tickers, annual_years=cfg.default_years)
            save_result(name, result)
            log.info("Scheduler: completed %s", name)
        except Exception as exc:
            log.exception("Scheduler: failed for group %s: %s", name, exc)
        finally:
            release(name)


def start_scheduler() -> None:
    if not _scheduler_enabled:
        log.info("Scheduler disabled (SCHEDULER_ENABLED != true)")
        return
    if _scheduler.running:
        return
    _scheduler.add_job(
        _run_all_groups,
        CronTrigger(hour=_schedule_hour, minute=_schedule_minute),
        id=_JOB_ID,
        replace_existing=True,
    )
    _scheduler.start()
    log.info("Scheduler started — daily at %02d:%02d", _schedule_hour, _schedule_minute)


def get_scheduler_status() -> dict:
    job = _scheduler.get_job(_JOB_ID) if _scheduler.running else None
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else None
    return {
        "enabled": _scheduler_enabled,
        "running": _scheduler.running,
        "hour": _schedule_hour,
        "minute": _schedule_minute,
        "next_run": next_run,
    }


def update_schedule(hour: int, minute: int) -> None:
    global _schedule_hour, _schedule_minute
    _schedule_hour = hour
    _schedule_minute = minute
    if _scheduler.running:
        _scheduler.reschedule_job(
            _JOB_ID,
            trigger=CronTrigger(hour=hour, minute=minute),
        )
