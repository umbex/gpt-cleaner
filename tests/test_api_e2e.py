from __future__ import annotations

from io import BytesIO

from app.llm_gateway import LLMGatewayError


def test_chat_upload_and_audit_flow(client):
    create_session = client.post("/api/chat/sessions", json={"title": "E2E"})
    assert create_session.status_code == 200
    session = create_session.json()

    upload = client.post(
        "/api/files/upload",
        files={"file": ("notes.txt", BytesIO(b"Cliente Demo su progetto riservato"), "text/plain")},
    )
    assert upload.status_code == 200
    uploaded = upload.json()

    message_payload = {
        "message": "Contatta ACME S.p.A. via mario.rossi@example.com",
        "model": "gpt-5.2",
        "file_ids": [uploaded["id"]],
    }
    send = client.post(f"/api/chat/sessions/{session['id']}/messages", json=message_payload)
    assert send.status_code == 200
    body = send.json()

    assert body["session_id"] == session["id"]
    assert "<TKN_" in body["user_message"]["content"]
    assert body["assistant_message"]["role"] == "assistant"
    assert body["sanitization"]["transformations"] >= 1
    assert body["sanitization"]["logging_enabled"] is True
    assert body["audit_id"] is not None

    audit = client.get(f"/api/audit/events/{body['audit_id']}")
    assert audit.status_code == 200
    audit_payload = audit.json()
    assert audit_payload["session_id"] == session["id"]
    assert isinstance(audit_payload["rules_triggered"], list)


def test_delete_chat_session(client):
    created = client.post("/api/chat/sessions", json={"title": "ToDelete"})
    assert created.status_code == 200
    session_id = created.json()["id"]

    delete_response = client.delete(f"/api/chat/sessions/{session_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["ok"] is True

    messages_after_delete = client.get(f"/api/chat/sessions/{session_id}/messages")
    assert messages_after_delete.status_code == 404

    sessions = client.get("/api/chat/sessions")
    assert sessions.status_code == 200
    assert all(item["id"] != session_id for item in sessions.json())


def test_session_title_auto_renamed_after_first_prompt(client):
    create_session = client.post("/api/chat/sessions", json={"title": "New chat"})
    assert create_session.status_code == 200
    session_id = create_session.json()["id"]

    send = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"message": "Contract Enel annual supply", "model": "gpt-5.2", "file_ids": []},
    )
    assert send.status_code == 200

    sessions = client.get("/api/chat/sessions")
    assert sessions.status_code == 200
    current = next(item for item in sessions.json() if item["id"] == session_id)
    assert current["title"] == "Contract - Enel"


def test_same_as_input_generates_downloadable_file(client):
    create_session = client.post("/api/chat/sessions", json={"title": "OutputFile"})
    assert create_session.status_code == 200
    session_id = create_session.json()["id"]

    upload = client.post(
        "/api/files/upload",
        files={"file": ("brief.txt", BytesIO(b"Base contract content"), "text/plain")},
    )
    assert upload.status_code == 200
    source_file_id = upload.json()["id"]

    send = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={
            "message": "Prepare a structured response",
            "model": "gpt-5.2",
            "file_ids": [source_file_id],
            "response_mode": "same_as_input",
        },
    )
    assert send.status_code == 200
    payload = send.json()
    generated = payload["generated_file"]
    assert generated is not None
    assert generated["filename"].endswith(".txt")
    assert generated["mode"] == "same_as_input"
    assert generated["source_file_id"] == source_file_id

    download = client.get(generated["download_url"])
    assert download.status_code == 200
    assert len(download.content) > 0


def test_forced_output_format_csv_generates_csv_file(client):
    create_session = client.post("/api/chat/sessions", json={"title": "ForcedCSV"})
    assert create_session.status_code == 200
    session_id = create_session.json()["id"]

    upload = client.post(
        "/api/files/upload",
        files={"file": ("brief.md", BytesIO(b"Contenuto base"), "text/markdown")},
    )
    assert upload.status_code == 200
    source_file_id = upload.json()["id"]

    send = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={
            "message": "Genera output tabellare",
            "model": "gpt-5.2",
            "file_ids": [source_file_id],
            "response_mode": "csv",
        },
    )
    assert send.status_code == 200
    payload = send.json()
    generated = payload["generated_file"]
    assert generated is not None
    assert generated["filename"].endswith(".csv")
    assert generated["mode"] == "csv"

    download = client.get(generated["download_url"])
    assert download.status_code == 200
    assert download.headers.get("content-type", "").startswith("text/csv")


def test_output_mode_without_file_falls_back_to_chat(client):
    create_session = client.post("/api/chat/sessions", json={"title": "NoFileMode"})
    assert create_session.status_code == 200
    session_id = create_session.json()["id"]

    send = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={
            "message": "Prova output forzato",
            "model": "gpt-5.2",
            "file_ids": [],
            "response_mode": "docx",
        },
    )
    assert send.status_code == 200
    payload = send.json()
    assert payload["generated_file"] is None
    assert payload["sanitization"]["response_mode"] == "chat"


def test_rule_file_management_and_reload(client):
    files_before = client.get("/api/rules/files?subdir=lists")
    assert files_before.status_code == 200

    upload = client.post(
        "/api/rules/files?subdir=lists&overwrite=false",
        files={"file": ("custom_clients.txt", BytesIO(b"New Client\nClient Alpha"), "text/plain")},
    )
    assert upload.status_code == 200
    file_id = upload.json()["file_id"]

    downloaded = client.get(f"/api/rules/files/{file_id}/download")
    assert downloaded.status_code == 200
    assert "attachment" in (downloaded.headers.get("content-disposition", "").lower())
    assert "New Client" in downloaded.text

    validate = client.post("/api/rulesets/validate")
    assert validate.status_code == 200
    assert validate.json()["ok"] is True

    reload_result = client.post("/api/rules/reload")
    assert reload_result.status_code == 200
    assert reload_result.json()["ok"] is True

    delete_result = client.delete(f"/api/rules/files/{file_id}")
    assert delete_result.status_code == 200
    assert delete_result.json()["ok"] is True


def test_rules_file_browser_blocks_path_traversal(client):
    response = client.get("/api/rules/files?subdir=../outside")
    assert response.status_code == 400


def test_logging_disabled_mode(client_no_logging):
    session = client_no_logging.post("/api/chat/sessions", json={"title": "NoLog"}).json()

    send = client_no_logging.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"message": "Segreto sk-ABCDEFGHIJKLMNOPQRSTUV", "model": "gpt-5.3", "file_ids": []},
    )
    assert send.status_code == 200
    payload = send.json()
    assert payload["audit_id"] is None
    assert payload["sanitization"]["logging_enabled"] is False

    no_audit = client_no_logging.get("/api/audit/events/unknown")
    assert no_audit.status_code == 404


def test_provider_599_is_exposed_as_502(client, monkeypatch):
    session = client.post("/api/chat/sessions", json={"title": "ProviderError"}).json()

    def _raise_provider_error(messages, model):
        raise LLMGatewayError(message="HTTP 599 upstream timeout", upstream_status=599)

    monkeypatch.setattr(client.app.state.llm_gateway, "chat", _raise_provider_error)

    send = client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"message": "Test gpt 5.3", "model": "gpt-5.3", "file_ids": []},
    )
    assert send.status_code == 502
    assert "upstream status: 599" in send.json()["detail"]
