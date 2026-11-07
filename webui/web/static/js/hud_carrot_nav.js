/**
 * Carrot navigation HUD (glass card redesign).
 *
 * One compact semi-transparent "glass" card fed by state.sp_hud.carrot_nav:
 *   - head row: turn mini-icon (+ATC tint) | TBT main text + ETA/destination | dist + countdown
 *   - badge row: road/SDI, desired speed, speed camera, traffic light, curve advisory
 *
 * Duplicates are intentionally dropped: the speed limit circle and road-name
 * chip already live in the top HUD next to the cluster speed, so the card no
 * longer renders its own LIMIT box / big road row — this keeps the card slim
 * (560px) and far from the speed area. Opaque blue panel styling is gone;
 * panel_opacity (CarrotPanelOpacity param) still scales the whole card.
 *
 * Also keeps the left/right AmapLaneIndicators edge bars (state.sp_hud.amap_lines).
 */

import { tr } from "./i18n.js?v=3";
import { apiGet } from "./api.js";

const ASSET_BASE = "/api/opui/assets/sunnypilot/selfdrive/assets/images";
const TURN_ICONS = {
  1: `${ASSET_BASE}/turn_l.png`,
  2: `${ASSET_BASE}/turn_r.png`,
  3: `${ASSET_BASE}/lane_change_l.png`,
  4: `${ASSET_BASE}/lane_change_r.png`,
  7: `${ASSET_BASE}/turn_u.png`,
};
const TURN_FALLBACK = (t) => (t === 6 ? "TG" : t === 8 ? tr("Destination") : `${tr("Slow down")}:${t}`);
const ROAD_CATE = {
  1: () => tr("Highway"),
  2: () => tr("City Expressway"),
  3: () => tr("National Road"),
  4: () => tr("Provincial Road"),
  5: () => tr("County Road"),
  6: () => tr("Town Road"),
};
const CAMERA_TYPES = {
  2: () => tr("Average Speed Camera"),
  4: () => tr("Average Speed Camera"),
  22: () => tr("Speed Bump"),
  100: () => tr("Mobile Speed Camera"),
};
const TRAFFIC = {
  1: { c: "#ff5a5a", t: () => tr("Red light") },
  2: { c: "#4ade80", t: () => tr("Green light") },
  3: { c: "#34d399", t: () => tr("Left-turn green") },
};
// TMC congestion colouring (App §2.5): very-free -> free -> slow -> congested
// -> severe -> unknown/current. 0 and 10 are "no data"/"current position".
const TMC_COLORS = {
  5: "#15803d",
  1: "#4ade80",
  2: "#f59e0b",
  3: "#ef4444",
  4: "#991b1b",
  0: "#6b7280",
  10: "#6b7280",
};
const TMC_LABELS = {
  5: () => tr("Very free"),
  1: () => tr("Free"),
  2: () => tr("Slow"),
  3: () => tr("Congested"),
  4: () => tr("Severe"),
  0: () => tr("No data"),
  10: () => tr("Current"),
};
const SAPA_TYPES = {
  0: () => tr("Service area"),
  1: () => tr("Toll gate"),
  2: () => tr("Checkpoint"),
};

let lastNavSig = "";
let styleInjected = false;
let crossroadTimer = null;
let lastCrossroadSig = "";
let pendingCrossroadFetch = null;
let mediaTimer = null;
let lastMediaSig = "";
let pendingMediaFetch = null;

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

