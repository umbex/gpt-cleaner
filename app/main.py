from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings, load_settings
from .db import Database, now_utc
from .file_generators import generate_response_file
from .file_parsers import FileParseError, ensure_allowed_filename, parse_file
from .llm_gateway import LLMGateway, LLMGatewayError
from .rule_engine import RuleEngine
from .schemas import (
    ChatTurnResponse,
    GeneratedFileResponse,
    MessageCreateRequest,
    MessageResponse,
    ModelsResponse,
    RulesFileContentUpdate,
    RulesFileListItem,
    RulesValidateResponse,
    SessionCreateRequest,
    SessionResponse,
    UploadResponse,
)
from .version import APP_VERSION


def _resolve_file_id(rules_dir: Path, file_id: str) -> Path:
    base = rules_dir.resolve()
    candidate = (base / file_id).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path")
    return candidate


def _to_message_response(row: Dict[str, Any]) -> MessageResponse:
    metadata = Database.from_json(row.get("metadata_json"), {})
    display_content = row["sanitized_content"] if row.get("role") == "user" else row["content"]
    return MessageResponse(
        id=row["id"],
        role=row["role"],
        content=display_content,
        created_at=row["created_at"],
        model=row.get("model"),
        metadata=metadata,
    )


_TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
}

def _is_default_session_title(title: str) -> bool:
    normalized = (title or "").strip().casefold()
    return normalized in {"", "new chat"}


_FORCED_OUTPUT_EXTENSIONS = {
    "txt": ".txt",
    "md": ".md",
    "csv": ".csv",
    "docx": ".docx",
    "xlsx": ".xlsx",
}


def _resolve_output_extension(response_mode: str, source_filename: str) -> tuple[str | None, str | None]:
    if response_mode == "chat":
        return None, None
    if response_mode in _FORCED_OUTPUT_EXTENSIONS:
        return _FORCED_OUTPUT_EXTENSIONS[response_mode], None
    if response_mode == "same_as_input":
        suffix = Path(source_filename).suffix.lower()
        if suffix == ".pdf":
            return ".txt", "PDF output is not supported: fallback to .txt"
        if suffix in {".txt", ".md", ".csv", ".docx", ".xlsx"}:
            return suffix, None
        return ".txt", "Input format is not supported for output: fallback to .txt"
    return None, None


def _build_output_format_instruction(extension: str) -> str:
    if extension == ".txt":
        return (
            "Required output format: TXT. Return plain text only, without markdown, "
            "without code blocks, and without introductory text."
        )
    if extension == ".md":
        return (
            "Required output format: Markdown (.md). Return only the final Markdown document, "
            "without additional introductions."
        )
    if extension == ".csv":
        return (
            "Required output format: CSV. Return only valid CSV rows using comma separator, "
            "without comments and without markdown."
        )
    if extension == ".docx":
        return (
            "Required output format: structured textual document for DOCX. "
            "Return only final clean content with headings and paragraphs."
        )
    if extension == ".xlsx":
        return (
            "Required output format: tabular content for XLSX. Return structured rows, "
            "one row per record, without markdown."
        )
    return "Required output format: plain text."


def _build_session_title_from_prompt(prompt: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9À-ÖØ-öø-ÿ]+", prompt or "")
    keywords: list[str] = []
    seen: set[str] = set()

    for token in tokens:
        normalized = token.casefold()
        if len(normalized) <= 2 or normalized in _TITLE_STOPWORDS or normalized in seen:
            continue
        seen.add(normalized)
        keywords.append(token)
        if len(keywords) == 2:
            break

    if not keywords:
        return ""

    return " - ".join(keywords)


def _map_llm_error(exc: LLMGatewayError, model: str) -> HTTPException:
    upstream = exc.upstream_status
    detail = f"LLM provider error for model '{model}'"
    if upstream is not None:
        detail = f"{detail} (upstream status: {upstream})"
    if exc.message:
        detail = f"{detail}: {exc.message}"

    if upstream in {400, 401, 403, 404, 422}:
        return HTTPException(status_code=400, detail=detail)
    if upstream == 429:
        return HTTPException(status_code=429, detail=detail)
    return HTTPException(status_code=502, detail=detail)


