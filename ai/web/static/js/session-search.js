/**
 * Cross-session search — header (desktop) + modal (mobile).
 */
const SessionSearch = (() => {
  let deps = {};
  let desktopInput = null;
  let desktopDropdown = null;
  let mobileBtn = null;
  let mobileModal = null;
  let mobileInput = null;
  let mobileResults = null;
  let debounceTimer = null;
  let activeIdx = -1;
  let lastHits = [];
  let open = false;
  let mobileOpen = false;
  let searchSeq = 0;
  let searchWrap = null;

  function label(key, fallback) {
    return deps.t?.(key, fallback) || fallback;
  }

  function stripSnippet(s) {
    return String(s || '').replace(/…/g, '').replace(/\u2026/g, '').trim();
  }

  function roleLabel(role) {
    if (role === 'user') return label('sessionSearchRoleUser', 'You');
    if (role === 'assistant') return label('sessionSearchRoleAssistant', 'Assistant');
    return label('sessionSearchRoleSystem', 'System');
  }

  function messageText(content) {
    if (typeof deps.messageText === 'function') return deps.messageText(content);
    if (typeof content === 'string') return content;
    return '';
  }

  function searchLocal(query, limit = 12) {
    const q = query.trim().toLowerCase();
    if (!q || typeof deps.listSessions !== 'function') return [];
    const hits = [];
    for (const session of deps.listSessions()) {
      const title = session.title || session.preview || session.id || '';
      const msgs = session.messages || [];
      for (let i = 0; i < msgs.length; i += 1) {
        const msg = msgs[i];
        const text = messageText(msg.content);
        if (!text || !text.toLowerCase().includes(q)) continue;
        const pos = text.toLowerCase().indexOf(q);
        const start = Math.max(0, pos - 24);
        const snippet = (start > 0 ? '…' : '') + text.slice(start, start + 72) + (start + 72 < text.length ? '…' : '');
        hits.push({
          sessionId: session.id,
          sessionTitle: title,
          role: msg.role,
          snippet,
          messageIndex: i,
          _local: true,
        });
        if (hits.length >= limit) return hits;
      }
    }
    return hits;
  }

  async function searchRemote(query, limit = 12) {
    if (!query.trim() || typeof deps.api !== 'function') return [];
    try {
      const { data } = await deps.api(
        'GET',
        `/api/ai/sessions/search?q=${encodeURIComponent(query)}&limit=${limit}`,
        null,
        { timeoutMs: 12000 },
      );
      return Array.isArray(data?.hits) ? data.hits : [];
    } catch {
      return [];
    }
  }

  async function runSearch(query) {
    const q = query.trim();
    const seq = ++searchSeq;
    if (!q) {
      lastHits = [];
      activeIdx = -1;
      renderHits([]);
      return;
    }
    renderHits([], q, { loading: true });
    const [remote, local] = await Promise.all([
      searchRemote(q, 10),
      Promise.resolve(searchLocal(q, 10)),
    ]);
    if (seq !== searchSeq) return;
    const seen = new Set();
    const merged = [];
    for (const hit of [...remote, ...local]) {
      const key = `${hit.sessionId}:${stripSnippet(hit.snippet).slice(0, 48)}`;
      if (seen.has(key)) continue;
      seen.add(key);
      merged.push(hit);
      if (merged.length >= 12) break;
    }
    lastHits = merged;
    activeIdx = merged.length ? 0 : -1;
    renderHits(merged, q);
  }

  function highlightSnippet(snippet, query) {
    const raw = String(snippet || '');
    const q = query.trim();
    if (!q) return deps.escapeHtml?.(raw) || raw;
    const plain = raw.replace(/…/g, '');
    const idx = plain.toLowerCase().indexOf(q.toLowerCase());
    if (idx < 0) return deps.escapeHtml?.(raw) || raw;
    const esc = (s) => (deps.escapeHtml ? deps.escapeHtml(s) : s);
    const before = raw.slice(0, idx);
    const match = raw.slice(idx, idx + q.length);
    const after = raw.slice(idx + q.length);
    return `${esc(before)}<mark>${esc(match)}</mark>${esc(after)}`;
  }

  function renderHitRow(hit, idx, query, container) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `session-search-hit${idx === activeIdx ? ' active' : ''}`;
    btn.dataset.idx = String(idx);
    btn.innerHTML = `
      <span class="session-search-hit-title">${deps.escapeHtml?.(hit.sessionTitle || hit.sessionId || '') || ''}</span>
      <span class="session-search-hit-meta">${roleLabel(hit.role)}</span>
      <span class="session-search-hit-snippet">${highlightSnippet(hit.snippet, query)}</span>
    `;
    btn.addEventListener('mousedown', (e) => e.preventDefault());
    btn.addEventListener('click', () => selectHit(hit));
    container.appendChild(btn);
  }

  function positionDesktopDropdown() {
    if (!desktopDropdown || !desktopInput || desktopDropdown.classList.contains('hidden')) return;
    const anchor = desktopInput.closest('.session-search-field') || desktopInput;
    const rect = anchor.getBoundingClientRect();
    const width = Math.min(Math.max(rect.width, 280), window.innerWidth - 16);
    const left = Math.min(Math.max(8, rect.left), window.innerWidth - width - 8);
    desktopDropdown.style.position = 'fixed';
    desktopDropdown.style.top = `${Math.round(rect.bottom + 6)}px`;
    desktopDropdown.style.left = `${Math.round(left)}px`;
    desktopDropdown.style.width = `${Math.round(width)}px`;
    desktopDropdown.style.right = 'auto';
    desktopDropdown.style.zIndex = '220';
  }

  function renderHits(hits, query = '', opts = {}) {
    const lists = [desktopDropdown, mobileResults].filter(Boolean);
    for (const list of lists) {
      list.innerHTML = '';
      if (opts.loading && query) {
        const loading = document.createElement('p');
        loading.className = 'session-search-empty';
        loading.textContent = label('sessionSearchLoading', 'Searching…');
        list.appendChild(loading);
      } else if (!hits.length) {
        const empty = document.createElement('p');
        empty.className = 'session-search-empty';
        empty.textContent = query
          ? label('sessionSearchNoHits', 'No matches')
          : label('sessionSearchHint', 'Search across all chats');
        list.appendChild(empty);
      } else {
        hits.forEach((hit, idx) => renderHitRow(hit, idx, query, list));
      }
    }
    const shouldOpen = Boolean(query && (opts.loading || hits.length));
    setDropdownOpen(shouldOpen || (open && query));
    if (shouldOpen) positionDesktopDropdown();
  }

  function setDropdownOpen(on) {
    open = !!on;
    desktopDropdown?.classList.toggle('hidden', !open);
    if (open) positionDesktopDropdown();
  }

  function setMobileOpen(on) {
    mobileOpen = !!on;
    mobileModal?.classList.toggle('open', mobileOpen);
    mobileModal?.setAttribute('aria-hidden', mobileOpen ? 'false' : 'true');
    document.body.classList.toggle('session-search-modal-open', mobileOpen);
    if (mobileOpen) {
      setTimeout(() => mobileInput?.focus(), 50);
    } else {
      mobileInput && (mobileInput.value = '');
      if (mobileResults) mobileResults.innerHTML = '';
    }
  }

  function findMessageIndex(sessionId, hit) {
    if (typeof hit.messageIndex === 'number' && hit.messageIndex >= 0) return hit.messageIndex;
    const session = deps.getSessionById?.(sessionId);
    if (!session?.messages?.length) return -1;
    const needle = stripSnippet(hit.snippet);
    if (!needle) return -1;
    const probe = needle.slice(0, Math.min(48, needle.length));
    for (let i = session.messages.length - 1; i >= 0; i -= 1) {
      const msg = session.messages[i];
      const text = messageText(msg.content);
      if (!text) continue;
      if (text.includes(probe) || probe.includes(text.slice(0, 32))) return i;
      if (hit.role && msg.role === hit.role && text.toLowerCase().includes(probe.slice(0, 20).toLowerCase())) {
        return i;
      }
    }
    return -1;
  }

  async function selectHit(hit) {
    if (!hit?.sessionId) return;
    setDropdownOpen(false);
    setMobileOpen(false);
    desktopInput && (desktopInput.value = '');
    if (typeof deps.navigateToHit === 'function') {
      await deps.navigateToHit(hit);
    }
  }

  function scheduleSearch(query) {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      debounceTimer = null;
      runSearch(query);
    }, 220);
  }

  function onInput(value) {
    if (!value.trim()) {
      searchSeq += 1;
      lastHits = [];
      activeIdx = -1;
      renderHits([]);
      setDropdownOpen(false);
      return;
    }
    setDropdownOpen(true);
    positionDesktopDropdown();
    scheduleSearch(value);
  }

  function moveActive(delta) {
    if (!lastHits.length) return;
    activeIdx = (activeIdx + delta + lastHits.length) % lastHits.length;
    renderHits(lastHits, desktopInput?.value || mobileInput?.value || '');
  }

  function onKeydown(e, input) {
    if (e.key === 'Escape') {
      setDropdownOpen(false);
      setMobileOpen(false);
      input?.blur();
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      moveActive(1);
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      moveActive(-1);
      return;
    }
    if (e.key === 'Enter' && activeIdx >= 0 && lastHits[activeIdx]) {
      e.preventDefault();
      selectHit(lastHits[activeIdx]);
    }
  }

  function bindDesktop() {
    desktopInput?.addEventListener('input', () => onInput(desktopInput.value));
    desktopInput?.addEventListener('focus', () => {
      if (desktopInput.value.trim()) {
        setDropdownOpen(true);
        positionDesktopDropdown();
      }
    });
    desktopInput?.addEventListener('keydown', (e) => onKeydown(e, desktopInput));
    window.addEventListener('resize', positionDesktopDropdown);
    window.addEventListener('scroll', positionDesktopDropdown, true);
    document.addEventListener('click', (e) => {
      if (!desktopInput || !desktopDropdown) return;
      const wrap = searchWrap || desktopInput.closest('.session-search');
      if (wrap?.contains(e.target)) return;
      setDropdownOpen(false);
    });
  }

  function bindMobile() {
    mobileBtn?.addEventListener('click', () => setMobileOpen(true));
    mobileModal?.querySelector('.session-search-modal-backdrop')?.addEventListener('click', () => setMobileOpen(false));
    mobileModal?.querySelector('.session-search-modal-close')?.addEventListener('click', () => setMobileOpen(false));
    mobileInput?.addEventListener('input', () => onInput(mobileInput.value));
    mobileInput?.addEventListener('keydown', (e) => onKeydown(e, mobileInput));
  }

  function mount(options = {}) {
    deps = options;
    searchWrap = document.getElementById('sessionSearchWrap');
    desktopInput = document.getElementById('sessionSearchInput');
    desktopDropdown = document.getElementById('sessionSearchDropdown');
    mobileBtn = document.getElementById('sessionSearchMobileBtn');
    mobileModal = document.getElementById('sessionSearchModal');
    mobileInput = document.getElementById('sessionSearchModalInput');
    mobileResults = document.getElementById('sessionSearchModalResults');
    if (desktopInput) {
      desktopInput.placeholder = label('sessionSearchPlaceholder', 'Search chats…');
    }
    if (mobileInput) {
      mobileInput.placeholder = label('sessionSearchPlaceholder', 'Search chats…');
    }
    bindDesktop();
    bindMobile();
  }

  return { mount, findMessageIndex };
})();
