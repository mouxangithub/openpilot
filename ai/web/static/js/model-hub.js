/**
 * ClawPanel-style model hub: provider accounts → model pool → primary + failover chain.
 */
const ModelHub = (() => {
  const OPTIONAL_BASE_URL = new Set(['qwen', 'minimax', 'mimo', 'bigmodel']);

  let root = null;
  let hub = { version: 2, accounts: [], primary: null, fallbacks: [], embeddingPrimary: null, embeddingFallbacks: [] };
  let providers = [];
  let providerLabels = {};
  let getProviderLabel = (id) => id;
  let translate = (_key, fallback) => fallback ?? '';
  let apiFn = async () => ({ data: {} });
  let onLegacySync = () => {};
  let saveHubFn = null;
  let saveHubTimer = null;
  let saveHubChain = Promise.resolve();

  let accountModal = null;
  let accountModalState = { index: -1, isNew: false };
  let accountModalDraft = null;

  function getRoutes(kind = 'chat') {
    if (kind === 'embedding') return getEmbeddingRoutes();
    const routes = [];
    const p = hub.primary;
    if (p?.accountId) routes.push(p);
    for (const f of hub.fallbacks || []) {
      if (f?.accountId) routes.push(f);
    }
    return routes;
  }

  function getEmbeddingRoutes() {
    const routes = [];
    const p = hub.embeddingPrimary;
    if (p?.accountId) routes.push(p);
    for (const f of hub.embeddingFallbacks || []) {
      if (f?.accountId) routes.push(f);
    }
    return routes;
  }

  function setRoutes(routes, kind = 'chat') {
    if (kind === 'embedding') {
      setEmbeddingRoutes(routes);
      return;
    }
    const list = (routes || []).filter((r) => r?.accountId);
    hub.primary = list[0] ? { ...list[0] } : null;
    hub.fallbacks = list.slice(1).map((r) => ({ ...r }));
  }

  function setEmbeddingRoutes(routes) {
    const list = (routes || []).filter((r) => r?.accountId);
    hub.embeddingPrimary = list[0] ? { ...list[0] } : null;
    hub.embeddingFallbacks = list.slice(1).map((r) => ({ ...r }));
  }

  function t(key, fallback, vars) {
    let text = translate(key, fallback);
    if (vars && typeof text === 'string') {
      Object.entries(vars).forEach(([k, v]) => {
        text = text.replace(`{${k}}`, String(v));
      });
    }
    return text;
  }

  function escapeAttr(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
  }

  function escapeHtml(s) {
    return escapeAttr(s);
  }

  function newAccountId() {
    return `acc_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
  }

  function cloneHub(data) {
    return JSON.parse(JSON.stringify(data || {
      version: 2, accounts: [], primary: null, fallbacks: [],
      embeddingPrimary: null, embeddingFallbacks: [],
    }));
  }

  function accountById(id) {
    return (hub.accounts || []).find((a) => a.id === id);
  }

  function providerOptions(selected) {
    const base = providers.length ? [...providers] : Object.keys(providerLabels);
    if (selected && !base.includes(selected)) base.push(selected);
    return base.map((p) => {
      const id = typeof p === 'string' ? p : (p.id || p);
      const label = getProviderLabel(id);
      const text = label && label !== id ? `${label} (${id})` : id;
      return `<option value="${escapeAttr(id)}"${id === selected ? ' selected' : ''}>${escapeHtml(text)}</option>`;
    }).join('');
  }

  function accountOptions(selected, { enabledOnly = false } = {}) {
    const rows = (hub.accounts || []).filter((a) => !enabledOnly || a.enabled !== false);
    if (!rows.length) {
      return `<option value="">${escapeHtml(t('modelHubNoAccount', '请先添加服务商账户'))}</option>`;
    }
    return rows.map((a) => {
      const prov = getProviderLabel(a.provider);
      const text = a.label ? `${a.label} · ${prov}` : prov;
      return `<option value="${escapeAttr(a.id)}"${a.id === selected ? ' selected' : ''}>${escapeHtml(text)}</option>`;
    }).join('');
  }

  function modelsForAccount(accountId, kind = 'chat') {
    const acc = accountById(accountId);
    if (!acc) return [];
    const pool = kind === 'embedding'
      ? (Array.isArray(acc.embeddingModels) && acc.embeddingModels.length ? acc.embeddingModels : acc.models)
      : acc.models;
    const ids = Array.isArray(pool) ? pool : [];
    return ids.map((id) => ({ id }));
  }

  function defaultModelForAccount(accountId, kind = 'chat') {
    const opts = modelsForAccount(accountId, kind);
    if (opts.length) return opts[0].id;
    if (kind === 'embedding') {
      const ep = hub.embeddingPrimary;
      if (ep?.accountId === accountId && ep.model) return ep.model;
    } else {
      const primary = hub.primary;
      if (primary?.accountId === accountId && primary.model) return primary.model;
    }
    return '';
  }

  function needsBaseUrlPrimary(provider) {
    return provider === 'custom';
  }

  function needsBaseUrlAdvanced(provider) {
    return OPTIONAL_BASE_URL.has(provider);
  }

  function accountDisplayName(acc) {
    if (!acc) return '—';
    const prov = getProviderLabel(acc.provider);
    const label = (acc.label || '').trim();
    if (!label || label === prov || label === acc.provider) return prov;
    return label;
  }

  function modelPreviewText(models, maxShow = 3) {
    const list = (models || []).filter(Boolean);
    if (!list.length) return '';
    const shown = list.slice(0, maxShow);
    let text = shown.join(', ');
    if (list.length > maxShow) text += '…';
    return text;
  }

  function removeModelFromPool(acc, modelId, { renderList = true } = {}) {
    if (!acc || !modelId) return;
    acc.models = (acc.models || []).filter((m) => m !== modelId);
    const routes = getRoutes().filter((r) => !(r.accountId === acc.id && r.model === modelId));
    setRoutes(routes);
    if (renderList) {
      renderAccounts();
      renderRouting();
    }
  }

  function renderModelPoolTags(acc, { inModal = false } = {}) {
    const models = acc.models || [];
    if (!models.length) {
      return `<span class="model-hub-tag muted">${escapeHtml(t('modelHubPoolEmpty', '未拉取，点击「拉取模型」'))}</span>`;
    }
    return models.map((m) => `
      <span class="model-hub-tag${inModal ? ' removable' : ''}" title="${escapeAttr(m)}">
        <span class="model-hub-tag-text">${escapeHtml(m)}</span>
        ${inModal ? `<button type="button" class="model-hub-tag-remove" data-model="${escapeAttr(m)}" aria-label="${escapeAttr(t('modelHubRemoveModel', '移除模型'))}">×</button>` : ''}
      </span>
    `).join('');
  }

  function resolveProviderUsageLabel(providerId) {
    const pid = String(providerId || '').trim();
    if (!pid) return '—';
    const matches = (hub.accounts || []).filter((a) => a.provider === pid);
    if (matches.length === 1) return accountDisplayName(matches[0]);
    if (matches.length > 1) {
      return matches.map((a) => accountDisplayName(a)).join(' · ');
    }
    return getProviderLabel(pid) || pid;
  }

  function accountLabel(accountId) {
    return accountDisplayName(accountById(accountId));
  }

  function routeCardParts(row) {
    if (!row?.accountId || !row?.model) return null;
    const acc = accountById(row.accountId);
    const badges = [];
    if (row.contextWindow > 0) badges.push(`${row.contextWindow} ctx`);
    if (row.maxTokens > 0) badges.push(`max ${row.maxTokens}`);
    if (row.label) badges.push(row.label);
    if (isThinkingModel(row.model)) {
      badges.push(row.thinkingEnabled === false
        ? t('modelHubThinkingOff', '直出')
        : t('modelHubThinkingOn', '思考'));
    }
    return {
      model: row.model,
      provider: accountDisplayName(acc),
      badges,
    };
  }

  function routeCardHtml(row) {
    const parts = routeCardParts(row);
    if (!parts) {
      return `<span class="mh-route-empty">${escapeHtml(t('modelHubRouteUnset', '未配置'))}</span>`;
    }
    const badges = parts.badges.length
      ? `<div class="mh-route-badges">${parts.badges.map((b) => `<span class="mh-pill">${escapeHtml(b)}</span>`).join('')}</div>`
      : '';
    return `
      <div class="mh-route-text">
        <div class="mh-route-model" title="${escapeAttr(parts.model)}">${escapeHtml(parts.model)}</div>
        <div class="mh-route-provider">${escapeHtml(parts.provider)}</div>
      </div>
      ${badges}
    `;
  }

  function buildOnboardingHub({
    provider,
    apiKey = '',
    model = '',
    baseUrl = '',
    models = [],
    label = '',
    embeddingSeparate = false,
    embeddingProvider = '',
    embeddingApiKey = '',
    embeddingBaseUrl = '',
    embeddingModel = '',
    embeddingDefaults = {},
  }) {
    const chatId = newAccountId();
    const modelList = models.length ? [...models] : (model ? [model] : []);
    if (model && !modelList.includes(model)) modelList.unshift(model);
    const accounts = [{
      id: chatId,
      provider,
      label: label || '',
      apiKey,
      baseUrl,
      enabled: true,
      models: modelList,
      embeddingModels: [],
    }];
    const chatProvider = provider;
    const embModel = (embeddingModel || '').trim() || embeddingDefaults[chatProvider] || '';
    const embProv = embeddingSeparate
      ? ((embeddingProvider || '').trim() || 'siliconflow')
      : chatProvider;
    const embKey = embeddingSeparate ? (embeddingApiKey || '').trim() : apiKey;
    const embUrl = embeddingSeparate ? (embeddingBaseUrl || '').trim() : baseUrl;
    let embeddingPrimary = null;
    if (embModel) {
      const sameAccount = embProv === chatProvider && embKey === apiKey && embUrl === baseUrl;
      let embAccId = chatId;
      if (sameAccount) {
        const acc = accounts[0];
        if (!acc.embeddingModels.includes(embModel)) acc.embeddingModels.push(embModel);
      } else {
        embAccId = newAccountId();
        accounts.push({
          id: embAccId,
          provider: embProv,
          label: '',
          apiKey: embKey,
          baseUrl: embUrl,
          enabled: true,
          models: [],
          embeddingModels: [embModel],
        });
      }
      embeddingPrimary = { accountId: embAccId, model: embModel };
    }
    return {
      version: 2,
      accounts,
      primary: model ? { accountId: chatId, model } : null,
      fallbacks: [],
      embeddingPrimary,
      embeddingFallbacks: [],
    };
  }

  function buildSingleProviderHub(opts = {}) {
    return buildOnboardingHub({
      ...opts,
      embeddingSeparate: false,
      embeddingModel: opts.embeddingModel || '',
      embeddingDefaults: opts.embeddingDefaults || {},
    });
  }

  function exportRoute(row) {
    if (!row) return null;
    const item = {
      accountId: row.accountId,
      model: (row.model || '').trim(),
    };
    if (!item.accountId || !item.model) return null;
    const label = (row.label || '').trim();
    if (label) item.label = label;
    const cw = parseInt(row.contextWindow, 10);
    if (cw > 0) item.contextWindow = cw;
    const mt = parseInt(row.maxTokens, 10);
    if (mt > 0) item.maxTokens = mt;
    const temp = row.temperature;
    if (temp !== undefined && temp !== null && String(temp).trim() !== '') {
      const v = parseFloat(temp);
      if (!Number.isNaN(v)) item.temperature = v;
    }
    const topP = row.topP;
    if (topP !== undefined && topP !== null && String(topP).trim() !== '') {
      const v = parseFloat(topP);
      if (!Number.isNaN(v)) item.topP = v;
    }
    return item;
  }

  let routeModal = null;
  let routeModalCombo = null;
  let routeModalState = { index: -1, kind: 'chat' };
  let defaultThinkingEnabled = true;

  const THINKING_MODEL_HINTS = [
    'kimi-k2', 'deepseek-reasoner', 'deepseek-r1', 'deepseek-v4-pro',
    'minimax-m2', 'minimax-m3', 'mimo-v2', 'glm-5', 'glm-4.5', 'o1', 'o3', 'qwq',
  ];

  function isThinkingModel(modelId) {
    const m = String(modelId || '').toLowerCase();
    return THINKING_MODEL_HINTS.some((hint) => m.includes(hint));
  }

  function ensureRouteModal() {
    if (routeModal) return routeModal;
    const el = document.createElement('div');
    el.className = 'modal model-hub-route-modal';
    el.hidden = true;
    el.innerHTML = `
      <div class="modal-backdrop" data-close="1"></div>
      <div class="modal-content" role="dialog" aria-modal="true">
        <header class="modal-header">
          <h2 id="modelHubRouteModalTitle">${escapeHtml(t('modelHubRouteModalTitle', '模型路由配置'))}</h2>
          <button type="button" class="modal-close" data-close="1" aria-label="${escapeAttr(t('close', '关闭'))}">×</button>
        </header>
        <div class="modal-body">
          <label class="field">
            <span class="field-label">${escapeHtml(t('modelHubAccount', '账户'))}</span>
            <select id="modelHubRouteAccount"></select>
          </label>
          <label class="field">
            <span class="field-label">${escapeHtml(t('model', '模型'))}</span>
            <div id="modelHubRouteModelHost" class="model-combobox-host"></div>
          </label>
          <label class="field model-hub-route-label-field">
            <span class="field-label">${escapeHtml(t('fallbackLabel', '标签'))}</span>
            <input type="text" id="modelHubRouteLabel" placeholder="${escapeAttr(t('fallbackLabelPh', '可选'))}">
          </label>
          <div class="model-hub-route-advanced-fields">
          <div class="field-row">
            <label class="field">
              <span class="field-label">${escapeHtml(t('modelHubContextWindow', '上下文窗口'))}</span>
              <input type="number" id="modelHubRouteContext" min="0" max="2000000" step="1024" placeholder="${escapeAttr(t('modelHubUseDefault', '0=默认'))}">
            </label>
            <label class="field">
              <span class="field-label">${escapeHtml(t('maxTokens', 'Max Tokens'))}</span>
              <input type="number" id="modelHubRouteMaxTokens" min="0" max="128000" step="256" placeholder="${escapeAttr(t('modelHubUseDefault', '0=默认'))}">
            </label>
          </div>
          <div class="field-row">
            <label class="field">
              <span class="field-label">${escapeHtml(t('temperature', 'Temperature'))}</span>
              <input type="number" id="modelHubRouteTemp" min="0" max="2" step="0.1" placeholder="${escapeAttr(t('modelHubUseDefault', '默认'))}">
            </label>
            <label class="field">
              <span class="field-label">${escapeHtml(t('topP', 'Top P'))}</span>
              <input type="number" id="modelHubRouteTopP" min="0" max="1" step="0.05" placeholder="${escapeAttr(t('modelHubUseDefault', '默认'))}">
            </label>
          </div>
          <label class="field switch-row model-hub-route-thinking-row" id="modelHubRouteThinkingRow">
            <span class="field-label">${escapeHtml(t('thinking', '思考模式'))}</span>
            <label class="switch">
              <input type="checkbox" id="modelHubRouteThinking" checked>
              <span class="slider"></span>
            </label>
          </label>
          <p class="field-hint model-hub-route-thinking-hint" id="modelHubRouteThinkingHint">${escapeHtml(t('modelHubThinkingHint', '思考模型可开启深度推理；非思考模型可忽略此项。'))}</p>
          </div>
          <p class="field-hint">${escapeHtml(t('modelHubRouteModalHint', '留空或 0 表示使用内置默认值。'))}</p>
          <p class="model-hub-status hidden pending" id="modelHubRouteStatus"></p>
        </div>
        <footer class="modal-footer">
          <button type="button" class="btn ghost" data-close="1">${escapeHtml(t('cancel', '取消'))}</button>
          <button type="button" class="btn primary" id="modelHubRouteSave">${escapeHtml(t('save', '保存'))}</button>
        </footer>
      </div>
    `;
    document.body.appendChild(el);
    el.querySelectorAll('[data-close]').forEach((node) => {
      node.addEventListener('click', () => closeRouteModal());
    });
    el.querySelector('#modelHubRouteSave')?.addEventListener('click', () => saveRouteModal());
    el.querySelector('#modelHubRouteAccount')?.addEventListener('change', (e) => {
      const accountId = e.target.value;
      const kind = routeModalState.kind || 'chat';
      if (routeModalCombo) {
        routeModalCombo.setOptions(modelsForAccount(accountId, kind));
        routeModalCombo.setValue(defaultModelForAccount(accountId, kind), { silent: true });
      }
      syncRouteModalThinkingVisibility();
    });
    el.querySelector('#modelHubRouteThinking')?.addEventListener('change', syncRouteModalThinkingVisibility);
    routeModal = el;
    return el;
  }

  function syncRouteModalThinkingVisibility() {
    if (!routeModal) return;
    const model = routeModalCombo?.getValue?.() || '';
    const row = routeModal.querySelector('#modelHubRouteThinkingRow');
    const hint = routeModal.querySelector('#modelHubRouteThinkingHint');
    const thinking = isThinkingModel(model);
    row?.classList.toggle('is-thinking-model', thinking);
    if (hint) {
      hint.textContent = thinking
        ? t('modelHubThinkingHintOn', '该模型支持思考模式，关闭后将直出回答。')
        : t('modelHubThinkingHint', '思考模型可开启深度推理；非思考模型可忽略此项。');
    }
  }

  function openRouteModal(opts = {}) {
    ensureRouteModal();
    const kind = opts.kind === 'embedding' ? 'embedding' : 'chat';
    routeModalState = { index: opts.index ?? -1, kind };
    const routes = getRoutes(kind);
    const idx = routeModalState.index;
    const row = idx >= 0 ? { ...routes[idx] } : {
      accountId: hub.accounts?.[0]?.id || '',
      model: '',
      label: '',
    };

    routeModal.querySelector('#modelHubRouteModalTitle').textContent = idx >= 0
      ? (kind === 'embedding' ? t('modelHubEditEmbedRoute', '编辑 Embedding') : t('modelHubEditRoute', '编辑模型'))
      : (kind === 'embedding' ? t('modelHubAddEmbedRoute', '添加 Embedding') : t('modelHubAddRoute', '添加模型'));

    const isEmbed = kind === 'embedding';
    routeModal.querySelector('.model-hub-route-advanced-fields')?.classList.toggle('hidden', isEmbed);
    routeModal.querySelector('.model-hub-route-thinking-row')?.classList.toggle('hidden', isEmbed);
    routeModal.querySelector('.model-hub-route-thinking-hint')?.classList.toggle('hidden', isEmbed);

    routeModal.querySelector('.model-hub-route-label-field')?.classList.remove('hidden');

    const accSel = routeModal.querySelector('#modelHubRouteAccount');
    accSel.innerHTML = accountOptions(row.accountId, { enabledOnly: true });
    if (row.accountId) accSel.value = row.accountId;

    const host = routeModal.querySelector('#modelHubRouteModelHost');
    host.innerHTML = '';
    if (typeof ModelCombobox !== 'undefined') {
      routeModalCombo = ModelCombobox.mount(host, {
        placeholder: 'model-id',
        onChange: () => syncRouteModalThinkingVisibility(),
        onInput: () => syncRouteModalThinkingVisibility(),
      });
      routeModalCombo.setOptions(modelsForAccount(row.accountId, kind));
      routeModalCombo.setValue(row.model || '', { silent: true });
    }

    routeModal.querySelector('#modelHubRouteLabel').value = row.label || '';
    routeModal.querySelector('#modelHubRouteContext').value = row.contextWindow > 0 ? row.contextWindow : '';
    routeModal.querySelector('#modelHubRouteMaxTokens').value = row.maxTokens > 0 ? row.maxTokens : '';
    routeModal.querySelector('#modelHubRouteTemp').value = row.temperature ?? '';
    routeModal.querySelector('#modelHubRouteTopP').value = row.topP ?? '';
    const thinkEl = routeModal.querySelector('#modelHubRouteThinking');
    if (thinkEl) {
      thinkEl.checked = row.thinkingEnabled !== undefined
        ? row.thinkingEnabled !== false
        : (isThinkingModel(row.model) ? true : defaultThinkingEnabled);
    }

    routeModal.hidden = false;
    routeModal.classList.add('is-open');
    syncRouteModalThinkingVisibility();
  }

  function closeRouteModal() {
    if (!routeModal) return;
    routeModal.hidden = true;
    routeModal.classList.remove('is-open');
  }

  function readRouteModal() {
    const accountId = routeModal.querySelector('#modelHubRouteAccount')?.value || '';
    const model = routeModalCombo?.getValue?.() || '';
    const row = {
      accountId,
      model: model.trim(),
      label: (routeModal.querySelector('#modelHubRouteLabel')?.value || '').trim(),
    };
    if (routeModalState.kind === 'embedding') {
      return row;
    }
    row.contextWindow = parseInt(routeModal.querySelector('#modelHubRouteContext')?.value, 10) || 0;
    row.maxTokens = parseInt(routeModal.querySelector('#modelHubRouteMaxTokens')?.value, 10) || 0;
    const tempRaw = routeModal.querySelector('#modelHubRouteTemp')?.value;
    if (tempRaw !== '' && tempRaw != null) row.temperature = parseFloat(tempRaw);
    const topPRaw = routeModal.querySelector('#modelHubRouteTopP')?.value;
    if (topPRaw !== '' && topPRaw != null) row.topP = parseFloat(topPRaw);
    row.thinkingEnabled = !!routeModal.querySelector('#modelHubRouteThinking')?.checked;
    return row;
  }

  async function saveRouteModal() {
    const row = readRouteModal();
    if (!row.accountId || !row.model) {
      return;
    }
    const kind = routeModalState.kind || 'chat';
    const routes = getRoutes(kind);
    const idx = routeModalState.index;
    if (idx >= 0) {
      routes[idx] = { ...routes[idx], ...row };
    } else {
      routes.push(row);
    }
    setRoutes(routes, kind);
    const btn = routeModal?.querySelector('#modelHubRouteSave');
    if (btn) btn.disabled = true;
    setRouteModalBusy(true, t('saving', '保存中…'));
    try {
      await commitHubSave();
      closeRouteModal();
      if (kind === 'embedding') renderEmbeddingRouting();
      else renderRouting();
    } catch (e) {
      setRouteModalBusy(false, '');
      showRouteModalStatus(e?.message || t('saveFailed', '保存失败'), 'err');
    } finally {
      setRouteModalBusy(false, '');
      if (btn) btn.disabled = false;
    }
  }

  function showRouteModalStatus(message, kind) {
    const status = routeModal?.querySelector('#modelHubRouteStatus');
    if (!status) return;
    status.classList.remove('hidden', 'ok', 'err', 'pending');
    if (kind) status.classList.add(kind);
    status.textContent = message || '';
  }

  function ensureAccountModal() {
    if (accountModal) return accountModal;
    const el = document.createElement('div');
    el.className = 'modal model-hub-account-modal';
    el.hidden = true;
    el.innerHTML = `
      <div class="modal-backdrop" data-close="1"></div>
      <div class="modal-content" role="dialog" aria-modal="true">
        <header class="modal-header">
          <h2 id="modelHubAccountModalTitle">${escapeHtml(t('modelHubAccountModalTitle', '服务商配置'))}</h2>
          <button type="button" class="modal-close" data-close="1" aria-label="${escapeAttr(t('close', '关闭'))}">×</button>
        </header>
        <div class="modal-body">
          <label class="field switch-row model-hub-account-enabled-row">
            <span class="field-label">${escapeHtml(t('modelHubEnabled', '启用'))}</span>
            <label class="switch">
              <input type="checkbox" id="modelHubAccountEnabled">
              <span class="slider"></span>
            </label>
          </label>
          <label class="field">
            <span class="field-label">${escapeHtml(t('modelHubLabelPh', '备注名'))}</span>
            <input type="text" id="modelHubAccountLabel" placeholder="${escapeAttr(t('modelHubLabelPlaceholder', '可选，如：公司账号'))}">
          </label>
          <label class="field">
            <span class="field-label">${escapeHtml(t('provider', '服务商'))}</span>
            <select id="modelHubAccountProvider"></select>
          </label>
          <label class="field">
            <span class="field-label">${escapeHtml(t('apiKey', 'API Key'))}</span>
            ${PasswordField.wrapInput('modelHubAccountApiKey', 'placeholder="sk-..."')}
          </label>
          <div class="model-hub-url-primary hidden" id="modelHubAccountUrlPrimary">
            <label class="field">
              <span class="field-label">${escapeHtml(t('baseUrl', 'Base URL'))}</span>
              <input type="text" id="modelHubAccountBaseUrl" placeholder="https://api.example.com/v1">
            </label>
          </div>
          <details class="model-hub-advanced hidden" id="modelHubAccountUrlAdvanced">
            <summary>${escapeHtml(t('modelHubAdvanced', '高级（Base URL）'))}</summary>
            <label class="field">
              <span class="field-label">${escapeHtml(t('baseUrl', 'Base URL'))}</span>
              <input type="text" id="modelHubAccountBaseUrlAdv" placeholder="${escapeAttr(t('fallbackUrlOptionalPh', '留空=默认'))}">
            </label>
          </details>
          <div class="model-hub-pool model-hub-account-pool">
            <div class="model-hub-pool-head">
              <span class="field-label">${escapeHtml(t('modelHubPool', '模型池'))}</span>
              <div class="model-hub-account-tool-actions">
                <button type="button" class="btn small ghost" id="modelHubAccountTest">${escapeHtml(t('testConnection', '测试'))}</button>
                <button type="button" class="btn small ghost" id="modelHubAccountFetch">${escapeHtml(t('fetchModels', '拉取模型'))}</button>
              </div>
            </div>
            <div class="model-hub-tags" id="modelHubAccountPoolTags"></div>
          </div>
          <p class="model-hub-status hidden" id="modelHubAccountStatus"></p>
        </div>
        <footer class="modal-footer">
          <button type="button" class="btn ghost" data-close="1">${escapeHtml(t('cancel', '取消'))}</button>
          <button type="button" class="btn primary" id="modelHubAccountSave">${escapeHtml(t('save', '保存'))}</button>
        </footer>
      </div>
    `;
    document.body.appendChild(el);
    el.querySelectorAll('[data-close]').forEach((node) => {
      node.addEventListener('click', () => closeAccountModal());
    });
    el.querySelector('#modelHubAccountSave')?.addEventListener('click', () => saveAccountModal());
    el.querySelector('#modelHubAccountProvider')?.addEventListener('change', () => {
      syncAccountModalDraftFromForm();
      updateAccountModalUrlFields();
    });
    el.querySelector('#modelHubAccountTest')?.addEventListener('click', () => testAccountFromModal());
    el.querySelector('#modelHubAccountFetch')?.addEventListener('click', () => fetchAccountModelsFromModal());
    PasswordField.bind(el);
    accountModal = el;
    return el;
  }

  function updateAccountModalUrlFields() {
    if (!accountModal || !accountModalDraft) return;
    const provider = accountModalDraft.provider || '';
    accountModal.querySelector('#modelHubAccountUrlPrimary')?.classList.toggle('hidden', !needsBaseUrlPrimary(provider));
    accountModal.querySelector('#modelHubAccountUrlAdvanced')?.classList.toggle('hidden', !needsBaseUrlAdvanced(provider));
  }

  function showAccountModalStatus(message, kind) {
    const status = accountModal?.querySelector('#modelHubAccountStatus');
    if (!status) return;
    status.classList.remove('hidden', 'ok', 'err', 'pending');
    if (kind) status.classList.add(kind);
    status.textContent = message || '';
    if (!message) status.classList.add('hidden');
  }

  function setAccountModalBusy(busy, message) {
    if (!accountModal) return;
    accountModal.classList.toggle('is-busy', busy);
    accountModal.querySelectorAll('button, input, select, textarea').forEach((el) => {
      if (el.closest('[data-close]')) {
        el.disabled = busy;
        return;
      }
      if (el.id === 'modelHubAccountSave' || el.id === 'modelHubAccountTest' || el.id === 'modelHubAccountFetch') {
        el.disabled = busy;
      }
    });
    if (busy && message) showAccountModalStatus(message, 'pending');
    else if (!busy) {
      const status = accountModal?.querySelector('#modelHubAccountStatus');
      if (status?.classList.contains('pending')) {
        status.textContent = '';
        status.classList.add('hidden');
        status.classList.remove('pending');
      }
    }
  }

  function setRouteModalBusy(busy, message) {
    if (!routeModal) return;
    routeModal.classList.toggle('is-busy', busy);
    routeModal.querySelectorAll('button, input, select').forEach((el) => {
      el.disabled = busy;
    });
    const status = routeModal.querySelector('#modelHubRouteStatus');
    if (!status) return;
    status.classList.toggle('hidden', !message);
    status.classList.toggle('pending', !!message);
    status.textContent = message || '';
  }

  function renderAccountModalPool() {
    const host = accountModal?.querySelector('#modelHubAccountPoolTags');
    if (!host || !accountModalDraft) return;
    host.innerHTML = renderModelPoolTags(accountModalDraft, { inModal: true });
    host.querySelectorAll('.model-hub-tag-remove').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const modelId = btn.dataset.model;
        if (!modelId) return;
        removeModelFromPool(accountModalDraft, modelId, { renderList: false });
        renderAccountModalPool();
      });
    });
  }

  function syncAccountModalDraftFromForm() {
    if (!accountModal || !accountModalDraft) return;
    accountModalDraft.label = accountModal.querySelector('#modelHubAccountLabel')?.value || '';
    accountModalDraft.provider = accountModal.querySelector('#modelHubAccountProvider')?.value || '';
    accountModalDraft.apiKey = accountModal.querySelector('#modelHubAccountApiKey')?.value || '';
    accountModalDraft.baseUrl = (
      accountModal.querySelector('#modelHubAccountBaseUrl')?.value
      || accountModal.querySelector('#modelHubAccountBaseUrlAdv')?.value
      || ''
    ).trim();
    accountModalDraft.enabled = !!accountModal.querySelector('#modelHubAccountEnabled')?.checked;
  }

  function openAccountModal(opts = {}) {
    ensureAccountModal();
    const accounts = hub.accounts || [];
    const idx = opts.index ?? (opts.accountId ? accounts.findIndex((a) => a.id === opts.accountId) : -1);
    accountModalState = { index: idx, isNew: opts.isNew === true || idx < 0 };
    const source = accountModalState.isNew
      ? {
        id: newAccountId(),
        provider: providers[0] || 'opencode-zen',
        label: '',
        apiKey: '',
        baseUrl: '',
        enabled: true,
        models: [],
      }
      : { ...accounts[idx] };
    accountModalDraft = cloneHub({ accounts: [source] }).accounts[0];

    accountModal.querySelector('#modelHubAccountModalTitle').textContent = accountModalState.isNew
      ? t('modelHubAddAccountModal', '添加服务商')
      : t('modelHubAccountModalTitle', '服务商配置');

    accountModal.querySelector('#modelHubAccountProvider').innerHTML = providerOptions(accountModalDraft.provider);
    accountModal.querySelector('#modelHubAccountLabel').value = accountModalDraft.label || '';
    accountModal.querySelector('#modelHubAccountApiKey').value = accountModalDraft.apiKey || '';
    PasswordField.bind(accountModal);
    accountModal.querySelector('#modelHubAccountBaseUrl').value = accountModalDraft.baseUrl || '';
    accountModal.querySelector('#modelHubAccountBaseUrlAdv').value = accountModalDraft.baseUrl || '';
    accountModal.querySelector('#modelHubAccountEnabled').checked = accountModalDraft.enabled !== false;
    updateAccountModalUrlFields();
    renderAccountModalPool();
    showAccountModalStatus('', null);

    accountModal.hidden = false;
    accountModal.classList.add('is-open');
    accountModal.querySelector('#modelHubAccountLabel')?.focus();
  }

  function closeAccountModal() {
    if (!accountModal) return;
    accountModal.hidden = true;
    accountModal.classList.remove('is-open');
    accountModalDraft = null;
  }

  function accountRequestPayload(acc, { omitAccountId = false } = {}) {
    const payload = {
      provider: acc.provider,
      apiKey: acc.apiKey || '',
      baseUrl: acc.baseUrl || '',
    };
    if (acc.model) payload.model = acc.model;
    if (!omitAccountId && acc.id) payload.accountId = acc.id;
    return payload;
  }

  async function postHubModelsFetch(payload) {
    const endpoints = ['/api/ai/model-hub/fetch-models', '/api/ai/models'];
    let last = { status: 0, data: { ok: false, error: '' } };
    for (const path of endpoints) {
      try {
        const res = await apiFn('POST', path, payload);
        last = res;
        if (res.status !== 404) return res;
        if (res.data?.error && !String(res.data.error).includes('账户不存在')) return res;
      } catch (e) {
        last = { status: 0, data: { ok: false, error: e?.message || 'request failed' } };
      }
    }
    return last;
  }

  async function testAccountFromModal() {
    syncAccountModalDraftFromForm();
    if (!accountModalDraft) return;
    const btn = accountModal.querySelector('#modelHubAccountTest');
    if (btn) btn.disabled = true;
    showAccountModalStatus(t('testing', '测试中…'), null);
    let data;
    try {
      ({ data } = await apiFn('POST', '/api/ai/test', accountRequestPayload(accountModalDraft, { omitAccountId: accountModalState.isNew })));
    } catch (e) {
      showAccountModalStatus(e?.message || t('testFailed', '连接失败'), 'err');
      if (btn) btn.disabled = false;
      return;
    }
    if (btn) btn.disabled = false;
    if (data?.ok) {
      showAccountModalStatus(t('testOk', '连接成功'), 'ok');
    } else {
      showAccountModalStatus(data?.error || t('testFailed', '连接失败'), 'err');
    }
  }

  async function fetchAccountModelsFromModal() {
    syncAccountModalDraftFromForm();
    if (!accountModalDraft) return;
    const btn = accountModal.querySelector('#modelHubAccountFetch');
    if (btn) btn.disabled = true;
    showAccountModalStatus(t('loadingModels', '加载中…'), null);
    let httpStatus = 0;
    let data;
    const payloads = [
      accountRequestPayload(accountModalDraft, { omitAccountId: accountModalState.isNew }),
    ];
    const credOnly = accountRequestPayload(accountModalDraft, { omitAccountId: true });
    if (JSON.stringify(credOnly) !== JSON.stringify(payloads[0])) payloads.push(credOnly);
    try {
      for (const payload of payloads) {
        ({ status: httpStatus, data } = await postHubModelsFetch(payload));
        if (httpStatus !== 404) break;
      }
    } catch (e) {
      if (btn) btn.disabled = false;
      showAccountModalStatus(e?.message || t('modelHubFetchFail', '拉取失败'), 'err');
      return;
    }
    if (btn) btn.disabled = false;
    if (httpStatus === 404) {
      showAccountModalStatus(
        data?.error || t('modelHubApiMissing', '模型 API 未就绪，请重启 op助手 后重试'),
        'err',
      );
      return;
    }
    if (data?.modelHub) {
      const remote = (data.modelHub.accounts || []).find((a) => a.id === accountModalDraft.id);
      if (remote?.models) accountModalDraft.models = [...remote.models];
    } else if (data?.ok && Array.isArray(data.models)) {
      accountModalDraft.models = data.models.map((m) => (typeof m === 'string' ? m : m.id)).filter(Boolean);
    }
    renderAccountModalPool();
    if (data?.ok) {
      showAccountModalStatus(t('modelHubFetchOkPending', '已更新模型池（保存后生效）'), 'ok');
    } else {
      showAccountModalStatus(data?.error || t('modelHubFetchFail', '拉取失败'), 'err');
    }
  }

  async function saveAccountModal() {
    syncAccountModalDraftFromForm();
    if (!accountModalDraft) return;
    const draft = { ...accountModalDraft };
    if (!draft.provider) return;

    const accounts = [...(hub.accounts || [])];
    if (accountModalState.isNew) {
      accounts.push(draft);
    } else if (accountModalState.index >= 0) {
      accounts[accountModalState.index] = draft;
    } else {
      return;
    }
    hub.accounts = accounts;

    const btn = accountModal?.querySelector('#modelHubAccountSave');
    if (btn) btn.disabled = true;
    setAccountModalBusy(true, t('saving', '保存中…'));
    try {
      await commitHubSave();
      closeAccountModal();
      render();
    } catch (e) {
      showAccountModalStatus(e?.message || t('saveFailed', '保存失败'), 'err');
    } finally {
      setAccountModalBusy(false, '');
      if (btn) btn.disabled = false;
    }
  }

  let persistTimer = null;

  async function commitHubSave(opts = {}) {
    if (opts.debounce) {
      clearTimeout(saveHubTimer);
      saveHubTimer = setTimeout(() => commitHubSave({ silent: opts.silent }), opts.debounce);
      return;
    }
    clearTimeout(saveHubTimer);
    clearTimeout(persistTimer);
    onLegacySync(hub);
    if (!saveHubFn) {
      root?.dispatchEvent(new CustomEvent('hubchange', { bubbles: true }));
      return;
    }
    const payload = prepareForSave();
    const run = saveHubChain.then(() => saveHubFn(payload, opts));
    saveHubChain = run.catch(() => {});
    return run;
  }

  function persistChange(opts = {}) {
    return commitHubSave(opts);
  }

  function mount(container, opts = {}) {
    root = typeof container === 'string' ? document.querySelector(container) : container;
    if (!root) return;
    providers = opts.providers || [];
    providerLabels = opts.providerLabels || {};
    getProviderLabel = opts.getProviderLabel || ((id) => providerLabels[id] || id);
    translate = opts.t || translate;
    apiFn = opts.api || apiFn;
    onLegacySync = opts.onLegacySync || onLegacySync;
    saveHubFn = opts.onSaveHub || null;
    defaultThinkingEnabled = opts.defaultThinkingEnabled !== false;

    root.innerHTML = `
      <div class="model-hub">
        <section class="model-hub-section model-hub-section-routing">
          <div class="model-hub-section-head">
            <div>
              <h4 class="model-hub-section-title">${escapeHtml(t('modelHubListTitle', '聊天路由'))}</h4>
              <p class="field-hint">${escapeHtml(t('modelHubListHint', '按顺序调用，第一位为主模型。'))}</p>
            </div>
            <button type="button" class="btn small ghost" id="modelHubAddRoute">${escapeHtml(t('modelHubAddRoute', '+ 添加'))}</button>
          </div>
          <div class="mh-route-list" id="modelHubRouteList"></div>
          <p class="model-hub-empty hidden" id="modelHubRouteEmpty">${escapeHtml(t('modelHubRouteEmpty', '暂无模型，点击添加。'))}</p>
        </section>
        <section class="model-hub-section model-hub-section-embedding">
          <div class="model-hub-section-head">
            <div>
              <h4 class="model-hub-section-title">${escapeHtml(t('modelHubEmbedTitle', 'Embedding 路由'))}</h4>
              <p class="field-hint">${escapeHtml(t('modelHubEmbedHint', '知识库与记忆检索；按顺序尝试，第一位为主模型。'))}</p>
            </div>
            <button type="button" class="btn small ghost" id="modelHubAddEmbedRoute">${escapeHtml(t('modelHubAddEmbedRoute', '+ 添加'))}</button>
          </div>
          <div class="mh-route-list" id="modelHubEmbedRouteList"></div>
          <p class="model-hub-empty hidden" id="modelHubEmbedRouteEmpty">${escapeHtml(t('modelHubEmbedRouteEmpty', '暂无 Embedding 模型'))}</p>
        </section>
        <section class="model-hub-section model-hub-section-accounts">
          <div class="model-hub-section-head">
            <div>
              <h4 class="model-hub-section-title">${escapeHtml(t('modelHubAccountsTitle', '服务商账户'))}</h4>
              <p class="field-hint">${escapeHtml(t('modelHubAccountsHintShort', '点击「配置」编辑账户；保存后拉取模型。'))}</p>
            </div>
            <button type="button" class="btn small ghost" id="modelHubAddAccount">${escapeHtml(t('modelHubAddAccount', '添加'))}</button>
          </div>
          <div class="model-hub-accounts" id="modelHubAccounts"></div>
          <p class="model-hub-empty hidden" id="modelHubAccountsEmpty">${escapeHtml(t('modelHubAccountsEmpty', '暂无账户'))}</p>
        </section>
      </div>
    `;

    root.querySelector('#modelHubAddAccount')?.addEventListener('click', () => {
      const btn = root.querySelector('#modelHubAddAccount');
      if (btn) btn.classList.add('is-loading');
      requestAnimationFrame(() => {
        try {
          openAccountModal({ isNew: true });
        } finally {
          if (btn) btn.classList.remove('is-loading');
        }
      });
    });

    root.querySelector('#modelHubAddRoute')?.addEventListener('click', () => {
      openRouteModal({ index: -1, kind: 'chat' });
    });

    root.querySelector('#modelHubAddEmbedRoute')?.addEventListener('click', () => {
      openRouteModal({ index: -1, kind: 'embedding' });
    });

    if (opts.initial) setHub(opts.initial);
    else render();

    const prefetch = () => {
      ensureAccountModal();
      ensureRouteModal();
    };
    if (typeof requestIdleCallback === 'function') requestIdleCallback(prefetch);
    else setTimeout(prefetch, 120);
  }


  function render() {
    renderAccounts();
    renderRouting();
    renderEmbeddingRouting();
  }

  function accountModelPool(acc) {
    const seen = new Set();
    const out = [];
    for (const m of [...(acc?.models || []), ...(acc?.embeddingModels || [])]) {
      if (!m || seen.has(m)) continue;
      seen.add(m);
      out.push(m);
    }
    return out;
  }

  function renderAccounts() {
    const list = root?.querySelector('#modelHubAccounts');
    const empty = root?.querySelector('#modelHubAccountsEmpty');
    if (!list) return;
    const accounts = hub.accounts || [];
    empty?.classList.toggle('hidden', accounts.length > 0);
    list.innerHTML = '';
    accounts.forEach((acc, idx) => {
      const el = document.createElement('div');
      el.className = `mh-account-item${acc.enabled === false ? ' is-disabled' : ''}`;
      el.dataset.accountId = acc.id;
      const pool = accountModelPool(acc);
      const modelCount = pool.length;
      const hasKey = !!(acc.apiKey || '').trim();
      const preview = modelPreviewText(pool, 3);
      el.innerHTML = `
        <span class="mh-account-dot${hasKey ? ' ok' : ''}" title="${escapeAttr(hasKey ? t('modelHubKeySet', '已配置 Key') : t('modelHubKeyMissing', '未配置 Key'))}"></span>
        <div class="mh-account-body">
          <div class="mh-account-name">${escapeHtml(accountDisplayName(acc))}</div>
          <div class="mh-account-meta">${modelCount ? t('modelHubModelCount', '{n} 个模型', { n: modelCount }) : escapeHtml(t('modelHubPoolEmptyShort', '未拉取'))}${acc.enabled === false ? ` · ${escapeHtml(t('modelHubDisabled', '已禁用'))}` : ''}</div>
          ${preview ? `<div class="mh-account-preview" title="${escapeAttr(pool.join(', '))}">${escapeHtml(preview)}</div>` : ''}
        </div>
        <div class="mh-account-actions">
          <button type="button" class="btn small ghost mh-account-edit" data-idx="${idx}">${escapeHtml(t('modelHubConfigure', '配置'))}</button>
          <button type="button" class="btn small ghost danger mh-account-remove" data-idx="${idx}">${escapeHtml(t('remove', '删除'))}</button>
        </div>
      `;
      list.appendChild(el);

      el.querySelector('.mh-account-edit')?.addEventListener('click', () => {
        openAccountModal({ index: idx });
      });
      el.querySelector('.mh-account-remove')?.addEventListener('click', async () => {
        const removedId = acc.id;
        hub.accounts = accounts.filter((_, i) => i !== idx);
        const routes = getRoutes('chat').filter((r) => r.accountId !== removedId);
        setRoutes(routes, 'chat');
        const embRoutes = getRoutes('embedding').filter((r) => r.accountId !== removedId);
        setRoutes(embRoutes, 'embedding');
        render();
        await commitHubSave();
      });
    });
  }

  function setHub(data, opts = {}) {
    hub = cloneHub(data);
    if (!Array.isArray(hub.accounts)) hub.accounts = [];
    if (!Array.isArray(hub.fallbacks)) hub.fallbacks = [];
    if (!hub.embeddingPrimary && data?.embeddingPrimary) hub.embeddingPrimary = data.embeddingPrimary;
    if (!Array.isArray(hub.embeddingFallbacks)) hub.embeddingFallbacks = [];
    render();
    if (!opts.silent) {
      onLegacySync(hub);
    }
  }

  function renderRouting() {
    renderRouteList('chat', '#modelHubRouteList', '#modelHubRouteEmpty');
  }

  function renderEmbeddingRouting() {
    renderRouteList('embedding', '#modelHubEmbedRouteList', '#modelHubEmbedRouteEmpty');
  }

  function renderRouteList(kind, listSel, emptySel) {
    const list = root?.querySelector(listSel);
    const empty = root?.querySelector(emptySel);
    if (!list) return;
    const routes = getRoutes(kind);
    empty?.classList.toggle('hidden', routes.length > 0);
    list.innerHTML = '';
    routes.forEach((row, idx) => {
      const el = document.createElement('div');
      const isMain = idx === 0;
      el.className = `mh-route-item${isMain ? ' mh-route-primary' : ''}`;
      el.innerHTML = `
        <span class="mh-route-badge${isMain ? ' is-main' : ''}" title="${escapeAttr(isMain ? t('modelHubPrimary', '主模型') : '')}">${isMain ? '★' : idx + 1}</span>
        <div class="mh-route-body">${routeCardHtml(row)}</div>
        <div class="mh-route-actions">
          <button type="button" class="btn small ghost mh-route-edit" data-idx="${idx}">${escapeHtml(t('modelHubConfigure', '配置'))}</button>
          <button type="button" class="btn small ghost mh-route-up" data-idx="${idx}" title="${escapeAttr(t('moveUp', '上移'))}" ${idx === 0 ? 'disabled' : ''}>↑</button>
          <button type="button" class="btn small ghost mh-route-down" data-idx="${idx}" title="${escapeAttr(t('moveDown', '下移'))}" ${idx >= routes.length - 1 ? 'disabled' : ''}>↓</button>
          <button type="button" class="btn small ghost danger mh-route-remove" data-idx="${idx}">×</button>
        </div>
      `;
      list.appendChild(el);

      el.querySelector('.mh-route-edit')?.addEventListener('click', () => {
        openRouteModal({ index: idx, kind });
      });
      el.querySelector('.mh-route-remove')?.addEventListener('click', async () => {
        const next = getRoutes(kind).filter((_, i) => i !== idx);
        setRoutes(next, kind);
        if (kind === 'embedding') renderEmbeddingRouting();
        else renderRouting();
        await commitHubSave();
      });
      el.querySelector('.mh-route-up')?.addEventListener('click', async () => {
        if (idx <= 0) return;
        const r = getRoutes(kind);
        [r[idx - 1], r[idx]] = [r[idx], r[idx - 1]];
        setRoutes(r, kind);
        if (kind === 'embedding') renderEmbeddingRouting();
        else renderRouting();
        await commitHubSave({ silent: true });
      });
      el.querySelector('.mh-route-down')?.addEventListener('click', async () => {
        if (idx >= routes.length - 1) return;
        const r = getRoutes(kind);
        [r[idx], r[idx + 1]] = [r[idx + 1], r[idx]];
        setRoutes(r, kind);
        if (kind === 'embedding') renderEmbeddingRouting();
        else renderRouting();
        await commitHubSave({ silent: true });
      });
    });
  }

  function syncHubFromUi() {
    // Routing is edited via modal; hub object is source of truth after modal save.
    return hub;
  }

  function prepareForSave() {
    clearTimeout(persistTimer);
    persistTimer = null;
    return getHub();
  }

  function getHub() {
    const out = cloneHub(hub);
    out.fallbacks = (out.fallbacks || [])
      .map((row) => exportRoute(row))
      .filter(Boolean);
    if (out.primary) {
      out.primary = exportRoute(out.primary);
    }
    out.embeddingFallbacks = (out.embeddingFallbacks || [])
      .map((row) => exportRoute(row))
      .filter(Boolean);
    if (out.embeddingPrimary) {
      out.embeddingPrimary = exportRoute(out.embeddingPrimary);
    }
    out.version = 2;
    return out;
  }

  function setProviders(list, labels) {
    providers = list || [];
    if (labels) providerLabels = labels;
  }

  function getPrimaryAccount() {
    const id = hub.primary?.accountId;
    return id ? accountById(id) : hub.accounts?.[0];
  }

  return {
    mount,
    setHub,
    getHub,
    prepareForSave,
    syncHubFromUi,
    setProviders,
    getPrimaryAccount,
    buildSingleProviderHub,
    buildOnboardingHub,
    resolveProviderUsageLabel,
    render,
  };
})();
