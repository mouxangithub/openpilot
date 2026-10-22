"use strict";

function bindDeviceTabEvents(container) {
  bindDeviceDisabledControls(container);
  bindDeviceToggleRows(container);
  bindDevicePersonality(container);
  bindDeviceLanguage(container);
  bindDeviceSpControls(container);

  bindDeviceAction(container, "btnDeviceReboot", "/api/reboot", getUIText("confirm_reboot", "Reboot now?"));
  bindDeviceAction(container, "btnDevicePoweroff", "/api/poweroff", getUIText("power_off_confirm", "Power off device?"));
  bindDeviceAction(container, "btnDeviceRecalib", "/api/recalibrate", getUIText("reset_calibration_confirm", "Reset calibration and reboot?"));

  const trainingButton = container.querySelector("#btnDeviceTraining");
  if (trainingButton) {
    trainingButton.addEventListener("click", async () => {
      const ok = await appConfirm(getUIText("review_training_confirm", "Are you sure you want to review the training guide?"), {
        title: getUIText("review_training_guide", "Review Training Guide"),
        confirmLabel: getUIText("review", "Review"),
      });
      if (ok) openTrainingGuide();
    });
  }

  const calibrationStatusButton = container.querySelector("#btnDeviceCalibrationStatus");
  if (calibrationStatusButton) {
    calibrationStatusButton.addEventListener("click", () => openCalibrationStatusModal());
  }

  const regulatoryButton = container.querySelector("#btnDeviceRegulatory");
  if (regulatoryButton) {
    regulatoryButton.addEventListener("click", () => {
      openRegulatoryInfo().catch((err) => {
        showAppToast(err.message || getUIText("regulatory_load_failed", "Failed to load regulatory information."), { tone: "error" });
      });
    });
  }

  container.querySelectorAll("[data-ssh-action]").forEach((button) => {
    button.addEventListener("click", () => handleSshKeysButton(button));
  });
}

function bindDeviceToggleRows(container) {
  container.querySelectorAll(".device-toggle .c-switch__input").forEach((input) => {
    input.addEventListener("change", async (event) => {
      const toggle = event.target.closest(".device-toggle");
      const param = toggle?.dataset.param;
      if (!param) return;
      const confirmKey = toggle?.dataset.confirmKey || "";
      const confirmedParam = toggle?.dataset.confirmedParam || "";
      const alreadyConfirmed = toggle?.dataset.confirmed === "1";
      try {
        if (event.target.checked && confirmKey && !alreadyConfirmed) {
          const ok = await appConfirm(getUIText(confirmKey, ""), {
            title: getUIText("confirm_title", "Confirm"),
            confirmLabel: getUIText("enable", "Enable"),
          });
          if (!ok) {
            event.target.checked = false;
            return;
          }
          if (confirmedParam) {
            await setParam(confirmedParam, 1);
            toggle.dataset.confirmed = "1";
          }
        }
        await setParam(param, event.target.checked ? 1 : 0);
        if (event.target.checked && (param === "JoystickDebugMode" || param === "LongitudinalManeuverMode")) {
          const otherParam = param === "JoystickDebugMode" ? "LongitudinalManeuverMode" : "JoystickDebugMode";
          await setParam(otherParam, 0);
          const otherToggle = container.querySelector(`.device-toggle[data-param="${otherParam}"] .c-switch__input`);
          if (otherToggle) otherToggle.checked = false;
        }
      } catch (err) {
        showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
        event.target.checked = !event.target.checked;
      }
    });
  });
}

function bindDevicePersonality(container) {
  const btnPersonality = container.querySelector("#btnDevicePersonality");
  if (!btnPersonality) return;

  async function cyclePersonality() {
    let current = 1;
    try {
      const values = await bulkGet(["LongitudinalPersonality"]);
      current = Number(values.LongitudinalPersonality ?? 1);
    } catch {}

    const currentIndex = PERSONALITY_OPTIONS.findIndex((entry) => entry.value === current);
    const nextOption = PERSONALITY_OPTIONS[(Math.max(0, currentIndex) + 1) % PERSONALITY_OPTIONS.length];
    try {
      await setParam("LongitudinalPersonality", nextOption.value);
      btnPersonality.textContent = getUIText(nextOption.labelKey, nextOption.defaultLabel);
    } catch (err) {
      showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
    }
  }

  // Same commit contract as the CarrotPilot tab: this button cycles the
  // driving personality on a single tap, so a scroll that starts on it must
  // not change anything.
  const gesture = window.CarrotUI?.numericStepper?.createGesture;
  if (!gesture) {
    console.error("[DeviceTab] commit gesture component is unavailable");
    return;
  }
  gesture(btnPersonality, { onCommit: () => { cyclePersonality(); } });
}

function bindDeviceLanguage(container) {
  const langSelect = container.querySelector("#deviceLanguageSelect");
  if (!langSelect) return;
  langSelect.addEventListener("change", async (event) => {
    try {
      await setParam("LanguageSetting", event.target.value);
      if (typeof setWebLanguage === "function") {
        setWebLanguage(event.target.value, { persist: true });
      }
      showAppToast(getUIText("device_lang_changed", "Language changed, reboot required."), { tone: "info" });
    } catch (err) {
      showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
    }
  });
}

function bindDeviceDisabledControls(container) {
  const showMessage = (event) => {
    event.preventDefault();
    event.stopPropagation();
    showAppToast(getUIText("device_only_control", "This can only be controlled on the device."), { tone: "info" });
  };

  container.querySelectorAll("[data-device-disabled=\"true\"]").forEach((el) => {
    el.addEventListener("click", showMessage);
    el.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      showMessage(event);
    });
  });
}

function bindDeviceAction(container, id, endpoint, confirmMessage = "") {
  const button = container.querySelector(`#${id}`);
  if (!button) return;
  button.addEventListener("click", async () => {
    // The app dialog everywhere else uses. Reboot and power off were the only
    // actions still on the browser's own confirm(), which cannot be themed or
    // translated — the most consequential buttons had the most foreign prompt.
    if (confirmMessage) {
      const confirmed = await appConfirm(confirmMessage, {
        title: getUIText("confirm_title", "Confirm"),
        confirmLabel: getUIText("ok", "OK"),
        cancelLabel: getUIText("cancel", "Cancel"),
      });
      if (!confirmed) return;
    }
    try {
      await postJson(endpoint, {});
      showAppToast(getUIText("action_triggered", "Action triggered"), { tone: "info" });
    } catch (err) {
      showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
    }
  });
}

async function getCalibrationStatusMessage() {
  const payload = await getJson("/api/calibration_status");
  const calib = payload.calibration || {};
  let message = getUIText(
    "calibration_status_desc",
    "openpilot requires the device to be mounted within 4° left or right and within 5° up or 9° down. openpilot is continuously calibrating, resetting is rarely required.",
  );
  if (calib.calibrated) {
    message += "\n\n" + getUIText("calibration_position_desc", "Current position: pitch {pitch}°, yaw {yaw}°", {
      pitch: calib.pitch ?? "-",
      yaw: calib.yaw ?? "-",
    });
  } else {
    message += "\n\n" + getUIText("uncalibrated", "Uncalibrated");
  }
  return message;
}

async function openCalibrationStatusModal() {
  try {
    const message = await getCalibrationStatusMessage();
    appAlert(message, {
      title: getUIText("calibration_status", "Calibration Status"),
    });
  } catch (err) {
    showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
  }
}

async function handleSshKeysButton(button) {
  const action = button.dataset.sshAction || "";
  if (action === "edit") {
    const status = getSshDialogStatus();
    await openSettingFormDialog({
      title: getUIText("ssh_github_username", "GitHub username"),
      defaultValue: String(status.username || ""),
      placeholder: getUIText("ssh_github_username_prompt", "Enter your GitHub username"),
      onSave: saveSshUsername,
    });
    return;
  }

  if (action === "view") {
    await openSshKeyListDialog();
    return;
  }

  if (action === "remove") {
    const ok = await appConfirm(getUIText("ssh_keys_remove_confirm", "Remove SSH keys from this device?"), {
      title: getUIText("ssh_keys", "SSH Keys"),
      confirmLabel: getUIText("remove_upper", "REMOVE"),
    });
    if (!ok) return;
    const removed = await runSshKeyAction(button, { action: "remove" }, getUIText("ssh_keys_removed", "SSH keys removed"));
    if (removed) {
      await renderDeviceItems(CURRENT_DEVICE_GROUP, false, { silentRefresh: true });
    }
    return;
  }

}

async function saveSshUsername(rawValue) {
  const username = String(rawValue || "").trim();
  if (!username) throw new Error(getUIText("ssh_github_username_prompt", "Enter your GitHub username"));
  try {
    await postJson("/api/ssh_keys", { action: "add", username });
    await loadDeviceSshStatus(false);
    await renderDeviceItems(CURRENT_DEVICE_GROUP, false, { silentRefresh: true });
    showAppToast(getUIText("ssh_keys_added", "SSH keys added"), { tone: "info" });
  } catch (err) {
    throw new Error(err?.message || getUIText("failed", "Failed"));
  }
}

function getSshDialogStatus() {
  return deviceSshStatus || deviceParamValues.SshKeyStatus || {
    username: deviceParamValues.GithubUsername || "",
    has_keys: Boolean(deviceParamValues.GithubSshKeys),
    key_count: 0,
    fingerprints: [],
    updated_at: "",
  };
}

function renderSshKeyListDialogHtml(status = getSshDialogStatus()) {
  const fingerprints = Array.isArray(status.fingerprints) ? status.fingerprints : [];
  if (!fingerprints.length) {
    return `<div class="device-ssh-dialog"><div class="device-ssh-dialog__empty">${escapeHtml(getUIText("ssh_keys_none", "No SSH keys configured"))}</div></div>`;
  }
  return `
    <div class="device-ssh-dialog">
      <div class="device-ssh-key-list">
        ${fingerprints.map((item) => {
          const type = String(item?.type || "").replace(/^ssh-/, "");
          const fingerprint = String(item?.fingerprint || "");
          return `<div class="device-ssh-key-list__item">
            <span>${escapeHtml(type || "key")}</span>
            <code>${escapeHtml(fingerprint || "-")}</code>
          </div>`;
        }).join("")}
      </div>
    </div>`;
}

async function openSshKeyListDialog() {
  await loadDeviceSshStatus(false).catch(() => {});
  const dialogPromise = appAlert("", {
    title: getUIText("ssh_key_fingerprints", "SSH key fingerprints"),
    html: true,
    messageHtml: renderSshKeyListDialogHtml(),
    confirmLabel: getUIText("close", "Close"),
  });
  if (typeof appDialog !== "undefined" && appDialog) {
    appDialog.classList.add("app-dialog--device-ssh");
  }
  dialogPromise.finally(() => {
    if (typeof appDialog !== "undefined" && appDialog) {
      appDialog.classList.remove("app-dialog--device-ssh");
    }
  });
  return dialogPromise;
}

async function runSshKeyAction(button, payload, successMessage) {
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = getUIText("loading", "Loading...");
  try {
    await postJson("/api/ssh_keys", payload);
    await loadDeviceSshStatus(false);
    showAppToast(successMessage, { tone: "info" });
    return true;
  } catch (err) {
    button.disabled = false;
    button.textContent = originalText;
    await refreshDeviceSshPanel().catch(() => {});
    await appAlert(err.message || getUIText("failed", "Failed"), {
      title: getUIText("ssh_keys", "SSH Keys"),
    });
    return false;
  }
}

function openDeviceInfoModal(title, html) {
  const overlay = document.createElement("div");
  overlay.className = "training-guide-modal device-info-modal";
  overlay.innerHTML = `
    <div class="training-guide-modal__surface device-info-modal__surface" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}">
      <button type="button" class="training-guide-modal__close c-close" data-device-info-close aria-label="${escapeHtml(getUIText("close", "Close"))}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7l10 10M17 7L7 17"/></svg></button>
      <div class="device-info-modal__header">${escapeHtml(title)}</div>
      <div class="device-info-modal__body"></div>
    </div>`;

  const close = () => overlay.remove();
  overlay.querySelector(".device-info-modal__body").innerHTML = html || "";
  overlay.querySelector("[data-device-info-close]").addEventListener("click", close);
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) close();
  });
  document.body.appendChild(overlay);
}