function injectStyle() {
  if (styleInjected) return;
  styleInjected = true;
  const style = document.createElement("style");
  style.id = "opui-hud-carrot-style";
  style.textContent = `
.opui-hud-carrot {
  position: absolute; bottom: 280px; left: 50%; transform: translateX(-50%);
  width: 560px; max-width: calc(100% - 20px); box-sizing: border-box;
  padding: 12px 16px 12px 14px;
  background: rgba(10, 16, 24, 0.55);
  -webkit-backdrop-filter: blur(16px); backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 20px;
  box-shadow: 0 6px 28px rgba(0, 0, 0, 0.30);
  color: #fff; font-family: Inter, sans-serif;
  z-index: 5; transition: opacity 0.15s linear;
}
/* The card is horizontally centered and raised above the steering torque
   arc band (bottom 180px), so it never overlaps the arc or the speed block. */

/* head row: turn mini-icon | headline | meta */
.cn-head { display: flex; align-items: center; gap: 14px; min-height: 60px; }
.cn-turn-mini {
  position: relative; flex: 0 0 60px; width: 60px; height: 60px;
  border-radius: 14px; background: rgba(22, 200, 122, 0.28);
  display: flex; align-items: center; justify-content: center;
  box-sizing: border-box; overflow: hidden;
}
.cn-turn-mini.cn-atc { background: rgba(22, 200, 122, 0.85); }
.cn-turn-mini.cn-atc-prepare { background: rgba(22, 200, 122, 0.35); }
.cn-turn-icon { width: 46px; height: 46px; object-fit: contain; }
.cn-turn-fallback { font-size: 17px; font-weight: 700; text-align: center; line-height: 1.15; padding: 0 4px; }
.cn-headline { flex: 1 1 auto; min-width: 0; }
.cn-tbt { font-size: 29px; font-weight: 700; line-height: 1.2; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cn-sub { font-size: 20px; font-weight: 500; color: rgba(255, 255, 255, 0.72); margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cn-turnmeta { flex: 0 0 auto; text-align: right; }
.cn-tdist { font-size: 29px; font-weight: 700; line-height: 1.1; }
.cn-tcd { font-size: 19px; font-weight: 700; color: #ffdc64; margin-top: 3px; min-height: 22px; }

/* Fused guidance from navInstructionCarrotSP: the multi-step manoeuvre chain and the
   per-lane arrows. Sizes follow the card's existing scale (29 headline / 20 sub /
   19 badge) so the three rows stay visually consistent. */
.cn-maneuvers { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
.cn-mv { display: inline-flex; align-items: center; gap: 5px; font-size: 19px; font-weight: 700;
         color: rgba(255, 255, 255, 0.86); }
.cn-mv i { width: 26px; height: 26px; border-radius: 6px; display: inline-flex;
           align-items: center; justify-content: center; background: rgba(255, 255, 255, 0.13);
           font-size: 16px; font-style: normal; }
.cn-mv.cn-mv--then { color: rgba(255, 255, 255, 0.62); }
.cn-lanes { display: flex; align-items: flex-end; gap: 6px; margin-top: 9px; }
.cn-lane { display: flex; flex-direction: column; align-items: center; gap: 3px;
           font-size: 17px; font-weight: 700; color: rgba(255, 255, 255, 0.45);
           padding: 4px 7px; border-radius: 7px; background: rgba(255, 255, 255, 0.07); }
.cn-lane.cn-lane--active { color: #fff; background: rgba(56, 132, 255, 0.42); }
.cn-typical { font-size: 17px; font-weight: 600; color: rgba(255, 255, 255, 0.62); }

/* badge row */
.cn-badges { display: flex; align-items: center; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
.cn-badge {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 19px; font-weight: 700; line-height: 1;
  padding: 6px 12px; border-radius: 999px;
  background: rgba(255, 255, 255, 0.13); color: rgba(255, 255, 255, 0.92);
  white-space: nowrap;
}
.cn-badge .cn-cate { font-size: 17px; padding: 2px 7px; border-radius: 7px; background: rgba(255, 255, 255, 0.18); }
.cn-badge .cn-cate.cn-cate-1 { background: rgba(22, 160, 74, 0.85); }
.cn-badge .cn-cate.cn-cate-2 { background: rgba(217, 145, 10, 0.85); }
.cn-badge.cn-badge--sdi { background: rgba(22, 160, 74, 0.8); color: #fff; }
/* Projected road limit from the phone app. Solid when the resolver adopted it, outlined
   when it did not - so "the app says 50" and "the car is using 50" are distinguishable.
   The top speed HUD shows the resolver's merged value, which is a different thing: when
   the limit is not adopted there is nothing up there, which is exactly when this badge
   matters most. */
.cn-badge.cn-badge--limit { background: rgba(255, 255, 255, 0.95); color: #101418; font-weight: 800; }
.cn-badge.cn-badge--limit.is-unused {
  background: rgba(255, 255, 255, 0.10); color: rgba(255, 255, 255, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.45); font-weight: 700;
}
.cn-badge.cn-badge--limit .cn-limit-src { font-size: 15px; font-weight: 600; opacity: 0.65; margin-left: 4px; }
/* Above the projected limit. The filled variant has a light background, the outlined one
   is dark, so each needs its own red. */
.cn-badge.cn-badge--limit.is-over { color: #c81e1e; }
.cn-badge.cn-badge--limit.is-unused.is-over { color: #ff8a8a; border-color: rgba(255, 138, 138, 0.7); }
.cn-badge.cn-badge--apply { background: rgba(255, 180, 50, 0.88); color: #101418; }
.cn-badge.cn-badge--cam { background: rgba(239, 68, 68, 0.82); color: #fff; }
.cn-badge.cn-badge--cam.is-ok { background: rgba(239, 68, 68, 0.35); }
.cn-badge.cn-badge--scc-curve { background: rgba(56, 132, 255, 0.30); color: #cfe0ff; border: 1px solid rgba(120, 170, 255, 0.5); }
.cn-badge.cn-badge--vturn { background: rgba(255, 200, 50, 0.18); color: #ffc832; border: 1px solid rgba(255, 200, 50, 0.45); }
.cn-badge.cn-tlight { background: rgba(255, 255, 255, 0.10); }
.cn-badge.cn-tlight i { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
.cn-badge.cn-badge--sapa { background: rgba(56, 132, 255, 0.22); color: #bcd8ff; border: 1px solid rgba(56, 132, 255, 0.45); }
.cn-badge.cn-badge--tmc { background: rgba(255, 255, 255, 0.10); }
.cn-badge .cn-tmc-bar { display: inline-flex; width: 90px; height: 12px; border-radius: 3px; overflow: hidden; }
.cn-badge .cn-tmc-bar i { display: block; height: 100%; }

/* amap lane edge bars (unchanged behavior) */
.opui-amapbar {
  position: absolute; top: 55%; transform: translateY(-50%);
  width: 8px; height: 120px; border-radius: 4px;
  background: #66ff99; opacity: 1; transition: opacity 0.15s linear, background 0.15s linear;
  z-index: 5;
}
.opui-amapbar--l { left: 12px; }
.opui-amapbar--r { right: 12px; }
.opui-amapbar.is-blocked { background: #ff6633; }

/* complex crossroad overlay: small picture-in-picture above the nav card */
.opui-carrot-crossroad {
  position: absolute; bottom: 100%; left: 50%; transform: translateX(-50%);
  margin-bottom: 12px;
  width: 220px; max-width: calc(100vw - 40px);
  background: rgba(10, 16, 24, 0.72);
  -webkit-backdrop-filter: blur(14px); backdrop-filter: blur(14px);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 16px;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35);
  overflow: hidden; z-index: 6;
  transition: opacity 0.18s linear;
}
.opui-carrot-crossroad img {
  display: block; width: 100%; height: auto; object-fit: contain;
  background: rgba(0, 0, 0, 0.25);
}
.opui-carrot-crossroad .opui-carrot-crossroad-meta {
  padding: 7px 10px; font-size: 16px; font-weight: 600; color: #fff;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  text-align: center;
}
.opui-carrot-crossroad .opui-carrot-crossroad-progress {
  position: absolute; left: 0; bottom: 0; height: 3px;
  background: rgba(22, 200, 122, 0.85); transition: width 0.2s linear;
}

/* carrot media overlays (tbt / lane / traffic_signal / center) */
.opui-carrot-media {
  position: absolute; bottom: 100%; left: 50%; transform: translateX(-50%);
  margin-bottom: 12px;
  display: flex; flex-direction: row; gap: 10px; align-items: flex-end;
  justify-content: center; z-index: 6; pointer-events: none;
  max-width: calc(100vw - 40px);
}
.opui-carrot-media-frame {
  position: relative;
  background: rgba(10, 16, 24, 0.72);
  -webkit-backdrop-filter: blur(14px); backdrop-filter: blur(14px);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 14px;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35);
  overflow: hidden; pointer-events: auto;
  min-width: 64px; max-width: 180px;
  transition: opacity 0.18s linear;
}
.opui-carrot-media-frame img {
  display: block; width: 100%; height: auto; object-fit: contain;
  background: rgba(0, 0, 0, 0.25);
}
.opui-carrot-media-frame .opui-carrot-media-label {
  padding: 5px 8px; font-size: 14px; font-weight: 600; color: #fff;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center;
  background: rgba(0, 0, 0, 0.35);
}

/* road-lite mode: the synthesized canvas already draws TBT / traffic light /
   curve advisory — hide the DOM nav card and edge bars for a clean scene.
   (road_lite.js toggles road-lite-on on both #camera-wrap and #hud; #hud is
   the parent of the nav card, the wrap is only its sibling.) */
#hud.road-lite-on #hud-carrot-nav,
#hud.road-lite-on .opui-amapbar,
#hud.road-lite-on .opui-carrot-crossroad,
#hud.road-lite-on .opui-carrot-media { display: none !important; }
`;
  document.head.appendChild(style);
}

