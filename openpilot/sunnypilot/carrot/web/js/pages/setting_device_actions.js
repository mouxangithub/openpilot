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


// ── Generic list picker: the car-picker dialog pattern, for any list choice ─

function closeDevicePicker(overlay) {
  if (!overlay) return;
  overlay.classList.remove("is-open");
  overlay.hidden = true;
  overlay.remove();
}

// groups: [{ name, items: [{ value, label, badge, current, actions: [{label, onClick}] }] }]
// onPick(item) runs when an item row (not its actions) is tapped; the overlay
// closes first unless onPick returns the string "keep-open".
function openDeviceListPicker({ title, meta, groups, onPick }) {
  const overlay = document.createElement("div");
  overlay.className = "app-dialog device-picker";
  overlay.hidden = true;
  overlay.innerHTML = `
    <button type="button" class="app-dialog__backdrop" aria-label="Close"></button>
    <div class="app-dialog__sheet app-branch-picker__sheet device-picker__sheet" role="dialog" aria-modal="true">
      <div class="app-branch-picker__head">
        <div class="app-branch-picker__titles">
          <div class="app-dialog__title">${escapeHtml(title)}</div>
          <div class="muted app-branch-picker__meta">${escapeHtml(meta || "-")}</div>
        </div>
        <button type="button" class="smallBtn device-picker__close">${escapeHtml(getUIText("close", "Close"))}</button>
      </div>
      <div class="app-branch-picker__list device-picker__list"></div>
    </div>`;

  const close = () => closeDevicePicker(overlay);
  overlay.querySelector(".app-dialog__backdrop").onclick = close;
  overlay.querySelector(".device-picker__close").onclick = close;

  const list = overlay.querySelector(".device-picker__list");
  (groups || []).forEach((group) => {
    if (group?.name) {
      const head = document.createElement("div");
      head.className = "device-picker__group";
      head.textContent = group.name;
      list.appendChild(head);
    }
    (group?.items || []).forEach((item) => {
      const row = document.createElement(item.actions && item.actions.length ? "div" : "button");
      row.type = "button";
      row.className = `btn groupBtn device-picker__item${item.current ? " is-current" : ""}`;
      const labelSpan = document.createElement("span");
      labelSpan.className = "device-picker__item-label";
      labelSpan.textContent = item.label + (item.badge ? ` (${item.badge})` : "");
      row.appendChild(labelSpan);
      (item.actions || []).forEach((action) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "smallBtn";
        if (action.id) btn.dataset.modelFav = action.id;
        btn.textContent = action.label;
        btn.onclick = (event) => {
          event.stopPropagation();
          action.onClick(item, overlay);
        };
        row.appendChild(btn);
      });
      if (!row.tagName || row.tagName !== "DIV") {
        row.onclick = async () => {
          close();
          await onPick?.(item);
        };
      }
      list.appendChild(row);
    });
  });

  document.body.appendChild(overlay);
  overlay.hidden = false;
  requestAnimationFrame(() => overlay.classList.add("is-open"));
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

