import { apiGet, apiPut } from "./api.js";
import { tr, syncDriverCamUi } from "./i18n.js";
import { updateSpHud } from "./hud_sp.js";
import { updateDevUi } from "./hud_dev.js";
import { updateCircularAlert } from "./hud_circular.js";
import { updateConfidenceBall } from "./hud_confidence.js";
import { updateTorqueBar } from "./hud_torque.js";
import {
  startRoadStream as startRoadWebrtc,
  stopRoadStream as stopRoadWebrtc,
  updateRoadCameraForState,
  openDriverCamera,
  closeDriverCamera,
  prewarmWebrtc,
  isRoadStreaming,
  isCameraPlaying,
} from "./webrtc_stream.js?v=97";

const EXP_WHEEL_ICON = "/api/opui/assets/icons/chffr_wheel.png";
const EXP_MODE_ICON = "/api/opui/assets/icons/experimental.png";

/** ICBM cluster speed display hold — 3s wall clock (matches hud_renderer SP). */
let icbmHoldUntil = 0;
const ICBM_HOLD_MS = 3000;

let bottomFadeFiltered = 0;

let expHeldMode = null;
let expHoldUntil = 0;
let lastOnroadState = null;
let lastHudDigest = "";
let lastDriverFaceKey = "";
let hudAnimRafId = null;

function updateAnimatedOnroadHud(st) {
  applyCruiseStyle(st);
  applyExperimentalButton(st);
  updateSpHud(st);
  updateDevUi(st);
  updateCircularAlert(st);
  updateConfidenceBall(st);
}

function tickOnroadHudAnim() {
  hudAnimRafId = null;
  const app = document.getElementById("app");
  const st = lastOnroadState;
  if (!st?.ok || !st.started || app?.dataset.screen !== "onroad") {
    return;
  }
  updateAnimatedOnroadHud(st);
  hudAnimRafId = requestAnimationFrame(tickOnroadHudAnim);
}

function ensureOnroadHudAnimLoop() {
  if (hudAnimRafId != null) return;
  tickOnroadHudAnim();
}

export function stopOnroadHudAnimLoop() {
  if (hudAnimRafId != null) {
    cancelAnimationFrame(hudAnimRafId);
    hudAnimRafId = null;
  }
}

export async function startRoadStream() {
  const video = document.getElementById("road-video");
  const wrap = document.getElementById("camera-wrap");
  const fb = document.getElementById("camera-fallback");
  try {
    if (fb) fb.hidden = false;
    await startRoadWebrtc(video, wrap);
    if (lastOnroadState) updateRoadCameraForState(lastOnroadState);
  } catch (err) {
    console.error("WebRTC:", err);
    if (fb) {
      const p = document.getElementById("camera-status-text") || fb.querySelector("p");
      if (p) p.textContent = `${tr("Camera unavailable")}: ${err.message}`;
      fb.hidden = false;
    }
    throw err;
  }
}

export async function stopRoadStream() {
  const video = document.getElementById("road-video");
  const wrap = document.getElementById("camera-wrap");
  await stopRoadWebrtc(video, wrap);
}

function hudDigest(st) {
  const alert = st.alert || {};
  const sp = st.sp_hud || {};
  return [
    st.started,
    st.ui_status,
    st.speed,
    st.hide_v_ego_ui,
    st.is_metric,
    st.unit,
    st.is_cruise_available,
    st.is_cruise_set,
    st.set_speed,
    st.experimental_mode,
    st.experimental_mode_confirmed,
    st.has_longitudinal_control,
    st.engageable,
    st.engaged,
    st.car_control_enabled,
    sp.speed_limit_assist_active,
    sp.long_override,
    sp.pcm_cruise_speed,
    sp.cluster_speed,
    alert.text1,
    alert.text2,
    alert.size,
    alert.status,
    alert.height_px,
    st.developer_ui,
    st.torque_bar ? 1 : 0,
  ].join("|");
}

function driverFaceKey(st) {
  const df = st?.driver_face;
  if (!df?.visible || !df.box) return "";
  const b = df.box;
  return `${b.x}|${b.y}|${b.size}|${df.alpha}|${df.source_size?.w}|${df.source_size?.h}`;
}

