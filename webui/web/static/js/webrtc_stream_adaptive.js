/** Adaptive WebRTC preview tuning — safety-first; only affects livestream path. */

import { toast } from "./api.js";
import { tr } from "./i18n.js";

export const QUALITY_PREF_KEY = "opui-preview-quality";
export const QUALITY_LEVELS = ["auto", "low", "med", "high", "off"];

const CPU_WARM_C = 80;
const CPU_HOT_C = 92;
const MEM_STRESS_PCT = 85;

let effectiveQuality = "auto";
let overlayAllowed = true;
let videoPausedByPolicy = false;
let lastDowngradeToastAt = 0;
let thermalHot = false;
let deviceWarm = false;
let forcedLowReason = null;
let recommendedOverlayFps = null;
let notifyFn = null;

export function registerWebrtcNotify(fn) {
  notifyFn = fn;
}

export function getQualityPreference() {
  const v = localStorage.getItem(QUALITY_PREF_KEY) || "auto";
  return QUALITY_LEVELS.includes(v) ? v : "auto";
}

export function setQualityPreference(level) {
  if (!QUALITY_LEVELS.includes(level)) return null;
  localStorage.setItem(QUALITY_PREF_KEY, level);
  window.dispatchEvent(new CustomEvent("opui:stream-quality-changed", { detail: { level } }));
  return applyStreamQuality(level, { user: true });
}

export function getEffectiveQuality() {
  return effectiveQuality;
}

export function isPreviewStreamEnabled() {
  return getQualityPreference() !== "off";
}

export function isOverlayAllowed() {
  return overlayAllowed && !document.hidden;
}

export function shouldDrawModelOverlay() {
  return overlayAllowed && !document.hidden;
}

export function getOverlayFpsHint() {
  if (!overlayAllowed) return 0;
  if (!isPreviewStreamEnabled()) {
    let fps = 10;
    if (typeof recommendedOverlayFps === "number" && recommendedOverlayFps > 0) {
      fps = Math.min(fps, recommendedOverlayFps);
    }
    if (window.__OPUI_HEADLESS) fps = Math.min(fps, 5);
    return fps;
  }
  let fps = 15;
  if (!overlayAllowed || effectiveQuality === "low" || thermalHot || forcedLowReason) fps = 5;
  else if (effectiveQuality === "med" || deviceWarm) fps = 10;
  if (typeof recommendedOverlayFps === "number" && recommendedOverlayFps > 0) {
    fps = Math.min(fps, recommendedOverlayFps);
  }
  if (window.__OPUI_HEADLESS) fps = Math.min(fps, 5);
  return fps;
}

export function setRecommendedOverlayFps(fps) {
  if (typeof fps === "number" && fps > 0) recommendedOverlayFps = fps;
}

function weakClientNetwork() {
  const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
  if (!conn) return false;
  if (conn.saveData) return true;
  return conn.effectiveType === "slow-2g" || conn.effectiveType === "2g";
}

function isThermalHot(device) {
  const t = String(device?.thermal || "ok").toLowerCase();
  return t === "overheated" || t === "critical" || t === "danger";
}

function isDeviceWarm(device) {
  if (isThermalHot(device)) return true;
  const cpu = device?.cpu_temp;
  return cpu != null && cpu >= CPU_WARM_C && cpu < CPU_HOT_C;
}

function isResourceStressed(device) {
  const mem = device?.memory_usage_percent;
  const cpu = device?.cpu_temp;
  if (mem != null && mem >= MEM_STRESS_PCT) return true;
  if (cpu != null && cpu >= CPU_HOT_C) return true;
  return false;
}

function pickStressReason(device) {
  if (device?.livestream_encoder_lagging) return "encoder_lag";
  if (isThermalHot(device)) return "thermal";
  if (isResourceStressed(device)) return "resource";
  return null;
}

function resolveNotifyQuality(pref) {
  if (forcedLowReason) return "low";
  if (deviceWarm && (pref === "auto" || pref === "high")) return "med";
  if (weakClientNetwork()) {
    if (pref === "high") return "med";
    if (pref === "auto") return "low";
  }
  return pref;
}

