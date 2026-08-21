import { apiGet, apiPost, apiPut, toast } from "./api.js";
import { tr } from "./i18n.js";
import { getQualityPreference, setQualityPreference, QUALITY_LEVELS } from "./webrtc_stream_adaptive.js";
import {
  getWebCodecsPreference, setWebCodecsPreference, webCodecsCapable, webCodecsCapability, getStreamDecodePath,
} from "./webrtc_webcodecs.js";
import { renderWebUiUpdateRow, fetchWebUiUpdate, syncWebUiUpdateRow } from "./webui_update.js";
import { runSoftwareInstallFlow, runRebootFlow } from "./system_wait_overlay.js";
import { opuiWs } from "./ws.js";
import {
  showConfirm, showKeyboard, showTree, showHtml, showMultiOption, showQrPair,
  createSpToggle, createProgressRow, createDualButton, bindRowExpand, experimentalE2eHtml,
} from "./components.js";
import { reopenOnboarding } from "./onboarding.js";

function t(s) {
  return tr(s);
}

function trFormat(template, ...args) {
  let i = 0;
  return tr(template)
    .replace(/\{:\.(\d+)f\}/g, (_, digits) => Number(args[i++]).toFixed(Number(digits)))
    .replace(/\{\}/g, () => String(args[i++]));
}

function buildCalibrationDescHtml(w, cal) {
  const parts = [escapeHtml(t(w.desc))];
  if (cal?.has_mount_angles && cal.pitch_deg != null && cal.yaw_deg != null) {
    const pitch = cal.pitch_deg;
    const yaw = cal.yaw_deg;
    parts.push(escapeHtml(trFormat(
      " Your device is pointed {:.1f}° {} and {:.1f}° {}.",
      Math.abs(pitch),
      t(pitch > 0 ? "down" : "up"),
      Math.abs(yaw),
      t(yaw > 0 ? "left" : "right"),
    )));
  }
  if (cal?.lag_perc != null) {
    if (cal.lag_perc < 100) {
      parts.push(trFormat("<br><br>Steering lag calibration is {}% complete.", cal.lag_perc));
    } else {
      parts.push(t("<br><br>Steering lag calibration is complete."));
    }
  }
  if (cal?.torque_applicable) {
    if (cal.torque_perc < 100) {
      parts.push(trFormat(" Steering torque response calibration is {}% complete.", cal.torque_perc));
    } else {
      parts.push(t(" Steering torque response calibration is complete."));
    }
  }
  parts.push("<br><br>");
  parts.push(escapeHtml(t(
    "sunnypilot is continuously calibrating, resetting is rarely required. "
    + "Resetting calibration will restart sunnypilot if the car is powered on.",
  )));
  return parts.join("");
}

function panelHelpText(w) {
  if (w?.desc_i18n) return t(w.desc_i18n);
  if (w?.desc) return t(w.desc);
  return "";
}

function bindPanelHelp(row, w) {
  const desc = panelHelpText(w);
  if (desc) bindRowExpand(row, { desc });
}

export function clearPanelDomCache() {
  panelDomCache.clear();
}

const panelDomCache = new Map();
const panelChromeCache = new Map();

function isPanelLoadingNode(node) {
  return node?.nodeType === Node.ELEMENT_NODE && node.classList?.contains("opui-panel-loading");
}

function stashPanelDom(panelId, container) {
  if (!panelId || !container?.childNodes?.length) return;
  if (container.childNodes.length === 1 && isPanelLoadingNode(container.firstChild)) return;
  let hold = panelDomCache.get(panelId);
  if (!hold) {
    hold = document.createElement("div");
    hold.className = "opui-panel-cache-hold";
    hold.hidden = true;
    panelDomCache.set(panelId, hold);
  }
  while (container.firstChild) {
    hold.appendChild(container.firstChild);
  }
}

function restorePanelDom(panelId, container) {
  const hold = panelDomCache.get(panelId);
  if (!hold?.firstChild || !container) return false;
  disposePanelWidgets(container);
  while (container.firstChild) container.removeChild(container.firstChild);
  while (hold.firstChild) {
    container.appendChild(hold.firstChild);
  }
  return true;
}