function applyCruiseStyle(st) {
  const cruise = document.getElementById("hud-set-speed");
  const cruiseMax = document.querySelector(".opui-hud-cruise-max");
  if (!cruise) return;

  const status = st.ui_status || "disengaged";
  const sp = st.sp_hud || {};
  const assistActive = !!sp.speed_limit_assist_active;
  const hasSet = st.set_speed != null && st.started;
  const pcmCruise = sp.pcm_cruise_speed !== false;
  const cluster = sp.cluster_speed;
  const clusterMismatch = hasSet && cluster != null
    && Math.round(st.set_speed) !== Math.round(cluster);

  if (!pcmCruise && clusterMismatch && st.car_control_enabled) {
    icbmHoldUntil = performance.now() + ICBM_HOLD_MS;
  }

  const showIcbm = performance.now() < icbmHoldUntil;

  cruise.className = "opui-hud-cruise";
  if (hasSet) cruise.classList.add("is-set");
  if (assistActive) {
    cruise.classList.add("opui-hud-cruise--sla");
    if (sp.long_override) cruise.classList.add("is-override");
  } else if (hasSet) {
    cruise.classList.add(`opui-hud-cruise--${status}`);
  }

  if (cruiseMax) {
    cruiseMax.classList.toggle("is-icbm", showIcbm);
    cruiseMax.textContent = showIcbm ? String(Math.round(cluster)) : tr("MAX");
  }
}

function applyCruiseRadius() {
  const cruise = document.getElementById("hud-set-speed");
  if (!cruise || cruise.hidden) return;
  const w = cruise.offsetWidth;
  const h = cruise.offsetHeight;
  if (w > 0 && h > 0) {
    cruise.style.borderRadius = `${Math.round(Math.min(w, h) * 0.35)}px`;
  }
}

function applyExperimentalButton(st) {
  const expBtn = document.getElementById("btn-experimental");
  const expIcon = document.getElementById("exp-icon");
  if (!expBtn || !expIcon) return;

  const show = !!st.started;
  expBtn.hidden = !show;

  const canToggle = !!st.experimental_mode_confirmed && !!st.has_longitudinal_control;
  const engageable = !!st.engageable || !!st.engaged;
  expBtn.classList.toggle("is-engageable", engageable);
  expBtn.classList.toggle("is-disabled", !canToggle);
  expBtn.disabled = !canToggle;

  const now = performance.now();
  let mode = !!st.experimental_mode;
  if (expHoldUntil > now && expHeldMode !== null) {
    mode = expHeldMode;
  } else if (expHoldUntil) {
    expHeldMode = null;
    expHoldUntil = 0;
  }
  expIcon.src = mode ? EXP_MODE_ICON : EXP_WHEEL_ICON;
  const pressed = !engageable || expBtn.matches(":active");
  expBtn.classList.toggle("is-pressed", pressed);
  expBtn.classList.toggle("is-not-engageable", !engageable);
}

function updateCameraBottomFade(st) {
  const fade = document.getElementById("camera-bottom-fade");
  if (!fade) return;
  const engaged = !!st.started && st.ui_status !== "disengaged";
  const target = engaged && !!st.torque_bar ? 1 : 0;
  const k = 1 - Math.exp(-1 / (20 * 0.1));
  bottomFadeFiltered += (target - bottomFadeFiltered) * k;
  fade.style.opacity = String(Math.max(0, Math.min(1, bottomFadeFiltered)));
}

