/** Offroad home layout — Prime card, experimental banner, Firehose setup, UPDATE/ALERTS pills. */

import { tr, trn } from "./i18n.js";
import { apiGet, apiPost } from "./api.js";
import { runSoftwareInstallFlow, runAgnosUpdateFlow } from "./system_wait_overlay.js";
import { reopenOnboarding } from "./onboarding.js";

function assetUrl(rel) {
  return `/api/opui/assets/${rel.replace(/^\//, "")}`;
}

const PRIME_FEATURES = [
  "Remote access",
  "24/7 LTE connectivity",
  "1 year of drive storage",
  "Remote snapshots",
];

const HOME_SKELETON = `
  <div class="opui-home-skeleton">
    <div class="opui-home-skeleton-bar"></div>
    <div class="opui-home-skeleton-bar opui-home-skeleton-bar--short"></div>
  </div>`;

let homeView = "home";
let lastHome = null;

export function showHomeLoading() {
  const prime = document.getElementById("home-prime");
  const setup = document.getElementById("home-setup");
  if (prime && !prime.dataset.loaded) prime.innerHTML = HOME_SKELETON;
  if (setup && !setup.dataset.loaded) setup.innerHTML = HOME_SKELETON;
}

export function updateHomeScreen(home) {
  if (!home?.ok) return;
  lastHome = home;

  const versionEl = document.getElementById("home-version");
  const descEl = document.getElementById("home-desc");
  if (descEl) descEl.textContent = home.version_text || "";

  renderHomePills(home);
  renderStartupBlockers(home);
  renderHomeView(home);

  const expBanner = document.getElementById("home-exp-banner");
  if (expBanner && homeView === "home") {
    expBanner.hidden = false;
    expBanner.classList.toggle("opui-home-exp--experimental", !!home.experimental_mode);
    expBanner.classList.toggle("opui-home-exp--chill", !home.experimental_mode);
    const icon = expBanner.querySelector(".opui-home-exp-icon");
    if (icon) {
      icon.src = assetUrl(home.experimental_mode
        ? "selfdrive/assets/icons/experimental_grey.png"
        : "selfdrive/assets/icons/couch.png");
    }
    const label = expBanner.querySelector(".opui-home-exp-label");
    if (label) {
      label.textContent = home.experimental_mode
        ? tr("EXPERIMENTAL MODE ON")
        : tr("CHILL MODE ON");
    }
  } else if (expBanner) {
    expBanner.hidden = true;
  }

  if (homeView === "home") {
    renderPrimeCard(home);
    renderSetupCard(home);
  }
}

export async function refreshHomeScreen() {
  showHomeLoading();
  try {
    const home = await apiGet("/api/opui/home");
    updateHomeScreen(home);
  } catch (_) { /* keep skeleton */ }
}

function renderStartupBlockers(home) {
  let el = document.getElementById("home-startup-blockers");
  const leftCol = document.querySelector(".opui-home-col--left");
  if (!el && leftCol) {
    el = document.createElement("div");
    el.id = "home-startup-blockers";
    el.className = "opui-home-blockers";
    leftCol.insertBefore(el, leftCol.firstChild);
  }
  if (!el) return;

  const blockers = home.startup_blockers || [];
  const mgrErr = home.manager_error;
  const agnosPending = !!home.agnos_update_required;
  if (!blockers.length && !mgrErr && !agnosPending) {
    el.hidden = true;
    el.innerHTML = "";
    return;
  }

  el.hidden = false;
  let html = "";
  if (agnosPending) {
    const fromVer = home.agnos_current_version || "?";
    const toVer = home.agnos_target_version || "?";
    const actionLabel = home.agnos_ready_to_reboot ? tr("REBOOT") : tr("INSTALL");
    html += `
      <div class="opui-setup-card opui-setup-card--warn" id="home-agnos-card">
        <h3 class="opui-setup-title">${escapeHtml(tr("AGNOS Update"))}</h3>
        <p class="opui-setup-desc">${escapeHtml(tr("Operating system update required (~1GB download)."))}</p>
        <p class="opui-setup-desc">${escapeHtml(`${fromVer} → ${toVer}`)}</p>
        <button type="button" class="opui-btn opui-btn--primary opui-setup-btn" id="home-agnos-action">${escapeHtml(actionLabel)}</button>
      </div>`;
  }
  if (mgrErr) {
    html += `
      <div class="opui-setup-card opui-setup-card--danger">
        <h3 class="opui-setup-title">${escapeHtml(tr("Manager failed to start"))}</h3>
        <pre class="opui-manager-error">${escapeHtml(mgrErr)}</pre>
      </div>`;
  }
  if (blockers.length) {
    const onboardingIds = new Set(["accepted_terms", "accepted_terms_sp", "completed_training"]);
    const needsOnboarding = blockers.some((b) => onboardingIds.has(b.id));
    html += `
      <div class="opui-setup-card opui-setup-card--warn">
        <h3 class="opui-setup-title">${escapeHtml(tr("Cannot start driving"))}</h3>
        <ul class="opui-blocker-list">
          ${blockers.map((b) => `<li>${escapeHtml(tr(b.message) || b.message)}</li>`).join("")}
        </ul>
        ${needsOnboarding ? `<button type="button" class="opui-btn opui-btn--primary opui-setup-btn" id="home-onboarding-action">${escapeHtml(tr("Continue setup"))}</button>` : ""}
      </div>`;
  }
  el.innerHTML = html;
  document.getElementById("home-onboarding-action")?.addEventListener("click", async () => {
    const blockers = home.startup_blockers || [];
    const phase = blockers.some((b) => b.id === "completed_training") && !blockers.some((b) => b.id === "accepted_terms" || b.id === "accepted_terms_sp")
      ? "training"
      : undefined;
    await reopenOnboarding(phase);
  });
  document.getElementById("home-agnos-action")?.addEventListener("click", async () => {
    const btn = document.getElementById("home-agnos-action");
    if (btn) btn.disabled = true;
    await runAgnosUpdateFlow({ readyToReboot: !!home.agnos_ready_to_reboot });
    if (btn) btn.disabled = false;
    await refreshHomeScreen();
  });
}

