const state = {
  sessions: [],
  currentSessionId: null,
  models: [],
  defaultModel: "",
  selectedModel: "",
  pendingFileIds: [],
  loggingEnabled: true,
};

const elements = {
  sessionList: document.getElementById("sessionList"),
  newSessionBtn: document.getElementById("newSessionBtn"),
  chatView: document.getElementById("chatView"),
  modelSelect: document.getElementById("modelSelect"),
  sendBtn: document.getElementById("sendBtn"),
  messageInput: document.getElementById("messageInput"),
  fileInput: document.getElementById("fileInput"),
  responseModeSelect: document.getElementById("responseModeSelect"),
  attachmentInfo: document.getElementById("attachmentInfo"),
  statusBadge: document.getElementById("statusBadge"),
  themeToggleBtn: document.getElementById("themeToggleBtn"),
  rulesToggleBtn: document.getElementById("rulesToggleBtn"),
  rulesPanel: document.getElementById("rulesPanel"),
  rulesCloseBtn: document.getElementById("rulesCloseBtn"),
  rulesFileInput: document.getElementById("rulesFileInput"),
  overwriteToggle: document.getElementById("overwriteToggle"),
  rulesFileList: document.getElementById("rulesFileList"),
  reloadRulesBtn: document.getElementById("reloadRulesBtn"),
  rulesValidationInfo: document.getElementById("rulesValidationInfo"),
  loggingToggle: document.getElementById("loggingToggle"),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = payload.detail || payload.error || `HTTP ${response.status}`;
    throw new Error(detail);
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return null;
}

function setStatus(text) {
  elements.statusBadge.textContent = text;
}

function applyTheme() {
  const current = localStorage.getItem("theme") || "light";
  document.body.classList.toggle("theme-dark", current === "dark");
  updateThemeButton(current);
}

function toggleTheme() {
  const current = localStorage.getItem("theme") || "light";
  localStorage.setItem("theme", current === "light" ? "dark" : "light");
  applyTheme();
}

function updateThemeButton(currentTheme) {
  const iconContainer = elements.themeToggleBtn.querySelector(".theme-btn-icon");
  const isDark = currentTheme === "dark";
  const sunSvg =
    '<svg viewBox="0 0 24 24" aria-hidden="true" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="M4.93 4.93l1.41 1.41"></path><path d="M17.66 17.66l1.41 1.41"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="M4.93 19.07l1.41-1.41"></path><path d="M17.66 6.34l1.41-1.41"></path></svg>';
  const moonSvg =
    '<svg viewBox="0 0 24 24" aria-hidden="true" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3c-.1.63-.15 1.27-.15 1.93a9 9 0 0 0 9.94 7.86z"></path></svg>';
  iconContainer.innerHTML = isDark ? moonSvg : sunSvg;

  const nextModeLabelEn = isDark ? "Switch to light theme" : "Switch to dark theme";
  elements.themeToggleBtn.setAttribute("aria-label", nextModeLabelEn);
  elements.themeToggleBtn.title = nextModeLabelEn;
}

function formatDate(iso) {
  const date = new Date(iso);
  return `${date.toLocaleDateString()} ${date.toLocaleTimeString()}`;
}

function renderSessions() {
  elements.sessionList.innerHTML = "";
  for (const session of state.sessions) {
    const row = document.createElement("div");
    row.className = "session-item-row";

    const button = document.createElement("button");
    button.className = `session-item ${state.currentSessionId === session.id ? "active" : ""}`;
    button.textContent = session.title;
    button.onclick = async () => {
      state.currentSessionId = session.id;
      renderSessions();
      await loadMessages();
    };

    const closeBtn = document.createElement("button");
    closeBtn.className = "session-close-btn";
    closeBtn.type = "button";
    closeBtn.title = "Delete chat";
    closeBtn.setAttribute("aria-label", `Delete chat ${session.title}`);
    closeBtn.textContent = "×";
    closeBtn.onclick = async (event) => {
      event.stopPropagation();
      if (!confirm(`Delete chat \"${session.title}\"?`)) return;
      try {
        await deleteSession(session.id);
      } catch (error) {
        setStatus(`Delete chat error: ${error.message}`);
      }
    };

    row.appendChild(button);
    row.appendChild(closeBtn);
    elements.sessionList.appendChild(row);
  }
}

function renderMessage(role, content, meta = "") {
  const container = document.createElement("div");
  container.className = `msg ${role}`;

  const metaEl = document.createElement("div");
  metaEl.className = "msg-meta";
  metaEl.textContent = meta;

  const contentEl = document.createElement("div");
  contentEl.textContent = content;

  container.appendChild(metaEl);
  container.appendChild(contentEl);
  elements.chatView.appendChild(container);
  elements.chatView.scrollTop = elements.chatView.scrollHeight;
}