async function openRegulatoryInfo() {
  const payload = await getJson("/api/regulatory");
  openDeviceInfoModal(getUIText("regulatory", "Regulatory"), payload.html || "");
}

function openTrainingGuide() {
  let index = 0;
  const overlay = document.createElement("div");
  overlay.className = "training-guide-modal";
  overlay.innerHTML = `
    <div class="training-guide-modal__surface" role="dialog" aria-modal="true" aria-label="${escapeHtml(getUIText("review_training_guide", "Review Training Guide"))}">
      <button type="button" class="training-guide-modal__close c-close" data-training-close aria-label="${escapeHtml(getUIText("close", "Close"))}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7l10 10M17 7L7 17"/></svg></button>
      <img class="training-guide-modal__image" alt="" />
      <div class="training-guide-modal__bar">
        <button type="button" class="smallBtn" data-training-prev>${escapeHtml(getUIText("back", "Back"))}</button>
        <div class="training-guide-modal__count"></div>
        <button type="button" class="smallBtn" data-training-next>${escapeHtml(getUIText("next", "Next"))}</button>
      </div>
    </div>`;

  const image = overlay.querySelector(".training-guide-modal__image");
  const count = overlay.querySelector(".training-guide-modal__count");
  const prev = overlay.querySelector("[data-training-prev]");
  const next = overlay.querySelector("[data-training-next]");

  const close = () => overlay.remove();
  const render = () => {
    image.src = `/training/step${index}.png`;
    count.textContent = `${index + 1} / ${TRAINING_STEP_COUNT}`;
    prev.disabled = index === 0;
    next.textContent = getUIText(index === TRAINING_STEP_COUNT - 1 ? "close" : "next", index === TRAINING_STEP_COUNT - 1 ? "Close" : "Next");
  };

  overlay.querySelector("[data-training-close]").addEventListener("click", close);
  prev.addEventListener("click", () => {
    index = Math.max(0, index - 1);
    render();
  });
  next.addEventListener("click", () => {
    if (index >= TRAINING_STEP_COUNT - 1) {
      close();
      return;
    }
    index += 1;
    render();
  });
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) close();
  });

  render();
  document.body.appendChild(overlay);
}

// ── sunnypilot sections: generic catalog-driven controls ───────────────────

function spClampStepValue(value, step) {
  const fixed = Math.round(value * 100) / 100;
  return step < 1 ? fixed : Math.round(fixed);
}

function bindDeviceSpControls(container) {
  container.querySelectorAll(".sp-stepper[data-sp-param]").forEach((row) => {
    const param = row.dataset.spParam;
    const valueButton = row.querySelector(".sp-value");
    if (!valueButton) return;
    const step = Number(row.dataset.spStep || 1);
    const hasRange = row.dataset.spMin !== undefined && row.dataset.spMax !== undefined;
    const min = hasRange ? Number(row.dataset.spMin) : -Number.MAX_SAFE_INTEGER;
    const max = hasRange ? Number(row.dataset.spMax) : Number.MAX_SAFE_INTEGER;

    async function commit(next) {
      const value = spClampStepValue(Math.min(max, Math.max(min, next)), step);
      try {
        await setParam(param, value);
        valueButton.textContent = String(value);
      } catch (err) {
        showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
      }
    }

    const minusButton = row.querySelector(".sp-minus");
    const plusButton = row.querySelector(".sp-plus");
    if (minusButton && plusButton && window.CarrotUI?.numericStepper?.create) {
      // Same commit gesture the CarrotPilot tab uses: the value is written on
      // release, so a scroll starting on a button never changes anything.
      window.CarrotUI.numericStepper.create({
        minusButton,
        plusButton,
        getValue: () => Number(valueButton.textContent) || 0,
        getFallback: () => 0,
        getStep: () => step,
        getRange: () => ({ min, max }),
        commit,
      });
    }

    valueButton.addEventListener("click", async () => {
      const rangeMeta = hasRange ? `${min} ~ ${max}` : "";
      const input = await appPrompt(rangeMeta, {
        title: param,
        defaultValue: valueButton.textContent,
        placeholder: "0",
        confirmLabel: getUIText("ok", "OK"),
        cancelLabel: getUIText("cancel", "Cancel"),
        showCancel: true,
      });
      if (input === null) return;
      const next = Number(input);
      if (!Number.isFinite(next)) {
        showAppToast(getUIText("setting_value_invalid", "Enter a valid number."), { tone: "error" });
        return;
      }
      await commit(next);
    });
  });

  container.querySelectorAll("[data-sp-choice]").forEach((button) => {
    const param = button.dataset.spChoice;
    let labels = [];
    try {
      labels = JSON.parse(button.dataset.spOptions || "[]");
    } catch {}
    if (!Array.isArray(labels) || !labels.length) return;

    button.addEventListener("click", async () => {
      let current = 0;
      try {
        const values = await bulkGet([param]);
        const value = Number(values[param]);
        if (Number.isInteger(value) && value >= 0) current = value;
      } catch {}
      openDeviceListPicker({
        title: button.dataset.spTitle || param,
        meta: labels[current] || "-",
        groups: [{
          items: labels.map((label, index) => ({
            value: index,
            label: String(label),
            badge: "",
            current: index === current,
          })),
        }],
        onPick: async (item) => {
          if (item.value === current) return;
          try {
            await setParam(param, item.value);
            button.textContent = labels[item.value];
          } catch (err) {
            showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
          }
        },
      });
    });
  });
}


// ── Searchable picker foundation ──────────────────────────────────────────
// 5080's `showTree` is the reference: a dialog with a search field, the current
// item pinned on top, folders that auto-expand while a query is active, and a
// footer whose Select stays disabled until the pick actually changes. Every
// picker on this panel (vehicle, map region, model, branch, torque tune,
// bluetooth mapping) is built on the two helpers below so the interaction is
// identical everywhere instead of one dialog per call site.

// Below this many rows a search box is noise; above it, it is the only way to
// find anything (the vehicle list is 31 brands, the region list is 200+).
const DEVICE_PICKER_SEARCH_MIN_ITEMS = 8;

function closeDevicePicker(overlay) {
  if (!overlay) return;
  overlay.classList.remove("is-open");
  overlay.hidden = true;
  overlay.remove();
}

// Haystack for one row: what the user sees plus the group it sits under, so
// "hyundai" finds a platform even when the brand folder is collapsed.
function devicePickerHaystack(item, groupName) {
  const parts = [item?.label, item?.badge, item?.keywords, groupName];
  if (item && typeof item.value === "string") parts.push(item.value);
  return parts.map((value) => String(value == null ? "" : value).toLowerCase()).join(" ");
}

function devicePickerBuildSheet({ title, meta, showSearch, showFooter, confirmLabel }) {
  const overlay = document.createElement("div");
  overlay.className = "app-dialog device-picker";
  overlay.hidden = true;
  overlay.innerHTML = `
    <button type="button" class="app-dialog__backdrop" aria-label="Close"></button>
    <div class="app-dialog__sheet app-branch-picker__sheet device-picker__sheet" role="dialog" aria-modal="true">
      <div class="app-branch-picker__head">
        <div class="app-branch-picker__titles">
          <div class="app-dialog__title">${escapeHtml(title)}</div>
          <div class="muted app-branch-picker__meta" data-picker-meta>${escapeHtml(meta || "-")}</div>
        </div>
        <button type="button" class="smallBtn device-picker__close">${escapeHtml(getUIText("close", "Close"))}</button>
      </div>
      ${showSearch ? `<div class="device-picker__search">
        <input type="text" class="input-text" data-picker-search autocomplete="off"
               placeholder="${escapeHtml(getUIText("picker_search", "Search"))}" />
      </div>` : ""}
      <div class="app-branch-picker__list device-picker__list"></div>
      ${showFooter ? `<div class="device-picker__footer">
        <button type="button" class="smallBtn device-picker__close">${escapeHtml(getUIText("cancel", "Cancel"))}</button>
        <button type="button" class="smallBtn device-picker__ok" disabled>${escapeHtml(confirmLabel || getUIText("model_manager_select", "Select"))}</button>
      </div>` : ""}
    </div>`;
  return overlay;
}

// Every close affordance (backdrop, header X, footer Cancel) plus Escape.
function devicePickerBindClose(overlay, close) {
  overlay.querySelector(".app-dialog__backdrop").onclick = close;
  // querySelector would bind only the header button and leave footer Cancel dead.
  overlay.querySelectorAll(".device-picker__close").forEach((btn) => {
    btn.onclick = close;
  });
  overlay.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close();
  });
}

// One row. A div[role=button] when the row carries action buttons - nesting a
// <button> inside a <button> makes the parser close the outer one early and the
// row click silently dies.
function devicePickerRow(item, { hasActions, current, indent, pinned, onActivate }) {
  const row = document.createElement(hasActions ? "div" : "button");
  row.type = "button";
  const classes = ["btn", "groupBtn", "device-picker__item"];
  if (current) classes.push("is-current");
  if (indent) classes.push("device-picker__item--child");
  if (pinned) classes.push("device-picker__item--pinned");
  row.className = classes.join(" ");
  const label = document.createElement("span");
  label.className = "device-picker__item-label";
  label.textContent = String(item.label ?? item.value ?? "-") + (item.badge ? ` (${item.badge})` : "");
  row.appendChild(label);
  (item.actions || []).forEach((action) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "smallBtn";
    if (action.id) btn.dataset.modelFav = action.id;
    btn.textContent = action.label;
    btn.onclick = (event) => {
      event.stopPropagation();
      action.onClick?.(item);
    };
    row.appendChild(btn);
  });
  if (hasActions) {
    row.setAttribute("role", "button");
    row.tabIndex = 0;
    row.onclick = onActivate;
    row.onkeydown = (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onActivate();
      }
    };
  } else {
    row.onclick = onActivate;
  }
  return row;
}

// groups: [{ name, items: [{ value, label, badge, keywords, current, actions }] }]
// onPick(item) runs when an item row (not its actions) is tapped. The overlay
// closes first unless onPick returns the string "keep-open".
//
// Pass `selectedValue` to get 5080's confirm footer: the current row is pinned
// on top and Select stays disabled until a *different* row is picked.
function openDeviceListPicker(options) {
  const {
    title, meta, groups, onPick,
    searchable, selectedValue, confirmLabel, emptyText,
  } = options;

  const sourceGroups = (groups || []).map((group) => ({
    name: group?.name || "",
    items: (group?.items || []).map((item) => ({ ...item })),
  }));
  const totalItems = sourceGroups.reduce((sum, group) => sum + group.items.length, 0);
  const showSearch = searchable === true
    || (searchable !== false && totalItems >= DEVICE_PICKER_SEARCH_MIN_ITEMS);
  // A pinned current item only makes sense when the caller told us what it is.
  const showFooter = selectedValue !== undefined && selectedValue !== null;
  const currentValue = showFooter ? selectedValue : undefined;

  const overlay = devicePickerBuildSheet({ title, meta, showSearch, showFooter, confirmLabel });
  const list = overlay.querySelector(".device-picker__list");
  const metaEl = overlay.querySelector("[data-picker-meta]");
  const searchInput = overlay.querySelector("[data-picker-search]");
  const selectBtn = overlay.querySelector(".device-picker__ok");
  let query = "";
  let pick = currentValue;

  const close = () => closeDevicePicker(overlay);
  devicePickerBindClose(overlay, close);

  const syncSelectBtn = () => {
    if (!selectBtn) return;
    const changed = pick !== undefined && pick !== currentValue;
    selectBtn.disabled = !changed;
  };

  const renderList = () => {
    list.innerHTML = "";
    const queryLower = query.trim().toLowerCase();
    let shown = 0;

    sourceGroups.forEach((group) => {
      const visible = group.items.filter((item) => (
        !queryLower || devicePickerHaystack(item, group.name).includes(queryLower)
      ));
      if (!visible.length) return;
      if (group.name) {
        const head = document.createElement("div");
        head.className = "device-picker__group";
        head.textContent = group.name;
        list.appendChild(head);
      }
      visible.forEach((item) => {
        shown += 1;
        const isCurrent = currentValue !== undefined && item.value === currentValue;
        list.appendChild(devicePickerRow(item, {
          hasActions: Boolean(item.actions && item.actions.length),
          current: isCurrent,
          onActivate: async () => {
            pick = item.value;
            if (showFooter) {
              syncSelectBtn();
              renderList();
              return;
            }
            close();
            const result = await onPick?.(item);
            if (result === "keep-open" && overlay.isConnected) {
              overlay.hidden = false;
              requestAnimationFrame(() => overlay.classList.add("is-open"));
            }
          },
        }));
      });
    });

    if (!shown) {
      const empty = document.createElement("div");
      empty.className = "muted text-center device-picker__empty";
      empty.textContent = emptyText || getUIText("picker_no_results", "No matches");
      list.appendChild(empty);
    }
    if (metaEl) {
      metaEl.textContent = query.trim() && shown !== totalItems
        ? `${shown} / ${totalItems}`
        : (meta || String(totalItems));
    }
  };

  if (searchInput) {
    searchInput.addEventListener("input", () => {
      query = searchInput.value;
      renderList();
    });
  }
  if (selectBtn) {
    selectBtn.onclick = async () => {
      overlay.remove();
      const item = sourceGroups
        .flatMap((group) => group.items)
        .find((entry) => entry.value === pick);
      if (item) await onPick?.(item);
    };
  }

  syncSelectBtn();
  document.body.appendChild(overlay);
  overlay.hidden = false;
  requestAnimationFrame(() => overlay.classList.add("is-open"));
  if (searchInput) searchInput.focus();
  renderList();
  return { close, overlay };
}

