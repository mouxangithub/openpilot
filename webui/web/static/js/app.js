import { apiGet, apiPost } from "./api.js";
import {
  loadPanelList, renderPanel, setGlobalState, setHomeState, setSubpanelNavigator,
  applyPanelSync, syncDrivingPersonality, notifyPanelWatch, applyPanelCustom, clearPanelDomCache,
} from "./panels.js?v=106";
import { startRoadStream, stopRoadStream, updateOnroadHud, bindExperimentalButton, bindDriverCameraDialog, prewarmWebrtc, isCameraPlaying, isRoadStreaming, updateStreamDeviceState, onDocumentVisibilityChange, isOverlayAllowed, shouldDrawModelOverlay, getOverlayFpsHint, isPreviewStreamEnabled, applyPreviewOffUi, stopOnroadHudAnimLoop } from "./onroad.js";
import { setRecommendedOverlayFps } from "./webrtc_stream_adaptive.js";
import { getOverlayProjectionSize, syncModelOverlayViewport } from "./model_viewport.js";
import { updateHomeScreen, showHomeLoading, refreshHomeScreen, bindHomeHeader, applyLiveStartupBlockers } from "./home.js";
import { updateSidebarMetrics, updateSidebarMode, updateSidebarRecording } from "./sidebar.js";
import { bindDmArcClick } from "./hud_sp.js";
import { initDevPanel } from "./dev.js";
import { initModelCanvas, showModelOverlay, scheduleDrawModelOverlay, setModelOverlayEnabled, hasOverlayGeometry } from "./model_canvas.js";
import { loadI18n, translatePanelTitle, syncStaticUiStrings, tr } from "./i18n.js";
import { initOnboarding, bindOnboardingDialog } from "./onboarding.js";
import { initWebUiUpdate, refreshWebUiUpdateI18n } from "./webui_update.js";
import { initSystemWaitOverlay } from "./system_wait_overlay.js";
import { initScreenSaver, updateScreenSaverState } from "./screensaver.js";
import { opuiWs } from "./ws.js";
import { clientToOpui } from "./opui_coords.js";
import { initBrowserSounds, updateAlertSound } from "./soundd_browser.js";

export { clientToOpui };

const $ = (sel) => document.querySelector(sel);

const app = $("#app");
const settingsSidebar = $("#settings-sidebar");
const metricsSidebar = $("#metrics-sidebar");
const nav = $("#nav");
const panelContent = $("#panel-content");
const panelTitle = $("#panel-title");

let panels = [];
let currentPanel = "device";
let lastStarted = false;
let lastUiState = null;
let devPc = false;
let onroadSidebarVisible = false;
let cameraPreview = false;
let panelIconMap = {};
let roadStreamPromise = null;

function ensureRoadStream() {
  if (devPc) {
    const wrap = document.getElementById("camera-wrap");
    wrap?.classList.add("is-dev-pc");
    applyPreviewOffUi(wrap);
    scheduleOverlaySync();
    return Promise.resolve();
  }
  if (!isPreviewStreamEnabled()) {
    applyPreviewOffUi();
    scheduleOverlaySync();
    return Promise.resolve();
  }
  if (isRoadStreaming()) return Promise.resolve();
  if (roadStreamPromise) return roadStreamPromise;
  roadStreamPromise = startRoadStream()
    .catch(() => {})
    .finally(() => {
      roadStreamPromise = null;
    });
  return roadStreamPromise;
}

function assetUrl(rel) {
  if (!rel) return "";
  return `/api/opui/assets/${rel.replace(/^\//, "")}`;
}

