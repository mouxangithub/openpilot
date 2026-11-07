/** Road lite view — data-only synthesized driving scene shown when the video
 * stream is off/failing (preview off, connecting, or WebRTC error).
 * Replaces the frozen/black video with a dark perspective road, lane markings,
 * ego car and lead indicators. All data comes from the existing WS state
 * channel. Road curvature, lane count, the Tesla-style rainbow planning path
 * and adjacent vehicles follow the real modelV2 geometry sampled server-side
 * (state.road_model); without model data a straight three-lane fallback road
 * is drawn. */

import { opuiWs } from "./ws.js";
import { tr } from "./i18n.js?v=3";

const ROAD_LITE_MS = 400;

let host = null;
let canvas = null;
let ctx = null;
let active = false;
let forced = false;
let rafId = null;
let lastFrameTs = 0;
let distM = 0;
let lastState = null;
let watchTimer = null;
let lastWrapClass = "";
let frameSkip = 0;

/* Fake-live detection: a playing <video> whose frames never change is frozen
   (decoder stall). N identical probes in a row → treat the stream as dead so
   the synthesized scene takes over. */
const FROZEN_PROBES = 3;
let frozenStreak = 0;
let lastFrozenHash = null;
let frozenProbeTs = 0;
let probeCanvas = null;

function isOnroadScreen() {
  const app = document.getElementById("app");
  return !!app && app.dataset.screen === "onroad";
}

function videoActive() {
  const wrap = document.getElementById("camera-wrap");
  if (!wrap) return true;
  if (forced) return false;
  if (frozenStreak >= FROZEN_PROBES) return false;  // fake-live (frozen) video
  if (wrap.classList.contains("preview-off")) return false;  // preview quality = off
  if (wrap.classList.contains("is-dev-pc")) return true;
  return wrap.classList.contains("is-playing");
}

function shouldShow() {
  return isOnroadScreen() && !videoActive();
}

export function isRoadLiteActive() {
  return active;
}

function buildDom() {
  host = document.createElement("div");
  host.id = "road-lite";
  host.className = "opui-road-lite";
  host.hidden = true;

  canvas = document.createElement("canvas");
  canvas.className = "opui-road-lite__canvas";
  host.appendChild(canvas);

  const wrap = document.getElementById("camera-wrap");
  if (wrap) wrap.appendChild(host);

  ctx = canvas.getContext("2d");
}

function resizeCanvas() {
  if (!canvas || !host) return;
  const w = host.clientWidth || 1600;
  const h = host.clientHeight || 900;
  const dpr = window.devicePixelRatio || 1;
  const pw = Math.max(1, Math.floor(w * dpr));
  const ph = Math.max(1, Math.floor(h * dpr));
  if (canvas.width !== pw || canvas.height !== ph) {
    canvas.width = pw;
    canvas.height = ph;
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { w, h };
}

/* ---------- scene rendering ---------- */

const HORIZON = 0.42;        // horizon line, fraction of height
const Z_NEAR = 2.5;          // m in front of bumper at canvas bottom
const Z_FAR = 160;           // culling distance, m
const Z0 = 4.5;              // perspective strength (pinhole-ish)
const HALF_ROAD_M = 5.55;    // fallback half road width, m (three ~3.7m lanes)
const DASH_LEN = 4.0;        // m, roughly the CN urban 4 m line / 6 m gap
const DASH_GAP = 6.0;        // m
const POLE_SPACING = 33.0;   // m
const POLE_RANGE = 200.0;    // m
const LINE_PROB_MIN = 0.35;  // model lane line confidence to draw it
// longitudinal sample steps for curved geometry (m)
const Z_STEPS = [2.5, 4, 6.5, 10, 15, 22, 32, 46, 64, 88, 118, 145, 160];

/* Lane-marking semantics, mirrored from AmapLineType (server folds them into
   road_model.line_kinds). Kept in sync with
   openpilot/sunnypilot/selfdrive/car/amap_fusion.py. */
const LK_UNKNOWN = 0;
const LK_SOLID_WHITE = 1;
const LK_DASHED_WHITE = 2;
const LK_SOLID_YELLOW = 3;
const LK_DOUBLE_YELLOW = 4;
const LK_BOTTS_DOTS = 5;
const LK_ROAD_EDGE = 6;
// Kinds that must be drawn continuous (never dashed) and block lane changes.
const SOLID_KINDS = new Set([LK_SOLID_WHITE, LK_SOLID_YELLOW, LK_DOUBLE_YELLOW, LK_ROAD_EDGE]);

/* Perception target classes. cereal carries no object class, so these are
   heuristics over leadsV3 kinematics (v / lateral & longitudinal std) and the
   radar track list — good enough for the synthesized scene, never fed back to
   the vehicle. */
const OBJ_CAR = "car";
const OBJ_TRUCK = "truck";
const OBJ_BIKE = "bike";     // bicycle
const OBJ_EBIKE = "ebike";   // e-bike / scooter
const OBJ_MOTO = "moto";     // motorcycle
const OBJ_PED = "ped";       // pedestrian
const OBJ_UNKNOWN = "unknown";

/* ---------- road geometry (model frame: lateral y, +right) ---------- */

function roadGeom() {
  const rm = lastState?.road_model;
  if (!rm || !Array.isArray(rm.dists) || rm.dists.length < 3) return null;
  const dists = rm.dists;
  const valid = (a) => Array.isArray(a) && a.length === dists.length && a.every((v) => Number.isFinite(v));
  const lines = [0, 1, 2, 3].map((i) => (valid(rm.lines?.[i]) ? rm.lines[i] : null));
  const probs = Array.isArray(rm.probs) ? rm.probs : [];
  const kindsRaw = Array.isArray(rm.line_kinds) ? rm.line_kinds : [];
  const kinds = [0, 1, 2, 3].map((i) => Number(kindsRaw[i] ?? LK_UNKNOWN) || LK_UNKNOWN);
  const visible = lines
    .map((arr, i) => ({
      arr, i, prob: Number(probs[i] ?? 0), y: arr ? arr[arr.length - 1] : 0,
      kind: kinds[i],
      solid: SOLID_KINDS.has(kinds[i]),
    }))
    .filter((l) => l.arr && l.prob >= LINE_PROB_MIN);
  const edges = [valid(rm.edges?.[0]) ? rm.edges[0] : null, valid(rm.edges?.[1]) ? rm.edges[1] : null];
  return {
    dists, lines, probs, visible, edges, kinds,
    lineTypes: Array.isArray(rm.line_types) ? rm.line_types : [0, 0, 0, 0],
    // Ego-lane centreline per sample, computed server-side from the innermost
    // bracketing lane lines. Preferred over deriving it from `visible` because
    // it survives a dropped (low-confidence) line on one side.
    laneCenters: valid(rm.lane_centers) ? rm.lane_centers : null,
    leads: Array.isArray(rm.leads) ? rm.leads : [],
    path: valid(rm.path) ? rm.path : null,
    pathStd: valid(rm.path_std) ? rm.path_std : null,
  };
}

function sampleCurve(arr, dists, z) {
  // Catmull-Rom interpolation over the distance samples
  const n = arr.length;
  if (z <= dists[0]) return arr[0];
  if (z >= dists[n - 1]) return arr[n - 1];
  let i = 0;
  while (i < n - 2 && dists[i + 1] < z) i++;
  const t = (z - dists[i]) / (dists[i + 1] - dists[i]);
  const p0 = arr[Math.max(0, i - 1)];
  const p1 = arr[i];
  const p2 = arr[i + 1];
  const p3 = arr[Math.min(n - 1, i + 2)];
  const t2 = t * t;
  const t3 = t2 * t;
  return 0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3);
}

/* Distant city: a haze band plus a procedural skyline with a scattering of lit
   windows. Fully deterministic (hash-based, no Math.random) so it never
   shimmers, and rendered once per viewport size into an offscreen canvas
   because none of it moves. */
let skylineCache = null;

function skylineBitmap(w, h, horizonY) {
  if (skylineCache && skylineCache.w === w && skylineCache.h === h && skylineCache.horizonY === horizonY) {
    return skylineCache.canvas;
  }
  const dpr = window.devicePixelRatio || 1;
  const off = document.createElement("canvas");
  off.width = Math.max(1, Math.floor(w * dpr));
  off.height = Math.max(1, Math.floor(h * dpr));
  const c = off.getContext("2d");
  c.setTransform(dpr, 0, 0, dpr, 0, 0);

  const rand = (i) => {
    const s = Math.sin(i * 12.9898) * 43758.5453;
    return s - Math.floor(s);
  };

  // light-pollution haze hugging the horizon
  const hz = c.createLinearGradient(0, horizonY - h * 0.18, 0, horizonY);
  hz.addColorStop(0, "rgba(58, 84, 138, 0)");
  hz.addColorStop(0.7, "rgba(70, 100, 156, 0.13)");
  hz.addColorStop(1, "rgba(96, 126, 184, 0.26)");
  c.fillStyle = hz;
  c.fillRect(0, horizonY - h * 0.18, w, h * 0.18);

  const baseY = horizonY + 1.5;
  const maxH = h * 0.082;
  const n = 30;
  for (let i = 0; i < n; i++) {
    const bw = w * (0.026 + rand(i * 3.1) * 0.046);
    const bx = (w * i) / n - bw * 0.28;
    const bh = maxH * (0.22 + rand(i * 7.7) * 0.78);

    c.fillStyle = "rgba(13, 20, 37, 0.94)";
    c.fillRect(bx, baseY - bh, bw, bh);
    // occasional rooftop mast
    if (rand(i * 11.3) > 0.82) {
      c.fillRect(bx + bw * 0.46, baseY - bh - maxH * 0.16, Math.max(1, w * 0.0012), maxH * 0.16);
    }

    const cols = Math.max(2, Math.round(bw / (w * 0.0085)));
    const rows = Math.max(2, Math.round(bh / (h * 0.0125)));
    for (let col = 0; col < cols; col++) {
      for (let row = 0; row < rows; row++) {
        if (rand(i * 31.7 + col * 5.31 + row * 2.73) < 0.76) continue;
        c.fillStyle = row % 3 === 0 ? "rgba(255, 226, 170, 0.22)" : "rgba(158, 194, 250, 0.20)";
        c.fillRect(
          bx + (col + 0.28) * (bw / cols),
          baseY - bh + (row + 0.32) * (bh / rows),
          Math.max(1, (bw / cols) * 0.4),
          Math.max(1, (bh / rows) * 0.36),
        );
      }
    }
  }

  skylineCache = { w, h, horizonY, canvas: off };
  return off;
}