export function updateOnroadHud(st) {
  if (!st?.ok) return;
  lastOnroadState = st;
  updateRoadCameraForState(st);

  const digest = hudDigest(st);
  const staticChanged = digest !== lastHudDigest;
  if (staticChanged) lastHudDigest = digest;

  const hud = document.getElementById("hud");
  const speedEl = document.getElementById("hud-speed");
  const unitEl = document.getElementById("hud-unit");
  const setSpeedWrap = document.getElementById("hud-set-speed");
  const setSpeedVal = document.getElementById("set-speed-val");
  const alertBar = document.getElementById("alert-bar");
  const alertT1 = document.getElementById("alert-text1");
  const alertT2 = document.getElementById("alert-text2");
  const border = document.getElementById("border");
  const cameraWrap = document.getElementById("camera-wrap");
  const app = document.getElementById("app");

  if (staticChanged) {
    if (app) app.dataset.metric = st.is_metric === false ? "0" : "1";
    const activeDrive = ["engaged", "lat_only", "long_only"].includes(st.ui_status);
    if (hud) {
      hud.classList.toggle("is-engaged", activeDrive);
      hud.classList.toggle("is-torque-fade", activeDrive && !!st.torque_bar);
    }
    cameraWrap?.classList.toggle("is-onroad", !!st.started);

    const hideSpeed = !!st.hide_v_ego_ui;
    if (speedEl) {
      if (hideSpeed || st.speed == null) {
        speedEl.textContent = "";
        speedEl.hidden = true;
      } else {
        speedEl.hidden = false;
        speedEl.textContent = String(st.speed);
      }
    }
    if (unitEl) {
      if (hideSpeed) {
        unitEl.hidden = true;
      } else {
        unitEl.hidden = false;
        unitEl.textContent = st.unit || (st.is_metric === false ? "mph" : "km/h");
      }
    }

    const cruiseAvailable = st.is_cruise_available !== false;
    if (st.started && setSpeedWrap && setSpeedVal && cruiseAvailable) {
      setSpeedWrap.hidden = false;
      setSpeedVal.textContent = st.is_cruise_set && st.set_speed != null
        ? String(st.set_speed) : "–";
    } else if (setSpeedWrap) {
      setSpeedWrap.hidden = true;
    }

    applyCruiseRadius();

    if (border) {
      const inner = border.querySelector(".opui-border__inner");
      if (inner) {
        inner.className = `opui-border__inner opui-border--${st.ui_status || "disengaged"}`;
      }
    }

    if (alertBar && alertT1) {
      const t1 = st.alert?.text1 || "";
      const t2 = st.alert?.text2 || "";
      const size = (st.alert?.size || "").toLowerCase();
      if (t1 && st.started && size !== "none") {
        alertBar.hidden = false;
        alertT1.textContent = tr(t1);
        if (alertT2) {
          alertT2.textContent = tr(t2);
          alertT2.hidden = !t2 || size === "small";
        }
        alertBar.classList.remove("opui-alert--small", "opui-alert--mid", "opui-alert--full");
        if (size === "full") alertBar.classList.add("opui-alert--full");
        else if (size === "small") alertBar.classList.add("opui-alert--small");
        else alertBar.classList.add("opui-alert--mid");
        const heightPx = Number(st.alert?.height_px);
        alertBar.classList.toggle("opui-alert--dynamic", heightPx > 0);
        if (heightPx > 0) {
          alertBar.style.minHeight = `${heightPx}px`;
        } else {
          alertBar.style.minHeight = "";
        }
        if (size === "full") {
          const t1Len = (t1 || "").length;
          const titleLong = t1Len > 15;
          const topLong = titleLong || (t1 || "").includes("\n");
          alertBar.style.setProperty("--alert-title-size", titleLong ? "132px" : "177px");
          alertBar.style.setProperty("--alert-title-top", topLong ? "200px" : "270px");
          alertBar.style.setProperty("--alert-subtitle-bottom", titleLong ? "361px" : "420px");
        } else {
          alertBar.style.removeProperty("--alert-title-size");
          alertBar.style.removeProperty("--alert-title-top");
          alertBar.style.removeProperty("--alert-subtitle-bottom");
        }
        alertBar.style.background = "";
        const status = (st.alert?.status || "normal").toLowerCase();
        if (status.includes("critical")) alertBar.dataset.status = "critical";
        else if (status.includes("user")) alertBar.dataset.status = "user";
        else alertBar.dataset.status = "normal";
      } else {
        alertBar.hidden = true;
        alertBar.classList.remove("opui-alert--small", "opui-alert--mid", "opui-alert--full");
        delete alertBar.dataset.status;
      }
      const devMode = Number(st.developer_ui) || 0;
      const isFull = size === "full";
      if (!isFull && devMode) {
        alertBar.style.right = (devMode === 2 || devMode === 3)
          ? "calc(var(--border-w) + var(--alert-margin) + 230px)" : "";
        alertBar.style.bottom = (devMode === 1 || devMode === 3)
          ? "calc(var(--border-w) + var(--alert-margin) + 40px)" : "";
      } else {
        alertBar.style.right = "";
        alertBar.style.bottom = "";
      }
    }
  }

  if (st.started) {
    updateAnimatedOnroadHud(st);
    ensureOnroadHudAnimLoop();
  } else {
    stopOnroadHudAnimLoop();
    updateAnimatedOnroadHud(st);
  }

  updateTorqueBar(st, Number(st.developer_ui) || 0);
  updateCameraBottomFade(st);

  const faceKey = driverFaceKey(st);
  if (faceKey !== lastDriverFaceKey) {
    lastDriverFaceKey = faceKey;
    updateDriverCameraOverlay(st);
  }
}