// ── Model manager, mirroring the 5080 webui panel: two slot rows (qcom = the
// small on-device model, usbgpu = the big model on the eGPU), each opening a
// searchable tree dialog (folders, pinned selection, favorites, footer
// Select/Cancel), plus refresh / clear-cache actions. ────────────────────────

const DEVICE_MODEL_SLOTS = [
  { source: "qcom", titleKey: "model_slot_small", fallback: "Small Model" },
  { source: "usbgpu", titleKey: "model_slot_big", fallback: "Big Model" },
];

let DEVICE_MODEL_PAYLOAD = null;
let DEVICE_MODEL_OFFROAD = true;

function deviceModelSlot(payload, source) {
  return payload?.slots?.[source] || { tree: [], selected: {}, active_ref: "Default", default_label: "" };
}

function deviceModelSlotSelectedName(slot) {
  return String(slot?.selected?.name || slot?.default_label || "—");
}

function renderDeviceModelManagerShell() {
  const rows = DEVICE_MODEL_SLOTS.map(({ source, titleKey, fallback }) => `
    <div class="setting device-setting" data-model-slot="${source}">
      <div class="settingTop">
        <div>
          <div class="title">${escapeHtml(getUIText(titleKey, fallback))}</div>
          <div class="descr" data-model-warning hidden></div>
        </div>
        <div class="ctrl device-model-slot-ctrl">
          <span class="title muted device-value" data-model-value>—</span>
          <button type="button" class="smallBtn" data-model-select-row>${escapeHtml(getUIText("model_manager_select", "Select"))}</button>
        </div>
      </div>
    </div>`).join("");
  return `
    ${rows}
    <div class="setting device-setting">
      <div class="settingTop">
        <div>
          <div class="title">${escapeHtml(getUIText("model_manager_refresh", "Refresh model list"))}</div>
        </div>
        <div class="ctrl">
          <button type="button" class="smallBtn" id="btnDeviceModelSync">${escapeHtml(getUIText("model_manager_sync_btn", "SYNC"))}</button>
        </div>
      </div>
    </div>
    <div class="setting device-setting">
      <div class="settingTop">
        <div>
          <div class="title">${escapeHtml(getUIText("model_manager_clear_cache", "Clear model cache"))}</div>
          <div class="descr">${escapeHtml(getUIText("model_manager_clear_cache_hint", "Deletes every downloaded model except the active one"))}</div>
        </div>
        <div class="ctrl">
          <button type="button" class="smallBtn" id="btnDeviceModelClear">${escapeHtml(getUIText("model_manager_clear_btn", "CLEAR"))}</button>
        </div>
      </div>
    </div>
    <div class="setting device-setting" data-model-download hidden>
      <div class="settingTop">
        <div>
          <div class="title">${escapeHtml(getUIText("model_manager_downloading", "Downloading"))}</div>
          <div class="descr" data-model-download-name></div>
        </div>
        <div class="ctrl">
          <button type="button" class="smallBtn" id="btnDeviceModelCancel">${escapeHtml(getUIText("model_manager_cancel", "CANCEL"))}</button>
        </div>
      </div>
    </div>`;
}

function paintDeviceModelRows() {
  const payload = DEVICE_MODEL_PAYLOAD;
  const carry = payload?.carry_source;
  DEVICE_MODEL_SLOTS.forEach(({ source }) => {
    const row = document.querySelector(`[data-model-slot="${source}"]`);
    if (!row) return;
    const slot = deviceModelSlot(payload, source);
    const valueEl = row.querySelector("[data-model-value]");
    if (valueEl) {
      valueEl.textContent = deviceModelSlotSelectedName(slot);
      valueEl.classList.toggle("device-model-value--active", carry === source);
    }
    const button = row.querySelector("[data-model-select-row]");
    if (button) button.disabled = !(payload?.ok && DEVICE_MODEL_OFFROAD);
    const warning = row.querySelector("[data-model-warning]");
    if (warning) {
      warning.hidden = DEVICE_MODEL_OFFROAD;
      warning.textContent = getUIText("model_manager_offroad_only", "Only available when the vehicle is off");
    }
  });
  const downloadRow = document.querySelector("[data-model-download]");
  const queued = payload?.download?.queued_name || payload?.download?.name || "";
  if (downloadRow) {
    downloadRow.hidden = !queued;
    const nameEl = downloadRow.querySelector("[data-model-download-name]");
    if (nameEl) nameEl.textContent = queued;
  }
}

async function refreshDeviceModelManager() {
  try {
    const [payload, values] = await Promise.all([
      requestJson("/api/opui/models", { cache: "no-store" }),
      bulkGet(["IsOffroad"]).catch(() => ({})),
    ]);
    DEVICE_MODEL_PAYLOAD = payload?.ok ? payload : null;
    DEVICE_MODEL_OFFROAD = isTruthyDeviceFlag(values.IsOffroad);
  } catch {
    DEVICE_MODEL_PAYLOAD = null;
  }
  paintDeviceModelRows();
}

// Tree dialog, showTree parity: folders with +/- collapse, the current node
// pinned on top, optional star favorites, search, footer Cancel/Select.
//
// `folders` is `[{name, bundles:[{ref, name, internal, fav}]}]`. Anything with
// a single flat list passes `name: ""` and gets a folder-less tree - that is
// how 5080 renders countries, states, branches and torque versions.
//
// `onFavorite(ref)` toggles the star and `getFolders()` refetches the tree
// afterwards (models only). Both optional - without them no star is drawn.
function openDeviceTreeDialog({ title, meta, folders, selectedRef = "", onFavorite, getFolders, confirmLabel }) {
  return new Promise((resolve) => {
    const overlay = devicePickerBuildSheet({
      title,
      meta,
      showSearch: true,
      showFooter: true,
      confirmLabel,
    });
    const listEl = overlay.querySelector(".device-picker__list");
    const selectBtn = overlay.querySelector(".device-picker__ok");
    const searchInput = overlay.querySelector("[data-picker-search]");
    const metaEl = overlay.querySelector("[data-picker-meta]");

    let treeFolders = (folders || []).map((f) => ({ ...f, bundles: [...(f.bundles || [])] }));
    let pick = selectedRef;
    let query = "";
    const expanded = new Set(treeFolders.filter((f) => f.name).map((f) => f.name));

    const close = () => {
      closeDevicePicker(overlay);
      resolve(null);
    };
    devicePickerBindClose(overlay, close);

    if (searchInput) {
      searchInput.addEventListener("input", () => {
        query = searchInput.value;
        renderList();
      });
    }

    const syncSelectBtn = () => {
      if (!selectBtn) return;
      const enabled = Boolean(pick) && pick !== selectedRef;
      selectBtn.disabled = !enabled;
    };

    const folderLabel = (name) => (name == null || name === "" ? getUIText("picker_default_folder", "Default") : String(name));

    const findSelectedBundle = () => {
      for (const folder of treeFolders) {
        for (const bundle of folder.bundles || []) {
          if (bundle.ref === selectedRef || bundle.name === selectedRef) return { folder, bundle };
        }
      }
      return null;
    };

    const starFor = (bundle) => {
      const star = document.createElement("button");
      star.type = "button";
      star.className = "smallBtn";
      star.dataset.modelFav = bundle.ref;
      star.textContent = bundle.fav ? "★" : "☆";
      star.onclick = async (event) => {
        event.stopPropagation();
        try {
          const result = await onFavorite(bundle.ref);
          if (result === false) return;
          bundle.fav = !bundle.fav;
          star.textContent = bundle.fav ? "★" : "☆";
          if (typeof getFolders === "function") {
            const fresh = await getFolders();
            if (fresh?.length) {
              treeFolders = fresh.map((f) => ({ ...f, bundles: [...(f.bundles || [])] }));
              renderList();
            }
          }
        } catch (err) {
          showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
        }
      };
      return star;
    };

    const bundleRow = (bundle, { pinned = false, indent = false }) => {
      const row = devicePickerRow(
        { label: String(bundle.name || bundle.ref || "-"), actions: [] },
        {
          // A div, not a button: the favourite star inside is a real <button>,
          // and nesting buttons makes the parser close the outer one early -
          // the row click then never fires and Select stays disabled forever.
          hasActions: true,
          current: bundle.ref === pick || (pick === "" && bundle.ref === "Default"),
          indent,
          pinned,
          onActivate: () => {
            pick = bundle.ref;
            syncSelectBtn();
            renderList();
          },
        },
      );
      if (typeof onFavorite === "function" && bundle.ref && bundle.ref !== "Default") {
        row.appendChild(starFor(bundle));
      }
      return row;
    };

    function renderList() {
      listEl.innerHTML = "";
      const queryLower = query.toLowerCase().trim();
      const searching = Boolean(queryLower);
      const selectedNode = findSelectedBundle();
      let shown = 0;

      // Pin the currently selected item at the very top, matching the GUI
      // TreeOptionDialog and 5080's showTree.
      if (selectedNode?.bundle && !searching) {
        listEl.appendChild(bundleRow(selectedNode.bundle, { pinned: true }));
      }
      for (const folder of treeFolders) {
        const folderName = String(folder.name || "");
        const bundles = (folder.bundles || []).filter((b) => {
          if (!queryLower) return true;
          return String(b.name || b.ref || "").toLowerCase().includes(queryLower)
            || String(b.internal || "").toLowerCase().includes(queryLower)
            || folderLabel(folder.name).toLowerCase().includes(queryLower);
        });
        // Skip the pinned node inside its own folder so it is not listed twice.
        const visible = selectedNode?.bundle && !searching
          ? bundles.filter((b) => !(b.ref === selectedNode.bundle.ref && b.name === selectedNode.bundle.name))
          : bundles;
        if (!visible.length) continue;
        shown += visible.length;
        const hasFolder = Boolean(folderName);
        // Searching force-expands every folder: matches would otherwise hide
        // inside collapsed branches and look like "no results".
        const isOpen = searching || !hasFolder || expanded.has(folderName);
        if (hasFolder) {
          const header = document.createElement("button");
          header.type = "button";
          header.className = "btn groupBtn device-picker__item device-picker__folder";
          header.textContent = `${isOpen ? "−" : "+"} ${folderLabel(folder.name)}`;
          header.onclick = () => {
            if (expanded.has(folderName)) expanded.delete(folderName);
            else expanded.add(folderName);
            renderList();
          };
          listEl.appendChild(header);
          if (!isOpen) continue;
        }
        for (const bundle of visible) {
          listEl.appendChild(bundleRow(bundle, { indent: hasFolder }));
        }
      }
      if (!shown) {
        const empty = document.createElement("div");
        empty.className = "muted text-center device-picker__empty";
        empty.textContent = getUIText("picker_no_results", "No matches");
        listEl.appendChild(empty);
      }
      if (metaEl) {
        metaEl.textContent = searching ? `${shown}` : (meta || String(shown));
      }
    }

    if (selectBtn) {
      selectBtn.onclick = () => {
        overlay.remove();
        resolve(pick);
      };
    }

    syncSelectBtn();
    document.body.appendChild(overlay);
    overlay.hidden = false;
    requestAnimationFrame(() => overlay.classList.add("is-open"));
    if (searchInput) searchInput.focus();
    renderList();
  });
}

