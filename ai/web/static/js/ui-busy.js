/**
 * Shared busy states for async buttons and lightweight panel loaders.
 */
const UiBusy = (() => {
  const states = new WeakMap();

  function capture(btn) {
    return {
      html: btn.innerHTML,
      disabled: btn.disabled,
      ariaLabel: btn.getAttribute('aria-label'),
    };
  }

  function setButtonBusy(btn, busy, opts = {}) {
    if (!btn) return;
    const busyLabel = opts.busyLabel;
    if (busy) {
      if (!states.has(btn)) states.set(btn, capture(btn));
      btn.disabled = true;
      btn.classList.add('is-loading');
      btn.setAttribute('aria-busy', 'true');
      if (busyLabel) btn.textContent = busyLabel;
      return;
    }
    btn.classList.remove('is-loading');
    btn.removeAttribute('aria-busy');
    const prev = states.get(btn);
    if (prev) {
      btn.innerHTML = prev.html;
      btn.disabled = prev.disabled;
      if (prev.ariaLabel) btn.setAttribute('aria-label', prev.ariaLabel);
      else btn.removeAttribute('aria-label');
      states.delete(btn);
    } else {
      btn.disabled = false;
    }
  }

  async function withButtonBusy(btn, fn, opts = {}) {
    if (!btn || btn.classList.contains('is-loading')) return undefined;
    setButtonBusy(btn, true, opts);
    try {
      return await fn();
    } finally {
      setButtonBusy(btn, false);
    }
  }

  function setGroupBusy(buttons, busy, opts = {}) {
    (buttons || []).filter(Boolean).forEach((b) => setButtonBusy(b, busy, opts));
  }

  function showPanelLoading(el, message) {
    if (!el) return;
    el.setAttribute('aria-busy', 'true');
    const text = String(message || '…')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
    el.innerHTML = `<p class="panel-loading field-hint">${text}</p>`;
  }

  function clearPanelBusy(el) {
    if (!el) return;
    el.removeAttribute('aria-busy');
  }

  return {
    setButtonBusy,
    withButtonBusy,
    setGroupBusy,
    showPanelLoading,
    clearPanelBusy,
  };
})();