function fmtDist(meters, isMetric) {
  if (isMetric) {
    return meters < 1000 ? `${meters} m` : `${(meters / 1000).toFixed(1)} km`;
  }
  const ft = meters * 3.28084;
  return ft < 1609 ? `${Math.round(ft)} ft` : `${(meters / 1609.344).toFixed(1)} mi`;
}

function etaString(seconds) {
  const minutes = seconds / 60;
  const now = new Date();
  const total = now.getHours() * 60 + now.getMinutes() + Math.round(minutes);
  const hh = String(Math.floor(total / 60) % 24).padStart(2, "0");
  const mm = String(total % 60).padStart(2, "0");
  return minutes >= 60
    ? `${tr("ETA")} ${Math.floor(minutes / 60)}h${Math.round(minutes % 60)}m · ${hh}:${mm}`
    : `${tr("ETA")} ${Math.round(minutes)}min · ${hh}:${mm}`;
}

function hasNavContent(nav) {
  return !!(nav
    && ((nav.go_pos_dist > 0 && nav.go_pos_time > 0)
      || nav.goal_name || nav.turn_info > 0
      || (nav.spd_limit > 0 && nav.spd_dist > 0)
      || nav.traffic_state > 0 || nav.road_name || nav.sdi_descr || nav.tbt_main_text));
}