async function deviceModelIndexForRef(source, ref) {
  const slot = deviceModelSlot(DEVICE_MODEL_PAYLOAD, source);
  for (const folder of slot?.tree || []) {
    for (const bundle of folder.bundles || []) {
      if (bundle.ref === ref) return Number(bundle.index ?? -1);
    }
  }
  return -1;
}

async function openDeviceModelSlotPicker(source, title) {
  if (!DEVICE_MODEL_PAYLOAD?.ok) return;
  const slot = deviceModelSlot(DEVICE_MODEL_PAYLOAD, source);
  const treeOf = (payload) => (deviceModelSlot(payload, source).tree || [])
    .map((f) => ({ ...f, bundles: [...(f.bundles || [])] }));
  const ref = await openDeviceTreeDialog({
    title,
    meta: deviceModelSlotSelectedName(slot),
    folders: treeOf(DEVICE_MODEL_PAYLOAD),
    selectedRef: String(slot?.active_ref || "Default"),
    onFavorite: async (ref2) => {
      const res = await postJson("/api/opui/models/favorite", { ref: ref2 });
      if (res && res.ok === false) {
        showAppToast(res.error || getUIText("failed", "Failed"), { tone: "error" });
        return false;
      }
      return true;
    },
    getFolders: async () => {
      const fresh = await requestJson("/api/opui/models", { cache: "no-store" });
      if (fresh?.ok) DEVICE_MODEL_PAYLOAD = fresh;
      return fresh?.ok ? treeOf(fresh) : [];
    },
  });
  if (ref === null || ref === undefined) return;
  const index = await deviceModelIndexForRef(source, ref);
  try {
    const res = await postJson("/api/opui/models/select", { ref, index, source });
    if (res?.needs_reset_cal) {
      const ok = await appConfirm(getUIText("model_manager_reset_cal", "Model download has started in the background. We suggest resetting calibration. Would you like to do that now?"), {
        title,
        confirmLabel: getUIText("ok", "OK"),
        cancelLabel: getUIText("cancel", "Cancel"),
      });
      if (ok) await postJson("/api/recalibrate", {});
    } else {
      showAppToast(getUIText("model_manager_applied", "Applied"), { tone: "info" });
    }
    await refreshDeviceModelManager();
  } catch (err) {
    showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
  }
}

async function loadDeviceModelManager(container) {
  await refreshDeviceModelManager();
  DEVICE_MODEL_SLOTS.forEach(({ source, titleKey, fallback }) => {
    const row = container.querySelector(`[data-model-slot="${source}"]`);
    const button = row?.querySelector("[data-model-select-row]");
    if (button && !button.dataset.bound) {
      button.dataset.bound = "1";
      button.addEventListener("click", () => openDeviceModelSlotPicker(source, getUIText(titleKey, fallback)));
    }
  });
  const sync = container.querySelector("#btnDeviceModelSync");
  if (sync && !sync.dataset.bound) {
    sync.dataset.bound = "1";
    sync.addEventListener("click", async () => {
      sync.disabled = true;
      try {
        await postJson("/api/opui/action/models_sync", {});
        await new Promise((r) => setTimeout(r, 2500));
        await refreshDeviceModelManager();
      } catch (err) {
        showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
      } finally {
        sync.disabled = false;
      }
    });
  }
  const clear = container.querySelector("#btnDeviceModelClear");
  if (clear && !clear.dataset.bound) {
    clear.dataset.bound = "1";
    clear.addEventListener("click", async () => {
      const ok = await appConfirm(getUIText("model_manager_clear_confirm", "Delete ALL downloaded models except the currently active one?"), {
        title: getUIText("model_manager_clear_cache", "Clear model cache"),
        confirmLabel: getUIText("model_manager_clear_btn", "CLEAR"),
        cancelLabel: getUIText("cancel", "Cancel"),
      });
      if (!ok) return;
      try {
        await postJson("/api/opui/action/models_clear_cache", {});
        showAppToast(getUIText("model_manager_applied", "Applied"), { tone: "info" });
        await refreshDeviceModelManager();
      } catch (err) {
        showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
      }
    });
  }
  const cancel = container.querySelector("#btnDeviceModelCancel");
  if (cancel && !cancel.dataset.bound) {
    cancel.dataset.bound = "1";
    cancel.addEventListener("click", async () => {
      try {
        await postJson("/api/opui/action/models_cancel_download", {});
        await refreshDeviceModelManager();
      } catch (err) {
        showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
      }
    });
  }
}

// ── Section manager blocks backed by the 5080 webui daemon ─────────────────
// OSM downloads, trips, IMU calibration and bluetooth pairing live in the
// daemon; each section gets a shell here plus a loader that fills it.

DEVICE_SECTION_SHELLS.Models = () => renderDeviceModelManagerShell();
DEVICE_SECTION_SHELLS.Osm = () => renderDeviceOsmShell();
DEVICE_SECTION_SHELLS.Trips = () => renderDeviceTripsShell();
DEVICE_SECTION_SHELLS.Imu = () => renderDeviceImuShell();

function deviceManagerRow({ id, title, descr = "", value = "", button = "", buttonId = "", disabled = false }) {
  const ctrl = [];
  if (value !== "") ctrl.push(`<span class="title muted device-value"${id ? ` id="${id}-value"` : ""}>${escapeHtml(value)}</span>`);
  if (button) ctrl.push(`<button type="button" class="smallBtn"${buttonId ? ` id="${buttonId}"` : ""} ${disabled ? "disabled" : ""}>${escapeHtml(button)}</button>`);
  return `
    <div class="setting device-setting"${id ? ` id="${id}"` : ""}>
      <div class="settingTop">
        <div>
          <div class="title">${escapeHtml(title)}</div>
          ${descr ? `<div class="descr"${id ? ` id="${id}-descr"` : ""}>${escapeHtml(descr)}</div>` : ""}
        </div>
        <div class="ctrl device-model-slot-ctrl">${ctrl.join("")}</div>
      </div>
    </div>`;
}

function bindOnce(element, event, handler) {
  if (!element || element.dataset.bound) return;
  element.dataset.bound = "1";
  element.addEventListener(event, handler);
}

// ── OSM (Maps): 5080's panel is Country / State / Database Update / size ────
// 5080 keeps the region as two independent rows (so the state can be changed
// without re-picking the country) and only shows the State row for countries
// that are split by region (US states, CN provinces). Both open a searchable
// tree - the country list is ~200 entries.

const DEVICE_OSM_STATE_COUNTRIES = new Set(["US", "CN"]);

function renderDeviceOsmShell() {
  return `
    ${deviceManagerRow({ id: "osmRegion", title: getUIText("osm_download_region", "Download map region"), descr: getUIText("osm_download_region_hint", "Pick a country, then a state or province"), value: "-", button: getUIText("model_manager_select", "Select"), buttonId: "btnDeviceOsmRegion" })}
    ${deviceManagerRow({ id: "osmState", title: getUIText("osm_pick_state", "State / Province"), value: "-", button: getUIText("model_manager_select", "Select"), buttonId: "btnDeviceOsmState" })}
    ${deviceManagerRow({ id: "osmProgress", title: getUIText("osm_progress", "Download progress"), value: "-" })}
    ${deviceManagerRow({ id: "osmUpdate", title: getUIText("osm_update", "Database update"), descr: getUIText("osm_update_hint", "Last time the map database was refreshed"), value: "-", button: getUIText("osm_check_btn", "CHECK"), buttonId: "btnDeviceOsmCheck" })}
    ${deviceManagerRow({ id: "osmSize", title: getUIText("osm_size", "Downloaded map size"), value: "-" })}
    ${deviceManagerRow({ id: "osmDelete", title: getUIText("osm_delete", "Delete downloaded maps"), descr: getUIText("osm_delete_hint", "Removes every OSM map on the device"), button: getUIText("model_manager_clear_btn", "CLEAR"), buttonId: "btnDeviceOsmDelete" })}`;
}

// OsmLocationName / OsmStateName / OsmDownloadedDate are the params the daemon
// writes; they are the same source 5080 reads for its labels.
async function deviceOsmReadLocation() {
  const values = await bulkGet(["OsmLocationName", "OsmLocationTitle", "OsmStateName", "OsmStateTitle", "OsmDownloadedDate"]).catch(() => ({}));
  return {
    country: String(values.OsmLocationName || ""),
    countryTitle: String(values.OsmLocationTitle || ""),
    state: String(values.OsmStateName || ""),
    stateTitle: String(values.OsmStateTitle || ""),
    downloaded: String(values.OsmDownloadedDate || ""),
  };
}

function deviceOsmNeedsState(country) {
  return DEVICE_OSM_STATE_COUNTRIES.has(String(country || "").toUpperCase());
}

function deviceOsmStateTitle(country) {
  return String(country || "").toUpperCase() === "CN"
    ? getUIText("osm_province", "Province")
    : getUIText("osm_state", "State");
}

function deviceOsmFormatDate(raw) {
  const text = String(raw || "").trim();
  if (!text) return getUIText("osm_never", "never");
  const seconds = Number(text);
  if (Number.isFinite(seconds) && seconds > 0) {
    return new Date(seconds * 1000).toLocaleString();
  }
  return text;
}

async function deviceOsmApplyProgress(container) {
  const progressValue = container.querySelector("#osmProgress-value");
  if (!progressValue) return false;
  try {
    const progress = await requestJson("/api/opui/osm/progress", { cache: "no-store" });
    const pct = Number(progress?.progress ?? 0);
    const done = Number(progress?.done ?? 0);
    const total = Number(progress?.total ?? 0);
    if (progress?.downloading || progress?.active) {
      progressValue.textContent = total > 0 ? `${pct.toFixed(0)}% (${done}/${total})` : `${pct.toFixed(0)}%`;
      return true;
    }
    progressValue.textContent = getUIText("osm_idle", "idle");
    return false;
  } catch {
    progressValue.textContent = "-";
    return false;
  }
}

// While a download runs the panel re-reads progress until it finishes, so the
// row is live instead of a snapshot taken when the section opened.
let deviceOsmPollTimer = null;

function deviceOsmStopPolling() {
  if (!deviceOsmPollTimer) return;
  window.clearTimeout(deviceOsmPollTimer);
  deviceOsmPollTimer = null;
}

function deviceOsmPoll(container) {
  deviceOsmStopPolling();
  const step = async () => {
    const container2 = document.getElementById("deviceItems");
    if (!container2 || !container2.querySelector("#osmProgress-value")) {
      deviceOsmStopPolling();
      return;
    }
    const active = await deviceOsmApplyProgress(container2);
    if (!active) {
      deviceOsmStopPolling();
      await loadDeviceOsmManager(container2);
      return;
    }
    deviceOsmPollTimer = window.setTimeout(step, 3000);
  };
  deviceOsmPollTimer = window.setTimeout(step, 3000);
}

