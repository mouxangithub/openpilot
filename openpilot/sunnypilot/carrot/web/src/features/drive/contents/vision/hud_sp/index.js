"use strict";

/* sunnypilot onroad HUD overlay.
 *
 * Replaces the cluster-style carrot HUD on this fork: the base project is
 * sunnypilot, so the driving view follows webui's onroad presentation (speed
 * block, SLA sign, cruise set chip, road name, blinkers, blind spot, SCC
 * labels, rocket fuel, experimental button, torque bar, border states).
 *
 * Data flows through the same channel the carrot HUD used: vision_raw.js
 * rebuilds a compact payload from RAW_HUD_STATE and calls
 * DriveVisionHudContent.update(payload) -> CarrotHudOverlay.update(payload).
 * mapSpHudPayload() merges that compact payload with RAW_HUD_STATE so live and
 * replay present identically, matching the webui single-update behaviour.
 *
 * Lifecycle mirrors the carrot overlay (root/update/activate/deactivate/
 * relayout/setSuppressed/status/destroy) so the facade layer around it stays
 * unchanged.
 */

import { injectSpHudStyle, SP_IMAGES } from "./style.js";
import { mapSpHudPayload } from "./payload.js";
import { el, setText, setHidden } from "../hud/dom.js";
import { createHudLayoutObserver } from "../hud/layout.js";
import { createHudDebugFacade } from "../hud/debug.js";
import { CarrotHudDataBridge } from "../hud/data_bridge.js";

const installed = new WeakMap();
if (typeof globalThis === "object" && !globalThis.CarrotHudDataBridge) {
  globalThis.CarrotHudDataBridge = CarrotHudDataBridge;
}

/* Speed / unit / SLA text with the same units handled in mapSpHudPayload. */
function applySpeedText(node, value) {
  setText(node, value == null ? "" : String(value));
}

function applySlClasses(slaEl, data) {
  if (!slaEl) return;
  const hasLimit = data.speedLimit != null && data.speedLimit > 0;
  setHidden(slaEl, !hasLimit);
  if (!hasLimit) return;
  slaEl.classList.toggle("is-three-digit", String(data.speedLimit).length >= 3);
  slaEl.classList.toggle("is-assist", Boolean(data.slaAssistActive));
  slaEl.classList.toggle("is-overspeed", Boolean(data.speedLimitOver));
  slaEl.classList.toggle("is-invalid", false);
}