function turnMiniHtml(nav) {
  const t = nav.turn_info;
  const atc = nav.atc_type ? (nav.atc_type.includes("prepare")
    ? "cn-atc cn-atc-prepare" : "cn-atc") : "";
  let inner;
  if (TURN_ICONS[t]) {
    inner = `<img class="cn-turn-icon" src="${TURN_ICONS[t]}" alt="" onerror="this.outerHTML='<div class=&quot;cn-turn-fallback&quot;>${esc(TURN_FALLBACK(t))}</div>'">`;
  } else {
    inner = `<div class="cn-turn-fallback">${esc(TURN_FALLBACK(t))}</div>`;
  }
  return `<div class="cn-turn-mini ${atc}">${inner}</div>`;
}

function badgesHtml(nav, speedKph, spHud) {
  const badges = [];

  // Projected road limit from the phone app (carrotManSP.nRoadLimitSpeed).
  //
  // This badge exists because the "glass navigation card" redesign removed the old
  // LIMIT box on the grounds that the top speed HUD already shows the limit. That
  // reasoning does not hold when the two disagree: the top HUD shows the RESOLVER's
  // merged value (speed_limit_resolver / speed_limit_source), while this is what the
  // phone actually projected. If the resolver did not adopt it - wrong policy for the
  // active source, a stale packet, an inactive packet - the top HUD shows nothing and
  // the projected limit became invisible everywhere.
  //
  // So: always shown when carrot projects one, and styled as outlined when the resolver
  // is not currently using it. Filled = in effect, outlined = the app says so but the
  // car is not acting on it.
  const roadLimit = Number(nav.road_limit_speed) || 0;
  if (roadLimit > 0) {
    // "adopted" needs both halves: the resolver picked the map source AND landed on
    // this same number. Either alone can be true while the car uses something else.
    const resolved = Number(spHud?.speed_limit_resolver) || 0;
    const adopted = spHud?.speed_limit_source === "map" && Math.round(resolved) === Math.round(roadLimit);
    const over = Math.round(speedKph) > roadLimit;
    const cls = (adopted ? "" : " is-unused") + (over ? " is-over" : "");
    const src = adopted ? "" : `<span class="cn-limit-src">${esc(tr("Projected"))}</span>`;
    badges.push(`<span class="cn-badge cn-badge--limit${cls}">${roadLimit}${src}</span>`);
  }
  if (nav.sdi_descr) {
    badges.push(`<span class="cn-badge cn-badge--sdi">${esc(nav.sdi_descr)}</span>`);
  } else if (nav.road_name) {
    const cate = ROAD_CATE[nav.road_cate]
      ? `<b class="cn-cate cn-cate-${nav.road_cate}">${ROAD_CATE[nav.road_cate]()}</b>` : "";
    badges.push(`<span class="cn-badge">${cate}${esc(nav.road_name)}</span>`);
  }
  if (nav.desired_speed > 0 && (nav.desired_source_label || nav.desired_source)) {
    // Prefer the resolved reason + colour from carrot_man; fall back to the raw
    // token so an older packet still renders something rather than nothing.
    const label = nav.desired_source_label || esc(nav.desired_source).slice(0, 10);
    const mode = Number(nav.desired_source_color) || 0;
    const cls = mode === 3 ? " is-vnavi" : mode === 4 ? " is-extnavi" : "";
    badges.push(`<span class="cn-badge cn-badge--apply${cls}">${esc(label)} ${nav.desired_speed}</span>`);
  }
  if (nav.spd_limit > 0 && nav.spd_dist > 0) {
    const over = Math.round(speedKph) > nav.spd_limit;
    const type = CAMERA_TYPES[nav.spd_type] ? CAMERA_TYPES[nav.spd_type]() : tr("Camera");
    badges.push(`<span class="cn-badge cn-badge--cam${over ? "" : " is-ok"}">◉ ${nav.spd_limit} · ${esc(fmtDist(nav.spd_dist, true))}${nav.spd_countdown > 0 ? ` ${nav.spd_countdown}s` : ""}<i style="font-style:normal;font-weight:500;opacity:.8">${esc(type)}</i></span>`);
  }
  if (nav.traffic_state > 0) {
    const info = TRAFFIC[nav.traffic_state] || { c: "#ffd644", t: () => tr("Traffic light") };
    const cd = nav.traffic_countdown > 0 ? nav.traffic_countdown : nav.left_sec;
    badges.push(`<span class="cn-badge cn-tlight"><i style="background:${info.c}"></i><span style="color:${info.c}">${info.t()}</span>${cd > 0 ? `${cd}s` : ""}</span>`);
  }
  // Curve deceleration. Two distinct numbers exist and they must not be conflated:
  //
  //   * nav.v_turn_speed is carrot's own advisory, computed in
  //     carrot_functions.vturn_speed() from the max model orientation rate against a
  //     fixed 1.9 m/s^2 target. It is DISPLAY-ONLY - it feeds `desiredSpeed`, which
  //     nothing acts on.
  //   * scc_vision_v_target_ms / scc_map_v_target_ms is what the controllers that
  //     actually slow the car are commanding right now (m/s), read from
  //     longitudinalPlanSP.smartCruiseControl.
  //
  // They use different models and will not agree. Showing the executing one first, and
  // marking carrot's as an advisory, is the honest presentation - previously only the
  // advisory was drawn, so the HUD could claim a curve speed the car was not using.
  const sccMs = Math.max(Number(spHud?.scc_vision_v_target_ms) || 0,
                         Number(spHud?.scc_map_v_target_ms) || 0);
  if (sccMs > 0) {
    const kph = isMetric ? sccMs * 3.6 : sccMs * 2.23694;
    badges.push(`<span class="cn-badge cn-badge--scc-curve">${tr("Curve")} ${Math.round(kph)}km/h</span>`);
  }
  if (nav.v_turn_speed > 0 && nav.v_turn_speed < 120) {
    badges.push(`<span class="cn-badge cn-badge--vturn">${tr("Advisory")} ${nav.v_turn_speed}km/h</span>`);
  }
  if (nav.sapa_name && nav.sapa_dist > 0) {
    const kind = SAPA_TYPES[nav.sapa_type] ? SAPA_TYPES[nav.sapa_type]() : tr("Service area");
    badges.push(`<span class="cn-badge cn-badge--sapa">P ${esc(kind)} · ${esc(fmtDist(nav.sapa_dist, true))} · ${esc(nav.sapa_name)}</span>`);
  }
  const tmc = tmcBarHtml(nav);
  if (tmc) badges.push(tmc);
  return badges.length ? `<div class="cn-badges">${badges.join("")}</div>` : "";
}

