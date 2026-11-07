/**
 * observability-panel.js — P1/P2 可观测性面板
 *
 * 1. 会话事件日志查看器：从 /api/ai/sessions/{id}/log 拉取 durable JSONL 事件，
 *    按类型过滤（user/message、tool/call、tool/result、lifecycle、spill、approval、mcp/trust）。
 * 2. Spill / Approval 事件徽标：包装 renderToolCall / updateToolCallResult，当工具结果
 *    包含 toolresult:// 指针或涉及 approval/hitl/mcp trust 时，在卡片头部显示徽章。
 * 3. 浮动开关按钮 + 右侧抽屉面板。
 *
 * 依赖：ai.js 加载之后执行。
 */
(function () {
  'use strict';

  if (window.ObservabilityPanel) return;

  // ---------------------------------------------------------------------------
  // ToolCard 徽标增强（spill / approval / mcp trust）
  // ---------------------------------------------------------------------------
  const _origUpdateToolCallResult = window.updateToolCallResult;
  const _origRenderToolCall = window.renderToolCall;

  function badgeClass(kind) {
    return `obs-badge obs-badge--${kind}`;
  }

  function applyBadges(container, id, result) {
    const div = container && container.querySelector
      ? container.querySelector(`[data-tool-id="${id}"]`)
      : null;
    if (!div) return;
    const summary = div.querySelector('summary');
    if (!summary) return;

    // Spill / externalization badge: result.value or result.content contains toolresult://
    const text = JSON.stringify(result);
    const hasSpill = text.includes('toolresult://');
    if (hasSpill && !summary.querySelector('.obs-badge--spill')) {
      const chip = document.createElement('span');
      chip.className = badgeClass('spill');
      chip.title = '结果已外部化到磁盘（spill）';
      chip.textContent = 'spill';
      summary.appendChild(chip);
    }

    // Approval / HITL badge
    const approvalKinds = ['approval_required', 'approval_asked', 'hitl_asked', 'human_in_the_loop'];
    const hasApproval = result && typeof result === 'object' && (
      approvalKinds.includes(result.status) ||
      approvalKinds.includes(result.error_code) ||
      approvalKinds.includes(result.code) ||
      (result.approval && result.approval.status) ||
      result.needsApproval
    );
    if (hasApproval && !summary.querySelector('.obs-badge--approval')) {
      const chip = document.createElement('span');
      chip.className = badgeClass('approval');
      chip.title = '需要人工审批';
      chip.textContent = 'approval';
      summary.appendChild(chip);
    }

    // MCP trust badge
    const hasMcpTrust = result && typeof result === 'object' && (
      result.mcpTrust || result.trustRequest || result.fingerprint_digest ||
      (typeof result.decision === 'string' && ['allow', 'deny', 'ask'].includes(result.decision))
    );
    if (hasMcpTrust && !summary.querySelector('.obs-badge--mcp-trust')) {
      const chip = document.createElement('span');
      chip.className = badgeClass('mcp-trust');
      chip.title = 'MCP trust 决策';
      chip.textContent = 'MCP trust';
      summary.appendChild(chip);
    }
  }

  window.renderToolCall = function (container, id, name, args, result, agentId, opts) {
    const r = _origRenderToolCall.call(this, container, id, name, args, result, agentId, opts || {});
    if (result !== undefined && result !== null) applyBadges(container, id, result);
    return r;
  };

  window.updateToolCallResult = function (container, id, result) {
    const r = _origUpdateToolCallResult.call(this, container, id, result);
    applyBadges(container, id, result);
    return r;
  };

  // ---------------------------------------------------------------------------
  // Session log viewer 侧栏
  // ---------------------------------------------------------------------------
  const PANEL_ID = 'observabilityPanel';
  const EVENT_KINDS = [
    { key: 'all', label: '全部' },
    { key: 'user/message', label: '用户' },
    { key: 'assistant/message', label: '助手' },
    { key: 'tool/call', label: '工具调用' },
    { key: 'tool/result', label: '工具结果' },
    { key: 'lifecycle', label: '生命周期' },
    { key: 'spill', label: 'Spill' },
    { key: 'approval', label: '审批' },
    { key: 'mcp/trust', label: 'MCP Trust' },
  ];

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  function api(method, path, body) {
    return window.WebApi && typeof window.WebApi.api === 'function'
      ? window.WebApi.api(method, path, body)
      : fetch(path, {
          method,
          headers: { 'Content-Type': 'application/json' },
          body: body ? JSON.stringify(body) : undefined,
        }).then((res) => res.json()).then((data) => ({ data }));
  }

  function getSessionId() {
    return (typeof SessionStore !== 'undefined' && SessionStore.activeId) || '';
  }

  function formatTime(ts) {
    if (!ts) return '—';
    const d = new Date(typeof ts === 'number' && ts > 1e12 ? ts : ts * 1000);
    return isNaN(d.getTime()) ? String(ts) : d.toLocaleString();
  }

  function buildPanel() {
    if (document.getElementById(PANEL_ID)) return document.getElementById(PANEL_ID);
    const aside = document.createElement('aside');
    aside.id = PANEL_ID;
    aside.className = 'observability-panel';
    aside.setAttribute('aria-hidden', 'true');
    aside.innerHTML = `
      <div class="observability-head">
        <span class="observability-title">可观测性</span>
        <button type="button" class="btn icon observability-close" aria-label="关闭">✕</button>
      </div>
      <div class="observability-toolbar">
        <select class="observability-filter" id="obsEventFilter">
          ${EVENT_KINDS.map((k) => `<option value="${esc(k.key)}">${esc(k.label)}</option>`).join('')}
        </select>
        <button type="button" class="btn observability-refresh" id="obsRefreshBtn">刷新</button>
      </div>
      <div class="observability-session-id" id="obsSessionId">—</div>
      <div class="observability-body" id="obsEventList"><div class="observability-empty">选择会话后查看事件日志</div></div>
      <div class="observability-foot">
        <button type="button" class="btn observability-action" id="obsPauseBtn">暂停</button>
        <button type="button" class="btn observability-action" id="obsResumeBtn">恢复</button>
        <button type="button" class="btn observability-action" id="obsForkBtn">Fork</button>
      </div>`;
    document.body.appendChild(aside);

    aside.querySelector('.observability-close').addEventListener('click', () => ObservabilityPanel.toggle(false));
    aside.querySelector('#obsRefreshBtn').addEventListener('click', () => ObservabilityPanel.refresh());
    aside.querySelector('#obsEventFilter').addEventListener('change', () => ObservabilityPanel.render());
    aside.querySelector('#obsPauseBtn').addEventListener('click', () => ObservabilityPanel.lifecycle('pause'));
    aside.querySelector('#obsResumeBtn').addEventListener('click', () => ObservabilityPanel.lifecycle('resume'));
    aside.querySelector('#obsForkBtn').addEventListener('click', () => ObservabilityPanel.fork());
    return aside;
  }

  function eventKind(event) {
    const t = event.type || '';
    if (t.includes('spill') || JSON.stringify(event.data || {}).includes('toolresult://')) return 'spill';
    if (t.includes('approval') || t.includes('hitl')) return 'approval';
    if (t.includes('mcp/trust') || t.includes('mcp_trust')) return 'mcp/trust';
    return t;
  }

  function renderEvent(event, index) {
    const kind = eventKind(event);
    const summary = event.data && typeof event.data === 'object'
      ? (event.data.content || event.data.state || event.data.action || event.data.name || JSON.stringify(event.data).slice(0, 160))
      : '';
    return `
      <div class="obs-event obs-event--${esc(kind.replace(/\//g, '-'))}" data-kind="${esc(kind)}">
        <div class="obs-event-meta">
          <span class="obs-event-seq">#${esc(String(event.seq || index))}</span>
          <span class="obs-event-type">${esc(event.type || 'unknown')}</span>
          <span class="obs-event-time">${esc(formatTime(event.time))}</span>
        </div>
        <div class="obs-event-summary">${esc(summary)}</div>
      </div>`;
  }

  let cachedEvents = [];

  const ObservabilityPanel = {
    refresh: async function () {
      const aside = document.getElementById(PANEL_ID);
      if (!aside) return;
      const sessionId = getSessionId();
      const idEl = aside.querySelector('#obsSessionId');
      idEl.textContent = sessionId ? `会话: ${sessionId}` : '未选择会话';
      const list = aside.querySelector('#obsEventList');
      if (!sessionId) {
        list.innerHTML = '<div class="observability-empty">选择会话后查看事件日志</div>';
        cachedEvents = [];
        return;
      }
      list.innerHTML = '<div class="observability-empty">加载中…</div>';
      try {
        const { data } = await api('GET', `/api/ai/sessions/${encodeURIComponent(sessionId)}/log`);
        cachedEvents = (data && data.ok && Array.isArray(data.events)) ? data.events : [];
      } catch (e) {
        cachedEvents = [];
      }
      ObservabilityPanel.render();
    },

    render: function () {
      const aside = document.getElementById(PANEL_ID);
      if (!aside) return;
      const filter = aside.querySelector('#obsEventFilter').value;
      const list = aside.querySelector('#obsEventList');
      const events = filter === 'all' ? cachedEvents : cachedEvents.filter((e) => eventKind(e) === filter || (filter === 'spill' && JSON.stringify(e.data || {}).includes('toolresult://')));
      if (!events.length) {
        list.innerHTML = '<div class="observability-empty">无匹配事件</div>';
        return;
      }
      list.innerHTML = events.map((e, i) => renderEvent(e, i + 1)).join('');
    },

    toggle: function (show) {
      const aside = buildPanel();
      const willShow = show == null ? aside.getAttribute('aria-hidden') === 'true' : show;
      aside.setAttribute('aria-hidden', willShow ? 'false' : 'true');
      if (willShow) ObservabilityPanel.refresh();
      return willShow;
    },

    lifecycle: async function (action) {
      const sessionId = getSessionId();
      if (!sessionId) return;
      const { data } = await api('POST', `/api/ai/sessions/${encodeURIComponent(sessionId)}/${action}`);
      if (data && data.ok) ObservabilityPanel.refresh();
    },

    fork: async function () {
      const sessionId = getSessionId();
      if (!sessionId) return;
      const { data } = await api('POST', `/api/ai/sessions/${encodeURIComponent(sessionId)}/fork`, { count: 10 });
      if (data && data.ok) {
        cachedEvents = (data.events || []).map((e) => ({ ...e, type: e.type || 'unknown' }));
        ObservabilityPanel.render();
      }
    },
  };
  window.ObservabilityPanel = ObservabilityPanel;

  // 浮动开关按钮
  function ensureToggle() {
    if (document.getElementById('observabilityToggle')) return;
    const btn = document.createElement('button');
    btn.id = 'observabilityToggle';
    btn.className = 'observability-toggle';
    btn.title = '可观测性面板';
    btn.textContent = '👁';
    btn.addEventListener('click', () => ObservabilityPanel.toggle());
    document.body.appendChild(btn);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ensureToggle);
  } else {
    ensureToggle();
  }
})();
