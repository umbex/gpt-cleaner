from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel):
    title: str = Field(default="New chat")


class SessionResponse(BaseModel):
    id: str
    title: str
    created_at: str


class MessageCreateRequest(BaseModel):
    message: str = Field(min_length=1)
    model: Optional[str] = None
    file_ids: List[str] = Field(default_factory=list)
    response_mode: Literal[
        "chat",
        "same_as_input",
        "txt",
        "md",
        "docx",
        "xlsx",
        "csv",
    ] = "chat"


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: str
    model: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GeneratedFileResponse(BaseModel):
    id: str
    filename: str
    content_type: str
    size: int
    download_url: str
    source_file_id: str
    mode: str


class ChatTurnResponse(BaseModel):
    session_id: str
    user_message: MessageResponse
    assistant_message: MessageResponse
    sanitization: Dict[str, Any]
    audit_id: Optional[str] = None
    generated_file: Optional[GeneratedFileResponse] = None


class UploadResponse(BaseModel):
    id: str
    filename: str
    content_type: str
    chars_extracted: int
    created_at: str


class RulesValidateResponse(BaseModel):
    ok: bool
    rule_count: int
    list_count: int
    message: str


class RulesFileListItem(BaseModel):
    file_id: str
    name: str
    size: int
    updated_at: float


class RulesFileContentUpdate(BaseModel):
    content: str


class ModelsResponse(BaseModel):
    default: str
    models: List[str]
