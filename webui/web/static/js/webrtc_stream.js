/** WebRTC livestream client — proxies SDP via webui, media to webrtcd on device. */


import { apiGet, apiPost } from "./api.js";
import { tr } from "./i18n.js?v=3";
import {
  applyStreamQuality,
  getQualityPreference,
  getEffectiveQuality,
  getOverlayFpsHint,
  initStreamAdaptive,
  isOverlayAllowed,
  isPreviewStreamEnabled,
  onDocumentVisibilityChange,
  registerWebrtcNotify,
  setQualityPreference,
  shouldDrawModelOverlay,
  updateStreamDeviceState,
} from "./webrtc_stream_adaptive.js";
import { tryAttachWebCodecsDecode, stopWebCodecsDecode, tuneVideoReceiver } from "./webrtc_webcodecs.js";
import { syncModelOverlayViewport } from "./model_viewport.js";


export const CAM = {
  ROAD: "road",
  WIDE: "wideRoad",
};


/** Matches openpilot onroad wide/road hysteresis (m/s).
 * Big UI: WIDE_CAM_MAX_SPEED=5.0, ROAD_CAM_MIN_SPEED=10.0 */

const WIDE_MAX_MS = 5.0;

const ROAD_MIN_MS = 10.0;


const ICE = { iceServers: [{ urls: "stun:stun.l.google.com:19302" }] };


let roadDisableTimer = null;
const ROAD_DISABLE_IDLE_MS = 5000;

function cancelRoadDisableTimer() {
  if (roadDisableTimer != null) {
    clearTimeout(roadDisableTimer);
    roadDisableTimer = null;
  }
}

function scheduleRoadDisable() {
  cancelRoadDisableTimer();
  roadDisableTimer = setTimeout(() => {
    roadDisableTimer = null;
  }, ROAD_DISABLE_IDLE_MS);
}

let roadPc = null;
let roadStreaming = false;
let roadCamera = CAM.ROAD;

let prewarmPromise = null;

let roadVideoBound = false;

let manualCamera = null;
let manualCameraOverride = false;


function setCameraStatus(msg) {

  const fb = document.getElementById("camera-fallback");

  const text = document.getElementById("camera-status-text");

  if (!fb || !text) return;

  if (msg) {

    text.textContent = msg;

    fb.hidden = false;

  } else {

    fb.hidden = true;

  }

}


export function isCameraPlaying() {
  const wrap = document.getElementById("camera-wrap");
  if (!wrap) return false;
  if (wrap.classList.contains("is-dev-pc")) return true;
  return wrap.classList.contains("is-playing");
}

function notifyCameraReady(ready) {
  window.dispatchEvent(new CustomEvent("opui:camera-ready", { detail: { ready: !!ready } }));
}

function bindRoadVideoPlayback(video, wrap) {

  if (!video || !wrap || roadVideoBound) return;

  roadVideoBound = true;

  const onPlaying = () => {
    wrap.classList.add("is-playing");
    syncModelOverlayViewport();
    setCameraStatus("");
    notifyCameraReady(true);
  };
  const onWaiting = () => {
  };
  video.addEventListener("playing", onPlaying);
  video.addEventListener("waiting", onWaiting);
  video.addEventListener("emptied", () => {
    wrap.classList.remove("is-playing");
    notifyCameraReady(false);
  });
}


function sleep(ms) {

  return new Promise((r) => setTimeout(r, ms));

}


function waitIceComplete(pc) {

  return new Promise((resolve) => {

    if (pc.iceGatheringState === "complete") {

      resolve();

      return;

    }

    const check = () => {

      if (pc.iceGatheringState === "complete") {

        pc.removeEventListener("icegatheringstatechange", check);

        resolve();

      }

    };

    pc.addEventListener("icegatheringstatechange", check);

    setTimeout(resolve, 2000);

  });

}


async function wakeWebrtcd() {

  const wakeMsg = tr("Starting live stream service (~4s)…");
  setCameraStatus(wakeMsg);

  await apiPost("/api/opui/action/webrtc_enable");

  for (let i = 3; i >= 0; i--) {
    if (i > 0) {
      const tick = tr("Starting live stream service ({s}s)…").replace("{s}", String(i));
      setCameraStatus(tick);
    }
    await sleep(1000);
  }

}


