/**
 * Chat message feedback — thumbs up/down, dislike reason modal, /api/ai/feedback.
 */
const MessageFeedback = (() => {
  const REASONS = [
    'misunderstanding',
    'context',
    'unclear',
    'code_error',
    'unprofessional',
    'code_format',
    'other',
  ];

  let deps = {};
  let pendingMsgIdx = null;
  let selectedReason = null;

  function t(key, fallback) {
    return deps.t ? deps.t(key, fallback) : (fallback || key);
  }

  function els() {
    return {
      modal: document.getElementById('feedbackModal'),
      backdrop: document.getElementById('feedbackBackdrop'),
      close: document.getElementById('feedbackClose'),
      submit: document.getElementById('feedbackSubmit'),
      reasons: document.getElementById('feedbackReasons'),
      commentWrap: document.getElementById('feedbackCommentWrap'),
      comment: document.getElementById('feedbackComment'),
    };
  }

  function previewText(msg) {
    if (!msg) return '';
    const content = msg.content;
    if (typeof content === 'string') return content.trim().slice(0, 400);
    if (Array.isArray(content)) {
      return content
        .filter((p) => p?.type === 'text')
        .map((p) => String(p.text || '').trim())
        .join('\n')
        .slice(0, 400);
    }
    return '';
  }

  function updateSubmitState() {
    const ui = els();
    if (!ui.submit) return;
    const needsComment = selectedReason === 'other';
    const commentOk = !needsComment || Boolean(ui.comment?.value?.trim());
    ui.submit.disabled = !selectedReason || !commentOk;
    ui.commentWrap?.classList.toggle('hidden', selectedReason !== 'other');
  }

  function renderReasonChips() {
    const ui = els();
    if (!ui.reasons) return;
    ui.reasons.innerHTML = '';
    for (const reason of REASONS) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'feedback-reason-chip';
      btn.dataset.reason = reason;
      btn.textContent = t(`feedbackReason_${reason}`, reason);
      btn.setAttribute('aria-pressed', 'false');
      btn.addEventListener('click', () => {
        selectedReason = reason;
        ui.reasons.querySelectorAll('.feedback-reason-chip').forEach((chip) => {
          const active = chip.dataset.reason === reason;
          chip.classList.toggle('is-active', active);
          chip.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        updateSubmitState();
      });
      ui.reasons.appendChild(btn);
    }
  }

  function setModalOpen(open) {
    const ui = els();
    deps.setOverlayVisible?.(ui.modal, open);
    if (!open) {
      pendingMsgIdx = null;
      selectedReason = null;
      if (ui.comment) ui.comment.value = '';
      ui.reasons?.querySelectorAll('.feedback-reason-chip').forEach((chip) => {
        chip.classList.remove('is-active');
        chip.setAttribute('aria-pressed', 'false');
      });
      updateSubmitState();
    }
  }

  function openDislikeModal(msgIdx) {
    pendingMsgIdx = msgIdx;
    selectedReason = null;
    renderReasonChips();
    const ui = els();
    if (ui.comment) ui.comment.value = '';
    updateSubmitState();
    setModalOpen(true);
    ui.reasons?.querySelector('.feedback-reason-chip')?.focus();
  }

  function updateButtons(turn, msg) {
    if (!turn) return;
    const rating = msg?.feedback || null;
    turn.querySelectorAll('.msg-action-btn[data-action="like"], .msg-action-btn[data-action="dislike"]').forEach((btn) => {
      const active = (btn.dataset.action === 'like' && rating === 'up')
        || (btn.dataset.action === 'dislike' && rating === 'down');
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  async function submitFeedback({ msgIdx, rating, reason = null, comment = null }) {
    const history = deps.getCurrentMessages?.() || [];
    const msg = history[msgIdx];
    if (!msg || msg.role !== 'assistant') return false;

    const sessionId = deps.SessionStore?.activeId;
    if (!sessionId) {
      deps.showToast?.(t('feedbackNoSession', 'No active session'), 'warning');
      return false;
    }

    const userMsg = history[msgIdx - 1];
    const body = {
      sessionId,
      messageIndex: msgIdx,
      rating,
      reason,
      comment,
      resolvedModel: msg.resolvedModel || null,
      messagePreview: previewText(msg),
      userPreview: userMsg?.role === 'user' ? previewText(userMsg) : null,
    };

    try {
      const res = await deps.api('POST', '/api/ai/feedback', body);
      if (!res?.data?.ok) {
        deps.showToast?.(res?.data?.error || t('feedbackSubmitFailed', 'Failed to submit feedback'), 'error');
        return false;
      }
    } catch {
      deps.showToast?.(t('feedbackSubmitFailed', 'Failed to submit feedback'), 'error');
      return false;
    }

    msg.feedback = rating;
    msg.feedbackReason = rating === 'down' ? reason : null;
    msg.feedbackComment = rating === 'down' ? (comment || null) : null;
    msg.feedbackAt = rating ? Date.now() : null;
    deps.saveCurrentMessages?.(history);

    const turn = document.getElementById('messages')?.querySelector(`.message-turn[data-msg-idx="${msgIdx}"]`);
    updateButtons(turn, msg);

    if (rating === 'up') {
      deps.showToast?.(t('feedbackThanks', 'Thanks for your feedback'), 'success');
    } else if (rating === 'down') {
      deps.showToast?.(t('feedbackSubmitted', 'Feedback submitted'), 'success');
    }
    return true;
  }

  async function handleLike(msgIdx) {
    const history = deps.getCurrentMessages?.() || [];
    const msg = history[msgIdx];
    if (!msg) return;
    const next = msg.feedback === 'up' ? null : 'up';
    await submitFeedback({ msgIdx, rating: next });
  }

  async function handleDislike(msgIdx) {
    const history = deps.getCurrentMessages?.() || [];
    const msg = history[msgIdx];
    if (!msg) return;
    if (msg.feedback === 'down') {
      await submitFeedback({ msgIdx, rating: null });
      return;
    }
    openDislikeModal(msgIdx);
  }

  async function submitPendingDislike() {
    if (pendingMsgIdx == null || !selectedReason) return;
    const ui = els();
    const comment = selectedReason === 'other' ? (ui.comment?.value?.trim() || '') : null;
    if (selectedReason === 'other' && !comment) {
      updateSubmitState();
      return;
    }
    const ok = await submitFeedback({
      msgIdx: pendingMsgIdx,
      rating: 'down',
      reason: selectedReason,
      comment,
    });
    if (ok) setModalOpen(false);
  }

  function bindModal() {
    const ui = els();
    ui.backdrop?.addEventListener('click', () => setModalOpen(false));
    ui.close?.addEventListener('click', () => setModalOpen(false));
    ui.submit?.addEventListener('click', () => { submitPendingDislike(); });
    ui.comment?.addEventListener('input', updateSubmitState);
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && ui.modal?.classList.contains('is-open')) {
        setModalOpen(false);
      }
    });
  }

  function init(options = {}) {
    deps = options;
    bindModal();
    renderReasonChips();
  }

  function refreshTranslations() {
    renderReasonChips();
    const ui = els();
    const title = ui.modal?.querySelector('[data-i18n="feedbackTitle"]');
    if (title) title.textContent = t('feedbackTitle', 'Why was this unhelpful?');
  }

  return {
    REASONS,
    init,
    refreshTranslations,
    updateButtons,
    handleLike,
    handleDislike,
  };
})();