function formatTimeAgo(ts) {
  if (ts == null || ts === "") return t("never");
  const sec = typeof ts === "number" ? ts : parseFloat(String(ts));
  if (!sec || Number.isNaN(sec)) return t("never");
  const date = new Date(sec * 1000);
  const diff = Math.floor((Date.now() - date.getTime()) / 1000);
  if (diff < 60) return t("now");
  if (diff < 3600) {
    const m = Math.floor(diff / 60);
    return (m === 1 ? t("{} minute ago") : t("{} minutes ago")).replace("{}", String(m));
  }
  if (diff < 86400) {
    const h = Math.floor(diff / 3600);
    return (h === 1 ? t("{} hour ago") : t("{} hours ago")).replace("{}", String(h));
  }
  if (diff < 604800) {
    const d = Math.floor(diff / 86400);
    return (d === 1 ? t("{} day ago") : t("{} days ago")).replace("{}", String(d));
  }
  const lang = document.documentElement.lang || "en";
  return date.toLocaleDateString(lang.startsWith("zh") ? "zh-CN" : "en-US", {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function formatLastChecked(ts) {
  return t("Last checked {}").replace("{}", formatTimeAgo(ts));
}

function formatSoftwareDownloadStatus(sw) {
  if (!sw) return "--";
  if (sw.download_status) {
    if (sw.download_status === "busy") {
      const state = sw.download_state || sw.updater_state || "";
      const known = {
        "checking...": "checking...",
        "downloading...": "downloading...",
        "finalizing update...": "finalizing update...",
      };
      return t(known[state] || state);
    }
    if (sw.download_status === "failed") return t("failed to check for update");
    if (sw.download_status === "fetch_available") return t("update available");
    if (!sw.last_update_epoch) return t("up to date, last checked never");
    return t("up to date, last checked {}").replace("{}", formatTimeAgo(sw.last_update_epoch));
  }
  return t(sw.download_value || sw.updater_state || "--");
}

const MADS_STEERING_MODE_DESCS = [
  "Remain Active: ALC will remain active when the brake pedal is pressed.",
  "Pause: ALC will pause when the brake pedal is pressed.",
  "Disengage: ALC will disengage when the brake pedal is pressed.",
];

function platformDisplayText(value) {
  if (value == null || value === "") return "";
  if (typeof value === "string") return value;
  if (typeof value === "object") {
    return value.name || value.platform || value.bundle || "";
  }
  return String(value);
}

function paramIsOn(val) {
  const v = String(val ?? "").trim().toLowerCase();
  return v === "1" || v === "true" || v === "on";
}

function resolveWidgetType(w) {
  const known = new Set([
    "section", "separator", "html", "action", "subpanel", "custom", "dual_button", "option",
    "readonly", "bool", "choice", "int", "multiple_button",
  ]);
  if (known.has(w.type)) return w.type;
  const pt = String(w.param_type || w.type || "").toUpperCase();
  if (w.buttons?.length) return "multiple_button";
  if (w.options?.length) return "choice";
  if (pt.includes("BOOL")) return "bool";
  if (pt.includes("INT") || pt.includes("FLOAT")) return w.label_format ? "option" : "int";
  if (pt.includes("STRING")) return w.options?.length ? "choice" : "readonly";
  return w.type;
}

function widgetVisible(w, panelData) {
  if (w.hide_when_paired && homeState.paired) return false;
  if (w.advanced_if) {
    const adv = panelData.values?.[w.advanced_if.param];
    if (String(adv) !== String(w.advanced_if.eq)) return false;
  }
  if (w.hide_if) {
    const dep = panelData.values?.[w.hide_if.param];
    if (w.hide_if.eq != null && String(dep) === String(w.hide_if.eq)) return false;
    if (w.hide_if.ne != null && String(dep) !== String(w.hide_if.ne)) return false;
  }
  if (!w.visible_if) return true;
  if (w.visible_if.state) return !!globalState[w.visible_if.state];
  const dep = panelData.values?.[w.visible_if.param];
  if (w.visible_if.ne != null) return String(dep) !== String(w.visible_if.ne);
  return String(dep) === String(w.visible_if.eq);
}

function resolveOptionIndex(w, rawVal) {
  const valueMap = w.value_map || {};
  const keys = Object.keys(valueMap);
  if (!keys.length) {
    const idx = parseInt(rawVal, 10);
    return Number.isNaN(idx) ? (w.min ?? 0) : idx;
  }
  const stored = parseInt(rawVal, 10);
  if (!Number.isNaN(stored)) {
    const hit = keys.find((k) => Number(valueMap[k]) === stored);
    if (hit != null) return parseInt(hit, 10);
  }
  const idx = parseInt(rawVal, 10);
  return Number.isNaN(idx) ? (w.min ?? 0) : idx;
}

function optionParamValue(w, idx) {
  const mapped = w.value_map?.[String(idx)];
  return mapped != null ? mapped : idx;
}

function formatOptionLabel(w, rawVal, panelData = panelDataRef) {
  const valueMap = w.value_map || {};
  const hasValueMap = Object.keys(valueMap).length > 0;
  const idx = hasValueMap ? resolveOptionIndex(w, rawVal) : parseInt(rawVal, 10);
  const val = Number.isNaN(idx) ? rawVal : idx;
  const fmt = w.label_format;

  if (fmt === "lane_change_timer") {
    const map = { [-1]: t("Off"), 0: t("Nudge"), 1: t("Nudgeless"), 2: `0.5 ${t("s")}`, 3: `1 ${t("s")}`, 4: `2 ${t("s")}`, 5: `3 ${t("s")}` };
    return map[val] ?? String(val);
  }
  if (fmt === "offroad_brightness") {
    if (!val) return t("Default (50%)");
    return `${val} %`;
  }
  if (fmt === "onroad_brightness") {
    if (val === 0) return t("Auto (Default)");
    if (val === 1) return t("Auto (Dark)");
    if (val === 2) return t("Screen Off");
    return `${(val - 2) * 5} %`;
  }
  if (fmt === "onroad_brightness_timer") {
    const minutes = valueMap[String(val)];
    if (minutes == null) return String(val);
    return minutes < 60 ? `${minutes} ${t("s")}` : `${Math.floor(minutes / 60)} ${t("m")}`;
  }
  if (fmt === "interactivity_timeout") {
    if (!val) return t("Default");
    return val < 60 ? `${val} ${t("s")}` : `${Math.floor(val / 60)} ${t("m")}`;
  }
  if (fmt === "screensaver_timeout") return `${Math.floor(val / 60)} m`;
  if (fmt === "lagd_delay") return `${(val / 100).toFixed(2)}s`;
  if (fmt === "camera_offset") return `${(val / 100).toFixed(2)} m`;
  if (fmt === "lane_turn_speed") {
    const mph = val / 100;
    const shown = globalState.is_metric ? Math.round(mph * 1.60934) : Math.round(mph);
    return `${shown} ${globalState.is_metric ? t("km/h") : t("mph")}`;
  }
  if (fmt === "torque_lat_accel") return `${(val / 100).toFixed(2)} m/s²`;
  if (fmt === "torque_friction") return `${(val / 100).toFixed(2)}`;
  if (fmt === "blinker_min_speed") {
    return `${val} ${globalState.is_metric ? t("km/h") : t("mph")}`;
  }
  if (fmt === "blinker_delay") return `${val} ${t("s")}`;
  if (fmt === "speed_limit_offset") {
    const offsetType = panelDataRef?.values?.SpeedLimitOffsetType ?? "0";
    if (String(offsetType) === "2") return `${val}%`;
    if (String(offsetType) === "1") return `${val} ${globalState.is_metric ? "km/h" : "mph"}`;
    return String(val);
  }
  if (fmt === "acc_long_press") {
    const mapped = valueMap[String(val)];
    return mapped != null ? String(mapped) : String(val);
  }
  if (hasValueMap) return formatMaxTimeLabel(val, valueMap);
  return String(val);
}

let panelDataRef = null;
let lastPanelVisibilityHash = "";

const UNREGISTERED_SUNNYLINK_DONGLE_ID = "UnregisteredDevice";
const SOFTWARE_UPDATER_TIMEOUT_MS = 10000;
let softwareDownloadWaitUntil = 0;
let modelsPanelPoll = null;

function stopModelsPanelPoll() {
  if (modelsPanelPoll) {
    clearInterval(modelsPanelPoll);
    modelsPanelPoll = null;
  }
}

function laneTurnOptionStep(w) {
  if (w?.param === "LaneTurnValue" && globalState.is_metric) return Math.round(100 / 1.609344);
  return w?.step ?? 1;
}

const SPEED_LIMIT_MODE_DESCS = [
  "Off: Disables the Speed Limit functions.",
  "Information: Displays the current road's speed limit.",
  "Warning: Provides a warning when exceeding the current road's speed limit.",
  "Assist: Adjusts the vehicle's cruise speed based on the current road's speed limit when operating the +/- buttons.",
];
const SPEED_LIMIT_OFFSET_DESCS = [
  "None: No Offset",
  "Fixed: Adds a fixed offset [Speed Limit + Offset]",
  "Percent: Adds a percent offset [Speed Limit + (Offset % Speed Limit)]",
];

function panelAssetUrl(rel) {
  return `/api/opui/assets/${String(rel).replace(/^\//, "")}`;
}

function buildHighlightedDescHtml(descriptions, selectedIdx) {
  return descriptions.map((key, i) => {
    const text = escapeHtml(t(key));
    return i === selectedIdx ? `<b>${text}</b>` : text;
  }).join("<br>");
}

let globalState = { started: false, engaged: false, is_offroad: true };
let homeState = { paired: false };
let onNavigateSubpanel = null;
let deviceExtrasCache = null;

async function putParam(key, value, needsCycle = false, skipEffects = false) {
  let res;
  try {
    if (opuiWs.connected) {
      res = await opuiWs.putParam(key, value, needsCycle);
      res = res || { ok: false, error: "ws failed" };
    } else {
      res = await apiPut(`/api/opui/params/${encodeURIComponent(key)}`, {
        value, needs_cycle: !!needsCycle,
      });
    }
  } catch (err) {
    res = { ok: false, error: String(err) };
  }
  if (res?.ok && !skipEffects) await applyParamSideEffects(key, value);
  return res;
}

async function removeParam(key) {
  try {
    const r = await fetch(`/api/opui/params/${encodeURIComponent(key)}`, { method: "DELETE" });
    return await r.json();
  } catch (err) {
    return { ok: false, error: String(err) };
  }
}

async function applyParamSideEffects(key, value) {
  const off = (k, v, cycle = false) => putParam(k, v, cycle, true);
  if (key === "JoystickDebugMode" && value === "1") {
    await off("LongitudinalManeuverMode", "0");
    await off("LateralManeuverMode", "0");
  } else if (key === "LongitudinalManeuverMode" && value === "1") {
    await off("JoystickDebugMode", "0");
    await off("LateralManeuverMode", "0");
  } else if (key === "LateralManeuverMode" && value === "1") {
    await off("JoystickDebugMode", "0");
    await off("LongitudinalManeuverMode", "0");
    await off("ExperimentalMode", "0");
  } else if (key === "ToyotaEnforceStockLongitudinal" && value === "1") {
    await off("AlphaLongitudinalEnabled", "0");
    await off("ToyotaStopAndGoHack", "0");
    await off("OnroadCycleRequested", "1", true);
  } else if (key === "ToyotaEnforceStockLongitudinal" && value === "0") {
    await off("OnroadCycleRequested", "1", true);
  } else if (key === "ToyotaStopAndGoHack") {
    await off("OnroadCycleRequested", "1", true);
  } else if (key === "LiveTorqueParamsToggle" && value === "0") {
    await removeParam("LiveTorqueParamsRelaxedToggle");
  } else if (key === "ShowAdvancedControls") {
    updateDeveloperCapabilities(globalState);
  } else if (key === "EnforceTorqueControl" && value === "1") {
    await off("NeuralNetworkLateralControl", "0");
  } else if (key === "NeuralNetworkLateralControl" && value === "1") {
    await off("EnforceTorqueControl", "0");
  } else if (key === "LateralJerkTorqueController" && value === "1") {
    await off("NeuralNetworkLateralControl", "0");
  } else if (key === "NeuralNetworkLateralControl" && value === "1") {
    await off("LateralJerkTorqueController", "0");
  }
  requestPanelRefresh();
}

const paramHandlers = {
  toast,
  putParam,
};

export function setGlobalState(st) {
  globalState = st || globalState;
  updateEngagedWidgets();
  syncToggleLocksFromPanel();
  updateToggleCapabilities(st);
  updateCruiseCapabilities(st);
  updateVisualsCapabilities(st);
  updateSteeringCapabilities(st);
  updateMadsSubpanel(st);
  updateLaneChangeSubpanel(st);
  updateSoftwareExtras(st);
  updateSlaCapabilities(st);
  updateModelsCapabilities(st);
  updateDeveloperCapabilities(st);
  updateModelsDynamicDesc(st);
  updateTorqueSubpanel(st);
  updateVehicleBrandCapabilities(st);
  syncMadsLimitedParams(st);
  updateSubpanelStates();
}

export function setHomeState(home) {
  if (!home) return;
  const paired = !!home.paired;
  if (homeState.paired === paired) return;
  homeState = { paired };
  requestPanelRefresh();
}

function updateToggleCapabilities(st) {
  if (!st) return;
  const hasLong = st.has_longitudinal_control !== false;
  const spRelease = !!st.is_release_branch;
  const expRow = document.querySelector('[data-param="ExperimentalMode"]');
  const expInput = expRow?.querySelector("input[type=checkbox]");
  const expDesc = expRow?.querySelector(".opui-sp-row-desc--expandable, .opui-sp-row-desc:not(.opui-sp-row-desc--hint):not(.opui-sp-row-desc--experimental)");
  const longRow = document.querySelector('[data-param="LongitudinalPersonality"]');

  if (expInput) {
    const disable = !hasLong;
    const locked = expRow?.dataset.locked === "1";
    expInput.disabled = disable || locked || (globalState.engaged && expRow?.dataset.needsCycle === "1");
    expRow?.querySelector(".opui-sp-toggle")?.classList.toggle("disabled", disable || locked);
    if (disable && expInput.checked) {
      expInput.checked = false;
      expRow?.querySelector(".opui-sp-toggle")?.classList.remove("on");
      removeParam("ExperimentalMode");
    }
    const e2e = experimentalE2eHtml();
    if (expDesc) {
      if (!hasLong) {
        let unavailable = t(
          "Experimental mode is currently unavailable on this car since the car's stock ACC is used for longitudinal control.",
        );
        if (st.alpha_longitudinal_available) {
          if (spRelease) {
            unavailable += ` ${t("An alpha version of sunnypilot longitudinal control can be tested, along with Experimental mode, on non-release branches.")}`;
          } else {
            unavailable += ` ${t("Enable the sunnypilot longitudinal control (alpha) toggle to allow Experimental mode.")}`;
          }
        } else {
          unavailable += ` ${t("sunnypilot longitudinal control may come in a future update.")}`;
        }
        expDesc.innerHTML = `<b>${unavailable}</b><br><br>${e2e}`;
      } else {
        expDesc.innerHTML = e2e;
      }
    }
  }
  longRow?.querySelectorAll("button").forEach((b) => { b.disabled = !hasLong; });
}

function syncToggleLocksFromPanel() {
  if (!panelDataRef?.widgets) return;
  for (const w of panelDataRef.widgets) {
    if (!w.param) continue;
    const row = document.querySelector(`[data-param="${CSS.escape(w.param)}"]`);
    if (!row) continue;
    if (w.locked) {
      row.dataset.locked = "1";
      const input = row.querySelector("input[type=checkbox]");
      const label = row.querySelector(".opui-sp-toggle");
      if (input) input.disabled = true;
      label?.classList.add("disabled");
      const hint = row.querySelector(".opui-sp-row-desc--hint");
      if (hint) hint.hidden = true;
    } else {
      delete row.dataset.locked;
    }
  }
}

function setPanelRowDesc(row, text) {
  if (!row || !text) return;
  let descEl = row.querySelector(".opui-sp-row-desc:not(.opui-sp-row-desc--hint):not(.opui-sp-row-desc--experimental)");
  if (!descEl) {
    descEl = document.createElement("div");
    descEl.className = "opui-sp-row-desc opui-sp-row-desc--expandable";
    descEl.hidden = true;
    row.querySelector(".opui-sp-row-text")?.appendChild(descEl);
    row.querySelector(".opui-sp-row-text")?.classList.add("opui-sp-row-text--expandable");
  }
  descEl.innerHTML = escapeHtml(t(text)).replace(/\n/g, "<br>");
}

function setPanelRowDescHtml(row, html) {
  if (!row || !html) return;
  let descEl = row.querySelector(".opui-sp-row-desc:not(.opui-sp-row-desc--hint):not(.opui-sp-row-desc--experimental)");
  if (!descEl) {
    descEl = document.createElement("div");
    descEl.className = "opui-sp-row-desc opui-sp-row-desc--expandable";
    row.querySelector(".opui-sp-row-text")?.appendChild(descEl);
    row.querySelector(".opui-sp-row-text")?.classList.add("opui-sp-row-text--expandable");
  }
  descEl.innerHTML = html;
  descEl.hidden = false;
  row.classList.add("opui-sp-row--desc-open");
}

function buildMadsSteeringDescHtml(selectedIdx, limited) {
  if (limited) {
    return `<b>${escapeHtml(t("This platform only supports Disengage mode due to vehicle limitations."))}</b>`;
  }
  let html = `${escapeHtml(t("Choose how Automatic Lane Centering (ALC) behaves after the brake pedal is manually pressed in sunnypilot."))}<br><br>`;
  MADS_STEERING_MODE_DESCS.forEach((key, i) => {
    const text = escapeHtml(t(key));
    html += i === selectedIdx ? `<b>${text}</b><br>` : `${text}<br>`;
  });
  return html;
}

function updateMadsSteeringModeDesc(selectedIdx, limited) {
  const row = document.querySelector('[data-param="MadsSteeringMode"]');
  if (!row) return;
  setPanelRowDescHtml(row, buildMadsSteeringDescHtml(selectedIdx, limited));
  row.querySelectorAll(".opui-multi-btn-group button").forEach((btn, i) => {
    if (limited) btn.disabled = i !== 2;
  });
}

function updateMadsSubpanel(st) {
  if (!st) return;
  const limited = !!st.mads_limited;
  const mainDesc = limited
    ? `${t("This feature defaults to OFF, and does not allow selection due to vehicle limitations.")}\n${t("Note: For vehicles without LFA/LKAS button, disabling this will prevent lateral control engagement.")}`
    : t("Note: For vehicles without LFA/LKAS button, disabling this will prevent lateral control engagement.");
  setToggleRowState("MadsMainCruiseAllowed", { disabled: limited, desc: mainDesc });

  const uemBase = `${t("Engage lateral and longitudinal control with cruise control engagement.")}\n${t("Note: Once lateral control is engaged via UEM, it will remain engaged until it is manually disabled via the MADS button or car shut off.")}`;
  const uemDesc = limited
    ? `${t("This feature defaults to ON, and does not allow selection due to vehicle limitations.")}\n${uemBase}`
    : uemBase;
  setToggleRowState("MadsUnifiedEngagementMode", { disabled: limited, desc: uemDesc });

  const modeIdx = limited ? 2 : parseInt(panelDataRef?.values?.MadsSteeringMode ?? "0", 10);
  updateMadsSteeringModeDesc(modeIdx, limited);
}

function updateLaneChangeSubpanel(st) {
  if (!st) return;
  const enableBsm = !!st.enable_bsm;
  const timer = parseInt(panelDataRef?.values?.AutoLaneChangeTimer ?? "0", 10);
  const bsmDisabled = !enableBsm || timer <= 0;
  const row = document.querySelector('[data-param="AutoLaneChangeBsmDelay"]');
  if (!row) return;
  const input = row.querySelector("input[type=checkbox]");
  const label = row.querySelector(".opui-sp-toggle");
  if (input) input.disabled = bsmDisabled;
  label?.classList.toggle("disabled", bsmDisabled);
}

function updateSoftwareExtras(st) {
  const row = document.querySelector('[data-param="DisableUpdates"]');
  if (!row) return;
  const offroad = st?.is_offroad !== false;
  const html = offroad
    ? `${escapeHtml(t("When enabled, automatic software updates will be off."))}<br><b>${escapeHtml(t("This requires a reboot to take effect."))}</b>`
    : escapeHtml(t('Please enable "Always Offroad" mode or turn off the vehicle to adjust these toggles.'));
  setPanelRowDescHtml(row, html);
  const input = row.querySelector("input[type=checkbox]");
  const label = row.querySelector(".opui-sp-toggle");
  if (input) input.disabled = !offroad;
  label?.classList.toggle("disabled", !offroad);
}

function setToggleRowState(param, { disabled, desc }) {
  const row = document.querySelector(`[data-param="${CSS.escape(param)}"]`);
  if (!row) return;
  const input = row.querySelector("input[type=checkbox]");
  const label = row.querySelector(".opui-sp-toggle");
  if (disabled != null) {
    if (input) input.disabled = !!disabled;
    label?.classList.toggle("disabled", !!disabled);
  }
  if (desc) setPanelRowDesc(row, desc);
}

function updateSlaCapabilities(st) {
  if (!st) return;
  const row = document.querySelector('[data-param="SpeedLimitMode"]');
  if (!row) return;
  const slaOk = !!st.sla_available;
  let modeIdx = parseInt(panelDataRef?.values?.SpeedLimitMode ?? "0", 10);
  if (!slaOk && modeIdx === 3) {
    putParam("SpeedLimitMode", "2", false, true);
    if (panelDataRef?.values) panelDataRef.values.SpeedLimitMode = "2";
    modeIdx = 2;
    row.querySelectorAll(".opui-multi-btn-group button").forEach((btn, i) => {
      btn.classList.toggle("selected", i === modeIdx);
    });
  }
  row.querySelectorAll(".opui-multi-btn-group button").forEach((btn, i) => {
    if (i === 3) btn.disabled = !slaOk;
  });
  setPanelRowDescHtml(row, buildHighlightedDescHtml(SPEED_LIMIT_MODE_DESCS, modeIdx));
  const offsetRow = document.querySelector('[data-param="SpeedLimitOffsetType"]');
  if (offsetRow) {
    const offsetIdx = parseInt(panelDataRef?.values?.SpeedLimitOffsetType ?? "0", 10);
    setPanelRowDescHtml(offsetRow, buildHighlightedDescHtml(SPEED_LIMIT_OFFSET_DESCS, offsetIdx));
  }
}

function updateModelsCapabilities(st) {
  const btn = document.querySelector("[data-models-select] button");
  if (btn) btn.disabled = !st?.is_offroad;
  const camRow = document.querySelector('[data-param="CameraOffset"]');
  if (camRow) camRow.hidden = !st?.custom_model_active;
  const turnDesire = paramIsOn(panelDataRef?.values?.LaneTurnDesire);
  const advanced = paramIsOn(panelDataRef?.values?.ShowAdvancedControls);
  const laneTurnRow = document.querySelector('[data-param="LaneTurnValue"]');
  if (laneTurnRow) laneTurnRow.hidden = !(turnDesire && advanced);
  const lagdOn = paramIsOn(panelDataRef?.values?.LagdToggle);
  const delayRow = document.querySelector('[data-param="LagdToggleDelay"]');
  if (delayRow) delayRow.hidden = lagdOn || !advanced;
}

function updateModelsDynamicDesc(st) {
  if (!st) return;
  const lagdRow = document.querySelector('[data-param="LagdToggle"]');
  if (!lagdRow) return;
  const lagdOn = paramIsOn(panelDataRef?.values?.LagdToggle);
  let desc = t("Enable this for the car to learn and adapt its steering response time. Disable to use a fixed steering response time. Keeping this on provides the stock openpilot experience.");
  if (lagdOn && st.live_lateral_delay != null) {
    desc += `\n${t("Live Steer Delay:")} ${Number(st.live_lateral_delay).toFixed(3)} s`;
  } else if (st.steer_actuator_delay != null) {
    const sw = parseFloat(panelDataRef?.values?.LagdToggleDelay ?? "20") / 100;
    const cp = Number(st.steer_actuator_delay);
    desc += `\n${t("Actuator Delay:")} ${cp.toFixed(2)} s + ${t("Software Delay:")} ${sw.toFixed(2)} s = ${t("Total Delay:")} ${(cp + sw).toFixed(2)} s`;
  }
  setPanelRowDesc(lagdRow, desc);
  const delayRow = document.querySelector('[data-param="LagdToggleDelay"]');
  if (delayRow) delayRow.hidden = lagdOn;
}

function updateDeveloperCapabilities(st) {
  if (!st) return;
  const spRelease = !!st.is_release_branch;
  const devBranch = !!st.is_development_branch;
  const advanced = paramIsOn(panelDataRef?.values?.ShowAdvancedControls);

  const adbRow = document.querySelector('[data-param="AdbEnabled"]');
  if (adbRow) {
    const disabled = !globalState.is_offroad;
    const input = adbRow.querySelector("input");
    const label = adbRow.querySelector(".opui-sp-toggle");
    if (input) input.disabled = disabled;
    label?.classList.toggle("disabled", disabled);
  }

  const joyRow = document.querySelector('[data-param="JoystickDebugMode"]');
  if (joyRow) {
    joyRow.hidden = spRelease;
    const disabled = !globalState.is_offroad;
    const input = joyRow.querySelector("input");
    const label = joyRow.querySelector(".opui-sp-toggle");
    if (input) input.disabled = disabled;
    label?.classList.toggle("disabled", disabled);
  }

  const alphaRow = document.querySelector('[data-param="AlphaLongitudinalEnabled"]');
  if (alphaRow) {
    const hideAlpha = spRelease || !st.cp_loaded || st.alpha_longitudinal_available === false;
    alphaRow.hidden = hideAlpha;
    if (hideAlpha && paramIsOn(panelDataRef?.values?.AlphaLongitudinalEnabled)) {
      removeParam("AlphaLongitudinalEnabled");
    }
    const input = alphaRow.querySelector("input");
    const label = alphaRow.querySelector(".opui-sp-toggle");
    const disabled = !!globalState.engaged;
    if (input) input.disabled = disabled;
    label?.classList.toggle("disabled", disabled);
  }

  const errRow = document.querySelector('[data-action="developer_error_log"]');
  if (errRow) errRow.hidden = spRelease;

  const ghRow = document.querySelector('[data-param="EnableGithubRunner"]');
  if (ghRow) ghRow.hidden = !advanced || spRelease;

  const cpRow = document.querySelector('[data-param="EnableCopyparty"]');
  if (cpRow) cpRow.hidden = !advanced;

  const qbRow = document.querySelector('[data-param="QuickBootToggle"]');
  if (qbRow) {
    qbRow.hidden = !advanced || spRelease || devBranch;
    const input = qbRow.querySelector("input");
    const label = qbRow.querySelector(".opui-sp-toggle");
    const disabled = !st.disable_updates;
    if (input) input.disabled = disabled;
    label?.classList.toggle("disabled", disabled);
    const desc = disabled
      ? t("Quickboot mode requires updates to be disabled. Enable 'Disable Updates' in the Software panel first.")
      : t("When toggled on, this creates a prebuilt file to allow accelerated boot times. When toggled off, it removes the prebuilt file so compilation of locally edited cpp files can be made.");
    setPanelRowDesc(qbRow, desc);
  }

  const longMan = document.querySelector('[data-param="LongitudinalManeuverMode"]');
  if (longMan) {
    longMan.hidden = spRelease;
    const disabled = !globalState.is_offroad || !st.has_longitudinal_control;
    const input = longMan.querySelector("input");
    const label = longMan.querySelector(".opui-sp-toggle");
    if (input) input.disabled = disabled || !!globalState.engaged;
    label?.classList.toggle("disabled", disabled || !!globalState.engaged);
  }

  const latMan = document.querySelector('[data-param="LateralManeuverMode"]');
  if (latMan) {
    latMan.hidden = spRelease;
    const disabled = !globalState.is_offroad;
    const input = latMan.querySelector("input");
    const label = latMan.querySelector(".opui-sp-toggle");
    if (input) input.disabled = disabled || !!globalState.engaged;
    label?.classList.toggle("disabled", disabled || !!globalState.engaged);
  }
}

function updateTorqueSubpanel(st) {
  if (!st) return;
  const selfTune = paramIsOn(panelDataRef?.values?.LiveTorqueParamsToggle);
  const relaxedRow = document.querySelector('[data-param="LiveTorqueParamsRelaxedToggle"]');
  if (relaxedRow) relaxedRow.hidden = !selfTune;
  const rtTune = paramIsOn(panelDataRef?.values?.TorqueParamsOverrideEnabled);
  const latRow = document.querySelector('[data-param="TorqueParamsOverrideLatAccelFactor"]');
  const fricRow = document.querySelector('[data-param="TorqueParamsOverrideFriction"]');
  const suffix = rtTune ? t("(Real-Time & Offline)") : t("(Offline Only)");
  [latRow, fricRow].forEach((row) => {
    if (!row) return;
    const title = row.querySelector(".opui-sp-row-title");
    if (!title) return;
    const base = row.dataset.baseTitle || title.textContent.replace(/\s*\([^)]*\)\s*$/, "");
    row.dataset.baseTitle = base;
    title.textContent = `${base} ${suffix}`;
  });
  const jerkRow = document.querySelector('[data-param="LateralJerkTorqueController"]');
  if (jerkRow) {
    const nnlc = paramIsOn(panelDataRef?.values?.NeuralNetworkLateralControl);
    const input = jerkRow.querySelector("input");
    const label = jerkRow.querySelector(".opui-sp-toggle");
    if (input) input.disabled = nnlc || !globalState.is_offroad;
    label?.classList.toggle("disabled", nnlc || !globalState.is_offroad);
  }
}

function updateVehicleBrandCapabilities(st) {
  if (!st) return;
  const teslaBtn = document.querySelector('[data-param="TeslaMadsScreenButton"]');
  if (teslaBtn) teslaBtn.hidden = !st.tesla_has_vehicle_bus;
  const subaruSng = document.querySelector('[data-param="SubaruStopAndGo"]');
  const subaruPb = document.querySelector('[data-param="SubaruStopAndGoManualParkingBrake"]');
  [subaruSng, subaruPb].forEach((row) => {
    if (!row) return;
    const disabled = !st.subaru_sng_available || !globalState.is_offroad;
    const input = row.querySelector("input");
    const label = row.querySelector(".opui-sp-toggle");
    if (input) input.disabled = disabled;
    label?.classList.toggle("disabled", disabled);
  });
  const toyotaSng = document.querySelector('[data-param="ToyotaStopAndGoHack"]');
  if (toyotaSng) {
    const hasLong = st.has_longitudinal_control !== false;
    const enforce = paramIsOn(panelDataRef?.values?.ToyotaEnforceStockLongitudinal);
    const disabled = !st.cp_loaded || !hasLong || enforce || !!globalState.engaged;
    const input = toyotaSng.querySelector("input");
    const label = toyotaSng.querySelector(".opui-sp-toggle");
    if (input) input.disabled = disabled;
    label?.classList.toggle("disabled", disabled);
    let desc = t("sunnypilot will allow some Toyota/Lexus cars to auto resume during stop and go traffic.");
    if (!st.cp_loaded) desc = `${t("Start the vehicle to check vehicle compatibility.")}\n\n${desc}`;
    else if (!hasLong || enforce) desc = `${t("sunnypilot Longitudinal Control must be available and enabled for your vehicle to use this feature.")}\n\n${desc}`;
    setPanelRowDesc(toyotaSng, desc);
  }
  const hyundaiTune = document.querySelector('[data-param="HyundaiLongitudinalTuning"]');
  if (hyundaiTune) {
    hyundaiTune.hidden = !st.alpha_longitudinal_available;
    const idx = parseInt(panelDataRef?.values?.HyundaiLongitudinalTuning ?? "0", 10);
    const descs = [
      t("Your vehicle will use the Default longitudinal tuning."),
      t("Your vehicle will use the Dynamic longitudinal tuning."),
      t("Your vehicle will use the Predictive longitudinal tuning."),
    ];
    let desc = descs[idx] || descs[0];
    const longEnabled = st.has_longitudinal_control !== false;
    let disabled = !globalState.is_offroad || !longEnabled;
    if (!globalState.is_offroad) {
      desc = t("This feature is unavailable while the car is onroad.");
      disabled = true;
    } else if (!longEnabled) {
      desc = t("This feature is unavailable because sunnypilot Longitudinal Control (Alpha) is not enabled.");
      disabled = true;
    }
    setPanelRowDesc(hyundaiTune, desc);
    hyundaiTune.querySelectorAll(".opui-multi-btn-group button").forEach((b) => { b.disabled = disabled; });
  }
}

let madsLimitedSynced = false;
async function syncMadsLimitedParams(st) {
  if (!st?.mads_limited) {
    madsLimitedSynced = false;
    return;
  }
  if (madsLimitedSynced) return;
  madsLimitedSynced = true;
  await removeParam("MadsMainCruiseAllowed");
  await putParam("MadsUnifiedEngagementMode", "1", false, true);
  await putParam("MadsSteeringMode", "2", false, true);
}

function updateCruiseCapabilities(st) {
  if (!st) return;
  const offroad = globalState.is_offroad;
  const hasLong = st.has_longitudinal_control !== false;
  const hasIcbm = !!st.has_icbm;
  const icbmAvailable = !!st.icbm_available;
  const pcm = !!st.pcm_cruise;
  const sccOk = hasLong || hasIcbm;
  const customAccOk = offroad && ((hasLong && !pcm) || hasIcbm);

  const clearIfOn = async (param) => {
    if (paramIsOn(panelDataRef?.values?.[param])) {
      await removeParam(param);
      if (panelDataRef?.values) panelDataRef.values[param] = "0";
    }
  };

  const icbmBaseDesc = "When enabled, sunnypilot will attempt to manage the built-in cruise control buttons by emulating button presses for limited longitudinal control.";
  let icbmDisabled = !offroad;
  const icbmRow = document.querySelector('[data-param="IntelligentCruiseButtonManagement"]');
  if (!offroad) {
    setToggleRowState("IntelligentCruiseButtonManagement", { disabled: true, desc: "Start the vehicle to check vehicle compatibility." });
  } else if (icbmAvailable) {
    setToggleRowState("IntelligentCruiseButtonManagement", { disabled: false, desc: icbmBaseDesc });
  } else {
    let unavailable = "sunnypilot Longitudinal Control is the default longitudinal control for this platform.";
    if (hasLong) {
      unavailable = "Disable the sunnypilot Longitudinal Control (alpha) toggle to allow Intelligent Cruise Button Management.";
      if (st.alpha_longitudinal_available) {
        unavailable += " An alpha version of sunnypilot longitudinal control can be tested, along with Experimental mode, on non-release branches.";
      } else {
        unavailable += " sunnypilot longitudinal control may come in a future update.";
      }
    }
    setToggleRowState("IntelligentCruiseButtonManagement", { disabled: true });
    if (icbmRow) {
      setPanelRowDescHtml(icbmRow, `<b>${escapeHtml(t(unavailable))}</b><br><br>${escapeHtml(t(icbmBaseDesc))}`);
    }
    clearIfOn("IntelligentCruiseButtonManagement");
  }

  setToggleRowState("DynamicExperimentalControl", { disabled: !hasLong });
  if (!hasLong) clearIfOn("DynamicExperimentalControl");

  setToggleRowState("SmartCruiseControlVision", { disabled: !sccOk });
  setToggleRowState("SmartCruiseControlMap", { disabled: !sccOk });
  if (!sccOk) {
    clearIfOn("SmartCruiseControlVision");
    clearIfOn("SmartCruiseControlMap");
  }

  let customDesc = "Enable custom Short & Long press increments for cruise speed increase/decrease.";
  let customDisabled = !customAccOk;
  if (!offroad) {
    customDesc = "Start the vehicle to check vehicle compatibility.";
    customDisabled = true;
  } else if (!customAccOk) {
    customDisabled = true;
    clearIfOn("CustomAccIncrementsEnabled");
    if (pcm) customDesc = "This feature is not supported on this platform due to vehicle limitations.";
    else customDesc = "This feature can only be used with sunnypilot longitudinal control enabled.";
  }
  setToggleRowState("CustomAccIncrementsEnabled", { disabled: customDisabled, desc: customDesc });

  document.querySelectorAll('[data-capability="custom_acc"]').forEach((row) => {
    const input = row.querySelector("input, button");
    const disabled = !customAccOk || !paramIsOn(panelDataRef?.values?.CustomAccIncrementsEnabled);
    if (input) input.disabled = disabled;
    row.classList.toggle("opui-sp-row--disabled", disabled);
  });
}

function updateVisualsCapabilities(st) {
  if (!st) return;
  const hasLong = st.has_longitudinal_control !== false;
  const chevronRow = document.querySelector('[data-param="ChevronInfo"]');
  if (chevronRow) {
    const desc = hasLong
      ? "Display useful metrics below the chevron that tracks the lead car only applicable to cars with sunnypilot longitudinal control."
      : "This feature requires sunnypilot longitudinal control to be available.";
    setPanelRowDesc(chevronRow, desc);
    chevronRow.querySelectorAll("button").forEach((b) => { b.disabled = !hasLong; });
    if (!hasLong && paramIsOn(panelDataRef?.values?.ChevronInfo)) {
      putParam("ChevronInfo", "0", false, true);
    }
  }
}

function updateSteeringCapabilities(st) {
  if (!st) return;
  const offroad = globalState.is_offroad;
  const torqueAllowed = st.torque_control_allowed !== false;
  const jerk = !!st.lateral_jerk_torque;

  const setToggleDisabled = (param, disabled) => {
    const row = document.querySelector(`[data-param="${CSS.escape(param)}"]`);
    if (!row) return;
    const input = row.querySelector("input[type=checkbox]");
    const label = row.querySelector(".opui-sp-toggle");
    if (input) input.disabled = disabled;
    label?.classList.toggle("disabled", disabled);
  };

  setToggleDisabled("Mads", !offroad);
  const madsRow = document.querySelector('[data-param="Mads"]');
  if (madsRow) {
    const baseDesc = t("Enable the beloved MADS feature. Disable toggle to revert back to stock sunnypilot engagement/disengagement.");
    if (!st.cp_loaded) {
      setPanelRowDescHtml(madsRow, `<b>${escapeHtml(t("Start the vehicle to check vehicle compatibility."))}</b><br><br>${escapeHtml(baseDesc)}`);
    } else {
      const limitedDesc = st.mads_limited
        ? t("This platform supports limited MADS settings.")
        : t("This platform supports full MADS settings.");
      setPanelRowDescHtml(madsRow, `<b>${escapeHtml(limitedDesc)}</b><br><br>${escapeHtml(baseDesc)}`);
    }
  }
  setToggleDisabled("EnforceTorqueControl", !offroad || !torqueAllowed);
  setToggleDisabled("NeuralNetworkLateralControl", !offroad || !torqueAllowed || jerk);

  const torqueOn = paramIsOn(panelDataRef?.values?.EnforceTorqueControl);
  const nnlcOn = paramIsOn(panelDataRef?.values?.NeuralNetworkLateralControl);
  setToggleDisabled("EnforceTorqueControl", !offroad || !torqueAllowed || nnlcOn);
  setToggleDisabled("NeuralNetworkLateralControl", !offroad || !torqueAllowed || jerk || torqueOn);

  updateSubpanelStates();
}

function updateSubpanelStates() {
  document.querySelectorAll(".opui-simple-btn").forEach((btn) => {
    let disabled = btn.dataset.offroadOnly === "1" && !globalState.is_offroad;
    const req = btn.dataset.requiresParam;
    const eq = btn.dataset.requiresEq;
    if (req && panelDataRef?.values) {
      disabled = disabled || String(panelDataRef.values[req]) !== String(eq);
    }
    btn.disabled = disabled;
  });
}

function applySoftwareCustom(sw) {
  if (!sw?.ok) return;
  const warn = document.getElementById("software-onroad-warn");
  if (warn) warn.hidden = !sw.is_onroad;

  const dlVal = document.getElementById("software-download-value");
  const dlBtn = document.getElementById("software-download-btn");
  const dlRow = document.getElementById("software-download-row");
  if (dlRow) dlRow.hidden = !sw.is_offroad;
  if (dlVal) dlVal.textContent = formatSoftwareDownloadStatus(sw);
  if (dlBtn) {
    dlBtn.textContent = t(sw.download_label || "CHECK");
    const waiting = softwareDownloadWaitUntil > Date.now();
    dlBtn.disabled = waiting || sw.download_enabled === false;
    dlBtn.hidden = !sw.is_offroad;
  }

  const installRow = document.getElementById("software-install-row");
  const installVal = document.getElementById("software-install-value");
  const installNotes = document.getElementById("software-install-notes");
  if (installRow) installRow.hidden = !sw.install_visible;
  if (installVal) installVal.textContent = sw.new_description || "";

  const curNotes = document.getElementById("software-current-notes");
  if (curNotes) {
    const html = sw.current_release_notes || "";
    if (html.trim().startsWith("<")) {
      curNotes.innerHTML = html;
      curNotes.classList.add("opui-html-block", "opui-release-notes");
    } else {
      curNotes.textContent = html;
      curNotes.classList.remove("opui-html-block");
    }
    curNotes.hidden = !html || curNotes.dataset.expanded !== "1";
  }

  if (installNotes) {
    const html = sw.new_release_notes || "";
    if (html.trim().startsWith("<")) {
      installNotes.innerHTML = html;
      installNotes.classList.add("opui-html-block", "opui-release-notes");
    } else {
      installNotes.textContent = html;
      installNotes.classList.remove("opui-html-block");
    }
    installNotes.hidden = !html || installNotes.dataset.expanded !== "1";
  }
}

function firehoseStatusText(active) {
  return active ? t("ACTIVE") : t("INACTIVE: connect to an unmetered network");
}

export function applyPanelCustom(panelId, data) {
  if (!data?.ok) return;
  if (panelId === "software") {
    applySoftwareCustom(data);
    updateSoftwareExtras(globalState);
  }
  if (panelId === "firehose") {
    const el = document.getElementById("firehose-status-text");
    if (el) {
      el.textContent = firehoseStatusText(data.active);
      el.style.color = data.active ? "#2ecc71" : "#e74c3c";
    }
  }
  if (panelId === "osm") {
    applyOsmCustom(data);
  }
  if (panelId === "vehicle") {
    applyVehicleCustom(data);
  }
}

function applyVehicleCustom(data) {
  if (!data?.ok) return;
  const vp = data.platforms;
  if (!vp?.ok) return;
  const titleEl = document.getElementById("vehicle-platform-title");
  const btn = document.getElementById("vehicle-platform-btn");
  if (!titleEl || !btn) return;
  const status = vp.status || (vp.manual ? "manual" : "unknown");
  const display = platformDisplayText(vp.display) || platformDisplayText(vp.active) || t("No vehicle selected");
  titleEl.textContent = display;
  titleEl.className = `opui-sp-row-title opui-vehicle-title--${status === "auto" ? "auto" : status === "manual" ? "manual" : "unknown"}`;
  btn.textContent = vp.manual ? t("REMOVE") : t("SELECT");
}

function updateEngagedWidgets() {
  const root = document.getElementById("panel-content");
  if (!root) return;
  root.querySelectorAll("[data-needs-cycle='1']").forEach((row) => {
    if (row.dataset.locked === "1") return;
    const input = row.querySelector("input[type=checkbox]");
    const label = row.querySelector(".opui-sp-toggle");
    const disabled = globalState.engaged;
    if (input) input.disabled = disabled;
    label?.classList.toggle("disabled", disabled);
  });
  root.querySelectorAll("[data-offroad-only='1']").forEach((row) => {
    const input = row.querySelector("input[type=checkbox], button");
    const disabled = !globalState.is_offroad;
    if (input) input.disabled = disabled;
  });
}

function panelVisibilityHash(data) {
  const widgets = (data.widgets || [])
    .filter((w) => widgetVisible(w, data))
    .map((w) => w.param || w.type || w.custom || w.action || "")
    .join("|");
  return `${widgets}|paired:${homeState.paired ? 1 : 0}`;
}

export function applyPanelSync(data) {
  if (!data?.ok) return;
  panelDataRef = data;
  syncToggleLocksFromPanel();
  const hash = panelVisibilityHash(data);
  if (hash !== lastPanelVisibilityHash) {
    if (currentPanelRef) panelDomCache.delete(currentPanelRef);
    lastPanelVisibilityHash = hash;
    if (data.custom) {
      const container = document.getElementById("panel-content");
      if (container) {
        if (data.custom === "software" || data.custom === "models" || data.custom === "osm") {
          container.querySelectorAll("[data-panel-widget]").forEach((el) => el.remove());
          appendPanelWidgets(container, data);
          if (data.custom === "osm") {
            ensureOsmCustomBlock(container, data);
            updateOsmLabels(document.getElementById("osm-custom-root"), data);
            const ver = document.getElementById("osm-mapd-version");
            if (ver) ver.textContent = data.values?.MapdVersion || t("Loading...");
          }
        } else {
          window.dispatchEvent(new CustomEvent("opui:refresh-panel"));
        }
      }
    } else {
      const container = document.getElementById("panel-content");
      if (container) renderGenericPanel(container, data, currentPanelRef);
    }
    updateEngagedWidgets();
    updateToggleCapabilities(globalState);
    updateCruiseCapabilities(globalState);
    updateVisualsCapabilities(globalState);
    updateSteeringCapabilities(globalState);
    updateMadsSubpanel(globalState);
    updateLaneChangeSubpanel(globalState);
    updateSoftwareExtras(globalState);
    updateDisplayDependencies(data);
    updateDeveloperCapabilities(globalState);
    if (data.custom === "osm") {
      updateOsmLabels(document.getElementById("osm-custom-root"), data);
      const ver = document.getElementById("osm-mapd-version");
      if (ver) ver.textContent = data.values?.MapdVersion || t("Loading...");
    }
    return;
  }
  const root = document.getElementById("panel-content");
  if (!root) return;
  for (const w of data.widgets || []) {
    if (!widgetVisible(w, data)) continue;
    if (w.type === "dual_button") {
      updateDualButtonRow(root, w);
      continue;
    }
    if (!w.param) continue;
    updateWidgetValue(root, w, data);
  }
  updateEngagedWidgets();
  updateToggleCapabilities(globalState);
  updateCruiseCapabilities(globalState);
  updateVisualsCapabilities(globalState);
  updateSteeringCapabilities(globalState);
  updateMadsSubpanel(globalState);
  updateLaneChangeSubpanel(globalState);
  updateSoftwareExtras(globalState);
  updateDisplayDependencies(data);
  updateDeveloperCapabilities(globalState);
  if (data.custom === "osm") {
    updateOsmLabels(document.getElementById("osm-custom-root"), data);
    const ver = document.getElementById("osm-mapd-version");
    if (ver) ver.textContent = data.values?.MapdVersion || t("Loading...");
  }
}

let currentPanelRef = "";
let panelRenderGen = 0;

function beginPanelRender() {
  return ++panelRenderGen;
}

function panelRenderStale(gen) {
  return gen !== panelRenderGen;
}

export function setCurrentPanelId(id) {
  currentPanelRef = id || "";
}

function updateWidgetValue(root, w, panelData = panelDataRef) {
  const el = root.querySelector(`[data-param="${CSS.escape(w.param)}"]`);
  if (!el) return;
  const kind = el.dataset.widget || resolveWidgetType(w);
  if (kind === "bool") {
    const checked = paramIsOn(w.value);
    const input = el.querySelector("input[type=checkbox]");
    const label = el.querySelector(".opui-sp-toggle");
    if (input) {
      input.checked = checked;
      label?.classList.toggle("on", checked);
    }
    return;
  }
  if (kind === "multiple_button" || kind === "choice") {
    let idx = parseInt(w.value, 10);
    if (Number.isNaN(idx)) idx = 0;
    el.querySelectorAll(".opui-multi-btn-group button, .opui-choice-group button").forEach((btn, i) => {
      btn.classList.toggle("selected", i === idx);
    });
    return;
  }
  if (kind === "readonly") {
    const valEl = el.querySelector(".opui-row-value");
    if (valEl) valEl.textContent = formatValue(w.value) || t("N/A");
    return;
  }
  if (kind === "int" || kind === "option") {
    const min = w.min ?? 0;
    const max = w.max ?? 100;
    let val = kind === "option" ? resolveOptionIndex(w, w.value) : parseInt(w.value, 10);
    if (Number.isNaN(val)) val = min;
    const span = el.querySelector(".opui-option-value, .opui-int-control span");
    if (span) {
      span.textContent = kind === "option" ? formatOptionLabel(w, w.value, panelData) : String(val);
    }
    const minus = el.querySelector(".opui-option-bar button:first-child, .opui-int-control button:first-child");
    const plus = el.querySelector(".opui-option-bar button:last-child, .opui-int-control button:last-child");
    if (minus) minus.disabled = val <= min;
    if (plus) plus.disabled = val >= max;
  }
}

function updateDualButtonRow(root, w) {
  const left = w.left || {};
  const right = w.right || {};
  const row = root.querySelector(`[data-dual="${CSS.escape(`${left.label || ""}|${right.label || ""}`)}"]`);
  if (!row) return;
  for (const side of ["left", "right"]) {
    const cfg = w[side];
    if (!cfg?.toggle || !cfg.param) continue;
    const btn = row.querySelector(`[data-side="${side}"]`);
    if (!btn) continue;
    btn.classList.toggle("primary", paramIsOn(cfg.value));
  }
}

function updateDisplayDependencies(data) {
  if (data?.panel !== "display") return;
  const brightness = parseInt(data.values?.OnroadScreenOffBrightness ?? "0", 10);
  const timerRow = document.querySelector('[data-param="OnroadScreenOffTimer"]');
  const disabled = brightness === 0 || brightness === 1;
  timerRow?.querySelectorAll(".opui-option-bar button").forEach((btn) => {
    btn.disabled = disabled;
  });
  timerRow?.classList.toggle("disabled", disabled);
}

function widgetUsesStacked(w) {
  return w.layout === "stacked";
}

export function syncDrivingPersonality(personality, personalityIndex) {
  let idx = personalityIndex;
  if (idx == null && personality) {
    idx = PERSONALITY_INDEX[String(personality).toLowerCase()];
  }
  if (idx == null) return;
  const el = document.querySelector('[data-param="LongitudinalPersonality"]');
  if (!el) return;
  el.querySelectorAll(".opui-multi-btn-group button").forEach((btn, i) => {
    btn.classList.toggle("selected", i === idx);
  });
}

export function notifyPanelWatch(panelId) {
  opuiWs.watchPanel(panelId || null);
}

export function setSubpanelNavigator(fn) {
  onNavigateSubpanel = fn;
}

export async function loadPanelList() {
  const data = await apiGet("/api/opui/panels");
  if (!data.ok) return [];
  const p = data.panels;
  if (Array.isArray(p)) return p;
  console.warn("panels API returned non-array; restart webui server after panel_icons fix");
  return [];
}

function applyPanelTitle(panelId, titleEl, data, options = {}) {
  if (!titleEl || !data) return;
  const header = titleEl.closest(".opui-panel-header");
  if (data.parent && options.showBack !== false) {
    header?.classList.add("opui-panel-header--subpanel");
    titleEl.innerHTML = `<button type="button" class="opui-back" data-parent="${escapeAttr(data.parent)}">‹</button> ${escapeHtml(t(data.title))}`;
    titleEl.querySelector(".opui-back")?.addEventListener("click", () => {
      if (onNavigateSubpanel) onNavigateSubpanel(data.parent);
    });
  } else {
    header?.classList.remove("opui-panel-header--subpanel");
    titleEl.textContent = "";
  }
  panelChromeCache.set(panelId, { title: data.title, parent: data.parent || null });
}

export async function renderPanel(panelId, container, titleEl, options = {}) {
  const prevPanel = currentPanelRef;
  if (container && prevPanel && prevPanel !== panelId && container.childNodes.length) {
    stashPanelDom(prevPanel, container);
  }
  currentPanelRef = panelId;
  notifyPanelWatch(panelId);
  if (!options.force && container && restorePanelDom(panelId, container)) {
    const chrome = panelChromeCache.get(panelId);
    if (chrome && titleEl) {
      applyPanelTitle(panelId, titleEl, chrome, options);
    }
    return;
  }
  if (container && !container.querySelector(".opui-panel-loading")) {
    container.innerHTML = '<p class="opui-muted opui-panel-loading" style="padding:48px;text-align:center">' + escapeHtml(t("Loading...")) + '</p>';
  }
  const data = await apiGet(`/api/opui/panels/${encodeURIComponent(panelId)}`);
  if (!data.ok) {
    container.innerHTML = `<p class="opui-muted" style="padding:48px">${escapeHtml(t("Load failed"))}: ${escapeHtml(data.error)}</p>`;
    return;
  }
  if (titleEl) {
    applyPanelTitle(panelId, titleEl, data, options);
  }

  if (data.custom === "device") {
    await renderDevicePanel(container, data, titleEl, options);
    return;
  }
  if (data.custom === "network") {
    await renderNetworkPanel(container, data);
    return;
  }
  if (data.custom === "network_advanced") {
    await renderNetworkAdvancedPanel(container, data);
    return;
  }
  if (data.custom === "software") {
    await renderSoftwarePanel(container, data);
    return;
  }
  if (data.custom === "trips") {
    await renderTripsPanel(container, data);
    return;
  }
  if (data.custom === "models") {
    await renderModelsPanel(container, data);
    return;
  }
  if (data.custom === "firehose") {
    await renderFirehosePanel(container);
    return;
  }
  if (data.custom === "storage") {
    await renderStoragePanel(container);
    return;
  }
  if (data.custom === "sunnylink") {
    await renderSunnylinkPanel(container, data);
    return;
  }
  if (data.custom === "osm") {
    await renderOsmPanel(container, data);
    return;
  }
  if (data.custom === "vehicle") {
    await renderVehiclePanel(container, data);
    return;
  }

  renderGenericPanel(container, data, panelId);
  updateDisplayDependencies(data);
  if (panelId === "steering__mads") updateMadsSubpanel(globalState);
  if (panelId === "steering__lane_change") updateLaneChangeSubpanel(globalState);
  if (data.custom === "software") updateSoftwareExtras(globalState);
  lastPanelVisibilityHash = panelVisibilityHash(data);
}

async function renderDevicePanel(container, data, titleEl, options = {}) {
  const ex = await apiGet("/api/opui/device/extras");
  deviceExtrasCache = ex.ok ? ex : null;
  let widgets = prunePanelWidgets([...(data.widgets || [])], data);
  const aoWidget = widgets.find((w) => w.custom === "always_offroad");
  if (aoWidget) {
    widgets = widgets.filter((w) => w.custom !== "always_offroad");
    const alwaysOffroad = !!deviceExtrasCache?.offroad_mode;
    const powerIdx = widgets.findIndex((w) => w.type === "dual_button" && w.left?.action === "reboot");
    if (powerIdx >= 0) {
      widgets.splice(powerIdx, 0, { type: "separator", gap: 10 }, { type: "separator" });
    }
    const powerIdx2 = widgets.findIndex((w) => w.type === "dual_button" && w.left?.action === "reboot");
    if (globalState.is_offroad && !alwaysOffroad && powerIdx2 >= 0) {
      widgets.splice(powerIdx2, 0, aoWidget);
    } else {
      widgets.unshift(aoWidget);
    }
  }
  renderGenericPanel(container, { ...data, widgets });
}

function renderAlwaysOffroadRow(active) {
  const row = document.createElement("div");
  row.className = "opui-dual-row opui-dual-row--single";
  const label = active ? t("Exit Always Offroad") : t("Enable Always Offroad");
  row.innerHTML = `<button type="button" class="opui-dual-btn ${active ? "primary" : "danger"}">${escapeHtml(label)}</button>`;
  row.querySelector("button")?.addEventListener("click", async () => {
    if (globalState.engaged) {
      toast(t("Disengage to Enter Always Offroad Mode"));
      return;
    }
    const msg = active
      ? t("Are you sure you want to exit Always Offroad mode?")
      : t("Are you sure you want to enter Always Offroad mode?");
    if (!(await showConfirm({ message: msg, confirmText: t("Confirm") }))) return;
    const res = await apiPut("/api/opui/params/OffroadMode", { value: active ? "0" : "1" });
    if (res.ok) {
      deviceExtrasCache = { ...(deviceExtrasCache || {}), offroad_mode: !active };
      toast(label);
      requestPanelRefresh();
    } else toast(res.error || "Failed");
  });
  return row;
}

function prunePanelWidgets(widgets, panelData) {
  const kept = [];
  for (const w of widgets || []) {
    if (w.type === "separator") {
      if (!kept.length) continue;
      if (kept[kept.length - 1].type === "separator") continue;
      kept.push(w);
      continue;
    }
    if (w.offroad_only && !globalState.is_offroad) continue;
    if (!widgetVisible(w, panelData)) continue;
    kept.push(w);
  }
  while (kept.length && kept[kept.length - 1].type === "separator") kept.pop();
  return kept;
}

function appendPanelWidgets(container, data) {
  panelDataRef = data;
  lastPanelVisibilityHash = panelVisibilityHash(data);
  for (const w of prunePanelWidgets(data.widgets, data)) {
    const el = renderWidget(w, data);
    if (el) {
      el.dataset.panelWidget = "1";
      container.appendChild(el);
    }
  }
}

function prependSubpanelNav(container, data) {
  if (!data?.parent) return;
  const nav = document.createElement("div");
  nav.className = "opui-subpanel-nav";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "opui-nav-back";
  btn.textContent = t("Back");
  btn.addEventListener("click", () => {
    if (onNavigateSubpanel) onNavigateSubpanel(data.parent);
  });
  nav.appendChild(btn);
  container.appendChild(nav);
}

function disposePanelWidgets(container) {
  for (const row of container.querySelectorAll(".opui-stream-diag")) {
    if (row._streamDiagTimer) {
      clearInterval(row._streamDiagTimer);
      row._streamDiagTimer = null;
    }
    if (row._streamDiagVisHandler) {
      document.removeEventListener("visibilitychange", row._streamDiagVisHandler);
      row._streamDiagVisHandler = null;
    }
    if (row._streamHealthOff) {
      row._streamHealthOff();
      row._streamHealthOff = null;
    }
  }
}

function renderGenericPanel(container, data, panelId = "") {
  disposePanelWidgets(container);
  container.innerHTML = "";
  appendPanelWidgets(container, data);
}

function renderWidget(w, panelData) {
  const kind = resolveWidgetType(w);
  const offroad = globalState.is_offroad;
  if (w.offroad_only && !offroad) return null;

  if (!widgetVisible(w, panelData)) return null;

  if (kind === "section") {
    const row = document.createElement("div");
    row.className = "opui-row opui-row--section";
    row.textContent = t(w.label);
    return row;
  }

  if (kind === "separator") {
    const sep = document.createElement("div");
    sep.className = "opui-sp-separator" + (w.gap ? ` opui-sp-separator--gap-${w.gap}` : "");
    sep.setAttribute("aria-hidden", "true");
    return sep;
  }

  if (kind === "html") {
    const block = document.createElement("div");
    block.className = "opui-html-block";
    if (w.i18n_key) {
      block.classList.add("opui-muted");
      block.textContent = t(w.i18n_key);
    } else {
      block.innerHTML = w.html || "";
    }
    return block;
  }

  if (kind === "dual_button") {
    return renderDualButtonRow(w);
  }

  if (kind === "option") {
    return renderOptionRow(w, panelData);
  }

  if (kind === "multiple_button") {
    return renderMultipleButtonRow(w, panelData);
  }

  if (kind === "action") {
    return renderActionRow(w);
  }

  if (kind === "subpanel") {
    return renderSubpanelRow(w);
  }

  if (kind === "custom") {
    if (w.custom === "ssh_keys") return renderSshKeysBlock();
    if (w.custom === "device_language") return renderLanguageRow();
    if (w.custom === "stream_headless_mode") return renderStreamHeadlessModeRow(w);
    if (w.custom === "stream_preview_quality") return renderStreamPreviewQualityRow(w);
    if (w.custom === "stream_webcodecs") return renderStreamWebcodecsRow();
    if (w.custom === "stream_diagnostics") return renderStreamDiagnosticsRow();
    if (w.custom === "driver_camera") return renderDriverCameraRow();
    if (w.custom === "always_offroad") {
      const active = !!deviceExtrasCache?.offroad_mode;
      return renderAlwaysOffroadRow(active);
    }
    if (w.custom === "webui_update") return renderWebUiUpdateRow();
    if (w.custom === "device_calibration") return null;
    return null;
  }

  if (!w.available && w.missing) return null;

  if (kind === "readonly") {
    return renderReadonlyRow(w);
  }

  if (kind === "bool") {
    return renderBoolRow(w);
  }

  if (kind === "choice") {
    return renderChoiceRow(w);
  }

  if (kind === "int") {
    return renderIntRow(w);
  }

  return null;
}

function renderReadonlyRow(w) {
  const row = document.createElement("div");
  row.className = "opui-sp-row";
  row.dataset.param = w.param;
  row.dataset.widget = "readonly";
  const val = formatValue(w.value) || t("N/A");
  row.innerHTML = `
    <div class="opui-sp-row-text">
      <div class="opui-sp-row-title">${escapeHtml(t(w.label))}</div>
    </div>
    <div class="opui-row-value">${escapeHtml(val)}</div>`;
  return row;
}

function renderBoolRow(w) {
  const stacked = widgetUsesStacked(w);
  const toggleDef = { ...w };
  if (w.param === "DisableUpdates") {
    toggleDef.onBeforeChange = async (checked) => {
      const ok = await showConfirm({
        message: t("System reboot required for changes to take effect. Reboot now?"),
        confirmText: t("Reboot"),
        cancelText: t("Cancel"),
      });
      if (!ok) return false;
      const res = await putParam("DisableUpdates", checked ? "1" : "0");
      if (res.ok) await runRebootFlow();
      else toast(res.error || t("Save failed"));
      return "handled";
    };
  }
  if (w.param === "AlphaLongitudinalEnabled") {
    toggleDef.confirm_rich = true;
    toggleDef.confirm_message = w.desc || "";
  }
  if (w.confirm_enable) {
    toggleDef.confirm_enable = true;
    toggleDef.confirm_message = w.desc || w.label;
  }
  if (w.confirm_enable_rich) {
    toggleDef.confirm_rich = true;
    toggleDef.confirm_message = `<h1>${escapeHtml(t(w.label))}</h1><br><p>${escapeHtml(t(w.desc || ""))}</p>`;
  }
  if (w.locked) toggleDef.locked = true;
  const row = createSpToggle({
    ...toggleDef,
    label: stacked ? "" : t(w.label),
    desc: w.desc ? t(w.desc) : "",
    confirm_experimental: w.confirm_experimental,
    stacked,
  }, {}, globalState, paramHandlers);
  row.dataset.param = w.param;
  row.dataset.widget = "bool";
  if (w.locked) row.dataset.locked = "1";
  if (w.dynamic_desc) row.dataset.dynamicDesc = w.dynamic_desc;
  if (w.capability) row.dataset.capability = w.capability;
  if (w.needs_cycle) row.dataset.needsCycle = "1";
  if (w.offroad_only) row.dataset.offroadOnly = "1";
  if (stacked) {
    row.classList.add("opui-sp-row--stacked", "opui-sp-row--toggle-below");
    const title = document.createElement("div");
    title.className = "opui-sp-row-title";
    title.textContent = t(w.label);
    row.querySelector(".opui-sp-row-text")?.prepend(title);
  }
  return row;
}

function renderMultipleButtonRow(w, panelData) {
  const inline = w.layout === "inline";
  const stacked = w.layout === "stacked" || !inline;
  const row = document.createElement("div");
  row.className = "opui-sp-row"
    + (inline ? " opui-sp-row--control-inline" : " opui-sp-row--stacked opui-sp-row--segmented");
  row.dataset.param = w.param;
  row.dataset.widget = "multiple_button";
  const buttons = (w.buttons || []).map((b) => t(b));
  let idx = parseInt(w.value, 10);
  if (Number.isNaN(idx)) idx = 0;

  const text = document.createElement("div");
  text.className = "opui-sp-row-text";
  text.innerHTML = `<div class="opui-sp-row-title">${escapeHtml(t(w.label))}</div>`;

  const group = document.createElement("div");
  group.className = "opui-multi-btn-group";
  if (inline) group.classList.add("opui-multi-btn-group--inline");
  buttons.forEach((label, i) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = label;
    btn.classList.toggle("selected", i === idx);
    const disabled = (w.offroad_only && !globalState.is_offroad) || w.locked;
    if (disabled) btn.disabled = true;
    btn.addEventListener("click", async () => {
      if (w.param === "SpeedLimitMode" && i === 3 && globalState.sla_available === false) {
        toast(t("Speed Limit Assist is not available on this platform."));
        return;
      }
      const res = await putParam(w.param, String(i), !!w.needs_cycle);
      if (!res.ok) {
        toast(res.error || t("Save failed"));
        return;
      }
      w.value = String(i);
      if (panelData.values) panelData.values[w.param] = String(i);
      group.querySelectorAll("button").forEach((b, j) => b.classList.toggle("selected", j === i));
      if (w.param === "MadsSteeringMode") {
        updateMadsSteeringModeDesc(i, !!globalState.mads_limited);
      }
      if (w.param === "SpeedLimitMode") {
        setPanelRowDescHtml(row, buildHighlightedDescHtml(SPEED_LIMIT_MODE_DESCS, i));
      }
      if (w.param === "SpeedLimitOffsetType") {
        setPanelRowDescHtml(row, buildHighlightedDescHtml(SPEED_LIMIT_OFFSET_DESCS, i));
      }
    });
    group.appendChild(btn);
  });
  if (inline) {
    row.append(text, group);
  } else {
    row.appendChild(text);
    row.appendChild(group);
  }
  bindRowExpand(row, { ...w, desc: w.desc ? t(w.desc) : "" });
  return row;
}

function requestPanelRefresh() {
  window.dispatchEvent(new CustomEvent("opui:refresh-panel"));
}

function renderChoiceRow(w) {
  const row = document.createElement("div");
  row.className = "opui-sp-row opui-sp-row--stacked opui-sp-row--segmented";
  row.dataset.param = w.param;
  row.dataset.widget = "choice";
  const opts = (w.options || []).map((o) => t(o));
  let idx = parseInt(w.value, 10);
  if (Number.isNaN(idx)) idx = 0;

  const text = document.createElement("div");
  text.className = "opui-sp-row-text";
  text.innerHTML = `
    <div class="opui-sp-row-title">${escapeHtml(t(w.label))}</div>
    ${w.show_desc && w.desc ? `<div class="opui-sp-row-desc">${escapeHtml(t(w.desc)).replace(/\n/g, "<br>")}</div>` : ""}`;
  row.appendChild(text);

  const group = document.createElement("div");
  group.className = "opui-choice-group";
  opts.forEach((opt, i) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = opt;
    btn.classList.toggle("selected", i === idx);
    btn.addEventListener("click", async () => {
      group.querySelectorAll("button").forEach((b) => b.classList.remove("selected"));
      btn.classList.add("selected");
      const res = await putParam(w.param, String(i));
      if (!res.ok) toast(res.error || t("Save failed"));
    });
    group.appendChild(btn);
  });
  row.appendChild(group);
  return row;
}