/**
 * Congestion bar from the App §2.5 TMC arrays. Segment widths are proportional
 * to tmc_segment_distances; colours come from TMC_COLORS. Renders nothing when
 * the arrays are absent or unparseable, so the card is unchanged without data.
 */
function tmcBarHtml(nav) {
  const statuses = parseJsonIntArray(nav.tmc_segment_statuses);
  if (!statuses.length) return "";
  const distances = parseJsonIntArray(nav.tmc_segment_distances);

  const cells = statuses.map((status, i) => {
    const dist = i < distances.length ? Math.max(0, distances[i]) : 0;
    const colour = TMC_COLORS[status] || TMC_COLORS[0];
    const label = TMC_LABELS[status] ? TMC_LABELS[status]() : tr("No data");
    // flex-grow carries the proportional width; a minimum keeps tiny segments visible.
    return `<i style="flex:${dist > 0 ? dist : 1} 1 0;background:${colour}" title="${esc(label)}"></i>`;
  }).join("");

  const overall = Number(nav.tmc_overall_status) || 0;
  const overallLabel = TMC_LABELS[overall] ? TMC_LABELS[overall]() : "";
  const residual = nav.tmc_residual_distance > 0 ? ` · ${esc(fmtDist(nav.tmc_residual_distance, true))}` : "";
  return `<span class="cn-badge cn-badge--tmc"><b class="cn-tmc-bar">${cells}</b>${overallLabel ? esc(overallLabel) : ""}${residual}</span>`;
}

function parseJsonIntArray(raw) {
  if (raw === null || raw === undefined) return [];
  let value = raw;
  if (typeof value === "string") {
    const text = value.trim();
    if (!text) return [];
    try {
      value = JSON.parse(text);
    } catch {
      return [];
    }
  }
  if (!Array.isArray(value)) return [];
  return value.map((v) => {
    const n = Number(v);
    return Number.isFinite(n) ? n : 0;
  });
}

