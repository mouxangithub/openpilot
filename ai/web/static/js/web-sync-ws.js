/**
 * Sync WebSocket client — connect handshake + message dispatch.
 */
const SyncWsClient = (() => {
  const PROTOCOL_VERSION = 2;
  let ws = null;
  let connected = false;
  let reconnectTimer = null;
  let fallbackTimer = null;
  let handlers = {};

  function url() {
    if (typeof aiSyncWsUrl === 'function') return aiSyncWsUrl();
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${location.host}/api/ai/sync/ws`;
  }

  function isConnected() {
    return connected && ws?.readyState === WebSocket.OPEN;
  }

  function send(payload) {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
    }
  }

  function connect(h = {}) {
    handlers = h;
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
    clearTimeout(reconnectTimer);
    try {
      ws = new WebSocket(url());
    } catch {
      handlers.onFallback?.();
      return;
    }
    ws.onopen = () => {
      connected = true;
      if (fallbackTimer) {
        clearInterval(fallbackTimer);
        fallbackTimer = null;
      }
      send({
        type: 'connect',
        protocolVersion: PROTOCOL_VERSION,
        client: 'op-web',
        capabilities: ['sessions', 'chat', 'canvas', 'office', 'lifecycle'],
      });
    };
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === 'connect_ack' && !data.ok) {
          console.warn('sync ws connect_ack failed', data.error);
        }
        handlers.onMessage?.(data);
      } catch (e) {
        console.warn('sync ws parse', e);
      }
    };
    ws.onclose = () => {
      connected = false;
      ws = null;
      reconnectTimer = setTimeout(() => connect(handlers), 3000);
      handlers.onFallback?.();
    };
    ws.onerror = () => { try { ws?.close(); } catch {} };
  }

  function reconnect() {
    if (ws) { try { ws.close(); } catch {} ws = null; }
    connected = false;
    connect(handlers);
  }

  function close() {
    if (ws) { try { ws.close(); } catch {} ws = null; }
    connected = false;
  }

  function startFallbackPolling(fn, intervalMs = 15000) {
    if (fallbackTimer) return;
    fallbackTimer = setInterval(() => {
      if (isConnected() || document.visibilityState !== 'visible') return;
      fn?.();
    }, intervalMs);
  }

  return {
    PROTOCOL_VERSION,
    connect,
    reconnect,
    close,
    send,
    isConnected,
    startFallbackPolling,
  };
})();