function updateDriverCameraOverlay(st) {
  const dlg = document.getElementById("driver-camera-dialog");
  if (!dlg?.open) return;

  const loading = document.getElementById("driver-cam-loading");
  const video = document.getElementById("driver-video");
  const face = document.getElementById("driver-face-box");
  if (!loading || !video || !face) return;

  const hasFrame = video.readyState >= 2 && !video.paused;
  loading.hidden = hasFrame;

  const df = st?.driver_face;
  if (!hasFrame || !df?.visible || !df.box) {
    face.hidden = true;
    return;
  }

  const vw = video.videoWidth || df.source_size?.w || 1928;
  const vh = video.videoHeight || df.source_size?.h || 1208;
  const rect = video.getBoundingClientRect();
  const scaleX = rect.width / vw;
  const scaleY = rect.height / vh;
  const box = df.box;
  const size = (box.size || 220) * Math.min(scaleX, scaleY);
  const left = (box.x || 0) * scaleX;
  const top = (box.y || 0) * scaleY;

  face.hidden = false;
  face.style.width = `${size}px`;
  face.style.height = `${size}px`;
  face.style.left = `${left}px`;
  face.style.top = `${top}px`;
  face.style.opacity = String(df.alpha ?? 0.7);
}

export function bindExperimentalButton() {
  document.getElementById("btn-experimental")?.addEventListener("click", async () => {
    const boot = await apiGet("/api/opui/bootstrap").catch(() => ({}));
    const st = boot?.state || lastOnroadState || {};
    if (!st.experimental_mode_confirmed || !st.has_longitudinal_control) return;
    const cur = !!st.experimental_mode;
    const next = !cur;
    await apiPut("/api/opui/params/ExperimentalMode", { value: next ? "1" : "0" });
    expHeldMode = next;
    expHoldUntil = performance.now() + 2000;
    applyExperimentalButton({ ...st, experimental_mode: next });
    updateRoadCameraForState({ ...st, experimental_mode: next });
  });
}

export function bindDriverCameraDialog() {
  const dlg = document.getElementById("driver-camera-dialog");
  if (!dlg) return;

  const video = document.getElementById("driver-video");
  const loading = document.getElementById("driver-cam-loading");
  const onVideoFrame = () => {
    if (loading) loading.hidden = true;
    if (lastOnroadState) updateDriverCameraOverlay(lastOnroadState);
  };
  video?.addEventListener("loadeddata", onVideoFrame);
  video?.addEventListener("playing", onVideoFrame);

  window.addEventListener("opui:open-driver-camera", async () => {
    try {
      syncDriverCamUi();
      if (loading) {
        loading.hidden = false;
        const text = document.getElementById("driver-cam-loading-text");
        if (text) text.textContent = tr("camera starting");
      }
      if (!dlg.open) dlg.showModal();
      await openDriverCamera(lastOnroadState);
    } catch (err) {
      console.warn("Driver camera:", err);
      const text = document.getElementById("driver-cam-loading-text");
      if (text) text.textContent = String(err.message || err);
    }
  });

  const onClose = () => closeDriverCamera().catch(() => {});
  document.getElementById("driver-cam-close")?.addEventListener("click", () => dlg.close());
  dlg.addEventListener("close", onClose);
  dlg.addEventListener("click", (ev) => {
    if (ev.target === dlg) dlg.close();
  });
}

export { prewarmWebrtc, isRoadStreaming, isCameraPlaying, applyPreviewOffUi } from "./webrtc_stream.js?v=97";
export {
  applyStreamQuality,
  getQualityPreference,
  getEffectiveQuality,
  getOverlayFpsHint,
  isOverlayAllowed,
  isPreviewStreamEnabled,
  shouldDrawModelOverlay,
  onDocumentVisibilityChange,
  setQualityPreference,
  updateStreamDeviceState,
} from "./webrtc_stream.js?v=97";