// (type, modifier) -> a compact glyph, mirroring the backend NAV_TYPE_MAPPING intent.
// Kept deliberately small: this is a glanceable HUD, not a routing display.
const MV_GLYPH = {
  "turn|left": "\u2190", "turn|right": "\u2192",
  "turn|sharp left": "\u21B0", "turn|sharp right": "\u21B1",
  "turn|slight left": "\u2196", "turn|slight right": "\u2197",
  "turn|uturn": "\u21BA",
  "fork|slight left": "\u2196", "fork|slight right": "\u2197",
  "fork|left": "\u2196", "fork|right": "\u2197",
  "off ramp|left": "\u2196", "off ramp|right": "\u2197",
  "merge|left": "\u2196", "merge|right": "\u2197",
  "continue|straight": "\u2191", "new name|straight": "\u2191",
  "roundabout|left": "\u21BA", "roundabout|right": "\u21BB",
  "arrive|straight": "\u25CF",
};

function mvGlyph(type, modifier) {
  const key = `${String(type || "").toLowerCase()}|${String(modifier || "").toLowerCase()}`;
  if (MV_GLYPH[key]) return MV_GLYPH[key];
  if (key.includes("|left")) return "\u2190";
  if (key.includes("|right")) return "\u2192";
  if (key.includes("straight")) return "\u2191";
  return "\u2191";
}

function maneuversHtml(inst, isMetric) {
  const list = Array.isArray(inst?.maneuvers) ? inst.maneuvers : [];
  if (!list.length) return "";
  // Skip the first entry: it duplicates the headline row, which comes from carrotManSP.
  const rest = list.slice(1, 4);
  if (!rest.length) return "";
  const parts = rest.map((mv, i) => {
    const dist = Number(mv.distance) > 0 ? esc(fmtDist(Number(mv.distance), isMetric)) : "";
    const cls = i === 0 ? "cn-mv" : "cn-mv cn-mv--then";
    return `<span class="${cls}"><i>${esc(mvGlyph(mv.type, mv.modifier))}</i>${dist}</span>`;
  });
  return `<div class="cn-maneuvers">${parts.join("")}</div>`;
}

const LANE_GLYPH = { 0: "", 1: "\u2190", 2: "\u2192", 3: "\u2191", 4: "\u2196", 5: "\u2197" };

function lanesHtml(inst) {
  const lanes = Array.isArray(inst?.lanes) ? inst.lanes : [];
  if (!lanes.length) return "";
  const cells = lanes.map((ln) => {
    const dirs = Array.isArray(ln.directions) ? ln.directions : [];
    // An empty direction list means "this lane has no guidance", drawn as a dash.
    const glyph = dirs.map((d) => LANE_GLYPH[d] || "").join("") || "\u2013";
    const cls = ln.active ? "cn-lane cn-lane--active" : "cn-lane";
    return `<span class="${cls}">${esc(glyph)}</span>`;
  });
  return `<div class="cn-lanes">${cells.join("")}</div>`;
}

function typicalHtml(inst) {
  // Only worth showing when the live estimate is meaningfully worse than typical.
  const live = Number(inst?.time_remaining) || 0;
  const typical = Number(inst?.time_remaining_typical) || 0;
  if (!(live > 0 && typical > 0)) return "";
  const delta = Math.round((live - typical) / 60);
  if (delta < 5) return "";
  return `<div class="cn-typical">${esc(tr("Typical"))} +${delta} ${esc(tr("min"))}</div>`;
}

function renderPanel(nav, isMetric, speedKph, inst, spHud) {
  const tbt = nav.tbt_main_text
    ? nav.tbt_main_text + (nav.near_dir_name ? " → " + nav.near_dir_name : "")
    : "";
  const turn = nav.turn_info > 0 ? turnMiniHtml(nav) : "";
  const hasEta = nav.go_pos_dist > 0 && nav.go_pos_time > 0;
  let sub = "";
  if (hasEta) {
    sub = `${esc(etaString(nav.go_pos_time))} · ${esc(fmtDist(nav.go_pos_dist, isMetric))}${nav.goal_name ? " 🏁 " + esc(nav.goal_name) : ""}`;
  } else if (nav.goal_name) {
    sub = `🏁 ${esc(nav.goal_name)}`;
  }
  const dist = nav.dist_to_turn > 0 ? `<div class="cn-tdist">${esc(fmtDist(nav.dist_to_turn, isMetric))}</div>` : "";
  const cd = nav.turn_countdown > 0 ? `<div class="cn-tcd">${nav.turn_countdown}s</div>` : "<div class=\"cn-tcd\"></div>";
  const badges = badgesHtml(nav, speedKph, spHud);
  return `
    <div class="cn-head">
      ${turn}
      <div class="cn-headline">
        <div class="cn-tbt">${esc(tbt)}</div>
        ${sub ? `<div class="cn-sub">${sub}</div>` : ""}
      </div>
      ${dist || cd ? `<div class="cn-turnmeta">${dist}${cd}</div>` : ""}
    </div>
    ${maneuversHtml(inst, isMetric)}
    ${lanesHtml(inst)}
    ${typicalHtml(inst)}
    ${badges}`;
}

