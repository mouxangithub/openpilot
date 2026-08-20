/**
 * sunnypilot BIG UI widget kit — dialogs + list rows matching raylib interactions.
 */

import { tr } from "./i18n.js";

const stack = [];

function assetUrl(rel) {
  return `/api/opui/assets/${rel.replace(/^\//, "")}`;
}

function paramIsOn(val) {
  const v = String(val ?? "").trim().toLowerCase();
  return v === "1" || v === "true" || v === "on";
}

export function experimentalE2eHtml() {
  return (
    `<h1>${tr("Experimental Mode")}</h1><br>`
    + `<p>${tr(
      "sunnypilot defaults to driving in chill mode. Experimental mode enables alpha-level features that aren't ready for chill mode. "
      + "Experimental features are listed below:",
    )}</p>`
    + `<h4>${tr("End-to-End Longitudinal Control")}</h4><br>`
    + `<p>${tr(
      "Let the driving model control the gas and brakes. sunnypilot will drive as it thinks a human would, including stopping for red lights and stop signs. "
      + "Since the driving model decides the speed to drive, the set speed will only act as an upper bound. This is an alpha quality feature; mistakes should be expected.",
    )}</p>`
    + `<h4>${tr("New Driving Visualization")}</h4><br>`
    + `<p>${tr(
      "The driving visualization will transition to the road-facing wide-angle camera at low speeds to better show some turns. "
      + "The Experimental mode logo will also be shown in the top right corner.",
    )}</p>`
  );
}

function pushModal(el, onBackdrop) {
  if (!el) return;
  el._backdropDismiss = onBackdrop || null;
  stack.push(el);
  el.removeAttribute("hidden");
  el.setAttribute("aria-hidden", "false");
  document.body.classList.add("opui-modal-open");
}

function popModal(el) {
  if (!el) return;
  const i = stack.indexOf(el);
  if (i >= 0) stack.pop();
  el._backdropDismiss = null;
  el.setAttribute("hidden", "");
  el.setAttribute("aria-hidden", "true");
  if (!stack.length) document.body.classList.remove("opui-modal-open");
}

function initModalBackdropDismiss() {
  document.querySelectorAll(".opui-modal").forEach((modal) => {
    modal.addEventListener("click", (e) => {
      if (e.target !== modal) return;
      const dismiss = modal._backdropDismiss;
      if (typeof dismiss === "function") dismiss();
    });
    modal.querySelector("[class*='opui-modal-card']")?.addEventListener("click", (e) => e.stopPropagation());
  });
}

initModalBackdropDismiss();

export function showConfirm(opts) {
  const {
    message = "",
    rich = false,
    confirmText = tr("Confirm"),
    cancelText = tr("Cancel"),
    single = false,
  } = typeof opts === "string" ? { message: opts } : opts;

  return new Promise((resolve) => {
    const root = document.getElementById("modal-confirm");
    const msg = document.getElementById("modal-confirm-msg");
    const ok = document.getElementById("modal-confirm-ok");
    const cancel = document.getElementById("modal-confirm-cancel");
    if (!root || !msg) {
      resolve(window.confirm(message));
      return;
    }
    if (rich) {
      msg.innerHTML = message;
      msg.classList.add("opui-rich");
    } else {
      msg.textContent = message;
      msg.classList.remove("opui-rich");
    }
    ok.textContent = confirmText;
    cancel.textContent = cancelText;
    cancel.hidden = single;
    const done = (v) => {
      popModal(root);
      ok.removeEventListener("click", onOk);
      cancel.removeEventListener("click", onCancel);
      root.removeEventListener("cancel", onCancel);
      resolve(v);
    };
    const onOk = () => done(true);
    const onCancel = () => done(false);
    pushModal(root, onCancel);
    ok.addEventListener("click", onOk);
    cancel.addEventListener("click", onCancel);
    root.addEventListener("cancel", onCancel);
  });
}

