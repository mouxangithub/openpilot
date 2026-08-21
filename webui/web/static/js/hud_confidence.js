/** mici confidence ball — mirrors confidence_ball.py (right edge vertical dot). */

const RADIUS = 24;
const RC = 0.5;
const SIDE_INSET = 24;

let filtered = -0.5;
let lastTs = 0;

function filterStep(current, target, dt) {
  const alpha = 1 - Math.exp(-dt / RC);
  return current + (target - current) * alpha;
}

function colorsFor(status, confidence) {
  if (status === "lat_only") {
    return { top: "#00c8c8", bottom: "#00c8c8" };
  }
  if (status === "long_only") {
    return { top: "#961ca8", bottom: "#961ca8" };
  }
  if (status === "override") {
    return { top: "#ffffff", bottom: "#525252" };
  }
  if (status === "engaged") {
    if (confidence > 0.5) return { top: "#00ffcc", bottom: "#00ff26" };
    if (confidence > 0.2) return { top: "#ffc800", bottom: "#ff7300" };
    return { top: "#ff0015", bottom: "#ff0059" };
  }
  return { top: "#323232", bottom: "#0d0d0d" };
}

export function updateConfidenceBall(st) {
  const el = document.getElementById("confidence-ball");
  const wrap = document.getElementById("camera-wrap");
  if (!el || !wrap) return;

  const cb = st?.confidence_ball;
  if (!st?.started || !cb) {
    el.hidden = true;
    filtered = -0.5;
    lastTs = 0;
    return;
  }

  const now = performance.now();
  const dt = lastTs ? Math.min(0.2, (now - lastTs) / 1000) : 0;
  lastTs = now;
  filtered = filterStep(filtered, Number(cb.target ?? -0.5), dt);

  const h = wrap.clientHeight || 900;
  const w = wrap.clientWidth || 1600;
  const travel = Math.max(0, h - 2 * RADIUS);
  const y = (1 - filtered) * travel + RADIUS;
  const x = w - SIDE_INSET;

  const { top, bottom } = colorsFor(st.ui_status || "disengaged", filtered);
  el.hidden = false;
  el.style.left = `${x - RADIUS}px`;
  el.style.top = `${y - RADIUS}px`;
  el.style.width = `${RADIUS * 2}px`;
  el.style.height = `${RADIUS * 2}px`;
  el.style.background = `radial-gradient(circle at 50% 35%, ${top} 0%, ${bottom} 100%)`;
}
