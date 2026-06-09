from __future__ import annotations

from filelock import FileLock
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..dependencies import get_config, get_config_path
from ..scheduler import get_scheduler_status, update_schedule
from ...settings import settings

router = APIRouter(tags=["settings"])


class SettingsResponse(BaseModel):
    anthropic_api_key: str   # "set" or "not set"
    fmp_api_key: str         # "set" or "not set"
    default_years: int
    schedule_hour: int
    schedule_minute: int
    scheduler_enabled: bool


class SettingsPatch(BaseModel):
    default_years: int | None = None
    schedule_hour: int | None = None
    schedule_minute: int | None = None


@router.get("/settings", response_model=SettingsResponse)
def get_settings(cfg=Depends(get_config)) -> SettingsResponse:
    sched = get_scheduler_status()
    return SettingsResponse(
        anthropic_api_key="set" if settings.anthropic_api_key else "not set",
        fmp_api_key="set" if settings.fmp_api_key else "not set",
        default_years=cfg.default_years,
        schedule_hour=sched["hour"],
        schedule_minute=sched["minute"],
        scheduler_enabled=sched["enabled"],
    )


@router.patch("/settings")
def patch_settings(
    body: SettingsPatch,
    cfg=Depends(get_config),
    config_path=Depends(get_config_path),
) -> dict:
    with FileLock(str(config_path) + ".lock"):
        if body.default_years is not None:
            cfg.set_default_years(body.default_years)
        cfg.save(config_path)

    if body.schedule_hour is not None or body.schedule_minute is not None:
        sched = get_scheduler_status()
        update_schedule(
            hour=body.schedule_hour if body.schedule_hour is not None else sched["hour"],
            minute=body.schedule_minute if body.schedule_minute is not None else sched["minute"],
        )

    return {"status": "ok"}
