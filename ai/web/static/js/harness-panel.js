/**
 * harness-panel.js — Goal/Plan/Todo 状态侧栏 + ToolCard 增强
 *
 * 对齐 deepseek-harness 的能力可视化要求：
 * 1. 右侧浮动侧栏展示当前目标(goal)、计划(plan)、待办(todo) 的层级状态；
 * 2. 增强 ToolCard 展示：结构化错误码(error_code)、可重试(retryable)、
 *    工具耗时(duration)、来源徽标(agent/subagent)。
 *
 * 依赖：ai.js 加载之后执行（包装其全局 renderToolCall / updateToolCallResult）。
 */
(function () {
  'use strict';

  if (window.HarnessPanel) return;

  // ---------------------------------------------------------------------------
  // ToolCard 增强 — 包装 updateToolCallResult
  // ---------------------------------------------------------------------------
  const toolTimestamps = new Map();
  const _origUpdateToolCallResult = window.updateToolCallResult;
  const _origRenderToolCall = window.renderToolCall;

  function applyToolCardEnhancement(container, id, result, opts) {
    const div = container && container.querySelector
      ? container.querySelector(`[data-tool-id="${id}"]`)
      : null;
    if (!div) return;

    const nameEl = div.querySelector('.chat-tool-row__name, .tool-name');
    const statusEl = div.querySelector('.chat-tool-row__status, .tool-status');
    const bodyEl = div.querySelector('.chat-tool-msg-body');

    // 耗时徽标
    if (opts && typeof opts.startedAt === 'number') {
      toolTimestamps.set(id, opts.startedAt);
    }
    const started = toolTimestamps.get(id);
    if (result && started && bodyEl && !bodyEl.querySelector('.tool-duration')) {
      const dur = Math.max(0, Math.round((Date.now() - started) / 100) / 10);
      const chip = document.createElement('span');
      chip.className = 'tool-duration';
      chip.textContent = `${dur}s`;
      statusEl && statusEl.after(chip);
    }

    // 结构化错误分类：error_code + retryable
    if (result && typeof result === 'object' && result.ok === false) {
      const code = result.error_code || result.code;
      const retry = result.retryable ? '· 可重试' : '';
      if (code && statusEl && !statusEl.dataset.harnessCode) {
        statusEl.dataset.harnessCode = String(code);
        const chip = document.createElement('span');
        chip.className = 'tool-error-code';
        chip.title = retry;
        chip.textContent = String(code);
        statusEl.after(chip);
      }
    }

    // 工具来源徽标（来自事件属性，非渲染期可推导时跳过）
    const source = opts && (opts.subagent ? 'subagent' : (opts.agentId && opts.agentId !== 'op' ? opts.agentId : 'op'));
    if (source && bodyEl && !bodyEl.querySelector('.tool-source')) {
      const chip = document.createElement('span');
      chip.className = 'tool-source';
      chip.textContent = source === 'subagent' ? '子专员' : `专员:${source}`;
      bodyEl.querySelector('.tool-section') && bodyEl.querySelector('.tool-section').prepend(chip);
    }
  }

  window.renderToolCall = function (container, id, name, args, result, agentId, opts) {
    if (!toolTimestamps.has(id)) toolTimestamps.set(id, Date.now());
    const r = _origRenderToolCall.call(this, container, id, name, args, result, agentId, opts || {});
    applyToolCardEnhancement(container, id, result, opts || {});
    return r;
  };

  window.updateToolCallResult = function (container, id, result) {
    const r = _origUpdateToolCallResult.call(this, container, id, result);
    applyToolCardEnhancement(container, id, result, {});
    // goal/plan/todo 工具结果落地后刷新侧栏
    const nameEl = container && container.querySelector ? container.querySelector(`[data-tool-id="${id}"] .tool-name`) : null;
    if (nameEl) {
      const nm = (nameEl.textContent || '').trim();
      if (/^(goal|plan|todo)_/.test(nm) || nm === 'subagent_report') {
        if (typeof window.HarnessPanel.refresh === 'function') {
          setTimeout(() => window.HarnessPanel.refresh(), 300);
        }
      }
    }
    return r;
  };

  // ---------------------------------------------------------------------------
  // Goal/Plan/Todo 侧栏
  // ---------------------------------------------------------------------------
  const PANEL_ID = 'harnessStatusPanel';

  function api(method, path) {
    return window.WebApi && typeof window.WebApi.api === 'function'
      ? window.WebApi.api(method, path)
      : fetch(path, { method, headers: { 'Content-Type': 'application/json' } })
          .then((res) => res.json())
          .then((data) => ({ data }));
  }

  function phaseLabel(phase) {
    const map = { active: '进行中', paused: '已暂停', blocked: '受阻', complete: '已完成', disarmed: '未激活', armed: '已激活' };
    return map[phase] || phase || '—';
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  async function fetchGoal() {
    const { data } = await api('GET', '/api/ai/goals');
    return data && data.ok ? data.goal : null;
  }

  async function fetchPlans() {
    const { data } = await api('GET', '/api/ai/plans');
    return data && data.ok ? data.plans || [] : [];
  }

  async function fetchTodos() {
    const { data } = await api('GET', '/api/ai/todos');
    return data && data.ok ? data : null;
  }

  function buildPanel() {
    if (document.getElementById(PANEL_ID)) return document.getElementById(PANEL_ID);
    const aside = document.createElement('aside');
    aside.id = PANEL_ID;
    aside.className = 'harness-status-panel';
    aside.setAttribute('aria-hidden', 'true');
    aside.innerHTML = `
      <div class="harness-status-head">
        <span class="harness-status-title">目标 / 计划 / 待办</span>
        <button type="button" class="btn icon harness-status-close" aria-label="关闭">✕</button>
      </div>
      <div class="harness-status-body">
        <section class="harness-status-section" data-section="goal">
          <h4>🎯 当前目标</h4>
          <div class="harness-status-content"><div class="harness-status-empty">无</div></div>
        </section>
        <section class="harness-status-section" data-section="plans">
          <h4>🗂 计划</h4>
          <div class="harness-status-content"><div class="harness-status-empty">无</div></div>
        </section>
        <section class="harness-status-section" data-section="todos">
          <h4>✅ 待办</h4>
          <div class="harness-status-content"><div class="harness-status-empty">无</div></div>
        </section>
      </div>
      <div class="harness-status-foot">
        <button type="button" class="btn harness-status-refresh">刷新</button>
      </div>`;
    document.body.appendChild(aside);
    aside.querySelector('.harness-status-close').addEventListener('click', () => HarnessPanel.toggle(false));
    aside.querySelector('.harness-status-refresh').addEventListener('click', () => HarnessPanel.refresh());
    return aside;
  }

  function renderGoal(section, goal) {
    const box = section.querySelector('.harness-status-content');
    if (!box) return;
    box.innerHTML = goal
      ? `<div class="harness-goal">
           <div class="harness-goal-phase ${esc(goal.phase || '')}">${esc(phaseLabel(goal.phase))}</div>
           <div class="harness-goal-objective">${esc(goal.objective || '')}</div>
           <div class="harness-goal-meta">轮次 ${goal.roundsStarted ?? '—'} · rev ${goal.revision ?? '—'}${goal.blockedReason ? ' · 受阻: ' + esc(goal.blockedReason.message || '') : ''}</div>
         </div>`
      : '<div class="harness-status-empty">无</div>';
  }

  function renderPlans(section, plans) {
    const box = section.querySelector('.harness-status-content');
    if (!box) return;
    if (!plans.length) {
      box.innerHTML = '<div class="harness-status-empty">无</div>';
      return;
    }
    box.innerHTML = plans.map((p) => `
      <div class="harness-plan">
        <div class="harness-plan-head">
          <span class="harness-plan-status ${esc(p.status || '')}">${esc(phaseLabel(p.status))}</span>
          <span class="harness-plan-title">${esc(p.title || p.id || '')}</span>
        </div>
        ${(p.steps || []).length ? `<ol class="harness-plan-steps">${p.steps.map((s) => `<li class="${esc(s.status || '')}">${esc(s.description || s.tool || '')}</li>`).join('')}</ol>` : ''}
      </div>`).join('');
  }

  function renderTodos(section, todos) {
    const box = section.querySelector('.harness-status-content');
    if (!box) return;
    const items = Array.isArray(todos) ? todos : (todos && todos.todos ? todos.todos : []);
    if (!items.length) {
      box.innerHTML = '<div class="harness-status-empty">无</div>';
      return;
    }
    box.innerHTML = `<ul class="harness-todos">${items.map((t) => {
      const done = t.status === 'done' || t.status === 'completed';
      return `<li class="${done ? 'done' : ''}">${done ? '☑' : '☐'} ${esc(t.content || '')}</li>`;
    }).join('')}</ul>`;
  }

  const HarnessPanel = {
    refresh: async function () {
      const aside = document.getElementById(PANEL_ID);
      if (!aside) return;
      const [goal, plans, todos] = await Promise.all([
        fetchGoal().catch(() => null),
        fetchPlans().catch(() => []),
        fetchTodos().catch(() => null),
      ]);
      renderGoal(aside.querySelector('[data-section="goal"]'), goal);
      renderPlans(aside.querySelector('[data-section="plans"]'), plans || []);
      renderTodos(aside.querySelector('[data-section="todos"]'), todos ? todos.todos : []);
    },
    toggle: function (show) {
      const aside = buildPanel();
      const willShow = show == null ? aside.getAttribute('aria-hidden') === 'true' : show;
      aside.setAttribute('aria-hidden', willShow ? 'false' : 'true');
      if (willShow) HarnessPanel.refresh();
      return willShow;
    },
  };
  window.HarnessPanel = HarnessPanel;

  // 浮动开关按钮
  function ensureToggle() {
    if (document.getElementById('harnessStatusToggle')) return;
    const btn = document.createElement('button');
    btn.id = 'harnessStatusToggle';
    btn.className = 'harness-status-toggle';
    btn.title = '目标 / 计划 / 待办';
    btn.textContent = '🎯';
    btn.addEventListener('click', () => HarnessPanel.toggle());
    document.body.appendChild(btn);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ensureToggle);
  } else {
    ensureToggle();
  }
})();