export function updateCarrotNav(st) {
  injectStyle();
  const el = document.getElementById("hud-carrot-nav");
  if (!el) return;
  const nav = st?.sp_hud?.carrot_nav;
  const inst = st?.sp_hud?.carrot_instruction;
  if (!st?.started || !hasNavContent(nav)) {
    el.hidden = true;
    lastNavSig = "";
    return;
  }
  const isMetric = st.is_metric !== false;
  const speedKph = Number(st?.sp_hud?.cluster_speed) || 0;
  el.hidden = false;
  // horizontally centered, raised above the torque arc band (panel_side is
  // intentionally no longer used — the user prefers a fixed centered card)
  el.style.opacity = String(Math.max(0.1, Math.min(1, (Number(nav.panel_opacity) || 100) / 100)));
  const sig = JSON.stringify(nav) + "|" + JSON.stringify(inst) + "|" +
              (isMetric ? "m" : "i") + "|" + speedKph;
  if (sig === lastNavSig) return;
  lastNavSig = sig;
  el.innerHTML = renderPanel(nav, isMetric, speedKph, inst, st?.sp_hud);
}

export function updateAmapBars(st) {
  injectStyle();
  const lines = st?.sp_hud?.amap_lines;
  const show = !!st?.started && !!lines?.valid;
  for (const side of ["l", "r"]) {
    const el = document.getElementById(side === "l" ? "hud-amap-bar-l" : "hud-amap-bar-r");
    if (!el) continue;
    el.hidden = !show;
    if (show) {
      const blocked = side === "l" ? lines.left_blocked : lines.right_blocked;
      el.classList.toggle("is-blocked", !!blocked);
    }
  }
}

const CROSSROAD_POLL_MS = 2000;
const CROSSROAD_SHOW_MAX_DIST_M = 600;
const CROSSROAD_FADE_DIST_M = 50;

const MEDIA_POLL_MS = 2000;
const MEDIA_KINDS = ["tbt", "lane", "traffic_signal", "center"];
const MEDIA_KIND_LABELS = {
  tbt: () => tr("Turn preview"),
  lane: () => tr("Lane guidance"),
  traffic_signal: () => tr("Signal"),
  center: () => tr("Junction"),
};

function crossroadSig(cr, img) {
  return JSON.stringify([cr?.ts, cr?.distanceM, img?.imageHash, img?.show, img?.source]);
}

function buildCrossroadImageSrc(image) {
  if (!image?.show) return null;
  const b64 = image.imageBase64 || "";
  if (!b64) return null;
  const mime = image.imageMime || "image/png";
  return `data:${mime};base64,${b64}`;
}

function selectCrossroadImage(frame, image) {
  // Prefer a recent carrotNaviMediaSP frame; fall back to the CarrotNaviImage Param.
  if (frame?.show && frame.imageBase64) {
    return { img: frame, source: frame.source || "carrotNaviMediaSP" };
  }
  if (image?.show && image.imageBase64) {
    return { img: image, source: image.source || "CarrotNaviImage" };
  }
  return { img: null, source: null };
}

function renderCrossroad(cr, image, frame) {
  const nav = document.getElementById("hud-carrot-nav");
  if (!nav) return;
  let wrap = document.getElementById("hud-carrot-crossroad");
  const { img, source } = selectCrossroadImage(frame, image);
  const src = buildCrossroadImageSrc(img);
  const distM = cr?.distanceM ?? 0;
  const show = !!src && distM > 0 && distM <= CROSSROAD_SHOW_MAX_DIST_M;
  if (!show) {
    if (wrap) wrap.hidden = true;
    return;
  }
  if (!wrap) {
    wrap = document.createElement("div");
    wrap.id = "hud-carrot-crossroad";
    wrap.className = "opui-carrot-crossroad";
    nav.parentNode.insertBefore(wrap, nav);
  }
  wrap.hidden = false;
  const ratio = Math.max(0, Math.min(1, img?.remainRatio ?? cr?.remainRatio ?? 0));
  const metaText = distM > 1000
    ? `${(distM / 1000).toFixed(1)} km`
    : `${Math.round(distM)} m`;
  const sig = crossroadSig(cr, img);
  if (sig === lastCrossroadSig) return;
  lastCrossroadSig = sig;
  wrap.innerHTML = `
    <img src="${src}" alt="" data-source="${esc(source)}" />
    <div class="opui-carrot-crossroad-meta">${esc(tr("Junction ahead"))} · ${esc(metaText)}</div>
    <div class="opui-carrot-crossroad-progress" style="width:${Math.round(ratio * 100)}%"></div>`;
}