function renderGeneratedFile(file) {
  const container = document.createElement("div");
  container.className = "msg assistant";

  const metaEl = document.createElement("div");
  metaEl.className = "msg-meta";
  metaEl.textContent = "ASSISTANT | file output";

  const link = document.createElement("a");
  link.className = "generated-file-link";
  link.href = file.download_url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = `Download file: ${file.filename}`;

  container.appendChild(metaEl);
  container.appendChild(link);
  elements.chatView.appendChild(container);
  elements.chatView.scrollTop = elements.chatView.scrollHeight;
}

async function loadConfig() {
  const config = await api("/api/config");
  state.loggingEnabled = Boolean(config.logging_enabled);
  elements.loggingToggle.checked = state.loggingEnabled;
  setStatus(config.mock_mode ? "MOCK mode active" : "LLM provider active");
}

async function saveConfig() {
  const payload = { logging_enabled: elements.loggingToggle.checked };
  const result = await api("/api/config", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  state.loggingEnabled = Boolean(result.logging_enabled);
  setStatus(`Logging ${state.loggingEnabled ? "enabled" : "disabled"}`);
}

async function loadModels() {
  const data = await api("/api/models");
  state.models = data.models;
  state.defaultModel = data.default;
  state.selectedModel = data.default;

  elements.modelSelect.innerHTML = "";
  for (const model of state.models) {
    const option = document.createElement("option");
    option.value = model;
    option.textContent = model;
    if (model === state.defaultModel) option.selected = true;
    elements.modelSelect.appendChild(option);
  }
}

async function createSession() {
  const created = await api("/api/chat/sessions", {
    method: "POST",
    body: JSON.stringify({ title: "New chat" }),
  });
  state.sessions.unshift(created);
  state.currentSessionId = created.id;
  renderSessions();
  elements.chatView.innerHTML = "";
}

async function loadSessions() {
  state.sessions = await api("/api/chat/sessions");
  if (!state.sessions.length) {
    await createSession();
  } else if (!state.currentSessionId) {
    state.currentSessionId = state.sessions[0].id;
  }
  renderSessions();
}

async function deleteSession(sessionId) {
  await api(`/api/chat/sessions/${sessionId}`, { method: "DELETE" });
  state.sessions = state.sessions.filter((session) => session.id !== sessionId);

  if (!state.sessions.length) {
    await createSession();
    await loadMessages();
    setStatus("Chat deleted");
    return;
  }

  if (state.currentSessionId === sessionId) {
    state.currentSessionId = state.sessions[0].id;
    await loadMessages();
  }
  renderSessions();
  setStatus("Chat deleted");
}

async function loadMessages() {
  if (!state.currentSessionId) return;
  const messages = await api(`/api/chat/sessions/${state.currentSessionId}/messages`);
  elements.chatView.innerHTML = "";
  for (const msg of messages) {
    const model = msg.model ? ` | ${msg.model}` : "";
    renderMessage(msg.role, msg.content, `${msg.role.toUpperCase()}${model} | ${formatDate(msg.created_at)}`);
  }
}

async function uploadAttachment(file) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch("/api/files/upload", { method: "POST", body: formData });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `Upload failed (${response.status})`);
  }
  state.pendingFileIds.push(payload.id);
  elements.attachmentInfo.textContent = `Queued attachments: ${state.pendingFileIds.length}`;
}

async function sendMessage() {
  if (!state.currentSessionId) return;
  const message = elements.messageInput.value.trim();
  if (!message) return;

  elements.messageInput.value = "";
  setStatus("Sending...");

  try {
    let responseMode = elements.responseModeSelect.value;
    const modeRequiresFile = responseMode !== "chat";
    const modeFallbackToChat = modeRequiresFile && state.pendingFileIds.length === 0;
    if (modeFallbackToChat) {
      responseMode = "chat";
    }

    const payload = {
      message,
      model: elements.modelSelect.value,
      file_ids: state.pendingFileIds,
      response_mode: responseMode,
    };

    const result = await api(`/api/chat/sessions/${state.currentSessionId}/messages`, {
      method: "POST",
      body: JSON.stringify(payload),
    });

    renderMessage(
      "user",
      result.user_message.content,
      `USER | ${result.user_message.model} | ${new Date(result.user_message.created_at).toLocaleTimeString()}`
    );
    renderMessage(
      "assistant",
      result.assistant_message.content,
      `ASSISTANT | ${result.assistant_message.model} | ${new Date(result.assistant_message.created_at).toLocaleTimeString()}`
    );
    if (result.generated_file) {
      renderGeneratedFile(result.generated_file);
    }

    const sanitization = result.sanitization || {};
    const rules = (sanitization.rules_triggered || []).join(", ") || "none";
    const modeInfo = result.generated_file ? `, output file ${result.generated_file.filename}` : "";
    const fallbackInfo = modeFallbackToChat
      ? ", file output mode ignored (no attachment)"
      : "";
    setStatus(
      `Sanitization: ${sanitization.transformations || 0} transformations, rules [${rules}], logging ${sanitization.logging_enabled ? "on" : "off"}${modeInfo}${fallbackInfo}`
    );
    await loadSessions();

    state.pendingFileIds = [];
    elements.attachmentInfo.textContent = "";
  } catch (error) {
    setStatus(`Error: ${error.message}`);
    renderMessage("assistant", `Error: ${error.message}`, "SYSTEM");
  }
}

