// ── LAN services ──────────────────────────────────────────────────────────
// The device runs three web services on the same address: this panel (7000),
// the webui submodule (5080) and the OP assistant (5090). Reaching them used to
// mean typing a URL by hand; this block lists each with its live status and
// opens it in a new tab.
//
// The probe is `/api/lan_services` because the browser cannot check the sibling
// ports itself (different origin, no CORS) - the server probes them over
// loopback/LAN and returns one flag per service.

const LAN_SERVICE_ICON_BY_ID = {
  carrot: "CW",
  webui: "UI",
  op: "AI",
};

const LAN_SERVICE_DESC_KEYS = {
  carrot: ["lan_service_carrot_desc", "This settings panel"],
  webui: ["lan_service_webui_desc", "sunnypilot on-device web interface"],
  op: ["lan_service_op_desc", "OP assistant (AI chat and tools)"],
};

function lanServiceOpen(url) {
  if (!url) return;
  window.open(url, "_blank", "noopener,noreferrer");
}

function lanServiceCard(service, t) {
  const id = String(service?.id || "");
  const label = service?.label || id;
  const url = String(service?.url || "");
  const online = Boolean(service?.online);
  const [descKey, descFallback] = LAN_SERVICE_DESC_KEYS[id] || ["", ""];
  const desc = descKey ? t(descKey, descFallback) : "";
  const stateText = online ? t("lan_service_online", "online") : t("lan_service_offline", "offline");
  // 7000 is serving this page, so an "offline" flag there means the probe
  // could not resolve the host - never claim the panel itself is down.
  const self = id === "carrot";
  const state = self ? "online" : (online ? "online" : "offline");

  const card = document.createElement("a");
  card.className = `lan-service lan-service--${state}`;
  card.setAttribute("role", "listitem");
  card.dataset.lanService = id;
  if (url) {
    card.href = url;
    card.target = "_blank";
    card.rel = "noopener noreferrer";
  }
  card.innerHTML = `
    <span class="lan-service__icon" aria-hidden="true">${escapeHtml(LAN_SERVICE_ICON_BY_ID[id] || "··")}</span>
    <span class="lan-service__body">
      <span class="lan-service__name">${escapeHtml(label)}</span>
      <span class="lan-service__desc">${escapeHtml(desc)}</span>
      <span class="lan-service__url">${escapeHtml(url ? url.replace(/^https?:\/\//, "") : "-")}</span>
    </span>
    <span class="lan-service__state">
      <span class="lan-service__dot" aria-hidden="true"></span>
      <span class="lan-service__state-text">${escapeHtml(stateText)}</span>
    </span>`;
  return card;
}

function renderLanServices(root, payload, t) {
  const services = Array.isArray(payload?.services) ? payload.services : [];
  root.innerHTML = "";
  if (!services.length) {
    const empty = document.createElement("div");
    empty.className = "muted lan-services__empty";
    empty.textContent = t("lan_service_unavailable", "LAN services unavailable");
    root.appendChild(empty);
    return;
  }
  services.forEach((service) => root.appendChild(lanServiceCard(service, t)));
}

function initLanServices(options = {}) {
  const root = document.getElementById("toolsLanServices");
  const hint = document.getElementById("lanServicesHint");
  const titleEl = document.getElementById("lanServicesTitle");
  const t = options.t || ((key, fallback) => (typeof getUIText === "function" ? getUIText(key, fallback) : fallback));
  if (!root || root.dataset.lanServicesBound === "1") return;
  root.dataset.lanServicesBound = "1";

  if (titleEl) titleEl.textContent = t("lan_services_title", "LAN Services");
  if (hint) hint.textContent = t("lan_services_hint", "Opens in a new tab. Every service runs on this device.");

  const refresh = async () => {
    try {
      const payload = await requestJson("/api/lan_services", { cache: "no-store" });
      renderLanServices(root, payload, t);
    } catch {
      renderLanServices(root, null, t);
    }
  };

  // Anchor clicks already navigate; keep middle-click / ctrl-click working and
  // never let a plain left click reload this panel.
  root.addEventListener("click", (event) => {
    const card = event.target.closest?.("[data-lan-service]");
    if (!card || !card.getAttribute("href")) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    lanServiceOpen(card.href);
  });

  refresh();
  document.addEventListener("carrot:languagechange", () => {
    if (titleEl) titleEl.textContent = t("lan_services_title", "LAN Services");
    if (hint) hint.textContent = t("lan_services_hint", "Opens in a new tab. Every service runs on this device.");
    refresh();
  });
}

// runtime.js calls this from initToolsPage, the same way it starts the eGPU and
// bluetooth cards.
Object.assign(globalThis, { initLanServices });
export { initLanServices };