function applyDesignTokens(tokens) {
  if (!tokens) return;
  const root = document.documentElement;
  const d = tokens.design || {};
  const c = tokens.colors || {};
  if (d.width) root.style.setProperty("--opui-w", String(d.width));
  if (d.height) root.style.setProperty("--opui-h", String(d.height));
  if (d.sidebar_width) root.style.setProperty("--sidebar-w", `${d.sidebar_width}px`);
  if (d.onroad_sidebar_width) root.style.setProperty("--onroad-sidebar-w", `${d.onroad_sidebar_width}px`);
  if (d.border_size) root.style.setProperty("--border-w", `${d.border_size}px`);
  if (d.border_roundness != null) {
    root.style.setProperty("--border-roundness", String(d.border_roundness));
    root.style.setProperty("--border-r", `calc(min(100cqw, 100cqh) * ${d.border_roundness})`);
  }
  if (c.engaged) root.style.setProperty("--engaged", c.engaged);
  if (c.disengaged) root.style.setProperty("--disengaged", c.disengaged);
  if (c.override) root.style.setProperty("--override", c.override);
  if (c.lat_only) root.style.setProperty("--lat-only", c.lat_only);
  if (c.long_only) root.style.setProperty("--long-only", c.long_only);
  if (c.alert_normal) root.style.setProperty("--alert-normal", c.alert_normal);
  if (c.alert_user) root.style.setProperty("--alert-user", c.alert_user);
  if (c.alert_critical) root.style.setProperty("--alert-critical", c.alert_critical);
  if (c.hud_engaged) root.style.setProperty("--hud-engaged", c.hud_engaged);
  if (c.hud_disengaged) root.style.setProperty("--hud-disengaged", c.hud_disengaged);
  if (c.on_bg) root.style.setProperty("--sp-on-bg", c.on_bg);
  if (c.button_primary) root.style.setProperty("--sp-primary", c.button_primary);

  const fonts = tokens.fonts || {};
  panelIconMap = tokens.panel_icons || {};
  const style = document.getElementById("opui-fonts") || document.createElement("style");
  style.id = "opui-fonts";
  const faces = Object.entries(fonts)
    .filter(([name]) => !name.toLowerCase().includes("op"))
    .map(([name, path]) => {
      const family = name === "audiowide" ? "Audiowide" : "Inter";
      const weight = name.includes("Bold") ? 700 : name.includes("Semi") ? 600 : name.includes("Medium") ? 500 : 400;
      return `
    @font-face {
      font-family: "${family}";
      font-weight: ${family === "Audiowide" ? 400 : weight};
      src: url("${assetUrl(path)}") format("${path.endsWith(".otf") ? "opentype" : "truetype"}");
    }`;
    }).join("\n");
  style.textContent = faces;
  if (!style.parentNode) document.head.appendChild(style);

  applySidebarAssets();
  fitOpuiScale();
}

function fitOpuiScale() {
  const root = document.documentElement;
  const cs = getComputedStyle(root);
  const w = parseFloat(cs.getPropertyValue("--opui-w")) || 2160;
  const h = parseFloat(cs.getPropertyValue("--opui-h")) || 1080;
  const pad = 24;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const portrait = vh > vw;
  root.classList.toggle("opui-portrait-host", portrait);
  const scale = portrait
    ? Math.min((vh - pad) / w, (vw - pad) / h, 1)
    : Math.min((vw - pad) / w, (vh - pad) / h, 1);
  root.style.setProperty("--opui-scale", String(scale));
}

/** Portrait phones rotate the canvas 90° — map touch drags to vertical scroll (scale-aware). */
function getOpuiScale() {
  return parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--opui-scale")) || 1;
}

function setupPortraitTouchScroll() {
  if (window.__opuiPortraitScrollBound) return;
  window.__opuiPortraitScrollBound = true;
  const state = { el: null, startX: 0, startY: 0, startScroll: 0, axis: null };

  const scrollSelector = ".opui-nav, .opui-panel, .opui-modal-scroll";
  const TOUCH_SLOP = 6;

  document.addEventListener("touchstart", (e) => {
    if (!document.documentElement.classList.contains("opui-portrait-host")) return;
    const el = e.target.closest(scrollSelector);
    if (!el || e.touches.length !== 1) return;
    if (el.scrollHeight <= el.clientHeight + 1) return;
    state.el = el;
    state.startX = e.touches[0].clientX;
    state.startY = e.touches[0].clientY;
    state.startScroll = el.scrollTop;
    state.axis = null;
  }, { passive: true, capture: true });

  document.addEventListener("touchmove", (e) => {
    if (!state.el) return;
    if (!document.documentElement.classList.contains("opui-portrait-host")) {
      state.el = null;
      return;
    }
    const max = state.el.scrollHeight - state.el.clientHeight;
    if (max <= 0) return;

    const dx = e.touches[0].clientX - state.startX;
    const dy = e.touches[0].clientY - state.startY;
    if (!state.axis) {
      if (Math.abs(dx) < TOUCH_SLOP && Math.abs(dy) < TOUCH_SLOP) return;
      state.axis = Math.abs(dy) >= Math.abs(dx) ? "y" : "x";
    }

    const scale = getOpuiScale();
    const delta = (state.axis === "y" ? dy : dx) / scale;
    state.el.scrollTop = Math.max(0, Math.min(max, state.startScroll + delta));
    e.preventDefault();
  }, { passive: false, capture: true });

  const end = () => {
    state.el = null;
    state.axis = null;
  };
  document.addEventListener("touchend", end, { passive: true, capture: true });
  document.addEventListener("touchcancel", end, { passive: true, capture: true });
}

