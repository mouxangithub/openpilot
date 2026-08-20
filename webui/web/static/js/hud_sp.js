/** sunnypilot onroad HUD extensions (speed limit, road name, blinkers, DM arc, rocket fuel, SCC). */

import { tr } from "./i18n.js";
import { AlertFadeAnimator } from "./fade_anim.js";

const TURN_IMG = "/api/opui/assets/icons_mici/onroad/turn_signal_left.png";
const BSM_IMG = "/api/opui/assets/icons_mici/onroad/blind_spot_left.png";
const DM_FACE_IMG = "/api/opui/assets/icons/driver_face.png";
const ARROW_UP = "/api/opui/assets/sunnypilot/selfdrive/assets/img_plus_arrow_up.png";
const ARROW_DOWN = "/api/opui/assets/sunnypilot/selfdrive/assets/img_minus_arrow_down.png";
const ARC_LEN = 133;

const TURN_BLINK_PERIOD = 1 / (80 / 60);
const TURN_FILTER_RC = 0.3;
const TURN_TARGET_ON = 510;
const TURN_TARGET_OFF = 51;

let vcAccel = 0;
const turnBlink = {
  left: { timer: 0, alpha: TURN_TARGET_OFF, active: false },
  right: { timer: 0, alpha: TURN_TARGET_OFF, active: false },
};
let turnAnimId = 0;

const roadMarquee = {
  offset: 0,
  direction: 1,
  pause: 0,
  overflow: 0,
  speed: 40,
  animId: 0,
};

export function updateSpHud(st) {
  const hud = document.getElementById("hud");
  if (!hud) return;

  if (!st?.started) {
    clearSpHud();
    vcAccel = 0;
    return;
  }

  const sp = st.sp_hud || {};
  const alertSize = (st.alert?.size || "none").toLowerCase();
  const hideDm = alertSize && alertSize !== "none";

  updateSpeedLimit(sp, st);
  updateSccTags(sp);
  updateRocketFuel(st);
  updateTurnSignals(st, sp);

  const roadName = st.road_name_toggle ? sp.road_name : "";
  updateRoadName(roadName);
  drawDmArc(st.dm_arc, hideDm, Number(st.developer_ui) || 0);
}

function measureRoadText(text, fontSize = 46) {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  if (!ctx) return text.length * fontSize * 0.55;
  ctx.font = `600 ${fontSize}px Inter, system-ui, sans-serif`;
  return ctx.measureText(text).width;
}

function stopRoadMarquee() {
  if (roadMarquee.animId) {
    cancelAnimationFrame(roadMarquee.animId);
    roadMarquee.animId = 0;
  }
}

function updateRoadName(text) {
  const wrap = document.getElementById("hud-road-name");
  const label = wrap?.querySelector(".opui-hud-road__text");
  if (!wrap || !label) return;

  if (!text) {
    wrap.hidden = true;
    wrap.classList.remove("is-marquee");
    label.textContent = "";
    label.style.transform = "";
    stopRoadMarquee();
    return;
  }

  wrap.hidden = false;
  const hud = document.getElementById("hud");
  const availW = Math.max(400, (hud?.clientWidth || 2160) - 40);
  const padding = 40;
  const fontSize = 46;
  const maxBox = Math.max(200, Math.min(measureRoadText(text, fontSize) + padding, availW * 0.7));
  const fullW = measureRoadText(text, fontSize);

  wrap.style.maxWidth = `${Math.round(maxBox)}px`;
  label.textContent = text;
  label.style.fontSize = `${fontSize}px`;

  if (fullW + padding > maxBox) {
    wrap.classList.add("is-marquee");
    roadMarquee.overflow = fullW - (maxBox - padding);
    if (!roadMarquee.animId) {
      let last = performance.now();
      const tick = (now) => {
        if (wrap.hidden || !wrap.classList.contains("is-marquee")) {
          roadMarquee.animId = 0;
          return;
        }
        const dt = Math.min(0.05, (now - last) / 1000);
        last = now;
        if (roadMarquee.pause > 0) {
          roadMarquee.pause -= dt;
        } else {
          roadMarquee.offset += roadMarquee.direction * roadMarquee.speed * dt;
          if (roadMarquee.offset >= roadMarquee.overflow) {
            roadMarquee.offset = roadMarquee.overflow;
            roadMarquee.direction = -1;
            roadMarquee.pause = 1.2;
          } else if (roadMarquee.offset <= 0) {
            roadMarquee.offset = 0;
            roadMarquee.direction = 1;
            roadMarquee.pause = 1.2;
          }
        }
        label.style.transform = `translateX(${-roadMarquee.offset}px)`;
        roadMarquee.animId = requestAnimationFrame(tick);
      };
      roadMarquee.animId = requestAnimationFrame(tick);
    }
  } else {
    wrap.classList.remove("is-marquee");
    label.style.transform = "";
    stopRoadMarquee();
  }
}

