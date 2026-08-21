/**
 * Full-screen wait overlay for AGNOS / software updates and device reboot.
 * Persists across page reload during reboot via sessionStorage.
 */

import { apiGet, apiPost, toast } from "./api.js";
import { tr } from "./i18n.js";

const SESSION_KEY = "opui_system_wait_v1";
const BOOTSTRAP_TIMEOUT_MS = 6000;
const RECONNECT_TIMEOUT_MS = 5 * 60 * 1000;
const AGNOS_POLL_MS = 2000;

let active = false;
let abortCtrl = null;

function $(id) {
  return document.getElementById(id);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function readSession() {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeSession(data) {
  try {
    if (data) sessionStorage.setItem(SESSION_KEY, JSON.stringify(data));
    else sessionStorage.removeItem(SESSION_KEY);
  } catch { /* ignore */ }
}

function showOverlay({ title, message, hint = "", progress = null, showDismiss = false }) {
  const root = $("system-wait-overlay");
  const titleEl = $("system-wait-title");
  const msgEl = $("system-wait-message");
  const hintEl = $("system-wait-hint");
  const progWrap = $("system-wait-progress-wrap");
  const progBar = $("system-wait-progress-bar");
  const progLabel = $("system-wait-progress-label");
  const dismiss = $("system-wait-dismiss");
  if (!root) return;

  if (titleEl) titleEl.textContent = title || "";
  if (msgEl) msgEl.textContent = message || "";
  if (hintEl) {
    hintEl.textContent = hint || "";
    hintEl.hidden = !hint;
  }
  if (progWrap && progBar) {
    const showProg = typeof progress === "number" && progress >= 0;
    progWrap.hidden = !showProg;
    if (showProg) {
      const pct = Math.min(100, Math.max(0, Math.round(progress)));
      progBar.style.width = `${pct}%`;
      if (progLabel) progLabel.textContent = `${pct}%`;
    }
  }
  if (dismiss) {
    dismiss.hidden = !showDismiss;
    dismiss.textContent = tr("Close");
  }
  root.hidden = false;
  document.body.classList.add("opui-system-wait-open");
  active = true;
}

function hideOverlay() {
  const root = $("system-wait-overlay");
  if (root) root.hidden = true;
  document.body.classList.remove("opui-system-wait-open");
  active = false;
  writeSession(null);
  if (abortCtrl) {
    abortCtrl.abort();
    abortCtrl = null;
  }
}

function bindDismiss() {
  const dismiss = $("system-wait-dismiss");
  if (!dismiss || dismiss._bound) return;
  dismiss._bound = true;
  dismiss.addEventListener("click", () => hideOverlay());
}

async function fetchBootstrap() {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), BOOTSTRAP_TIMEOUT_MS);
  try {
    const r = await fetch("/api/opui/bootstrap", { signal: ctrl.signal, cache: "no-store" });
    if (!r.ok) throw new Error(`http ${r.status}`);
    return await r.json();
  } finally {
    clearTimeout(timer);
  }
}

async function waitForDeviceReconnect({
  kind = "reboot",
  startedAt = Date.now(),
  onPhase,
  successMessage,
} = {}) {
  const doneMsg = successMessage || (
    kind === "reboot"
      ? tr("Device is back online")
      : tr("Update complete — device is back online")
  );
  const deadline = startedAt + RECONNECT_TIMEOUT_MS;
  const minOfflineAt = startedAt + 2500;
  let delay = 1200;
  let sawDisconnect = false;
  let countdownTimer = null;

  const updateRestartCountdown = () => {
    const secs = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
    onPhase?.(tr("Device restarting... ({s}s)").replace("{s}", String(secs)));
  };

  const startCountdown = () => {
    if (countdownTimer != null) return;
    updateRestartCountdown();
    countdownTimer = setInterval(updateRestartCountdown, 1000);
  };

  const stopCountdown = () => {
    if (countdownTimer != null) {
      clearInterval(countdownTimer);
      countdownTimer = null;
    }
  };

  writeSession({ kind, phase: "rebooting", startedAt });

  try {
    while (Date.now() < deadline) {
      if (abortCtrl?.signal.aborted) return false;
      try {
        await fetchBootstrap();
        if (sawDisconnect && Date.now() >= minOfflineAt) {
          stopCountdown();
          hideOverlay();
          toast(doneMsg);
          const url = new URL(window.location.href);
          url.searchParams.set("v", String(Date.now()));
          window.location.replace(url.toString());
          return true;
        }
        stopCountdown();
        onPhase?.(tr("Waiting for device to restart..."));
      } catch {
        sawDisconnect = true;
        startCountdown();
      }
      await sleep(delay);
      delay = Math.min(Math.round(delay * 1.15), 3000);
    }
  } finally {
    stopCountdown();
  }

  showOverlay({
    title: tr("Connection timed out"),
    message: tr("The device did not come back online in time. It may still be updating — wait a minute and refresh the page."),
    hint: "",
    progress: null,
    showDismiss: true,
  });
  return false;
}

async function pollAgnosJob(onUpdate) {
  while (true) {
    if (abortCtrl?.signal.aborted) return "aborted";
    const st = await apiGet("/api/opui/agnos").catch(() => null);
    if (!st?.ok) {
      await sleep(AGNOS_POLL_MS);
      continue;
    }
    const job = st.job || {};
    if (job.status === "running" || st.install_running) {
      const pct = typeof job.progress === "number" ? job.progress : (typeof st.progress === "number" ? st.progress : null);
      onUpdate?.(job.message || tr("Installing AGNOS update..."), pct);
      await sleep(AGNOS_POLL_MS);
      continue;
    }
    if (job.status === "done") return "done";
    if (job.status === "failed") return job.message || tr("AGNOS update failed");
    if (!st.update_required && !st.install_running) return "done";
    await sleep(AGNOS_POLL_MS);
  }
}

