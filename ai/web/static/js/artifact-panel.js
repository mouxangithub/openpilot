/**
 * Artifact delivery drawer — WorkBuddy-style result cards (overlay, no layout shift).
 */
const ArtifactPanel = (() => {
  let drawerEl = null;
  let backdropEl = null;
  let listEl = null;
  let toggleBtn = null;
  let closeBtn = null;
  let open = false;
  const bySession = typeof ArtifactStore !== 'undefined' ? null : new Map();

  function ensureDom() {
    drawerEl = document.getElementById('artifactPanel');
    backdropEl = document.getElementById('artifactBackdrop');
    listEl = document.getElementById('artifactPanelList');
    toggleBtn = document.getElementById('artifactPanelToggle');
    closeBtn = document.getElementById('artifactPanelClose');
    if (toggleBtn && !toggleBtn.dataset.bound) {
      toggleBtn.dataset.bound = '1';
      toggleBtn.addEventListener('click', () => setOpen(!open));
    }
    if (closeBtn && !closeBtn.dataset.bound) {
      closeBtn.dataset.bound = '1';
      closeBtn.addEventListener('click', () => setOpen(false));
    }
    if (backdropEl && !backdropEl.dataset.bound) {
      backdropEl.dataset.bound = '1';
      backdropEl.addEventListener('click', () => setOpen(false));
    }
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && open) setOpen(false);
    });
  }

  function setOpen(next) {
    open = !!next;
    drawerEl?.classList.toggle('open', open);
    backdropEl?.classList.toggle('visible', open);
    drawerEl?.setAttribute('aria-hidden', open ? 'false' : 'true');
    backdropEl?.setAttribute('aria-hidden', open ? 'false' : 'true');
    toggleBtn?.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function sid(sessionId) {
    return sessionId || (typeof SessionStore !== 'undefined' ? SessionStore.activeId : '') || '__global__';
  }

  function addArtifact(sessionId, artifact) {
    if (!artifact) return;
    if (typeof ArtifactStore !== 'undefined') {
      ArtifactStore.add(sessionId, artifact);
    } else {
      const key = sid(sessionId);
      const items = bySession.get(key) || [];
      items.unshift(artifact);
      bySession.set(key, items.slice(0, 40));
    }
    updateBadge(sid(sessionId));
    render(sessionId);
    setOpen(true);
  }

  function updateBadge(key) {
    const items = typeof ArtifactStore !== 'undefined' ? ArtifactStore.list(key) : (bySession.get(key) || []);
    const n = items.length;
    const badge = document.getElementById('artifactPanelBadge');
    if (badge) {
      badge.textContent = String(n);
      badge.classList.toggle('hidden', n === 0);
    }
  }

  function renderDiff(diffText) {
    if (!diffText) return '';
    const lines = String(diffText).split('\n').slice(0, 120);
    return `<pre class="artifact-diff">${lines.map((ln) => {
      let cls = '';
      if (ln.startsWith('+') && !ln.startsWith('+++')) cls = 'diff-add';
      else if (ln.startsWith('-') && !ln.startsWith('---')) cls = 'diff-del';
      return `<span class="${cls}">${escapeHtml(ln)}</span>`;
    }).join('\n')}</pre>`;
  }

  function renderBody(artifact) {
    const payload = artifact.payload || {};
    const kind = artifact.kind || '';
    if (kind === 'file' || payload.filePath) {
      const path = payload.filePath || payload.path || '';
      const diff = payload.diff || payload.patch;
      return `${path ? `<footer class="artifact-card-foot"><code>${escapeHtml(path)}</code></footer>` : ''}
        ${diff ? renderDiff(diff) : ''}
        ${payload.preview ? `<pre class="artifact-preview">${escapeHtml(String(payload.preview).slice(0, 4000))}</pre>` : ''}
        <div class="artifact-actions">
          ${path ? `<button type="button" class="btn small artifact-copy-path" data-path="${escapeHtml(path)}">复制路径</button>` : ''}
        </div>`;
    }
    if (payload.summary) {
      return `<p class="artifact-summary">${escapeHtml(payload.summary)}</p>`;
    }
    if (payload.preview) {
      return `<pre class="artifact-preview">${escapeHtml(String(payload.preview).slice(0, 4000))}</pre>`;
    }
    if (payload.markdown && typeof renderMarkdown === 'function') {
      const div = document.createElement('div');
      div.className = 'artifact-md';
      renderMarkdown(div, String(payload.markdown));
      return div.outerHTML;
    }
    return `<pre class="artifact-preview">${escapeHtml(JSON.stringify(payload, null, 2).slice(0, 3000))}</pre>`;
  }

  function render(sessionId) {
    ensureDom();
    if (!listEl) return;
    const key = sid(sessionId);
    const items = typeof ArtifactStore !== 'undefined' ? ArtifactStore.list(key) : (bySession.get(key) || []);
    const emptyText = typeof t === 'function'
      ? t('artifactEmpty', '暂无交付物。工具生成的报告、图表或大段输出会出现在这里。')
      : '暂无交付物。工具生成的报告、图表或大段输出会出现在这里。';
    if (!items.length) {
      listEl.innerHTML = `<p class="artifact-empty">${escapeHtml(emptyText)}</p>`;
      updateBadge(key);
      return;
    }
    listEl.innerHTML = items.map((a) => {
      const kind = a.kind || 'report';
      const title = a.title || a.sourceTool || kind;
      const ts = a.createdAt ? new Date(a.createdAt * 1000).toLocaleString() : '';
      const path = (a.payload || {}).path || (a.payload || {}).filePath || '';
      const cardCls = kind === 'file' || (a.payload || {}).filePath ? 'artifact-card file-card' : 'artifact-card';
      return `<article class="${cardCls}" data-id="${escapeHtml(a.id || '')}">
        <header class="artifact-card-head">
          <span class="artifact-kind">${escapeHtml(kind)}</span>
          <strong>${escapeHtml(title)}</strong>
          <time>${escapeHtml(ts)}</time>
        </header>
        ${renderBody(a)}
        ${path && kind !== 'file' ? `<footer class="artifact-card-foot"><code>${escapeHtml(path)}</code></footer>` : ''}
      </article>`;
    }).join('');
    listEl.querySelectorAll('.artifact-copy-path').forEach((btn) => {
      btn.addEventListener('click', () => {
        const p = btn.getAttribute('data-path');
        if (p && navigator.clipboard) navigator.clipboard.writeText(p).catch(() => {});
      });
    });
    updateBadge(key);
  }

  function handleStreamEvent(ctx, data) {
    if (data.type === 'canvas' && data.artifact) {
      addArtifact(ctx.sessionId, data.artifact);
    }
    if (data.type === 'prompt_budget' && data.budget && typeof ComposerContextMeter !== 'undefined') {
      ComposerContextMeter.applyServerBudget?.(data.budget);
    }
  }

  function init() {
    ensureDom();
    setOpen(false);
    if (typeof ArtifactStore !== 'undefined') {
      ArtifactStore.subscribe(() => {
        if (typeof SessionStore !== 'undefined' && SessionStore.activeId) render(SessionStore.activeId);
      });
    }
    if (typeof SessionStore !== 'undefined' && SessionStore.activeId) {
      render(SessionStore.activeId);
    }
  }

  return { init, addArtifact, render, handleStreamEvent, setOpen };
})();
