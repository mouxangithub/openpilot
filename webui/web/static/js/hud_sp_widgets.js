/**
 * StarPilot-era onroad widgets for the web HUD:
 *   - CEM badge (CEStatus: 0 off, 1 curves, 2 lead, 3 signal, 4 manual)
 *   - traffic-signal ring (signalAssistAction evidence: 1 red, 2 green, 3 mixed)
 *   - red-light stopping-point marker + optional distance metrics
 *   - per-source speed-limit drawer (dashboard / map / vision)
 *   - onroad personality quick-switch button (cycles LongitudinalPersonality)
 *
 * Mirrors the BIG UI renderers in selfdrive/ui/sunnypilot/onroad/
 * (stopping_point.py, signal_hud.py, personality_button.py), adapted to the
 * web UI's DOM overlay on the road stream.
 */

import { apiPut } from "./api.js";

const $ = (id) => document.getElementById(id);

async function putParam(key, value) {
  return apiPut(`/api/opui/params/${encodeURIComponent(key)}`, { value });
}

const CE_LABELS = { 1: "CEM·C", 2: "CEM·L", 3: "CEM·S", 4: "CEM·M" };

// cereal LongitudinalPersonality: aggressive @1, standard @2, relaxed @3
const PERSONALITY_VALUE = { aggressive: 1, standard: 2, relaxed: 3 };
const PERSONALITY_LABEL = { aggressive: "AGGR", standard: "STD", relaxed: "RELAX" };

const SOURCE_ROWS = [
  ["speed_limit_dashboard", "speed_limit_dashboard_valid", "DASH"],
  ["speed_limit_map", "speed_limit_map_valid", "MAP"],
  ["speed_limit_vision", "speed_limit_vision_valid", "VIS"],
];

let personalityBound = false;

function ensureBound() {
  if (personalityBound) return;
  personalityBound = true;
  $("hud-personality")?.addEventListener("click", async () => {
    const btn = $("hud-personality");
    const current = btn?.dataset.personality || "standard";
    const order = ["aggressive", "standard", "relaxed"];
    const next = order[(order.indexOf(current) + 1) % order.length];
    const res = await putParam("LongitudinalPersonality", String(PERSONALITY_VALUE[next]));
    if (!res.ok) return;
    btn.dataset.personality = next;
    $("hud-personality-label").textContent = PERSONALITY_LABEL[next];
  });
}

export function updateSpWidgets(st) {
  ensureBound();
  const hud = document.getElementById("hud");
  if (!hud || !st?.ok || !st.started) {
    hideAll();
    return;
  }

  updateCeBadge(st);
  updateSignalRing(st);
  updateStopSign(st);
  updateSlSources(st);
  updatePersonalityButton(st);
}

function hideAll() {
  for (const id of ["hud-ce-badge", "hud-signal-ring", "hud-stop-sign", "hud-sl-sources", "hud-personality"]) {
    const el = $(id);
    if (el) el.hidden = true;
  }
}

function updateCeBadge(st) {
  const el = $("hud-ce-badge");
  if (!el) return;
  const ce = Number(st.sp_hud?.ce_status) || 0;
  const show = Boolean(st.conditional_experimental) && ce > 0;
  el.hidden = !show;
  if (!show) return;
  el.dataset.ce = String(ce);
  el.textContent = CE_LABELS[ce] || "CEM";
}

function updateSignalRing(st) {
  const el = $("hud-signal-ring");
  if (!el) return;
  const action = Number(st.sp_hud?.signal_assist_action) || 0;
  el.hidden = action === 0;
  if (action === 0) return;
  el.dataset.signal = String(action);
}

function updateStopSign(st) {
  const el = $("hud-stop-sign");
  if (!el) return;
  const show = Boolean(st.show_stopping_point)
    && Number(st.sp_hud?.signal_assist_action) === 1
    && !st.standstill;
  el.hidden = !show;
  if (!show) return;

  // Approximate remaining stop distance (stopping_point.py): v^2/(2*decel),
  // comfortable decel 0.6 m/s^2 when not braking yet, 0 at standstill.
  const speedMs = Number(st.speed) > 0
    ? Number(st.speed) / (st.is_metric ? 3.6 : 2.23694)
    : 0;
  const decel = Math.max(0.6, -Number(st.a_ego ?? 0));
  const distance = speedMs > 0 ? (speedMs * speedMs) / (2 * decel) : 0;

  const distEl = $("hud-stop-distance");
  const showMetrics = Boolean(st.show_stopping_point_metrics);
  distEl.hidden = !showMetrics;
  if (showMetrics) {
    distEl.textContent = st.is_metric
      ? `${Math.round(distance)} m`
      : `${Math.round(distance * 3.28084)} ft`;
  }

  // Height above the bottom edge grows with distance (STOP_DISTANCE_MAX_M = 120,
  // fraction 0.08..0.55, matching stopping_point.py).
  const fraction = 0.08 + 0.47 * Math.min(1, distance / 120);
  el.style.bottom = `${(fraction * 100).toFixed(1)}%`;
}

function updateSlSources(st) {
  const el = $("hud-sl-sources");
  if (!el) return;
  const show = Boolean(st.show_speed_limit_sources)
    && Number(st.speed_limit_mode) > 0
    && st.sp_hud != null;
  el.hidden = !show;
  if (!show) return;

  // Per-source values are pre-converted to display units by state_api.
  const rows = SOURCE_ROWS.map(([valKey, validKey, label]) => {
    const value = st.sp_hud[valKey];
    const valid = Boolean(st.sp_hud[validKey]);
    const text = Number(value) > 0 ? `${Math.round(value)}` : "–";
    return `<div class="opui-sl-source${valid ? "" : " is-invalid"}">
      <span class="opui-sl-source-name">${label}</span><span>${text}</span></div>`;
  });
  el.innerHTML = rows.join("");
}

function updatePersonalityButton(st) {
  const el = $("hud-personality");
  if (!el) return;
  const show = Boolean(st.show_personality_button);
  el.hidden = !show;
  if (!show) return;
  const personality = PERSONALITY_LABEL[st.personality] ? st.personality : "standard";
  el.dataset.personality = personality;
  $("hud-personality-label").textContent = PERSONALITY_LABEL[personality];
}
