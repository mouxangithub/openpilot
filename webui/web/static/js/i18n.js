let strings = {};
let language = "en";
let lastLang = "";
let poCode = "en";

/** Bundled fallbacks when /api/opui/i18n has not picked up WebUI-only keys yet. */
const LOCAL_FALLBACKS = {
  en: {
    Refresh: "Refresh",
    "webui_storage_routes_autodelete_hint": (
      "Routes auto-delete when free space is below 10% or 5 GB (oldest first). "
      + "Upload is not required. Starred routes are kept."
    ),
    "webui_storage_routes_external_includes": "Includes {size} on external SSD.",
    "webui_storage_external_note": (
      "Route recordings on external SSD are moved here when internal storage is low."
    ),
    "Clear starred routes": "Clear starred routes",
    "Deletes route recordings you bookmarked while driving. Other routes are not affected.": (
      "Deletes route recordings you bookmarked while driving. Other routes are not affected."
    ),
    "webui_storage_starred_count": "{count} starred routes on device.",
    "webui_storage_starred_more": "and {count} more…",
    "webui_storage_starred_confirm": (
      "This will permanently delete {count} starred routes ({size}). Continue?"
    ),
    "OTA staging": "OTA staging",
    "Build cache": "Build cache",
    "Clear build cache": "Clear build cache",
    "webui_storage_ota_staging_note": (
      "OTA update workspace used by the system updater. Usually released after an update is applied."
    ),
    "webui_storage_scons_cache_clear_desc": (
      "Removes the scons build cache. The next compile will take significantly longer."
    ),
    "webui_storage_scons_cache_confirm": (
      "Clearing the build cache frees space, but the next compile will take significantly longer. Continue?"
    ),
  },
  "zh-CHS": {
    Refresh: "刷新",
    "webui_storage_routes_autodelete_hint": (
      "可用空间低于 10% 或 5 GB 时，系统会自动删除最旧路线（与是否上传无关），收藏路线会保留。"
    ),
    "webui_storage_routes_external_includes": "其中外置 SSD 约 {size}。",
    "webui_storage_external_note": (
      "内置存储不足时，旧路线会迁移到此盘；外置盘空间不足时也会自动删除最旧路线。"
    ),
    "Clear starred routes": "清理收藏路线",
    "Deletes route recordings you bookmarked while driving. Other routes are not affected.": (
      "删除行驶中收藏的路线录像，不会影响其他未收藏路线。"
    ),
    "webui_storage_starred_count": "设备上共有 {count} 条收藏路线。",
    "webui_storage_starred_more": "另有 {count} 条…",
    "webui_storage_starred_confirm": "将永久删除 {count} 条收藏路线（约 {size}），是否继续？",
    "OTA staging": "更新暂存",
    "Build cache": "编译缓存",
    "Clear build cache": "清理编译缓存",
    "webui_storage_ota_staging_note": (
      "系统 OTA 更新工作区，用于下载和准备新版本；应用更新后通常会释放。"
    ),
    "webui_storage_scons_cache_clear_desc": (
      "删除 scons 编译缓存。清理后下次重新编译将耗时明显更长。"
    ),
    "webui_storage_scons_cache_confirm": (
      "清理编译缓存可释放空间，但下次重新编译将耗时明显更长。是否继续？"
    ),
    "Disable Driver Monitoring": "禁用驾驶员监控",
    "Disable driver monitoring (no cabin camera required). Similar to LITE mode.": (
      "禁用驾驶员监控（无需舱内摄像头），效果类似 LITE 模式。"
    ),
  },
  "zh-CHT": {
    Refresh: "重新整理",
    "webui_storage_routes_autodelete_hint": (
      "可用空間低於 10% 或 5 GB 時，系統會自動刪除最舊路線（與是否上傳無關），收藏路線會保留。"
    ),
    "webui_storage_routes_external_includes": "其中外接 SSD 約 {size}。",
    "webui_storage_external_note": (
      "內建儲存不足時，舊路線會遷移到此碟；外接碟空間不足時也會自動刪除最舊路線。"
    ),
    "Clear starred routes": "清理收藏路線",
    "Deletes route recordings you bookmarked while driving. Other routes are not affected.": (
      "刪除行駛中收藏的路線錄影，不會影響其他未收藏路線。"
    ),
    "webui_storage_starred_count": "裝置上共有 {count} 條收藏路線。",
    "webui_storage_starred_more": "另有 {count} 條…",
    "webui_storage_starred_confirm": "將永久刪除 {count} 條收藏路線（約 {size}），是否繼續？",
    "OTA staging": "更新暫存",
    "Build cache": "編譯快取",
    "Clear build cache": "清理編譯快取",
    "webui_storage_ota_staging_note": (
      "系統 OTA 更新工作區，用於下載和準備新版本；套用更新後通常會釋放。"
    ),
    "webui_storage_scons_cache_clear_desc": (
      "刪除 scons 編譯快取。清理後下次重新編譯將耗時明顯更長。"
    ),
    "webui_storage_scons_cache_confirm": (
      "清理編譯快取可釋放空間，但下次重新編譯將耗時明顯更長。是否繼續？"
    ),
  },
};

