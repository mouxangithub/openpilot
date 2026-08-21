/**
 * Composer @ context menu — files, folders, URLs, branch, browser, past chats.
 */
const ComposerMention = (() => {
  const MAX_REFS = 8;
  const SEARCH_DEBOUNCE_MS = 140;

  const CATEGORIES = [
    { type: 'branch', icon: '⎇', titleKey: 'mentionBranch', metaKey: 'mentionBranchMeta' },
    { type: 'browser', icon: '🌐', titleKey: 'mentionBrowser', metaKey: 'mentionBrowserMeta' },
    { type: 'files', icon: '📁', titleKey: 'mentionFilesFolders', metaKey: 'mentionFilesFoldersMeta' },
    { type: 'sessions', icon: '💬', titleKey: 'mentionPastChats', metaKey: 'mentionPastChatsMeta' },
  ];

  let deps = {};
  let menuOpen = false;
  let highlight = 0;
  let mentionState = null;
  let searchTimer = null;
  let searchSeq = 0;
  let lastResults = [];
  let filesMode = false;

  function t(key, fallback) {
    return deps.t ? deps.t(key, fallback) : (fallback || key);
  }

  function esc(value) {
    return deps.escapeHtml ? deps.escapeHtml(value) : String(value || '');
  }

  function els() {
    return {
      menu: document.getElementById('composerMentionMenu'),
      label: document.getElementById('composerMentionLabel'),
      list: document.getElementById('composerMentionList'),
      input: deps.getInput?.(),
    };
  }

  function caretPos(input) {
    if (!input) return 0;
    return input.selectionStart ?? input.value.length;
  }

  function getMentionState(text, caret) {
    const value = text || '';
    const pos = typeof caret === 'number' ? caret : value.length;
    if (value.trimStart().startsWith('/')) return null;
    const before = value.slice(0, pos);
    const atIdx = before.lastIndexOf('@');
    if (atIdx === -1) return null;
    if (atIdx > 0 && !/\s/.test(before[atIdx - 1])) return null;
    const query = before.slice(atIdx + 1);
    if (/\s/.test(query)) return null;
    return { query, atIdx, caret: pos };
  }

  function isUrlQuery(query) {
    const q = (query || '').trim();
    if (!q) return false;
    if (/^https?:\/\//i.test(q)) return true;
    return /^[\w.-]+\.[a-z]{2,}(\/|$)/i.test(q);
  }

  function refKey(ref) {
    const type = ref.type || (ref.kind === 'dir' ? 'dir' : 'file');
    if (type === 'url') return `url:${ref.url}`;
    if (type === 'branch') return 'branch';
    if (type === 'browser') return 'browser';
    if (type === 'session') return `session:${ref.sessionId}`;
    return `file:${ref.path}`;
  }

  function fileIcon(entry) {
    const type = entry?.type || entry?.kind;
    if (type === 'dir' || type === 'files') return '📁';
    if (type === 'branch') return '⎇';
    if (type === 'browser') return '🌐';
    if (type === 'url') return '🔗';
    if (type === 'session') return '💬';
    const ext = entry?.ext || '';
    const map = {
      py: '🐍', js: '📜', ts: '📘', json: '{}', md: '📝', html: '🌐', css: '🎨',
      capnp: '📡', cpp: '⚙️', c: '⚙️', h: '⚙️', sh: '🖥️', yaml: '📋', yml: '📋', toml: '📋', txt: '📄',
    };
    return map[(ext || '').toLowerCase()] || '📄';
  }

  function hideMenu() {
    menuOpen = false;
    highlight = 0;
    mentionState = null;
    lastResults = [];
    filesMode = false;
    els().menu?.classList.add('hidden');
  }

  function showMenu(state) {
    deps.hideSlashMenu?.();
    menuOpen = true;
    mentionState = state;
    els().menu?.classList.remove('hidden');
    updateLabel(state);
  }

  function updateLabel(state) {
    if (!els().label) return;
    if (!state?.query) {
      els().label.textContent = t('mentionAddContext', 'Add context');
      return;
    }
    if (isUrlQuery(state.query)) {
      els().label.textContent = t('mentionAttachLink', 'Attach link');
      return;
    }
    els().label.textContent = t('mentionSearchContext', 'Search context');
  }

  function renderEmpty(message) {
    const ui = els();
    if (!ui.list) return;
    ui.list.innerHTML = '';
    const empty = document.createElement('p');
    empty.className = 'composer-slash-empty';
    empty.textContent = message;
    ui.list.appendChild(empty);
    highlight = 0;
    lastResults = [];
  }

  function renderResults(items) {
    const ui = els();
    if (!ui.list) return;
    ui.list.innerHTML = '';
    lastResults = items || [];
    if (!lastResults.length) {
      renderEmpty(t('mentionNoResults', 'No matching context'));
      return;
    }
    if (highlight >= lastResults.length) highlight = 0;
    lastResults.forEach((item, idx) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = `composer-slash-item composer-mention-item${idx === highlight ? ' active' : ''}`;
      btn.dataset.idx = String(idx);
      const title = item.title || item.name || item.label || '';
      const meta = item.meta || item.rel || item.path || item.url || item.sessionTitle || '';
      const rootLabel = item.root && item.root !== 'openpilot' ? item.root : '';
      btn.innerHTML = `
        <span class="composer-mention-row">
          <span class="composer-mention-icon" aria-hidden="true">${fileIcon(item)}</span>
          <span class="composer-mention-main">
            <span class="composer-slash-item-title">${esc(title)}${item.kind === 'dir' ? '/' : ''}${rootLabel ? `<span class="composer-mention-root">${esc(rootLabel)}</span>` : ''}</span>
            <span class="composer-slash-item-meta">${esc(meta)}</span>
          </span>
        </span>
      `;
      btn.title = meta || title;
      btn.addEventListener('click', () => selectItem(item));
      ui.list.appendChild(btn);
    });
  }

  function buildCategoryItems() {
    return CATEGORIES.map((cat) => ({
      type: cat.type,
      title: t(cat.titleKey, cat.type),
      meta: t(cat.metaKey, ''),
      _category: true,
    }));
  }

  function buildRecentSessions(limit = 5) {
    const sessions = deps.listSessions?.() || [];
    const activeId = deps.getActiveSessionId?.();
    return sessions
      .filter((s) => s.id && s.id !== activeId && (s.title || s.preview || (s.messages || []).length))
      .slice(0, limit)
      .map((s) => ({
        type: 'session',
        sessionId: s.id,
        title: s.title || s.preview || t('mentionUntitledChat', 'Untitled chat'),
        meta: s.preview || s.id,
        name: s.title || s.preview || s.id,
      }));
  }

  function renderDefaultMenu() {
    const items = [...buildCategoryItems(), ...buildRecentSessions()];
    renderResults(items);
  }

  async function searchFiles(query) {
    const { status, data } = await deps.api(
      'GET',
      `/api/ai/files/search?q=${encodeURIComponent(query || '')}&limit=20`,
      null,
      { timeoutMs: 12000 },
    );
    if (!data?.ok || status >= 400) {
      throw new Error(data?.error || 'file search failed');
    }
    return (data.files || []).map((file) => ({
      ...file,
      type: file.kind === 'dir' ? 'dir' : 'file',
      title: file.name,
      meta: file.rel || file.path || '',
    }));
  }

  async function searchSessions(query) {
    if (!query.trim()) return buildRecentSessions(8);
    const { data } = await deps.api(
      'GET',
      `/api/ai/sessions/search?q=${encodeURIComponent(query)}&limit=8`,
      null,
      { timeoutMs: 12000 },
    );
    const hits = Array.isArray(data?.hits) ? data.hits : [];
    return hits.map((hit) => ({
      type: 'session',
      sessionId: hit.sessionId || hit.session_id,
      title: hit.sessionTitle || hit.title || t('mentionUntitledChat', 'Untitled chat'),
      meta: hit.snippet || hit.preview || hit.sessionId || '',
      name: hit.sessionTitle || hit.title || hit.sessionId,
    })).filter((item) => item.sessionId);
  }

  function buildUrlItem(query) {
    let url = query.trim();
    if (!/^https?:\/\//i.test(url)) url = `https://${url}`;
    return {
      type: 'url',
      url,
      title: t('mentionAttachLink', 'Attach link'),
      meta: url,
      name: url,
    };
  }

  async function runSearch(state) {
    const seq = ++searchSeq;
    const query = (state?.query || '').trim();
    if (!query) {
      if (seq !== searchSeq || !menuOpen) return;
      renderDefaultMenu();
      return;
    }

    renderEmpty(t('mentionSearching', 'Searching…'));

    if (isUrlQuery(query)) {
      if (seq !== searchSeq || !menuOpen) return;
      renderResults([buildUrlItem(query)]);
      return;
    }

    try {
      const [files, sessions] = await Promise.all([
        searchFiles(query).catch(() => []),
        searchSessions(query).catch(() => []),
      ]);
      if (seq !== searchSeq || !menuOpen) return;
      const merged = [...sessions.slice(0, 6), ...files.slice(0, 18)];
      if (!merged.length) {
        renderEmpty(t('mentionNoResults', 'No matching context'));
        return;
      }
      renderResults(merged);
    } catch {
      if (seq !== searchSeq || !menuOpen) return;
      renderEmpty(t('mentionSearchFailed', 'Search failed'));
    }
  }

  function scheduleSearch(state) {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      searchTimer = null;
      runSearch(state);
    }, SEARCH_DEBOUNCE_MS);
  }

  async function refresh() {
    const input = els().input;
    if (!input) {
      hideMenu();
      return false;
    }
    const state = getMentionState(input.value, caretPos(input));
    if (!state) {
      hideMenu();
      return false;
    }
    showMenu(state);
    if (filesMode && !state.query) {
      filesMode = false;
    }
    scheduleSearch(state);
    return true;
  }

  function removeMentionToken(input, state) {
    if (!input || !state) return;
    const before = input.value.slice(0, state.atIdx);
    const after = input.value.slice(state.caret);
    input.value = before + after;
    const nextPos = before.length;
    input.setSelectionRange(nextPos, nextPos);
  }

  function attachRef(ref) {
    const pending = deps.getPendingRefs?.() || [];
    if (pending.length >= MAX_REFS) {
      deps.showToast?.(t('mentionRefLimit', 'Too many context items attached'), 'warning');
      return false;
    }
    const key = refKey(ref);
    if (pending.some((item) => refKey(item) === key)) {
      deps.showToast?.(t('mentionRefDuplicate', 'Context already attached'), 'warning');
      return false;
    }
    deps.onAttach?.(ref);
    return true;
  }

  function selectItem(item) {
    const input = els().input;
    const state = mentionState || getMentionState(input?.value || '', caretPos(input));
    if (!input || !state) return;

    if (item._category) {
      if (item.type === 'files') {
        filesMode = true;
        updateLabel(state);
        runSearch({ ...state, query: state.query || '' });
        return;
      }
      if (item.type === 'branch') {
        const branch = deps.getGitBranch?.() || '';
        if (attachRef({ type: 'branch', branch, name: branch || 'branch', title: branch || t('mentionBranch', 'Branch') })) {
          removeMentionToken(input, state);
          hideMenu();
        }
        deps.autoResize?.();
        input.focus();
        return;
      }
      if (item.type === 'browser') {
        if (attachRef({ type: 'browser', name: t('mentionBrowser', 'Browser'), title: t('mentionBrowser', 'Browser') })) {
          removeMentionToken(input, state);
          hideMenu();
        }
        deps.autoResize?.();
        input.focus();
        return;
      }
      if (item.type === 'sessions') {
        runSearch({ ...state, query: '' });
        renderResults(buildRecentSessions(10));
        return;
      }
      return;
    }

    if (item.type === 'session') {
      if (attachRef({
        type: 'session',
        sessionId: item.sessionId,
        name: item.title || item.name,
        title: item.title || item.name,
      })) {
        removeMentionToken(input, state);
        hideMenu();
      }
    } else if (item.type === 'url') {
      if (attachRef({
        type: 'url',
        url: item.url,
        name: item.url,
        title: item.title || item.url,
      })) {
        removeMentionToken(input, state);
        hideMenu();
      }
    } else if (item.path) {
      if (attachRef({
        type: item.kind === 'dir' ? 'dir' : 'file',
        path: item.path,
        rel: item.rel || item.name,
        name: item.name,
        ext: item.ext || '',
        kind: item.kind || 'file',
        root: item.root || 'openpilot',
        title: item.name,
      })) {
        removeMentionToken(input, state);
        hideMenu();
      }
    }

    deps.autoResize?.();
    input.focus();
  }

  function onKeydown(e) {
    if (!menuOpen || !mentionState) return false;
    if (!lastResults.length && e.key !== 'Escape') return false;

    if (e.key === 'ArrowDown' && lastResults.length) {
      e.preventDefault();
      highlight = (highlight + 1) % lastResults.length;
      renderResults(lastResults);
      return true;
    }
    if (e.key === 'ArrowUp' && lastResults.length) {
      e.preventDefault();
      highlight = (highlight - 1 + lastResults.length) % lastResults.length;
      renderResults(lastResults);
      return true;
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      hideMenu();
      return true;
    }
    if ((e.key === 'Enter' || e.key === 'Tab') && lastResults.length) {
      e.preventDefault();
      selectItem(lastResults[highlight]);
      return true;
    }
    return false;
  }

  function isOpen() {
    return menuOpen;
  }

  function init(options = {}) {
    deps = options;
  }

  function refreshTranslations() {
    if (!menuOpen) return;
    updateLabel(mentionState);
  }

  return {
    init,
    refresh,
    onKeydown,
    isOpen,
    hideMenu,
    refreshTranslations,
    getMentionState,
  };
})();
