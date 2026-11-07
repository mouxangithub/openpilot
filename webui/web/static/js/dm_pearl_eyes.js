/** Pearl Eyes DM character — canvas-rendered cartoon eyes that mirror head pose.
 * Mirrors openpilot/selfdrive/ui/onroad/driver_preview.py (cp 7f99be428 port).
 * Gated by CarrotDMPearlEyes param (default ON in sp). */

const PREVIEW_MAX_AGE = 0.5;

// Colors matching big UI
const PEARL = "#f4eddf";
const PUPIL = "#3a3530";
const SHADOW = "rgba(15,17,22,0.82)";
const UNKNOWN = "#919199";
const WARNING = "#ff9769";
const HANDS = "#a0cce5";

let canvas = null;
let ctx = null;
let lastDrawTime = 0;
let expression = null;
let modelFrame = null;
let modelProgress = 0;
let driverSide = null;

function resetExpression() {
  expression = null;
  driverSide = null;
  modelFrame = null;
  modelProgress = 0;
}

export function initPearlEyes() {
  canvas = document.getElementById("dm-pearl-eyes-canvas");
  if (!canvas) {
    // Create canvas inside dm-arc-wrap
    const wrap = document.getElementById("dm-arc-wrap");
    if (!wrap) return null;
    canvas = document.createElement("canvas");
    canvas.id = "dm-pearl-eyes-canvas";
    canvas.style.cssText = "position:absolute;inset:0;width:100%;height:100%;pointer-events:none;";
    wrap.appendChild(canvas);
  }
  ctx = canvas.getContext("2d");
  return canvas;
}

function eyeExpression(driver) {
  const orientation = driver.faceOrientation || [0, 0, 0];
  const uncertainty = driver.faceOrientationStd || [0, 0, 0];
  const poseKnown = orientation.length === 3 && uncertainty.length === 3 &&
    orientation.every(Number.isFinite) && uncertainty.every(Number.isFinite) &&
    uncertainty[0] >= 0 && uncertainty[0] < 0.3 && uncertainty[1] >= 0 && uncertainty[1] < 0.3;

  const x = poseKnown ? Math.max(-1, Math.min(1, -orientation[1] / 0.6)) : 0;
  const y = poseKnown ? Math.max(-1, Math.min(1, orientation[0] / 0.5)) : 0;
  const glasses = driver.sunglassesProb || 0;

  function eyelid(confidence, blink) {
    const known = Number.isFinite(glasses) && glasses >= 0 && glasses < 0.9 &&
      Number.isFinite(confidence) && confidence > 0.65 && confidence <= 1 &&
      Number.isFinite(blink) && blink >= 0 && blink <= 1;
    return [known ? Math.max(0.08, 1.0 - blink) : 1.0, known];
  }

  const [leftOpen, leftKnown] = eyelid(driver.leftEyeProb, driver.leftBlinkProb);
  const [rightOpen, rightKnown] = eyelid(driver.rightEyeProb, driver.rightBlinkProb);
  return { x, y, leftOpen, rightOpen, leftKnown, rightKnown };
}

function smoothExpression(previous, target, dt) {
  if (!previous) return target;
  const clampedDt = Math.min(Math.max(dt, 0), 0.1);
  const alpha = 1.0 - Math.exp(-clampedDt / 0.08);

  function eyelid(oldV, newV, wasKnown, known) {
    if (!known || !wasKnown) return newV;
    const weight = 1.0 - Math.exp(-clampedDt / (newV < oldV ? 0.018 : 0.06));
    return oldV + weight * (newV - oldV);
  }

  return {
    x: previous.x + alpha * (target.x - previous.x),
    y: previous.y + alpha * (target.y - previous.y),
    leftOpen: eyelid(previous.leftOpen, target.leftOpen, previous.leftKnown, target.leftKnown),
    rightOpen: eyelid(previous.rightOpen, target.rightOpen, previous.rightKnown, target.rightKnown),
    leftKnown: target.leftKnown,
    rightKnown: target.rightKnown,
  };
}

