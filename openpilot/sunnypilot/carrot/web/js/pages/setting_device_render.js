"use strict";

function renderDeviceInfoRow(title, value) {
  return `
    <div class="setting device-setting">
      <div class="settingTop">
        <div>
          <div class="title">${escapeHtml(title)}</div>
        </div>
        <div class="ctrl">
          <div class="title muted device-value">${escapeHtml(String(value))}</div>
        </div>
      </div>
    </div>`;
}

function renderDeviceVersionRow(title, value) {
  const parts = String(value || "-")
    .split(/\s+\/\s+/)
    .map((part) => part.trim())
    .filter(Boolean);
  const lines = parts.length ? parts : ["-"];
  return `
    <div class="setting device-setting">
      <div class="settingTop">
        <div>
          <div class="title">${escapeHtml(title)}</div>
        </div>
        <div class="ctrl">
          <div class="title muted device-value device-version-value">
            ${lines.map((line) => `<span>${escapeHtml(line)}</span>`).join("")}
          </div>
        </div>
      </div>
    </div>`;
}

function renderDeviceActionRow(title, descr, buttonText, buttonId, buttonClass = "smallBtn", disabled = false) {
  const disabledAttrs = disabled ? "data-device-disabled=\"true\"" : "";
  const disabledClass = disabled ? " device-setting--disabled" : "";
  const buttonAttrs = disabled ? "aria-disabled=\"true\" class=\"" + buttonClass + " is-device-disabled\"" : "class=\"" + buttonClass + "\"";
  return `
    <div class="setting device-setting${disabledClass}" ${disabledAttrs}>
      <div class="settingTop">
        <div>
          <div class="title">${escapeHtml(title)}</div>
          ${descr ? `<div class="descr">${escapeHtml(descr)}</div>` : ""}
        </div>
        <div class="ctrl">
          <button type="button" ${buttonAttrs} id="${buttonId}">${escapeHtml(buttonText)}</button>
        </div>
      </div>
    </div>`;
}

function renderSshKeysRow(statusOrUsername, fallbackHasKeys) {
  const status = (statusOrUsername && typeof statusOrUsername === "object")
    ? statusOrUsername
    : { username: statusOrUsername || "", has_keys: Boolean(fallbackHasKeys) };
  const displayName = String(status.username || "").trim();
  const hasKeys = Boolean(status.has_keys || status.hasKeys);
  const fingerprints = Array.isArray(status.fingerprints) ? status.fingerprints : [];
  const accountText = hasKeys ? (displayName || "-") : getUIText("not_configured", "Not configured");
  const control = renderSettingFormControl({
    label: getUIText("ssh_github_username", "GitHub username"),
    value: accountText,
    placeholder: getUIText("ssh_github_username_prompt", "Enter your GitHub username"),
    configured: hasKeys,
    editAction: "edit",
    actionAttribute: "data-ssh-action",
    actions: [
      { action: "remove", label: getUIText("remove_upper", "REMOVE"), disabled: !hasKeys },
      ...(fingerprints.length ? [{ action: "view", label: getUIText("ssh_keys_view", "View keys") }] : []),
    ],
  });
  return `
    <div class="setting device-setting device-setting--ssh">
      <div class="settingTop">
        <div>
          <div class="title">${escapeHtml(getUIText("ssh_keys", "SSH Keys"))}</div>
        </div>
        <div class="ctrl device-ssh-control">
          <div class="device-ssh-form">${control}</div>
        </div>
      </div>
    </div>`;
}

function renderDeviceLanguageRow(info) {
  const currentLang = info.language || "en";
  return `
    <div class="setting device-setting">
      <div class="settingTop">
        <div>
          <div class="title">${escapeHtml(getUIText("change_language", "Change Language"))}</div>
          <div class="descr">${escapeHtml(getUIText("language_note", "Requires reboot"))}</div>
        </div>
        <div class="ctrl">
          <select id="deviceLanguageSelect" class="input-text device-select">
            ${(info.languages || []).map((lang) => `
              <option value="${escapeHtml(lang.code)}" ${lang.code === currentLang ? "selected" : ""}>${escapeHtml(lang.name)}</option>
            `).join("")}
          </select>
        </div>
      </div>
    </div>`;
}

function wifiSignalLabel(signal) {
  if (signal === null || signal === undefined || signal === "") return "-";
  return `${signal}%`;
}