async function loadDeviceOsmManager(container) {
  const location = await deviceOsmReadLocation();
  const regionValue = container.querySelector("#osmRegion-value");
  if (regionValue) regionValue.textContent = location.countryTitle || location.country || getUIText("osm_not_selected", "Not selected");

  const stateRow = container.querySelector("#osmState");
  const stateButton = container.querySelector("#btnDeviceOsmState");
  const stateValue = container.querySelector("#osmState-value");
  const needsState = deviceOsmNeedsState(location.country);
  if (stateRow) stateRow.hidden = !needsState;
  if (stateValue) stateValue.textContent = location.stateTitle || location.state || getUIText("osm_not_selected", "Not selected");
  if (stateButton) {
    stateButton.textContent = getUIText("model_manager_select", "Select");
    stateButton.disabled = !location.country;
  }
  const stateTitleEl = container.querySelector("#osmState .title");
  if (stateTitleEl) stateTitleEl.textContent = deviceOsmStateTitle(location.country);

  const updateRow = container.querySelector("#osmUpdate");
  if (updateRow) updateRow.hidden = !location.country;
  const updateValue = container.querySelector("#osmUpdate-value");
  if (updateValue) updateValue.textContent = deviceOsmFormatDate(location.downloaded);

  try {
    const size = await requestJson("/api/opui/osm/size", { cache: "no-store" });
    const sizeValue = container.querySelector("#osmSize-value");
    if (sizeValue) {
      const mb = Number(size?.size_mb ?? size?.mb ?? 0);
      sizeValue.textContent = size?.pending
        ? getUIText("osm_calculating", "Calculating…")
        : (mb >= 1024 ? `${(mb / 1024).toFixed(2)} GB` : `${mb.toFixed(1)} MB`);
    }
  } catch {
    const sizeValue = container.querySelector("#osmSize-value");
    if (sizeValue) sizeValue.textContent = "-";
  }

  const active = await deviceOsmApplyProgress(container);
  if (active) deviceOsmPoll(container);
  else deviceOsmStopPolling();

  bindOnce(container.querySelector("#btnDeviceOsmRegion"), "click", () => deviceOsmPickRegion(container, "Country"));
  bindOnce(container.querySelector("#btnDeviceOsmState"), "click", () => deviceOsmPickRegion(container, "State"));

  bindOnce(container.querySelector("#btnDeviceOsmCheck"), "click", async () => {
    const ok = await appConfirm(getUIText("osm_check_confirm", "This will start the download process and it might take a while to complete."), {
      title: getUIText("osm_update", "Database update"),
      confirmLabel: getUIText("osm_start_download", "Start Download"),
      cancelLabel: getUIText("cancel", "Cancel"),
    });
    if (!ok) return;
    try {
      await postJson("/api/opui/action/osm_check_updates", {});
      showAppToast(getUIText("osm_download_started", "Download started"), { tone: "info" });
      deviceOsmPoll(container);
    } catch (err) {
      showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
    }
  });

  bindOnce(container.querySelector("#btnDeviceOsmDelete"), "click", async () => {
    const ok = await appConfirm(getUIText("osm_delete_confirm", "Delete all downloaded OSM maps?"), {
      title: getUIText("osm_delete", "Delete downloaded maps"),
      confirmLabel: getUIText("model_manager_clear_btn", "CLEAR"),
      cancelLabel: getUIText("cancel", "Cancel"),
    });
    if (!ok) return;
    const btn = container.querySelector("#btnDeviceOsmDelete");
    if (btn) {
      btn.disabled = true;
      btn.textContent = getUIText("osm_deleting", "DELETING…");
    }
    try {
      await postJson("/api/opui/osm/delete", {});
      showAppToast(getUIText("model_manager_applied", "Applied"), { tone: "info" });
      await loadDeviceOsmManager(container);
    } catch (err) {
      showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = getUIText("model_manager_clear_btn", "CLEAR");
      }
    }
  });
}

// 5080's pickOsmRegion: one searchable tree per level, then the download
// prompt. Cancelling the state dialog clears the country when a split country
// has no state yet.
async function deviceOsmPickRegion(container, regionType) {
  const button = container.querySelector(regionType === "Country" ? "#btnDeviceOsmRegion" : "#btnDeviceOsmState");
  const label = button?.textContent || "";
  if (button) {
    button.disabled = true;
    button.textContent = getUIText("osm_fetching", "FETCHING…");
  }
  let regions = null;
  try {
    const location = await deviceOsmReadLocation();
    const country = regionType === "Country" ? "" : location.country;
    if (regionType !== "Country" && !country) {
      showAppToast(getUIText("osm_select_country_first", "Select a country first"), { tone: "error" });
      return;
    }
    regions = await requestJson(
      `/api/opui/osm/regions?type=${encodeURIComponent(regionType)}&country=${encodeURIComponent(country)}`,
      { cache: "no-store" },
    );
    if (!regions?.ok) throw new Error(regions?.error || getUIText("failed", "Failed"));

    const entries = regionType === "Country" ? (regions.countries || []) : (regions.states || []);
    const folders = [{ name: "", bundles: entries.map((e) => ({ ref: e.name, name: e.title || e.name })) }];
    const selectedRef = regionType === "Country" ? location.country : location.state;
    const ref = await openDeviceTreeDialog({
      title: regionType === "Country" ? getUIText("osm_pick_country", "Country") : deviceOsmStateTitle(location.country),
      meta: `${entries.length}`,
      folders,
      selectedRef,
    });
    if (ref === null || ref === undefined) {
      // Cancelled the state dialog on a split country with no state yet:
      // drop the half-made selection like 5080 does with osm/clear.
      if (regionType === "State" && deviceOsmNeedsState(location.country) && !location.state) {
        await postJson("/api/opui/osm/clear", {}).catch(() => {});
      }
      return;
    }
    await deviceOsmSelect(location, regionType, ref, entries);
  } catch (err) {
    showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = label || getUIText("model_manager_select", "Select");
    }
  }
}

async function deviceOsmSelect(location, regionType, ref, entries) {
  const entry = entries.find((e) => e.name === ref) || { name: ref, title: ref };
  const country = regionType === "Country" ? ref : location.country;
  const countryTitle = regionType === "Country" ? (entry.title || ref) : location.countryTitle;
  const state = regionType === "State" ? ref : "";
  const stateTitle = regionType === "State" ? (entry.title || ref) : "";
  const summary = regionType === "Country"
    ? (entry.title || ref)
    : `${location.countryTitle || location.country} · ${stateTitle}`;
  const ok = await appConfirm(
    `${getUIText("osm_download_confirm", "Download this region's map?")}\n\n${summary}`,
    { title: getUIText("osm_download_region", "Download map region"), confirmLabel: getUIText("ok", "OK"), cancelLabel: getUIText("cancel", "Cancel") },
  );
  if (!ok) return;
  try {
    await postJson("/api/opui/osm/select", {
      country,
      country_title: countryTitle,
      state,
      state_title: stateTitle,
    });
    showAppToast(getUIText("osm_download_started", "Download started"), { tone: "info" });
    const container = document.getElementById("deviceItems");
    if (container) {
      await loadDeviceOsmManager(container);
      deviceOsmPoll(container);
    }
    // A freshly picked US/CN country has no state yet - prompt for it like
    // 5080 does instead of leaving the selection half-made.
    if (regionType === "Country" && deviceOsmNeedsState(country) && container) {
      await deviceOsmPickRegion(container, "State");
    }
  } catch (err) {
    showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
  }
}

// ── Trips: source + stats ──────────────────────────────────────────────────

function renderDeviceTripsShell() {
  return `
    ${deviceManagerRow({ id: "tripsSource", title: getUIText("trips_source", "Trips data source"), value: "-", button: getUIText("model_manager_select", "Select"), buttonId: "btnDeviceTripsSource" })}
    ${deviceManagerRow({ id: "tripsAll", title: getUIText("trips_all", "All time"), value: "-" })}
    ${deviceManagerRow({ id: "tripsWeek", title: getUIText("trips_week", "This week"), value: "-" })}`;
}

function deviceTripsStatsText(stats) {
  if (!stats) return "-";
  return `${Number(stats.routes ?? 0)} ${getUIText("trips_routes", "drives")} · ${Number(stats.distance ?? 0).toFixed(0)} km · ${Number(stats.minutes ?? 0).toFixed(0)} min`;
}

async function loadDeviceTripsManager(container) {
  const values = await bulkGet(["TripsDataSource"]).catch(() => ({}));
  const source = String(values.TripsDataSource || "local");
  const sourceValue = container.querySelector("#tripsSource-value");
  if (sourceValue) sourceValue.textContent = source;
  try {
    const payload = await requestJson(`/api/opui/trips?source=${encodeURIComponent(source)}`, { cache: "no-store" });
    const all = container.querySelector("#tripsAll-value");
    const week = container.querySelector("#tripsWeek-value");
    if (all) all.textContent = deviceTripsStatsText(payload?.stats?.all);
    if (week) week.textContent = deviceTripsStatsText(payload?.stats?.week);
  } catch {}

  bindOnce(container.querySelector("#btnDeviceTripsSource"), "click", () => {
    const options = ["local", "cloud", "all"];
    openDeviceListPicker({
      title: getUIText("trips_source", "Trips data source"),
      meta: source,
      groups: [{ items: options.map((value) => ({ value, label: value, current: value === source })) }],
      onPick: async (item) => {
        try {
          await setParam("TripsDataSource", item.value);
          const container2 = document.getElementById("deviceItems");
          if (container2) await loadDeviceTripsManager(container2);
        } catch (err) {
          showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
        }
      },
    });
  });
}

// ── IMU calibration ───────────────────────────────────────────────────────
// 5080's block is status + progress + estimated orientation + error + a CANCEL
// that only exists while a run is in progress. Calibration is a multi-minute
// process, so the section polls while it runs.

const DEVICE_IMU_STATE_KEYS = {
  idle: ["imu_state_idle", "Idle"],
  static_collecting: ["imu_state_static", "Collecting static data — keep parked"],
  dynamic_collecting: ["imu_state_dynamic", "Collecting dynamic data — drive straight"],
  computing: ["imu_state_computing", "Computing calibration..."],
  completed: ["imu_state_completed", "Calibration completed"],
  failed: ["imu_state_failed", "Calibration failed"],
  cancelled: ["imu_state_cancelled", "Calibration cancelled"],
};

function renderDeviceImuShell() {
  return `
    ${deviceManagerRow({ id: "imuState", title: getUIText("imu_state", "Calibration status"), value: "-" })}
    ${deviceManagerRow({ id: "imuAngles", title: getUIText("imu_angles", "Estimated orientation"), value: "-" })}
    ${deviceManagerRow({ id: "imuError", title: getUIText("imu_error", "Error"), value: "-" })}
    ${deviceManagerRow({ id: "imuActions", title: getUIText("imu_actions", "Calibration actions"), descr: getUIText("imu_actions_hint", "Keep the vehicle parked and ignition on"), button: getUIText("imu_start", "START"), buttonId: "btnDeviceImuStart" })}
    ${deviceManagerRow({ id: "imuCancel", title: getUIText("imu_in_progress", "Calibration in progress"), button: getUIText("cancel", "Cancel"), buttonId: "btnDeviceImuCancel" })}
    ${deviceManagerRow({ id: "imuReset", title: getUIText("imu_reset", "Reset calibration"), button: getUIText("reset", "Reset"), buttonId: "btnDeviceImuReset" })}`;
}

function deviceImuStateText(state) {
  const [key, fallback] = DEVICE_IMU_STATE_KEYS[String(state || "")] || ["imu_state_unknown", String(state || "unknown")];
  return getUIText(key, fallback);
}

function deviceImuAnglesText(status) {
  const angles = status?.angles || status?.estimated_angles || status?.orientation;
  if (!angles) return "-";
  if (Array.isArray(angles)) return angles.map((v) => `${Number(v || 0).toFixed(2)}°`).join(" · ");
  if (typeof angles === "object") {
    return Object.entries(angles).map(([k, v]) => `${k} ${Number(v || 0).toFixed(2)}°`).join(" · ");
  }
  return String(angles);
}

let deviceImuPollTimer = null;

function deviceImuStopPolling() {
  if (!deviceImuPollTimer) return;
  window.clearTimeout(deviceImuPollTimer);
  deviceImuPollTimer = null;
}

const DEVICE_IMU_RUNNING_STATES = new Set(["static_collecting", "dynamic_collecting", "computing"]);