export function showQrPair(opts = {}) {
  const {
    title = tr("Scan QR code"),
    url = "",
    qrDataUrl = "",
    onPoll = null,
    pollMs = 1500,
  } = opts;
  return new Promise((resolve) => {
    const root = document.getElementById("modal-qr");
    const titleEl = document.getElementById("modal-qr-title");
    const img = document.getElementById("modal-qr-img");
    const hint = document.getElementById("modal-qr-hint");
    const openBtn = document.getElementById("modal-qr-open");
    const closeBtn = document.getElementById("modal-qr-close");
    if (!root || !img) {
      if (url) window.open(url, "_blank", "noopener");
      resolve(true);
      return;
    }
    if (titleEl) titleEl.textContent = title;
    if (hint) hint.textContent = url;
    img.src = qrDataUrl || "";
    img.hidden = !qrDataUrl;
    if (openBtn) openBtn.textContent = tr("Open link");
    if (closeBtn) closeBtn.textContent = tr("Close");
    const finish = () => {
      if (pollTimer) clearInterval(pollTimer);
      popModal(root);
      openBtn?.removeEventListener("click", onOpen);
      closeBtn?.removeEventListener("click", onClose);
      resolve(true);
    };
    const onOpen = () => {
      if (url) window.open(url, "_blank", "noopener");
    };
    const onClose = () => finish();
    let pollTimer = null;
    if (typeof onPoll === "function") {
      pollTimer = setInterval(async () => {
        try {
          if (await onPoll()) finish();
        } catch { /* ignore poll errors */ }
      }, pollMs);
    }
    openBtn?.addEventListener("click", onOpen);
    closeBtn?.addEventListener("click", onClose, { once: true });
    pushModal(root, onClose);
  });
}

export function showKeyboard(opts = {}) {
  const {
    title = "Enter text",
    value = "",
    password = false,
    minLen = 0,
    maxLen = 64,
  } = opts;

  return new Promise((resolve) => {
    const root = document.getElementById("modal-keyboard");
    const titleEl = document.getElementById("keyboard-title");
    const display = document.getElementById("keyboard-display");
    const grid = document.getElementById("keyboard-grid");
    if (!root || !grid || !display) {
      resolve(window.prompt(title, value));
      return;
    }
    titleEl.textContent = title;
    const cancelBtn = document.getElementById("keyboard-cancel");
    const confirmBtn = document.getElementById("keyboard-confirm");
    if (cancelBtn) cancelBtn.textContent = tr("Cancel");
    if (confirmBtn) confirmBtn.textContent = tr("Confirm");
    let buf = value;
    const render = () => {
      display.textContent = password ? "•".repeat(buf.length) : buf;
      if (confirmBtn) confirmBtn.disabled = buf.length < minLen;
    };
    render();

    const layouts = {
      alpha: [
        "123", "q", "w", "e", "r", "t", "y", "u", "i", "o", "p",
        "ABC", "a", "s", "d", "f", "g", "h", "j", "k", "l", "⌫",
        "#+=", "z", "x", "c", "v", "b", "n", "m", "Enter",
      ],
      num: [
        "ABC", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0",
        "", "-", "_", ".", "@", "", "", "", "", "⌫", "Enter",
      ],
    };
    let mode = "alpha";

    const paint = () => {
      grid.innerHTML = "";
      for (const key of layouts[mode]) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "opui-kb-key" + (key === "Enter" ? " opui-kb-key--wide" : "");
        btn.textContent = key || "";
        if (!key) btn.disabled = true;
        btn.addEventListener("click", () => {
          if (key === "⌫") buf = buf.slice(0, -1);
          else if (key === "Enter") {
            if (buf.length >= minLen) finish(buf);
          } else if (key === "123") mode = "num";
          else if (key === "ABC") mode = "alpha";
          else if (key === "#+=") mode = "num";
          else if (buf.length < maxLen) buf += key;
          render();
          if (key === "123" || key === "ABC" || key === "#+=") paint();
        });
        grid.appendChild(btn);
      }
    };
    paint();

    const finish = (v) => {
      popModal(root);
      resolve(v);
    };
    const onConfirm = () => {
      if (buf.length >= minLen) finish(buf);
    };
    document.getElementById("keyboard-cancel")?.addEventListener("click", () => finish(null), { once: true });
    confirmBtn?.addEventListener("click", onConfirm, { once: true });
    pushModal(root, () => finish(null));
  });
}

