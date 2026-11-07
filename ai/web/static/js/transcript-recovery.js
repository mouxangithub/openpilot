/**
 * Transcript crash recovery banner (WorkBuddy s09).
 */
const TranscriptRecovery = (() => {
  let api = null;
  let banner = null;

  function tr(key, fallback) {
    return (typeof t === 'function') ? t(key, fallback) : fallback;
  }

  function ensureBanner() {
    if (banner) return banner;
    const thread = document.querySelector('.chat-thread');
    if (!thread) return null;
    banner = document.createElement('div');
    banner.id = 'transcriptRecoveryBanner';
    banner.className = 'transcript-recovery-banner hidden';
    banner.innerHTML = `
      <span class="transcript-recovery-text"></span>
      <button type="button" class="btn small primary transcript-recovery-btn">${tr('transcriptRecoverBtn', '恢复内容')}</button>
      <button type="button" class="btn small ghost transcript-recovery-dismiss">${tr('dismiss', '忽略')}</button>
    `;
    const messages = document.getElementById('messages');
    if (messages) thread.insertBefore(banner, messages);
    else thread.prepend(banner);
    banner.querySelector('.transcript-recovery-dismiss')?.addEventListener('click', () => {
      banner.classList.add('hidden');
    });
    return banner;
  }

  async function checkSession(sessionId) {
    if (!api || !sessionId) return;
    const jobId = typeof SessionStore !== 'undefined' ? SessionStore.getActiveJobId?.(sessionId) : null;
    if (!jobId) return;
    if (typeof ChatJobs !== 'undefined' && ChatJobs.isSessionStreaming?.(sessionId)) return;
    const { data } = await api('GET', `/api/ai/transcript/recover?sessionId=${encodeURIComponent(sessionId)}`);
    if (!data?.ok || !data.recoverable) return;
    const el = ensureBanner();
    if (!el) return;
    const text = el.querySelector('.transcript-recovery-text');
    if (text) {
      text.textContent = tr('transcriptRecoverHint', '检测到未完成的回复，可尝试恢复草稿内容。');
    }
    el.classList.remove('hidden');
    el.querySelector('.transcript-recovery-btn')?.replaceWith(el.querySelector('.transcript-recovery-btn').cloneNode(true));
    el.querySelector('.transcript-recovery-btn')?.addEventListener('click', () => applyRecovery(sessionId, data));
  }

  function applyRecovery(sessionId, data) {
    if (typeof SessionStore === 'undefined') return;
    const session = SessionStore.get?.(sessionId) || SessionStore.list?.().find((s) => s.id === sessionId);
    if (!session) return;
    const msgs = session.messages || [];
    let last = [...msgs].reverse().find((m) => m.role === 'assistant');
    if (!last) {
      last = { role: 'assistant', content: '', tool_calls: [], tool_results: {} };
      msgs.push(last);
    }
    if (data.content) last.content = data.content;
    if (data.reasoning) last.reasoning_content = data.reasoning;
    if (data.toolCalls?.length) {
      last.tool_calls = data.toolCalls.map((tc) => ({
        id: tc.id,
        type: 'function',
        function: { name: tc.name, arguments: tc.arguments || '' },
      }));
      last.tool_results = {};
      for (const tc of data.toolCalls) {
        if (tc.result) last.tool_results[tc.id] = tc.result;
      }
    }
    SessionStore.save?.(sessionId, msgs);
    banner?.classList.add('hidden');
    if (typeof renderMessages === 'function') renderMessages();
  }

  function init(deps = {}) {
    api = deps.api || (typeof WebApi !== 'undefined' ? WebApi.api : null);
    if (typeof SessionStore !== 'undefined') {
      const prev = SessionStore.setActive;
      if (prev && !SessionStore._transcriptRecoveryPatched) {
        SessionStore._transcriptRecoveryPatched = true;
        SessionStore.setActive = function patchedSetActive(id) {
          const r = prev.apply(this, arguments);
          checkSession(id).catch(() => {});
          return r;
        };
      }
    }
  }

  return { init, checkSession, applyRecovery };
})();
