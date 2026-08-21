/**
 * Orchestration task blackboard — multi-specialist progress (WorkBuddy s22).
 */
const OrchestrationBlackboard = (() => {
  let board = null;
  let list = null;
  const agents = new Map();

  function ensureDom() {
    board = document.getElementById('orchestrationBlackboard');
    list = document.getElementById('orchestrationBlackboardList');
    if (!board || board.dataset.bound) return;
    board.dataset.bound = '1';
    document.getElementById('orchestrationBlackboardClose')?.addEventListener('click', () => {
      board.classList.add('hidden');
    });
  }

  function agentMeta(id) {
    if (typeof OfficePanel !== 'undefined') return OfficePanel.agentMeta(id);
    return { icon: '🤖', name: id };
  }

  function render() {
    ensureDom();
    if (!list) return;
    const items = [...agents.values()];
    if (!items.length) {
      board?.classList.add('hidden');
      return;
    }
    board?.classList.remove('hidden');
    list.innerHTML = items.map((a) => {
      const meta = agentMeta(a.id);
      const statusCls = a.status === 'done' ? 'done' : (a.status === 'working' ? 'working' : 'pending');
      const tool = a.tool ? `<span class="orch-board-tool">${a.tool}</span>` : '';
      return `<li class="orch-board-item ${statusCls}">
        <span class="orch-board-icon">${meta.icon}</span>
        <span class="orch-board-name">${meta.name || a.id}</span>
        <span class="orch-board-status">${a.statusLabel || a.status}</span>
        ${tool}
      </li>`;
    }).join('');
  }

  function reset() {
    agents.clear();
    render();
  }

  function handleStreamEvent(data) {
    if (data.type === 'orchestration_start') {
      agents.clear();
      for (const p of (data.plan || [])) {
        const id = p.agent_id || p.agentId;
        if (!id) continue;
        agents.set(id, { id, status: 'pending', statusLabel: '等待中' });
      }
      render();
      return;
    }
    if (data.type === 'agent_status') {
      const id = data.agentId || data.agent_id;
      if (!id) return;
      const cur = agents.get(id) || { id, status: 'pending' };
      if (data.status === 'working') {
        cur.status = 'working';
        cur.statusLabel = '执行中';
        cur.tool = data.tool || '';
      } else if (data.status === 'assigned' || data.status === 'idle') {
        cur.status = 'done';
        cur.statusLabel = '完成';
        cur.tool = '';
      }
      agents.set(id, cur);
      render();
    }
    if (data.type === 'orchestration_synthesis') {
      const id = data.agentId || 'op';
      agents.set(id, { id, status: 'working', statusLabel: '汇总中' });
      render();
    }
    if (data.type === 'done') {
      setTimeout(reset, 2500);
    }
  }

  function init() {
    ensureDom();
  }

  return { init, handleStreamEvent, reset };
})();
