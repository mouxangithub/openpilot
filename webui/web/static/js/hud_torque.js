/** Steering torque arc (mirrors sunnypilot/onroad/hud_renderer.py TorqueBar scale=3). */

const TORQUE_ANGLE_SPAN = 12.7;
const TORQUE_SCALE = 3.0;
let filtered = 0;
let alphaFiltered = 0;
let torqueAnimId = 0;
let lastTorqueTs = 0;
let pendingTorque = null;

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function blendColor(c1, c2, t) {
  const k = clamp(t, 0, 1);
  return {
    r: Math.round(lerp(c1.r, c2.r, k)),
    g: Math.round(lerp(c1.g, c2.g, k)),
    b: Math.round(lerp(c1.b, c2.b, k)),
    a: lerp(c1.a, c2.a, k),
  };
}

function rgba(c) {
  return `rgba(${c.r},${c.g},${c.b},${c.a})`;
}

function arcBarPts(rMid, thickness, a0Deg, a1Deg, capRadius = 7, capSegs = 10, pxPerSeg = 2) {
  if (a1Deg < a0Deg) [a0Deg, a1Deg] = [a1Deg, a0Deg];
  const half = thickness * 0.5;
  capRadius = Math.min(capRadius, half);
  const span = Math.max(1e-3, a1Deg - a0Deg);

  function getCap(left, aDeg) {
    const rad = (aDeg * Math.PI) / 180;
    const nx = Math.cos(rad);
    const ny = Math.sin(rad);
    const tx = -ny;
    const ty = nx;
    const mx = nx * rMid;
    const my = ny * rMid;
    const ex = mx + nx * (half - capRadius);
    const ey = my + ny * (half - capRadius);

    const capEnd = [];
    const alpha = left
      ? Array.from({ length: capSegs }, (_, i) => ((Math.PI / 2) * (capSegs - i)) / capSegs)
      : Array.from({ length: capSegs }, (_, i) => (Math.PI / 2) * (1 - i / capSegs));
    for (const a of alpha.slice(1, -1)) {
      capEnd.push([
        ex + Math.cos(a) * capRadius * tx + Math.sin(a) * capRadius * nx,
        ey + Math.cos(a) * capRadius * ty + Math.sin(a) * capRadius * ny,
      ]);
    }

    const ex2 = mx + nx * (-half + capRadius);
    const ey2 = my + ny * (-half + capRadius);
    const alpha2 = left
      ? Array.from({ length: capSegs + 1 }, (_, i) => -((Math.PI / 2) * i) / capSegs).slice(0, -1)
      : Array.from({ length: capSegs + 1 }, (_, i) => -((Math.PI / 2) * i) / capSegs).slice(0, -1);
    const capEndBot = [];
    for (const a of alpha2) {
      capEndBot.push([
        ex2 + Math.cos(a) * capRadius * tx + Math.sin(a) * capRadius * nx,
        ey2 + Math.cos(a) * capRadius * ty + Math.sin(a) * capRadius * ny,
      ]);
    }
    return left ? [...capEndBot, ...capEnd] : [...capEnd, ...capEndBot];
  }

  const arcLen = rMid * ((span * Math.PI) / 180);
  let arcSegs = Math.max(6, Math.floor(arcLen / pxPerSeg));
  const maxArc = Math.floor((100 - (4 * capSegs + 3)) / 2);
  arcSegs = Math.max(6, Math.min(arcSegs, maxArc));

  const outer = [];
  for (let i = 0; i <= arcSegs; i++) {
    const ang = ((a0Deg + (span * i) / arcSegs) * Math.PI) / 180;
    outer.push([Math.cos(ang) * (rMid + half), Math.sin(ang) * (rMid + half)]);
  }
  const capEnd = getCap(false, a1Deg);
  const inner = [];
  for (let i = 0; i <= arcSegs; i++) {
    const ang = ((a1Deg - (span * i) / arcSegs) * Math.PI) / 180;
    inner.push([Math.cos(ang) * (rMid - half), Math.sin(ang) * (rMid - half)]);
  }
  const capStart = getCap(true, a0Deg);
  const pts = [...outer, ...capEnd, ...inner, ...capStart, outer[0]];
  const roll = capSegs % pts.length;
  return pts.slice(roll).concat(pts.slice(0, roll));
}

function fillPoly(ctx, pts, fill) {
  if (pts.length < 3) return;
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
  ctx.closePath();
  if (typeof fill === "string") {
    ctx.fillStyle = fill;
    ctx.fill();
    return;
  }
  ctx.fillStyle = fill;
  ctx.fill();
}

function stopTorqueAnim() {
  if (torqueAnimId) {
    cancelAnimationFrame(torqueAnimId);
    torqueAnimId = 0;
  }
  lastTorqueTs = 0;
}