function renderIntRow(w) {
  const row = document.createElement("div");
  row.className = "opui-sp-row";
  if (w.capability) row.dataset.capability = w.capability;
  row.dataset.param = w.param;
  let val = parseInt(w.value, 10);
  if (Number.isNaN(val)) val = w.min || 0;
  const min = w.min ?? 0;
  const max = w.max ?? 100;
  const step = w.step ?? 1;
  const valueMap = w.value_map || {};
  const hasMap = Object.keys(valueMap).length > 0;
  const displayVal = hasMap ? (valueMap[String(val)] ?? val) : val;

  row.innerHTML = `
    <div class="opui-sp-row-text">
      <div class="opui-sp-row-title">${escapeHtml(t(w.label))}</div>
    </div>`;
  const ctrl = document.createElement("div");
  ctrl.className = "opui-int-control";
  const minus = document.createElement("button");
  minus.type = "button";
  minus.textContent = "−";
  const span = document.createElement("span");
  span.textContent = String(displayVal);
  const plus = document.createElement("button");
  plus.type = "button";
  plus.textContent = "+";

  const save = async (v) => {
    v = Math.max(min, Math.min(max, v));
    const store = hasMap ? (valueMap[String(v)] ?? v) : v;
    span.textContent = String(hasMap ? (valueMap[String(v)] ?? v) : v);
    const res = await putParam(w.param, String(store));
    if (!res.ok) toast(res.error || t("Save failed"));
  };

  minus.addEventListener("click", () => { val = Math.max(min, val - step); save(val); });
  plus.addEventListener("click", () => { val = Math.min(max, val + step); save(val); });

  ctrl.append(minus, span, plus);
  row.appendChild(ctrl);
  return row;
}