async function sendQuality(quality) {
  if (!notifyFn) return;
  try {
    await notifyFn({ type: "livestreamSettings", data: { quality } });
  } catch {
    /* optional */
  }
}

async function sendVideoEnable(enabled) {
  if (!notifyFn) return;
  try {
    await notifyFn({ type: "livestreamVideoEnable", data: { enabled } });
  } catch {
    /* optional */
  }
}

function maybeToastDowngrade(reason) {
  const now = Date.now();
  if (now - lastDowngradeToastAt < 8000) return;
  lastDowngradeToastAt = now;
  if (reason === "thermal" || reason === "resource") {
    toast(tr("Device warm — preview switched to smooth mode"));
  } else if (reason === "encoder_lag") {
    toast(tr("Encoder busy — preview switched to smooth mode"));
  } else if (reason !== "hidden") {
    toast(tr("Weak network — preview switched to smooth mode"));
  }
}

function updateOverlayPolicy() {
  const allow = !thermalHot && !forcedLowReason
    && !document.hidden && !videoPausedByPolicy;
  if (allow === overlayAllowed) return;
  overlayAllowed = allow;
  window.dispatchEvent(new CustomEvent("opui:overlay-policy", { detail: { allowed: overlayAllowed } }));
}

export async function applyStreamQuality(pref = getQualityPreference(), opts = {}) {
  if (pref === "off") {
    effectiveQuality = "off";
    updateOverlayPolicy();
    window.dispatchEvent(new CustomEvent("opui:stream-quality-applied", { detail: { quality: "off" } }));
    window.dispatchEvent(new CustomEvent("opui:preview-stream-changed", { detail: { enabled: false } }));
    return "off";
  }

  if (effectiveQuality === "off") {
    overlayAllowed = true;
  }

  const prev = effectiveQuality;
  const q = resolveNotifyQuality(pref);
  effectiveQuality = q;
  await sendQuality(q);
  updateOverlayPolicy();
  if (q === "low" && prev !== "low" && !opts.silent) {
    maybeToastDowngrade(opts.reason || forcedLowReason);
  }
  window.dispatchEvent(new CustomEvent("opui:stream-quality-applied", { detail: { quality: q } }));
  window.dispatchEvent(new CustomEvent("opui:preview-stream-changed", { detail: { enabled: true } }));
  return q;
}

export function updateStreamDeviceState(st) {
  const device = st?.device || {};
  const warm = isDeviceWarm(device);
  const hot = isThermalHot(device) || isResourceStressed(device);
  deviceWarm = warm && !hot;
  thermalHot = hot;

  const reason = pickStressReason(device);
  if (reason) {
    if (forcedLowReason !== reason) {
      forcedLowReason = reason;
      applyStreamQuality(getQualityPreference(), { reason });
    } else {
      updateOverlayPolicy();
    }
    return;
  }

  if (forcedLowReason) {
    forcedLowReason = null;
    applyStreamQuality(getQualityPreference(), { silent: true });
    return;
  }

  if (deviceWarm) {
    applyStreamQuality(getQualityPreference(), { silent: true });
    return;
  }

  updateOverlayPolicy();
}

export async function onDocumentVisibilityChange(isStreaming) {
  if (!isStreaming) return;
  if (document.hidden) {
    videoPausedByPolicy = true;
    overlayAllowed = false;
    await sendVideoEnable(false);
    window.dispatchEvent(new CustomEvent("opui:overlay-policy", { detail: { allowed: false } }));
    return;
  }
  if (!videoPausedByPolicy) return;
  videoPausedByPolicy = false;
  await sendVideoEnable(true);
  await applyStreamQuality(getQualityPreference(), { silent: true });
}

export function initStreamAdaptive() {
  if (initStreamAdaptive._done) return;
  initStreamAdaptive._done = true;
  const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
  conn?.addEventListener?.("change", () => {
    if (forcedLowReason) return;
    applyStreamQuality(getQualityPreference(), { reason: "network" });
  });
}