function stopTurnAnimLoop() {
  if (!turnAnimId) return;
  cancelAnimationFrame(turnAnimId);
  turnAnimId = 0;
}

function ensureTurnAnimLoop() {
  if (turnAnimId) return;
  let last = performance.now();
  const tick = (now) => {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    const k = 1 - Math.exp(-dt / TURN_FILTER_RC);
    for (const side of ["left", "right"]) {
      const state = turnBlink[side];
      const target = state.active ? TURN_TARGET_ON : TURN_TARGET_OFF;
      if (state.active && now / 1000 - state.timer > TURN_BLINK_PERIOD) {
        state.timer = now / 1000;
        state.alpha = TURN_TARGET_ON;
      }
      state.alpha += (target - state.alpha) * k;
      const el = document.getElementById(side === "left" ? "hud-blinker-l" : "hud-blinker-r");
      if (el && !el.hidden && !el.classList.contains("is-bsm")) {
        el.style.opacity = String(Math.min(1, Math.max(0, state.alpha / 255)));
      }
    }
    if (!turnSignalsNeedAnim()) {
      stopTurnAnimLoop();
      return;
    }
    turnAnimId = requestAnimationFrame(tick);
  };
  turnAnimId = requestAnimationFrame(tick);
}

function turnSignalsNeedAnim() {
  const l = document.getElementById("hud-blinker-l");
  const r = document.getElementById("hud-blinker-r");
  return (l && !l.hidden) || (r && !r.hidden);
}

function updateTurnSignals(st, sp) {
  const allowTurn = !!st.turn_signals;
  const allowBsm = !!st.blindspot;
  if (!allowTurn && !allowBsm) {
    hideEl("hud-blinker-l");
    hideEl("hud-blinker-r");
    hideEl("hud-bsl");
    hideEl("hud-bsr");
    stopTurnAnimLoop();
    return;
  }

  hideEl("hud-bsl");
  hideEl("hud-bsr");
  updateTurnSide("hud-blinker-l", allowBsm && sp.blindspot_left, allowTurn && sp.turn_signal_left);
  updateTurnSide("hud-blinker-r", allowBsm && sp.blindspot_right, allowTurn && sp.turn_signal_right, true);
  ensureTurnAnimLoop();
}

function updateTurnSide(id, bsm, blinker, flip = false) {
  const el = document.getElementById(id);
  if (!el) return;
  if (!bsm && !blinker) {
    el.hidden = true;
    return;
  }
  el.hidden = false;
  el.classList.toggle("is-bsm", bsm);
  el.classList.remove("is-blink");
  const img = bsm ? BSM_IMG : TURN_IMG;
  el.style.backgroundImage = `url("${img}")`;
  const baseTransform = flip ? "scaleX(-1)" : "";
  if (bsm) {
    el.style.opacity = "1";
    el.style.transform = baseTransform;
    return;
  }
  const side = id.includes("r") ? "right" : "left";
  turnBlink[side].active = !!blinker;
  if (!blinker) {
    el.style.opacity = "0.2";
    el.style.transform = baseTransform;
    return;
  }
  el.style.transform = baseTransform;
}

