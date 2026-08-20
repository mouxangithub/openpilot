/**
 * Composer context usage ring + breakdown panel (Cursor-style).
 */
const ComposerContextMeter = (() => {
  const MODEL_CONTEXT_WINDOWS = {
    'deepseek-v4-flash': 128_000,
    'deepseek-chat': 64_000,
    'gpt-4o': 128_000,
    'gpt-4o-mini': 128_000,
    'claude-sonnet-4': 200_000,
    'kimi-k2': 128_000,
    default: 128_000,
  };

  const CATEGORIES = [
    { id: 'system', color: '#7dd87a', labelKey: 'contextCatSystem', fallback: 'System prompt' },
    { id: 'toolsAgents', color: '#e8a44a', labelKey: 'contextCatTools', fallback: 'Tools & sub-agents' },
    { id: 'messages', color: '#b794f6', labelKey: 'contextCatMessages', fallback: 'Conversation' },
    { id: 'knowledge', color: '#e879a9', labelKey: 'contextCatKnowledge', fallback: 'Knowledge base' },
    { id: 'embedding', color: '#38bdf8', labelKey: 'contextCatEmbedding', fallback: 'Embedding & memory' },
    { id: 'connectors', color: '#4ecdc4', labelKey: 'contextCatConnectors', fallback: 'Connectors & MCP' },
    { id: 'skills', color: '#6ba4f5', labelKey: 'contextCatSkills', fallback: 'Skills' },
  ];

  const RAG_HIT_LIMIT = 8;
  const RAG_SNIPPET_CHARS = 800;
  const MEMORY_NOTES_TOKENS = 420;
  const DAILY_MEMORY_TOKENS = 620;
  const WORKSPACE_ENRICH_TOKENS = 320;

  const RING_R = 9;
  const RING_C = 2 * Math.PI * RING_R;
  const DEFAULT_PERSONA_TOKENS = 1500;

  let deps = {};
  let root = null;
  let btn = null;
  let panel = null;
  let closeBtn = null;
  let ringFg = null;
  let pctEl = null;
  let panelPctEl = null;
  let panelUsedEl = null;
  let barEl = null;
  let listEl = null;
  let footerEl = null;
  let compactBtn = null;
  let refreshTimer = null;
  let panelOpen = false;

  function routeKey(route) {
    if (!route?.accountId || !route?.model) return '';
    return `${route.accountId}\0${route.model}`;
  }

  function estimateMessageTokens(content) {
    let text = '';
    if (typeof content === 'string') text = content;
    else if (Array.isArray(content)) {
      text = content
        .filter((p) => p && p.type === 'text')
        .map((p) => String(p.text || ''))
        .join(' ');
    } else if (content != null) text = String(content);
    const n = text.length;
    if (!n) return 0;
    return Math.max(1, Math.floor(n / 3.5));
  }

  function estimateToolsSchemaTokens(toolsMeta) {
    if (!toolsMeta || typeof toolsMeta !== 'object') return 0;
    try {
      return estimateMessageTokens(JSON.stringify(toolsMeta));
    } catch {
      return 0;
    }
  }

  function estimateSkillsTokens(skills, config) {
    const max = Math.max(1, Number(config?.skillsDisclosureMax) || 10);
    const list = Array.isArray(skills) ? skills : [];
    let total = 0;
    let count = 0;
    for (const s of list) {
      if (count >= max) break;
      total += estimateMessageTokens(s?.description || s?.name || '');
      total += 180;
      count += 1;
    }
    return total;
  }

  function estimateConnectorsTokens(connectors) {
    if (!Array.isArray(connectors) || !connectors.length) return 0;
    let total = 0;
    for (const c of connectors) {
      total += estimateMessageTokens(c?.name || c?.id || '');
      total += estimateMessageTokens(c?.command || '');
      total += 120;
    }
    return total;
  }

  function estimateMessagesBreakdown(messages) {
    let messagesTokens = 0;
    let toolsAgentsTokens = 0;
    for (const m of messages || []) {
      messagesTokens += 4;
      messagesTokens += estimateMessageTokens(m?.content);
      if (m?.reasoning_content) messagesTokens += estimateMessageTokens(m.reasoning_content);

      for (const tc of m?.tool_calls || []) {
        toolsAgentsTokens += 4;
        const fn = tc?.function || {};
        toolsAgentsTokens += estimateMessageTokens(fn.name);
        toolsAgentsTokens += estimateMessageTokens(fn.arguments);
      }
      const tr = m?.tool_results || {};
      if (tr && typeof tr === 'object') {
        Object.values(tr).forEach((v) => {
          toolsAgentsTokens += estimateMessageTokens(typeof v === 'string' ? v : JSON.stringify(v));
        });
      }
      for (const ev of m?.agent_events || []) {
        toolsAgentsTokens += estimateMessageTokens(ev?.title);
        toolsAgentsTokens += estimateMessageTokens(ev?.body);
      }
    }
    return { messagesTokens, toolsAgentsTokens };
  }

  function contextWindowForModel(model, routeOverride, globalOverride) {
    const routeCw = Number(routeOverride) || 0;
    if (routeCw > 0) return routeCw;
    const globalCw = Number(globalOverride) || 0;
    if (globalCw > 0) return globalCw;
    const m = String(model || '').trim().toLowerCase();
    for (const [key, window] of Object.entries(MODEL_CONTEXT_WINDOWS)) {
      if (key !== 'default' && m.includes(key)) return window;
    }
    return MODEL_CONTEXT_WINDOWS.default;
  }

  function routeContextWindow(hub, route) {
    if (!hub || !route?.accountId || !route?.model) return 0;
    const key = routeKey(route);
    const primary = hub.primary;
    if (primary && routeKey(primary) === key && Number(primary.contextWindow) > 0) {
      return Number(primary.contextWindow);
    }
    for (const row of hub.fallbacks || []) {
      if (routeKey(row) === key && Number(row.contextWindow) > 0) return Number(row.contextWindow);
    }
    return 0;
  }

  function lastUserMessageText(messages) {
    for (let i = (messages || []).length - 1; i >= 0; i -= 1) {
      const m = messages[i];
      if (m?.role !== 'user') continue;
      if (typeof deps.messageText === 'function') return deps.messageText(m.content);
      if (typeof m.content === 'string') return m.content;
    }
    return '';
  }

  function isEmbeddingConfigured(config) {
    if (!config) return false;
    const mode = String(config.embeddingMode || 'same').toLowerCase();
    if (mode === 'separate') {
      return Boolean(
        (config.embeddingProvider && config.embeddingModel)
        || (config.embeddingApiKey && config.embeddingModel),
      );
    }
    const hub = typeof deps.getHub === 'function' ? deps.getHub() : config.modelHub;
    return Boolean(hub?.accounts?.length || config.provider || config.model);
  }

  function ragHitLimit() {
    const config = deps.getConfig?.() || {};
    const n = Number(config.ragSearchLimit);
    return Number.isFinite(n) && n > 0 ? n : RAG_HIT_LIMIT;
  }

  function estimateKnowledgeTokens(_ragStats, _messages) {
    return 0;
  }

  function estimateEmbeddingContextTokens(config, messages, ragStats) {
    let total = 0;
    const chunks = Number(ragStats?.vector_chunks) || 0;
    const query = lastUserMessageText(messages);

    if (isEmbeddingConfigured(config)) {
      if (query) total += estimateMessageTokens(query);
      if (chunks > 0) total += 48;
    }

    if (docCountOrNotes(ragStats, config) > 0) {
      total += MEMORY_NOTES_TOKENS;
    }
    if (messages?.length) {
      total += DAILY_MEMORY_TOKENS;
      total += WORKSPACE_ENRICH_TOKENS;
    }
    return total;
  }

  function docCountOrNotes(ragStats, config) {
    const stats = ragStats || {};
    if ((Number(stats.count) || 0) > 0) return stats.count;
    if (config?.evolutionAutoMemory !== false) return 1;
    return 0;
  }

  function computeState() {
    const config = deps.getConfig?.() || {};
    const hub = deps.getHub?.() || config.modelHub || null;
    const session = deps.getSession?.() || null;
    const route = typeof deps.getEffectiveRoute === 'function'
      ? deps.getEffectiveRoute(session, hub)
      : (hub?.primary || null);
    const model = route?.model || config.model || '';
    const routeCw = routeContextWindow(hub, route);
    const window = contextWindowForModel(model, routeCw, config.contextWindow);
    const messages = typeof deps.getMessages === 'function' ? deps.getMessages() : [];
    const { messagesTokens, toolsAgentsTokens } = estimateMessagesBreakdown(messages);

    const sysText = String(config.systemPrompt || '').trim();
    const systemTokens = sysText
      ? estimateMessageTokens(sysText) + 4
      : DEFAULT_PERSONA_TOKENS;

    const toolsSchemaTokens = estimateToolsSchemaTokens(deps.getToolsMeta?.());
    const skillsTokens = estimateSkillsTokens(deps.getSkillsRegistry?.(), config);
    const connectorsTokens = estimateConnectorsTokens(deps.getConnectors?.());
    const ragStats = typeof deps.getRagStats === 'function' ? deps.getRagStats() : null;
    const knowledgeTokens = estimateKnowledgeTokens(ragStats, messages);
    const embeddingTokens = estimateEmbeddingContextTokens(config, messages, ragStats);

    const breakdown = {
      system: systemTokens,
      toolsAgents: toolsAgentsTokens + toolsSchemaTokens,
      messages: messagesTokens,
      knowledge: knowledgeTokens,
      embedding: embeddingTokens,
      connectors: connectorsTokens,
      skills: skillsTokens,
    };
    const used = Object.values(breakdown).reduce((a, b) => a + b, 0);
    const pct = window > 0 ? Math.min(100, (used / window) * 100) : 0;
    return { used, window, pct, model, breakdown };
  }

  function fmtTokens(n) {
    if (typeof deps.fmtTokenNum === 'function') return deps.fmtTokenNum(n);
    const v = Number(n) || 0;
    if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`;
    if (v >= 1_000) return `${(v / 1_000).toFixed(1).replace(/\.0$/, '')}K`;
    return String(v);
  }

  function fmtPct(n) {
    const v = Number(n) || 0;
    if (v >= 10) return `${v.toFixed(1)}%`;
    if (v >= 1) return `${v.toFixed(1)}%`;
    if (v > 0) return `${v.toFixed(1)}%`;
    return '0%';
  }

  function label(key, fallback) {
    return deps.t?.(key, fallback) || fallback;
  }

  function setPanelOpen(open) {
    panelOpen = !!open;
    panel?.classList.toggle('open', panelOpen);
    btn?.setAttribute('aria-expanded', panelOpen ? 'true' : 'false');
  }

  function embeddingApiUsageSummary() {
    const usage = typeof deps.getEmbeddingUsage === 'function' ? deps.getEmbeddingUsage() : null;
    if (!usage) return '';
    const total = Number(usage.total_tokens ?? usage.prompt_tokens ?? 0);
    if (!total) return '';
    return deps.tf?.(
      'contextEmbeddingApiTotal',
      { total: fmtTokens(total) },
      `Embedding API total: ${fmtTokens(total)}`,
    ) || `Embedding API total: ${fmtTokens(total)}`;
  }

  function updateCompactBtn() {
    if (!compactBtn) return;
    const busy = typeof deps.isBusy === 'function' ? !!deps.isBusy() : false;
    compactBtn.disabled = busy;
    compactBtn.textContent = label('contextCompactBtn', 'Compact context');
    compactBtn.title = label('contextCompactHint', 'Same as /compact — summarize older turns into memory');
  }

  function renderPanel(state) {
    if (!panel || !barEl || !listEl) return;
    const { used, window, pct, breakdown } = state;
    if (panelPctEl) panelPctEl.textContent = `${pct.toFixed(1)}%`;
    if (panelUsedEl) {
      panelUsedEl.textContent = deps.tf?.(
        'contextUsedSummary',
        { used: fmtTokens(used), window: fmtTokens(window) },
        `Used ${fmtTokens(used)} / ${fmtTokens(window)}`,
      ) || `Used ${fmtTokens(used)} / ${fmtTokens(window)}`;
    }

    barEl.innerHTML = '';
    listEl.innerHTML = '';
    for (const cat of CATEGORIES) {
      const tokens = breakdown[cat.id] || 0;
      const share = window > 0 ? (tokens / window) * 100 : 0;
      if (share > 0.05) {
        const seg = document.createElement('span');
        seg.className = 'composer-context-bar-seg';
        seg.style.width = `${Math.max(share, 0.4)}%`;
        seg.style.background = cat.color;
        barEl.appendChild(seg);
      }

      const row = document.createElement('div');
      row.className = 'composer-context-row';
      row.innerHTML = `
        <span class="composer-context-dot" style="background:${cat.color}"></span>
        <span class="composer-context-row-label">${label(cat.labelKey, cat.fallback)}</span>
        <span class="composer-context-row-pct">${fmtPct(share)}</span>
      `;
      listEl.appendChild(row);
    }

    if (footerEl) {
      const apiLine = embeddingApiUsageSummary();
      const ragStats = typeof deps.getRagStats === 'function' ? deps.getRagStats() : null;
      const chunks = Number(ragStats?.vector_chunks) || 0;
      const docs = Number(ragStats?.count) || 0;
      const indexLine = (chunks > 0 || docs > 0)
        ? (deps.tf?.(
          'contextKnowledgeIndex',
          { docs, chunks },
          `${docs} docs · ${chunks} vector chunks`,
        ) || `${docs} docs · ${chunks} vector chunks`)
        : '';
      const parts = [indexLine, apiLine].filter(Boolean);
      footerEl.textContent = parts.join(' · ');
      footerEl.classList.toggle('hidden', !parts.length);
    }
    updateCompactBtn();
  }

  function render() {
    if (!root || !ringFg || !pctEl) return;
    const state = computeState();
    const { used, window, pct } = state;
    const offset = RING_C * (1 - Math.min(1, pct / 100));
    ringFg.style.strokeDasharray = `${RING_C}`;
    ringFg.style.strokeDashoffset = `${offset}`;
    pctEl.textContent = `${Math.round(pct)}%`;
    root.classList.toggle('warn', pct >= 75 && pct < 90);
    root.classList.toggle('critical', pct >= 90);
    root.classList.remove('hidden');
    renderPanel(state);
    if (btn) {
      btn.setAttribute(
        'aria-label',
        deps.tf?.('contextUsedTitle', { pct: Math.round(pct) }, `${Math.round(pct)}% context used`)
          || `${Math.round(pct)}% context used`,
      );
    }
  }

  function refresh() {
    if (refreshTimer) clearTimeout(refreshTimer);
    refreshTimer = setTimeout(() => {
      refreshTimer = null;
      render();
    }, 60);
  }

  function bindEvents() {
    btn?.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      setPanelOpen(!panelOpen);
    });
    closeBtn?.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      setPanelOpen(false);
    });
    document.addEventListener('click', (e) => {
      if (!panelOpen || !root) return;
      if (root.contains(e.target)) return;
      setPanelOpen(false);
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && panelOpen) setPanelOpen(false);
    });
    compactBtn?.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (compactBtn.disabled) return;
      setPanelOpen(false);
      deps.onCompact?.();
    });
  }

  function mount(selector, options = {}) {
    deps = options;
    root = document.querySelector(selector);
    if (!root) return;
    btn = root.querySelector('.composer-context-meter-btn');
    panel = root.querySelector('.composer-context-panel');
    closeBtn = root.querySelector('.composer-context-panel-close');
    ringFg = root.querySelector('.composer-context-ring-fg');
    pctEl = root.querySelector('.composer-context-pct');
    panelPctEl = root.querySelector('.composer-context-panel-pct');
    panelUsedEl = root.querySelector('.composer-context-panel-used');
    barEl = root.querySelector('.composer-context-bar');
    listEl = root.querySelector('.composer-context-list');
    footerEl = root.querySelector('.composer-context-panel-footer');
    compactBtn = root.querySelector('.composer-context-compact-btn');
    bindEvents();
    render();
  }

  function applyServerBudget(budget) {
    if (!budget || !root) return;
    const total = Number(budget.total_window) || 128000;
    const system = Number(budget.system_tokens) || 0;
    const pct = total > 0 ? Math.min(100, (system / total) * 100) : 0;
    if (panelPctEl) panelPctEl.textContent = `${pct.toFixed(1)}%`;
    if (panelUsedEl) {
      panelUsedEl.textContent = `System ${fmtTokens(system)} / ${fmtTokens(total)}`;
    }
    if (pctEl) pctEl.textContent = `${Math.round(pct)}%`;
    if (ringFg) {
      const offset = RING_C * (1 - Math.min(1, pct / 100));
      ringFg.style.strokeDasharray = `${RING_C}`;
      ringFg.style.strokeDashoffset = `${offset}`;
    }
    if (barEl && Array.isArray(budget.blocks) && listEl) {
      barEl.innerHTML = '';
      listEl.innerHTML = '';
      const colors = ['#7dd87a', '#e8a44a', '#b794f6', '#e879a9', '#38bdf8', '#4ecdc4', '#6ba4f5'];
      budget.blocks.forEach((b, i) => {
        const share = total > 0 ? (b.tokens / total) * 100 : 0;
        if (share > 0.05) {
          const seg = document.createElement('span');
          seg.className = 'composer-context-bar-seg';
          seg.style.width = `${Math.max(share, 0.4)}%`;
          seg.style.background = colors[i % colors.length];
          barEl.appendChild(seg);
        }
        const row = document.createElement('div');
        row.className = 'composer-context-row';
        row.innerHTML = `
          <span class="composer-context-dot" style="background:${colors[i % colors.length]}"></span>
          <span class="composer-context-row-label">${b.label || 'block'}</span>
          <span class="composer-context-row-pct">${fmtTokens(b.tokens)}${b.truncated ? ' ✂' : ''}</span>
        `;
        listEl.appendChild(row);
      });
    }
  }

  return { mount, refresh, computeState, applyServerBudget };
})();