function renderSubpanelRow(w) {
  const wrap = document.createElement("div");
  wrap.className = "opui-subpanel-wrap";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "opui-simple-btn";
  btn.textContent = t(w.label || w.button);
  if (w.target) btn.dataset.subpanel = w.target;
  if (w.offroad_only) btn.dataset.offroadOnly = "1";
  if (w.requires?.param) {
    btn.dataset.requiresParam = w.requires.param;
    btn.dataset.requiresEq = String(w.requires.eq ?? "1");
  }
  btn.addEventListener("click", () => {
    if (btn.disabled) return;
    if (onNavigateSubpanel && w.target) onNavigateSubpanel(w.target);
  });
  wrap.appendChild(btn);
  return wrap;
}

function formatMaxTimeLabel(index, valueMap) {
  const minutes = valueMap?.[String(index)];
  if (minutes === 0) return t("Always On");
  if (minutes == null) return String(index);
  if (minutes < 60) return `${minutes}${t("m")}`;
  const hours = Math.floor(minutes / 60);
  const label = `${hours}${t("h")}`;
  return minutes === 1800 ? `${label}${t(" (Default)")}` : label;
}

function dualButtonClass(side) {
  if (side.action === "shutdown" || side.action === "reset_all_params") return "danger";
  return "";
}

function renderOptionRow(w, panelData) {
  const inline = w.layout === "inline";
  const row = document.createElement("div");
  row.className = "opui-sp-row" + (inline ? " opui-sp-row--control-inline" : " opui-sp-row--stacked opui-sp-row--control-below");
  row.dataset.param = w.param;
  row.dataset.widget = "option";
  let idx = resolveOptionIndex(w, w.value);
  const min = w.min ?? 0;
  const max = w.max ?? 11;
  const step = laneTurnOptionStep(w);

  const text = document.createElement("div");
  text.className = "opui-sp-row-text";
  text.innerHTML = `<div class="opui-sp-row-title">${escapeHtml(t(w.label))}</div>`;
  row.appendChild(text);

  const bar = document.createElement("div");
  bar.className = "opui-option-bar";
  const minus = document.createElement("button");
  minus.type = "button";
  minus.textContent = "−";
  const span = document.createElement("span");
  span.className = "opui-option-value";
  span.textContent = formatOptionLabel(w, w.value, panelData);
  const plus = document.createElement("button");
  plus.type = "button";
  plus.textContent = "+";

  const save = async (v) => {
    idx = Math.max(min, Math.min(max, v));
    const paramVal = optionParamValue(w, idx);
    span.textContent = formatOptionLabel(w, paramVal, panelData);
    minus.disabled = idx <= min;
    plus.disabled = idx >= max;
    const res = await putParam(w.param, String(paramVal));
    if (!res.ok) toast(res.error || t("Save failed"));
    else {
      w.value = String(paramVal);
      if (panelData?.values) panelData.values[w.param] = String(paramVal);
      if (w.param === "OnroadScreenOffBrightness") updateDisplayDependencies(panelData);
      if (w.param === "AutoLaneChangeTimer") updateLaneChangeSubpanel(globalState);
      if (w.param === "Brightness") {
        try {
          if (opuiWs.connected) {
            await opuiWs.rpc("PUT", "/api/opui/display/brightness", { brightness: paramVal });
          } else {
            await apiPut("/api/opui/display/brightness", { brightness: paramVal });
          }
        } catch (err) {
          // Hardware brightness is best-effort; the param already persisted above.
          console.warn("immediate brightness apply failed:", err);
        }
      }
    }
  };
  minus.disabled = idx <= min;
  plus.disabled = idx >= max;
  minus.addEventListener("click", () => save(idx - step));
  plus.addEventListener("click", () => save(idx + step));
  bar.append(minus, span, plus);
  row.appendChild(bar);
  bindRowExpand(row, { ...w, desc: w.desc ? t(w.desc) : "" });
  return row;
}

async function showTrainingGuide() {
  const full = await showConfirm({
    message: t("Open the full step-by-step training guide? This satisfies the training requirement when completed."),
    confirmText: t("Open"),
    cancelText: t("Quick review"),
  });
  if (full) {
    await reopenOnboarding("training");
    return;
  }
  const pages = [
    `<h2>${t("Training Guide")}</h2><p>${t("Review the rules, features, and limitations of sunnypilot")}</p>`,
    `<h3>${t("Driver Monitoring")}</h3><p>${t("Keep your hands on the wheel and eyes on the road at all times.")}</p>`,
    `<h3>${t("Takeover")}</h3><p>${t("Be ready to take over at any time. sunnypilot is not a substitute for an attentive driver.")}</p>`,
  ];
  for (let i = 0; i < pages.length; i++) {
    const cont = i < pages.length - 1;
    const ok = await showConfirm({
      rich: true,
      message: pages[i] + (cont ? `<br><br><i>${i + 1} / ${pages.length}</i>` : ""),
      confirmText: cont ? t("Next") : t("Done"),
      cancelText: t("Close"),
      single: !cont,
    });
    if (!ok && cont) break;
  }
}

async function runDualSideAction(side) {
  if (side.custom === "driver_camera") {
    window.dispatchEvent(new CustomEvent("opui:open-driver-camera"));
    return;
  }
  if (side.action === "open_regulatory") {
    const reg = await apiGet("/api/opui/device/regulatory");
    await showHtml({
      title: t("Regulatory"),
      html: reg.ok ? reg.html : `<p>${t("Regulatory information unavailable")}</p>`,
    });
    return;
  }
  if (side.action === "open_training") {
    await showTrainingGuide();
    return;
  }
  if (side.action === "reset_all_params") {
    if (!(await showConfirm({
      message: t("Are you sure you want to reset all sunnypilot settings to default? Once the settings are reset, there is no going back."),
      confirmText: t("Reset"),
    }))) return;
    if (!(await showConfirm({
      message: t("The reset cannot be undone. You have been warned."),
      confirmText: t("Confirm"),
    }))) return;
    const res = await apiPost("/api/opui/action/reset_all_params");
    if (res.ok) toast(t("Reset Settings"));
    else toast(res.error || "Failed");
    return;
  }
  if (side.action) {
    if (side.action === "reboot") {
      if (globalState.engaged) {
        toast(t("Disengage to Reboot"));
        return;
      }
      if (!(await showConfirm({ message: t("Are you sure you want to reboot?"), confirmText: t("Reboot") }))) return;
      await runRebootFlow();
      return;
    }
    if (side.action === "shutdown") {
      if (globalState.engaged) {
        toast(t("Disengage to Power Off"));
        return;
      }
      if (!(await showConfirm({ message: t("Are you sure you want to power off?"), confirmText: t("Power Off") }))) return;
    }
    if (side.confirm && !(await showConfirm({ message: t(side.confirm), confirmText: t("Yes") }))) return;
    const res = await apiPost(`/api/opui/action/${encodeURIComponent(side.action)}`);
    if (res.ok) toast(t(side.label));
    else toast(res.error || "Failed");
  }
}

function renderDualButtonRow(w) {
  const left = w.left || {};
  const right = w.right || {};
  const offroad = globalState.is_offroad;

  const row = document.createElement("div");
  row.className = "opui-dual-row";
  row.dataset.dual = `${left.label || ""}|${right.label || ""}`;
  if (left.action === "reboot") row.dataset.powerRow = "1";
  const lBtn = document.createElement("button");
  lBtn.type = "button";
  lBtn.className = "opui-dual-btn";
  lBtn.dataset.side = "left";
  lBtn.textContent = t(left.label);
  const rBtn = document.createElement("button");
  rBtn.type = "button";
  rBtn.className = `opui-dual-btn ${dualButtonClass(right)}`.trim();
  rBtn.dataset.side = "right";
  rBtn.textContent = t(right.label);

  if (left.toggle) {
    lBtn.classList.toggle("primary", paramIsOn(left.value));
  }
  if (right.toggle) {
    rBtn.classList.toggle("primary", paramIsOn(right.value));
  }
  if (left.offroad_only && !offroad) lBtn.disabled = true;
  if (right.offroad_only && !offroad) rBtn.disabled = true;
  if (right.hide_when_onroad && !offroad) {
    rBtn.remove();
  } else if (left.hide_when_onroad && !offroad) {
    lBtn.remove();
  }

  lBtn.addEventListener("click", async () => {
    if (left.toggle && left.param) {
      const on = !paramIsOn(left.value);
      const res = await putParam(left.param, on ? "1" : "0");
      if (res.ok) {
        lBtn.classList.toggle("primary", on);
        left.value = on ? "1" : "0";
      } else toast(res.error || "Failed");
      return;
    }
    await runDualSideAction(left);
  });
  rBtn.addEventListener("click", async () => {
    if (right.toggle && right.param) {
      const on = !paramIsOn(right.value);
      const res = await putParam(right.param, on ? "1" : "0");
      if (res.ok) {
        rBtn.classList.toggle("primary", on);
        right.value = on ? "1" : "0";
      } else toast(res.error || "Failed");
      return;
    }
    await runDualSideAction(right);
  });

  row.append(lBtn, rBtn);
  return row;
}

function renderSshKeysBlock() {
  const sshDesc = tr(
    "Warning: This grants SSH access to all public keys in your GitHub settings. Never enter a GitHub username other than your own. A comma employee will NEVER ask you to add their GitHub username.",
  );
  const row = document.createElement("div");
  row.className = "opui-sp-row";
  row.id = "ssh-keys-row";
  row.innerHTML = `
    <div class="opui-sp-row-text">
      <div class="opui-sp-row-title">${escapeHtml(tr("SSH Keys"))}</div>
    </div>
    <div class="opui-sp-row-actions">
      <span class="opui-sp-row-value" id="ssh-username-display"></span>
      <button type="button" class="opui-btn opui-btn--action" id="ssh-action-btn">${escapeHtml(t("ADD"))}</button>
    </div>`;

  const refresh = async () => {
    const st = await apiGet("/api/opui/ssh/status");
    const userEl = row.querySelector("#ssh-username-display");
    const btn = row.querySelector("#ssh-action-btn");
    if (!st.ok) {
      if (userEl) userEl.textContent = "";
      if (btn) {
        btn.textContent = t("ADD");
        btn.disabled = true;
      }
      return;
    }
    if (userEl) userEl.textContent = st.keys ? (st.username || "") : "";
    if (btn) {
      btn.textContent = st.keys ? t("REMOVE") : t("ADD");
      btn.disabled = false;
    }
  };

  row.querySelector("#ssh-action-btn")?.addEventListener("click", async (e) => {
    e.stopPropagation();
    const btn = row.querySelector("#ssh-action-btn");
    const st = await apiGet("/api/opui/ssh/status");
    if (!st.ok) {
      toast(st.error || t("Failed"));
      return;
    }
    if (st.keys) {
      const res = await apiPost("/api/opui/ssh/remove");
      if (res.ok) toast(t("SSH keys removed"));
      else toast(res.error || t("Failed"));
      refresh();
      return;
    }
    if (btn) btn.disabled = true;
    const username = await showKeyboard({
      title: t("Enter your GitHub username"),
      value: st.username || "",
      minLen: 1,
      maxLen: 39,
    });
    if (!username) {
      if (btn) btn.disabled = false;
      return;
    }
    if (btn) btn.textContent = t("LOADING");
    const res = await apiPost("/api/opui/ssh/fetch", { username });
    if (res.ok) toast(t("SSH keys updated"));
    else toast(res.error || t("Failed"));
    if (btn) btn.disabled = false;
    refresh();
  });

  row.querySelector(".opui-sp-row-actions")?.addEventListener("click", (e) => e.stopPropagation());
  bindRowExpand(row, { desc: sshDesc });
  refresh();
  return row;
}

function renderActionRow(w) {
  const row = document.createElement("div");
  row.className = "opui-sp-row";
  if (w.action) row.dataset.action = w.action;
  const disabled = (w.offroad_only && !globalState.is_offroad);
  const calHtml = (w.dynamic_desc === "calibration")
    ? buildCalibrationDescHtml(w, deviceExtrasCache?.calibration)
    : "";
  row.innerHTML = `
    <div class="opui-sp-row-text">
      <div class="opui-sp-row-title">${escapeHtml(t(w.label))}</div>
    </div>
    <button type="button" class="opui-btn opui-btn--action" ${disabled ? "disabled" : ""}>${escapeHtml(t(w.button || "GO"))}</button>`;
  if (calHtml) {
    bindRowExpand(row, { desc_html: calHtml });
  } else if (w.desc) {
    bindRowExpand(row, { desc: t(w.desc) });
  }
  const btn = row.querySelector("button");
  if (disabled) {
    btn.disabled = true;
    return row;
  }
  if (w.action === "reset_calibration" && globalState.engaged) {
    btn.classList.add("is-engaged-blocked");
  }
  btn.addEventListener("click", async () => {
    if (w.action === "reset_calibration" && globalState.engaged) {
      toast(t("Disengage to Reset Calibration"));
      return;
    }
    if (w.confirm && !(await showConfirm({
      message: t(w.confirm),
      confirmText: t(w.confirm_button || (w.action === "reset_calibration" ? "Reset" : "Yes")),
    }))) return;
    if (w.action === "pair_device") {
      const res = await apiGet("/api/opui/device/pair");
      if (!res.ok) { toast(res.error || t("Failed")); return; }
      await showQrPair({
        title: t("Pair your device to your comma account"),
        url: res.url,
        qrDataUrl: res.qr_data_url,
        onPoll: async () => {
          const home = await apiGet("/api/opui/home");
          return !!home?.paired;
        },
      });
      requestPanelRefresh();
      return;
    }
    if (w.action === "models_sync") {
      const res = await apiPost("/api/opui/action/models_sync");
      if (!res.ok) { toast(res.error || t("Failed")); return; }
      await showConfirm({ message: t("Fetching Latest Models"), single: true, confirmText: t("OK") });
      requestPanelRefresh();
      return;
    }
    if (w.action === "developer_error_log") {
      const log = await apiGet("/api/opui/developer/error-log");
      if (!log.ok) {
        toast(log.error || "Failed");
        return;
      }
      await showHtml({ title: t("Error Log"), html: log.html || "" });
      if (log.exists && (await showConfirm({ message: t("Would you like to delete this log?"), confirmText: t("Yes") }))) {
        await apiPost("/api/opui/action/developer_delete_error_log");
        toast(t("Log deleted"));
      }
      return;
    }
    if (w.action === "torque_tune_version") {
      const tv = await apiGet("/api/opui/steering/torque-versions");
      if (!tv.ok) {
        toast(tv.error || "Failed");
        return;
      }
      const folders = [{
        name: "",
        bundles: (tv.options || []).map((o) => ({ name: o.label, ref: o.label })),
      }];
      const ref = await showTree({
        title: t("Torque Control Tune Version"),
        folders,
        selectedRef: tv.current_label || "Default",
        searchable: true,
      });
      if (!ref) return;
      const pick = (tv.options || []).find((o) => o.label === ref);
      if (!pick || pick.version == null) {
        await apiPut("/api/opui/params/TorqueControlTune", { value: "" });
      } else {
        await apiPut("/api/opui/params/TorqueControlTune", { value: String(pick.version) });
      }
      toast(t("Torque tune updated"));
      requestPanelRefresh();
      return;
    }
    if (w.action === "network_set_apn") {
      const apn = await showKeyboard({ title: t("APN"), value: "", maxLen: 64 });
      if (apn == null) return;
      const res = await apiPost("/api/opui/action/network_set_apn", { apn });
      if (res.ok) toast(t("APN saved"));
      else toast(res.error || "Failed");
      return;
    }
    const res = await apiPost(`/api/opui/action/${encodeURIComponent(w.action)}`);
    if (res.ok) {
      toast(t(w.label));
      if (w.action === "reset_calibration") requestPanelRefresh();
    } else toast(res.error || "Failed");
  });
  return row;
}

