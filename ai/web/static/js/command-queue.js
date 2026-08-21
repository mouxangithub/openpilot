/**
 * Driving command queue modes — steer / followup / collect.
 */
const CommandQueue = (() => {
  const STORAGE_KEY = 'ai-chat-queue-mode';
  const MODES = ['steer', 'followup', 'collect'];

  function getMode() {
    const v = (localStorage.getItem(STORAGE_KEY) || 'steer').toLowerCase();
    return MODES.includes(v) ? v : 'steer';
  }

  function setMode(mode) {
    const m = String(mode || 'steer').toLowerCase();
    localStorage.setItem(STORAGE_KEY, MODES.includes(m) ? m : 'steer');
    renderBadge();
  }

  function cycleMode() {
    const idx = MODES.indexOf(getMode());
    setMode(MODES[(idx + 1) % MODES.length]);
    return getMode();
  }

  function label(mode) {
    const m = mode || getMode();
    if (m === 'followup') return '排队';
    if (m === 'collect') return '合并';
    return '抢占';
  }

  function describe(mode) {
    const m = mode || getMode();
    if (m === 'followup') return '当前任务完成后逐条处理';
    if (m === 'collect') return '行驶中多条消息合并为一次发送';
    return '取消当前任务并立即发送';
  }

  function renderBadge() {
    const el = document.getElementById('queueModeBadge');
    if (!el) return;
    el.textContent = label();
    el.title = `行驶队列：${label()} — ${describe()}`;
    el.dataset.mode = getMode();
  }

  function bindUi() {
    const el = document.getElementById('queueModeBadge');
    if (!el || el.dataset.bound) return;
    el.dataset.bound = '1';
    el.addEventListener('click', () => {
      const next = cycleMode();
      if (typeof showToast === 'function') {
        showToast(`队列模式：${label(next)}`);
      }
    });
    renderBadge();
  }

  function payloadExtras(driving) {
    if (!driving) return {};
    return { queueMode: getMode() };
  }

  return { getMode, setMode, cycleMode, label, describe, bindUi, renderBadge, payloadExtras };
})();
