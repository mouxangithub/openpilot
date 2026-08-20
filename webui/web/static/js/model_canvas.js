/** Canvas overlay for modelV2 lanes / path / leads (mirrors ModelRenderer). */

import { tr } from "./i18n.js";
import { initModelWebGL, drawModelWebGL, isModelWebGLReady, clearModelWebGL } from "./model_webgl.js";

let canvas = null;
let ctx = null;
let rainbowHue = 0;
let lastOverlay = null;

const PATH_WHITE = "rgba(242, 242, 242, 0.7)";
const LEAD_FILL = "rgba(255, 196, 0, 0.45)";

export function initModelCanvas() {
  const host = document.getElementById("model-overlay");
  if (!host) return;
  initModelWebGL();
  if (canvas) return;
  canvas = document.createElement("canvas");
  canvas.className = "opui-model-canvas opui-model-metrics";
  host.appendChild(canvas);
  ctx = canvas.getContext("2d");
}

export function showModelOverlay(show) {
  const el = document.getElementById("model-overlay");
  if (el) el.hidden = !show;
}

function resize(w, h) {
  if (!canvas) return;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(w * dpr));
  canvas.height = Math.max(1, Math.floor(h * dpr));
  canvas.style.width = `${w}px`;
  canvas.style.height = `${h}px`;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function asPoints(raw) {
  if (!raw?.length) return [];
  if (Array.isArray(raw[0])) return raw;
  const pts = [];
  for (let i = 0; i + 1 < raw.length; i += 2) pts.push([raw[i], raw[i + 1]]);
  return pts;
}

function drawPoly(pts, fill, stroke, lineW = 2) {
  if (pts.length < 2) return;
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
  if (fill) {
    ctx.fillStyle = fill;
    ctx.fill();
  }
  if (stroke) {
    ctx.strokeStyle = stroke;
    ctx.lineWidth = lineW;
    ctx.stroke();
  }
}

function drawLane(lane) {
  const prob = lane.prob ?? 0.5;
  const alpha = Math.max(0.15, Math.min(0.85, prob));
  const fill = `rgba(255, 255, 255, ${alpha * 0.7})`;
  const poly = asPoints(lane.polygon);
  if (poly.length >= 3) {
    drawPoly(poly, fill, null);
    return;
  }
  const center = asPoints(lane.center);
  if (center.length >= 2) {
    ctx.strokeStyle = fill;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(center[0][0], center[0][1]);
    for (let i = 1; i < center.length; i++) ctx.lineTo(center[i][0], center[i][1]);
    ctx.stroke();
  }
}

function drawRainbowPolygon(pts) {
  const minY = Math.min(...pts.map((p) => p[1]));
  const maxY = Math.max(...pts.map((p) => p[1]));
  const grad = ctx.createLinearGradient(0, maxY, 0, minY);
  for (let i = 0; i <= 8; i++) {
    const hue = (rainbowHue + i * 40) % 360;
    grad.addColorStop(i / 8, `hsla(${hue}, 95%, 55%, ${0.9 - i * 0.07})`);
  }
  drawPoly(pts, grad, null);
}

function buildPathGradient(pts, stops, blend = 1) {
  const minY = Math.min(...pts.map((p) => p[1]));
  const maxY = Math.max(...pts.map((p) => p[1]));
  const grad = ctx.createLinearGradient(0, maxY, 0, minY);
  const factor = Math.max(0, Math.min(1, Number(blend) || 1));
  for (const stop of stops) {
    const rgba = stop.rgba || [];
    const [r, g, b, a] = rgba;
    const alpha = ((a ?? 255) / 255) * factor;
    grad.addColorStop(Math.max(0, Math.min(1, stop.pos ?? 0)), `rgba(${r}, ${g}, ${b}, ${alpha})`);
  }
  return grad;
}

