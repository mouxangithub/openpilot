/**
 * OP 办公室 — 等距动态场景 + 专员列表 + 任务侧栏
 */
const OfficePanel = (() => {
  let root = null;
  let tasksEl = null;
  let statsEl = null;
  let rosterEl = null;
  let detailEl = null;
  let backdrop = null;
  let toggleBtn = null;
  let agentsById = new Map();
  let officeState = null;
  let usageTokens = 0;
  let selectedAgentId = null;
  let onOpenCallback = null;
  let onVisibilityChange = null;
  let getDriving = () => false;
  let getVehicleState = () => null;
  let showToast = null;
  let apiFn = null;
  let open = false;
  let sceneReady = false;
  let sceneInitPromise = null;
  let agentsLoading = false;

  const STATUS_LABEL = {
    idle: '空闲',
    assigned: '已派活',
    working: '执行中',
    waiting: '待确认',
  };

  function agentMeta(id) {
    const a = agentsById.get(id);
    return a || { id: id || 'op', name: id || 'op', icon: '🤖' };
  }

  function liveAgentStatus(id) {
    const live = (officeState?.agents || []).find((a) => a.id === id);
    return live?.status || 'idle';
  }

  function liveAgentTool(id) {
    const live = (officeState?.agents || []).find((a) => a.id === id);
    return live?.tool || '';
  }

  function statusLabel(id) {
    const status = liveAgentStatus(id);
    const tool = liveAgentTool(id);
    if (status === 'working' && tool) return tool;
    return STATUS_LABEL[status] || status;
  }

  function setAgents(list) {
    agentsById = new Map();
    for (const a of list || []) {
      if (a?.id) agentsById.set(a.id, a);
    }
    if (typeof OfficeScene !== 'undefined') {
      OfficeScene.setAgents(list);
    }
    renderRoster();
    renderStats();
    if (selectedAgentId && !agentsById.has(selectedAgentId)) {
      selectAgent(null);
    } else if (selectedAgentId) {
      renderAgentDetail(selectedAgentId);
    }
  }

  function applyOffice(data) {
    officeState = data || null;
    if (typeof OfficeScene !== 'undefined') {
      OfficeScene.applyOffice(data);
    }
    renderTasks();
    renderStats();
    renderRoster();
    if (selectedAgentId) renderAgentDetail(selectedAgentId);
  }

  function setUsageTokens(total) {
    usageTokens = Number(total) || 0;
    renderStats();
  }

  function formatTokens(n) {
    const v = Number(n) || 0;
    if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`;
    if (v >= 1_000) return `${(v / 1_000).toFixed(1).replace(/\.0$/, '')}K`;
    return String(v);
  }

  function renderStats() {
    if (!statsEl) return;
    const active = officeState?.activeCount ?? 0;
    const tasks = officeState?.tasks?.length ?? 0;
    const agentCount = agentsById.size || officeState?.agents?.length || 0;
    const countLabel = agentsLoading && !agentCount ? '…' : agentCount;
    statsEl.innerHTML = `
      <div class="office-stat"><span>专员</span><b>${countLabel}</b></div>
      <div class="office-stat"><span>进行中</span><b>${active}</b></div>
      <div class="office-stat"><span>任务记录</span><b>${tasks}</b></div>
      <div class="office-stat"><span>累计 Token</span><b>${formatTokens(usageTokens)}</b></div>
    `;
  }

  function renderRoster() {
    if (!rosterEl) return;
    const list = [...agentsById.values()].sort((a, b) => {
      const da = a.desk || {};
      const db = b.desk || {};
      return (da.row - db.row) || (da.col - db.col) || String(a.id).localeCompare(b.id);
    });
    if (!list.length) {
      rosterEl.innerHTML = '<p class="office-tasks-empty">加载专员中…</p>';
      return;
    }
    rosterEl.innerHTML = `
      <div class="office-roster-title">专员 (${list.length})</div>
      ${list.map((agent) => {
        const status = liveAgentStatus(agent.id);
        const active = status !== 'idle';
        const selected = agent.id === selectedAgentId;
        return `
          <button type="button" class="office-roster-item${selected ? ' is-selected' : ''}${active ? ' is-active' : ''}" data-agent-id="${escapeOffice(agent.id)}">
            <span class="office-roster-icon">${agent.icon || '🤖'}</span>
            <span class="office-roster-body">
              <span class="office-roster-name">${escapeOffice(agent.name || agent.id)}</span>
              <span class="office-roster-status">${escapeOffice(statusLabel(agent.id))}</span>
            </span>
          </button>
        `;
      }).join('')}
    `;
    rosterEl.querySelectorAll('[data-agent-id]').forEach((btn) => {
      btn.addEventListener('click', () => selectAgent(btn.dataset.agentId));
    });
  }

  function renderAgentDetail(id) {
    if (!detailEl) return;
    if (!id || !agentsById.has(id)) {
      detailEl.hidden = true;
      detailEl.innerHTML = '';
      return;
    }
    const agent = agentsById.get(id);
    const status = liveAgentStatus(id);
    const tool = liveAgentTool(id);
    detailEl.hidden = false;
    detailEl.innerHTML = `
      <div class="office-agent-detail-head">
        <span class="office-roster-icon">${agent.icon || '🤖'}</span>
        <h4>${escapeOffice(agent.name || agent.id)}</h4>
      </div>
      <p class="office-agent-detail-desc">${escapeOffice(agent.description || '内置专员')}</p>
      <div class="office-agent-detail-meta">
        状态：${escapeOffice(statusLabel(id))}
        ${tool ? ` · 工具：${escapeOffice(tool)}` : ''}
        ${agent.pcOnly ? ' · 仅 PC 联调' : ''}
      </div>
    `;
  }

  function selectAgent(id) {
    selectedAgentId = id || null;
    if (typeof OfficeScene !== 'undefined') {
      OfficeScene.setSelectedAgent(selectedAgentId);
    }
    renderRoster();
    renderAgentDetail(selectedAgentId);
  }

  function renderTasks() {
    if (!tasksEl) return;
    const tasks = [...(officeState?.tasks || [])].reverse().slice(0, 12);
    if (!tasks.length) {
      tasksEl.innerHTML = '<p class="office-tasks-empty">暂无任务动态 — 派活后专员会走向工位</p>';
      return;
    }
    tasksEl.innerHTML = tasks.map((t) => {
      const meta = agentMeta(t.agentId);
      const time = t.at ? new Date(t.at * 1000).toLocaleTimeString() : '';
      return `
        <div class="office-task status-${t.status || 'info'}">
          <div class="office-task-head">
            <span class="office-task-agent">${meta.icon} ${escapeOffice(meta.name)}</span>
            <span class="office-task-time">${time}</span>
          </div>
          <div class="office-task-msg">${escapeOffice(t.message || '')}</div>
        </div>
      `;
    }).join('');
  }

  function escapeOffice(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  async function ensureAgentsLoaded() {
    if (agentsById.size > 0 || agentsLoading || !apiFn) return;
    agentsLoading = true;
    renderStats();
    try {
      const { data } = await apiFn('GET', '/api/ai/agents');
      if (data?.ok) {
        if (Array.isArray(data.agents)) setAgents(data.agents);
        if (data.office) applyOffice(data.office);
      }
    } catch (_) { /* ignore */ } finally {
      agentsLoading = false;
      renderStats();
      renderRoster();
    }
  }

  async function ensureScene() {
    if (sceneReady) return true;
    if (typeof OfficeScene === 'undefined') return false;
    if (!sceneInitPromise) {
      sceneInitPromise = OfficeScene.init(document.getElementById('officeSceneHost')).then((ok) => {
        sceneReady = !!ok;
        if (sceneReady) {
          OfficeScene.setOnSelectAgent((id) => selectAgent(id));
          if (agentsById.size) {
            OfficeScene.setAgents([...agentsById.values()]);
          }
        }
        return sceneReady;
      }).catch(() => {
        sceneInitPromise = null;
        sceneReady = false;
        return false;
      });
    }
    return sceneInitPromise;
  }

  function setVisible(visible) {
    if (!root) return;
    open = visible;
    root.classList.toggle('is-open', visible);
    if (visible) root.removeAttribute('hidden');
    else root.setAttribute('hidden', '');
    toggleBtn?.classList.toggle('active', visible);
    onVisibilityChange?.(visible);
    if (visible) {
      setDrivingMode(getDriving());
      setVehicleState(getVehicleState());
      ensureAgentsLoaded().catch(() => {});
      ensureScene().then((ok) => {
        if (ok) {
          OfficeScene.resize();
          OfficeScene.start();
        }
      });
      onOpenCallback?.();
    } else if (sceneReady) {
      OfficeScene.stop();
    }
  }

  function show() {
    setVisible(true);
  }

  function hide() {
    setVisible(false);
  }

  function toggle() {
    if (open) hide();
    else show();
  }

  function setDrivingMode(driving) {
    if (typeof OfficeScene !== 'undefined') {
      OfficeScene.setDrivingPaused(!!driving);
    }
  }

  function setVehicleState(vs) {
    if (typeof OfficeScene !== 'undefined') {
      OfficeScene.setVehicleState?.(vs);
    }
  }

  function init(opts = {}) {
    root = opts.modal || opts.panel || document.getElementById('officeModal');
    tasksEl = opts.tasks || document.getElementById('officeTasks');
    statsEl = opts.stats || document.getElementById('officeStats');
    rosterEl = opts.roster || document.getElementById('officeRoster');
    detailEl = opts.detail || document.getElementById('officeAgentDetail');
    backdrop = opts.backdrop || document.getElementById('officeBackdrop');
    toggleBtn = opts.toggleBtn || document.getElementById('officeBtn');
    const closeBtn = opts.closeBtn || document.getElementById('officeCloseBtn');
    onVisibilityChange = opts.onVisibilityChange || null;
    getDriving = typeof opts.getDriving === 'function' ? opts.getDriving : getDriving;
    getVehicleState = typeof opts.getVehicleState === 'function' ? opts.getVehicleState : getVehicleState;
    showToast = opts.showToast || null;
    apiFn = opts.api || null;
    onOpenCallback = opts.onOpen || null;

    toggleBtn?.addEventListener('click', toggle);
    closeBtn?.addEventListener('click', hide);
    backdrop?.addEventListener('click', hide);
    renderTasks();
    renderStats();
    renderRoster();
  }

  return {
    init,
    setAgents,
    setUsageTokens,
    applyOffice,
    agentMeta,
    show,
    hide,
    toggle,
    isOpen: () => open,
    setDrivingMode,
    setVehicleState,
    selectAgent,
  };
})();
