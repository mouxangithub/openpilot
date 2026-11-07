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
    // opts.signal: external AbortSignal for immediate cancellation (user Stop).
    // opts.timeoutMs: internal abort after N ms. Either or both may be given.
    const internalAc = opts.timeoutMs ? new AbortController() : null;
    let timer;
    let signal = opts.signal || null;
    if (internalAc) {
      if (signal) {
        const outer = signal;
        signal = null; // combined below
        const combined = new AbortController();
        const onAbort = () => combined.abort();
        outer.addEventListener('abort', onAbort, { once: true });
        internalAc.signal.addEventListener('abort', onAbort, { once: true });
        if (outer.aborted || internalAc.signal.aborted) combined.abort();
        signal = combined.signal;
      } else {
        signal = internalAc.signal;
      }
    }
    const fetchOpts = { method, headers: getApiHeaders() };
    if (signal) fetchOpts.signal = signal;
    if (body) {
      fetchOpts.headers['Content-Type'] = 'application/json';
      fetchOpts.body = JSON.stringify(body);
    }
    if (internalAc) timer = setTimeout(() => internalAc.abort(), opts.timeoutMs);
    try {
      const res = await fetch(path, fetchOpts);
      const text = await res.text();
      let data;
      try { data = JSON.parse(text); } catch { data = { ok: false, error: text }; }
      return { status: res.status, data };
    } catch (e) {
      if (e?.name === 'AbortError') {
        return { status: 0, data: { ok: false, error: opts.signal?.aborted ? 'request cancelled' : 'request timeout' } };
      }
      throw e;
    } finally {
      if (timer) clearTimeout(timer);
    }
  }

  return { configure, api, getApiHeaders };
})();