export function createSpHudOverlay(doc) {
  injectSpHudStyle(doc);
  const root = el(doc, "div", { class: "sp-hud", attrs: { "data-carrot-hud": "overlay-sp" } });

  /* road name (marquee) */
  const roadWrap = el(doc, "div", { class: "sp-hud-road", attrs: { hidden: "" } });
  const roadText = el(doc, "span", { class: "sp-hud-road__text" });
  roadWrap.appendChild(roadText);

  /* cruise set chip */
  const cruise = el(doc, "div", { class: "sp-hud-cruise", attrs: { hidden: "" } });
  const cruiseMax = el(doc, "div", { class: "sp-hud-cruise-max", text: "MAX" });
  const cruiseVal = el(doc, "div", { class: "sp-hud-cruise-val", text: "–" });
  cruise.append(cruiseMax, cruiseVal);

  /* SLA limit sign */
  const sla = el(doc, "div", { class: "sp-hud-sla", attrs: { hidden: "" } });
  const slaValue = el(doc, "div", { class: "sp-hud-sla-value" });
  sla.appendChild(slaValue);

  /* speed block */
  const speedBlock = el(doc, "div", { class: "sp-hud-speed-block" });
  const speedNode = el(doc, "span", { class: "sp-hud-speed", text: "" });
  const unitNode = el(doc, "span", { class: "sp-hud-unit", text: "" });
  speedBlock.append(speedNode, unitNode);

  /* blinkers + blind spot */
  const blinkerL = el(doc, "div", { class: "sp-hud-blinker sp-hud-blinker--l", attrs: { hidden: "" } });
  const blinkerR = el(doc, "div", { class: "sp-hud-blinker sp-hud-blinker--r", attrs: { hidden: "" } });
  const bslL = el(doc, "div", { class: "sp-hud-bsl sp-hud-bsl--l", attrs: { hidden: "" } });
  const bslR = el(doc, "div", { class: "sp-hud-bsl sp-hud-bsl--r", attrs: { hidden: "" } });

  /* SCC labels */
  const sccV = el(doc, "div", { class: "sp-hud-scc", text: "SCC-V", attrs: { hidden: "" } });
  const sccM = el(doc, "div", { class: "sp-hud-scc sp-hud-scc--map", text: "SCC-M", attrs: { hidden: "" } });

  /* rocket fuel */
  const rocket = el(doc, "div", { class: "sp-hud-rocket", attrs: { hidden: "" } });
  const rocketUp = el(doc, "div", { class: "sp-hud-rocket__up" });
  const rocketDown = el(doc, "div", { class: "sp-hud-rocket__down" });
  rocket.append(rocketUp, rocketDown);

  /* torque bar (canvas, mirrors webui #torque-bar-canvas) */
  const torque = doc.createElement("canvas");
  torque.className = "sp-hud-torque";
  torque.setAttribute("aria-hidden", "true");
  torque.hidden = true;
  const torqueCtx = torque.getContext("2d");

  /* experimental button (shown when the panel knows the param) */
  const expBtn = el(doc, "button", {
    class: "sp-hud-exp",
    attrs: { type: "button", hidden: "", title: "Experimental" },
  });
  const expIcon = doc.createElement("img");
  expIcon.className = "sp-hud-exp-icon";
  expIcon.setAttribute("alt", "");
  expIcon.src = "/shared-assets/icons/chffr_wheel.png";
  const expIconMode = "/shared-assets/icons/experimental.png";
  expBtn.appendChild(expIcon);
  /* Mirrors webui bindExperimentalButton: toggle ExperimentalMode through the
   * fork's own param endpoint (7000 /api/param_set). */
  let expHeld = null;
  let expHoldUntil = 0;
  if (typeof doc.defaultView?.fetch === "function" || typeof globalThis.fetch === "function") {
    expBtn.addEventListener?.("click", async () => {
      if (expBtn.disabled) return;
      const now = Date.now();
      const next = expHeld != null && expHoldUntil > now ? !expHeld : !(expBtn.dataset.on === "1");
      try {
        const response = await fetch("/api/param_set", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: "ExperimentalMode", value: next ? "1" : "0" }),
        });
        if (!response.ok) return;
        expHeld = next;
        expHoldUntil = now + 2000;
        expBtn.dataset.on = next ? "1" : "0";
        expBtn.classList.toggle("is-engaged", next);
      } catch {}
    });
  }

  root.append(
    roadWrap,
    cruise,
    sla,
    speedBlock,
    blinkerL,
    blinkerR,
    bslL,
    bslR,
    sccV,
    sccM,
    rocket,
    torque,
    expBtn,
  );

  const widgets = {
    speedNode, unitNode, cruise, cruiseMax, cruiseVal,
    sla, slaValue, roadWrap, roadText,
    blinkerL, blinkerR, bslL, bslR, sccV, sccM,
    rocket, rocketUp, rocketDown, torque, expBtn, expIcon,
  };

  const suppressions = new Set();
  let active = false;
  let destroyed = false;
  let lastData = null;
  let layoutObserver = null;

  function syncVisibility() {
    const hidden = destroyed || !active || suppressions.size > 0;
    root.hidden = hidden;
    root.inert = hidden;
    root.classList.toggle("is-hud-suppressed", hidden);
    if (hidden) root.setAttribute("aria-hidden", "true");
    else root.removeAttribute("aria-hidden");
    return !hidden;
  }

  function applyLayout() {
    // cqw container scaling handles all sizing; no extra JS layout needed.
  }

  function scheduleLayout() {
    if (layoutObserver) layoutObserver.schedule();
    else applyLayout();
  }

  function setBlinker(el, active, isBlink) {
    if (!el) return;
    setHidden(el, !active);
    el.classList.toggle("is-blink", Boolean(active && isBlink));
  }

  function drawTorque(torqueEl, output) {
    if (!torqueEl || !torqueCtx) return;
    const width = torqueEl.width;
    const height = torqueEl.height;
    torqueCtx.clearRect(0, 0, width, height);
    if (output == null) return;
    const clamped = Math.max(-1, Math.min(1, Number(output)));
    if (Math.abs(clamped) < 0.01) return;
    const scale = 3;
    const halfH = height / 2;
    const midX = width / 2;
    const len = Math.abs(clamped) * scale * 0.15 * width;
    const color = clamped > 0 ? "rgba(255,255,255,0.85)" : "rgba(244,172,54,0.85)";
    torqueCtx.strokeStyle = color;
    torqueCtx.lineWidth = Math.max(2, height * 0.08);
    torqueCtx.lineCap = "round";
    torqueCtx.beginPath();
    torqueCtx.moveTo(midX, halfH);
    torqueCtx.lineTo(midX + (clamped > 0 ? len : -len), halfH);
    torqueCtx.stroke();
  }

  function update(payload) {
    if (destroyed || !payload) return false;
    // Merge with the compact RAW_HUD_STATE the runtime keeps on window: the
    // classic update path passes only a derived compact payload, and the
    // sunnypilot fields (SLA resolver, road name, blindspot, alerts) live in
    // the raw services. Replay fills the same window.CarrotHudState.
    const rawState = (typeof globalThis !== "undefined" && globalThis.CarrotHudState)
      ? globalThis.CarrotHudState
      : {};
    const data = mapSpHudPayload(payload, rawState);
    lastData = data;

    /* speed + unit */
    const speedOn = data.speed != null;
    setHidden(speedNode, !speedOn);
    applySpeedText(speedNode, speedOn ? String(data.speed) : "");
    setHidden(unitNode, !speedOn);
    if (speedOn) setText(unitNode, data.unit || (data.isMetric === false ? "mph" : "km/h"));

    /* cruise set chip - mirrors webui onroad.js:
     *   shown while started and cruise is available; the value reads "--" until
     *   a set speed exists (openpilot is_cruise_set), so an unset cruise never
     *   renders a phantom number. */
    const cruiseOn = data.started && data.isCruiseAvailable !== false;
    setHidden(cruise, !cruiseOn);
    if (cruiseOn) {
      const cruiseSet = Boolean(data.isCruiseSet) && data.setSpeed != null;
      cruise.classList.toggle("is-set", cruiseSet);
      cruiseMax.classList.toggle("is-set", cruiseSet);
      setText(cruiseVal, cruiseSet ? String(data.setSpeed) : "–");
    }

    /* SLA */
    applySlClasses(sla, data);
    setText(slaValue, data.speedLimit != null ? String(data.speedLimit) : "---");

    /* road name */
    if (data.roadName) {
      setHidden(roadWrap, false);
      setText(roadText, data.roadName);
    } else {
      setHidden(roadWrap, true);
    }

    /* blinkers */
    setBlinker(blinkerL, data.leftBlinker, true);
    setBlinker(blinkerR, data.rightBlinker, true);

    /* blind spot */
    setHidden(bslL, !data.leftBlindspot);
    setHidden(bslR, !data.rightBlindspot);

    /* SCC labels */
    setHidden(sccV, !data.sccVisionEnabled);
    setHidden(sccM, !data.sccMapEnabled);
    sccV.classList.toggle("is-override", Boolean(data.longOverride));
    sccM.classList.toggle("is-override", Boolean(data.longOverride));

    /* rocket fuel */
    const accel = Number(data.rocketFuel) || 0;
    const rocketOn = data.started && Math.abs(accel) > 0.01;
    setHidden(rocket, !rocketOn);
    if (rocketOn) {
      const barPct = Math.min(100, Math.abs(accel) * 22);
      rocket.style.setProperty("--rocket-up", accel > 0 ? `${barPct}%` : "0%");
      rocket.style.setProperty("--rocket-down", accel < 0 ? `${barPct}%` : "0%");
    }

    /* torque bar */
    const torqueOn = data.started && data.steerOutput != null;
    setHidden(torque, !torqueOn);
    if (torqueOn) {
      torque.width = Math.max(50, Math.floor(root.clientWidth || 800));
      torque.height = Math.max(10, Math.floor(clampCqw(root, 0.08)));
      drawTorque(torque, data.steerOutput);
    }

    /* border state */
    const state = String(data.uiStatus || "disengaged");
    root.classList.remove("is-engaged", "is-lat_only", "is-long_only", "is-override", "is-disengaged");
    root.classList.add(`is-${state}`);
    root.classList.toggle("is-engaged", state === "engaged");

    /* experimental button: visible only while started with longitudinal
     * control. The param state is refreshed from the same runtime params the
     * panel keeps, so the icon reflects the real ExperimentalMode. */
    const expKnown = typeof globalThis !== "undefined"
      && globalThis.CarrotLiveRuntimeState?.runtime?.params?.ExperimentalMode != null;
    const expOn = expKnown
      ? String(globalThis.CarrotLiveRuntimeState.runtime.params.ExperimentalMode) === "1"
      : (data.experimental === true);
    setHidden(expBtn, !data.started);
    if (data.started) {
      expBtn.dataset.on = expOn ? "1" : "0";
      expBtn.classList.toggle("is-engaged", expOn);
      expBtn.disabled = expOn == null;
      if (expIcon.src !== (expOn ? expIconMode : "/shared-assets/icons/chffr_wheel.png")) {
        expIcon.src = expOn ? expIconMode : "/shared-assets/icons/chffr_wheel.png";
      }
    }
    return true;
  }

  function clampCqw(node, ratio) {
    const width = node?.clientWidth || 800;
    return Math.max(10, width * ratio);
  }

  function relayout(viewport) {
    if (destroyed) return false;
    const width = Number(viewport?.width);
    const height = Number(viewport?.height);
    if (width > 0 && height > 0) scheduleLayout();
    return width > 0 && height > 0;
  }

  function startLayout(target) {
    if (destroyed) return false;
    if (!layoutObserver) {
      layoutObserver = createHudLayoutObserver(root, applyLayout, target);
    }
    layoutObserver?.schedule();
    return Boolean(layoutObserver);
  }

  function activate() {
    if (destroyed) return false;
    const changed = !active;
    active = true;
    syncVisibility();
    return changed;
  }

  function deactivate() {
    if (destroyed) return false;
    const changed = active;
    active = false;
    syncVisibility();
    return changed;
  }

  function setSuppressed(reason, value) {
    if (destroyed) return false;
    const key = String(reason || "external");
    if (value) suppressions.add(key);
    else suppressions.delete(key);
    return syncVisibility();
  }

  function status() {
    return Object.freeze({
      active,
      destroyed,
      visible: !root.hidden,
      suppressions: Object.freeze(Array.from(suppressions)),
      data: lastData,
    });
  }

  function destroy() {
    if (destroyed) return false;
    active = false;
    destroyed = true;
    suppressions.clear();
    layoutObserver?.destroy?.();
    layoutObserver = null;
    syncVisibility();
    root.remove?.();
    return true;
  }

  syncVisibility();
  return {
    root,
    update,
    relayout,
    activate,
    deactivate,
    setSuppressed,
    status,
    destroy,
    startClock: () => false,
    stopClock: () => false,
    startLayout,
  };
}