function renderHomePills(home) {
  const wrap = document.getElementById("home-pills");
  const updateBtn = document.getElementById("home-pill-update");
  const alertsBtn = document.getElementById("home-pill-alerts");
  if (!wrap || !updateBtn || !alertsBtn) return;

  const showUpdate = !!home.update_visible;
  const alertCount = Number(home.alert_count) || 0;
  const showAlerts = alertCount > 0;

  wrap.hidden = !(showUpdate || showAlerts);
  updateBtn.hidden = !showUpdate;
  alertsBtn.hidden = !showAlerts;

  updateBtn.classList.toggle("is-active", homeView === "update");
  alertsBtn.classList.toggle("is-active", homeView === "alerts");
  updateBtn.textContent = tr("UPDATE");
  alertsBtn.textContent = trn("{} ALERT", "{} ALERTS", alertCount);
}

function renderHomeView(home) {
  const content = document.querySelector(".opui-home-content");
  const overlay = document.getElementById("home-overlay");
  const body = document.getElementById("home-overlay-body");
  const actions = document.getElementById("home-overlay-actions");
  if (!content || !overlay || !body || !actions) return;

  if (homeView === "home") {
    overlay.hidden = true;
    content.hidden = false;
    return;
  }

  content.hidden = true;
  overlay.hidden = false;
  actions.innerHTML = "";

  if (homeView === "update") {
    body.innerHTML = `
      <h2 class="opui-home-overlay-title">${escapeHtml(home.new_description || tr("Update available"))}</h2>
      <div class="opui-home-overlay-html">${home.new_release_notes || `<p>${escapeHtml(tr("No release notes available."))}</p>`}</div>`;
    const close = actionBtn(tr("Close"), () => setHomeView("home"));
    actions.appendChild(close);
    if (home.update_available) {
      actions.appendChild(actionBtn(tr("Reboot and Update"), async () => {
        await runSoftwareInstallFlow();
      }, "primary"));
    } else {
      actions.appendChild(actionBtn(tr("CHECK"), async () => {
        await apiPost("/api/opui/action/updater_check");
        await refreshHomeScreen();
      }));
    }
    if (home.fetch_available || home.update_available) {
      actions.appendChild(actionBtn(tr("Snooze Update"), async () => {
        const { apiPut } = await import("./api.js");
        await apiPut("/api/opui/params/SnoozeUpdate", { value: "1" });
        setHomeView("home");
        await refreshHomeScreen();
      }, "dark"));
    }
    return;
  }

  if (homeView === "alerts") {
    const alerts = home.offroad_alerts || [];
    body.innerHTML = alerts.length
      ? alerts.map((a) => `
        <div class="opui-offroad-alert ${a.severity > 0 ? "opui-offroad-alert--high" : ""}">
          ${escapeHtml(a.text)}
        </div>`).join("")
      : `<p class="opui-muted">${escapeHtml(tr("No alerts"))}</p>`;
    actions.appendChild(actionBtn(tr("Close"), () => setHomeView("home")));
    const hasConnectivity = alerts.some((a) => a.key === "Offroad_ConnectivityNeeded");
    const hasActuation = alerts.some((a) => a.key === "Offroad_ExcessiveActuation");
    if (hasActuation) {
      actions.appendChild(actionBtn(tr("Acknowledge Excessive Actuation"), async () => {
        await apiPost("/api/opui/action/dismiss_offroad_alert", { key: "Offroad_ExcessiveActuation" });
        setHomeView("home");
        await refreshHomeScreen();
      }, "dark"));
    } else if (hasConnectivity) {
      actions.appendChild(actionBtn(tr("Snooze Update"), async () => {
        const { apiPut } = await import("./api.js");
        await apiPut("/api/opui/params/SnoozeUpdate", { value: "1" });
        setHomeView("home");
        await refreshHomeScreen();
      }, "dark"));
    }
  }
}

