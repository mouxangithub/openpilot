/** Web UI self-update (git) — separate from openpilot Software UPDATE pill. */

import { apiGet, apiPost } from "./api.js";
import { tr } from "./i18n.js";

const POLL_MS = 10 * 60 * 1000;
let lastStatus = null;
let pollTimer = null;
let modalOpen = false;

function $(id) {
  return document.getElementById(id);
}

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function commitListHtml(commits) {
  if (!commits?.length) {
    return `<p class="opui-webui-update-empty">${escapeHtml(tr("No new commit messages."))}</p>`;
  }
  return `<ul class="opui-webui-update-commits">${commits.map((c) => (
    `<li><code>${escapeHtml(c.hash || "")}</code><span>${escapeHtml(c.title || "")}</span></li>`
  )).join("")}</ul>`;
}

export function getWebUiUpdateStatus() {
  return lastStatus;
}

export async function fetchWebUiUpdate({ fetchRemote = false } = {}) {
  const q = fetchRemote ? "?fetch=1" : "";
  const data = await apiGet(`/api/opui/webui-update${q}`).catch(() => ({ ok: false }));
  if (data?.ok) lastStatus = data;
  syncWebUiUpdateRow();
  return data;
}

function setModalVisible(show) {
  const modal = $("modal-webui-update");
  if (!modal) return;
  modal.hidden = !show;
  document.body.classList.toggle("opui-modal-open", show);
  modalOpen = show;
}

export function openWebUiUpdateModal(status = lastStatus) {
  const modal = $("modal-webui-update");
  const body = $("webui-update-body");
  const title = $("webui-update-title");
  const applyBtn = $("webui-update-apply");
  const laterBtn = $("webui-update-later");
  const checkBtn = $("webui-update-check");
  if (!modal || !body) return;

  const st = status || lastStatus || {};
  const local = st.local_short || "—";
  const remote = st.remote_short || local;
  const branch = st.branch || "main";
  const available = !!st.available;

  if (title) {
    title.textContent = available ? tr("Web UI update available") : tr("Web UI");
  }

  const statusText = available
    ? tr("New commits on {branch}").replace("{branch}", branch)
    : tr("Web UI is up to date");

  body.innerHTML = `
    <div class="opui-webui-update-versions${available ? " is-available" : ""}">
      <span class="opui-webui-update-badge" title="${escapeHtml(tr("Current"))}">${escapeHtml(local)}</span>
      ${available ? `<span class="opui-webui-update-arrow" aria-hidden="true">→</span>
      <span class="opui-webui-update-badge is-new" title="${escapeHtml(tr("Available"))}">${escapeHtml(remote)}</span>` : ""}
    </div>
    <p class="opui-webui-update-summary">${escapeHtml(statusText)}</p>
    ${st.fetch_error ? `<p class="opui-webui-update-error">${escapeHtml(st.fetch_error)}</p>` : ""}
    <div class="opui-webui-update-commits-wrap">
      <div class="opui-webui-update-commits-label">${escapeHtml(tr("Changes"))}</div>
      ${commitListHtml(st.commits)}
    </div>
    <p class="opui-webui-update-hint">${escapeHtml(tr("This updates only the Web UI files, not openpilot firmware."))}</p>`;

  if (applyBtn) {
    applyBtn.hidden = !available;
    applyBtn.disabled = false;
    applyBtn.textContent = tr("Update now");
  }
  if (laterBtn) {
    laterBtn.textContent = available ? tr("Later") : tr("Close");
  }
  if (checkBtn) {
    checkBtn.hidden = false;
    checkBtn.disabled = false;
    checkBtn.textContent = tr("Check again");
  }
  setModalVisible(true);
}

async function dismissUpdate(commit) {
  await apiPost("/api/opui/webui-update/dismiss", { commit: commit || lastStatus?.remote_commit || "" });
  if (lastStatus) {
    lastStatus = { ...lastStatus, show_prompt: false, dismissed_commit: commit || lastStatus.remote_commit };
  }
  syncWebUiUpdateRow();
}

