const RAG_WIKI_MAX_FILES_PER_REPO = 0;
/* $, $$, els, APP_SPLASH_* provided by app/dom.js */

let toolsMeta = {};
let skillsRegistry = [];
let mcpConnectors = [];
let ragStatsCache = { count: 0, vector_chunks: 0, totalChars: 0, embeddedDocs: 0 };
let embeddingDefaults = {};
let configSaveState = 'idle';
let configSaveInFlight = false;

const i18n = new I18n();
let state = { driving: true, configured: false };
let providers = [];
let providerLabels = {};
const FALLBACK_PROVIDERS = [
  'opencode-zen', 'opencode-go', 'deepseek', 'bigmodel', 'qwen', 'mimo', 'minimax',
  'openrouter', 'openai', 'kimi', 'siliconflow', 'custom',
];
const FALLBACK_PROVIDER_LABELS = {
  'opencode-zen': 'OpenCode Zen',
  'opencode-go': 'OpenCode Go',
  deepseek: 'DeepSeek',
  bigmodel: '智谱 BigModel',
  qwen: '通义千问',
  mimo: '小米 MiMo',
  minimax: 'MiniMax',
  openrouter: 'OpenRouter',
  openai: 'OpenAI',
  kimi: 'Kimi (Moonshot)',
  siliconflow: '硅基流动 SiliconFlow',
  custom: 'Custom',
};
let modelCatalog = {};
let defaults = {};
let models = [];
let mainModelCombo = null;
let embeddingModelCombo = null;
let onboardingModelCombo = null;
let onboardingEmbeddingModelCombo = null;
let onboardingRagSetupActive = false;
let onboardingFetchedModels = [];
let embeddingProviders = [];
let embeddingProviderLabels = {};
let embeddingModelCatalog = {};
let embeddingSameModeCatalog = {};
let embeddingModels = [];
const FALLBACK_EMBEDDING_PROVIDERS = ['siliconflow', 'openrouter', 'openai', 'bigmodel', 'qwen', 'custom'];
const FALLBACK_EMBEDDING_PROVIDER_LABELS = {
  siliconflow: '硅基流动 SiliconFlow',
  openrouter: 'OpenRouter',
  openai: 'OpenAI',
  bigmodel: '智谱 BigModel',
  qwen: '通义千问',
  custom: 'Custom',
};
let usageData = null;
let embeddingUsageData = null;
let usageDetailOpen = false;
let usageDetailView = { chat: 'provider', embedding: 'provider' };
let configured = false;
let configureError = '';
let savedConfig = {};
let schedActionManual = false;
let abortController = null;
let streamSessionId = null;
let _sessionPullTimer = null;
let _suppressSessionPush = false;
let _syncWsGotHello = false;
let _gatewayHydrated = false;
let _statusPollTimer = null;
const CHAT_MODE = 'unlimited';
let pendingWorkflow = '';
let pendingAgentId = '';
let pendingCompact = false;
let pendingConsumerMode = false;
let _lastStateVersion = 0;

function getAbortController() { return abortController; }
function setAbortController(v) { abortController = v; }
function getStreamSessionId() { return streamSessionId; }
function setStreamSessionId(v) { streamSessionId = v; }
function consumePendingWorkflow() {
  const w = pendingWorkflow;
  pendingWorkflow = '';
  return w;
}

function consumePendingAgentId() {
  const a = pendingAgentId;
  pendingAgentId = '';
  return a;
}

function consumePendingCompact() {
  const c = pendingCompact;
  pendingCompact = false;
  return c;
}

function consumePendingConsumerMode() {
  const c = pendingConsumerMode;
  pendingConsumerMode = false;
  return c;
}

async function sendUserMessage(text, opts = {}) {
  if (!text?.trim()) return;
  if (opts.workflow) pendingWorkflow = opts.workflow;
  if (opts.consumerMode) pendingConsumerMode = true;
  if (els.chatInput) els.chatInput.value = text;
  if (els.composer) {
    await sendChat({ preventDefault() {} });
  }
}

function initChatJobs() {
  if (typeof ChatJobs === 'undefined') return;
  ChatJobs.init({
    api,
    els,
    t,
    SessionStore,
    chatMode: CHAT_MODE,
    getState: () => state,
    getAbortController,
    setAbortController,
    getStreamSessionId,
    setStreamSessionId,
    consumePendingWorkflow,
    consumePendingAgentId,
    consumePendingCompact,
    consumePendingConsumerMode,
    showWriteConfirmModal,
    getChatDebugPrefs: () => (
      (typeof LocalPrefs !== 'undefined' && LocalPrefs.getChatDebugPrefs)
        ? LocalPrefs.getChatDebugPrefs()
        : { verbose: false, trace: false }
    ),
    isSyncWsConnected,
    syncSessionsToDevice,
    getCurrentMessages,
    prepareMessagesForApi,
    normalizeStoredMessage,
    appendAssistantMessage,
    showAssistantLoading,
    markLiveStreamUi,
    hideAssistantLoading,
    finishAssistant,
    endChatStream,
    commitAssistantMessage,
    savePartialAssistant,
    renderStoredMessages,
    formatApiError,
    showToast,
    reconcileStreamUi,
    handleAgentStreamEvent,
    scrollToBottom,
    renderToolCall,
    updateToolCallsSummary,
    updateToolCallResult,
    renderUsage,
    loadUsage,
    syncThinkingBlock,
    updateModelBadge,
    setMessageModelTag,
    clearLiveStreamChrome,
    setDetailsCollapsed,
    renderMessageFooter,
    appendTraceLine,
    isChatTraceEnabled,
    getLiveStreamUi,
    getLastAssistantUi,
    resolveAttachAssistantUi,
    stripLeakedToolCalls,
    renderMarkdownContent,
    hydrateAssistantUi,
    assistantMessageHasContent,
    isLocallyStreaming,
    isChatUiLocked,
    isSessionJobRunning,
    getSessionMessages,
    renderSessionList,
    updateComposerSendBtn,
    scheduleSessionSync,
  });
}

async function streamAssistantResponse(messages) {
  if (typeof ChatJobs !== 'undefined') return ChatJobs.stream(messages);
}

async function attachToChatJob(sessionId, jobId, initialData) {
  if (typeof ChatJobs !== 'undefined') return ChatJobs.attach(sessionId, jobId, initialData);
}

async function syncActiveSessionStreaming() {
  if (typeof ChatJobs !== 'undefined') return ChatJobs.syncActiveSession();
}

async function handleSyncWsChatEvent(payload) {
  if (typeof ChatJobs !== 'undefined') return ChatJobs.handleSyncWsEvent(payload);
}

function findChatJobCtx(jobId, sessionId) {
  if (typeof ChatJobs !== 'undefined') return ChatJobs.findCtx(jobId, sessionId);
  return null;
}

function abortActiveChat() {
  if (typeof ChatJobs !== 'undefined') ChatJobs.abortActive();
}

function abortSessionChat(sessionId) {
  if (typeof ChatJobs !== 'undefined') ChatJobs.abortSession(sessionId);
}

function isSessionJobRunning(sessionId) {
  return typeof ChatJobs !== 'undefined' && ChatJobs.isSessionJobPending(sessionId);
}

function isSessionStreaming(sessionId) {
  return typeof ChatJobs !== 'undefined' && ChatJobs.isSessionStreaming(sessionId);
}

function getSessionMessages(sessionId) {
  const session = SessionStore.getById(sessionId);
  return session?.messages || [];
}

function updateComposerSendBtn() {
  const sessionId = SessionStore.activeId;
  const streaming = isSessionStreaming(sessionId);
  if (!els.sendBtn) return;
  let label = t('send', 'Send');
  if (streaming) label = t('stop', 'Stop');
  else if (editingUserMsgIdx !== null) label = t('resendEdited', 'Resend');
  els.sendBtn.title = label;
  els.sendBtn.setAttribute('aria-label', label);
  els.sendBtn.classList.toggle('is-stop', streaming);
}

function applyBuiltinAgents(data) {
  if (typeof AgentsPanel !== 'undefined') AgentsPanel.applyBuiltinAgents(data);
}

function handleAgentStreamEvent(data, ctx) {
  const ui = ctx?.ui || getLiveStreamUi() || getLastAssistantUi();
  if (ui && data?.type) {
    recordAgentStreamEvent(ui, data, ctx?.assistantMessage);
  }
  if (typeof AgentsPanel !== 'undefined') AgentsPanel.handleStreamEvent(data);
}

function currentActiveAgentId() {
  return typeof AgentsPanel !== 'undefined' ? AgentsPanel.getCurrentAgentId() : 'op';
}

const MAX_IMAGES_PER_MESSAGE = 9;
const MAX_IMAGE_DIMENSION = 1280;
const JPEG_QUALITY = 0.82;
const CHAT_SCROLL_PIN_THRESHOLD = 120;

const OP_COMMA_LOGO_SVG = `<svg viewBox="0 0 24 42" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><path fill-rule="evenodd" clip-rule="evenodd" d="M3.2265 42C3.2265 41.0282 3.15054 40.2141 3.26228 39.4294C3.3099 39.0948 3.70043 38.7365 4.01893 38.5344C5.57173 37.5489 7.25857 36.7621 8.70427 35.6319C13.387 31.9708 16.1628 27.1512 16.3145 20.8905C16.3574 19.1128 15.7039 18.6687 14.2108 19.3612C9.90092 21.3604 5.26623 20.1883 2.79277 16.4731C0.0953566 12.421 0.475192 7.0259 3.70716 3.4862C7.83541 -1.03482 14.6281 -1.1701 19.3123 3.14764C22.1182 5.73404 23.4514 9.07362 23.7839 12.8722C24.8985 25.598 18.5156 36.0872 6.89848 40.695C5.74875 41.1508 4.56975 41.5252 3.2265 42Z" fill="currentColor"/></svg>`;

let pendingImages = [];
let pendingFileRefs = [];
let editingUserMsgIdx = null;
let cabanaOpen = false;
let secocOpen = false;
let cabanaInited = false;
const OPTIONAL_BASE_URL_PROVIDERS = new Set(['qwen', 'minimax', 'mimo', 'bigmodel']);

function setOverlayVisible(el, visible) {
  if (!el) return;
  el.classList.toggle('is-open', visible);
  if (visible) el.removeAttribute('hidden');
  else el.setAttribute('hidden', '');
}

function ensureCabanaInited() {
  if (cabanaInited || typeof CabanaPanel === 'undefined') return;
  CabanaPanel.init({
    root: document.getElementById('cabanaPanelRoot'),
    t,
    tf,
    getLang: () => i18n.getLang(),
    onSendToChat: sendTextToChat,
  });
  cabanaInited = true;
}

function t(key, fallback) {
  return i18n.t(key, fallback);
}

function tf(key, vars, fallback) {
  return i18n.tf(key, vars, fallback);
}

function applyDataI18n() {
  document.querySelectorAll('[data-i18n]').forEach((el) => {
    if (el.id === 'cabanaMetaBar') return;
    const key = el.dataset.i18n;
    if (!key) return;
    const fallback = (el.textContent || '').trim() || el.getAttribute('aria-label') || '';
    const val = t(key, fallback);
    const attr = el.dataset.i18nAttr;
    if (attr) el.setAttribute(attr, val);
    else if (val) el.textContent = val;
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
    const key = el.dataset.i18nPlaceholder;
    if (key) el.placeholder = t(key);
  });
  document.querySelectorAll('[data-i18n-title]').forEach((el) => {
    const key = el.dataset.i18nTitle;
    if (key) {
      const val = t(key);
      el.title = val;
      if (!el.getAttribute('aria-label')) el.setAttribute('aria-label', val);
    }
  });
}

function setI18nText(selector, key, fallback) {
  const el = typeof selector === 'string' ? $(selector) : selector;
  if (!el) return;
  el.textContent = fallback !== undefined ? t(key, fallback) : t(key);
}

function applyCachedUiState() {
  const src = savedConfig?.model ? savedConfig : LocalPrefs.getConfigCache();
  if (!src?.model && !src?.modelHub) return;
  updateModelBadgeFromSaved();
}

function hydrateFromLocalPrefs() {
  const cache = LocalPrefs.getConfigCache();
  if (cache && Object.keys(cache).length) {
    savedConfig = { ...savedConfig, ...cache };
    if (cache._providers?.length) {
      providers = cache._providers;
      renderProviderOptions();
    }
    applyConfigToForm(cache);
  }
  applyCachedUiState();
  primeModelsFromCacheOrCatalog(savedConfig?.provider || els.providerSelect?.value);
}

function timezoneOptionKey(id) {
  return I18n.timezoneKey(id);
}

function renderTimezoneSelect(preferred) {
  if (!els.timezoneSelect) return;
  const current = preferred || els.timezoneSelect.value || savedConfig?.timezone || 'Asia/Shanghai';
  const ids = I18n.getTimezoneIds();
  els.timezoneSelect.innerHTML = '';
  for (const id of ids) {
    const opt = document.createElement('option');
    opt.value = id;
    opt.textContent = t(timezoneOptionKey(id), id);
    els.timezoneSelect.appendChild(opt);
  }
  els.timezoneSelect.value = ids.includes(current) ? current : 'Asia/Shanghai';
}

function bindPasswordReveals(root) {
  if (typeof PasswordField !== 'undefined') {
    PasswordField.bind(root);
  }
}

function applySecocPaneI18n() {
  if (typeof TskPanel !== 'undefined' && TskPanel.applyTranslations) {
    TskPanel.applyTranslations(t);
  }
}

function applyChatPlaceholder() {
  if (!els.chatInput) return;
  const mobile = window.matchMedia('(max-width: 767px)').matches;
  els.chatInput.placeholder = mobile
    ? t('chatPlaceholderMobile', '描述问题…')
    : t('chatPlaceholder', '描述问题，可贴图或日志');
}

function applyTranslations() {
  document.title = t('title', 'op助手');
  if (els.composerHintTooltip) {
    els.composerHintTooltip.textContent = t('composerHint', 'Enter 发送 · Shift+Enter 换行 · 支持粘贴图片');
  }
  if (els.composerHintBtn) {
    els.composerHintBtn.title = t('composerHintAria', 'Input shortcuts');
    els.composerHintBtn.setAttribute('aria-label', els.composerHintBtn.title);
  }
  if (els.jumpToBottomBtn) {
    els.jumpToBottomBtn.title = t('jumpToBottomAria', 'Jump to latest messages');
    els.jumpToBottomBtn.setAttribute('aria-label', els.jumpToBottomBtn.title);
  }
  const contextPanelTitle = document.getElementById('composerContextPanelTitle');
  if (contextPanelTitle) contextPanelTitle.textContent = t('contextUsageTitle', 'Context usage');
  const contextCompactBtn = document.getElementById('composerContextCompactBtn');
  if (contextCompactBtn) {
    contextCompactBtn.textContent = t('contextCompactBtn', '压缩上下文');
    contextCompactBtn.title = t('contextCompactHint', '等同 /compact，将较早对话摘要写入记忆');
  }
  const sessionSearchInput = document.getElementById('sessionSearchInput');
  if (sessionSearchInput) sessionSearchInput.placeholder = t('sessionSearchPlaceholder', 'Search chats…');
  const sessionSearchModalInput = document.getElementById('sessionSearchModalInput');
  if (sessionSearchModalInput) sessionSearchModalInput.placeholder = t('sessionSearchPlaceholder', 'Search chats…');
  const sessionSearchModalTitle = document.getElementById('sessionSearchModalTitle');
  if (sessionSearchModalTitle) sessionSearchModalTitle.textContent = t('sessionSearchTitle', 'Search chats');
  const sessionSearchMobileBtn = document.getElementById('sessionSearchMobileBtn');
  if (sessionSearchMobileBtn) {
    sessionSearchMobileBtn.title = t('sessionSearchPlaceholder', 'Search chats…');
    sessionSearchMobileBtn.setAttribute('aria-label', sessionSearchMobileBtn.title);
  }
  const composerEditBannerText = document.getElementById('composerEditBannerText');
  if (composerEditBannerText) composerEditBannerText.textContent = t('editingMessage', 'Editing message');
  const composerEditCancel = document.getElementById('composerEditCancel');
  if (composerEditCancel) {
    const cancelLabel = t('cancelEdit', 'Cancel');
    composerEditCancel.title = cancelLabel;
    composerEditCancel.setAttribute('aria-label', cancelLabel);
  }
  updateComposerSendBtn();
  refreshContextMeter();
  if (els.composerSlashLabel && !composerSlashOpen) {
    els.composerSlashLabel.textContent = t('slashMenuPickCommand', 'Slash commands');
  }
  els.imageBtn.title = t('attachImage', 'Add image');
  setI18nText('#settingsTitle', 'settings', 'Settings');
  setI18nText('#providerLabel', 'provider');
  setI18nText('#modelLabel', 'model');
  setI18nText('#apiKeyLabel', 'apiKey');
  setI18nText('#baseUrlLabel', 'baseUrl');
  setI18nText('#systemPromptLabel', 'systemPrompt', 'System Prompt');
  setI18nText('#personaSectionTitle', 'personaSectionTitle', '系统人设');
  setI18nText('#personaGenHint', 'personaGenHint', 'Temperature、Max Tokens 等生成参数请在上方模型列表的配置弹窗里按模型设置。');
  if (els.personaSaveBtn) els.personaSaveBtn.textContent = t('personaSaveBtn', '保存人设');
  setI18nText('#thinkingLabel', 'thinking', 'Thinking');
  updateConfigSaveHint();
  setI18nText('#usageTitle', 'usage', 'Usage');
  if (els.usageDetailBtn) els.usageDetailBtn.textContent = t('usageDetail', 'Usage detail');
  if (els.embeddingUsageDetailBtn) els.embeddingUsageDetailBtn.textContent = t('usageDetail', 'Usage detail');
  setI18nText('#usageDetailTitle', 'usageDetail', 'Usage detail');
  setI18nText('#usageDetailDesc', 'usageDetailDesc', 'By provider and model');
  setI18nText('#usageChatSectionTitle', 'usageChatSectionTitle', 'Chat models');
  setI18nText('#usageEmbeddingSectionTitle', 'usageEmbeddingSection', 'Embedding');
  setI18nText('#usageEmbeddingSectionDesc', 'usageEmbeddingSectionDesc', 'Knowledge base embedding usage');
  setI18nText('#usageChatTabProvider', 'usageByProvider', 'By provider');
  setI18nText('#usageChatTabModel', 'usageByModel', 'By model');
  setI18nText('#usageEmbTabProvider', 'usageByProvider', 'By provider');
  setI18nText('#usageEmbTabModel', 'usageByModel', 'By model');
  setI18nText('#embeddingUsageTitle', 'embeddingUsageTitle', 'Embedding usage');
  setI18nText('#langLabel', 'langLabel', 'Language');
  setI18nText('#timezoneLabel', 'timezoneLabel', 'Timezone');
  renderTimezoneSelect();
  els.saveBtn.textContent = t('save');
  setI18nText('#sessionsTitle', 'sessions', 'Sessions');
  setI18nText('#tabModel', 'tabModel', '模型');
  setI18nText('#tabKnowledge', 'tabKnowledge', '知识库');
  const tabSecocEl = $('#secocBtn');
  if (tabSecocEl) tabSecocEl.title = t('tabSecoc', 'SecOC');
  setI18nText('#tabScheduler', 'tabScheduler', '定时');
  setI18nText('#modelPaneDesc', 'modelPaneDesc', '配置模型列表与服务商账户；修改后自动保存。');
  setI18nText('#modelHubTitle', 'modelHubTitle', '模型中心');
  setI18nText('#schedulerListTitle', 'schedulerListTitle', '已添加任务');
  setI18nText('#schedulerFormTitle', 'schedulerFormTitle', '新建任务');
  const tabDevEl = $('#tabDev');
  if (tabDevEl) tabDevEl.textContent = t('tabDev', '开发');
  const devPaneDescEl = $('#devPaneDesc');
  if (devPaneDescEl) devPaneDescEl.textContent = t('devPaneDescCollab', 'Fork 分析、发布 PR 与反馈');
  setI18nText('#devPaneTabCollab', 'devPaneTabCollab', '代码协作');
  setI18nText('#devPaneTabCache', 'devPaneTabCache', '本地缓存');
  setI18nText('#devPaneTabRuntime', 'devPaneTabRuntime', '运行环境');
  setI18nText('#devRuntimeTitle', 'devRuntimeTitle', '运行环境与输出');
  setI18nText('#devCacheTitle', 'devCacheTitle', '本地缓存');
  setI18nText('#devCacheDesc', 'devCacheDesc', '清理路线回放、TSK 提取等本地缓存，不影响已安装 SecOC 密钥。');
  setI18nText('#devCacheDaysLabel', 'devCacheDaysLabel', '时间范围');
  setI18nText('#devCacheModeLabel', 'devCacheModeLabel', '清理策略');
  if (els.devCacheClearBtn) els.devCacheClearBtn.textContent = t('devCacheClearBtn', '清理全部');
  setI18nText('#runtimeTabEnv', 'devRuntimeTabEnv', '环境');
  setI18nText('#runtimeTabTools', 'devRuntimeTabTools', '工具');
  setI18nText('#runtimeTabOutput', 'devRuntimeTabOutput', '输出');
  setI18nText('#devCanvasDesc', 'devCanvasDesc', '调参报告、图表与结构化结果（随当前会话）');
  setI18nText('#devCanvasFilterLabel', 'devCanvasFilterLabel', '筛选');
  setI18nText('#knowledgeIndexTitle', 'knowledgeIndexTitle', '索引与检索');
  setI18nText('#ragSearchLimitLabel', 'ragSearchLimitLabel', '工具检索默认条数');
  setI18nText('#ragSearchLimitHint', 'ragSearchLimitHint', 'AI 通过 search_knowledge_base 工具自行检索；此为未指定 limit 时的默认值（最大 50）');
  const devPackageTitle = $('#devPackageTitle');
  if (devPackageTitle) devPackageTitle.textContent = t('devPackageTitle', 'op助手 版本');
  if (els.devPackageCheckBtn) els.devPackageCheckBtn.textContent = t('devPackageCheck', '检查更新');
  if (els.devPackageUpdateBtn) els.devPackageUpdateBtn.textContent = t('devPackageUpdate', '立即更新');
  setI18nText('#devCollabTitle', 'devCollabTitle', '代码协作');
  setI18nText('#devCollabCredentialsTitle', 'devCollabCredentialsTitle', '凭据');
  setI18nText('#collabTabRepo', 'devCollabTabRepo', '仓库');
  setI18nText('#collabTabPublish', 'devCollabTabPublish', '发布');
  setI18nText('#collabTabIssue', 'devCollabTabIssue', '反馈');
  setI18nText('#forkDetailsSummary', 'devForkDetailsSummary', '技术详情');
  setI18nText('#packageDetailsSummary', 'devPackageDetailsSummary', '版本详情');
  setI18nText('#collabPublishConfigTitle', 'devCollabPublishConfigTitle', '发布策略');
  setI18nText('#collabPublishUnitsTitle', 'devCollabPublishUnitsTitle', '发布单元');
  if (els.collabGoPublishPrTab) els.collabGoPublishPrTab.textContent = t('devCollabGoPublishPr', '已改代码？去发布 PR');
  const devForkTitle = $('#devForkTitle');
  if (devForkTitle) devForkTitle.textContent = t('devForkTitle', 'Fork 分析');
  const devPublishTitle = $('#devPublishTitle');
  if (devPublishTitle) devPublishTitle.textContent = t('devPublishTitle', '代码发布');
  if (els.devPublishSaveBtn) els.devPublishSaveBtn.textContent = t('devPublishSave', '保存配置');
  const devIssueTitle = $('#devIssueTitle');
  if (devIssueTitle) devIssueTitle.textContent = t('devIssueTitle', '反馈提交');
  if (els.devIssueSubmitBtn) els.devIssueSubmitBtn.textContent = t('devIssueSubmit', '提交 Issue');
  setI18nText('#contextSettingsTitle', 'contextSettingsTitle', '上下文与压缩');
  setI18nText('#contextSettingsHint', 'contextSettingsHint', '长对话自动摘要写入记忆；也可在上下文用量面板点击「压缩上下文」或输入 /compact');
  setI18nText('#compactionEnabledLabel', 'compactionEnabledLabel', '自动压缩会话');
  setI18nText('#compactionTokenTriggerLabel', 'compactionTokenTriggerLabel', '按 token 数触发压缩');
  setI18nText('#evolutionSettingsTitle', 'evolutionSettingsTitle', '助手学习与进化');
  setI18nText('#evolutionEnabledLabel', 'evolutionEnabledLabel', '启用进化管线');
  setI18nText('#evolutionAutoWorkspaceLabel', 'evolutionAutoWorkspaceLabel', '对话后自动补工作区模板');
  setI18nText('#evolutionAutoMemoryLabel', 'evolutionAutoMemoryLabel', '对话后自动提炼记忆（每日日志 + MEMORY）');
  setI18nText('#evolutionLlmReflectLabel', 'evolutionLlmReflectLabel', 'LLM 反思诊断 (GEPA)');
  setI18nText('#evolutionAutoProposeLabel', 'evolutionAutoProposeLabel', '自动提案技能（需批准）');
  setI18nText('#evolutionGepaEnabledLabel', 'evolutionGepaEnabledLabel', '内置 GEPA 技能进化');
  setI18nText('#evolutionUseDspyLabel', 'evolutionUseDspyLabel', '使用 DSPy 后端（需 pip install dspy，PC）');
  setI18nText('#evolutionSettingsHint', 'evolutionSettingsHint', '三层记忆 + 轨迹反思 + 技能/工具描述进化；详见 设置→平台→技能进化');
  setI18nText('#skillsDisclosureMaxLabel', 'skillsDisclosureMaxLabel', '按需加载技能数');
  setI18nText('#evolutionCandidatesLabel', 'evolutionCandidatesLabel', 'Pareto 候选数');
  const publishPromptTitle = $('#publishPromptTitle');
  if (publishPromptTitle) publishPromptTitle.textContent = t('publishPromptTitle', '发布改动');
  if (els.publishPromptCancel) els.publishPromptCancel.textContent = t('publishPromptLater', '稍后');
  if (els.publishPromptOk) els.publishPromptOk.textContent = t('publishPromptGo', '发布');
  if (els.devForkRefreshBtn) els.devForkRefreshBtn.textContent = t('devForkRefresh', '扫描仓库');
  if (els.devForkSyncBtn) els.devForkSyncBtn.textContent = t('devForkAnalyze', 'AI 分析并生成草稿');
  const forkThinkingSummary = $('#forkProgressThinkingSummary');
  if (forkThinkingSummary) forkThinkingSummary.textContent = t('devForkProgressThinking', '思考过程');
  const forkContentSummary = $('#forkProgressContentSummary');
  if (forkContentSummary) forkContentSummary.textContent = t('devForkProgressOutput', '模型输出');
  const devSessionsTitle = $('#devSessionsTitle');
  if (devSessionsTitle) devSessionsTitle.textContent = t('devSessionsTitle', 'PC 工具会话');
  const devAssetsTitle = $('#devAssetsTitle');
  if (devAssetsTitle) devAssetsTitle.textContent = t('devAssetsTitle', '报告与导出');
  const devRefreshLabel = $('#devRefreshLabel');
  if (devRefreshLabel) devRefreshLabel.textContent = t('devRefresh', '刷新');
  setI18nText('#embeddingSectionTitle', 'embeddingSection', '知识库 Embedding');
  setI18nText('#embeddingPaneDesc', 'embeddingPaneDesc', '向量检索用（与聊天模型分开配置）');
  setI18nText('#schedulerPaneDesc', 'schedulerPaneDesc');
  if (els.settingsKnowledgeBtn) els.settingsKnowledgeBtn.textContent = t('knowledgeManageDocs', '管理文档');
  setI18nText('#knowledgeTitle', 'knowledgeTitle', '知识库');
  setI18nText('#knowledgePaneDesc', 'knowledgePaneDesc', '向量检索引用；可追加个人笔记');
  if (els.settingsKnowledgeBtn) els.settingsKnowledgeBtn.title = t('knowledgeTitle', '知识库');
  applySchedulerFormI18n();
  const brandSpan = document.querySelector('.chat-title span');
  if (brandSpan) brandSpan.textContent = t('brandSuffix', '助手');
  if (els.cabanaBtn) els.cabanaBtn.title = t('openCabana', 'CAN 分析');
  if (els.notificationsBtn) els.notificationsBtn.title = t('notificationsTitle', '通知');
  if (els.notificationsTitle) els.notificationsTitle.textContent = t('notificationsTitle', '通知');
  if (els.notificationsMarkReadBtn) {
    els.notificationsMarkReadBtn.textContent = t('notificationsMarkRead', '全部已读');
  }
  applyDataI18n();
  if (els.apiKeyInput) els.apiKeyInput.placeholder = t('apiKeyPlaceholder');
  if (els.baseUrlInput) els.baseUrlInput.placeholder = t('baseUrlPlaceholder');
  mainModelCombo?.setPlaceholder(t('modelPlaceholder'));
  embeddingModelCombo?.setPlaceholder(t('embeddingModelPlaceholder', 'BAAI/bge-m3'));
  if (els.systemPromptInput) els.systemPromptInput.placeholder = t('systemPromptPlaceholder');
  if (els.schedName) els.schedName.placeholder = t('schedNamePlaceholder');
  if (els.ragTitle) els.ragTitle.placeholder = t('ragTitlePlaceholder');
  if (els.ragText) els.ragText.placeholder = t('ragTextPlaceholder');
  if (els.ragSaveBtn) els.ragSaveBtn.textContent = t('ragAddDoc');
  if (els.ragSyncWikiBtn) els.ragSyncWikiBtn.textContent = t('ragSyncWiki');
  if (els.ragReindexBtn) els.ragReindexBtn.textContent = t('ragReindex');
  if (els.ragTitleLabel) els.ragTitleLabel.textContent = t('ragTitleLabel');
  if (els.ragTextLabel) els.ragTextLabel.textContent = t('ragTextLabel');
  setI18nText('#onboardingTitle', 'onboardingTitle', 'Welcome to op助手');
  setI18nText('#onboardingDesc', 'onboardingDesc', 'Configure one chat model to get started; add more providers and fallbacks in Settings.');
  setI18nText('#onboardingModelTitle', 'onboardingModelTitle', 'Chat model');
  setI18nText('#onboardingModelHint', 'onboardingModelHint', 'Pick a provider, enter API Key, and select a model.');
  setI18nText('#onboardingProviderLabel', 'provider', 'Provider');
  setI18nText('#onboardingApiKeyLabel', 'apiKey', 'API Key');
  setI18nText('#onboardingModelLabel', 'model', 'Model');
  setI18nText('#onboardingEmbeddingTitle', 'onboardingEmbeddingTitle', 'Embedding (RAG)');
  setI18nText('#onboardingEmbeddingDesc', 'onboardingEmbeddingDesc', 'For knowledge search; uses chat account embedding by default.');
  setI18nText('#onboardingEmbeddingSeparateLabel', 'onboardingEmbeddingSeparateLabel', 'Separate embedding provider');
  setI18nText('#onboardingEmbeddingProviderLabel', 'embeddingProviderLabel', 'Embedding provider');
  setI18nText('#onboardingEmbeddingApiKeyLabel', 'embeddingApiKeyLabel', 'Embedding API Key');
  setI18nText('#onboardingEmbeddingModelLabel', 'embeddingModelLabel', 'Embedding model');
  setI18nText('#onboardingCarLabel', 'onboardingCarLabel', 'Car model (optional)');
  setI18nText('#onboardingBrandLabel', 'onboardingBrandLabel', 'Brand (optional)');
  setI18nText('#onboardingGoalsLabel', 'onboardingGoalsLabel', 'What do you need most?');
  setI18nText('#onboardingGoalTuning', 'onboardingGoalTuning', 'Tuning');
  setI18nText('#onboardingGoalEngage', 'onboardingGoalEngage', 'Cannot engage');
  setI18nText('#onboardingGoalAdapt', 'onboardingGoalAdapt', 'New car');
  setI18nText('#onboardingGoalRoutes', 'onboardingGoalRoutes', 'Route review');
  setI18nText('#onboardingRagTitle', 'onboardingRagTitle', 'Knowledge base setup');
  setI18nText('#onboardingRagDesc', 'onboardingRagDesc', 'Index built-in docs and community wiki for RAG.');
  setI18nText('#onboardingRagReindexLabel', 'onboardingRagReindexLabel', 'Vectorize existing documents');
  setI18nText('#onboardingRagWikiLabel', 'onboardingRagWikiLabel', 'Pull community wiki and vectorize');
  if (els.onboardingTestBtn) els.onboardingTestBtn.textContent = t('testConnection', 'Test connection');
  if (els.onboardingSaveBtn) els.onboardingSaveBtn.textContent = t('onboardingSaveBtn', 'Save and continue');
  if (els.onboardingRagSkipBtn) els.onboardingRagSkipBtn.textContent = t('onboardingRagSkip', 'Set up later');
  if (els.onboardingRagStartBtn) els.onboardingRagStartBtn.textContent = t('onboardingRagStart', 'Start setup');
  const writeTitle = $('#writeConfirmTitle');
  if (writeTitle) writeTitle.textContent = t('writeConfirmTitle');
  const writeHint = $('#writeConfirmHint');
  if (writeHint) writeHint.textContent = t('writeConfirmHint');
  if (els.writeConfirmCancel) els.writeConfirmCancel.textContent = t('writeConfirmCancel');
  if (els.writeConfirmOk) els.writeConfirmOk.textContent = t('writeConfirmOk');
  if (els.sessionsToggleBtn) els.sessionsToggleBtn.title = t('sessionsToggleTitle');
  if (els.embeddingModeSelect) {
    const same = els.embeddingModeSelect.querySelector('option[value="same"]');
    const sep = els.embeddingModeSelect.querySelector('option[value="separate"]');
    if (same) same.textContent = t('embeddingModeSame');
    if (sep) sep.textContent = t('embeddingModeSeparate');
  }
  const devPassportTitle = $('#devPassportTitle');
  if (devPassportTitle) devPassportTitle.textContent = t('devPassportTitle', 'Tune passport');
  applySecocPaneI18n();
  applyChatPlaceholder();
  bindPasswordReveals();
}

function updateThemeIcon() {
  const mode = typeof Theme.getMode === 'function' ? Theme.getMode() : Theme.get();
  if (!els.themeBtn) return;
  if (mode === Theme.THEME_AUTO) {
    els.themeBtn.innerHTML = '<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/></svg>';
    els.themeBtn.title = t('themeAuto', 'Follow system');
    return;
  }
  const isLight = document.documentElement.getAttribute('data-theme') === 'light';
  els.themeBtn.innerHTML = isLight
    ? '<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M4.93 19.07l1.41-1.41M18.36 5.64l1.41-1.41"/></svg>'
    : '<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
  els.themeBtn.title = isLight ? t('themeLight') : t('themeDark');
}

async function api(method, path, body, opts = {}) {
  return WebApi.api(method, path, body, opts);
}

function getApiHeaders() {
  return WebApi.getApiHeaders();
}

function showToast(msg, type = 'info') {
  if (!els.toast) return;
  els.toast.textContent = msg;
  els.toast.className = `toast show ${type}`;
  els.toast.removeAttribute('aria-hidden');
  setTimeout(() => {
    els.toast.classList.remove('show');
    els.toast.textContent = '';
    els.toast.setAttribute('aria-hidden', 'true');
  }, 3000);
}

// ---------------------------------------------------------------------------
// Sessions & chat persistence
// ---------------------------------------------------------------------------

function getCurrentMessages() {
  const session = SessionStore.getActive();
  if (!session?.messages) return [];
  return session.messages.map(normalizeStoredMessage);
}

function sessionsForSync() {
  const maxMsgs = SessionStore.MAX_MESSAGES_PER_SESSION || 200;
  return SessionStore.listWithContent().map((s) => {
    const { activeJobId: _drop, ...rest } = s;
    const msgs = Array.isArray(rest.messages) ? rest.messages.slice(-maxMsgs) : [];
    return { ...rest, messages: msgs };
  });
}

function buildSessionSyncPayload() {
  const sessions = sessionsForSync();
  const payload = { sessions };
  if (!isDraftSessionView()) {
    const activeId = sessions.length && SessionStore.activeId && sessions.some((s) => s.id === SessionStore.activeId)
      ? SessionStore.activeId
      : (sessions[0]?.id ?? null);
    payload.activeId = sessions.length ? activeId : null;
  }
  return payload;
}

function saveCurrentMessages(messages) {
  const session = SessionStore.getActive();
  if (!session) return;
  const maxMsgs = SessionStore.MAX_MESSAGES_PER_SESSION || 200;
  SessionStore.updateMessages(session.id, messages.slice(-maxMsgs));
  if (typeof SessionSync !== 'undefined') SessionSync.markLocalDirty();
  renderSessionList();
  scheduleSessionSync();
}

let _sessionSyncTimer = null;
let _sessionSyncRetryCount = 0;
const SESSION_SYNC_MAX_RETRY = 6;

function scheduleSessionSync() {
  if (_suppressSessionPush) return;
  clearTimeout(_sessionSyncTimer);
  _sessionSyncRetryCount = 0;
  _sessionSyncTimer = setTimeout(syncSessionsToDevice, 400);
}

function scheduleSessionSyncRetry() {
  _sessionSyncRetryCount += 1;
  if (_sessionSyncRetryCount > SESSION_SYNC_MAX_RETRY) return;
  const delay = Math.min(400 * (2 ** (_sessionSyncRetryCount - 1)), 30000);
  clearTimeout(_sessionSyncTimer);
  _sessionSyncTimer = setTimeout(syncSessionsToDevice, delay);
}

function flushSessionSyncOnUnload() {
  clearTimeout(_sessionSyncTimer);
  const payload = buildSessionSyncPayload();
  if (!payload.sessions.length) return;
  const body = JSON.stringify(payload);
  try {
    fetch('/api/ai/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getApiHeaders() },
      body,
      keepalive: true,
    }).catch(() => {});
  } catch {}
}

async function syncSessionsToDevice() {
  const payload = buildSessionSyncPayload();
  try {
    const { data } = await api('POST', '/api/ai/sessions', payload);
    if (data?.ok) {
      if (typeof SessionSync !== 'undefined') {
        SessionSync.setServerSyncMeta(data);
        SessionSync.clearLocalDirty();
      }
      _sessionSyncRetryCount = 0;
    } else {
      scheduleSessionSyncRetry();
    }
  } catch {
    scheduleSessionSyncRetry();
  }
}

function getProtectedSessionIds() {
  const ids = new Set();
  if (isLocallyStreaming() && SessionStore.activeId) ids.add(SessionStore.activeId);
  for (const s of SessionStore.listWithContent()) {
    if (isSessionJobRunning(s.id)) ids.add(s.id);
  }
  return ids;
}

function mergeSessionRecords(remoteSessions, localSessions, opts = {}) {
  if (typeof SessionSync !== 'undefined') {
    return SessionSync.mergeSessionRecords(
      remoteSessions,
      localSessions,
      SessionStore.sessionHasContent,
      opts,
    );
  }
  return remoteSessions;
}

async function applyRemoteSessionsData(data) {
  if (!data?.ok) return false;

  if (typeof SessionSync !== 'undefined' && SessionSync.shouldSkipRemoteMerge({ data })) {
    return false;
  }

  _suppressSessionPush = true;
  try {
  const prevActiveId = SessionStore.activeId;
  const prevMessagesJson = JSON.stringify(getCurrentMessages());

  const localActiveBefore = SessionStore.activeId;
  const remoteSessions = (Array.isArray(data.sessions) ? data.sessions : [])
    .filter((s) => SessionStore.sessionHasContent(s));
  const localSessions = SessionStore.listWithContent();
  const localHasContent = localSessions.length > 0;
  const protectedSessionIds = getProtectedSessionIds();

  const remoteAuthoritative = typeof SessionSync !== 'undefined'
    && SessionSync.shouldTakeRemoteAuthoritative(data)
    && !isLocallyStreaming();

  let merged = [];
  if (remoteSessions.length || localSessions.length) {
    merged = mergeSessionRecords(remoteSessions, localSessions, {
      remoteAuthoritative,
      protectedSessionIds,
    });
  }

  if (!merged.length) {
    SessionStore.startDraft();
    return false;
  }

  const activeId = (pinnedActiveSessionId && merged.some((s) => s.id === pinnedActiveSessionId))
    ? pinnedActiveSessionId
    : (isDraftSessionView()
      ? null
      : (typeof SessionSync !== 'undefined'
        ? SessionSync.pickActiveId({
          merged,
          data,
          localHasContent,
          localActiveBefore,
        })
        : merged[0].id));

  SessionStore.importMerged(merged, activeId, {
    draft: isDraftSessionView(),
    preserveJobIds: protectedSessionIds,
  });
  if (typeof SessionSync !== 'undefined') SessionSync.setServerSyncMeta(data);
  _gatewayHydrated = true;

  const messagesChanged = JSON.stringify(getCurrentMessages()) !== prevMessagesJson;
  const activeChanged = prevActiveId !== SessionStore.activeId;
  return messagesChanged || activeChanged;
  } finally {
    _suppressSessionPush = false;
  }
}

async function loadSessionDetail(sessionId) {
  if (!sessionId) return false;
  const { data } = await api(
    'GET',
    `/api/ai/sessions?session_id=${encodeURIComponent(sessionId)}`,
    null,
    { timeoutMs: 20000 },
  );
  if (!data?.ok || !data.session) return false;
  SessionStore.patchSession(sessionId, data.session);
  return true;
}

async function ensureSessionMessagesLoaded(sessionId) {
  if (!sessionId) return false;
  const session = SessionStore.getById(sessionId);
  if (!session) return false;
  if ((session.messages || []).length) return true;
  if (!session.hasContent && !(Number(session.messageCount) > 0)) return false;
  return loadSessionDetail(sessionId);
}

async function loadSessionsFromDevice() {
  const { data } = await api('GET', '/api/ai/sessions?compact=1', null, { timeoutMs: 20000 });
  return applyRemoteSessionsData(data);
}

async function applyRemoteConfigData(config) {
  if (!config || configSaveState === 'dirty' || configSaveInFlight) return false;
  const prev = JSON.stringify(savedConfig);
  if (JSON.stringify(config) === prev) return false;
  await applyServerConfig(config);
  const provider = els.providerSelect?.value;
  const savedModel = savedConfig.model || defaults[provider] || '';
  await ensureModelsLoaded(savedModel, { refresh: false });
  refreshEmbeddingModels();
  applyEmbeddingModelSelection(savedConfig.embeddingModel || '');
  showConfigureHint();
  return true;
}

async function refreshSessionViewFromRemote() {
  const hadLocalSessions = SessionStore.listWithContent().length > 0;
  const sessionsChanged = await loadSessionsFromDevice();
  const configChanged = await pullConfigFromDevice();
  renderSessionList();
  if (pinnedActiveSessionId) return;
  if (isSessionStreaming(SessionStore.activeId)) {
    updateLiveAssistantFromSession();
    return;
  }
  const gainedRemote = !hadLocalSessions && SessionStore.listWithContent().length > 0;
  if (sessionsChanged || configChanged || gainedRemote) {
    if (isDraftSessionView()) {
      renderSessionList();
      return;
    }
    const activeId = SessionStore.activeId;
    if (activeId) await ensureSessionMessagesLoaded(activeId);
    if (pinnedActiveSessionId) return;
    renderStoredMessages({ force: true });
    await syncActiveSessionStreaming();
  }
}

async function refreshSessionView() {
  await refreshSessionViewFromRemote();
}

function updateLiveAssistantFromSession() {
  const session = SessionStore.getActive();
  if (!session?.messages?.length) return;
  const last = normalizeStoredMessage(session.messages[session.messages.length - 1]);
  if (last.role !== 'assistant') return;
  const ui = getLiveStreamUi() || getLastAssistantUi();
  if (!ui) return;
  hydrateAssistantUi(ui, last);
}

function aiSyncWsUrl() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${location.host}/api/ai/sync/ws`;
}

function isSyncWsConnected() {
  return typeof SyncWsClient !== 'undefined' && SyncWsClient.isConnected();
}

function sendSyncWs(payload) {
  if (typeof SyncWsClient !== 'undefined') SyncWsClient.send(payload);
}

function reconnectSyncWebSocket() {
  if (typeof SyncWsClient !== 'undefined') SyncWsClient.reconnect();
}

function connectSyncWebSocket() {
  if (typeof SyncWsClient === 'undefined') return;
  SyncWsClient.connect({
    onMessage: handleSyncWsMessage,
    onFallback: scheduleSyncWsFallback,
  });
}

function scheduleSyncWsFallback() {
  refreshSessionViewFromRemote().catch(() => {});
}

function startSyncWebSocket() {
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      connectSyncWebSocket();
      refreshSessionViewFromRemote().catch(() => {});
      if (typeof ChatJobs !== 'undefined') ChatJobs.recoverStuckStreams?.().catch(() => {});
    } else if (typeof SyncWsClient !== 'undefined') SyncWsClient.close();
  });
  connectSyncWebSocket();
  setInterval(() => {
    if (isSyncWsConnected()) sendSyncWs({ type: 'ping' });
  }, 25000);
  setInterval(() => {
    if (typeof ChatJobs !== 'undefined') ChatJobs.recoverStuckStreams?.().catch(() => {});
  }, 12000);
  if (typeof SyncWsClient !== 'undefined') {
    SyncWsClient.startFallbackPolling(() => {
      refreshSessionViewFromRemote().catch(() => {});
      if (typeof ChatJobs !== 'undefined') {
        ChatJobs.resumePolling();
        ChatJobs.recoverStuckStreams?.().catch(() => {});
      }
    }, 15000);
  }
}

async function handleSyncWsSessions(data) {
  if (typeof SessionSync !== 'undefined') SessionSync.setServerSyncMeta(data);
  if (isDraftSessionView()) {
    await applyRemoteSessionsData(data);
    renderSessionList();
    return;
  }
  const locallyAttached = SessionStore.listWithContent().some((s) => isSessionJobRunning(s.id));
  const changed = await applyRemoteSessionsData(data);
  renderSessionList();
  if (locallyAttached) {
    updateLiveAssistantFromSession();
    return;
  }
  if (changed) {
    renderStoredMessages({ force: true });
    await syncActiveSessionStreaming();
  }
}

async function handleSyncWsHello(data) {
  _syncWsGotHello = true;
  if (typeof SessionSync !== 'undefined') SessionSync.setServerSyncMeta(data);
  const remoteVersion = Number(data.stateVersion || data.savedAt || 0);
  if (_lastStateVersion && remoteVersion && remoteVersion < _lastStateVersion) {
    sendSyncWs({ type: 'resync' });
  } else if (remoteVersion) {
    _lastStateVersion = Math.max(_lastStateVersion, remoteVersion);
  }
  applyBuiltinAgents(data);
  if (data.driving !== undefined || data.state) applyStatusFromPayload(data);
  if (data.notifications) handleWsNotifications(data);
  if (data.sessions) await handleSyncWsSessions(data);
  if (data.config) await applyRemoteConfigData(data.config);
  if (data.deviceTrust?.needsPairing && typeof DeviceTrust !== 'undefined') {
    DeviceTrust.ensureTrusted(api).catch(() => {});
  }
  if (Array.isArray(data.activeJobs) && data.activeJobs.length) {
    if (typeof ChatJobs !== 'undefined' && ChatJobs.resumeActiveJobs) {
      await ChatJobs.resumeActiveJobs(data.activeJobs);
    } else {
      await syncActiveSessionStreaming();
    }
  }
}

function applyStatusFromPayload(data) {
  if (!data || data.ok === false) return;
  state = {
    ...state,
    driving: !!data.driving,
    state: data.state || state?.state || {},
    configured: data.ai?.configured ?? state?.configured,
    adminMode: data.adminMode ?? state?.adminMode,
  };
  if (data.hostEnvironment) hostEnvironment = data.hostEnvironment;
  applyStatusPill(data);
  if (typeof OfficePanel !== 'undefined') {
    OfficePanel.setDrivingMode?.(!!data.driving);
    OfficePanel.setVehicleState?.(data.state);
  }
}

function handleWsNotifications(data) {
  if (!data?.ok) return;
  const items = data.notifications || [];
  const unread = items.filter((i) => !i.read).length;
  updateNotificationsBadge(unread);
  if (notificationsOpen) renderNotifications(items);
}

async function handleSyncWsMessage(data) {
  if (!data?.type) return;
  switch (data.type) {
    case 'hello':
      await handleSyncWsHello(data);
      break;
    case 'connect_ack':
      if (!data.ok) console.warn('sync connect_ack', data.error);
      break;
    case 'protocol_error':
      console.warn('sync protocol_error', data.error);
      break;
    case 'sessions':
      await handleSyncWsSessions(data);
      break;
    case 'config':
      if (data.config) {
        const changed = await applyRemoteConfigData(data.config);
        if (changed) updateModelBadgeFromSaved();
      }
      break;
    case 'status':
      applyStatusFromPayload(data);
      break;
    case 'notifications':
      handleWsNotifications(data);
      break;
    case 'chat_event':
    case 'chat_status':
      await handleSyncWsChatEvent(data);
      break;
    case 'office':
      applyBuiltinAgents(data);
      break;
    case 'canvas':
      if (typeof CanvasPanel !== 'undefined') CanvasPanel.handleWs(data);
      break;
    case 'lifecycle':
      if (data.phase === 'stuck' && typeof showToast === 'function') {
        showToast('聊天任务可能卡住，请稍后重试');
      }
      break;
    case 'pong':
      break;
    default:
      break;
  }
}

function normalizeStoredMessage(msg) {
  if (!msg || typeof msg !== 'object') return msg;
  const out = { ...msg };
  if (out.role === 'assistant') {
    if (!out.tool_results) out.tool_results = {};
    if (!out.tool_calls) out.tool_calls = [];
    if (!out.agent_events) out.agent_events = [];
    if (typeof out.content === 'string') {
      out.content = stripLeakedToolCalls(out.content);
    }
  }
  return out;
}

function prepareMessagesForApi(messages) {
  const MAX_API_MESSAGES = 64;
  const MAX_TOOL_RESULT_CHARS = 12000;
  const trimToolResult = (value) => {
    if (value == null) return value;
    let text;
    try {
      text = typeof value === 'string' ? value : JSON.stringify(value);
    } catch {
      text = String(value);
    }
    if (text.length <= MAX_TOOL_RESULT_CHARS) return value;
    const clipped = `${text.slice(0, MAX_TOOL_RESULT_CHARS)}\n…[truncated]`;
    return typeof value === 'string' ? clipped : { ok: true, truncated: true, preview: clipped };
  };
  const recent = messages.slice(-MAX_API_MESSAGES);
  return recent.map((m) => {
    if (m.role === 'user') return { role: 'user', content: m.content };
    if (m.role !== 'assistant') return { ...m };
    const out = { role: 'assistant' };
    if (m.content) out.content = m.content;
    if (m.reasoning_content != null && m.reasoning_content !== '') {
      out.reasoning_content = m.reasoning_content;
    } else if (m.tool_calls?.length) {
      out.reasoning_content = m.reasoning_content || '';
    }
    if (m.tool_calls?.length) {
      out.tool_calls = m.tool_calls;
      const raw = m.tool_results || {};
      const trimmed = {};
      Object.keys(raw).forEach((id) => {
        trimmed[id] = trimToolResult(raw[id]);
      });
      out.tool_results = trimmed;
    }
    return out;
  });
}

function isMobileLayout() {
  return MOBILE_LAYOUT_MQ.matches;
}

let knowledgeOpen = false;
let notificationsOpen = false;
let notificationsPollTimer = null;

function syncBodyScrollLock() {
  const locked = Boolean(
    cabanaOpen ||
    secocOpen ||
    knowledgeOpen ||
    notificationsOpen ||
    (typeof OfficePanel !== 'undefined' && OfficePanel.isOpen()) ||
    (typeof TerminalPanel !== 'undefined' && TerminalPanel.isOpen()) ||
    els.sessionsPanel?.classList.contains('open') ||
    els.settingsSidebar?.classList.contains('open') ||
    (els.writeConfirmModal && !els.writeConfirmModal.hidden) ||
    (els.publishPromptModal && !els.publishPromptModal.hidden) ||
    usageDetailOpen,
  );
  document.body.style.overflow = locked ? 'hidden' : '';
}

function openKnowledgeModal(opts = {}) {
  knowledgeOpen = true;
  setOverlayVisible(els.knowledgeModal, true);
  els.knowledgeBtn?.classList.add('active');
  syncBodyScrollLock();
  if (opts.onboarding) {
    onboardingRagSetupActive = true;
    if (els.onboardingRagSetup) els.onboardingRagSetup.hidden = false;
    if (els.knowledgeMainContent) els.knowledgeMainContent.classList.add('hidden');
    if (els.onboardingRagReindex) els.onboardingRagReindex.checked = true;
    if (els.onboardingRagWiki) els.onboardingRagWiki.checked = true;
    if (els.onboardingRagStatus) els.onboardingRagStatus.textContent = '';
    if (els.knowledgeClose) els.knowledgeClose.hidden = true;
  } else {
    finishOnboardingKnowledgeSetup({ keepOpen: true });
  }
  loadRagPanel();
}

function finishOnboardingKnowledgeSetup({ keepOpen = false } = {}) {
  onboardingRagSetupActive = false;
  if (els.onboardingRagSetup) els.onboardingRagSetup.hidden = true;
  if (els.knowledgeMainContent) els.knowledgeMainContent.classList.remove('hidden');
  if (els.knowledgeClose) els.knowledgeClose.hidden = false;
  if (!keepOpen && knowledgeOpen) {
    closeKnowledgeModal();
  }
}

async function runOnboardingRagSetup() {
  const doReindex = !!els.onboardingRagReindex?.checked;
  const doWiki = !!els.onboardingRagWiki?.checked;
  if (!doReindex && !doWiki) {
    finishOnboardingKnowledgeSetup();
    return;
  }
  const setStatus = (msg) => {
    if (els.onboardingRagStatus) els.onboardingRagStatus.textContent = msg;
  };
  const run = async () => {
    if (doWiki) {
      setStatus(t('onboardingRagWikiRunning', '正在拉取社区 Wiki…'));
      const job = await startRagBackgroundJob(
        {
          operation: 'wiki_ingest',
          all_registered: true,
          max_files_per_repo: RAG_WIKI_MAX_FILES_PER_REPO,
          force: false,
          chain_reindex: doReindex,
        },
        {
          onPhase: (phase) => setStatus(ragJobPhaseLabel(phase)),
        },
      );
      const wiki = job?.result?.wiki || job?.result || {};
      if (wiki.ok === false) throw new Error(wiki.error || t('ragWikiSyncFailed', 'Wiki 同步失败'));
      setStatus(tf('ragWikiSyncResult', { indexed: Number(wiki.indexed) || 0 }));
    } else if (doReindex) {
      setStatus(t('onboardingRagIndexRunning', '正在建立向量索引…'));
      const job = await startRagBackgroundJob({ operation: 'reindex' });
      const res = job?.result?.reindex || job?.result || job;
      if (res?.ok === false) throw new Error(res.error || t('ragReindexFailed', '索引失败'));
      setStatus(tf('onboardingRagDone', { indexed: res.indexed, total: res.total }));
    }
    showToast(t('onboardingRagComplete', '知识库设置完成'), 'success');
    loadUsage();
    finishOnboardingKnowledgeSetup({ keepOpen: true });
    loadRagPanel();
  };
  if (typeof UiBusy !== 'undefined') {
    if (els.onboardingRagSkipBtn) els.onboardingRagSkipBtn.disabled = true;
    try {
      await UiBusy.withButtonBusy(els.onboardingRagStartBtn, run, { busyLabel: t('uiWorking', '处理中…') });
    } catch (e) {
      setStatus(String(e?.message || e));
      showToast(String(e?.message || e), 'error');
    } finally {
      if (els.onboardingRagSkipBtn) els.onboardingRagSkipBtn.disabled = false;
    }
  } else {
    try {
      await run();
    } catch (e) {
      setStatus(String(e?.message || e));
      showToast(String(e?.message || e), 'error');
    }
  }
}

function openOnboardingKnowledgeSetup() {
  openKnowledgeModal({ onboarding: true });
}

function closeKnowledgeModal() {
  if (onboardingRagSetupActive) {
    onboardingRagSetupActive = false;
    if (els.onboardingRagSetup) els.onboardingRagSetup.hidden = true;
    if (els.knowledgeMainContent) els.knowledgeMainContent.classList.remove('hidden');
    if (els.knowledgeClose) els.knowledgeClose.hidden = false;
  }
  knowledgeOpen = false;
  setOverlayVisible(els.knowledgeModal, false);
  els.knowledgeBtn?.classList.remove('active');
  syncBodyScrollLock();
}

function toggleKnowledgeModal() {
  if (knowledgeOpen) closeKnowledgeModal();
  else openKnowledgeModal();
}

function formatNotifTime(at) {
  if (!at) return '';
  try {
    return new Date(at * 1000).toLocaleString();
  } catch {
    return '';
  }
}

function renderNotifications(items) {
  const list = els.notificationsList;
  if (!list) return;
  list.innerHTML = '';
  if (!items?.length) {
    const li = document.createElement('li');
    li.className = 'notifications-empty';
    li.textContent = t('notificationsEmpty', '暂无通知');
    list.appendChild(li);
    return;
  }
  for (const n of items) {
    const li = document.createElement('li');
    li.className = `notifications-item level-${n.level || 'info'}${n.read ? '' : ' unread'}`;
    li.innerHTML = `<div class="notifications-item-title">${escapeHtml(n.title || '')}</div>`
      + `<div class="notifications-item-body">${escapeHtml(n.body || '')}</div>`
      + `<time class="notifications-item-time">${formatNotifTime(n.at)}</time>`;
    list.appendChild(li);
  }
}

function updateNotificationsBadge(count) {
  const badge = els.notificationsBadge;
  if (!badge) return;
  if (count > 0) {
    badge.hidden = false;
    badge.textContent = count > 99 ? '99+' : String(count);
    els.notificationsBtn?.classList.remove('hidden');
  } else {
    badge.hidden = true;
    els.notificationsBtn?.classList.add('hidden');
  }
}

function applyHeaderChrome() {
  const kind = hostEnvironment?.host_kind;
  const showCabana = kind === 'pc_dev' || kind === 'comma_device';
  els.cabanaBtn?.classList.toggle('hidden', !showCabana);
}

async function loadNotifications() {
  const { data } = await api('GET', '/api/ai/notifications?unread=0');
  if (!data.ok) return [];
  const items = data.notifications || [];
  if (notificationsOpen) renderNotifications(items);
  updateNotificationsBadge(items.filter((i) => !i.read).length);
  return items;
}

async function markAllNotificationsRead() {
  await api('POST', '/api/ai/notifications', {});
  await loadNotifications();
}

function openNotificationsPanel() {
  notificationsOpen = true;
  els.notificationsPanel?.classList.add('open');
  els.notificationsPanel?.removeAttribute('hidden');
  els.notificationsBackdrop?.classList.add('visible');
  els.notificationsBackdrop?.removeAttribute('hidden');
  els.notificationsBtn?.classList.add('active');
  syncBodyScrollLock();
  loadNotifications();
}

function closeNotificationsPanel() {
  notificationsOpen = false;
  els.notificationsPanel?.classList.remove('open');
  els.notificationsPanel?.setAttribute('hidden', '');
  els.notificationsBackdrop?.classList.remove('visible');
  els.notificationsBackdrop?.setAttribute('hidden', '');
  els.notificationsBtn?.classList.remove('active');
  syncBodyScrollLock();
}

function toggleNotificationsPanel() {
  if (notificationsOpen) closeNotificationsPanel();
  else openNotificationsPanel();
}

function startNotificationsPolling() {
  if (notificationsPollTimer) return;
  notificationsPollTimer = setInterval(() => {
    if (isSyncWsConnected() || document.visibilityState !== 'visible') return;
    loadNotifications().catch(() => {});
  }, 120000);
}

function loadSessionMode() {
  /* single mode: unlimited */
}

function openCabanaModal() {
  ensureCabanaInited();
  cabanaOpen = true;
  setOverlayVisible(els.cabanaModal, true);
  els.cabanaBtn?.classList.add('active');
  syncBodyScrollLock();
  if (typeof CabanaPanel !== 'undefined') {
    CabanaPanel.syncMode?.();
    CabanaPanel.refresh().catch((e) => console.error('Cabana refresh failed', e));
  }
}

function closeCabanaModal() {
  cabanaOpen = false;
  setOverlayVisible(els.cabanaModal, false);
  els.cabanaBtn?.classList.remove('active');
  syncBodyScrollLock();
  if (typeof CabanaPanel !== 'undefined') {
    CabanaPanel.disconnectLive?.();
    CabanaPanel.disconnectReplay?.();
  }
}

function toggleCabanaModal() {
  if (cabanaOpen) closeCabanaModal();
  else openCabanaModal();
}

async function sendTextToChat(text, opts = {}) {
  if (!text?.trim()) return;
  if (!opts.keepCabanaOpen) closeCabanaModal();
  SessionStore.ensureSessionOnSend(text.trim());
  renderSessionList();
  els.chatInput.value = text;
  autoResize();
  await sendChat(new Event('submit'));
}

function clearWelcomePanel() {
  els.messages.querySelectorAll('.welcome-hero, .welcome-banner, .quick-actions').forEach((el) => el.remove());
}

function getQuickActionsList() {
  if (typeof OP_QUICK_ACTIONS !== 'undefined' && Array.isArray(OP_QUICK_ACTIONS)) {
    return OP_QUICK_ACTIONS;
  }
  return [];
}

function getComposerQuickActions() {
  return [];
}

function messageHasVisibleContent(msg) {
  if (!msg || typeof msg !== 'object') return false;
  if (msg.role === 'user') {
    const text = messageText(msg.content).trim();
    const imgs = messageImages(msg.content);
    return Boolean(text || imgs.length);
  }
  if (msg.role === 'assistant') {
    const text = messageText(msg.content).trim();
    if (text) return true;
    if (msg.tool_calls?.length) return true;
    if (msg.reasoning_content?.trim()) return true;
  }
  return false;
}

function hasVisibleChatHistory(messages) {
  return Array.isArray(messages) && messages.some(messageHasVisibleContent);
}

function syncMessagesLayoutMode() {
  if (!els.messages) return;
  const welcome = !hasVisibleChatHistory(getCurrentMessages());
  els.messages.classList.toggle('messages-welcome', welcome);
}

// ---------------------------------------------------------------------------
// Session list UI
// ---------------------------------------------------------------------------

function renderSessionList() {
  if (!els.sessionList) return;
  const sessions = SessionStore.listWithContent();
  const activeId = SessionStore.activeId;
  els.sessionList.innerHTML = '';
  if (!sessions.length) {
    const li = document.createElement('li');
    li.className = 'session-item session-item-empty';
    li.textContent = t('sessionsEmpty', '发送第一条消息后将出现在这里');
    els.sessionList.appendChild(li);
    return;
  }
  for (const s of sessions) {
    const li = document.createElement('li');
    const streaming = isSessionStreaming(s.id);
    if (!streaming && isSessionJobRunning(s.id) && typeof ChatJobs !== 'undefined') {
      ChatJobs.scheduleStaleJobSweep(s.id);
      ChatJobs.scheduleSweepAllPendingJobs?.();
    }
    li.className = `session-item${s.id === activeId ? ' active' : ''}${streaming ? ' streaming' : ''}`;
    if (streaming) {
      li.setAttribute('aria-busy', 'true');
      const status = document.createElement('span');
      status.className = 'session-status-spinner';
      status.setAttribute('role', 'status');
      status.title = t('sessionRunning', 'Generating…');
      status.setAttribute('aria-label', t('sessionRunning', 'Generating…'));
      li.appendChild(status);
    }
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'session-btn';
    btn.textContent = s.title || t('newChat', 'New chat');
    btn.title = s.title || '';
    btn.addEventListener('click', () => switchSession(s.id));
    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'session-delete';
    del.textContent = '×';
    del.title = t('deleteSession', 'Delete');
    del.addEventListener('click', (e) => {
      e.stopPropagation();
      deleteSession(s.id);
    });
    li.appendChild(btn);
    li.appendChild(del);
    els.sessionList.appendChild(li);
  }
}

function isLocallyStreaming(sessionId = SessionStore.activeId) {
  if (!sessionId) return false;
  return SessionStore.activeId === sessionId && isSessionStreaming(sessionId);
}

function isChatUiLocked() {
  return isLocallyStreaming(SessionStore.activeId);
}

let sessionSwitchGeneration = 0;
let pinnedActiveSessionId = null;

function isDraftSessionView() {
  return typeof SessionStore.isDraftMode === 'function' && SessionStore.isDraftMode();
}

function getLiveStreamUi() {
  const live = els.messages?.querySelector('.assistant-wrapper[data-live-stream="1"]');
  if (!live) return null;
  return wrapperToAssistantUi(live);
}

function reconcileStreamUi(ctx) {
  if (!ctx?.isVisible?.()) return ctx?.ui ?? null;
  if (ctx.ui?.wrapper?.isConnected) return ctx.ui;
  const live = getLiveStreamUi();
  if (live?.wrapper?.isConnected) {
    ctx.ui = live;
    return live;
  }
  const existing = getLastAssistantUi();
  if (existing?.wrapper?.isConnected) {
    markLiveStreamUi(existing);
    ctx.ui = existing;
    return existing;
  }
  const messages = getCurrentMessages();
  const last = messages[messages.length - 1];
  if (last?.role !== 'user') return ctx?.ui ?? null;
  const ui = appendAssistantMessage({ withLoading: true });
  markLiveStreamUi(ui);
  ctx.ui = ui;
  return ui;
}

function resolveAttachAssistantUi(messages, sessionId) {
  if (SessionStore.activeId !== sessionId) return null;
  if (!SessionStore.getActiveJobId(sessionId)) return null;

  const live = getLiveStreamUi();
  if (live?.wrapper?.isConnected) return live;

  const last = messages[messages.length - 1];
  const prev = messages[messages.length - 2];

  if (last?.role === 'user') {
    return appendAssistantMessage({ withLoading: true });
  }

  if (last?.role === 'assistant' && prev?.role === 'user') {
    const existing = getLastAssistantUi();
    if (existing?.wrapper?.isConnected) return existing;
    return appendAssistantMessage({ withLoading: !assistantMessageHasContent(last) });
  }

  return null;
}

async function copyTextToClipboard(text) {
  const value = String(text || '');
  if (!value) return false;
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch {
      /* fall through */
    }
  }
  const ta = document.createElement('textarea');
  ta.value = value;
  ta.setAttribute('readonly', '');
  ta.style.position = 'fixed';
  ta.style.left = '-9999px';
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand('copy');
  } catch {
    ok = false;
  }
  document.body.removeChild(ta);
  return ok;
}

function assistantMessageHasContent(msg) {
  if (!msg) return false;
  const text = stripLeakedToolCalls(messageText(msg.content) || (typeof msg.content === 'string' ? msg.content : ''));
  return Boolean(
    text
    || (msg.reasoning_content && String(msg.reasoning_content).trim())
    || (msg.tool_calls && msg.tool_calls.length)
    || (msg.agent_events && msg.agent_events.length)
  );
}

function hideAssistantLoading(ui) {
  if (!ui) return;
  ui.wrapper?.querySelectorAll('.assistant-loading').forEach((el) => el.remove());
  ui.loading = null;
  if (!ui.thinking) return;
  const hasReasoning = Boolean(String(ui.thinkingBody?.textContent || '').trim());
  ui.thinkingWaitingDots?.classList.add('hidden');
  ui.thinking.classList.remove('is-activity-waiting');
  if (!hasReasoning) ui.thinking.classList.add('hidden');
}

function renderThinkingContent(el, text) {
  if (!el) return;
  const raw = String(text || '').trim();
  if (!raw) {
    el.innerHTML = '';
    return;
  }
  el.classList.add('chat-thinking');
  const mdText = (typeof Markdown !== 'undefined' && typeof Markdown.formatReasoningMarkdown === 'function')
    ? Markdown.formatReasoningMarkdown(raw)
    : raw;
  if (typeof Markdown !== 'undefined' && typeof Markdown.renderToElement === 'function') {
    Markdown.renderToElement(el, mdText, { streaming: false, cursor: false });
  } else {
    el.textContent = raw;
  }
}

function setDetailsCollapsed(el, collapsed) {
  if (!el) return;
  if (el.tagName === 'DETAILS') el.open = !collapsed;
  else el.classList.toggle('collapsed', collapsed);
}

function syncThinkingBlock(ui, msg) {
  if (!ui?.thinking) return;
  const hasReasoning = Boolean(String(msg?.reasoning_content || '').trim());
  if (!hasReasoning) {
    ui.thinking.classList.add('hidden');
    return;
  }
  hideAssistantLoading(ui);
  ui.thinking.classList.remove('hidden', 'is-activity-waiting');
  ui.thinkingWaitingDots?.classList.add('hidden');
  setDetailsCollapsed(ui.thinking, true);
  if (ui.thinkingBody) renderThinkingContent(ui.thinkingBody, msg.reasoning_content);
  if (ui.thinkingLabel) ui.thinkingLabel.textContent = t('thinking', 'Thinking');
}

function clearLiveStreamChrome(ui) {
  hideAssistantLoading(ui);
  if (!ui) return;
  ui.content?.classList.remove('streaming');
  const hasReasoning = Boolean(String(ui.thinkingBody?.textContent || '').trim());
  if (!hasReasoning) ui.thinking?.classList.add('hidden');
}

function showAssistantLoading(ui) {
  if (!ui?.thinking) return;
  const hasReasoning = Boolean(String(ui.thinkingBody?.textContent || '').trim());
  if (hasReasoning) return;
  hideAssistantLoading(ui);
  ui.thinking.classList.remove('hidden');
  ui.thinking.classList.add('is-activity-waiting');
  setDetailsCollapsed(ui.thinking, true);
  if (ui.thinkingLabel) ui.thinkingLabel.textContent = t('assistantLoading', '正在思考…');
  ui.thinkingWaitingDots?.classList.remove('hidden');
  if (ui.thinkingBody) ui.thinkingBody.innerHTML = '';
}

function endChatStream(sessionId) {
  if (sessionId && streamSessionId === sessionId) {
    streamSessionId = null;
    abortController = null;
  }
  // Do not call ChatJobs.endPoll() — other sessions may still stream in background.
  if (!sessionId || SessionStore.activeId === sessionId) {
    els.messages?.querySelectorAll('.assistant-wrapper[data-live-stream="1"]').forEach((el) => {
      clearLiveStreamChrome(wrapperToAssistantUi(el));
      delete el.dataset.liveStream;
    });
    if (els.sendBtn) updateComposerSendBtn();
  }
}

function isChatTraceEnabled() {
  return !!(typeof LocalPrefs !== 'undefined' && LocalPrefs.getChatDebugPrefs?.().trace);
}

function updateTraceSummary(traceBlock) {
  const list = traceBlock?.querySelector('.chat-trace-list');
  const countEl = traceBlock?.querySelector('.trace-count');
  const count = list?.querySelectorAll('.assistant-trace-line').length || 0;
  if (countEl) countEl.textContent = count ? `(${count})` : '';
  if (count) traceBlock?.classList.remove('hidden');
  else traceBlock?.classList.add('hidden');
}

function appendTraceLine(ui, message, round) {
  if (!ui?.traceBlock || !isChatTraceEnabled()) return;
  const list = ui.traceList || ui.traceBlock.querySelector('.chat-trace-list');
  if (!list) return;
  const line = document.createElement('div');
  line.className = 'assistant-trace-line';
  const prefix = round != null ? `[${round}] ` : '';
  line.textContent = `${prefix}${String(message || '')}`;
  list.appendChild(line);
  setDetailsCollapsed(ui.traceBlock, true);
  updateTraceSummary(ui.traceBlock);
}

function wrapperToAssistantUi(wrapper) {
  const bubble = wrapper.querySelector('.chat-bubble') || wrapper;
  const thinking = bubble.querySelector('.chat-thinking-collapse, .thinking-block');
  const agentCallsBlock = bubble.querySelector('.chat-activity-collapse, .agent-calls-block');
  const toolsBlock = bubble.querySelector('.chat-tools-collapse, .tool-calls-block');
  const traceBlock = bubble.querySelector('.chat-trace-collapse');
  const turn = wrapper.closest('.message-turn');
  return {
    wrapper,
    turn,
    bubble,
    loading: null,
    thinking,
    thinkingLabel: thinking?.querySelector('.thinking-label'),
    thinkingBody: thinking?.querySelector('.thinking-body, .chat-thinking'),
    thinkingWaitingDots: thinking?.querySelector('.thinking-waiting-dots'),
    agentCallsBlock,
    agentCallsList: agentCallsBlock?.querySelector('.chat-activity-list, .agent-calls-list'),
    toolsBlock,
    toolsList: toolsBlock?.querySelector('.chat-tools-list, .tool-calls-list'),
    traceBlock,
    traceList: traceBlock?.querySelector('.chat-trace-list'),
    content: bubble.querySelector('.chat-bubble > .chat-text.message.assistant, .chat-bubble > .chat-text, .chat-text.message.assistant'),
    footer: bubble.querySelector('.chat-group-footer'),
    actionsBar: turn?.querySelector('.message-actions-bar'),
  };
}

function getLastAssistantUi() {
  const wrappers = els.messages?.querySelectorAll('.assistant-wrapper');
  if (!wrappers?.length) return null;
  return wrapperToAssistantUi(wrappers[wrappers.length - 1]);
}

function markLiveStreamUi(ui) {
  if (ui?.wrapper) ui.wrapper.dataset.liveStream = '1';
}

function scrollToMessageIndex(idx) {
  const el = els.messages?.querySelector(`[data-msg-idx="${idx}"]`);
  if (!el) return false;
  chatScrollPinned = false;
  updateJumpToBottomButton();
  el.scrollIntoView({ block: 'center', behavior: 'smooth' });
  el.classList.add('search-hit-flash');
  setTimeout(() => el.classList.remove('search-hit-flash'), 2200);
  return true;
}

async function navigateToSessionHit(hit) {
  if (!hit?.sessionId) return;
  const sessionId = hit.sessionId;
  const needsSwitch = SessionStore.activeId !== sessionId;
  if (needsSwitch) {
    switchSession(sessionId);
    const session = SessionStore.getById(sessionId);
    if (session?.hasContent && !(session.messages || []).length) {
      await loadSessionDetail(sessionId);
      loadSessionMode();
      renderStoredMessages();
      renderSessionList();
    }
  }
  let msgIdx = typeof hit.messageIndex === 'number' ? hit.messageIndex : -1;
  if (msgIdx < 0 && typeof SessionSearch !== 'undefined') {
    msgIdx = SessionSearch.findMessageIndex(sessionId, hit);
  }
  if (msgIdx >= 0) {
    requestAnimationFrame(() => {
      if (!scrollToMessageIndex(msgIdx)) {
        setTimeout(() => scrollToMessageIndex(msgIdx), 120);
      }
    });
  }
}

function switchSession(id) {
  const gen = ++sessionSwitchGeneration;
  pinnedActiveSessionId = id;
  cancelEditUserMessage();
  SessionStore.setActive(id);
  refreshModelBadgeForSession();
  if (typeof SessionModelPicker !== 'undefined') SessionModelPicker.refresh();
  updateComposerSendBtn();
  if (els.messages) clearMessagesPreservingJump();
  if (typeof ChatJobs !== 'undefined') ChatJobs.detachInactiveStreamUis?.();

  const finishSwitch = async () => {
    try {
      if (gen !== sessionSwitchGeneration) return;
      if (SessionStore.activeId !== id) SessionStore.setActive(id);
      loadSessionMode();
      await ensureSessionMessagesLoaded(id);
      if (gen !== sessionSwitchGeneration) return;
      if (SessionStore.activeId !== id) SessionStore.setActive(id);
      renderStoredMessages({ force: true, forceScroll: true, switchGen: gen, sessionId: id });
      renderSessionList();
      if (typeof ChatJobs !== 'undefined') {
        await ChatJobs.verifySessionJobId(id);
        if (gen !== sessionSwitchGeneration) return;
        await syncActiveSessionStreaming();
      }
      if (gen !== sessionSwitchGeneration) return;
      if (typeof CanvasPanel !== 'undefined') CanvasPanel.loadSession(id).catch(() => {});
      closeSessionsDrawer();
    } finally {
      if (pinnedActiveSessionId === id) pinnedActiveSessionId = null;
    }
  };

  finishSwitch().catch(() => {
    if (pinnedActiveSessionId === id) pinnedActiveSessionId = null;
  });
  renderSessionList();
  scheduleSessionSync();
}

function createNewSession() {
  ++sessionSwitchGeneration;
  pinnedActiveSessionId = null;
  cancelEditUserMessage();
  SessionStore.startDraft();
  const before = SessionStore.listWithContent();
  const deduped = typeof SessionSync !== 'undefined' && SessionSync.dedupeSessionList
    ? SessionSync.dedupeSessionList(before)
    : before;
  if (deduped.length < before.length) {
    SessionStore.importMerged(deduped, null, { draft: true });
    scheduleSessionSync();
  }
  refreshModelBadgeForSession();
  if (typeof SessionModelPicker !== 'undefined') SessionModelPicker.refresh();
  updateComposerSendBtn();
  clearMessagesPreservingJump();
  renderStoredMessages({ force: true, draft: true });
  renderSessionList();
  closeSessionsDrawer();
}

function formatResolvedModelLabel(model) {
  if (typeof ChatModelTag !== 'undefined') return ChatModelTag.formatResolvedModelLabel(model);
  const raw = String(model || '').trim();
  if (!raw) return '';
  return raw.length > 28 ? `${raw.slice(0, 26)}…` : raw;
}

function setMessageModelTag(ui, resolvedModel) {
  if (!ui) return;
  ui._resolvedModel = resolvedModel;
  renderMessageFooter(ui, { resolvedModel, usage: ui._usage });
}

function hubPrimaryChatRoute() {
  const hub = effectiveModelHub(savedConfig);
  const primary = hub?.primary;
  if (!primary?.accountId || !primary?.model) return null;
  return { accountId: primary.accountId, model: primary.model };
}

function updateModelBadge(label, title) {
  if (!els.modelBadge) return;
  const raw = String(label || '').trim();
  const display = raw || t('modelUnset', 'Not configured');
  els.modelBadge.textContent = display;
  els.modelBadge.title = String(title || raw || display);
  els.modelBadge.classList.toggle('unset', !raw);
}

function refreshModelBadgeForSession() {
  const hub = effectiveModelHub(savedConfig);
  const session = SessionStore.getActive();
  if (typeof SessionModelPicker !== 'undefined') {
    const route = SessionModelPicker.getEffectiveRoute(session, hub);
    updateModelBadge(
      SessionModelPicker.formatRouteLabel(route, hub),
      SessionModelPicker.formatRouteTitle(route, hub),
    );
    return;
  }
  updateModelBadge(savedConfig?.model || '');
}

function updateModelBadgeFromSaved() {
  refreshModelBadgeForSession();
}

function formatApiError(raw) {
  const text = String(raw || '').trim();
  if (!text) return t('chatErrorGeneric', '请求失败，请稍后重试。');
  if (/Server got itself in trouble|500 Internal Server Error/i.test(text)) {
    return t(
      'serverErrorHint',
      'op助手 服务内部错误。请在车机执行: tail -50 /tmp/aid.log；若提示 web UI missing，请运行 git submodule update --init ai 或 ai/install/install.sh，然后重启 manager。',
    );
  }
  if (/401|403|AuthError|Invalid API key|invalid api key|authentication/i.test(text)) {
    const prov = savedConfig?.provider || els.providerSelect?.value || '';
    const provLabel = prov ? providerDisplayName(prov) : t('provider', '服务商');
    return `${t('apiKeyInvalidHint', 'API 密钥无效或与当前服务商不匹配。请在 设置→模型 重新填写密钥并点击「保存」。')}\n${t('apiKeyInvalidProvider', '当前生效')}: ${provLabel}${savedConfig?.model ? ` · ${savedConfig.model}` : ''}\n\n${text}`;
  }
  return text;
}

function hasUnsavedConfigDraft() {
  const draft = LocalPrefs.getConfigDraft();
  if (!draft || !savedConfig || !Object.keys(savedConfig).length) return false;
  const keys = ['provider', 'model', 'baseUrl'];
  return keys.some((k) => {
    const a = draft[k];
    const b = savedConfig[k];
    if (a === undefined || a === null || a === '') return false;
    return String(a) !== String(b ?? '');
  });
}

function showUnsavedConfigWarning() {}

function deleteSession(id) {
  abortSessionChat(id);
  SessionStore.remove(id);
  if (!SessionStore.listWithContent().length) {
    SessionStore.startDraft();
  }
  loadSessionMode();
  renderStoredMessages({ force: true });
  renderSessionList();
  scheduleSessionSync();
}

function openSessionsDrawer() {
  renderSessionList();
  els.sessionsPanel?.classList.add('open');
  els.sessionsPanel?.setAttribute('aria-hidden', 'false');
  els.sessionsToggleBtn?.classList.add('active');
  if (els.sessionsBackdrop) {
    els.sessionsBackdrop.hidden = false;
    requestAnimationFrame(() => els.sessionsBackdrop.classList.add('visible'));
  }
  syncBodyScrollLock();
}

function closeSessionsDrawer() {
  els.sessionsPanel?.classList.remove('open');
  els.sessionsPanel?.setAttribute('aria-hidden', 'true');
  els.sessionsToggleBtn?.classList.remove('active');
  els.sessionsBackdrop?.classList.remove('visible');
  syncBodyScrollLock();
  setTimeout(() => {
    if (!els.sessionsPanel?.classList.contains('open') && els.sessionsBackdrop) {
      els.sessionsBackdrop.hidden = true;
    }
  }, 260);
}

function toggleSessionsPanel() {
  if (els.sessionsPanel?.classList.contains('open')) {
    closeSessionsDrawer();
  } else {
    openSessionsDrawer();
  }
}

// ---------------------------------------------------------------------------
// Settings drawer (all screen sizes)
// ---------------------------------------------------------------------------

const SETTINGS_TAB_PANES = {
  api: 'paneModel',
  model: 'paneModel',
  knowledge: 'paneKnowledge',
  scheduler: 'paneScheduler',
  platform: 'panePlatform',
  dev: 'paneDev',
};

function normalizeSettingsTab(name) {
  if (!name || name === 'api') return 'model';
  return name;
}

function syncSettingsSaveBar(_tabName) {
  const bar = document.getElementById('settingsSaveBar');
  if (bar) bar.hidden = true;
}

function openSecocModal() {
  secocOpen = true;
  setOverlayVisible(els.secocModal, true);
  els.secocBtn?.classList.add('active');
  if (typeof TskPanel !== 'undefined') TskPanel.startPoll();
  syncBodyScrollLock();
}

function closeSecocModal() {
  secocOpen = false;
  setOverlayVisible(els.secocModal, false);
  els.secocBtn?.classList.remove('active');
  if (typeof TskPanel !== 'undefined') TskPanel.stopPoll();
  syncBodyScrollLock();
}

function openSettings(tab) {
  closeSecocModal();
  closeCabanaModal();
  closeKnowledgeModal();
  closeSessionsDrawer();
  ensureProviderOptions();
  loadConfig().then(() => {
    if (savedConfig) applyModelHubFromConfig(savedConfig);
  }).catch(console.error);
  if (!models.length) {
    ensureModelsLoaded(savedConfig?.model || '').catch(console.error);
  }
  els.settingsSidebar?.classList.add('open');
  els.settingsSidebar?.setAttribute('aria-hidden', 'false');
  if (els.settingsBackdrop) {
    els.settingsBackdrop.hidden = false;
    requestAnimationFrame(() => els.settingsBackdrop.classList.add('visible'));
  }
  syncBodyScrollLock();
  const activeTab = tab ? normalizeSettingsTab(tab) : 'model';
  activateSettingsTab(activeTab);
  if (!tab) loadUsage();
}

function activateSettingsTab(name) {
  const tabName = normalizeSettingsTab(name);
  const tab = document.querySelector(`.settings-tab[data-tab="${tabName}"]`)
    || document.querySelector(`.settings-tab[data-tab="${name}"]`);
  if (!tab) return;
  $$('.settings-tab').forEach((t) => t.classList.toggle('active', t === tab));
  $$('.settings-pane').forEach((p) => p.classList.remove('active'));
  const paneId = SETTINGS_TAB_PANES[tabName] || SETTINGS_TAB_PANES[name];
  document.getElementById(paneId)?.classList.add('active');
  syncSettingsSaveBar(tabName);
  tab.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
  if (tabName === 'scheduler') {
    loadSchedulerPanel();
    if (typeof WorkbuddyPanel !== 'undefined') WorkbuddyPanel.onSettingsOpen('scheduler');
  }
  if (tabName === 'dev') {
    renderDevPane();
    if (typeof CanvasPanel !== 'undefined') {
      CanvasPanel.loadSession(SessionStore.activeId).catch(() => {});
    }
  }
  if (tabName === 'knowledge') {
    loadKnowledgeRagStatus().catch(() => {});
  }
  if (tabName === 'model') loadUsage();
  if (tabName === 'platform' && typeof PlatformPanel !== 'undefined') {
    PlatformPanel.onSettingsOpen('platform');
  }
  if (tabName === 'platform' && typeof WorkbuddyPanel !== 'undefined') {
    WorkbuddyPanel.onSettingsOpen('platform');
  }
}

function openSettingsTab(tab) {
  if (tab === 'secoc') {
    openSecocModal();
    return;
  }
  openSettings(tab);
}

function closeSettings() {
  els.settingsSidebar?.classList.remove('open');
  els.settingsSidebar?.setAttribute('aria-hidden', 'true');
  els.settingsBackdrop?.classList.remove('visible');
  syncBodyScrollLock();
  setTimeout(() => {
    if (!els.settingsSidebar?.classList.contains('open') && els.settingsBackdrop) {
      els.settingsBackdrop.hidden = true;
    }
  }, 260);
}

function bindSettingsTabs() {
  $$('.settings-tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      activateSettingsTab(tab.dataset.tab);
    });
  });
}

function ensureProviderOptions() {
  if (!providers.length) {
    providers = FALLBACK_PROVIDERS.slice();
    providerLabels = { ...FALLBACK_PROVIDER_LABELS };
    renderProviderOptions();
  }
}

const SCHED_ACTION_OPTIONS = [
  { value: 'read_usage', key: 'schedActionReadUsage' },
  { value: 'read_last_log', key: 'schedActionReadLog' },
  { value: 'read_tune_snapshot', key: 'schedActionTuneSnapshot' },
  { value: 'snapshot_tune', key: 'schedActionParamSnapshot' },
  { value: 'memory_ping', key: 'schedActionMemoryPing' },
  { value: 'trip_review_offroad', key: 'schedActionTripReview' },
  { value: 'reindex_rag_wifi', key: 'schedActionReindexRag' },
  { value: 'check_critical_events', key: 'schedActionCheckEvents' },
  { value: 'post_drive_review_offroad', key: 'schedActionPostDriveReview' },
  { value: 'check_param_watchlist_offroad', key: 'schedActionParamWatchlist' },
  { value: 'git_fetch_wifi', key: 'schedActionGitFetch' },
];

function applySchedulerFormI18n() {
  const paneDesc = $('#schedulerPaneDesc');
  if (paneDesc) paneDesc.textContent = t('schedulerPaneDesc');
  const nameLabel = $('#schedNameLabel');
  if (nameLabel) nameLabel.textContent = t('schedName');
  const actionLabel = $('#schedActionLabel');
  if (actionLabel) actionLabel.textContent = t('schedAction');
  const triggerLabel = $('#schedTriggerLabel');
  if (triggerLabel) triggerLabel.textContent = t('schedTrigger');
  const intervalLabel = $('#schedIntervalLabel');
  if (intervalLabel) intervalLabel.textContent = t('schedInterval');
  const schedHourLabel = $('#schedHourLabel');
  if (schedHourLabel) schedHourLabel.textContent = t('schedHourLabel');
  const schedMinuteLabel = $('#schedMinuteLabel');
  if (schedMinuteLabel) schedMinuteLabel.textContent = t('schedMinuteLabel');
  if (els.schedAddBtn) els.schedAddBtn.textContent = t('schedAdd');
  if (els.schedActionModeBtn) els.schedActionModeBtn.textContent = t('manual', 'Manual');
  if (els.schedActionCustom) els.schedActionCustom.placeholder = t('schedActionCustom');
  if (els.schedAction) {
    const current = schedActionManual ? '__custom__' : (els.schedAction.value || 'read_usage');
    els.schedAction.innerHTML = [
      ...SCHED_ACTION_OPTIONS.map((o) => `<option value="${o.value}">${t(o.key)}</option>`),
      `<option value="__custom__">${t('schedActionCustomOption')}</option>`,
    ].join('');
    els.schedAction.value = SCHED_ACTION_OPTIONS.some((o) => o.value === current) ? current : '__custom__';
  }
  if (els.schedTrigger) {
    const triggerVal = els.schedTrigger.value || 'interval';
    els.schedTrigger.innerHTML = `
      <option value="interval">${t('schedTriggerInterval')}</option>
      <option value="on_offroad">${t('schedTriggerOffroad')}</option>
      <option value="on_ignition">${t('schedTriggerIgnition')}</option>
      <option value="on_wifi">${t('schedTriggerWifi')}</option>
      <option value="daily_at">${t('schedTriggerDaily')}</option>`;
    els.schedTrigger.value = triggerVal;
  }
  setSchedActionMode(schedActionManual);
  updateSchedDailyFieldsVisibility();
}

function updateSchedDailyFieldsVisibility() {
  const daily = els.schedTrigger?.value === 'daily_at';
  if (els.schedDailyFields) els.schedDailyFields.classList.toggle('hidden', !daily);
}

function setSchedActionMode(manual) {
  schedActionManual = manual;
  if (!els.schedAction || !els.schedActionCustom || !els.schedActionModeBtn) return;
  els.schedAction.classList.toggle('hidden', manual);
  els.schedActionCustom.classList.toggle('hidden', !manual);
  els.schedActionModeBtn.textContent = manual ? t('dropdown', 'Dropdown') : t('manual', 'Manual');
  if (manual && !els.schedActionCustom.value) {
    const fromSelect = els.schedAction.value;
    if (fromSelect && fromSelect !== '__custom__') {
      els.schedActionCustom.value = fromSelect;
    }
  }
}

function getSchedActionValue() {
  if (schedActionManual) {
    return (els.schedActionCustom?.value || '').trim() || 'read_usage';
  }
  const v = els.schedAction?.value || 'read_usage';
  if (v === '__custom__') {
    return (els.schedActionCustom?.value || '').trim() || 'read_usage';
  }
  return v;
}

async function fetchRagApi({ compact = false, timeoutMs = 10000 } = {}) {
  const q = compact ? '?compact=1' : '';
  return api('GET', `/api/ai/rag${q}`, null, { timeoutMs });
}

async function loadRagPanel() {
  if (!els.ragDocList) return;
  if (typeof UiBusy !== 'undefined') {
    UiBusy.showPanelLoading(els.ragDocList, t('uiLoading', '加载中…'));
  }
  const { data } = await fetchRagApi({ timeoutMs: 30000 });
  if (typeof UiBusy !== 'undefined') UiBusy.clearPanelBusy(els.ragDocList);
  if (!data.ok || !els.ragDocList) return;
  applyRagStatsFromApi(data);
  await loadKnowledgeRagStatus(data);
  const docs = data.documents || [];
  const chunks = data.vector_chunks ?? 0;
  if (els.ragVectorStatus) {
    els.ragVectorStatus.textContent = tf('ragVectorStatus', { chunks, count: data.count ?? docs.length });
  }
  els.ragDocList.innerHTML = docs.length
    ? docs.map((d) => `
      <div class="rag-item" data-id="${d.id}">
        <b>${escapeHtml(d.title)}</b>
        <span class="field-hint">${d.chars} ${d.embedded ? t('ragCharsEmbedded') : t('ragCharsOnly')}</span>
        <button type="button" class="btn link rag-del" data-id="${d.id}">${t('ragDelete')}</button>
      </div>`).join('')
    : `<p class="field-hint">${t('ragNoDocs')}</p>`;
  els.ragDocList.querySelectorAll('.rag-del').forEach((btn) => {
    btn.addEventListener('click', async () => {
      if (btn.classList.contains('is-loading')) return;
      const docId = btn.dataset.id;
      if (typeof UiBusy !== 'undefined') {
        UiBusy.setButtonBusy(btn, true, { busyLabel: t('uiDeleting', '删除中…') });
      } else {
        btn.disabled = true;
      }
      const { data } = await api('POST', '/api/ai/rag', { operation: 'remove', doc_id: docId });
      if (typeof UiBusy !== 'undefined') {
        UiBusy.setButtonBusy(btn, false);
      } else {
        btn.disabled = false;
      }
      if (data.ok) {
        showToast(t('ragDeleted', '文档已删除'), 'success');
        loadRagPanel();
      } else {
        showToast(data.error || t('ragDeleteFailed', '删除失败'), 'error');
      }
    });
  });
}

function setRagActionsBusy(busy, busyLabel) {
  const buttons = [els.ragSaveBtn, els.ragSyncWikiBtn, els.ragReindexBtn];
  if (typeof UiBusy !== 'undefined') {
    UiBusy.setGroupBusy(buttons, busy, busyLabel ? { busyLabel } : {});
    return;
  }
  buttons.forEach((btn) => {
    if (btn) btn.disabled = busy;
  });
}

const RAG_JOB_POLL_MS = 2000;
const RAG_JOB_TIMEOUT_MS = 20 * 60 * 1000;

function ragJobPhaseLabel(phase) {
  if (phase === 'wiki_ingest') return t('ragWikiSyncing', '正在同步社区 Wiki…');
  if (phase === 'reindex') return t('ragReindexing', '正在重建向量索引…');
  if (phase === 'wiki_done') return t('ragWikiReindexing', '正在重建向量索引…');
  return t('uiWorking', '处理中…');
}

async function pollRagJob({ onPhase } = {}) {
  const started = Date.now();
  while (Date.now() - started < RAG_JOB_TIMEOUT_MS) {
    const { data } = await api('GET', '/api/ai/rag?job=1', null, { timeoutMs: 12000 });
    if (!data?.ok) throw new Error(data?.error || t('ragJobFailed', '知识库任务失败'));
    const job = data.job || {};
    const running = data.running ?? (job.status === 'queued' || job.status === 'running');
    const phase = data.phase || job.phase || job.operation;
    if (typeof onPhase === 'function' && phase) onPhase(phase);
    if (!running) {
      if ((data.status || job.status) === 'error') throw new Error(data.error || job.error || t('ragJobFailed', '知识库任务失败'));
      return { ...data, result: data.result || { wiki: job.wiki, reindex: job.reindex } };
    }
    await new Promise((r) => setTimeout(r, RAG_JOB_POLL_MS));
  }
  throw new Error(t('ragJobTimeout', '知识库任务超时，请稍后在设置中查看状态'));
}

async function startRagBackgroundJob(body, { onPhase } = {}) {
  const { data } = await api('POST', '/api/ai/rag', { background: true, ...body }, { timeoutMs: 15000 });
  if (!data?.ok) {
    if (data?.job?.running) throw new Error(t('ragJobBusy', '已有知识库任务进行中'));
    throw new Error(data?.error || t('ragJobFailed', '知识库任务失败'));
  }
  if (data.started || data.jobId) return pollRagJob({ onPhase });
  return data;
}

async function reindexRag({ silent = false } = {}) {
  if (!els.ragReindexBtn) return false;
  if (els.ragReindexBtn.classList.contains('is-loading')) return false;
  if (typeof UiBusy !== 'undefined') {
    UiBusy.setButtonBusy(els.ragReindexBtn, true, { busyLabel: t('ragReindexing', '索引中…') });
  } else {
    els.ragReindexBtn.disabled = true;
  }
  try {
    const job = await startRagBackgroundJob(
      { operation: 'reindex' },
      {
        onPhase: (phase) => {
          if (typeof UiBusy !== 'undefined' && phase === 'reindex') {
            UiBusy.setButtonBusy(els.ragReindexBtn, true, { busyLabel: t('ragReindexing', '索引中…') });
          }
        },
      },
    );
    const res = job?.result?.reindex || job?.result || job;
    if (res?.ok !== false) {
      if (!silent) {
        showToast(
          tf('ragReindexResult', { indexed: res.indexed, total: res.total }),
          res.errors?.length ? 'warning' : 'success',
        );
      }
      loadRagPanel();
      loadUsage();
      return true;
    }
    if (!silent) showToast(res.error || t('ragReindexFailed'), 'error');
    return false;
  } catch (e) {
    if (!silent) showToast(String(e?.message || e), 'error');
    return false;
  } finally {
    if (typeof UiBusy !== 'undefined') {
      UiBusy.setButtonBusy(els.ragReindexBtn, false);
    } else {
      els.ragReindexBtn.disabled = false;
    }
  }
}

async function syncWikiRag() {
  if (!els.ragSyncWikiBtn || els.ragSyncWikiBtn.classList.contains('is-loading')) return;
  if (typeof UiBusy !== 'undefined') {
    UiBusy.setButtonBusy(els.ragSyncWikiBtn, true, { busyLabel: t('ragWikiSyncingShort', '同步中…') });
  } else {
    els.ragSyncWikiBtn.disabled = true;
  }
  try {
    const job = await startRagBackgroundJob(
      {
        operation: 'wiki_ingest',
        all_registered: true,
        max_files_per_repo: RAG_WIKI_MAX_FILES_PER_REPO,
        force: false,
        chain_reindex: true,
      },
      {
        onPhase: (phase) => {
          if (typeof UiBusy !== 'undefined') {
            UiBusy.setButtonBusy(els.ragSyncWikiBtn, true, {
              busyLabel: ragJobPhaseLabel(phase),
            });
          }
        },
      },
    );
    const wiki = job?.result?.wiki || job?.result || {};
    const reindex = job?.result?.reindex || {};
    const indexed = Number(wiki.indexed) || 0;
    const vectorChunks = Number(reindex.vector_chunks) || 0;
    if ((wiki.skipped || indexed === 0) && vectorChunks === 0) {
      showToast(t('ragWikiSyncSkipped', 'Wiki 无新变化（已达文档上限或未变更时可忽略）'), 'info');
    } else if (vectorChunks > 0) {
      showToast(tf('ragReindexResult', { indexed: reindex.indexed || vectorChunks, total: reindex.total || indexed }), 'success');
    } else {
      showToast(tf('ragWikiSyncResult', { indexed }), indexed > 0 ? 'success' : 'info');
    }
    await loadRagPanel();
    loadUsage();
  } catch (e) {
    showToast(String(e?.message || e), 'error');
  } finally {
    if (typeof UiBusy !== 'undefined') {
      UiBusy.setButtonBusy(els.ragSyncWikiBtn, false);
    } else {
      els.ragSyncWikiBtn.disabled = false;
    }
  }
}

async function saveRagDoc() {
  const title = (els.ragTitle?.value || '').trim();
  const text = (els.ragText?.value || '').trim();
  if (!text || els.ragSaveBtn?.classList.contains('is-loading')) return;
  const run = async () => {
    const { data } = await api('POST', '/api/ai/rag', { title: title || t('ragNoteDefault'), text });
    if (data.ok) {
      if (els.ragTitle) els.ragTitle.value = '';
      if (els.ragText) els.ragText.value = '';
      showToast(t('saved', '已保存'), 'success');
      loadRagPanel();
      loadUsage();
    } else {
      showToast(data.error || t('saveFailed', '保存失败'), 'error');
    }
  };
  if (typeof UiBusy !== 'undefined') {
    await UiBusy.withButtonBusy(els.ragSaveBtn, run, { busyLabel: t('uiSaving', '保存中…') });
  } else {
    els.ragSaveBtn.disabled = true;
    try {
      await run();
    } finally {
      els.ragSaveBtn.disabled = false;
    }
  }
}

function renderConsumerQuickActions(_wizards) {
  // Top quick-action bar removed; use welcome cards + slash commands instead.
}

function resolveConsumerWizard(wizardId) {
  const list = window.__consumerWizards || [];
  return list.find((w) => w.id === wizardId) || null;
}

async function startConsumerWizard(wizardId, workflowId) {
  const cached = resolveConsumerWizard(wizardId);
  let prompt = cached?.starter_prompt || '';
  let workflow = workflowId || cached?.workflow_id || '';

  if (!prompt) {
    const { data } = await api(
      'GET',
      `/api/ai/consumer/wizards/${encodeURIComponent(wizardId)}/start`,
      null,
      { timeoutMs: 8000 },
    ).catch(() => ({ data: {} }));
    prompt = data?.message || data?.wizard?.starter_prompt || '';
    workflow = workflow || data?.workflow || data?.wizard?.workflow_id || '';
  }

  if (!prompt?.trim()) {
    showToast(t('quickActionsMissing', '快捷卡片未加载，请刷新页面。'), 'error');
    return;
  }

  await sendUserMessage(prompt, { workflow, consumerMode: true });
}

function renderConsumerWritePreview(consumerPreview, rawPreview) {
  const box = els.writeConfirmConsumer;
  const rawEl = els.writeConfirmPreview;
  if (!box) return;
  const cp = consumerPreview || {};
  const rows = cp.rows || [];
  if (rows.length) {
    box.classList.remove('hidden');
    box.innerHTML = `
      <p class="write-confirm-summary">${escapeHtml(cp.summary || t('writeConfirmConsumerSummary', '将调整以下驾驶设置：'))}</p>
      ${rows.map((r) => `
        <div class="write-confirm-row">
          <span class="label">${escapeHtml(r.label || r.key)}</span>
          <span class="before">${escapeHtml(r.before)}</span>
          <span class="after">→ ${escapeHtml(r.after)}</span>
          ${r.hint ? `<span class="hint">${escapeHtml(r.hint)}</span>` : ''}
        </div>`).join('')}`;
    if (rawEl) {
      rawEl.classList.add('hidden');
      rawEl.textContent = '';
    }
  } else {
    box.classList.add('hidden');
    box.innerHTML = '';
    if (rawEl) {
      rawEl.classList.remove('hidden');
      rawEl.textContent = typeof rawPreview === 'string' ? rawPreview : JSON.stringify(rawPreview, null, 2);
    }
  }
}

function showWriteConfirmModal(preview, pendingId, toolResult) {
  return new Promise((resolve) => {
    if (!els.writeConfirmModal) return resolve({ ok: false, error: 'no modal' });
    const consumerPreview = toolResult?.consumer_preview || toolResult?.consumerPreview;
    renderConsumerWritePreview(consumerPreview, preview);
    if (els.writeConfirmRollback) {
      els.writeConfirmRollback.classList.toggle('hidden', !toolResult?.action?.includes?.('tune') && toolResult?.action !== 'write_params');
    }
    els.writeConfirmModal.hidden = false;
    syncBodyScrollLock();
    const cleanup = () => {
      els.writeConfirmModal.hidden = true;
      syncBodyScrollLock();
      els.writeConfirmOk.removeEventListener('click', onOk);
      els.writeConfirmCancel.removeEventListener('click', onCancel);
      els.writeConfirmClose?.removeEventListener('click', onCancel);
      els.writeConfirmBackdrop?.removeEventListener('click', onCancel);
      els.writeConfirmRollback?.removeEventListener('click', onRollback);
    };
    const onCancel = () => { cleanup(); resolve({ ok: false, cancelled: true }); };
    const onRollback = async () => {
      cleanup();
      await sendUserMessage(t('rollbackTunePrompt', '请帮我撤销上一次调参，恢复之前的快照。'), { consumerMode: true });
      resolve({ ok: false, cancelled: true, rollback: true });
    };
    const onOk = async () => {
      cleanup();
      const { data } = await api('POST', '/api/ai/write/confirm', { pending_id: pendingId });
      resolve(data);
      if (data?.ok) setTimeout(() => maybeShowPublishPrompt(), 400);
    };
    els.writeConfirmOk.addEventListener('click', onOk);
    els.writeConfirmCancel.addEventListener('click', onCancel);
    els.writeConfirmClose?.addEventListener('click', onCancel);
    els.writeConfirmBackdrop?.addEventListener('click', onCancel);
    els.writeConfirmRollback?.addEventListener('click', onRollback);
  });
}

async function loadSchedulerPanel() {
  const { data } = await api('GET', '/api/ai/scheduler');
  if (!data.ok || !els.schedulerTaskList) return;
  const tasks = data.tasks || [];
  const minLabel = t('schedMinutes', 'min');
  els.schedulerTaskList.innerHTML = tasks.length
    ? tasks.map((task) => {
        const trig = task.trigger || 'interval';
        const payload = task.payload || {};
        const trigLabel = trig === 'daily_at'
          ? `${t('schedTriggerDaily')} ${payload.hour ?? 8}:${String(payload.minute ?? 0).padStart(2, '0')}`
          : trig;
        return `
      <div class="scheduler-item" data-id="${task.id}">
        <div><b>${escapeHtml(task.name || task.action)}</b> · ${escapeHtml(trigLabel)} · ${task.interval_minutes || '-'} ${minLabel}</div>
        <div class="field-hint">${escapeHtml(task.last_result || t('schedNotRun'))}</div>
        <button type="button" class="btn link sched-del" data-id="${task.id}">${t('schedDelete')}</button>
      </div>`;
      }).join('')
    : `<p class="field-hint">${t('schedNoTasks')}</p>`;
  els.schedulerTaskList.querySelectorAll('.sched-del').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset.id;
      const prev = btn.textContent;
      btn.disabled = true;
      btn.textContent = t('schedDeleting');
      try {
        const { data: res } = await api('POST', '/api/ai/scheduler', { operation: 'remove', task_id: id });
        if (res.ok && res.removed) {
          showToast(t('schedDeleted'), 'success');
          await loadSchedulerPanel();
        } else {
          showToast(res.error || t('saveFailed', 'Save failed'), 'error');
          btn.disabled = false;
          btn.textContent = prev;
        }
      } catch {
        showToast(t('saveFailed', 'Save failed'), 'error');
        btn.disabled = false;
        btn.textContent = prev;
      }
    });
  });
}

async function addSchedulerTask() {
  if (!els.schedAddBtn || els.schedAddBtn.disabled) return;
  const name = (els.schedName?.value || '').trim();
  const action = getSchedActionValue();
  const interval = parseInt(els.schedInterval?.value || '60', 10);
  const prevText = els.schedAddBtn.textContent;
  els.schedAddBtn.disabled = true;
  els.schedAddBtn.classList.add('is-loading');
  els.schedAddBtn.textContent = t('schedAdding');
  try {
    const trigger = els.schedTrigger?.value || 'interval';
    const payload = trigger === 'daily_at'
      ? {
          hour: Math.min(23, Math.max(0, parseInt(els.schedHour?.value || '9', 10))),
          minute: Math.min(59, Math.max(0, parseInt(els.schedMinute?.value || '0', 10))),
        }
      : {};
    const { data } = await api('POST', '/api/ai/scheduler', {
      name: name || action,
      action,
      interval_minutes: interval,
      enabled: true,
      trigger,
      payload,
    });
    if (data.ok) {
      if (els.schedName) els.schedName.value = '';
      showToast(t('schedAdded'), 'success');
      await loadSchedulerPanel();
    } else {
      showToast(data.error || t('saveFailed', 'Save failed'), 'error');
    }
  } catch {
    showToast(t('saveFailed', 'Save failed'), 'error');
  } finally {
    els.schedAddBtn.disabled = false;
    els.schedAddBtn.classList.remove('is-loading');
    els.schedAddBtn.textContent = prevText;
  }
}

function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ---------------------------------------------------------------------------
// Message rendering & multimodal helpers
// ---------------------------------------------------------------------------

function messageText(content) {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content.filter((p) => p.type === 'text').map((p) => p.text).join('\n');
  }
  return '';
}

function messageImages(content) {
  if (!Array.isArray(content)) return [];
  return content
    .filter((p) => p.type === 'image_url')
    .map((p) => p.image_url?.url)
    .filter(Boolean);
}

function buildUserContent(text, images) {
  const parts = [];
  const trimmed = (text || '').trim();
  if (trimmed) parts.push({ type: 'text', text: trimmed });
  for (const img of images) {
    parts.push({ type: 'image_url', image_url: { url: img.dataUrl } });
  }
  if (parts.length === 0) return '';
  if (parts.length === 1 && parts[0].type === 'text') return parts[0].text;
  return parts;
}

async function buildUserMessageContent(text, images, contextRefs = []) {
  let finalText = (text || '').trim();
  const refs = (contextRefs || []).slice();
  if (refs.length) {
    const blocks = [];
    for (const ref of refs) {
      const type = ref.type || (ref.kind === 'dir' ? 'dir' : 'file');
      try {
        if (type === 'browser') {
          blocks.push(`\n\n---\n@${t('mentionBrowser', 'Browser')}\n${t('mentionBrowserPrompt', 'You may fetch live web pages and use browser tools when helpful.')}`);
          continue;
        }
        if (type === 'branch') {
          const q = ref.branch ? `branch=${encodeURIComponent(ref.branch)}` : '';
          const { data } = await api('GET', `/api/ai/context/branch${q ? `?${q}` : ''}`);
          if (data?.ok && data.content) {
            const label = data.branch || ref.name || 'branch';
            blocks.push(`\n\n---\n@Branch ${label}\n\`\`\`diff\n${data.content}\n\`\`\``);
          }
          continue;
        }
        if (type === 'session') {
          const { data } = await api('GET', `/api/ai/context/session?session_id=${encodeURIComponent(ref.sessionId)}`);
          if (data?.ok && data.content) {
            const label = data.title || ref.name || ref.sessionId;
            blocks.push(`\n\n---\n@Past chat: ${label}\n\`\`\`\n${data.content}\n\`\`\``);
          }
          continue;
        }
        if (type === 'url') {
          const { data } = await api('GET', `/api/ai/context/url?url=${encodeURIComponent(ref.url)}`);
          if (data?.ok && data.content) {
            const label = data.title || ref.url;
            blocks.push(`\n\n---\n@${label}\n${ref.url}\n\`\`\`\n${data.content}\n\`\`\``);
          }
          continue;
        }
        const { data } = await api('GET', `/api/ai/files/content?path=${encodeURIComponent(ref.path)}`);
        if (data?.ok && data.content) {
          const label = data.rel || ref.rel || ref.name;
          const fence = data.kind === 'dir' ? '' : '';
          blocks.push(`\n\n---\n@${label}\n\`\`\`${fence}\n${data.content}\n\`\`\``);
        }
      } catch {
        const label = ref.rel || ref.name || ref.url || ref.sessionId || type;
        blocks.push(`\n\n---\n@${label}\n(${t('mentionReadFailed', '无法读取上下文')})`);
      }
    }
    if (blocks.length) {
      finalText = (finalText || t('mentionDefaultPrompt', '请结合以下上下文回答：')) + blocks.join('');
    }
  }
  return buildUserContent(finalText, images);
}

function loadImageElement(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function compressImageFile(file) {
  if (!file?.type?.startsWith('image/')) {
    throw new Error('not an image');
  }
  const dataUrl = await readFileAsDataUrl(file);
  const img = await loadImageElement(dataUrl);
  let width = img.naturalWidth || img.width;
  let height = img.naturalHeight || img.height;
  const scale = Math.min(1, MAX_IMAGE_DIMENSION / Math.max(width, height, 1));
  width = Math.max(1, Math.round(width * scale));
  height = Math.max(1, Math.round(height * scale));
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(img, 0, 0, width, height);
  const usePng = file.type === 'image/png' || file.type === 'image/gif' || file.type === 'image/webp';
  const mimeType = usePng ? 'image/png' : 'image/jpeg';
  const outUrl = usePng
    ? canvas.toDataURL('image/png')
    : canvas.toDataURL('image/jpeg', JPEG_QUALITY);
  return { dataUrl: outUrl, mimeType };
}

async function addImageFiles(files) {
  const list = Array.from(files || []).filter((f) => f.type.startsWith('image/'));
  if (!list.length) return;
  const remaining = MAX_IMAGES_PER_MESSAGE - pendingImages.length;
  if (remaining <= 0) {
    showToast(t('imageLimit', 'Maximum 9 images per message'), 'warning');
    return;
  }
  for (const file of list.slice(0, remaining)) {
    try {
      pendingImages.push(await compressImageFile(file));
    } catch {
      showToast(t('imageReadFailed', 'Failed to read image'), 'error');
    }
  }
  if (list.length > remaining) {
    showToast(t('imageLimit', 'Maximum 9 images per message'), 'warning');
  }
  renderComposerAttachments();
}

function pendingRefKey(ref) {
  const type = ref.type || (ref.kind === 'dir' ? 'dir' : 'file');
  if (type === 'url') return `url:${ref.url}`;
  if (type === 'branch') return 'branch';
  if (type === 'browser') return 'browser';
  if (type === 'session') return `session:${ref.sessionId}`;
  return `file:${ref.path}`;
}

function removePendingRef(ref) {
  const key = pendingRefKey(ref);
  pendingFileRefs = pendingFileRefs.filter((item) => pendingRefKey(item) !== key);
  renderComposerAttachments();
}

function renderComposerAttachments() {
  const hasImages = pendingImages.length > 0;
  const hasFiles = pendingFileRefs.length > 0;
  if (!hasImages && !hasFiles) {
    els.composerAttachments.classList.add('hidden');
    els.composerAttachments.innerHTML = '';
    return;
  }
  els.composerAttachments.classList.remove('hidden');
  els.composerAttachments.innerHTML = '';

  pendingFileRefs.forEach((ref) => {
    const item = document.createElement('div');
    item.className = 'composer-file-chip';
    const icon = document.createElement('span');
    icon.className = 'composer-file-chip-icon';
    const type = ref.type || (ref.kind === 'dir' ? 'dir' : 'file');
    const iconMap = { dir: '📁', file: '📄', url: '🔗', branch: '⎇', session: '💬', browser: '🌐' };
    icon.textContent = iconMap[type] || '📄';
    const label = document.createElement('span');
    label.className = 'composer-file-chip-name';
    label.textContent = ref.rel || ref.name || ref.title || ref.url || ref.sessionId || type;
    label.title = ref.path || ref.url || ref.sessionId || ref.rel || ref.name || '';
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'composer-file-chip-remove';
    remove.textContent = '×';
    remove.title = t('mentionRemoveFile', 'Remove file');
    remove.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      removePendingRef(ref);
    });
    item.appendChild(icon);
    item.appendChild(label);
    item.appendChild(remove);
    els.composerAttachments.appendChild(item);
  });

  pendingImages.forEach((img, index) => {
    const item = document.createElement('div');
    item.className = 'composer-attachment';
    const thumb = document.createElement('img');
    thumb.src = img.dataUrl;
    thumb.alt = '';
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'composer-attachment-remove';
    remove.textContent = '×';
    remove.title = t('removeImage', 'Remove');
    remove.addEventListener('click', () => {
      pendingImages.splice(index, 1);
      renderComposerAttachments();
    });
    item.appendChild(thumb);
    item.appendChild(remove);
    els.composerAttachments.appendChild(item);
  });
}

function clearComposerAttachments() {
  pendingImages = [];
  pendingFileRefs = [];
  renderComposerAttachments();
}

function renderMarkdownContent(el, text) {
  if (!el || !text) {
    if (el) el.textContent = '';
    return;
  }
  const clean = stripLeakedToolCalls(text);
  if (!clean) {
    el.textContent = '';
    return;
  }
  if (typeof Markdown !== 'undefined' && typeof Markdown.renderToElement === 'function') {
    Markdown.renderToElement(el, clean, { streaming: false });
    return;
  }
  if (typeof Markdown !== 'undefined') {
    el.classList.add('md-content', 'chat-text');
    const normalized = typeof Markdown.normalizeMarkdownInput === 'function'
      ? Markdown.normalizeMarkdownInput(clean)
      : clean;
    el.innerHTML = Markdown.render(normalized);
  } else {
    el.textContent = clean;
  }
}

/** Remove function-call syntax some models leak into content (e.g. Kimi code). */
function stripLeakedToolCalls(text) {
  if (!text) return '';
  let s = String(text);
  let out = '';
  let i = 0;
  while (i < s.length) {
    const rest = s.slice(i);
    const m = rest.match(/(?:^|\s)(functions\.[a-zA-Z_][\w.]*)\s*:/);
    if (!m || m.index === undefined) {
      out += rest;
      break;
    }
    const lead = m[0].startsWith(' ') ? 1 : 0;
    const start = i + m.index + lead;
    out += s.slice(i, start);
    i = start + m[1].length + 1;
    while (i < s.length && /\s/.test(s[i])) i += 1;
    if (s[i] === '{') {
      let depth = 0;
      let inStr = false;
      let esc = false;
      while (i < s.length) {
        const ch = s[i];
        if (inStr) {
          if (esc) esc = false;
          else if (ch === '\\') esc = true;
          else if (ch === '"') inStr = false;
        } else if (ch === '"') inStr = true;
        else if (ch === '{') depth += 1;
        else if (ch === '}') {
          depth -= 1;
          if (depth === 0) { i += 1; break; }
        }
        i += 1;
      }
    } else if (s[i] === '"') {
      i += 1;
      while (i < s.length) {
        if (s[i] === '\\') { i += 2; continue; }
        if (s[i] === '"') { i += 1; break; }
        i += 1;
      }
    } else {
      while (i < s.length && !/\s/.test(s[i])) i += 1;
    }
    const badge = s.slice(i).match(/^\s*\[\d+\]/);
    if (badge) i += badge[0].length;
  }
  return out.replace(/[ \t]{2,}/g, ' ').replace(/\n{3,}/g, '\n\n').trim();
}

function createAgentCallsBlock() {
  const block = document.createElement('details');
  block.className = 'chat-activity-collapse hidden';
  block.innerHTML = `
    <summary>
      <span class="agent-icon">🧭</span>
      <span class="agent-calls-label">${t('agentCalls', '专员调用')}</span>
      <span class="agent-calls-count"></span>
      <span class="chat-activity-summary__names agent-calls-summary hidden"></span>
    </summary>
    <div class="chat-activity-list agent-calls-list"></div>
  `;
  return block;
}

function updateAgentCallsSummary(block) {
  if (!block) return;
  const count = block.querySelectorAll('.chat-activity-item, .agent-call').length;
  const countEl = block.querySelector('.agent-calls-count');
  if (countEl) countEl.textContent = count ? `(${count})` : '';
  const summaryEl = block.querySelector('.agent-calls-summary, .chat-activity-summary__names');
  if (summaryEl) {
    const titles = [...block.querySelectorAll('.agent-call-title, .chat-activity-item strong')].map((el) => el.textContent.trim()).filter(Boolean);
    if (!titles.length) {
      summaryEl.textContent = '';
      summaryEl.classList.add('hidden');
    } else if (titles.length <= 2) {
      summaryEl.textContent = titles.join(' · ');
      summaryEl.classList.remove('hidden');
    } else {
      summaryEl.textContent = `${titles.slice(0, 2).join(' · ')} +${titles.length - 2}`;
      summaryEl.classList.remove('hidden');
    }
  }
  if (count) block.classList.remove('hidden');
}

function renderAgentCallItem(list, event) {
  if (!list || !event) return;
  const id = event.id || `${event.type}:${event.agentId || event.agent_id || Date.now()}`;
  if (list.querySelector(`[data-agent-event-id="${CSS.escape(id)}"]`)) return;
  const aid = event.agentId || event.agent_id || 'op';
  const meta = typeof OfficePanel !== 'undefined' ? OfficePanel.agentMeta(aid) : { icon: '🤖', name: aid };
  const div = document.createElement('div');
  div.className = 'chat-activity-item';
  div.dataset.agentEventId = id;
  const title = event.title || meta.name || aid;
  const body = event.body ? `<div class="chat-activity-detail">${escapeHtml(event.body)}</div>` : '';
  div.innerHTML = `<span>${event.icon || meta.icon || '🤖'}</span> <strong class="agent-call-title">${escapeHtml(title)}</strong>${body}`;
  list.appendChild(div);
  scrollToBottom();
}

function hydrateAgentEvents(ui, events) {
  if (!ui?.agentCallsBlock || !events?.length) return;
  ui.agentCallsBlock.classList.remove('hidden');
  for (const ev of events) renderAgentCallItem(ui.agentCallsList, ev);
  updateAgentCallsSummary(ui.agentCallsBlock);
}

function agentEventFromStream(data) {
  const aid = data.agentId || data.agent_id || 'op';
  const meta = typeof OfficePanel !== 'undefined' ? OfficePanel.agentMeta(aid) : { icon: '🤖', name: aid };
  if (data.type === 'orchestration_start') {
    const plan = (data.plan || []).map((p) => {
      const id = p.agent_id || p.agentId;
      const m = typeof OfficePanel !== 'undefined' ? OfficePanel.agentMeta(id) : { icon: '🤖', name: id };
      return `${m.icon} ${m.name || id}`;
    }).join(' → ');
    return {
      id: `orch:${Date.now()}`,
      type: 'orchestration',
      icon: '🧭',
      title: '多专员编排',
      body: plan || '已启动',
    };
  }
  if (data.type === 'agent_handoff') {
    if (!aid || aid === 'op') return null;
    return {
      id: `handoff:${aid}:${Date.now()}`,
      type: 'handoff',
      agentId: aid,
      icon: meta.icon,
      title: `${meta.name} 已接手`,
      body: data.workflow_id ? `工作流：${data.workflow_id}` : (data.reason || ''),
    };
  }
  if (data.type === 'agent_summary') {
    return {
      id: `summary:${aid}:${Date.now()}`,
      type: 'summary',
      agentId: aid,
      icon: meta.icon,
      title: `${meta.name} 子任务完成`,
      body: (data.content || '').trim() || '（已通过工具完成子任务）',
    };
  }
  if (data.type === 'orchestration_synthesis') {
    return {
      id: `synth:${Date.now()}`,
      type: 'synthesis',
      icon: '🎯',
      title: 'OP 主调度',
      body: '正在汇总结论…',
    };
  }
  if (data.type === 'agent_status' && data.tool) {
    return {
      id: `status:${aid}:${data.tool}`,
      type: 'status',
      agentId: aid,
      icon: meta.icon,
      title: `${meta.name} · ${data.tool}`,
      body: data.status === 'working' ? '执行工具中…' : (data.status || ''),
    };
  }
  return null;
}

function recordAgentStreamEvent(ui, data, assistantMessage) {
  const event = agentEventFromStream(data);
  if (!event || !ui?.agentCallsBlock) return;
  if (assistantMessage) {
    if (!assistantMessage.agent_events) assistantMessage.agent_events = [];
    assistantMessage.agent_events.push(event);
  }
  renderAgentCallItem(ui.agentCallsList, event);
  updateAgentCallsSummary(ui.agentCallsBlock);
}

function renderMessageImages(container, images) {
  if (!images.length) return;
  const gallery = document.createElement('div');
  gallery.className = 'message-images';
  for (const url of images) {
    const img = document.createElement('img');
    img.src = url;
    img.className = 'message-image';
    img.loading = 'lazy';
    img.alt = '';
    gallery.appendChild(img);
  }
  container.appendChild(gallery);
}

// ---------------------------------------------------------------------------
// Message rendering
// ---------------------------------------------------------------------------

function createMessageElement(role) {
  const div = document.createElement('div');
  div.className = `message ${role}`;
  return div;
}

const MSG_ACTION_ICONS = {
  copy: '<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>',
  edit: '<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>',
  like: '<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z"/></svg>',
  dislike: '<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><path d="M17 14V2"/><path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z"/></svg>',
  speak: '<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><path d="M11 5 6 9H2v6h4l5 4V5Z"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/></svg>',
  regenerate: '<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg>',
};

let activeTtsBtn = null;

function createMessageActionBtn(action, label) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'msg-action-btn';
  btn.dataset.action = action;
  btn.title = label;
  btn.setAttribute('aria-label', label);
  btn.innerHTML = MSG_ACTION_ICONS[action] || '';
  return btn;
}

function createMessageActionsBar(role) {
  const bar = document.createElement('div');
  bar.className = 'message-actions-bar';
  bar.dataset.role = role;

  const left = document.createElement('div');
  left.className = 'message-actions-left';

  if (role === 'user') {
    left.appendChild(createMessageActionBtn('copy', t('copy', 'Copy')));
    left.appendChild(createMessageActionBtn('edit', t('editMessage', 'Edit')));
  } else {
    left.appendChild(createMessageActionBtn('copy', t('copy', 'Copy')));
    left.appendChild(createMessageActionBtn('like', t('feedbackUp', 'Good response')));
    left.appendChild(createMessageActionBtn('dislike', t('feedbackDown', 'Bad response')));
    left.appendChild(createMessageActionBtn('speak', t('speakMessage', 'Read aloud')));
    left.appendChild(createMessageActionBtn('regenerate', t('regenerate', 'Regenerate')));
    bar.appendChild(left);
    return bar;
  }

  bar.appendChild(left);
  return bar;
}

function getMessageTurnContentEl(turn) {
  if (!turn) return null;
  return turn.querySelector('.chat-bubble > .chat-text.message.assistant')
    || turn.querySelector('.chat-bubble > .chat-text.user-text')
    || turn.querySelector('.chat-bubble > .chat-text')
    || turn.querySelector('.message-text');
}

function getMessageTurnCopyText(turn) {
  const el = getMessageTurnContentEl(turn);
  const domText = el?.innerText?.trim() || el?.textContent?.trim() || '';
  if (domText) return domText;

  const msgIdx = parseInt(turn?.dataset?.msgIdx, 10);
  if (!Number.isFinite(msgIdx) || msgIdx < 0) return '';

  const msg = getCurrentMessages()[msgIdx];
  if (!msg) return '';
  if (typeof msg.content === 'string') return stripLeakedToolCalls(msg.content).trim();
  if (Array.isArray(msg.content)) {
    return msg.content
      .filter((p) => p?.type === 'text')
      .map((p) => String(p.text || '').trim())
      .filter(Boolean)
      .join('\n');
  }
  return '';
}

function stopMessageSpeech() {
  if (typeof window !== 'undefined' && window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }
  if (activeTtsBtn) {
    activeTtsBtn.classList.remove('is-speaking');
    activeTtsBtn = null;
  }
}

function pickSpeechVoice(langPrefix) {
  if (typeof window === 'undefined' || !window.speechSynthesis) return null;
  const voices = window.speechSynthesis.getVoices() || [];
  return voices.find((v) => v.lang?.toLowerCase().startsWith(langPrefix)) || voices[0] || null;
}

function speakMessageFromTurn(turn, btn) {
  if (typeof window === 'undefined' || !window.speechSynthesis) {
    showToast(t('ttsUnsupported', 'Speech not supported in this browser'), 'warning');
    return;
  }
  if (state.driving) {
    showToast(t('ttsWhileDriving', 'Avoid speech playback while driving'), 'warning');
    return;
  }
  const text = getMessageTurnCopyText(turn);
  if (!text) return;

  if (btn?.classList.contains('is-speaking')) {
    stopMessageSpeech();
    return;
  }
  stopMessageSpeech();

  const lang = (typeof i18n !== 'undefined' && i18n.getLang?.()?.startsWith('zh')) ? 'zh-CN' : 'en-US';
  const utter = new SpeechSynthesisUtterance(text.slice(0, 4000));
  utter.lang = lang;
  const voice = pickSpeechVoice(lang.split('-')[0]);
  if (voice) utter.voice = voice;
  utter.rate = 1.02;
  utter.onend = () => stopMessageSpeech();
  utter.onerror = () => stopMessageSpeech();
  if (btn) {
    btn.classList.add('is-speaking');
    activeTtsBtn = btn;
  }
  window.speechSynthesis.speak(utter);
}

async function regenerateAssistantMessage(assistantIdx) {
  if (isChatUiLocked()) {
    showToast(t('regenerateWhileStreaming', 'Wait for the reply to finish'), 'warning');
    return;
  }
  const history = getCurrentMessages();
  const msg = history[assistantIdx];
  if (!msg || msg.role !== 'assistant') return;
  const truncated = history.slice(0, assistantIdx);
  if (!truncated.length || truncated[truncated.length - 1]?.role !== 'user') {
    showToast(t('regenerateFailed', 'Cannot find the user message to retry'), 'warning');
    return;
  }
  stopMessageSpeech();
  saveCurrentMessages(truncated);
  renderStoredMessages();
  syncSessionsToDevice().catch(() => {});
  await streamAssistantResponse(truncated);
}

function finalizeAssistantTurn(ui, msgIdx) {
  if (!ui?.turn) return;
  if (msgIdx != null) ui.turn.dataset.msgIdx = String(msgIdx);
  ui.actionsBar?.classList.remove('is-pending');
}

function appendUserMessage(content, { scroll = true, msgIdx = null, fileRefs = [] } = {}) {
  const turn = document.createElement('div');
  turn.className = 'message-turn user-turn msg-in';
  if (msgIdx != null) turn.dataset.msgIdx = String(msgIdx);

  const chatGroup = document.createElement('div');
  chatGroup.className = 'chat-group user';

  const groupMessages = document.createElement('div');
  groupMessages.className = 'chat-group-messages';

  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble user-bubble message user';

  const text = messageText(content);
  const images = messageImages(content);
  renderMessageImages(bubble, images);
  const refs = fileRefs?.length ? fileRefs : [];
  if (refs.length) {
    const filesEl = document.createElement('div');
    filesEl.className = 'message-file-refs';
    for (const ref of refs) {
      const chip = document.createElement('span');
      chip.className = 'message-file-ref';
      chip.textContent = `@${ref.rel || ref.name}`;
      chip.title = ref.path || '';
      filesEl.appendChild(chip);
    }
    bubble.appendChild(filesEl);
  }
  if (text) {
    const textEl = document.createElement('div');
    textEl.className = 'message-text md-content user-text';
    if (typeof Markdown !== 'undefined' && typeof Markdown.renderToElement === 'function') {
      Markdown.renderToElement(textEl, text, { streaming: false, cursor: false });
    } else {
      textEl.textContent = text;
    }
    bubble.appendChild(textEl);
  }

  groupMessages.appendChild(bubble);
  groupMessages.appendChild(createMessageActionsBar('user'));
  chatGroup.appendChild(groupMessages);
  turn.appendChild(chatGroup);
  appendToMessages(turn);
  if (scroll) scrollToBottom({ force: true });
  return turn;
}

function dataUrlToPendingImage(url) {
  const mimeMatch = /^data:([^;]+);/.exec(url || '');
  return { dataUrl: url, mimeType: mimeMatch?.[1] || 'image/jpeg' };
}

function highlightEditingMessage(msgIdx) {
  els.messages?.querySelectorAll('.message.user.is-editing').forEach((el) => {
    el.classList.remove('is-editing');
  });
  if (msgIdx == null) return;
  const el = els.messages?.querySelector(`.message-turn.user-turn[data-msg-idx="${msgIdx}"] .message.user`);
  el?.classList.add('is-editing');
}

function updateComposerEditUi() {
  const banner = document.getElementById('composerEditBanner');
  const form = els.composer;
  banner?.classList.toggle('hidden', editingUserMsgIdx === null);
  form?.classList.toggle('is-editing', editingUserMsgIdx !== null);
  updateComposerSendBtn();
}

function cancelEditUserMessage({ clearComposer = true } = {}) {
  editingUserMsgIdx = null;
  highlightEditingMessage(null);
  if (clearComposer) {
    if (els.chatInput) els.chatInput.value = '';
    clearComposerAttachments();
    autoResize();
  }
  updateComposerEditUi();
}

function startEditUserMessage(msgIdx) {
  if (isChatUiLocked()) {
    showToast(t('editWhileStreaming', 'Wait for the reply to finish before editing'), 'warning');
    return;
  }
  const history = getCurrentMessages();
  const msg = history[msgIdx];
  if (!msg || msg.role !== 'user') return;

  if (editingUserMsgIdx !== null) cancelEditUserMessage({ clearComposer: true });
  editingUserMsgIdx = msgIdx;

  if (els.chatInput) {
    els.chatInput.value = messageText(msg.content);
    autoResize();
  }
  pendingImages = messageImages(msg.content).map(dataUrlToPendingImage);
  renderComposerAttachments();

  highlightEditingMessage(msgIdx);
  updateComposerEditUi();
  els.chatInput?.focus();
  scrollToMessageIndex(msgIdx);
}

function appendAssistantMessage({ withLoading = true } = {}) {
  const turn = document.createElement('div');
  turn.className = 'message-turn assistant-turn msg-in';

  const wrapper = document.createElement('div');
  wrapper.className = 'message assistant-wrapper';

  const chatGroup = document.createElement('div');
  chatGroup.className = 'chat-group assistant';

  const avatar = document.createElement('div');
  avatar.className = 'chat-avatar brand-mark sm';
  avatar.setAttribute('aria-hidden', 'true');
  avatar.innerHTML = OP_COMMA_LOGO_SVG;

  const groupMessages = document.createElement('div');
  groupMessages.className = 'chat-group-messages';

  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble assistant-bubble';

  const thinking = document.createElement('details');
  thinking.className = 'chat-thinking-collapse hidden';
  thinking.innerHTML = `<summary><span class="thinking-icon">🧠</span><span class="thinking-label">${t('thinking', 'Thinking')}</span><span class="thinking-waiting-dots typing-dots hidden" aria-hidden="true"><span></span><span></span><span></span></span></summary><div class="chat-thinking thinking-body"></div>`;

  const agentCallsBlock = createAgentCallsBlock();
  const agentCallsList = agentCallsBlock.querySelector('.agent-calls-list');

  const toolsBlock = document.createElement('details');
  toolsBlock.className = 'chat-tools-collapse hidden';
  toolsBlock.open = false;
  toolsBlock.innerHTML = `
    <summary class="chat-tools-summary">
      <span class="tool-icon">⚡</span>
      <span class="tool-calls-label">${t('toolCalls', 'Tool calls')}</span>
      <span class="tool-calls-count"></span>
      <span class="chat-tools-summary__names tool-calls-summary hidden"></span>
    </summary>
    <div class="chat-tools-list tool-calls-list"></div>
  `;

  const toolsList = toolsBlock.querySelector('.tool-calls-list');

  const traceBlock = document.createElement('details');
  traceBlock.className = 'chat-trace-collapse hidden';
  traceBlock.open = false;
  traceBlock.innerHTML = `
    <summary class="chat-trace-summary">
      <span class="trace-icon">📍</span>
      <span class="trace-label">${t('traceLog', 'Trace')}</span>
      <span class="trace-count"></span>
    </summary>
    <div class="chat-trace-list assistant-trace"></div>
  `;

  const content = document.createElement('div');
  content.className = 'chat-text md-content message assistant';

  const footer = document.createElement('div');
  footer.className = 'chat-group-footer hidden';
  footer.innerHTML = '<span class="msg-meta"></span>';

  bubble.appendChild(thinking);
  bubble.appendChild(agentCallsBlock);
  bubble.appendChild(toolsBlock);
  bubble.appendChild(traceBlock);
  bubble.appendChild(content);
  bubble.appendChild(footer);

  const actionsBar = createMessageActionsBar('assistant');
  actionsBar.classList.add('is-pending');

  groupMessages.appendChild(bubble);
  groupMessages.appendChild(actionsBar);
  chatGroup.appendChild(avatar);
  chatGroup.appendChild(groupMessages);
  wrapper.appendChild(chatGroup);

  turn.appendChild(wrapper);
  appendToMessages(turn);
  scrollToBottom();
  const ui = {
    turn,
    actionsBar,
    wrapper,
    bubble,
    loading: null,
    thinking,
    thinkingLabel: thinking.querySelector('.thinking-label'),
    thinkingBody: thinking.querySelector('.thinking-body'),
    thinkingWaitingDots: thinking.querySelector('.thinking-waiting-dots'),
    agentCallsBlock,
    agentCallsList,
    toolsBlock,
    toolsList,
    traceBlock,
    traceList: traceBlock.querySelector('.chat-trace-list'),
    content,
    footer,
  };
  if (withLoading) showAssistantLoading(ui);
  return ui;
}

function clearMessagesPreservingJump() {
  if (!els.messages) return;
  els.messages.innerHTML = '';
}

function appendToMessages(el) {
  if (!els.messages || !el) return;
  els.messages.appendChild(el);
}

let chatScrollPinned = true;
let _chatScrollPinRaf = null;
let _suppressScrollPinUpdate = 0;

function isChatNearBottom(el = els.messages) {
  if (!el) return true;
  const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
  return distance <= CHAT_SCROLL_PIN_THRESHOLD;
}

function updateJumpToBottomButton() {
  const btn = els.jumpToBottomBtn;
  if (!btn || !els.messages) return;
  const canScroll = els.messages.scrollHeight > els.messages.clientHeight + 8;
  const show = canScroll && !chatScrollPinned;
  btn.classList.toggle('visible', show);
  btn.classList.toggle('hidden', !show);
  btn.setAttribute('aria-hidden', show ? 'false' : 'true');
}

function onMessagesScroll() {
  if (_suppressScrollPinUpdate > 0) return;
  if (_chatScrollPinRaf) return;
  _chatScrollPinRaf = requestAnimationFrame(() => {
    _chatScrollPinRaf = null;
    chatScrollPinned = isChatNearBottom();
    updateJumpToBottomButton();
  });
}

function refreshContextMeter() {
  if (typeof ComposerContextMeter !== 'undefined') ComposerContextMeter.refresh();
}

function applyRagStatsFromApi(data) {
  if (!data?.ok) return;
  const docs = data.documents || [];
  ragStatsCache = {
    count: data.count ?? docs.length,
    vector_chunks: data.vector_chunks ?? 0,
    totalChars: docs.reduce((sum, d) => sum + (Number(d.chars) || 0), 0),
    embeddedDocs: docs.filter((d) => d.embedded).length,
    embedded_docs: data.embedded_docs ?? docs.filter((d) => d.embedded).length,
  };
  refreshContextMeter();
}

async function refreshRagStatsForMeter() {
  try {
    const { data } = await fetchRagApi({ compact: true, timeoutMs: 8000 });
    applyRagStatsFromApi(data);
  } catch {
    /* ignore */
  }
}

function scrollToBottom({ force = false } = {}) {
  const el = els.messages;
  if (!el) return;
  if (!force && !chatScrollPinned) {
    updateJumpToBottomButton();
    return;
  }
  _suppressScrollPinUpdate += 1;
  const prevBehavior = el.style.scrollBehavior;
  el.style.scrollBehavior = 'auto';
  el.scrollTop = el.scrollHeight;
  el.style.scrollBehavior = prevBehavior;
  requestAnimationFrame(() => {
    _suppressScrollPinUpdate = Math.max(0, _suppressScrollPinUpdate - 1);
    chatScrollPinned = force ? true : isChatNearBottom();
    updateJumpToBottomButton();
  });
}

function jumpToBottom() {
  scrollToBottom({ force: true });
}

// ---------------------------------------------------------------------------
// Composer slash commands (/status, /tsk, /can, …)
// ---------------------------------------------------------------------------

const SLASH_COMMAND_DEFS = [
  { id: 'tune_feel', icon: '🎛️', labelKey: 'slashCmdTuneFeel', descKey: 'slashCmdTuneFeelDesc', promptKey: 'slashCmdTuneFeelPrompt', workflow: 'tune_session', consumer: true, aliases: ['调手感', '手感'] },
  { id: 'adapt_new', icon: '🚗', labelKey: 'slashCmdAdaptNew', descKey: 'slashCmdAdaptNewDesc', promptKey: 'slashCmdAdaptNewPrompt', workflow: 'vehicle_adaptation', consumer: true, aliases: ['适配新车', '新车'] },
  { id: 'cant_engage', icon: '🚦', labelKey: 'slashCmdCantEngage', descKey: 'slashCmdCantEngageDesc', promptKey: 'slashCmdCantEngagePrompt', workflow: 'engage_triage', consumer: true, aliases: ['开不起来', '排查'] },
  { id: 'review_trip', icon: '📝', labelKey: 'slashCmdReviewTrip', descKey: 'slashCmdReviewTripDesc', promptKey: 'slashCmdReviewTripPrompt', workflow: 'post_drive_review', consumer: true, aliases: ['复盘', '上一趟'] },
  { id: 'status', icon: '🚗', labelKey: 'slashCmdStatus', descKey: 'slashCmdStatusDesc', promptKey: 'qaVehiclePrompt', enrich: 'status' },
  { id: 'compact', icon: '🗜️', labelKey: 'slashCmdCompact', descKey: 'slashCmdCompactDesc', action: 'compact' },
  { id: 'issue', icon: '📝', labelKey: 'slashCmdIssue', descKey: 'slashCmdIssueDesc', action: 'issue' },
  { id: 'new', icon: '✨', labelKey: 'slashCmdNew', descKey: 'slashCmdNewDesc', action: 'new_session' },
  { id: 'agent', icon: '🤖', labelKey: 'slashCmdAgent', descKey: 'slashCmdAgentDesc', action: 'agent' },
  { id: 'think', icon: '💭', labelKey: 'slashCmdThink', descKey: 'slashCmdThinkDesc', action: 'think' },
  { id: 'verbose', icon: '🔍', labelKey: 'slashCmdVerbose', descKey: 'slashCmdVerboseDesc', action: 'verbose' },
  { id: 'trace', icon: '📍', labelKey: 'slashCmdTrace', descKey: 'slashCmdTraceDesc', action: 'trace' },
  { id: 'usage', icon: '📊', labelKey: 'slashCmdUsage', descKey: 'slashCmdUsageDesc', enrich: 'usage' },
  { id: 'memory', icon: '🧠', labelKey: 'slashCmdMemory', descKey: 'slashCmdMemoryDesc', enrich: 'memory' },
  { id: 'workspace', icon: '📁', labelKey: 'slashCmdWorkspace', descKey: 'slashCmdWorkspaceDesc', action: 'workspace' },
  { id: 'office', icon: '🏢', labelKey: 'slashCmdOffice', descKey: 'slashCmdOfficeDesc', action: 'office' },
  { id: 'tsk', icon: '🔐', labelKey: 'slashCmdTsk', descKey: 'slashCmdTskDesc', submenu: 'tsk' },
  { id: 'can', icon: '📡', labelKey: 'slashCmdCan', descKey: 'slashCmdCanDesc', submenu: 'routes' },
  { id: 'logs', icon: '📋', labelKey: 'slashCmdLogs', descKey: 'slashCmdLogsDesc', promptKey: 'qaLogsPrompt' },
  { id: 'events', icon: '⚡', labelKey: 'slashCmdEvents', descKey: 'slashCmdEventsDesc', promptKey: 'qaEventsPrompt' },
  { id: 'engage', icon: '🚦', labelKey: 'slashCmdEngage', descKey: 'slashCmdEngageDesc', promptKey: 'qaEngagePrompt', workflow: 'engage_triage' },
  { id: 'trip', icon: '📝', labelKey: 'slashCmdTrip', descKey: 'slashCmdTripDesc', promptKey: 'qaTripReviewPrompt' },
  { id: 'system', icon: '📊', labelKey: 'slashCmdSystem', descKey: 'slashCmdSystemDesc', promptKey: 'qaSystemLoadPrompt' },
  { id: 'settings', icon: '⚙️', labelKey: 'slashCmdSettings', descKey: 'slashCmdSettingsDesc', promptKey: 'qaDpSettingsPrompt', aliases: ['dp', 'tune'] },
  { id: 'alka', icon: '🛣️', labelKey: 'slashCmdAlka', descKey: 'slashCmdAlkaDesc', promptKey: 'qaAlkaPrompt' },
  { id: 'lon', icon: '🎯', labelKey: 'slashCmdLon', descKey: 'slashCmdLonDesc', promptKey: 'qaLonPrompt' },
  { id: 'konik', icon: '☁️', labelKey: 'slashCmdKonik', descKey: 'slashCmdKonikDesc', promptKey: 'qaKonikPrompt', workflow: 'konik_connect' },
  { id: 'adapt', icon: '🔧', labelKey: 'slashCmdAdapt', descKey: 'slashCmdAdaptDesc', promptKey: 'qaAdaptPrompt', workflow: 'vehicle_adaptation' },
  { id: 'routes', icon: '📈', labelKey: 'slashCmdRoutes', descKey: 'slashCmdRoutesDesc', promptKey: 'qaCompareRoutesPrompt', workflow: 'compare_routes_tune', aliases: ['route', 'compare'] },
  { id: 'batch', icon: '📦', labelKey: 'slashCmdBatch', descKey: 'slashCmdBatchDesc', promptKey: 'qaBatchRoutesPrompt', workflow: 'batch_route_review' },
  { id: 'cabana', icon: '🔌', labelKey: 'slashCmdCabana', descKey: 'slashCmdCabanaDesc', action: 'cabana' },
  { id: 'secoc', icon: '🔑', labelKey: 'slashCmdSecoc', descKey: 'slashCmdSecocDesc', action: 'secoc' },
  { id: 'help', icon: '❓', labelKey: 'slashCmdHelp', descKey: 'slashCmdHelpDesc', enrich: 'help' },
];

const TSK_SLASH_ITEMS = [
  { id: 'status', labelKey: 'slashTskStatus', descKey: 'slashTskStatusDesc', enrich: 'tsk' },
  { id: 'extract', labelKey: 'slashTskExtract', descKey: 'slashTskExtractDesc', promptKey: 'slashTskExtractPrompt' },
  { id: 'match', labelKey: 'slashTskMatch', descKey: 'slashTskMatchDesc', promptKey: 'slashTskMatchPrompt' },
  { id: 'secoc', labelKey: 'slashTskSecoc', descKey: 'slashTskSecocDesc', action: 'secoc' },
];

const TSK_BY_ID = Object.fromEntries(TSK_SLASH_ITEMS.map((d) => [d.id, d]));

let composerSlashRoutes = null;
let composerSlashRoutesLoading = false;
let composerSlashHighlight = 0;
let composerSlashOpen = false;
let composerSlashMenuState = null;

function slashCommandTokens(def) {
  return [def.id, ...(def.aliases || [])];
}

function findSlashDef(cmd) {
  const c = (cmd || '').toLowerCase();
  return SLASH_COMMAND_DEFS.find((d) => slashCommandTokens(d).includes(c)) || null;
}

function getSlashMenuState(text) {
  const trimmed = (text || '').trimStart();
  if (!trimmed.startsWith('/')) return null;

  const body = trimmed.slice(1);
  const spaceIdx = body.indexOf(' ');
  const cmdPart = (spaceIdx === -1 ? body : body.slice(0, spaceIdx)).toLowerCase();
  const argPart = spaceIdx === -1 ? '' : body.slice(spaceIdx + 1);
  const argFilter = argPart.trim().toLowerCase();
  const argFirst = argPart.trim().split(/\s+/)[0]?.toLowerCase() || '';

  if (spaceIdx === -1) {
    if (cmdPart === 'can') return { mode: 'routes', filter: '' };
    if (cmdPart === 'tsk') return { mode: 'tsk', filter: '' };
    if (findSlashDef(cmdPart) && !['can', 'tsk'].includes(cmdPart)) return null;
    return { mode: 'commands', filter: cmdPart };
  }

  if (cmdPart === 'can') return { mode: 'routes', filter: argFilter };
  if (cmdPart === 'tsk') {
    if (argFirst && TSK_BY_ID[argFirst] && argPart.trim() === argFirst) return null;
    return { mode: 'tsk', filter: argFilter };
  }
  return null;
}

function hideComposerSlashMenu() {
  composerSlashOpen = false;
  composerSlashHighlight = 0;
  composerSlashMenuState = null;
  els.composerSlashMenu?.classList.add('hidden');
}

function showComposerSlashMenu(state) {
  if (typeof ComposerMention !== 'undefined') ComposerMention.hideMenu();
  composerSlashOpen = true;
  composerSlashMenuState = state;
  els.composerSlashMenu?.classList.remove('hidden');
}

function updateSlashMenuLabel(state) {
  if (!els.composerSlashLabel) return;
  let key = 'slashMenuPickCommand';
  if (state?.mode === 'routes') key = 'slashCanPickRoute';
  else if (state?.mode === 'tsk') key = 'slashTskPickAction';
  els.composerSlashLabel.textContent = t(key);
}

function getFilteredSlashCommands(filter) {
  const f = (filter || '').toLowerCase();
  return SLASH_COMMAND_DEFS.filter((def) => {
    if (!f) return true;
    if (slashCommandTokens(def).some((tok) => tok.startsWith(f) || f.startsWith(tok))) return true;
    const label = t(def.labelKey, def.id).toLowerCase();
    const desc = t(def.descKey, '').toLowerCase();
    return label.includes(f) || desc.includes(f);
  });
}

function getFilteredTskItems(filter) {
  const f = (filter || '').toLowerCase();
  return TSK_SLASH_ITEMS.filter((item) => {
    if (!f) return true;
    if (item.id.startsWith(f) || f.startsWith(item.id)) return true;
    const label = t(item.labelKey, item.id).toLowerCase();
    const desc = t(item.descKey, '').toLowerCase();
    return label.includes(f) || desc.includes(f);
  });
}

async function ensureComposerSlashRoutes() {
  if (composerSlashRoutes) return composerSlashRoutes;
  if (composerSlashRoutesLoading) return composerSlashRoutes || [];
  composerSlashRoutesLoading = true;
  try {
    const { data } = await api('GET', '/api/cabana/routes', null, { timeoutMs: 15000 });
    if (data?.ok && Array.isArray(data.routes)) {
      composerSlashRoutes = data.routes.filter((r) => r.has_qlog || r.has_rlog);
    } else {
      composerSlashRoutes = [];
    }
  } catch {
    composerSlashRoutes = [];
  } finally {
    composerSlashRoutesLoading = false;
  }
  return composerSlashRoutes;
}

function invalidateComposerSlashRoutes() {
  composerSlashRoutes = null;
}

function getFilteredSlashRoutes(filter) {
  const routes = composerSlashRoutes || [];
  if (!filter) return routes;
  return routes.filter((r) => {
    const hay = `${r.name} ${r.date || ''}`.toLowerCase();
    return hay.includes(filter);
  });
}

function getSlashMenuItems(state) {
  if (!state) return [];
  if (state.mode === 'commands') {
    return getFilteredSlashCommands(state.filter).map((def) => ({ type: 'command', def }));
  }
  if (state.mode === 'routes') {
    return getFilteredSlashRoutes(state.filter).map((route) => ({ type: 'route', route }));
  }
  if (state.mode === 'tsk') {
    return getFilteredTskItems(state.filter).map((item) => ({ type: 'tsk', item }));
  }
  return [];
}

function renderSlashEmpty(state, messageKey, fallback) {
  const empty = document.createElement('div');
  empty.className = 'composer-slash-empty';
  empty.textContent = t(messageKey, fallback);
  els.composerSlashList.appendChild(empty);
  composerSlashHighlight = 0;
}

function renderComposerSlashList(state) {
  if (!els.composerSlashList) return;
  updateSlashMenuLabel(state);
  els.composerSlashList.innerHTML = '';

  if (state.mode === 'routes' && composerSlashRoutesLoading && !composerSlashRoutes) {
    renderSlashEmpty(state, 'slashCanLoading', 'Loading routes…');
    return;
  }

  const items = getSlashMenuItems(state);
  if (!items.length) {
    const emptyKey = state.mode === 'routes'
      ? 'slashCanNoRoutes'
      : (state.mode === 'tsk' ? 'slashTskNoItems' : 'slashNoCommands');
    const emptyFallback = state.mode === 'routes' ? 'No routes' : (state.mode === 'tsk' ? 'No actions' : 'No commands');
    renderSlashEmpty(state, emptyKey, emptyFallback);
    return;
  }

  if (composerSlashHighlight >= items.length) composerSlashHighlight = 0;

  items.forEach((entry, idx) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `composer-slash-item${idx === composerSlashHighlight ? ' active' : ''}`;
    btn.setAttribute('role', 'option');

    if (entry.type === 'command') {
      const { def } = entry;
      const title = document.createElement('span');
      title.className = 'composer-slash-item-title';
      title.textContent = `${def.icon || ''} /${def.id}`.trim();
      const meta = document.createElement('span');
      meta.className = 'composer-slash-item-meta';
      meta.textContent = t(def.descKey, '');
      btn.appendChild(title);
      if (meta.textContent) btn.appendChild(meta);
      btn.addEventListener('mousedown', (ev) => {
        ev.preventDefault();
        selectSlashCommand(def);
      });
    } else if (entry.type === 'route') {
      const { route } = entry;
      const title = document.createElement('span');
      title.className = 'composer-slash-item-title';
      title.textContent = route.name;
      const meta = document.createElement('span');
      meta.className = 'composer-slash-item-meta';
      meta.textContent = [
        route.date,
        route.has_qlog ? 'qlog' : null,
        route.has_rlog ? 'rlog' : null,
      ].filter(Boolean).join(' · ');
      btn.appendChild(title);
      if (meta.textContent) btn.appendChild(meta);
      btn.addEventListener('mousedown', (ev) => {
        ev.preventDefault();
        selectComposerSlashRoute(route.name);
      });
    } else if (entry.type === 'tsk') {
      const { item } = entry;
      const title = document.createElement('span');
      title.className = 'composer-slash-item-title';
      title.textContent = `/tsk ${item.id}`;
      const meta = document.createElement('span');
      meta.className = 'composer-slash-item-meta';
      meta.textContent = t(item.descKey, '');
      btn.appendChild(title);
      if (meta.textContent) btn.appendChild(meta);
      btn.addEventListener('mousedown', (ev) => {
        ev.preventDefault();
        selectTskSlashItem(item);
      });
    }

    els.composerSlashList.appendChild(btn);
  });
}

async function refreshComposerSlashMenu() {
  if (typeof ComposerMention !== 'undefined' && ComposerMention.isOpen()) {
    hideComposerSlashMenu();
    return;
  }
  const state = getSlashMenuState(els.chatInput?.value || '');
  if (!state) {
    hideComposerSlashMenu();
    return;
  }
  showComposerSlashMenu(state);
  renderComposerSlashList(state);
  if (state.mode === 'routes') {
    await ensureComposerSlashRoutes();
    renderComposerSlashList(state);
  }
}

function selectSlashCommand(def) {
  if (!els.chatInput || !def) return;
  if (def.submenu === 'routes') {
    els.chatInput.value = '/can ';
  } else if (def.submenu === 'tsk') {
    els.chatInput.value = '/tsk ';
  } else if (def.action === 'cabana') {
    openCabanaModal();
    hideComposerSlashMenu();
    els.chatInput.value = '';
    autoResize();
    return;
  } else if (def.action === 'secoc') {
    openSecocModal();
    hideComposerSlashMenu();
    els.chatInput.value = '';
    autoResize();
    return;
  } else if (def.action === 'compact') {
    els.chatInput.value = '/compact ';
  } else if (def.action === 'issue') {
    openSettingsTab('dev');
    loadIssuePane().catch(() => {});
    hideComposerSlashMenu();
    els.chatInput.value = '';
    return;
  } else if (def.action === 'new_session') {
    createNewSession();
    hideComposerSlashMenu();
    els.chatInput.value = '';
    autoResize();
    return;
  } else if (def.action === 'workspace') {
    openSettingsTab('platform');
    hideComposerSlashMenu();
    els.chatInput.value = '';
    return;
  } else if (def.action === 'office') {
    if (typeof OfficePanel !== 'undefined') OfficePanel.open();
    hideComposerSlashMenu();
    els.chatInput.value = '';
    return;
  } else if (def.action === 'verbose' || def.action === 'trace') {
    if (typeof LocalPrefs !== 'undefined') {
      const prefs = LocalPrefs.getChatDebugPrefs();
      if (def.action === 'verbose') prefs.verbose = !prefs.verbose;
      else prefs.trace = !prefs.trace;
      LocalPrefs.setChatDebugPrefs(prefs);
      const on = prefs[def.action];
      showToast(def.action === 'trace'
        ? (on ? t('slashTraceOn', 'Trace 已开启（仅控制台，不在聊天区显示）') : t('slashTraceOff', 'Trace 已关闭'))
        : (on ? t('slashVerboseOn', 'Verbose 已开启') : t('slashVerboseOff', 'Verbose 已关闭')));
    }
    hideComposerSlashMenu();
    els.chatInput.value = '';
    return;
  } else if (def.action === 'think') {
    if (typeof LocalPrefs !== 'undefined') {
      const next = LocalPrefs.getModelProfile() === 'deep' ? 'auto' : 'deep';
      LocalPrefs.setModelProfile(next);
      showToast(next === 'deep' ? t('slashThinkOn', '深度思考：开') : t('slashThinkOff', '深度思考：关'));
    }
    hideComposerSlashMenu();
    els.chatInput.value = '';
    return;
  } else if (def.action === 'agent') {
    els.chatInput.value = '/agent ';
  } else {
    els.chatInput.value = `/${def.id} `;
    hideComposerSlashMenu();
    autoResize();
    els.chatInput.focus();
    return;
  }
  composerSlashHighlight = 0;
  refreshComposerSlashMenu().catch(() => {});
  autoResize();
  els.chatInput.focus();
}

function selectComposerSlashRoute(routeName) {
  if (!els.chatInput) return;
  els.chatInput.value = `/can ${routeName} `;
  hideComposerSlashMenu();
  autoResize();
  els.chatInput.focus();
}

function selectTskSlashItem(item) {
  if (!els.chatInput || !item) return;
  if (item.action === 'secoc') {
    openSecocModal();
    hideComposerSlashMenu();
    els.chatInput.value = '';
    autoResize();
    return;
  }
  els.chatInput.value = `/tsk ${item.id} `;
  hideComposerSlashMenu();
  autoResize();
  els.chatInput.focus();
}

function selectSlashMenuItem(entry) {
  if (!entry) return;
  if (entry.type === 'command') selectSlashCommand(entry.def);
  else if (entry.type === 'route') selectComposerSlashRoute(entry.route.name);
  else if (entry.type === 'tsk') selectTskSlashItem(entry.item);
}

function compactRouteSummaryJson(summary, routeName) {
  const s = summary.summary || summary;
  return JSON.stringify({
    route: s.route || routeName,
    duration: s.duration,
    can_frames: s.can_frames,
    dbc: s.dbc,
  });
}

function compactStatusSnapshot(data) {
  return {
    driving: data.driving,
    state: data.state,
    ai: data.ai,
  };
}

function compactTskSummary(data) {
  return {
    key_installed: data.key_installed,
    poll: data.poll,
    can: data.can,
    dataflash: data.dataflash,
    next_steps: data.next_steps,
    install_options: data.install_options,
  };
}

async function buildCanRouteChatMessage(routeName) {
  const parts = [t('cabanaRouteChatPrompt')];
  parts.push(`\n${t('cabanaRouteLabel', 'Route')}: ${routeName}`);
  parts.push(`\n${t('cabanaRouteLogsHint')}`);
  try {
    const { data } = await api(
      'GET',
      `/api/cabana/route/${encodeURIComponent(routeName)}/summary`,
      null,
      { timeoutMs: 15000 },
    );
    if (data?.ok) {
      parts.push(`\n${t('cabanaRouteSummaryLabel', 'Route summary')}:\n${compactRouteSummaryJson(data, routeName)}`);
    }
  } catch { /* optional */ }
  return parts.join('\n');
}

async function buildStatusSlashMessage() {
  const parts = [t('qaVehiclePrompt')];
  try {
    const { data } = await api('GET', '/api/ai/status', null, { timeoutMs: 10000 });
    if (data?.ok) {
      parts.push(`\n${t('slashStatusSnapshotLabel', 'Status snapshot')}:\n${JSON.stringify(compactStatusSnapshot(data), null, 2)}`);
    }
  } catch { /* optional */ }
  return parts.join('\n');
}

async function buildTskSlashMessage(subId) {
  const item = TSK_BY_ID[subId];
  const parts = [];
  if (item?.promptKey) parts.push(t(item.promptKey));
  else parts.push(t('slashTskStatusPrompt', 'Check Toyota SecOC / TSK status and recommend next steps.'));
  if (subId === 'status' || item?.enrich === 'tsk') {
    try {
      const { data } = await api('GET', '/api/tsk/summary', null, { timeoutMs: 15000 });
      if (data) {
        parts.push(`\n${t('slashTskSnapshotLabel', 'TSK snapshot')}:\n${JSON.stringify(compactTskSummary(data), null, 2)}`);
      }
    } catch { /* optional */ }
  }
  return parts.join('\n');
}

async function buildUsageSlashMessage() {
  const parts = [t('slashUsageIntro', 'Current AI usage on this device:')];
  try {
    const { data } = await api('GET', '/api/ai/usage/detail', null, { timeoutMs: 10000 });
    if (data?.ok) {
      parts.push(`\n${JSON.stringify({
        calls: data.usage?.calls,
        total_tokens: data.usage?.total_tokens,
        by_provider: data.byProvider,
      }, null, 2)}`);
    }
  } catch { /* optional */ }
  return parts.join('\n');
}

async function buildMemorySlashMessage() {
  const parts = [t('slashMemoryIntro', 'Device memory summary:')];
  try {
    const { data } = await api('GET', '/api/ai/memory', null, { timeoutMs: 10000 });
    if (data?.ok) {
      parts.push(`\nnotes=${(data.notes || []).length}`);
      parts.push(`vehicle_profile=${JSON.stringify(data.vehicle_profile || {}, null, 2)}`);
    }
    const ws = await api('GET', '/api/ai/workspace?key=user');
    if (ws.data?.content) {
      parts.push(`\nUSER.md:\n${ws.data.content.slice(0, 1200)}`);
    }
  } catch { /* optional */ }
  return parts.join('\n');
}

function buildHelpSlashMessage() {
  const lines = [t('slashHelpIntro', 'Available slash commands:')];
  for (const def of SLASH_COMMAND_DEFS) {
    if (def.action === 'cabana' || def.action === 'secoc') {
      lines.push(`• /${def.id} — ${t(def.descKey, '')}`);
      continue;
    }
    if (def.submenu === 'routes') {
      lines.push(`• /can <route> — ${t(def.descKey, '')}`);
      continue;
    }
    if (def.submenu === 'tsk') {
      lines.push(`• /tsk <status|extract|match|secoc> — ${t(def.descKey, '')}`);
      continue;
    }
    const aliases = (def.aliases || []).map((a) => `/${a}`).join(', ');
    const aliasSuffix = aliases ? ` (${aliases})` : '';
    lines.push(`• /${def.id}${aliasSuffix} — ${t(def.descKey, '')}`);
  }
  return lines.join('\n');
}

async function resolveSlashSend(text) {
  const trimmed = (text || '').trim();
  if (!trimmed.startsWith('/')) return null;

  for (const w of (window.__consumerWizards || [])) {
    for (const alias of (w.slash || [])) {
      const a = String(alias).toLowerCase();
      const tl = trimmed.toLowerCase();
      if (tl === a || tl.startsWith(`${a} `)) {
        return {
          displayText: trimmed,
          preview: w.name || alias,
          historyContent: buildUserContent(w.starter_prompt || trimmed, []),
          workflow: w.workflow_id || '',
          consumer: true,
        };
      }
    }
  }

  if (/^\/can\s*$/i.test(trimmed)) return { blockSend: true };
  if (/^\/tsk\s*$/i.test(trimmed)) return { blockSend: true };

  const canMatch = trimmed.match(/^\/can\s+(\S+)/i);
  if (canMatch) {
    const routeName = canMatch[1];
    return {
      displayText: trimmed,
      preview: `${t('cabanaRouteLabel', 'Route')}: ${routeName}`,
      historyContent: buildUserContent(await buildCanRouteChatMessage(routeName), []),
    };
  }

  const tskMatch = trimmed.match(/^\/tsk\s+(\w+)/i);
  if (tskMatch) {
    const sub = tskMatch[1].toLowerCase();
    const tskItem = TSK_BY_ID[sub];
    if (!tskItem) {
      return { displayText: trimmed, preview: trimmed, historyContent: buildUserContent(trimmed, []) };
    }
    if (tskItem.action === 'secoc') {
      openSecocModal();
      return { blockSend: true, handled: true };
    }
    const msg = await buildTskSlashMessage(sub);
    return {
      displayText: trimmed,
      preview: t(tskItem.labelKey, `/tsk ${sub}`),
      historyContent: buildUserContent(msg, []),
    };
  }

  const cmdMatch = trimmed.match(/^\/([a-z]+)(?:\s+(.+))?$/i);
  if (!cmdMatch) return null;

  const cmd = cmdMatch[1].toLowerCase();
  const arg = (cmdMatch[2] || '').trim();

  if (cmd === 'agent' && arg) {
    pendingAgentId = arg;
    return {
      displayText: trimmed,
      preview: `agent: ${arg}`,
      historyContent: buildUserContent(t('slashAgentPrompt', `请作为专员 ${arg} 处理后续问题。`), []),
      agentId: arg,
    };
  }

  if (cmd === 'compact') {
    return {
      displayText: trimmed,
      preview: t('slashCmdCompact', '/compact'),
      historyContent: buildUserContent(t('slashCompactPrompt', '请压缩本会话历史并写入记忆。'), []),
      compact: true,
    };
  }

  if (cmd === 'issue') {
    const rest = arg || t('slashIssueDefaultText', '请根据上文帮我整理并提交 GitHub Issue 草稿');
    return {
      displayText: trimmed,
      preview: t('slashCmdIssue', '/issue'),
      historyContent: buildUserContent(rest, []),
      issueDraft: true,
    };
  }

  if (!arg && trimmed.match(/^\/[a-z]+\s*$/i)) {
    const def = findSlashDef(cmd);
    if (!def) return null;

    if (def.action === 'cabana') {
      openCabanaModal();
      return { blockSend: true, handled: true };
    }
    if (def.action === 'secoc') {
      openSecocModal();
      return { blockSend: true, handled: true };
    }
    if (def.submenu) return { blockSend: true };

    let msg = def.promptKey ? t(def.promptKey) : trimmed;
    if (def.enrich === 'status') msg = await buildStatusSlashMessage();
    else if (def.enrich === 'help') msg = buildHelpSlashMessage();
    else if (def.enrich === 'usage') msg = await buildUsageSlashMessage();
    else if (def.enrich === 'memory') msg = await buildMemorySlashMessage();

    return {
      displayText: trimmed,
      preview: t(def.labelKey, `/${def.id}`),
      historyContent: buildUserContent(msg, []),
      workflow: def.workflow || '',
      consumer: !!def.consumer,
    };
  }

  return null;
}

function onComposerSlashKeydown(e) {
  if (!composerSlashOpen || !composerSlashMenuState) return false;
  const state = getSlashMenuState(els.chatInput?.value || '') || composerSlashMenuState;
  const items = getSlashMenuItems(state);
  const allowNav = items.length > 0 || e.key === 'Escape';

  if (!allowNav) return false;

  if (e.key === 'ArrowDown' && items.length) {
    e.preventDefault();
    composerSlashHighlight = (composerSlashHighlight + 1) % items.length;
    renderComposerSlashList(state);
    return true;
  }
  if (e.key === 'ArrowUp' && items.length) {
    e.preventDefault();
    composerSlashHighlight = (composerSlashHighlight - 1 + items.length) % items.length;
    renderComposerSlashList(state);
    return true;
  }
  if (e.key === 'Escape') {
    e.preventDefault();
    hideComposerSlashMenu();
    return true;
  }
  if (e.key === 'Enter' && !e.shiftKey && items.length) {
    e.preventDefault();
    selectSlashMenuItem(items[composerSlashHighlight]);
    return true;
  }
  if (e.key === 'Tab' && items.length) {
    e.preventDefault();
    selectSlashMenuItem(items[composerSlashHighlight]);
    return true;
  }
  return false;
}

function onComposerInput() {
  autoResize();
  refreshComposerSlashMenu().catch(() => {});
  if (typeof ComposerMention !== 'undefined') ComposerMention.refresh().catch(() => {});
}

// ---------------------------------------------------------------------------
// Streaming chat
// ---------------------------------------------------------------------------

async function runManualCompact() {
  const sessionId = SessionStore.activeId;
  if (isSessionJobRunning(sessionId)) {
    showToast(t('contextCompactBusy', '请等待当前回复完成后再压缩'), 'warning');
    return;
  }
  if (!getCurrentMessages().length) {
    showToast(t('contextCompactEmpty', '当前会话为空，无需压缩'), 'info');
    return;
  }

  SessionStore.ensureSessionOnSend(t('slashCmdCompact', '/compact'));
  renderSessionList();
  clearWelcomePanel();
  syncMessagesLayoutMode();
  chatScrollPinned = true;

  const historyContent = buildUserContent(t('slashCompactPrompt', '请压缩本会话历史并写入记忆。'), []);
  const displayContent = buildUserContent(t('slashCmdCompact', '/compact'), []);
  appendUserMessage(displayContent);

  const history = getCurrentMessages();
  history.push({ role: 'user', content: historyContent });
  saveCurrentMessages(history);
  syncSessionsToDevice().catch(() => {});

  pendingCompact = true;
  try {
    await streamAssistantResponse(history);
    showToast(t('contextCompactDone', '已触发会话压缩'), 'success');
  } catch {
    showToast(t('contextCompactFailed', '压缩失败，请稍后重试'), 'error');
  } finally {
    pendingCompact = false;
    refreshContextMeter();
  }
}

async function sendChat(e) {
  e.preventDefault();
  const sessionId = SessionStore.activeId;
  if (isSessionJobRunning(sessionId)) {
    abortSessionChat(sessionId);
    return;
  }

  let text = els.chatInput.value.trim();
  const images = pendingImages.slice();
  const fileRefs = pendingFileRefs.slice();
  if (!text && images.length === 0 && fileRefs.length === 0) return;

  const isResendEdit = editingUserMsgIdx !== null;
  const editMsgIdx = editingUserMsgIdx;

  const slashResolved = await resolveSlashSend(text);
  if (slashResolved?.blockSend) {
    if (!slashResolved.handled) refreshComposerSlashMenu().catch(() => {});
    return;
  }

  let displayText = text;
  let historyContent = null;
  let sessionPreview = text || (fileRefs.length ? t('mentionSessionPreview', 'Attached files') : t('imageMessage', '图片消息'));
  let slashWorkflow = '';
  let slashAgentId = '';
  let slashCompact = false;

  if (slashResolved) {
    hideComposerSlashMenu();
    displayText = slashResolved.displayText || text;
    sessionPreview = slashResolved.preview || displayText;
    if (slashResolved.historyContent !== undefined) historyContent = slashResolved.historyContent;
    slashWorkflow = slashResolved.workflow || '';
    slashAgentId = slashResolved.agentId || '';
    slashCompact = !!slashResolved.compact;
  }

  const workflowForSend = slashWorkflow || pendingWorkflow;
  pendingWorkflow = '';

  const content = await buildUserMessageContent(displayText, images, fileRefs);
  let finalHistoryContent = historyContent || content;
  if (historyContent && (images.length || fileRefs.length)) {
    const msgText = typeof historyContent === 'string'
      ? historyContent
      : (Array.isArray(historyContent)
        ? (historyContent.find((p) => p?.type === 'text')?.text || '')
        : '');
    finalHistoryContent = await buildUserMessageContent(msgText, images, fileRefs);
  }
  const storedFileRefs = fileRefs.map((ref) => ({ ...ref }));

  if (isResendEdit) {
    cancelEditUserMessage({ clearComposer: false });
    clearWelcomePanel();
    syncMessagesLayoutMode();
    chatScrollPinned = true;

    const history = getCurrentMessages().slice(0, editMsgIdx);
    history.push({ role: 'user', content: finalHistoryContent, file_refs: storedFileRefs });
    saveCurrentMessages(history);

    els.chatInput.value = '';
    clearComposerAttachments();
    autoResize();
    renderStoredMessages();
    syncSessionsToDevice().catch(() => {});

    pendingWorkflow = workflowForSend;
    pendingAgentId = slashAgentId || pendingAgentId;
    pendingCompact = !!slashCompact;
    if (slashResolved?.consumer) pendingConsumerMode = true;
    await streamAssistantResponse(history);
    pendingWorkflow = '';
    pendingAgentId = '';
    pendingCompact = false;
    pendingConsumerMode = false;
    return;
  }

  SessionStore.ensureSessionOnSend(sessionPreview);
  renderSessionList();

  clearWelcomePanel();
  syncMessagesLayoutMode();
  chatScrollPinned = true;
  appendUserMessage(content, { fileRefs: storedFileRefs, msgIdx: getCurrentMessages().length });
  els.chatInput.value = '';
  clearComposerAttachments();
  autoResize();

  const history = getCurrentMessages();
  history.push({ role: 'user', content: finalHistoryContent, file_refs: storedFileRefs });
  saveCurrentMessages(history);
  syncSessionsToDevice().catch(() => {});

  pendingWorkflow = workflowForSend;
  pendingAgentId = slashAgentId || pendingAgentId;
  pendingCompact = slashCompact;
  if (slashResolved?.consumer) pendingConsumerMode = true;
  await streamAssistantResponse(history);
  pendingWorkflow = '';
  pendingAgentId = '';
  pendingCompact = false;
  pendingConsumerMode = false;
}

function savePartialAssistant(sessionId, assistantMessage) {
  if (!sessionId || !assistantMessageHasContent(assistantMessage)) return;
  const session = SessionStore.getById(sessionId);
  if (!session) return;
  const msgs = (session.messages || []).map(normalizeStoredMessage);
  const partial = {
    role: 'assistant',
    content: stripLeakedToolCalls(assistantMessage.content || ''),
    reasoning_content: assistantMessage.reasoning_content || '',
    tool_calls: assistantMessage.tool_calls || [],
    tool_results: assistantMessage.tool_results || {},
    agent_events: assistantMessage.agent_events || [],
  };
  if (assistantMessage.resolvedModel) partial.resolvedModel = assistantMessage.resolvedModel;
  if (msgs[msgs.length - 1]?.role === 'assistant') {
    msgs[msgs.length - 1] = partial;
  } else {
    msgs.push(partial);
  }
  const maxMsgs = SessionStore.MAX_MESSAGES_PER_SESSION || 200;
  SessionStore.updateMessages(sessionId, msgs.slice(-maxMsgs));
  if (typeof SessionSync !== 'undefined') SessionSync.markLocalDirty();
  scheduleSessionSync();
}

function hydrateAssistantUi(ui, assistantMessage) {
  const text = stripLeakedToolCalls(messageText(assistantMessage.content) || assistantMessage.content || '');
  syncThinkingBlock(ui, assistantMessage);
  hydrateAgentEvents(ui, assistantMessage.agent_events);
  if (ui.agentCallsBlock && !ui.agentCallsBlock.classList.contains('hidden')) {
    setDetailsCollapsed(ui.agentCallsBlock, true);
  }
  if (assistantMessage.tool_calls?.length) {
    hideAssistantLoading(ui);
    ui.toolsBlock.classList.remove('hidden');
    setDetailsCollapsed(ui.toolsBlock, true);
    for (const tc of assistantMessage.tool_calls) {
      const fn = tc.function || {};
      renderToolCall(
        ui.toolsList,
        tc.id,
        fn.name || '',
        fn.arguments || '',
        assistantMessage.tool_results?.[tc.id] ?? null,
      );
    }
    updateToolCallsSummary(ui.toolsBlock);
  }
  if (text) {
    renderMarkdownContent(ui.content, text);
    hideAssistantLoading(ui);
  } else if (assistantMessage.content) {
    ui.content.textContent = assistantMessage.content;
    hideAssistantLoading(ui);
  } else if (assistantMessageHasContent(assistantMessage)) {
    hideAssistantLoading(ui);
  }
  renderMessageFooter(ui, { usage: assistantMessage.usage, resolvedModel: assistantMessage.resolvedModel });
}

function commitAssistantMessage(sessionId, assistantMessage) {
  if (!sessionId) return;
  const session = SessionStore.getById(sessionId);
  if (!session) return;
  const msgs = (session.messages || []).map(normalizeStoredMessage);
  const normalized = normalizeStoredMessage({ ...assistantMessage });
  if (msgs[msgs.length - 1]?.role === 'assistant') {
    msgs[msgs.length - 1] = normalized;
  } else {
    msgs.push(normalized);
  }
  const maxMsgs = SessionStore.MAX_MESSAGES_PER_SESSION || 200;
  SessionStore.updateMessages(sessionId, msgs.slice(-maxMsgs));
  if (typeof SessionSync !== 'undefined') SessionSync.markLocalDirty();
  scheduleSessionSync();
  if (SessionStore.activeId === sessionId) {
    const history = getCurrentMessages();
    if (history[history.length - 1]?.role === 'assistant') {
      history[history.length - 1] = normalized;
    } else {
      history.push(normalized);
    }
  }
}

function finishAssistant(ui, assistantMessage, sessionId) {
  if (!sessionId) return;
  commitAssistantMessage(sessionId, assistantMessage);
  if (SessionStore.activeId !== sessionId) return;
  clearLiveStreamChrome(ui);
  hideAssistantLoading(ui);
  syncThinkingBlock(ui, assistantMessage);
  assistantMessage.content = stripLeakedToolCalls(assistantMessage.content || '');
  if (!assistantMessage.content && !assistantMessage.reasoning_content && assistantMessage.tool_calls.length === 0) {
    assistantMessage.content = t('noResponse', 'No response');
  }
  const text = stripLeakedToolCalls(messageText(assistantMessage.content) || assistantMessage.content || '');
  if (text) {
    renderMarkdownContent(ui.content, text);
  } else {
    ui.content.textContent = '';
  }
  if (ui?.wrapper) delete ui.wrapper.dataset.liveStream;
  setMessageModelTag(ui, assistantMessage.resolvedModel);
  renderMessageFooter(ui, { usage: assistantMessage.usage, resolvedModel: assistantMessage.resolvedModel });
  setDetailsCollapsed(ui.toolsBlock, true);
  const history = getCurrentMessages();
  const assistantIdx = history.length - 1;
  if (history[assistantIdx]?.role === 'assistant') {
    finalizeAssistantTurn(ui, assistantIdx);
    MessageFeedback.updateButtons(ui.turn, history[assistantIdx]);
  } else {
    ui.actionsBar?.classList.remove('is-pending');
  }
  syncSessionsToDevice().catch(() => {});
  updateComposerSendBtn();
  renderSessionList();
}

function updateToolCallsSummary(toolsBlock) {
  const list = toolsBlock?.querySelector('.chat-tools-list, .tool-calls-list');
  if (!list || !toolsBlock) return;
  const count = list.querySelectorAll('.chat-tool-msg-collapse, .tool-call').length;
  const countEl = toolsBlock.querySelector('.tool-calls-count');
  if (countEl) {
    countEl.textContent = count ? `(${count})` : '';
  }
  const summaryEl = toolsBlock.querySelector('.tool-calls-summary, .chat-tools-summary__names');
  if (summaryEl) {
    const names = [...list.querySelectorAll('.chat-tool-row__name, .tool-name')].map((el) => el.textContent.trim()).filter(Boolean);
    if (!names.length) {
      summaryEl.textContent = '';
      summaryEl.classList.add('hidden');
    } else if (names.length <= 2) {
      summaryEl.textContent = names.join(', ');
      summaryEl.classList.remove('hidden');
    } else {
      summaryEl.textContent = `${names.slice(0, 2).join(', ')} +${names.length - 2}`;
      summaryEl.classList.remove('hidden');
    }
  }
  if (count) toolsBlock.classList.remove('hidden');
}

function renderToolCall(container, id, name, args, result, agentId, opts = {}) {
  const existing = container.querySelector(`[data-tool-id="${id}"]`);
  if (existing) {
    if (result !== undefined && result !== null) {
      updateToolCallResult(container, id, result);
    }
    return;
  }
  const aid = agentId || currentActiveAgentId() || 'op';
  const meta = typeof OfficePanel !== 'undefined' ? OfficePanel.agentMeta(aid) : null;
  const agentTag = meta && aid !== 'op'
    ? `<span class="tool-agent-tag">${meta.icon} ${escapeHtml(meta.name)}</span>`
    : '';
  const subTag = opts.subagent ? '<span class="tool-subagent-tag">子专员</span>' : '';
  const hasResult = result !== undefined && result !== null;
  const statusCls = hasResult ? (result?.ok === false ? 'err' : 'ok') : 'run';
  const statusText = hasResult ? (result?.ok === false ? '✗' : '✓') : '…';

  const div = document.createElement('details');
  div.className = 'chat-tool-msg-collapse';
  div.dataset.toolId = id;
  div.open = opts.expanded === true;
  div.innerHTML = `
    <summary>
      ${agentTag}${subTag}
      <code class="chat-tool-row__name tool-name">${escapeHtml(name)}</code>
      <span class="chat-tool-row__status tool-status ${statusCls}">${statusText}</span>
    </summary>
    <div class="chat-tool-msg-body">
      <div class="tool-section"><label>${t('toolArgs', 'Arguments')}</label><pre class="tool-args"></pre></div>
      <div class="tool-section tool-result-section${hasResult ? '' : ' hidden'}"><label>${t('toolResult', 'Result')}</label><pre class="tool-result"></pre></div>
    </div>
  `;
  div.querySelector('.tool-args').textContent = formatJson(args);
  if (hasResult) {
    if (result.ui_card?.type === 'tsk') {
      container.appendChild(div);
      updateToolCallResult(container, id, result);
      return;
    }
    div.querySelector('.tool-result').textContent = formatJson(result);
  }
  container.appendChild(div);
  scrollToBottom();
}

function updateToolCallResult(container, id, result) {
  const div = container.querySelector(`[data-tool-id="${id}"]`);
  if (!div) return;
  if (result?.ui_card?.type === 'tsk') {
    renderTskUiCard(div, result.ui_card);
    if (result.ui_card.poll) startTskPoll(div, id);
    else stopTskPoll(id);
    scrollToBottom();
    return;
  }
  stopTskPoll(id);
  const section = div.querySelector('.tool-result-section');
  const pre = div.querySelector('.tool-result');
  const status = div.querySelector('.chat-tool-row__status, .tool-status');
  section?.classList.remove('hidden');
  pre?.classList.remove('hidden');
  div.querySelector('.tsk-progress-card')?.remove();
  if (pre) pre.textContent = formatJson(result);
  if (status) {
    status.textContent = result?.ok === false ? '✗' : '✓';
    status.classList.remove('run', 'ok', 'err');
    status.classList.add(result?.ok === false ? 'err' : 'ok');
  }
  scrollToBottom();
}

const tskPollers = new Map();

function renderTskUiCard(div, card) {
  const section = div.querySelector('.tool-result-section');
  if (!section) return;
  section.classList.remove('hidden');
  const pre = section.querySelector('.tool-result');
  if (pre) pre.classList.add('hidden');
  let el = section.querySelector('.tsk-progress-card');
  if (!el) {
    el = document.createElement('div');
    el.className = 'tsk-progress-card';
    section.appendChild(el);
  }
  const s = card.summary || {};
  const can = s.can || {};
  const df = s.dataflash || {};
  const keyLabel = s.secoc_key_installed ? '已安装' : '未安装';
  const steps = (s.next_steps || []).map((x) => `<li>${escapeHtml(x)}</li>`).join('');
  el.innerHTML = `
    <div class="tsk-card-head">丰田 SecOC · TSK</div>
    <div class="tsk-card-row"><span>密钥</span><strong>${keyLabel}</strong></div>
    <div class="tsk-card-row"><span>CAN</span><span>sync ${can.sync_count || 0}/50 · protected ${can.protected_count || 0}/30 · ${escapeHtml(can.status || 'idle')}</span></div>
    <div class="tsk-card-row"><span>DataFlash</span><span>${df.bytes || 0}/${df.total || 32768} · ${escapeHtml(df.status || 'idle')}</span></div>
    ${steps ? `<ul class="tsk-card-steps">${steps}</ul>` : ''}
    ${card.url ? `<button type="button" class="tsk-card-link btn link" data-open-secoc="1">打开 SecOC 设置</button>` : ''}
  `;
  el.querySelector('[data-open-secoc]')?.addEventListener('click', () => openSecocModal());
}

function startTskPoll(div, id) {
  stopTskPoll(id);
  const timer = setInterval(async () => {
    try {
      const res = await fetch('/api/tsk/summary', { cache: 'no-store' });
      const summary = await res.json();
      renderTskUiCard(div, { type: 'tsk', summary, poll: summary.poll, url: summary.url });
      if (!summary.poll) stopTskPoll(id);
    } catch (_) { /* ignore */ }
  }, 2000);
  tskPollers.set(id, timer);
}

function stopTskPoll(id) {
  const t = tskPollers.get(id);
  if (t) clearInterval(t);
  tskPollers.delete(id);
}

function renderMessageFooter(ui, { usage, resolvedModel } = {}) {
  const footer = ui?.footer || ui?.bubble?.querySelector('.chat-group-footer');
  const meta = footer?.querySelector('.msg-meta');
  if (!footer || !meta) return;
  if (usage) ui._usage = usage;
  if (resolvedModel) ui._resolvedModel = resolvedModel;
  const parts = [];
  const modelLabel = formatResolvedModelLabel(resolvedModel ?? ui._resolvedModel);
  if (modelLabel) {
    const rawModel = String(resolvedModel ?? ui._resolvedModel ?? '');
    parts.push(`<span class="msg-meta__model" title="${escapeHtml(rawModel)}">${escapeHtml(modelLabel)}</span>`);
  }
  const u = usage || ui._usage;
  if (u) {
    const pt = u.prompt_tokens || 0;
    const ct = u.completion_tokens || 0;
    const total = u.total_tokens || (pt + ct);
    if (total) parts.push(`<span class="msg-meta__tokens">${pt} ↑ ${ct} ↓</span>`);
  }
  if (!parts.length) {
    footer.classList.add('hidden');
    meta.innerHTML = '';
    return;
  }
  footer.classList.remove('hidden');
  meta.innerHTML = parts.join('');
}

function renderUsage(target, usage) {
  if (target?.footer || target?.bubble || target?.content) {
    renderMessageFooter(target, { usage });
    return;
  }
  const root = target?.closest?.('.assistant-wrapper') || target;
  if (root?.classList?.contains('assistant-wrapper') || root?.querySelector?.('.chat-bubble')) {
    renderMessageFooter(wrapperToAssistantUi(root), { usage });
    return;
  }
  let el = target?.querySelector?.('.usage-badge');
  if (!el && target?.appendChild) {
    el = document.createElement('div');
    el.className = 'usage-badge';
    target.appendChild(el);
  }
  if (!el) return;
  const pt = usage.prompt_tokens || 0;
  const ct = usage.completion_tokens || 0;
  el.textContent = `${pt} ↑ / ${ct} ↓`;
}

function formatJson(value) {
  try {
    const obj = typeof value === 'string' ? JSON.parse(value) : value;
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(value);
  }
}

// ---------------------------------------------------------------------------
// Settings / config
// ---------------------------------------------------------------------------

function getMainModelValue() {
  return mainModelCombo?.getValue()?.trim() || '';
}

function getEmbeddingModelValue() {
  return embeddingModelCombo?.getValue()?.trim() || '';
}

function syncLegacyFromModelHub(hubData) {
  if (!hubData) return;
  const primary = hubData.primary;
  const acc = (hubData.accounts || []).find((a) => a.id === primary?.accountId)
    || (hubData.accounts || [])[0];
  if (!acc) return;
  if (providers.includes(acc.provider)) els.providerSelect.value = acc.provider;
  else if (acc.provider === 'zhipu' && providers.includes('bigmodel')) els.providerSelect.value = 'bigmodel';
  els.apiKeyInput.value = acc.apiKey || '';
  els.baseUrlInput.value = acc.baseUrl || '';
  const model = primary?.model || acc.models?.[0] || '';
  if (model) mainModelCombo?.setValue(model, { silent: true });
  const provider = acc.provider;
  const showBaseUrl = provider === 'custom' || OPTIONAL_BASE_URL_PROVIDERS.has(provider);
  els.baseUrlField?.classList.toggle('hidden', !showBaseUrl);
  refreshUsageForCurrentModel();
}

function effectiveModelHub(c) {
  if (!c) return null;
  const hub = c.modelHub;
  if (Array.isArray(hub?.accounts) && hub.accounts.length > 0) {
    return hub;
  }
  const provider = c.provider;
  const model = c.model;
  if (!provider && !model) return hub || null;
  const providerId = provider === 'zhipu' ? 'bigmodel' : (provider || 'opencode-zen');
  const accId = 'acc_default';
  const account = {
    id: accId,
    provider: providerId,
    label: '',
    apiKey: c.apiKey || '',
    baseUrl: c.baseUrl || '',
    enabled: true,
    models: model ? [model] : [],
    embeddingModels: [],
  };
  const accounts = [account];
  const index = { [`${providerId}\0${c.apiKey || ''}\0${c.baseUrl || ''}`]: accId };
  const fallbacks = [];
  for (const fb of c.modelFallbacks || []) {
    const fbModel = (fb?.model || '').trim();
    if (!fbModel) continue;
    const fbProvider = fb.provider === 'zhipu' ? 'bigmodel' : ((fb.provider || providerId).trim() || providerId);
    const fbKey = (fb.apiKey || '').trim() || (c.apiKey || '');
    const fbUrl = (fb.baseUrl || '').trim() || (c.baseUrl || '');
    const key = `${fbProvider}\0${fbKey}\0${fbUrl}`;
    let aid = index[key];
    if (!aid) {
      aid = `acc_${accounts.length}_${fbProvider}`;
      accounts.push({
        id: aid,
        provider: fbProvider,
        label: '',
        apiKey: fbKey,
        baseUrl: fbUrl,
        enabled: true,
        models: [],
        embeddingModels: [],
      });
      index[key] = aid;
    }
    const acc = accounts.find((a) => a.id === aid);
    if (acc && !acc.models.includes(fbModel)) acc.models.push(fbModel);
    const row = { accountId: aid, model: fbModel };
    if (fb.label) row.label = fb.label;
    fallbacks.push(row);
  }
  let embeddingPrimary = hub?.embeddingPrimary || null;
  let embeddingFallbacks = Array.isArray(hub?.embeddingFallbacks) ? hub.embeddingFallbacks : [];
  if (!embeddingPrimary) {
    const embModel = (c.embeddingModel || '').trim();
    if (embModel) {
      const embMode = c.embeddingMode || 'same';
      const embProv = c.embeddingProvider === 'zhipu' ? 'bigmodel' : ((c.embeddingProvider || providerId).trim() || providerId);
      const embKey = embMode === 'separate' ? (c.embeddingApiKey || '').trim() : (c.apiKey || '');
      const embUrl = embMode === 'separate' ? (c.embeddingBaseUrl || '').trim() : (c.baseUrl || '');
      const sameAccount = embProv === providerId && embKey === (c.apiKey || '') && embUrl === (c.baseUrl || '');
      let embAccId = accId;
      if (!sameAccount) {
        const embKeyIndex = `${embProv}\0${embKey}\0${embUrl}`;
        let aid = index[embKeyIndex];
        if (!aid) {
          aid = `acc_emb_${accounts.length}_${embProv}`;
          accounts.push({
            id: aid,
            provider: embProv,
            label: '',
            apiKey: embKey,
            baseUrl: embUrl,
            enabled: true,
            models: [],
            embeddingModels: [embModel],
          });
          index[embKeyIndex] = aid;
        } else {
          const acc = accounts.find((a) => a.id === aid);
          if (acc && !acc.embeddingModels.includes(embModel)) acc.embeddingModels.push(embModel);
        }
        embAccId = aid;
      } else {
        account.embeddingModels = [embModel];
      }
      embeddingPrimary = { accountId: embAccId, model: embModel };
    }
  }
  return {
    version: 2,
    accounts,
    primary: model ? { accountId: accId, model } : null,
    fallbacks,
    embeddingPrimary,
    embeddingFallbacks,
  };
}

function applyModelHubFromConfig(c) {
  const hub = effectiveModelHub(c);
  if (typeof ModelHub === 'undefined' || !hub) return;
  ModelHub.setHub(hub, { silent: true });
  syncLegacyFromModelHub(hub);
  const hubProviders = hubProviderOptions();
  ModelHub.setProviders(hubProviders.providers, hubProviders.providerLabels);
  refreshEmbeddingRouteSummary();
  if (typeof SessionModelPicker !== 'undefined') SessionModelPicker.refresh();
  refreshModelBadgeForSession();
}

function initModelCombos() {
  if (typeof ModelCombobox === 'undefined') return;
  const labels = () => ({
    placeholder: t('modelPlaceholder', 'model-id'),
    emptyLabel: t('noModels', 'No models loaded'),
    loadingLabel: t('loadingModels', 'Loading...'),
  });
  mainModelCombo = ModelCombobox.mount('#mainModelCombobox', {
    ...labels(),
    onChange: () => {
      persistConfigDraft();
      refreshUsageForCurrentModel();
    },
    onInput: () => {
      persistConfigDraft();
      refreshUsageForCurrentModel();
    },
  });
  if (document.querySelector('#embeddingModelCombobox')) {
    embeddingModelCombo = ModelCombobox.mount('#embeddingModelCombobox', {
      ...labels(),
      placeholder: t('embeddingModelPlaceholder', 'BAAI/bge-m3'),
      onChange: () => refreshEmbeddingUsageForCurrentModel(),
      onInput: () => refreshEmbeddingUsageForCurrentModel(),
    });
  }
  onboardingModelCombo = ModelCombobox.mount('#onboardingModelCombobox', {
    placeholder: 'deepseek-v4-flash',
    emptyLabel: t('noModels', 'No models loaded'),
    loadingLabel: t('loadingModels', 'Loading...'),
  });
  onboardingEmbeddingModelCombo = ModelCombobox.mount('#onboardingEmbeddingModelCombobox', {
    placeholder: t('embeddingModelPlaceholder', 'BAAI/bge-m3'),
    emptyLabel: t('noModels', 'No models loaded'),
    loadingLabel: t('loadingModels', 'Loading...'),
  });
  if (typeof ModelHub !== 'undefined') {
    ModelHub.mount('#modelHubRoot', {
      providers,
      providerLabels,
      getProviderLabel: (id) => providerDisplayName(id),
      t: (key, fallback) => t(key, fallback),
      api,
      onLegacySync: syncLegacyFromModelHub,
      onSaveHub: saveModelHubToServer,
      initial: savedConfig?.modelHub,
      defaultThinkingEnabled: savedConfig?.thinkingEnabled !== false,
    });
  } else if (typeof FallbackModels !== 'undefined') {
    FallbackModels.mount('#fallbackModelsRoot', {
      getProvider: () => els.providerSelect?.value || 'opencode-zen',
      getProviderLabel: (id) => providerDisplayName(id),
      providers,
      t: (key, fallback) => t(key, fallback),
    });
    document.getElementById('fallbackModelsRoot')?.addEventListener('fallbackchange', () => {
      persistConfigDraft();
      configSaveState = 'dirty';
      showUnsavedConfigWarning();
    });
  }
}

function sanitizeModelHubForSave(hub) {
  if (!hub?.accounts) return hub;
  return {
    ...hub,
    accounts: hub.accounts.map((acc) => {
      const row = { ...acc };
      if (row.apiKey?.startsWith('•')) delete row.apiKey;
      return row;
    }),
  };
}

async function saveModelHubToServer(hub, opts = {}) {
  const silent = !!opts.silent;
  const hubRoot = document.querySelector('#modelHubRoot');
  hubRoot?.classList.add('is-saving');
  try {
    const body = { modelHub: sanitizeModelHubForSave(hub) };
    const { data } = await api('POST', '/api/ai/config', body);
    if (!data?.ok) {
      if (!silent) showToast(data?.error || t('saveFailed', '保存失败'), 'error');
      throw new Error(data?.error || 'save failed');
    }
    configured = !!data.configured;
    configureError = data.configureError || '';
    if (data.modelHub) {
      savedConfig = { ...savedConfig, modelHub: data.modelHub };
      if (typeof ModelHub !== 'undefined') {
        ModelHub.setHub(data.modelHub, { silent: true });
      }
    }
    syncLegacyFromModelHub(savedConfig.modelHub || hub);
    updateModelBadgeFromSaved();
    refreshUsageForCurrentModel();
    LocalPrefs.clearConfigDraft();
    if (!silent) {
      showToast(t('saved', '已保存'), 'success');
    }
    return data;
  } finally {
    hubRoot?.classList.remove('is-saving');
  }
}

function getPersonaPayload() {
  return {
    systemPrompt: els.systemPromptInput?.value?.trim() || '',
    contextWindow: parseInt(els.contextWindowInput?.value, 10) || 0,
    compactionEnabled: !!els.compactionEnabledToggle?.checked,
    compactAfterTurns: parseInt(els.compactAfterTurnsInput?.value, 10) || 24,
    keepRecentTurns: parseInt(els.keepRecentTurnsInput?.value, 10) || 8,
    reserveTokens: parseInt(els.reserveTokensInput?.value, 10) || 8000,
    compactionTokenTrigger: !!els.compactionTokenTriggerToggle?.checked,
    evolutionEnabled: els.evolutionEnabledToggle?.checked !== false,
    evolutionAutoWorkspace: els.evolutionAutoWorkspaceToggle?.checked !== false,
    evolutionAutoMemory: els.evolutionAutoMemoryToggle?.checked !== false,
    evolutionLlmReflect: els.evolutionLlmReflectToggle?.checked !== false,
    evolutionAutoPropose: !!els.evolutionAutoProposeToggle?.checked,
    evolutionToolDesc: els.evolutionToolDescToggle?.checked !== false,
    evolutionGepaEnabled: els.evolutionGepaEnabledToggle?.checked !== false,
    evolutionUseDspy: !!els.evolutionUseDspyToggle?.checked,
    skillsDisclosureMax: parseInt(els.skillsDisclosureMaxInput?.value, 10) || 10,
    ragSearchLimit: parseInt(els.ragSearchLimitInput?.value, 10) || 20,
    evolutionCandidates: parseInt(els.evolutionCandidatesInput?.value, 10) || 3,
    thinkingEnabled: !!els.thinkingToggle?.checked,
    thinkingKeep: '',
    timezone: els.timezoneSelect?.value || 'Asia/Shanghai',
  };
}

async function savePersonaConfig() {
  const body = getPersonaPayload();
  const run = async () => {
    const { data } = await api('POST', '/api/ai/config', body);
    if (!data?.ok) {
      showToast(data?.error || t('saveFailed', '保存失败'), 'error');
      return;
    }
    savedConfig = { ...savedConfig, ...body };
    LocalPrefs.clearConfigDraft();
    showToast(t('saved', '已保存'), 'success');
  };
  if (typeof UiBusy !== 'undefined') {
    await UiBusy.withButtonBusy(els.personaSaveBtn, run, { busyLabel: t('uiSaving', '保存中…') });
  } else {
    await run();
  }
}

let embeddingSaveTimer = null;
function scheduleEmbeddingSave() {
  /* Embedding routes are saved via ModelHub */
}

async function saveEmbeddingConfig(_opts = {}) {
  /* no-op: embedding configured in model hub */
}

function refreshEmbeddingRouteSummary() {
  const el = document.getElementById('embeddingRouteSummary');
  const hint = document.getElementById('embeddingRouteHint');
  if (!el) return;
  const hub = effectiveModelHub(savedConfig);
  const routes = [];
  if (hub?.embeddingPrimary?.accountId) routes.push(hub.embeddingPrimary);
  for (const f of hub?.embeddingFallbacks || []) {
    if (f?.accountId) routes.push(f);
  }
  if (!routes.length) {
    const p = savedConfig?.embeddingProvider;
    const m = savedConfig?.embeddingModel;
    if (p && m) {
      el.textContent = `${providerLabels[p] || p} · ${m}`;
      if (hint) hint.textContent = t('embeddingRouteLegacyHint', '建议在模型中心配置 Embedding 路由与备用模型。');
      return;
    }
    el.textContent = t('embeddingRouteEmpty', '未配置 Embedding 模型');
    if (hint) hint.textContent = t('embeddingRouteHint', '在模型中心添加 Embedding 路由与备用模型，保存后自动重建索引。');
    return;
  }
  const lines = routes.map((r, i) => {
    const acc = (hub.accounts || []).find((a) => a.id === r.accountId);
    const prov = providerLabels[acc?.provider] || acc?.provider || r.accountId;
    const label = r.label ? `${r.label} · ` : '';
    const prefix = i === 0 ? t('modelHubPrimary', '主模型') : `#${i + 1}`;
    return `${prefix}: ${label}${prov} / ${r.model}`;
  });
  el.textContent = lines.join(' → ');
  if (hint) {
    const fb = Math.max(0, routes.length - 1);
    hint.textContent = fb
      ? t('embeddingRouteFallbackCount', '含 {n} 个备用模型', { n: fb })
      : t('embeddingRouteHint', '在模型中心添加 Embedding 路由与备用模型，保存后自动重建索引。');
  }
}

function getModelHubPayload() {
  if (typeof ModelHub === 'undefined') return undefined;
  const hub = ModelHub.prepareForSave?.() || ModelHub.getHub();
  if (hub?.accounts?.length) return hub;
  return effectiveModelHub({
    provider: els.providerSelect.value,
    model: getMainModelValue(),
    apiKey: els.apiKeyInput.value.trim(),
    baseUrl: els.baseUrlInput.value.trim(),
    modelFallbacks: typeof FallbackModels !== 'undefined' ? FallbackModels.getRows() : [],
  });
}

function getConfigPayload() {
  return {
    provider: els.providerSelect.value,
    model: getMainModelValue(),
    apiKey: els.apiKeyInput.value.trim(),
    baseUrl: els.baseUrlInput.value.trim(),
    systemPrompt: els.systemPromptInput.value.trim(),
    contextWindow: parseInt(els.contextWindowInput?.value, 10) || 0,
    compactionEnabled: !!els.compactionEnabledToggle?.checked,
    compactAfterTurns: parseInt(els.compactAfterTurnsInput?.value, 10) || 24,
    keepRecentTurns: parseInt(els.keepRecentTurnsInput?.value, 10) || 8,
    reserveTokens: parseInt(els.reserveTokensInput?.value, 10) || 8000,
    compactionTokenTrigger: !!els.compactionTokenTriggerToggle?.checked,
    evolutionEnabled: els.evolutionEnabledToggle?.checked !== false,
    evolutionAutoWorkspace: els.evolutionAutoWorkspaceToggle?.checked !== false,
    evolutionAutoMemory: els.evolutionAutoMemoryToggle?.checked !== false,
    evolutionLlmReflect: els.evolutionLlmReflectToggle?.checked !== false,
    evolutionAutoPropose: !!els.evolutionAutoProposeToggle?.checked,
    evolutionToolDesc: els.evolutionToolDescToggle?.checked !== false,
    evolutionGepaEnabled: els.evolutionGepaEnabledToggle?.checked !== false,
    evolutionUseDspy: !!els.evolutionUseDspyToggle?.checked,
    skillsDisclosureMax: parseInt(els.skillsDisclosureMaxInput?.value, 10) || 10,
    ragSearchLimit: parseInt(els.ragSearchLimitInput?.value, 10) || 20,
    evolutionCandidates: parseInt(els.evolutionCandidatesInput?.value, 10) || 3,
    thinkingEnabled: els.thinkingToggle.checked,
    thinkingKeep: '',
    timezone: els.timezoneSelect?.value || 'Asia/Shanghai',
    modelHub: getModelHubPayload(),
    modelFallbacks: typeof FallbackModels !== 'undefined' ? FallbackModels.getRows() : [],
  };
}

async function applyServerConfig(config, opts = {}) {
  if (!config) return;
  const prevTz = savedConfig?.timezone;
  savedConfig = { ...config };
  configured = !!config.configured;
  configureError = config.configureError || '';
  LocalPrefs.setConfigCache({ ...config, _providers: providers });

  const hasDraft = opts.keepDraft && reconcileConfigDraft(config);
  if (hasDraft) {
    applyConfigToForm(LocalPrefs.mergeDraftOntoServer(config, LocalPrefs.getConfigDraft()));
    configSaveState = 'dirty';
    showUnsavedConfigWarning();
  } else {
    applyConfigToForm(config);
    if (!opts.keepDraft) LocalPrefs.clearConfigDraft();
    if (configSaveState !== 'saving') configSaveState = 'saved';
  }
  updateConfigSaveHint();
  updateModelBadgeFromSaved();
  maybeDismissOnboardingWizard();
  refreshContextMeter();
  if (prevTz && prevTz !== config.timezone) {
    invalidateComposerSlashRoutes();
    if (cabanaInited && typeof CabanaPanel.reloadRoutes === 'function') {
      CabanaPanel.reloadRoutes().catch(() => {});
    }
  }
}

async function pullConfigFromDevice() {
  if (configSaveState === 'dirty' || configSaveInFlight) return false;
  const { data } = await api('GET', '/api/ai/config');
  if (!data?.ok || !data.config) return false;
  const prev = JSON.stringify(savedConfig);
  if (JSON.stringify(data.config) === prev) return false;
  await applyServerConfig(data.config);
  const provider = els.providerSelect?.value;
  const savedModel = savedConfig.model || defaults[provider] || '';
  await ensureModelsLoaded(savedModel, { refresh: false });
  refreshEmbeddingModels();
  applyEmbeddingModelSelection(savedConfig.embeddingModel || '');
  showConfigureHint();
  return true;
}

function updateConfigSaveHint() {}

function persistConfigDraft() {
  const draft = getConfigPayload();
  const safe = { ...draft };
  if (safe.apiKey?.startsWith('•')) delete safe.apiKey;
  if (safe.embeddingApiKey?.startsWith('•')) delete safe.embeddingApiKey;
  if (safe.modelHub?.accounts) {
    safe.modelHub = {
      ...safe.modelHub,
      accounts: safe.modelHub.accounts.map((acc) => {
        const row = { ...acc };
        if (row.apiKey?.startsWith('•')) delete row.apiKey;
        return row;
      }),
    };
    if (!safe.modelHub.accounts.length) delete safe.modelHub;
  }
  LocalPrefs.setConfigDraft(safe);
  if (configSaveState !== 'saving') {
    configSaveState = 'dirty';
    updateConfigSaveHint();
  }
  showUnsavedConfigWarning();
}

function bindConfigPersistence() {
  const personaFields = [
    els.systemPromptInput,
    els.contextWindowInput,
    els.compactionEnabledToggle,
    els.compactAfterTurnsInput,
    els.keepRecentTurnsInput,
    els.reserveTokensInput,
    els.compactionTokenTriggerToggle,
    els.thinkingToggle,
    els.evolutionEnabledToggle,
    els.evolutionAutoWorkspaceToggle,
    els.evolutionAutoMemoryToggle,
    els.evolutionLlmReflectToggle,
    els.evolutionAutoProposeToggle,
    els.evolutionToolDescToggle,
    els.evolutionGepaEnabledToggle,
    els.evolutionUseDspyToggle,
    els.skillsDisclosureMaxInput,
    els.ragSearchLimitInput,
    els.evolutionCandidatesInput,
    els.timezoneSelect,
  ].filter(Boolean);
  for (const field of personaFields) {
    const evt = field.tagName === 'SELECT' || field.type === 'checkbox' ? 'change' : 'input';
    field.addEventListener(evt, () => {
      configSaveState = 'dirty';
    });
  }
  const embeddingFields = [
    els.embeddingModeSelect,
    els.embeddingProviderSelect,
    embeddingModelCombo?.input,
    els.embeddingApiKeyInput,
    els.embeddingBaseUrlInput,
  ].filter(Boolean);
  for (const field of embeddingFields) {
    const evt = field.tagName === 'SELECT' || field.type === 'checkbox' ? 'change' : 'input';
    field.addEventListener(evt, () => scheduleEmbeddingSave());
  }
}

function reconcileConfigDraft(serverConfig) {
  const draft = LocalPrefs.getConfigDraft();
  if (!draft || !serverConfig) return false;
  const keys = [
    'provider', 'model', 'baseUrl', 'systemPrompt',
    'thinkingEnabled', 'embeddingMode', 'embeddingProvider', 'embeddingModel', 'embeddingBaseUrl',
  ];
  const differs = keys.some((k) => {
    const d = draft[k];
    const s = serverConfig[k];
    if (d === undefined || d === null || d === '') return false;
    return String(d) !== String(s ?? '');
  });
  const hasNewSecret = ['apiKey', 'embeddingApiKey'].some((k) => {
    const v = draft[k];
    if (!v || String(v).startsWith('•')) return false;
    return String(v) !== String(serverConfig[k] ?? '');
  });
  if (!differs && !hasNewSecret) {
    LocalPrefs.clearConfigDraft();
    return false;
  }
  return true;
}

function resolveFormConfig(serverConfig) {
  if (configSaveState === 'dirty' || LocalPrefs.getConfigDraft()) {
    return LocalPrefs.mergeDraftOntoServer(serverConfig, LocalPrefs.getConfigDraft());
  }
  return { ...(serverConfig || {}) };
}

async function applySavedModelSelection(savedModel) {
  const provider = els.providerSelect.value;
  const target = savedModel || defaults[provider] || '';
  if (!target) {
    applyDefaultModelForProvider();
    return;
  }
  mainModelCombo?.setValue(target, { silent: true });
}

function canFetchModelsFromForm() {
  if (configured) return true;
  const payload = getConfigPayload();
  if (payload.provider === 'custom' && !payload.baseUrl) {
    return false;
  }
  return !!(payload.apiKey?.trim());
}

function primeModelsFromCatalog(provider) {
  const cat = catalogModelsForProvider(provider || els.providerSelect?.value);
  if (!cat.length) return;
  models = cat;
  renderModelSelect();
}

function primeModelsFromCacheOrCatalog(provider) {
  const pid = provider || els.providerSelect?.value;
  if (models.length) return;
  const cache = LocalPrefs.getModelsCache(pid);
  if (cache?.models?.length) {
    models = cache.models;
    renderModelSelect();
    return;
  }
  primeModelsFromCatalog(pid);
}

async function ensureModelsLoaded(savedModel, opts = {}) {
  const refresh = opts.refresh !== false;
  const provider = els.providerSelect?.value;
  const target = savedModel || defaults[provider] || '';
  primeModelsFromCacheOrCatalog(provider);
  await applySavedModelSelection(target);
  updateModelBadgeFromSaved();
  if (refresh && canFetchModelsFromForm()) {
    fetchModels({ savedModel: target }).catch(() => {});
  }
}

function providerDisplayName(id) {
  if (providerLabels[id]) return providerLabels[id];
  if (embeddingProviderLabels[id]) return embeddingProviderLabels[id];
  const key = `provider_${id}`;
  const label = t(key, '');
  return label || id;
}

function hubProviderOptions() {
  const out = [...providers];
  for (const p of embeddingProviders) {
    if (!out.includes(p)) out.push(p);
  }
  return {
    providers: out,
    providerLabels: { ...embeddingProviderLabels, ...providerLabels },
  };
}

function renderProviderOptions() {
  if (!providers.length) {
    providers = FALLBACK_PROVIDERS.slice();
    if (!Object.keys(providerLabels).length) {
      providerLabels = { ...FALLBACK_PROVIDER_LABELS };
    }
  }
  const html = providers.map((p) => `<option value="${p}">${providerDisplayName(p)}</option>`).join('');
  if (els.providerSelect) els.providerSelect.innerHTML = html;
  renderEmbeddingProviderOptions();
}

function embeddingProviderDisplayName(id) {
  if (embeddingProviderLabels[id]) return embeddingProviderLabels[id];
  return FALLBACK_EMBEDDING_PROVIDER_LABELS[id] || id;
}

function renderEmbeddingProviderOptions() {
  if (!embeddingProviders.length) {
    embeddingProviders = FALLBACK_EMBEDDING_PROVIDERS.slice();
    if (!Object.keys(embeddingProviderLabels).length) {
      embeddingProviderLabels = { ...FALLBACK_EMBEDDING_PROVIDER_LABELS };
    }
  }
  const html = embeddingProviders.map((p) => `<option value="${p}">${embeddingProviderDisplayName(p)}</option>`).join('');
  if (els.embeddingProviderSelect) els.embeddingProviderSelect.innerHTML = html;
}

function getActiveEmbeddingProvider() {
  const separate = els.embeddingModeSelect?.value === 'separate';
  return separate ? (els.embeddingProviderSelect?.value || 'siliconflow') : els.providerSelect.value;
}

function embeddingCatalogForProvider(provider, sameMode = false) {
  const catalog = sameMode ? embeddingSameModeCatalog : embeddingModelCatalog;
  const ids = (catalog && catalog[provider]) || [];
  if (ids.length) return ids.map((id) => ({ id }));
  const def = embeddingDefaults[provider];
  return def ? [{ id: def }] : [];
}

function renderEmbeddingModelSelect() {
  embeddingModelCombo?.setOptions(embeddingModels);
}

function applyEmbeddingModelSelection(savedModel) {
  const provider = getActiveEmbeddingProvider();
  const target = savedModel || embeddingDefaults[provider] || '';
  if (!target) {
    if (embeddingModels.length) {
      embeddingModelCombo?.setValue(embeddingModels[0].id || embeddingModels[0], { silent: true });
    }
    return;
  }
  embeddingModelCombo?.setValue(target, { silent: true });
}

function refreshEmbeddingModels() {
  const separate = els.embeddingModeSelect?.value === 'separate';
  const provider = getActiveEmbeddingProvider();
  embeddingModels = embeddingCatalogForProvider(provider, !separate);
  renderEmbeddingModelSelect();
  if (!getEmbeddingModelValue() && embeddingModels.length) {
    embeddingModelCombo?.setValue(embeddingModels[0].id || embeddingModels[0], { silent: true });
  }
}

function catalogModelsForProvider(provider) {
  const ids = modelCatalog[provider] || [];
  return ids.map((id) => ({ id }));
}

function applyCatalogModelsIfNeeded() {
  const provider = els.providerSelect?.value;
  if (!provider || models.length) return;
  const cat = catalogModelsForProvider(provider);
  if (!cat.length) return;
  models = cat;
  renderModelSelect();
  applyDefaultModelForProvider();
}

function applyDefaultModelForProvider() {
  const provider = els.providerSelect.value;
  const defaultModel = defaults[provider];
  if (!defaultModel) return;
  if (!getMainModelValue()) {
    mainModelCombo?.setValue(defaultModel, { silent: true });
  }
}

function showConfigureHint() {}

async function loadProviders() {
  const { data } = await api('GET', '/api/ai/providers');
  if (!data.ok) return;
  providers = data.providers || [];
  providerLabels = data.providerLabels || {};
  modelCatalog = data.modelCatalog || {};
  defaults = data.defaults || {};
  embeddingProviders = data.embeddingProviders || FALLBACK_EMBEDDING_PROVIDERS.slice();
  embeddingProviderLabels = data.embeddingProviderLabels || { ...FALLBACK_EMBEDDING_PROVIDER_LABELS };
  embeddingModelCatalog = data.embeddingModelCatalog || {};
  embeddingSameModeCatalog = data.embeddingSameModeCatalog || {};
  embeddingDefaults = data.embeddingDefaults || embeddingDefaults;
  renderProviderOptions();
}

function applyConfigToForm(c) {
  if (!c) return;
  configured = !!c.configured;
  configureError = c.configureError || '';
  if (providers.includes(c.provider)) els.providerSelect.value = c.provider;
  else if (c.provider === 'zhipu' && providers.includes('bigmodel')) els.providerSelect.value = 'bigmodel';
  els.apiKeyInput.value = c.apiKey || '';
  els.baseUrlInput.value = c.baseUrl || '';
  els.systemPromptInput.value = c.systemPrompt || '';
  if (els.contextWindowInput) els.contextWindowInput.value = c.contextWindow ?? 0;
  if (els.compactionEnabledToggle) els.compactionEnabledToggle.checked = c.compactionEnabled !== false;
  if (els.compactAfterTurnsInput) els.compactAfterTurnsInput.value = c.compactAfterTurns ?? 24;
  if (els.keepRecentTurnsInput) els.keepRecentTurnsInput.value = c.keepRecentTurns ?? 8;
  if (els.reserveTokensInput) els.reserveTokensInput.value = c.reserveTokens ?? 8000;
  if (els.compactionTokenTriggerToggle) els.compactionTokenTriggerToggle.checked = c.compactionTokenTrigger !== false;
  if (els.evolutionEnabledToggle) els.evolutionEnabledToggle.checked = c.evolutionEnabled !== false;
  if (els.evolutionAutoWorkspaceToggle) els.evolutionAutoWorkspaceToggle.checked = c.evolutionAutoWorkspace !== false;
  if (els.evolutionAutoMemoryToggle) els.evolutionAutoMemoryToggle.checked = c.evolutionAutoMemory !== false;
  if (els.evolutionLlmReflectToggle) els.evolutionLlmReflectToggle.checked = c.evolutionLlmReflect !== false;
  if (els.evolutionAutoProposeToggle) els.evolutionAutoProposeToggle.checked = !!c.evolutionAutoPropose;
  if (els.evolutionToolDescToggle) els.evolutionToolDescToggle.checked = c.evolutionToolDesc !== false;
  if (els.evolutionGepaEnabledToggle) els.evolutionGepaEnabledToggle.checked = c.evolutionGepaEnabled !== false;
  if (els.evolutionUseDspyToggle) els.evolutionUseDspyToggle.checked = !!c.evolutionUseDspy;
  if (els.skillsDisclosureMaxInput) els.skillsDisclosureMaxInput.value = c.skillsDisclosureMax ?? 10;
  if (els.ragSearchLimitInput) els.ragSearchLimitInput.value = c.ragSearchLimit ?? 20;
  if (els.evolutionCandidatesInput) els.evolutionCandidatesInput.value = c.evolutionCandidates ?? 3;
  els.thinkingToggle.checked = !!c.thinkingEnabled;
  if (els.timezoneSelect) {
    renderTimezoneSelect(c.timezone || 'Asia/Shanghai');
  }
  if (c.model) mainModelCombo?.setValue(c.model, { silent: true });
  applyModelHubFromConfig(c);
  refreshEmbeddingRouteSummary();
  if (typeof FallbackModels !== 'undefined' && !(effectiveModelHub(c)?.accounts?.length)) {
    FallbackModels.setRows(c.modelFallbacks || []);
    FallbackModels.setProviders(providers);
  }
}

async function loadBootstrap() {
  const { data } = await api('GET', '/api/ai/bootstrap?lite=1', null, { timeoutMs: 20000 });
  if (!data.ok) {
    ensureProviderOptions();
    const cache = LocalPrefs.getConfigCache();
    if (cache && Object.keys(cache).length) {
      savedConfig = { ...cache };
      if (cache._providers?.length) {
        providers = cache._providers;
        renderProviderOptions();
      }
      applyConfigToForm(cache);
      updateModelBadgeFromSaved();
    }
    showConfigureHint();
    configSaveState = reconcileConfigDraft(savedConfig) ? 'dirty' : 'idle';
    updateConfigSaveHint();
    return;
  }

  providers = data.providers || [];
  providerLabels = data.providerLabels || {};
  modelCatalog = data.modelCatalog || {};
  defaults = data.defaults || {};
  embeddingDefaults = data.embeddingDefaults || {};
  embeddingProviders = data.embeddingProviders || FALLBACK_EMBEDDING_PROVIDERS.slice();
  embeddingProviderLabels = data.embeddingProviderLabels || { ...FALLBACK_EMBEDDING_PROVIDER_LABELS };
  embeddingModelCatalog = data.embeddingModelCatalog || {};
  embeddingSameModeCatalog = data.embeddingSameModeCatalog || {};
  renderProviderOptions();
  if (typeof ModelHub !== 'undefined') {
    const hubProviders = hubProviderOptions();
    ModelHub.setProviders(hubProviders.providers, hubProviders.providerLabels);
  }

  if (data.config) {
    await applyServerConfig(data.config, { keepDraft: true });
  }

  state = {
    driving: !!data.driving,
    configured: data.config?.configured,
    state: data.state || {},
    adminMode: data.adminMode !== false,
  };
  if (data.tools) {
    toolsMeta = data.tools;
    LocalPrefs.setServerToolDefaults(data.tools);
  }
  if (Array.isArray(data.skills)) skillsRegistry = data.skills;
  hostEnvironment = data.hostEnvironment || hostEnvironment;
  applyHeaderChrome();
  applyStatusPill(data);
  applyBuiltinAgents(data);
  if (data.notifications) {
    updateNotificationsBadge((data.notifications || []).filter((i) => !i.read).length);
  }

  const provider = els.providerSelect.value;
  if (Array.isArray(data.models) && data.models.length) {
    models = data.models;
    renderModelSelect();
    LocalPrefs.setModelsCache(provider, models);
  } else {
    const modelCache = LocalPrefs.getModelsCache(provider);
    if (modelCache?.models?.length) {
      models = modelCache.models;
      renderModelSelect();
    } else {
      primeModelsFromCatalog(provider);
    }
  }

  const savedModel = savedConfig?.model || defaults[provider] || '';
  const gotLiveModels = data.modelsSource === 'api' && Array.isArray(data.models) && data.models.length > 0;
  ensureModelsLoaded(savedModel, { refresh: false }).catch(() => {});
  if (!gotLiveModels && canFetchModelsFromForm()) {
    fetchModels({ savedModel }).catch(() => {});
  }
  refreshEmbeddingModels();
  applyEmbeddingModelSelection(savedConfig?.embeddingModel || '');

  showConfigureHint();
  if (data.onboarding?.showWizard) {
    openOnboardingWizard();
  }
  if (data.consumer?.wizards) {
    window.__consumerWizards = data.consumer.wizards;
    renderConsumerQuickActions(data.consumer.wizards);
  }
  loadUsage().catch(() => {});
  refreshRagStatsForMeter();
  api('GET', '/api/ai/mcp').then(({ data }) => {
    if (Array.isArray(data?.servers)) {
      mcpConnectors = data.servers;
      refreshContextMeter();
    }
  }).catch(() => {});
}

async function loadConfig() {
  const { data } = await api('GET', '/api/ai/config');
  if (!data.ok) return;
  await applyServerConfig(data.config, { keepDraft: configSaveState === 'dirty' });

  const c = savedConfig;
  const savedModel = c.model || defaults[c.provider] || '';
  primeModelsFromCacheOrCatalog(c.provider);
  if (savedModel) {
    await applySavedModelSelection(savedModel);
  } else {
    applyDefaultModelForProvider();
    renderModelSelect();
  }

  showConfigureHint();
  loadUsage().catch(() => {});
  if (canFetchModelsFromForm()) {
    fetchModels({ savedModel }).catch(() => {});
  }
}

function renderModelSelect() {
  mainModelCombo?.setOptions(models);
}

async function fetchModels(opts = {}) {
  const savedModel = opts.savedModel ?? getMainModelValue() ?? '';
  const provider = els.providerSelect.value;
  if (!canFetchModelsFromForm()) {
    models = catalogModelsForProvider(provider);
    renderModelSelect();
    if (savedModel) await applySavedModelSelection(savedModel);
    else applyDefaultModelForProvider();
    showConfigureHint();
    return;
  }

  if (!models.length) {
    primeModelsFromCacheOrCatalog(provider);
    if (savedModel) await applySavedModelSelection(savedModel);
  }

  const showSpinner = !models.length;
  if (showSpinner) mainModelCombo?.setLoading(true);
  const payload = getConfigPayload();
  const { data } = await api('POST', '/api/ai/models', {
    provider: payload.provider,
    apiKey: payload.apiKey,
    baseUrl: payload.baseUrl,
    model: payload.model,
  });
  models = [];
  configured = !!data.configured;
  configureError = data.configureError || data.error || '';
  if (data.ok && Array.isArray(data.models)) {
    models = data.models;
    LocalPrefs.setModelsCache(payload.provider, models);
  } else {
    const cat = catalogModelsForProvider(payload.provider);
    if (cat.length) {
      models = cat;
    }
  }
  mainModelCombo?.setLoading(false);
  renderModelSelect();
  if (savedModel) await applySavedModelSelection(savedModel);
}

function onProviderChange() {
  const provider = els.providerSelect.value;
  const showBaseUrl = provider === 'custom' || OPTIONAL_BASE_URL_PROVIDERS.has(provider);
  els.baseUrlField.classList.toggle('hidden', !showBaseUrl);
  if (els.baseUrlInput) {
    const hintKey = `baseUrlPlaceholder_${provider}`;
    const hint = t(hintKey, '');
    els.baseUrlInput.placeholder = hint || t('baseUrlPlaceholder');
  }
  applyDefaultModelForProvider();
  applyCatalogModelsIfNeeded();
  if (els.embeddingModeSelect?.value === 'same') {
    refreshEmbeddingModels();
    if (!getEmbeddingModelValue()) {
      applyEmbeddingModelSelection(embeddingDefaults[provider] || '');
    }
  }
  if (typeof ModelHub !== 'undefined') {
    ModelHub.setProviders(providers, providerLabels);
  } else if (typeof FallbackModels !== 'undefined') {
    FallbackModels.setProviders(providers);
    FallbackModels.refreshMainProviderLabels?.();
  }
}

function onEmbeddingModeChange() {
  const separate = els.embeddingModeSelect?.value === 'separate';
  els.embeddingSeparateFields?.classList.toggle('hidden', !separate);
  if (separate) {
    const isCustom = els.embeddingProviderSelect?.value === 'custom';
    els.embeddingBaseUrlField?.classList.toggle('hidden', !isCustom);
  }
  refreshEmbeddingModels();
  applyEmbeddingModelSelection(getEmbeddingModelValue());
}

function onEmbeddingProviderChange() {
  onEmbeddingModeChange();
}

async function saveConfig(opts = {}) {
  const silent = !!opts.silent;
  if (configSaveInFlight) return;
  if (typeof ModelHub !== 'undefined' && ModelHub.prepareForSave) {
    ModelHub.prepareForSave();
  }
  const body = getConfigPayload();
  if (body.modelHub?.accounts) {
    body.modelHub = {
      ...body.modelHub,
      accounts: body.modelHub.accounts.map((acc) => {
        const row = { ...acc };
        if (row.apiKey?.startsWith('•')) delete row.apiKey;
        return row;
      }),
    };
  }
  if (body.apiKey?.startsWith('•')) delete body.apiKey;
  if (body.embeddingApiKey?.startsWith('•')) delete body.embeddingApiKey;
  configSaveInFlight = true;
  configSaveState = 'saving';
  updateConfigSaveHint();
  if (typeof UiBusy !== 'undefined') {
    UiBusy.setButtonBusy(els.saveBtn, true, { busyLabel: t('uiSaving', '保存中…') });
  } else if (els.saveBtn) {
    els.saveBtn.disabled = true;
  }
  let status = 0;
  let data = {};
  try {
    ({ status, data } = await api('POST', '/api/ai/config', body));
  } finally {
    configSaveInFlight = false;
    if (typeof UiBusy !== 'undefined') {
      UiBusy.setButtonBusy(els.saveBtn, false);
    } else if (els.saveBtn) {
      els.saveBtn.disabled = false;
    }
  }
  if (data.ok) {
    configured = !!data.configured;
    configureError = data.configureError || '';
    if (data.modelHub) {
      savedConfig = { ...savedConfig, modelHub: data.modelHub };
      if (typeof ModelHub !== 'undefined') {
        ModelHub.setHub(data.modelHub, { silent: true });
      }
    }
    LocalPrefs.clearConfigDraft();
    await loadConfig();
    configSaveState = 'saved';
    updateConfigSaveHint();
    updateModelBadgeFromSaved();
    if (!silent) {
      showToast(t('saved', 'Saved'), 'success');
    }
    if (configured) {
      await api('POST', '/api/ai/onboarding/complete', {}).catch(() => {});
      closeOnboardingWizard();
      await fetchModels();
      await verifyConnection({ silent: true });
    } else {
      showConfigureHint();
      if (!silent) {
        showToast(configureError || t('configureHint', 'Configuration incomplete'), 'warning');
      }
    }
    invalidateComposerSlashRoutes();
    if (cabanaInited && typeof CabanaPanel.reloadRoutes === 'function') {
      CabanaPanel.reloadRoutes().catch(() => {});
    }
  } else {
    configSaveState = 'error';
    updateConfigSaveHint();
    if (!silent) {
      showToast(data.error || `${t('saveFailed', 'Save failed')} (${status})`, 'error');
    }
  }
}

function connectionPayloadFromSaved() {
  if (!savedConfig?.provider) return null;
  return {
    provider: savedConfig.provider,
    model: savedConfig.model,
    apiKey: savedConfig.apiKey || '',
    baseUrl: savedConfig.baseUrl || '',
  };
}

async function verifyConnection(opts = {}) {
  const silent = !!opts.silent;
  const payload = connectionPayloadFromSaved();
  if (!payload?.provider) {
    showConfigureHint();
    return false;
  }
  if (!canFetchModelsFromForm() && !savedConfig?.configured) {
    const msg = configureError || t('configureHint', 'Set API key and Base URL (for custom) then save.');
    if (!silent) showToast(msg, 'warning');
    return false;
  }

  if (opts.testBtn && typeof UiBusy !== 'undefined') {
    UiBusy.setButtonBusy(opts.testBtn, true, { busyLabel: t('testing', '测试中…') });
  }
  try {
    const { data } = await api('POST', '/api/ai/test_connection', payload);
    if (!data.ok) {
      const msg = formatApiError(data.error || t('connectionFailed', 'Connection failed'));
      configureError = data.error || msg;
      configured = false;
      if (!silent) showToast(msg.split('\n')[0], 'error');
      return false;
    }
    configured = true;
    configureError = '';
    if (!silent) {
      showToast(data.message || t('connectionOk', 'Connection OK'), data.model_available ? 'success' : 'warning');
    }
    return true;
  } finally {
    if (opts.testBtn && typeof UiBusy !== 'undefined') {
      UiBusy.setButtonBusy(opts.testBtn, false);
    }
  }
}

// ---------------------------------------------------------------------------
// Status
// ---------------------------------------------------------------------------

function formatVehicleStatus(vs) {
  if (!vs || typeof vs !== 'object') return { short: '', title: '' };
  const kph = vs.vEgoKph ?? (vs.v_ego != null ? Math.round(vs.v_ego * 3.6) : null);
  const speed = kph != null ? `${kph} km/h` : '';
  const op = vs.enabled
    ? (vs.active ? t('statusOpActive') : t('statusOpStandby'))
    : (vs.engageable ? t('statusEngageable') : '');
  const alert = vs.alert_text1 || vs.alertText1 || '';
  const vehicle = [vs.brand, vs.car_fingerprint || vs.carFingerprint].filter(Boolean).join(' ');
  const chunks = [speed, op, alert].filter(Boolean);
  const short = chunks.length ? chunks.join(' · ') : (vs.started ? t('statusOnroad', 'On road') : t('statusOffroad', 'Off road'));
  const titleParts = [
    vehicle,
    speed,
    vs.selfdrive_state || vs.selfdriveState,
    vs.gear_shifter || vs.gearShifter,
    alert,
    vs.alert_text2 || vs.alertText2,
  ].filter(Boolean);
  return { short, title: titleParts.join(' · ') };
}

function getHardwareProfile(env) {
  return env?.hardware_profile || env?.comma_device || {};
}

function formatEnvKindLabel(env) {
  const hp = getHardwareProfile(env);
  if (hp.host_kind_label) return hp.host_kind_label;
  if (env?.host_kind === 'pc_dev') return 'PC';
  const map = { tici: 'C3', tizi: 'C3X', mici: 'C4' };
  return hp.product_label || map[hp.device_type] || 'COMMA';
}

function commaEnvTag(env) {
  return formatEnvKindLabel(env);
}

function renderRunStatus(label, on) {
  const cls = on ? 'on' : 'off';
  const text = on ? t('devStatusOn', '运行中') : t('devStatusOff', '未运行');
  return `<span class="dev-status ${cls}">${escapeHtml(label)} · ${text}</span>`;
}

function applyStatusPill(data) {
  const pill = els.statusPill;
  if (!pill || !data) return;
  pill.classList.remove('loading');
  pill.removeAttribute('hidden');
  const vs = data.state || {};
  const { short, title } = formatVehicleStatus(vs);
  const env = data.hostEnvironment || hostEnvironment;
  const envTag = commaEnvTag(env);
  if (data.driving) {
    pill.textContent = envTag ? `${envTag} · ${short || t('statusDriving', 'Driving')}` : (short || t('statusDriving', 'Driving — read only'));
    pill.className = 'status-pill driving';
  } else {
    pill.textContent = envTag ? `${envTag} · ${short || t('statusStopped', 'Stopped')}` : (short || t('statusStopped', 'Stopped — config allowed'));
    pill.className = 'status-pill stopped';
  }
  const hp = getHardwareProfile(env);
  const envLine = env
    ? `\n环境: ${formatEnvKindLabel(env)}${hp.panda_mcu ? ` · MCU ${hp.panda_mcu}` : ''}${hp.panda_backend ? ` · ${hp.panda_backend}` : ''} · ${env.platform || ''}`
    : '';
  pill.title = (title || pill.textContent) + envLine;
  const queueBadge = document.getElementById('queueModeBadge');
  if (queueBadge) {
    queueBadge.classList.toggle('hidden', !data.driving);
    if (typeof CommandQueue !== 'undefined') CommandQueue.renderBadge?.();
  }
}

function renderHostEnvCard(env) {
  const paths = env.paths || {};
  const isPc = env.host_kind === 'pc_dev';
  const hp = getHardwareProfile(env);
  const kindLabel = formatEnvKindLabel(env);
  const hwChips = [
    hp.panda_mcu ? `MCU ${hp.panda_mcu}` : '',
    hp.panda_backend || '',
    hp.pandad_process || '',
    hp.use_tici_panda_stack === false && hp.tici_dos ? 'panda 回退' : '',
  ].filter(Boolean).map((text) => `<span class="dev-chip dev-chip-tool">${escapeHtml(text)}</span>`).join('');

  const launchable = Object.entries(env.pc_tools || {})
    .filter(([, v]) => v?.launchable)
    .map(([k]) => k);
  const envHint = paths.env_overrides?.OPENPILOT_ROOT
    ? t('devEnvFromEnv', '已通过 OPENPILOT_ROOT 指定')
    : t('devEnvAutoDetect', '自动识别；可设 OPENPILOT_ROOT / OPENPILOT_ROUTES_DIR');
  const routesMissing = paths.routes_dir_exists === false
    ? `<div class="dev-env-hint">${t('devRoutesMissing', '路线目录不存在：请先录路，或设置 OPENPILOT_ROUTES_DIR')}</div>`
  : '';

  const toolChips = launchable.length
    ? launchable.map((k) => `<span class="dev-chip dev-chip-tool">${escapeHtml(k)}</span>`).join('')
    : `<span class="dev-chip dev-chip-tool">${t('devNoPcTools', '无')}</span>`;

  const pandaValue = isPc
    ? (hp.panda_connected
      ? `${hwChips}${hp.inferred_class ? ` <span class="muted">(${escapeHtml(hp.inferred_class)})</span>` : ''}`
      : `<span class="muted">${t('devEnvPandaDisconnected', '未连接')} (${escapeHtml(hp.panda_probe || 'panda')})</span>${hp.panda_probe_error ? `<div class="dev-env-hint muted">${escapeHtml(hp.panda_probe_error)}</div>` : ''}`)
    : (hwChips || `<span class="muted">${escapeHtml(hp.product_name || hp.device_type || '—')}</span>`);

  const runtimeRow = `
    <div class="dev-kv">
      <span class="dev-kv-label">${t('devEnvRuntime', '进程')}</span>
      <span class="dev-kv-value"><div class="dev-chip-row">
        ${renderRunStatus('manager', !!hp.manager_running)}
        ${renderRunStatus(hp.pandad_process || 'pandad', !!hp.pandad_running)}
      </div></span>
    </div>`;

  return `
    <div class="dev-kv">
      <span class="dev-kv-label">${t('devEnvKind', '环境')}</span>
      <span class="dev-kv-value">
        <span class="dev-chip ${isPc ? 'dev-chip-pc' : 'dev-chip-device'}">${escapeHtml(kindLabel)}</span>
        ${hp.device_type ? `<span class="muted"> ${escapeHtml(hp.device_type)}</span>` : ''}
      </span>
    </div>
    <div class="dev-kv">
      <span class="dev-kv-label">${t('devEnvPanda', 'Panda')}</span>
      <span class="dev-kv-value">${pandaValue}</span>
    </div>
    ${runtimeRow}
    <div class="dev-kv">
      <span class="dev-kv-label">${t('devEnvPlatform', '系统')}</span>
      <span class="dev-kv-value">${escapeHtml(env.platform || '—')}</span>
    </div>
    <div class="dev-kv">
      <span class="dev-kv-label">${t('devEnvRoot', '仓库')}</span>
      <span class="dev-kv-value"><code>${escapeHtml(env.openpilot_root || paths.openpilot_root || '—')}</code></span>
    </div>
    <div class="dev-kv">
      <span class="dev-kv-label">${t('devEnvRoutes', '路线')}</span>
      <span class="dev-kv-value"><code>${escapeHtml(env.routes_dir || paths.routes_dir || '—')}</code></span>
    </div>
    <div class="dev-kv">
      <span class="dev-kv-label">${t('devEnvTools', 'PC 工具')}</span>
      <span class="dev-kv-value"><div class="dev-chip-row">${toolChips}</div></span>
    </div>
    ${routesMissing}
    ${env.hint ? `<p class="dev-env-hint">${escapeHtml(env.hint)}</p>` : ''}
    <p class="dev-env-hint muted">${escapeHtml(envHint)}</p>`;
}

function renderDevSessions(sessions) {
  if (!sessions.length) {
    return `<li class="dev-empty">${t('devNoSessions', '暂无 PC 工具会话')}</li>`;
  }
  return sessions.map((s) => {
    const sid = String(s.session_id || '').slice(0, 8);
    const tool = escapeHtml(s.tool || 'tool');
    const route = escapeHtml(s.route || t('devNoRoute', '未绑定路线'));
    const alive = Boolean(s.alive);
    return `<li class="dev-item dev-session-item">
      <div class="dev-item-main">
        <span class="dev-item-title">${tool}</span>
        <span class="dev-item-sub">${sid ? `#${sid}` : ''} · ${route}</span>
      </div>
      <span class="dev-status ${alive ? 'on' : 'off'}">${alive ? t('devSessionAlive', '运行中') : t('devSessionDone', '已结束')}</span>
    </li>`;
  }).join('');
}

function renderDevAssets(rows) {
  if (!rows.length) {
    return `<li class="dev-empty">${t('devNoAssets', '暂无报告或导出文件')}</li>`;
  }
  return rows.map((r) => {
    const kindLabel = r.kind === 'reports' ? t('devKindReport', '报告') : t('devKindExport', '导出');
    return `<li class="dev-item dev-asset-item">
      <a class="dev-item-link dev-item-main" href="${escapeHtml(r.url)}" target="_blank" rel="noopener">${escapeHtml(r.name)}</a>
      <span class="dev-kind-tag">${escapeHtml(kindLabel)}</span>
    </li>`;
  }).join('');
}

async function loadKnowledgeRagStatus(ragData) {
  if (!els.ragStatusBox) return;
  try {
    let rag = ragData;
    let cfg = savedConfig;
    if (!rag) {
      const [{ data }, boot] = await Promise.all([
        fetchRagApi({ compact: true, timeoutMs: 8000 }),
        cfg ? Promise.resolve({ data: { config: cfg } }) : api('GET', '/api/ai/bootstrap').catch(() => ({ data: {} })),
      ]);
      rag = data;
      cfg = boot?.data?.config || savedConfig;
    }
    els.ragStatusBox.innerHTML = renderRagStatusCard(rag, cfg);
    if (els.knowledgeRagBadge) {
      const chunks = Number(rag?.vector_chunks) || 0;
      const docs = Number(rag?.count) || 0;
      els.knowledgeRagBadge.textContent = chunks > 0 ? String(chunks) : (docs > 0 ? String(docs) : '—');
    }
  } catch (e) {
    els.ragStatusBox.innerHTML = `<p class="dev-empty">${escapeHtml(e.message || t('devRagLoadFail', '无法加载知识库状态'))}</p>`;
  }
}

const runtimeState = { activeTab: 'env' };
const devPaneState = { activeSection: 'collab' };

function setDevPaneSection(section) {
  const id = section || 'collab';
  devPaneState.activeSection = id;
  document.querySelectorAll('[data-dev-pane]').forEach((btn) => {
    const on = btn.dataset.devPane === id;
    btn.classList.toggle('is-active', on);
    btn.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  document.querySelectorAll('[data-dev-section]').forEach((panel) => {
    panel.classList.toggle('hidden', panel.dataset.devSection !== id);
  });
  const desc = $('#devPaneDesc');
  if (desc) {
    const key = id === 'cache' ? 'devPaneDescCache' : (id === 'runtime' ? 'devPaneDescRuntime' : 'devPaneDescCollab');
    const fallback = id === 'cache'
      ? '路线回放、TSK 提取等本地缓存管理'
      : (id === 'runtime' ? '本机环境、工具会话与输出资产' : 'Fork 分析、发布 PR 与反馈');
    desc.textContent = t(key, fallback);
  }
  if (id === 'cache') loadDevCacheStatus().catch(() => {});
}

function bindDevPaneSectionControls() {
  document.querySelectorAll('[data-dev-pane]').forEach((btn) => {
    btn.addEventListener('click', () => setDevPaneSection(btn.dataset.devPane));
  });
  setDevPaneSection(devPaneState.activeSection || 'collab');
}

function setRuntimeTab(tab) {
  const id = tab || 'env';
  runtimeState.activeTab = id;
  document.querySelectorAll('[data-runtime-tab]').forEach((btn) => {
    const on = btn.dataset.runtimeTab === id;
    btn.classList.toggle('is-active', on);
    btn.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  document.querySelectorAll('[data-runtime-panel]').forEach((panel) => {
    panel.classList.toggle('hidden', panel.dataset.runtimePanel !== id);
  });
}

function bindRuntimeTabControls() {
  document.querySelectorAll('[data-runtime-tab]').forEach((btn) => {
    btn.addEventListener('click', () => setRuntimeTab(btn.dataset.runtimeTab));
  });
  setRuntimeTab(runtimeState.activeTab || 'env');
}

function updateRuntimeSummary({ env, sessions, passport, assets }) {
  if (!els.devRuntimeSummary) return;
  const kind = env ? formatEnvKindLabel(env) : '—';
  const platform = (env?.platform || '').split(' - ')[0] || '—';
  const hp = env?.hardware_profile || {};
  const pandaOk = !!hp.panda_connected;
  const pandaText = pandaOk
    ? t('devEnvPandaConnected', 'Panda 已连接')
    : t('devEnvPandaDisconnected', 'Panda 未连接');
  const sessN = sessions?.length || 0;
  const passportN = passport?.entries?.length ?? passport?.count ?? 0;
  const assetN = assets?.length || 0;
  const parts = [
    kind,
    platform,
    pandaText,
    `${sessN} ${t('devRuntimeSessionsShort', '会话')}`,
    `${assetN} ${t('devRuntimeAssetsShort', '文件')}`,
  ];
  if (passportN > 0) parts.push(`${passportN} ${t('devRuntimePassportShort', '调参')}`);
  els.devRuntimeSummary.textContent = parts.filter(Boolean).join(' · ');
}

const collabState = {
  pkg: null,
  fork: null,
  publish: null,
  primaryForge: 'github',
  activeTab: 'repo',
};

function setCollabTab(tab) {
  const id = tab || 'repo';
  collabState.activeTab = id;
  document.querySelectorAll('[data-collab-tab]').forEach((btn) => {
    const on = btn.dataset.collabTab === id;
    btn.classList.toggle('is-active', on);
    btn.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  document.querySelectorAll('[data-collab-panel]').forEach((panel) => {
    panel.classList.toggle('hidden', panel.dataset.collabPanel !== id);
  });
}

function bindCollabTabControls() {
  document.querySelectorAll('[data-collab-tab]').forEach((btn) => {
    btn.addEventListener('click', () => setCollabTab(btn.dataset.collabTab));
  });
  els.collabGoPublishPrTab?.addEventListener('click', () => setCollabTab('publish'));
  setCollabTab(collabState.activeTab || 'repo');
}

function renderCollabForgeChip(forge, auth) {
  const label = forge === 'gitee' ? 'Gitee' : 'GitHub';
  const statusClass = auth?.valid ? 'on' : (auth?.configured ? 'warn' : 'off');
  let text = label;
  if (auth?.valid && auth.user) text = `${label} @${auth.user}`;
  else if (auth?.valid) text = `${label} ✓`;
  else if (auth?.configured) text = `${label} !`;
  else text = `${label} —`;
  return `<span class="dev-collab-chip dev-status ${statusClass}">${escapeHtml(text)}</span>`;
}

function updateCollabStatusBar() {
  const pkg = collabState.pkg;
  const fork = collabState.fork;
  const publish = collabState.publish;
  if (els.collabVersionLine) {
    const version = pkg?.version ? `v${pkg.version}` : '—';
    const git = pkg?.git_commit
      ? `${pkg.git_commit.slice(0, 8)}${pkg.git_dirty ? ' *' : ''}`
      : (pkg?.ok === false ? '' : t('devPackageNotGit', '非 git 安装'));
    const updateHint = pkg?.update_available
      ? ` · ${t('devPackageUpdateAvailable', '有新版本可更新')}`
      : '';
    els.collabVersionLine.textContent = `op助手 ${version}${git ? ` · ${git}` : ''}${updateHint}`;
  }
  if (els.collabRepoLine) {
    if (!fork?.ok) {
      els.collabRepoLine.textContent = fork?.error || t('devForkLoadFail', '无法扫描 fork');
    } else {
      const community = fork.community_match || {};
      const displayId = community.id || fork.fork_id || '—';
      const displayLabel = community.name || fork.fork_label || displayId;
      const branch = fork.git_branch || '—';
      const units = publish?.units || [];
      const dirtyTotal = units.reduce((sum, u) => sum + (Number(u.dirty_count) || 0), 0);
      const dirtyPart = dirtyTotal > 0
        ? ` · ${dirtyTotal} ${t('devPublishDirty', '处改动')}`
        : ` · ${t('devPublishClean', '无改动')}`;
      els.collabRepoLine.textContent = `${displayLabel} · ${branch}${dirtyPart}`;
    }
  }
  if (els.collabAuthLine) {
    const auth = publish?.forge_auth || {};
    const primary = collabState.primaryForge || inferCollabForge({ fork: collabState.fork, publish });
    const chip = renderCollabForgeChip(primary, auth[primary] || {});
    els.collabAuthLine.innerHTML = chip;
  }
  if (els.devCollabDirtyBadge) {
    const units = publish?.units || [];
    const dirtyUnits = units.filter((u) => u.has_changes).length;
    els.devCollabDirtyBadge.textContent = dirtyUnits > 0 ? String(dirtyUnits) : '—';
    els.devCollabDirtyBadge.title = dirtyUnits > 0
      ? `${dirtyUnits} ${t('devCollabDirtyUnits', '个仓库有未发布改动')}`
      : '';
  }
  if (els.devPackageUpdateBtn && pkg) {
    els.devPackageUpdateBtn.hidden = !pkg.update_available;
    els.devPackageUpdateBtn.disabled = false;
  }
}

function renderPackageVersionCard(pkg) {
  if (!pkg || !pkg.ok) {
    return `<p class="dev-empty">${escapeHtml(pkg?.error || t('devPackageLoadFail', '无法加载版本信息'))}</p>`;
  }
  const lines = [
    ['版本', pkg.version || '—'],
    ['Git', pkg.git_commit ? `${pkg.git_commit}${pkg.git_dirty ? ' *' : ''}` : t('devPackageNotGit', '非 git 安装')],
    ['远程', pkg.remote_version || pkg.remote_commit || '—'],
  ];
  const rows = lines.map(([label, val]) => `
    <div class="dev-kv">
      <span class="dev-kv-label">${escapeHtml(label)}</span>
      <span class="dev-kv-value">${escapeHtml(String(val))}</span>
    </div>`).join('');
  const hint = pkg.update_available
    ? `<p class="dev-env-hint">${t('devPackageUpdateAvailable', '有新版本可更新')}${pkg.remote_version ? ` → v${escapeHtml(pkg.remote_version)}` : ''}</p>`
    : (pkg.fetch_error ? `<p class="dev-env-hint muted">${escapeHtml(pkg.fetch_error)}</p>` : '');
  const installHint = !pkg.is_git_install
    ? `<p class="dev-env-hint muted">${t('devPackageNonGitUpdateHint', '非 git 安装：点「立即更新」将备份当前 ai/ 并重新克隆最新版')}</p>`
    : '';
  return rows + hint + installHint;
}

function inferForgeFromUrl(url) {
  const u = String(url || '').toLowerCase();
  if (u.includes('gitee.com')) return 'gitee';
  if (u.includes('gitlab')) return 'gitlab';
  return 'github';
}

function inferCollabForge({ fork, publish } = {}) {
  if (publish?.primary_forge) return publish.primary_forge;
  const counts = { github: 0, gitee: 0, gitlab: 0 };
  const add = (url) => {
    if (!url) return;
    const f = inferForgeFromUrl(url);
    counts[f] = (counts[f] || 0) + 1;
  };
  const forkRemotes = fork?.git_remotes || fork?.scan?.git_remotes || [];
  forkRemotes.forEach(add);
  (publish?.units || []).forEach((u) => add(u.origin_url));
  const forks = publish?.settings?.project_publish?.forks || {};
  Object.values(forks).forEach((f) => add(f?.fork_url));
  const ranked = Object.entries(counts).filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1]);
  return ranked[0]?.[0] || 'github';
}

function collabForgeLabel(forge) {
  if (forge === 'gitee') return 'Gitee';
  if (forge === 'gitlab') return 'GitLab';
  return 'GitHub';
}

function renderCollabCredentialsCard(publish, fork) {
  const forge = inferCollabForge({ fork, publish });
  collabState.primaryForge = forge;
  const auth = publish?.forge_auth?.[forge] || {};
  const statusClass = auth.valid ? 'on' : (auth.configured ? 'warn' : '');
  const statusText = auth.valid
    ? t('devPublishTokenOk', '已验证')
    : (auth.configured ? t('devPublishTokenBad', '无效') : t('devPublishTokenMissing', '未配置'));
  const userLine = auth.valid && auth.user
    ? `<span class="publish-token-user">${t('devPublishTokenBound', '已绑定')} @${escapeHtml(auth.user)}</span>`
    : '';
  const secondary = (publish?.secondary_forges || []).filter((f) => f !== forge);
  const secondaryHint = secondary.length
    ? `<p class="field-hint muted">${escapeHtml(t('devCollabSecondaryForgeHint', '仓库也使用 {forges}，当前仅需配置主平台 Token。').replace('{forges}', secondary.map(collabForgeLabel).join(' / ')))}</p>`
    : '';
  const hintKey = forge === 'gitee' ? 'devPublishTokenHintGitee' : 'devPublishTokenHintGithub';
  const hintDefault = forge === 'gitee'
    ? 'Gitee 私人令牌，需具备 Pull Request 权限。'
    : '需 classic/细粒度 PAT，含 repo 权限。';
  const hintLink = forge === 'gitee'
    ? '<a href="https://gitee.com/profile/personal_access_tokens" target="_blank" rel="noopener noreferrer">gitee.com/profile/personal_access_tokens</a>'
    : '<a href="https://github.com/settings/tokens" target="_blank" rel="noopener noreferrer">github.com/settings/tokens</a>';
  const detectHint = t('devCollabForgeAuto', '根据仓库 remote 自动识别为 {forge}').replace('{forge}', collabForgeLabel(forge));
  return `
    <div class="collab-credentials-card" data-primary-forge="${forge}">
      <div class="collab-credentials-head">
        <span class="field-label" id="collabForgeTokenLabel">${collabForgeLabel(forge)} Token</span>
        <div class="publish-token-meta">
          <span class="dev-status ${statusClass}">${statusText}</span>
          ${userLine}
        </div>
      </div>
      <input type="text" id="collabForgeToken" class="collab-forge-token" data-forge="${forge}" placeholder="${t('devCollabTokenPlaceholder', '粘贴 Token，仓库/发布/反馈共用')}" autocomplete="off" spellcheck="false">
      <div class="publish-token-actions">
        <button type="button" class="btn small ghost collab-token-verify" data-forge="${forge}">${t('devPublishVerify', '验证')}</button>
        <button type="button" class="btn small ghost collab-token-clear" data-forge="${forge}">${t('devPublishClear', '清除')}</button>
      </div>
      <p class="field-hint">${escapeHtml(detectHint)} · ${t(hintKey, hintDefault)} ${hintLink}</p>
      ${secondaryHint}
    </div>`;
}

function refreshCollabCredentials(publish, fork) {
  if (!els.collabCredentialsBox) return;
  els.collabCredentialsBox.innerHTML = renderCollabCredentialsCard(publish, fork);
}

function bindCollabCredentialsControls() {
  const wrap = els.collabCredentialsWrap;
  if (!wrap || wrap.dataset.bound === '1') return;
  wrap.dataset.bound = '1';
  wrap.addEventListener('click', async (e) => {
    const verifyBtn = e.target.closest('.collab-token-verify');
    const clearBtn = e.target.closest('.collab-token-clear');
    if (!verifyBtn && !clearBtn) return;
    const forge = (verifyBtn || clearBtn).dataset.forge || collabState.primaryForge || 'github';
    const input = document.getElementById('collabForgeToken');
    if (clearBtn) {
      if (!window.confirm(t('devPublishClearConfirm', '清除已保存的 Token？'))) return;
      try {
        await api('POST', '/api/ai/publish', { operation: 'set_forge_token', forge, token: '' });
        showToast(t('devPublishTokenCleared', 'Token 已清除'));
        await loadPublishPane();
      } catch (err) {
        showToast(err.message || t('devPublishFail', '发布失败'));
      }
      return;
    }
    const token = input?.value?.trim() || '';
    const run = async () => {
      const { data } = await api('POST', '/api/ai/publish', {
        operation: 'verify_forge',
        forge,
        token,
      });
      if (!data.valid) throw new Error(data.error_detail || data.hint || t('devPublishTokenBad', '无效'));
      if (token) {
        await api('POST', '/api/ai/publish', { operation: 'set_forge_token', forge, token });
      }
      showToast(data.user ? `${t('devPublishTokenBound', '已绑定')} @${data.user}` : t('devPublishTokenOk', '已验证'));
      await loadPublishPane();
    };
    const btn = verifyBtn;
    if (typeof UiBusy !== 'undefined') {
      await UiBusy.withButtonBusy(btn, run, { busyLabel: t('uiWorking', '处理中…') });
    } else {
      btn.disabled = true;
      try { await run(); } catch (err) { showToast(err.message); } finally { btn.disabled = false; }
    }
  });
}

function renderPublishConfigCard(status) {
  const settings = status?.settings || {};
  const proj = settings.project_publish || {};
  const mode = proj.default_mode || 'current_remote';
  const forks = proj.forks || {};
  const opFork = forks.openpilot || {};
  return `
    <div class="dev-form-stack dev-form-stack-compact">
      <label class="field">
        <span class="field-label">${t('devPublishDefaultMode', '项目仓默认')}</span>
        <select id="publishDefaultMode">
          <option value="current_remote" ${mode === 'current_remote' ? 'selected' : ''}>${t('devPublishModeCurrent', '当前 remote')}</option>
          <option value="user_fork" ${mode === 'user_fork' ? 'selected' : ''}>${t('devPublishModeFork', '我的 fork')}</option>
        </select>
      </label>
      <label class="field">
        <span class="field-label">openpilot fork</span>
        <input type="url" id="publishOpenpilotForkUrl" placeholder="https://gitee.com/user/openpilot" value="${escapeHtml(opFork.fork_url || '')}">
      </label>
      <p class="field-hint">${t('devPublishAssistantHint', 'op助手 (ai) 默认 PR 到 mouxangithub/ai；项目仓 PR 目标由 remote 或 fork 决定。')}</p>
    </div>`;
}


function renderPublishUnits(units) {
  const list = units || [];
  if (!list.length) {
    return `<p class="dev-empty">${t('devPublishNoUnits', '未检测到 git 仓库')}</p>`;
  }
  return list.map((u) => {
    const dirty = Number(u.dirty_count) || 0;
    const targetHint = u.kind === 'assistant'
      ? 'mouxangithub/ai'
      : (u.repo_slug || u.origin_url || '—');
    const modeOpts = u.kind === 'assistant'
      ? `<option value="assistant_upstream" selected>${t('devPublishModeUpstream', '上游 ai 仓')}</option>
         <option value="user_fork">${t('devPublishModeFork', '我的 fork')}</option>`
      : `<option value="current_remote">${t('devPublishModeCurrent', '当前 remote')}</option>
         <option value="user_fork">${t('devPublishModeFork', '我的 fork')}</option>`;
    return `
    <div class="publish-unit-card" data-unit-id="${escapeHtml(u.id)}">
      <div class="publish-unit-head">
        <strong class="publish-unit-title">${escapeHtml(u.display_name || u.id)}</strong>
        <span class="dev-status ${dirty ? 'on' : ''}">${dirty ? `${dirty} ${t('devPublishDirty', '处改动')}` : t('devPublishClean', '无改动')}</span>
      </div>
      <p class="publish-unit-meta">${escapeHtml(u.branch || '—')} · ${escapeHtml(targetHint)}</p>
      <div class="publish-unit-actions">
        <label class="field publish-unit-mode-field">
          <span class="field-label">${t('devPublishTarget', '发布目标')}</span>
          <select class="publish-unit-mode">${modeOpts}</select>
        </label>
        <button type="button" class="btn small primary publish-unit-btn" data-unit="${escapeHtml(u.id)}" ${dirty ? '' : 'disabled'}>${t('devPublishBtn', '发布 PR')}</button>
      </div>
    </div>`;
  }).join('');
}

async function loadPublishPane() {
  if (!els.collabCredentialsBox && !els.publishSettingsBox) return;
  try {
    const { data } = await api('GET', '/api/ai/publish');
    if (!data.ok) throw new Error(data.error || 'load failed');
    collabState.publish = data;
    refreshCollabCredentials(data, collabState.fork);
    if (els.publishSettingsBox) {
      els.publishSettingsBox.innerHTML = renderPublishConfigCard(data);
    }
    const units = data.units || [];
    if (els.publishUnitsBox) {
      els.publishUnitsBox.innerHTML = renderPublishUnits(units);
      bindPublishUnitButtons();
    }
    updateCollabStatusBar();
  } catch (e) {
    const msg = `<p class="dev-empty">${escapeHtml(e.message || t('devPublishLoadFail', '无法加载发布配置'))}</p>`;
    if (els.collabCredentialsBox) els.collabCredentialsBox.innerHTML = msg;
    if (els.publishSettingsBox) els.publishSettingsBox.innerHTML = '';
    if (els.publishUnitsBox) els.publishUnitsBox.innerHTML = '';
  }
}

function collectPublishSettingsPatch() {
  const mode = document.getElementById('publishDefaultMode')?.value || 'current_remote';
  const forkUrl = document.getElementById('publishOpenpilotForkUrl')?.value?.trim() || '';
  const patch = {
    project_publish: {
      default_mode: mode,
      forks: {},
    },
  };
  if (forkUrl) {
    const forge = forkUrl.includes('gitee.com') ? 'gitee' : 'github';
    patch.project_publish.forks.openpilot = {
      fork_url: forkUrl,
      forge,
      git_remote: 'fork',
    };
  }
  return patch;
}

async function savePublishSettings() {
  const { data } = await api('POST', '/api/ai/publish', {
    operation: 'save_settings',
    settings: collectPublishSettingsPatch(),
  });
  if (!data.ok) throw new Error(data.error || 'save failed');
  showToast(t('devPublishSaved', '发布配置已保存'));
  await loadPublishPane();
}

function bindPublishUnitButtons() {
  els.publishUnitsBox?.querySelectorAll('.publish-unit-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const unitId = btn.dataset.unit;
      const card = btn.closest('.publish-unit-card');
      const mode = card?.querySelector('.publish-unit-mode')?.value || '';
      const title = `chore(ai): update ${unitId}`;
      const run = async () => {
        const preview = await api('POST', '/api/ai/publish', {
          operation: 'publish',
          unit_id: unitId,
          target_mode: mode,
          title,
          confirm: false,
        });
        if (!preview.data?.ok && !preview.data?.needs_confirmation) {
          throw new Error(preview.data?.error || 'preview failed');
        }
        if (!window.confirm(t('publishConfirmBody', '确认发布 PR/MR？'))) return;
        const { data } = await api('POST', '/api/ai/publish', {
          operation: 'publish',
          unit_id: unitId,
          target_mode: mode,
          title,
          confirm: true,
        });
        if (data.ok && data.pull_request_url) {
          showToast(t('devPublishOk', '已创建 PR'));
          window.open(data.pull_request_url, '_blank', 'noopener');
        } else if (data.ok) {
          showToast(t('devPublishPushed', '已推送分支'));
        } else {
          throw new Error(data.error || t('devPublishFail', '发布失败'));
        }
        await loadPublishPane();
      };
      if (typeof UiBusy !== 'undefined') {
        await UiBusy.withButtonBusy(btn, run, { busyLabel: t('uiWorking', '处理中…') });
      } else {
        btn.disabled = true;
        try { await run(); } catch (e) { showToast(e.message); } finally { btn.disabled = false; }
      }
    });
  });
}

async function maybeShowPublishPrompt() {
  try {
    const { data } = await api('GET', '/api/ai/publish?view=units&dirty=1');
    const units = (data.units || []).filter((u) => u.has_changes);
    if (!units.length || !els.publishPromptModal) return;
    if (els.publishPromptUnits) {
      els.publishPromptUnits.innerHTML = renderPublishUnits(units);
      bindPublishPromptUnits(units);
    }
    els.publishPromptModal.hidden = false;
    syncBodyScrollLock();
  } catch {
    /* ignore */
  }
}

function bindPublishPromptUnits(units) {
  els.publishPromptUnits?.querySelectorAll('.publish-unit-mode').forEach((sel, i) => {
    sel.dataset.unit = units[i]?.id || '';
  });
  els.publishPromptUnits?.querySelectorAll('.publish-unit-btn').forEach((btn) => {
    btn.addEventListener('click', () => publishFromPrompt(btn.dataset.unit));
  });
}

function closePublishPrompt() {
  if (els.publishPromptModal) els.publishPromptModal.hidden = true;
  syncBodyScrollLock();
}

async function publishFromPrompt(unitId) {
  const card = els.publishPromptUnits?.querySelector(`[data-unit-id="${unitId}"]`);
  const mode = card?.querySelector('.publish-unit-mode')?.value || '';
  const title = (els.publishPromptTitleInput?.value || '').trim() || `chore(ai): update ${unitId}`;
  try {
    const { data } = await api('POST', '/api/ai/publish', {
      operation: 'publish',
      unit_id: unitId,
      target_mode: mode,
      title,
      confirm: true,
    });
    if (data.ok && data.pull_request_url) {
      showToast(t('devPublishOk', '已创建 PR'));
      window.open(data.pull_request_url, '_blank', 'noopener');
    } else if (!data.ok) {
      showToast(data.error || t('devPublishFail', '发布失败'));
      return;
    }
    closePublishPrompt();
    await loadPublishPane();
  } catch (e) {
    showToast(e.message || t('devPublishFail', '发布失败'));
  }
}

let issueTemplatesCache = [];

function renderIssueSettingsCard(status) {
  const settings = status?.settings || {};
  const unit = settings.default_unit || 'assistant';
  const tpl = settings.default_template || 'bug';
  return `
    <div class="dev-form-stack dev-form-stack-compact">
      <label class="field">
        <span class="field-label">${t('devIssueDefaultUnit', 'Issue 提交到')}</span>
        <select id="issueDefaultUnit">
          <option value="assistant" ${unit === 'assistant' ? 'selected' : ''}>${t('devUnitAssistant', 'op助手 (mouxangithub/ai)')}</option>
          <option value="openpilot" ${unit === 'openpilot' ? 'selected' : ''}>${t('devUnitOpenpilot', 'openpilot 主仓')}</option>
        </select>
      </label>
      <label class="field">
        <span class="field-label">${t('devIssueDefaultTemplate', '默认模板')}</span>
        <select id="issueDefaultTemplate">
          ${(status?.templates || []).map((x) => `<option value="${escapeHtml(x.id)}" ${x.id === tpl ? 'selected' : ''}>${escapeHtml(x.name || x.id)}</option>`).join('')}
        </select>
      </label>
      <p class="field-hint">${t('devIssueUnitHint', '选择 GitHub Issue 要开在哪个仓库；与「发布」里的发布单元对应。')}</p>
      <p class="field-hint">${t('devIssueHint', 'Bug/建议先开 Issue；已改代码请用「发布」开 PR。')}</p>
    </div>`;
}

function renderIssueForm(templates) {
  issueTemplatesCache = templates || [];
  const tplOpts = issueTemplatesCache.map((x) =>
    `<option value="${escapeHtml(x.id)}">${escapeHtml(x.name || x.id)}</option>`).join('');
  return `
    <div class="dev-form-stack">
      <label class="field">
        <span class="field-label" id="issueKindSelectLabel">${t('devIssueKind', '类型')}</span>
        <select id="issueKindSelect">
          <option value="bug">${t('devIssueKindBug', 'Bug')}</option>
          <option value="feature">${t('devIssueKindFeature', '功能建议')}</option>
          <option value="suggestion">${t('devIssueKindSuggestion', '体验反馈')}</option>
        </select>
      </label>
      <label class="field">
        <span class="field-label" id="issueTemplateSelectLabel">${t('devIssueTemplate', '模板')}</span>
        <select id="issueTemplateSelect">${tplOpts}</select>
      </label>
      <label class="field">
        <span class="field-label" id="issueTitleInputLabel">${t('devIssueTitleLabel', '标题')}</span>
        <input type="text" id="issueTitleInput" placeholder="${t('devIssueTitlePh', '简要描述问题')}">
      </label>
      <label class="field">
        <span class="field-label" id="issueSummaryInputLabel">${t('devIssueSummary', '描述')}</span>
        <textarea id="issueSummaryInput" class="issue-summary-input" rows="4" placeholder="${t('devIssueSummaryPh', '复现步骤、期望与实际行为…')}"></textarea>
      </label>
    </div>`;
}

async function loadIssuePane() {
  if (!els.issueSettingsBox) return;
  try {
    const { data } = await api('GET', '/api/ai/issues');
    if (!data.ok) throw new Error(data.error || 'load failed');
    els.issueSettingsBox.innerHTML = renderIssueSettingsCard(data);
    const tplRes = await api('GET', '/api/ai/issues?view=templates&unit_id=assistant');
    const templates = tplRes.data?.templates || data.templates || [];
    if (els.issueFormBox) {
      els.issueFormBox.innerHTML = renderIssueForm(templates);
    }
  } catch (e) {
    if (els.issueSettingsBox) {
      els.issueSettingsBox.innerHTML = `<p class="dev-empty">${escapeHtml(e.message || t('devIssueLoadFail', '无法加载 Issue 配置'))}</p>`;
    }
  }
}

async function saveIssueSettings() {
  const unit = document.getElementById('issueDefaultUnit')?.value || 'assistant';
  const template = document.getElementById('issueDefaultTemplate')?.value || 'bug';
  const { data } = await api('POST', '/api/ai/issues', {
    operation: 'save_settings',
    settings: {
      issue_publish: {
        default_unit: unit,
        default_template: template,
        dedupe_search: true,
      },
    },
  });
  if (!data.ok) throw new Error(data.error || 'save failed');
  showToast(t('devIssueSaved', 'Issue 配置已保存'));
}

async function submitIssue() {
  const kind = document.getElementById('issueKindSelect')?.value || 'bug';
  const templateId = document.getElementById('issueTemplateSelect')?.value || 'bug';
  const title = document.getElementById('issueTitleInput')?.value?.trim() || '';
  const summary = document.getElementById('issueSummaryInput')?.value?.trim() || '';
  const unit = document.getElementById('issueDefaultUnit')?.value || 'assistant';
  if (!title && !summary) {
    showToast(t('devIssueNeedContent', '请填写标题或描述'));
    return;
  }
  const preview = await api('POST', '/api/ai/issues', {
    operation: 'report',
    kind,
    unit_id: unit,
    template_id: templateId,
    title,
    summary,
    repro_steps: summary,
    confirm: false,
  });
  if (!preview.data?.ok && !preview.data?.needs_confirmation) {
    throw new Error(preview.data?.error || 'preview failed');
  }
  const similar = preview.data?.preview?.similar_issues || [];
  let msg = t('issueConfirmBody', '确认创建 Issue？');
  if (similar.length) {
    msg += `\n\n${t('devIssueSimilar', '相似 Issue')}:\n` + similar.map((i) => `#${i.number} ${i.title}`).join('\n');
  }
  if (!window.confirm(msg)) return;
  const { data } = await api('POST', '/api/ai/issues', {
    operation: 'report',
    kind,
    unit_id: unit,
    title,
    summary,
    repro_steps: summary,
    confirm: true,
  });
  if (data.ok && data.issue_url) {
    showToast(t('devIssueOk', 'Issue 已创建'));
    window.open(data.issue_url, '_blank', 'noopener');
  } else if (!data.ok) {
    throw new Error(data.error || t('devIssueFail', '创建失败'));
  }
}

function renderRagStatusCard(rag, cfg) {
  const docCount = Number(rag?.count) || 0;
  const vectorChunks = Number(rag?.vector_chunks) || 0;
  const embedded = Number(rag?.embedded_docs)
    || (rag?.documents || []).filter((d) => d.embedded).length;
  const embedOk = !!cfg?.embeddingConfigured;
  const vectorReady = embedOk && vectorChunks > 0;
  const staleEmbedded = embedded > 0 && vectorChunks === 0;
  const lines = [
    [t('devRagDocs', '文档'), `${docCount}（已向量化 ${embedded}）`],
    [t('devRagVectors', '向量块'), String(vectorChunks)],
    [t('devRagEmbedding', 'Embedding'), embedOk ? t('devRagEmbeddingOk', '已配置') : t('devRagEmbeddingMissing', '未配置')],
    [t('devRagChat', '向量检索'), vectorReady ? t('devRagChatOn', '已启用（工具检索）') : t('devRagChatOff', '未启用')],
  ];
  const rows = lines.map(([label, val]) => `
    <div class="dev-kv">
      <span class="dev-kv-label">${escapeHtml(label)}</span>
      <span class="dev-kv-value">${escapeHtml(String(val))}</span>
    </div>`).join('');
  let hint;
  if (staleEmbedded) {
    hint = `<p class="dev-env-hint muted">${escapeHtml(t('devRagStaleHint', '文档标记与向量索引不一致，请点击「重建向量索引」。'))}</p>`;
  } else if (vectorReady) {
    hint = `<p class="dev-env-hint muted">${escapeHtml(t('devRagChatHintOn', '模型可通过 search_knowledge_base 工具检索知识库。'))}</p>`;
  } else {
    hint = `<p class="dev-env-hint muted">${escapeHtml(t('devRagChatHintOff', '请配置 Embedding 后点击「重建向量索引」。'))}</p>`;
  }
  return rows + hint;
}

function renderForkDetectSummary(fork) {
  if (!fork || !fork.ok) {
    return `<p class="dev-empty">${escapeHtml(fork?.error || t('devForkLoadFail', '无法扫描 fork'))}</p>`;
  }
  const community = fork.community_match || {};
  const displayId = community.id || fork.fork_id || '—';
  const displayLabel = community.name || fork.fork_label || displayId;
  const modeLabel = fork.mode === 'ai_cached' ? t('devForkModeAi', 'AI 已分析') : t('devForkModeScan', '仓库扫描');
  const analysis = fork.analysis || {};
  const summaryLine = analysis.summary
    ? `<p class="dev-env-hint">${escapeHtml(analysis.summary.slice(0, 160))}${analysis.summary.length > 160 ? '…' : ''}</p>`
    : '';
  const hint = fork.hint ? `<p class="dev-env-hint muted">${escapeHtml(fork.hint)}</p>` : '';
  return `
    <div class="dev-kv dev-kv-compact">
      <span class="dev-kv-label">${t('devForkSummaryId', '识别')}</span>
      <span class="dev-kv-value">${escapeHtml(displayLabel)} <span class="dev-collab-muted">(${escapeHtml(fork.confidence || '—')})</span></span>
    </div>
    <div class="dev-kv dev-kv-compact">
      <span class="dev-kv-label">${t('devForkSummaryRepo', '仓库')}</span>
      <span class="dev-kv-value"><code>${escapeHtml(displayId)}</code> · ${escapeHtml(fork.git_branch || '—')}</span>
    </div>
    <div class="dev-kv dev-kv-compact">
      <span class="dev-kv-label">${t('devForkSummaryMode', '模式')}</span>
      <span class="dev-kv-value">${escapeHtml(modeLabel)}</span>
    </div>
    ${summaryLine}${hint}`;
}

function renderForkDetectDetails(fork) {
  if (!fork || !fork.ok) return '';
  const scan = fork.scan || {};
  const remotes = [...new Set(fork.git_remotes || scan.git_remotes || [])].join('\n') || '—';
  const lines = [
    [t('devForkDetailBranch', '分支'), fork.git_branch || '—'],
    ['Remote', remotes],
    [t('devForkDetailDirs', '特征目录'), (scan.distinctive_dirs || []).join(', ') || '—'],
    [t('devForkDetailParams', 'Param 前缀'), Object.keys(scan.param_prefixes || {}).join(', ') || '—'],
  ];
  const rows = lines.map(([label, val]) => `
    <div class="dev-kv">
      <span class="dev-kv-label">${escapeHtml(label)}</span>
      <span class="dev-kv-value">${escapeHtml(String(val))}</span>
    </div>`).join('');
  const reasons = (fork.reasons || []).slice(0, 4).join(' · ');
  const reasonHint = reasons ? `<p class="dev-env-hint muted">${escapeHtml(reasons)}</p>` : '';
  return rows + reasonHint;
}

function renderForkDetectCard(fork) {
  return renderForkDetectSummary(fork);
}

const forkRunUi = {
  phases: new Map(),
  reasoningByPhase: {},
  contentByPhase: {},
  activePhase: null,
};

function resetForkRunUi() {
  forkRunUi.phases.clear();
  forkRunUi.reasoningByPhase = {};
  forkRunUi.contentByPhase = {};
  forkRunUi.activePhase = null;
  if (els.forkProgressPhases) els.forkProgressPhases.innerHTML = '';
  if (els.forkProgressLog) {
    els.forkProgressLog.textContent = '';
    els.forkProgressLog.hidden = true;
  }
  if (els.forkProgressThinking) els.forkProgressThinking.textContent = '';
  if (els.forkProgressContent) els.forkProgressContent.textContent = '';
  if (els.forkProgressThinkingWrap) els.forkProgressThinkingWrap.hidden = true;
  if (els.forkProgressContentWrap) els.forkProgressContentWrap.hidden = true;
}

function setForkRunBusy(busy, statusText) {
  if (!els.forkProgressBox) return;
  els.forkProgressBox.classList.toggle('hidden', false);
  els.forkProgressBox.classList.toggle('is-idle', !busy);
  els.forkProgressBox.setAttribute('aria-busy', busy ? 'true' : 'false');
  if (els.forkProgressStatus && statusText) {
    els.forkProgressStatus.textContent = statusText;
  }
}

function forkPhaseIcon(status) {
  if (status === 'done') return '✓';
  if (status === 'error') return '✕';
  if (status === 'active') return '…';
  return '○';
}

function renderForkRunPhases() {
  if (!els.forkProgressPhases) return;
  const order = ['scan', 'cache', 'read_files', 'llm_analyze', 'parse', 'save_analysis', 'llm_draft', 'save_drafts'];
  const items = [...forkRunUi.phases.values()].sort((a, b) => {
    const ai = order.indexOf(a.id);
    const bi = order.indexOf(b.id);
    return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi);
  });
  els.forkProgressPhases.innerHTML = items.map((p) => {
    const cls = p.status === 'active' ? 'is-active' : (p.status === 'error' ? 'is-error' : (p.status === 'done' ? 'is-done' : ''));
    const msg = p.message ? ` — ${escapeHtml(p.message)}` : '';
    return `<li class="${cls}"><span class="fork-phase-icon">${forkPhaseIcon(p.status)}</span><span>${escapeHtml(p.label || p.id)}${msg}</span></li>`;
  }).join('');
}

function appendForkRunLog(message) {
  if (!els.forkProgressLog || !message) return;
  els.forkProgressLog.hidden = false;
  const line = document.createElement('div');
  line.textContent = message;
  els.forkProgressLog.appendChild(line);
  els.forkProgressLog.scrollTop = els.forkProgressLog.scrollHeight;
}

function updateForkStreamPanels() {
  const reasoning = Object.values(forkRunUi.reasoningByPhase).join('');
  const content = Object.values(forkRunUi.contentByPhase).join('');
  if (els.forkProgressThinkingWrap && els.forkProgressThinking) {
    const has = Boolean(reasoning.trim());
    els.forkProgressThinkingWrap.hidden = !has;
    if (has) els.forkProgressThinking.textContent = reasoning;
  }
  if (els.forkProgressContentWrap && els.forkProgressContent) {
    const has = Boolean(content.trim());
    els.forkProgressContentWrap.hidden = !has;
    if (has) els.forkProgressContent.textContent = content;
  }
}

function handleForkRunEvent(event) {
  if (!event || !event.type) return;
  if (event.type === 'phase') {
    forkRunUi.phases.set(event.id, {
      id: event.id,
      label: event.label || event.id,
      status: event.status,
      message: event.message || '',
    });
    if (event.status === 'active') {
      forkRunUi.activePhase = event.id;
      forkRunUi.reasoningByPhase[event.id] = forkRunUi.reasoningByPhase[event.id] || '';
      forkRunUi.contentByPhase[event.id] = forkRunUi.contentByPhase[event.id] || '';
      setForkRunBusy(true, event.label || t('devForkRunning', 'AI 分析进行中…'));
    }
    if (event.message) appendForkRunLog(`${event.label || event.id}: ${event.message}`);
    renderForkRunPhases();
    return;
  }
  if (event.type === 'reasoning' && event.delta) {
    const phase = event.phase || forkRunUi.activePhase || 'llm';
    forkRunUi.reasoningByPhase[phase] = (forkRunUi.reasoningByPhase[phase] || '') + event.delta;
    updateForkStreamPanels();
    return;
  }
  if (event.type === 'content' && event.delta) {
    const phase = event.phase || forkRunUi.activePhase || 'llm';
    forkRunUi.contentByPhase[phase] = (forkRunUi.contentByPhase[phase] || '') + event.delta;
    updateForkStreamPanels();
    return;
  }
  if (event.type === 'log' && event.message) {
    appendForkRunLog(event.message);
    return;
  }
  if (event.type === 'error') {
    appendForkRunLog(event.error || t('devForkAnalyzeFail', 'AI 分析失败'));
    setForkRunBusy(false, event.error || t('devForkAnalyzeFail', 'AI 分析失败'));
  }
}

async function postSseStream(url, body, onEvent) {
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let errText = res.statusText;
    try {
      const j = await res.json();
      errText = j.error || errText;
    } catch (_) {
      try { errText = await res.text(); } catch (__) { /* ignore */ }
    }
    throw new Error(errText || `HTTP ${res.status}`);
  }
  if (!res.body) throw new Error('No response body');
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split('\n\n');
    buf = parts.pop() || '';
    for (const part of parts) {
      const line = part.split('\n').find((l) => l.startsWith('data: '));
      if (!line) continue;
      try {
        onEvent(JSON.parse(line.slice(6)));
      } catch (_) { /* ignore malformed chunk */ }
    }
  }
}

async function refreshForkDetectCard() {
  if (els.forkDetectBox) {
    els.forkDetectBox.innerHTML = `
      <div class="dev-skeleton dev-skeleton-line"></div>
      <div class="dev-skeleton dev-skeleton-line short"></div>`;
  }
  const { data: fork } = await api('GET', '/api/ai/fork/detect');
  collabState.fork = fork;
  if (els.forkDetectBox) els.forkDetectBox.innerHTML = renderForkDetectSummary(fork);
  if (els.forkDetailsBox) els.forkDetailsBox.innerHTML = renderForkDetectDetails(fork);
  const forkDetailsWrap = $('#forkDetailsWrap');
  if (forkDetailsWrap) forkDetailsWrap.classList.toggle('hidden', !fork?.ok);
  refreshCollabCredentials(collabState.publish, fork);
  updateCollabStatusBar();
  return fork;
}

async function runForkAnalyzePipeline({ force = false } = {}) {
  if (!configured) {
    showToast(t('devForkNeedConfig', '请先在设置中配置模型 API'));
    openSettings('model');
    return null;
  }
  resetForkRunUi();
  setForkRunBusy(true, t('devForkRunning', 'AI 分析进行中…'));
  if (typeof UiBusy !== 'undefined') {
    UiBusy.setButtonBusy(els.devForkSyncBtn, true, { busyLabel: t('uiWorking', '处理中…') });
    UiBusy.setButtonBusy(els.devForkRefreshBtn, true);
  } else {
    els.devForkSyncBtn.disabled = true;
    els.devForkRefreshBtn.disabled = true;
  }
  let finalResult = null;
  try {
    await postSseStream('/api/ai/fork/run', { confirm: true, force }, (event) => {
      handleForkRunEvent(event);
      if (event.type === 'done') finalResult = event;
    });
    if (finalResult?.ok) {
      setForkRunBusy(false, t('devForkSyncOk', '分析与草稿已生成'));
      showToast(t('devForkSyncOk', '分析与草稿已生成'));
      await refreshForkDetectCard();
    } else if (finalResult) {
      const err = finalResult.error || t('devForkSyncFail', '草稿生成失败');
      setForkRunBusy(false, err);
      showToast(err);
    } else {
      setForkRunBusy(false, t('devForkAnalyzeFail', 'AI 分析失败'));
      showToast(t('devForkAnalyzeFail', 'AI 分析失败'));
    }
    return finalResult;
  } catch (e) {
    const err = e?.message || t('devForkAnalyzeFail', 'AI 分析失败');
    handleForkRunEvent({ type: 'error', error: err });
    showToast(err);
    return null;
  } finally {
    if (typeof UiBusy !== 'undefined') {
      UiBusy.setButtonBusy(els.devForkSyncBtn, false);
      UiBusy.setButtonBusy(els.devForkRefreshBtn, false);
    } else {
      els.devForkSyncBtn.disabled = false;
      els.devForkRefreshBtn.disabled = false;
    }
  }
}

async function refreshOnboardingModels() {
  const provider = els.onboardingProvider?.value || 'opencode-zen';
  const apiKey = els.onboardingApiKey?.value?.trim() || '';
  const catalog = catalogModelsForProvider(provider);
  if (!apiKey) {
    onboardingModelCombo?.setOptions(catalog);
    refreshOnboardingEmbeddingModels();
    return;
  }
  onboardingModelCombo?.setLoading(true);
  const { data } = await api('POST', '/api/ai/models', {
    provider,
    apiKey,
    baseUrl: '',
    model: onboardingModelCombo?.getValue() || '',
  });
  let list = catalog;
  if (data.ok && Array.isArray(data.models) && data.models.length) {
    list = data.models;
    onboardingFetchedModels = list.map((m) => (typeof m === 'string' ? m : m.id)).filter(Boolean);
    LocalPrefs.setModelsCache(provider, list);
  }
  onboardingModelCombo?.setLoading(false);
  onboardingModelCombo?.setOptions(list);
  refreshOnboardingEmbeddingModels();
}

function renderOnboardingEmbeddingProviders() {
  if (!els.onboardingEmbeddingProvider) return;
  if (!embeddingProviders.length) {
    embeddingProviders = FALLBACK_EMBEDDING_PROVIDERS.slice();
  }
  const html = embeddingProviders.map((p) => `<option value="${p}">${embeddingProviderDisplayName(p)}</option>`).join('');
  els.onboardingEmbeddingProvider.innerHTML = html;
}

function getOnboardingEmbeddingProvider() {
  const separate = !!els.onboardingEmbeddingSeparateToggle?.checked;
  if (separate) {
    return els.onboardingEmbeddingProvider?.value || 'siliconflow';
  }
  return els.onboardingProvider?.value || 'opencode-zen';
}

function refreshOnboardingEmbeddingModels(preferredModel = '') {
  const separate = !!els.onboardingEmbeddingSeparateToggle?.checked;
  const provider = getOnboardingEmbeddingProvider();
  const list = embeddingCatalogForProvider(provider, !separate);
  onboardingEmbeddingModelCombo?.setOptions(list);
  const hub = effectiveModelHub(savedConfig);
  const hubModel = hub?.embeddingPrimary?.model || '';
  const current = (preferredModel || onboardingEmbeddingModelCombo?.getValue() || hubModel || savedConfig?.embeddingModel || '').trim();
  if (current) {
    onboardingEmbeddingModelCombo?.setValue(current, { silent: true });
    return;
  }
  const def = embeddingDefaults[provider] || '';
  if (def) {
    onboardingEmbeddingModelCombo?.setValue(def, { silent: true });
  } else if (list.length) {
    onboardingEmbeddingModelCombo?.setValue(list[0].id || list[0], { silent: true });
  }
}

function onOnboardingEmbeddingSeparateToggle() {
  const separate = !!els.onboardingEmbeddingSeparateToggle?.checked;
  els.onboardingEmbeddingSeparateFields?.classList.toggle('hidden', !separate);
  refreshOnboardingEmbeddingModels();
}

function onboardingHasStoredApiKey() {
  return !!(savedConfig?.configured && savedConfig?.apiKey?.trim());
}

function syncOnboardingFromSavedConfig() {
  const c = savedConfig || {};
  const hub = effectiveModelHub(c);
  const acc = hub?.accounts?.[0];
  const primary = hub?.primary;
  const provider = acc?.provider
    || ((c.provider && providers.includes(c.provider)) ? c.provider : null)
    || els.providerSelect?.value
    || providers[0]
    || 'opencode-zen';
  if (els.onboardingProvider && providers.includes(provider)) {
    els.onboardingProvider.value = provider;
  }
  if (els.onboardingApiKey) {
    const key = acc?.apiKey || c.apiKey || '';
    els.onboardingApiKey.value = key || '';
    els.onboardingApiKey.placeholder = t('apiKey', 'API Key');
  }
  const model = primary?.model || c.model || defaults[provider] || modelCatalog[provider]?.[0] || '';
  if (model) onboardingModelCombo?.setValue(model, { silent: true });
  if (acc?.models?.length) onboardingFetchedModels = acc.models.slice();
  renderOnboardingEmbeddingProviders();
  let separate = false;
  let embedModel = c.embeddingModel || '';
  const ep = hub?.embeddingPrimary;
  const chatAccId = primary?.accountId || hub?.accounts?.[0]?.id;
  if (ep?.accountId && ep?.model) {
    embedModel = ep.model;
    separate = ep.accountId !== chatAccId;
    if (separate) {
      const embAcc = (hub.accounts || []).find((a) => a.id === ep.accountId);
      if (embAcc?.provider && els.onboardingEmbeddingProvider && embeddingProviders.includes(embAcc.provider)) {
        els.onboardingEmbeddingProvider.value = embAcc.provider;
      } else if (c.embeddingProvider && els.onboardingEmbeddingProvider && embeddingProviders.includes(c.embeddingProvider)) {
        els.onboardingEmbeddingProvider.value = c.embeddingProvider;
      }
      if (els.onboardingEmbeddingApiKey) {
        els.onboardingEmbeddingApiKey.value = (hub.accounts || []).find((a) => a.id === ep.accountId)?.apiKey || c.embeddingApiKey || '';
        els.onboardingEmbeddingApiKey.placeholder = t('embeddingApiKeyPlaceholder', '留空则使用上方聊天 Key');
      }
    }
  } else if (c.embeddingMode === 'separate') {
    separate = true;
    if (c.embeddingProvider && els.onboardingEmbeddingProvider && embeddingProviders.includes(c.embeddingProvider)) {
      els.onboardingEmbeddingProvider.value = c.embeddingProvider;
    }
    if (els.onboardingEmbeddingApiKey) {
      els.onboardingEmbeddingApiKey.value = c.embeddingApiKey || '';
      els.onboardingEmbeddingApiKey.placeholder = t('embeddingApiKeyPlaceholder', '留空则使用上方聊天 Key');
    }
  }
  if (els.onboardingEmbeddingSeparateToggle) {
    els.onboardingEmbeddingSeparateToggle.checked = separate;
  }
  onOnboardingEmbeddingSeparateToggle();
  refreshOnboardingEmbeddingModels(embedModel);
}

function maybeDismissOnboardingWizard() {
  if (configured && els.onboardingModal && !els.onboardingModal.hidden) {
    closeOnboardingWizard();
  }
}

function openOnboardingWizard() {
  if (!els.onboardingModal || configured) return;
  const sel = els.onboardingProvider;
  if (sel && providers.length) {
    sel.innerHTML = providers.map((p) => `<option value="${escapeHtml(p)}">${escapeHtml(providerLabels[p] || p)}</option>`).join('');
  }
  syncOnboardingFromSavedConfig();
  refreshOnboardingModels().catch(() => {
    refreshOnboardingEmbeddingModels(savedConfig?.embeddingModel || '');
  });
  if (els.onboardingResult) {
    els.onboardingResult.textContent = '';
    els.onboardingResult.className = 'field-hint';
  }
  els.onboardingModal.hidden = false;
}

function closeOnboardingWizard() {
  if (els.onboardingModal) els.onboardingModal.hidden = true;
}

async function testOnboardingWizard() {
  const provider = els.onboardingProvider?.value || 'opencode-zen';
  const apiKey = els.onboardingApiKey?.value?.trim() || '';
  const model = onboardingModelCombo?.getValue()?.trim() || '';
  const run = async () => {
    if (els.onboardingResult) els.onboardingResult.textContent = t('testing', '测试中…');
    const { data } = await api('POST', '/api/ai/test_connection', { provider, apiKey, model });
    if (els.onboardingResult) {
      els.onboardingResult.textContent = data.ok
        ? t('connectionOk', '连接成功')
        : (data.error || t('connectionFail', '连接失败'));
      els.onboardingResult.className = `connection-result ${data.ok ? 'success' : 'error'}`;
    }
  };
  if (typeof UiBusy !== 'undefined') {
    await UiBusy.withButtonBusy(els.onboardingTestBtn, run, { busyLabel: t('testing', '测试中…') });
  } else {
    await run();
  }
}

async function restoreOnboardingBackup() {
  const file = els.onboardingBackupFile?.files?.[0];
  if (!file) {
    if (els.onboardingRestoreStatus) els.onboardingRestoreStatus.textContent = t('platformBackupPickFile', '请选择 .opbak 文件');
    return;
  }
  const run = async () => {
    if (els.onboardingRestoreStatus) els.onboardingRestoreStatus.textContent = t('uiWorking', '处理中…');
    const restore = typeof PlatformPanel !== 'undefined' && PlatformPanel.restoreFromFile
      ? PlatformPanel.restoreFromFile.bind(PlatformPanel)
      : null;
    if (!restore) {
      if (els.onboardingRestoreStatus) els.onboardingRestoreStatus.textContent = t('saveFailed', '保存失败');
      return;
    }
    const { data } = await restore(file, { mode: 'merge', confirm: true });
    if (!data?.ok) {
      if (els.onboardingRestoreStatus) els.onboardingRestoreStatus.textContent = data?.error || t('saveFailed', '保存失败');
      return;
    }
    await api('POST', '/api/ai/onboarding/complete', {}).catch(() => ({}));
    configured = true;
    closeOnboardingWizard();
    showToast(t('platformBackupRestored', '恢复完成'), 'success');
    await loadBootstrap();
  };
  if (typeof UiBusy !== 'undefined') {
    await UiBusy.withButtonBusy(els.onboardingRestoreBtn, run, { busyLabel: t('uiWorking', '处理中…') });
  } else {
    await run();
  }
}

async function saveOnboardingWizard() {
  const provider = els.onboardingProvider?.value || 'opencode-zen';
  const apiKey = els.onboardingApiKey?.value?.trim() || '';
  const model = onboardingModelCombo?.getValue()?.trim() || '';
  if (!model) {
    if (els.onboardingResult) {
      els.onboardingResult.textContent = t('onboardingMissingModel', '请选择聊天模型');
      els.onboardingResult.className = 'connection-result warning';
    }
    return;
  }
  if (!apiKey && !onboardingHasStoredApiKey()) {
    if (els.onboardingResult) {
      els.onboardingResult.textContent = t('onboardingMissing', '请填写 API Key 和模型');
      els.onboardingResult.className = 'connection-result warning';
    }
    return;
  }
  const run = async () => {
    const embeddingSeparate = !!els.onboardingEmbeddingSeparateToggle?.checked;
    const embeddingModel = onboardingEmbeddingModelCombo?.getValue()?.trim() || '';
    const embeddingProvider = els.onboardingEmbeddingProvider?.value || 'siliconflow';
    const embeddingApiKey = els.onboardingEmbeddingApiKey?.value?.trim() || '';
    const buildHub = typeof ModelHub !== 'undefined'
      ? (ModelHub.buildOnboardingHub || ModelHub.buildSingleProviderHub)
      : null;
    const modelHub = buildHub
      ? buildHub({
        provider,
        apiKey,
        model,
        models: onboardingFetchedModels,
        embeddingSeparate,
        embeddingProvider,
        embeddingApiKey,
        embeddingModel,
        embeddingDefaults,
      })
      : undefined;
    const payload = {
      provider,
      apiKey,
      model,
      modelHub,
    };
    const { data } = await api('POST', '/api/ai/config', payload);
    if (!data.ok) {
      if (els.onboardingResult) {
        els.onboardingResult.textContent = data.error || t('saveFailed', '保存失败');
        els.onboardingResult.className = 'connection-result error';
      }
      return;
    }
    const goals = Array.from(document.querySelectorAll('input[name="onboardingGoal"]:checked')).map((el) => el.value);
    const car = els.onboardingCar?.value?.trim();
    const brand = els.onboardingBrand?.value?.trim();
    const vehicleProfile = {};
    if (car) vehicleProfile.car = car;
    if (brand) vehicleProfile.brand = brand;
    if (vehicleProfile.car || vehicleProfile.brand || goals.length) {
      await api('POST', '/api/ai/onboarding/profile', {
        vehicle_profile: vehicleProfile,
        goals,
      }).catch(() => ({}));
    }
    await api('POST', '/api/ai/onboarding/complete', {});
    configured = !!data.configured;
    closeOnboardingWizard();
    showToast(t('onboardingDone', '配置已保存，可以开始对话'));
    await loadConfig();
    refreshEmbeddingRouteSummary();
    const hasEmbedding = !!(modelHub?.embeddingPrimary?.model || data.embeddingConfigured);
    if (hasEmbedding) {
      openOnboardingKnowledgeSetup();
    }
  };
  if (typeof UiBusy !== 'undefined') {
    await UiBusy.withButtonBusy(els.onboardingSaveBtn, run, { busyLabel: t('uiSaving', '保存中…') });
  } else {
    await run();
  }
}

function formatDevCacheBytes(n) {
  const bytes = Number(n) || 0;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function getDevCacheFilterParams() {
  return {
    days: Number(els.devCacheDays?.value || 3),
    mode: els.devCacheMode?.value || 'within',
  };
}

function devCacheFilterHintText() {
  const modeLabel = els.devCacheMode?.selectedOptions?.[0]?.textContent || '';
  const daysLabel = els.devCacheDays?.selectedOptions?.[0]?.textContent || '';
  return t(
    'devCacheFilterHint',
    '下方列表按「{mode} · {days}」筛选显示；可逐项清理或一键清理全部。'
  ).replace('{mode}', modeLabel).replace('{days}', daysLabel);
}

function updateDevCacheFilterHint() {
  const el = document.getElementById('devCacheFilterHint');
  if (el) el.textContent = devCacheFilterHintText();
}

function renderDevCacheStatus(data) {
  if (!data?.ok) {
    return `<p class="dev-empty">${escapeHtml(data?.error || t('devCacheLoadFail', '无法加载缓存信息'))}</p>`;
  }
  const groups = data.groups || [];
  if (!groups.length) {
    return `<p class="dev-empty">${t('devCacheEmpty', '暂无本地缓存')}</p>`;
  }
  return `<ul class="dev-cache-list">${groups.map((g) => {
    const disabled = !(g.files > 0);
    return `
    <li class="dev-cache-item${disabled ? ' is-empty' : ''}" data-group-id="${escapeHtml(g.id)}">
      <div class="dev-cache-item-main">
        <span class="dev-cache-label">${escapeHtml(g.label || g.id)}</span>
        <span class="dev-cache-meta">${g.files || 0} ${t('devCacheFiles', '个文件')} · ${formatDevCacheBytes(g.bytes)}</span>
      </div>
      <button type="button" class="btn small ghost danger dev-cache-clear-one" data-group-id="${escapeHtml(g.id)}" data-group-label="${escapeHtml(g.label || g.id)}" ${disabled ? 'disabled' : ''}>${escapeHtml(t('devCacheClearOne', '清理'))}</button>
    </li>`;
  }).join('')}</ul>`;
}

async function loadDevCacheStatus() {
  if (!els.devCacheStatusBox) return;
  updateDevCacheFilterHint();
  const { days, mode } = getDevCacheFilterParams();
  const qs = `?days=${encodeURIComponent(days)}&mode=${encodeURIComponent(mode)}`;
  try {
    const { status, data } = await api('GET', `/api/ai/dev-cache${qs}`);
    if (status === 404 || (data?.error && String(data.error).includes('404'))) {
      els.devCacheStatusBox.innerHTML = `<p class="dev-empty">${escapeHtml(t('devCacheApiMissing', '缓存 API 未就绪，请重启 op助手 服务后刷新。'))}</p>`;
      if (els.devCacheTotalBadge) els.devCacheTotalBadge.textContent = '—';
      return;
    }
    if (!data?.ok) throw new Error(data?.error || t('devCacheLoadFail', '无法加载缓存信息'));
    els.devCacheStatusBox.innerHTML = renderDevCacheStatus(data);
    if (els.devCacheTotalBadge) {
      const total = Number(data.total_bytes) || 0;
      els.devCacheTotalBadge.textContent = total > 0 ? formatDevCacheBytes(total) : '—';
      els.devCacheTotalBadge.title = total > 0
        ? `${data.total_files || 0} ${t('devCacheFiles', '个文件')}`
        : '';
    }
  } catch (e) {
    els.devCacheStatusBox.innerHTML = `<p class="dev-empty">${escapeHtml(e.message || t('devCacheLoadFail', '无法加载缓存信息'))}</p>`;
    if (els.devCacheTotalBadge) els.devCacheTotalBadge.textContent = '—';
  }
}

function bindDevCacheControls() {
  if (els.devCacheDays && els.devCacheDays.dataset.bound !== '1') {
    els.devCacheDays.dataset.bound = '1';
    els.devCacheDays.addEventListener('change', () => loadDevCacheStatus().catch(() => {}));
  }
  if (els.devCacheMode && els.devCacheMode.dataset.bound !== '1') {
    els.devCacheMode.dataset.bound = '1';
    els.devCacheMode.addEventListener('change', () => loadDevCacheStatus().catch(() => {}));
  }
  if (els.devCacheStatusBox && els.devCacheStatusBox.dataset.bound !== '1') {
    els.devCacheStatusBox.dataset.bound = '1';
    els.devCacheStatusBox.addEventListener('click', (e) => {
      const btn = e.target.closest('.dev-cache-clear-one');
      if (!btn || btn.disabled) return;
      clearDevCacheGroup(btn.dataset.groupId, btn.dataset.groupLabel, btn);
    });
  }
  if (!els.devCacheClearBtn || els.devCacheClearBtn.dataset.bound === '1') return;
  els.devCacheClearBtn.dataset.bound = '1';
  els.devCacheClearBtn.addEventListener('click', () => clearDevCacheAll());
}

async function clearDevCacheGroup(groupId, groupLabel, triggerBtn) {
  if (!groupId) return;
  const { days, mode } = getDevCacheFilterParams();
  const modeLabel = els.devCacheMode?.selectedOptions?.[0]?.textContent || mode;
  const daysLabel = els.devCacheDays?.selectedOptions?.[0]?.textContent || `${days}`;
  const body = t(
    'devCacheConfirmGroupBody',
    '将按「{mode} · {days}」清理「{group}」。已安装的 SecOC 密钥不会删除。'
  ).replace('{mode}', modeLabel).replace('{days}', daysLabel).replace('{group}', groupLabel || groupId);
  if (!window.confirm(`${t('devCacheConfirmGroupTitle', '清理此项缓存？')}\n\n${body}`)) return;
  const run = async () => {
    const { data } = await api('POST', '/api/ai/dev-cache', { days, mode, groups: [groupId] });
    if (!data.ok) throw new Error(data.error || t('devCacheClearFail', '清理失败'));
    const freed = formatDevCacheBytes(data.freed_bytes);
    const count = data.deleted_files || 0;
    showToast(t('devCacheCleared', '已清理 {count} 个文件（{size}）')
      .replace('{count}', String(count))
      .replace('{size}', freed));
    await loadDevCacheStatus();
  };
  if (typeof UiBusy !== 'undefined' && triggerBtn) {
    await UiBusy.withButtonBusy(triggerBtn, run, { busyLabel: t('uiWorking', '处理中…') });
  } else {
    try { await run(); } catch (e) { showToast(e.message); }
  }
}

async function clearDevCacheAll() {
  const { days, mode } = getDevCacheFilterParams();
  const modeLabel = els.devCacheMode?.selectedOptions?.[0]?.textContent || mode;
  const daysLabel = els.devCacheDays?.selectedOptions?.[0]?.textContent || `${days}`;
  const body = t(
    'devCacheConfirmBody',
    '将按「{mode} · {days}」清理路线回放、TSK 提取等缓存。已安装的 SecOC 密钥不会删除。'
  ).replace('{mode}', modeLabel).replace('{days}', daysLabel);
  if (!window.confirm(`${t('devCacheConfirmTitle', '清理本地缓存？')}\n\n${body}`)) return;
  const run = async () => {
    const { data } = await api('POST', '/api/ai/dev-cache', { days, mode });
    if (!data.ok) throw new Error(data.error || t('devCacheClearFail', '清理失败'));
    const freed = formatDevCacheBytes(data.freed_bytes);
    const count = data.deleted_files || 0;
    showToast(t('devCacheCleared', '已清理 {count} 个文件（{size}）')
      .replace('{count}', String(count))
      .replace('{size}', freed));
    await loadDevCacheStatus();
  };
  if (typeof UiBusy !== 'undefined') {
    await UiBusy.withButtonBusy(els.devCacheClearBtn, run, { busyLabel: t('uiWorking', '处理中…') });
  } else {
    els.devCacheClearBtn.disabled = true;
    try { await run(); } catch (e) { showToast(e.message); } finally { els.devCacheClearBtn.disabled = false; }
  }
}

function setDevPaneLoading(loading) {
  els.devRefreshBtn?.classList.toggle('is-loading', loading);
  if (loading && els.hostEnvBox) {
    els.hostEnvBox.innerHTML = `
      <div class="dev-skeleton dev-skeleton-block"></div>
      <div class="dev-skeleton dev-skeleton-line"></div>
      <div class="dev-skeleton dev-skeleton-line short"></div>`;
  }
}

async function loadDevPane() {
  if (!els.hostEnvBox) return;
  setDevPaneLoading(true);
  try {
    const [{ data: boot }, { data: assets }, { data: pcs }, { data: passport }, { data: pkg }, { data: fork }] = await Promise.all([
      api('GET', '/api/ai/bootstrap').catch(() => ({ data: {} })),
      api('GET', '/api/ai/dev-assets').catch(() => ({ data: {} })),
      api('GET', '/api/ai/pc-sessions').catch(() => ({ data: {} })),
      api('GET', '/api/ai/tune_passport?limit=15').catch(() => ({ data: {} })),
      api('GET', '/api/ai/package/version?fetch=1').catch(() => ({ data: {} })),
      api('GET', '/api/ai/fork/detect').catch(() => ({ data: {} })),
    ]);
    const env = boot.hostEnvironment || hostEnvironment;
    if (env) {
      hostEnvironment = env;
      els.hostEnvBox.innerHTML = renderHostEnvCard(env);
    } else {
      els.hostEnvBox.innerHTML = `<p class="dev-empty">${t('devEnvLoadFail', '无法加载环境信息')}</p>`;
    }

    if (els.packageVersionBox) {
      els.packageVersionBox.innerHTML = renderPackageVersionCard(pkg);
    }
    collabState.pkg = pkg;

    if (els.forkDetectBox) {
      els.forkDetectBox.innerHTML = renderForkDetectSummary(fork);
    }
    if (els.forkDetailsBox) {
      els.forkDetailsBox.innerHTML = renderForkDetectDetails(fork);
    }
    collabState.fork = fork;
    const forkDetailsWrap = $('#forkDetailsWrap');
    if (forkDetailsWrap) forkDetailsWrap.classList.toggle('hidden', !fork?.ok);

    await loadPublishPane();
    await loadIssuePane();
    await loadDevCacheStatus();
    updateCollabStatusBar();

    const sessions = pcs?.sessions || [];
    const rows = [...(assets?.reports || []), ...(assets?.exports || [])];

    if (els.pcSessionsList) {
      els.pcSessionsList.innerHTML = renderDevSessions(sessions);
    }
    if (els.devAssetsList) {
      els.devAssetsList.innerHTML = renderDevAssets(rows);
    }
    const sessCount = $('#pcSessionsCount');
    if (sessCount) sessCount.textContent = String(sessions.length);
    const assetCount = $('#devAssetsCount');
    if (assetCount) assetCount.textContent = String(rows.length);

    const entries = passport?.entries || [];
    if (els.tunePassportList) {
      els.tunePassportList.innerHTML = entries.length
        ? entries.map((e) => {
            const when = e.at ? new Date(e.at * 1000).toLocaleString() : '';
            const params = Object.keys(e.params_changed || {}).join(', ') || '—';
            return `<li class="dev-item"><div><b>${escapeHtml(e.action || '')}</b> <span class="field-hint">${escapeHtml(when)}</span></div><div class="field-hint">${escapeHtml(params)}</div></li>`;
          }).join('')
        : `<li class="dev-empty">${t('tunePassportEmpty', '暂无调参记录')}</li>`;
    }
    const passportCount = $('#tunePassportCount');
    if (passportCount) passportCount.textContent = String(passport?.count ?? entries.length);

    updateRuntimeSummary({
      env,
      sessions,
      passport,
      assets: rows,
    });
  } catch {
    if (els.hostEnvBox) {
      els.hostEnvBox.innerHTML = `<p class="dev-empty">${t('devEnvLoadFail', '无法加载环境信息')}</p>`;
    }
  } finally {
    setDevPaneLoading(false);
  }
}

function renderDevPane() {
  loadDevPane().catch(() => {});
  if (typeof CanvasPanel !== 'undefined') {
    CanvasPanel.loadSession(SessionStore.activeId).catch(() => {});
    CanvasPanel.render();
  }
}

async function loadStatus() {
  const { data } = await api('GET', '/api/ai/status', null, { timeoutMs: 10000 });
  if (!data.ok) return;
  applyStatusFromPayload(data);
}

function startStatusPolling() {
  const tick = async () => {
    if (!isSyncWsConnected() && document.visibilityState === 'visible') {
      await loadStatus().catch(() => {});
    }
    const ms = isSyncWsConnected() ? 120000 : 15000;
    _statusPollTimer = setTimeout(tick, ms);
  };
  clearTimeout(_statusPollTimer);
  tick();
}

async function loadUsage() {
  if (!els.usageGrid && !els.embeddingUsageGrid) return;
  const { data } = await api('GET', '/api/ai/usage');
  if (!data.ok) return;
  if (data.usage) usageData = data.usage;
  if (data.embeddingUsage) {
    embeddingUsageData = data.embeddingUsage;
    refreshContextMeter();
  }
  refreshUsageForCurrentModel();
  refreshEmbeddingUsageForCurrentModel();
  if (usageDetailOpen) renderUsageDetailModal();
}

function getCurrentEmbeddingModelKey() {
  const hub = effectiveModelHub(savedConfig);
  const ep = hub?.embeddingPrimary;
  if (ep?.accountId && ep?.model) {
    const acc = (hub.accounts || []).find((a) => a.id === ep.accountId);
    const provider = acc?.provider || savedConfig?.embeddingProvider || '';
    if (provider) return `${provider}::${ep.model}`;
    return ep.model;
  }
  const provider = savedConfig?.embeddingProvider || getActiveEmbeddingProvider?.() || '';
  const model = savedConfig?.embeddingModel || getEmbeddingModelValue?.() || '';
  if (!provider || !model) return '';
  return `${provider}::${model}`;
}

function refreshEmbeddingUsageForCurrentModel() {
  if (!els.embeddingUsageGrid || !embeddingUsageData) return;
  const key = getCurrentEmbeddingModelKey();
  const bucket = (key && embeddingUsageData.by_model?.[key])
    ? embeddingUsageData.by_model[key]
    : emptyUsageBucket();
  els.embeddingUsageGrid.innerHTML = usageGridHtml(bucket, { hideCompletion: true });
  if (els.embeddingUsageHint) {
    const modelName = key ? key.split('::').slice(1).join('::') : '';
    els.embeddingUsageHint.textContent = modelName
      ? tf('usageCurrentEmbeddingModel', { model: modelName })
      : t('usagePickEmbeddingModel', '请选择 Embedding 服务商与模型');
  }
}

function fmtUsageNum(n) {
  return (Number(n) || 0).toLocaleString();
}

function fmtTokenNum(n) {
  const v = Number(n) || 0;
  if (v >= 1_000_000) {
    const m = v / 1_000_000;
    return `${m >= 10 ? m.toFixed(1) : m.toFixed(2)}M`.replace(/\.0+M$/, 'M');
  }
  if (v >= 1_000) {
    const k = v / 1_000;
    return `${k >= 100 ? k.toFixed(0) : k.toFixed(1)}K`.replace(/\.0+K$/, 'K');
  }
  return String(v);
}

function usageStatCols({ tokensAsM = true, includeCompletion = true } = {}) {
  const fmtTok = tokensAsM ? fmtTokenNum : fmtUsageNum;
  const cols = [
    { label: t('usageCalls'), render: (r) => fmtUsageNum(r.calls) },
    { label: t('usagePrompt'), render: (r) => fmtTok(r.prompt_tokens) },
  ];
  if (includeCompletion) {
    cols.push({ label: t('usageCompletion'), render: (r) => fmtTok(r.completion_tokens) });
  }
  cols.push({ label: t('usageTotal'), render: (r) => fmtTok(r.total_tokens) });
  return cols;
}

function emptyUsageBucket() {
  return { calls: 0, prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 };
}

function getCurrentModelKey() {
  const hub = effectiveModelHub(savedConfig);
  const primary = hub?.primary;
  const acc = primary?.accountId
    ? (hub.accounts || []).find((a) => a.id === primary.accountId)
    : (hub.accounts || [])[0];
  const hubModel = primary?.model || acc?.models?.[0] || '';
  if (acc?.provider && hubModel) {
    return `${acc.provider}::${hubModel}`;
  }
  const provider = els.providerSelect?.value?.trim();
  const model = getMainModelValue();
  if (!provider || !model) return '';
  return `${provider}::${model}`;
}

function usageGridHtml(bucket, { hideCompletion = false } = {}) {
  const u = bucket || emptyUsageBucket();
  const completionCell = hideCompletion ? '' : `
    <div class="usage-cell"><span>${t('usageCompletion')}</span><b>${fmtTokenNum(u.completion_tokens)}</b></div>`;
  return `
    <div class="usage-cell"><span>${t('usageCalls')}</span><b>${fmtUsageNum(u.calls)}</b></div>
    <div class="usage-cell"><span>${t('usagePrompt')}</span><b>${fmtTokenNum(u.prompt_tokens)}</b></div>${completionCell}
    <div class="usage-cell"><span>${t('usageTotal')}</span><b>${fmtTokenNum(u.total_tokens)}</b></div>
  `;
}

function refreshUsageForCurrentModel() {
  if (!els.usageGrid || !usageData) return;
  const key = getCurrentModelKey();
  const bucket = (key && usageData.by_model?.[key]) ? usageData.by_model[key] : emptyUsageBucket();
  els.usageGrid.innerHTML = usageGridHtml(bucket);
  if (els.usageModelHint) {
    const modelName = key ? key.split('::').slice(1).join('::') : '';
    els.usageModelHint.textContent = modelName
      ? tf('usageCurrentModel', { model: modelName })
      : t('usagePickModel', '请选择服务商与模型');
  }
}

function usageProviderDisplayName(providerId) {
  if (typeof ModelHub !== 'undefined' && ModelHub.resolveProviderUsageLabel) {
    return ModelHub.resolveProviderUsageLabel(providerId);
  }
  const hub = savedConfig?.modelHub;
  const accounts = (hub?.accounts || []).filter((a) => a.provider === providerId);
  if (accounts.length === 1) {
    const acc = accounts[0];
    const label = (acc.label || '').trim();
    if (label) return label;
  }
  if (accounts.length > 1) {
    const labels = accounts.map((a) => (a.label || '').trim()).filter(Boolean);
    if (labels.length) return labels.join(' · ');
  }
  return providerDisplayName(providerId);
}

function renderUsageDetailTable(rows, columns) {
  if (!rows.length) {
    return `<p class="field-hint">${t('usageNoData', '暂无记录')}</p>`;
  }
  const head = columns.map((c) => `<th>${c.label}</th>`).join('');
  const body = rows.map((row) => {
    const cells = columns.map((c) => `<td>${c.render(row)}</td>`).join('');
    return `<tr>${cells}</tr>`;
  }).join('');
  return `<table class="usage-detail-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function syncUsageDetailTabUi() {
  const chatView = usageDetailView.chat || 'provider';
  const embView = usageDetailView.embedding || 'provider';
  const providerTable = $('#usageByProviderTable');
  const modelTable = $('#usageByModelTable');
  const embProviderTable = $('#usageEmbeddingByProviderTable');
  const embModelTable = $('#usageEmbeddingByModelTable');
  providerTable?.classList.toggle('hidden', chatView !== 'provider');
  modelTable?.classList.toggle('hidden', chatView !== 'model');
  if (providerTable) providerTable.hidden = chatView !== 'provider';
  if (modelTable) modelTable.hidden = chatView !== 'model';
  embProviderTable?.classList.toggle('hidden', embView !== 'provider');
  embModelTable?.classList.toggle('hidden', embView !== 'model');
  if (embProviderTable) embProviderTable.hidden = embView !== 'provider';
  if (embModelTable) embModelTable.hidden = embView !== 'model';
  els.usageDetailModal?.querySelectorAll('.usage-detail-seg-btn').forEach((btn) => {
    const section = btn.dataset.section;
    const view = btn.dataset.view;
    const active = (section === 'chat' && view === chatView) || (section === 'embedding' && view === embView);
    btn.classList.toggle('is-active', active);
    btn.setAttribute('aria-selected', active ? 'true' : 'false');
  });
}

function bindUsageDetailTabs() {
  els.usageDetailModal?.querySelectorAll('.usage-detail-seg-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const section = btn.dataset.section;
      const view = btn.dataset.view;
      if (!section || !view) return;
      usageDetailView[section] = view;
      syncUsageDetailTabUi();
    });
  });
}

function renderUsageDetailModal() {
  if (!usageData) return;
  const u = usageData;
  const emb = embeddingUsageData || emptyUsageBucket();
  if (els.usageDetailTotals) {
    els.usageDetailTotals.innerHTML = `<div class="usage-grid usage-grid-inline">${usageGridHtml(u)}</div>`;
  }
  if (els.usageEmbeddingTotals) {
    els.usageEmbeddingTotals.innerHTML = `<div class="usage-grid usage-grid-inline usage-grid-embedding">${usageGridHtml(emb, { hideCompletion: true })}</div>`;
  }
  const statCols = usageStatCols();
  const embStatCols = usageStatCols({ includeCompletion: false });
  const providers = Object.entries(u.by_provider || {})
    .map(([id, row]) => ({ id, ...row }))
    .sort((a, b) => (b.total_tokens || 0) - (a.total_tokens || 0));
  if (els.usageByProviderTable) {
    els.usageByProviderTable.innerHTML = renderUsageDetailTable(
      providers,
      [{ label: t('usageProviderCol', '服务商'), render: (r) => usageProviderDisplayName(r.provider || r.id) }, ...statCols],
    );
  }
  const models = Object.entries(u.by_model || {})
    .map(([id, row]) => ({ id, ...row }))
    .sort((a, b) => (b.total_tokens || 0) - (a.total_tokens || 0));
  if (els.usageByModelTable) {
    els.usageByModelTable.innerHTML = renderUsageDetailTable(
      models,
      [
        { label: t('usageProviderCol', '服务商'), render: (r) => usageProviderDisplayName(r.provider || String(r.id).split('::')[0]) },
        { label: t('usageModelCol', '模型'), render: (r) => r.model || String(r.id).split('::').slice(1).join('::') },
        ...statCols,
      ],
    );
  }
  const embProviders = Object.entries(emb.by_provider || {})
    .map(([id, row]) => ({ id, ...row }))
    .sort((a, b) => (b.total_tokens || 0) - (a.total_tokens || 0));
  if (els.usageEmbeddingByProviderTable) {
    els.usageEmbeddingByProviderTable.innerHTML = renderUsageDetailTable(
      embProviders,
      [{ label: t('usageProviderCol', '服务商'), render: (r) => usageProviderDisplayName(r.provider || r.id) }, ...embStatCols],
    );
  }
  const embModels = Object.entries(emb.by_model || {})
    .map(([id, row]) => ({ id, ...row }))
    .sort((a, b) => (b.total_tokens || 0) - (a.total_tokens || 0));
  if (els.usageEmbeddingByModelTable) {
    els.usageEmbeddingByModelTable.innerHTML = renderUsageDetailTable(
      embModels,
      [
        { label: t('usageProviderCol', '服务商'), render: (r) => usageProviderDisplayName(r.provider || String(r.id).split('::')[0]) },
        { label: t('usageModelCol', '模型'), render: (r) => r.model || String(r.id).split('::').slice(1).join('::') },
        ...embStatCols,
      ],
    );
  }
  syncUsageDetailTabUi();
}

function openUsageDetailModal(opts = {}) {
  if (!usageData) {
    loadUsage().then(() => {
      if (usageData) openUsageDetailModal(opts);
    });
    return;
  }
  usageDetailOpen = true;
  setOverlayVisible(els.usageDetailModal, true);
  renderUsageDetailModal();
  syncBodyScrollLock();
  if (opts.focus === 'embedding') {
    requestAnimationFrame(() => {
      document.getElementById('usageDetailEmbeddingSection')?.scrollIntoView({ block: 'start', behavior: 'smooth' });
    });
  }
}

function closeUsageDetailModal() {
  usageDetailOpen = false;
  setOverlayVisible(els.usageDetailModal, false);
  syncBodyScrollLock();
}

// ---------------------------------------------------------------------------
// Modals
// ---------------------------------------------------------------------------

function onOverlayKeydown(e) {
  if (e.key !== 'Escape') return;
  if (els.writeConfirmModal && !els.writeConfirmModal.hidden) return;
  if (knowledgeOpen) { closeKnowledgeModal(); return; }
  if (usageDetailOpen) { closeUsageDetailModal(); return; }
  if (notificationsOpen) { closeNotificationsPanel(); return; }
  if (cabanaOpen) { closeCabanaModal(); return; }
  if (secocOpen) { closeSecocModal(); return; }
  if (typeof TerminalPanel !== 'undefined' && TerminalPanel.isOpen()) { TerminalPanel.setOpen(false); syncBodyScrollLock(); return; }
  if (typeof OfficePanel !== 'undefined' && OfficePanel.isOpen()) { OfficePanel.hide(); syncBodyScrollLock(); return; }
  if (els.settingsSidebar?.classList.contains('open')) { closeSettings(); return; }
  if (els.sessionsPanel?.classList.contains('open')) { closeSessionsDrawer(); }
}

// ---------------------------------------------------------------------------
// Misc
// ---------------------------------------------------------------------------

function autoResize() {
  const mobile = window.matchMedia('(max-width: 767px)').matches;
  const maxH = mobile ? 120 : 120;
  if (!els.chatInput) return;
  els.chatInput.style.height = 'auto';
  const next = Math.min(els.chatInput.scrollHeight, maxH);
  els.chatInput.style.height = `${Math.max(44, next)}px`;
}

function onChatKeydown(e) {
  if (typeof ComposerMention !== 'undefined' && ComposerMention.onKeydown(e)) return;
  if (onComposerSlashKeydown(e)) return;
  if (e.key !== 'Enter' || e.shiftKey || e.isComposing) return;
  e.preventDefault();
  els.composer.requestSubmit();
}

async function onChatPaste(e) {
  const items = e.clipboardData?.items;
  if (!items) return;
  const files = [];
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      const file = item.getAsFile();
      if (file) files.push(file);
    }
  }
  if (!files.length) return;
  e.preventDefault();
  await addImageFiles(files);
}

function renderAssistantFromHistory(msg) {
  const ui = appendAssistantMessage({ withLoading: false });
  if (msg.reasoning_content) {
    ui.thinking.classList.remove('hidden');
    renderThinkingContent(ui.thinkingBody, msg.reasoning_content);
    setDetailsCollapsed(ui.thinking, true);
  }
  hydrateAgentEvents(ui, msg.agent_events);
  if (ui.agentCallsBlock && !ui.agentCallsBlock.classList.contains('hidden')) {
    setDetailsCollapsed(ui.agentCallsBlock, true);
  }
  const toolResults = msg.tool_results || {};
  if (msg.tool_calls?.length) {
    ui.toolsBlock.classList.remove('hidden');
    setDetailsCollapsed(ui.toolsBlock, true);
    for (const tc of msg.tool_calls) {
      const id = tc.id;
      const fn = tc.function || {};
      renderToolCall(ui.toolsList, id, fn.name || '', fn.arguments || '', toolResults[id]);
    }
    updateToolCallsSummary(ui.toolsBlock);
  }
  const text = stripLeakedToolCalls(messageText(msg.content) || (typeof msg.content === 'string' ? msg.content : ''));
  if (text) {
    renderMarkdownContent(ui.content, text);
  } else if (!msg.tool_calls?.length) {
    ui.content.textContent = t('noResponse', 'No response');
  }
  ui.actionsBar?.classList.remove('is-pending');
  setMessageModelTag(ui, msg.resolvedModel);
  renderMessageFooter(ui, { usage: msg.usage, resolvedModel: msg.resolvedModel });
  return ui.turn;
}

function renderWelcomePanel() {
  const hero = document.createElement('div');
  hero.className = 'welcome-hero';
  hero.innerHTML = `<h2>✨ ${t('welcomeTitle', '你好！我是 op助手')}</h2><p>${t('welcomeSubtitle', '有什么可以帮你的？')}</p>`;

  const banner = document.createElement('div');
  banner.className = 'welcome-banner';
  banner.textContent = t('welcomeBanner', '内置 AI 助手，使用设置中的 API 配置。可查询车辆状态、读取参数、执行诊断命令。');

  const grid = document.createElement('div');
  grid.className = 'quick-actions';
  const actions = getQuickActionsList();
  if (!actions.length) {
    const empty = document.createElement('p');
    empty.className = 'quick-actions-empty';
    empty.textContent = t('quickActionsMissing', '快捷卡片未加载，请刷新页面。');
    grid.appendChild(empty);
  }
  for (const action of actions) {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'quick-action-card';
    card.innerHTML = `
      <span class="qa-icon">${action.icon}</span>
      <div class="qa-text">
        <div class="qa-title">${t(action.titleKey, action.titleKey)}</div>
        <div class="qa-desc">${t(action.descKey, '')}</div>
      </div>
    `;
    card.addEventListener('click', () => runQuickAction(action));
    grid.appendChild(card);
  }

  appendToMessages(hero);
  appendToMessages(banner);
  appendToMessages(grid);
  syncMessagesLayoutMode();
}

async function runQuickAction(action) {
  if (action.action === 'cabana') {
    openCabanaModal();
    return;
  }
  pendingWorkflow = action.workflow || '';
  els.chatInput.value = action.promptKey ? t(action.promptKey) : (action.prompt || '');
  autoResize();
  await sendChat(new Event('submit'));
}

function renderStoredMessages(opts = {}) {
  if (!opts.force && isChatUiLocked()) return;
  const isDraft = opts.draft === true || isDraftSessionView();
  const sessionId = opts.sessionId ?? SessionStore.activeId;
  const switchGen = opts.switchGen;
  if (switchGen != null && switchGen !== sessionSwitchGeneration) return;
  if (!isDraft && (!sessionId || SessionStore.activeId !== sessionId)) return;

  const rawHistory = isDraft ? [] : getCurrentMessages();
  const history = typeof SessionStore.dedupeTrailingAssistants === 'function'
    ? SessionStore.dedupeTrailingAssistants(rawHistory)
    : rawHistory;

  clearMessagesPreservingJump();
  for (let i = 0; i < history.length; i += 1) {
    const msg = history[i];
    if (msg.role === 'user') {
      const turn = appendUserMessage(msg.content, { scroll: false, msgIdx: i, fileRefs: msg.file_refs || [] });
      if (turn && editingUserMsgIdx === i) {
        turn.querySelector('.message.user')?.classList.add('is-editing');
      }
    } else if (msg.role === 'assistant') {
      if (!assistantMessageHasContent(msg)) continue;
      const turn = renderAssistantFromHistory(msg);
      if (turn) {
        turn.dataset.msgIdx = String(i);
        MessageFeedback.updateButtons(turn, msg);
      }
    }
  }
  if (!isDraft) {
    if (switchGen != null && switchGen !== sessionSwitchGeneration) return;
    if (SessionStore.activeId !== sessionId) return;
  }

  if (!hasVisibleChatHistory(history)) {
    renderWelcomePanel();
  }
  syncMessagesLayoutMode();
  if (opts.forceScroll) scrollToBottom({ force: true });
  else scrollToBottom();
  refreshContextMeter();
}

function onLangChange() {
  i18n.setLang(els.langSelect.value);
  applyTranslations();
  updateThemeIcon();
  if (!hasVisibleChatHistory(getCurrentMessages())) {
    renderStoredMessages();
  }
  if (els.schedulerTaskList?.closest('.settings-pane')?.classList.contains('active')) {
    loadSchedulerPanel();
  }
  if (typeof CabanaPanel !== 'undefined') {
    CabanaPanel.refresh();
  }
  if (typeof WorkbuddyPanel !== 'undefined') {
    WorkbuddyPanel.onLangChange?.();
  }
  if (typeof MessageFeedback !== 'undefined') MessageFeedback.refreshTranslations();
  if (typeof ComposerMention !== 'undefined') ComposerMention.refreshTranslations();
}

function onThemeToggle() {
  Theme.toggle();
  updateThemeIcon();
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

function bindMessageActions() {
  els.messages?.addEventListener('click', (e) => {
    const btn = e.target.closest('.msg-action-btn');
    if (!btn) return;
    e.preventDefault();
    const turn = btn.closest('.message-turn');
    if (!turn) return;
    const action = btn.dataset.action;
    const msgIdx = parseInt(turn.dataset.msgIdx, 10);

    if (action === 'copy') {
      const text = getMessageTurnCopyText(turn);
      if (!text) {
        showToast(t('copyFailed', 'Nothing to copy'), 'warning');
        return;
      }
      copyTextToClipboard(text).then((ok) => {
        if (!ok) {
          showToast(t('copyFailed', 'Copy failed'), 'warning');
          return;
        }
        btn.classList.add('copied');
        setTimeout(() => btn.classList.remove('copied'), 1400);
      });
      return;
    }

    if (action === 'edit') {
      if (!Number.isFinite(msgIdx) || msgIdx < 0) return;
      startEditUserMessage(msgIdx);
      return;
    }

    if (action === 'like' || action === 'dislike') {
      if (!Number.isFinite(msgIdx) || msgIdx < 0) return;
      if (action === 'like') MessageFeedback.handleLike(msgIdx);
      else MessageFeedback.handleDislike(msgIdx);
      return;
    }

    if (action === 'speak') {
      speakMessageFromTurn(turn, btn);
      return;
    }

    if (action === 'regenerate') {
      if (!Number.isFinite(msgIdx) || msgIdx < 0) return;
      regenerateAssistantMessage(msgIdx);
    }
  });

  document.getElementById('composerEditCancel')?.addEventListener('click', () => {
    cancelEditUserMessage();
  });

  if (typeof window !== 'undefined' && window.speechSynthesis) {
    window.speechSynthesis.addEventListener('voiceschanged', () => {});
  }
}

function bindHeaderMoreMenu() {
  const btn = document.getElementById('headerMoreBtn');
  const menu = document.getElementById('headerMoreMenu');
  if (!btn || !menu) return;

  const actionMap = {
    notifications: () => toggleNotificationsPanel(),
    terminal: () => {
      if (typeof TerminalPanel === 'undefined') return;
      TerminalPanel.setOpen(!TerminalPanel.isOpen());
    },
    secoc: () => {
      if (secocOpen) closeSecocModal();
      else openSecocModal();
    },
    office: () => {
      if (typeof OfficePanel !== 'undefined') OfficePanel.toggle();
    },
    cabana: () => toggleCabanaModal(),
  };

  const setOpen = (open) => {
    menu.classList.toggle('hidden', !open);
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  };

  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    setOpen(menu.classList.contains('hidden'));
  });

  menu.querySelectorAll('[data-header-action]').forEach((item) => {
    item.addEventListener('click', () => {
      const action = item.getAttribute('data-header-action');
      actionMap[action]?.();
      setOpen(false);
    });
  });

  document.addEventListener('click', (e) => {
    if (!menu.classList.contains('hidden') && !btn.contains(e.target) && !menu.contains(e.target)) {
      setOpen(false);
    }
  });
}

function bindUiEvents() {
  bindMessageActions();
  bindHeaderMoreMenu();
  els.messages?.addEventListener('scroll', onMessagesScroll, { passive: true });
  els.jumpToBottomBtn?.addEventListener('click', jumpToBottom);
  els.cabanaBtn?.addEventListener('click', toggleCabanaModal);
  els.cabanaClose?.addEventListener('click', closeCabanaModal);
  els.cabanaBackdrop?.addEventListener('click', closeCabanaModal);
  els.notificationsBtn?.addEventListener('click', toggleNotificationsPanel);
  els.notificationsCloseBtn?.addEventListener('click', closeNotificationsPanel);
  els.notificationsBackdrop?.addEventListener('click', closeNotificationsPanel);
  els.notificationsMarkReadBtn?.addEventListener('click', () => {
    markAllNotificationsRead().catch(console.error);
  });
  els.usageDetailBtn?.addEventListener('click', () => openUsageDetailModal());
  els.embeddingUsageDetailBtn?.addEventListener('click', () => openUsageDetailModal({ focus: 'embedding' }));
  els.usageDetailClose?.addEventListener('click', closeUsageDetailModal);
  els.usageDetailBackdrop?.addEventListener('click', closeUsageDetailModal);
  els.knowledgeBtn?.addEventListener('click', toggleKnowledgeModal);
  els.settingsKnowledgeBtn?.addEventListener('click', toggleKnowledgeModal);
  document.getElementById('embeddingGoModelHubBtn')?.addEventListener('click', () => {
    openSettingsTab('model');
  });
  els.knowledgeClose?.addEventListener('click', closeKnowledgeModal);
  els.knowledgeBackdrop?.addEventListener('click', closeKnowledgeModal);

  els.composer?.addEventListener('submit', sendChat);
  els.chatInput?.addEventListener('keydown', onChatKeydown);
  els.chatInput?.addEventListener('paste', onChatPaste);
  els.chatInput?.addEventListener('input', autoResize);
  window.matchMedia('(max-width: 767px)').addEventListener('change', () => {
    applyChatPlaceholder();
    autoResize();
  });
  els.composer?.addEventListener('dragover', (e) => {
    if (e.dataTransfer?.types?.includes('Files')) {
      e.preventDefault();
      els.composer.classList.add('drag-over');
    }
  });
  els.composer?.addEventListener('dragleave', () => els.composer.classList.remove('drag-over'));
  els.composer?.addEventListener('drop', async (e) => {
    e.preventDefault();
    els.composer.classList.remove('drag-over');
    if (e.dataTransfer?.files?.length) {
      await addImageFiles(e.dataTransfer.files);
    }
  });
  els.imageBtn?.addEventListener('click', () => els.imageInput?.click());
  els.imageInput?.addEventListener('change', async () => {
    await addImageFiles(els.imageInput.files);
    els.imageInput.value = '';
  });
  els.themeBtn?.addEventListener('click', onThemeToggle);
  els.devRefreshBtn?.addEventListener('click', () => renderDevPane());
  bindCollabTabControls();
  bindCollabCredentialsControls();
  bindDevCacheControls();
  bindDevPaneSectionControls();
  bindRuntimeTabControls();
  els.devPublishSaveBtn?.addEventListener('click', async () => {
    const run = async () => { await savePublishSettings(); };
    if (typeof UiBusy !== 'undefined') {
      await UiBusy.withButtonBusy(els.devPublishSaveBtn, run, { busyLabel: t('uiSaving', '保存中…') });
    } else {
      els.devPublishSaveBtn.disabled = true;
      try { await run(); } catch (e) { showToast(e.message); } finally { els.devPublishSaveBtn.disabled = false; }
    }
  });
  els.devIssueSubmitBtn?.addEventListener('click', async () => {
    const run = async () => {
      await saveIssueSettings().catch(() => {});
      await submitIssue();
    };
    if (typeof UiBusy !== 'undefined') {
      await UiBusy.withButtonBusy(els.devIssueSubmitBtn, run, { busyLabel: t('uiWorking', '处理中…') });
    } else {
      els.devIssueSubmitBtn.disabled = true;
      try { await run(); } catch (e) { showToast(e.message); } finally { els.devIssueSubmitBtn.disabled = false; }
    }
  });
  els.publishPromptClose?.addEventListener('click', closePublishPrompt);
  els.publishPromptCancel?.addEventListener('click', closePublishPrompt);
  els.publishPromptBackdrop?.addEventListener('click', closePublishPrompt);
  els.publishPromptOk?.addEventListener('click', async () => {
    const first = els.publishPromptUnits?.querySelector('.publish-unit-card');
    const unitId = first?.dataset?.unitId;
    if (unitId) await publishFromPrompt(unitId);
  });
  els.devPackageCheckBtn?.addEventListener('click', () => renderDevPane());
  els.devPackageUpdateBtn?.addEventListener('click', async () => {
    const run = async () => {
      const { data } = await api('POST', '/api/ai/package/update', { confirm: true });
      if (data.ok) {
        const msg = data.update_mode === 'reinstall'
          ? t('devPackageUpdateOkReinstall', '更新完成（已重新克隆），请重启 ai.aid')
          : t('devPackageUpdateOk', '更新完成，请重启 ai.aid');
        showToast(msg);
        renderDevPane();
      } else {
        showToast(data.error || t('devPackageUpdateFail', '更新失败'));
        throw new Error(data.error || 'update failed');
      }
    };
    if (typeof UiBusy !== 'undefined') {
      await UiBusy.withButtonBusy(els.devPackageUpdateBtn, run, { busyLabel: t('uiWorking', '处理中…') });
    } else {
      els.devPackageUpdateBtn.disabled = true;
      try {
        await run();
      } catch {
        els.devPackageUpdateBtn.disabled = false;
      }
    }
  });
  els.devForkRefreshBtn?.addEventListener('click', async () => {
    const run = async () => {
      await refreshForkDetectCard();
    };
    if (typeof UiBusy !== 'undefined') {
      await UiBusy.withButtonBusy(els.devForkRefreshBtn, run, { busyLabel: t('uiWorking', '处理中…') });
    } else {
      els.devForkRefreshBtn.disabled = true;
      try {
        await run();
      } catch {
        showToast(t('devForkLoadFail', '无法扫描 fork'));
      } finally {
        els.devForkRefreshBtn.disabled = false;
      }
    }
  });
  els.devForkSyncBtn?.addEventListener('click', async () => {
    if (!window.confirm(t('devForkAnalyzeConfirm', 'AI 将阅读整个 openpilot 项目并分析 fork，随后生成草稿（需人工审核）。继续？'))) return;
    await runForkAnalyzePipeline({ force: false });
  });
  els.onboardingBackdrop?.addEventListener('click', closeOnboardingWizard);
  els.onboardingTestBtn?.addEventListener('click', () => testOnboardingWizard());
  els.onboardingSaveBtn?.addEventListener('click', () => saveOnboardingWizard());
  els.onboardingRestoreBtn?.addEventListener('click', () => restoreOnboardingBackup().catch(console.error));
  els.onboardingProvider?.addEventListener('change', async () => {
    const p = els.onboardingProvider.value;
    if (!onboardingModelCombo?.getValue()) {
      onboardingModelCombo?.setValue(defaults[p] || '', { silent: true });
    }
    if (!els.onboardingEmbeddingSeparateToggle?.checked) {
      refreshOnboardingEmbeddingModels();
    }
    await refreshOnboardingModels().catch(() => refreshOnboardingEmbeddingModels());
  });
  els.onboardingEmbeddingSeparateToggle?.addEventListener('change', onOnboardingEmbeddingSeparateToggle);
  els.onboardingEmbeddingProvider?.addEventListener('change', refreshOnboardingEmbeddingModels);
  els.onboardingApiKey?.addEventListener('change', () => {
    refreshOnboardingModels().catch(() => {});
  });
  els.onboardingRagStartBtn?.addEventListener('click', () => runOnboardingRagSetup());
  els.onboardingRagSkipBtn?.addEventListener('click', () => finishOnboardingKnowledgeSetup({ keepOpen: true }));
  els.settingsBtn?.addEventListener('click', () => openSettings());
  els.settingsSidebarClose?.addEventListener('click', () => closeSettings());
  els.settingsBackdrop?.addEventListener('click', () => closeSettings());
  els.sessionsToggleBtn?.addEventListener('click', toggleSessionsPanel);
  els.sessionsCloseBtn?.addEventListener('click', closeSessionsDrawer);
  els.newSessionBtn?.addEventListener('click', createNewSession);
  els.sessionsBackdrop?.addEventListener('click', closeSessionsDrawer);
  els.providerSelect?.addEventListener('change', () => {
    onProviderChange();
    persistConfigDraft();
    fetchModels().catch(() => {});
    refreshUsageForCurrentModel();
    refreshEmbeddingUsageForCurrentModel();
  });
  els.baseUrlInput?.addEventListener('change', fetchModels);
  els.apiKeyInput?.addEventListener('change', fetchModels);
  els.langSelect?.addEventListener('change', onLangChange);
  els.chatInput?.addEventListener('input', onComposerInput);
  els.saveBtn?.addEventListener('click', () => saveConfig({ silent: false }));
  els.personaSaveBtn?.addEventListener('click', () => savePersonaConfig().catch(console.error));
  bindConfigPersistence();
  if (savedConfig && Object.keys(savedConfig).length) {
    configSaveState = reconcileConfigDraft(savedConfig) ? 'dirty' : 'saved';
  } else {
    configSaveState = LocalPrefs.getConfigDraft() ? 'dirty' : 'saved';
  }
  updateConfigSaveHint();
  els.schedActionModeBtn?.addEventListener('click', () => setSchedActionMode(!schedActionManual));
  els.schedAction?.addEventListener('change', () => {
    if (els.schedAction.value === '__custom__') {
      setSchedActionMode(true);
    }
  });
  els.schedTrigger?.addEventListener('change', updateSchedDailyFieldsVisibility);
  els.schedAddBtn?.addEventListener('click', addSchedulerTask);
  els.ragSaveBtn?.addEventListener('click', saveRagDoc);
  els.ragReindexBtn?.addEventListener('click', () => reindexRag());
  els.ragSyncWikiBtn?.addEventListener('click', syncWikiRag);
  els.embeddingModeSelect?.addEventListener('change', () => {
    onEmbeddingModeChange();
    refreshEmbeddingUsageForCurrentModel();
  });
  els.embeddingProviderSelect?.addEventListener('change', () => {
    onEmbeddingProviderChange();
    refreshEmbeddingUsageForCurrentModel();
  });
  document.addEventListener('keydown', onOverlayKeydown);
  window.addEventListener('pagehide', flushSessionSyncOnUnload);
  window.addEventListener('beforeunload', flushSessionSyncOnUnload);
}

async function migrateLegacySessionsOnce() {
  const legacy = SessionStore.readLegacyLocalSnapshot?.();
  if (!legacy?.sessions?.length) return;
  try {
    const { data: server } = await api('GET', '/api/ai/sessions');
    if (server?.sessions?.length) {
      SessionStore.clearLegacyLocalStorage?.();
      return;
    }
    const { data } = await api('POST', '/api/ai/sessions', {
      sessions: legacy.sessions.filter((s) => SessionStore.sessionHasContent(s)),
      activeId: legacy.activeId,
    });
    if (data?.ok) {
      if (typeof SessionSync !== 'undefined') SessionSync.setServerSyncMeta(data);
      SessionStore.clearLegacyLocalStorage?.();
      await loadSessionsFromDevice();
    }
  } catch (e) {
    console.warn('legacy session migration skipped', e);
  }
}

function waitForSyncHello(timeoutMs = 6000) {
  if (_syncWsGotHello) return Promise.resolve(true);
  return new Promise((resolve) => {
    const deadline = Date.now() + timeoutMs;
    const tick = () => {
      if (_syncWsGotHello) return resolve(true);
      if (Date.now() >= deadline) return resolve(false);
      setTimeout(tick, 40);
    };
    tick();
  });
}

async function init() {
  SessionStore.init({ getDefaultChatRoute: hubPrimaryChatRoute });
  initChatJobs();
  if (typeof WorkbuddyPanel !== 'undefined') {
    WorkbuddyPanel.init({ api, showToast });
  }
  if (typeof WorkflowEditor !== 'undefined') {
    WorkflowEditor.init({ api });
  }
  if (typeof TranscriptRecovery !== 'undefined') {
    TranscriptRecovery.init({ api });
  }
  if (typeof PlatformPanel !== 'undefined') {
    PlatformPanel.init({ api, showToast });
    PlatformPanel.bindFilePicker?.('onboardingBackupFile', 'onboardingBackupFileName', 'onboardingBackupPick');
  }
  initModelCombos();
  if (typeof SessionModelPicker !== 'undefined') {
    SessionModelPicker.mount('#sessionModelPicker', {
      SessionStore,
      getHub: () => effectiveModelHub(savedConfig),
      getSession: () => SessionStore.getActive(),
      providerLabel: providerDisplayName,
      t,
      scheduleSessionSync,
      isSessionStreaming: isSessionStreaming,
      onRouteChange: () => {
        refreshModelBadgeForSession();
        refreshContextMeter();
      },
    });
  }
  if (typeof ComposerContextMeter !== 'undefined') {
    ComposerContextMeter.mount('#composerContextMeter', {
      getConfig: () => savedConfig,
      getHub: () => effectiveModelHub(savedConfig),
      getSession: () => SessionStore.getActive(),
      getMessages: getCurrentMessages,
      getToolsMeta: () => toolsMeta,
      getSkillsRegistry: () => skillsRegistry,
      getConnectors: () => mcpConnectors,
      getRagStats: () => ragStatsCache,
      getEmbeddingUsage: () => embeddingUsageData,
      messageText,
      getEffectiveRoute: typeof SessionModelPicker !== 'undefined'
        ? (session, hub) => SessionModelPicker.getEffectiveRoute(session, hub)
        : undefined,
      fmtTokenNum,
      t,
      tf,
      isBusy: () => isSessionStreaming(SessionStore.activeId),
      onCompact: () => { runManualCompact().catch(() => {}); },
    });
  }
  if (typeof SessionSearch !== 'undefined') {
    SessionSearch.mount({
      api,
      t,
      escapeHtml,
      messageText,
      listSessions: () => SessionStore.listWithContent(),
      getSessionById: (id) => SessionStore.getById(id),
      navigateToHit: navigateToSessionHit,
    });
  }
  if (typeof AgentsPanel !== 'undefined') {
    AgentsPanel.init({
      api,
      els,
      escapeHtml,
      scrollToBottom,
      showToast,
    });
  }
  if (typeof OfficePanel !== 'undefined') {
    OfficePanel.init({
      api: WebApi.api,
      showToast,
      onOpen: () => {
        if (typeof AgentsPanel !== 'undefined') AgentsPanel.refreshOfficeUsage();
      },
      onVisibilityChange: () => syncBodyScrollLock(),
      getDriving: () => !!state.driving,
      getVehicleState: () => state.state || null,
    });
  }
  if (typeof CommandQueue !== 'undefined') CommandQueue.bindUi();
  if (typeof DeviceTrust !== 'undefined') {
    DeviceTrust.refreshTrust(api).catch(() => {});
  }
  bindSettingsTabs();
  if (typeof ComposerMention !== 'undefined') {
    ComposerMention.init({
      api,
      t,
      showToast,
      escapeHtml,
      getInput: () => els.chatInput,
      getPendingRefs: () => pendingFileRefs,
      getPendingFiles: () => pendingFileRefs,
      listSessions: () => SessionStore.listWithContent(),
      getActiveSessionId: () => SessionStore.activeId,
      getGitBranch: () => state?.fork?.git_branch || '',
      onAttach: (ref) => {
        pendingFileRefs.push(ref);
        renderComposerAttachments();
      },
      autoResize,
      hideSlashMenu: hideComposerSlashMenu,
    });
  }
  if (typeof MessageFeedback !== 'undefined') {
    MessageFeedback.init({
      api,
      t,
      showToast,
      SessionStore,
      getCurrentMessages,
      saveCurrentMessages,
      setOverlayVisible,
    });
  }
  bindUiEvents();
  bindUsageDetailTabs();
  if (typeof TskPanel !== 'undefined') TskPanel.bind();
  if (typeof TerminalPanel !== 'undefined') {
    if (typeof TerminalAi !== 'undefined') {
      TerminalAi.init({
        api: WebApi.api,
        SessionStore,
        prepareMessagesForApi,
        syncSessionsToDevice,
        getState: () => state,
        chatMode: CHAT_MODE,
        onAiActivity: (active) => TerminalPanel.setPtyMuted?.(active),
        ptyMuted: () => TerminalPanel.isPtyMuted?.() ?? false,
      });
    }
    TerminalPanel.init({ onVisibilityChange: () => syncBodyScrollLock() });
  }
  els.secocBtn?.addEventListener('click', () => {
    if (secocOpen) closeSecocModal();
    else openSecocModal();
  });
  els.secocCloseBtn?.addEventListener('click', closeSecocModal);
  els.secocBackdrop?.addEventListener('click', closeSecocModal);

  Theme.init();
  window.addEventListener('themechange', updateThemeIcon);
  updateThemeIcon();
  if (els.langSelect) els.langSelect.value = i18n.getLang();
  applyTranslations();
  hydrateFromLocalPrefs();

  if (typeof CabanaPanel !== 'undefined') {
    ensureCabanaInited();
  }

  loadSessionMode();
  renderSessionList();
  renderStoredMessages({ force: true, forceScroll: true });
  updateModelBadgeFromSaved();

  await dismissAppSplash();

  startSyncWebSocket();

  loadBootstrap()
    .then(() => {
      renderSessionList();
      renderStoredMessages({ force: true, forceScroll: true });
      updateModelBadgeFromSaved();
      if (typeof ChatJobs !== 'undefined') ChatJobs.recoverStuckStreams?.().catch(() => {});
    })
    .catch((e) => {
      console.error('loadBootstrap failed', e);
      hydrateFromLocalPrefs();
    });

  if (!_gatewayHydrated) {
    refreshSessionViewFromRemote().catch((e) => {
      console.warn('initial session pull failed', e);
    });
  }

  migrateLegacySessionsOnce().catch(() => {});

  if (typeof CanvasPanel !== 'undefined') {
    CanvasPanel.loadSession(SessionStore.activeId).catch(() => {});
  }

  startStatusPolling();
  loadNotifications().catch(() => {});
  startNotificationsPolling();

  if (new URLSearchParams(location.search).get('cabana') === '1') {
    openCabanaModal();
  }

  const settingsTab = new URLSearchParams(location.search).get('settings');
  if (settingsTab === 'secoc') openSecocModal();
  else if (settingsTab) openSettingsTab(settingsTab);
}

function dismissAppSplash() {
  const splash = document.getElementById('appSplash');
  if (!splash || splash.dataset.dismissed === '1') return Promise.resolve();
  const elapsed = (typeof performance !== 'undefined' ? performance.now() : Date.now()) - appSplashStartedAt;
  const wait = Math.max(0, APP_SPLASH_MIN_MS - elapsed);
  return new Promise((resolve) => {
    setTimeout(() => {
      splash.dataset.dismissed = '1';
      splash.classList.add('is-hidden');
      splash.setAttribute('aria-busy', 'false');
      document.body.classList.remove('app-booting');
      const done = () => {
        splash.remove();
        resolve();
      };
      splash.addEventListener('transitionend', done, { once: true });
      setTimeout(done, 500);
    }, wait);
  });
}

init().catch(console.error);