export function installSpHudOverlay(target = globalThis, options = {}) {
  if (installed.has(target)) return installed.get(target);
  const doc = options.document || target.document;
  if (!doc) return null;
  const stage = options.stage || doc.getElementById?.("carrotStage");
  if (!stage) {
    if (!target.__carrotSpHudDeferred) {
      target.__carrotSpHudDeferred = true;
      const retry = () => { target.__carrotSpHudDeferred = false; installSpHudOverlay(target, options); };
      if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", retry, { once: true });
      else target.setTimeout?.(retry, 0);
    }
    return null;
  }

  const overlay = createSpHudOverlay(doc);
  stage.appendChild(overlay.root);
  overlay.startLayout(target);

  const handleViewportLayout = (event) => overlay.relayout(event.detail);
  target.addEventListener?.("carrot:viewportlayout", handleViewportLayout, { passive: true });

  const destroyOverlay = overlay.destroy;
  overlay.destroy = () => {
    target.removeEventListener?.("carrot:viewportlayout", handleViewportLayout);
    const changed = destroyOverlay();
    if (changed) {
      installed.delete(target);
      if (target.CarrotHudOverlay === overlay) target.CarrotHudOverlay = null;
      if (target.CarrotHudDebug) target.CarrotHudDebug = null;
    }
    return changed;
  };

  target.CarrotHudOverlay = overlay;
  target.CarrotHudDebug = createHudDebugFacade(target, overlay);
  installed.set(target, overlay);
  target.DriveVisionHudContent?.syncPresentation?.();
  return overlay;
}

export { SP_IMAGES };
export * from "./payload.js";