function drawPathRibbon(poly, experimental, rainbow, allowThrottle, pathGradient, pathBlend) {
  const pts = asPoints(poly);
  if (pts.length < 4) return false;

  if (rainbow) {
    drawRainbowPolygon(pts);
    return true;
  }

  if (experimental && pathGradient?.length) {
    drawPoly(pts, buildPathGradient(pts, pathGradient, 1), null);
    return true;
  }

  if (experimental) {
    const minY = Math.min(...pts.map((p) => p[1]));
    const maxY = Math.max(...pts.map((p) => p[1]));
    const grad = ctx.createLinearGradient(0, maxY, 0, minY);
    grad.addColorStop(0, "rgba(13, 248, 122, 0.85)");
    grad.addColorStop(0.5, "rgba(114, 255, 92, 0.55)");
    grad.addColorStop(1, "rgba(114, 255, 92, 0)");
    drawPoly(pts, grad, null);
    return true;
  }

  const blend = typeof pathBlend === "number" ? pathBlend : 1;
  const minY = Math.min(...pts.map((p) => p[1]));
  const maxY = Math.max(...pts.map((p) => p[1]));
  const grad = ctx.createLinearGradient(0, maxY, 0, minY);
  if (allowThrottle === false) {
    grad.addColorStop(0, `rgba(242, 242, 242, ${0.35 * blend})`);
    grad.addColorStop(1, "rgba(242, 242, 242, 0)");
  } else {
    grad.addColorStop(0, `rgba(13, 248, 122, ${0.55 * blend})`);
    grad.addColorStop(0.5, `rgba(114, 255, 92, ${0.45 * blend})`);
    grad.addColorStop(1, "rgba(114, 255, 92, 0)");
  }
  drawPoly(pts, grad, null);
  return true;
}

function drawPath(path, experimental, rainbow, allowThrottle) {
  const pts = asPoints(path);
  if (pts.length < 2) return;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.lineWidth = 8;

  if (rainbow) {
    for (let i = 0; i < pts.length - 1; i++) {
      const hue = (rainbowHue + i * 8) % 360;
      ctx.strokeStyle = `hsla(${hue}, 95%, 55%, 0.9)`;
      ctx.beginPath();
      ctx.moveTo(pts[i][0], pts[i][1]);
      ctx.lineTo(pts[i + 1][0], pts[i + 1][1]);
      ctx.stroke();
    }
    return;
  }

  if (experimental) {
    const grad = ctx.createLinearGradient(0, pts[0][1], 0, pts[pts.length - 1][1]);
    grad.addColorStop(0, "rgba(13, 248, 122, 0.85)");
    grad.addColorStop(0.5, "rgba(114, 255, 92, 0.65)");
    grad.addColorStop(1, "rgba(114, 255, 92, 0)");
    ctx.strokeStyle = grad;
  } else {
    ctx.strokeStyle = allowThrottle === false
      ? "rgba(242, 242, 242, 0.35)"
      : PATH_WHITE;
  }
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
  ctx.stroke();
}

function drawLead(lead, chevronAlpha, canvasH) {
  const chevron = asPoints(lead.chevron);
  const metrics = lead.metrics || [];
  if (!metrics.length || !chevron.length || chevronAlpha <= 0) return;

  const apex = chevron[1] || chevron[0];
  const chevronX = apex[0];
  const chevronY = apex[1];
  const dRel = Number(lead.d_rel);
  const sz = Number.isFinite(dRel)
    ? Math.max(15, Math.min(30, (25 * 30) / (dRel / 3 + 30))) * 2.35
    : 55;
  const fontSize = 40;
  const lineHeight = 50;
  const margin = 20;
  const textAlpha = Math.max(0, Math.min(1, chevronAlpha));

  let textY = chevronY + sz + 15;
  const totalH = metrics.length * lineHeight;
  if (textY + totalH > (canvasH || 900) - margin) {
    const yMax = Math.min(chevronY, (canvasH || 900) - margin);
    textY = Math.max(margin, yMax - 15 - totalH);
  }

  ctx.font = `600 ${fontSize}px Inter, system-ui, sans-serif`;
  ctx.textBaseline = "top";

  metrics.forEach((line, i) => {
    const y = textY + i * lineHeight;
    if (y + lineHeight > (canvasH || 900) - margin) return;
    const text = formatMetricLine(line);
    const textW = ctx.measureText(text).width;
    let x = chevronX - textW / 2;
    x = Math.max(margin, Math.min(x, (lastOverlay?.width || 1600) - textW - margin));
    ctx.fillStyle = `rgba(0, 0, 0, ${0.78 * textAlpha})`;
    ctx.fillText(text, x + 2, y + 2);
    ctx.fillStyle = `rgba(255, 255, 255, ${textAlpha})`;
    ctx.fillText(text, x, y);
  });
}

