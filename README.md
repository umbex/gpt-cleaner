# GPT Cleaner Gateway

GPT Cleaner Gateway is a web app proxy/gateway for cloud LLMs that sanitizes prompts and attachments before forwarding content to the model.

The goal is to prevent sensitive data leakage while keeping a ChatGPT-like user experience.

## Project Status

- Version: see `VERSION` (Semantic Versioning)
- Changelog: `CHANGELOG.md`
- License: MIT (`LICENSE`)

## Core Features

- Modern chat UI with multi-session support and Light/Dark theme
- Model selector (default: `gpt-4o-mini`, `gpt-4.1-mini`, `gpt-4.1`, `gpt-5-mini`, `gpt-5`, `gpt-5.2`)
- File upload support: `.txt`, `.md`, `.docx`, `.pdf`, `.xlsx`, `.csv`
- Rule engine with:
  - regex rules
  - external list rules from `rules/lists/*`
  - actions: `replace`, `anagram`, `simple_encrypt`, `tokenize`
- Deterministic tokenization with encrypted token mapping per session
- Controlled response reconciliation by category policy
- Rules file manager from UI (list/upload/overwrite/delete/reload)
- Rules list file download by clicking filename
- Response modes:
  - `In chat`
  - `Same as input`
  - `Force .txt`, `Force .md`, `Force .docx`, `Force .xlsx`, `Force .csv`
- Generated output file download (`/api/files/{file_id}/download`)
- Assistant messages rendered as sanitized Markdown (bold/lists/code)
- Message meta header with model, time, and sanitization counters (`ENCODED`, `DECODED`)

Note: PDF output is not supported. For `Same as input` with PDF input, fallback is `.txt`.

## Architecture (MVP)

- Backend: FastAPI (`app/`)
- Frontend: static app served by FastAPI (`static/`)
- Local storage:
  - SQLite: `data/app.db`
  - Uploaded/generated files: `data/uploads/`
  - Rules: `rules/`
- Deployment: single Docker container (`docker-compose.yml`)

## Requirements

- Docker + Docker Compose, or Python 3.12+
- OpenAI API key for real provider mode (optional for development)

## Quick Start (Docker)

1. Create your env file:

```bash
cp .env.example .env
```

2. Set API credentials for real provider mode:

```env
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
```

`OPENAI_BASE_URL` is optional. Leave it empty for default OpenAI endpoint behavior.

3. Start the app:

```bash
docker compose up -d --build
```

4. Verify service:

```bash
curl -sS http://localhost:8000/health
curl -sS http://localhost:8000/api/config
```

5. Open browser:

- `http://localhost:8000`

### Mock Mode

If `OPENAI_API_KEY` is empty, the app runs in mock mode. This is useful for end-to-end pipeline testing without real model calls.

## API Key Configuration

### OpenAI (official)

```env
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
```

or leave `OPENAI_BASE_URL=` empty.

### OpenAI-compatible gateway

```env
OPENAI_API_KEY=your-token
OPENAI_BASE_URL=https://your-gateway.example.com/v1
```

## Environment Variables

Main variables:

- `OPENAI_API_KEY`: enables real provider mode
- `OPENAI_BASE_URL`: custom provider base URL (optional)
- `LOGGING_ENABLED`: `true|false` (default: `false`)
- `AVAILABLE_MODELS`: comma-separated model list
- `DEFAULT_MODEL`: default selected model
- `MAX_UPLOAD_MB`: max upload size
- `TOKEN_SECRET`: token mapping encryption secret
- `TOKEN_TTL_DAYS`: token mapping TTL
- `NEVER_RECONCILE_CATEGORIES`: categories never reconciled

See `.env.example` for default values.

## Local Run (No Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Functional Flow

1. Create or select a chat session.
2. Write a prompt and optionally attach one or more files.
3. Choose response mode:
   - `In chat`: assistant reply stays in chat
   - `Same as input`: generate output file with first attachment format (if supported)
   - `Force ...`: force output format
4. Send.
5. If a file was generated, a `Download file` link appears in the assistant message area.
6. Message headers show model/time plus `ENCODED` (tokens masked) and `DECODED` (tokens reconciled).

Note: file-output modes require at least one attachment. Without attachment, backend falls back to `In chat`.

## Rule Engine and Sensitive Lists

Main files:

- `rules/ruleset.yaml`
- `rules/lists/*.txt|*.csv|*.json`

Included samples:

- `rules/lists/clients.txt`
- `rules/lists/brands.txt`
- `rules/lists/employees.txt`

To add a new list:

1. Upload via UI (Rules panel) or copy file into `rules/lists/`.
2. Recommended: declare it explicitly in `rules/ruleset.yaml` with category/action/priority.
3. Reload rules via UI button or `POST /api/rules/reload`.

If a list file is not declared in the ruleset, it is auto-loaded with default category `BUSINESS`.

## Main API Endpoints

- `GET /health`
- `GET /api/config`
- `PUT /api/config`
- `GET /api/models`
- `POST /api/chat/sessions`
- `GET /api/chat/sessions`
- `DELETE /api/chat/sessions/{session_id}`
- `GET /api/chat/sessions/{session_id}/messages`
- `POST /api/chat/sessions/{session_id}/messages`
- `POST /api/files/upload`
- `GET /api/files/{file_id}/download`
- `GET /api/audit/events/{event_id}`
- `POST /api/rulesets/validate`
- `POST /api/rules/reload`
- `GET /api/rules/files`
- `POST /api/rules/files`
- `PUT /api/rules/files/{file_id}`
- `DELETE /api/rules/files/{file_id}`

## Security and Current Limits

- MVP is single-user and has no authentication
- Best for local/trusted network usage
- Production hardening should include:
  - authentication and authorization
  - infrastructure hardening and TLS
  - retention policies and monitoring

## Troubleshooting

- UI not updating: hard-refresh browser (`Cmd+Shift+R`)
- Port conflict: change port mapping in `docker-compose.yml`
- No real model output: verify `OPENAI_API_KEY` and `OPENAI_BASE_URL`
- Rules not applied: validate and reload ruleset
- No output file generated: verify attachment presence and response mode

## Testing

```bash
./.venv/bin/python -m pytest -q
```

## License

MIT (`LICENSE`).
