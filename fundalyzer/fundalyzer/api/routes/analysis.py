from __future__ import annotations

import asyncio
import json
import logging

import anyio
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from .._running import is_running, release, try_acquire
from ..dependencies import get_config
from ..runner import execute_group_analysis
from ..store import GroupReportData, save_result

router = APIRouter(tags=["analysis"])
log = logging.getLogger(__name__)


def _get_tickers(group: str, cfg) -> list[str]:
    tickers = cfg.group(group)
    if tickers is None:
        raise HTTPException(status_code=404, detail=f"Group '{group}' not found in config")
    if len(tickers) < 2:
        raise HTTPException(status_code=422, detail="Group needs at least 2 tickers")
    return tickers


# ── Fire-and-wait endpoint (used by scheduler) ────────────────────────────────

@router.post("/analyze/{group}", response_model=GroupReportData)
async def run_analysis(group: str, cfg=Depends(get_config)) -> GroupReportData:
    tickers = _get_tickers(group, cfg)
    if not try_acquire(group):
        raise HTTPException(status_code=409, detail=f"Analysis already running for '{group}'")
    try:
        result = await anyio.to_thread.run_sync(
            lambda: execute_group_analysis(group, tickers)
        )
        save_result(group, result)
        return result
    finally:
        release(group)


# ── SSE streaming endpoint (used by the UI Run-now button) ────────────────────

@router.get("/analyze/{group}/stream")
async def stream_analysis(group: str, cfg=Depends(get_config)) -> StreamingResponse:
    tickers = _get_tickers(group, cfg)

    if not try_acquire(group):
        async def already_running():
            yield f"event: error\ndata: {json.dumps({'message': 'Analysis already running for ' + group})}\n\n"
        return StreamingResponse(already_running(), media_type="text/event-stream")

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue[dict] = asyncio.Queue()

    def progress_callback(ticker: str, step: str, index: int, total: int) -> None:
        loop.call_soon_threadsafe(
            queue.put_nowait,
            {"ticker": ticker, "step": step, "index": index, "total": total},
        )

    async def generate():
        task = asyncio.create_task(
            anyio.to_thread.run_sync(
                lambda: execute_group_analysis(group, tickers, progress_callback=progress_callback)
            )
        )

        try:
            while not task.done():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25.0)
                    yield f"event: progress\ndata: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"

            # Drain any remaining events
            while not queue.empty():
                event = queue.get_nowait()
                yield f"event: progress\ndata: {json.dumps(event)}\n\n"

            result = task.result()
            save_result(group, result)
            yield f"event: done\ndata: {json.dumps({'group': group, 'date': result.run_date})}\n\n"

        except (asyncio.CancelledError, GeneratorExit):
            log.info("SSE client disconnected for group %s — pipeline continues", group)
        except Exception as exc:
            log.exception("Analysis stream failed for group %s", group)
            yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"
        finally:
            release(group)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Status endpoint ───────────────────────────────────────────────────────────

@router.get("/analyze/running")
def get_running() -> list[str]:
    from .._running import all_running
    return all_running()