function applySidebarAssets() {
  const settingsBtn = $("#btn-sidebar-settings");
  const bottomBtn = $("#btn-sidebar-bottom");
  const settingsImg = assetUrl("selfdrive/assets/images/button_settings.png");
  const homeImg = assetUrl("selfdrive/assets/images/button_home.png");
  const flagImg = assetUrl("selfdrive/assets/images/button_flag.png");
  if (settingsBtn) {
    settingsBtn.style.backgroundImage = `url("${settingsImg}")`;
    settingsBtn.style.backgroundSize = "100% 100%";
  }
  if (bottomBtn) {
    bottomBtn.style.setProperty("--sidebar-home-img", `url("${homeImg}")`);
    bottomBtn.style.setProperty("--sidebar-flag-img", `url("${flagImg}")`);
    bottomBtn.style.backgroundSize = "100% 100%";
  }
  const micBtn = document.getElementById("sidebar-mic");
  if (micBtn) {
    micBtn.style.backgroundImage = `url("${assetUrl("icons/microphone.png")}")`;
  }
}

let lastModelWatch = null;
const OVERLAY_SIZE_THRESHOLD = 8;
let refitTimer = null;
let overlayStartupTimer = null;

function scheduleOverlaySync() {
  if (overlayStartupTimer) clearTimeout(overlayStartupTimer);
  const delay = window.__OPUI_HEADLESS ? 500 : 200;
  overlayStartupTimer = setTimeout(() => {
    overlayStartupTimer = null;
    syncModelOverlayWatch();
  }, delay);
}

function cancelOverlaySync() {
  if (overlayStartupTimer) {
    clearTimeout(overlayStartupTimer);
    overlayStartupTimer = null;
  }
}

function isOverlayStreamReady() {
  const wrap = document.getElementById("camera-wrap");
  if (!wrap) return false;
  if (wrap.classList.contains("is-dev-pc")) return true;
  if (!isPreviewStreamEnabled()) return true;
  return isCameraPlaying() || isRoadStreaming();
}

function syncModelOverlayWatch() {
  if (app.dataset.screen !== "onroad") {
    opuiWs.unwatchModelOverlay();
    stopModelOverlayPoll();
    lastModelWatch = null;
    return;
  }
  syncModelOverlayViewport();
  if (!isOverlayStreamReady() || !isOverlayAllowed() || !shouldDrawModelOverlay()) {
    opuiWs.unwatchModelOverlay();
    stopModelOverlayPoll();
    setModelOverlayEnabled(false);
    lastModelWatch = null;
    return;
  }
  setModelOverlayEnabled(true);
  const { w, h } = getOverlayProjectionSize();
  const fps = getOverlayFpsHint();
  const watch = { w, h, fps };
  if (opuiWs.connected) {
    const same = lastModelWatch
      && Math.abs(lastModelWatch.w - watch.w) < OVERLAY_SIZE_THRESHOLD
      && Math.abs(lastModelWatch.h - watch.h) < OVERLAY_SIZE_THRESHOLD
      && lastModelWatch.fps === watch.fps;
    if (!same) {
      opuiWs.watchModelOverlay(w, h, fps);
      lastModelWatch = watch;
    }
    stopModelOverlayPoll();
    return;
  }
  lastModelWatch = watch;
  startModelOverlayPoll(w, h);
}

let modelOverlayPollTimer = null;
let lastOverlayEtag = null;

async function fetchModelOverlay(width, height) {
  const headers = {};
  if (lastOverlayEtag) headers["If-None-Match"] = lastOverlayEtag;
  const r = await fetch(`/api/opui/model/overlay?w=${width}&h=${height}`, { headers });
  if (r.status === 304) return null;
  const data = await r.json();
  const etag = r.headers.get("ETag");
  if (etag) lastOverlayEtag = etag;
  return data;
}

