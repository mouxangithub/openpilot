import assert from "node:assert/strict";
import test from "node:test";

import {
  deriveSpHudPayload,
  mapSpHudPayload,
  SpHudPayload,
} from "../src/features/drive/contents/vision/hud_sp/payload.js";
import { CSS } from "../src/features/drive/contents/vision/hud_sp/style.js";

function compactState() {
  return {
    carState: {
      vEgoCluster: 20.0, // 72 km/h
      vCruiseCluster: 30.0, // 108 km/h
      aEgo: 0.5,
      leftBlinker: true,
      rightBlinker: false,
      leftBlindspot: false,
      rightBlindspot: true,
    },
    controlsState: { enabled: true, lateralOutput: 0.25 },
    selfdriveState: {
      enabled: true,
      alertStatus: "normal",
      alertSize: "none",
      alertText1: "",
      alertText2: "",
    },
    carrotMan: {
      nRoadLimitSpeed: 80,
      szPosRoadName: "Gyeongbu Expressway",
    },
    longitudinalPlan: {
      sccVisionActive: true,
      sccMapActive: false,
      longOverride: false,
    },
  };
}

test("deriveSpHudPayload maps m/s carState to display units", () => {
  const data = deriveSpHudPayload(compactState(), { isMetric: true, started: true });
  assert.equal(data.speed, 72);
  assert.equal(data.setSpeed, 108);
  assert.equal(data.speedLimit, 80);
  assert.equal(data.unit, "km/h");
  assert.equal(data.roadName, "Gyeongbu Expressway");
  assert.equal(data.leftBlinker, true);
  assert.equal(data.rightBlindspot, true);
  assert.equal(data.rocketFuel, 0.5);
  assert.equal(data.steerOutput, 0.25);
  assert.equal(data.uiStatus, "engaged");
  assert.equal(data.sccVisionActive, true);
});

test("deriveSpHudPayload converts to mph when imperial", () => {
  const data = deriveSpHudPayload(compactState(), { isMetric: false, started: true });
  assert.equal(data.unit, "mph");
  assert.equal(data.speed, Math.round(72 * 0.621371));
  assert.equal(data.setSpeed, Math.round(108 * 0.621371));
});

test("deriveSpHudPayload derives ui_status from control activation", () => {
  const state = compactState();
  state.selfdriveState.enabled = false;
  state.controlsState.enabled = false;
  assert.equal(deriveSpHudPayload(state, { started: true }).uiStatus, "disengaged");

  const latOnly = compactState();
  latOnly.selfdriveState.enabled = false;
  latOnly.controlsState.enabled = false;
  latOnly.carControl = { latActive: true, longActive: false };
  assert.equal(deriveSpHudPayload(latOnly, { started: true }).uiStatus, "lat_only");

  const longOnly = compactState();
  longOnly.selfdriveState.enabled = false;
  longOnly.controlsState.enabled = false;
  longOnly.carControl = { latActive: false, longActive: true };
  assert.equal(deriveSpHudPayload(longOnly, { started: true }).uiStatus, "long_only");

  const madsOnly = compactState();
  madsOnly.selfdriveState.enabled = false;
  madsOnly.controlsState.enabled = false;
  madsOnly.carControl = { latActive: true, longActive: false };
  assert.equal(deriveSpHudPayload(madsOnly, { started: true }).uiStatus, "lat_only");
});

test("deriveSpHudPayload hides invalid limit and empty road name", () => {
  const state = compactState();
  state.carrotMan.nRoadLimitSpeed = 0;
  state.carrotMan.szPosRoadName = "   ";
  const data = deriveSpHudPayload(state, { started: true });
  assert.equal(data.speedLimit, null);
  assert.equal(data.roadName, null);
});

test("mapSpHudPayload merges a compact payload path over raw state", () => {
  // compact payload from vision_raw carries m/s vEgo plus pre-computed kph
  // fields, but the raw compact state is the authority (same frame, fresher
  // than a derived snapshot), so raw values win for every field it provides.
  const compact = {
    isMetric: true,
    vEgo: 24.444, // 88 km/h (ignored in favour of raw)
    vSetKph: 100,
    speedLimitKph: 100,
    aEgo: -1.2,
    steerOutput: -0.5,
    roadName: "Local Road",
  };
  const data = mapSpHudPayload(compact, compactState());
  assert.equal(data.speed, 72); // raw vEgoCluster 20 m/s
  assert.equal(data.setSpeed, 108); // raw vCruiseCluster 30 m/s
  assert.equal(data.speedLimit, 80); // raw nRoadLimitSpeed wins over payload
  assert.equal(data.roadName, "Gyeongbu Expressway"); // raw wins
  assert.equal(data.rocketFuel, 0.5); // raw aEgo wins
});

test("mapSpHudPayload falls back to payload when raw state is empty", () => {
  // payload.vEgo is m/s (raw compact), vSetKph/speedLimitKph are kph.
  const data = mapSpHudPayload(
    { isMetric: false, vEgo: 16.667, vSetKph: 80, speedLimitKph: 50, aEgo: 0.8, leftBlinker: true },
    {},
  );
  assert.equal(data.speed, Math.round(60 * 0.621371)); // 16.667 m/s = 60 km/h
  assert.equal(data.setSpeed, Math.round(80 * 0.621371));
  assert.equal(data.speedLimit, Math.round(50 * 0.621371));
  assert.equal(data.leftBlinker, true);
});

test("SpHudPayload facade exposes both entry points", () => {
  assert.equal(typeof SpHudPayload.derive, "function");
  assert.equal(typeof SpHudPayload.map, "function");
});

test("sp hud style ships the sunnypilot HUD look", () => {
  for (const token of [
    ".sp-hud-speed-block",
    ".sp-hud-speed",
    ".sp-hud-unit",
    ".sp-hud-cruise",
    ".sp-hud-sla",
    ".sp-hud-road",
    ".sp-hud-blinker",
    ".sp-hud-bsl",
    ".sp-hud-scc",
    ".sp-hud-rocket",
    ".sp-hud-exp",
  ]) {
    assert.ok(CSS.includes(token), `style.js must include ${token}`);
  }
});
