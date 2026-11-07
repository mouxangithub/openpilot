(function (global) {
  const app = global.SettingsApp = global.SettingsApp || {};
  const R = app.registry;
  const esc = app.render.esc;
  const VM_KEY = 'settings.viewmode';

  app.feature = {
    isEnabled() {
      if (new URLSearchParams(global.location.search).get('settings') === 'new') return true;
      try { return global.localStorage.getItem(VM_KEY) === 'new'; } catch { return false; }
    },
    setEnabled(on) { try { global.localStorage.setItem(VM_KEY, on ? 'new' : 'legacy'); } catch {} },
  };

  app.setOverlayThreshold = function setOverlayThreshold(on) {
    const root = document.getElementById('settingsNewRoot');
    if (root) root.style.pointerEvents = on ? 'none' : '';
  };

  function defaultDeps(deps) {
    return {
      api: (deps && deps.api) || global.WebApi?.api || (() => Promise.resolve({ status: 0, data: { ok:false, error:'no api' } })),
      t: (deps && deps.t) || ((k, fb) => fb || k),
      showToast: (deps && deps.showToast) || ((m, ty) => console.log(`[${ty||'info'}] ${m}`)),
      getConfig: (deps && deps.getConfig) || (() => ({})),
      ...deps,
    };
  }

  function ensureRoot(deps) {
    let root = document.getElementById('settingsNewRoot');
    if (root) return root;
    root = document.createElement('div');
    root.id = 'settingsNewRoot';
    root.className = 'settings-new-root';
    root.innerHTML = `
      <div class="settings-new-toolbar">
        <div class="settings-search">
          <input type="text" class="settings-search-input" data-search placeholder="搜索设置…（label/key/说明）">
          <div class="settings-search-results" data-results hidden></div>
        </div>
        <button type="button" class="btn small ghost" data-viewtoggle title="切换新版/经典视图">切换</button>
        <button type="button" class="btn small ghost" data-audit title="危险操作审计">审计</button>
      </div>
      <div class="settings-tabs-scroll"><div class="settings-tabs settings-tabs-new" data-tabs></div></div>
      <div class="settings-body settings-body-new" data-body></div>`;
    const legacyTabs = document.querySelector('#settingsSidebar .settings-tabs-scroll');
    const legacyBody = document.querySelector('#settingsSidebar .settings-body');
    if (legacyTabs && legacyTabs.parentNode) legacyTabs.parentNode.insertBefore(root, legacyTabs.nextSibling);
    else document.querySelector('#settingsSidebar')?.appendChild(root);
    // view toggle
    root.querySelector('[data-viewtoggle]').addEventListener('click', () => {
      app.feature.setEnabled(false);
      applyViewMode(deps, false);
      deps.showToast(deps.t('settings.legacy', '已切回经典视图'), 'info');
    });
    root.querySelector('[data-audit]').addEventListener('click', () => app.danger.openAudit(deps));
    // search
    const input = root.querySelector('[data-search]');
    const results = root.querySelector('[data-results]');
    input.addEventListener('input', () => {
      const q = input.value;
      if (!q.trim()) { results.hidden = true; results.innerHTML = ''; return; }
      app.search.renderResults(app.search.search(q), results, {
        t: deps.t,
        onPick: (r) => { results.hidden = true; input.value = ''; app.open(r.domain.id, { highlightField: r.field }); },
      });
      results.hidden = false;
    });
    input.addEventListener('focus', () => { if (input.value.trim()) results.hidden = false; });
    document.addEventListener('click', (e) => { if (!root.contains(e.target)) results.hidden = true; });
    return root;
  }

  function buildTabs(deps) {
    const root = document.getElementById('settingsNewRoot');
    const tabs = root.querySelector('[data-tabs]');
    const visible = R.all().filter((d) => !d.gated || deps.allowDev === true);
    tabs.innerHTML = visible.map((d) => `<button type="button" class="settings-tab" data-nd="${esc(d.id)}" role="tab">${d.icon || ''} ${esc(d.label)}</button>`).join('');
    tabs.querySelectorAll('[data-nd]').forEach((btn) => btn.addEventListener('click', () => app.open(btn.dataset.nd)));
  }

  function applyViewMode(deps, enabled) {
    const root = document.getElementById('settingsNewRoot');
    if (!root) return;
    root.classList.toggle('is-active', !!enabled);
    const legacyTabs = document.querySelector('#settingsSidebar .settings-tabs-scroll');
    const legacyBody = document.querySelector('#settingsSidebar .settings-body');
    if (legacyTabs) legacyTabs.style.display = enabled ? 'none' : '';
    if (legacyBody) legacyBody.style.display = enabled ? 'none' : '';
    // view toggle label reflects current state
    const btn = root.querySelector('[data-viewtoggle]');
    if (btn) btn.textContent = enabled ? deps.t('settings.toLegacy', '经典视图') : deps.t('settings.toNew', '新版视图');
  }

  app.open = function open(domainId, opts = {}) {
    const root = document.getElementById('settingsNewRoot');
    if (!root) return;
    const domain = R.get(domainId) || R.all()[0];
    if (!domain) return;
    root.querySelectorAll('[data-nd]').forEach((b) => b.classList.toggle('active', b.dataset.nd === domain.id));
    const body = root.querySelector('[data-body]');
    body.dataset.activeDomain = domain.id;
    if (domain.standalone) {
      body.innerHTML = `<p class="settings-pane-lead">${esc(domain.desc)}</p>` + app.schedulerView.html();
      app.schedulerView.load(body, app._deps);
      return;
    }
    app.render.renderDomain(domain, body, {
      ...app._deps,
      onDirty: (dom, card) => { app.save.markDirty(card); const cardEl = body.querySelector(`[data-card="${card.id}"]`); if (cardEl) app.save.renderSavebar(cardEl, card, app._deps); },
    });
    // prefill from config
    const cfg = (app._deps.getConfig && app._deps.getConfig()) || {};
    (domain.cards || []).forEach((card) => {
      const cardEl = body.querySelector(`[data-card="${card.id}"]`);
      if (!cardEl) return;
      if (card.kind === 'action') bindActionCard(domain, card, cardEl);
      else if (card.kind === 'danger') bindDangerCard(domain, card, cardEl);
      else {
        const values = {}; (card.fields || []).forEach((f) => { values[f.key] = cfg[f.key]; });
        app.render.applyValuesToCard(cardEl, values, card);
        app.save.snapshotCard(card, values);
      }
    });
    if (opts.highlightField) { requestAnimationFrame(() => app.search.highlightMatch(body, opts.highlightField)); }
  };
  app.openDomain = app.open;

  function bindActionCard(domain, card, cardEl) {
    const root = cardEl.querySelector('[data-action-card]');
    if (domain.id === 'data_backup' && card.id === 'backup') {
      root.innerHTML = `<button type="button" class="btn small primary" data-audit>查看审计</button>
        <p class="field-hint">工作区文件、.opbak 备份/恢复仍在经典「平台」面板中管理。新视图将在此提供一站式入口。</p>`;
      root.querySelector('[data-audit]').addEventListener('click', () => app.danger.openAudit(app._deps));
    } else if (domain.id === 'dev_diagnostics' && card.id === 'diagnostics') {
      root.innerHTML = `<button type="button" class="btn small primary" data-run>运行启动诊断</button><div data-out></div>`;
      root.querySelector('[data-run]').addEventListener('click', async () => {
        const out = root.querySelector('[data-out]');
        out.innerHTML = '<span class="field-hint">诊断中…</span>';
        try { const { data } = await app._deps.api('GET', '/api/ai/config/diagnose'); out.innerHTML = `<pre class="settings-preview">${esc(JSON.stringify(data, null, 2))}</pre>`; }
        catch (e) { out.innerHTML = `<p class="field-hint">诊断端点不可用：${esc(String(e && e.message || e))}</p>`; }
      });
    } else {
      root.innerHTML = `<p class="field-hint">该操作入口将在后端接入后启用。</p>`;
    }
  }

  function bindDangerCard(domain, card, cardEl) {
    const root = cardEl.querySelector('[data-danger-card]');
    const actions = Array.from(app.danger.actions.values());
    root.innerHTML = actions.map((a) => `<div class="settings-danger-row"><div><b>${esc(a.title)}</b><p class="settings-field-desc">${esc(a.description)}</p></div><button type="button" class="btn small danger" data-danger-run="${esc(a.id)}">执行</button></div>`).join('') || '<p class="field-hint">暂无危险操作</p>';
    root.querySelectorAll('[data-danger-run]').forEach((btn) => btn.addEventListener('click', () => {
      const a = app.danger.actions.get(btn.dataset.dangerRun);
      if (a) app.danger.openConfirm(a, app._deps);
    }));
  }

  app.mount = function mount(deps) {
    app._deps = defaultDeps(deps);
    app.schema.registerDefault();
    const root = ensureRoot(app._deps);
    buildTabs(app._deps);
    const enabled = app.feature.isEnabled();
    applyViewMode(app._deps, enabled);
    if (enabled) app.open(R.all()[0].id);
    return { root, enabled };
  };

  app.openTab = function openTab(name) {
    app.schema.registerDefault();
    if (R.get(name)) { app.mount({ ...app._deps }); app.feature.setEnabled(true); applyViewMode(app._deps, true); app.open(name); }
  };
})(window);