function paintTorque(st, devUi) {
  const canvas = document.getElementById("torque-bar-canvas");
  if (!canvas) return;

  const wrap = document.getElementById("camera-wrap");
  const w = wrap?.clientWidth || canvas.clientWidth || 1860;
  const roadH = wrap?.clientHeight || 680;
  const canvasH = Math.round(60 * TORQUE_SCALE);
  const dpr = window.devicePixelRatio || 1;
  const pxW = Math.max(1, Math.round(w * dpr));
  const pxH = Math.max(1, Math.round(canvasH * dpr));

  if (canvas.width !== pxW || canvas.height !== pxH) {
    canvas.width = pxW;
    canvas.height = pxH;
    canvas.style.width = `${w}px`;
    canvas.style.height = `${canvasH}px`;
  }

  const engaged = st.ui_status === "engaged" || st.ui_status === "lat_only";
  const util = Math.abs(filtered);
  const offset = lerp(22 * TORQUE_SCALE, 26 * TORQUE_SCALE, clamp((util - 0.5) / 0.5, 0, 1));
  const thickness = lerp(14 * TORQUE_SCALE, 56 * TORQUE_SCALE, clamp((util - 0.5) / 0.5, 0, 1));
  const capRadius = 7 * TORQUE_SCALE;

  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, canvasH);

  const cx = w / 2 + 8;
  const radius = 1200 * TORQUE_SCALE;
  const canvasTopInRoad = roadH - canvasH;
  const cy = roadH + radius - offset - canvasTopInRoad;
  const span = TORQUE_ANGLE_SPAN * alphaFiltered;
  const top = -90;
  const bgA0 = top - span / 2;
  const bgA1 = top + span / 2;
  const bgAlpha = lerp(0.25, 0.5, clamp((util - 0.5) / 0.5, 0, 1)) * alphaFiltered;
  const midR = radius + thickness / 2;

  const bgPts = arcBarPts(midR, thickness, bgA0, bgA1, capRadius).map(([x, y]) => [x + cx, y + cy]);
  fillPoly(ctx, bgPts, rgba({ r: 255, g: 255, b: 255, a: engaged ? bgAlpha : 0.15 * alphaFiltered }));

  const fillEnd = top + (span / 2) * filtered;
  const hot = clamp((util - 0.75) * 4, 0, 1);
  let start = blendColor(
    { r: 255, g: 255, b: 255, a: 0.9 * alphaFiltered },
    { r: 255, g: 200, b: 0, a: alphaFiltered },
    hot,
  );
  let end = blendColor(
    { r: 255, g: 255, b: 255, a: 0.9 * alphaFiltered },
    { r: 255, g: 115, b: 0, a: alphaFiltered },
    hot,
  );
  if (!engaged) {
    start = end = { r: 255, g: 255, b: 255, a: 0.35 * alphaFiltered };
  }

  const slPts = arcBarPts(midR, thickness, top, fillEnd, capRadius).map(([x, y]) => [x + cx, y + cy]);
  const minX = Math.min(...bgPts.map((p) => p[0]));
  const maxX = Math.max(...bgPts.map((p) => p[0]));
  const gradStart = filtered < 0 ? cx * 0.35 + minX * 0.65 : cx;
  const gradEnd = filtered < 0 ? cx : cx * 0.35 + maxX * 0.65;
  const grad = ctx.createLinearGradient(gradStart, 0, gradEnd, 0);
  grad.addColorStop(0, rgba(start));
  grad.addColorStop(1, rgba(end));
  fillPoly(ctx, slPts, grad);

  if (util < 0.5) {
    const dotY = canvasH - offset - thickness / 2;
    ctx.beginPath();
    ctx.arc(cx, dotY, (10 / 2) * TORQUE_SCALE, 0, Math.PI * 2);
    ctx.fillStyle = rgba({ r: 182, g: 182, b: 182, a: 0.9 * alphaFiltered });
    ctx.fill();
  }
}

function torqueTick(now) {
  if (!pendingTorque) {
    stopTorqueAnim();
    return;
  }
  const { st, devUi } = pendingTorque;
  const canvas = document.getElementById("torque-bar-canvas");
  if (!canvas || !st?.started || !st.torque_bar) {
    canvas.hidden = true;
    filtered = 0;
    alphaFiltered = 0;
    pendingTorque = null;
    stopTorqueAnim();
    return;
  }

  const dt = lastTorqueTs ? Math.min(0.1, (now - lastTorqueTs) / 1000) : 1 / 60;
  lastTorqueTs = now;
  const k = 1 - Math.exp(-dt / 0.1);
  const target = clamp(Number(st.torque_utilization) || 0, -1, 1);
  filtered += (target - filtered) * k;
  const engaged = st.ui_status === "engaged" || st.ui_status === "lat_only";
  const alphaTarget = engaged ? 1 : 0.35;
  alphaFiltered += (alphaTarget - alphaFiltered) * k;

  paintTorque(st, devUi);
  torqueAnimId = requestAnimationFrame(torqueTick);
}

export function updateTorqueBar(st, devUi = 0) {
  const canvas = document.getElementById("torque-bar-canvas");
  if (!canvas) return;

  const show = !!st?.started && !!st.torque_bar;
  if (!show) {
    canvas.hidden = true;
    filtered = 0;
    alphaFiltered = 0;
    pendingTorque = null;
    canvas.classList.remove("is-dev-bottom");
    stopTorqueAnim();
    return;
  }

  const devBottom = devUi === 1 || devUi === 3;
  canvas.classList.toggle("is-dev-bottom", devBottom);
  canvas.hidden = false;
  pendingTorque = { st, devUi };
  if (!torqueAnimId) {
    lastTorqueTs = 0;
    torqueAnimId = requestAnimationFrame(torqueTick);
  }
}
