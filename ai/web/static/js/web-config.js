/**
 * Workspace markdown files (SOUL / AGENTS / HEARTBEAT) — OpenClaw-style.
 */
const WebWorkspace = (() => {
  async function list(apiFn) {
    const { data } = await apiFn('GET', '/api/ai/workspace');
    return data;
  }

  async function read(apiFn, key) {
    const { data } = await apiFn('GET', `/api/ai/workspace?key=${encodeURIComponent(key)}`);
    return data;
  }

  async function write(apiFn, key, content) {
    const { data } = await apiFn('POST', '/api/ai/workspace', { key, content });
    return data;
  }

  return { list, read, write };
})();
