(function (global) {
  const app = global.SettingsApp = global.SettingsApp || {};
  app.save = app.save || {};
  const esc = app.render.esc;
  const state = {
    snapshots: new Map(),   // cardId -> { revision, values }
    dirty: new Set(),
    saving: new Set(),
  };

  function depsOrDefault(deps) {
    return {
      api: (deps && deps.api) || global.WebApi?.api || (() => Promise.resolve({ status: 0, data: { ok:false, error:'no api' } })),
      t: (deps && deps.t) || ((k, fb) => fb || k),
      showToast: (deps && deps.showToast) || ((m, ty) => console.log(`[${ty||'info'}] ${m}`)),
      onConflict: (deps && deps.onConflict) || (() => {}),
      ...deps,
    };
  }
  app.save.depsOrDefault = depsOrDefault;

  function snapshotCard(card, values) {
    state.snapshots.set(card.id, { revision: 0, values: { ...values } });
  }
  app.save.snapshotCard = snapshotCard;

  function markDirty(card) { state.dirty.add(card.id); }
  app.save.markDirty = markDirty;
  function isDirty(card) { return state.dirty.has(card.id); }
  app.save.isDirty = isDirty;

  function renderSavebar(cardEl, card, deps) {
    const bar = cardEl.querySelector(`[data-savebar="${CSS.escape ? CSS.escape(card.id) : card.id}"]`);
    if (!bar) return;
    if (!isDirty(card)) { bar.innerHTML = ''; return; }
    bar.innerHTML = `<button type="button" class="btn small primary" data-save-card="${esc(card.id)}">保存</button>
      <button type="button" class="btn small ghost" data-discard-card="${esc(card.id)}">放弃</button>
      <button type="button" class="btn small ghost" data-restore-card="${esc(card.id)}">恢复默认</button>`;
    bar.querySelector('[data-save-card]').addEventListener('click', () => saveCard(cardEl, card, deps));
    bar.querySelector('[data-discard-card]').addEventListener('click', () => discard(cardEl, card, deps));
    bar.querySelector('[data-restore-card]').addEventListener('click', () => restoreDefault(cardEl, card, deps));
  }
  app.save.renderSavebar = renderSavebar;

  function collectValues(cardEl, card) { return app.render.collectCardValues(cardEl, card); }

  async function saveCard(cardEl, card, deps) {
    const d = depsOrDefault(deps);
    if (state.saving.has(card.id)) return;
    const snap = state.snapshots.get(card.id) || { revision: 0, values: {} };
    state.saving.add(card.id);
    renderSavingState(cardEl, card, true);
    const values = collectValues(cardEl, card);
    const body = { ...values, revision: snap.revision };
    try {
      const res = await d.api('POST', '/api/ai/config', body);
      const data = res.data || {};
      if (res.status === 409 || data.error_code === 'ERR_CONFIG_STALE' || data.error_code === 'ERR_STALE_REVISION') {
        d.showToast(d.t('settings.conflict', '配置已变更，请刷新后重试'), 'error');
        d.onConflict(card, values);
        return { ok: false, conflict: true };
      }
      if (!data.ok) { d.showToast(data.error || data.message || d.t('settings.saveFail', '保存失败'), 'error'); return { ok:false }; }
      state.snapshots.set(card.id, { revision: (data.revision ?? snap.revision + 1), values: { ...values } });
      state.dirty.delete(card.id);
      renderSavebar(cardEl, card, deps);
      d.showToast(d.t('settings.saved', '已保存'), 'success');
      return { ok: true, data };
    } finally {
      state.saving.delete(card.id);
      renderSavingState(cardEl, card, false);
    }
  }
  app.save.saveCard = saveCard;

  function discard(cardEl, card, deps) {
    const d = depsOrDefault(deps);
    const snap = state.snapshots.get(card.id);
    state.dirty.delete(card.id);
    if (snap) app.render.applyValuesToCard(cardEl, snap.values, card);
    renderSavebar(cardEl, card, deps);
  }
  app.save.discard = discard;

  function restoreDefault(cardEl, card, deps) {
    const d = depsOrDefault(deps);
    const defaults = {}; (card.fields||[]).forEach((fld) => { defaults[fld.key] = fld.default === undefined ? (fld.type==='boolean'?false:(fld.type==='number'?0:'')) : fld.default; });
    app.render.clearCardValues(cardEl, defaults, card);
    markDirty(card);
    renderSavebar(cardEl, card, deps);
    d.showToast(d.t('settings.defaultsApplied', '已填入默认值，点击保存生效'), 'info');
  }
  app.save.restoreDefault = restoreDefault;

  function renderSavingState(cardEl, _card, saving) {
    const bar = cardEl.querySelector('.settings-card-savebar');
    if (bar && saving) bar.innerHTML = '<span class="field-hint">保存中…</span>';
  }
})(window);