async function renderNetworkPanel(container, data) {
  const gen = beginPanelRender();
  container.innerHTML = "";
  const body = createPanelBody(container, "opui-panel-body--wifi");

  const header = document.createElement("div");
  header.className = "opui-wifi-header";
  const scanBtn = document.createElement("button");
  scanBtn.type = "button";
  scanBtn.className = "opui-wifi-scan-btn";
  scanBtn.textContent = t("Scan");
  const advBtn = document.createElement("button");
  advBtn.type = "button";
  advBtn.className = "opui-wifi-adv-btn";
  advBtn.textContent = t("Advanced");
  advBtn.addEventListener("click", () => {
    if (onNavigateSubpanel) onNavigateSubpanel("network__advanced");
  });
  header.append(scanBtn, advBtn);
  body.appendChild(header);

  const listCard = document.createElement("div");
  listCard.className = "opui-wifi-list-card";
  const list = document.createElement("div");
  list.className = "opui-wifi-list";
  listCard.appendChild(list);
  body.appendChild(listCard);

  const asset = (rel) => `/api/opui/assets/${rel.replace(/^\//, "")}`;
  const strengthIcon = (strength, secured) => {
    if (secured && strength <= 0) {
      return asset("icons_mici/settings/network/wifi_strength_slash.png");
    }
    const level = Math.max(0, Math.min(2, Math.floor((strength || 0) / 34)));
    const names = [
      "icons_mici/settings/network/wifi_strength_low.png",
      "icons_mici/settings/network/wifi_strength_medium.png",
      "icons_mici/settings/network/wifi_strength_full.png",
    ];
    return asset(names[level]);
  };

  const fetchScan = (trigger = false) => apiGet(`/api/opui/wifi/scan${trigger ? "?trigger=1" : ""}`);

  const paintList = (scan) => {
    if (panelRenderStale(gen)) return;
    list.innerHTML = "";
    if (!scan.ok) {
      list.innerHTML = `<p class="opui-wifi-status">${escapeHtml(t("Wi-Fi unavailable"))}: ${escapeHtml(scan.error || "")}</p>`;
      return;
    }
    const networks = scan.networks || [];
    if (!networks.length) {
      list.innerHTML = `<p class="opui-wifi-status">${escapeHtml(t("No networks found"))}</p>`;
      return;
    }
    for (const n of networks) {
      const item = document.createElement("div");
      item.className = "opui-wifi-item" + (n.connected ? " connected" : "");
      const ssidBtn = document.createElement("button");
      ssidBtn.type = "button";
      ssidBtn.className = "opui-wifi-ssid";
      ssidBtn.textContent = n.ssid;
      const meta = document.createElement("div");
      meta.className = "opui-wifi-meta";
      if (n.saved) {
        const forget = document.createElement("button");
        forget.type = "button";
        forget.className = "opui-wifi-forget";
        forget.textContent = t("Forget");
        forget.addEventListener("click", async (e) => {
          e.stopPropagation();
          const msg = t('Forget Wi-Fi Network "{}"?').replace("{}", n.ssid);
          if (!(await showConfirm({ message: msg, confirmText: t("Forget"), cancelText: t("Cancel") }))) return;
          const res = await apiPost("/api/opui/wifi/forget", { ssid: n.ssid });
          if (res.ok) toast(t("Forgot") + ` ${n.ssid}`);
          else toast(res.error || t("Failed"));
          await runScan(false);
        });
        meta.appendChild(forget);
      }
      if (n.connected) {
        const mark = document.createElement("img");
        mark.className = "opui-wifi-icon";
        mark.src = asset("selfdrive/assets/icons/checkmark.png");
        mark.alt = "";
        meta.appendChild(mark);
      } else if (n.security > 0) {
        const lock = document.createElement("img");
        lock.className = "opui-wifi-icon";
        lock.src = asset("selfdrive/assets/icons/lock_closed.png");
        lock.alt = "";
        meta.appendChild(lock);
      }
      const signal = document.createElement("img");
      signal.className = "opui-wifi-icon opui-wifi-signal";
      signal.src = strengthIcon(n.strength, n.security > 0);
      signal.alt = "";
      meta.appendChild(signal);
      item.append(ssidBtn, meta);
      ssidBtn.addEventListener("click", async () => {
        if (n.connected) return;
        let password = "";
        if (n.security > 0) {
          password = await showKeyboard({
            title: `${t("Enter password")} (${n.ssid})`,
            password: true,
            minLen: 8,
            maxLen: 64,
          }) || "";
          if (!password) return;
        }
        const prevText = ssidBtn.textContent;
        ssidBtn.disabled = true;
        ssidBtn.textContent = t("Connecting...");
        const res = await apiPost("/api/opui/wifi/connect", { ssid: n.ssid, password });
        if (res.ok) {
          toast(`${t("Connecting")} ${n.ssid}`);
          for (let i = 0; i < 24; i++) {
            await new Promise((r) => setTimeout(r, 500));
            const latest = await fetchScan(false);
            if (panelRenderStale(gen)) return;
            const hit = (latest.networks || []).find((x) => x.ssid === n.ssid && x.connected);
            if (hit) {
              toast(`${t("Connected")} ${n.ssid}`);
              break;
            }
          }
          await runScan(false);
        } else {
          toast(res.error || t("Connect failed"));
        }
        ssidBtn.disabled = false;
        ssidBtn.textContent = prevText;
      });
      list.appendChild(item);
    }
  };

  const runScan = async (trigger = false) => {
    if (trigger) {
      list.innerHTML = `<p class="opui-wifi-status">${escapeHtml(t("Scanning Wi-Fi networks..."))}</p>`;
    }
    let scan = await fetchScan(trigger);
    if (panelRenderStale(gen)) return;
    if (trigger) {
      for (let i = 0; i < 12; i++) {
        if ((scan.networks || []).length) break;
        await new Promise((r) => setTimeout(r, 500));
        scan = await fetchScan(false);
        if (panelRenderStale(gen)) return;
      }
    }
    paintList(scan);
  };

  scanBtn.addEventListener("click", async () => {
    scanBtn.disabled = true;
    scanBtn.textContent = t("Scanning...");
    await runScan(true);
    if (panelRenderStale(gen)) return;
    scanBtn.disabled = false;
    scanBtn.textContent = t("Scan");
  });

  await runScan(true);
}

async function renderNetworkAdvancedPanel(container, data) {
  const gen = beginPanelRender();
  container.innerHTML = "";
  const adv = await apiGet("/api/opui/network/advanced");
  if (panelRenderStale(gen)) return;

  const tetherChecked = !!(adv.ok && adv.tethering);
  const tetherRow = document.createElement("div");
  tetherRow.className = "opui-sp-row";
  tetherRow.innerHTML = `
    <label class="opui-sp-toggle${tetherChecked ? " on" : ""}">
      <input type="checkbox" ${tetherChecked ? "checked" : ""} />
      <span class="opui-sp-toggle-track"><span class="opui-sp-toggle-thumb"></span></span>
    </label>
    <div class="opui-sp-row-text">
      <div class="opui-sp-row-title">${escapeHtml(t("Enable Tethering"))}</div>
    </div>`;
  tetherRow.querySelector("input")?.addEventListener("change", async (ev) => {
    const input = ev.target;
    const label = tetherRow.querySelector(".opui-sp-toggle");
    const active = !!input.checked;
    label?.classList.toggle("on", active);
    const res = await apiPost("/api/opui/wifi/tethering", { active });
    if (!res.ok) {
      toast(res.error || t("Failed"));
      input.checked = !active;
      label?.classList.toggle("on", input.checked);
    }
  });
  container.appendChild(tetherRow);

  const passRow = document.createElement("div");
  passRow.className = "opui-sp-row";
  passRow.innerHTML = `
    <div class="opui-sp-row-text">
      <div class="opui-sp-row-title">${escapeHtml(t("Tethering Password"))}</div>
    </div>
    <button type="button" class="opui-btn opui-btn--action">${escapeHtml(t("EDIT"))}</button>`;
  passRow.querySelector("button")?.addEventListener("click", async () => {
    const password = await showKeyboard({
      title: t("Tethering Password"),
      password: true,
      minLen: 8,
      maxLen: 64,
    });
    if (password == null) return;
    const res = await apiPost("/api/opui/wifi/tethering/password", { password });
    if (res.ok) toast(t("Saved"));
    else toast(res.error || t("Failed"));
  });
  container.appendChild(passRow);

  const ipRow = document.createElement("div");
  ipRow.className = "opui-sp-row";
  ipRow.innerHTML = `
    <div class="opui-sp-row-text">
      <div class="opui-sp-row-title">${escapeHtml(t("IP Address"))}</div>
    </div>
    <div class="opui-row-value">${escapeHtml(adv.ok ? (adv.ipv4 || "—") : "—")}</div>`;
  container.appendChild(ipRow);

  for (const w of data.widgets || []) {
    const el = renderWidget(w, data);
    if (el) container.appendChild(el);
  }

  const apnRow = document.createElement("div");
  apnRow.className = "opui-sp-row";
  apnRow.innerHTML = `
    <div class="opui-sp-row-text">
      <div class="opui-sp-row-title">${escapeHtml(t("APN Setting"))}</div>
    </div>
    <button type="button" class="opui-btn opui-btn--action">${escapeHtml(t("EDIT"))}</button>`;
  apnRow.querySelector("button")?.addEventListener("click", async () => {
    const apn = await showKeyboard({
      title: `${t("Enter APN")} — ${t("leave blank for automatic configuration")}`,
      minLen: 0,
      maxLen: 64,
    });
    if (apn == null) return;
    const res = await apiPost("/api/opui/action/network_set_apn", { apn });
    if (res.ok) toast(t("Saved"));
    else toast(res.error || t("Failed"));
  });
  const roamingRow = container.querySelector('[data-param="GsmRoaming"]');
  if (roamingRow) roamingRow.insertAdjacentElement("afterend", apnRow);
  else container.appendChild(apnRow);

  const meteredRow = document.createElement("div");
  meteredRow.className = "opui-sp-row opui-sp-row--stacked opui-sp-row--segmented";
  meteredRow.dataset.param = "WifiMeteredUi";
  meteredRow.dataset.widget = "multiple_button";
  const meteredLabels = [t("default"), t("metered"), t("unmetered")];
  let meteredIdx = adv.ok ? (adv.wifi_metered || 0) : 0;
  const meteredText = document.createElement("div");
  meteredText.className = "opui-sp-row-text";
  meteredText.innerHTML = `
    <div class="opui-sp-row-title">${escapeHtml(t("Wi-Fi Network Metered"))}</div>
    <div class="opui-sp-row-desc">${escapeHtml(t("Prevent large data uploads when on a metered Wi-Fi connection"))}</div>`;
  const meteredGroup = document.createElement("div");
  meteredGroup.className = "opui-multi-btn-group";
  const meteredEnabled = adv.ok && adv.wifi_metered_enabled;
  meteredLabels.forEach((label, i) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = label;
    btn.classList.toggle("selected", i === meteredIdx);
    btn.disabled = !meteredEnabled;
    btn.addEventListener("click", async () => {
      const res = await apiPost("/api/opui/wifi/metered", { metered: i });
      if (!res.ok) {
        toast(res.error || t("Failed"));
        return;
      }
      meteredIdx = i;
      meteredGroup.querySelectorAll("button").forEach((b, j) => b.classList.toggle("selected", j === i));
    });
    meteredGroup.appendChild(btn);
  });
  meteredRow.append(meteredText, meteredGroup);
  container.appendChild(meteredRow);

  const hiddenRow = document.createElement("div");
  hiddenRow.className = "opui-sp-row";
  hiddenRow.innerHTML = `
    <div class="opui-sp-row-text">
      <div class="opui-sp-row-title">${escapeHtml(t("Hidden Network"))}</div>
    </div>
    <button type="button" class="opui-btn opui-btn--action">${escapeHtml(t("CONNECT"))}</button>`;
  hiddenRow.querySelector("button")?.addEventListener("click", async () => {
    const ssid = await showKeyboard({ title: t("Hidden Network"), minLen: 1, maxLen: 64 });
    if (!ssid) return;
    let password = await showKeyboard({
      title: `${t("Enter password")} (${ssid})`,
      password: true,
      minLen: 0,
      maxLen: 64,
    });
    if (password == null) return;
    const res = await apiPost("/api/opui/wifi/connect/hidden", { ssid, password });
    if (res.ok) toast(`${t("Connecting")} ${ssid}`);
    else toast(res.error || t("Connect failed"));
  });
  container.appendChild(hiddenRow);
}

async function renderTripsPanel(container, data) {
  const gen = beginPanelRender();
  container.innerHTML = "";
  const trips = await apiGet("/api/opui/trips");
  if (panelRenderStale(gen)) return;
  if (!trips.ok) {
    container.innerHTML = `<p class="opui-muted" style="padding:48px">${escapeHtml(trips.error || "")}</p>`;
    return;
  }
  const wrap = document.createElement("div");
  wrap.className = "opui-trips-wrap";
  container.appendChild(wrap);
  const s = trips.stats || {};
  const metric = globalState.is_metric;
  for (const [title, key] of [[t("ALL TIME"), "all"], [t("PAST WEEK"), "week"]]) {
    const block = s[key] || {};
    const card = document.createElement("div");
    card.className = "opui-trips-card";
    const dist = block.distance ?? 0;
    const distStr = metric ? Math.round(dist * 1.60934) : Math.round(dist);
    const unit = metric ? t("KM") : t("Miles");
    card.innerHTML = `
      <div class="opui-trips-title">${escapeHtml(title)}</div>
      <div class="opui-trips-cols">
        <div class="opui-trips-col">
          <img class="opui-trips-icon" src="/api/opui/assets/icons_mici/wheel.png" alt="" />
          <div class="opui-trips-num">${block.routes || 0}</div>
          <div class="opui-trips-unit">${escapeHtml(t("Drives"))}</div>
        </div>
        <div class="opui-trips-col">
          <img class="opui-trips-icon opui-trips-icon--road" src="/api/opui/assets/icons/road.png" alt="" />
          <div class="opui-trips-num">${distStr}</div>
          <div class="opui-trips-unit">${escapeHtml(unit)}</div>
        </div>
        <div class="opui-trips-col">
          <img class="opui-trips-icon" src="/api/opui/assets/sunnypilot/selfdrive/assets/icons/clock.png" alt="" />
          <div class="opui-trips-num">${Math.round((block.minutes || 0) / 60)}</div>
          <div class="opui-trips-unit">${escapeHtml(t("Hours"))}</div>
        </div>
      </div>`;
    wrap.appendChild(card);
  }
}

function formatStat(v) {
  if (v == null) return "—";
  if (typeof v === "number") return v.toFixed?.(1) ?? v;
  return String(v);
}

async function renderModelsPanel(container, data) {
  stopModelsPanelPoll();
  const gen = beginPanelRender();
  container.innerHTML = "";
  const m = await apiGet("/api/opui/models");
  if (panelRenderStale(gen)) return;
  if (!m.ok) {
    container.innerHTML = `<p class="opui-muted" style="padding:48px">${escapeHtml(m.error || t("Failed"))}</p>`;
    return;
  }

  const pickRow = document.createElement("div");
  pickRow.className = "opui-sp-row opui-sp-row--has-action";
  pickRow.dataset.modelsSelect = "1";
  const modelName = m.active_name || formatBundleDisplay(data.values?.ModelManager_ActiveBundle) || "—";
  const modelDesc = !globalState.is_offroad
    ? t("Only available when vehicle is off, or always offroad mode is on")
    : modelName;
  pickRow.innerHTML = `
    <div class="opui-sp-row-text">
      <div class="opui-sp-row-title">${escapeHtml(t("Current Model"))}</div>
      <div class="opui-sp-row-desc">${escapeHtml(modelDesc)}</div>
    </div>
    <button type="button" class="opui-btn opui-btn--action" ${globalState.is_offroad ? "" : "disabled"}>${escapeHtml(t("SELECT"))}</button>`;
  pickRow.querySelector("button")?.addEventListener("click", async () => {
    if (!globalState.is_offroad) {
      toast(t("Changing model is only allowed while offroad."));
      return;
    }
    if (m.model_manager_online === false) {
      toast(t("Model list is still loading. Tap Refresh Model List and try again."));
    }
    const ref = await showTree({
      title: t("Select a Model"),
      folders: m.tree || [],
      selectedRef: m.active_ref,
      searchable: true,
      getFolders: async () => {
        const latest = await apiGet("/api/opui/models");
        return latest?.tree || [];
      },
      onFavorite: async (modelRef) => {
        const res = await apiPost("/api/opui/models/favorite", { ref: modelRef });
        if (!res.ok) {
          toast(res.error || t("Failed"));
          return false;
        }
        return true;
      },
    });
    if (!ref) return;
    const latest = await apiGet("/api/opui/models");
    const bundle = (latest?.tree || m.tree || []).flatMap((f) => f.bundles || []).find((b) => b.ref === ref);
    const res = await apiPost("/api/opui/models/select", { ref, index: bundle?.index });
    if (res.ok) {
      if (res.needs_reset_cal) {
        const reset = await showConfirm({
          message: t("Model download has started in the background. We suggest resetting calibration. Would you like to do that now?"),
          confirmText: t("Reset Calibration"),
          cancelText: t("Cancel"),
        });
        if (reset) {
          const cal = await apiPost("/api/opui/action/reset_calibration");
          if (cal.ok) toast(t("Reset Calibration"));
          else toast(cal.error || t("Failed"));
        }
      }
      toast(t("Model selected"));
      await renderModelsPanel(container, data);
    } else toast(res.error || t("Failed"));
  });
  container.appendChild(pickRow);

  const downloadRoot = document.createElement("div");
  downloadRoot.dataset.modelsDownload = "1";
  container.appendChild(downloadRoot);

  const paintModelsDownload = (status) => {
    downloadRoot.innerHTML = "";
    const hasDownload = status.download?.name && status.download_index != null && status.download_index !== "";
    if (!hasDownload) return;
    const cancel = document.createElement("div");
    cancel.className = "opui-sp-row opui-sp-row--has-action";
    cancel.innerHTML = `<div class="opui-sp-row-text"><div class="opui-sp-row-title">${escapeHtml(t("Cancel Download"))}</div></div>
      <button type="button" class="opui-btn opui-btn--action danger">${escapeHtml(t("Cancel"))}</button>`;
    cancel.querySelector("button")?.addEventListener("click", async () => {
      await apiPost("/api/opui/action/models_cancel_download");
      toast(t("Download cancelled"));
      await renderModelsPanel(container, data);
    });
    downloadRoot.appendChild(cancel);
    const types = {
      supercombo: t("Driving Model"),
      vision: t("Vision Model"),
      policy: t("Policy Model"),
      offPolicy: t("Off-Policy Model"),
      onPolicy: t("On-Policy Model"),
    };
    const parts = status.download.models?.length
      ? status.download.models
      : Object.keys(types).map((type) => ({ type, progress: 0 }));
    for (const part of parts) {
      const label = types[part.type] || part.type;
      downloadRoot.appendChild(createProgressRow(`${label} — ${status.download.name}`, part.progress || 0));
    }
  };

  const syncModelsExtras = (status) => {
    paintModelsDownload(status);
    const clearRow = container.querySelector('[data-action="models_clear_cache"]');
    if (clearRow && status.cache_size_mb != null) {
      const text = clearRow.querySelector(".opui-sp-row-text");
      if (text) {
        let d = text.querySelector(".opui-sp-row-desc");
        if (!d) {
          d = document.createElement("div");
          d.className = "opui-sp-row-desc";
          text.appendChild(d);
        }
        d.textContent = `${Number(status.cache_size_mb).toFixed(2)} ${t("MB")}`;
      }
    }
  };

  syncModelsExtras(m);
  appendPanelWidgets(container, data);
  syncModelsExtras(m);

  modelsPanelPoll = setInterval(async () => {
    if (panelRenderStale(gen)) {
      stopModelsPanelPoll();
      return;
    }
    try {
      const latest = await apiGet("/api/opui/models");
      if (latest?.ok) syncModelsExtras(latest);
    } catch { /* ignore transient poll errors */ }
  }, 500);
}

function applyOsmPanelValues(patch) {
  if (!patch || typeof patch !== "object") return;
  if (!panelDataRef) panelDataRef = { ok: true, values: {} };
  if (!panelDataRef.values) panelDataRef.values = {};
  Object.assign(panelDataRef.values, patch);
  const block = document.getElementById("osm-custom-root");
  if (block) updateOsmLabels(block, panelDataRef);
  const ver = document.getElementById("osm-mapd-version");
  if (ver && panelDataRef.values.MapdVersion) {
    ver.textContent = panelDataRef.values.MapdVersion;
  }
}

async function syncOsmPanelAfterSelect(values) {
  applyOsmPanelValues(values);
  const block = document.getElementById("osm-custom-root");
  if (!block) return;
  try {
    const [size, prog] = await Promise.all([
      apiGet("/api/opui/osm/size"),
      apiGet("/api/opui/osm/progress"),
    ]);
    updateOsmCustomDom(block, { ok: true, size, progress: prog });
  } catch (_) {
    /* keep selected labels */
  }
  updateOsmLabels(block, panelDataRef);
}

async function promptOsmDatabaseDownload() {
  if (!(await showConfirm({
    message: t("This will start the download process and it might take a while to complete."),
    confirmText: t("Start Download"),
  }))) return;
  const res = await apiPost("/api/opui/action/osm_check_updates");
  if (res.ok) toast(t("Start Download"));
  else toast(res.error || t("Failed"));
}

function ensureOsmCustomBlock(container, data) {
  let block = container.querySelector("#osm-custom-root");
  if (block) {
    updateOsmLabels(block, data);
    return block;
  }
  block = document.createElement("div");
  block.id = "osm-custom-root";
  block.className = "opui-osm-block";
  block.innerHTML = `
    <div class="opui-sp-row" id="osm-size-row">
      <div class="opui-sp-row-text">
        <div class="opui-sp-row-title">${escapeHtml(t("Downloaded Maps"))}</div>
      </div>
      <span class="opui-sp-row-value" id="osm-size-text">${escapeHtml(t("Calculating..."))}</span>
      <button type="button" class="opui-btn opui-btn--action danger" id="osm-delete-btn">${escapeHtml(t("DELETE"))}</button>
    </div>
    <div id="osm-progress-slot"></div>
    <div class="opui-sp-row" id="osm-update-row">
      <div class="opui-sp-row-text">
        <div class="opui-sp-row-title">${escapeHtml(t("Database Update"))}</div>
      </div>
      <span class="opui-sp-row-value" id="osm-update-text"></span>
      <button type="button" class="opui-btn opui-btn--action" id="osm-check-btn">${escapeHtml(t("CHECK"))}</button>
    </div>
    <div class="opui-sp-row" id="osm-country-row">
      <div class="opui-sp-row-text">
        <div class="opui-sp-row-title">${escapeHtml(t("Country"))}</div>
      </div>
      <span class="opui-sp-row-value" id="osm-country-text"></span>
      <button type="button" class="opui-btn opui-btn--action" id="osm-country-btn">${escapeHtml(t("SELECT"))}</button>
    </div>
    <div class="opui-sp-row" id="osm-state-row" hidden>
      <div class="opui-sp-row-text">
        <div class="opui-sp-row-title">${escapeHtml(t("State"))}</div>
      </div>
      <span class="opui-sp-row-value" id="osm-state-text"></span>
      <button type="button" class="opui-btn opui-btn--action" id="osm-state-btn">${escapeHtml(t("SELECT"))}</button>
    </div>`;
  container.appendChild(block);

  block.querySelector("#osm-delete-btn")?.addEventListener("click", async () => {
    if (!(await showConfirm({
      message: t("This will delete ALL downloaded maps\n\nAre you sure you want to delete all maps?"),
      confirmText: t("Yes, delete all maps"),
    }))) return;
    const btn = block.querySelector("#osm-delete-btn");
    if (btn) {
      btn.disabled = true;
      btn.textContent = t("DELETING...");
    }
    const res = await apiPost("/api/opui/osm/delete");
    if (res.ok) toast(t("Delete requested"));
    else toast(res.error || t("Failed"));
    if (btn) {
      btn.disabled = false;
      btn.textContent = t("DELETE");
    }
  });

  block.querySelector("#osm-check-btn")?.addEventListener("click", async () => {
    if (!(await showConfirm({
      message: t("This will start the download process and it might take a while to complete."),
      confirmText: t("Start Download"),
    }))) return;
    const res = await apiPost("/api/opui/action/osm_check_updates");
    if (res.ok) toast(t("CHECK"));
    else toast(res.error || t("Failed"));
  });

  block.querySelector("#osm-country-btn")?.addEventListener("click", () => pickOsmRegion("Country"));
  block.querySelector("#osm-state-btn")?.addEventListener("click", () => pickOsmRegion("State"));
  updateOsmLabels(block, data);
  return block;
}

