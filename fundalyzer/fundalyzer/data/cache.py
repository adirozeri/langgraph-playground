import json
from datetime import date
from pathlib import Path
from typing import Any, Protocol


class Cache(Protocol):
    def get(self, ticker: str, endpoint: str) -> Any | None: ...
    def set(self, ticker: str, endpoint: str, data: Any) -> None: ...


class DiskCache:
    """JSON cache keyed by (ticker, endpoint, today's date).

    One calendar day = one cache entry; stale entries from prior days are
    ignored automatically (new key path) and left for manual cleanup.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._dir = cache_dir or Path.home() / ".cache" / "fundalyzer"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, ticker: str, endpoint: str) -> Path:
        today = date.today().isoformat()
        safe = ticker.upper().replace("/", "_").replace(".", "_")
        return self._dir / safe / today / f"{endpoint}.json"

    def get(self, ticker: str, endpoint: str) -> Any | None:
        p = self._path(ticker, endpoint)
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def set(self, ticker: str, endpoint: str, data: Any) -> None:
        p = self._path(ticker, endpoint)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data), encoding="utf-8")


class NullCache:
    """No-op cache for tests and CI — never stores or returns anything."""

    def get(self, ticker: str, endpoint: str) -> None:
        return None

    def set(self, ticker: str, endpoint: str, data: Any) -> None:
        pass


class ReadonlyCache:
    """Dry-run cache — reads from an underlying cache, never fetches live.

    Raises NoCachedDataError when the requested data is not cached, so
    the caller can surface a helpful message instead of making a live request.
    """

    def __init__(self, inner: DiskCache) -> None:
        self._inner = inner

    def get(self, ticker: str, endpoint: str) -> Any | None:
        data = self._inner.get(ticker, endpoint)
        if data is None:
            from .errors import NoCachedDataError
            raise NoCachedDataError(ticker, endpoint)
        return data

    def set(self, ticker: str, endpoint: str, data: Any) -> None:
        pass  # dry-run: never write
