"""Tracks in-progress group analysis runs to prevent duplicates.

Thread-safe: used from both async FastAPI routes (via anyio worker threads)
and APScheduler background threads.
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_running: set[str] = set()


def try_acquire(group_name: str) -> bool:
    """Mark group as running.  Returns True if acquired, False if already running."""
    with _lock:
        if group_name in _running:
            return False
        _running.add(group_name)
        return True


def release(group_name: str) -> None:
    with _lock:
        _running.discard(group_name)


def is_running(group_name: str) -> bool:
    with _lock:
        return group_name in _running


def all_running() -> list[str]:
    with _lock:
        return list(_running)