def _ensure_default_rules(settings: Settings) -> None:
    settings.rules_dir.mkdir(parents=True, exist_ok=True)
    (settings.rules_dir / "lists").mkdir(parents=True, exist_ok=True)

    if not settings.ruleset_file.exists():
        default_rules = {
            "version": 1,
            "mode": "enforce",
            "never_reconcile_categories": ["PII", "SECRET", "FINANCIAL"],
            "rules": [
                {
                    "id": "email_regex",
                    "type": "regex",
                    "pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
                    "category": "PII",
                    "action": "tokenize",
                    "priority": 120,
                },
                {
                    "id": "phone_regex",
                    "type": "regex",
                    "pattern": r"\b(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}\b",
                    "category": "PII",
                    "action": "tokenize",
                    "priority": 110,
                },
                {
                    "id": "api_key_regex",
                    "type": "regex",
                    "pattern": r"\b(?:sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_\-]{20,})\b",
                    "category": "SECRET",
                    "action": "tokenize",
                    "priority": 130,
                },
            ],
            "lists": [
                {
                    "id": "clients",
                    "source": "lists/clients.txt",
                    "category": "BUSINESS",
                    "action": "tokenize",
                    "priority": 95,
                }
            ],
        }
        try:
            import yaml  # type: ignore

            settings.ruleset_file.write_text(yaml.safe_dump(default_rules, sort_keys=False), encoding="utf-8")
        except Exception:
            settings.ruleset_file.write_text(json.dumps(default_rules, indent=2), encoding="utf-8")

    clients_path = settings.rules_dir / "lists" / "clients.txt"
    if not clients_path.exists():
        clients_path.write_text("ACME S.p.A.\nUmbex SRL\nDemo Client\n", encoding="utf-8")