function updateOsmLabels(block, data) {
  if (!block) return;
  const values = data?.values || panelDataRef?.values || {};
  const countryText = block.querySelector("#osm-country-text");
  const stateText = block.querySelector("#osm-state-text");
  const updateText = block.querySelector("#osm-update-text");
  const stateRow = block.querySelector("#osm-state-row");
  const updateRow = block.querySelector("#osm-update-row");
  if (countryText) countryText.textContent = values.OsmLocationTitle || t("Not selected");
  if (stateText) stateText.textContent = values.OsmStateTitle || t("Not selected");
  if (updateText) updateText.textContent = formatLastChecked(values.OsmDownloadedDate);
  if (stateRow) stateRow.hidden = String(values.OsmLocationName || "") !== "US";
  if (updateRow) updateRow.hidden = !values.OsmLocationName;
}

function applyOsmCustom(data) {
  const block = document.getElementById("osm-custom-root");
  if (!block || !data?.ok) return;
  if (data.values) {
    if (!panelDataRef) panelDataRef = { ok: true, values: {} };
    panelDataRef.values = { ...(panelDataRef.values || {}), ...data.values };
  }
  updateOsmCustomDom(block, data);
  updateOsmLabels(block, panelDataRef || { values: data.values || {} });
  const ver = document.getElementById("osm-mapd-version");
  const mapd = panelDataRef?.values?.MapdVersion || data.values?.MapdVersion;
  if (ver && mapd) ver.textContent = mapd;
}

function updateOsmCustomDom(block, data) {
  const size = data.size || {};
  const prog = data.progress || {};
  const sizeEl = block.querySelector("#osm-size-text");
  if (sizeEl) {
    if (size.pending) sizeEl.textContent = t("Calculating...");
    else if (size.ok) {
      const mb = Number(size.size_mb || 0);
      sizeEl.textContent = mb >= 1024
        ? `${(mb / 1024).toFixed(2)} ${t("GB")}`
        : `${mb.toFixed(2)} ${t("MB")}`;
    }
  }

  const slot = block.querySelector("#osm-progress-slot");
  if (slot) {
    slot.innerHTML = "";
    if (prog.ok && prog.active) {
      const pct = prog.progress || 0;
      const done = prog.done || 0;
      const total = prog.total || 0;
      let label = t("Downloading Map");
      if (total > 0 && prog.downloading) {
        label = `${Math.round(pct)}% - ${t("Downloading Maps")} (${done}/${total})`;
      }
      slot.appendChild(createProgressRow(label, pct));
    }
  }

  const checkBtn = block.querySelector("#osm-check-btn");
  const updateText = block.querySelector("#osm-update-text");
  if (checkBtn && prog.ok && prog.active) {
    const done = prog.done || 0;
    const total = prog.total || 0;
    if (total > 0 && prog.downloading) {
      const pct = Math.round(prog.progress || 0);
      checkBtn.textContent = `${done}/${total} (${pct}%)`;
      checkBtn.disabled = true;
    } else if (!prog.downloading && total > 0 && done < total) {
      checkBtn.textContent = t("Error: Invalid download. Retry.");
      checkBtn.disabled = false;
    } else {
      checkBtn.textContent = t("Downloading Maps...");
      checkBtn.disabled = true;
    }
  } else if (checkBtn) {
    checkBtn.textContent = t("CHECK");
    checkBtn.disabled = false;
    if (updateText && !prog.active) {
      updateText.textContent = formatLastChecked(panelDataRef?.values?.OsmDownloadedDate);
    }
  }

  const stateBtn = block.querySelector("#osm-state-btn");
  if (stateBtn) {
    const loc = panelDataRef?.values?.OsmLocationName || "";
    const stateRow = block.querySelector("#osm-state-row");
    if (stateRow) stateRow.hidden = String(loc) !== "US";
  }
}

async function pickOsmRegion(regionType) {
  const btn = document.getElementById(regionType === "Country" ? "osm-country-btn" : "osm-state-btn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = t("FETCHING...");
  }
  const regions = await apiGet(`/api/opui/osm/regions?type=${encodeURIComponent(regionType)}`);
  if (btn) {
    btn.disabled = false;
    btn.textContent = t("SELECT");
  }
  if (!regions.ok) {
    toast(regions.error || "Failed");
    return;
  }
  if (regions.bundled) {
    toast(t(regions.full ? "Using offline region list" : "Using offline region list (partial)"));
  } else if (regions.cached) {
    toast(t("Using cached region list"));
  }

  if (regionType === "Country") {
    const folders = [{
      name: "",
      bundles: (regions.countries || []).map((c) => ({ ref: c.name, name: c.title })),
    }];
    const ref = await showTree({ title: t("Country"), folders, searchable: true });
    if (!ref) return;
    const c = regions.countries.find((x) => x.name === ref);
    if (!c) return;
    const res = await apiPost("/api/opui/osm/select", { country: c.name, country_title: c.title });
    if (!res.ok) {
      toast(res.error || t("Failed"));
      return;
    }
    await syncOsmPanelAfterSelect(res.values);
    if (c.name === "US") {
      const stateRow = document.getElementById("osm-state-row");
      if (stateRow) stateRow.hidden = false;
      await pickOsmRegion("State");
    } else {
      await promptOsmDatabaseDownload();
    }
    return;
  }

  const countryTitle = panelDataRef?.values?.OsmLocationTitle || "";
  const country = panelDataRef?.values?.OsmLocationName || "";
  if (!country) {
    toast(t("Select a country first"));
    return;
  }
  const folders = [{
    name: "",
    bundles: (regions.states || []).map((s) => ({ ref: s.name, name: s.title })),
  }];
  const ref = await showTree({ title: t("State"), folders, searchable: true });
  if (!ref) {
    if (country === "US" && !panelDataRef?.values?.OsmStateName) {
      const clear = await apiPost("/api/opui/osm/clear");
      if (clear.ok) await syncOsmPanelAfterSelect(clear.values);
    }
    return;
  }
  const st = regions.states.find((s) => s.name === ref);
  const res = await apiPost("/api/opui/osm/select", {
    country,
    country_title: countryTitle,
    state: ref,
    state_title: st?.title || ref,
  });
  if (!res.ok) {
    toast(res.error || t("Failed"));
    return;
  }
  await syncOsmPanelAfterSelect(res.values);
  await promptOsmDatabaseDownload();
}

async function renderOsmPanel(container, data) {
  panelDataRef = data;
  const gen = beginPanelRender();
  container.innerHTML = "";
  const versionRow = document.createElement("div");
  versionRow.className = "opui-sp-row";
  versionRow.innerHTML = `
    <div class="opui-sp-row-text">
      <div class="opui-sp-row-title">${escapeHtml(t("Mapd Version"))}</div>
    </div>
    <span class="opui-sp-row-value" id="osm-mapd-version">${escapeHtml(data.values?.MapdVersion || t("Loading..."))}</span>`;
  container.appendChild(versionRow);

  const block = ensureOsmCustomBlock(container, data);
  if (panelRenderStale(gen)) return;
  try {
    const [size, prog] = await Promise.all([
      apiGet("/api/opui/osm/size"),
      apiGet("/api/opui/osm/progress"),
    ]);
    if (panelRenderStale(gen)) return;
    updateOsmCustomDom(block, { ok: true, size, progress: prog });
  } catch (_) {
    /* WS custom data will fill in */
  }
}

async function renderVehiclePanel(container, data) {
  const gen = beginPanelRender();
  container.innerHTML = "";
  const vp = await apiGet("/api/opui/vehicle/platforms");
  if (panelRenderStale(gen)) return;
  if (!vp.ok) return;

  const status = vp.status || (vp.manual ? "manual" : "unknown");
  const display = platformDisplayText(vp.display) || platformDisplayText(vp.active) || "";
  const titleText = display || t("No vehicle selected");
  const statusClass = status === "auto" ? "auto" : status === "manual" ? "manual" : "unknown";
  const actionLabel = vp.manual ? t("REMOVE") : t("SELECT");

  const pickRow = document.createElement("div");
  pickRow.className = "opui-sp-row";
  pickRow.innerHTML = `
    <div class="opui-sp-row-text">
      <div id="vehicle-platform-title" class="opui-sp-row-title opui-vehicle-title--${statusClass}">${escapeHtml(titleText)}</div>
    </div>
    <button type="button" id="vehicle-platform-btn" class="opui-btn opui-btn--action">${escapeHtml(actionLabel)}</button>`;
  pickRow.querySelector("button")?.addEventListener("click", async () => {
    const latest = await apiGet("/api/opui/vehicle/platforms");
    const hasManual = !!latest.manual;
    if (hasManual) {
      await apiPost("/api/opui/vehicle/select", { bundle: "" });
      toast(t("Vehicle"));
      await renderVehiclePanel(container, data);
      return;
    }
    const folders = (latest.tree || []).map((b) => ({
      name: b.name,
      bundles: (b.platforms || []).map((p) => ({ ref: p.bundle, name: p.label })),
    }));
    const ref = await showTree({ title: t("Select a vehicle"), folders, searchable: true });
    if (!ref) return;
    const offroadMsg = globalState.is_offroad
      ? t("This setting will take effect immediately.")
      : t("This setting will take effect once the device enters offroad state.");
    if (!(await showConfirm({ message: offroadMsg, confirmText: t("Confirm") }))) return;
    const res = await apiPost("/api/opui/vehicle/select", { bundle: ref });
    if (res.ok) {
      toast(platformDisplayText(res.display) || ref);
      await renderVehiclePanel(container, data);
    } else {
      toast(res.error || t("Failed"));
    }
  });
  container.appendChild(pickRow);

  const legend = document.createElement("div");
  legend.className = "opui-vehicle-legend";
  legend.innerHTML = `
    <p>${escapeHtml(t("Select vehicle to force fingerprint manually."))}</p>
    <p>${escapeHtml(t("Colors represent vehicle fingerprint status:"))}</p>
    <p><span class="dot green"></span> ${escapeHtml(t("Fingerprinted automatically"))}</p>
    <p><span class="dot blue"></span> ${escapeHtml(t("Manually selected fingerprint"))}</p>
    <p><span class="dot yellow"></span> ${escapeHtml(t("Not fingerprinted or manually selected"))}</p>`;
  container.appendChild(legend);

  const bw = await apiGet("/api/opui/vehicle/brand-widgets");
  if (panelRenderStale(gen)) return;
  if (bw.ok && bw.widgets?.length) {
    const brandData = { values: { ...data.values, ...bw.values } };
    for (const w of bw.widgets) {
      if (w.capability === "hyundai_long_tuning" && !bw.hyundai_long_tuning_available) continue;
      const el = renderWidget(w, brandData);
      if (el) container.appendChild(el);
    }
  }
}

const STREAM_QUALITY_LABELS = {
  auto: "Auto",
  low: "Smooth",
  med: "SD",
  high: "HD",
  off: "Off",
};

const HEADLESS_MODE_LABELS = { auto: "Auto", on: "Turn on", off: "Off" };
const HEADLESS_MODE_LEVELS = ["auto", "on", "off"];

function renderStreamHeadlessModeRow(w) {
  const row = document.createElement("div");
  row.className = "opui-sp-row opui-sp-row--stacked opui-sp-row--segmented opui-stream-settings-block";
  let cur = window.__OPUI_HEADLESS_MODE || "auto";
  let canTurnOff = window.__OPUI_HAS_BUILTIN_DISPLAY !== false;

  const text = document.createElement("div");
  text.className = "opui-sp-row-text";
  text.innerHTML = `<div class="opui-sp-row-title">${escapeHtml(t("Headless mode"))}</div>`;

  const hint = document.createElement("div");
  hint.className = "opui-stream-hint opui-stream-hint--muted";
  hint.hidden = true;

  const group = document.createElement("div");
  group.className = "opui-multi-btn-group";
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", t("Headless mode"));

  const buttons = new Map();

  function paint() {
    for (const [mode, btn] of buttons) {
      btn.classList.toggle("selected", mode === cur);
      if (mode === "off") {
        btn.disabled = !canTurnOff;
        btn.title = canTurnOff ? "" : t("No built-in display — headless cannot be turned off");
      }
    }
    hint.hidden = canTurnOff;
    if (!canTurnOff) {
      hint.textContent = t("No built-in display — headless cannot be turned off");
    }
  }

  for (const mode of HEADLESS_MODE_LEVELS) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = t(HEADLESS_MODE_LABELS[mode] || mode);
    buttons.set(mode, btn);
    btn.addEventListener("click", async () => {
      if (mode === "off" && !canTurnOff) return;
      const res = await apiPut("/api/opui/headless-mode", { mode });
      if (!res.ok) {
        toast(`${t("Headless mode update failed")}: ${res.error || t("Unknown error")}`);
        return;
      }
      cur = res.mode || mode;
      canTurnOff = res.can_turn_off !== false;
      paint();
      toast(t("Headless mode updated"));
      window.dispatchEvent(new CustomEvent("opui:headless-mode-changed", {
        detail: {
          mode: cur,
          effective_headless: !!res.effective_headless,
          recommended_overlay_fps: res.effective_headless ? 5 : 10,
        },
      }));
    });
    group.appendChild(btn);
  }

  paint();
  text.appendChild(hint);
  row.append(text, group);
  bindPanelHelp(row, w);

  apiGet("/api/opui/headless-mode").then((data) => {
    if (!data?.ok) return;
    cur = data.mode || "auto";
    canTurnOff = data.can_turn_off !== false;
    paint();
  }).catch(() => {});

  return row;
}

function renderStreamPreviewQualityRow(w) {
  const row = document.createElement("div");
  row.className = "opui-sp-row opui-sp-row--stacked opui-sp-row--segmented opui-stream-settings-block";
  const cur = getQualityPreference();

  const text = document.createElement("div");
  text.className = "opui-sp-row-text";
  text.innerHTML = `<div class="opui-sp-row-title">${escapeHtml(t("Preview quality"))}</div>`;

  const group = document.createElement("div");
  group.className = "opui-multi-btn-group";
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", t("Preview quality"));

  for (const level of QUALITY_LEVELS) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.classList.toggle("selected", level === cur);
    btn.textContent = t(STREAM_QUALITY_LABELS[level] || level);
    btn.addEventListener("click", async () => {
      const prev = getQualityPreference();
      setQualityPreference(level);
      group.querySelectorAll("button").forEach((el) => el.classList.remove("selected"));
      btn.classList.add("selected");
      toast(t("Preview quality updated"));
      const { applyStreamQuality, applyPreviewOffUi, isRoadStreaming, startRoadStream, stopRoadStream } = await import("./webrtc_stream.js?v=97");
      applyPreviewOffUi();
      if (level === "off") {
        if (isRoadStreaming()) await stopRoadStream();
      } else if (prev === "off" && document.getElementById("app")?.dataset.screen === "onroad") {
        await startRoadStream();
      } else if (isRoadStreaming()) {
        await applyStreamQuality(level, { user: true });
      }
    });
    group.appendChild(btn);
  }

  row.append(text, group);
  bindPanelHelp(row, w);
  return row;
}

const WEBCODECS_LABELS = { auto: "Auto", on: "Turn on", off: "Off" };

function renderStreamWebcodecsRow() {
  const row = document.createElement("div");
  row.className = "opui-sp-row opui-sp-row--stacked opui-sp-row--segmented opui-stream-settings-block";
  const cur = getWebCodecsPreference();
  const capable = webCodecsCapable();
  const cap = webCodecsCapability();

  const text = document.createElement("div");
  text.className = "opui-sp-row-text";
  text.innerHTML = `<div class="opui-sp-row-title">${escapeHtml(t("Hardware decode"))}</div>`;
  if (!capable) {
    const hint = document.createElement("div");
    hint.className = "opui-stream-hint opui-stream-hint--muted";
    if (!cap.secureContext) {
      hint.textContent = t("WebCodecs requires HTTPS or localhost. On the device use https://<IP>:5080/ (trust the certificate once).");
    } else if (!cap.videoDecoder || !cap.trackGenerator || !cap.encodedStreams) {
      hint.textContent = t("WebCodecs is not available in this browser.");
    } else {
      hint.textContent = t("WebCodecs is not available in this browser.");
    }
    text.appendChild(hint);
  }

  const group = document.createElement("div");
  group.className = "opui-multi-btn-group";
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", t("Hardware decode"));

  for (const mode of ["auto", "on", "off"]) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.classList.toggle("selected", mode === cur);
    btn.disabled = !capable && mode !== "off";
    btn.textContent = t(WEBCODECS_LABELS[mode] || mode);
    btn.addEventListener("click", () => {
      setWebCodecsPreference(mode);
      group.querySelectorAll("button").forEach((el) => el.classList.remove("selected"));
      btn.classList.add("selected");
      toast(t("Hardware decode setting updated"));
    });
    group.appendChild(btn);
  }

  row.append(text, group);
  bindPanelHelp(row, { desc_i18n: "webui_hardware_decode_desc" });
  return row;
}

function formatBitrate(bps) {
  if (bps == null) return "—";
  const mbps = bps / 1_000_000;
  if (mbps >= 1) return `${mbps.toFixed(1)} Mbps`;
  return `${Math.round(bps / 1000)} kbps`;
}

function streamDiagValueClass(kind) {
  if (kind === "on") return "opui-stream-diag-value--on";
  if (kind === "off") return "opui-stream-diag-value--off";
  if (kind === "warn") return "opui-stream-diag-value--warn";
  if (kind === "danger") return "opui-stream-diag-value--danger";
  return "";
}

function renderStreamDiagnosticsRow() {
  const row = document.createElement("div");
  row.className = "opui-stream-diag opui-stream-settings-block";
  row.innerHTML = `
    <div class="opui-stream-diag-title">${escapeHtml(t("Livestream diagnostics"))}</div>
    <div class="opui-stream-diag-grid" id="stream-diag-grid"></div>
    <div class="opui-stream-diag-foot" id="stream-diag-foot" hidden></div>`;
  const grid = row.querySelector("#stream-diag-grid");
  const foot = row.querySelector("#stream-diag-foot");

  const tiles = [
    { id: "stream", label: t("Stream stack") },
    { id: "bitrate", label: t("Bitrate") },
    { id: "camera", label: t("Camera") },
    { id: "thermal", label: t("Thermal") },
    { id: "lag", label: t("Encoder lag") },
    { id: "memory", label: t("Memory") },
    { id: "gpu", label: t("GPU") },
    { id: "storage", label: t("Storage") },
    { id: "cpu", label: t("CPU temp") },
    { id: "cpu_usage", label: t("CPU usage") },
    { id: "power", label: t("Power") },
  ];

  const cells = {};
  for (const tile of tiles) {
    const item = document.createElement("div");
    item.className = "opui-stream-diag-item";
    item.dataset.tile = tile.id;
    item.innerHTML = `
      <span class="opui-stream-diag-label">${escapeHtml(tile.label)}</span>
      <span class="opui-stream-diag-value">—</span>`;
    grid.appendChild(item);
    cells[tile.id] = item.querySelector(".opui-stream-diag-value");
  }

  const setCell = (id, text, tone = "") => {
    const el = cells[id];
    const item = el?.closest(".opui-stream-diag-item");
    if (!el || !item) return;
    if (text === null) {
      item.hidden = true;
      return;
    }
    item.hidden = false;
    el.textContent = text;
    el.className = "opui-stream-diag-value" + (tone ? ` ${streamDiagValueClass(tone)}` : "");
  };

  const streamStackLabel = (status) => {
    if (status === "active") return t("Active");
    if (status === "partial") return t("Partial");
    return t("Off");
  };

  const applyHealth = (h) => {
    if (!h?.ok) {
      setCell("stream", h?.error || t("Update status unavailable"), "danger");
      ["bitrate", "camera", "thermal", "lag", "memory", "gpu", "storage", "cpu", "cpu_usage", "power"].forEach((id) => setCell(id, null));
      foot.hidden = true;
      return;
    }
    const stack = h.stream_stack || ((h.livestreaming && h.webrtcd_listening) ? "active" : (h.livestreaming || h.webrtcd_listening) ? "partial" : "off");
    const stackTone = stack === "active" ? "on" : (stack === "partial" ? "warn" : "off");
    setCell("stream", streamStackLabel(stack), stackTone);
    setCell("bitrate", formatBitrate(h.encoder_bitrate));
    setCell("camera", h.active_camera || "—");
    setCell("thermal", h.thermal || "—", h.thermal === "ok" ? "on" : "warn");
    setCell("lag", h.encoder_lagging ? t("Yes") : t("No"), h.encoder_lagging ? "warn" : "on");
    setCell("memory", h.memory_usage_percent != null ? `${h.memory_usage_percent}%` : "—");
    setCell("gpu", h.gpu_usage_percent != null ? `${h.gpu_usage_percent}%` : "—");
    setCell("storage", h.free_space_percent != null ? `${h.free_space_percent}% ${t("free")}` : "—");
    setCell("cpu", h.cpu_temp != null ? `${h.cpu_temp}°C` : "—");
    setCell("cpu_usage", h.cpu_usage_percent != null ? `${h.cpu_usage_percent}%` : "—");
    setCell("power", h.power_draw_w != null ? `${h.power_draw_w} W` : "—");
    const decode = getStreamDecodePath();
    const parts = [`${t("Decode path")}: ${decode === "webcodecs" ? t("WebCodecs (browser HW)") : t("Video element (browser HW)")}`];
    if (h.livestreaming != null || h.webrtcd_listening != null) {
      parts.push(`${t("Livestream")}: ${h.livestreaming ? t("On") : t("Off")} · webrtcd: ${h.webrtcd_listening ? t("On") : t("Off")}`);
    }
    foot.textContent = parts.join(" · ");
    foot.hidden = false;
  };

  const refreshHttp = async () => {
    try {
      applyHealth(await apiGet("/api/opui/stream/health"));
    } catch {
      setCell("stream", t("Update status unavailable"), "danger");
      foot.hidden = true;
    }
  };

  if (opuiWs.connected) {
    opuiWs.watchStreamHealth();
    row._streamHealthOff = opuiWs.on("stream_health", (msg) => {
      if (msg?.data) applyHealth(msg.data);
    });
    if (opuiWs.lastStreamHealth?.data) applyHealth(opuiWs.lastStreamHealth.data);
    else refreshHttp();
  } else {
    refreshHttp();
    row._streamDiagTimer = setInterval(refreshHttp, 3000);
  }

  row._streamDiagVisHandler = () => {
    if (document.hidden) {
      if (row._streamDiagTimer) {
        clearInterval(row._streamDiagTimer);
        row._streamDiagTimer = null;
      }
    } else if (!row._streamHealthOff && !row._streamDiagTimer) {
      refreshHttp();
      row._streamDiagTimer = setInterval(refreshHttp, 3000);
    }
  };
  document.addEventListener("visibilitychange", row._streamDiagVisHandler);
  return row;
}