export function showMultiOption(opts) {
  const {
    title = tr("Select"),
    options = [],
    selected = 0,
    current = selected,
  } = opts;
  return new Promise((resolve) => {
    const root = document.getElementById("modal-multi");
    const titleEl = document.getElementById("multi-title");
    const list = document.getElementById("multi-list");
    const cancelBtn = document.getElementById("multi-cancel");
    const selectBtn = document.getElementById("multi-select");
    if (!root || !list || !selectBtn) {
      resolve(selected);
      return;
    }
    titleEl.textContent = title;
    if (cancelBtn) cancelBtn.textContent = tr("Cancel");
    selectBtn.textContent = tr("Select");
    list.innerHTML = "";
    let pending = selected;
    const updateSelectState = () => {
      selectBtn.disabled = pending === current;
      list.querySelectorAll(".opui-multi-opt").forEach((btn, i) => {
        btn.classList.toggle("selected", i === pending);
      });
    };
    options.forEach((opt, i) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "opui-multi-opt" + (i === pending ? " selected" : "");
      btn.textContent = typeof opt === "string" ? opt : opt.label;
      btn.addEventListener("click", () => {
        pending = i;
        updateSelectState();
      });
      list.appendChild(btn);
    });
    updateSelectState();
    const finish = (value) => {
      popModal(root);
      cancelBtn?.removeEventListener("click", onCancel);
      selectBtn.removeEventListener("click", onSelect);
      resolve(value);
    };
    const onCancel = () => finish(null);
    const onSelect = () => {
      if (selectBtn.disabled) return;
      finish(pending);
    };
    cancelBtn?.addEventListener("click", onCancel, { once: true });
    selectBtn.addEventListener("click", onSelect, { once: true });
    pushModal(root, onCancel);
  });
}

export function showTree(opts) {
  const {
    title = tr("Select"),
    folders = [],
    selectedRef = "",
    searchable = true,
    onFavorite,
    getFolders,
  } = opts;

  return new Promise((resolve) => {
    const root = document.getElementById("modal-tree");
    const titleEl = document.getElementById("tree-title");
    const body = document.getElementById("tree-body");
    const searchWrap = document.getElementById("tree-search-wrap");
    const search = document.getElementById("tree-search");
    const selectBtn = document.getElementById("tree-select");
    if (!root || !body) {
      resolve(null);
      return;
    }
    titleEl.textContent = title;
    searchWrap.hidden = !searchable;
    if (search) {
      search.value = "";
      search.placeholder = tr("Search");
    }
    const cancelBtn = document.getElementById("tree-cancel");
    if (cancelBtn) cancelBtn.textContent = tr("Cancel");
    if (selectBtn) selectBtn.textContent = tr("Select");
    let pick = selectedRef;
    let query = "";
    let treeFolders = folders;
    const expanded = new Set(
      treeFolders.filter((f) => f.name != null && f.name !== "").map((f) => f.name),
    );

    const reloadFolders = async () => {
      if (typeof getFolders === "function") {
        treeFolders = await getFolders();
      }
    };

    const syncSelectBtn = () => {
      if (!selectBtn) return;
      const enabled = !!pick && pick !== selectedRef;
      selectBtn.disabled = !enabled;
      selectBtn.classList.toggle("opui-btn--primary", enabled);
    };

    const folderLabel = (name) => {
      if (name == null || name === "") return tr("Default");
      return name;
    };

    const render = () => {
      body.innerHTML = "";
      const q = query.toLowerCase().trim();
      const searching = !!q;
      for (const folder of treeFolders) {
        const bundles = (folder.bundles || []).filter((b) => {
          const label = (b.name || b.ref || "").toLowerCase();
          const folderName = folderLabel(folder.name).toLowerCase();
          return !q || label.includes(q) || folderName.includes(q);
        });
        if (!bundles.length) continue;
        const hasFolder = !!(folder.name != null && folder.name !== "");
        const isOpen = searching || !hasFolder || expanded.has(folder.name);
        if (hasFolder) {
          const hdr = document.createElement("button");
          hdr.type = "button";
          hdr.className = "opui-tree-dialog-item opui-tree-dialog-item--folder";
          hdr.textContent = `${isOpen ? "−" : "+"} ${folderLabel(folder.name)}`;
          hdr.addEventListener("click", () => {
            if (expanded.has(folder.name)) expanded.delete(folder.name);
            else expanded.add(folder.name);
            render();
          });
          body.appendChild(hdr);
          if (!isOpen) continue;
        }
        for (const b of bundles) {
          const row = document.createElement("button");
          row.type = "button";
          const indent = hasFolder ? " opui-tree-dialog-item--child" : "";
          row.className = `opui-tree-dialog-item${indent}` + (b.ref === pick ? " selected" : "");
          row.innerHTML = `<span class="opui-tree-dialog-label">${escapeHtml(b.name || b.ref)}</span>`;
          if (onFavorite) {
            const star = document.createElement("span");
            star.className = "opui-tree-star";
            star.textContent = b.fav ? "★" : "☆";
            star.addEventListener("click", async (e) => {
              e.stopPropagation();
              const result = await onFavorite(b.ref);
              if (result === false) return;
              await reloadFolders();
              render();
            });
            row.appendChild(star);
          }
          row.addEventListener("click", () => {
            pick = b.ref;
            syncSelectBtn();
            render();
          });
          body.appendChild(row);
        }
      }
    };

    if (search) search.oninput = () => { query = search.value; render(); };
    syncSelectBtn();
    const close = () => {
      popModal(root);
      resolve(null);
    };
    selectBtn.onclick = () => {
      popModal(root);
      resolve(pick);
    };
    document.getElementById("tree-cancel")?.addEventListener("click", close, { once: true });
    render();
    pushModal(root, close);
  });
}