function formatMetricLine(line) {
  const raw = String(line);
  const parts = raw.split(/\s+/);
  if (parts.length < 2) return tr(raw);
  const unit = tr(parts.pop());
  return `${parts.join(" ")} ${unit}`;
}

let overlayDrawEnabled = true;
let lastDrawFrameKey = null;
let lastDrawAnimKey = null;
let canvasRainbowRafId = null;
let pendingOverlayFrame = null;
let overlayDrawRafId = null;

export function hasOverlayGeometry() {
  const o = lastOverlay;
  if (!o) return false;
  return !!(
    (o.lanes && o.lanes.length > 0)
    || (o.path_polygon && o.path_polygon.length > 0)
    || (o.edges && o.edges.length > 0)
  );
}

export function scheduleDrawModelOverlay(data) {
  pendingOverlayFrame = data;
  if (overlayDrawRafId != null) return;
  overlayDrawRafId = requestAnimationFrame(() => {
    overlayDrawRafId = null;
    const frame = pendingOverlayFrame;
    pendingOverlayFrame = null;
    if (frame) drawModelOverlay(frame);
  });
}

function resolveAnimOverlay(data) {
  if (!data?.anim_only) return data;
  if (!lastOverlay) {
    window.dispatchEvent(new CustomEvent("opui:need-full-overlay"));
    return data;
  }
  const gk = data.geometry_key || lastOverlay.geometry_key;
  if (gk && lastOverlay.geometry_key && gk !== lastOverlay.geometry_key) return data;
  return {
    ...lastOverlay,
    path_blend: data.path_blend ?? lastOverlay.path_blend,
    chevron_alpha: data.chevron_alpha ?? lastOverlay.chevron_alpha,
    anim_key: data.anim_key,
    frame_key: data.frame_key,
    geometry_key: gk,
    width: data.width ?? lastOverlay.width,
    height: data.height ?? lastOverlay.height,
    _animFast: true,
  };
}

function stopCanvasRainbowLoop() {
  if (canvasRainbowRafId != null) {
    cancelAnimationFrame(canvasRainbowRafId);
    canvasRainbowRafId = null;
  }
  const host = document.getElementById("model-overlay");
  if (host) host.style.filter = "";
}

function scheduleCanvasRainbowLoop() {
  if (canvasRainbowRafId != null) return;
  const tick = () => {
    canvasRainbowRafId = null;
    if (!lastOverlay?.rainbow || isModelWebGLReady()) return;
    rainbowHue = (rainbowHue + 2) % 360;
    const host = document.getElementById("model-overlay");
    if (host) host.style.filter = `hue-rotate(${rainbowHue}deg)`;
    canvasRainbowRafId = requestAnimationFrame(tick);
  };
  canvasRainbowRafId = requestAnimationFrame(tick);
}

export function setModelOverlayEnabled(enabled) {
  overlayDrawEnabled = !!enabled;
  const host = document.getElementById("model-overlay");
  if (host && !enabled) {
    stopCanvasRainbowLoop();
    lastDrawFrameKey = null;
    lastDrawAnimKey = null;
    clearModelWebGL();
    ctx?.clearRect(0, 0, canvas?.width || 0, canvas?.height || 0);
  }
}