def create_app(base_dir: Path | None = None) -> FastAPI:
    settings = load_settings(base_dir)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    _ensure_default_rules(settings)

    db = Database(settings.db_path)
    rule_engine = RuleEngine(settings, db)
    llm_gateway = LLMGateway(settings)

    app = FastAPI(title="GPT Cleaner Gateway", version=APP_VERSION)
    app.state.settings = settings
    app.state.db = db
    app.state.rule_engine = rule_engine
    app.state.llm_gateway = llm_gateway

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def disable_frontend_cache(request: Request, call_next):
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    static_dir = settings.root_dir / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok", "version": APP_VERSION}

    @app.get("/")
    def root() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/api/models", response_model=ModelsResponse)
    def list_models() -> ModelsResponse:
        return ModelsResponse(default=settings.default_model, models=settings.available_models)

    @app.get("/api/config")
    def get_config() -> Dict[str, Any]:
        return {
            "app_version": APP_VERSION,
            "logging_enabled": settings.logging_enabled,
            "max_upload_mb": settings.max_upload_mb,
            "default_model": settings.default_model,
            "available_models": settings.available_models,
            "mock_mode": llm_gateway.is_mock_mode,
        }

    @app.put("/api/config")
    def update_config(payload: Dict[str, Any]) -> Dict[str, Any]:
        if "logging_enabled" in payload:
            settings.logging_enabled = bool(payload["logging_enabled"])
        return {"ok": True, "logging_enabled": settings.logging_enabled}

    @app.post("/api/chat/sessions", response_model=SessionResponse)
    def create_session(request: SessionCreateRequest) -> SessionResponse:
        session_id = str(uuid.uuid4())
        created_at = now_utc()
        db.execute(
            "INSERT INTO chat_sessions (id, title, created_at) VALUES (?, ?, ?)",
            (session_id, request.title.strip() or "New chat", created_at),
        )
        return SessionResponse(id=session_id, title=request.title.strip() or "New chat", created_at=created_at)

    @app.get("/api/chat/sessions", response_model=List[SessionResponse])
    def get_sessions() -> List[SessionResponse]:
        rows = db.fetchall("SELECT id, title, created_at FROM chat_sessions ORDER BY created_at DESC")
        return [SessionResponse(**row) for row in rows]

    @app.delete("/api/chat/sessions/{session_id}")
    def delete_session(session_id: str) -> Dict[str, Any]:
        session = db.fetchone("SELECT id FROM chat_sessions WHERE id = ?", (session_id,))
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

        db.execute("DELETE FROM audit_events WHERE session_id = ?", (session_id,))
        db.execute("DELETE FROM token_mappings WHERE session_id = ?", (session_id,))
        db.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
        db.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
        return {"ok": True, "session_id": session_id}

    @app.get("/api/chat/sessions/{session_id}/messages", response_model=List[MessageResponse])
    def get_messages(session_id: str) -> List[MessageResponse]:
        session = db.fetchone("SELECT id FROM chat_sessions WHERE id = ?", (session_id,))
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        rows = db.fetchall(
            "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        )
        return [_to_message_response(row) for row in rows]

    @app.post("/api/files/upload", response_model=UploadResponse)
    async def upload_file(file: UploadFile = File(...)) -> UploadResponse:
        filename = file.filename or "file.txt"
        ensure_allowed_filename(filename)

        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Empty file")

        size_mb = len(raw) / (1024 * 1024)
        if size_mb > settings.max_upload_mb:
            raise HTTPException(status_code=400, detail=f"File exceeds {settings.max_upload_mb}MB limit")

        file_id = str(uuid.uuid4())
        destination = settings.uploads_dir / f"{file_id}{Path(filename).suffix.lower()}"
        destination.write_bytes(raw)

        try:
            extracted = parse_file(destination)
        except FileParseError as exc:
            destination.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        created_at = now_utc()
        db.execute(
            """
            INSERT INTO uploaded_files (id, filename, content_type, path, extracted_text, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                file_id,
                filename,
                file.content_type or "application/octet-stream",
                str(destination),
                extracted,
                created_at,
            ),
        )

        return UploadResponse(
            id=file_id,
            filename=filename,
            content_type=file.content_type or "application/octet-stream",
            chars_extracted=len(extracted),
            created_at=created_at,
        )

    @app.get("/api/files/{file_id}/download")
    def download_file(file_id: str) -> FileResponse:
        row = db.fetchone(
            "SELECT filename, content_type, path FROM uploaded_files WHERE id = ?",
            (file_id,),
        )
        if row is None:
            raise HTTPException(status_code=404, detail="File not found")
        path = Path(row["path"])
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="File is not available in storage")
        return FileResponse(path=str(path), media_type=row["content_type"], filename=row["filename"])

    @app.post("/api/chat/sessions/{session_id}/messages", response_model=ChatTurnResponse)
    def post_message(session_id: str, request: MessageCreateRequest) -> ChatTurnResponse:
        session = db.fetchone("SELECT id, title FROM chat_sessions WHERE id = ?", (session_id,))
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

        model = request.model or settings.default_model
        if model not in settings.available_models:
            raise HTTPException(status_code=400, detail=f"Model not allowed: {model}")

        effective_response_mode = request.response_mode
        if effective_response_mode == "same_as_input" and not request.file_ids:
            effective_response_mode = "chat"
        if effective_response_mode in _FORCED_OUTPUT_EXTENSIONS and not request.file_ids:
            effective_response_mode = "chat"

        attachment_chunks: list[str] = []
        first_attachment_filename = ""
        for file_id in request.file_ids:
            file_row = db.fetchone("SELECT filename, extracted_text FROM uploaded_files WHERE id = ?", (file_id,))
            if file_row is None:
                raise HTTPException(status_code=404, detail=f"Attachment not found: {file_id}")
            if not first_attachment_filename:
                first_attachment_filename = file_row["filename"]
            attachment_chunks.append(
                f"\n\n[ALLEGATO: {file_row['filename']}]\n{file_row['extracted_text']}"
            )

        output_extension, mode_warning = _resolve_output_extension(
            effective_response_mode,
            first_attachment_filename,
        )

        original_user_text = request.message + "".join(attachment_chunks)
        sanitized = rule_engine.sanitize(session_id, original_user_text)

        user_count_row = db.fetchone(
            "SELECT COUNT(*) AS total FROM chat_messages WHERE session_id = ? AND role = 'user'",
            (session_id,),
        )
        is_first_user_turn = int((user_count_row or {}).get("total", 0)) == 0
        if is_first_user_turn and _is_default_session_title(session["title"]):
            generated_title = _build_session_title_from_prompt(request.message)
            if generated_title:
                db.execute(
                    "UPDATE chat_sessions SET title = ? WHERE id = ?",
                    (generated_title, session_id),
                )

        user_message_id = str(uuid.uuid4())
        user_created_at = now_utc()
        user_metadata = {
            "sanitized": True,
            "rules_triggered": sanitized.rules_triggered,
            "file_ids": request.file_ids,
            "tokens_created": sanitized.tokens_created,
        }
        db.execute(
            """
            INSERT INTO chat_messages (id, session_id, role, content, sanitized_content, model, created_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_message_id,
                session_id,
                "user",
                original_user_text,
                sanitized.sanitized_text,
                model,
                user_created_at,
                Database.to_json(user_metadata),
            ),
        )

        history_rows = db.fetchall(
            "SELECT role, sanitized_content FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        )
        provider_messages = [
            {"role": row["role"], "content": row["sanitized_content"]}
            for row in history_rows
        ]
        if output_extension:
            provider_messages.append(
                {"role": "system", "content": _build_output_format_instruction(output_extension)}
            )

        try:
            llm_raw_response, usage = llm_gateway.chat(provider_messages, model)
        except LLMGatewayError as exc:
            raise _map_llm_error(exc, model) from exc
        assistant_content, tokens_reconciled, missing_tokens = rule_engine.reconcile(
            session_id, llm_raw_response
        )

        generated_file_payload: GeneratedFileResponse | None = None
        generated_file_warning: str | None = None
        if output_extension and request.file_ids:
            source_row = db.fetchone(
                "SELECT id, filename FROM uploaded_files WHERE id = ?",
                (request.file_ids[0],),
            )
            if source_row is not None:
                generated_file_id = str(uuid.uuid4())
                generated = generate_response_file(
                    output_dir=settings.uploads_dir,
                    source_filename=source_row["filename"],
                    content=assistant_content,
                    file_id=generated_file_id,
                    output_extension=output_extension,
                )
                warnings = [warning for warning in [mode_warning, generated.warning] if warning]
                generated_file_warning = "; ".join(warnings) if warnings else None
                created_at = now_utc()
                db.execute(
                    """
                    INSERT INTO uploaded_files (id, filename, content_type, path, extracted_text, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        generated_file_id,
                        generated.filename,
                        generated.content_type,
                        str(generated.path),
                        assistant_content,
                        created_at,
                    ),
                )
                size = generated.path.stat().st_size if generated.path.exists() else 0
                generated_file_payload = GeneratedFileResponse(
                    id=generated_file_id,
                    filename=generated.filename,
                    content_type=generated.content_type,
                    size=size,
                    download_url=f"/api/files/{generated_file_id}/download",
                    source_file_id=source_row["id"],
                    mode=effective_response_mode,
                )

        assistant_message_id = str(uuid.uuid4())
        assistant_created_at = now_utc()
        assistant_metadata = {
            "reconciled": True,
            "tokens_reconciled": tokens_reconciled,
            "missing_tokens": missing_tokens,
            "provider_usage": usage,
            "mock_mode": llm_gateway.is_mock_mode,
            "response_mode": effective_response_mode,
            "generated_file_id": generated_file_payload.id if generated_file_payload else None,
            "generated_file_warning": generated_file_warning,
        }
        db.execute(
            """
            INSERT INTO chat_messages (id, session_id, role, content, sanitized_content, model, created_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                assistant_message_id,
                session_id,
                "assistant",
                assistant_content,
                llm_raw_response,
                model,
                assistant_created_at,
                Database.to_json(assistant_metadata),
            ),
        )

        audit_id = None
        if settings.logging_enabled:
            audit_id = str(uuid.uuid4())
            details = {
                "model": model,
                "llm_usage": usage,
                "missing_tokens": missing_tokens,
                "file_ids": request.file_ids,
                "response_mode": effective_response_mode,
                "output_extension": output_extension,
            }
            db.execute(
                """
                INSERT INTO audit_events (
                    id, created_at, session_id, message_id, correlation_id,
                    rules_triggered_json, transformations, tokens_created, tokens_reconciled,
                    original_hash, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit_id,
                    now_utc(),
                    session_id,
                    user_message_id,
                    str(uuid.uuid4()),
                    Database.to_json(sanitized.rules_triggered),
                    sanitized.transformations,
                    sanitized.tokens_created,
                    tokens_reconciled,
                    sanitized.original_hash,
                    Database.to_json(details),
                ),
            )

        user_response = MessageResponse(
            id=user_message_id,
            role="user",
            content=sanitized.sanitized_text,
            created_at=user_created_at,
            model=model,
            metadata=user_metadata,
        )
        assistant_response = MessageResponse(
            id=assistant_message_id,
            role="assistant",
            content=assistant_content,
            created_at=assistant_created_at,
            model=model,
            metadata=assistant_metadata,
        )

        return ChatTurnResponse(
            session_id=session_id,
            user_message=user_response,
            assistant_message=assistant_response,
            sanitization={
                "rules_triggered": sanitized.rules_triggered,
                "transformations": sanitized.transformations,
                "tokens_created": sanitized.tokens_created,
                "tokens_reconciled": tokens_reconciled,
                "logging_enabled": settings.logging_enabled,
                "response_mode": effective_response_mode,
            },
            audit_id=audit_id,
            generated_file=generated_file_payload,
        )

    @app.get("/api/audit/events/{event_id}")
    def get_audit_event(event_id: str) -> Dict[str, Any]:
        if not settings.logging_enabled:
            raise HTTPException(status_code=404, detail="Logging is disabled")

        row = db.fetchone("SELECT * FROM audit_events WHERE id = ?", (event_id,))
        if row is None:
            raise HTTPException(status_code=404, detail="Audit event not found")

        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "session_id": row["session_id"],
            "message_id": row["message_id"],
            "correlation_id": row["correlation_id"],
            "rules_triggered": Database.from_json(row["rules_triggered_json"], []),
            "transformations": row["transformations"],
            "tokens_created": row["tokens_created"],
            "tokens_reconciled": row["tokens_reconciled"],
            "original_hash": row["original_hash"],
            "details": Database.from_json(row["details_json"], {}),
        }

    @app.post("/api/rulesets/validate", response_model=RulesValidateResponse)
    def validate_ruleset() -> RulesValidateResponse:
        ok, rule_count, list_count, message = rule_engine.validate()
        return RulesValidateResponse(ok=ok, rule_count=rule_count, list_count=list_count, message=message)

    @app.post("/api/rules/reload", response_model=RulesValidateResponse)
    def reload_rules() -> RulesValidateResponse:
        ok, rule_count, list_count, message = rule_engine.validate()
        return RulesValidateResponse(ok=ok, rule_count=rule_count, list_count=list_count, message=message)

    @app.get("/api/rules/files", response_model=List[RulesFileListItem])
    def list_rule_files(subdir: str = Query(default="lists")) -> List[RulesFileListItem]:
        target_dir = _resolve_file_id(settings.rules_dir, subdir)
        if not target_dir.exists():
            return []

        items: list[RulesFileListItem] = []
        for file_path in sorted(target_dir.iterdir()):
            if not file_path.is_file():
                continue
            relative = str(file_path.relative_to(settings.rules_dir))
            stat = file_path.stat()
            items.append(
                RulesFileListItem(
                    file_id=relative,
                    name=file_path.name,
                    size=stat.st_size,
                    updated_at=stat.st_mtime,
                )
            )
        return items

    @app.post("/api/rules/files", response_model=RulesFileListItem)
    async def upload_rule_file(
        file: UploadFile = File(...),
        overwrite: bool = Query(default=False),
        subdir: str = Query(default="lists"),
    ) -> RulesFileListItem:
        filename = file.filename or "list.txt"
        if Path(filename).suffix.lower() not in {".txt", ".csv", ".json", ".yaml", ".yml"}:
            raise HTTPException(status_code=400, detail="Extension not allowed for rules file")

        target_dir = _resolve_file_id(settings.rules_dir, subdir)
        target_dir.mkdir(parents=True, exist_ok=True)
        destination = _resolve_file_id(settings.rules_dir, str(Path(subdir) / Path(filename).name))

        if destination.exists() and not overwrite:
            raise HTTPException(status_code=409, detail="File already exists. Use overwrite=true")

        content = await file.read()
        destination.write_bytes(content)

        stat = destination.stat()
        return RulesFileListItem(
            file_id=str(destination.relative_to(settings.rules_dir)),
            name=destination.name,
            size=stat.st_size,
            updated_at=stat.st_mtime,
        )

    @app.get("/api/rules/files/{file_id:path}/download")
    def download_rule_file(file_id: str) -> FileResponse:
        destination = _resolve_file_id(settings.rules_dir, file_id)
        if not destination.exists() or not destination.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(path=str(destination), filename=destination.name)

    @app.put("/api/rules/files/{file_id:path}", response_model=RulesFileListItem)
    def overwrite_rule_file(file_id: str, payload: RulesFileContentUpdate) -> RulesFileListItem:
        destination = _resolve_file_id(settings.rules_dir, file_id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(payload.content, encoding="utf-8")
        stat = destination.stat()
        return RulesFileListItem(
            file_id=str(destination.relative_to(settings.rules_dir)),
            name=destination.name,
            size=stat.st_size,
            updated_at=stat.st_mtime,
        )

    @app.delete("/api/rules/files/{file_id:path}")
    def delete_rule_file(file_id: str) -> Dict[str, Any]:
        destination = _resolve_file_id(settings.rules_dir, file_id)
        if not destination.exists() or not destination.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        destination.unlink(missing_ok=True)
        return {"ok": True, "file_id": file_id}

    return app


app = create_app()