function drawEye(cx, cy, scale, openness, known, expr, color) {
  const width = 42 * scale;
  const height = Math.max(4, 54 * openness) * scale;
  const eyeColor = known || color === WARNING ? color : UNKNOWN;

  // Shadow silhouette
  ctx.fillStyle = SHADOW;
  roundRect(ctx, cx - width / 2 - scale, cy - height / 2 - scale, width + 2 * scale, height + 2 * scale, 12 * scale);
  ctx.fill();

  // Eye
  ctx.fillStyle = eyeColor;
  roundRect(ctx, cx - width / 2, cy - height / 2, width, height, 12 * scale);
  ctx.fill();

  // Pupil
  if (known && openness > 0.22) {
    const pw = width * 0.43;
    const ph = height * 0.48;
    const px = cx + expr.x * width * 0.16;
    const py = cy + expr.y * height * 0.12;

    ctx.fillStyle = PUPIL;
    roundRect(ctx, px - pw / 2, py - ph / 2, pw, ph, 10 * scale);
    ctx.fill();

    // Pearl highlight
    ctx.fillStyle = PEARL;
    ctx.beginPath();
    ctx.arc(px + pw * 0.16, py - ph * 0.2, Math.min(pw, ph) * 0.14, 0, Math.PI * 2);
    ctx.fill();
  }
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

export function drawPearlEyes(dmState, driverState, engaged, alertVisible) {
  if (!canvas || !ctx) {
    if (!initPearlEyes()) return false;
  }

  const wrap = document.getElementById("dm-arc-wrap");
  if (!wrap) return false;

  const now = performance.now() / 1000;
  const rect = wrap.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const w = Math.round(rect.width * dpr);
  const h = Math.round(rect.height * dpr);

  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;
  }

  // Reset if state changed
  if (driverState && modelFrame !== driverState.frameId) {
    modelFrame = driverState.frameId;
    modelProgress = now;
  }

  const monitoringFresh = dmState && dmState.valid;
  const driverFresh = driverState && driverState.valid && (now - modelProgress) < PREVIEW_MAX_AGE;
  const cameraUnavailable = dmState?.cameraUnavailable || false;
  const faceDetected = dmState?.faceDetected || false;
  const distracted = dmState?.isDistracted || false;
  const lockout = dmState?.lockout || dmState?.alwaysOnLockout || false;
  const wheelPolicy = dmState?.activePolicy === "wheeltouch";

  // Determine state
  let stateKind = "tracking";
  let stateLabel = "DM FACE";
  if (!monitoringFresh) { stateKind = "waiting"; stateLabel = "DM CHECK"; }
  else if (lockout) { stateKind = "warning"; stateLabel = "DM LIMIT"; }
  else if (cameraUnavailable) { stateKind = "wheel"; stateLabel = "DM HANDS"; }
  else if (!driverFresh) { stateKind = "waiting"; stateLabel = "DM CHECK"; }
  else if (!faceDetected) { stateKind = "searching"; stateLabel = "DM FACE?"; }
  else if (distracted) { stateKind = "warning"; stateLabel = "DM ALERT"; }
  else if (wheelPolicy) { stateKind = "wheel"; stateLabel = "DM HANDS"; }

  const color = { tracking: PEARL, warning: WARNING, wheel: HANDS }[stateKind] || UNKNOWN;

  // Animate expression
  const animate = monitoringFresh && driverFresh && !cameraUnavailable && faceDetected &&
    (stateKind === "tracking" || stateKind === "warning");

  if (animate && driverState) {
    const isRHD = dmState?.isRHD || false;
    if (driverSide !== isRHD || now - lastDrawTime >= PREVIEW_MAX_AGE) {
      expression = null;
    }
    driverSide = isRHD;
    const driver = isRHD ? driverState.rightDriverData : driverState.leftDriverData;
    const target = eyeExpression(driver);
    expression = smoothExpression(expression, target, now - lastDrawTime);
  } else {
    expression = null;
  }
  lastDrawTime = now;

  // Draw
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, rect.width, rect.height);

  const labelH = 32;
  const fontSize = 21;
  const scale = Math.min(rect.width / 154, (rect.height - labelH - 8) / 90);
  const cx = rect.width / 2;
  const cy = (rect.height - labelH) * 0.47;

  if (stateKind === "wheel") {
    const radius = 24 * scale;
    ctx.strokeStyle = color;
    ctx.lineWidth = Math.max(1, 2 * scale);
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.stroke();
    // Steering wheel spokes
    for (const [dx, dy] of [[-0.9, -0.2], [0.9, -0.2], [0, 0.9]]) {
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + dx * radius, cy + dy * radius);
      ctx.stroke();
    }
  } else {
    for (const left of [true, false]) {
      const ex = cx + (left ? -29 : 29) * scale;
      const known = expression && (left ? expression.leftKnown : expression.rightKnown);
      const openness = expression ? (left ? expression.leftOpen : expression.rightOpen) : 0.08;
      drawEye(ex, cy, scale, openness, known, expression || { x: 0, y: 0 }, color);

      // Warning eyebrows
      if (stateKind === "warning") {
        const direction = left ? 1 : -1;
        ctx.strokeStyle = color;
        ctx.lineWidth = Math.max(2, 3 * scale);
        ctx.beginPath();
        ctx.moveTo(ex - 14 * scale, cy - (35 + direction * 3) * scale);
        ctx.lineTo(ex + 14 * scale, cy - (35 - direction * 3) * scale);
        ctx.stroke();
      }
    }
  }

  // Label
  const label = stateKind === "tracking" && !(expression?.leftKnown || expression?.rightKnown)
    ? "DM EYES?" : stateLabel;
  ctx.font = `600 ${fontSize}px Inter, system-ui, sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "bottom";

  // Shadow
  ctx.fillStyle = SHADOW;
  ctx.fillText(label, cx + 1, rect.height - labelH + 1);
  // Text
  ctx.fillStyle = color;
  ctx.fillText(label, cx, rect.height - labelH);

  return true;
}

export function hidePearlEyes() {
  if (canvas) {
    canvas.hidden = true;
  }
  resetExpression();
}

export function showPearlEyes() {
  if (canvas) {
    canvas.hidden = false;
  }
}
