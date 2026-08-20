import { apiGet, apiPost } from "./api.js";
import { opuiWs } from "./ws.js";
import { tr } from "./i18n.js";
import { updateHomeScreen } from "./home.js";
import { replayAlertSoundFromState } from "./soundd_browser.js";

const PRESET_I18N = {
  home: "Offroad",
  onroad_engaged: "On road · Engaged",
  onroad_disengaged: "On road · Disengaged",
  lat_only: "Lateral only",
  alert_critical: "Critical alert",
  e2e_green: "E2E green",
  standstill_timer: "Standstill timer",
  long_only: "Longitudinal only",
  alert_full: "Full-screen alert",
  sound_engage: "Sound · engage",
  sound_disengage: "Sound · disengage",
  sound_warning: "Sound · warning",
  home_update: "Home · Update",
  home_alerts: "Home · Alerts",
  confidence_low: "Confidence · low",
  confidence_high: "Confidence · high",
  onroad_overlay: "On road · overlay",
  software_agnos: "Software · AGNOS",
};

function syncDevPanelI18n() {
  const title = document.getElementById("dev-panel-title");
  if (title) title.textContent = tr("PC Dev simulation");
  const overrideBtn = document.getElementById("dev-preset-override");
  if (overrideBtn) overrideBtn.textContent = tr("Override");
  document.querySelectorAll("[data-preset]").forEach((btn) => {
    const key = PRESET_I18N[btn.dataset.preset];
    if (key) btn.textContent = tr(key);
  });
  const map = {
    "dev-label-headless": "Headless (no display)",
    "dev-label-started": "On road",
    "dev-label-engaged": "Engaged",
    "dev-label-experimental": "Experimental",
    "dev-label-recording": "Recording microphone",
    "dev-label-speed": "Speed",
    "dev-label-agnos": "AGNOS update pending",
  };
  for (const [id, key] of Object.entries(map)) {
    const el = document.getElementById(id);
    if (el) el.textContent = tr(key);
  }
}

function dispatchDevState(st) {
  if (!st?.ok) return;
  window.dispatchEvent(new CustomEvent("opui:dev-state", { detail: st }));
}

function applySimLocally(patch) {
  const base = opuiWs.lastState?.data || opuiWs.bootstrap?.state;
  if (!base?.ok) return null;
  const next = { ...base, ...patch };
  if (patch.started === false) {
    next.started = false;
    next.engaged = false;
    next.ui_status = "disengaged";
    next.is_offroad = true;
  } else if (patch.started === true) {
    next.is_offroad = false;
  }
  if ("engaged" in patch) {
    next.engaged = !!patch.engaged;
    next.ui_status = patch.ui_status || (patch.engaged ? "engaged" : "disengaged");
  }
  if (patch.experimental_mode !== undefined) {
    next.experimental_mode = !!patch.experimental_mode;
  }
  if (patch.recording_audio !== undefined) {
    next.recording_audio = !!patch.recording_audio;
  }
  if (patch.speed_kmh != null) {
    next.speed_kmh = patch.speed_kmh;
  }
  next.ok = true;
  dispatchDevState(next);
  return next;
}

