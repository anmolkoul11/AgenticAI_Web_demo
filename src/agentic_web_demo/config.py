"""Small, side-effect-free configuration for the foundation checkpoint."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Non-secret settings; relative data paths resolve from the working directory."""

    data_dir: Path
    log_level: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if environ is None else environ
        data_dir = values.get("AGENTIC_DEMO_DATA_DIR", "./data").strip()
        log_level = values.get("AGENTIC_DEMO_LOG_LEVEL", "INFO").strip().upper()
        if not data_dir:
            raise ValueError("AGENTIC_DEMO_DATA_DIR must not be empty")
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("AGENTIC_DEMO_LOG_LEVEL must be a standard logging level")
        return cls(data_dir=Path(data_dir), log_level=log_level)