function startModelOverlayPoll(w, h) {
  stopModelOverlayPoll();
  if (opuiWs.connected || document.hidden) return;
  const poll = async () => {
    if (app.dataset.screen !== "onroad" || !isOverlayStreamReady() || !shouldDrawModelOverlay()) return;
    syncModelOverlayViewport();
    const { w: width, h: height } = getOverlayProjectionSize();
    try {
      const data = await fetchModelOverlay(width, height);
      if (data?.ok) scheduleDrawModelOverlay(data);
    } catch (_) { /* WS may already deliver frames */ }
  };
  modelOverlayPollTimer = setInterval(poll, Math.max(200, Math.round(1000 / getOverlayFpsHint())));
  poll();
}

function stopModelOverlayPoll() {
  if (modelOverlayPollTimer) {
    clearInterval(modelOverlayPollTimer);
    modelOverlayPollTimer = null;
  }
  lastOverlayEtag = null;
}

function updateCameraPreviewUi() {
  const bottomBtn = document.getElementById("btn-sidebar-bottom");
  if (!bottomBtn) return;
  const showExit = cameraPreview && !lastStarted;
  bottomBtn.disabled = false;
  bottomBtn.classList.toggle("opui-sidebar-btn--home", showExit);
  bottomBtn.classList.toggle("opui-sidebar-btn--flag", !showExit);
}

function setScreen(name) {
  const prevScreen = app.dataset.screen;
  app.dataset.screen = name;
  opuiWs.syncScreen(name);
  $("#screen-home").hidden = name !== "home";
  $("#screen-settings").hidden = name !== "settings";
  $("#screen-onroad").hidden = name !== "onroad";
  settingsSidebar.hidden = name !== "settings";

  if (name === "home") {
    onroadSidebarVisible = false;
    metricsSidebar.hidden = false;
    app.classList.remove("opui--onroad-sidebar-hidden");
    notifyPanelWatch(null);
    cancelOverlaySync();
    opuiWs.unwatchModelOverlay();
    stopModelOverlayPoll();
    stopOnroadHudAnimLoop();
    if (opuiWs.lastHome?.data) {
      updateHomeScreen(opuiWs.lastHome.data);
    } else if (opuiWs.bootstrap?.home) {
      updateHomeScreen(opuiWs.bootstrap.home);
    } else {
      refreshHomeScreen();
    }
  } else if (name === "onroad") {
    metricsSidebar.hidden = !onroadSidebarVisible;
    app.classList.toggle("opui--onroad-sidebar-hidden", !onroadSidebarVisible);
    notifyPanelWatch(null);
    ensureRoadStream();
    scheduleOverlaySync();
  } else {
    metricsSidebar.hidden = true;
    app.classList.remove("opui--onroad-sidebar-hidden");
    opuiWs.unwatchI18n();
    notifyPanelWatch(currentPanel);
    cancelOverlaySync();
    opuiWs.unwatchModelOverlay();
    stopModelOverlayPoll();
    stopOnroadHudAnimLoop();
  }

  showModelOverlay(name === "onroad");
  updateCameraPreviewUi();

  if (prevScreen === "onroad" && name !== "onroad" && !lastStarted) {
    stopRoadStream().catch(() => {});
  }
}

function toggleOnroadSidebar() {
  if (app.dataset.screen !== "onroad") return;
  onroadSidebarVisible = !onroadSidebarVisible;
  metricsSidebar.hidden = !onroadSidebarVisible;
  app.classList.toggle("opui--onroad-sidebar-hidden", !onroadSidebarVisible);
}

function openSettings(panelId = "device") {
  currentPanel = panelId;
  setScreen("settings");
  opuiWs.watchI18n();
  renderNav();
  loadCurrentPanel();
}

function iconCandidates(rel) {
  if (!rel) return [];
  const paths = [rel];
  if (rel.startsWith("sunnypilot/")) {
    paths.push(rel.replace("sunnypilot/", "openpilot/sunnypilot/"));
    paths.push(rel.replace("sunnypilot/", ""));
  }
  return [...new Set(paths)];
}