export async function initDevPanel() {
  const meta = await apiGet("/api/opui/bootstrap");
  if (!meta.dev_pc) return;

  const panel = document.getElementById("dev-panel");
  if (!panel) return;
  panel.hidden = false;
  syncDevPanelI18n();
  window.addEventListener("opui:language-changed", syncDevPanelI18n);

  const toggle = document.getElementById("dev-panel-toggle");
  const COLLAPSE_KEY = "opui-dev-panel-collapsed";

  const setCollapsed = (collapsed) => {
    panel.classList.toggle("opui-dev-panel--collapsed", collapsed);
    toggle?.setAttribute("aria-expanded", collapsed ? "false" : "true");
    try {
      localStorage.setItem(COLLAPSE_KEY, collapsed ? "1" : "0");
    } catch {
      /* ignore */
    }
  };

  try {
    setCollapsed(localStorage.getItem(COLLAPSE_KEY) === "1");
  } catch {
    setCollapsed(false);
  }

  toggle?.addEventListener("click", () => {
    setCollapsed(!panel.classList.contains("opui-dev-panel--collapsed"));
  });

  const headless = document.getElementById("dev-headless");
  const started = document.getElementById("dev-started");
  const engaged = document.getElementById("dev-engaged");
  const experimental = document.getElementById("dev-experimental");
  const recording = document.getElementById("dev-recording");
  const agnosPending = document.getElementById("dev-agnos-pending");
  const speed = document.getElementById("dev-speed");
  const speedVal = document.getElementById("dev-speed-val");
  let speedTimer = null;

  function syncFormFromSim(s) {
    if (!s) return;
    if (headless) headless.checked = !!s.headless;
    if (started) started.checked = !!s.started;
    if (engaged) engaged.checked = !!s.engaged;
    if (experimental) experimental.checked = !!s.experimental_mode;
    if (recording) recording.checked = !!s.recording_audio;
    if (agnosPending) agnosPending.checked = !!s.agnos_update_required;
    if (speed) speed.value = String(s.speed_kmh ?? 72);
    if (speedVal) speedVal.textContent = String(s.speed_kmh ?? 72);
  }

  async function syncFromServer() {
    const r = await apiGet("/api/opui/dev/simulation");
    if (!r.ok) return;
    syncFormFromSim(r.simulation);
    if (r.state) dispatchDevState(r.state);
    if (r.home?.ok) updateHomeScreen(r.home);
    if (r.simulation?.headless) {
      window.__OPUI_HEADLESS = true;
      window.dispatchEvent(new CustomEvent("opui:headless-sim", { detail: { headless: true } }));
    }
  }

  async function pushPatch(patch, { optimistic = true } = {}) {
    if (optimistic) {
      applySimLocally(patch);
      if (started && patch.started === false && engaged) engaged.checked = false;
      if (engaged && patch.engaged === false) engaged.checked = false;
      if (engaged && patch.engaged === true) engaged.checked = true;
    }
    const r = await apiPost("/api/opui/dev/simulation", patch);
    if (r.ok) {
      syncFormFromSim(r.simulation);
      if (r.state) dispatchDevState(r.state);
      if ("headless" in patch) {
        window.__OPUI_HEADLESS = !!patch.headless;
        window.dispatchEvent(new CustomEvent("opui:headless-sim", {
          detail: { headless: window.__OPUI_HEADLESS },
        }));
      }
      if (r.home?.ok) updateHomeScreen(r.home);
    }
    return r;
  }

  panel.querySelectorAll("[data-preset]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const r = await apiPost(`/api/opui/dev/preset/${btn.dataset.preset}`);
      if (r.ok) {
        syncFormFromSim(r.simulation);
        if (r.state) {
          dispatchDevState(r.state);
          if (r.preset?.startsWith("sound_")) replayAlertSoundFromState(r.state);
        }
        window.dispatchEvent(new CustomEvent("opui:refresh-panel"));
      }
    });
  });

  headless?.addEventListener("change", () => {
    pushPatch({ headless: headless.checked });
  });
  started?.addEventListener("change", () => {
    const patch = { started: started.checked };
    if (!started.checked) patch.engaged = false;
    pushPatch(patch);
  });
  engaged?.addEventListener("change", () => {
    pushPatch({
      engaged: engaged.checked,
      ui_status: engaged.checked ? "engaged" : "disengaged",
      alert_sound: engaged.checked ? "engage" : "disengage",
    });
  });
  experimental?.addEventListener("change", () => {
    pushPatch({ experimental_mode: experimental.checked });
  });
  recording?.addEventListener("change", () => {
    pushPatch({ recording_audio: recording.checked });
  });
  agnosPending?.addEventListener("change", () => {
    pushPatch({
      agnos_update_required: agnosPending.checked,
      agnos_ready_to_reboot: false,
    }).then(() => {
      window.dispatchEvent(new CustomEvent("opui:refresh-panel"));
    });
  });
  speed?.addEventListener("input", () => {
    const val = parseInt(speed.value, 10);
    if (speedVal) speedVal.textContent = String(val);
    applySimLocally({ speed_kmh: val });
    clearTimeout(speedTimer);
    speedTimer = setTimeout(() => pushPatch({ speed_kmh: val }, { optimistic: false }), 120);
  });

  await syncFromServer();
}
