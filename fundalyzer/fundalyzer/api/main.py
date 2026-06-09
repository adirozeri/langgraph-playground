"""FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routes import analysis, groups, results
from .routes import settings as settings_router
from .scheduler import start_scheduler

WEBAPP_DIST = Path(__file__).parent.parent.parent / "webapp" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield


app = FastAPI(
    title="Fundalyzer API",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(groups.router,          prefix="/api")
app.include_router(results.router,         prefix="/api")
app.include_router(analysis.router,        prefix="/api")
app.include_router(settings_router.router, prefix="/api")

# Serve built React app in production (after `make build`)
if WEBAPP_DIST.exists():
    app.mount("/", StaticFiles(directory=str(WEBAPP_DIST), html=True), name="webapp")
