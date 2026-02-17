# PRD - GPT Cleaner Gateway

Version: 1.1  
Date: February 18, 2026  
Status: Draft  
Authors: Project Team (User + Codex)

## 1. Executive Summary

GPT Cleaner Gateway is a web app proxy between end users and cloud LLM providers.
It sanitizes prompts and attachments before sending data to the model, then optionally reconciles allowed tokens in the output.

The product aims to reduce sensitive data leakage while preserving a familiar chat experience.

## 2. Problem Statement

Teams want to use cloud LLMs without exposing sensitive information.
Main risks:

- accidental disclosure of PII/secrets in prompt text
- sensitive content inside uploaded documents
- lack of visibility into which transformations were applied
- inconsistent policy enforcement across users

## 3. Product Goals

### 3.1 Primary Goals

1. Prevent sensitive data leakage to cloud LLM providers.
2. Keep UX close to standard chat workflows.
3. Support common text-document formats.
4. Enable configurable sanitization policies via rulesets.
5. Provide technical auditability.

### 3.2 MVP Measurable Goals

1. Parsing success on valid supported files >= 95%.
2. Detection/masking for known sensitive patterns >= 99%.
3. Median gateway overhead <= 1.2s (excluding provider latency).
4. No known plaintext leakage for critical patterns during UAT.

### 3.3 Non-Goals (MVP)

1. OCR/image processing.
2. Audio/video processing.
3. Full feature parity with ChatGPT official UI.
4. Enterprise multi-tenant RBAC.

## 4. MVP Scope

### 4.1 In Scope

1. Chat sessions with message history.
2. Model selection per interaction.
3. Supported file upload and text extraction.
4. Rule engine with regex + external term lists.
5. Rules directory and list file browser (list/upload/delete/overwrite).
6. Rules validation and reload.
7. No login in MVP (single-user/local deployment).
8. Tokenization + optional controlled reconciliation.
9. Runtime toggle for persistent logging.
10. Response modes:
   - In chat
   - Same as input
   - Forced output (`txt`, `md`, `docx`, `xlsx`, `csv`)

### 4.2 Out of Scope

1. ML-based entity detection.
2. Advanced visual policy editor.
3. SSO/SAML/SCIM.
4. Dynamic intelligent multi-provider routing.

## 5. Users and Stakeholders

1. End user: sends prompts/files and consumes responses.
2. Security owner: defines rules and policy boundaries.
3. Technical operator: manages runtime, rules, logs, and issues.
4. Product owner: balances usability and risk.

## 6. Main User Journeys

### 6.1 Standard Chat

1. User opens chat.
2. User writes prompt.
3. Gateway sanitizes content and generates tokens.
4. Sanitized payload is sent to provider.
5. Allowed tokens may be reconciled in output.
6. Response is displayed.

### 6.2 Chat with Attachment

1. User uploads supported file.
2. Backend extracts text.
3. Prompt + extracted text are sanitized.
4. Sanitized payload is sent to provider.
5. Response is shown (chat and/or file output mode).

### 6.3 Rules Management

1. Operator opens rules panel.
2. Lists files in rules directory.
3. Uploads/overwrites/deletes files.
4. Validates and reloads rules.
5. Reviews result and audit event.

## 7. Functional Requirements

### 7.1 Chat and Sessions

1. Create/list/delete sessions.
2. Multi-turn context managed by backend.
3. Default model list configurable.
4. Auto-title from first prompt keywords (if default title).

### 7.2 Attachments

1. Supported formats: `.txt`, `.md`, `.docx`, `.pdf`, `.xlsx`, `.csv`.
2. Configurable upload limit (default 20MB).
3. Clear error on unsupported/corrupt file.
4. UTF-8 normalization.

### 7.3 Rule Engine

1. Rules from structured ruleset (`yaml/json`) and external lists.
2. Rule types: regex + list.
3. List formats: `.txt`, `.csv`, `.json`.
4. Priorities and overlap resolution.
5. Modes: report-only/enforce.
6. Validation and safe reload.

### 7.4 Sanitization and Reconciliation

1. Per-rule actions: `replace`, `anagram`, `simple_encrypt`, `tokenize`.
2. Deterministic token placeholders.
3. Secure token mapping storage and TTL.
4. Category-based reconciliation policy.
5. If mapping missing/expired, token remains and warning is recorded.

### 7.5 LLM Gateway

1. OpenAI-compatible provider adapter.
2. Mock mode when API key is missing.
3. No plaintext original payload sent upstream.
4. Output format instruction can be appended automatically based on selected response mode.

### 7.6 Response Output Modes

1. `chat`: response in chat only.
2. `same_as_input`: file generated using first attachment format (if supported).
3. Forced output modes: `txt`, `md`, `docx`, `xlsx`, `csv`.
4. PDF output is not supported (fallback to `.txt`).
5. Generated file is downloadable via API.

### 7.7 Logging and Audit

1. Correlation-enabled technical events.
2. Optional persistent logging (`logging_enabled`).
3. Rules file operations are auditable.

## 8. Non-Functional Requirements

1. Security: encryption at rest for sensitive mappings, secret management, least privilege.
2. Reliability: graceful degradation on parser/provider failure.
3. Performance: sanitization overhead targets as defined in goals.
4. Observability: metrics for rules, parsing, tokenization/reconciliation outcomes.
5. UX: modern minimal interface, light/dark support.

## 9. Privacy and Compliance

1. Data minimization by default.
2. Configurable retention for logs and reversible mappings.
3. Conversation deletion support.
4. Provider/legal compliance to be finalized before production rollout.

## 10. MVP Technical Architecture

1. Frontend static SPA served by backend.
2. FastAPI backend for chat, files, rules, gateway, audits.
3. SQLite persistence for sessions/messages/audit/mappings.
4. Local file storage for uploads/generated outputs.
5. Single-container Docker deployment.

## 11. API Surface (MVP)

1. `GET /health`
2. `GET /api/config`
3. `PUT /api/config`
4. `GET /api/models`
5. `POST /api/chat/sessions`
6. `GET /api/chat/sessions`
7. `DELETE /api/chat/sessions/{session_id}`
8. `GET /api/chat/sessions/{session_id}/messages`
9. `POST /api/chat/sessions/{session_id}/messages`
10. `POST /api/files/upload`
11. `GET /api/files/{file_id}/download`
12. `GET /api/audit/events/{event_id}`
13. `POST /api/rulesets/validate`
14. `POST /api/rules/reload`
15. `GET /api/rules/files`
16. `POST /api/rules/files`
17. `PUT /api/rules/files/{file_id}`
18. `DELETE /api/rules/files/{file_id}`

## 12. Acceptance Criteria (MVP)

1. Sensitive terms are tokenized according to rules before provider call.
2. Chat displays sanitized user content and reconciled assistant content.
3. Rules file management works end-to-end from UI.
4. Output file modes generate downloadable files in expected format.
5. Logging toggle correctly enables/disables persistent audit writes.
6. End-to-end tests pass for core flows.

## 13. Risks

1. False negatives in rule coverage.
2. Latency increase on large attachments.
3. Misconfiguration of reconciliation policy.
4. Insecure local deployment without proper controls.

Mitigation: conservative defaults, validation, tests, and clear operational guidance.

## 14. Milestones

1. M1 - Core backend + sanitization engine.
2. M2 - Frontend chat + file upload + rules panel.
3. M3 - Token reconciliation + output file modes.
4. M4 - Hardening, docs, packaging, release candidate.
