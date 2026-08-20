/**
 * REST API helper — JSON fetch with optional device headers.
 */
const WebApi = (() => {
  function configure(_opts = {}) {}

  function getApiHeaders() {
    const h = {};
    if (typeof DeviceTrust !== 'undefined') {
      Object.assign(h, DeviceTrust.headers());
    }
    return h;
  }

  async function api(method, path, body, opts = {}) {
    const ac = opts.timeoutMs ? new AbortController() : null;
    let timer;
    const fetchOpts = { method, headers: getApiHeaders() };
    if (ac) fetchOpts.signal = ac.signal;
    if (body) {
      fetchOpts.headers['Content-Type'] = 'application/json';
      fetchOpts.body = JSON.stringify(body);
    }
    if (ac) timer = setTimeout(() => ac.abort(), opts.timeoutMs);
    try {
      const res = await fetch(path, fetchOpts);
      const text = await res.text();
      let data;
      try { data = JSON.parse(text); } catch { data = { ok: false, error: text }; }
      return { status: res.status, data };
    } catch (e) {
      if (e?.name === 'AbortError') {
        return { status: 0, data: { ok: false, error: 'request timeout' } };
      }
      throw e;
    } finally {
      if (timer) clearTimeout(timer);
    }
  }

  return { configure, api, getApiHeaders };
})();
