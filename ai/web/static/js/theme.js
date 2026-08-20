/**
 * Theme helper for the AI and Cabana web UIs.
 *
 * Modes:
 *   - auto: follow prefers-color-scheme (default)
 *   - light / dark: manual override
 *
 * Toggle cycles: auto → light → dark → auto
 */

(function (global) {
  'use strict';

  const STORAGE_KEY = 'ui_theme';
  const THEME_AUTO = 'auto';
  const THEME_LIGHT = 'light';
  const THEME_DARK = 'dark';

  function getSystemTheme() {
    if (global.matchMedia && global.matchMedia('(prefers-color-scheme: light)').matches) {
      return THEME_LIGHT;
    }
    return THEME_DARK;
  }

  function getMode() {
    try {
      const stored = global.localStorage.getItem(STORAGE_KEY);
      if (stored === THEME_LIGHT || stored === THEME_DARK || stored === THEME_AUTO) {
        return stored;
      }
    } catch (e) {}
    return THEME_AUTO;
  }

  function resolveTheme() {
    const mode = getMode();
    if (mode === THEME_LIGHT || mode === THEME_DARK) return mode;
    return getSystemTheme();
  }

  function apply(theme) {
    document.documentElement.setAttribute('data-theme', theme);
  }

  function get() {
    return document.documentElement.getAttribute('data-theme') || THEME_DARK;
  }

  function notifyChange() {
    try {
      global.dispatchEvent(new CustomEvent('themechange'));
    } catch (e) {}
  }

  function set(theme) {
    if (theme !== THEME_LIGHT && theme !== THEME_DARK && theme !== THEME_AUTO) return;
    try { global.localStorage.setItem(STORAGE_KEY, theme); } catch (e) {}
    apply(theme === THEME_AUTO ? getSystemTheme() : theme);
    notifyChange();
  }

  function toggle() {
    const mode = getMode();
    if (mode === THEME_AUTO) set(THEME_LIGHT);
    else if (mode === THEME_LIGHT) set(THEME_DARK);
    else set(THEME_AUTO);
  }

  function init() {
    apply(resolveTheme());
    if (global.matchMedia) {
      const mq = global.matchMedia('(prefers-color-scheme: dark)');
      const onSystemChange = () => {
        if (getMode() === THEME_AUTO) {
          apply(getSystemTheme());
          notifyChange();
        }
      };
      if (typeof mq.addEventListener === 'function') {
        mq.addEventListener('change', onSystemChange);
      } else if (typeof mq.addListener === 'function') {
        mq.addListener(onSystemChange);
      }
    }
  }

  global.Theme = {
    init,
    get,
    getMode,
    set,
    toggle,
    THEME_AUTO,
    THEME_LIGHT,
    THEME_DARK,
  };
})(typeof window !== 'undefined' ? window : globalThis);
