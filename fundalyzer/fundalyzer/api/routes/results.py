from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..store import GroupReportData, latest_result, list_dates, load_result

router = APIRouter(tags=["results"])


@router.get("/results/{group}", response_model=GroupReportData)
def get_latest_result(group: str) -> GroupReportData:
    result = latest_result(group)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No results for group '{group}'")
    return result


@router.get("/results/{group}/dates")
def get_available_dates(group: str) -> list[str]:
    return list_dates(group)


@router.get("/results/{group}/{date}", response_model=GroupReportData)
def get_result_by_date(group: str, date: str) -> GroupReportData:
    result = load_result(group, date)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No result for group '{group}' on {date}")
    return result


@router.get("/results/{group}/company/{ticker}")
def get_company_decision(group: str, ticker: str) -> dict:
    result = latest_result(group)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No results for group '{group}'")
    decision = result.decisions.get(ticker.upper())
    if decision is None:
        raise HTTPException(status_code=404, detail=f"No data for {ticker} in group '{group}'")
    return decision.model_dump(mode="json")