function setIconWithFallback(img, rel) {
  const candidates = iconCandidates(rel);
  let idx = 0;
  const tryNext = () => {
    if (idx >= candidates.length) {
      img.remove();
      return;
    }
    img.src = assetUrl(candidates[idx]);
    idx += 1;
  };
  img.onerror = tryNext;
  tryNext();
}

function renderNav() {
  if (!nav) return;
  const existing = new Map([...nav.querySelectorAll("button[data-panel]")].map((b) => [b.dataset.panel, b]));
  for (const p of panels) {
    let btn = existing.get(p.id);
    if (!btn) {
      btn = document.createElement("button");
      btn.type = "button";
      btn.dataset.panel = p.id;
      const iconPath = p.icon || panelIconMap[p.id] || "";
      if (iconPath) {
        const img = document.createElement("img");
        img.className = "opui-nav-icon";
        img.alt = "";
        setIconWithFallback(img, iconPath);
        btn.appendChild(img);
      }
      const span = document.createElement("span");
      btn.appendChild(span);
      btn.addEventListener("click", () => {
        currentPanel = p.id;
        renderNav();
        loadCurrentPanel();
      });
      nav.appendChild(btn);
    }
    existing.delete(p.id);
    btn.classList.toggle("active", p.id === currentPanel);
    const span = btn.querySelector("span");
    if (span) span.textContent = translatePanelTitle(p.title);
  }
  for (const orphan of existing.values()) orphan.remove();
}

async function loadCurrentPanel(options = {}) {
  await renderPanel(currentPanel, panelContent, panelTitle, options);
}

const HEADLESS_BANNER_KEY = "opui-headless-banner-dismissed";
const BANNER_AUTO_HIDE_MS = 3000;
let bannerAutoHideTimer = null;

function clearBannerAutoHide() {
  if (bannerAutoHideTimer) {
    clearTimeout(bannerAutoHideTimer);
    bannerAutoHideTimer = null;
  }
}

function scheduleBannerAutoHide() {
  clearBannerAutoHide();
  bannerAutoHideTimer = setTimeout(() => {
    bannerAutoHideTimer = null;
    showBootstrapBanner("");
  }, BANNER_AUTO_HIDE_MS);
}

function showHeadlessBanner() {
  if (devPc || !window.__OPUI_HEADLESS) return;
  try {
    if (localStorage.getItem(HEADLESS_BANNER_KEY) === "1") return;
  } catch {
    /* ignore */
  }
  const el = document.getElementById("bootstrap-banner");
  if (!el) return;
  el.hidden = false;
  el.dataset.tone = "info";
  el.classList.add("opui-bootstrap-banner--dismissible");
  el.replaceChildren();
  const text = document.createElement("span");
  text.className = "opui-bootstrap-banner-text";
  text.textContent = tr("No built-in display — use this Web UI as your primary interface.");
  const close = document.createElement("button");
  close.type = "button";
  close.className = "opui-bootstrap-banner-close";
  close.setAttribute("aria-label", tr("Close"));
  close.textContent = "×";
  close.addEventListener("click", () => {
    clearBannerAutoHide();
    try {
      localStorage.setItem(HEADLESS_BANNER_KEY, "1");
    } catch {
      /* ignore */
    }
    showBootstrapBanner("");
    el.classList.remove("opui-bootstrap-banner--dismissible");
  });
  el.append(text, close);
  scheduleBannerAutoHide();
}

function showBootstrapBanner(message, tone = "warn") {
  const el = document.getElementById("bootstrap-banner");
  if (!el) return;
  clearBannerAutoHide();
  if (!message) {
    el.hidden = true;
    el.textContent = "";
    el.replaceChildren();
    el.classList.remove("opui-bootstrap-banner--dismissible");
    return;
  }
  el.hidden = false;
  el.dataset.tone = tone;
  el.classList.remove("opui-bootstrap-banner--dismissible");
  el.textContent = message;
  if (tone === "info") scheduleBannerAutoHide();
}

async function waitWsBootstrapPayload(timeoutMs = 600) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (opuiWs.lastHome?.data?.ok || opuiWs.lastState?.data != null) break;
    await new Promise((r) => setTimeout(r, 40));
  }
}