function drawScene() {
  const size = resizeCanvas();
  if (!size) return;
  const { w, h } = size;
  const horizonY = h * HORIZON;
  const cx = w / 2;
  const mToPx = (w * 0.62) / HALF_ROAD_M;       // px per meter at z = Z_NEAR
  const fn = (z) => (Z0 + Z_NEAR) / (Z0 + Math.max(z, 0.4)); // 1 at bumper → 0 far
  const yOf = (z) => horizonY + (h - horizonY) * fn(z);

  // screen x for a point at distance z with model-frame lateral offset yM
  const xOf = (z, yM) => cx + yM * mToPx * fn(z);

  const geom = roadGeom();

  // edge curves: prefer roadEdges, else outermost visible lane lines
  let edgeL = null;
  let edgeR = null;
  let edgesFromLines = false;
  if (geom && geom.edges[0] && geom.edges[1]) {
    edgeL = geom.edges[0];
    edgeR = geom.edges[1];
  } else if (geom && geom.visible.length >= 2) {
    const vis = [...geom.visible].sort((a, b) => a.y - b.y);
    edgeL = vis[0].arr;
    edgeR = vis[vis.length - 1].arr;
    edgesFromLines = true;
  }

  const edgeLatAt = (side, z) => {
    const arr = side < 0 ? edgeL : edgeR;
    if (arr) return sampleCurve(arr, geom.dists, z);
    return side < 0 ? -HALF_ROAD_M : HALF_ROAD_M;
  };
  const lineLatAt = (line, z) => {
    if (!line) return null;
    if (line.y0 !== undefined) return line.y0; // straight fallback divider
    return sampleCurve(line.arr, geom.dists, z);
  };

  // divider lines = visible lines that are not the outermost ones
  let dividers = [];
  if (geom) {
    const vis = [...geom.visible].sort((a, b) => a.y - b.y);
    if (edgesFromLines && vis.length >= 2) dividers = vis.slice(1, -1);
    else dividers = vis;
  } else {
    dividers = [{ y0: -1.85 }, { y0: 1.85 }];
  }

  ctx.clearRect(0, 0, w, h);

  // --- sky gradient ---
  let g = ctx.createLinearGradient(0, 0, 0, horizonY);
  g.addColorStop(0, "#05080f");
  g.addColorStop(0.65, "#0a1120");
  g.addColorStop(1, "#0e1730");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, w, horizonY);

  // --- ground gradient ---
  g = ctx.createLinearGradient(0, horizonY, 0, h);
  g.addColorStop(0, "#0c1424");
  g.addColorStop(1, "#05080f");
  ctx.fillStyle = g;
  ctx.fillRect(0, horizonY, w, h - horizonY);

  // --- horizon glow (city ambience) ---
  const rg = ctx.createRadialGradient(cx, horizonY, 0, cx, horizonY, w * 0.42);
  rg.addColorStop(0, "rgba(96, 140, 220, 0.20)");
  rg.addColorStop(0.5, "rgba(96, 140, 220, 0.07)");
  rg.addColorStop(1, "rgba(96, 140, 220, 0)");
  ctx.fillStyle = rg;
  ctx.fillRect(0, 0, w, h);

  // --- distant skyline + haze (cached; geometry is viewport-independent) ---
  ctx.drawImage(skylineBitmap(w, h, horizonY), 0, 0, w, h);

  // --- road surface: polygon following the (possibly curved) edges ---
  const steps = Z_STEPS.filter((z) => z >= Z_NEAR && z <= Z_FAR);
  ctx.beginPath();
  for (let i = steps.length - 1; i >= 0; i--) {
    const z = steps[i];
    ctx.lineTo(xOf(z, edgeLatAt(-1, z)), yOf(z));
  }
  for (const z of steps) {
    ctx.lineTo(xOf(z, edgeLatAt(1, z)), yOf(z));
  }
  ctx.closePath();
  g = ctx.createLinearGradient(0, yOf(Z_FAR), 0, h);
  g.addColorStop(0, "#141c30");
  g.addColorStop(1, "#232f4c");
  ctx.fillStyle = g;
  ctx.fill();

  // ego-lane centreline: the server-computed lane_centers when available,
  // else the midpoint of the innermost bracketing pair of visible lines.
  const laneCenterAt = (z) => {
    if (geom && geom.laneCenters) return sampleCurve(geom.laneCenters, geom.dists, z);
    if (geom && geom.visible.length >= 2) {
      const vis = [...geom.visible].sort((a, b) => a.y - b.y);
      const inner = (edgesFromLines && vis.length >= 2) ? vis.slice(1, -1) : vis;
      if (inner.length >= 2) {
        return (lineLatAt(inner[0], z) + lineLatAt(inner[inner.length - 1], z)) / 2;
      }
      if (inner.length === 1) return lineLatAt(inner[0], z);
    }
    return 0;
  };

  // --- asphalt texture: faint longitudinal banding + tyre tracks ---------
  if (geom) {
    ctx.save();
    ctx.beginPath();
    for (let i = steps.length - 1; i >= 0; i--) ctx.lineTo(xOf(steps[i], edgeLatAt(-1, steps[i])), yOf(steps[i]));
    for (const z of steps) ctx.lineTo(xOf(z, edgeLatAt(1, z)), yOf(z));
    ctx.closePath();
    ctx.clip();
    // tyre-polished tracks either side of the ego lane centre
    for (const off of [-0.85, 0.85]) {
      ctx.beginPath();
      for (let i = 0; i < steps.length; i++) {
        const z = steps[i];
        const x = xOf(z, laneCenterAt(z) + off);
        if (i === 0) ctx.moveTo(x, yOf(z));
        else ctx.lineTo(x, yOf(z));
      }
      ctx.strokeStyle = "rgba(6, 10, 20, 0.22)";
      ctx.lineWidth = Math.max(2, w * 0.012);
      ctx.lineCap = "round";
      ctx.stroke();
    }
    // faint transverse seams scrolling toward the viewer
    const seamSpacing = 9.0;
    let zs = Z_NEAR + (seamSpacing - (distM % seamSpacing)) % seamSpacing;
    for (; zs < Z_FAR; zs += seamSpacing) {
      const f = fn(zs);
      if (f < 0.05) continue;
      ctx.beginPath();
      ctx.moveTo(xOf(zs, edgeLatAt(-1, zs)), yOf(zs));
      ctx.lineTo(xOf(zs, edgeLatAt(1, zs)), yOf(zs));
      ctx.strokeStyle = `rgba(180, 205, 255, ${0.035 * f})`;
      ctx.lineWidth = Math.max(0.6, w * 0.0016 * f);
      ctx.stroke();
    }
    ctx.restore();
  }

  // --- subtle sheen along the ego lane ----------------------------------
  // Three nested bands instead of one: a single polygon leaves a hard edge
  // against the asphalt that reads as an extra faint lane line.
  const sheenGrad = ctx.createLinearGradient(0, yOf(Z_FAR), 0, h);
  sheenGrad.addColorStop(0, "rgba(140, 170, 230, 0.010)");
  sheenGrad.addColorStop(0.55, "rgba(150, 180, 240, 0.038)");
  sheenGrad.addColorStop(1, "rgba(170, 200, 255, 0.016)");
  ctx.fillStyle = sheenGrad;
  for (const half of [1.20, 0.86, 0.48]) {
    ctx.beginPath();
    for (let i = steps.length - 1; i >= 0; i--) {
      const z = steps[i];
      ctx.lineTo(xOf(z, laneCenterAt(z) - half), yOf(z));
    }
    for (const z of steps) {
      ctx.lineTo(xOf(z, laneCenterAt(z) + half), yOf(z));
    }
    ctx.closePath();
    ctx.fill();
  }

  // --- ego headlight wash: anchors the car in the scene and sells depth ---
  drawHeadlights(w, h, cx, mToPx, fn, yOf);

  drawLightPools(w, h, cx, mToPx, fn, yOf, xOf, edgeLatAt);
  drawEdgeLines(w, h, cx, fn, yOf, xOf, edgeLatAt, steps);
  drawLaneLines(w, cx, mToPx, fn, yOf, xOf, dividers, lineLatAt);
  drawPlanPath(w, cx, mToPx, fn, yOf, xOf, geom, steps);
  drawLdw(w, h, fn, yOf, xOf, geom, lineLatAt);
  drawAlcArch(w, h, cx, mToPx, fn, yOf, xOf, geom, lineLatAt);
  drawPoles(w, h, cx, mToPx, fn, yOf, xOf, edgeLatAt);
  drawPerception(w, cx, mToPx, fn, yOf);
  drawEgoCar(w, h, cx);
  drawBsm(w, h);
  drawFcw(w, h);
  drawVignette(w, h, cx);
  // nav band last so neither the vignette nor any road furniture can wash it out
  drawNavBand(w, h);
}

/* Two soft low-beam wedges in front of the ego car, additively blended so they
   brighten the asphalt without hiding the markings drawn afterwards. */
function drawHeadlights(w, h, cx, mToPx, fn, yOf) {
  const carW = w * 0.15;
  const carH = carW * 0.62;
  const frontY = h * 0.955 - carH;
  const farZ = 42;
  const farY = yOf(farZ);
  const farF = fn(farZ);
  ctx.save();
  ctx.globalCompositeOperation = "lighter";
  const beam = ctx.createLinearGradient(0, frontY, 0, farY);
  beam.addColorStop(0, "rgba(200, 220, 255, 0.17)");
  beam.addColorStop(0.5, "rgba(178, 204, 255, 0.075)");
  beam.addColorStop(1, "rgba(160, 190, 255, 0)");
  ctx.fillStyle = beam;
  for (const side of [-1, 1]) {
    ctx.beginPath();
    ctx.moveTo(cx + side * carW * 0.40, frontY);
    ctx.lineTo(cx + side * carW * 0.26, frontY);
    ctx.lineTo(cx + side * mToPx * 3.6 * farF, farY);
    ctx.lineTo(cx + side * mToPx * 1.2 * farF, farY);
    ctx.closePath();
    ctx.fill();
  }
  ctx.restore();
}

