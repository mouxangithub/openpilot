(function (global) {
  const app = global.SettingsApp = global.SettingsApp || {};
  app.schedulerView = app.schedulerView || {};
  const esc = app.render.esc;

  const ACTION_OPTIONS = [
    { value: 'read_usage', label: '读取用量' },
    { value: 'read_last_log', label: '读取最近日志' },
    { value: 'clear_chat', label: '清空聊天' },
  ];

  function depsOrDefault(deps) {
    return {
      api: (deps && deps.api) || global.WebApi?.api || (() => Promise.resolve({ status: 0, data: { ok:false, error:'no api' } })),
      t: (deps && deps.t) || ((k, fb) => fb || k),
      showToast: (deps && deps.showToast) || ((m, ty) => console.log(`[${ty||'info'}] ${m}`)),
      ...deps,
    };
  }
  app.schedulerView.depsOrDefault = depsOrDefault;

  app.schedulerView.html = function html() {
    return `<div class="settings-sched-view" data-sched-root>
      <div class="settings-sched-form">
        <div class="settings-sched-fields">
          <label class="field"><span class="field-label">名称</span><input type="text" data-sched-name placeholder="如 每天检查日志"></label>
          <label class="field"><span class="field-label">动作</span><select data-sched-action>${ACTION_OPTIONS.map((a)=>`<option value="${a.value}">${esc(a.label)}</option>`).join('')}</select></label>
          <label class="field"><span class="field-label">间隔(分钟)</span><input type="number" data-sched-interval value="60" min="1"></label>
          <label class="field"><span class="field-label">触发</span><select data-sched-trigger><option value="interval">interval</option><option value="daily_at">daily_at</option><option value="on_offroad">on_offroad</option></select></label>
        </div>
        <div class="settings-sched-actions"><button type="button" class="btn small primary" data-sched-add>添加任务</button></div>
      </div>
      <div class="settings-sched-list" data-sched-list></div>
    </div>`;
  };

  async function load(container, deps) {
    const d = depsOrDefault(deps);
    const list = container.querySelector('[data-sched-list]');
    const { data } = await d.api('GET', '/api/ai/scheduler');
    if (!data.ok) { list.innerHTML = `<p class="field-hint">${esc(data.error || '加载失败')}</p>`; return; }
    const tasks = data.tasks || [];
    list.innerHTML = tasks.length ? tasks.map((task) => {
      const trig = task.trigger || 'interval';
      const payload = task.payload || {};
      const trigLabel = trig === 'daily_at' ? `每日 ${payload.hour ?? 8}:${String(payload.minute ?? 0).padStart(2,'0')}` : trig;
      return `<div class="scheduler-item" data-id="${esc(task.id)}">
        <div><b>${esc(task.name || task.action)}</b> · ${esc(trigLabel)} · ${task.interval_minutes || '-'} min</div>
        <div class="field-hint">${esc(task.last_result || '未运行')}</div>
        <div class="settings-sched-item-actions">
          <label class="settings-check-row"><input type="checkbox" data-sched-toggle data-id="${esc(task.id)}" ${task.enabled === false ? '' : 'checked'}> <span>启用</span></label>
          <button type="button" class="btn link sched-del" data-sched-del data-id="${esc(task.id)}">删除</button>
        </div>
      </div>`;
    }).join('') : `<p class="field-hint">暂无定时任务</p>`;
    bind(container, deps);
  }
  app.schedulerView.load = load;

  function bind(container, deps) {
    const d = depsOrDefault(deps);
    const root = container.closest('[data-sched-root]') || container;
    root.querySelector('[data-sched-add]').addEventListener('click', async () => {
      const name = (root.querySelector('[data-sched-name]').value || '').trim();
      const action = root.querySelector('[data-sched-action]').value;
      const interval = parseInt(root.querySelector('[data-sched-interval]').value || '60', 10);
      const trigger = root.querySelector('[data-sched-trigger]').value;
      const payload = trigger === 'daily_at' ? { hour: 9, minute: 0 } : {};
      const { data } = await d.api('POST', '/api/ai/scheduler', { name: name || action, action, interval_minutes: interval, enabled: true, trigger, payload });
      if (data.ok) { d.showToast(d.t('schedAdded', '已添加'), 'success'); load(container, deps); }
      else d.showToast(data.error || '添加失败', 'error');
    });
    root.querySelectorAll('[data-sched-del]').forEach((btn) => btn.addEventListener('click', async () => {
      const { data } = await d.api('POST', '/api/ai/scheduler', { operation: 'remove', task_id: btn.dataset.id });
      if (data.removed) { d.showToast('已删除', 'success'); load(container, deps); }
      else d.showToast(data.error || '删除失败', 'error');
    }));
    root.querySelectorAll('[data-sched-toggle]').forEach((cb) => cb.addEventListener('change', async () => {
      await d.api('POST', '/api/ai/scheduler', { operation: 'enable', task_id: cb.dataset.id, enabled: cb.checked });
    }));
  }
  app.schedulerView.bind = bind;
})(window);