function mergeBootstrapPayload(raw) {
  if (!raw) return raw;
  const merged = { ...raw };
  if (!merged.home?.ok && opuiWs.lastHome?.data?.ok) merged.home = opuiWs.lastHome.data;
  if (merged.state == null && opuiWs.lastState?.data != null) merged.state = opuiWs.lastState.data;
  return merged;
}

function applyBootstrapPayload(bootstrapData) {
  devPc = !!bootstrapData.dev_pc;
  window.__OPUI_DEV_PC = devPc;
  window.__OPUI_HEADLESS = !!(bootstrapData.headless || bootstrapData.state?.headless);
  window.__OPUI_HEADLESS_MODE = bootstrapData.headless_mode || "auto";
  window.__OPUI_HAS_BUILTIN_DISPLAY = bootstrapData.has_builtin_display !== false;
  if (typeof bootstrapData.recommended_overlay_fps === "number") {
    setRecommendedOverlayFps(bootstrapData.recommended_overlay_fps);
  }
  applyDesignTokens(bootstrapData);

  const home = bootstrapData.home;
  if (home?.ok) {
    updateHomeScreen(home);
    setHomeState(home);
  } else if (home?.error) {
    showBootstrapBanner(`${tr("Home data failed to load")}: ${home.error}`);
    refreshHomeScreen();
  } else if (!home) {
    refreshHomeScreen();
  }

  const st = bootstrapData.state;
  if (st?.ok) handleState(st);
  if (devPc) {
    document.getElementById("camera-wrap")?.classList.add("is-dev-pc");
    showBootstrapBanner(tr("PC preview — some data is mocked and may differ from the device"), "info");
  } else if (st?.ok === false) {
    showBootstrapBanner(`${tr("Driving state unavailable")}: ${st.error || tr("Unknown error")}`, "warn");
  } else if (window.__OPUI_HEADLESS) {
    showHeadlessBanner();
  }
}

async function bootstrap() {
  opuiWs.connect();
  showHomeLoading();
  setScreen("home");

  const httpPromise = apiGet("/api/opui/bootstrap").catch(() => null);
  const wsHelloPromise = opuiWs.waitHello(2500);
  const [httpMeta] = await Promise.all([httpPromise, wsHelloPromise]);
  await waitWsBootstrapPayload();

  let bootstrapData = mergeBootstrapPayload(opuiWs.bootstrap || httpMeta);
  if (bootstrapData) {
    applyBootstrapPayload(bootstrapData);
  } else {
    try {
      const fallback = mergeBootstrapPayload(await apiGet("/api/opui/bootstrap"));
      bootstrapData = fallback;
      if (fallback) {
        applyBootstrapPayload(fallback);
      } else {
        showBootstrapBanner(`${tr("WebSocket and HTTP bootstrap failed")}: ${tr("No response")}`);
        refreshHomeScreen();
      }
    } catch (_) {
      showBootstrapBanner(tr("WebUI not ready — run py -3 webui/dev/run_pc.py for local preview"));
      refreshHomeScreen();
    }
  }

  if (!bootstrapData) {
    showBootstrapBanner(tr("WebSocket disconnected — confirm the webui service is running"));
  }

  const panelListPromise = bootstrapData?.panels_schema?.ok
    ? Promise.resolve(bootstrapData.panels_schema.panels)
    : loadPanelList();

  const [panelResult] = await Promise.all([
    panelListPromise,
    loadI18n(true),
  ]);
  panels = panelResult;
  syncStaticUiStrings();
  if (!panels.length) {
    panels = [
      { id: "device", title: "Device" },
      { id: "toggles", title: "Toggles" },
    ];
  }
  currentPanel = panels[0]?.id || "device";
  renderNav();
}

function handleState(st) {
  lastUiState = st;
  setGlobalState(st);
  updateSidebarMetrics(st);
  updateSidebarMode(!!st.started);
  updateSidebarRecording(st);
  updateScreenSaverState(st);
  updateAlertSound(st);

  if (!st.ok) return;

  updateStreamDeviceState(st);

  if (st.started && (st.personality || st.personality_index != null)) {
    syncDrivingPersonality(st.personality, st.personality_index);
  }

  if (st.started) {
    if (!lastStarted) {
      onroadSidebarVisible = false;
    }
    if (app.dataset.screen === "home") {
      setScreen("onroad");
    } else if (app.dataset.screen === "onroad" && !devPc) {
      ensureRoadStream();
    }
    updateOnroadHud(st);
  } else {
    if (lastStarted) {
      stopRoadStream().catch(() => {});
    }
    if (app.dataset.screen === "onroad" && !cameraPreview) {
      setScreen("home");
    }
    if (cameraPreview && app.dataset.screen === "onroad") {
      updateOnroadHud(st);
    }
  }
  lastStarted = !!st.started;
  if (st.started) cameraPreview = false;
  updateCameraPreviewUi();

  if (!st.started) {
    applyLiveStartupBlockers(st);
  }
}

