"""Local API configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    workspace: Path
    database: Path
    allowed_origins: tuple[str, ...]


def load_settings() -> Settings:
    workspace = Path(os.getenv("DATAPILOT_WORKSPACE", ".datapilot")).resolve()
    database = Path(os.getenv("DATAPILOT_DATABASE", str(workspace / "metadata.sqlite3"))).resolve()
    origins = tuple(
        value.strip()
        for value in os.getenv(
            "DATAPILOT_ALLOWED_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if value.strip()
    )
    return Settings(workspace, database, origins)