export function showHtml(opts) {
  const { title = "", html = "" } = opts;
  return new Promise((resolve) => {
    const root = document.getElementById("modal-html");
    const titleEl = document.getElementById("html-title");
    const bodyEl = document.getElementById("html-body");
    const okBtn = document.getElementById("html-ok");
    if (!root || !bodyEl) {
      resolve(true);
      return;
    }
    if (titleEl) titleEl.textContent = title;
    bodyEl.innerHTML = normalizeHtmlFragment(html);
    if (okBtn) okBtn.textContent = tr("OK");
    const close = () => {
      popModal(root);
      resolve(true);
    };
    okBtn?.addEventListener("click", close, { once: true });
    pushModal(root, close);
  });
}

function normalizeHtmlFragment(html) {
  const raw = String(html || "").trim();
  if (!raw) return "";
  const tpl = document.createElement("template");
  tpl.innerHTML = raw;
  const body = tpl.content.querySelector("body");
  if (body) return body.innerHTML;
  return raw;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function bindRowExpand(row, w) {
  const text = row.querySelector(".opui-sp-row-text");
  if (!text) return;
  const hasDesc = !!(w.desc || w.desc_html || w.confirm_experimental);
  if (!hasDesc) return;

  if ((w.desc || w.desc_html) && !text.querySelector(".opui-sp-row-desc--expandable:not(.opui-sp-row-desc--experimental)")) {
    const descEl = document.createElement("div");
    descEl.className = "opui-sp-row-desc opui-sp-row-desc--expandable";
    descEl.hidden = true;
    if (w.desc_html) {
      descEl.innerHTML = w.desc_html;
    } else {
      descEl.innerHTML = escapeHtml(w.desc).replace(/\n/g, "<br>");
    }
    text.appendChild(descEl);
  }
  if (w.confirm_experimental && !text.querySelector(".opui-sp-row-desc--experimental")) {
    const expDesc = document.createElement("div");
    expDesc.className = "opui-sp-row-desc opui-sp-row-desc--expandable opui-sp-row-desc--experimental";
    expDesc.hidden = true;
    text.appendChild(expDesc);
  }

  text.classList.add("opui-sp-row-text--expandable");
  text.addEventListener("click", (e) => {
    if (e.target.closest("label, button, input, .opui-sp-toggle, .opui-multi-btn-group, .opui-option-bar, .opui-choice-group, .opui-sp-row-actions")) {
      return;
    }
    let open = false;
    text.querySelectorAll(".opui-sp-row-desc--expandable").forEach((el) => {
      el.hidden = !el.hidden;
      if (!el.hidden) open = true;
    });
    row.classList.toggle("opui-sp-row--desc-open", open);
  });
}

export function createSpToggle(w, panelData, globalState, handlers) {
  const row = document.createElement("div");
  row.className = "opui-sp-row" + (w.stacked ? " opui-sp-row--stacked opui-sp-row--toggle-below" : "");
  const checked = paramIsOn(w.value);
  const disabled = w.locked || (w.needs_cycle && globalState.engaged) || (w.offroad_only && !globalState.is_offroad);
  const toggleHtml = `
    <label class="opui-sp-toggle${disabled ? " disabled" : ""}${checked ? " on" : ""}">
      <input type="checkbox" ${checked ? "checked" : ""} ${disabled ? "disabled" : ""} />
      <span class="opui-sp-toggle-track"><span class="opui-sp-toggle-thumb"></span></span>
    </label>`;
  const textHtml = `
    <div class="opui-sp-row-text">
      ${w.label ? `<div class="opui-sp-row-title">${escapeHtml(w.label)}${w.locked ? " 🔒" : ""}</div>` : ""}
      ${w.needs_cycle ? `<div class="opui-sp-row-desc opui-sp-row-desc--hint">${tr("Changing this setting will restart sunnypilot if the car is powered on.")}</div>` : ""}
    </div>`;
  row.innerHTML = w.stacked ? `${textHtml}${toggleHtml}` : `${toggleHtml}${textHtml}`;
  bindRowExpand(row, { ...w, desc: w.desc || "" });
  const input = row.querySelector("input");
  const label = row.querySelector(".opui-sp-toggle");
  input?.addEventListener("change", async () => {
    const next = input.checked;
    if (w.onBeforeChange) {
      const proceed = await w.onBeforeChange(next, input);
      if (proceed === false) {
        input.checked = !next;
        label?.classList.toggle("on", input.checked);
        return;
      }
      if (proceed === "handled") {
        label?.classList.toggle("on", next);
        return;
      }
    }
    if (w.confirm && next) {
      const ok = await showConfirm({
        message: tr(w.confirm),
        confirmText: tr("OK"),
        cancelText: tr("Cancel"),
      });
      if (!ok) {
        input.checked = false;
        label?.classList.remove("on");
        return;
      }
    }
    if (w.confirm_experimental && next && !globalState.experimental_mode_confirmed) {
      const ok = await showConfirm({
        rich: true,
        message: experimentalE2eHtml(),
        confirmText: tr("Enable"),
        cancelText: tr("Cancel"),
      });
      if (!ok) {
        input.checked = false;
        label?.classList.remove("on");
        return;
      }
      await handlers.putParam("ExperimentalModeConfirmed", "1");
    }
    if (w.confirm_enable && next) {
      const ok = await showConfirm({
        message: tr(w.confirm_message || w.desc || w.label),
        confirmText: tr("Enable"),
        cancelText: tr("Cancel"),
      });
      if (!ok) {
        input.checked = false;
        label?.classList.remove("on");
        return;
      }
    }
    if (w.confirm_rich && next) {
      const ok = await showConfirm({
        rich: true,
        message: tr(w.confirm_message || w.desc || ""),
        confirmText: tr("Enable"),
        cancelText: tr("Cancel"),
      });
      if (!ok) {
        input.checked = false;
        label?.classList.remove("on");
        return;
      }
    }
    label?.classList.toggle("on", next);
    const res = await handlers.putParam(w.param, next ? "1" : "0", !!w.needs_cycle);
    if (!res.ok) {
      handlers.toast(res.error || "Save failed");
      input.checked = !input.checked;
      label?.classList.toggle("on", input.checked);
    }
  });
  return row;
}

export function createProgressRow(label, pct) {
  const row = document.createElement("div");
  row.className = "opui-sp-row opui-sp-row--progress";
  row.innerHTML = `
    <div class="opui-sp-row-text"><div class="opui-sp-row-title">${escapeHtml(label)}</div></div>
    <div class="opui-progress"><div class="opui-progress-fill" style="width:${Math.round(pct * 100)}%"></div></div>`;
  return row;
}

export function createDualButton(left, right, onLeft, onRight) {
  const row = document.createElement("div");
  row.className = "opui-dual-row";
  const btnClass = (opts) => [
    "opui-dual-btn",
    opts?.primary ? "primary" : "",
    opts?.danger ? "danger" : "",
  ].filter(Boolean).join(" ");
  row.innerHTML = `
    <button type="button" class="${btnClass(left)}" ${left.disabled ? "disabled" : ""}>${escapeHtml(left.label)}</button>
    <button type="button" class="${btnClass(right)}" ${right.disabled ? "disabled" : ""}>${escapeHtml(right.label)}</button>`;
  const [l, r] = row.querySelectorAll("button");
  l?.addEventListener("click", onLeft);
  r?.addEventListener("click", onRight);
  return row;
}
