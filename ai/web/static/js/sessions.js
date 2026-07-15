/**
 * Multi-session chat storage for op助手.
 * Sessions appear in the list only after the user sends the first message.
 */
const SessionStore = (() => {
  const STORAGE_KEY = 'openpilot-op-sessions-v1';
  const LEGACY_KEY = 'openpilot-op-assistant-v2';
  const LEGACY_KEY2 = 'openpilot-ai-chat-v1';
  const MAX_SESSIONS = 50;

  let sessions = [];
  let activeId = null;

  function uid() {
    return `s_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
  }

  function messageHasVisibleContent(msg) {
    if (!msg || typeof msg !== 'object') return false;
    if (msg.role === 'user') {
      const text = typeof msg.content === 'string'
        ? msg.content.trim()
        : (Array.isArray(msg.content)
          ? msg.content.some((p) => p?.type === 'text' && String(p.text || '').trim())
          : false);
      const hasImage = Array.isArray(msg.content)
        && msg.content.some((p) => p?.type === 'image_url');
      return Boolean(text || hasImage);
    }
    if (msg.role === 'assistant') {
      const text = typeof msg.content === 'string' ? msg.content.trim() : '';
      if (text) return true;
      if (msg.tool_calls?.length) return true;
      if (msg.reasoning_content?.trim()) return true;
    }
    return false;
  }

  function sessionHasContent(session) {
    if (!session) return false;
    const msgs = session.messages || [];
    return msgs.some(messageHasVisibleContent);
  }

  function resolveActiveId() {
    const valid = activeId && sessions.some((s) => s.id === activeId && sessionHasContent(s));
    if (!valid) {
      activeId = sessions.find(sessionHasContent)?.id ?? null;
    }
  }

  function pruneEmptySessions() {
    const prevActive = activeId;
    sessions = sessions.filter(sessionHasContent);
    if (prevActive && sessions.some((s) => s.id === prevActive)) {
      activeId = prevActive;
    } else {
      activeId = sessions[0]?.id ?? null;
    }
    resolveActiveId();
    persist();
  }

  function load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const data = JSON.parse(raw);
        sessions = Array.isArray(data.sessions) ? data.sessions : [];
        activeId = data.activeId ?? null;
        pruneEmptySessions();
        persist();
        return;
      }
    } catch {}

    sessions = [];
    activeId = null;
    const legacy = readLegacyHistory();
    if (legacy.length) {
      const id = uid();
      sessions = [{
        id,
        title: legacyTitle(legacy),
        messages: legacy,
        mode: 'chat',
        updatedAt: Date.now(),
      }];
      activeId = id;
      persist();
    }
  }

  function readLegacyHistory() {
    for (const key of [LEGACY_KEY, LEGACY_KEY2]) {
      try {
        const raw = localStorage.getItem(key);
        if (raw) return JSON.parse(raw);
      } catch {}
    }
    return [];
  }

  function legacyTitle(messages) {
    const first = messages.find((m) => m.role === 'user');
    const text = typeof first?.content === 'string' ? first.content : '';
    return (text || '历史对话').slice(0, 40);
  }

  function persist() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ sessions, activeId }));
  }

  function list() {
    return [...sessions].sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
  }

  function listWithContent() {
    return list().filter(sessionHasContent);
  }

  function getActive() {
    if (!activeId) return null;
    return sessions.find((s) => s.id === activeId) || null;
  }

  function setActive(id) {
    if (id == null) {
      activeId = null;
      persist();
      return;
    }
    if (!sessions.some((s) => s.id === id)) return;
    activeId = id;
    persist();
  }

  function createSession(title) {
    const id = uid();
    const session = {
      id,
      title: (title || '新对话').slice(0, 60),
      messages: [],
      mode: 'chat',
      updatedAt: Date.now(),
    };
    sessions.unshift(session);
    activeId = id;
    while (sessions.length > MAX_SESSIONS) sessions.pop();
    persist();
    return session;
  }

  /** Create a session when the user sends the first message (not before). */
  function ensureSessionOnSend(previewText) {
    const existing = getActive();
    if (existing) return existing;
    const title = String(previewText || '').trim().slice(0, 40) || '新对话';
    return createSession(title);
  }

  /** Draft mode: no active session until the user sends a message. */
  function startDraft() {
    activeId = null;
    persist();
  }

  function remove(id) {
    sessions = sessions.filter((s) => s.id !== id);
    if (activeId === id) {
      activeId = sessions[0]?.id ?? null;
    }
    resolveActiveId();
    persist();
  }

  function updateMessages(id, messages, title) {
    const s = sessions.find((x) => x.id === id);
    if (!s) return;
    s.messages = messages;
    s.updatedAt = Date.now();
    if (title) s.title = title.slice(0, 60);
    else {
      const user = messages.find((m) => m.role === 'user');
      const text = typeof user?.content === 'string' ? user.content : '';
      if (text) s.title = text.slice(0, 40);
    }
    persist();
  }

  function setMode(id, mode) {
    const s = sessions.find((x) => x.id === id);
    if (!s) return;
    s.mode = mode;
    persist();
  }

  function getMode(id) {
    return sessions.find((x) => x.id === id)?.mode || 'chat';
  }

  function setActiveJobId(id, jobId) {
    const s = sessions.find((x) => x.id === id);
    if (!s) return;
    if (jobId) s.activeJobId = jobId;
    else delete s.activeJobId;
    persist();
  }

  function getActiveJobId(id) {
    return sessions.find((x) => x.id === id)?.activeJobId || null;
  }

  function clearActiveJobId(id) {
    setActiveJobId(id, null);
  }

  function dedupeTrailingAssistants(msgs) {
    const out = Array.isArray(msgs) ? [...msgs] : [];
    const score = (m) => (
      String(m?.content || '').length
      + String(m?.reasoning_content || '').length
      + ((m?.tool_calls || []).length * 100)
    );
    while (
      out.length >= 2
      && out[out.length - 1]?.role === 'assistant'
      && out[out.length - 2]?.role === 'assistant'
    ) {
      if (score(out[out.length - 1]) >= score(out[out.length - 2])) out.splice(out.length - 2, 1);
      else out.pop();
    }
    return out;
  }

  function importMerged(nextSessions, nextActiveId) {
    const cleaned = (Array.isArray(nextSessions) ? nextSessions : [])
      .filter(sessionHasContent)
      .map((s) => ({
        ...s,
        messages: dedupeTrailingAssistants(s.messages),
      }))
      .slice(0, MAX_SESSIONS);
    sessions = cleaned;
    if (nextActiveId && sessions.some((s) => s.id === nextActiveId)) {
      activeId = nextActiveId;
    } else {
      activeId = sessions[0]?.id ?? null;
    }
    resolveActiveId();
    persist();
    return sessions.length > 0;
  }

  return {
    load,
    list,
    listWithContent,
    getActive,
    setActive,
    createSession,
    ensureSessionOnSend,
    startDraft,
    remove,
    updateMessages,
    setMode,
    getMode,
    setActiveJobId,
    getActiveJobId,
    clearActiveJobId,
    importMerged,
    sessionHasContent,
    get activeId() { return activeId; },
  };
})();