function updateSpeedLimit(sp, st) {
  const slaWrap = document.getElementById("hud-speed-limit-wrap");
  if (!slaWrap) return;

  if (Number(st.speed_limit_mode) === 0) {
    slaWrap.hidden = true;
    return;
  }

  slaWrap.hidden = false;
  const isMutcd = st.is_metric === false;
  slaWrap.classList.toggle("opui-hud-sla--mutcd", isMutcd);
  if (isMutcd) {
    const w = slaWrap.offsetWidth || 200;
    const h = slaWrap.offsetHeight || 204;
    slaWrap.style.borderRadius = `${Math.round(Math.min(w, h) * 0.35)}px`;
  } else {
    slaWrap.style.borderRadius = "";
  }

  const mutcdLabels = slaWrap.querySelector(".opui-hud-sla-mutcd-labels");
  if (mutcdLabels) {
    const showMutcd = st.is_metric === false;
    mutcdLabels.hidden = !showMutcd;
    if (showMutcd) {
      const speedLbl = mutcdLabels.querySelector(".opui-hud-sla-mutcd-speed");
      const limitLbl = mutcdLabels.querySelector(".opui-hud-sla-mutcd-limit");
      if (speedLbl) speedLbl.textContent = tr("SPEED");
      if (limitLbl) limitLbl.textContent = tr("LIMIT");
    }
  }

  const hasLimit = !!(sp.speed_limit_valid || sp.speed_limit_last_valid);
  const limitVal = hasLimit
    ? Math.round(sp.speed_limit_last ?? sp.speed_limit_resolver ?? 0)
    : null;
  const limitText = limitVal != null ? String(limitVal) : "---";

  const el = document.getElementById("hud-speed-limit");
  if (el) el.textContent = limitText;
  slaWrap.classList.toggle("is-three-digit", limitText.length >= 3);

  const warningMode = Number(st.speed_limit_mode) >= 2;
  const isOverspeed = hasLimit
    && Math.round(sp.speed_limit_final_last ?? limitVal ?? 0) < Math.round(st.speed ?? 0);
  slaWrap.classList.toggle("is-overspeed", warningMode && isOverspeed);
  slaWrap.classList.toggle("is-invalid", hasLimit && !sp.speed_limit_valid);

  const offset = Number(sp.speed_limit_offset) || 0;
  let offsetEl = document.getElementById("hud-speed-limit-offset");
  if (!offsetEl && slaWrap) {
    offsetEl = document.createElement("span");
    offsetEl.id = "hud-speed-limit-offset";
    offsetEl.className = "opui-hud-sla-offset";
    slaWrap.appendChild(offsetEl);
  }
  if (offsetEl) {
    if (offset !== 0 && hasLimit) {
      const sign = offset > 0 ? "" : "-";
      offsetEl.textContent = `${sign}${Math.round(Math.abs(offset))}`;
      offsetEl.hidden = false;
    } else {
      offsetEl.hidden = true;
    }
  }

  const assistState = sp.speed_limit_assist_state || sp.speed_limit_assist || "";
  const preActive = assistState === "preActive" || sp.speed_limit_assist === "preActive";
  const assist = preActive || sp.speed_limit_assist_active;
  slaWrap.classList.toggle("opui-hud-sla--assist", assist);
  slaWrap.classList.toggle("opui-hud-sla--preactive", preActive);

  let arrowEl = document.getElementById("hud-speed-limit-arrow");
  if (!arrowEl && slaWrap.parentElement) {
    arrowEl = document.createElement("img");
    arrowEl.id = "hud-speed-limit-arrow";
    arrowEl.className = "opui-hud-sla-arrow";
    arrowEl.alt = "";
    slaWrap.parentElement.appendChild(arrowEl);
  }
  if (arrowEl) {
    slaArrowFade.update(preActive);
    if (preActive && sp.pre_active_arrow) {
      arrowEl.hidden = false;
      arrowEl.src = sp.pre_active_arrow === "down" ? ARROW_DOWN : ARROW_UP;
      arrowEl.style.opacity = String(Math.max(0, Math.min(1, slaArrowFade.alpha)));
    } else {
      arrowEl.hidden = true;
      arrowEl.style.opacity = "0";
    }
  }

  let ahead = document.getElementById("hud-speed-limit-ahead");
  if (!ahead && slaWrap.parentElement) {
    ahead = document.createElement("div");
    ahead.id = "hud-speed-limit-ahead";
    ahead.className = "opui-hud-sla-ahead";
    ahead.hidden = true;
    slaWrap.parentElement.appendChild(ahead);
  }
  if (ahead) {
    const sourceIsMap = sp.speed_limit_source === "map";
    const currentLimit = sp.speed_limit_resolver ?? limitVal;
    const showAhead = sourceIsMap
      && sp.speed_limit_ahead_valid
      && sp.speed_limit_ahead != null
      && currentLimit != null
      && Math.round(sp.speed_limit_ahead) !== Math.round(currentLimit);
    if (showAhead) {
      ahead.hidden = false;
      const dist = formatAheadDist(sp.speed_limit_ahead_dist, st.is_metric !== false);
      ahead.innerHTML = `<span class="opui-hud-sla-ahead__label">${tr("AHEAD")}</span>`
        + `<span class="opui-hud-sla-ahead__val">${Math.round(sp.speed_limit_ahead)}</span>`
        + `<span class="opui-hud-sla-ahead__dist">${dist}</span>`;
    } else {
      ahead.hidden = true;
    }
  }
}