async function loadDeviceImuManager(container) {
  let status = null;
  try {
    const payload = await requestJson("/api/opui/imu/calibration", { cache: "no-store" });
    status = payload?.status || null;
  } catch {}

  const stateValue = container.querySelector("#imuState-value");
  const anglesRow = container.querySelector("#imuAngles");
  const anglesValue = container.querySelector("#imuAngles-value");
  const errorRow = container.querySelector("#imuError");
  const errorValue = container.querySelector("#imuError-value");
  const cancelRow = container.querySelector("#imuCancel");
  const startButton = container.querySelector("#btnDeviceImuStart");

  if (!status) {
    if (stateValue) stateValue.textContent = getUIText("model_manager_unavailable", "Model manager (5080) unreachable");
    deviceImuStopPolling();
    if (startButton) startButton.disabled = true;
    if (cancelRow) cancelRow.hidden = true;
    return;
  }

  const state = String(status.state || "unknown");
  const progress = Number(status.progress ?? 0);
  if (stateValue) {
    stateValue.textContent = progress > 0
      ? `${deviceImuStateText(state)} ${progress}%`
      : deviceImuStateText(state);
  }
  const angles = deviceImuAnglesText(status);
  if (anglesRow) anglesRow.hidden = angles === "-";
  if (anglesValue) anglesValue.textContent = angles;

  const error = String(status.error || "");
  if (errorRow) errorRow.hidden = !error;
  if (errorValue) errorValue.textContent = error || "-";

  const running = DEVICE_IMU_RUNNING_STATES.has(state);
  if (cancelRow) cancelRow.hidden = !running;
  if (startButton) {
    startButton.disabled = running;
    startButton.textContent = running ? getUIText("imu_running", "RUNNING") : getUIText("imu_start", "START");
  }

  // Keep polling while a run is live; stop as soon as it settles.
  deviceImuStopPolling();
  if (running) {
    deviceImuPollTimer = window.setTimeout(async () => {
      deviceImuPollTimer = null;
      const container2 = document.getElementById("deviceItems");
      if (container2 && container2.querySelector("#imuState-value")) {
        await loadDeviceImuManager(container2).catch(() => {});
      }
    }, 3000);
  }

  bindOnce(container.querySelector("#btnDeviceImuStart"), "click", async () => {
    try {
      await postJson("/api/opui/imu/calibration/start", {});
      showAppToast(getUIText("imu_started", "Calibration started"), { tone: "info" });
      const container2 = document.getElementById("deviceItems");
      if (container2) await loadDeviceImuManager(container2);
    } catch (err) {
      showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
    }
  });

  bindOnce(container.querySelector("#btnDeviceImuCancel"), "click", async () => {
    try {
      await postJson("/api/opui/imu/calibration/cancel", {});
      showAppToast(getUIText("imu_cancelled", "Calibration cancelled"), { tone: "info" });
      const container2 = document.getElementById("deviceItems");
      if (container2) await loadDeviceImuManager(container2);
    } catch (err) {
      showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
    }
  });

  bindOnce(container.querySelector("#btnDeviceImuReset"), "click", async () => {
    const ok = await appConfirm(getUIText("imu_reset_confirm", "Reset IMU calibration? sunnypilot will recalibrate."), {
      title: getUIText("imu_reset", "Reset calibration"),
      confirmLabel: getUIText("reset", "Reset"),
      cancelLabel: getUIText("cancel", "Cancel"),
    });
    if (!ok) return;
    try {
      await postJson("/api/opui/imu/calibration/reset", {});
      const container2 = document.getElementById("deviceItems");
      if (container2) await loadDeviceImuManager(container2);
    } catch (err) {
      showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
    }
  });
}

// ── Bluetooth: pairing + HID button mapping ────────────────────────────────

function renderDeviceBluetoothShell() {
  return `
    ${deviceManagerRow({ id: "btRuntime", title: getUIText("bt_status", "Bluetooth status"), value: "-" })}
    ${deviceManagerRow({ id: "btDevices", title: getUIText("bt_devices", "Paired devices"), descr: getUIText("bt_devices_hint", "Tap to connect, disconnect or forget"), value: "-" })}
    <div data-bt-device-list></div>
    ${deviceManagerRow({ id: "btScan", title: getUIText("bt_scan", "Scan and pair"), descr: getUIText("bt_scan_hint", "Put the remote in pairing mode first"), button: getUIText("bt_scan_btn", "SCAN"), buttonId: "btnDeviceBtScan" })}
    ${deviceManagerRow({ id: "btMapping", title: getUIText("bt_mapping", "Button mapping"), descr: getUIText("bt_mapping_hint", "Map the remote's buttons to driving actions"), value: "-", button: getUIText("model_manager_select", "Select"), buttonId: "btnDeviceBtMapping" })}`;
}

function deviceBluetoothDeviceRow(device) {
  const mac = String(device.mac || "");
  const connected = !!device.connected;
  const action = connected ? "disconnect" : "connect";
  const actionLabel = connected ? getUIText("bt_disconnect", "DISCONNECT") : getUIText("bt_connect", "CONNECT");
  const detail = device.paired ? getUIText("bt_paired", "paired") : getUIText("bt_not_paired", "not paired");
  return `
    <div class="setting device-setting">
      <div class="settingTop">
        <div>
          <div class="title">${escapeHtml(device.name || mac)}</div>
          <div class="descr">${escapeHtml(mac)} · ${escapeHtml(detail)}</div>
        </div>
        <div class="ctrl device-model-actions">
          <button type="button" class="smallBtn" data-bt-op="${escapeHtml(action)}" data-bt-address="${escapeHtml(mac)}">${escapeHtml(actionLabel)}</button>
          <button type="button" class="smallBtn" data-bt-op="forget" data-bt-address="${escapeHtml(mac)}">${escapeHtml(getUIText("bt_forget", "FORGET"))}</button>
        </div>
      </div>
    </div>`;
}

// The daemon answers with two device views: `devices` is the live bluez
// snapshot (address/name/paired/connected), `config.devices` is what has been
// saved. A remote can be in either, so merge them on MAC - showing only the
// saved ones left a freshly scanned remote invisible.
function bluetoothDeviceEntries(payload) {
  const saved = payload?.config?.devices || {};
  const byMac = new Map();
  (Array.isArray(payload?.devices) ? payload.devices : []).forEach((entry) => {
    const mac = String(entry?.address || "").toUpperCase();
    if (!mac) return;
    byMac.set(mac, {
      mac,
      name: entry?.name || saved[mac]?.name || "",
      paired: !!entry?.paired,
      connected: !!entry?.connected,
    });
  });
  Object.keys(saved).forEach((key) => {
    const mac = String(key || "").toUpperCase();
    if (!mac || byMac.has(mac)) return;
    byMac.set(mac, { mac, name: saved[key]?.name || "", paired: false, connected: false });
  });
  return [...byMac.values()];
}

async function loadDeviceBluetoothManager(container) {
  let payload = null;
  try {
    payload = await requestJson("/api/bluetooth", { cache: "no-store" });
  } catch {}

  const runtime = payload?.runtime || {};
  const runtimeValue = container.querySelector("#btRuntime-value");
  if (runtimeValue) {
    runtimeValue.textContent = payload
      ? `${runtime.alive ? getUIText("bt_alive", "service up") : getUIText("bt_dead", "service down")} · ${payload?.radioEnabled ? getUIText("on", "ON") : getUIText("off", "OFF")}`
      : getUIText("bt_unavailable", "Bluetooth service unavailable");
  }

  const devices = bluetoothDeviceEntries(payload);
  const listRoot = container.querySelector("[data-bt-device-list]");
  if (listRoot) listRoot.innerHTML = devices.map((device) => deviceBluetoothDeviceRow(device)).join("");
  const devicesValue = container.querySelector("#btDevices-value");
  if (devicesValue) devicesValue.textContent = String(devices.length);

  const saved = payload?.config?.devices || {};
  const mappingValue = container.querySelector("#btMapping-value");
  if (mappingValue) {
    const summary = Object.entries(saved)
      .map(([mac, entry]) => `${entry?.name || mac}: ${Object.keys(entry?.mapping || {}).length}`)
      .join(" · ");
    mappingValue.textContent = summary || getUIText("bt_none_found", "No device found");
  }

  container.querySelectorAll("[data-bt-op]").forEach((button) => {
    bindOnce(button, "click", async () => {
      const op = button.dataset.btOp;
      const address = button.dataset.btAddress;
      const confirmText = op === "forget"
        ? getUIText("bt_forget_confirm", "Forget this device?")
        : op === "disconnect"
          ? getUIText("bt_disconnect_confirm", "Disconnect this device?")
          : getUIText("bt_connect_confirm", "Connect to this device?");
      const ok = await appConfirm(confirmText, { title: getUIText("device_group_bluetooth", "Bluetooth"), confirmLabel: getUIText("ok", "OK"), cancelLabel: getUIText("cancel", "Cancel") });
      if (!ok) return;
      try {
        await postJson(`/api/bluetooth/${op}`, { address });
        showAppToast(getUIText("model_manager_applied", "Applied"), { tone: "info" });
        await loadDeviceBluetoothManager(container);
      } catch (err) {
        showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
      }
    });
  });

  bindOnce(container.querySelector("#btnDeviceBtScan"), "click", async () => {
    try {
      await postJson("/api/bluetooth/scan", {});
      showAppToast(getUIText("bt_scanning", "Scanning…"), { tone: "info" });
      await new Promise((r) => setTimeout(r, 6000));
      const fresh = await requestJson("/api/bluetooth", { cache: "no-store" });
      const found = bluetoothDeviceEntries(fresh).filter((device) => !device.paired);
      if (!found.length) {
        showAppToast(getUIText("bt_none_found", "No device found"), { tone: "error" });
        return;
      }
      openDeviceListPicker({
        title: getUIText("bt_scan", "Scan and pair"),
        meta: getUIText("bt_scan_hint", "Put the remote in pairing mode first"),
        groups: [{ items: found.map((device) => ({ value: device.mac, label: device.name || device.mac, badge: device.mac })) }],
        onPick: async (item) => {
          try {
            await postJson("/api/bluetooth/pair", { address: item.value });
            showAppToast(getUIText("bt_pairing", "Pairing…"), { tone: "info" });
            await loadDeviceBluetoothManager(container);
          } catch (err) {
            showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
          }
        },
      });
    } catch (err) {
      showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
    }
  });

  // Mapping is per remote, not global: the daemon stores
  // config.devices[MAC].mapping[button] = action, so the picker walks
  // remote -> button -> action and rewrites only that one device entry.
  bindOnce(container.querySelector("#btnDeviceBtMapping"), "click", () => {
    if (!devices.length) {
      showAppToast(getUIText("bt_pair_first", "Pair a remote first"), { tone: "error" });
      return;
    }
    openDeviceListPicker({
      title: getUIText("bt_mapping", "Button mapping"),
      meta: getUIText("bt_mapping_hint", "Map the remote's buttons to driving actions"),
      groups: [{ items: devices.map((device) => ({ value: device.mac, label: device.name || device.mac, badge: device.mac })) }],
      onPick: (deviceItem) => {
        const entry = saved[deviceItem.value] || {};
        const mapping = entry.mapping || {};
        const keys = Object.keys(mapping).length ? Object.keys(mapping) : Object.keys(payload?.defaults || {});
        openDeviceListPicker({
          title: getUIText("bt_button", "Button"),
          meta: entry.name || deviceItem.value,
          groups: [{ items: keys.map((key) => ({ value: key, label: key, badge: String(mapping[key] || "") })) }],
          onPick: (keyItem) => {
            const actions = payload?.actions || ["none"];
            openDeviceListPicker({
              title: getUIText("bt_action", "Action"),
              meta: `${keyItem.value} → ${mapping[keyItem.value] || "-"}`,
              groups: [{ items: actions.map((action) => ({ value: action, label: action, current: action === mapping[keyItem.value] })) }],
              onPick: async (actionItem) => {
                try {
                  await postJson("/api/bluetooth/device-config", {
                    address: deviceItem.value,
                    device: {
                      name: entry.name || deviceItem.value,
                      profile: entry.profile || "generic",
                      enabled: entry.enabled !== false,
                      mapping: { ...mapping, [keyItem.value]: actionItem.value },
                    },
                  });
                  showAppToast(getUIText("bt_mapping_saved", "Mapping saved"), { tone: "info" });
                  await loadDeviceBluetoothManager(container);
                } catch (err) {
                  showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
                }
              },
            });
          },
        });
      },
    });
  });
}

// ── Storage / sunnylink / firehose: the three 5080 sections this panel was
// missing. All read-only summaries plus the actions the daemon exposes. ─────

DEVICE_SECTION_SHELLS.Storage = () => renderDeviceStorageShell();
DEVICE_SECTION_SHELLS.Sunnylink = () => renderDeviceSunnylinkShell();
DEVICE_SECTION_SHELLS.Firehose = () => renderDeviceFirehoseShell();
DEVICE_SECTION_SHELLS.Bluetooth = () => renderDeviceBluetoothShell();

