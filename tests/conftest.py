from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.main import create_app


def _copy_default_rules(target_rules_dir: Path) -> None:
    source = ROOT_DIR / "rules"
    if target_rules_dir.exists():
        shutil.rmtree(target_rules_dir)
    shutil.copytree(source, target_rules_dir)


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    data_dir = tmp_path / "data"
    rules_dir = tmp_path / "rules"
    _copy_default_rules(rules_dir)

    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("RULES_DIR", str(rules_dir))
    monkeypatch.setenv("DB_PATH", str(data_dir / "app.db"))
    monkeypatch.setenv("LOGGING_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("AVAILABLE_MODELS", "gpt-4o-mini,gpt-5.2,gpt-5.3")

    app = create_app(base_dir=ROOT_DIR)
    return TestClient(app)


@pytest.fixture()
def client_no_logging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    data_dir = tmp_path / "data"
    rules_dir = tmp_path / "rules"
    _copy_default_rules(rules_dir)

    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("RULES_DIR", str(rules_dir))
    monkeypatch.setenv("DB_PATH", str(data_dir / "app.db"))
    monkeypatch.setenv("LOGGING_ENABLED", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("AVAILABLE_MODELS", "gpt-4o-mini,gpt-5.2,gpt-5.3")

    app = create_app(base_dir=ROOT_DIR)
    return TestClient(app)