async function waitWebrtcdReady() {
  let delayMs = 200;
  for (let i = 0; i < 20; i++) {
    const schema = await apiGet("/api/opui/webrtc/schema");
    if (schema.ok) return true;
    await sleep(delayMs);
    delayMs = Math.min(2000, Math.round(delayMs * 1.5));
  }
  return false;
}


async function ensureWebrtcd() {

  if (await waitWebrtcdReady()) return;

  setCameraStatus(tr("Waking webrtcd…"));

  await wakeWebrtcd();

  if (await waitWebrtcdReady()) return;

  setCameraStatus(tr("Restarting webrtcd…"));

  await apiPost("/api/opui/action/webrtc_disable");

  await sleep(1000);

  await wakeWebrtcd();

  if (!(await waitWebrtcdReady())) {

    throw new Error("webrtcd not ready");

  }

}


/** Background warm-up after page load — avoids ~30s first SDP on user click. */

export function prewarmWebrtc() {

  if (!isPreviewStreamEnabled()) return null;

  if (prewarmPromise || roadStreaming) return prewarmPromise;

  if (window.__OPUI_DEV_PC) return null;

  prewarmPromise = (async () => {

    const boot = await apiGet("/api/opui/bootstrap").catch(() => ({}));

    if (boot.dev_pc) return;

    try {

      await ensureWebrtcd();

    } catch {

      prewarmPromise = null;

    }

  })();

  return prewarmPromise;

}


export async function notifyWebrtc(payload) {

  return apiPost("/api/opui/webrtc/notify", payload);

}


export async function switchCamera(camera) {

  if (!roadStreaming) {
    console.warn("[webrtc] switchCamera skipped: not streaming");
    return { ok: false, error: "not streaming" };
  }
  console.log("[webrtc] switching camera to", camera);
  const res = await notifyWebrtc({

    type: "livestreamCameraSwitch",

    data: { camera },

  });
  console.log("[webrtc] switchCamera response", res);
  if (res.ok) roadCamera = camera;

  return res;

}


export function getCurrentCamera() {

  return roadCamera || CAM.ROAD;

}


export function setManualCamera(camera) {

  manualCamera = camera;

  manualCameraOverride = true;

}


export function clearManualCamera() {

  manualCamera = null;

  manualCameraOverride = false;

}


function pickRoadCamera(st) {

  if (manualCameraOverride && manualCamera) return manualCamera;

  // Big UI: openpilotLongitudinalControl gates the wide-cam switch.
  // WebUI: use experimental_mode as the equivalent gate (e2e uses wide cam).
  if (!st?.experimental_mode) return CAM.ROAD;

  const v = Number(st.speed_raw);

  if (!Number.isFinite(v)) return roadCamera || CAM.ROAD;

  if (v < WIDE_MAX_MS) return CAM.WIDE;

  if (v > ROAD_MIN_MS) return CAM.ROAD;

  return roadCamera || CAM.ROAD;

}


export function updateRoadCameraForState(st) {

  if (!st?.started) return;

  const target = pickRoadCamera(st);

  if (target !== roadCamera) {

    console.log("[webrtc] auto camera switch requested", { target, roadCamera, manualCameraOverride, manualCamera, experimental: st.experimental_mode, speed: st.speed_raw });

    switchCamera(target).catch(() => {});

  }

}


