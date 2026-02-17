from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Database:
    path: Path
    _lock: threading.Lock = field(init=False, repr=False)
    _conn: sqlite3.Connection = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            sanitized_content TEXT NOT NULL,
            model TEXT,
            created_at TEXT NOT NULL,
            metadata_json TEXT,
            FOREIGN KEY(session_id) REFERENCES chat_sessions(id)
        );

        CREATE TABLE IF NOT EXISTS uploaded_files (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            content_type TEXT NOT NULL,
            path TEXT NOT NULL,
            extracted_text TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS token_mappings (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            token TEXT NOT NULL,
            value_hash TEXT NOT NULL,
            original_value_enc TEXT NOT NULL,
            category TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            UNIQUE(session_id, token),
            UNIQUE(session_id, value_hash, category)
        );

        CREATE TABLE IF NOT EXISTS audit_events (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            session_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            correlation_id TEXT NOT NULL,
            rules_triggered_json TEXT NOT NULL,
            transformations INTEGER NOT NULL,
            tokens_created INTEGER NOT NULL,
            tokens_reconciled INTEGER NOT NULL,
            original_hash TEXT NOT NULL,
            details_json TEXT NOT NULL
        );
        """
        with self._lock:
            self._conn.executescript(schema)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
        with self._lock:
            self._conn.execute(query, params)
            self._conn.commit()

    def fetchone(self, query: str, params: tuple[Any, ...] = ()) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(query, params).fetchone()
        if row is None:
            return None
        return dict(row)

    def fetchall(self, query: str, params: tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [dict(item) for item in rows]

    @staticmethod
    def to_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=True)

    @staticmethod
    def from_json(value: str | None, default: Any) -> Any:
        if not value:
            return default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