async function applyUpdate() {
  const applyBtn = $("webui-update-apply");
  if (applyBtn) {
    applyBtn.disabled = true;
    applyBtn.textContent = tr("Updating...");
  }
  const res = await apiPost("/api/opui/webui-update/apply").catch((err) => ({
    ok: false,
    error: err?.message || tr("Update failed"),
  }));
  if (!res.ok) {
    if (applyBtn) {
      applyBtn.disabled = false;
      applyBtn.textContent = tr("Update now");
    }
    const body = $("webui-update-body");
    if (body) {
      body.insertAdjacentHTML("beforeend", `<p class="opui-webui-update-error">${escapeHtml(res.error || tr("Update failed"))}</p>`);
    }
    return;
  }
  setModalVisible(false);
  const url = new URL(window.location.href);
  url.searchParams.set("v", String(Date.now()));
  window.location.replace(url.toString());
}

export async function checkWebUiUpdate({ fetchRemote = true, autoPrompt = false } = {}) {
  const st = await fetchWebUiUpdate({ fetchRemote });
  if (!st?.ok) return st;
  if (autoPrompt && st.show_prompt && !modalOpen) {
    openWebUiUpdateModal(st);
  }
  return st;
}

export function renderWebUiUpdateRow() {
  const row = document.createElement("div");
  row.className = "opui-sp-row opui-sp-row--has-action opui-webui-update-row";
  row.id = "webui-update-software-row";
  row.innerHTML = `
    <div class="opui-sp-row-text">
      <div class="opui-sp-row-title">${escapeHtml(tr("Web UI"))}</div>
    </div>
    <div class="opui-sp-row-value" id="webui-update-software-desc">${escapeHtml(tr("Loading..."))}</div>
    <button type="button" class="opui-btn opui-btn--action" id="webui-update-software-btn">${escapeHtml(tr("CHECK"))}</button>`;
  row.querySelector("#webui-update-software-btn")?.addEventListener("click", async () => {
    const btn = row.querySelector("#webui-update-software-btn");
    if (btn) {
      btn.disabled = true;
      btn.textContent = tr("CHECK");
    }
    await checkWebUiUpdate({ fetchRemote: true, autoPrompt: false });
    openWebUiUpdateModal(lastStatus);
    if (btn) {
      btn.disabled = false;
      syncWebUiUpdateRow();
    }
  });
  return row;
}

export function syncWebUiUpdateRow() {
  const desc = $("webui-update-software-desc");
  const btn = $("webui-update-software-btn");
  const row = $("webui-update-software-row");
  if (!desc) return;
  const st = lastStatus;
  if (!st?.ok) {
    desc.textContent = st?.error
      ? `${tr("Update status unavailable")} (${st.error})`
      : tr("Update status unavailable");
    if (btn) btn.textContent = tr("CHECK");
    return;
  }
  if (st.git === false) {
    desc.textContent = st.message || tr("Web UI is not a git checkout");
    row?.classList.remove("is-update-available");
    if (btn) btn.textContent = tr("CHECK");
    return;
  }
  const local = st.local_short || "—";
  if (st.available) {
    desc.textContent = tr("Update available: {local} → {remote}")
      .replace("{local}", local)
      .replace("{remote}", st.remote_short || "?");
    row?.classList.add("is-update-available");
    if (btn) btn.textContent = tr("UPDATE");
  } else {
    desc.textContent = tr("Up to date ({commit})").replace("{commit}", local);
    row?.classList.remove("is-update-available");
    if (btn) btn.textContent = tr("CHECK");
  }
}

export function refreshWebUiUpdateI18n() {
  syncWebUiUpdateRow();
  const modal = $("modal-webui-update");
  if (modal && !modal.hidden && lastStatus) {
    openWebUiUpdateModal(lastStatus);
  }
}

export function initWebUiUpdate() {
  const laterBtn = $("webui-update-later");
  const applyBtn = $("webui-update-apply");
  const checkBtn = $("webui-update-check");

  laterBtn?.addEventListener("click", async () => {
    if (lastStatus?.available) {
      await dismissUpdate(lastStatus?.remote_commit);
    }
    setModalVisible(false);
  });

  applyBtn?.addEventListener("click", () => applyUpdate());

  checkBtn?.addEventListener("click", async () => {
    if (checkBtn) {
      checkBtn.disabled = true;
      checkBtn.textContent = tr("Checking...");
    }
    await checkWebUiUpdate({ fetchRemote: true, autoPrompt: false });
    openWebUiUpdateModal(lastStatus);
    if (checkBtn) {
      checkBtn.disabled = false;
      checkBtn.textContent = tr("Check again");
    }
  });

  checkWebUiUpdate({ fetchRemote: true, autoPrompt: true });
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(() => {
    checkWebUiUpdate({ fetchRemote: true, autoPrompt: true });
  }, POLL_MS);
}
