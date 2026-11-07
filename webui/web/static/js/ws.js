/** WebSocket client for live UI state + panel param sync + RPC. */

const WS_PATH = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/opui`;

function channelsForScreen(screen) {
  if (screen === "home") return ["state", "home"];
  if (screen === "onroad") return ["state"];
  return ["state"];
}

class OpuiSocket {
  constructor() {
    this._ws = null;
    this._connected = false;
    this._handlers = new Map();
    this._pending = new Map();
    this._req = 0;
    this._reconnectMs = 500;
    this._watchPanel = null;
    this._shouldRun = false;
    this.bootstrap = null;
    this._helloWaiters = [];
    this._lastHome = null;
    this._lastState = null;
    this._modelWatch = null;
    this._watchI18n = false;
    this._watchStreamHealth = false;
    this._screen = "home";
    this._lastStreamHealth = null;
  }

  get connected() {
    return this._connected;
  }

  get lastHome() {
    return this._lastHome;
  }

  get lastState() {
    return this._lastState;
  }

  get lastStreamHealth() {
    return this._lastStreamHealth;
  }

  on(type, fn) {
    if (!this._handlers.has(type)) this._handlers.set(type, new Set());
    this._handlers.get(type).add(fn);
    if (type === "home" && this._lastHome) {
      try { fn(this._lastHome); } catch (_) { /* ignore */ }
    }
    if (type === "state" && this._lastState) {
      try { fn(this._lastState); } catch (_) { /* ignore */ }
    }
    if (type === "stream_health" && this._lastStreamHealth) {
      try { fn(this._lastStreamHealth); } catch (_) { /* ignore */ }
    }
    return () => this._handlers.get(type)?.delete(fn);
  }

  _emit(type, payload) {
    for (const fn of this._handlers.get(type) || []) {
      try { fn(payload); } catch (_) { /* ignore */ }
    }
  }

  _resolvePending(id, msg) {
    const pending = this._pending.get(id);
    if (!pending) return;
    this._pending.delete(id);
    pending.resolve(msg);
  }

  _subscribeChannels() {
    const channels = [...channelsForScreen(this._screen)];
    if (this._watchI18n) channels.push("i18n");
    if (this._watchStreamHealth) channels.push("stream_health");
    this._send({ type: "subscribe", channels });
  }

  syncScreen(screen) {
    this._screen = screen || "home";
    if (this._connected) this._subscribeChannels();
  }

  connect() {
    this._shouldRun = true;
    if (this._ws && (this._ws.readyState === WebSocket.OPEN || this._ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    const ws = new WebSocket(WS_PATH);
    this._ws = ws;
    ws.onopen = () => {
      this._connected = true;
      this._reconnectMs = 500;
      this._subscribeChannels();
      if (this._watchPanel) {
        this._send({ type: "watch_panel", panel: this._watchPanel });
      }
      if (this._modelWatch) {
        const { w, h, fps } = this._modelWatch;
        this._send({ type: "watch_model_overlay", w, h, fps });
      }
      this._emit("open", null);
    };
    ws.onclose = () => {
      this._connected = false;
      this._emit("close", null);
      if (!this._shouldRun) return;
      setTimeout(() => this.connect(), this._reconnectMs);
      this._reconnectMs = Math.min(this._reconnectMs * 1.5, 5000);
    };
    ws.onerror = () => { /* onclose handles reconnect */ };
    ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch (_) { return; }
      const { type, id } = msg;

      if (type === "hello") {
        this.bootstrap = msg.bootstrap || null;
        if (this.bootstrap?.home) {
          this._lastHome = { type: "home", data: this.bootstrap.home };
        }
        if (this.bootstrap?.state) {
          this._lastState = { type: "state", data: this.bootstrap.state };
        }
        this._emit("hello", msg);
        for (const resolve of this._helloWaiters.splice(0)) resolve(msg);
      }

      if ((type === "put_param_result" || type === "rpc_result") && id != null) {
        this._resolvePending(id, msg);
      }

      if (type === "home") this._lastHome = msg;
      if (type === "state") this._lastState = msg;
      if (type === "stream_health") {
        this._lastStreamHealth = msg;
      }

      this._emit(type, msg);
    };
  }

  waitHello(timeoutMs = 5000) {
    if (this.bootstrap) return Promise.resolve({ bootstrap: this.bootstrap });
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        const i = this._helloWaiters.indexOf(done);
        if (i >= 0) this._helloWaiters.splice(i, 1);
        resolve({ bootstrap: this.bootstrap });
      }, timeoutMs);
      const done = (msg) => {
        clearTimeout(timer);
        resolve(msg);
      };
      this._helloWaiters.push(done);
    });
  }

  disconnect() {
    this._shouldRun = false;
    this._ws?.close();
    this._ws = null;
    this._connected = false;
  }

  _send(obj) {
    if (!this._ws || this._ws.readyState !== WebSocket.OPEN) return false;
    this._ws.send(JSON.stringify(obj));
    return true;
  }

  watchPanel(panelId) {
    this._watchPanel = panelId || null;
    if (this._connected && panelId) {
      this._send({ type: "watch_panel", panel: panelId });
    } else if (this._connected && !panelId) {
      this._send({ type: "watch_panel", panel: "" });
    }
  }

  watchModelOverlay(w, h, fps = 10) {
    if (!this._connected) return false;
    const prev = this._modelWatch;
    if (prev && prev.w === w && prev.h === h && prev.fps === fps) return false;
    this._modelWatch = { w, h, fps };
    this._send({ type: "watch_model_overlay", w, h, fps });
    return true;
  }

  unwatchModelOverlay() {
    this._modelWatch = null;
    if (!this._connected) return;
    this._send({ type: "unwatch_model_overlay" });
  }

  watchStreamHealth() {
    if (this._watchStreamHealth) return;
    this._watchStreamHealth = true;
    if (this._connected) this._subscribeChannels();
  }

  unwatchStreamHealth() {
    if (!this._watchStreamHealth) return;
    this._watchStreamHealth = false;
    if (this._connected) this._subscribeChannels();
  }

  watchI18n() {
    if (this._watchI18n) return;
    this._watchI18n = true;
    if (this._connected) this._subscribeChannels();
  }

  unwatchI18n() {
    if (!this._watchI18n) return;
    this._watchI18n = false;
    if (this._connected) this._subscribeChannels();
  }

  rpc(method, path, body = null) {
    const id = `r${++this._req}`;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this._pending.delete(id);
        reject(new Error("rpc timeout"));
      }, 30000);
      this._pending.set(id, {
        resolve: (msg) => {
          clearTimeout(timer);
          resolve(msg);
        },
      });
      const payload = { type: "rpc", id, method, path };
      if (body != null) payload.body = body;
      if (!this._send(payload)) {
        clearTimeout(timer);
        this._pending.delete(id);
        reject(new Error("not connected"));
      }
    });
  }

  putParam(key, value, needsCycle = false) {
    if (!this._connected) return null;
    const id = `p${++this._req}`;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this._pending.delete(id);
        reject(new Error("timeout"));
      }, 8000);
      this._pending.set(id, {
        resolve: (msg) => {
          clearTimeout(timer);
          resolve(msg);
        },
      });
      if (!this._send({ type: "put_param", id, key, value: String(value), needs_cycle: !!needsCycle })) {
        clearTimeout(timer);
        this._pending.delete(id);
        reject(new Error("not connected"));
      }
    });
  }
}

export const opuiWs = new OpuiSocket();