async function fetchCrossroad() {
  if (pendingCrossroadFetch) return;
  pendingCrossroadFetch = apiGet("/api/opui/carrot/crossroad").finally(() => {
    pendingCrossroadFetch = null;
  });
  const data = await pendingCrossroadFetch;
  if (!data?.ok) return;
  renderCrossroad(data.crossroad, data.image, data.frame);
}

function ensureCrossroadPolling() {
  if (crossroadTimer) return;
  fetchCrossroad();
  crossroadTimer = setInterval(fetchCrossroad, CROSSROAD_POLL_MS);
}

function stopCrossroadPolling() {
  if (crossroadTimer) {
    clearInterval(crossroadTimer);
    crossroadTimer = null;
  }
  lastCrossroadSig = "";
  const wrap = document.getElementById("hud-carrot-crossroad");
  if (wrap) wrap.hidden = true;
}

export function updateCarrotCrossroad(st) {
  injectStyle();
  const navActive = !!st?.sp_hud?.carrot_nav?.active;
  if (!st?.started || !navActive) {
    stopCrossroadPolling();
    return;
  }
  ensureCrossroadPolling();
}

function buildMediaImageSrc(frame) {
  if (!frame?.show) return null;
  const b64 = frame.imageBase64 || "";
  if (!b64) return null;
  const mime = frame.imageMime || "image/png";
  return `data:${mime};base64,${b64}`;
}

function mediaSig(data) {
  if (!data?.ok || !data.frames) return "";
  const parts = [];
  for (const name of Object.keys(data.frames).sort()) {
    const f = data.frames[name];
    parts.push(`${name}:${f.imageHash || ""}:${f.ts || 0}`);
  }
  return parts.join("|");
}

function renderMediaFrames(data) {
  const nav = document.getElementById("hud-carrot-nav");
  if (!nav) return;
  let wrap = document.getElementById("hud-carrot-media");
  if (!data?.ok || !data.byKind || Object.keys(data.byKind).length === 0) {
    if (wrap) wrap.hidden = true;
    return;
  }
  if (!wrap) {
    wrap = document.createElement("div");
    wrap.id = "hud-carrot-media";
    wrap.className = "opui-carrot-media";
    nav.parentNode.insertBefore(wrap, nav);
  }
  wrap.hidden = false;

  const sig = mediaSig(data);
  if (sig === lastMediaSig) return;
  lastMediaSig = sig;

  const htmlParts = [];
  for (const kind of MEDIA_KINDS) {
    const names = data.byKind[kind];
    if (!names || names.length === 0) continue;
    const frame = data.frames[names[0]];
    const src = buildMediaImageSrc(frame);
    if (!src) continue;
    const label = (MEDIA_KIND_LABELS[kind] || (() => kind))();
    htmlParts.push(`
      <div class="opui-carrot-media-frame" data-kind="${esc(kind)}">
        <img src="${src}" alt="" data-name="${esc(frame.name || names[0])}" />
        <div class="opui-carrot-media-label">${esc(label)}</div>
      </div>`);
  }
  wrap.innerHTML = htmlParts.join("");
}

async function fetchMedia() {
  if (pendingMediaFetch) return;
  pendingMediaFetch = apiGet("/api/opui/carrot/media").finally(() => {
    pendingMediaFetch = null;
  });
  const data = await pendingMediaFetch;
  renderMediaFrames(data);
}

function ensureMediaPolling() {
  if (mediaTimer) return;
  fetchMedia();
  mediaTimer = setInterval(fetchMedia, MEDIA_POLL_MS);
}

function stopMediaPolling() {
  if (mediaTimer) {
    clearInterval(mediaTimer);
    mediaTimer = null;
  }
  lastMediaSig = "";
  const wrap = document.getElementById("hud-carrot-media");
  if (wrap) wrap.hidden = true;
}

export function updateCarrotMedia(st) {
  injectStyle();
  const navActive = !!st?.sp_hud?.carrot_nav?.active;
  if (!st?.started || !navActive) {
    stopMediaPolling();
    return;
  }
  ensureMediaPolling();
}