export function drawModelOverlay(data) {
  if (!overlayDrawEnabled || !data?.ok) return;

  if (data.clear) {
    stopCanvasRainbowLoop();
    lastOverlay = null;
    lastDrawFrameKey = null;
    lastDrawAnimKey = null;
    clearModelWebGL();
    if (ctx && canvas) ctx.clearRect(0, 0, canvas.width || 0, canvas.height || 0);
    return;
  }

  const merged = resolveAnimOverlay(data);
  if (data?.anim_only && !lastOverlay) return;
  const frameKey = merged.frame_key || null;
  const animKey = merged.anim_key || null;
  const animateOnly = !!merged._animate;
  const animFast = !!merged._animFast;

  if (!animateOnly) {
    if (animFast) {
      if (animKey && animKey === lastDrawAnimKey) return;
      if (animKey) lastDrawAnimKey = animKey;
      lastOverlay = merged;
    } else {
      lastOverlay = merged;
      if (frameKey && frameKey === lastDrawFrameKey) {
        if (merged.rainbow && !isModelWebGLReady()) scheduleCanvasRainbowLoop();
        else stopCanvasRainbowLoop();
        return;
      }
      if (frameKey) lastDrawFrameKey = frameKey;
      if (animKey) lastDrawAnimKey = animKey;
      if (merged.rainbow && !isModelWebGLReady()) scheduleCanvasRainbowLoop();
      else stopCanvasRainbowLoop();
    }
  } else if (!merged.rainbow) {
    return;
  }
  const host = document.getElementById("model-overlay");
  const w = merged.width || host?.clientWidth || 1600;
  const h = merged.height || host?.clientHeight || 900;

  if (isModelWebGLReady()) {
    drawModelWebGL(merged);
    if (ctx && canvas) {
      const dpr = window.devicePixelRatio || 1;
      const pw = Math.max(1, Math.floor(w * dpr));
      const ph = Math.max(1, Math.floor(h * dpr));
      if (canvas.width !== pw || canvas.height !== ph) {
        canvas.width = pw;
        canvas.height = ph;
        canvas.style.width = `${w}px`;
        canvas.style.height = `${h}px`;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      }
      ctx.clearRect(0, 0, w, h);
      const chevronAlpha = Number(merged.chevron_alpha) || 0;
      for (const lead of merged.leads || []) drawLead(lead, chevronAlpha, h);
    }
    return;
  }

  if (!ctx || !canvas) return;
  if (!animFast) {
    resize(w, h);
    ctx.clearRect(0, 0, w, h);

    for (const lane of merged.lanes || []) drawLane(lane);
    for (const edge of merged.edges || []) {
      const poly = asPoints(edge.polygon);
      if (poly.length >= 3) {
        const std = typeof edge.std === "number" ? edge.std : 0;
        const alpha = Math.max(0, Math.min(1, 1 - std));
        drawPoly(poly, `rgba(255, 0, 0, ${alpha * 0.45})`, `rgba(255, 0, 0, ${alpha})`, 2);
      }
    }
  } else {
    ctx.clearRect(0, 0, w, h);
    for (const lane of merged.lanes || []) drawLane(lane);
    for (const edge of merged.edges || []) {
      const poly = asPoints(edge.polygon);
      if (poly.length >= 3) {
        const std = typeof edge.std === "number" ? edge.std : 0;
        const alpha = Math.max(0, Math.min(1, 1 - std));
        drawPoly(poly, `rgba(255, 0, 0, ${alpha * 0.45})`, `rgba(255, 0, 0, ${alpha})`, 2);
      }
    }
  }
  const drewRibbon = drawPathRibbon(
    merged.path_polygon,
    merged.experimental,
    merged.rainbow,
    merged.allow_throttle !== false,
    merged.path_gradient,
    merged.path_blend,
  );
  if (!drewRibbon) {
    drawPath(merged.path, merged.experimental, merged.rainbow, merged.allow_throttle !== false);
  }
  const chevronAlpha = Number(merged.chevron_alpha) || 0;
  for (const lead of merged.leads || []) {
    const glow = asPoints(lead.glow);
    const chevron = asPoints(lead.chevron);
    const alpha = (lead.alpha ?? 180) / 255;
    if (!animFast) {
      if (glow.length >= 3) drawPoly(glow, `rgba(255, 196, 0, ${alpha * 0.35})`, null);
      if (chevron.length >= 3) drawPoly(chevron, LEAD_FILL, "rgba(255, 220, 80, 0.9)", 2);
    }
    drawLead(lead, chevronAlpha, h);
  }

}
