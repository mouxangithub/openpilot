/**
 * Gateway session sync — server-first conflict resolution (OpenClaw-style).
 * stateVersion tracked in memory; no localStorage for session truth.
 */
const SessionSync = (() => {
  let serverStateVersion = 0;
  let serverSavedAt = 0;

  let localDirtyVersion = 0;
  let lastLocalMutationAt = 0;

  function setServerSyncMeta(data) {
    const version = Number(data?.stateVersion || data?.savedAt) || 0;
    const savedAt = Number(data?.savedAt) || 0;
    if (version) serverStateVersion = Math.max(serverStateVersion, version);
    if (savedAt) serverSavedAt = Math.max(serverSavedAt, savedAt);
  }

  function getServerStateVersion() {
    return serverStateVersion;
  }

  function getServerSavedAt() {
    return serverSavedAt;
  }

  function markLocalDirty() {
    localDirtyVersion += 1;
    lastLocalMutationAt = Date.now();
  }

  function clearLocalDirty() {
    localDirtyVersion = 0;
  }

  /** True until POST succeeds and clearLocalDirty() is called. */
  function isLocallyDirty() {
    return localDirtyVersion > 0;
  }

  function messagesContentScore(msgs) {
    if (!Array.isArray(msgs)) return 0;
    let score = msgs.length * 1000;
    for (const m of msgs) {
      const text = typeof m?.content === 'string' ? m.content : '';
      score += text.length;
      if (m?.reasoning_content) score += String(m.reasoning_content).length;
      if (m?.tool_calls?.length) score += m.tool_calls.length * 50;
    }
    return score;
  }

  function sessionCreatedAt(s) {
    if (!s) return 0;
    const explicit = Number(s.createdAt);
    if (Number.isFinite(explicit) && explicit > 0) return explicit;
    const m = /^s_([a-z0-9]+)_/i.exec(String(s.id || ''));
    if (m) {
      const parsed = parseInt(m[1], 36);
      if (Number.isFinite(parsed) && parsed > 1e11) return parsed;
    }
    return Number(s.updatedAt) || 0;
  }

  function sortSessionsByCreated(sessions) {
    return [...sessions].sort((a, b) => sessionCreatedAt(b) - sessionCreatedAt(a));
  }

  function pickSessionMessages(a, b) {
    const aMsgs = Array.isArray(a.messages) ? a.messages : [];
    const bMsgs = Array.isArray(b.messages) ? b.messages : [];
    if (aMsgs.length !== bMsgs.length) {
      return aMsgs.length > bMsgs.length ? aMsgs : bMsgs;
    }
    const aScore = messagesContentScore(aMsgs);
    const bScore = messagesContentScore(bMsgs);
    if (aScore !== bScore) {
      return aScore > bScore ? aMsgs : bMsgs;
    }
    return (Number(a.updatedAt) || 0) >= (Number(b.updatedAt) || 0) ? aMsgs : bMsgs;
  }

  /** Server wins when its stateVersion is newer (Gateway authoritative). */
  function shouldTakeRemoteAuthoritative(data) {
    const remoteV = Number(data?.stateVersion || data?.savedAt) || 0;
    if (!remoteV) return false;
    if (serverStateVersion === 0) return true;
    return remoteV > serverStateVersion;
  }

  function pickBetterSession(a, b) {
    const aScore = messagesContentScore(a?.messages);
    const bScore = messagesContentScore(b?.messages);
    if (aScore !== bScore) return aScore > bScore ? a : b;
    return (Number(a?.updatedAt) || 0) >= (Number(b?.updatedAt) || 0) ? a : b;
  }

  function normalizeSession(s) {
    return {
      ...s,
      mode: s.mode || 'chat',
      messages: Array.isArray(s.messages) ? s.messages : [],
      createdAt: sessionCreatedAt(s),
      updatedAt: Number(s.updatedAt) || 0,
    };
  }

  function sessionFromLocalPrefer(local, remote) {
    const localN = normalizeSession(local);
    return {
      ...localN,
      activeJobId: local.activeJobId || null,
      title: String(localN.title || remote?.title || '').trim() || localN.title,
      updatedAt: Math.max(localN.updatedAt, Number(remote?.updatedAt) || 0),
      chatRoute: localN.chatRoute || remote?.chatRoute,
      chatRoutePins: localN.chatRoutePins || remote?.chatRoutePins,
    };
  }

  /** Dedupe by session id only (never merge different ids). */
  function dedupeSessionList(sessions) {
    const byId = new Map();
    for (const s of sessions || []) {
      if (!s?.id) continue;
      const prev = byId.get(s.id);
      byId.set(s.id, prev ? pickBetterSession(prev, s) : s);
    }
    return sortSessionsByCreated([...byId.values()]);
  }

  function mergeSessionRecords(remoteSessions, localSessions, sessionHasContent, opts = {}) {
    const protectedIds = opts.protectedSessionIds instanceof Set ? opts.protectedSessionIds : new Set();
    const localById = new Map(
      (Array.isArray(localSessions) ? localSessions : []).map((s) => [s.id, s]),
    );

    if (opts.remoteAuthoritative && remoteSessions.length) {
      const remoteIds = new Set();
      const normalized = remoteSessions
        .filter((s) => sessionHasContent(s))
        .map((s) => {
          remoteIds.add(s.id);
          const local = localById.get(s.id);
          if (protectedIds.has(s.id) && local) {
            return sessionFromLocalPrefer(local, s);
          }
          const { activeJobId: remoteJob, ...rest } = s;
          const remoteMsgs = Array.isArray(s.messages) ? s.messages : [];
          const localMsgs = Array.isArray(local?.messages) ? local.messages : [];
          const messages = pickSessionMessages(
            { messages: remoteMsgs, updatedAt: s.updatedAt || 0 },
            { messages: localMsgs, updatedAt: local?.updatedAt || 0 },
          );
          const keepJobId = protectedIds.has(s.id)
            ? (local?.activeJobId || remoteJob || null)
            : (local?.activeJobId || null);
          return {
            ...rest,
            mode: s.mode || 'chat',
            messages,
            title: String(s.title || '').trim() || local?.title || s.title,
            createdAt: sessionCreatedAt(s),
            updatedAt: Math.max(Number(s.updatedAt) || 0, Number(local?.updatedAt) || 0),
            ...(keepJobId ? { activeJobId: keepJobId } : {}),
            chatRoute: local?.chatRoute || s.chatRoute,
            chatRoutePins: local?.chatRoutePins || s.chatRoutePins,
          };
        });

      for (const ls of localSessions) {
        if (!ls?.id || remoteIds.has(ls.id) || !sessionHasContent(ls)) continue;
        normalized.push(protectedIds.has(ls.id) ? sessionFromLocalPrefer(ls, null) : normalizeSession(ls));
      }
      return dedupeSessionList(normalized);
    }

    const byId = new Map();

    for (const rs of remoteSessions) {
      const n = normalizeSession(rs);
      if (!sessionHasContent(n)) continue;
      if (protectedIds.has(rs.id) && localById.has(rs.id)) {
        byId.set(rs.id, sessionFromLocalPrefer(localById.get(rs.id), rs));
        continue;
      }
      byId.set(rs.id, n);
    }

    for (const ls of localSessions) {
      const n = normalizeSession(ls);
      if (!sessionHasContent(n)) continue;
      if (protectedIds.has(ls.id)) {
        byId.set(ls.id, sessionFromLocalPrefer(ls, byId.get(ls.id)));
        continue;
      }
      const prev = byId.get(ls.id);
      if (!prev) {
        byId.set(ls.id, { ...n, activeJobId: ls.activeJobId || null });
        continue;
      }

      const localScore = messagesContentScore(ls.messages);
      const remoteScore = messagesContentScore(prev.messages);
      const localNewer = (ls.updatedAt || 0) > (prev.updatedAt || 0);
      const localRicher = localScore > remoteScore;
      const preferLocalMeta = localNewer || localRicher;

      const messages = pickSessionMessages(
        { messages: ls.messages, updatedAt: ls.updatedAt || 0 },
        { messages: prev.messages, updatedAt: prev.updatedAt || 0 },
      );

      byId.set(ls.id, {
        ...prev,
        mode: prev.mode || ls.mode || 'chat',
        messages,
        title: preferLocalMeta && ls.title ? ls.title : (prev.title || ls.title),
        createdAt: sessionCreatedAt(preferLocalMeta ? ls : prev),
        updatedAt: Math.max(ls.updatedAt || 0, prev.updatedAt || 0),
        activeJobId: ls.activeJobId || prev.activeJobId || null,
        chatRoute: preferLocalMeta ? (ls.chatRoute || prev.chatRoute) : (prev.chatRoute || ls.chatRoute),
        chatRoutePins: preferLocalMeta
          ? (ls.chatRoutePins || prev.chatRoutePins)
          : (prev.chatRoutePins || ls.chatRoutePins),
      });
    }

    return dedupeSessionList(sortSessionsByCreated([...byId.values()]));
  }

  function shouldSkipRemoteMerge(ctx) {
    const { data } = ctx;
    const remoteSavedAt = Number(data?.savedAt) || 0;
    if (isLocallyDirty() && remoteSavedAt <= serverSavedAt) return true;
    return false;
  }

  function pickActiveId({
    merged,
    data,
    localHasContent,
    localActiveBefore,
  }) {
    if (!localHasContent && merged.length) {
      return data.activeId && merged.some((s) => s.id === data.activeId)
        ? data.activeId
        : merged[0].id;
    }
    if (localActiveBefore && merged.some((s) => s.id === localActiveBefore)) {
      return localActiveBefore;
    }
    if (data.activeId && merged.some((s) => s.id === data.activeId)) {
      return data.activeId;
    }
    return merged[0]?.id ?? null;
  }

  return {
    setServerSyncMeta,
    getServerStateVersion,
    getServerSavedAt,
    markLocalDirty,
    clearLocalDirty,
    isLocallyDirty,
    pickSessionMessages,
    mergeSessionRecords,
    dedupeSessionList,
    shouldSkipRemoteMerge,
    pickActiveId,
    shouldTakeRemoteAuthoritative,
  };
})();