function formatAheadDist(d, metric) {
  const dist = Number(d) || 0;
  if (metric) {
    if (dist < 50) return tr("Near");
    if (dist >= 1000) return `${(dist / 1000).toFixed(1)} ${tr("km")}`;
    const rounded = dist < 200 ? Math.round(dist / 10) * 10 : Math.round(dist / 100) * 100;
    return `${rounded} ${tr("m")}`;
  }
  const dFt = dist * 3.28084;
  if (dFt < 100) return tr("Near");
  if (dFt >= 900) return `${(dist * 0.000621371).toFixed(1)} ${tr("mi")}`;
  const rounded = dFt < 200 ? Math.round(dFt / 10) * 10 : Math.round(dFt / 100) * 100;
  return `${rounded} ${tr("ft")}`;
}

function updateRocketFuel(st) {
  const rocket = document.getElementById("hud-rocket");
  if (!rocket) return;

  if (!st.rocket_fuel_enabled) {
    rocket.hidden = true;
    return;
  }

  const aEgo = Number(st.a_ego) || 0;
  vcAccel += (aEgo - vcAccel) / 5;

  let hha = 0;
  let isBrake = false;
  if (vcAccel > 0) {
    hha = Math.max(0, 0.85 - 0.1 / vcAccel);
  } else if (vcAccel < 0) {
    hha = Math.max(0, 0.85 + 0.1 / vcAccel);
    isBrake = true;
  }

  if (hha <= 0) {
    rocket.hidden = true;
    return;
  }

  rocket.hidden = false;
  const barPct = (hha / 2) * 100;
  rocket.style.setProperty("--rocket-up", isBrake ? "0%" : `${barPct}%`);
  rocket.style.setProperty("--rocket-down", isBrake ? `${barPct}%` : "0%");
}

function clearSpHud() {
  stopRoadMarquee();
  turnBlink.left.active = false;
  turnBlink.right.active = false;
  dmFadeFiltered = 0;
  dmFadeTs = 0;
  ["hud-speed-limit-wrap", "hud-blinker-l", "hud-blinker-r", "hud-bsl", "hud-bsr",
    "hud-rocket", "hud-road-name", "hud-scc-v", "hud-scc-m", "dm-arc-wrap"].forEach((id) => {
    hideEl(id);
  });
  hideEl("hud-speed-limit-ahead");
  hideEl("hud-speed-limit-arrow");
}

function hideEl(id) {
  const el = document.getElementById(id);
  if (el) el.hidden = true;
}

function updateSccTags(sp) {
  const vision = document.getElementById("hud-scc-v");
  const map = document.getElementById("hud-scc-m");
  const override = !!sp.long_override;

  sccVisionActive = !!sp.scc_vision_active;
  sccMapActive = !!sp.scc_map_active;
  sccVisionFade.update(sccVisionActive);
  sccMapFade.update(sccMapActive);

  if (vision) {
    vision.hidden = !sp.scc_vision_enabled;
    vision.classList.toggle("is-override", override);
    vision.classList.remove("is-dim");
    const alpha = sccVisionActive ? sccVisionFade.alpha : 1;
    vision.style.opacity = String(Math.max(0, Math.min(1, alpha)));
  }
  if (map) {
    map.hidden = !sp.scc_map_enabled;
    map.classList.toggle("is-override", override);
    map.classList.remove("is-dim");
    const alpha = sccMapActive ? sccMapFade.alpha : 1;
    map.style.opacity = String(Math.max(0, Math.min(1, alpha)));
  }
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (!el) return;
  if (!text) {
    el.hidden = true;
    return;
  }
  el.hidden = false;
  el.textContent = text;
}

let dmFadeFiltered = 0;
let dmFadeTs = 0;

