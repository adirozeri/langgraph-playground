"""Shared FastAPI dependencies."""
from __future__ import annotations

from pathlib import Path

from ..config import FundalyzerConfig, load_config

# Always use the user-wide config so it's consistent regardless of cwd.
_CONFIG_PATH = Path.home() / ".config" / "fundalyzer" / "config.toml"


def get_config() -> FundalyzerConfig:
    return load_config(_CONFIG_PATH)


def get_config_path() -> Path:
    return _CONFIG_PATH