function setupWebSocket() {
  opuiWs.on("state", (msg) => {
    if (msg?.data) handleState(msg.data);
  });
  opuiWs.on("home", (msg) => {
    if (msg?.data) {
      updateHomeScreen(msg.data);
      setHomeState(msg.data);
    }
  });
  opuiWs.on("panel", (msg) => {
    if (app.dataset.screen !== "settings") return;
    if (msg.panel !== currentPanel) return;
    applyPanelSync(msg.data);
  });
  opuiWs.on("panel_custom", (msg) => {
    if (app.dataset.screen !== "settings") return;
    if (msg.panel !== currentPanel) return;
    applyPanelCustom(msg.panel, msg.data);
  });
  opuiWs.on("model_overlay", (msg) => {
    if (app.dataset.screen !== "onroad" || !msg?.data || !shouldDrawModelOverlay()) return;
    if (msg.data.anim_only && !hasOverlayGeometry()) {
      const { w, h } = getOverlayProjectionSize();
      fetchModelOverlay(w, h).then((data) => {
        if (data?.ok && !data.anim_only) scheduleDrawModelOverlay(data);
      }).catch(() => {});
      return;
    }
    scheduleDrawModelOverlay(msg.data);
  });
  opuiWs.on("i18n", async (msg) => {
    if (msg?.data?.ok) {
      const { applyI18nPayload } = await import("./i18n.js");
      if (applyI18nPayload(msg.data, true)) {
        clearPanelDomCache();
        renderNav();
        refreshWebUiUpdateI18n();
        syncStaticUiStrings();
        if (app.dataset.screen === "settings") loadCurrentPanel({ force: true });
      }
    }
  });
  opuiWs.on("open", () => {
    if (app.dataset.screen === "settings") notifyPanelWatch(currentPanel);
    syncModelOverlayWatch();
  });
  opuiWs.on("close", () => {
    if (app.dataset.screen === "onroad") syncModelOverlayWatch();
  });
}

setSubpanelNavigator((panelId) => {
  currentPanel = panelId;
  renderNav();
  loadCurrentPanel();
});

window.addEventListener("opui:overlay-viewport", () => {
  if (app.dataset.screen === "onroad") syncModelOverlayWatch();
});

window.addEventListener("opui:need-full-overlay", () => {
  if (app.dataset.screen !== "onroad" || !shouldDrawModelOverlay()) return;
  const { w, h } = getOverlayProjectionSize();
  fetchModelOverlay(w, h).then((data) => {
    if (data?.ok) scheduleDrawModelOverlay(data);
  }).catch(() => {});
});

window.addEventListener("opui:camera-ready", (ev) => {
  if (!ev.detail?.ready) return;
  if (app.dataset.screen === "onroad") {
    syncModelOverlayWatch();
    if (lastUiState?.ok) updateOnroadHud(lastUiState);
  }
});

window.addEventListener("opui:overlay-policy", () => {
  syncModelOverlayWatch();
});

window.addEventListener("opui:stream-quality-applied", () => {
  syncModelOverlayWatch();
});

document.addEventListener("visibilitychange", () => {
  const onroad = app.dataset.screen === "onroad";
  if (onroad && (lastStarted || cameraPreview)) {
    onDocumentVisibilityChange(isRoadStreaming()).catch(() => {});
  }
  syncModelOverlayWatch();
});

window.addEventListener("opui:open-settings", (ev) => {
  openSettings(ev.detail?.panel || "device");
});

window.addEventListener("opui:language-changed", () => {
  syncStaticUiStrings();
  refreshWebUiUpdateI18n();
  renderNav();
  clearPanelDomCache();
  if (app.dataset.screen === "settings") loadCurrentPanel({ force: true });
  if (lastUiState?.ok) updateSidebarMetrics(lastUiState);
});

