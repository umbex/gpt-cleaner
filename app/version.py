from __future__ import annotations

from pathlib import Path


DEFAULT_APP_VERSION = "0.2.0"


def get_app_version() -> str:
    root_dir = Path(__file__).resolve().parents[1]
    version_file = root_dir / "VERSION"
    if not version_file.exists():
        return DEFAULT_APP_VERSION
    value = version_file.read_text(encoding="utf-8").strip()
    return value or DEFAULT_APP_VERSION


APP_VERSION = get_app_version()
