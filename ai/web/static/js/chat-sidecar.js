/**
 * Chat-level tool sidecar — WorkBuddy-style live tool activity in main chat.
 */
const ChatSidecar = (() => {
  let panel = null;
  let listEl = null;
  const events = [];

  function ensureDom() {
    panel = document.getElementById('chatSidecar');
    listEl = document.getElementById('chatSidecarList');
    if (!panel || panel.dataset.bound) return;
    panel.dataset.bound = '1';
    document.getElementById('chatSidecarClear')?.addEventListener('click', clear);
  }

  function show() {
    ensureDom();
    panel?.classList.remove('hidden');
  }

  function render() {
    ensureDom();
    if (!listEl) return;
    if (!events.length) {
      listEl.innerHTML = '<li class="chat-sidecar-empty">暂无工具调用</li>';
      panel?.classList.add('hidden');
      return;
    }
    show();
    listEl.innerHTML = events.slice(-25).reverse().map((ev) => {
      const name = ev.name || ev.tool || 'tool';
      const ok = ev.type === 'tool_done' ? ev.ok !== false : null;
      const badge = ev.type === 'tool_start' || ev.type === 'tool_call'
        ? '<span class="chat-sidecar-badge running">…</span>'
        : (ok ? '<span class="chat-sidecar-badge ok">✓</span>' : '<span class="chat-sidecar-badge err">✗</span>');
      const agent = ev.agentId ? `<span class="chat-sidecar-agent">${ev.agentId}</span>` : '';
      return `<li class="chat-sidecar-item">${badge}<code>${name}</code>${agent}</li>`;
    }).join('');
  }

  function push(ev) {
    if (!ev) return;
    events.push({ ...ev, ts: Date.now() });
    if (events.length > 60) events.splice(0, events.length - 60);
    render();
  }

  function handleStreamEvent(data) {
    if (data.type === 'tool_call') {
      push({ type: 'tool_start', name: data.name, agentId: data.agentId || data.agent_id });
    }
    if (data.type === 'tool_result') {
      const ok = data.result?.ok !== false;
      push({ type: 'tool_done', name: data.name, ok, agentId: data.agentId || data.agent_id });
    }
  }

  function clear() {
    events.length = 0;
    render();
  }

  function init() {
    ensureDom();
    render();
  }

  return { init, handleStreamEvent, clear, push };
})();
