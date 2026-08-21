/** Offroad screen saver — mirrors ScreenSaverSP bouncing logo when idle. */

import { tr } from "./i18n.js";

let overlay = null;
let animId = null;
let lastActivity = Date.now();
let active = false;
let dismissed = false;
let timeoutSec = 300;
let enabled = false;
let offroad = true;

const IDLE_MS = 5000;

function ensureOverlay() {
  if (overlay) return overlay;
  overlay = document.createElement("div");
  overlay.id = "opui-screensaver";
  overlay.className = "opui-screensaver";
  overlay.hidden = true;
  overlay.innerHTML = '<div class="opui-screensaver__logo">sunnypilot</div>';
  overlay.addEventListener("pointerdown", () => {
    dismissed = true;
    hideScreenSaver();
  });
  document.body.appendChild(overlay);
  return overlay;
}

function hideScreenSaver() {
  active = false;
  if (overlay) overlay.hidden = true;
  if (animId != null) {
    cancelAnimationFrame(animId);
    animId = null;
  }
}

function animateLogo(el) {
  const wrap = ensureOverlay();
  const logo = el || wrap.querySelector(".opui-screensaver__logo");
  if (!logo) return;

  let x = 80;
  let y = 120;
  let vx = 2.2;
  let vy = 1.4;
  const pad = 24;

  const tick = () => {
    if (!active) return;
    const w = wrap.clientWidth || window.innerWidth;
    const h = wrap.clientHeight || window.innerHeight;
    const lw = logo.offsetWidth || 200;
    const lh = logo.offsetHeight || 48;
    x += vx;
    y += vy;
    if (x <= pad || x + lw >= w - pad) vx *= -1;
    if (y <= pad || y + lh >= h - pad) vy *= -1;
    logo.style.transform = `translate(${x}px, ${y}px)`;
    animId = requestAnimationFrame(tick);
  };
  animId = requestAnimationFrame(tick);
}

function showScreenSaver() {
  if (active || dismissed || !enabled || !offroad) return;
  const wrap = ensureOverlay();
  wrap.hidden = false;
  active = true;
  animateLogo(wrap.querySelector(".opui-screensaver__logo"));
}

function onUserActivity() {
  lastActivity = Date.now();
  if (active) {
    dismissed = true;
    hideScreenSaver();
    return;
  }
  dismissed = false;
}

export function updateScreenSaverState(st) {
  if (!st) return;
  offroad = !st.started;
  enabled = !!st.screensaver_enabled;
  timeoutSec = Math.max(60, Number(st.screensaver_timeout_sec) || 300);
  if (!enabled || !offroad) {
    hideScreenSaver();
    dismissed = false;
  }
}

export function initScreenSaver() {
  for (const ev of ["pointerdown", "pointermove", "keydown", "wheel", "touchstart"]) {
    window.addEventListener(ev, onUserActivity, { passive: true });
  }
  setInterval(() => {
    if (!enabled || !offroad || dismissed || active) return;
    const idleFor = Date.now() - lastActivity;
    if (idleFor >= IDLE_MS) showScreenSaver();
    if (active && idleFor >= timeoutSec * 1000) {
      // Native turns display off after duration; keep overlay visible until user taps.
    }
  }, 1000);
}
