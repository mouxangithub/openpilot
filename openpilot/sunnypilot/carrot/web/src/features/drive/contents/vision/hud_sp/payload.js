"use strict";

/* sunnypilot HUD payload mapping.
 *
 * The webui (5080) renders its onroad HUD from the device state (state_api.py:
 * speed / set_speed / sp_hud / dm_arc / alert ...). This fork's Carrot Vision
 * gets the same cereal services through the compact websocket instead, so this
 * module derives the sunnypilot HUD fields from RAW_HUD_STATE. Live and replay
 * both feed the same RAW_HUD_STATE object, so the mapping is identical for the
 * two paths - matching the webui behaviour where one update function drives
 * every surface.
 */

function finite(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function bool(value) {
  return value === true;
}

/* m/s -> displayed unit (webui rounds to integers). */
function kphFromMs(value, isMetric) {
  const ms = finite(value);
  if (ms == null || ms <= 0) return null;
  const converted = ms * 3.6;
  return Math.round(isMetric ? converted : converted * 0.621371);
}

/* kph -> displayed unit (payload path carries pre-converted kph). */
function kphFromKph(value, isMetric) {
  const kphValue = finite(value);
  if (kphValue == null || kphValue <= 0) return null;
  return Math.round(isMetric ? kphValue : kphValue * 0.621371);
}

/* ui_status mirrors webui's derive_ui_status(): engaged / lat_only / long_only
 * / override / disengaged. compact selfdriveState carries enabled (openpilot
 * longitudinal engagement) while MADS-only lateral control surfaces as
 * carControl.latActive on the overlay channel. Without a selfdriveStateSP
 * sample the webui fallback returns "engaged" when enabled, so this mapping
 * does the same rather than downgrading to disengaged.
 */
function deriveUiStatus(state) {
  const controlsState = state.controlsState || {};
  const selfdriveState = state.selfdriveState || {};
  const carControl = state.carControl || {};
  const openpilotEnabled = bool(selfdriveState.enabled) || bool(controlsState.enabled);
  const hasCarControl = Boolean(carControl && (carControl.latActive != null || carControl.longActive != null));
  if (!hasCarControl) {
    // No control-actuation sample on the wire (replay or early boot): openpilot
    // enabled is the closest analogue of webui's engaged fallback.
    return openpilotEnabled ? "engaged" : "disengaged";
  }
  const longActive = bool(carControl.longActive);
  const latActive = bool(carControl.latActive);
  if (openpilotEnabled || (longActive && latActive)) return "engaged";
  if (longActive) return "long_only";
  if (latActive) return "lat_only";
  return "disengaged";
}

function deriveAlertSize(raw) {
  const size = String(raw || "none").toLowerCase();
  return size === "none" || size === "small" || size === "mid" || size === "full" ? size : "none";
}

function deriveAlertStatus(raw) {
  const status = String(raw || "normal").toLowerCase();
  if (status.includes("critical")) return "critical";
  if (status.includes("user")) return "user";
  return "normal";
}

/* Derive the full sunnypilot HUD payload from compact RAW_HUD_STATE.
 * Shared by the live socket and the recorded replay timeline. */
export function deriveSpHudPayload(state = {}, options = {}) {
  const carState = state.carState || {};
  const controlsState = state.controlsState || {};
  const selfdriveState = state.selfdriveState || {};
  const deviceState = state.deviceState || {};
  const carrotMan = state.carrotMan || {};
  const longitudinalPlan = state.longitudinalPlan || {};

  const isMetric = options.isMetric != null ? Boolean(options.isMetric) : true;
  const speedMs = finite(carState.vEgoCluster) ?? finite(carState.vEgo);
  const setMs = finite(carState.vCruiseCluster) ?? finite(controlsState.vCruiseCluster);
  const roadLimit = finite(carrotMan.nRoadLimitSpeed);
  const started = options.started != null
    ? Boolean(options.started)
    : bool(deviceState.started) || bool(selfdriveState.started);

  return {
    started,
    isMetric,
    unit: isMetric ? "km/h" : "mph",
    speed: speedMs != null && speedMs > 0 ? kphFromMs(speedMs, isMetric) : null,
    setSpeed: setMs != null && setMs > 0 ? kphFromMs(setMs, isMetric) : null,
    /* carrotMan.nRoadLimitSpeed is the road limit resolved by the navigation
     * stack; the webui SLA resolver lives in longitudinalPlanSP. Without that
     * service this is the closest sunnylimit source and is hidden when 0. */
    speedLimit: roadLimit != null && roadLimit > 0 && roadLimit < 250 ? Math.round(roadLimit) : null,
    speedLimitOver: bool(carrotMan.nRoadLimitSpeed) && speedMs != null && speedMs * 3.6 > roadLimit + 1,
    roadName: String(carrotMan.szPosRoadName || "").trim() || null,
    leftBlinker: bool(carState.leftBlinker),
    rightBlinker: bool(carState.rightBlinker),
    leftBlindspot: bool(carState.leftBlindspot),
    rightBlindspot: bool(carState.rightBlindspot),
    sccVisionActive: bool(longitudinalPlan.sccVisionActive),
    sccMapActive: bool(longitudinalPlan.sccMapActive),
    sccVisionEnabled: bool(longitudinalPlan.sccVisionEnabled) || bool(longitudinalPlan.sccVisionActive),
    sccMapEnabled: bool(longitudinalPlan.sccMapEnabled) || bool(longitudinalPlan.sccMapActive),
    longOverride: bool(longitudinalPlan.longOverride) || bool(carrotMan.desiredSpeed) && finite(carrotMan.desiredSpeed) > 0,
    rocketFuel: finite(carState.aEgo), // m/s²
    aEgo: finite(carState.aEgo),
    uiStatus: deriveUiStatus(state),
    alert: {
      text1: String(selfdriveState.alertText1 || "").trim(),
      text2: String(selfdriveState.alertText2 || "").trim(),
      size: deriveAlertSize(selfdriveState.alertSize),
      status: deriveAlertStatus(selfdriveState.alertStatus),
    },
    steerOutput: finite(controlsState.lateralOutput),
    experimental: bool(options.experimental),
  };
}

/* Compact payload normalization for the sp HUD - the vision_raw classic path
 * builds a compact payload (vEgoKph / vSetKph / aEgo ...) that is merged with
 * RAW_HUD_STATE here, so the same overlay consumes either source. */
export function mapSpHudPayload(payload = {}, state = {}) {
  const derived = deriveSpHudPayload(state, {
    isMetric: payload.isMetric,
    started: payload.started ?? payload.vEgo != null,
    experimental: payload.experimental,
  });
  const isMetric = payload.isMetric !== false;
  return {
    ...derived,
    /* payload.vEgo is m/s (raw compact), vSetKph / speedLimitKph are already
     * kph integers computed by vision_raw.js; the derived raw-state path
     * always wins and these are fallbacks for an empty raw state. */
    speed: derived.speed ?? kphFromMs(payload.vEgo ?? payload.vEgoKph, isMetric),
    setSpeed: derived.setSpeed ?? kphFromKph(payload.vSetKph ?? payload.setSpeed, isMetric),
    speedLimit: derived.speedLimit ?? kphFromKph(payload.speedLimitKph, isMetric),
    roadName: derived.roadName || String(payload.roadName || "").trim() || null,
    rocketFuel: derived.rocketFuel ?? finite(payload.aEgo ?? payload.accel),
    steerOutput: derived.steerOutput ?? finite(payload.steerOutput),
    leftBlinker: derived.leftBlinker || bool(payload.leftBlinker),
    rightBlinker: derived.rightBlinker || bool(payload.rightBlinker),
    leftBlindspot: derived.leftBlindspot || bool(payload.leftBlindspot),
    rightBlindspot: derived.rightBlindspot || bool(payload.rightBlindspot),
    // compact path carries alert fields on selfdriveState via RAW_HUD_STATE;
    // the derived merge already prefers raw state, keep payload alert fallback.
    alert: payload.alert && typeof payload.alert === "object" && payload.alert.text1
      ? payload.alert
      : derived.alert,
  };
}

export const SpHudPayload = Object.freeze({
  derive: deriveSpHudPayload,
  map: mapSpHudPayload,
});