function actionBtn(label, onClick, variant = "") {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = `opui-btn opui-home-overlay-btn${variant ? ` opui-btn--${variant}` : ""}`;
  btn.textContent = label;
  btn.addEventListener("click", onClick);
  return btn;
}

function setHomeView(view) {
  homeView = view;
  if (lastHome) updateHomeScreen(lastHome);
}

export function bindHomeHeader() {
  document.getElementById("home-pill-update")?.addEventListener("click", () => {
    setHomeView(homeView === "update" ? "home" : "update");
  });
  document.getElementById("home-pill-alerts")?.addEventListener("click", () => {
    setHomeView(homeView === "alerts" ? "home" : "alerts");
  });
}

export function applyLiveStartupBlockers(st) {
  if (!lastHome || !st || st.started) return;
  updateHomeScreen({
    ...lastHome,
    startup_blockers: st.startup_blockers || [],
    ignition: st.ignition,
    can_start: st.can_start,
  });
}

function renderPrimeCard(home) {
  const el = document.getElementById("home-prime");
  if (!el) return;
  el.dataset.loaded = "1";

  if (home.prime) {
    el.innerHTML = `
      <div class="opui-prime opui-prime--subscribed">
        <div class="opui-prime-check"><img src="/api/opui/assets/icons/checkmark.png" alt="" /> ${escapeHtml(tr("SUBSCRIBED"))}</div>
        <div class="opui-prime-brand">${escapeHtml(tr("comma prime"))}</div>
      </div>`;
    return;
  }

  el.innerHTML = `
    <div class="opui-prime opui-prime--upsell">
      <h3 class="opui-prime-title">${escapeHtml(tr("Upgrade Now"))}</h3>
      <p class="opui-prime-desc">${escapeHtml(tr("Become a comma prime member at connect.comma.ai"))}</p>
      <div class="opui-prime-features-title">${escapeHtml(tr("PRIME FEATURES:"))}</div>
      <ul class="opui-prime-features">
        ${PRIME_FEATURES.map((f) => `<li><span class="opui-prime-tick"><img src="/api/opui/assets/icons/checkmark.png" alt="" /></span>${escapeHtml(tr(f))}</li>`).join("")}
      </ul>
    </div>`;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderSetupCard(home) {
  const el = document.getElementById("home-setup");
  if (!el) return;
  el.dataset.loaded = "1";

  if (!home.paired) {
    el.innerHTML = `
      <div class="opui-setup-card">
        <h3 class="opui-setup-title">${escapeHtml(tr("Finish Setup"))}</h3>
        <p class="opui-setup-desc">${escapeHtml(tr("Pair your device with comma connect (connect.comma.ai) and claim your comma prime offer."))}</p>
        <button type="button" class="opui-btn opui-btn--primary opui-setup-btn" id="btn-pair-device">${escapeHtml(tr("Pair device"))}</button>
      </div>`;
    document.getElementById("btn-pair-device")?.addEventListener("click", () => {
      window.dispatchEvent(new CustomEvent("opui:open-settings", { detail: { panel: "device" } }));
    }, { once: true });
    return;
  }

  el.innerHTML = `
    <div class="opui-setup-card opui-setup-card--firehose">
      <h3 class="opui-setup-title">
        <img class="opui-setup-firehose-icon" src="${assetUrl("sunnypilot/selfdrive/assets/offroad/icon_firehose.png")}" alt="" />
        ${escapeHtml(tr("🔥 Firehose Mode 🔥"))}
      </h3>
      <p class="opui-setup-desc">${escapeHtml(tr("Maximize your training data uploads to improve openpilot's driving models."))}</p>
      <button type="button" class="opui-btn opui-btn--primary opui-setup-btn" id="btn-open-firehose">${escapeHtml(tr("Open"))}</button>
    </div>`;
  document.getElementById("btn-open-firehose")?.addEventListener("click", () => {
    window.dispatchEvent(new CustomEvent("opui:open-settings", { detail: { panel: "firehose" } }));
  }, { once: true });
}