window.addEventListener("opui:refresh-panel", () => {
  if (app.dataset.screen === "settings") loadCurrentPanel();
});

window.addEventListener("opui:dev-state", (ev) => {
  if (ev.detail) handleState(ev.detail);
});

window.addEventListener("opui:preview-stream-changed", (ev) => {
  applyPreviewOffUi();
  if (!ev.detail?.enabled) {
    stopRoadStream().catch(() => {});
    if (app.dataset.screen === "onroad") {
      scheduleOverlaySync();
      if (lastUiState?.ok) updateOnroadHud(lastUiState);
    }
    return;
  }
  if (app.dataset.screen === "onroad" && (lastStarted || cameraPreview)) {
    ensureRoadStream();
    scheduleOverlaySync();
  }
});

window.addEventListener("opui:headless-mode-changed", (ev) => {
  const detail = ev.detail || {};
  window.__OPUI_HEADLESS = !!detail.effective_headless;
  window.__OPUI_HEADLESS_MODE = detail.mode || "auto";
  if (typeof detail.recommended_overlay_fps === "number") {
    setRecommendedOverlayFps(detail.recommended_overlay_fps);
  }
  if (window.__OPUI_HEADLESS) showHeadlessBanner();
  else {
    const el = document.getElementById("bootstrap-banner");
    if (el && !devPc) {
      el.hidden = true;
      el.textContent = "";
    }
  }
  if (app.dataset.screen === "settings") loadCurrentPanel();
});

window.addEventListener("opui:headless-sim", (ev) => {
  window.__OPUI_HEADLESS = !!ev.detail?.headless;
  if (window.__OPUI_HEADLESS) showHeadlessBanner();
  else showBootstrapBanner("");
  if (app.dataset.screen === "settings") loadCurrentPanel();
});

$("#btn-close-settings").addEventListener("click", () => {
  setScreen(lastStarted ? "onroad" : "home");
});

$("#btn-sidebar-settings").addEventListener("click", () => openSettings("device"));

$("#btn-sidebar-bottom").addEventListener("click", async () => {
  if (cameraPreview && !lastStarted) {
    cameraPreview = false;
    await stopRoadStream();
    setScreen("home");
    return;
  }
  if (lastStarted) {
    const res = await apiPost("/api/opui/action/bookmark");
    const bottomBtn = document.getElementById("btn-sidebar-bottom");
    if (res?.ok && bottomBtn) {
      const saved = tr("Route bookmarked");
      bottomBtn.title = saved;
      bottomBtn.setAttribute("aria-label", saved);
      window.setTimeout(() => updateSidebarMode(true), 2000);
    }
  }
});

document.getElementById("btn-home-camera-preview")?.addEventListener("click", () => {
  cameraPreview = true;
  setScreen("onroad");
});

document.getElementById("sidebar-mic")?.addEventListener("click", () => {
  openSettings("toggles");
});

document.getElementById("camera-wrap")?.addEventListener("click", (ev) => {
  if (ev.target.closest(".opui-camera-fallback, .opui-exp-btn, #hud, #dm-arc-wrap")) return;
  toggleOnroadSidebar();
});

$("#home-exp-banner")?.addEventListener("click", () => openSettings("toggles"));

bindExperimentalButton();
bindDriverCameraDialog();
bindDmArcClick();
bindHomeHeader();
bindOnboardingDialog();
initModelCanvas();
applySidebarAssets();
setupWebSocket();
initBrowserSounds();

bootstrap().then(() => {
  initDevPanel();
  initWebUiUpdate();
  initSystemWaitOverlay();
  initScreenSaver();
  refreshWebUiUpdateI18n();
  initOnboarding();
  setupPortraitTouchScroll();
  fitOpuiScale();
  applyPreviewOffUi();
  if (isPreviewStreamEnabled()) prewarmWebrtc();
  const refit = () => {
    if (refitTimer) clearTimeout(refitTimer);
    refitTimer = setTimeout(() => {
      refitTimer = null;
      fitOpuiScale();
      syncModelOverlayViewport();
      syncModelOverlayWatch();
    }, 200);
  };
  window.addEventListener("resize", refit);
  window.addEventListener("orientationchange", refit);
});
