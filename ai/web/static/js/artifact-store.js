/**
 * Shared artifact store — unified canvas + delivery drawer (WorkBuddy s20).
 */
const ArtifactStore = (() => {
  const bySession = new Map();
  const listeners = new Set();

  function sid(sessionId) {
    return sessionId || (typeof SessionStore !== 'undefined' ? SessionStore.activeId : '') || '__global__';
  }

  function notify(sessionId) {
    for (const fn of listeners) {
      try { fn(sessionId); } catch {}
    }
  }

  function add(sessionId, artifact) {
    if (!artifact) return;
    const key = sid(sessionId);
    const items = bySession.get(key) || [];
    const exists = items.some((a) => a.id && a.id === artifact.id);
    if (!exists) items.unshift(artifact);
    bySession.set(key, items.slice(0, 40));
    notify(key);
  }

  function list(sessionId) {
    return bySession.get(sid(sessionId)) || [];
  }

  function setSession(sessionId, artifacts) {
    bySession.set(sid(sessionId), (artifacts || []).slice(0, 40));
    notify(sid(sessionId));
  }

  function subscribe(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  }

  return { add, list, setSession, subscribe, sid };
})();