async function loadRulesFiles() {
  const files = await api("/api/rules/files?subdir=lists");
  elements.rulesFileList.innerHTML = "";

  for (const file of files) {
    const li = document.createElement("li");
    li.className = "rules-file-item";

    const main = document.createElement("div");
    main.className = "rules-file-main";
    const name = document.createElement("div");
    name.className = "rules-file-name";
    name.textContent = file.name;
    const size = document.createElement("div");
    size.className = "rules-file-size";
    size.textContent = `${file.size} bytes`;
    main.appendChild(name);
    main.appendChild(size);

    const delBtn = document.createElement("button");
    delBtn.className = "btn delete-btn";
    delBtn.textContent = "Delete";
    delBtn.onclick = async () => {
      if (!confirm(`Delete ${file.name}?`)) return;
      await api(`/api/rules/files/${encodeURIComponent(file.file_id)}`, { method: "DELETE" });
      await loadRulesFiles();
    };

    li.appendChild(main);
    li.appendChild(delBtn);
    elements.rulesFileList.appendChild(li);
  }
}

async function uploadRuleFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  const overwrite = elements.overwriteToggle.checked ? "true" : "false";

  const response = await fetch(`/api/rules/files?subdir=lists&overwrite=${overwrite}`, {
    method: "POST",
    body: formData,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `Rules upload failed (${response.status})`);
  }
  return payload;
}

async function reloadRules() {
  const result = await api("/api/rules/reload", { method: "POST" });
  elements.rulesValidationInfo.textContent = `${result.message} | rules=${result.rule_count}, lists=${result.list_count}`;
}

function bindEvents() {
  elements.newSessionBtn.onclick = async () => {
    await createSession();
    await loadMessages();
  };

  elements.sendBtn.onclick = sendMessage;
  elements.messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      sendMessage().catch((err) => setStatus(`Error: ${err.message}`));
    }
  });

  elements.fileInput.onchange = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      await uploadAttachment(file);
      setStatus(`Attachment uploaded: ${file.name}`);
    } catch (error) {
      setStatus(`Upload error: ${error.message}`);
    } finally {
      elements.fileInput.value = "";
    }
  };

  elements.modelSelect.onchange = (event) => {
    state.selectedModel = event.target.value;
  };

  elements.themeToggleBtn.onclick = toggleTheme;

  elements.rulesToggleBtn.onclick = async () => {
    elements.rulesPanel.classList.toggle("hidden");
    if (!elements.rulesPanel.classList.contains("hidden")) {
      await loadRulesFiles();
    }
  };

  elements.rulesCloseBtn.onclick = () => {
    elements.rulesPanel.classList.add("hidden");
  };

  elements.rulesFileInput.onchange = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      await uploadRuleFile(file);
      await loadRulesFiles();
      setStatus(`Rules file uploaded: ${file.name}`);
    } catch (error) {
      setStatus(`Rules upload error: ${error.message}`);
    } finally {
      elements.rulesFileInput.value = "";
    }
  };

  elements.reloadRulesBtn.onclick = async () => {
    try {
      await reloadRules();
      setStatus("Ruleset reloaded");
    } catch (error) {
      setStatus(`Reload error: ${error.message}`);
    }
  };

  elements.loggingToggle.onchange = async () => {
    try {
      await saveConfig();
    } catch (error) {
      setStatus(`Config error: ${error.message}`);
    }
  };
}

async function bootstrap() {
  applyTheme();
  bindEvents();
  await loadConfig();
  await loadModels();
  await loadSessions();
  await loadMessages();
}

bootstrap().catch((error) => {
  setStatus(`Bootstrap error: ${error.message}`);
});
