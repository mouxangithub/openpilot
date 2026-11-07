/**
 * Onroad navigation instruction card (BIG UI navigation_card.py, web port).
 *
 * Data: `nav_card` block in the state payload — {enabled, valid, collapsed,
 * instruction: {maneuverPrimaryText, maneuverSecondaryText, maneuverDistance(m),
 * maneuverType, maneuverModifier, nextManeuverType, nextManeuverModifier}}.
 *
 * Interaction: tap toggles collapsed (NavInstructionCollapsed param); long-press
 * 0.65 s cancels the route (POST /api/opui/navcard/cancel, which removes
 * NavDestination and blanks NavInstructionState — matching the BIG UI behaviour).
 *
 * Icons come from the openpilot tree through the existing asset API
 * (/api/opui/assets/...), so there is no icon copy to keep in sync.
 */

import { apiPost, apiPut } from "./api.js";

const $ = (id) => document.getElementById(id);

const ASSET_BASE = "/api/opui/assets/selfdrive/assets/navigation/";
const FALLBACK_ICON = "direction_turn_straight.png";
const NAV_CANCEL_HOLD_MS = 650;

const MODIFIER_SUFFIX = {
  left: "left",
  right: "right",
  straight: "straight",
  slightLeft: "slight_left",
  slightRight: "slight_right",
  sharpLeft: "sharp_left",
  sharpRight: "sharp_right",
};

let pressStartedAt = null;
let cancelFired = false;
let collapseBound = false;

function normalizeType(type) {
  let t = (type || "turn").toLowerCase();
  if (t === "rotary") t = "roundabout";
  else if (t === "new name" || t === "continue") t = "turn";
  return t.replace(/ /g, "_");
}

function iconUrl(type, modifier) {
  if ((modifier || "") === "uturn") {
    return ASSET_BASE + "direction_uturn.png";
  }
  const suffix = MODIFIER_SUFFIX[modifier];
  const name = suffix ? `direction_${normalizeType(type)}_${suffix}.png` : `direction_${normalizeType(type)}.png`;
  return ASSET_BASE + name;
}

function formatDistance(distanceM, isMetric) {
  const d = Math.max(0, Number(distanceM) || 0);
  if (isMetric) {
    if (d < 1000) {
      const step = d < 500 ? 25 : 50;
      return `${Math.round(d / step) * step} m`;
    }
    const km = d / 1000;
    return km >= 10 ? `${Math.floor(km)} km` : `${km.toFixed(1)} km`;
  }
  const ft = d * 3.28084;
  if (ft < 1000) {
    const step = ft <= 100 ? 10 : 50;
    return `${Math.round(ft / step) * step} ft`;
  }
  const mi = ft / 5280;
  return mi >= 10 ? `${Math.floor(mi)} mi` : `${mi.toFixed(1)} mi`;
}

function setIcon(imgEl, type, modifier) {
  if (!imgEl) return;
  const url = iconUrl(type, modifier);
  if (imgEl.dataset.src !== url) {
    imgEl.dataset.src = url;
    imgEl.onerror = () => {
      imgEl.onerror = null;
      imgEl.src = ASSET_BASE + FALLBACK_ICON;
    };
    imgEl.src = url;
  }
}

export function updateNavCard(st) {
  const card = $("hud-navcard");
  if (!card || !st?.ok || !st.started) {
    if (card) card.hidden = true;
    return;
  }
  const nc = st.nav_card || {};
  const show = Boolean(nc.enabled) && Boolean(nc.valid) && nc.instruction != null;
  card.hidden = !show;
  if (!show) return;

  const ins = nc.instruction;
  const collapsed = Boolean(nc.collapsed);
  card.classList.toggle("is-collapsed", collapsed);

  setIcon($("hud-navcard-icon"), ins.maneuverType, ins.maneuverModifier);
  $("hud-navcard-dist").textContent = formatDistance(ins.maneuverDistance, st.is_metric);
  $("hud-navcard-primary").textContent = ins.maneuverPrimaryText || "";

  const hasNext = Boolean(ins.nextManeuverType || ins.nextManeuverModifier);
  const thenEl = $("hud-navcard-then");
  thenEl.hidden = collapsed || !hasNext;
  if (hasNext) {
    setIcon($("hud-navcard-next-icon"), ins.nextManeuverType, ins.nextManeuverModifier);
  }

  if (!collapseBound) {
    collapseBound = true;
    bindInteraction(card);
  }
}

function bindInteraction(card) {
  card.addEventListener("pointerdown", () => {
    pressStartedAt = Date.now();
    cancelFired = false;
  });
  card.addEventListener("pointerup", async () => {
    if (pressStartedAt == null || cancelFired) {
      pressStartedAt = null;
      return;
    }
    const held = Date.now() - pressStartedAt;
    pressStartedAt = null;
    if (held >= NAV_CANCEL_HOLD_MS) {
      cancelFired = true;
      await apiPost("/api/opui/navcard/cancel");
      card.hidden = true;
      return;
    }
    const collapsed = !card.classList.contains("is-collapsed");
    await apiPut("/api/opui/params/NavInstructionCollapsed", { value: collapsed ? "1" : "0" });
  });
  card.addEventListener("pointerleave", () => {
    pressStartedAt = null;
  });
}