function smoothSplinePath(points, closed = false) {
  if (!points?.length) return "";
  if (points.length < 3) {
    return `M ${points[0][0]},${points[0][1]} L ${points[points.length - 1][0]},${points[points.length - 1][1]}`;
  }
  const pts = closed ? [...points, points[0], points[1]] : points;
  let d = `M ${pts[0][0]},${pts[0][1]}`;
  for (let i = 0; i < pts.length - 2; i++) {
    const p0 = pts[Math.max(0, i - 1)];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[Math.min(pts.length - 1, i + 2)];
    const cp1x = p1[0] + (p2[0] - p0[0]) / 6;
    const cp1y = p1[1] + (p2[1] - p0[1]) / 6;
    const cp2x = p2[0] - (p3[0] - p1[0]) / 6;
    const cp2y = p2[1] - (p3[1] - p1[1]) / 6;
    d += ` C ${cp1x},${cp1y} ${cp2x},${cp2y} ${p2[0]},${p2[1]}`;
  }
  return d;
}

const slaArrowFade = new AlertFadeAnimator({ durationOn: 0.75, rc: 0.05 });
const sccVisionFade = new AlertFadeAnimator();
const sccMapFade = new AlertFadeAnimator();
let sccVisionActive = false;
let sccMapActive = false;

function drawDmArc(dm, hideDm, devUi) {
  const wrap = document.getElementById("dm-arc-wrap");
  const svg = document.getElementById("dm-arc");
  if (!wrap || !svg) return;
  if (!dm?.visible || hideDm) {
    wrap.hidden = true;
    wrap.classList.remove("is-clickable");
    dmFadeFiltered = hideDm ? 1 : 0;
    return;
  }
  wrap.hidden = false;
  wrap.classList.add("is-clickable");
  wrap.classList.toggle("opui-dm-wrap--rhd", !!dm.rhd);
  wrap.classList.toggle("opui-dm-wrap--dev-bottom", devUi === 1 || devUi === 3);
  wrap.classList.toggle("is-dm-active", !!dm.active);

  const fadeTarget = hideDm ? 1 : (Number(dm.fade) || 0);
  if (fadeTarget > dmFadeFiltered) {
    dmFadeFiltered = Math.min(fadeTarget, dmFadeFiltered + 0.2);
  } else if (fadeTarget < dmFadeFiltered) {
    dmFadeFiltered = Math.max(fadeTarget, dmFadeFiltered - 0.2);
  }
  const fadeMul = 1 - dmFadeFiltered;
  const arcAlpha = (dm.active ? 0.4 : 0.15) * fadeMul;
  const faceAlpha = (dm.active ? 0.65 : 0.2) * fadeMul;

  const faceLine = svg.querySelector(".dm-arc-face");
  const faceImg = wrap.querySelector(".opui-dm-face");
  const outline = dm.face_outline || [];
  if (faceImg) {
    faceImg.hidden = false;
    faceImg.style.opacity = String(faceAlpha);
  }
  if (faceLine) {
    if (outline.length >= 2) {
      faceLine.setAttribute("d", smoothSplinePath(outline, true));
      faceLine.hidden = false;
      faceLine.setAttribute("stroke-opacity", String(faceAlpha));
    } else {
      faceLine.setAttribute("d", "");
      faceLine.hidden = true;
    }
  }

  const hArc = svg.querySelector(".dm-arc-h");
  const vArc = svg.querySelector(".dm-arc-v");
  const engagedColor = dm.engaged ? "#1af242" : "#8b8b8b";

  function applyArcPath(el, arc) {
    if (!el) return;
    const pts = arc?.points;
    if (!pts?.length) {
      el.setAttribute("d", "");
      el.hidden = true;
      return;
    }
    el.hidden = false;
    el.setAttribute("d", smoothSplinePath(pts, false));
    el.setAttribute("stroke", engagedColor);
    el.setAttribute("stroke-width", String(arc.thickness ?? 6.7));
    el.setAttribute("stroke-opacity", String(arcAlpha));
  }

  applyArcPath(hArc, dm.h_arc);
  applyArcPath(vArc, dm.v_arc);
}

let dmArcBound = false;

export function bindDmArcClick() {
  if (dmArcBound) return;
  const wrap = document.getElementById("dm-arc-wrap");
  if (!wrap) return;
  dmArcBound = true;
  wrap.addEventListener("click", (ev) => {
    if (wrap.hidden) return;
    ev.stopPropagation();
    window.dispatchEvent(new CustomEvent("opui:open-driver-camera"));
  });
}
