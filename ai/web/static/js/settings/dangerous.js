(function (global) {
  const app = global.SettingsApp = global.SettingsApp || {};
  app.danger = app.danger || {};
  const esc = app.render.esc;
  const AUDIT_KEY = 'sp.settings.audit';

  function depsOrDefault(deps) {
    return {
      api: (deps && deps.api) || global.WebApi?.api || (() => Promise.resolve({ status: 0, data: { ok:false, error:'no api' } })),
      t: (deps && deps.t) || ((k, fb) => fb || k),
      showToast: (deps && deps.showToast) || ((m, ty) => console.log(`[${ty||'info'}] ${m}`)),
      ...deps,
    };
  }
  app.danger.depsOrDefault = depsOrDefault;

  function auditLog() { try { return JSON.parse(global.localStorage.getItem(AUDIT_KEY) || '[]'); } catch { return []; } }
  function appendAudit(entry) {
    const log = auditLog();
    entry.ts = new Date().toISOString();
    log.push(entry);
    try { global.localStorage.setItem(AUDIT_KEY, JSON.stringify(log.slice(-200))); } catch {}
    return entry;
  }
  app.danger.appendAudit = appendAudit;
  app.danger.auditLog = auditLog;

  class DangerousAction {
    constructor(cfg) {
      this.id = cfg.id; this.title = cfg.title; this.description = cfg.description;
      this.risk = cfg.risk || 'high'; this.confirmText = cfg.confirmText || cfg.id;
      this.preview = cfg.preview || null;  // async (deps) -> {ok, data}
      this.confirm = cfg.confirm || null;  // async (deps, token) -> {ok, data}
    }
  }
  app.danger.DangerousAction = DangerousAction;

  const ACTIONS = new Map();
  function register(action) { ACTIONS.set(action.id, action); return action; }
  app.danger.register = register;
  app.danger.actions = ACTIONS;

  function openConfirm(action, deps) {
    const d = depsOrDefault(deps);
    const body = document.body;
    let modal = document.getElementById('settingsDangerModal');
    if (!modal) {
      modal = document.createElement('div'); modal.id = 'settingsDangerModal'; modal.className = 'settings-danger-modal';
      modal.innerHTML = `<div class="settings-danger-backdrop" data-da-close></div><div class="settings-danger-panel">
        <header class="settings-danger-head"><h3 data-da-title></h3><button type="button" class="btn icon" data-da-close aria-label="Close">×</button></header>
        <p class="settings-danger-desc" data-da-desc></p>
        <div class="settings-danger-content" data-da-content></div>
        <div class="settings-danger-confirm-row"><label>输入 <code data-da-need></code> 确认</label><input type="text" data-da-typed autocomplete="off"></div>
        <div class="settings-danger-actions"><button type="button" class="btn ghost" data-da-close>取消</button><button type="button" class="btn primary danger" data-da-go disabled>确认执行</button></div>
      </div>`;
      body.appendChild(modal);
      modal.querySelectorAll('[data-da-close]').forEach((b) => b.addEventListener('click', () => hideModal(modal)));
      const need = modal.querySelector('[data-da-need]'); const typed = modal.querySelector('[data-da-typed]');
      typed.addEventListener('input', () => { modal.querySelector('[data-da-go]').disabled = typed.value !== need.textContent; });
    }
    modal.querySelector('[data-da-title]').textContent = action.title;
    modal.querySelector('[data-da-desc]').textContent = action.description;
    modal.querySelector('[data-da-need]').textContent = action.confirmText;
    modal.querySelector('[data-da-typed]').value = '';
    modal.querySelector('[data-da-go]').disabled = true;
    const content = modal.querySelector('[data-da-content]');
    content.innerHTML = '<p class="field-hint">正在生成预览…</p>';
    modal.classList.add('open');
    if (typeof app.setOverlayThreshold === 'function') app.setOverlayThreshold(true);
    const go = modal.querySelector('[data-da-go]');
    go.onclick = run;
    const run = async () => {
      go.disabled = true; go.textContent = '执行中…';
      try {
        let token = null;
        if (action.preview) { const p = await action.preview(d, action); if (!p || p.ok === false) { content.innerHTML = `<p class="field-hint">${esc(p?.error || '预览失败')}</p>`; go.disabled = false; return; } token = p.token || p.pending_id || null; content.innerHTML = app.danger.previewHtml(p.data); }
        const r = await action.confirm(d, token);
        if (r && r.ok === false) { content.innerHTML = `<p class="field-hint">${esc(r.error || '执行失败')}</p>`; go.disabled = false; return; }
        appendAudit({ id: action.id, action: action.title, status: 'executed', data: (r && r.data) || null, token: token || null });
        content.innerHTML = `<div class="settings-danger-result">${esc(r?.message || '执行完成')}</div>`;
        d.showToast(r?.message || d.t('settings.dangerDone', '危险操作已执行并记录审计'), 'success');
        setTimeout(() => hideModal(modal), 900);
      } catch (e) { content.innerHTML = `<p class="field-hint">${esc(String(e && e.message || e))}</p>`; } finally { go.textContent = '确认执行'; }
    };
    go.addEventListener('click', run);
    return modal;
  }
  app.danger.openConfirm = openConfirm;
  app.danger.previewHtml = (data) => `<pre class="settings-preview">${esc(typeof data === 'string' ? data : JSON.stringify(data, null, 2))}</pre>`;

  function hideModal(modal) { modal.classList.remove('open'); if (typeof app.setOverlayThreshold === 'function') app.setOverlayThreshold(false); }
  app.danger.hideModal = hideModal;

  function openAudit(deps) {
    const d = depsOrDefault(deps);
    const body = document.body;
    let modal = document.getElementById('settingsAuditModal');
    if (!modal) {
      modal = document.createElement('div'); modal.id = 'settingsAuditModal'; modal.className = 'settings-danger-modal';
      modal.innerHTML = `<div class="settings-danger-backdrop" data-audit-close></div><div class="settings-danger-panel">
        <header class="settings-danger-head"><h3>危险操作审计</h3><button type="button" class="btn icon" data-audit-close aria-label="Close">×</button></header>
        <div class="settings-audit-list" data-audit-list></div></div>`;
      body.appendChild(modal);
      modal.querySelectorAll('[data-audit-close]').forEach((b) => b.addEventListener('click', () => hideModal(modal)));
    }
    const list = modal.querySelector('[data-audit-list]');
    const log = auditLog();
    list.innerHTML = log.length ? log.slice().reverse().map((e) => `<div class="settings-audit-item"><span class="settings-audit-time">${esc(e.ts || '')}</span> <code>${esc(e.action || e.id || '')}</code> <span class="settings-audit-status">${esc(e.status || '')}</span></div>`).join('') : '<p class="field-hint">暂无审计记录</p>';
    modal.classList.add('open');
    if (typeof app.setOverlayThreshold === 'function') app.setOverlayThreshold(true);
  }
  app.danger.openAudit = openAudit;

  // ---- Registered sample dangerous actions (use existing endpoints) ----
  register(new DangerousAction({
    id: 'reset_config', title: '重置 AI 配置', description: '将所有 AI 配置恢复为默认值。此操作不可撤销，将覆盖当前模型、生成参数与进化设置。', risk: 'high', confirmText: 'reset-config',
    preview: async (d) => ({ ok: true, data: { warning: '将写入默认配置', method: 'POST /api/ai/config' } }),
    confirm: async (d) => {
      const defaults = { temperature: 0.7, topP: 1, maxTokens: 2048, compactionEnabled: true, evolutionEnabled: true };
      return d.api('POST', '/api/ai/config', defaults);
    },
  }));
  register(new DangerousAction({
    id: 'clear_scheduler', title: '清空全部定时任务', description: '移除所有已配置的定时任务。可通过再次添加恢复。', risk: 'medium', confirmText: 'clear-sched',
    preview: async (d) => { const { data } = await d.api('GET', '/api/ai/scheduler'); return { ok: true, data: { count: (data.tasks || []).length } }; },
    confirm: async (d) => { const { data } = await d.api('GET', '/api/ai/scheduler'); let removed = 0, err = null; for (const task of (data.tasks || [])) { const r = await d.api('POST', '/api/ai/scheduler', { operation: 'remove', task_id: task.id }); (r.data && (r.data.removed || r.data.ok)) ? removed++ : (err = r.data && r.data.error); } return { ok: true, message: `已移除 ${removed} 个任务${err ? `（${err}）` : ''}` }; },
  }));
})(window);