// Tree dialog, showTree parity: folders with +/- collapse, the current model
// pinned on top, star favorites that refresh the tree, search, footer buttons.
function openDeviceTreeDialog({ title, folders, selectedRef, source }) {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "app-dialog device-picker";
    overlay.hidden = true;
    overlay.innerHTML = `
      <button type="button" class="app-dialog__backdrop" aria-label="Close"></button>
      <div class="app-dialog__sheet app-branch-picker__sheet device-picker__sheet" role="dialog" aria-modal="true">
        <div class="app-branch-picker__head">
          <div class="app-branch-picker__titles">
            <div class="app-dialog__title">${escapeHtml(title)}</div>
          </div>
          <button type="button" class="smallBtn device-picker__close">${escapeHtml(getUIText("cancel", "Cancel"))}</button>
        </div>
        <div class="device-picker__search">
          <input type="text" class="input-text" placeholder="${escapeHtml(getUIText("model_manager_search", "Search"))}" />
        </div>
        <div class="app-branch-picker__list device-picker__list"></div>
        <div class="device-picker__footer">
          <button type="button" class="smallBtn device-picker__close">${escapeHtml(getUIText("cancel", "Cancel"))}</button>
          <button type="button" class="smallBtn device-picker__ok" disabled>${escapeHtml(getUIText("model_manager_select", "Select"))}</button>
        </div>
      </div>`;

    let treeFolders = folders.map((f) => ({ ...f, bundles: [...(f.bundles || [])] }));
    let pick = selectedRef;
    let query = "";
    const expanded = new Set(treeFolders.filter((f) => f.name).map((f) => f.name));
    const sourceSlot = deviceModelSlot(DEVICE_MODEL_PAYLOAD, source);

    const overlay_close = () => {
      overlay.classList.remove("is-open");
      overlay.remove();
      resolve(null);
    };
    overlay.querySelector(".app-dialog__backdrop").onclick = overlay_close;
    overlay.querySelector(".device-picker__close").onclick = overlay_close;

    const searchInput = overlay.querySelector(".device-picker__search input");
    searchInput.addEventListener("input", () => {
      query = searchInput.value;
      renderList();
    });

    const listEl = overlay.querySelector(".device-picker__list");
    const selectBtn = overlay.querySelector(".device-picker__ok");

    const findSelectedBundle = () => {
      for (const folder of treeFolders) {
        for (const bundle of folder.bundles || []) {
          if (bundle.ref === selectedRef || bundle.name === selectedRef) return { folder, bundle };
        }
      }
      return null;
    };

    const bundleRow = (bundle, { pinned = false, indent = false }) => {
      const row = document.createElement("button");
      row.type = "button";
      row.className = `btn groupBtn device-picker__item${indent ? " device-picker__item--child" : ""}`
        + (pinned ? " device-picker__item--pinned" : "")
        + (bundle.ref === pick || (pick === "" && bundle.ref === "Default") ? " is-current" : "");
      const label = document.createElement("span");
      label.className = "device-picker__item-label";
      label.textContent = String(bundle.name || bundle.ref || "-");
      row.appendChild(label);
      if (bundle.ref && bundle.ref !== "Default" && sourceSlot) {
        const star = document.createElement("button");
        star.type = "button";
        star.className = "smallBtn";
        star.dataset.modelFav = bundle.ref;
        star.textContent = bundle.fav ? "★" : "☆";
        star.onclick = async (event) => {
          event.stopPropagation();
          try {
            await postJson("/api/opui/models/favorite", { ref: bundle.ref });
            bundle.fav = !bundle.fav;
            star.textContent = bundle.fav ? "★" : "☆";
            const fresh = await requestJson("/api/opui/models", { cache: "no-store" });
            if (fresh?.ok) {
              DEVICE_MODEL_PAYLOAD = fresh;
              treeFolders = (deviceModelSlot(fresh, source).tree || []).map((f) => ({ ...f, bundles: [...(f.bundles || [])] }));
              renderList();
            }
          } catch (err) {
            showAppToast(err.message || getUIText("failed", "Failed"), { tone: "error" });
          }
        };
        row.appendChild(star);
      }
      row.onclick = () => {
        pick = bundle.ref;
        selectBtn.disabled = pick === selectedRef;
        renderList();
      };
      return row;
    };

    function renderList() {
      listEl.innerHTML = "";
      const queryLower = query.toLowerCase().trim();
      const searching = !!queryLower;
      const selectedNode = findSelectedBundle();

      if (selectedNode?.bundle) {
        listEl.appendChild(bundleRow(selectedNode.bundle, { pinned: true }));
      }
      for (const folder of treeFolders) {
        const folderName = String(folder.name || "");
        const all = folder.bundles || [];
        const bundles = all.filter((b) => {
          if (!queryLower) return true;
          return (b.name || "").toLowerCase().includes(queryLower)
            || (b.internal || "").toLowerCase().includes(queryLower)
            || folderName.toLowerCase().includes(queryLower);
        });
        const visible = selectedNode?.bundle
          ? bundles.filter((b) => !(b.ref === selectedNode.bundle.ref && b.name === selectedNode.bundle.name))
          : bundles;
        if (!visible.length) continue;
        const hasFolder = !!folderName;
        const isOpen = searching || !hasFolder || expanded.has(folderName);
        if (hasFolder) {
          const header = document.createElement("button");
          header.type = "button";
          header.className = "btn groupBtn device-picker__item device-picker__folder";
          header.textContent = `${isOpen ? "−" : "+"} ${folderName}`;
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
    }

    selectBtn.onclick = () => {
      overlay.remove();
      resolve(pick);
    };

    document.body.appendChild(overlay);
    overlay.hidden = false;
    requestAnimationFrame(() => overlay.classList.add("is-open"));
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
  const ref = await openDeviceTreeDialog({
    title,
    folders: (slot?.tree || []).map((f) => ({ ...f, bundles: [...(f.bundles || [])] })),
    selectedRef: String(slot?.active_ref || "Default"),
    source,
  });
  if (ref === null || ref === undefined) return;
  const index = await deviceModelIndexForRef(source, ref);
  try {
    await postJson("/api/opui/models/select", { ref, index, source });
    showAppToast(getUIText("model_manager_applied", "Applied"), { tone: "info" });
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
