from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Set


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _as_list(value: str | None, default: List[str]) -> List[str]:
    if value is None or not value.strip():
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(slots=True)
class Settings:
    root_dir: Path
    data_dir: Path
    uploads_dir: Path
    rules_dir: Path
    ruleset_file: Path
    db_path: Path
    max_upload_mb: int
    logging_enabled: bool
    available_models: List[str]
    default_model: str
    openai_api_key: str
    openai_base_url: str
    token_secret: str
    token_ttl_days: int
    never_reconcile_categories: Set[str]


def load_settings(base_dir: Path | None = None) -> Settings:
    root = base_dir or Path.cwd()
    data_dir = Path(os.getenv("DATA_DIR", str(root / "data")))
    rules_dir = Path(os.getenv("RULES_DIR", str(root / "rules")))
    uploads_dir = Path(os.getenv("UPLOADS_DIR", str(data_dir / "uploads")))
    db_path = Path(os.getenv("DB_PATH", str(data_dir / "app.db")))
    ruleset_file = Path(os.getenv("RULESET_FILE", str(rules_dir / "ruleset.yaml")))

    models = _as_list(
        os.getenv("AVAILABLE_MODELS"),
        ["gpt-4o-mini", "gpt-5.2", "gpt-5.3"],
    )
    default_model = os.getenv("DEFAULT_MODEL", models[0])

    never_reconcile = set(
        _as_list(
            os.getenv("NEVER_RECONCILE_CATEGORIES"),
            ["PII", "SECRET", "FINANCIAL"],
        )
    )

    return Settings(
        root_dir=root,
        data_dir=data_dir,
        uploads_dir=uploads_dir,
        rules_dir=rules_dir,
        ruleset_file=ruleset_file,
        db_path=db_path,
        max_upload_mb=_as_int(os.getenv("MAX_UPLOAD_MB"), 20),
        logging_enabled=_as_bool(os.getenv("LOGGING_ENABLED"), True),
        available_models=models,
        default_model=default_model,
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_base_url=os.getenv("OPENAI_BASE_URL", ""),
        token_secret=os.getenv("TOKEN_SECRET", "local-dev-secret"),
        token_ttl_days=_as_int(os.getenv("TOKEN_TTL_DAYS"), 7),
        never_reconcile_categories=never_reconcile,
    )
