/** HTTP helpers — routes through WebSocket RPC when connected. */

import { opuiWs } from "./ws.js";

const ASSET_RE = /^\/api\/opui\/assets\//;
const HTTP_FIRST_RE = /^\/api\/opui\/(panels|dev|i18n|device|bootstrap|agnos)/;
const HTTP_TIMEOUT_MS = 8000;
const WEBUI_UPDATE_TIMEOUT_MS = 120000;
const WEBRTC_TIMEOUT_MS = 45000;

function isWebrtcPath(path) {
  return /^\/api\/opui\/webrtc\//.test(path) || /^\/api\/opui\/action\/webrtc_/.test(path);
}

function useHttp(path) {
  if (isWebrtcPath(path)) return true;
  if (ASSET_RE.test(path)) return true;
  if (/^\/api\/opui\/bootstrap/.test(path)) return true;
  if (/^\/api\/opui\/agnos/.test(path)) return true;
  if (/^\/api\/opui\/webui-update/.test(path)) return true;
  if (window.__OPUI_DEV_PC && HTTP_FIRST_RE.test(path)) return true;
  return false;
}

async function fetchJson(path, init = {}) {
  const ctrl = new AbortController();
  const timeoutMs = isWebrtcPath(path)
    ? WEBRTC_TIMEOUT_MS
    : (/^\/api\/opui\/webui-update/.test(path) ? WEBUI_UPDATE_TIMEOUT_MS : HTTP_TIMEOUT_MS);
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(path, { ...init, signal: ctrl.signal });
    const text = await r.text();
    let data;
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = { ok: false, error: text || `HTTP ${r.status}` };
    }
    if (!r.ok && data.ok !== false) {
      data = { ok: false, error: data.error || text || `HTTP ${r.status}` };
    }
    return data;
  } finally {
    clearTimeout(timer);
  }
}

export async function apiGet(path) {
  if (!useHttp(path) && opuiWs.connected) {
    try {
      const data = await opuiWs.rpc("GET", path);
      if (data?.ok !== false) return data;
    } catch (_) { /* fallback */ }
  }
  return fetchJson(path);
}

export async function apiPut(path, body) {
  if (!useHttp(path) && opuiWs.connected) {
    try {
      const data = await opuiWs.rpc("PUT", path, body);
      if (data?.ok !== false) return data;
    } catch (_) { /* fallback */ }
  }
  return fetchJson(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function apiPost(path, body = {}) {
  if (!useHttp(path) && opuiWs.connected) {
    try {
      const data = await opuiWs.rpc("POST", path, body);
      if (data?.ok !== false) return data;
    } catch (_) { /* fallback */ }
  }
  return fetchJson(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function toast(msg, ms = 3000) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, ms);
}

export function confirmDialog(message) {
  return new Promise((resolve) => {
    const dlg = document.getElementById("confirm-dialog");
    const msg = document.getElementById("confirm-msg");
    const ok = document.getElementById("confirm-ok");
    const cancel = document.getElementById("confirm-cancel");
    if (!dlg || !msg) {
      resolve(window.confirm(message));
      return;
    }
    msg.textContent = message;
    dlg.showModal();
    const done = (v) => {
      dlg.close();
      ok.removeEventListener("click", onOk);
      cancel.removeEventListener("click", onCancel);
      resolve(v);
    };
    const onOk = () => done(true);
    const onCancel = () => done(false);
    ok.addEventListener("click", onOk);
    cancel.addEventListener("click", onCancel);
  });
}
