/**
 * Hermes-style terminal sidecar — live tool events beside Web terminal.
 */
const TerminalSidecar = (() => {
  let listEl = null;
  let ws = null;
  let events = [];

  function wsUrl() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${location.host}/api/ai/sidecar/ws`;
  }

  function ensureDom() {
    listEl = document.getElementById('terminalSidecarList');
  }

  function render() {
    ensureDom();
    if (!listEl) return;
    if (!events.length) {
      listEl.innerHTML = '<li class="sidecar-empty">暂无工具调用</li>';
      return;
    }
    listEl.innerHTML = events.slice(-30).reverse().map((ev) => {
      const name = ev.name || ev.tool || 'tool';
      const ok = ev.type === 'tool_done' ? ev.ok !== false : null;
      const badge = ev.type === 'tool_start'
        ? '<span class="sidecar-badge running">运行中</span>'
        : (ok ? '<span class="sidecar-badge ok">完成</span>' : '<span class="sidecar-badge err">失败</span>');
      const agent = ev.agentId ? `<span class="sidecar-agent">${ev.agentId}</span>` : '';
      return `<li class="sidecar-item">${badge}<code>${name}</code>${agent}</li>`;
    }).join('');
  }

  function push(ev) {
    if (!ev || !ev.type) return;
    events.push(ev);
    if (events.length > 80) events = events.slice(-80);
    render();
  }

  function connect() {
    disconnect();
    try {
      ws = new WebSocket(wsUrl());
    } catch {
      return;
    }
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === 'sidecar_hello' && Array.isArray(data.events)) {
          events = data.events;
          render();
          return;
        }
        if (data.type === 'sidecar_event' || data.type === 'tool_start' || data.type === 'tool_done') {
          push(data);
        }
      } catch {}
    };
    ws.onclose = () => {
      ws = null;
      setTimeout(connect, 4000);
    };
  }

  function disconnect() {
    if (ws) {
      try { ws.close(); } catch {}
      ws = null;
    }
  }

  function clear() {
    events = [];
    render();
  }

  return { connect, disconnect, clear, push };
})();
