/**
 * Chat job streaming — multi-session concurrent jobs, poll fallback, attach on refresh.
 */
const ChatJobs = (() => {
  let deps = {};
  const contexts = new Map();

  function init(d) {
    deps = d;
    if (typeof document !== 'undefined' && !document.__opChatVisibilityBound) {
      document.__opChatVisibilityBound = true;
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState !== 'visible') return;
        scheduleSweepAllPendingJobs();
        for (const ctx of contexts.values()) {
          if (!ctx?.ui?.content || !ctx.assistantMessage?.content) continue;
          if (!ctx.isVisible?.()) continue;
          const streaming = !ctx.cancelled;
          renderChatMarkdown(ctx.ui.content, ctx.assistantMessage.content, { streaming });
          if (streaming) ctx.ui.content.classList.add('streaming');
        }
      });
    }
  }

  function getActiveJobId() {
    const sessionId = deps.SessionStore?.activeId;
    if (!sessionId) return null;
    return deps.SessionStore?.getActiveJobId(sessionId) || null;
  }

  function setActiveJobId(id) {
    const sessionId = deps.SessionStore?.activeId;
    if (sessionId && id) deps.SessionStore?.setActiveJobId(sessionId, id);
  }

  function hasActiveCtx(sessionId) {
    if (!sessionId) return false;
    for (const ctx of contexts.values()) {
      if (ctx.sessionId === sessionId && !ctx.cancelled) return true;
    }
    return false;
  }

  /** Live stream in memory — used to lock composer re-render during token streaming. */
  function isSessionStreaming(sessionId) {
    return hasActiveCtx(sessionId);
  }

  /** Sidebar / stop button — job id or live ctx (may be stale until verified). */
  function isSessionJobPending(sessionId) {
    if (!sessionId) return false;
    if (hasActiveCtx(sessionId)) return true;
    return Boolean(deps.SessionStore?.getActiveJobId(sessionId));
  }

  function isSessionRunning(sessionId) {
    return isSessionJobPending(sessionId);
  }

  const staleJobSweepTimers = new Map();
  let sweepAllPendingTimer = null;

  function purgeSessionCtxs(sessionId, jobId) {
    if (!sessionId && !jobId) return;
    for (const [key, ctx] of [...contexts.entries()]) {
      const match = (sessionId && ctx.sessionId === sessionId)
        || (jobId && key === jobId)
        || (sessionId && key === `pending:${sessionId}`);
      if (!match) continue;
      ctx.cancelled = true;
      clearCtxPoll(ctx);
      if (ctx.mdRenderTimer) {
        clearTimeout(ctx.mdRenderTimer);
        ctx.mdRenderTimer = null;
      }
      contexts.delete(key);
    }
  }

  function scheduleSweepAllPendingJobs() {
    if (sweepAllPendingTimer) return;
    sweepAllPendingTimer = setTimeout(async () => {
      sweepAllPendingTimer = null;
      const sessions = deps.SessionStore?.listWithContent?.() || deps.SessionStore?.list?.() || [];
      for (const s of sessions) {
        const sid = s.id;
        if (!sid) continue;
        if (hasActiveCtx(sid)) continue;
        if (!deps.SessionStore?.getActiveJobId(sid)) continue;
        await verifySessionJobId(sid);
      }
      deps.renderSessionList?.();
      deps.updateComposerSendBtn?.();
    }, 80);
  }

  function scheduleStaleJobSweep(sessionId) {
    if (!sessionId || hasActiveCtx(sessionId)) return;
    const jobId = deps.SessionStore?.getActiveJobId(sessionId);
    if (!jobId) return;
    if (staleJobSweepTimers.has(sessionId)) return;
    staleJobSweepTimers.set(sessionId, setTimeout(() => {
      staleJobSweepTimers.delete(sessionId);
      verifySessionJobId(sessionId).catch(() => {});
    }, 60));
  }

  async function verifySessionJobId(sessionId) {
    if (!sessionId) return false;
    if (hasActiveCtx(sessionId)) return true;
    const jobId = deps.SessionStore?.getActiveJobId(sessionId);
    if (!jobId) return false;

    try {
      const { data } = await deps.api('GET', `/api/ai/chat/jobs/${encodeURIComponent(jobId)}?since=0`);
      if (!data?.ok) {
        deps.SessionStore?.clearActiveJobId(sessionId);
        deps.renderSessionList?.();
        deps.updateComposerSendBtn?.();
        return false;
      }
      if (data.status === 'running') return true;

      if (['done', 'error', 'cancelled'].includes(data.status)) {
        await applyTerminalJobState(jobId, sessionId, findCtx(jobId, sessionId), data.status, data);
      } else {
        deps.SessionStore?.clearActiveJobId(sessionId);
      }
      deps.renderSessionList?.();
      deps.updateComposerSendBtn?.();
      if (deps.SessionStore?.activeId === sessionId) {
        deps.renderStoredMessages?.({ force: true, forceScroll: true });
      }
      return false;
    } catch {
      deps.SessionStore?.clearActiveJobId(sessionId);
      deps.renderSessionList?.();
      deps.updateComposerSendBtn?.();
      return false;
    }
  }

  function findCtx(jobId, sessionId) {
    let ctx = contexts.get(jobId);
    if (ctx) return ctx;
    const pendingKey = `pending:${sessionId}`;
    ctx = contexts.get(pendingKey);
    if (ctx) return ctx;
    for (const [, candidate] of contexts.entries()) {
      if (candidate.sessionId === sessionId) return candidate;
    }
    return null;
  }

  function registerCtx(jobId, sessionId, ctx) {
    contexts.delete(`pending:${sessionId}`);
    contexts.set(jobId, ctx);
    deps.renderSessionList?.();
    deps.updateComposerSendBtn?.();
  }

  function makeCtxBase(sessionId) {
    return {
      sessionId,
      cancelled: false,
      isVisible: () => deps.SessionStore?.activeId === sessionId,
      jobActive: () => !ctxCancelled(this),
    };
  }

  function ctxCancelled(ctx) {
    return Boolean(ctx?.cancelled);
  }

  function clearCtxPoll(ctx) {
    if (ctx?.pollTimer) {
      clearTimeout(ctx.pollTimer);
      ctx.pollTimer = null;
    }
    ctx._pollActive = false;
  }

  function renderChatMarkdown(el, text, options) {
    if (!el) return;
    const clean = typeof deps.stripLeakedToolCalls === 'function'
      ? deps.stripLeakedToolCalls(text || '')
      : (text || '');
    if (!clean) {
      el.textContent = '';
      return;
    }
    const streaming = Boolean(options && options.streaming);
    if (typeof Markdown !== 'undefined' && typeof Markdown.renderToElement === 'function') {
      Markdown.renderToElement(el, clean, { streaming });
      return;
    }
    if (typeof deps.renderMarkdownContent === 'function') {
      deps.renderMarkdownContent(el, clean);
      return;
    }
    el.textContent = clean;
  }

  function scheduleMarkdownRender(ui, text, ctx) {
    if (!ui?.content || !text) return;
    if (ctx.mdRenderTimer) clearTimeout(ctx.mdRenderTimer);
    ctx.mdRenderTimer = setTimeout(() => {
      ctx.mdRenderTimer = null;
      renderChatMarkdown(ui.content, text, { streaming: true });
      ui.content?.classList.add('streaming');
      if (ctx.isVisible?.()) deps.scrollToBottom?.();
    }, 80);
  }

  function flushMarkdownRender(ui, text, ctx) {
    if (ctx?.mdRenderTimer) {
      clearTimeout(ctx.mdRenderTimer);
      ctx.mdRenderTimer = null;
    }
    if (!ui?.content) return;
    renderChatMarkdown(ui.content, text, { streaming: false });
    ui.content?.classList.remove('streaming');
  }

  function abortSession(sessionId) {
    if (!sessionId) return;
    const jobId = deps.SessionStore?.getActiveJobId(sessionId);
    for (const [key, ctx] of [...contexts.entries()]) {
      if (ctx.sessionId !== sessionId) continue;
      ctx.cancelled = true;
      clearCtxPoll(ctx);
      if (ctx.mdRenderTimer) {
        clearTimeout(ctx.mdRenderTimer);
        ctx.mdRenderTimer = null;
      }
      if (ctx.isVisible?.() && ctx.ui) {
        flushMarkdownRender(ctx.ui, ctx.assistantMessage?.content || '', ctx);
        deps.hideAssistantLoading?.(ctx.ui);
        deps.clearLiveStreamChrome?.(ctx.ui);
        if (deps.assistantMessageHasContent?.(ctx.assistantMessage)) {
          deps.finishAssistant?.(ctx.ui, ctx.assistantMessage, ctx.sessionId);
        }
      }
      contexts.delete(key);
    }
    if (jobId) {
      deps.api('DELETE', `/api/ai/chat/jobs/${encodeURIComponent(jobId)}`).catch(() => {});
      deps.SessionStore?.clearActiveJobId(sessionId);
      deps.syncSessionsToDevice?.().catch(() => {});
    }
    if (deps.SessionStore?.activeId === sessionId) {
      deps.setAbortController?.(null);
      deps.setStreamSessionId?.(null);
      deps.endChatStream?.(sessionId);
    }
    deps.renderSessionList?.();
    deps.updateComposerSendBtn?.();
  }

  function abortActive() {
    abortSession(deps.SessionStore?.activeId);
  }

  function endPoll() {
    for (const ctx of contexts.values()) clearCtxPoll(ctx);
  }

  async function handleStreamEvent(data, ctx) {
    if (ctxCancelled(ctx)) return 'stop';
    const visible = typeof ctx.isVisible === 'function' ? ctx.isVisible() : false;
    const ui = visible ? deps.reconcileStreamUi(ctx) : ctx.ui;
    const { assistantMessage } = ctx;

    if (visible) deps.handleAgentStreamEvent?.(data, ctx);

    if (data.type === 'error') {
      assistantMessage.content = deps.formatApiError(data.error);
      if (visible && ui?.content) {
        deps.hideAssistantLoading?.(ui);
        ui.content.textContent = assistantMessage.content;
      }
      return 'error';
    }

    if (data.type === 'reasoning') {
      assistantMessage.reasoning_content += data.delta || '';
      if (visible && ui) {
        deps.hideAssistantLoading?.(ui);
        if (!ctx.thinkingStarted) {
          ctx.thinkingStarted = true;
          ui.thinking?.classList.remove('hidden');
          deps.setDetailsCollapsed?.(ui.thinking, false);
          if (ui.thinkingLabel) ui.thinkingLabel.textContent = deps.t('thinkingActive', 'Thinking…');
        }
        if (ui.thinkingBody) renderThinkingContent(ui.thinkingBody, assistantMessage.reasoning_content);
        deps.scrollToBottom?.();
      }
    }

    if (data.type === 'content') {
      ctx.contentStarted = true;
      ctx.rawContent = (ctx.rawContent || '') + (data.delta || '');
      const clean = typeof deps.stripLeakedToolCalls === 'function'
        ? deps.stripLeakedToolCalls(ctx.rawContent)
        : ctx.rawContent;
      ctx.displayedContentLen = clean.length;
      assistantMessage.content = clean;
      if (visible && ui) {
        deps.hideAssistantLoading?.(ui);
        if (ctx.thinkingStarted) {
          deps.setDetailsCollapsed?.(ui.thinking, true);
          if (ui.thinkingLabel) ui.thinkingLabel.textContent = deps.t('thinking', 'Thinking');
        }
        if (clean) scheduleMarkdownRender(ui, clean, ctx);
        else if (ui.content) ui.content.textContent = '';
      }
    }

    if (data.type === 'tool_call') {
      if (!assistantMessage.tool_calls.some((tc) => tc.id === data.id)) {
        assistantMessage.tool_calls.push({
          id: data.id,
          type: 'function',
          function: { name: data.name, arguments: data.arguments },
        });
      }
      if (visible && ui) {
        deps.hideAssistantLoading?.(ui);
        if (ctx.thinkingStarted) {
          deps.setDetailsCollapsed?.(ui.thinking, true);
          if (ui.thinkingLabel) ui.thinkingLabel.textContent = deps.t('thinking', 'Thinking');
        } else {
          ui.thinking?.classList.add('hidden');
        }
        ui.toolsBlock?.classList.remove('hidden');
        deps.setDetailsCollapsed?.(ui.toolsBlock, true);
        deps.renderToolCall?.(ui.toolsList, data.id, data.name, data.arguments, null, data.agentId || data.agent_id, {
          subagent: !!data.subagent,
        });
        deps.updateToolCallsSummary?.(ui.toolsBlock);
      }
    }

    if (data.type === 'tool_result') {
      let result = data.result;
      if (result?.needs_confirmation && result.pending_id && visible) {
        let confirmed = { ok: false, cancelled: true };
        if (typeof deps.showWriteConfirmModal === 'function') {
          confirmed = await deps.showWriteConfirmModal(result.preview, result.pending_id, result);
        } else {
          const res = await deps.api('POST', '/api/ai/write/confirm', { pending_id: result.pending_id });
          confirmed = res.data;
        }
        result = confirmed;
      }
      assistantMessage.tool_results[data.id] = result;
      if (visible && ui) {
        deps.hideAssistantLoading?.(ui);
        deps.updateToolCallResult?.(ui.toolsList, data.id, result);
      }
    }

    if (data.type === 'canvas' && typeof CanvasPanel !== 'undefined') {
      CanvasPanel.addArtifact(ctx.sessionId, data.artifact);
    }

    if (data.type === 'usage' && visible && ui) {
      assistantMessage.usage = data.usage;
      deps.renderUsage?.(ui, data.usage);
      if (deps.els?.settingsSidebar?.classList.contains('open')) deps.loadUsage?.();
      if (typeof OfficePanel !== 'undefined' && OfficePanel.isOpen()) {
        OfficePanel.setUsageTokens(data.usage?.total_tokens || 0);
      }
    }

    if (data.type === 'trace' && data.message) {
      if (visible && ui) {
        deps.appendTraceLine?.(ui, data.message, data.round);
      } else {
        console.debug(`[chat trace ${data.round ?? '?'}]`, data.message);
      }
    }

    if (data.type === 'done') {
      if (data.resolvedModel) {
        assistantMessage.resolvedModel = data.resolvedModel;
      }
      if (visible && ui) {
        deps.hideAssistantLoading?.(ui);
        deps.syncThinkingBlock?.(ui, assistantMessage);
        flushMarkdownRender(ui, assistantMessage.content, ctx);
        if (data.resolvedModel) deps.setMessageModelTag?.(ui, data.resolvedModel);
        deps.renderMessageFooter?.(ui, { usage: assistantMessage.usage, resolvedModel: data.resolvedModel });
      }
      if (data.resolvedModel && visible) deps.updateModelBadge?.(data.resolvedModel);
    }

    if (['content', 'reasoning', 'tool_call', 'tool_result'].includes(data.type) && !ctxCancelled(ctx)) {
      deps.savePartialAssistant?.(ctx.sessionId, assistantMessage);
    }

    return 'continue';
  }

  async function finalizeCtx(jobId, sessionId, ctx, status, payload = {}) {
    const visible = ctx && typeof ctx.isVisible === 'function' ? ctx.isVisible() : false;
    if (ctx) {
      contexts.delete(jobId);
      clearCtxPoll(ctx);
      if (visible && ctx.ui) {
        flushMarkdownRender(ctx.ui, ctx.assistantMessage?.content || '', ctx);
        deps.clearLiveStreamChrome?.(ctx.ui);
      }
    }

    const assistant = deps.normalizeStoredMessage({
      role: 'assistant',
      ...(payload.assistant || ctx?.assistantMessage || {}),
    });
    if (payload.resolvedModel) assistant.resolvedModel = payload.resolvedModel;

    if (status === 'error') {
      assistant.content = deps.formatApiError(payload.error || assistant.content || 'Error');
    }

    if (status === 'cancelled') {
      if (visible && ctx?.ui?.wrapper?.isConnected && !deps.assistantMessageHasContent?.(assistant)) {
        ctx.ui.wrapper.remove();
      } else if (deps.assistantMessageHasContent?.(assistant)) {
        deps.commitAssistantMessage?.(sessionId, assistant);
      }
    } else if (status === 'done' || status === 'error') {
      const hasContent = deps.assistantMessageHasContent?.(assistant) || status === 'error';
      if (hasContent) {
        if (visible && ctx?.ui) {
          deps.finishAssistant?.(ctx.ui, assistant, sessionId);
        } else {
          deps.commitAssistantMessage?.(sessionId, assistant);
        }
      }
    }

    deps.SessionStore?.clearActiveJobId(sessionId);
    purgeSessionCtxs(sessionId, jobId);
    if (visible && deps.SessionStore?.activeId === sessionId) {
      deps.setAbortController?.(null);
      deps.endChatStream?.(sessionId);
    }
    deps.renderSessionList?.();
    deps.updateComposerSendBtn?.();
    deps.syncSessionsToDevice?.().catch(() => {});
  }

  function pollDelayMs() {
    return deps.isSyncWsConnected?.() ? 1200 : 400;
  }

  async function applyTerminalJobState(jobId, sessionId, ctx, status, payload = {}) {
    if (ctx) {
      await finalizeCtx(jobId, sessionId, ctx, status, payload);
      return;
    }
    contexts.delete(jobId);
    if (status === 'done' || status === 'error') {
      const assistant = deps.normalizeStoredMessage({
        role: 'assistant',
        content: '',
        reasoning_content: '',
        tool_calls: [],
        tool_results: {},
        ...(payload.assistant || {}),
      });
      if (payload.resolvedModel) assistant.resolvedModel = payload.resolvedModel;
      if (status === 'error') {
        assistant.content = deps.formatApiError(payload.error || assistant.content || 'Error');
      }
      if (deps.assistantMessageHasContent?.(assistant)) {
        deps.commitAssistantMessage?.(sessionId, assistant);
        if (deps.SessionStore?.activeId === sessionId) deps.renderStoredMessages?.();
      }
    }
    deps.SessionStore?.clearActiveJobId(sessionId);
    purgeSessionCtxs(sessionId, jobId);
    if (deps.SessionStore?.activeId === sessionId) {
      deps.endChatStream?.(sessionId);
      deps.updateComposerSendBtn?.();
    }
    deps.renderSessionList?.();
    deps.syncSessionsToDevice?.().catch(() => {});
  }

  function ensureBackgroundCtx(sessionId, jobId, initialData = {}) {
    let ctx = findCtx(jobId, sessionId);
    if (ctx) return ctx;
    const assistantMessage = deps.normalizeStoredMessage({
      role: 'assistant',
      content: '',
      reasoning_content: '',
      tool_calls: [],
      tool_results: {},
      agent_events: [],
      ...(initialData.assistant || {}),
    });
    const since = initialData.nextSince || 0;
    ctx = {
      ui: null,
      assistantMessage,
      sessionId,
      cancelled: false,
      isVisible: () => deps.SessionStore?.activeId === sessionId,
      thinkingStarted: Boolean(assistantMessage.reasoning_content),
      contentStarted: Boolean(assistantMessage.content),
      rawContent: assistantMessage.content || '',
      displayedContentLen: (assistantMessage.content || '').length,
      since,
      lastSeq: since,
    };
    registerCtx(jobId, sessionId, ctx);
    return ctx;
  }

  async function handleSyncWsEvent(payload) {
    const { jobId, sessionId, event, status } = payload;
    let ctx = findCtx(jobId, sessionId);
    if (ctx && !contexts.has(jobId)) registerCtx(jobId, sessionId, ctx);

    if (!ctx && (status === 'running' || event)) {
      deps.SessionStore?.setActiveJobId(sessionId, jobId);
      if (deps.SessionStore?.activeId === sessionId) {
        await attach(sessionId, jobId, {
          assistant: payload.assistant,
          events: event ? [event] : [],
          nextSince: payload.nextSince || 0,
          status: status || 'running',
        });
        ctx = findCtx(jobId, sessionId);
      } else {
        ctx = ensureBackgroundCtx(sessionId, jobId, payload);
        if (!ctx._pollActive) watch(jobId, sessionId, ctx);
      }
    }

    if (!ctx) {
      if (['done', 'error', 'cancelled'].includes(status)) {
        await applyTerminalJobState(jobId, sessionId, null, status, payload);
      }
      return;
    }

    if (event) {
      const seq = event._seq || 0;
      if (seq <= (ctx.lastSeq || 0)) {
        if (['done', 'error', 'cancelled'].includes(status)) {
          await finalizeCtx(jobId, sessionId, ctx, status, payload);
        }
        return;
      }
      ctx.lastSeq = seq;
      const result = await handleStreamEvent(event, ctx);
      if (result === 'error') {
        await finalizeCtx(jobId, sessionId, ctx, 'error', payload);
        return;
      }
    }

    if (['done', 'error', 'cancelled'].includes(status)) {
      await finalizeCtx(jobId, sessionId, ctx, status, payload);
    }
  }

  function watch(jobId, sessionId, ctx) {
    ctx.lastSeq = Math.max(ctx.lastSeq || 0, ctx.since || 0);
    ctx.since = ctx.lastSeq;
    ctx._pollActive = false;
    registerCtx(jobId, sessionId, ctx);
    poll(jobId, sessionId, ctx);
  }

  function poll(jobId, sessionId, ctx) {
    if (ctx._pollActive) return;
    ctx._pollActive = true;
    let since = ctx.since || 0;
    let finished = false;

    const tick = async () => {
      if (finished || ctxCancelled(ctx)) return;

      try {
        const { data } = await deps.api('GET', `/api/ai/chat/jobs/${encodeURIComponent(jobId)}?since=${since}`);
        if (!data?.ok) {
          if (deps.SessionStore?.getActiveJobId(sessionId) === jobId) {
            deps.SessionStore?.clearActiveJobId(sessionId);
            if (deps.SessionStore?.activeId === sessionId) deps.endChatStream?.(sessionId);
          }
          finished = true;
          contexts.delete(jobId);
          deps.renderSessionList?.();
          return;
        }

        for (const ev of data.events || []) {
          since = Math.max(since, ev._seq || since);
          ctx.since = since;
          ctx.lastSeq = since;
          const result = await handleStreamEvent(ev, ctx);
          if (result === 'error') {
            finished = true;
            await applyTerminalJobState(jobId, sessionId, ctx, 'error', data);
            return;
          }
          if (result === 'stop') break;
        }

        if (!ctxCancelled(ctx)) {
          deps.savePartialAssistant?.(sessionId, ctx.assistantMessage);
        }

        if (['done', 'error', 'cancelled'].includes(data.status)) {
          finished = true;
          await applyTerminalJobState(jobId, sessionId, ctx, data.status, data);
          return;
        }

        ctx.pollTimer = setTimeout(tick, pollDelayMs());
      } catch {
        if (!finished && !ctxCancelled(ctx)) {
          ctx.pollTimer = setTimeout(tick, pollDelayMs());
        }
      }
    };

    tick();
  }

  async function stream(messages) {
    const sessionId = deps.SessionStore.activeId;
    if (!sessionId) return;
    if (isSessionRunning(sessionId)) return;

    deps.setStreamSessionId?.(sessionId);
    const abortController = { cancelled: false };
    deps.setAbortController?.(abortController);
    deps.updateComposerSendBtn?.();

    const hasImages = messages.some(
      (m) => m.role === 'user' && Array.isArray(m.content) && m.content.some((p) => p.type === 'image_url'),
    );
    const useTools = !hasImages;
    const workflowId = deps.consumePendingWorkflow?.() || '';
    const agentId = deps.consumePendingAgentId?.() || '';
    const compact = deps.consumePendingCompact?.() || false;
    const consumerMode = deps.consumePendingConsumerMode?.() || false;
    const debug = deps.getChatDebugPrefs?.() || {};
    const chatRoute = typeof SessionModelPicker !== 'undefined'
      ? SessionModelPicker.getChatRouteForSend(sessionId)
      : null;

    const ui = deps.appendAssistantMessage();
    deps.showAssistantLoading(ui);
    deps.markLiveStreamUi(ui);
    const assistantMessage = {
      role: 'assistant',
      content: '',
      reasoning_content: '',
      tool_calls: [],
      tool_results: {},
      agent_events: [],
    };

    const ctx = {
      ui,
      assistantMessage,
      sessionId,
      cancelled: false,
      isVisible: () => deps.SessionStore?.activeId === sessionId,
      thinkingStarted: false,
      contentStarted: false,
      rawContent: '',
      displayedContentLen: 0,
      since: 0,
    };
    contexts.set(`pending:${sessionId}`, ctx);

    try {
      const idempotencyKey = `send-${sessionId}-${Date.now()}`;
      const queueExtras = (typeof CommandQueue !== 'undefined' && deps.getState?.()?.driving)
        ? CommandQueue.payloadExtras(true)
        : {};
      const body = {
        sessionId,
        idempotencyKey,
        messages: deps.prepareMessagesForApi(messages),
        tools: useTools,
        mode: deps.chatMode || 'unlimited',
        workflow: workflowId || undefined,
        agentId: agentId || undefined,
        consumerMode: consumerMode || undefined,
        compact: compact || undefined,
        verbose: !!debug.verbose,
        trace: !!debug.trace,
        maxToolRounds: 'infinite',
        ...queueExtras,
      };
      if (chatRoute) body.chatRoute = chatRoute;
      if (typeof WorkbuddyPanel !== 'undefined') {
        const tier = WorkbuddyPanel.getModelTier?.();
        if (tier && tier !== 'auto') body.modelTier = tier;
      }

      const { data: startData } = await deps.api('POST', '/api/ai/chat/jobs', body);

      if (!startData?.ok) {
        contexts.delete(`pending:${sessionId}`);
        if (!ctx.isVisible()) return;
        deps.hideAssistantLoading(ui);
        ui.content.textContent = deps.formatApiError(startData?.error || 'Failed to start chat job');
        assistantMessage.content = ui.content.textContent;
        deps.finishAssistant(ui, assistantMessage, sessionId);
        deps.endChatStream?.(sessionId);
        deps.updateComposerSendBtn?.();
        return;
      }

      if (startData.queued || startData.action === 'collected') {
        contexts.delete(`pending:${sessionId}`);
        if (!ctx.isVisible()) return;
        deps.hideAssistantLoading(ui);
        const pos = startData.queuePosition || startData.collectBatch || '?';
        const msg = startData.action === 'collected'
          ? `已合并入批处理队列（${pos} 条）`
          : `已加入行驶队列（位置 ${pos}）`;
        ui.content.textContent = msg;
        assistantMessage.content = ui.content.textContent;
        deps.finishAssistant(ui, assistantMessage, sessionId);
        deps.endChatStream?.(sessionId);
        deps.updateComposerSendBtn?.();
        deps.showToast?.('消息已排队，当前任务完成后继续');
        return;
      }

      if (!startData.jobId) {
        contexts.delete(`pending:${sessionId}`);
        if (!ctx.isVisible()) return;
        deps.hideAssistantLoading(ui);
        ui.content.textContent = deps.formatApiError('Failed to start chat job');
        assistantMessage.content = ui.content.textContent;
        deps.finishAssistant(ui, assistantMessage, sessionId);
        deps.endChatStream?.(sessionId);
        deps.updateComposerSendBtn?.();
        return;
      }

      const jobId = startData.jobId;
      deps.SessionStore.setActiveJobId(sessionId, jobId);
      deps.syncSessionsToDevice?.().catch(() => {});
      deps.renderSessionList?.();
      watch(jobId, sessionId, ctx);
    } catch (err) {
      contexts.delete(`pending:${sessionId}`);
      if (ctx.isVisible()) {
        deps.hideAssistantLoading(ui);
        ui.content.textContent = `Error: ${err.message}`;
        assistantMessage.content = ui.content.textContent;
        deps.finishAssistant(ui, assistantMessage, sessionId);
      } else if (ui.wrapper?.isConnected) {
        ui.wrapper.remove();
      }
      deps.endChatStream?.(sessionId);
      deps.updateComposerSendBtn?.();
    }
  }

  async function attach(sessionId, jobId, initialData) {
    const existingCtx = findCtx(jobId, sessionId);
    if (existingCtx?._pollActive) return;

    const messages = deps.getSessionMessages?.(sessionId) || deps.getCurrentMessages?.() || [];
    const serverAssistant = initialData?.assistant
      ? deps.normalizeStoredMessage({ role: 'assistant', ...initialData.assistant })
      : null;

    let ui = deps.resolveAttachAssistantUi?.(messages, sessionId);
    if (!ui) {
      const verified = await verifySessionJobId(sessionId);
      if (!verified) return;
      ui = deps.resolveAttachAssistantUi?.(messages, sessionId);
      if (!ui && deps.SessionStore?.getActiveJobId(sessionId)) {
        const lastMsg = messages[messages.length - 1];
        if (lastMsg?.role === 'user') {
          ui = deps.appendAssistantMessage?.({ withLoading: true });
        } else {
          ui = deps.getLastAssistantUi?.();
          if (ui?.wrapper?.isConnected) deps.markLiveStreamUi?.(ui);
        }
      }
      if (!ui) return;
    }

    let assistantMessage;
    const last = messages[messages.length - 1];
    let skipEventReplay = false;

    if (last?.role === 'assistant' && deps.assistantMessageHasContent?.(last)) {
      assistantMessage = serverAssistant && deps.assistantMessageHasContent?.(serverAssistant)
        ? serverAssistant
        : deps.normalizeStoredMessage({ ...last });
      deps.hydrateAssistantUi?.(ui, assistantMessage);
      skipEventReplay = true;
    } else if (last?.role === 'user') {
      if (!deps.getLiveStreamUi?.()) deps.showAssistantLoading(ui);
      assistantMessage = {
        role: 'assistant',
        content: '',
        reasoning_content: '',
        tool_calls: [],
        tool_results: {},
        agent_events: [],
        ...(initialData?.assistant || {}),
      };
      if (initialData?.assistant) deps.hydrateAssistantUi?.(ui, assistantMessage);
    } else if (last?.role === 'assistant') {
      if (!deps.getLiveStreamUi?.()) deps.showAssistantLoading(ui);
      assistantMessage = {
        role: 'assistant',
        content: '',
        reasoning_content: '',
        tool_calls: [],
        tool_results: {},
        agent_events: [],
        ...(initialData?.assistant || {}),
      };
      if (initialData?.assistant) deps.hydrateAssistantUi?.(ui, assistantMessage);
    } else {
      return;
    }

    deps.markLiveStreamUi(ui);
    deps.setStreamSessionId?.(sessionId);
    deps.setAbortController?.({ cancelled: false });
    deps.updateComposerSendBtn?.();

    const replaySince = Number.isFinite(initialData?.nextSince) ? initialData.nextSince : 0;
    const streamCtx = {
      ui,
      assistantMessage,
      sessionId,
      cancelled: false,
      isVisible: () => deps.SessionStore?.activeId === sessionId,
      thinkingStarted: Boolean(assistantMessage.reasoning_content),
      contentStarted: Boolean(assistantMessage.content),
      rawContent: assistantMessage.content || '',
      displayedContentLen: (assistantMessage.content || '').length,
      since: replaySince,
      lastSeq: replaySince,
    };

    if (!skipEventReplay && initialData?.events?.length) {
      for (const ev of initialData.events) {
        const seq = ev._seq || 0;
        if (seq <= streamCtx.lastSeq) continue;
        streamCtx.lastSeq = seq;
        streamCtx.since = seq;
        await handleStreamEvent(ev, streamCtx);
      }
    }

    const existing = findCtx(jobId, sessionId);
    if (existing && existing._pollActive) return;
    watch(jobId, sessionId, streamCtx);
  }

  async function syncActiveSession() {
    const sessionId = deps.SessionStore?.activeId;
    if (!sessionId) return;

    let jobId = deps.SessionStore.getActiveJobId(sessionId);
    if (!jobId) {
      const { data: listData } = await deps.api('GET', `/api/ai/chat/jobs?sessionId=${encodeURIComponent(sessionId)}`);
      jobId = listData?.jobs?.[0]?.id;
      if (jobId) deps.SessionStore.setActiveJobId(sessionId, jobId);
    }
    if (!jobId) {
      deps.updateComposerSendBtn?.();
      return;
    }

    const existing = findCtx(jobId, sessionId);
    if (existing?._pollActive) {
      deps.updateComposerSendBtn?.();
      return;
    }

    const messages = deps.getSessionMessages?.(sessionId) || [];
    const last = messages[messages.length - 1];
    const sinceHint = (last?.role === 'assistant' && deps.assistantMessageHasContent?.(last))
      ? Number.MAX_SAFE_INTEGER
      : 0;
    const { data } = await deps.api(
      'GET',
      `/api/ai/chat/jobs/${encodeURIComponent(jobId)}?since=${sinceHint}`,
    );
    if (!data?.ok) {
      deps.SessionStore.clearActiveJobId(sessionId);
      deps.updateComposerSendBtn?.();
      return;
    }

    if (data.status === 'done') {
      const doneMsg = deps.normalizeStoredMessage({
        role: 'assistant',
        content: '',
        reasoning_content: '',
        tool_calls: [],
        tool_results: {},
        ...(data.assistant || {}),
      });
      if (data.resolvedModel) doneMsg.resolvedModel = data.resolvedModel;
      if (deps.assistantMessageHasContent?.(doneMsg)) {
        deps.commitAssistantMessage?.(sessionId, doneMsg);
      }
      deps.SessionStore.clearActiveJobId(sessionId);
      deps.renderStoredMessages?.({ force: true, forceScroll: true });
      deps.syncSessionsToDevice?.().catch(() => {});
      deps.updateComposerSendBtn?.();
      return;
    }

    if (data.status !== 'running') {
      await applyTerminalJobState(jobId, sessionId, findCtx(jobId, sessionId), data.status, data);
      deps.updateComposerSendBtn?.();
      return;
    }

    await attach(sessionId, jobId, data);
  }

  function forEachPollingCtx(fn) {
    for (const [jobId, ctx] of contexts.entries()) {
      if (!ctx._pollActive) fn(jobId, ctx);
    }
  }

  function resumePolling() {
    for (const [jobId, ctx] of contexts.entries()) {
      if (!ctx._pollActive && ctx.sessionId && !ctx.cancelled) poll(jobId, ctx.sessionId, ctx);
    }
  }

  async function recoverStuckStreams() {
    const sessions = deps.SessionStore?.listWithContent?.() || deps.SessionStore?.list?.() || [];
    for (const s of sessions) {
      const sessionId = s.id;
      let jobId = deps.SessionStore.getActiveJobId(sessionId);
      if (!jobId) continue;
      const ctx = findCtx(jobId, sessionId);
      if (ctx && !ctx._pollActive && !ctx.cancelled) poll(jobId, sessionId, ctx);
      if (ctx) continue;

      const { data } = await deps.api('GET', `/api/ai/chat/jobs/${encodeURIComponent(jobId)}?since=0`);
      if (!data?.ok) {
        deps.SessionStore.clearActiveJobId(sessionId);
        continue;
      }
      if (data.status === 'running') {
        if (deps.SessionStore.activeId === sessionId) {
          await attach(sessionId, jobId, data);
        } else {
          const bg = ensureBackgroundCtx(sessionId, jobId, data);
          if (!bg._pollActive) watch(jobId, sessionId, bg);
        }
        continue;
      }
      if (['done', 'error', 'cancelled'].includes(data.status)) {
        await applyTerminalJobState(jobId, sessionId, null, data.status, data);
      }
    }
    deps.renderSessionList?.();
    deps.updateComposerSendBtn?.();
  }

  async function resumeActiveJobs(jobs) {
    if (!Array.isArray(jobs) || !jobs.length) return;
    for (const job of jobs) {
      const jobId = job.id || job.jobId;
      const sessionId = job.sessionId;
      if (!jobId || !sessionId) continue;
      deps.SessionStore?.setActiveJobId(sessionId, jobId);
      if (findCtx(jobId, sessionId)?._pollActive) continue;
      if (deps.SessionStore?.activeId === sessionId) {
        await syncActiveSession();
      } else {
        const ctx = ensureBackgroundCtx(sessionId, jobId, job);
        if (!ctx._pollActive) watch(jobId, sessionId, ctx);
      }
    }
    deps.renderSessionList?.();
    deps.updateComposerSendBtn?.();
  }

  function detachInactiveStreamUis() {
    const activeId = deps.SessionStore?.activeId;
    for (const ctx of contexts.values()) {
      if (!ctx || ctx.sessionId === activeId) continue;
      if (ctx.ui?.wrapper) delete ctx.ui.wrapper.dataset.liveStream;
      ctx.ui = null;
    }
  }

  return {
    init,
    stream,
    attach,
    syncActiveSession,
    verifySessionJobId,
    scheduleStaleJobSweep,
    scheduleSweepAllPendingJobs,
    handleSyncWsEvent,
    abortActive,
    abortSession,
    isSessionRunning,
    isSessionStreaming,
    isSessionJobPending,
    hasActiveCtx,
    findCtx,
    getActiveJobId,
    setActiveJobId,
    endPoll,
    forEachPollingCtx,
    resumePolling,
    recoverStuckStreams,
    resumeActiveJobs,
    detachInactiveStreamUis,
  };
})();