function renderLanguageRow() {
  const row = document.createElement("div");
  row.className = "opui-sp-row";
  const current = deviceExtrasCache?.languages?.find((l) => l.id === deviceExtrasCache?.current_language);
  row.innerHTML = `
    <div class="opui-sp-row-text">
      <div class="opui-sp-row-title">${escapeHtml(t("Change Language"))}</div>
      ${current ? `<div class="opui-sp-row-desc">${escapeHtml(current.label)}</div>` : ""}
    </div>
    <button type="button" class="opui-btn opui-btn--action">${escapeHtml(t("CHANGE"))}</button>`;
  row.querySelector("button")?.addEventListener("click", async () => {
    const ex = deviceExtrasCache || await apiGet("/api/opui/device/extras");
    if (!ex.ok) return;
    const langs = ex.languages || [];
    const idx = langs.findIndex((l) => l.id === ex.current_language);
    const pick = await showMultiOption({
      title: t("Select a language"),
      options: langs.map((l) => l.label),
      selected: Math.max(0, idx),
      current: Math.max(0, idx),
    });
    if (pick == null) return;
    const lang = langs[pick];
    if (!lang) return;
    const res = await apiPost("/api/opui/device/language", { language: lang.id });
    if (res.ok) {
      toast(`${t("Language")}: ${lang.label}`);
      deviceExtrasCache = { ...ex, current_language: lang.id };
      const { loadI18n } = await import("./i18n.js");
      await loadI18n(true);
      requestPanelRefresh();
      window.dispatchEvent(new CustomEvent("opui:language-changed"));
    }
  });
  return row;
}

function renderDriverCameraRow() {
  const row = document.createElement("div");
  row.className = "opui-sp-row";
  const disabled = !globalState.is_offroad;
  row.innerHTML = `
    <div class="opui-sp-row-text">
      <div class="opui-sp-row-title">${escapeHtml(t("Driver Camera"))}</div>
      <div class="opui-sp-row-desc">${escapeHtml(t("Preview the driver facing camera to ensure that driver monitoring has good visibility. (vehicle must be off)"))}</div>
    </div>
    <button type="button" class="opui-btn opui-btn--action" ${disabled ? "disabled" : ""}>${escapeHtml(t("PREVIEW"))}</button>`;
  if (!disabled) {
    row.querySelector("button")?.addEventListener("click", () => {
      window.dispatchEvent(new CustomEvent("opui:open-driver-camera"));
    });
  }
  return row;
}

function appendSpSeparator(container) {
  const sep = document.createElement("div");
  sep.className = "opui-sp-separator";
  sep.setAttribute("aria-hidden", "true");
  container.appendChild(sep);
}

function createSunnylinkActionRow({ title, desc, buttonText, valueText, valueColor, disabled, onClick }) {
  const row = document.createElement("div");
  row.className = "opui-sp-row opui-sp-row--sunnylink-action";
  if (disabled) row.classList.add("opui-sp-row--disabled");
  row.innerHTML = `
    <div class="opui-sp-row-text">
      <div class="opui-sp-row-title">${escapeHtml(t(title))}</div>
      ${desc ? `<div class="opui-sp-row-desc">${escapeHtml(t(desc))}</div>` : ""}
    </div>
    <div class="opui-row-actions">
      ${valueText ? `<span class="opui-row-value" style="${valueColor ? `color:${valueColor}` : ""}">${escapeHtml(valueText)}</span>` : ""}
      <button type="button" class="opui-btn opui-btn--action" ${disabled ? "disabled" : ""}>${escapeHtml(buttonText)}</button>
    </div>`;
  if (!disabled) row.querySelector("button")?.addEventListener("click", onClick);
  return row;
}

async function sunnylinkConsentFlow(slStatus) {
  while (true) {
    const enable = await showConfirm({
      message: t("sunnylink enables secured remote access to your comma device from anywhere, including settings management, remote monitoring, real-time dashboard, etc."),
      confirmText: t("Enable"),
      cancelText: t("Disable"),
    });
    if (enable) return true;
    const back = await showConfirm({
      message: t("sunnylink is designed to be enabled as part of sunnypilot's core functionality. If sunnylink is disabled, features such as settings management, remote monitoring, real-time dashboards will be unavailable."),
      confirmText: t("Back"),
      cancelText: t("Disable"),
    });
    if (back) continue;
    await putParam("CompletedSunnylinkConsentVersion", slStatus?.consent_declined_value || "-1");
    return false;
  }
}

async function ensureSunnylinkDongleRegistered(dongleId) {
  const dongle = String(dongleId || "").trim();
  if (!dongle || dongle === UNREGISTERED_SUNNYLINK_DONGLE_ID) {
    await showConfirm({
      message: `${t("sunnylink Dongle ID not found. ")}${t("This may be due to weak internet connection or sunnylink registration issue. ")}${t("Please reboot and try again.")}`,
      single: true,
      confirmText: t("OK"),
    });
    return false;
  }
  return true;
}

function updateSunnylinkHeaderDesc(hdr, enabled) {
  const green = hdr.querySelector(".opui-sunnylink-desc--green");
  const orange = hdr.querySelector(".opui-sunnylink-desc--orange");
  if (!green || !orange) return;
  if (enabled) {
    green.textContent = t("Welcome back!! We're excited to see you've enabled sunnylink again!");
    green.hidden = false;
    orange.hidden = true;
  } else {
    green.hidden = true;
    orange.innerHTML = `😢 ${escapeHtml(t("Not going to lie, it's sad to see you disabled sunnylink") + t(", but we'll be here when you're ready to come back."))}`;
    orange.hidden = false;
  }
}

function createSunnylinkToggleRow(w, rightValue, disabled, slStatus) {
  const extra = {};
  if (w.param === "SunnylinkEnabled") {
    extra.onBeforeChange = async (checked) => {
      if (!checked) return true;
      const ok = await sunnylinkConsentFlow(slStatus);
      if (!ok) return false;
      const version = slStatus?.required_consent_version || "1.0";
      await putParam("CompletedSunnylinkConsentVersion", version);
      return true;
    };
  }
  const row = createSpToggle({
    ...w,
    ...extra,
    label: t(w.label),
    desc: w.desc ? t(w.desc) : "",
    stacked: false,
    locked: disabled,
    offroad_only: w.offroad_only,
  }, {}, globalState, paramHandlers);
  row.classList.add("opui-sp-row--sunnylink-toggle");
  row.dataset.param = w.param;
  if (rightValue) {
    const dongle = document.createElement("div");
    dongle.className = "opui-row-value opui-sunnylink-dongle";
    dongle.textContent = rightValue;
    row.appendChild(dongle);
  }
  return row;
}

async function renderSunnylinkPanel(container, data) {
  const gen = beginPanelRender();
  container.innerHTML = "";
  const values = { ...(data.values || {}) };
  const offroad = globalState.is_offroad;
  const slEnabled = paramIsOn(values.SunnylinkEnabled);
  const childDisabled = !slEnabled;

  const hdr = document.createElement("div");
  hdr.className = "opui-sunnylink-header";
  hdr.innerHTML = `
    <div class="opui-sunnylink-title">${escapeHtml(t("🚀 sunnylink 🚀"))}</div>
    <div class="opui-sunnylink-desc opui-sunnylink-desc--green">${escapeHtml(t("For secure backup, restore, and remote configuration"))}</div>
    <div class="opui-sunnylink-desc opui-sunnylink-desc--orange">${escapeHtml(t("Sponsorship isn't required for basic backup/restore"))}<br>${escapeHtml(t("Click the Sponsor button for more details"))}</div>`;
  container.appendChild(hdr);
  appendSpSeparator(container);

  const slStatusPromise = apiGet("/api/opui/sunnylink/status");
  const sl = { ok: false, tier: "", tier_color: "#808080", is_sponsor: false, is_paired: false };

  const enabledRow = createSunnylinkToggleRow({
    param: "SunnylinkEnabled",
    label: "Enable sunnylink",
    desc: "This is the master switch, it will allow you to cutoff any sunnylink requests should you want to do that.",
    value: values.SunnylinkEnabled,
    offroad_only: true,
  }, `${t("Dongle ID")}: ${values.SunnylinkDongleId || t("N/A")}`, !offroad, sl);
  enabledRow.dataset.slMaster = "1";
  enabledRow.querySelector("input")?.addEventListener("change", () => {
    updateSunnylinkHeaderDesc(hdr, !!enabledRow.querySelector("input")?.checked);
  });
  container.appendChild(enabledRow);
  appendSpSeparator(container);

  const sponsorRow = createSunnylinkActionRow({
    title: "Sponsor Status",
    desc: "Become a sponsor of sunnypilot to get early access to sunnylink features when they become available.",
    buttonText: t("SPONSOR"),
    valueText: t("Not Sponsor"),
    valueColor: "#808080",
    disabled: childDisabled,
    onClick: async () => {
      if (!(await ensureSunnylinkDongleRegistered(values.SunnylinkDongleId))) return;
      const res = await apiGet("/api/opui/sunnylink/pair?mode=sponsor");
      if (!res.ok) { toast(res.error || t("Failed")); return; }
      await showQrPair({ title: t("Sponsor sunnylink"), url: res.url, qrDataUrl: res.qr_data_url });
    },
  });
  sponsorRow.dataset.slSponsor = "1";
  container.appendChild(sponsorRow);
  appendSpSeparator(container);

  const pairRow = createSunnylinkActionRow({
    title: "Pair GitHub Account",
    desc: "Pair your GitHub account to grant your device sponsor benefits, including API access on sunnylink.",
    buttonText: t("Not Paired"),
    disabled: childDisabled,
    onClick: async () => {
      if (!(await ensureSunnylinkDongleRegistered(values.SunnylinkDongleId))) return;
      const res = await apiGet("/api/opui/sunnylink/pair?mode=pair");
      if (!res.ok) { toast(res.error || t("Failed")); return; }
      await showQrPair({
        title: t("Pair GitHub Account"),
        url: res.url,
        qrDataUrl: res.qr_data_url,
        onPoll: async () => {
          const st = await apiGet("/api/opui/sunnylink/status");
          return !!st?.is_paired;
        },
      });
    },
  });
  pairRow.dataset.slPair = "1";
  container.appendChild(pairRow);
  appendSpSeparator(container);

  const uploaderRow = createSunnylinkToggleRow({
    param: "EnableSunnylinkUploader",
    label: "Enable sunnylink uploader (infrastructure test)",
    desc: "Enable sunnylink uploader to allow sunnypilot to upload your driving data to sunnypilot servers. (Only for highest tiers, and does NOT bring ANY benefit to you yet. We are just testing data volume.)",
    value: values.EnableSunnylinkUploader,
    offroad_only: false,
  }, "", childDisabled, sl);
  uploaderRow.dataset.slUploader = "1";
  container.appendChild(uploaderRow);
  appendSpSeparator(container);

  const backupSlot = document.createElement("div");
  backupSlot.dataset.slBackup = "1";
  container.appendChild(backupSlot);

  const dualDisabled = childDisabled || !offroad;
  let backupBtnEl = null;
  let restoreBtnEl = null;
  let backupBusy = false;
  let restoreBusy = false;
  let notifiedBackupDone = false;
  let notifiedRestoreDone = false;
  let notifiedRestoreFail = false;
  let slPollTimer = null;

  const dual = createDualButton(
    { label: t("Backup Settings"), disabled: dualDisabled },
    { label: t("Restore Settings"), primary: true, disabled: dualDisabled },
    async () => {
      if (!(await showConfirm({
        message: t("Are you sure you want to backup your current sunnypilot settings?"),
        confirmText: t("Backup"),
        cancelText: t("Cancel"),
      }))) return;
      const res = await apiPost("/api/opui/action/sunnylink_backup");
      if (res.ok) {
        backupBusy = true;
        restoreBusy = false;
        notifiedBackupDone = false;
        toast(t("Backup started"));
        startSunnylinkPoll();
      } else toast(res.error || t("Failed"));
    },
    async () => {
      if (!(await showConfirm({
        message: t("Are you sure you want to restore the last backed up sunnypilot settings?"),
        confirmText: t("Restore"),
        cancelText: t("Cancel"),
      }))) return;
      const res = await apiPost("/api/opui/action/sunnylink_restore");
      if (res.ok) {
        restoreBusy = true;
        backupBusy = false;
        notifiedRestoreDone = false;
        notifiedRestoreFail = false;
        toast(t("Restore started"));
        startSunnylinkPoll();
      } else toast(res.error || t("Failed"));
    },
  );
  [backupBtnEl, restoreBtnEl] = dual.querySelectorAll("button");
  dual.dataset.slDual = "1";
  container.appendChild(dual);

  const stopSunnylinkPoll = () => {
    if (slPollTimer) {
      clearInterval(slPollTimer);
      slPollTimer = null;
    }
  };

  const startSunnylinkPoll = () => {
    if (slPollTimer) return;
    slPollTimer = setInterval(async () => {
      if (panelRenderStale(gen)) {
        stopSunnylinkPoll();
        return;
      }
      const st = await apiGet("/api/opui/sunnylink/status").catch(() => null);
      if (st?.ok) applySunnylinkStatus(st);
    }, 1500);
  };

  const applySunnylinkStatus = async (status) => {
    if (!status?.ok) return;
    const dongleId = status.dongle_id || values.SunnylinkDongleId || t("N/A");
    const dongleEl = enabledRow.querySelector(".opui-sunnylink-dongle");
    if (dongleEl) dongleEl.textContent = `${t("Dongle ID")}: ${dongleId}`;

    const sponsorBtn = sponsorRow.querySelector("button");
    const sponsorVal = sponsorRow.querySelector(".opui-row-value");
    if (sponsorBtn) sponsorBtn.textContent = status.is_sponsor ? t("THANKS ♥") : t("SPONSOR");
    if (sponsorVal) {
      sponsorVal.textContent = status.tier || t("Not Sponsor");
      sponsorVal.style.color = status.tier_color || "#808080";
    }

    const pairBtn = pairRow.querySelector("button");
    if (pairBtn) pairBtn.textContent = status.is_paired ? t("Paired") : t("Not Paired");

    const bm = status.backup || {};
    const phase = bm.phase || bm.status || "idle";
    const progress = Math.round(bm.progress || 0);
    const canUse = slEnabled && offroad && !globalState.started;

    backupSlot.innerHTML = "";
    if (phase === "backing_up" || phase === "restoring") {
      const label = phase === "restoring"
        ? `${t("Restoring")} ${progress}%`
        : `${t("Backing up")} ${progress}%`;
      backupSlot.appendChild(createProgressRow(label, progress));
      appendSpSeparator(backupSlot);
    }

    if (backupBtnEl) {
      if (phase === "backing_up") {
        backupBtnEl.disabled = true;
        backupBtnEl.textContent = `${t("Backing up")} ${progress}%`;
      } else if (phase === "backup_failed") {
        backupBtnEl.disabled = !canUse;
        backupBtnEl.textContent = t("Backup Failed");
        backupBusy = false;
      } else {
        backupBtnEl.disabled = !canUse || phase === "restoring";
        backupBtnEl.textContent = t("Backup Settings");
        if (phase !== "backing_up") backupBusy = false;
      }
    }

    if (restoreBtnEl) {
      if (phase === "restoring") {
        restoreBtnEl.disabled = true;
        restoreBtnEl.textContent = `${t("Restoring")} ${progress}%`;
      } else if (phase === "restore_failed") {
        restoreBtnEl.disabled = !canUse;
        restoreBtnEl.textContent = t("Restore Failed");
        restoreBusy = false;
        if (!notifiedRestoreFail) {
          notifiedRestoreFail = true;
          await showConfirm({
            message: t("Unable to restore the settings, try again later."),
            confirmText: t("OK"),
            single: true,
          });
        }
      } else {
        restoreBtnEl.disabled = !canUse || phase === "backing_up";
        restoreBtnEl.textContent = t("Restore Settings");
        if (phase !== "restoring") restoreBusy = false;
      }
    }

    if (phase === "backup_done" && backupBusy && !notifiedBackupDone) {
      notifiedBackupDone = true;
      backupBusy = false;
      await showConfirm({
        message: t("Settings backup completed."),
        confirmText: t("OK"),
        single: true,
      });
    }

    if (phase === "restore_done" && restoreBusy && !notifiedRestoreDone) {
      notifiedRestoreDone = true;
      restoreBusy = false;
      const ok = await showConfirm({
        message: t("Settings restored. Confirm to restart the interface."),
        confirmText: t("OK"),
        single: true,
      });
      if (ok) window.location.reload();
    }

    if (!backupBusy && !restoreBusy && phase === "idle") {
      stopSunnylinkPoll();
    } else if (phase === "backing_up" || phase === "restoring") {
      startSunnylinkPoll();
    }
  };

  Object.assign(sl, await slStatusPromise);
  if (panelRenderStale(gen)) return;
  await applySunnylinkStatus(sl);
  if (sl.backup?.phase === "backing_up" || sl.backup?.phase === "restoring") {
    backupBusy = sl.backup.phase === "backing_up";
    restoreBusy = sl.backup.phase === "restoring";
    startSunnylinkPoll();
  }
}

