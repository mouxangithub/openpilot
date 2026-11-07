/**
 * Password input with optional reveal toggle (eye icon).
 */
const PasswordField = (() => {
  function label(key, fallback) {
    return (typeof t === 'function') ? t(key, fallback) : fallback;
  }

  function revealButtonHtml(inputId) {
    const id = String(inputId || '').replace(/"/g, '');
    return `<button type="button" class="password-reveal" data-password-for="${id}" aria-label="${label('showPassword', '显示')}" title="${label('showPassword', '显示')}">
      <svg class="icon-svg eye-closed" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>
      <svg class="icon-svg eye-open hidden" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
    </button>`;
  }

  function wrapInput(inputId, attrs = '') {
    const id = String(inputId || '');
    return `<div class="password-field"><input type="password" id="${id}" autocomplete="off" spellcheck="false" ${attrs}>${revealButtonHtml(id)}</div>`;
  }

  function bind(root) {
    const scope = root && root.querySelectorAll ? root : document;
    const nodes = root && root.querySelectorAll
      ? scope.querySelectorAll('.password-reveal[data-password-for]')
      : document.querySelectorAll('.password-reveal[data-password-for]');
    nodes.forEach((btn) => {
      if (btn.dataset.bound === '1') return;
      btn.dataset.bound = '1';
      const inputId = btn.getAttribute('data-password-for');
      const input = document.getElementById(inputId);
      if (!input) return;
      const eyeOpen = btn.querySelector('.eye-open');
      const eyeClosed = btn.querySelector('.eye-closed');
      const sync = (visible) => {
        input.type = visible ? 'text' : 'password';
        btn.setAttribute('aria-pressed', visible ? 'true' : 'false');
        const show = label('showPassword', '显示');
        const hide = label('hidePassword', '隐藏');
        btn.title = visible ? hide : show;
        btn.setAttribute('aria-label', btn.title);
        eyeOpen?.classList.toggle('hidden', !visible);
        eyeClosed?.classList.toggle('hidden', visible);
      };
      sync(input.type === 'text');
      btn.addEventListener('click', () => sync(input.type === 'password'));
    });
  }

  function enhanceInput(input) {
    if (!input || input.closest('.password-field')) return input;
    const id = input.id || `pwd-${Math.random().toString(36).slice(2, 9)}`;
    if (!input.id) input.id = id;
    if (input.type !== 'password' && input.type !== 'text') input.type = 'password';
    const wrap = document.createElement('div');
    wrap.className = 'password-field';
    const parent = input.parentNode;
    parent.insertBefore(wrap, input);
    wrap.appendChild(input);
    wrap.insertAdjacentHTML('beforeend', revealButtonHtml(id));
    bind(wrap);
    return input;
  }

  return { wrapInput, revealButtonHtml, enhanceInput, bind };
})();