const DEVICE_STORAGE_CATEGORY_LABELS = {
  routes: "Routes",
  models: "Models",
  maps: "Maps",
  software: "Software",
  logs: "Logs",
  ota_staging: "OTA staging",
  scons_cache: "Build cache",
  other: "Other",
};

function deviceBytesText(bytes) {
  const value = Number(bytes || 0);
  if (!Number.isFinite(value) || value <= 0) return "0 MB";
  const gb = value / (1024 ** 3);
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(value / (1024 ** 2)).toFixed(0)} MB`;
}

// ── Storage ────────────────────────────────────────────────────────────────

function renderDeviceStorageShell() {
  return `
    ${deviceManagerRow({ id: "stUsage", title: getUIText("storage_usage", "Storage usage"), descr: getUIText("storage_usage_hint", "Reading device storage"), value: "-" })}
    <div data-storage-categories></div>
    ${deviceManagerRow({ id: "stRefresh", title: getUIText("storage_rescan", "Rescan storage"), button: getUIText("refresh", "Refresh"), buttonId: "btnDeviceStorageRefresh" })}`;
}

async function loadDeviceStorageManager(container) {
  const usageValue = container.querySelector("#stUsage-value");
  const usageDescr = container.querySelector("#stUsage-descr");
  const catRoot = container.querySelector("[data-storage-categories]");
  try {
    const data = await requestJson("/api/opui/storage", { cache: "no-store" });
    if (!data?.ok) throw new Error(data?.error || "storage unavailable");
    if (usageValue) {
      usageValue.textContent = `${deviceBytesText(data.used_bytes)} / ${deviceBytesText(data.total_bytes)} (${Number(data.free_percent ?? 0).toFixed(0)}% ${getUIText("storage_free", "free")})`;
    }
    if (usageDescr) {
      const warn = data.critical_space ? getUIText("storage_critical", "Critically low on space")
        : (data.low_space ? getUIText("storage_low", "Low on space") : "");
      usageDescr.textContent = warn || getUIText("storage_ok", "Enough space available");
    }
    if (catRoot) {
      const cats = Array.isArray(data.categories) ? data.categories : [];
      catRoot.innerHTML = cats
        .filter((c) => Number(c?.bytes || 0) > 0)
        .map((c) => deviceManagerRow({
          id: `stCat-${String(c.id)}`,
          // Friendly names - the daemon reports raw ids (ota_staging, scons_cache).
          title: getUIText(`storage_cat_${String(c.id)}`, DEVICE_STORAGE_CATEGORY_LABELS[String(c.id)] || String(c.id)),
          value: `${deviceBytesText(c.bytes)} · ${Number(c.percent ?? 0).toFixed(1)}%`,
          button: getUIText("storage_clear_btn", "Clear"),
          buttonId: `btnStClear-${String(c.id)}`,
        }))
        .join("");
      cats.filter((c) => Number(c?.bytes || 0) > 0).forEach((c) => {
        const id = String(c.id);
        bindOnce(container.querySelector(`#btnStClear-${id}`), "click", async () => {
          const label = getUIText(`storage_cat_${id}`, DEVICE_STORAGE_CATEGORY_LABELS[id] || id);
          const ok = await appConfirm(
            `${getUIText("storage_clear_confirm", "Delete this category's data? This cannot be undone.")}\n\n${label} · ${deviceBytesText(c.bytes)}`,
            { title: getUIText("storage_clear_title", "Clear storage"), confirmLabel: getUIText("storage_clear_btn", "Clear"), cancelLabel: getUIText("cancel", "Cancel") },
          );
          if (!ok) return;
          try {
            await postJson("/api/opui/storage/clear", { category: id });
            showAppToast(getUIText("model_manager_applied", "Applied"), { tone: "info" });
            await loadDeviceStorageManager(container);
          } catch (err) {
            showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
          }
        });
      });
    }
  } catch (err) {
    if (usageValue) usageValue.textContent = "-";
    if (usageDescr) usageDescr.textContent = err.message || getUIText("failed", "Failed");
  }

  bindOnce(container.querySelector("#btnDeviceStorageRefresh"), "click", () => {
    loadDeviceStorageManager(container).catch(() => {});
  });
}

// ── sunnylink ──────────────────────────────────────────────────────────────

function renderDeviceSunnylinkShell() {
  return `
    ${deviceManagerRow({ id: "slStatus", title: getUIText("sunnylink_status", "sunnylink status"), value: "-" })}
    ${deviceManagerRow({ id: "slAccount", title: getUIText("sunnylink_account", "Account"), value: "-" })}
    ${deviceManagerRow({ id: "slBackup", title: getUIText("sunnylink_backup", "Backup / restore"), value: "-" })}
    ${deviceManagerRow({ id: "slPair", title: getUIText("sunnylink_pair", "Pair this device"), descr: getUIText("sunnylink_pair_hint", "Open the link on your phone to sign in"), button: getUIText("sunnylink_pair_btn", "PAIR"), buttonId: "btnDeviceSlPair" })}
    ${deviceManagerRow({ id: "slBackupAction", title: getUIText("sunnylink_backup_action", "Run backup"), descr: getUIText("sunnylink_backup_action_hint", "Uploads settings and calibration to sunnylink"), button: getUIText("sunnylink_backup_btn", "BACKUP"), buttonId: "btnDeviceSlBackup" })}
    ${deviceManagerRow({ id: "slRestoreAction", title: getUIText("sunnylink_restore_action", "Run restore"), descr: getUIText("sunnylink_restore_action_hint", "Pulls the last backup back onto this device"), button: getUIText("sunnylink_restore_btn", "RESTORE"), buttonId: "btnDeviceSlRestore" })}`;
}

async function loadDeviceSunnylinkManager(container) {
  const statusValue = container.querySelector("#slStatus-value");
  const accountValue = container.querySelector("#slAccount-value");
  const backupValue = container.querySelector("#slBackup-value");
  try {
    const data = await requestJson("/api/opui/sunnylink/status", { cache: "no-store" });
    if (!data?.ok) throw new Error(data?.error || "sunnylink unavailable");
    if (statusValue) {
      statusValue.textContent = data.enabled
        ? getUIText("on", "ON")
        : getUIText("off", "OFF");
    }
    if (accountValue) {
      const parts = [];
      if (data.tier) parts.push(String(data.tier));
      parts.push(data.paired ? getUIText("sunnylink_paired", "paired") : getUIText("sunnylink_unpaired", "not paired"));
      if (data.is_sponsor) parts.push(getUIText("sunnylink_sponsor", "sponsor"));
      accountValue.textContent = parts.join(" · ");
    }
    if (backupValue) {
      const backup = data.backup || {};
      backupValue.textContent = `${getUIText("sunnylink_backup_label", "backup")}: ${backup.backup_status ?? "-"} · ${getUIText("sunnylink_restore_label", "restore")}: ${backup.restore_status ?? "-"}`;
    }
  } catch (err) {
    if (statusValue) statusValue.textContent = err.message || getUIText("failed", "Failed");
  }

  bindOnce(container.querySelector("#btnDeviceSlPair"), "click", async () => {
    try {
      const pair = await requestJson("/api/opui/sunnylink/pair?mode=pair", { cache: "no-store" });
      const url = String(pair?.url || "").trim();
      const qr = String(pair?.qr_data_url || "").trim();
      if (!url && !qr) throw new Error(pair?.error || getUIText("sunnylink_pair_failed", "No pairing link returned"));
      // The daemon renders the QR itself (qr_data_url); the URL is the fallback.
      // A real dialog, not a hijacked picker: the picker's list is virtualised
      // for rows and the QR ended up clipped behind the search box.
      await openAppDialog({
        mode: "alert",
        title: getUIText("sunnylink_pair", "Pair this device"),
        messageHtml: `
          ${qr ? `<img src="${escapeHtml(qr)}" alt="QR" style="display:block;margin:0 auto 12px;width:220px;height:220px;background:#fff;border-radius:8px" />` : ""}
          <div style="word-break:break-all;text-align:center">${escapeHtml(url)}</div>`,
        html: true,
        confirmLabel: getUIText("close", "Close"),
      });
    } catch (err) {
      showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
    }
  });

  const runSunnylinkAction = (action, label) => async () => {
    const ok = await appConfirm(`${label}?`, {
      title: getUIText("device_group_sunnylink", "sunnylink"),
      confirmLabel: getUIText("ok", "OK"),
      cancelLabel: getUIText("cancel", "Cancel"),
    });
    if (!ok) return;
    try {
      await postJson(`/api/opui/action/${action}`, {});
      showAppToast(getUIText("model_manager_applied", "Applied"), { tone: "info" });
      const container2 = document.getElementById("deviceItems");
      if (container2) await loadDeviceSunnylinkManager(container2);
    } catch (err) {
      showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
    }
  };
  bindOnce(container.querySelector("#btnDeviceSlBackup"), "click",
    runSunnylinkAction("sunnylink_backup", getUIText("sunnylink_backup_action", "Run backup")));
  bindOnce(container.querySelector("#btnDeviceSlRestore"), "click",
    runSunnylinkAction("sunnylink_restore", getUIText("sunnylink_restore_action", "Run restore")));
}

// ── firehose (Data) ────────────────────────────────────────────────────────

function renderDeviceFirehoseShell() {
  return `
    ${deviceManagerRow({ id: "fhState", title: getUIText("firehose_state", "Data upload"), value: "-" })}
    ${deviceManagerRow({ id: "fhNetwork", title: getUIText("firehose_network", "Network"), value: "-" })}`;
}

async function loadDeviceFirehoseManager(container) {
  const stateValue = container.querySelector("#fhState-value");
  const networkValue = container.querySelector("#fhNetwork-value");
  try {
    const data = await requestJson("/api/opui/firehose", { cache: "no-store" });
    if (!data?.ok) throw new Error(data?.error || "firehose unavailable");
    if (stateValue) {
      stateValue.textContent = data.active
        ? `${getUIText("firehose_active", "uploading")} · ${Number(data.segments ?? 0)} ${getUIText("firehose_segments", "segments")}`
        : getUIText("firehose_idle", "idle");
    }
    if (networkValue) {
      networkValue.textContent = `${data.network_type || "-"}${data.metered ? ` · ${getUIText("firehose_metered", "metered")}` : ""}`;
    }
  } catch (err) {
    if (stateValue) stateValue.textContent = err.message || getUIText("failed", "Failed");
  }
}

// ── Vehicle: the fingerprint selector 5080 puts in Settings > Vehicle ───────
// The tools-page picker is CarrotPilot's; the settings section is where webui
// keeps it, showing the active platform, its fingerprint status, and a
// SELECT / REMOVE action (manual selection vs automatic fingerprinting).

DEVICE_SECTION_SHELLS.Vehicle = () => renderDeviceVehicleShell();

function renderDeviceVehicleShell() {
  return `
    ${deviceManagerRow({ id: "vehCurrent", title: getUIText("vehicle_current", "Vehicle"), descr: getUIText("vehicle_loading", "Reading fingerprint status"), value: "-", button: getUIText("model_manager_select", "Select"), buttonId: "btnDeviceVehiclePick" })}
    ${deviceManagerRow({ id: "vehLegend", title: getUIText("vehicle_legend", "Fingerprint status"), descr: getUIText("vehicle_legend_hint", "Select a vehicle to force the fingerprint manually; automatic detection is the default"), value: "-" })}`;
}

function deviceVehicleStatusText(payload) {
  const status = String(payload?.status || (payload?.manual ? "manual" : "unknown"));
  const keys = {
    auto: ["vehicle_status_auto", "Fingerprinted automatically"],
    manual: ["vehicle_status_manual", "Manually selected"],
    unknown: ["vehicle_status_unknown", "Not fingerprinted yet"],
  };
  const [key, fallback] = keys[status] || keys.unknown;
  return getUIText(key, fallback);
}

