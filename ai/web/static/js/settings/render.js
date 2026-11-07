(function (global) {
  const app = global.SettingsApp = global.SettingsApp || {};
  app.render = app.render || {};
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function fieldHtml(field, value) {
    const v = value === undefined || value === null ? field.default : value;
    const hint = field.description ? `<p class="settings-field-desc">${esc(field.description)}</p>` : '';
    const restart = field.restart ? '<span class="settings-restart-badge">重启生效</span>' : '';
    switch (field.type) {
      case 'secret':
        return `<div class="settings-field" data-key="${esc(field.key)}" data-type="secret">
          <label class="settings-field-label">${esc(field.label)}${restart}</label>
          <div class="settings-secret-row"><input type="password" class="settings-input" data-fk="${esc(field.key)}" value="${esc(v || '')}" autocomplete="off" spellcheck="false">
          <button type="button" class="btn small ghost settings-secret-toggle" data-for="${esc(field.key)}" title="显示">👁</button></div>
          ${hint}</div>`;
      case 'number':
        return `<div class="settings-field" data-key="${esc(field.key)}" data-type="number">
          <label class="settings-field-label">${esc(field.label)}${restart}</label>
          <input type="number" class="settings-input" data-fk="${esc(field.key)}" value="${esc(v)}" ${field.min!=null?`min="${field.min}"`:''} ${field.max!=null?`max="${field.max}"`:''}>
          ${hint}</div>`;
      case 'boolean':
        return `<div class="settings-field" data-key="${esc(field.key)}" data-type="boolean">
          <label class="settings-check-row"><input type="checkbox" data-fk="${esc(field.key)}" ${v?'checked':''}> <span>${esc(field.label)}${restart}</span></label>
          ${hint}</div>`;
      case 'enum':
        return `<div class="settings-field" data-key="${esc(field.key)}" data-type="enum">
          <label class="settings-field-label">${esc(field.label)}${restart}</label>
          <select class="settings-input" data-fk="${esc(field.key)}">${(field.enum||[]).map((o)=>`<option value="${esc(o)}" ${o===v?'selected':''}>${esc(o)}</option>`).join('')}</select>
          ${hint}</div>`;
      case 'textarea':
        return `<div class="settings-field" data-key="${esc(field.key)}" data-type="textarea">
          <label class="settings-field-label">${esc(field.label)}${restart}</label>
          <textarea class="settings-input" data-fk="${esc(field.key)}" rows="4">${esc(v || '')}</textarea>
          ${hint}</div>`;
      default:
        return `<div class="settings-field" data-key="${esc(field.key)}" data-type="string">
          <label class="settings-field-label">${esc(field.label)}${restart}</label>
          <input type="text" class="settings-input" data-fk="${esc(field.key)}" value="${esc(v)}" ${field.placeholder?`placeholder="${esc(field.placeholder)}"`:''}>
          ${hint}</div>`;
    }
  }

  function cardHtml(domain, card) {
    const head = `<header class="settings-card-head"><div><h3 class="settings-card-title">${esc(card.title)}</h3>${card.subtitle?`<p class="settings-card-sub">${esc(card.subtitle)}</p>`:''}</div>
      <div class="settings-card-actions" data-card-actions="${esc(card.id)}"></div></header>`;
    if (card.kind === 'action' || card.kind === 'danger') {
      const body = card.kind === 'danger'
        ? `<div class="settings-card-body settings-danger-root" data-danger-card="${esc(card.id)}"></div>`
        : `<div class="settings-card-body settings-action-root" data-action-card="${esc(card.id)}"></div>`;
      return `<section class="settings-card" data-domain="${esc(domain.id)}" data-card="${esc(card.id)}">${head}${body}</section>`;
    }
    const fields = (card.fields||[]).map((fld) => fieldHtml(fld, fld.default)).join('');
    return `<section class="settings-card" data-domain="${esc(domain.id)}" data-card="${esc(card.id)}">
      ${head}
      <div class="settings-card-body">${fields}<div class="settings-card-savebar" data-savebar="${esc(card.id)}"></div></div>
    </section>`;
  }

  app.render.cardHtml = cardHtml;
  app.render.fieldHtml = fieldHtml;
  app.render.esc = esc;

  function renderDomain(domain, container, deps) {
    container.innerHTML = (domain.cards||[]).map((c) => cardHtml(domain, c)).join('');
    bindCardInputs(container, domain, deps);
    return container;
  }
  app.render.renderDomain = renderDomain;

  function bindCardInputs(container, domain, deps) {
    container.querySelectorAll('.settings-card').forEach((cardEl) => {
      const cardId = cardEl.dataset.card;
      const card = (domain.cards||[]).find((c) => c.id === cardId);
      if (!card) return;
      cardEl.querySelectorAll('[data-fk]').forEach((input) => {
        input.addEventListener('input', () => { if (deps && deps.onDirty) deps.onDirty(domain, card); });
        input.addEventListener('change', () => { if (deps && deps.onDirty) deps.onDirty(domain, card); });
      });
      if (cardEl.querySelector('.settings-secret-toggle')) {
        cardEl.querySelectorAll('.settings-secret-toggle').forEach((btn) => btn.addEventListener('click', () => {
          const inp = cardEl.querySelector(`[data-fk="${btn.dataset.for}"]`);
          if (inp) { const show = inp.type === 'password'; inp.type = show ? 'text' : 'password'; btn.textContent = show ? '🙈' : '👁'; }
        }));
      }
    });
  }

  function collectCardValues(cardEl, card) {
    const out = {};
    (card.fields||[]).forEach((fld) => {
      const el = cardEl.querySelector(`[data-fk="${CSS.escape ? CSS.escape(fld.key) : fld.key}"]`);
      if (!el) return;
      if (fld.type === 'boolean') out[fld.key] = el.checked;
      else if (fld.type === 'number') { const n = Number(el.value); out[fld.key] = Number.isFinite(n) ? n : (fld.default ?? null); }
      else out[fld.key] = el.value;
    });
    return out;
  }
  app.render.collectCardValues = collectCardValues;
  function applyValuesToCard(cardEl, values, card) {
    (card.fields || []).forEach((fld) => { const el = cardEl.querySelector(`[data-fk="${fld.key}"]`); if (!el) return; const v = values[fld.key]; if (fld.type === 'boolean') el.checked = !!v; else el.value = v == null ? '' : String(v); });
  }
  function clearCardValues(cardEl, values, card) { applyValuesToCard(cardEl, values, card); }
  app.render.applyValuesToCard = applyValuesToCard;
  app.render.clearCardValues = clearCardValues;
})(window);
