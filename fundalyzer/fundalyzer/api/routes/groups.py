from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from filelock import FileLock
from pydantic import BaseModel

from ..dependencies import get_config, get_config_path
from ..store import latest_result, list_dates

router = APIRouter(tags=["groups"])


class GroupIn(BaseModel):
    name: str
    tickers: list[str]


class GroupMeta(BaseModel):
    name: str
    tickers: list[str]
    latest_date: str | None
    available_dates: list[str]


@router.get("/groups")
def list_groups(cfg=Depends(get_config)) -> dict[str, list[str]]:
    return cfg.all_groups()


@router.get("/groups/{name}", response_model=GroupMeta)
def get_group(name: str, cfg=Depends(get_config)) -> GroupMeta:
    tickers = cfg.group(name)
    if tickers is None:
        raise HTTPException(status_code=404, detail=f"Group '{name}' not found")
    dates = list_dates(name)
    return GroupMeta(
        name=name,
        tickers=tickers,
        latest_date=max(dates) if dates else None,
        available_dates=dates,
    )


@router.post("/groups", status_code=status.HTTP_201_CREATED)
def create_or_update_group(
    body: GroupIn,
    cfg=Depends(get_config),
    config_path=Depends(get_config_path),
) -> dict:
    if len(body.tickers) < 2:
        raise HTTPException(status_code=422, detail="A group needs at least 2 tickers")
    with FileLock(str(config_path) + ".lock"):
        cfg.add_group(body.name, body.tickers)
        cfg.save(config_path)
    return {"name": body.name, "tickers": [t.upper() for t in body.tickers]}


@router.delete("/groups/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    name: str,
    cfg=Depends(get_config),
    config_path=Depends(get_config_path),
) -> None:
    if cfg.group(name) is None:
        raise HTTPException(status_code=404, detail=f"Group '{name}' not found")
    with FileLock(str(config_path) + ".lock"):
        cfg.remove_group(name)
        cfg.save(config_path)
