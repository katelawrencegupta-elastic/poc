"""Minimal .env loader (no third-party dependency)."""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str | Path | None = None) -> Path | None:
    """Load KEY=VALUE pairs into os.environ if the file exists. Does not override."""
    candidates: list[Path] = []
    if path is not None:
        candidates.append(Path(path))
    else:
        cwd = Path.cwd() / ".env"
        pkg_root = Path(__file__).resolve().parent.parent / ".env"
        candidates.extend([cwd, pkg_root])

    for candidate in candidates:
        if not candidate.is_file():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = value
        return candidate
    return None
