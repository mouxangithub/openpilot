/**
 * Model failover chain editor — full combobox per fallback row.
 */
const FallbackModels = (() => {
  let root = null;
  let rows = [];
  let providers = [];
  let getProvider = () => 'opencode-zen';
  let getProviderLabel = (id) => id;
  let translate = (_key, fallback) => fallback ?? '';

  function t(key, fallback) {
    return translate(key, fallback);
  }

  function defaultRow() {
    return { provider: '', model: '', apiKey: '', baseUrl: '', label: '' };
  }

  function resolveProvider(row) {
    return (row?.provider || '').trim() || getProvider();
  }

  function usesMainProvider(row) {
    return !(row?.provider || '').trim();
  }

  function mainProviderOptionLabel() {
    const id = getProvider();
    const label = getProviderLabel(id);
    return label && label !== id ? `同主模型 · ${label}` : `同主模型 · ${id}`;
  }

  function mount(container, opts = {}) {
    root = typeof container === 'string' ? document.querySelector(container) : container;
    if (!root) return;
    getProvider = opts.getProvider || getProvider;
    getProviderLabel = opts.getProviderLabel || getProviderLabel;
    translate = opts.t || translate;
    providers = opts.providers || [];
    root.innerHTML = `
      <div class="fallback-models-head">
        <p class="field-hint" id="fallbackHint">${escapeHtml(t('fallbackHint', '主模型失败时按顺序尝试以下备用模型（仅在尚未输出内容时切换）。'))}</p>
        <button type="button" class="btn small ghost" id="fallbackAddBtn">${escapeHtml(t('fallbackAddBtn', '+ 添加备用模型'))}</button>
      </div>
      <div class="fallback-models-list" id="fallbackList"></div>
      <p class="fallback-models-empty hidden" id="fallbackEmpty">${escapeHtml(t('fallbackEmpty', '暂无备用模型，点击上方按钮添加。'))}</p>
    `;
    root.querySelector('#fallbackAddBtn')?.addEventListener('click', () => {
      rows.push({ ...defaultRow(), _combo: null });
      render();
      persistChange();
    });
    setRows(opts.initial || []);
  }

  function providerOptions(selected) {
    const followMain = !(selected || '').trim();
    const opts = providers.length ? providers : ['opencode-zen', 'openrouter', 'siliconflow', 'bigmodel'];
    let html = `<option value=""${followMain ? ' selected' : ''}>${escapeAttr(mainProviderOptionLabel())}</option>`;
    html += opts.map((p) => {
      const id = typeof p === 'string' ? p : (p.id || p);
      const label = getProviderLabel(id);
      const text = label && label !== id ? `${label} (${id})` : id;
      return `<option value="${escapeAttr(id)}"${id === selected ? ' selected' : ''}>${escapeAttr(text)}</option>`;
    }).join('');
    return html;
  }

  function syncRowCredLayout(el, row) {
    const advancedDetails = el.querySelector('.fallback-row-advanced');
    const summary = el.querySelector('.fallback-row-advanced-summary');
    const slotPrimary = el.querySelector('.fallback-cred-slot-primary');
    const slotAdvKey = el.querySelector('.fallback-cred-slot-adv-key');
    const slotAdvUrl = el.querySelector('.fallback-cred-slot-adv-url');
    const apiKeyField = el.querySelector('.fallback-apikey-field');
    const baseUrlField = el.querySelector('.fallback-baseurl-field');
    const apiKeyInput = el.querySelector('.fallback-apikey');
    const baseUrlInput = el.querySelector('.fallback-baseurl');
    if (!apiKeyField || !baseUrlField || !slotPrimary || !slotAdvKey || !slotAdvUrl) return;

    const mainProvider = usesMainProvider(row);
    const provider = resolveProvider(row);
    const isCustom = provider === 'custom';
    const showApiPrimary = !mainProvider;
    const showApiAdvanced = mainProvider;
    const showUrlPrimary = isCustom;
    const showUrlAdvanced = !isCustom;

    slotPrimary.innerHTML = '';
    slotAdvKey.innerHTML = '';
    slotAdvUrl.innerHTML = '';

    if (showApiPrimary) slotPrimary.appendChild(apiKeyField);
    else if (showApiAdvanced) slotAdvKey.appendChild(apiKeyField);
    apiKeyField.classList.toggle('hidden', !showApiPrimary && !showApiAdvanced);

    if (showUrlPrimary) slotPrimary.appendChild(baseUrlField);
    else if (showUrlAdvanced) slotAdvUrl.appendChild(baseUrlField);
    baseUrlField.classList.toggle('hidden', !showUrlPrimary && !showUrlAdvanced);

    if (apiKeyInput) {
      apiKeyInput.placeholder = mainProvider
        ? t('fallbackKeyMainPh', '留空=使用主 Key')
        : t('fallbackKeyOwnPh', '填写该服务商的 API Key');
    }
    if (baseUrlInput) {
      baseUrlInput.placeholder = isCustom
        ? t('baseUrlPlaceholder', 'https://api.example.com/v1')
        : t('fallbackUrlOptionalPh', '留空=使用服务商默认地址');
    }

    const advParts = [];
    if (showApiAdvanced) advParts.push(t('fallbackAdvKey', 'Key'));
    if (showUrlAdvanced) advParts.push(t('baseUrl', 'Base URL'));
    if (advancedDetails) {
      advancedDetails.classList.toggle('hidden', advParts.length === 0);
      if (summary) {
        summary.textContent = advParts.length === 1
          ? t('fallbackAdvSingle', '高级选项（{item}）').replace('{item}', advParts[0])
          : t('fallbackAdvBoth', '高级选项（Key / Base URL）');
      }
    }
  }

  function render() {
    const list = root?.querySelector('#fallbackList');
    const empty = root?.querySelector('#fallbackEmpty');
    if (!list) return;
    list.innerHTML = '';
    empty?.classList.toggle('hidden', rows.length > 0);
    rows.forEach((row, idx) => {
      const el = document.createElement('div');
      el.className = 'fallback-row';
      el.innerHTML = `
        <div class="fallback-row-head">
          <span class="fallback-row-index">#${idx + 1}</span>
          <button type="button" class="btn small ghost fallback-remove" data-idx="${idx}">${escapeHtml(t('fallbackRemove', '删除'))}</button>
        </div>
        <div class="fallback-row-fields">
          <label class="field fallback-field">
            <span class="field-label">${escapeHtml(t('fallbackLabel', '标签'))}</span>
            <input type="text" class="fallback-label" data-idx="${idx}" placeholder="${escapeAttr(t('fallbackLabelPh', '可选，如：备用 DeepSeek'))}" value="${escapeAttr(row.label || '')}">
          </label>
          <div class="fallback-row-split">
            <label class="field fallback-field">
              <span class="field-label">${escapeHtml(t('provider', '服务商'))}</span>
              <select class="fallback-provider" data-idx="${idx}">${providerOptions(row.provider)}</select>
            </label>
            <label class="field fallback-field fallback-field-model">
              <span class="field-label">${escapeHtml(t('model', '模型'))}</span>
              <div class="fallback-model-host" data-idx="${idx}"></div>
            </label>
          </div>
          <div class="fallback-row-primary-creds">
            <div class="fallback-cred-slot-primary"></div>
          </div>
          <details class="fallback-row-advanced">
            <summary class="fallback-row-advanced-summary">${escapeHtml(t('fallbackAdvBoth', '高级选项（Key / Base URL）'))}</summary>
            <div class="fallback-row-advanced-body">
              <div class="fallback-cred-slot-adv-key"></div>
              <div class="fallback-cred-slot-adv-url"></div>
            </div>
          </details>
          <label class="field fallback-field fallback-apikey-field hidden">
            <span class="field-label">${escapeHtml(t('apiKey', 'API Key'))}</span>
            <input type="password" class="fallback-apikey" data-idx="${idx}" value="${escapeAttr(row.apiKey || '')}" autocomplete="off" spellcheck="false">
          </label>
          <label class="field fallback-field fallback-baseurl-field hidden">
            <span class="field-label">${escapeHtml(t('baseUrl', 'Base URL'))}</span>
            <input type="text" class="fallback-baseurl" data-idx="${idx}" value="${escapeAttr(row.baseUrl || '')}">
          </label>
        </div>
      `;
      list.appendChild(el);
      const host = el.querySelector('.fallback-model-host');
      if (typeof ModelCombobox !== 'undefined' && host) {
        row._combo = ModelCombobox.mount(host, {
          placeholder: 'model-id',
          onChange: () => {
            row.model = row._combo.getValue();
            persistChange();
          },
        });
        row._combo.setValue(row.model || '', { silent: true });
      }
      syncRowCredLayout(el, row);
      const apiKeyInput = el.querySelector('.fallback-apikey');
      if (apiKeyInput && typeof PasswordField !== 'undefined') {
        PasswordField.enhanceInput(apiKeyInput);
      }
      el.querySelector('.fallback-remove')?.addEventListener('click', () => {
        rows.splice(idx, 1);
        render();
        persistChange();
      });
      el.querySelector('.fallback-provider')?.addEventListener('change', (e) => {
        row.provider = e.target.value;
        syncRowCredLayout(el, row);
        persistChange();
      });
      el.querySelector('.fallback-label')?.addEventListener('input', (e) => {
        row.label = e.target.value;
        persistChange();
      });
      el.querySelector('.fallback-apikey')?.addEventListener('input', (e) => {
        row.apiKey = e.target.value;
        persistChange();
      });
      el.querySelector('.fallback-baseurl')?.addEventListener('input', (e) => {
        row.baseUrl = e.target.value;
        persistChange();
      });
    });
  }

  function escapeAttr(s) {
    return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
  }

  function escapeHtml(s) {
    return escapeAttr(s);
  }

  function persistChange() {
    root?.dispatchEvent(new CustomEvent('fallbackchange', { bubbles: true }));
  }

  function refreshMainProviderLabels() {
    root?.querySelectorAll('.fallback-provider option[value=""]').forEach((opt) => {
      opt.textContent = mainProviderOptionLabel();
    });
    root?.querySelectorAll('.fallback-row').forEach((el, idx) => {
      if (rows[idx]) syncRowCredLayout(el, rows[idx]);
    });
  }

  function setRows(items) {
    const main = getProvider();
    rows = (items || []).map((r) => {
      const copy = { ...defaultRow(), ...r, _combo: null };
      if (copy.provider === main) copy.provider = '';
      return copy;
    });
    render();
  }

  function getRows() {
    return rows.map((r) => ({
      provider: resolveProvider(r),
      model: r._combo?.getValue?.()?.trim() || r.model || '',
      apiKey: (r.apiKey || '').trim(),
      baseUrl: (r.baseUrl || '').trim(),
      label: (r.label || '').trim(),
    })).filter((r) => r.model);
  }

  function setProviders(list) {
    providers = list || [];
    render();
  }

  return {
    mount,
    setRows,
    getRows,
    setProviders,
    refreshMainProviderLabels,
  };
})();