function resolvePoCode(lang, code) {
  if (code) return code;
  const l = String(lang || "en");
  if (l === "zh-CHT") return "zh-CHT";
  if (l === "zh" || l === "zh-CHS" || l.startsWith("zh")) return "zh-CHS";
  return "en";
}

function localFallback(text) {
  const loc = LOCAL_FALLBACKS[poCode] || LOCAL_FALLBACKS.en;
  return loc?.[text] || LOCAL_FALLBACKS.en?.[text] || "";
}

export function tr(text) {
  if (!text) return "";
  return strings[text] || localFallback(text) || text;
}

/** Plural helper — keys like "{} ALERT" / "{} ALERTS" with `{}` placeholder. */
export function trn(singular, plural, count) {
  const n = Number(count) || 0;
  const template = tr(n === 1 ? singular : plural);
  return template.includes("{}") ? template.replace("{}", String(n)) : template;
}

export function getLanguage() {
  return language;
}

const STATIC_UI_KEYS = {
  "modal-confirm-cancel": "Cancel",
  "modal-confirm-ok": "Confirm",
  "keyboard-cancel": "Cancel",
  "keyboard-confirm": "Confirm",
  "tree-cancel": "Cancel",
  "tree-select": "Select",
  "multi-cancel": "Cancel",
  "multi-select": "Select",
  "html-ok": "OK",
  "driver-cam-title": "Driver Camera Preview",
  "driver-cam-loading-text": "camera starting",
  "confirm-cancel": "Cancel",
  "confirm-ok": "Confirm",
  "webui-update-later": "Close",
  "webui-update-check": "Check again",
  "webui-update-apply": "Update now",
  "camera-status-text": "Loading camera...",
  "btn-home-camera-preview-label": "Driving preview",
  "sunnylink": "sunnylink",
  "Decline": "Decline",
  "Agree": "Agree",
  "Driver Camera Preview enabled": "Driver Camera Preview enabled",
  "Driver Camera Preview disabled": "Driver Camera Preview disabled",
  "Driver Camera Preview": "Driver Camera Preview",
  "Offroad only. Enables camerad for driver-facing preview in WebUI. Blocks onroad while enabled.": "Offroad only. Enables camerad for driver-facing preview in WebUI. Blocks onroad while enabled.",
  "No built-in display — use this Web UI as your primary interface.": "No built-in display — use this Web UI as your primary interface.",
  "Bookmark route": "Bookmark route",
  "Route bookmarked": "Route bookmarked",
  "Home": "Home",
  "Starting live stream service (~4s)…": "Starting live stream service (~4s)…",
  "Starting live stream service ({s}s)…": "Starting live stream service ({s}s)…",
  "Cannot start driving": "Cannot start driving",
  "Manager failed to start": "Manager failed to start",
  "No built-in display — use this Web UI as your primary interface. USB: https://10.255.128.121:5080/ or your device IP.": "No built-in display — use this Web UI as your primary interface. USB: https://10.255.128.121:5080/ or your device IP.",
  "Only available while offroad": "Only available while offroad",
  "Upload driver camera data to improve driver monitoring? You can change this later in Toggles.": "Upload driver camera data to improve driver monitoring? You can change this later in Toggles.",
  "Enable": "Enable",
  "Not now": "Not now",
  "Headless (no display)": "Headless (no display)",
};

const STATIC_UI_TITLES = {
  "btn-sidebar-settings": "Settings",
  "sidebar-mic": "Recording",
  "btn-sidebar-bottom": "Home",
};

const STATIC_ARIA_LABELS = {
  "driver-cam-close": "Close",
  "btn-close-settings": "Close",
};

export function syncDriverCamUi() {
  const title = document.getElementById("driver-cam-title");
  if (title) title.textContent = tr("Driver Camera Preview");
  const close = document.getElementById("driver-cam-close");
  if (close) close.setAttribute("aria-label", tr("Close"));
}

export function syncStaticUiStrings() {
  for (const [id, key] of Object.entries(STATIC_UI_KEYS)) {
    const el = document.getElementById(id);
    if (el) el.textContent = tr(key);
  }
  for (const [id, key] of Object.entries(STATIC_UI_TITLES)) {
    const el = document.getElementById(id);
    if (el) el.title = tr(key);
  }
  for (const [id, key] of Object.entries(STATIC_ARIA_LABELS)) {
    const el = document.getElementById(id);
    if (el) el.setAttribute("aria-label", tr(key));
  }
  syncDriverCamUi();
  const treeSearch = document.getElementById("tree-search");
  if (treeSearch) treeSearch.placeholder = tr("Search");
}

export function applyI18nPayload(data, force = false) {
  if (!data?.ok) return false;
  if (!force && data.language === lastLang && Object.keys(strings).length) {
    return false;
  }
  language = data.language || "en";
  lastLang = language;
  poCode = resolvePoCode(language, data.po_code);
  strings = data.strings || {};
  const po = data.po_code || language;
  document.documentElement.lang = String(po).startsWith("zh") ? "zh-CN" : (po === "en" ? "en" : po);
  syncStaticUiStrings();
  return true;
}

export async function loadI18n(force = false) {
  try {
    const { apiGet } = await import("./api.js");
    const data = await apiGet("/api/opui/i18n");
    if (!data.ok) return false;
    return applyI18nPayload(data, force);
  } catch {
    return false;
  }
}

export function translatePanelTitle(title) {
  return tr(title);
}