async function renderStoragePanel(container, opts = {}) {
  const force = Boolean(opts.force);
  const { loadI18n } = await import("./i18n.js");
  await loadI18n(true);
  container.innerHTML = `<p class="opui-muted opui-panel-loading" style="padding:48px;text-align:center">${escapeHtml(t("Calculating..."))}</p>`;
  const data = await apiGet(`/api/opui/storage${force ? "?force=1" : ""}`);
  if (!data.ok) {
    container.innerHTML = `<p class="opui-muted" style="padding:48px">${escapeHtml(data.error || t("Load failed"))}</p>`;
    return;
  }
  container.innerHTML = "";

  const CAT_META = {
    routes: { label: t("Routes"), color: "#4A90D9" },
    models: { label: t("Models"), color: "#9B59B6" },
    maps: { label: t("Maps"), color: "#27AE60" },
    software: { label: t("Software"), color: "#8E8E93" },
    logs: { label: t("Logs"), color: "#D4AC0D" },
    ota_staging: { label: t("OTA staging"), color: "#E67E22" },
    scons_cache: { label: t("Build cache"), color: "#3498DB" },
    other: { label: t("Other"), color: "#555555" },
  };

  const CLEAR_ACTIONS = [
    {
      category: "routes",
      label: t("Clear route recordings"),
      desc: t("Deletes non-preserved driving segments. Starred and recent routes are kept."),
    },
    {
      category: "routes_starred",
      label: t("Clear starred routes"),
      desc: t("Deletes route recordings you bookmarked while driving. Other routes are not affected."),
      starredList: true,
    },
    {
      category: "maps",
      label: t("Clear map cache"),
      desc: t("Removes downloaded OSM map data. Maps can be downloaded again from OSM settings."),
    },
    {
      category: "models_cache",
      label: t("Clear model cache"),
      desc: t("Removes downloaded models except the one currently in use."),
    },
    {
      category: "logs",
      label: t("Clear logs"),
      desc: t("Removes system logs and crash dumps."),
    },
    {
      category: "scons_cache",
      label: t("Clear build cache"),
      desc: t("webui_storage_scons_cache_clear_desc"),
    },
    {
      category: "download_cache",
      label: t("Clear download cache"),
      desc: t("Removes temporary download files. Safe to clear."),
    },
  ];

  const wrap = document.createElement("div");
  wrap.className = "opui-storage-wrap";

  const hasExternal = Boolean(data.external?.mounted);

  const summary = document.createElement("div");
  summary.className = "opui-storage-summary";
  const usedPct = data.total_bytes ? Math.round((data.used_bytes / data.total_bytes) * 100) : 0;
  const head = document.createElement("div");
  head.className = "opui-storage-summary-head";
  const titleEl = document.createElement("div");
  titleEl.className = "opui-storage-summary-title";
  titleEl.textContent = `${formatStorageBytes(data.total_bytes)} ${t("total")}`;
  const refreshBtn = document.createElement("button");
  refreshBtn.type = "button";
  refreshBtn.className = "opui-btn opui-btn--ghost opui-storage-refresh";
  refreshBtn.textContent = t("Refresh");
  refreshBtn.addEventListener("click", () => renderStoragePanel(container, { force: true }));
  head.appendChild(titleEl);
  head.appendChild(refreshBtn);
  summary.appendChild(head);
  const sub = document.createElement("div");
  sub.className = `opui-storage-summary-sub${data.low_space ? " opui-storage-summary-sub--warn" : ""}${data.critical_space ? " opui-storage-summary-sub--danger" : ""}`;
  sub.textContent = tFmt("Used {used} ({pct}%) · Free {free}", {
    used: formatStorageBytes(data.used_bytes),
    pct: String(usedPct),
    free: formatStorageBytes(data.free_bytes),
  });
  summary.appendChild(sub);
  wrap.appendChild(summary);

  const bar = document.createElement("div");
  bar.className = "opui-storage-bar";
  bar.setAttribute("role", "img");
  bar.setAttribute("aria-label", t("Storage usage"));

  if (hasExternal) {
    const intHead = document.createElement("div");
    intHead.className = "opui-storage-volume-head";
    intHead.innerHTML = `
      <div class="opui-storage-volume-title">${escapeHtml(t("Internal storage"))}</div>
      <div class="opui-storage-volume-capacity">${escapeHtml(formatStorageBytes(data.total_bytes))}</div>`;
    wrap.appendChild(intHead);
  }
  const segments = (data.categories || []).filter((c) => c.bytes > 0 && CAT_META[c.id]);
  const denom = data.total_bytes || 1;
  for (const cat of segments) {
    const seg = document.createElement("div");
    seg.className = "opui-storage-bar-seg";
    seg.style.width = `${Math.max(0.4, (cat.bytes / denom) * 100)}%`;
    seg.style.background = CAT_META[cat.id].color;
    seg.title = `${CAT_META[cat.id].label} ${formatStorageBytes(cat.bytes)}`;
    bar.appendChild(seg);
  }
  if (data.free_bytes > 0) {
    const freeSeg = document.createElement("div");
    freeSeg.className = "opui-storage-bar-seg opui-storage-bar-seg--free";
    freeSeg.style.width = `${Math.max(0.4, (data.free_bytes / denom) * 100)}%`;
    freeSeg.title = `${t("Free")} ${formatStorageBytes(data.free_bytes)}`;
    bar.appendChild(freeSeg);
  }
  wrap.appendChild(bar);

  const legend = document.createElement("div");
  legend.className = "opui-storage-legend";
  for (const cat of data.categories || []) {
    const meta = CAT_META[cat.id];
    if (!meta) continue;
    const row = document.createElement("div");
    row.className = "opui-storage-legend-row";
    row.innerHTML = `
      <span class="opui-storage-dot" style="background:${meta.color}"></span>
      <span class="opui-storage-legend-label">${escapeHtml(meta.label)}</span>
      <span class="opui-storage-legend-size">${escapeHtml(formatStorageBytes(cat.bytes))}</span>
      <span class="opui-storage-legend-pct">${escapeHtml(String(cat.percent))}%</span>`;
    legend.appendChild(row);
  }
  const freeRow = document.createElement("div");
  freeRow.className = "opui-storage-legend-row";
  freeRow.innerHTML = `
    <span class="opui-storage-dot opui-storage-dot--free"></span>
    <span class="opui-storage-legend-label">${escapeHtml(t("Free"))}</span>
    <span class="opui-storage-legend-size">${escapeHtml(formatStorageBytes(data.free_bytes))}</span>
    <span class="opui-storage-legend-pct">${escapeHtml(String(data.free_percent ?? 0))}%</span>`;
  legend.appendChild(freeRow);
  wrap.appendChild(legend);

  const otaStaging = (data.categories || []).find((c) => c.id === "ota_staging");
  if (otaStaging?.bytes > 0) {
    const otaNote = document.createElement("p");
    otaNote.className = "opui-storage-volume-note";
    otaNote.textContent = t("webui_storage_ota_staging_note");
    wrap.appendChild(otaNote);
  }

  if (hasExternal) {
    const ext = data.external;
    wrap.appendChild(document.createElement("hr"));
    const extBlock = document.createElement("div");
    extBlock.className = "opui-storage-volume opui-storage-volume--external";

    const extHead = document.createElement("div");
    extHead.className = "opui-storage-volume-head";
    extHead.innerHTML = `
      <div class="opui-storage-volume-title">${escapeHtml(t("External SSD"))}</div>
      <div class="opui-storage-volume-capacity">${escapeHtml(formatStorageBytes(ext.total_bytes))}</div>`;
    extBlock.appendChild(extHead);

    const extUsedPct = ext.total_bytes ? Math.round((ext.used_bytes / ext.total_bytes) * 100) : 0;
    const extSub = document.createElement("div");
    extSub.className = `opui-storage-summary-sub opui-storage-summary-sub--volume${ext.low_space ? " opui-storage-summary-sub--warn" : ""}${ext.critical_space ? " opui-storage-summary-sub--danger" : ""}`;
    extSub.textContent = tFmt("Used {used} ({pct}%) · Free {free}", {
      used: formatStorageBytes(ext.used_bytes),
      pct: String(extUsedPct),
      free: formatStorageBytes(ext.free_bytes),
    });
    extBlock.appendChild(extSub);

    const extNote = document.createElement("p");
    extNote.className = "opui-storage-volume-note";
    extNote.textContent = t("webui_storage_external_note");
    extBlock.appendChild(extNote);

    const extBar = document.createElement("div");
    extBar.className = "opui-storage-bar";
    extBar.setAttribute("role", "img");
    extBar.setAttribute("aria-label", t("External SSD"));
    const extDenom = ext.total_bytes || 1;
    const routesBytes = ext.routes_bytes || 0;
    if (routesBytes > 0) {
      const routeSeg = document.createElement("div");
      routeSeg.className = "opui-storage-bar-seg";
      routeSeg.style.width = `${Math.max(0.4, (routesBytes / extDenom) * 100)}%`;
      routeSeg.style.background = CAT_META.routes.color;
      routeSeg.title = `${CAT_META.routes.label} ${formatStorageBytes(routesBytes)}`;
      extBar.appendChild(routeSeg);
    }
    if (ext.free_bytes > 0) {
      const extFreeSeg = document.createElement("div");
      extFreeSeg.className = "opui-storage-bar-seg opui-storage-bar-seg--free";
      extFreeSeg.style.width = `${Math.max(0.4, (ext.free_bytes / extDenom) * 100)}%`;
      extFreeSeg.title = `${t("Free")} ${formatStorageBytes(ext.free_bytes)}`;
      extBar.appendChild(extFreeSeg);
    }
    extBlock.appendChild(extBar);

    const extLegend = document.createElement("div");
    extLegend.className = "opui-storage-legend";
    const routeRow = document.createElement("div");
    routeRow.className = "opui-storage-legend-row";
    const routePct = ext.total_bytes ? Math.round((routesBytes / ext.total_bytes) * 100) : 0;
    routeRow.innerHTML = `
      <span class="opui-storage-dot" style="background:${CAT_META.routes.color}"></span>
      <span class="opui-storage-legend-label">${escapeHtml(CAT_META.routes.label)}</span>
      <span class="opui-storage-legend-size">${escapeHtml(formatStorageBytes(routesBytes))}</span>
      <span class="opui-storage-legend-pct">${escapeHtml(String(routePct))}%</span>`;
    extLegend.appendChild(routeRow);
    const extFreeRow = document.createElement("div");
    extFreeRow.className = "opui-storage-legend-row";
    extFreeRow.innerHTML = `
      <span class="opui-storage-dot opui-storage-dot--free"></span>
      <span class="opui-storage-legend-label">${escapeHtml(t("Free"))}</span>
      <span class="opui-storage-legend-size">${escapeHtml(formatStorageBytes(ext.free_bytes))}</span>
      <span class="opui-storage-legend-pct">${escapeHtml(String(ext.free_percent ?? 0))}%</span>`;
    extLegend.appendChild(extFreeRow);
    extBlock.appendChild(extLegend);
    wrap.appendChild(extBlock);
  }

  if (data.critical_space) {
    const warn = document.createElement("p");
    warn.className = "opui-storage-warn opui-storage-warn--danger";
    warn.textContent = t("Free up storage (less than 2% space remaining)");
    wrap.appendChild(warn);
  } else if (data.low_space) {
    const warn = document.createElement("p");
    warn.className = "opui-storage-warn";
    warn.textContent = t("Storage is running low (less than 10% free).");
    wrap.appendChild(warn);
  }

  wrap.appendChild(document.createElement("hr"));

  const actionsTitle = document.createElement("div");
  actionsTitle.className = "opui-storage-section-title";
  actionsTitle.textContent = t("Cleanup");
  wrap.appendChild(actionsTitle);

  const offroad = data.offroad !== false;
  for (const action of CLEAR_ACTIONS) {
    const est = data.clearable?.[action.category];
    let desc = action.desc;
    if (action.category === "routes") {
      const autoHint = t("webui_storage_routes_autodelete_hint");
      let extraHint = "";
      if (data.routes_external_bytes > 0) {
        extraHint = tFmt("webui_storage_routes_external_includes", {
          size: formatStorageBytes(data.routes_external_bytes),
        });
      }
      desc = [action.desc, autoHint, extraHint].filter(Boolean).join(" ");
    }
    const starred = data.starred_routes || {};
    if (action.category === "routes_starred" && starred.count > 0) {
      desc = `${action.desc} ${tFmt("webui_storage_starred_count", { count: String(starred.count) })}`;
    }
    const row = document.createElement("div");
    row.className = "opui-sp-row opui-storage-action-row";
    const canClear = offroad && est != null && est > 0;
    row.innerHTML = `
      <div class="opui-sp-row-text">
        <div class="opui-sp-row-title">${escapeHtml(action.label)}</div>
        <div class="opui-sp-row-desc">${escapeHtml(desc)}</div>
        ${est != null && est > 0 ? `<div class="opui-sp-row-desc opui-storage-est">${escapeHtml(tFmt("About {size} can be freed", { size: formatStorageBytes(est) }))}</div>` : ""}
      </div>
      <button type="button" class="opui-btn opui-btn--dialog opui-storage-clear-btn" ${canClear ? "" : "disabled"}>${escapeHtml(t("Clear"))}</button>`;
    const btn = row.querySelector(".opui-storage-clear-btn");
    btn?.addEventListener("click", async () => {
      if (!offroad) {
        toast(t("Only available while offroad"));
        return;
      }
      const sizeText = est != null ? formatStorageBytes(est) : "";
      let confirmMessage = sizeText
        ? tFmt("This will free about {size}. Continue?", { size: sizeText })
        : t("Are you sure you want to clear this data?");
      if (action.category === "routes_starred" && starred.count > 0) {
        confirmMessage = tFmt("webui_storage_starred_confirm", {
          count: String(starred.count),
          size: sizeText || formatStorageBytes(starred.bytes || 0),
        });
      }
      if (action.category === "scons_cache") {
        confirmMessage = t("webui_storage_scons_cache_confirm");
      }
      const ok = await showConfirm({
        message: confirmMessage,
        confirmText: t("Clear"),
        cancelText: t("Cancel"),
      });
      if (!ok) return;
      btn.disabled = true;
      const res = await apiPost("/api/opui/storage/clear", { category: action.category });
      if (!res.ok) {
        toast(res.error || t("Save failed"));
        btn.disabled = false;
        return;
      }
      toast(tFmt("Freed {size}", { size: formatStorageBytes(res.freed_bytes || est || 0) }));
      await renderStoragePanel(container);
    });
    wrap.appendChild(row);

    if (action.starredList && starred.count > 0 && Array.isArray(starred.items)) {
      const list = document.createElement("div");
      list.className = "opui-storage-starred-list";
      const maxRows = 6;
      for (const item of starred.items.slice(0, maxRows)) {
        const line = document.createElement("div");
        line.className = "opui-storage-starred-row";
        const volLabel = item.volume === "external" ? t("External SSD") : t("Internal storage");
        line.innerHTML = `
          <span class="opui-storage-starred-id">${escapeHtml(item.id)}</span>
          <span class="opui-storage-starred-meta">${escapeHtml(volLabel)} · ${escapeHtml(formatStorageBytes(item.bytes))}</span>`;
        list.appendChild(line);
      }
      if (starred.items.length > maxRows) {
        const more = document.createElement("div");
        more.className = "opui-storage-starred-more";
        more.textContent = tFmt("webui_storage_starred_more", {
          count: String(starred.items.length - maxRows),
        });
        list.appendChild(more);
      }
      wrap.appendChild(list);
    }
  }

  if (!offroad) {
    const hint = document.createElement("p");
    hint.className = "opui-storage-hint";
    hint.textContent = t("Cleanup is only available while offroad.");
    wrap.appendChild(hint);
  }

  container.appendChild(wrap);
}

function formatStorageBytes(bytes) {
  const n = Number(bytes);
  if (!Number.isFinite(n) || n < 0) return "—";
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(1)} GB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  if (n >= 1024) return `${Math.round(n / 1024)} KB`;
  return `${n} B`;
}

function tFmt(template, vars = {}) {
  let out = t(template);
  for (const [k, v] of Object.entries(vars)) {
    out = out.replace(new RegExp(`\\{${k}\\}`, "g"), v);
  }
  return out;
}

async function renderFirehosePanel(container) {
  const fh = await apiGet("/api/opui/firehose");
  if (!fh.ok) {
    container.innerHTML = `<p class="opui-muted" style="padding:48px">${escapeHtml(fh.error || "")}</p>`;
    return;
  }
  container.innerHTML = "";

  const wrap = document.createElement("div");
  wrap.className = "opui-firehose-wrap";

  const title = document.createElement("h2");
  title.className = "opui-firehose-h";
  title.textContent = t("Firehose Mode");
  wrap.appendChild(title);

  const desc = document.createElement("p");
  desc.className = "opui-firehose-desc";
  desc.textContent = t(
    "sunnypilot learns to drive by watching humans, like you, drive.\n\n"
    + "Firehose Mode allows you to maximize your training data uploads to improve "
    + "openpilot's driving models. More data means bigger models, which means better Experimental Mode."
  );
  wrap.appendChild(desc);

  wrap.appendChild(document.createElement("hr"));

  const statusColor = fh.active ? "#2ecc71" : "#e74c3c";
  const status = document.createElement("p");
  status.id = "firehose-status-text";
  status.className = "opui-firehose-status";
  status.style.color = statusColor;
  status.textContent = firehoseStatusText(fh.active);
  wrap.appendChild(status);

  if (fh.segments > 0) {
    const seg = document.createElement("p");
    seg.className = "opui-firehose-segments";
    seg.textContent = `${fh.segments} ${t("segments in training dataset")}`;
    wrap.appendChild(seg);
  }

  const net = document.createElement("div");
  net.className = "opui-sp-row";
  net.innerHTML = `
    <div class="opui-sp-row-text">
      <div class="opui-sp-row-title">${escapeHtml(t("Network"))}</div>
      <div class="opui-sp-row-desc">${escapeHtml(fh.network_type || "--")}${fh.metered ? ` (${t("metered")})` : ""}</div>
    </div>`;
  wrap.appendChild(net);

  wrap.appendChild(document.createElement("hr"));

  const instructions = document.createElement("div");
  instructions.className = "opui-firehose-instructions";
  instructions.innerHTML = `
    <p>${escapeHtml(t("For maximum effectiveness, bring your device inside and connect to a good USB-C adapter and Wi-Fi weekly."))}</p>
    <p>${escapeHtml(t("Firehose Mode can also work while you're driving if connected to a hotspot or unlimited SIM card."))}</p>
    <h3>${escapeHtml(t("Frequently Asked Questions"))}</h3>
    <p><strong>${escapeHtml(t("Does it matter how or where I drive?"))}</strong> ${escapeHtml(t("Nope, just drive as you normally would."))}</p>
    <p><strong>${escapeHtml(t("Do all of my segments get pulled in Firehose Mode?"))}</strong> ${escapeHtml(t("No, we selectively pull a subset of your segments."))}</p>
    <p><strong>${escapeHtml(t("What's a good USB-C adapter?"))}</strong> ${escapeHtml(t("Any fast phone or laptop charger should be fine."))}</p>
    <p><strong>${escapeHtml(t("Does it matter which software I run?"))}</strong> ${escapeHtml(t("Yes, only upstream openpilot (and particular forks) are able to be used for training."))}</p>`;
  wrap.appendChild(instructions);

  container.appendChild(wrap);
}

async function renderSoftwarePanel(container, data) {
  const gen = beginPanelRender();
  const sw = await apiGet("/api/opui/software");
  if (panelRenderStale(gen)) return;
  container.innerHTML = "";
  if (!sw.ok) {
    container.innerHTML = `<p class="opui-muted" style="padding:48px">${escapeHtml(sw.error || t("Failed"))}</p>`;
    return;
  }

  const body = createPanelBody(container);

  if (sw.is_onroad) {
    const warn = document.createElement("div");
    warn.id = "software-onroad-warn";
    warn.className = "opui-row opui-row--warn";
    warn.textContent = t("Updates are only downloaded while the car is off.");
    body.insertBefore(warn, body.firstChild);
  }

  const version = document.createElement("div");
  version.className = "opui-sp-row opui-sp-row--value-right";
  version.innerHTML = `
    <div class="opui-sp-row-text opui-sp-row-text--expandable">
      <div class="opui-sp-row-title">${escapeHtml(t("Current Version"))}</div>
      <div class="opui-release-notes" id="software-current-notes" hidden></div>
    </div>
    <div class="opui-sp-row-value" id="software-current-desc">${escapeHtml(sw.current || t("N/A"))}</div>`;
  version.querySelector(".opui-sp-row-text")?.addEventListener("click", (e) => {
    const notes = document.getElementById("software-current-notes");
    if (!notes || !notes.innerHTML.trim()) return;
    const expanded = notes.dataset.expanded === "1";
    notes.dataset.expanded = expanded ? "0" : "1";
    notes.hidden = expanded;
    version.classList.toggle("opui-sp-row--desc-open", !expanded);
  });
  body.appendChild(version);

  const download = document.createElement("div");
  download.id = "software-download-row";
  download.className = "opui-sp-row opui-sp-row--has-action";
  download.innerHTML = `
    <div class="opui-sp-row-text">
      <div class="opui-sp-row-title">${escapeHtml(t("Download"))}</div>
    </div>
    <div class="opui-sp-row-value" id="software-download-value"></div>
    <button type="button" class="opui-btn opui-btn--action" id="software-download-btn">${escapeHtml(t("CHECK"))}</button>`;
  download.querySelector("#software-download-btn")?.addEventListener("click", async () => {
    const btn = download.querySelector("#software-download-btn");
    const label = btn?.textContent?.trim();
    const action = label === t("DOWNLOAD") ? "updater_download" : "updater_check";
    if (btn) btn.disabled = true;
    softwareDownloadWaitUntil = Date.now() + SOFTWARE_UPDATER_TIMEOUT_MS;
    applySoftwareCustom(panelDataRef);
    const res = await apiPost(`/api/opui/action/${action}`);
    if (!res.ok) {
      softwareDownloadWaitUntil = 0;
      toast(res.error || t("Failed"));
      applySoftwareCustom(panelDataRef);
      return;
    }
    const deadline = Date.now() + SOFTWARE_UPDATER_TIMEOUT_MS;
    while (Date.now() < deadline) {
      try {
        const sw = await apiGet("/api/opui/software");
        if (sw?.ok) {
          panelDataRef = { ...panelDataRef, software: sw };
          applySoftwareCustom(sw);
          if (sw.updater_state && sw.updater_state !== "idle") {
            softwareDownloadWaitUntil = 0;
            return;
          }
        }
      } catch { /* keep polling until timeout */ }
      await new Promise((r) => setTimeout(r, 400));
    }
    softwareDownloadWaitUntil = 0;
    try {
      const sw = await apiGet("/api/opui/software");
      if (sw?.ok) applySoftwareCustom(sw);
    } catch { applySoftwareCustom(panelDataRef); }
  });
  body.appendChild(download);

  const install = document.createElement("div");
  install.id = "software-install-row";
  install.className = "opui-sp-row opui-sp-row--has-action";
  install.hidden = true;
  install.innerHTML = `
    <div class="opui-sp-row-text opui-sp-row-text--expandable">
      <div class="opui-sp-row-title">${escapeHtml(t("Install Update"))}</div>
      <div class="opui-release-notes" id="software-install-notes" hidden></div>
    </div>
    <div class="opui-sp-row-value" id="software-install-value"></div>
    <button type="button" class="opui-btn opui-btn--action" id="software-install-btn">${escapeHtml(t("INSTALL"))}</button>`;
  install.querySelector(".opui-sp-row-text")?.addEventListener("click", (e) => {
    const notes = document.getElementById("software-install-notes");
    if (!notes || !notes.innerHTML.trim()) return;
    const expanded = notes.dataset.expanded === "1";
    notes.dataset.expanded = expanded ? "0" : "1";
    notes.hidden = expanded;
    install.classList.toggle("opui-sp-row--desc-open", !expanded);
  });
  install.querySelector("#software-install-btn")?.addEventListener("click", async () => {
    const btn = install.querySelector("#software-install-btn");
    if (btn) btn.disabled = true;
    await runSoftwareInstallFlow();
    if (btn) btn.disabled = false;
  });
  body.appendChild(install);

  if (sw.branches?.length) {
    const branchRow = document.createElement("div");
    branchRow.className = "opui-sp-row opui-sp-row--has-action";
    branchRow.innerHTML = `
      <div class="opui-sp-row-text">
        <div class="opui-sp-row-title">${escapeHtml(t("Target Branch"))}</div>
      </div>
      <div class="opui-sp-row-value">${escapeHtml(sw.target_branch || t("N/A"))}</div>
      <button type="button" class="opui-btn opui-btn--action">${escapeHtml(t("SELECT"))}</button>`;
    branchRow.querySelector("button")?.addEventListener("click", async () => {
      const idx = Math.max(0, sw.branches.indexOf(sw.target_branch));
      const pick = await showMultiOption({
        title: t("Select a branch"),
        options: sw.branches,
        selected: idx,
        current: idx,
      });
      if (pick == null) return;
      const b = sw.branches[pick];
      const res = await apiPost("/api/opui/action/set_branch", { branch: b });
      if (res.ok) {
        toast(`${t("Target Branch")}: ${b}`);
        requestPanelRefresh();
      }
    });
    body.appendChild(branchRow);
  }

  appendPanelWidgets(body, data);
  await fetchWebUiUpdate({ fetchRemote: true });
  syncWebUiUpdateRow();

  applySoftwareCustom(sw);
  updateSoftwareExtras(globalState);
}

function formatBundleDisplay(raw) {
  if (raw == null || raw === "") return "—";
  if (typeof raw === "object") {
    return raw.displayName || raw.internalName || raw.ref || "—";
  }
  const s = String(raw);
  const display = s.match(/displayName['"]:\s*['"]([^'"]+)['"]/);
  if (display) return display[1];
  const internal = s.match(/internalName['"]:\s*['"]([^'"]+)['"]/);
  if (internal) return internal[1];
  return formatValue(s);
}

function formatValue(v) {
  if (v == null || v === "") return "—";
  const s = String(v);
  if (s.length > 200) return s.slice(0, 200) + "…";
  return s;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function createPanelBody(container, extraClass = "") {
  const body = document.createElement("div");
  body.className = `opui-panel-body${extraClass ? ` ${extraClass}` : ""}`;
  container.appendChild(body);
  return body;
}

function escapeAttr(s) {
  return escapeHtml(s).replace(/'/g, "&#39;");
}
