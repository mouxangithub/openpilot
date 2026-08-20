/** E2E circular alerts + standstill timer — mirrors circular_alerts.py */

import { tr } from "./i18n.js";
import { TARGET_FPS } from "./fade_anim.js";

const GREEN_IMG = "/api/opui/assets/sunnypilot/selfdrive/assets/images/green_light.png";
const LEAD_IMG = "/api/opui/assets/sunnypilot/selfdrive/assets/images/lead_depart.png";
const E2E_DISPLAY_SEC = 3;

let e2eTimerSec = 0;
let e2eFrame = 0;
let standstillElapsed = 0;
let lastTs = 0;
let wasStandstill = false;
let seededTimer = false;

function syncDevUiAdj(devUi) {
  const mode = Number(devUi) || 0;
  const adj = mode === 2 || mode === 3 ? 180 : 100;
  document.documentElement.style.setProperty("--dev-ui-adj", `${adj}px`);
}

export function updateCircularAlert(st) {
  const wrap = document.getElementById("hud-circular-alert");
  if (!wrap) return;

  syncDevUiAdj(st?.developer_ui);

  const sp = st?.sp_hud || {};
  const green = !!sp.e2e_green_light;
  const lead = !!sp.e2e_lead_depart;
  const standstill = !!st?.standstill;
  const timerEnabled = !!st?.standstill_timer_enabled;
  const allowed = !!st?.circular_alert_allowed;

  const now = performance.now();
  const dt = lastTs ? Math.min(0.2, (now - lastTs) / 1000) : 0;
  lastTs = now;

  if (!st?.started || !allowed) {
    wrap.hidden = true;
    e2eTimerSec = 0;
    e2eFrame = 0;
    standstillElapsed = 0;
    seededTimer = false;
    wasStandstill = false;
    return;
  }

  if (green || lead) {
    e2eTimerSec = E2E_DISPLAY_SEC;
    e2eFrame += 1;
  } else if (e2eTimerSec > 0) {
    e2eTimerSec = Math.max(0, e2eTimerSec - dt);
    e2eFrame += 1;
  } else {
    e2eFrame = 0;
  }

  const showE2e = e2eTimerSec > 0;
  const showTimer = timerEnabled && standstill && !showE2e;

  if (showTimer) {
    const seed = sp.standstill_timer;
    if (!wasStandstill) {
      standstillElapsed = typeof seed === "number" && seed > 0 ? seed : 0;
      seededTimer = typeof seed === "number" && seed > 0;
    } else if (!seededTimer) {
      standstillElapsed += dt;
    }
  } else if (!standstill) {
    standstillElapsed = 0;
    seededTimer = false;
    e2eFrame = 0;
  } else {
    e2eFrame += 1;
  }
  wasStandstill = standstill;

  if (!showE2e && !showTimer) {
    wrap.hidden = true;
    return;
  }

  wrap.hidden = false;
  const ring = wrap.querySelector(".opui-hud-circular-ring");
  const img = document.getElementById("hud-circular-img");
  const text = document.getElementById("hud-circular-text");
  const stopped = document.getElementById("hud-circular-stopped");
  const timer = document.getElementById("hud-circular-timer");

  const pulseOn = (e2eFrame % TARGET_FPS) < (TARGET_FPS / 2.5);
  if (ring) {
    if (showE2e) {
      ring.style.boxShadow = pulseOn
        ? "0 0 0 8px rgba(255, 255, 255, 0.29)"
        : "0 0 0 8px rgba(0, 255, 0, 0.29)";
    } else {
      ring.style.boxShadow = "0 0 0 8px rgba(255, 255, 255, 0.29)";
    }
  }

  if (showE2e) {
    wrap.classList.add("is-e2e");
    if (stopped) stopped.hidden = true;
    if (timer) timer.hidden = true;
    if (text) text.hidden = false;
    if (img) {
      img.hidden = false;
      img.src = green ? GREEN_IMG : LEAD_IMG;
    }
    if (text) {
      text.hidden = false;
      text.textContent = green
        ? tr("GREEN\nLIGHT")
        : tr("LEAD VEHICLE\nDEPARTING");
      text.style.color = pulseOn ? "rgba(255,255,255,1)" : "rgba(0,255,0,0.75)";
    }
    return;
  }

  wrap.classList.remove("is-e2e");
  if (img) img.hidden = true;
  if (text) text.hidden = true;
  if (stopped) {
    stopped.hidden = false;
    stopped.textContent = tr("STOPPED");
  }
  if (timer) {
    timer.hidden = false;
    const minute = Math.floor(standstillElapsed / 60);
    const second = Math.floor(standstillElapsed % 60);
    timer.textContent = `${minute}:${String(second).padStart(2, "0")}`;
  }
}
