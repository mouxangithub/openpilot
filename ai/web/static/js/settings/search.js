(function (global) {
  const app = global.SettingsApp = global.SettingsApp || {};
  app.search = app.search || {};
  const esc = app.render.esc;

  function buildPalette(deps) {
    const registry = app.registry;
    const out = [];
    registry.all().forEach((d) => (d.cards || []).forEach((c) => (c.fields || []).forEach((f) => {
      out.push({ domain: d, card: c, field: f, label: f.label, text: [d.label, d.id, c.title, c.id, f.label, f.key, f.description].join(' ').toLowerCase() });
    })));
    return out;
  }
  app.search.buildPalette = buildPalette;

  function search(query) {
    const q = String(query || '').trim().toLowerCase();
    if (!q) return [];
    return buildPalette().filter((item) => item.text.includes(q)).slice(0, 12);
  }
  app.search.search = search;

  function renderResults(results, container, deps) {
    const t = (deps || {}).t || ((k, fb) => fb || k);
    if (!results.length) { container.innerHTML = `<p class="field-hint">${t('settings.noResults', '无匹配结果')}</p>`; return; }
    container.innerHTML = results.map((r, i) => `<button type="button" class="settings-search-result" data-i="${i}">
      <span class="settings-search-tag">${esc(r.domain.label)} / ${esc(r.card.title)}</span>
      <span class="settings-search-label">${esc(r.field.label)} <code>${esc(r.field.key)}</code></span>
    </button>`).join('');
    container.querySelectorAll('.settings-search-result').forEach((btn) => btn.addEventListener('click', () => {
      const r = results[Number(btn.dataset.i)];
      if (deps && deps.onPick) deps.onPick(r);
    }));
    return container;
  }
  app.search.renderResults = renderResults;

  // Highlight a card/field within a rendered domain container.
  function highlightMatch(domainContainer, field) {
    const veil = domainContainer.querySelectorAll('.settings-field-highlight');
    veil.forEach((el) => el.classList.remove('settings-field-highlight'));
    const el = domainContainer.querySelector(`[data-key="${field.key}"]`);
    if (el) {
      el.classList.add('settings-field-highlight');
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      setTimeout(() => el.classList.remove('settings-field-highlight'), 2200);
      return true;
    }
    return false;
  }
  app.search.highlightMatch = highlightMatch;
})(window);