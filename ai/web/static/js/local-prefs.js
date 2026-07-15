/**
 * Local preferences & cache (ClawPanel-style) — fast settings, tool toggles.
 */
const LocalPrefs = (() => {
  const CONFIG_CACHE = 'openpilot-ai-config-cache';
  const CONFIG_DRAFT = 'openpilot-ai-config-draft';
  const MODELS_CACHE = 'openpilot-ai-models-cache';
  const TOOL_PREFS = 'openpilot-ai-tool-prefs';
  const TOOL_DRIVING_PREFS = 'openpilot-ai-tool-driving-prefs';
  const MODEL_PROFILE = 'openpilot-ai-model-profile';

  let _serverToolDefaults = null;

  function readJson(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      if (raw) return JSON.parse(raw);
    } catch {}
    return fallback;
  }

  function writeJson(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {}
  }

  function setServerToolDefaults(toolMeta) {
    if (!toolMeta || typeof toolMeta !== 'object') return;
    _serverToolDefaults = toolMeta;
  }

  function buildDefaultTools() {
    const out = {};
    const meta = _serverToolDefaults || {};
    for (const [name, info] of Object.entries(meta)) {
      out[name] = !!info.default_enabled;
    }
    if (!Object.keys(out).length) {
      return {
        get_vehicle_state: true,
        read_params: true,
        list_dp_settings: true,
        run_shell: true,
      };
    }
    return out;
  }

  function buildDefaultDrivingTools() {
    const out = {};
    const meta = _serverToolDefaults || {};
    for (const [name, info] of Object.entries(meta)) {
      if (info.driving) out[name] = true;
    }
    return out;
  }

  function getConfigCache() {
    return readJson(CONFIG_CACHE, null);
  }

  function setConfigCache(config) {
    if (config) writeJson(CONFIG_CACHE, { ...config, cachedAt: Date.now() });
  }

  function getConfigDraft() {
    return readJson(CONFIG_DRAFT, null);
  }

  function setConfigDraft(draft) {
    if (draft) writeJson(CONFIG_DRAFT, { ...draft, draftAt: Date.now() });
  }

  function clearConfigDraft() {
    try { localStorage.removeItem(CONFIG_DRAFT); } catch {}
  }

  function mergeDraftOntoServer(server, draft) {
    const base = { ...(server || {}) };
    if (!draft) return base;
    for (const [k, v] of Object.entries(draft)) {
      if (k.startsWith('_') || k === 'cachedAt' || k === 'draftAt') continue;
      if (v === undefined || v === null) continue;
      if (k === 'apiKey' || k === 'embeddingApiKey' || k === 'webPin') {
        if (v && !String(v).startsWith('•')) base[k] = v;
        continue;
      }
      base[k] = v;
    }
    return base;
  }

  /** @deprecated use mergeDraftOntoServer — server wins; draft only overlays unsaved edits */
  function mergeConfigLayers(server, _cache, draft) {
    return mergeDraftOntoServer(server, draft);
  }

  function getModelsCache(provider) {
    const all = readJson(MODELS_CACHE, {});
    return all[provider] || null;
  }

  function setModelsCache(provider, models) {
    const all = readJson(MODELS_CACHE, {});
    all[provider] = { models, cachedAt: Date.now() };
    writeJson(MODELS_CACHE, all);
  }

  function getToolPrefs() {
    const defaults = buildDefaultTools();
    return { ...defaults, ...readJson(TOOL_PREFS, {}) };
  }

  function getToolDrivingPrefs() {
    const defaults = buildDefaultDrivingTools();
    return { ...defaults, ...readJson(TOOL_DRIVING_PREFS, {}) };
  }

  function setToolPrefs(prefs) {
    writeJson(TOOL_PREFS, { ...buildDefaultTools(), ...prefs });
  }

  function setToolDrivingPrefs(prefs) {
    writeJson(TOOL_DRIVING_PREFS, { ...buildDefaultDrivingTools(), ...prefs });
  }

  function getMaxToolRounds() {
    return 'infinite';
  }

  function setMaxToolRounds(_value) {
    /* fixed ∞ — no UI */
  }

  function getModelProfile() {
    const v = localStorage.getItem(MODEL_PROFILE);
    return v === 'fast' || v === 'deep' ? v : 'auto';
  }

  function setModelProfile(profile) {
    const v = profile === 'fast' || profile === 'deep' ? profile : 'auto';
    try {
      localStorage.setItem(MODEL_PROFILE, v);
    } catch {}
    return v;
  }

  return {
    getConfigCache,
    setConfigCache,
    getConfigDraft,
    setConfigDraft,
    clearConfigDraft,
    mergeDraftOntoServer,
    mergeConfigLayers,
    getModelsCache,
    setModelsCache,
    setServerToolDefaults,
    getToolPrefs,
    getToolDrivingPrefs,
    setToolPrefs,
    setToolDrivingPrefs,
    getMaxToolRounds,
    setMaxToolRounds,
    getModelProfile,
    setModelProfile,
    buildDefaultTools,
  };
})();