export function isSystemWaitActive() {
  return active;
}

export async function runAgnosUpdateFlow({ readyToReboot = false } = {}) {
  if (active) return;
  abortCtrl = new AbortController();

  const title = readyToReboot ? tr("Rebooting") : tr("AGNOS Update");
  showOverlay({
    title,
    message: readyToReboot ? tr("Rebooting to apply AGNOS update...") : tr("Preparing AGNOS update..."),
    hint: tr("Do not power off the device."),
    progress: readyToReboot ? null : 0,
  });

  const endpoint = readyToReboot ? "/api/opui/agnos/reboot" : "/api/opui/agnos/install";
  const res = await apiPost(endpoint).catch((err) => ({ ok: false, error: err?.message }));

  if (!res?.ok) {
    showOverlay({
      title: tr("Update failed"),
      message: res?.error || tr("Failed"),
      showDismiss: true,
    });
    return;
  }

  if (res.action === "reboot" || readyToReboot) {
    await waitForDeviceReconnect({
      kind: "agnos",
      startedAt: Date.now(),
      onPhase: (msg) => showOverlay({ title, message: msg, hint: tr("Do not power off the device.") }),
    });
    return;
  }

  if (res.started || res.already_running) {
    let lastProgress = 0;
    showOverlay({
      title,
      message: tr("Installing AGNOS update..."),
      hint: tr("This may take several minutes. Do not power off the device."),
      progress: 0,
    });
    const outcome = await pollAgnosJob((msg, pct) => {
      if (typeof pct === "number") lastProgress = pct;
      showOverlay({
        title,
        message: msg,
        hint: tr("This may take several minutes. Do not power off the device."),
        progress: lastProgress,
      });
    });
    if (outcome === "aborted") return;
    if (outcome !== "done") {
      showOverlay({
        title: tr("Update failed"),
        message: String(outcome),
        showDismiss: true,
      });
      return;
    }
    showOverlay({
      title: tr("Rebooting"),
      message: tr("AGNOS update complete — rebooting..."),
      hint: tr("Do not power off the device."),
    });
    await waitForDeviceReconnect({
      kind: "agnos",
      startedAt: Date.now(),
      onPhase: (msg) => showOverlay({
        title: tr("Rebooting"),
        message: msg,
        hint: tr("Do not power off the device."),
      }),
    });
  }
}

export async function runSoftwareInstallFlow() {
  if (active) return;
  abortCtrl = new AbortController();

  const title = tr("Installing Update");
  showOverlay({
    title,
    message: tr("Applying update — device will reboot shortly..."),
    hint: tr("Do not power off the device."),
  });

  const res = await apiPost("/api/opui/action/updater_install").catch((err) => ({ ok: false, error: err?.message }));
  if (!res?.ok) {
    showOverlay({
      title: tr("Update failed"),
      message: res?.error || tr("Failed"),
      showDismiss: true,
    });
    return;
  }

  await waitForDeviceReconnect({
    kind: "software",
    startedAt: Date.now(),
    onPhase: (msg) => showOverlay({ title, message: msg, hint: tr("Do not power off the device.") }),
  });
}

export async function runRebootFlow() {
  if (active) return;
  abortCtrl = new AbortController();

  const title = tr("Rebooting");
  showOverlay({
    title,
    message: tr("Rebooting device..."),
    hint: tr("Do not power off the device."),
  });

  const res = await apiPost("/api/opui/action/reboot").catch((err) => ({ ok: false, error: err?.message }));
  if (!res?.ok) {
    showOverlay({
      title: tr("Reboot failed"),
      message: res?.error || tr("Failed"),
      showDismiss: true,
    });
    return;
  }

  await waitForDeviceReconnect({
    kind: "reboot",
    startedAt: Date.now(),
    onPhase: (msg) => showOverlay({ title, message: msg, hint: tr("Do not power off the device.") }),
    successMessage: tr("Device is back online"),
  });
}

function titleForWaitKind(kind) {
  if (kind === "agnos") return tr("Rebooting");
  if (kind === "software") return tr("Installing Update");
  return tr("Rebooting");
}

export async function resumeSystemWaitIfNeeded() {
  const sess = readSession();
  if (!sess || sess.phase !== "rebooting") return;

  abortCtrl = new AbortController();
  const title = titleForWaitKind(sess.kind);
  showOverlay({
    title,
    message: tr("Reconnecting to device..."),
    hint: tr("Do not power off the device."),
  });

  await waitForDeviceReconnect({
    kind: sess.kind || "reboot",
    startedAt: sess.startedAt || Date.now(),
    onPhase: (msg) => showOverlay({ title, message: msg, hint: tr("Do not power off the device.") }),
  });
}

export async function resumeAgnosInstallIfRunning() {
  if (active) return;
  const st = await apiGet("/api/opui/agnos").catch(() => null);
  if (!st?.ok || !st.available) return;
  if (!st.install_running && st.job?.status !== "running") return;
  await runAgnosUpdateFlow({ readyToReboot: false });
}

export function initSystemWaitOverlay() {
  bindDismiss();
  resumeSystemWaitIfNeeded();
  resumeAgnosInstallIfRunning();
}
