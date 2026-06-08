"""Config file loader for fundalyzer.

Searches for ``fundalyzer.toml`` in the current directory first, then
``~/.config/fundalyzer/config.toml``.  Returns an empty config dict when
neither file exists — every field has a safe default.

Config format (TOML):

    [defaults]
    years = 5

    # Default peer sets, keyed by ticker symbol.
    # Peers listed here are used when --peers is omitted on the CLI.
    [peers]
    AAPL = ["MSFT", "GOOGL", "META", "AMZN"]
    MSFT = ["AAPL", "GOOGL", "META", "ORCL"]
    GOOGL = ["META", "MSFT", "AAPL", "SNAP"]

    # Sector-level fallback: used when a ticker is not listed individually.
    [sector_peers]
    Technology = ["AAPL", "MSFT", "GOOGL", "META", "AMZN", "NVDA"]
    Healthcare = ["JNJ", "MRK", "PFE", "ABT", "AMGN"]
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_CONFIG_SEARCH_PATHS = [
    Path("fundalyzer.toml"),
    Path.home() / ".config" / "fundalyzer" / "config.toml",
]


def _load_toml(path: Path) -> dict[str, Any]:
    if sys.version_info >= (3, 11):
        import tomllib
        return tomllib.loads(path.read_text(encoding="utf-8"))
    # Python < 3.11 fallback — try tomli third-party library
    try:
        import tomli  # type: ignore[import]
        return tomli.loads(path.read_text(encoding="utf-8"))
    except ImportError:
        # No TOML parser available; return empty config.
        return {}


class FundalyzerConfig:
    """Parsed configuration with typed accessors."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self._raw = raw

    # ── Accessors ─────────────────────────────────────────────────────────────

    @property
    def default_years(self) -> int:
        return int(self._raw.get("defaults", {}).get("years", 5))

    def peers_for(self, ticker: str) -> list[str] | None:
        """Return the configured peer list for *ticker*, or None if not set."""
        ticker = ticker.upper()
        peers_map: dict[str, list[str]] = self._raw.get("peers", {})
        # Normalise keys to uppercase so the config file can use any casing.
        upper_map = {k.upper(): v for k, v in peers_map.items()}
        if ticker in upper_map:
            return [p.upper() for p in upper_map[ticker] if p.upper() != ticker]
        return None

    def sector_peers(self, sector: str) -> list[str]:
        sp: dict[str, list[str]] = self._raw.get("sector_peers", {})
        return [p.upper() for p in sp.get(sector, [])]

    def all_peers(self) -> dict[str, list[str]]:
        return {k.upper(): [p.upper() for p in v]
                for k, v in self._raw.get("peers", {}).items()}

    def group(self, name: str) -> list[str] | None:
        """Return the ticker list for a named group, or None if not configured."""
        groups: dict[str, list[str]] = self._raw.get("groups", {})
        lower_map = {k.lower(): v for k, v in groups.items()}
        tickers = lower_map.get(name.lower())
        if tickers is None:
            return None
        return [t.upper() for t in tickers]

    def all_groups(self) -> dict[str, list[str]]:
        return {k: [t.upper() for t in v]
                for k, v in self._raw.get("groups", {}).items()}


_EMPTY = FundalyzerConfig({})


def load_config(path: Path | None = None) -> FundalyzerConfig:
    """Load and return the first config file found, or an empty config."""
    candidates = [path] if path is not None else _CONFIG_SEARCH_PATHS
    for candidate in candidates:
        if candidate and candidate.exists():
            try:
                raw = _load_toml(candidate)
                return FundalyzerConfig(raw)
            except Exception:
                pass
    return _EMPTY