function drawLightPools(w, h, cx, mToPx, fn, yOf, xOf, edgeLatAt) {
  // cool light pools cast by the streetlights onto the road
  ctx.lineCap = "round";
  // scroll toward the viewer (same phase convention as the poles below)
  let z = 6 + (POLE_SPACING - (distM % POLE_SPACING)) % POLE_SPACING;
  for (; z < POLE_RANGE; z += POLE_SPACING) {
    if (z > Z_FAR) break;
    const f = fn(z);
    if (f < 0.09) continue;
    const y = yOf(z);
    for (const side of [-1, 1]) {
      const px = xOf(z, edgeLatAt(side, z) + side * -1.2);
      const poolR = mToPx * 2.6 * f;
      ctx.save();
      ctx.translate(px, y);
      ctx.scale(1, 0.32);
      const pg = ctx.createRadialGradient(0, 0, 0, 0, 0, poolR);
      pg.addColorStop(0, "rgba(175, 200, 255, 0.10)");
      pg.addColorStop(1, "rgba(175, 200, 255, 0)");
      ctx.fillStyle = pg;
      ctx.beginPath();
      ctx.arc(0, 0, poolR, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }
  }
}

function drawEdgeLines(w, h, cx, fn, yOf, xOf, edgeLatAt, steps) {
  ctx.lineCap = "round";
  const pairs = [];
  for (let i = 0; i < steps.length - 1; i++) pairs.push([steps[i], steps[i + 1]]);

  // gravel / kerb band just outside each edge line — anchors the road in the
  // scene instead of letting the asphalt float on the background gradient.
  for (const side of [-1, 1]) {
    ctx.beginPath();
    for (let i = steps.length - 1; i >= 0; i--) {
      const z = steps[i];
      ctx.lineTo(xOf(z, edgeLatAt(side, z) + side * 1.5), yOf(z));
    }
    for (const z of steps) ctx.lineTo(xOf(z, edgeLatAt(side, z)), yOf(z));
    ctx.closePath();
    const sg = ctx.createLinearGradient(0, yOf(Z_FAR), 0, h);
    sg.addColorStop(0, "rgba(44, 52, 70, 0.30)");
    sg.addColorStop(1, "rgba(88, 96, 118, 0.50)");
    ctx.fillStyle = sg;
    ctx.fill();
  }

  for (const pass of [
    { width: w * 0.0035 * 2.4, color: "rgba(150, 190, 255, 0.11)" },  // glow
    { width: w * 0.0035, color: "rgba(234, 242, 254, 0.92)" },        // core
  ]) {
    ctx.strokeStyle = pass.color;
    for (const side of [-1, 1]) {
      for (const [za, zb] of pairs) {
        const zm = (za + zb) * 0.5;
        ctx.lineWidth = Math.max(1.0, pass.width * (0.38 + 0.62 * fn(zm)));
        ctx.beginPath();
        ctx.moveTo(xOf(za, edgeLatAt(side, za)), yOf(za));
        ctx.lineTo(xOf(zb, edgeLatAt(side, zb)), yOf(zb));
        ctx.stroke();
      }
    }
  }
}

/* Visual style for one Amap lane-line kind. `dash` = world-space dashed white,
   `double` = two parallel solid amber lines, `dots` = botts' dots, `wide` =
   road-edge / shoulder line.

   Redesigned 2026-09: lower glow, lower saturation, and thinner strokes so the
   road grid reads as context rather than a noisy foreground pattern. */
function laneStyle(kind) {
  switch (kind) {
    case LK_SOLID_YELLOW:
    case LK_DOUBLE_YELLOW:
      return { color: "rgba(232, 196, 90, 0.85)", glow: "rgba(240, 190, 70, 0.07)", dash: false, double: kind === LK_DOUBLE_YELLOW };
    case LK_BOTTS_DOTS:
      return { color: "rgba(210, 222, 245, 0.72)", glow: "rgba(140, 180, 255, 0.05)", dash: false, dots: true };
    case LK_DASHED_WHITE:
      return { color: "rgba(204, 216, 240, 0.74)", glow: "rgba(130, 170, 255, 0.06)", dash: true };
    case LK_ROAD_EDGE:
      return { color: "rgba(198, 210, 235, 0.62)", glow: "rgba(140, 180, 255, 0.05)", dash: false, wide: true };
    case LK_SOLID_WHITE:
      return { color: "rgba(218, 228, 248, 0.78)", glow: "rgba(140, 180, 255, 0.07)", dash: false };
    default:
      return { color: "rgba(194, 208, 234, 0.70)", glow: "rgba(130, 170, 255, 0.05)", dash: true };
  }
}

/* Lane dividers. Style comes from `line.kind` (road_model.line_kinds, folded
   from carStateSP.amap*LineType when the Amap sender is live); unknown falls
   back to dashed white. Widths taper with perspective via fn(z) so nearby
   markings read thicker than distant ones, matching the pinhole projection
   used for the rest of the scene. */
function drawLaneLines(w, cx, mToPx, fn, yOf, xOf, dividers, lineLatAt) {
  if (!dividers.length) return;
  const dashPeriod = DASH_LEN + DASH_GAP;
  const phase = distM % dashPeriod;
  ctx.lineCap = "round";

  for (const line of dividers) {
    const st = laneStyle(Number(line?.kind ?? LK_UNKNOWN));
    const baseW = st.wide ? w * 0.0048 : w * 0.0036;
    const offsets = st.double ? [-0.15, 0.15] : [0];

    for (const off of offsets) {
      // Glow is now deliberately faint; two thin strokes in perspective create
      // a "busy" picket-fence effect when the glow is thick.
      for (const pass of [
        { width: baseW * 1.7, color: st.glow },
        { width: baseW, color: st.color },
      ]) {
        ctx.strokeStyle = pass.color;
        ctx.fillStyle = pass.color;

        if (st.dots) {
          let z = Z_NEAR + (6.0 - (distM % 6.0)) % 6.0;
          for (; z < Z_FAR; z += 6.0) {
            const f = fn(z);
            if (f < 0.07) continue;
            const r = Math.max(0.6, pass.width * 0.45 * Math.max(0.25, f));
            ctx.beginPath();
            ctx.arc(xOf(z, lineLatAt(line, z) + off), yOf(z), r, 0, Math.PI * 2);
            ctx.fill();
          }
          continue;
        }

        let segs;
        if (st.dash) {
          segs = [];
          let z = Z_NEAR + (dashPeriod - phase) % dashPeriod;
          while (z < Z_FAR) {
            const z2 = z + DASH_LEN;
            if (z2 >= Z_FAR) break;
            segs.push([z, z2]);
            z = z2 + DASH_GAP;
          }
        } else {
          const zs = Z_STEPS.filter((z) => z >= Z_NEAR && z <= Z_FAR);
          segs = [];
          for (let i = 0; i < zs.length - 1; i++) segs.push([zs[i], zs[i + 1]]);
        }

        for (const [za, zb] of segs) {
          const zm = (za + zb) * 0.5;
          ctx.lineWidth = Math.max(1.0, pass.width * (0.32 + 0.68 * fn(zm)));
          ctx.beginPath();
          ctx.moveTo(xOf(za, lineLatAt(line, za) + off), yOf(za));
          ctx.lineTo(xOf(zb, lineLatAt(line, zb) + off), yOf(zb));
          ctx.stroke();
        }
      }
    }
  }
}

/* LDW: glowing orange line along the lane boundary the ego is drifting toward. */
function drawLdw(w, h, fn, yOf, xOf, geom, lineLatAt) {
  const st = lastState;
  if (!st?.started) return;
  if ((Number(st.speed_raw) || 0) < 3) return;  // not meaningful at a standstill
  const dev = laneDeviation(geom, lineLatAt);
  if (!dev) return;
  const pulse = 0.7 + 0.3 * Math.sin(performance.now() / 260);
  ctx.save();
  ctx.lineCap = "round";
  ctx.shadowColor = "rgba(255, 130, 30, 0.95)";
  ctx.shadowBlur = Math.max(8, w * 0.014);
  for (const pass of [
    { scale: 2.6, alpha: 0.5 * pulse * dev.ratio },
    { scale: 1.0, alpha: 0.95 * pulse * dev.ratio },
  ]) {
    ctx.strokeStyle = `rgba(255, 140, 40, ${Math.min(1, pass.alpha)})`;
    ctx.lineWidth = Math.max(2, w * 0.005 * pass.scale);
    ctx.beginPath();
    let first = true;
    for (const z of [4, 6, 9, 13, 18, 25, 33, 42]) {
      const x = xOf(z, lineLatAt(dev.line, z));
      if (first) { ctx.moveTo(x, yOf(z)); first = false; }
      else ctx.lineTo(x, yOf(z));
    }
    ctx.stroke();
  }
  ctx.restore();
}

/* Lane departure warning: deviation of the ego (lateral 0) from the innermost
   visible lane lines bracketing it, evaluated ~8 m ahead. */
function laneDeviation(geom, lineLatAt) {
  if (!geom) return null;
  const z = 8;
  const vis = [...geom.visible].sort((a, b) => a.y - b.y);
  if (vis.length < 2 && !geom.laneCenters) return null;
  const inner = (geom.edges[0] && geom.edges[1]) ? vis.filter((l) => l.arr !== geom.edges[0] && l.arr !== geom.edges[1]) : vis;
  const pool = inner.length >= 2 ? inner : vis;
  let li = null;
  let ri = null;
  for (const l of pool) {
    const y = lineLatAt(l, z);
    if (y < 0 && (li === null || y > lineLatAt(li, z))) li = l;
    if (y > 0 && (ri === null || y < lineLatAt(ri, z))) ri = l;
  }
  const yl = li ? lineLatAt(li, z) : null;
  const yr = ri ? lineLatAt(ri, z) : null;
  // Prefer the server-computed ego-lane centreline: unlike the midpoint of two
  // lines it survives one side dropping out, which is exactly when the warning
  // matters most.
  const center = geom.laneCenters
    ? sampleCurve(geom.laneCenters, geom.dists, z)
    : ((yl ?? -1.85) + (yr ?? 1.85)) / 2;
  const half = (yl != null && yr != null) ? (yr - yl) / 2 : 1.85;
  if (!(half >= 0.8)) return null;
  const dev = (0 - center) / half;          // -1 .. 1, + = drifting right
  const ratio = Math.max(0, Math.min(1, (Math.abs(dev) - 0.55) / 0.35));
  if (ratio <= 0) return null;
  const line = dev > 0 ? ri : li;
  if (!line) return null;
  return { side: dev > 0 ? 1 : -1, ratio, line };
}

/* Auto lane change: golden arch over the target lane while the blinker is on
   and openpilot is engaged. */
function drawAlcArch(w, h, cx, mToPx, fn, yOf, xOf, geom, lineLatAt) {
  const st = lastState;
  if (!st?.engaged) return;
  const sp = st.sp_hud || {};
  const side = sp.turn_signal_left ? -1 : sp.turn_signal_right ? 1 : 0;
  if (!side) return;
  // Target lane centre = the ego-lane centreline shifted one lane over, so the
  // arch follows road curvature instead of a fixed lateral offset.
  const baseAt = (z) => {
    let c = 0;
    if (geom && geom.laneCenters) c = sampleCurve(geom.laneCenters, geom.dists, z);
    return c + side * 1.85;
  };
  const pulse = 0.75 + 0.25 * Math.sin(performance.now() / 300);
  const zNear = 9;
  const zFar = 32;
  const N = 14;
  // half-width grows with distance then caps at one lane width; the whole band
  // is lifted off the road on a sine so it reads as an arch, not a stripe.
  const halfAt = (t) => Math.min(0.30 + t * 1.75, 1.80);
  const liftAt = (z) => (h - yOf(z)) * 0.055 * Math.sin(Math.PI * Math.max(0, Math.min(1, (z - zNear) / (zFar - zNear))));

  ctx.save();
  ctx.beginPath();
  for (let i = 0; i <= N; i++) {
    const t = i / N;
    const z = zNear + (zFar - zNear) * t;
    const x = xOf(z, baseAt(z) + halfAt(t));
    const y = yOf(z) - liftAt(z);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  for (let i = N; i >= 0; i--) {
    const t = i / N;
    const z = zNear + (zFar - zNear) * t;
    ctx.lineTo(xOf(z, baseAt(z) - halfAt(t)), yOf(z) - liftAt(z));
  }
  ctx.closePath();
  const ag = ctx.createLinearGradient(0, yOf(zNear), 0, yOf(zFar));
  ag.addColorStop(0, `rgba(255, 208, 88, ${0.44 * pulse})`);
  ag.addColorStop(0.6, `rgba(255, 190, 56, ${0.24 * pulse})`);
  ag.addColorStop(1, "rgba(255, 176, 40, 0)");
  ctx.fillStyle = ag;
  ctx.fill();
  // soft halo then a crisp leading edge
  ctx.strokeStyle = `rgba(255, 196, 70, ${0.28 * pulse})`;
  ctx.lineWidth = Math.max(4, w * 0.0045);
  ctx.stroke();
  ctx.strokeStyle = `rgba(255, 224, 140, ${0.9 * pulse})`;
  ctx.lineWidth = Math.max(1.4, w * 0.0016);
  ctx.stroke();
  ctx.restore();
}

/* Planned trajectory ribbon (Tesla-style rainbow). Data: state.road_model.path
   — modelV2.path sampled server-side at the same distances as the lane lines
   (model frame, +right). Ribbon half-width follows path.std (lateral
   uncertainty); hue sweeps pink-red near the ego car → yellow-green mid-range
   → cyan far, matching the model canvas rainbow gradient.

   Redesigned 2026-09: wider, brighter, drawn after lane lines so it sits on top
   of the road, with a crisp centre guide line so the intended path is obvious. */
function drawPlanPath(w, cx, mToPx, fn, yOf, xOf, geom, steps) {
  const path = geom?.path;
  if (!path || path.length < 3) return;
  const std = geom.pathStd;
  const z0 = steps[0];
  const z1 = steps[steps.length - 1];
  const dists = geom.dists;

  // Use a fixed comfortable lane-half width; path std only modulates the edge
  // softness, not the usable width, so the ribbon remains visible even when
  // uncertainty is low.
  const halfAt = (z) => {
    let s = 0.12;
    if (std) s = sampleCurve(std, dists, z);
    return Math.max(0.55, Math.min(0.95, 0.58 + s * 0.55));
  };
  const hueAt = (z) => {
    const t = Math.max(0, Math.min(1, (z - z0) / 90));
    return (330 + t * 210) % 360;
  };
  const alphaAt = (z) => {
    const t = Math.max(0, Math.min(1, (z - z0) / (z1 - z0)));
    // Brighter near the car, soft glow far away
    return 0.34 + 0.46 * Math.pow(1 - t, 0.6);
  };

  ctx.save();
  ctx.lineJoin = "round";

  // Outer glow: large, additive, drawn first so the ribbon pops against asphalt.
  ctx.globalCompositeOperation = "lighter";
  ctx.beginPath();
  for (let i = 0; i < steps.length; i++) {
    const z = steps[i];
    const x = xOf(z, sampleCurve(path, dists, z));
    if (i === 0) ctx.moveTo(x, yOf(z));
    else ctx.lineTo(x, yOf(z));
  }
  ctx.strokeStyle = "rgba(255, 80, 160, 0.28)";
  ctx.shadowColor = "rgba(255, 60, 140, 0.85)";
  ctx.shadowBlur = Math.max(14, w * 0.022);
  ctx.lineWidth = Math.max(6, w * 0.018);
  ctx.stroke();
  ctx.globalCompositeOperation = "source-over";

  // Ribbon segments, one quad per step pair, colored by distance.
  for (let i = 0; i < steps.length - 1; i++) {
    const za = steps[i];
    const zb = steps[i + 1];
    const zm = (za + zb) * 0.5;
    const hue = hueAt(zm);
    const alpha = alphaAt(zm);
    ctx.beginPath();
    ctx.moveTo(xOf(za, sampleCurve(path, dists, za) - halfAt(za)), yOf(za));
    ctx.lineTo(xOf(zb, sampleCurve(path, dists, zb) - halfAt(zb)), yOf(zb));
    ctx.lineTo(xOf(zb, sampleCurve(path, dists, zb) + halfAt(zb)), yOf(zb));
    ctx.lineTo(xOf(za, sampleCurve(path, dists, za) + halfAt(za)), yOf(za));
    ctx.closePath();
    ctx.fillStyle = `hsla(${hue.toFixed(0)}, 95%, 65%, ${alpha.toFixed(3)})`;
    ctx.fill();

    // Soft inner edge shadow to separate ribbon from lane paint.
    ctx.strokeStyle = `hsla(${hue.toFixed(0)}, 90%, 45%, ${(alpha * 0.55).toFixed(3)})`;
    ctx.lineWidth = Math.max(1, w * 0.0016);
    ctx.stroke();
  }

  // Crisp centre guide line — this is what the driver actually follows.
  ctx.beginPath();
  for (let i = 0; i < steps.length; i++) {
    const z = steps[i];
    const x = xOf(z, sampleCurve(path, dists, z));
    if (i === 0) ctx.moveTo(x, yOf(z));
    else ctx.lineTo(x, yOf(z));
  }
  ctx.strokeStyle = "rgba(255, 255, 255, 0.82)";
  ctx.shadowColor = "rgba(255, 255, 255, 0.55)";
  ctx.shadowBlur = Math.max(4, w * 0.005);
  ctx.lineWidth = Math.max(1.4, w * 0.0024);
  ctx.stroke();

  ctx.restore();
}

function drawPoles(w, h, cx, mToPx, fn, yOf, xOf, edgeLatAt) {
  const horizonBase = h * HORIZON;
  ctx.lineCap = "round";
  // scroll toward the viewer: apparent distance shrinks as the car advances
  let z = 6 + (POLE_SPACING - (distM % POLE_SPACING)) % POLE_SPACING;
  for (; z < POLE_RANGE; z += POLE_SPACING) {
    if (z > Z_FAR) break;
    const f = fn(z);
    if (f < 0.02) continue;
    const y = yOf(z);
    const poleH = Math.min((h - horizonBase) * 1.05 * f, y - h * 0.06);
    const alpha = Math.max(0, Math.min(0.6, f * 2.4));
    for (const side of [-1, 1]) {
      // poles stand off the carriageway, arm reaching back over the road
      const px = xOf(z, edgeLatAt(side, z) + side * 1.7);
      const topY = y - poleH;
      // pole
      ctx.strokeStyle = `rgba(125, 138, 162, ${alpha})`;
      ctx.lineWidth = Math.max(1.5, w * 0.0028 * f);
      ctx.beginPath();
      ctx.moveTo(px, y);
      ctx.lineTo(px, topY);
      ctx.stroke();
      // arm reaching over the road
      const armDx = -side * mToPx * 1.6 * f;
      ctx.beginPath();
      ctx.moveTo(px, topY);
      ctx.quadraticCurveTo(px + armDx * 0.4, topY - poleH * 0.06, px + armDx, topY - poleH * 0.02);
      ctx.stroke();
      // lamp glow
      const lampX = px + armDx;
      const lampY = topY - poleH * 0.02;
      const lampR = Math.max(4, w * 0.012 * f);
      const lg = ctx.createRadialGradient(lampX, lampY, 0, lampX, lampY, lampR * 2.4);
      lg.addColorStop(0, `rgba(210, 225, 255, ${alpha * 1.4})`);
      lg.addColorStop(0.35, `rgba(190, 210, 255, ${alpha * 0.5})`);
      lg.addColorStop(1, "rgba(190, 210, 255, 0)");
      ctx.fillStyle = lg;
      ctx.beginPath();
      ctx.arc(lampX, lampY, lampR * 2.4, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

/* ---------- perception ---------- */

/* Radar track history, used to differentiate each track's position over time
   into a heading. Keyed by trackId; pruned so the map cannot grow unbounded. */
const trackHist = new Map();
let trackHistStamp = 0;

function pruneTrackHist(now, liveIds) {
  if (now - trackHistStamp < 5000) return;
  trackHistStamp = now;
  for (const id of [...trackHist.keys()]) {
    if (!liveIds.has(id)) trackHist.delete(id);
  }
}

/* Heading of a visual lead, from the first two samples of its predicted
   trajectory. `y` is model-frame +right, so it is negated to the left-positive
   convention used everywhere else. Result: 0 = receding straight ahead,
   ±π/2 = crossing, |θ| > π/2 = oncoming. null when the trajectory is too
   short or degenerate. */
function leadHeading(x, y) {
  try {
    if (!x || !y || x.length < 2 || y.length < 2) return null;
    const dx = Number(x[1]) - Number(x[0]);
    const dy = Number(y[1]) - Number(y[0]);
    if (!Number.isFinite(dx) || !Number.isFinite(dy)) return null;
    if (Math.abs(dx) < 1e-3 && Math.abs(dy) < 1e-3) return null;
    return -Math.atan2(dy, dx);
  } catch {
    return null;
  }
}

/* Heading of a radar track from its own frame-to-frame motion. The track's
   absolute forward speed is (dRel rate + ego speed); the lateral rate needs no
   correction since the ego does not translate sideways in its own frame. */
function trackHeading(id, d, offM, now, vEgo) {
  const prev = trackHist.get(id);
  trackHist.set(id, { d, offM, t: now });
  if (!prev) return null;
  const dt = (now - prev.t) / 1000;
  if (dt < 0.08 || dt > 3.0) return null;
  const vd = (d - prev.d) / dt;          // + = opening (target pulling away)
  const vy = (offM - prev.offM) / dt;    // + = moving left
  const vfwd = vd + vEgo;                // absolute forward speed of the object
  if (Math.abs(vfwd) < 0.4 && Math.abs(vy) < 0.4) return null;
  return Math.atan2(vy, vfwd);
}

/* Cosmetic object class. cereal carries no class field for any target, so this
   is a heuristic over the only evidence available — kinematics and the size
   proxies xStd / yStd. The default is a car and every special branch requires
   strong (slow, short, wobbly) evidence, so uncertainty degrades to "car"
   rather than inventing a pedestrian. Nothing here feeds the vehicle. */
function classifyTarget(k) {
  // Radar carries no size or class evidence whatsoever, so those tracks are
  // always cars — inventing a pedestrian from a bare (dRel, yRel, vRel) triple
  // would be guesswork presented as fact.
  if (k.radarOnly) return OBJ_CAR;
  const v = Math.abs(Number(k.v) || 0);
  const xStd = Number(k.xStd) || 0;
  const yStd = Number(k.yStd) || 0;
  if (xStd > 1.6) return OBJ_TRUCK;
  const nearEdge = Math.abs(k.offM) > 3.0;
  // At highway speeds a stationary roadside blob is almost never a pedestrian;
  // degrading it to a car avoids alarming false positives.
  const vEgoKph = (Math.max(0, Number(lastState?.speed_raw) || 0)) * 3.6;
  if (v < 2.2 && (nearEdge || (Number(k.d) || 0) < 26) && vEgoKph < 70) return OBJ_PED;
  if (v < 10.5 && yStd > 0.75 && xStd < 1.0) return v < 5.6 ? OBJ_BIKE : OBJ_EBIKE;
  if (v < 13 && xStd < 0.7 && yStd < 0.6) return OBJ_MOTO;
  return OBJ_CAR;
}

/* Physical footprint per class, metres: [lateral, longitudinal]. */
const OBJ_SIZE = {
  [OBJ_CAR]: [1.85, 4.6],
  [OBJ_TRUCK]: [2.5, 11.0],
  [OBJ_BIKE]: [0.7, 1.8],
  [OBJ_EBIKE]: [0.8, 1.9],
  [OBJ_MOTO]: [0.85, 2.15],
  [OBJ_PED]: [0.6, 0.6],
  [OBJ_UNKNOWN]: [1.85, 4.6],
};

function drawPerception(w, cx, mToPx, fn, yOf) {
  const st = lastState;
  if (!st) return;
  const bsm = bsmSides();
  const vEgo = Math.max(0, Number(st.speed_raw) || 0);
  const now = performance.now();
  const rm = st?.road_model;
  const leads = Array.isArray(rm?.leads) ? rm.leads : [];

  const sideOf = (offM) => (offM >= 0 ? bsm.left : bsm.right);
  const placed = [];   // {d, offM} of everything already drawn, for dedupe

  const near = (d, offM, tolD, tolY) => placed.some((p) => Math.abs(p.d - d) < tolD && Math.abs(p.offM - offM) < tolY);

  /* Road-edge aware lateral gate. HALF_ROAD_M is the default three-lane
     half-width; when model edges are available the scene uses those, so we
     clip perceived targets to the same envelope. This keeps radar noise and
     dropped tracks from being painted on the shoulder / beyond the road. */
  const LAT_GATE_M = HALF_ROAD_M;

  /* 1) full radar track list: front-left / front-right and flanking objects.
        radarState only exposes leadOne/leadTwo, so without this the adjacent
        lanes stay empty. Deduped against the leads drawn below. */
  const tracks = Array.isArray(st.radar_tracks) ? st.radar_tracks : [];
  const liveIds = new Set();
  for (const t of tracks) {
    const d = Number(t?.d);
    const offM = Number(t?.y);
    if (!Number.isFinite(d) || !Number.isFinite(offM)) continue;
    if (d <= 1.0 || d > 120) continue;
    if (Math.abs(offM) > LAT_GATE_M) continue;
    const id = t?.id;
    liveIds.add(id);
    const heading = trackHeading(id, d, offM, now, vEgo);
    if (near(d, offM, 5, 1.2)) continue;
    // a track that lines up with the ego-lane lead is the same vehicle
    const dl = Number(st.lead_d_rel);
    if (Number.isFinite(dl) && Math.abs(offM) < 1.9 && Math.abs(d - dl) < 7) continue;
    const classId = classifyTarget({ d, offM, v: Number(t?.v) + vEgo, xStd: 0, yStd: 0, radarOnly: true });
    placed.push({ d, offM });
    drawTarget(w, cx, mToPx, fn, yOf, {
      d, offM, classId, heading, alphaMul: 0.55, bsm: sideOf(offM),
    });
  }
  pruneTrackHist(now, liveIds);

  /* 2) visual leads (leadsV3, up to 3): ego-lane plus adjacent. */
  for (const ml of leads) {
    const d = Number(ml?.d);
    const y = Number(ml?.y);
    if (!Number.isFinite(d) || !Number.isFinite(y)) continue;
    const offM = Math.max(-LAT_GATE_M, Math.min(LAT_GATE_M, -y));   // +left like radar yRel
    if (near(d, offM, 6, 1.8)) continue;
    placed.push({ d, offM });
    const classId = classifyTarget({ d, offM, v: ml.v, xStd: ml.x_std, yStd: ml.y_std });
    drawTarget(w, cx, mToPx, fn, yOf, {
      d, offM, classId, heading: ml.heading ?? null,
      alphaMul: 0.68, bsm: sideOf(offM),
      diag: { v: ml.v, xStd: ml.x_std, yStd: ml.y_std },
    });
  }

  /* 3) radar leadTwo — the secondary adjacent-lane lead, kept even when the
        full track list is unavailable (some cars report tracks only for a
        subset of objects). */
  if (st.lead2_d_rel != null && st.lead2_d_rel > 0 && st.lead2_d_rel <= 140) {
    const offM = Math.max(-LAT_GATE_M, Math.min(LAT_GATE_M, Number(st.lead2_y_rel) || 0));
    if (!near(st.lead2_d_rel, offM, 5, 1.4)) {
      placed.push({ d: st.lead2_d_rel, offM });
      drawTarget(w, cx, mToPx, fn, yOf, {
        d: st.lead2_d_rel, offM, classId: OBJ_CAR, heading: null,
        alphaMul: 0.55, bsm: sideOf(offM),
      });
    }
  }

  /* 4) the ego-lane lead last, so it always wins an overlap: radar is the most
        reliable source and its brake lights follow aLeadK. */
  const leadBrake = Number(st?.lead_a_lead_k) < -0.5;
  drawTarget(w, cx, mToPx, fn, yOf, {
    d: st.lead_d_rel, offM: 0, classId: OBJ_CAR, heading: null,
    alphaMul: 1.0, bsm: false,
    brake: leadBrake, risk: collisionRisk(), diag: null,
  });
}

/* Thin wrapper kept for readability: resolve the screen box for a target and
   hand off to the class-specific sprite. */
function drawTarget(w, cx, mToPx, fn, yOf, o) {
  if (o.d == null || !(Number(o.d) > 0)) return;
  if (Math.abs(o.offM) > 6.0) return;
  drawObject(w, cx, mToPx, fn, yOf, o.d, o.offM, {
    classId: o.classId, heading: o.heading, alphaMul: o.alphaMul,
    bsm: o.bsm, brake: o.brake, risk: o.risk, diag: o.diag,
  });
}

/* Debug overlay: `?objdiag=1` prints the raw kinematic evidence per target so
   the classifyTarget() thresholds can be tuned against real drives. */
function diagEnabled() {
  try {
    return new URLSearchParams(window.location.search).get("objdiag") === "1";
  } catch {
    return false;
  }
}


/* Forward collision risk 0..1 — TTC from radar closing speed, forced to 1
   when openpilot raises an fcw/aeb alert. */
function collisionRisk() {
  const st = lastState;
  if (!st?.started) return 0;
  const alertStatus = String(st.alert?.status || "");
  const aeb = alertStatus === "aeb" || alertStatus === "fcw";
  const d = Number(st.lead_d_rel);
  const v = Number(st.lead_v_rel);
  let risk = 0;
  if (Number.isFinite(d) && Number.isFinite(v) && d > 0 && v < -0.3) {
    const ttc = d / (-v);
    if (ttc < 3) risk = Math.min(1, (3 - ttc) / 2.4);
  }
  return aeb ? 1 : risk;
}

function bsmSides() {
  const sp = lastState?.sp_hud || {};
  return { left: !!sp.blindspot_left, right: !!sp.blindspot_right };
}

/* BSM (blind spot) indicator: amber edge glow + chevrons on the active side.
   Data: state.sp_hud.blindspot_left / blindspot_right (stock BSM radar). */
function drawBsm(w, h) {
  const { left, right } = bsmSides();
  if (!left && !right) return;
  const pulse = 0.72 + 0.28 * Math.sin(performance.now() / 280);

  for (const [side, on] of [[-1, left], [1, right]]) {
    if (!on) continue;
    const x0 = side < 0 ? 0 : w * 0.90;
    const x1 = side < 0 ? w * 0.10 : w;

    // Amber edge glow column. Brightest *at the screen edge* and fading
    // inward — the original gradient ran edge-ward for the left side but
    // inward-to-outward on the right, so the right glow faded out exactly where
    // it should have been strongest and had a hard cut where it should have
    // been invisible.
    const a = `rgba(255, 168, 44, ${0.30 * pulse})`;
    const grad = ctx.createLinearGradient(x0, 0, x1, 0);
    if (side < 0) {
      grad.addColorStop(0, a);
      grad.addColorStop(1, "rgba(255, 168, 44, 0)");
    } else {
      grad.addColorStop(0, "rgba(255, 168, 44, 0)");
      grad.addColorStop(1, a);
    }
    ctx.fillStyle = grad;
    ctx.fillRect(x0, h * 0.40, x1 - x0, h * 0.54);

    // chevrons pointing toward the ego lane
    const ix = side < 0 ? w * 0.040 : w * 0.960;
    const iy = h * 0.66;
    ctx.save();
    ctx.translate(ix, iy);
    ctx.scale(side, 1);
    ctx.strokeStyle = `rgba(255, 182, 66, ${0.95 * pulse})`;
    ctx.shadowColor = "rgba(255, 160, 30, 0.9)";
    ctx.shadowBlur = Math.max(6, w * 0.014);
    ctx.lineWidth = Math.max(3, w * 0.0065);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    for (let i = 0; i < 2; i++) {
      const bx = i * w * 0.024;
      ctx.beginPath();
      ctx.moveTo(bx, -w * 0.017);
      ctx.lineTo(bx + w * 0.019, 0);
      ctx.lineTo(bx, w * 0.017);
      ctx.stroke();
    }
    ctx.restore();
    ctx.shadowBlur = 0;
  }
}

/* Project one perceived object onto the road and dispatch to the sprite for
   its class. The box comes from the class footprint in metres pushed through
   the same pinhole scale as the road, so perspective does the work instead of a
   hand-tuned per-distance fudge factor. */
function drawObject(w, cx, mToPx, fn, yOf, d, offM, o) {
  if (d == null || !(d > 0) || d > 160) return;
  const z = Math.max(d, 0.5) + Z_NEAR;
  const f = fn(z);
  if (f <= 0.012) return;
  const s = OBJ_SIZE[o.classId] || OBJ_SIZE[OBJ_UNKNOWN];
  const groundY = yOf(z);
  const sw = Math.max(5, Math.min(w * 0.26, s[0] * mToPx * f));
  const sh = Math.max(4, Math.min(w * 0.34, s[1] * mToPx * f * 0.55));
  // Clamp laterally to the road surface so a noisy track beyond the edge is
  // not drawn on the shoulder. HALF_ROAD_M is the default three-lane half-width;
  // the lane-line rendering already respects model edges when available.
  const xCenter = Math.max(cx - mToPx * HALF_ROAD_M * f, Math.min(cx + mToPx * HALF_ROAD_M * f, cx - offM * mToPx * f));

  const baseAlpha = Math.max(0.28, Math.min(1, (1.15 - d / 160) * (o.alphaMul ?? 1)));
  ctx.save();
  ctx.globalAlpha = o.bsm ? Math.min(1, baseAlpha + 0.25) : baseAlpha;

  // contact shadow
  ctx.fillStyle = "rgba(0, 0, 0, 0.45)";
  ctx.beginPath();
  ctx.ellipse(xCenter, groundY, sw * 0.64, Math.max(1.4, sh * 0.15), 0, 0, Math.PI * 2);
  ctx.fill();

  const bx = xCenter - sw / 2;
  const by = groundY;                    // rear baseline; nose points up (-y)
  const opts = { tone: "lead", bsm: !!o.bsm, brake: !!o.brake, risk: o.risk || 0 };

  switch (o.classId) {
    case OBJ_TRUCK: drawTruckSprite(bx, by, sw, sh, opts); break;
    case OBJ_BIKE: drawBikeSprite(bx, by, sw, sh, opts, false); break;
    case OBJ_EBIKE: drawBikeSprite(bx, by, sw, sh, opts, true); break;
    case OBJ_MOTO: drawMotoSprite(bx, by, sw, sh, opts); break;
    case OBJ_PED: drawPedSprite(bx, by, sw, sh, opts); break;
    default: drawCarSprite(bx, by, sw, sh, opts);
  }

  const anchorTop = by - sh * (o.classId === OBJ_PED ? 1.15 : 1.06);
  drawHeadingArrow(xCenter, anchorTop, Math.max(5, sh * 0.40), o.heading);
  ctx.restore();

  if (diagEnabled() && o.diag) {
    ctx.save();
    ctx.globalAlpha = 0.88;
    ctx.fillStyle = "#9fe8ff";
    ctx.font = `600 ${Math.max(9, Math.min(13, sh * 0.36))}px ui-monospace, monospace`;
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    ctx.fillText(
      `${o.classId} d${Math.round(d)} v${(Number(o.diag.v) || 0).toFixed(1)}`
      + ` xs${(Number(o.diag.xStd) || 0).toFixed(2)} ys${(Number(o.diag.yStd) || 0).toFixed(2)}`,
      xCenter, anchorTop - sh * 0.25,
    );
    ctx.restore();
  }
}

/* Direction chevron in front of a target. `heading` is left-positive radians in
   the ego frame (0 = receding straight ahead) → screen direction (-sin, -cos),
   so ahead maps to up, left to -x, oncoming to down. Oncoming targets are
   tinted red so they read at a glance. */
function drawHeadingArrow(cx, y, size, heading) {
  if (heading == null || !Number.isFinite(heading)) return;
  if (Math.abs(heading) < 0.12) return;        // dead-ahead: the sprite says enough
  const oncoming = Math.abs(heading) > Math.PI * 0.62;
  const ux = -Math.sin(heading);
  const uy = -Math.cos(heading);
  const color = oncoming ? "rgba(255, 104, 84, 0.95)" : "rgba(150, 224, 255, 0.92)";
  ctx.save();
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.shadowColor = color;
  ctx.shadowBlur = size * 0.5;
  ctx.lineWidth = Math.max(1.3, size * 0.20);
  ctx.beginPath();
  ctx.moveTo(cx - ux * size * 0.42, y - uy * size * 0.42);
  ctx.lineTo(cx + ux * size * 0.52, y + uy * size * 0.52);
  ctx.stroke();
  const hx = cx + ux * size * 0.52;
  const hy = y + uy * size * 0.52;
  ctx.beginPath();
  ctx.moveTo(hx + ux * size * 0.30, hy + uy * size * 0.30);
  ctx.lineTo(hx - uy * size * 0.24, hy + ux * size * 0.24);
  ctx.lineTo(hx + uy * size * 0.24, hy - ux * size * 0.24);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

/* BSM amber outline and collision red pulse, shared by every sprite. pathFn
   must build its own path (beginPath … closePath). */
function applyAlerts(pathFn, refW, opts) {
  if (opts.bsm) {
    ctx.strokeStyle = "rgba(255, 182, 66, 0.95)";
    ctx.shadowColor = "rgba(255, 160, 30, 0.85)";
    ctx.shadowBlur = Math.max(6, refW * 0.22);
    ctx.lineWidth = Math.max(1.5, refW * 0.05);
    pathFn();
    ctx.stroke();
    ctx.shadowBlur = 0;
  }
  if (opts.risk > 0.35) {
    const pulse = 0.7 + 0.3 * Math.sin(performance.now() / 160);
    ctx.strokeStyle = `rgba(255, 46, 30, ${Math.min(1, 0.55 + 0.45 * pulse)})`;
    ctx.shadowColor = "rgba(255, 30, 20, 0.95)";
    ctx.shadowBlur = Math.max(8, refW * 0.30);
    ctx.lineWidth = Math.max(2, refW * 0.06);
    pathFn();
    ctx.stroke();
    ctx.shadowBlur = 0;
  }
}

/* Box truck / lorry: cab at the front, ribbed trailer behind, multi-axle. */
function drawTruckSprite(x, y, cw, ch, opts) {
  ctx.fillStyle = "#0a0e18";
  const ww = Math.max(2, cw * 0.11);
  const wh = Math.max(1.6, ch * 0.055);
  for (const cy of [0.075, 0.28, 0.42, 0.86]) {
    const wy = y - ch * cy - wh;
    for (const wx of [x - ww * 0.5, x + cw - ww * 0.5]) {
      roundRect(wx, wy, ww, wh, ww * 0.35);
      ctx.fill();
    }
  }

  const tg = ctx.createLinearGradient(x, y - ch, x + cw, y);
  tg.addColorStop(0, "#66799f");
  tg.addColorStop(0.5, "#414f73");
  tg.addColorStop(1, "#2a3450");
  ctx.fillStyle = tg;
  roundRect(x + cw * 0.02, y - ch * 0.66, cw * 0.96, ch * 0.63, cw * 0.08);
  ctx.fill();
  ctx.strokeStyle = "rgba(170, 192, 228, 0.32)";
  ctx.lineWidth = Math.max(1, cw * 0.016);
  ctx.stroke();

  ctx.strokeStyle = "rgba(16, 22, 38, 0.38)";
  ctx.lineWidth = Math.max(0.7, cw * 0.012);
  for (let i = 1; i <= 4; i++) {
    const ry = y - ch * (0.66 - i * 0.115);
    ctx.beginPath();
    ctx.moveTo(x + cw * 0.07, ry);
    ctx.lineTo(x + cw * 0.93, ry);
    ctx.stroke();
  }

  const cg = ctx.createLinearGradient(x, y - ch, x + cw, y);
  cg.addColorStop(0, "#8296bd");
  cg.addColorStop(1, "#3b4869");
  ctx.fillStyle = cg;
  roundRect(x + cw * 0.11, y - ch, cw * 0.78, ch * 0.35, cw * 0.10);
  ctx.fill();
  ctx.fillStyle = "rgba(11, 17, 30, 0.92)";
  roundRect(x + cw * 0.21, y - ch * 0.985, cw * 0.58, ch * 0.12, cw * 0.05);
  ctx.fill();

  ctx.shadowColor = "rgba(255, 66, 50, 0.9)";
  ctx.shadowBlur = opts.brake ? cw * 0.34 : Math.max(4, cw * 0.13);
  ctx.fillStyle = opts.brake ? "#ff4a38" : "rgba(255, 82, 64, 0.9)";
  for (const tx of [x + cw * 0.05, x + cw * 0.74]) {
    roundRect(tx, y - ch * 0.045, cw * 0.21, Math.max(1.8, ch * 0.028), ch * 0.014);
    ctx.fill();
  }
  ctx.shadowBlur = 0;

  applyAlerts(() => {
    ctx.beginPath();
    roundRect(x + cw * 0.02, y - ch, cw * 0.96, ch, cw * 0.09);
  }, cw, opts);
}

/* Bicycle (isEbike=false) and e-bike / scooter (isEbike=true): two wheels, a
   slim frame, handlebar and a rider seen from above. */
function drawBikeSprite(x, y, cw, ch, opts, isEbike) {
  const ccx = x + cw / 2;
  ctx.fillStyle = "#0a0e18";
  const wr = Math.max(1.5, cw * 0.30);
  const wrH = Math.max(2.0, ch * 0.20);
  for (const wy of [y - ch * 0.87, y - ch * 0.15]) {
    ctx.beginPath();
    ctx.ellipse(ccx, wy, wr, wrH, 0, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.strokeStyle = isEbike ? "#c8963e" : "#93a8cc";
  ctx.lineWidth = Math.max(1, cw * 0.09);
  ctx.lineCap = "round";
  ctx.beginPath();
  ctx.moveTo(ccx, y - ch * 0.15);
  ctx.lineTo(ccx, y - ch * 0.87);
  ctx.stroke();
  ctx.lineWidth = Math.max(1, cw * 0.11);
  ctx.beginPath();
  ctx.moveTo(ccx - cw * 0.42, y - ch * 0.90);
  ctx.lineTo(ccx + cw * 0.42, y - ch * 0.90);
  ctx.stroke();

  if (isEbike) {
    ctx.fillStyle = "rgba(255, 214, 140, 0.85)";
    roundRect(ccx - cw * 0.26, y - ch * 0.34, cw * 0.52, ch * 0.13, cw * 0.04);
    ctx.fill();
  }

  ctx.fillStyle = isEbike ? "#d0a151" : "#6c8cc4";
  ctx.beginPath();
  ctx.ellipse(ccx, y - ch * 0.52, cw * 0.40, ch * 0.21, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#e2d4c0";
  ctx.beginPath();
  ctx.arc(ccx, y - ch * 0.65, Math.max(1.2, cw * 0.19), 0, Math.PI * 2);
  ctx.fill();

  applyAlerts(() => {
    ctx.beginPath();
    ctx.ellipse(ccx, y - ch * 0.50, cw * 0.64, ch * 0.56, 0, 0, Math.PI * 2);
  }, cw, opts);
}

/* Motorcycle: wider body, rider with a helmet, tail light. */
function drawMotoSprite(x, y, cw, ch, opts) {
  const ccx = x + cw / 2;
  ctx.fillStyle = "#0a0e18";
  const wr = Math.max(1.8, cw * 0.31);
  const wrH = Math.max(2.2, ch * 0.18);
  for (const wy of [y - ch * 0.86, y - ch * 0.16]) {
    ctx.beginPath();
    ctx.ellipse(ccx, wy, wr, wrH, 0, 0, Math.PI * 2);
    ctx.fill();
  }

  const mg = ctx.createLinearGradient(x, y - ch, x + cw, y);
  mg.addColorStop(0, "#5f73a0");
  mg.addColorStop(1, "#2c3653");
  ctx.fillStyle = mg;
  roundRect(ccx - cw * 0.34, y - ch * 0.79, cw * 0.68, ch * 0.62, cw * 0.22);
  ctx.fill();
  ctx.fillStyle = "rgba(202, 218, 246, 0.18)";
  roundRect(ccx - cw * 0.22, y - ch * 0.64, cw * 0.44, ch * 0.20, cw * 0.09);
  ctx.fill();

  ctx.fillStyle = "#7f95c2";
  ctx.beginPath();
  ctx.ellipse(ccx, y - ch * 0.49, cw * 0.42, ch * 0.19, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#cbd8f0";
  ctx.beginPath();
  ctx.arc(ccx, y - ch * 0.63, Math.max(1.4, cw * 0.23), 0, Math.PI * 2);
  ctx.fill();

  ctx.shadowColor = "rgba(255, 66, 50, 0.9)";
  ctx.shadowBlur = opts.brake ? cw * 0.5 : Math.max(3, cw * 0.19);
  ctx.fillStyle = opts.brake ? "#ff4a38" : "rgba(255, 92, 72, 0.9)";
  roundRect(ccx - cw * 0.14, y - ch * 0.09, cw * 0.28, Math.max(1.4, ch * 0.045), ch * 0.022);
  ctx.fill();
  ctx.shadowBlur = 0;

  applyAlerts(() => {
    ctx.beginPath();
    ctx.ellipse(ccx, y - ch * 0.50, cw * 0.68, ch * 0.58, 0, 0, Math.PI * 2);
  }, cw, opts);
}

/* Pedestrian seen from above: head, shoulders and swinging arms. Only ever
   drawn when the kinematic evidence is strong (see classifyTarget). */
function drawPedSprite(x, y, cw, ch, opts) {
  const ccx = x + cw / 2;
  const cy = y - ch * 0.5;

  const pg = ctx.createLinearGradient(x, y - ch, x + cw, y);
  pg.addColorStop(0, "#8899bd");
  pg.addColorStop(1, "#404d6b");
  ctx.fillStyle = pg;
  ctx.beginPath();
  ctx.ellipse(ccx, cy + ch * 0.10, cw * 0.46, ch * 0.33, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = "#6d7fa6";
  ctx.lineWidth = Math.max(1, cw * 0.13);
  ctx.lineCap = "round";
  for (const sd of [-1, 1]) {
    ctx.beginPath();
    ctx.moveTo(ccx + sd * cw * 0.36, cy + ch * 0.05);
    ctx.lineTo(ccx + sd * cw * 0.54, cy + ch * 0.48);
    ctx.stroke();
  }

  ctx.fillStyle = "#ddccb5";
  ctx.beginPath();
  ctx.arc(ccx, cy - ch * 0.24, Math.max(1.5, cw * 0.30), 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "rgba(32, 42, 62, 0.5)";
  ctx.lineWidth = Math.max(0.6, cw * 0.05);
  ctx.stroke();

  applyAlerts(() => {
    ctx.beginPath();
    ctx.ellipse(ccx, cy + ch * 0.06, cw * 0.72, ch * 0.62, 0, 0, Math.PI * 2);
  }, cw, opts);
}

function drawEgoCar(w, h, cx) {
  const carW = w * 0.15;
  const carH = carW * 0.62;
  const y = h * 0.955;                // bottom anchor (rear bumper)
  const x = cx - carW / 2;

  ctx.save();

  // Stronger underglow for the ego car so it feels anchored and "present".
  const ug = ctx.createRadialGradient(cx, y - carH * 0.4, 0, cx, y - carH * 0.4, carW * 1.05);
  ug.addColorStop(0, "rgba(70, 160, 255, 0.28)");
  ug.addColorStop(0.55, "rgba(60, 130, 220, 0.10)");
  ug.addColorStop(1, "rgba(60, 130, 220, 0)");
  ctx.fillStyle = ug;
  ctx.fillRect(cx - carW * 1.2, y - carH * 1.9, carW * 2.4, carH * 2.5);

  const braking = lastState?.a_ego != null && Number(lastState.a_ego) < -0.6;
  drawCarSprite(x, y, carW, carH, { tone: "ego", brake: braking });

  // turn indicators: flashing amber lamps at the ego rear corners
  const sp = lastState?.sp_hud || {};
  const blinkOn = Math.floor(performance.now() / 400) % 2 === 0;
  if (blinkOn) {
    ctx.fillStyle = "rgba(255, 190, 45, 0.98)";
    ctx.shadowColor = "rgba(255, 170, 30, 0.95)";
    ctx.shadowBlur = Math.max(8, carW * 0.22);
    const lampR = Math.max(3, carW * 0.065);
    if (sp.turn_signal_left) {
      ctx.beginPath();
      ctx.arc(x + carW * 0.025, y - carH * 0.06, lampR, 0, Math.PI * 2);
      ctx.fill();
    }
    if (sp.turn_signal_right) {
      ctx.beginPath();
      ctx.arc(x + carW * 0.975, y - carH * 0.06, lampR, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.shadowBlur = 0;
  }

  ctx.restore();
}

/* Modern top-down vehicle glyph: a simplified, softly-lit rounded capsule
   inspired by FSD/Autopilot visualizations. Fewer details, stronger silhouette,
   and a glowing rim so vehicles read instantly against the dark road.

   The shape is defined by one rounded rect plus a tapered nose; it replaces the
   previous detailed sedan outline which looked flat and noisy at small sizes. */

function carBodyPath(x, y, carW, carH) {
  // x: left edge, y: rear bumper baseline; nose points up (-y)
  const r = carW * 0.22;
  const noseR = carW * 0.38;
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + carW - r, y);
  ctx.quadraticCurveTo(x + carW, y, x + carW, y - r);
  ctx.lineTo(x + carW, y - carH + noseR);
  // tapered nose
  ctx.quadraticCurveTo(x + carW, y - carH, x + carW * 0.82, y - carH);
  ctx.lineTo(x + carW * 0.18, y - carH);
  ctx.quadraticCurveTo(x, y - carH, x, y - carH + noseR);
  ctx.lineTo(x, y - r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function drawCarSprite(x, y, carW, carH, opts = {}) {
  const ego = opts.tone === "ego";
  const body = () => carBodyPath(x, y, carW, carH);

  // Soft underglow / rim light (drawn first so it sits behind the body).
  ctx.save();
  ctx.shadowColor = ego ? "rgba(80, 190, 255, 0.75)" : "rgba(140, 175, 230, 0.45)";
  ctx.shadowBlur = ego ? Math.max(14, carW * 0.35) : Math.max(8, carW * 0.22);
  ctx.strokeStyle = "rgba(0,0,0,0)";
  ctx.lineWidth = Math.max(2, carW * 0.06);
  body();
  ctx.stroke();
  ctx.restore();

  // Body fill: dark, slightly cool, with a subtle vertical gradient so the
  // capsule has volume without drawing windows/mirrors.
  const bg = ctx.createLinearGradient(x, y - carH, x + carW, y);
  if (ego) {
    bg.addColorStop(0, "#2b3a5e");
    bg.addColorStop(0.55, "#1d2745");
    bg.addColorStop(1, "#111829");
  } else {
    bg.addColorStop(0, "#384668");
    bg.addColorStop(0.55, "#252f4d");
    bg.addColorStop(1, "#151d33");
  }
  body();
  ctx.fillStyle = bg;
  ctx.fill();

  // Bright rim stroke — the main readable feature.
  ctx.strokeStyle = ego ? "rgba(110, 200, 255, 0.82)" : "rgba(180, 205, 245, 0.62)";
  ctx.lineWidth = Math.max(1.4, carW * 0.026);
  body();
  ctx.stroke();

  // BSM alert: amber outline + stronger glow
  if (opts.bsm) {
    ctx.save();
    ctx.strokeStyle = "rgba(255, 182, 66, 0.95)";
    ctx.shadowColor = "rgba(255, 160, 30, 0.90)";
    ctx.shadowBlur = Math.max(10, carW * 0.32);
    ctx.lineWidth = Math.max(2, carW * 0.042);
    body();
    ctx.stroke();
    ctx.restore();
  }

  // forward collision risk: pulsing red outline
  if (opts.risk > 0.35) {
    const pulse = 0.7 + 0.3 * Math.sin(performance.now() / 160);
    ctx.save();
    ctx.strokeStyle = `rgba(255, 46, 30, ${Math.min(1, 0.55 + 0.45 * pulse)})`;
    ctx.shadowColor = "rgba(255, 30, 20, 0.95)";
    ctx.shadowBlur = Math.max(12, carW * 0.42);
    ctx.lineWidth = Math.max(2.2, carW * 0.05);
    body();
    ctx.stroke();
    ctx.restore();
  }

  // Windshield band: a single dark horizontal strip for the cabin.
  const cabinTop = y - carH * 0.76;
  const cabinH = carH * 0.34;
  const cabinGrad = ctx.createLinearGradient(0, cabinTop, 0, cabinTop + cabinH);
  cabinGrad.addColorStop(0, "rgba(10, 15, 28, 0.92)");
  cabinGrad.addColorStop(1, "rgba(24, 34, 56, 0.78)");
  ctx.fillStyle = cabinGrad;
  roundRect(x + carW * 0.18, cabinTop, carW * 0.64, cabinH, carW * 0.12);
  ctx.fill();

  // Subtle specular highlight down the centre.
  const sheen = ctx.createLinearGradient(x + carW * 0.35, 0, x + carW * 0.65, 0);
  sheen.addColorStop(0, "rgba(215, 230, 255, 0)");
  sheen.addColorStop(0.5, ego ? "rgba(140, 210, 255, 0.14)" : "rgba(190, 215, 250, 0.10)");
  sheen.addColorStop(1, "rgba(215, 230, 255, 0)");
  ctx.fillStyle = sheen;
  roundRect(x + carW * 0.36, y - carH * 0.92, carW * 0.28, carH * 0.84, carW * 0.14);
  ctx.fill();

}

/* ---------- navigation band ---------- */

/* Turn direction → arrow glyph. Mirrors CarrotManSP.xTurnInfo. */
const TURN_DIR = { 1: "left", 2: "right", 3: "left", 4: "right", 6: "exit", 7: "uturn" };

function navInfo() {
  const nav = lastState?.sp_hud?.carrot_nav;
  if (!nav || !Number(nav.active)) return null;
  const turn = Number(nav.turn_info);
  const dist = Number(nav.dist_to_turn) || 0;
  const name = nav.tbt_main_text || nav.road_name || "";
  const next = nav.tbt_main_text_next || "";
  const hasTurn = turn > 0 && dist > 0;
  if (!hasTurn && !name && !next) return null;
  return {
    dir: TURN_DIR[turn] || "ahead",
    hasTurn,
    dist,
    name,
    next,
    atc: String(nav.atc_type || ""),
    countdown: Number(nav.turn_countdown) || 0,
    sdi: nav.sdi_descr || "",
    vTurn: Number(nav.v_turn_speed) || 0,
    spdLimit: Number(nav.spd_limit) || 0,
    spdDist: Number(nav.spd_dist) || 0,
    traffic: Number(nav.traffic_state) || 0,
    trafficCountdown: Number(nav.traffic_countdown) || 0,
    goal: nav.goal_name || "",
    eta: Number(nav.go_pos_time) || 0,
    etaDist: Number(nav.go_pos_dist) || 0,
  };
}

function fmtDist(meters) {
  const m = Number(meters) || 0;
  return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`;
}

function fmtEta(seconds) {
  const mins = Math.round((Number(seconds) || 0) / 60);
  if (mins < 60) return `${mins}min`;
  return `${Math.floor(mins / 60)}h${String(mins % 60).padStart(2, "0")}m`;
}

/* Bottom edge of the DOM speed block, in canvas logical px. getBoundingClientRect
   is in scaled screen coords, so divide by the stage scale. */
function speedBlockBottom() {
  try {
    const el = document.querySelector("#hud .opui-hud-speed-block");
    if (!el || !host) return null;
    const sr = el.getBoundingClientRect();
    const hr = host.getBoundingClientRect();
    const scale = (hr.width > 0 && host.clientWidth > 0) ? hr.width / host.clientWidth : 1;
    if (!(sr.height > 0) || !(scale > 0)) return null;
    return (sr.bottom - hr.top) / scale;
  } catch {
    return null;
  }
}

function ellipsize(text, maxW) {
  if (ctx.measureText(text).width <= maxW) return text;
  let lo = 0;
  let hi = text.length;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (ctx.measureText(`${text.slice(0, mid)}…`).width <= maxW) lo = mid;
    else hi = mid - 1;
  }
  return `${text.slice(0, lo)}…`;
}

/* Secondary chips under the headline. The speed limit itself is deliberately
   NOT repeated here — it lives in the sunnypilot SLA circle, which the resolver
   now feeds from the same carrot source (see speed_limit_resolver.py). */
function navPills(nav) {
  const out = [];
  if (nav.vTurn > 0 && nav.vTurn < 200) {
    out.push({ text: `${tr("Curve")} ${Math.round(nav.vTurn)}`, bg: "rgba(255, 200, 50, 0.17)", fg: "#ffd77a", border: "rgba(255, 200, 50, 0.45)" });
  }
  if (nav.sdi) {
    out.push({ text: nav.sdi, bg: "rgba(22, 160, 74, 0.55)", fg: "#eafff2", border: null });
  }
  if (nav.spdLimit > 0 && nav.spdDist > 0) {
    out.push({ text: `${tr("Camera")} ${nav.spdLimit} · ${fmtDist(nav.spdDist)}`, bg: "rgba(239, 68, 68, 0.45)", fg: "#ffe9e6", border: null });
  }
  if (nav.traffic > 0) {
    const c = nav.traffic === 1 ? "#ff5a5a" : nav.traffic === 2 ? "#4ade80" : "#34d399";
    const t = nav.traffic === 1 ? tr("Red light") : nav.traffic === 2 ? tr("Green light") : tr("Left-turn green");
    const cd = nav.trafficCountdown > 0 ? ` ${nav.trafficCountdown}s` : "";
    out.push({ text: `${t}${cd}`, dot: c, bg: "rgba(255, 255, 255, 0.10)", fg: c, border: null });
  }
  if (nav.goal) {
    out.push({ text: `🏁 ${nav.goal}`, bg: "rgba(255, 255, 255, 0.10)", fg: "rgba(226, 236, 252, 0.9)", border: null });
  }
  return out;
}

function drawTurnIcon(x, y, size, dir, atc) {
  const r = Math.round(size * 0.24);
  roundRect(x, y, size, size, r);
  const isAtc = !!atc;
  const bg = ctx.createLinearGradient(x, y, x, y + size);
  if (isAtc) {
    bg.addColorStop(0, "rgba(32, 210, 130, 0.92)");
    bg.addColorStop(1, "rgba(18, 168, 100, 0.92)");
  } else {
    bg.addColorStop(0, "rgba(22, 200, 122, 0.32)");
    bg.addColorStop(1, "rgba(16, 150, 96, 0.32)");
  }
  ctx.fillStyle = bg;
  ctx.fill();
  ctx.strokeStyle = isAtc ? "rgba(180, 255, 220, 0.55)" : "rgba(22, 200, 122, 0.45)";
  ctx.lineWidth = Math.max(1, size * 0.035);
  ctx.stroke();

  const cx = x + size / 2;
  const cy = y + size / 2;
  const s = size;
  ctx.strokeStyle = "#eaffe9";
  ctx.fillStyle = "#eaffe9";
  ctx.lineWidth = Math.max(2.5, s * 0.115);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  if (dir === "left" || dir === "right") {
    const d = dir === "left" ? -1 : 1;
    ctx.moveTo(cx - d * s * 0.11, cy + s * 0.27);
    ctx.lineTo(cx - d * s * 0.11, cy - s * 0.06);
    ctx.lineTo(cx + d * s * 0.13, cy - s * 0.06);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx + d * s * 0.30, cy - s * 0.06);
    ctx.lineTo(cx + d * s * 0.10, cy - s * 0.24);
    ctx.lineTo(cx + d * s * 0.10, cy + s * 0.12);
    ctx.closePath();
    ctx.fill();
  } else if (dir === "uturn") {
    ctx.arc(cx, cy + s * 0.02, s * 0.17, Math.PI * 0.85, Math.PI * 1.95);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx + s * 0.23, cy - s * 0.16);
    ctx.lineTo(cx + s * 0.31, cy + s * 0.03);
    ctx.lineTo(cx + s * 0.10, cy - s * 0.01);
    ctx.closePath();
    ctx.fill();
  } else if (dir === "exit") {
    ctx.moveTo(cx - s * 0.26, cy + s * 0.18);
    ctx.lineTo(cx + s * 0.14, cy - s * 0.2);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx + s * 0.26, cy - s * 0.28);
    ctx.lineTo(cx + s * 0.28, cy - s * 0.02);
    ctx.lineTo(cx + s * 0.03, cy - s * 0.13);
    ctx.closePath();
    ctx.fill();
  } else {
    ctx.moveTo(cx, cy + s * 0.27);
    ctx.lineTo(cx, cy - s * 0.14);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx, cy - s * 0.30);
    ctx.lineTo(cx - s * 0.15, cy - s * 0.09);
    ctx.lineTo(cx + s * 0.15, cy - s * 0.09);
    ctx.closePath();
    ctx.fill();
  }
}

/* Greedy chip layout: fill rows left to right up to `availW`, wrapping onto a
   second row when needed so a safety-relevant chip is never dropped just
   because it was measured last. Returns [] when there are no chips. */
function layoutPills(pills, availW, fontSize, pillH, pillGap) {
  if (!pills.length) return [];
  const rows = [];
  let row = [];
  let x = 0;
  for (const p of pills) {
    ctx.font = `700 ${fontSize}px Inter, system-ui, sans-serif`;
    const textW = ctx.measureText(p.text).width;
    const dotW = p.dot ? pillH * 0.42 : 0;
    const pw = textW + dotW + pillH * 0.86;
    if (row.length && x + pw > availW) {
      rows.push(row);
      if (rows.length >= 2) return rows;
      row = [];
      x = 0;
    }
    row.push({ p, x, w: pw });
    x += pw + pillGap;
  }
  if (row.length) rows.push(row);
  return rows;
}

/* Navigation band in lite mode. Replaces the DOM carrot card (hidden whenever
   #hud carries road-lite-on) and sits directly under the speed block so the
   two read as one cluster. Bigger type than the old top-of-screen banner, and
   the only nav text on screen — no second speed-limit widget. */
function drawNavBand(w, h) {
  const nav = navInfo();
  if (!nav) return;

  const k = Math.max(0.62, Math.min(1.4, w / 1600));
  const iconSize = Math.round(Math.max(48, Math.min(86, 68 * k)));
  const f1 = Math.round(Math.max(27, Math.min(46, 36 * k)));
  const f2 = Math.round(Math.max(19, Math.min(30, 24 * k)));
  const f3 = Math.round(Math.max(15, Math.min(23, 19 * k)));
  const padX = Math.round(16 * k);
  const padY = Math.round(12 * k);
  const gap = Math.round(13 * k);
  const pillH = Math.round(Math.max(25, 31 * k));
  const pillGap = Math.round(8 * k);

  const pills = navPills(nav);
  const second = nav.next
    || (nav.eta > 0 && nav.etaDist > 0 ? `${tr("ETA")} ${fmtEta(nav.eta)} · ${fmtDist(nav.etaDist)}` : "");

  const textH = f1 * 1.18 + (second ? f2 * 1.32 + 3 : 0);
  const bodyH = Math.max(iconSize, textH);
  // Kept narrower than the old full-width banner: the band now sits over the
  // road rather than over the sky, so every pixel it spans is a pixel of the
  // scene that gets hidden. Anything past ~45 m projects below its top edge.
  const bandW = Math.min(w * 0.62, 780);

  // Chips are laid out before the band height is known, and wrap onto a second
  // row rather than being silently dropped when they stop fitting.
  const rowGap = Math.round(6 * k);
  const pillRows = layoutPills(pills, bandW - padX * 2, f3, pillH, pillGap);
  const pillsH = pillRows.length ? pillRows.length * pillH + (pillRows.length - 1) * rowGap + Math.round(gap * 0.7) : 0;
  const bandH = bodyH + padY * 2 + pillsH;

  const bx = (w - bandW) / 2;
  const speedBottom = speedBlockBottom();
  const desiredTop = (speedBottom != null ? speedBottom + Math.round(16 * k) : h * 0.32);
  const maxTop = h - bandH - Math.round(14 * k);
  const by = Math.max(Math.round(10 * k), Math.min(desiredTop, maxTop));

  ctx.save();
  ctx.shadowColor = "rgba(0, 0, 0, 0.55)";
  ctx.shadowBlur = 20 * k;
  ctx.shadowOffsetY = 5 * k;
  roundRect(bx, by, bandW, bandH, Math.round(20 * k));
  // Deliberately translucent: the type is large and light-on-dark, so ~0.7
  // still reads while the road stays visible through the band.
  const bg = ctx.createLinearGradient(bx, by, bx, by + bandH);
  bg.addColorStop(0, "rgba(13, 19, 34, 0.64)");
  bg.addColorStop(1, "rgba(8, 12, 22, 0.74)");
  ctx.fillStyle = bg;
  ctx.fill();
  ctx.shadowBlur = 0;
  ctx.shadowOffsetY = 0;
  ctx.strokeStyle = "rgba(126, 168, 240, 0.30)";
  ctx.lineWidth = Math.max(1, 1.5 * k);
  ctx.stroke();

  drawTurnIcon(bx + padX, by + padY, iconSize, nav.dir, nav.atc);

  const tx = bx + padX + iconSize + gap;
  const tW = bx + bandW - padX - tx;

  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
  ctx.font = `700 ${f1}px Inter, system-ui, sans-serif`;
  ctx.fillStyle = "#f2f7ff";
  const cd = nav.countdown > 0 ? `  ${nav.countdown}s` : "";
  const headline = nav.hasTurn
    ? `${fmtDist(nav.dist)}${cd}${nav.name ? `   ${nav.name}` : ""}`
    : (nav.name || second);
  ctx.fillText(ellipsize(headline, tW), tx, by + padY + f1 * 0.92);

  const secondLine = nav.hasTurn ? second : (nav.name ? second : "");
  if (secondLine) {
    ctx.font = `500 ${f2}px Inter, system-ui, sans-serif`;
    ctx.fillStyle = "rgba(198, 214, 240, 0.86)";
    ctx.fillText(ellipsize(secondLine, tW), tx, by + padY + f1 * 1.18 + f2 * 1.05);
  }

  ctx.textBaseline = "middle";
  const pillsTop = by + padY + bodyH + Math.round(gap * 0.7);
  for (let r = 0; r < pillRows.length; r++) {
    const py = pillsTop + r * (pillH + rowGap);
    for (const { p, x, w: pw } of pillRows[r]) {
      const px = bx + padX + x;
      roundRect(px, py, pw, pillH, pillH / 2);
      ctx.fillStyle = p.bg;
      ctx.fill();
      if (p.border) {
        ctx.strokeStyle = p.border;
        ctx.lineWidth = 1;
        ctx.stroke();
      }
      let ix = px + pillH * 0.43;
      if (p.dot) {
        ctx.fillStyle = p.dot;
        ctx.beginPath();
        ctx.arc(ix, py + pillH / 2, pillH * 0.13, 0, Math.PI * 2);
        ctx.fill();
        ix += pillH * 0.42;
      }
      ctx.fillStyle = p.fg;
      ctx.font = `700 ${f3}px Inter, system-ui, sans-serif`;
      ctx.fillText(p.text, ix, py + pillH / 2 + 0.5);
    }
  }
  ctx.restore();
}

/* NOTE: there is deliberately no traffic light drawn on the road.
   A light standing at the end of the road (z ~ 45 m) projects to y ~ 400–540 px
   at 1080p, which is exactly where the navigation band now sits — so it was
   always fully hidden behind the band, leaving only its countdown floating in
   mid-air above it. The nav band's traffic-light pill carries the same state
   plus the countdown, so one representation is kept instead of two. */

/* Forward collision warning: full-screen red edge pulse (AEB/FCW or low TTC). */
function drawFcw(w, h) {
  const risk = collisionRisk();
  if (risk <= 0.05) return;
  const pulse = 0.72 + 0.28 * Math.sin(performance.now() / 180);
  const alpha = risk * 0.5 * pulse;
  const vg = ctx.createRadialGradient(w / 2, h * 0.45, Math.min(w, h) * 0.22, w / 2, h * 0.45, Math.max(w, h) * 0.72);
  vg.addColorStop(0, "rgba(255, 30, 20, 0)");
  vg.addColorStop(0.55, `rgba(255, 30, 20, ${alpha * 0.55})`);
  vg.addColorStop(1, `rgba(255, 20, 12, ${alpha})`);
  ctx.fillStyle = vg;
  ctx.fillRect(0, 0, w, h);
}

function drawVignette(w, h, cx) {
  // Gentle edge falloff: heavy enough to frame the scene, light enough that the
  // road keeps its contrast.
  const vg = ctx.createRadialGradient(cx, h * 0.46, Math.min(w, h) * 0.42, cx, h * 0.46, Math.max(w, h) * 0.80);
  vg.addColorStop(0, "rgba(0, 0, 0, 0)");
  vg.addColorStop(1, "rgba(0, 0, 0, 0.32)");
  ctx.fillStyle = vg;
  ctx.fillRect(0, 0, w, h);

  // Slightly darker band across the sky so the HUD can sit over the skyline.
  const tg = ctx.createLinearGradient(0, 0, 0, h * 0.24);
  tg.addColorStop(0, "rgba(4, 8, 16, 0.42)");
  tg.addColorStop(1, "rgba(4, 8, 16, 0)");
  ctx.fillStyle = tg;
  ctx.fillRect(0, 0, w, h * 0.24);
}

function roundRect(x, y, w, h, r) {
  const rr = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}

/* ---------- visibility / lifecycle ---------- */

function probeVideoFrozen(ts) {
  const wrap = document.getElementById("camera-wrap");
  const video = document.getElementById("road-video");
  const playing = wrap && wrap.classList.contains("is-playing") && video && !video.paused && video.readyState >= 2;
  if (!playing) {
    frozenStreak = 0;
    lastFrozenHash = null;
    return;
  }
  if (!probeCanvas) {
    probeCanvas = document.createElement("canvas");
    probeCanvas.width = 48;
    probeCanvas.height = 27;
  }
  if (ts - frozenProbeTs < 1500) return;
  frozenProbeTs = ts;
  let hash = null;
  try {
    const pctx = probeCanvas.getContext("2d", { willReadFrequently: true });
    pctx.drawImage(video, 0, 0, probeCanvas.width, probeCanvas.height);
    const data = pctx.getImageData(0, 0, probeCanvas.width, probeCanvas.height).data;
    let acc = 0;
    for (let i = 0; i < data.length; i += 97) acc = (acc + data[i]) % 100000007;
    hash = acc;
  } catch {
    return; // cross-origin or not decodable yet — do not judge
  }
  if (hash === lastFrozenHash) frozenStreak++;
  else frozenStreak = 0;
  lastFrozenHash = hash;
  if (frozenStreak === FROZEN_PROBES) {
    console.warn("[road_lite] video appears frozen — switching to synthesized scene");
    window.dispatchEvent(new CustomEvent("opui:road-lite", { detail: { active: true, reason: "frozen-video" } }));
  }
}

function renderLoop(ts) {
  rafId = null;
  if (!active) return;
  // adaptive frame rate: idle/standstill scenes drop to ~15 fps
  const v = Math.max(0, Number(lastState?.speed_raw) || 0);
  const slow = v < 2;
  if (slow) {
    frameSkip = (frameSkip + 1) % 4;
    if (frameSkip !== 0) {
      lastFrameTs = ts;
      rafId = requestAnimationFrame(renderLoop);
      return;
    }
  }
  if (lastFrameTs) {
    const dt = Math.min(0.2, (ts - lastFrameTs) / 1000);
    distM += v * dt;
  }
  lastFrameTs = ts;
  try {
    drawScene();
  } catch (err) {
    window.__rlErr = `${err?.message}\n${err?.stack || ""}`;
    console.error("[road_lite] drawScene failed:", err);
    stopRender();
    return;
  }
  rafId = requestAnimationFrame(renderLoop);
}

function startRender() {
  lastFrameTs = 0;
  if (rafId == null) rafId = requestAnimationFrame(renderLoop);
}

function stopRender() {
  if (rafId != null) {
    cancelAnimationFrame(rafId);
    rafId = null;
  }
}

function checkVisibility() {
  probeVideoFrozen(performance.now());
  const wrap = document.getElementById("camera-wrap");
  const cls = wrap?.className || "";
  const show = shouldShow();
  if (show === active && cls === lastWrapClass) return;
  lastWrapClass = cls;
  if (show && !active) {
    active = true;
    host.hidden = false;
    wrap?.classList.add("road-lite-on");
    document.getElementById("hud")?.classList.add("road-lite-on");
    startRender();
    window.dispatchEvent(new CustomEvent("opui:road-lite", { detail: { active: true } }));
  } else if (!show && active) {
    active = false;
    host.hidden = true;
    wrap?.classList.remove("road-lite-on");
    document.getElementById("hud")?.classList.remove("road-lite-on");
    stopRender();
    window.dispatchEvent(new CustomEvent("opui:road-lite", { detail: { active: false } }));
  }
}

export function initRoadLite() {
  if (host || !document.getElementById("camera-wrap")) return;
  forced = new URLSearchParams(window.location.search).get("lite") === "1";
  buildDom();
  opuiWs.on("state", (msg) => {
    if (msg?.data?.ok) {
      lastState = msg.data;
    }
  });
  watchTimer = setInterval(checkVisibility, ROAD_LITE_MS);
  window.addEventListener("resize", () => {
    if (active) resizeCanvas();
  });
  checkVisibility();
}