function renderNetworkPanel(network) {
  let html = renderDeviceActionRow(getUIText("advanced", "Advanced"), "", getUIText("view_upper", "VIEW"), "btnDeviceNetworkAdvanced", "smallBtn", true);
  html += renderWifiList(network.wifi || []);
  html += renderDeviceToggleViewRow(getUIText("enable_tethering", "Enable Tethering"), Boolean(network.tethering_enabled));
  html += renderDeviceInfoRow(getUIText("tethering_password", "Tethering Password"), "********");
  html += renderDeviceInfoRow(getUIText("ip_address", "IP Address"), network.ip_address || "-");
  html += renderDeviceToggleViewRow(getUIText("enable_roaming", "Enable Roaming"), Boolean(network.roaming_enabled));
  html += renderDeviceActionRow(getUIText("apn_setting", "APN Setting"), network.apn || getUIText("automatic", "automatic"), getUIText("edit_upper", "EDIT"), "btnDeviceApn", "smallBtn", true);
  html += renderDeviceToggleViewRow(getUIText("cellular_metered", "Cellular Metered"), Boolean(network.gsm_metered), getUIText("cellular_metered_desc", "Prevent large data uploads when on a metered connection"));
  html += renderDeviceActionRow(getUIText("hidden_network", "Hidden Network"), "", getUIText("connect_upper", "CONNECT"), "btnDeviceHiddenNetwork", "smallBtn", true);
  return html;
}

function renderWifiList(networks) {
  if (!Array.isArray(networks) || networks.length === 0) {
    return `
      <div class="setting device-setting">
        <div class="settingTop">
          <div>
            <div class="title">${escapeHtml(getUIText("scanning_networks", "Scanning for networks..."))}</div>
            <div class="descr">${escapeHtml(getUIText("wifi_viewer_only", "Viewer only"))}</div>
          </div>
          <div class="ctrl">
            <div class="title muted device-value">-</div>
          </div>
        </div>
      </div>`;
  }

  return networks.map((network) => {
    const ssid = network.ssid || "-";
    const meta = [
      network.connected ? getUIText("connected", "Connected") : getUIText("not_connected", "Not connected"),
      network.secure ? getUIText("secured", "Secured") : getUIText("open_network", "Open"),
      wifiSignalLabel(network.signal),
    ].filter(Boolean).join(" · ");
    return `
      <div class="setting device-setting wifi-view-row">
        <div class="settingTop">
          <div>
            <div class="title">${escapeHtml(ssid)}</div>
            <div class="descr">${escapeHtml(meta)}</div>
          </div>
          <div class="ctrl">
            <div class="wifi-view-status ${network.connected ? "is-connected" : ""}">
              ${escapeHtml(network.connected ? getUIText("connected", "Connected") : wifiSignalLabel(network.signal))}
            </div>
          </div>
        </div>
      </div>`;
  }).join("");
}

function renderDeviceToggleViewRow(title, checked, descr = "") {
  return `
    <div class="setting device-setting device-setting--disabled" data-device-disabled="true">
      <div class="settingTop">
        <div>
          <div class="title">${escapeHtml(title)}</div>
          ${descr ? `<div class="descr">${escapeHtml(descr)}</div>` : ""}
        </div>
        <div class="ctrl">
          <span class="device-toggle device-toggle--readonly">
            <span class="ctrl">
              <span class="c-switch">
                <input type="checkbox" class="c-switch__input" ${checked ? "checked" : ""} disabled />
                <span class="c-switch__track" aria-hidden="true"></span>
              </span>
            </span>
          </span>
        </div>
      </div>
    </div>`;
}

function renderDeviceToggleRow(param, title, checked, options = {}) {
  const disabled = options.disabled === true;
  const disabledAttrs = disabled ? "data-device-disabled=\"true\"" : "";
  const disabledClass = disabled ? " device-setting--disabled" : "";
  const confirmKey = options.confirmKey || "";
  const confirmedParam = options.confirmedParam || "";
  const confirmed = options.confirmed === true ? "1" : "0";
  const descr = options.descr || "";
  return `
    <div class="setting device-setting${disabledClass}" ${disabledAttrs}>
      <div class="settingTop">
        <label class="device-toggle" data-param="${escapeHtml(param)}" data-confirm-key="${escapeHtml(confirmKey)}" data-confirmed-param="${escapeHtml(confirmedParam)}" data-confirmed="${confirmed}">
          <span class="device-toggle__text">
            <span class="title">${escapeHtml(title)}</span>
            ${descr ? `<span class="descr">${escapeHtml(descr)}</span>` : ""}
          </span>
          <span class="ctrl">
            <span class="c-switch">
              <input type="checkbox" class="c-switch__input" ${checked ? "checked" : ""} ${disabled ? "disabled" : ""} />
              <span class="c-switch__track" aria-hidden="true"></span>
            </span>
          </span>
        </label>
      </div>
    </div>`;
}

// ── sunnypilot sections (generic catalog-driven rows) ──────────────────────

function spOptionLabels(item) {
  const options = item?.options;
  if (!options) return [];
  if (Array.isArray(options)) return options.map(String);
  const pack = options[LANG] || options.en || options.zh || options.ko || [];
  return Array.isArray(pack) ? pack.map(String) : [];
}