async function createStream(videoEl, initCamera) {

  if (roadPc) {

    roadPc.close();

    roadPc = null;

  }

  stopWebCodecsDecode();

  roadStreaming = false;


  const pc = new RTCPeerConnection(ICE);

  pc.addTransceiver("video", { direction: "recvonly" });

  pc.ontrack = async (ev) => {

    if (!videoEl) return;

    const receiver = ev.receiver;

    const stream = ev.streams?.[0];

    const attachStandardVideo = () => {

      stopWebCodecsDecode();

      if (stream) {

        videoEl.srcObject = stream;

        tuneVideoReceiver(receiver);

        videoEl.play().catch(() => {});

      }

    };

    const usedWebCodecs = await tryAttachWebCodecsDecode(receiver, videoEl, { fallback: attachStandardVideo });

    if (!usedWebCodecs) attachStandardVideo();

  };

  pc.oniceconnectionstatechange = () => {

    const state = pc.iceConnectionState;

    if (state === "failed" || state === "disconnected") {

      setCameraStatus(tr("WebRTC connection failed ({})").replace("{}", state));

    }

  };


  const offer = await pc.createOffer();

  await pc.setLocalDescription(offer);

  await waitIceComplete(pc);


  const resp = await apiPost("/api/opui/webrtc/offer", {

    sdp: pc.localDescription.sdp,

    init_camera: initCamera,

  });

  if ((!resp.ok || !resp.sdp) && String(resp.error || "").includes("not running")) {

    await ensureWebrtcd();

    const retry = await apiPost("/api/opui/webrtc/offer", {

      sdp: pc.localDescription.sdp,

      init_camera: initCamera,

    });

    if (!retry.ok || !retry.sdp) {

      pc.close();

      throw new Error(retry.error || retry.message || "no SDP answer");

    }

    await pc.setRemoteDescription({ type: "answer", sdp: retry.sdp });

    return pc;

  }

  if (!resp.ok || !resp.sdp) {

    pc.close();

    throw new Error(resp.error || resp.message || "no SDP answer");

  }

  await pc.setRemoteDescription({ type: "answer", sdp: resp.sdp });

  return pc;

}


async function tuneStreamForBrowser() {
  await applyStreamQuality(getQualityPreference(), { silent: true });
}

export {
  applyStreamQuality,
  getQualityPreference,
  getEffectiveQuality,
  getOverlayFpsHint,
  initStreamAdaptive,
  isOverlayAllowed,
  isPreviewStreamEnabled,
  onDocumentVisibilityChange,
  setQualityPreference,
  shouldDrawModelOverlay,
  updateStreamDeviceState,
};


export function isRoadStreaming() {

  return roadStreaming;

}


export function applyPreviewOffUi(wrapEl) {
  const wrap = wrapEl || document.getElementById("camera-wrap");
  if (!wrap) return;
  const off = !isPreviewStreamEnabled();
  wrap.classList.toggle("preview-off", off);
  if (off) {
    wrap.classList.remove("is-playing");
    const fb = document.getElementById("camera-fallback");
    if (fb) fb.hidden = true;
    setCameraStatus("");
  }
}

export async function startRoadStream(videoEl, wrapEl) {

  cancelRoadDisableTimer();

  const video = videoEl || document.getElementById("road-video");

  const wrap = wrapEl || document.getElementById("camera-wrap");

  if (!video) {

    throw new Error("road-video element missing");

  }

  bindRoadVideoPlayback(video, wrap);

  if (!isPreviewStreamEnabled()) {
    wrap?.classList.add("streaming");
    applyPreviewOffUi(wrap);
    notifyCameraReady(true);
    return;
  }

  wrap?.classList.remove("preview-off");


  if (roadStreaming) {

    wrap?.classList.add("streaming");

    try { await video.play(); } catch { /* ignore */ }

    return;

  }

  clearManualCamera();


  const boot = await apiGet("/api/opui/bootstrap").catch(() => ({}));

  if (boot.dev_pc) {

    wrap?.classList.add("is-dev-pc");

    return;

  }


  setCameraStatus(tr("Starting camera service…"));

  await prewarmWebrtc();

  await ensureWebrtcd();

  setCameraStatus(tr("WebRTC negotiating (first time ~30s)…"));

  roadCamera = CAM.ROAD;

  roadPc = await createStream(video, roadCamera);

  roadStreaming = true;

  wrap?.classList.add("streaming");

  video.playsInline = true;
  video.disablePictureInPicture = true;
  video.disableRemotePlayback = true;
  await tuneStreamForBrowser();

  try { await video.play(); } catch { /* ignore */ }

}


export async function stopRoadStream(videoEl, wrapEl) {

  if (roadPc) {

    roadPc.close();

    roadPc = null;

  }

  stopWebCodecsDecode();

  roadStreaming = false;

  roadCamera = CAM.ROAD;

  clearManualCamera();

  prewarmPromise = null;

  const video = videoEl || document.getElementById("road-video");

  const wrap = wrapEl || document.getElementById("camera-wrap");

  if (video) video.srcObject = null;

  wrap?.classList.remove("streaming", "is-onroad", "is-playing");

  notifyCameraReady(false);

  setCameraStatus("");

  scheduleRoadDisable();

}

registerWebrtcNotify((payload) => notifyWebrtc(payload));
initStreamAdaptive();