async function loadDeviceVehicleManager(container) {
  const valueEl = container.querySelector("#vehCurrent-value");
  const descrEl = container.querySelector("#vehCurrent-descr");
  const legendEl = container.querySelector("#vehLegend-value");
  const pickButton = container.querySelector("#btnDeviceVehiclePick");
  let payload = null;
  try {
    payload = await requestJson("/api/opui/vehicle/platforms", { cache: "no-store" });
    if (!payload?.ok) throw new Error(payload?.error || "vehicle list unavailable");
    const display = String(payload.display || payload.active || "").trim();
    if (valueEl) valueEl.textContent = display || getUIText("vehicle_none", "No vehicle selected");
    if (descrEl) descrEl.textContent = deviceVehicleStatusText(payload);
    if (legendEl) legendEl.textContent = payload.manual
      ? getUIText("vehicle_legend_manual", "Manual selection is active")
      : getUIText("vehicle_legend_auto", "Automatic fingerprinting is active");
    if (pickButton) {
      pickButton.textContent = payload.manual
        ? getUIText("vehicle_remove", "Remove")
        : getUIText("model_manager_select", "Select");
      pickButton.disabled = false;
    }
  } catch (err) {
    if (valueEl) valueEl.textContent = "-";
    if (descrEl) descrEl.textContent = err.message || getUIText("failed", "Failed");
    if (pickButton) pickButton.disabled = true;
  }

  bindOnce(pickButton, "click", async () => {
    if (!payload?.ok) return;
    if (payload.manual) {
      const ok = await appConfirm(getUIText("vehicle_remove_confirm", "Remove the manual selection and go back to automatic fingerprinting?"), {
        title: getUIText("device_group_vehicle", "Vehicle"),
        confirmLabel: getUIText("vehicle_remove", "Remove"),
        cancelLabel: getUIText("cancel", "Cancel"),
      });
      if (!ok) return;
      try {
        await postJson("/api/opui/vehicle/select", { bundle: "" });
        showAppToast(getUIText("model_manager_applied", "Applied"), { tone: "info" });
        const container2 = document.getElementById("deviceItems");
        if (container2) await loadDeviceVehicleManager(container2);
      } catch (err) {
        showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
      }
      return;
    }

    // 5080 opens ONE tree: brands are folders, platforms are leaves, and the
    // search box matches brand + platform. Two nested dialogs (the old shape)
    // made "find my Toyota" a two-screen treasure hunt with no search at all.
    const latest = await requestJson("/api/opui/vehicle/platforms", { cache: "no-store" }).catch(() => payload);
    if (!latest?.ok) return;
    const folders = (latest.tree || []).map((brand) => ({
      name: brand.name,
      bundles: (brand.platforms || []).map((p) => ({
        ref: p.bundle,
        name: p.label || p.bundle,
        internal: p.bundle,
      })),
    }));
    const total = folders.reduce((sum, f) => sum + f.bundles.length, 0);
    const ref = await openDeviceTreeDialog({
      title: getUIText("vehicle_select", "Select a vehicle"),
      meta: `${folders.length} · ${total}`,
      folders,
      selectedRef: "",
      confirmLabel: getUIText("model_manager_select", "Select"),
    });
    if (ref === null || ref === undefined) return;
    const offroadMsg = deviceIsOffroad()
      ? getUIText("vehicle_apply_now", "This setting will take effect immediately.")
      : getUIText("vehicle_apply_offroad", "This setting will take effect once the device enters offroad state.");
    const ok = await appConfirm(offroadMsg, {
      title: getUIText("vehicle_select", "Select a vehicle"),
      confirmLabel: getUIText("ok", "OK"),
      cancelLabel: getUIText("cancel", "Cancel"),
    });
    if (!ok) return;
    try {
      const res = await postJson("/api/opui/vehicle/select", { bundle: ref });
      showAppToast(String(res?.display || ref), { tone: "info" });
      const container2 = document.getElementById("deviceItems");
      if (container2) await loadDeviceVehicleManager(container2);
    } catch (err) {
      showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
    }
  });
}

function deviceIsOffroad() {
  return isTruthyDeviceFlag(deviceParamValues?.IsOffroad);
}

// ── Steering: torque control tune version ─────────────────────────────────
// 5080 exposes this as a searchable tree over /api/opui/steering/torque-versions
// rather than a raw number, so the user picks a named tune instead of typing a
// version. "Default" clears the param back to the car's own tune.

DEVICE_SECTION_SHELLS.Steering = () => renderDeviceTorqueTuneShell();

function renderDeviceTorqueTuneShell() {
  return deviceManagerRow({
    id: "torqueTune",
    title: getUIText("torque_tune_version", "Torque Control Tune Version"),
    descr: getUIText("torque_tune_version_hint", "Pick a named tune; Default uses the platform default"),
    value: "-",
    button: getUIText("model_manager_select", "Select"),
    buttonId: "btnDeviceTorqueTune",
  });
}

async function loadDeviceTorqueTuneManager(container) {
  const button = container.querySelector("#btnDeviceTorqueTune");
  const valueEl = container.querySelector("#torqueTune-value");
  let payload = null;
  try {
    payload = await requestJson("/api/opui/steering/torque-versions", { cache: "no-store" });
  } catch {}
  if (!payload?.ok) {
    // No daemon: keep the row but make it clear why the picker cannot open.
    if (valueEl) valueEl.textContent = "-";
    if (button) button.disabled = true;
    return;
  }
  if (valueEl) valueEl.textContent = String(payload.current_label || getUIText("torque_tune_default", "Default"));
  bindOnce(button, "click", async () => {
    const options = payload.options || [];
    const folders = [{
      name: "",
      bundles: [
        { ref: "Default", name: getUIText("torque_tune_default", "Default") },
        ...options.map((o) => ({ ref: o.label, name: o.label })),
      ],
    }];
    const ref = await openDeviceTreeDialog({
      title: getUIText("torque_tune_version", "Torque Control Tune Version"),
      meta: `${options.length}`,
      folders,
      selectedRef: String(payload.current_label || "Default"),
    });
    if (ref === null || ref === undefined) return;
    const pick = options.find((o) => o.label === ref);
    try {
      if (!pick || pick.version == null) await setParam("TorqueControlTune", "");
      else await setParam("TorqueControlTune", String(pick.version));
      showAppToast(getUIText("torque_tune_updated", "Torque tune updated"), { tone: "info" });
      const container2 = document.getElementById("deviceItems");
      if (container2) await loadDeviceTorqueTuneManager(container2);
    } catch (err) {
      showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
    }
  });
}

// ── Software: target branch ───────────────────────────────────────────────
// The branch row shipped disabled (no handler). It opens this fork's git branch
// picker, which does checkout + reboot - the same flow Tools > git branch uses.

function bindDeviceSoftwareActions(container) {
  bindOnce(container.querySelector("#btnDeviceTargetBranch"), "click", () => {
    if (typeof loadBranchesAndShow === "function") {
      loadBranchesAndShow().catch((err) => {
        showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
      });
      return;
    }
    showAppToast(getUIText("failed", "Failed"), { tone: "error" });
  });
}

// ── Developer: the actions 5080's developer panel exposes ─────────────────
// Error log (view + delete), reset all params, reset calibration, onroad
// preview and driver view. Each is a 5080 endpoint; the proxy returns 502 when
// the daemon is absent and the toast says so.

function renderDeviceDeveloperExtrasShell() {
  return `
    ${deviceManagerRow({ id: "devErrorLog", title: getUIText("dev_error_log", "Error log"), descr: getUIText("dev_error_log_hint", "Show the last crash log, then optionally delete it"), button: getUIText("view_upper", "VIEW"), buttonId: "btnDeviceErrorLog" })}
    ${deviceManagerRow({ id: "devResetParams", title: getUIText("dev_reset_params", "Reset all params"), descr: getUIText("dev_reset_params_hint", "Restores every openpilot parameter to its default"), button: getUIText("reset", "Reset"), buttonId: "btnDeviceResetParams" })}
    ${deviceManagerRow({ id: "devResetCalib", title: getUIText("dev_reset_calib", "Reset calibration"), descr: getUIText("dev_reset_calib_hint", "Clears camera calibration and reboots"), button: getUIText("reset", "Reset"), buttonId: "btnDeviceResetCalib" })}
    ${deviceManagerRow({ id: "devOnroadPreview", title: getUIText("dev_onroad_preview", "Onroad preview"), descr: getUIText("dev_onroad_preview_hint", "Stream the road camera while driving"), value: "-", button: getUIText("model_manager_select", "Select"), buttonId: "btnDeviceOnroadPreview" })}
    ${deviceManagerRow({ id: "devDriverView", title: getUIText("driver_camera", "Driver Camera"), descr: getUIText("driver_camera_desc", "Preview the driver facing camera to ensure that driver monitoring has good visibility. (vehicle must be off)"), value: "-", button: getUIText("preview", "PREVIEW"), buttonId: "btnDeviceDriverView" })}`;
}

async function loadDeviceDeveloperExtras(container) {
  const previewValue = container.querySelector("#devOnroadPreview-value");
  const driverValue = container.querySelector("#devDriverView-value");
  let extras = null;
  try {
    extras = await requestJson("/api/opui/device/extras", { cache: "no-store" });
  } catch {}
  if (previewValue) {
    previewValue.textContent = extras?.ok
      ? (extras.onroad_preview ? getUIText("on", "ON") : getUIText("off", "OFF"))
      : "-";
  }
  if (driverValue) {
    driverValue.textContent = extras?.ok
      ? (extras.driver_view_enabled ? getUIText("on", "ON") : getUIText("off", "OFF"))
      : "-";
  }

  bindOnce(container.querySelector("#btnDeviceErrorLog"), "click", async () => {
    try {
      const log = await requestJson("/api/opui/developer/error-log", { cache: "no-store" });
      if (!log?.ok) throw new Error(log?.error || getUIText("failed", "Failed"));
      await openAppDialog({
        mode: "alert",
        title: getUIText("dev_error_log", "Error log"),
        messageHtml: String(log.html || getUIText("dev_error_log_empty", "No error log")),
        html: true,
        confirmLabel: getUIText("close", "Close"),
      });
      if (!log.exists) return;
      const ok = await appConfirm(getUIText("dev_error_log_delete", "Would you like to delete this log?"), {
        title: getUIText("dev_error_log", "Error log"),
        confirmLabel: getUIText("delete", "Delete"),
        cancelLabel: getUIText("cancel", "Cancel"),
      });
      if (!ok) return;
      await postJson("/api/opui/action/developer_delete_error_log", {});
      showAppToast(getUIText("dev_error_log_deleted", "Log deleted"), { tone: "info" });
    } catch (err) {
      showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
    }
  });

  const runAction = (id, endpoint, label, danger) => bindOnce(container.querySelector(id), "click", async () => {
    const ok = await appConfirm(`${label}?`, {
      title: getUIText("device_group_developer", "Developer"),
      confirmLabel: getUIText("ok", "OK"),
      cancelLabel: getUIText("cancel", "Cancel"),
    });
    if (!ok) return;
    try {
      await postJson(endpoint, {});
      showAppToast(getUIText("model_manager_applied", "Applied"), { tone: "info" });
      const container2 = document.getElementById("deviceItems");
      if (container2) await loadDeviceDeveloperExtras(container2);
    } catch (err) {
      showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
    }
    void danger;
  });
  runAction("#btnDeviceResetParams", "/api/opui/action/reset_all_params", getUIText("dev_reset_params", "Reset all params"), true);
  runAction("#btnDeviceResetCalib", "/api/opui/action/reset_calibration", getUIText("dev_reset_calib", "Reset calibration"), true);

  bindOnce(container.querySelector("#btnDeviceOnroadPreview"), "click", async () => {
    try {
      await postJson("/api/opui/action/onroad_preview", {});
      showAppToast(getUIText("model_manager_applied", "Applied"), { tone: "info" });
      const container2 = document.getElementById("deviceItems");
      if (container2) await loadDeviceDeveloperExtras(container2);
    } catch (err) {
      showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
    }
  });

  bindOnce(container.querySelector("#btnDeviceDriverView"), "click", async () => {
    try {
      const enabled = !(extras?.driver_view_enabled);
      const res = await postJson("/api/opui/device/driver_view", { enabled });
      if (res?.ok === false) throw new Error(res.error || getUIText("failed", "Failed"));
      showAppToast(getUIText("model_manager_applied", "Applied"), { tone: "info" });
      const container2 = document.getElementById("deviceItems");
      if (container2) await loadDeviceDeveloperExtras(container2);
    } catch (err) {
      showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
    }
  });
}