function spParamKind(item, value) {
  const options = spOptionLabels(item);
  if (options.length) return "choice";
  const type = String(item?.type || "").toLowerCase();
  if (type === "bool" || typeof value === "boolean") return "bool";
  if (type === "int" || type === "float" || typeof value === "number") return "number";
  return "info";
}

function spParamStep(item) {
  return String(item?.type || "").toLowerCase() === "float" ? 0.1 : 1;
}

function spHasRange(item) {
  return Boolean(item && Number.isFinite(Number(item.min)) && Number.isFinite(Number(item.max)));
}

function spFormatValue(item, value) {
  const kind = spParamKind(item, value);
  if (kind === "choice") {
    const labels = spOptionLabels(item);
    const index = Number(value);
    return Number.isInteger(index) && index >= 0 && index < labels.length ? labels[index] : String(value);
  }
  if (kind === "bool") return isTruthyDeviceFlag(value) ? getUIText("on", "ON") : getUIText("off", "OFF");
  if (kind === "number") {
    const text = (value === null || value === undefined || value === "") ? String(item?.default ?? "-") : String(value);
    return item?.type === "float" ? String(Number(text)) : text;
  }
  const text = String(value ?? "").trim();
  return text || "-";
}

function renderDeviceSpRow(name, item, value) {
  const title = (item && spLocalizedText(item, "title")) || name;
  const descr = item ? spLocalizedText(item, "descr") : "";
  const kind = spParamKind(item, value);
  const display = spFormatValue(item, value);

  if (kind === "bool") {
    return renderDeviceSpToggleRow(name, title, descr, isTruthyDeviceFlag(value), item && SP_ACTION_PARAMS.has(name));
  }

  if (kind === "choice") {
    const labels = spOptionLabels(item);
    return `
      <div class="setting device-setting">
        <div class="settingTop">
          <div>
            <div class="title">${escapeHtml(title)}</div>
            ${descr ? `<div class="descr">${escapeHtml(descr)}</div>` : ""}
          </div>
          <div class="ctrl">
            <button type="button" class="val value-surface sp-choice" data-sp-choice="${escapeHtml(name)}" data-sp-title="${escapeHtml(title)}" data-sp-options="${escapeHtml(JSON.stringify(labels))}">${escapeHtml(display)}</button>
          </div>
        </div>
      </div>`;
  }

  if (kind === "number") {
    const range = spHasRange(item) ? ` data-sp-min="${Number(item.min)}" data-sp-max="${Number(item.max)}"` : "";
    const step = ` data-sp-step="${spParamStep(item)}"`;
    const buttons = spHasRange(item)
      ? `<button type="button" class="smallBtn sp-minus" aria-label="-">-</button>
         <button type="button" class="val value-surface sp-value">${escapeHtml(display)}</button>
         <button type="button" class="smallBtn sp-plus" aria-label="+">+</button>`
      // No catalog range: stepping blind could write nonsense, so offer the
      // direct input only.
      : `<button type="button" class="val value-surface sp-value">${escapeHtml(display)}</button>`;
    return `
      <div class="setting device-setting">
        <div class="settingTop">
          <div>
            <div class="title">${escapeHtml(title)}</div>
            ${descr ? `<div class="descr">${escapeHtml(descr)}</div>` : ""}
          </div>
          <div class="ctrl sp-stepper" data-sp-param="${escapeHtml(name)}"${range}${step}>
            ${buttons}
          </div>
        </div>
      </div>`;
  }

  // read-only state: identifiers, versions, computed status strings
  return renderDeviceInfoRow(title, display);
}

function renderDeviceSpToggleRow(param, title, descr, checked, needsConfirm) {
  return renderDeviceToggleRow(param, title, checked, {
    descr,
    confirmKey: needsConfirm ? "device_sp_action_confirm" : "",
  });
}

function renderDeviceSpItems(groupId, values) {
  const names = getDeviceGroupParamNames(groupId);
  const data = { ...deviceParamValues, ...(values || {}) };
  // Sections with real interactive surfaces lead with their manager block; the
  // generic rows below keep the tuning knobs around it. Capability sections
  // (Bluetooth, Storage, sunnylink, firehose) have no catalog params, so the
  // manager block is the whole section.
  const manager = DEVICE_SECTION_SHELLS[groupId] ? DEVICE_SECTION_SHELLS[groupId]() : "";
  return manager + names.map((name) => renderDeviceSpRow(name, spCatalogIndex?.[name], data[name])).join("");
}

// Filled by setting_device_actions.js (loaded after this file) - each returns
// the shell HTML for that section's manager block.
const DEVICE_SECTION_SHELLS = {};
