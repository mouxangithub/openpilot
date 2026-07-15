let hostEnvironment = null;
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const APP_SPLASH_MIN_MS = 480;
const appSplashStartedAt = (typeof performance !== 'undefined' ? performance.now() : Date.now());

document.body.classList.add('app-booting');

const els = {
  messages: $('#messages'),
  composer: $('#composer'),
  chatInput: $('#chatInput'),
  imageBtn: $('#imageBtn'),
  imageInput: $('#imageInput'),
  composerAttachments: $('#composerAttachments'),
  composerHintBtn: $('#composerHintBtn'),
  composerHintTooltip: $('#composerHintTooltip'),
  sendBtn: $('#sendBtn'),
  knowledgeBtn: $('#knowledgeBtn'),
  settingsKnowledgeBtn: $('#settingsKnowledgeBtn'),
  knowledgeModal: $('#knowledgeModal'),
  knowledgeBackdrop: $('#knowledgeBackdrop'),
  knowledgeClose: $('#knowledgeClose'),
  cabanaBtn: $('#cabanaBtn'),
  cabanaModal: $('#cabanaModal'),
  cabanaBackdrop: $('#cabanaBackdrop'),
  cabanaClose: $('#cabanaClose'),
  notificationsBtn: $('#notificationsBtn'),
  notificationsBadge: $('#notificationsBadge'),
  notificationsPanel: $('#notificationsPanel'),
  notificationsBackdrop: $('#notificationsBackdrop'),
  notificationsList: $('#notificationsList'),
  notificationsMarkReadBtn: $('#notificationsMarkReadBtn'),
  notificationsCloseBtn: $('#notificationsCloseBtn'),
  notificationsTitle: $('#notificationsTitle'),
  workspace: $('#workspace'),
  statusPill: $('#statusPill'),
  themeBtn: $('#themeBtn'),
  settingsBtn: $('#settingsBtn'),
  settingsSidebar: $('#settingsSidebar'),
  settingsSidebarClose: $('#settingsSidebarClose'),
  settingsBackdrop: $('#settingsBackdrop'),
  appShell: $('#appShell'),
  sessionsToggleBtn: $('#sessionsToggleBtn'),
  sessionsCloseBtn: $('#sessionsCloseBtn'),
  sessionsPanel: $('#sessionsPanel'),
  sessionsBackdrop: $('#sessionsBackdrop'),
  sessionList: $('#sessionList'),
  newSessionBtn: $('#newSessionBtn'),
  modelBadge: $('#modelBadge'),
  providerSelect: $('#providerSelect'),
  modelSelect: $('#modelSelect'),
  modelInput: $('#modelInput'),
  modelModeBtn: $('#modelModeBtn'),
  apiKeyInput: $('#apiKeyInput'),
  baseUrlField: $('#baseUrlField'),
  baseUrlInput: $('#baseUrlInput'),
  systemPromptInput: $('#systemPromptInput'),
  temperatureInput: $('#temperatureInput'),
  topPInput: $('#topPInput'),
  maxTokensInput: $('#maxTokensInput'),
  thinkingToggle: $('#thinkingToggle'),
  langSelect: $('#langSelect'),
  timezoneSelect: $('#timezoneSelect'),
  composerSlashMenu: $('#composerSlashMenu'),
  composerSlashLabel: $('#composerSlashLabel'),
  composerSlashList: $('#composerSlashList'),
  saveBtn: $('#saveBtn'),
  connectionResult: $('#connectionResult'),
  usageSection: $('#usageSection'),
  usageGrid: $('#usageGrid'),
  usageModelHint: $('#usageModelHint'),
  usageDetailBtn: $('#usageDetailBtn'),
  usageDetailModal: $('#usageDetailModal'),
  usageDetailBackdrop: $('#usageDetailBackdrop'),
  usageDetailClose: $('#usageDetailClose'),
  usageDetailTotals: $('#usageDetailTotals'),
  usageByProviderTable: $('#usageByProviderTable'),
  usageByModelTable: $('#usageByModelTable'),
  toast: $('#toast'),
  schedulerTaskList: $('#schedulerTaskList'),
  schedName: $('#schedName'),
  schedAction: $('#schedAction'),
  schedActionCustom: $('#schedActionCustom'),
  schedActionModeBtn: $('#schedActionModeBtn'),
  schedInterval: $('#schedInterval'),
  schedHour: $('#schedHour'),
  schedMinute: $('#schedMinute'),
  schedDailyFields: $('#schedDailyFields'),
  schedAddBtn: $('#schedAddBtn'),
  tunePassportList: $('#tunePassportList'),
  hostEnvBox: $('#hostEnvBox'),
  packageVersionBox: $('#packageVersionBox'),
  devPackageVersionBadge: $('#devPackageVersionBadge'),
  devPackageCheckBtn: $('#devPackageCheckBtn'),
  devPackageUpdateBtn: $('#devPackageUpdateBtn'),
  forkDetectBox: $('#forkDetectBox'),
  forkProgressBox: $('#forkProgressBox'),
  forkProgressStatus: $('#forkProgressStatus'),
  forkProgressPhases: $('#forkProgressPhases'),
  forkProgressLog: $('#forkProgressLog'),
  forkProgressThinkingWrap: $('#forkProgressThinkingWrap'),
  forkProgressThinking: $('#forkProgressThinking'),
  forkProgressContentWrap: $('#forkProgressContentWrap'),
  forkProgressContent: $('#forkProgressContent'),
  devForkBadge: $('#devForkBadge'),
  devForkRefreshBtn: $('#devForkRefreshBtn'),
  devForkSyncBtn: $('#devForkSyncBtn'),
  onboardingModal: $('#onboardingModal'),
  onboardingBackdrop: $('#onboardingBackdrop'),
  onboardingProvider: $('#onboardingProvider'),
  onboardingApiKey: $('#onboardingApiKey'),
  onboardingModel: $('#onboardingModel'),
  onboardingTestBtn: $('#onboardingTestBtn'),
  onboardingSaveBtn: $('#onboardingSaveBtn'),
  onboardingResult: $('#onboardingResult'),
  pcSessionsList: $('#pcSessionsList'),
  devAssetsList: $('#devAssetsList'),
  devRefreshBtn: $('#devRefreshBtn'),
  ragDocList: $('#ragDocList'),
  ragTitle: $('#ragTitle'),
  ragText: $('#ragText'),
  ragSaveBtn: $('#ragSaveBtn'),
  ragReindexBtn: $('#ragReindexBtn'),
  ragVectorStatus: $('#ragVectorStatus'),
  embeddingModeSelect: $('#embeddingModeSelect'),
  embeddingModelSelect: $('#embeddingModelSelect'),
  embeddingModelInput: $('#embeddingModelInput'),
  embeddingModelModeBtn: $('#embeddingModelModeBtn'),
  embeddingProviderSelect: $('#embeddingProviderSelect'),
  embeddingApiKeyInput: $('#embeddingApiKeyInput'),
  embeddingBaseUrlInput: $('#embeddingBaseUrlInput'),
  embeddingSeparateFields: $('#embeddingSeparateFields'),
  embeddingBaseUrlField: $('#embeddingBaseUrlField'),
  webPinInput: $('#webPinInput'),
  writeConfirmModal: $('#writeConfirmModal'),
  writeConfirmPreview: $('#writeConfirmPreview'),
  writeConfirmOk: $('#writeConfirmOk'),
  writeConfirmCancel: $('#writeConfirmCancel'),
  writeConfirmClose: $('#writeConfirmClose'),
  writeConfirmBackdrop: $('#writeConfirmBackdrop'),
  pinModal: $('#pinModal'),
  pinModalInput: $('#pinModalInput'),
  pinModalOk: $('#pinModalOk'),
  schedTrigger: $('#schedTrigger'),
};

let toolsMeta = {};
let pinRequired = false;
let embeddingDefaults = {};
let configSaveState = 'idle';
let configSaveInFlight = false;

const i18n = new I18n();
let state = { driving: true, configured: false };
let providers = [];
let providerLabels = {};
const FALLBACK_PROVIDERS = [
  'opencode-zen', 'opencode-go', 'deepseek', 'bigmodel', 'qwen', 'mimo', 'minimax',
  'openrouter', 'openai', 'kimi', 'custom',
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
  custom: 'Custom',
};
let modelCatalog = {};
let defaults = {};
let models = [];
let modelManual = false;
let embeddingProviders = [];
let embeddingProviderLabels = {};
let embeddingModelCatalog = {};
let embeddingSameModeCatalog = {};
let embeddingModels = [];
let embeddingModelManual = false;
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
let usageDetailOpen = false;
let configured = false;
let configureError = '';
let savedConfig = {};
let schedActionManual = false;
let abortController = null;
let streamSessionId = null;
let _chatJobPollTimer = null;
let _activeChatJobId = null;
let _sessionPullTimer = null;
let _syncWs = null;
let _syncWsConnected = false;
let _syncWsReconnectTimer = null;
let _syncWsFallbackTimer = null;
const _chatJobContexts = new Map();
let _suppressSessionPush = false;
let _syncWsGotHello = false;
let _statusPollTimer = null;
const CHAT_MODE = 'unlimited';
let pendingWorkflow = '';

const MAX_IMAGES_PER_MESSAGE = 9;
const MAX_IMAGE_DIMENSION = 1280;
const JPEG_QUALITY = 0.82;

let pendingImages = [];
let cabanaOpen = false;
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
    const key = el.dataset.i18n;
    if (!key) return;
    const val = t(key);
    const attr = el.dataset.i18nAttr;
    if (attr) el.setAttribute(attr, val);
    else el.textContent = val;
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
    const key = el.dataset.i18nPlaceholder;
    if (key) el.placeholder = t(key);
  });
}

function setI18nText(selector, key, fallback) {
  const el = typeof selector === 'string' ? $(selector) : selector;
  if (!el) return;
  el.textContent = fallback !== undefined ? t(key, fallback) : t(key);
}

function applyCachedUiState() {
  const src = savedConfig?.model ? savedConfig : LocalPrefs.getConfigCache();
  if (!src?.model) return;
  if (savedConfig?.model) updateModelBadgeFromSaved();
  else updateModelBadge(src.model);
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

function bindPasswordReveals() {
  document.querySelectorAll('.password-reveal[data-password-for]').forEach((btn) => {
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
      btn.title = visible ? t('hidePassword', 'Hide') : t('showPassword', 'Show');
      btn.setAttribute('aria-label', btn.title);
      eyeOpen?.classList.toggle('hidden', visible);
      eyeClosed?.classList.toggle('hidden', !visible);
    };
    sync(false);
    btn.addEventListener('click', () => sync(input.type === 'password'));
  });
}

function applySecocPaneI18n() {
  if (typeof TskPanel !== 'undefined' && TskPanel.applyTranslations) {
    TskPanel.applyTranslations(t);
  }
}

function applyTranslations() {
  document.title = t('title', 'op助手');
  els.chatInput.placeholder = t('chatPlaceholder', '描述问题，可粘贴日志或图片…');
  if (els.composerHintTooltip) {
    els.composerHintTooltip.textContent = t('composerHint', 'Enter 发送 · Shift+Enter 换行 · 支持粘贴图片');
  }
  if (els.composerHintBtn) {
    els.composerHintBtn.title = t('composerHintAria', 'Input shortcuts');
    els.composerHintBtn.setAttribute('aria-label', els.composerHintBtn.title);
  }
  if (els.composerSlashLabel && !composerSlashOpen) {
    els.composerSlashLabel.textContent = t('slashMenuPickCommand', 'Slash commands');
  }
  els.imageBtn.title = t('attachImage', 'Add image');
  els.sendBtn.title = t('send', 'Send');
  setI18nText('#settingsTitle', 'settings', 'Settings');
  setI18nText('#providerLabel', 'provider');
  setI18nText('#modelLabel', 'model');
  setI18nText('#apiKeyLabel', 'apiKey');
  setI18nText('#baseUrlLabel', 'baseUrl');
  setI18nText('#systemPromptLabel', 'systemPrompt', 'System Prompt');
  setI18nText('#temperatureLabel', 'temperature', 'Temperature');
  setI18nText('#topPLabel', 'topP', 'Top P');
  setI18nText('#maxTokensLabel', 'maxTokens', 'Max Tokens');
  setI18nText('#thinkingLabel', 'thinking', 'Thinking');
  updateConfigSaveHint();
  setI18nText('#usageTitle', 'usage', 'Usage');
  if (els.usageDetailBtn) els.usageDetailBtn.textContent = t('usageDetail', 'Usage detail');
  setI18nText('#usageDetailTitle', 'usageDetail', 'Usage detail');
  setI18nText('#usageDetailDesc', 'usageDetailDesc', 'All usage by provider and model');
  setI18nText('#usageByProviderTitle', 'usageByProvider', 'By provider');
  setI18nText('#usageByModelTitle', 'usageByModel', 'By model');
  setI18nText('#langLabel', 'langLabel', 'Language');
  setI18nText('#timezoneLabel', 'timezoneLabel', 'Timezone');
  renderTimezoneSelect();
  els.saveBtn.textContent = t('save');
  setI18nText('#sessionsTitle', 'sessions', 'Sessions');
  setI18nText('#tabModel', 'tabModel', '模型');
  setI18nText('#tabKnowledge', 'tabKnowledge', '知识库');
  const tabSecocEl = $('#tabSecoc');
  if (tabSecocEl) tabSecocEl.textContent = t('tabSecoc', 'SecOC');
  setI18nText('#tabScheduler', 'tabScheduler', '定时');
  setI18nText('#modelPaneDesc', 'modelPaneDesc', '连接服务商、选择对话模型并查看用量。');
  setI18nText('#modelConnectionTitle', 'modelConnectionTitle', '模型连接');
  setI18nText('#schedulerListTitle', 'schedulerListTitle', '已添加任务');
  setI18nText('#schedulerFormTitle', 'schedulerFormTitle', '新建任务');
  const tabDevEl = $('#tabDev');
  if (tabDevEl) tabDevEl.textContent = t('tabDev', '开发');
  const devPaneDescEl = $('#devPaneDesc');
  if (devPaneDescEl) devPaneDescEl.textContent = t('devPaneDesc', '运行环境、PC 工具会话与报告文件');
  const devEnvTitle = $('#devEnvTitle');
  if (devEnvTitle) devEnvTitle.textContent = t('devEnvTitle', '运行环境');
  const devPackageTitle = $('#devPackageTitle');
  if (devPackageTitle) devPackageTitle.textContent = t('devPackageTitle', 'op助手 版本');
  if (els.devPackageCheckBtn) els.devPackageCheckBtn.textContent = t('devPackageCheck', '检查更新');
  if (els.devPackageUpdateBtn) els.devPackageUpdateBtn.textContent = t('devPackageUpdate', '立即更新');
  const devForkTitle = $('#devForkTitle');
  if (devForkTitle) devForkTitle.textContent = t('devForkTitle', 'Fork 分析');
  if (els.devForkRefreshBtn) els.devForkRefreshBtn.textContent = t('devForkRefresh', '扫描仓库');
  if (els.devForkSyncBtn) els.devForkSyncBtn.textContent = t('devForkAnalyze', 'AI 分析并生成草稿');
  const forkThinkingSummary = $('#forkProgressThinkingSummary');
  if (forkThinkingSummary) forkThinkingSummary.textContent = t('devForkProgressThinking', '思考过程');
  const forkContentSummary = $('#forkProgressContentSummary');
  if (forkContentSummary) forkContentSummary.textContent = t('devForkProgressOutput', '模型输出');
  const attrTsk = $('#attrTskLabel');
  if (attrTsk) attrTsk.textContent = t('attrTskWeb', 'TSK Web');
  const attrAi = $('#attrAiLabel');
  if (attrAi) attrAi.textContent = t('attrOpAi', 'op助手');
  const devSessionsTitle = $('#devSessionsTitle');
  if (devSessionsTitle) devSessionsTitle.textContent = t('devSessionsTitle', 'PC 工具会话');
  const devAssetsTitle = $('#devAssetsTitle');
  if (devAssetsTitle) devAssetsTitle.textContent = t('devAssetsTitle', '报告与导出');
  const devRefreshLabel = $('#devRefreshLabel');
  if (devRefreshLabel) devRefreshLabel.textContent = t('devRefresh', '刷新');
  setI18nText('#personaSectionTitle', 'personaSection', '人设与生成');
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
  const webPinHint = $('#webPinHint');
  if (webPinHint) webPinHint.textContent = t('webPinHint');
  if (els.apiKeyInput) els.apiKeyInput.placeholder = t('apiKeyPlaceholder');
  if (els.baseUrlInput) els.baseUrlInput.placeholder = t('baseUrlPlaceholder');
  if (els.modelInput) els.modelInput.placeholder = t('modelPlaceholder');
  if (els.systemPromptInput) els.systemPromptInput.placeholder = t('systemPromptPlaceholder');
  if (els.schedName) els.schedName.placeholder = t('schedNamePlaceholder');
  if (els.ragTitle) els.ragTitle.placeholder = t('ragTitlePlaceholder');
  if (els.ragText) els.ragText.placeholder = t('ragTextPlaceholder');
  if (els.ragSaveBtn) els.ragSaveBtn.textContent = t('ragAddDoc');
  if (els.ragReindexBtn) els.ragReindexBtn.textContent = t('ragReindex');
  if (els.ragTitleLabel) els.ragTitleLabel.textContent = t('ragTitleLabel');
  if (els.ragTextLabel) els.ragTextLabel.textContent = t('ragTextLabel');
  const writeTitle = $('#writeConfirmTitle');
  if (writeTitle) writeTitle.textContent = t('writeConfirmTitle');
  const writeHint = $('#writeConfirmHint');
  if (writeHint) writeHint.textContent = t('writeConfirmHint');
  if (els.writeConfirmCancel) els.writeConfirmCancel.textContent = t('writeConfirmCancel');
  if (els.writeConfirmOk) els.writeConfirmOk.textContent = t('writeConfirmOk');
  const pinTitle = $('#pinModalTitle');
  if (pinTitle) pinTitle.textContent = t('pinModalTitle');
  if (els.pinModalOk) els.pinModalOk.textContent = t('pinModalOk');
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
  bindPasswordReveals();
  if (els.modelModeBtn) els.modelModeBtn.textContent = t('manual');
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
  const ac = opts.timeoutMs ? new AbortController() : null;
  let timer;
  const fetchOpts = { method, headers: getApiHeaders() };
  if (ac) fetchOpts.signal = ac.signal;
  if (body) {
    fetchOpts.headers['Content-Type'] = 'application/json';
    fetchOpts.body = JSON.stringify(body);
  }
  if (ac) timer = setTimeout(() => ac.abort(), opts.timeoutMs);
  try {
    const res = await fetch(path, fetchOpts);
    if (res.status === 401 && pinRequired) {
      const ok = await promptForPin();
      if (ok) return api(method, path, body, opts);
    }
    const text = await res.text();
    let data;
    try { data = JSON.parse(text); } catch { data = { ok: false, error: text }; }
    return { status: res.status, data };
  } catch (e) {
    if (e?.name === 'AbortError') {
      return { status: 0, data: { ok: false, error: 'request timeout' } };
    }
    throw e;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

function getApiHeaders() {
  const h = {};
  const pin = sessionStorage.getItem('ai-web-pin');
  if (pin) h['X-AI-Pin'] = pin;
  return h;
}

function promptForPin() {
  return new Promise((resolve) => {
    if (!els.pinModal) return resolve(false);
    els.pinModal.hidden = false;
    syncBodyScrollLock();
    els.pinModalInput.value = '';
    const done = (ok) => {
      els.pinModal.hidden = true;
      syncBodyScrollLock();
      els.pinModalOk.removeEventListener('click', onOk);
      resolve(ok);
    };
    const onOk = () => {
      const v = els.pinModalInput.value.trim();
      if (!v) return done(false);
      sessionStorage.setItem('ai-web-pin', v);
      reconnectSyncWebSocket();
      refreshSessionViewFromRemote().catch(() => {});
      done(true);
    };
    els.pinModalOk.addEventListener('click', onOk);
  });
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
  return SessionStore.listWithContent();
}

function saveCurrentMessages(messages) {
  const session = SessionStore.getActive();
  if (!session) return;
  SessionStore.updateMessages(session.id, messages.slice(-200));
  renderSessionList();
  scheduleSessionSync();
}

let _sessionSyncTimer = null;
function scheduleSessionSync() {
  if (_suppressSessionPush) return;
  clearTimeout(_sessionSyncTimer);
  _sessionSyncTimer = setTimeout(syncSessionsToDevice, 800);
}

function flushSessionSyncOnUnload() {
  clearTimeout(_sessionSyncTimer);
  const sessions = sessionsForSync();
  if (!sessions.length) return;
  const activeId = sessions.length && SessionStore.activeId && sessions.some((s) => s.id === SessionStore.activeId)
    ? SessionStore.activeId
    : (sessions[0]?.id ?? null);
  const body = JSON.stringify({
    sessions,
    activeId: sessions.length ? activeId : null,
  });
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
  const sessions = sessionsForSync();
  const activeId = sessions.length && SessionStore.activeId && sessions.some((s) => s.id === SessionStore.activeId)
    ? SessionStore.activeId
    : (sessions[0]?.id ?? null);
  try {
    const { data } = await api('POST', '/api/ai/sessions', {
      sessions,
      activeId: sessions.length ? activeId : null,
    });
    if (data?.ok && data.savedAt) {
      try { localStorage.setItem('openpilot-op-sessions-sync-at', String(data.savedAt)); } catch {}
    }
  } catch {}
}

function pickSessionMessages(a, b) {
  const aMsgs = a.messages || [];
  const bMsgs = b.messages || [];
  if (aMsgs.length !== bMsgs.length) {
    return aMsgs.length > bMsgs.length ? aMsgs : bMsgs;
  }
  return (a.updatedAt || 0) >= (b.updatedAt || 0) ? aMsgs : bMsgs;
}

function mergeSessionRecords(remoteSessions, localSessions) {
  const byId = new Map();
  const normalize = (s) => ({
    ...s,
    mode: s.mode || 'chat',
    messages: Array.isArray(s.messages) ? s.messages : [],
    updatedAt: Number(s.updatedAt) || 0,
  });

  for (const rs of remoteSessions) {
    const n = normalize(rs);
    if (!SessionStore.sessionHasContent(n)) continue;
    byId.set(rs.id, n);
  }
  for (const ls of localSessions) {
    const n = normalize(ls);
    if (!SessionStore.sessionHasContent(n)) continue;
    const prev = byId.get(ls.id);
    if (!prev) {
      byId.set(ls.id, n);
      continue;
    }
    const messages = pickSessionMessages(
      { messages: ls.messages, updatedAt: ls.updatedAt || 0 },
      { messages: prev.messages, updatedAt: prev.updatedAt || 0 },
    );
    const localNewer = (ls.updatedAt || 0) > (prev.updatedAt || 0);
    const newer = localNewer ? ls : prev;
    byId.set(ls.id, {
      ...prev,
      mode: prev.mode || ls.mode || 'chat',
      messages,
      title: localNewer && ls.title ? ls.title : (prev.title || ls.title),
      updatedAt: Math.max(ls.updatedAt || 0, prev.updatedAt || 0),
      activeJobId: newer.activeJobId || prev.activeJobId || ls.activeJobId || null,
    });
  }

  return [...byId.values()].sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
}

async function applyRemoteSessionsData(data) {
  if (!data?.ok) return false;

  _suppressSessionPush = true;
  try {
  const prevActiveId = SessionStore.activeId;
  const prevMessagesJson = JSON.stringify(getCurrentMessages());

  const localActiveBefore = SessionStore.activeId;
  const remoteSessions = (Array.isArray(data.sessions) ? data.sessions : [])
    .filter((s) => SessionStore.sessionHasContent(s));
  const localSessions = SessionStore.listWithContent();
  const remoteSavedAt = Number(data.savedAt) || 0;
  const localSavedAt = Number(localStorage.getItem('openpilot-op-sessions-sync-at')) || 0;
  const localHasContent = localSessions.length > 0;

  let merged = [];
  if (remoteSessions.length || localSessions.length) {
    merged = mergeSessionRecords(remoteSessions, localSessions);
  }

  if (!merged.length) {
    SessionStore.startDraft();
    return false;
  }

  let activeId = null;
  if (!localHasContent && remoteSessions.length) {
    activeId = data.activeId && merged.some((s) => s.id === data.activeId)
      ? data.activeId
      : merged[0].id;
  } else if (remoteSavedAt > localSavedAt && data.activeId && merged.some((s) => s.id === data.activeId)) {
    activeId = data.activeId;
  } else if (localActiveBefore && merged.some((s) => s.id === localActiveBefore)) {
    activeId = localActiveBefore;
  } else if (data.activeId && merged.some((s) => s.id === data.activeId)) {
    activeId = data.activeId;
  } else {
    activeId = merged[0].id;
  }

  SessionStore.importMerged(merged, activeId);
  if (remoteSavedAt) {
    try { localStorage.setItem('openpilot-op-sessions-sync-at', String(remoteSavedAt)); } catch {}
  }

  const messagesChanged = JSON.stringify(getCurrentMessages()) !== prevMessagesJson;
  const activeChanged = prevActiveId !== SessionStore.activeId;
  return messagesChanged || activeChanged;
  } finally {
    _suppressSessionPush = false;
  }
}

async function loadSessionsFromDevice() {
  const { data } = await api('GET', '/api/ai/sessions');
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
  if (_activeChatJobId && abortController) {
    updateLiveAssistantFromSession();
    return;
  }
  const gainedRemote = !hadLocalSessions && SessionStore.listWithContent().length > 0;
  if (sessionsChanged || configChanged || gainedRemote) {
    renderStoredMessages();
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
  let url = `${proto}//${location.host}/api/ai/sync/ws`;
  const pin = sessionStorage.getItem('ai-web-pin');
  if (pin) url += `?pin=${encodeURIComponent(pin)}`;
  return url;
}

function sendSyncWs(payload) {
  if (_syncWs?.readyState === WebSocket.OPEN) {
    _syncWs.send(JSON.stringify(payload));
  }
}

async function handleSyncWsSessions(data) {
  const locallyAttached = isLocallyStreaming() || Boolean(_activeChatJobId && abortController);
  const changed = await applyRemoteSessionsData(data);
  renderSessionList();
  if (locallyAttached) {
    updateLiveAssistantFromSession();
    return;
  }
  if (changed) {
    renderStoredMessages();
    await syncActiveSessionStreaming();
  }
}

async function handleSyncWsHello(data) {
  _syncWsGotHello = true;
  if (data.driving !== undefined || data.state) applyStatusFromPayload(data);
  if (data.notifications) handleWsNotifications(data);
  if (data.sessions) await handleSyncWsSessions(data);
  if (data.config) await applyRemoteConfigData(data.config);
  if (Array.isArray(data.activeJobs) && data.activeJobs.length) {
    await syncActiveSessionStreaming();
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
}

function handleWsNotifications(data) {
  if (!data?.ok) return;
  const items = data.notifications || [];
  const unread = items.filter((i) => !i.read).length;
  updateNotificationsBadge(unread);
  if (notificationsOpen) renderNotifications(items);
}

async function finalizeChatJobCtx(jobId, sessionId, ctx, status, payload = {}) {
  _chatJobContexts.delete(jobId);
  const streamActive = ctx.streamActive;
  clearLiveStreamChrome(ctx.ui);
  if (status === 'done' && streamActive()) {
    finishAssistant(ctx.ui, ctx.assistantMessage, sessionId);
  } else if (status === 'error' && streamActive()) {
    ctx.assistantMessage.content = formatApiError(payload.error || 'Error');
    finishAssistant(ctx.ui, ctx.assistantMessage, sessionId);
  } else if (status === 'cancelled' && streamActive() && ctx.ui.wrapper?.isConnected) {
    ctx.ui.wrapper.remove();
  } else if (status === 'done' && SessionStore.activeId === sessionId) {
    endChatStream(sessionId);
    commitAssistantMessage(sessionId, normalizeStoredMessage({
      role: 'assistant',
      ...(payload.assistant || ctx.assistantMessage),
    }));
    renderStoredMessages();
    SessionStore.clearActiveJobId(sessionId);
    syncSessionsToDevice().catch(() => {});
    return;
  }
  SessionStore.clearActiveJobId(sessionId);
  endChatStream(sessionId);
  syncSessionsToDevice().catch(() => {});
}

async function handleSyncWsChatEvent(payload) {
  const { jobId, sessionId, event, status } = payload;
  let ctx = findChatJobCtx(jobId, sessionId);
  if (ctx && !_chatJobContexts.has(jobId)) {
    registerChatJobCtx(jobId, sessionId, ctx);
  }
  if (!ctx && SessionStore.activeId === sessionId) {
    SessionStore.setActiveJobId(sessionId, jobId);
    await attachToChatJob(sessionId, jobId, {
      assistant: payload.assistant,
      events: event ? [event] : [],
      nextSince: payload.nextSince || 0,
      status: status || 'running',
    });
    ctx = findChatJobCtx(jobId, sessionId);
  }
  if (!ctx) return;

  if (event) {
    const seq = event._seq || 0;
    if (seq <= (ctx.lastSeq || 0)) return;
    ctx.lastSeq = seq;
    const result = await handleChatStreamEvent(event, ctx);
    if (result === 'error') {
      await finalizeChatJobCtx(jobId, sessionId, ctx, 'error', payload);
      return;
    }
    if (ctx.streamActive()) savePartialAssistant(sessionId, ctx.assistantMessage);
  }

  if (['done', 'error', 'cancelled'].includes(status)) {
    await finalizeChatJobCtx(jobId, sessionId, ctx, status, payload);
  }
}

async function handleSyncWsMessage(data) {
  if (!data?.type) return;
  switch (data.type) {
    case 'hello':
      await handleSyncWsHello(data);
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
    case 'pong':
      break;
    default:
      break;
  }
}

function reconnectSyncWebSocket() {
  clearTimeout(_syncWsReconnectTimer);
  if (_syncWs) {
    try { _syncWs.close(); } catch {}
    _syncWs = null;
  }
  _syncWsConnected = false;
  connectSyncWebSocket();
}

function connectSyncWebSocket() {
  if (_syncWs && (_syncWs.readyState === WebSocket.OPEN || _syncWs.readyState === WebSocket.CONNECTING)) {
    return;
  }
  clearTimeout(_syncWsReconnectTimer);
  try {
    _syncWs = new WebSocket(aiSyncWsUrl());
  } catch {
    scheduleSyncWsFallback();
    return;
  }

  _syncWs.onopen = () => {
    _syncWsConnected = true;
    if (_syncWsFallbackTimer) {
      clearInterval(_syncWsFallbackTimer);
      _syncWsFallbackTimer = null;
    }
    sendSyncWs({ type: 'resync' });
  };

  _syncWs.onmessage = (ev) => {
    try {
      handleSyncWsMessage(JSON.parse(ev.data));
    } catch (e) {
      console.warn('sync ws parse error', e);
    }
  };

  _syncWs.onclose = () => {
    _syncWsConnected = false;
    _syncWs = null;
    _syncWsReconnectTimer = setTimeout(connectSyncWebSocket, 3000);
    scheduleSyncWsFallback();
  };

  _syncWs.onerror = () => {
    try { _syncWs?.close(); } catch {}
  };
}

function scheduleSyncWsFallback() {
  if (_syncWsFallbackTimer) return;
  refreshSessionViewFromRemote().catch(() => {});
  _syncWsFallbackTimer = setInterval(() => {
    if (_syncWsConnected || document.visibilityState !== 'visible') return;
    refreshSessionViewFromRemote().catch(() => {});
    for (const [jobId, ctx] of _chatJobContexts.entries()) {
      if (!ctx._pollActive) pollChatJob(jobId, ctx.sessionId, ctx);
    }
  }, 15000);
}

function startSyncWebSocket() {
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      connectSyncWebSocket();
      refreshSessionViewFromRemote().catch(() => {});
    } else if (_syncWs) _syncWs.close();
  });
  connectSyncWebSocket();
  setInterval(() => {
    if (_syncWsConnected) sendSyncWs({ type: 'ping' });
  }, 25000);
}

function normalizeStoredMessage(msg) {
  if (!msg || typeof msg !== 'object') return msg;
  const out = { ...msg };
  if (out.role === 'assistant') {
    if (!out.tool_results) out.tool_results = {};
    if (!out.tool_calls) out.tool_calls = [];
  }
  return out;
}

function prepareMessagesForApi(messages) {
  return messages.map((m) => {
    if (m.role === 'user') return { role: 'user', content: m.content };
    if (m.role !== 'assistant') return { ...m };
    const out = { role: 'assistant' };
    if (m.content) out.content = m.content;
    if (m.reasoning_content) out.reasoning_content = m.reasoning_content;
    if (m.tool_calls?.length) {
      out.tool_calls = m.tool_calls;
      out.tool_results = m.tool_results || {};
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
    knowledgeOpen ||
    notificationsOpen ||
    els.sessionsPanel?.classList.contains('open') ||
    els.settingsSidebar?.classList.contains('open') ||
    (els.writeConfirmModal && !els.writeConfirmModal.hidden) ||
    (els.pinModal && !els.pinModal.hidden) ||
    usageDetailOpen,
  );
  document.body.style.overflow = locked ? 'hidden' : '';
}

function openKnowledgeModal() {
  knowledgeOpen = true;
  setOverlayVisible(els.knowledgeModal, true);
  els.knowledgeBtn?.classList.add('active');
  syncBodyScrollLock();
  loadRagPanel();
}

function closeKnowledgeModal() {
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
    if (_syncWsConnected || document.visibilityState !== 'visible') return;
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
    li.className = `session-item${s.id === activeId ? ' active' : ''}`;
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
  return Boolean(
    sessionId
    && streamSessionId === sessionId
    && abortController
    && !abortController.cancelled
  );
}

function isChatUiLocked() {
  return Boolean(
    isLocallyStreaming()
    || (abortController && !abortController.cancelled)
  );
}

function getLiveStreamUi() {
  const live = els.messages?.querySelector('.assistant-wrapper[data-live-stream="1"]');
  if (!live) return null;
  return wrapperToAssistantUi(live);
}

function reconcileStreamUi(ctx) {
  if (!ctx) return null;
  if (ctx.ui?.wrapper?.isConnected) return ctx.ui;
  const live = getLiveStreamUi();
  if (live?.wrapper?.isConnected) {
    ctx.ui = live;
    return live;
  }
  const last = getLastAssistantUi();
  if (last?.wrapper?.isConnected) {
    ctx.ui = last;
    markLiveStreamUi(last);
    return last;
  }
  return ctx.ui;
}

function assistantMessageHasContent(msg) {
  if (!msg) return false;
  return Boolean(
    (msg.content && String(messageText(msg.content) || msg.content).trim())
    || (msg.reasoning_content && String(msg.reasoning_content).trim())
    || (msg.tool_calls && msg.tool_calls.length)
  );
}

function hideAssistantLoading(ui) {
  if (!ui) return;
  const nodes = [];
  if (ui.loading) nodes.push(ui.loading);
  ui.wrapper?.querySelectorAll('.assistant-loading').forEach((el) => nodes.push(el));
  for (const el of nodes) {
    el.classList.add('hidden');
    el.remove();
  }
  ui.loading = null;
}

function syncThinkingBlock(ui, msg) {
  if (!ui?.thinking) return;
  const hasReasoning = Boolean(String(msg?.reasoning_content || '').trim());
  if (!hasReasoning) {
    ui.thinking.classList.add('hidden');
    return;
  }
  hideAssistantLoading(ui);
  ui.thinking.classList.remove('hidden');
  ui.thinking.classList.add('collapsed');
  if (ui.thinkingBody) ui.thinkingBody.textContent = msg.reasoning_content;
  if (ui.thinkingLabel) ui.thinkingLabel.textContent = t('thinking', 'Thinking');
}

function clearLiveStreamChrome(ui) {
  hideAssistantLoading(ui);
  if (!ui) return;
  const hasReasoning = Boolean(String(ui.thinkingBody?.textContent || '').trim());
  if (!hasReasoning) ui.thinking?.classList.add('hidden');
}

function showAssistantLoading(ui) {
  if (!ui?.wrapper) return;
  if (!ui.loading) {
    ui.loading = ui.wrapper.querySelector('.assistant-loading');
  }
  if (!ui.loading) {
    const loading = document.createElement('div');
    loading.className = 'assistant-loading';
    loading.innerHTML = `<span class="typing-dots" aria-hidden="true"><span></span><span></span><span></span></span><span class="typing-label">${t('assistantLoading', '正在思考…')}</span>`;
    ui.wrapper.insertBefore(loading, ui.wrapper.firstChild);
    ui.loading = loading;
  }
  ui.loading.classList.remove('hidden');
}

function findChatJobCtx(jobId, sessionId) {
  let ctx = _chatJobContexts.get(jobId);
  if (ctx) return ctx;
  const pendingKey = `pending:${sessionId}`;
  ctx = _chatJobContexts.get(pendingKey);
  if (ctx) return ctx;
  for (const [, candidate] of _chatJobContexts.entries()) {
    if (candidate.sessionId === sessionId) return candidate;
  }
  return null;
}

function registerChatJobCtx(jobId, sessionId, ctx) {
  const pendingKey = `pending:${sessionId}`;
  _chatJobContexts.delete(pendingKey);
  _chatJobContexts.set(jobId, ctx);
}

function abortActiveChat() {
  const jobId = _activeChatJobId || SessionStore.getActiveJobId(SessionStore.activeId);
  if (jobId) {
    api('DELETE', `/api/ai/chat/jobs/${encodeURIComponent(jobId)}`).catch(() => {});
    SessionStore.clearActiveJobId(SessionStore.activeId);
    syncSessionsToDevice().catch(() => {});
  }
  if (abortController) {
    if (typeof abortController.abort === 'function') abortController.abort();
    else abortController.cancelled = true;
  }
  endChatStream(streamSessionId);
}

function endChatStream(sessionId) {
  if (sessionId && streamSessionId === sessionId) streamSessionId = null;
  abortController = null;
  _activeChatJobId = null;
  if (_chatJobPollTimer) {
    clearTimeout(_chatJobPollTimer);
    _chatJobPollTimer = null;
  }
  els.messages?.querySelectorAll('.assistant-wrapper[data-live-stream="1"]').forEach((el) => {
    clearLiveStreamChrome(wrapperToAssistantUi(el));
    delete el.dataset.liveStream;
  });
  if (els.sendBtn) els.sendBtn.textContent = t('send', 'Send');
}

function wrapperToAssistantUi(wrapper) {
  const thinking = wrapper.querySelector('.thinking-block');
  const toolsBlock = wrapper.querySelector('.tool-calls-block');
  return {
    wrapper,
    loading: wrapper.querySelector('.assistant-loading'),
    thinking,
    thinkingLabel: thinking?.querySelector('.thinking-label'),
    thinkingBody: thinking?.querySelector('.thinking-body'),
    toolsBlock,
    toolsList: toolsBlock?.querySelector('.tool-calls-list'),
    content: wrapper.querySelector('.message.assistant'),
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

function switchSession(id) {
  abortActiveChat();
  SessionStore.setActive(id);
  loadSessionMode();
  renderStoredMessages();
  renderSessionList();
  scheduleSessionSync();
  syncActiveSessionStreaming().catch(() => {});
  closeSessionsDrawer();
}

function createNewSession() {
  abortActiveChat();
  SessionStore.startDraft();
  renderStoredMessages();
  renderSessionList();
  closeSessionsDrawer();
}

function updateModelBadge(model) {
  if (!els.modelBadge) return;
  const label = model || t('modelUnset', 'Not configured');
  els.modelBadge.textContent = label;
  els.modelBadge.classList.toggle('unset', !model);
}

function updateModelBadgeFromSaved() {
  updateModelBadge(savedConfig?.model || '');
}

function formatApiError(raw) {
  const text = String(raw || '').trim();
  if (!text) return t('chatErrorGeneric', '请求失败，请稍后重试。');
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

function showUnsavedConfigWarning() {
  if (!hasUnsavedConfigDraft() || !els.connectionResult) return;
  const hint = t('unsavedConfigHint', '有未保存的设置更改；对话仍使用上次保存的配置。');
  if (!els.connectionResult.textContent?.includes(hint)) {
    els.connectionResult.textContent = hint;
    els.connectionResult.className = 'connection-result warning';
  }
}

function deleteSession(id) {
  SessionStore.remove(id);
  if (!SessionStore.listWithContent().length) {
    SessionStore.startDraft();
  }
  loadSessionMode();
  renderStoredMessages();
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
  secoc: 'paneSecoc',
  scheduler: 'paneScheduler',
  dev: 'paneDev',
};

function normalizeSettingsTab(name) {
  if (!name || name === 'api') return 'model';
  return name;
}

function syncSettingsSaveBar(tabName) {
  const bar = document.getElementById('settingsSaveBar');
  if (!bar) return;
  const show = tabName === 'model' || tabName === 'knowledge';
  bar.hidden = !show;
}

function openSettings(tab) {
  closeCabanaModal();
  closeKnowledgeModal();
  closeSessionsDrawer();
  ensureProviderOptions();
  loadConfig().catch(console.error);
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
  if (tabName === 'scheduler') loadSchedulerPanel();
  if (tabName === 'dev') renderDevPane();
  if (tabName === 'model') loadUsage();
  if (tabName === 'secoc' && typeof TskPanel !== 'undefined') TskPanel.startPoll();
}

function openSettingsTab(tab) {
  openSettings(tab);
}

function closeSettings() {
  if (typeof TskPanel !== 'undefined') TskPanel.stopPoll();
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
      const name = tab.dataset.tab;
      if (typeof TskPanel !== 'undefined') TskPanel.stopPoll();
      activateSettingsTab(name);
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

async function loadRagPanel() {
  const { data } = await api('GET', '/api/ai/rag');
  if (!data.ok || !els.ragDocList) return;
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
      await api('POST', '/api/ai/rag', { operation: 'remove', doc_id: btn.dataset.id });
      loadRagPanel();
    });
  });
}

async function reindexRag() {
  if (!els.ragReindexBtn) return;
  els.ragReindexBtn.disabled = true;
  const { data } = await api('POST', '/api/ai/rag', { operation: 'reindex' });
  els.ragReindexBtn.disabled = false;
  if (data.ok) {
    showToast(tf('ragReindexResult', { indexed: data.indexed, total: data.total }), data.errors?.length ? 'warning' : 'success');
    loadRagPanel();
  } else {
    showToast(data.error || t('ragReindexFailed'), 'error');
  }
}

async function saveRagDoc() {
  const title = (els.ragTitle?.value || '').trim();
  const text = (els.ragText?.value || '').trim();
  if (!text) return;
  const { data } = await api('POST', '/api/ai/rag', { title: title || t('ragNoteDefault'), text });
  if (data.ok) {
    if (els.ragTitle) els.ragTitle.value = '';
    if (els.ragText) els.ragText.value = '';
    showToast(t('saved', '已保存'), 'success');
    loadRagPanel();
  }
}

function showWriteConfirmModal(preview, pendingId) {
  return new Promise((resolve) => {
    if (!els.writeConfirmModal) return resolve({ ok: false, error: 'no modal' });
    els.writeConfirmPreview.textContent = JSON.stringify(preview, null, 2);
    els.writeConfirmModal.hidden = false;
    syncBodyScrollLock();
    const cleanup = () => {
      els.writeConfirmModal.hidden = true;
      syncBodyScrollLock();
      els.writeConfirmOk.removeEventListener('click', onOk);
      els.writeConfirmCancel.removeEventListener('click', onCancel);
      els.writeConfirmClose?.removeEventListener('click', onCancel);
      els.writeConfirmBackdrop?.removeEventListener('click', onCancel);
    };
    const onCancel = () => { cleanup(); resolve({ ok: false, cancelled: true }); };
    const onOk = async () => {
      cleanup();
      const { data } = await api('POST', '/api/ai/write/confirm', { pending_id: pendingId });
      resolve(data);
    };
    els.writeConfirmOk.addEventListener('click', onOk);
    els.writeConfirmCancel.addEventListener('click', onCancel);
    els.writeConfirmClose?.addEventListener('click', onCancel);
    els.writeConfirmBackdrop?.addEventListener('click', onCancel);
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

function renderComposerAttachments() {
  if (!pendingImages.length) {
    els.composerAttachments.classList.add('hidden');
    els.composerAttachments.innerHTML = '';
    return;
  }
  els.composerAttachments.classList.remove('hidden');
  els.composerAttachments.innerHTML = '';
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
  renderComposerAttachments();
}

function renderMarkdownContent(el, text) {
  if (!el || !text) {
    if (el) el.textContent = '';
    return;
  }
  if (typeof Markdown !== 'undefined') {
    el.classList.add('md-content');
    el.innerHTML = Markdown.render(text);
  } else {
    el.textContent = text;
  }
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

function appendUserMessage(content) {
  const div = createMessageElement('user');
  const text = messageText(content);
  const images = messageImages(content);
  renderMessageImages(div, images);
  if (text) {
    const textEl = document.createElement('div');
    textEl.className = 'message-text';
    textEl.textContent = text;
    div.appendChild(textEl);
  }
  els.messages.appendChild(div);
  scrollToBottom();
  return div;
}

function appendAssistantMessage({ withLoading = true } = {}) {
  const wrapper = document.createElement('div');
  wrapper.className = 'message assistant-wrapper';

  let loading = null;
  if (withLoading) {
    loading = document.createElement('div');
    loading.className = 'assistant-loading';
    loading.innerHTML = `<span class="typing-dots" aria-hidden="true"><span></span><span></span><span></span></span><span class="typing-label">${t('assistantLoading', '正在思考…')}</span>`;
    wrapper.appendChild(loading);
  }

  const thinking = document.createElement('div');
  thinking.className = 'thinking-block collapsed hidden';
  thinking.innerHTML = `<div class="thinking-header"><span class="thinking-icon">🧠</span><span class="thinking-label">${t('thinking', 'Thinking')}</span><span class="chevron">▶</span></div><div class="thinking-body"></div>`;
  thinking.querySelector('.thinking-header').addEventListener('click', () => {
    thinking.classList.toggle('collapsed');
  });

  const content = document.createElement('div');
  content.className = 'message assistant md-content';

  const toolsBlock = document.createElement('div');
  toolsBlock.className = 'tool-calls-block collapsed hidden';
  toolsBlock.innerHTML = `
    <div class="tool-calls-header">
      <span class="tool-icon">🔧</span>
      <span class="tool-calls-label">${t('toolCalls', 'Tool calls')}</span>
      <span class="tool-calls-count"></span>
      <span class="chevron">▶</span>
    </div>
    <div class="tool-calls-list"></div>
  `;
  toolsBlock.querySelector('.tool-calls-header').addEventListener('click', () => {
    toolsBlock.classList.toggle('collapsed');
  });

  const toolsList = toolsBlock.querySelector('.tool-calls-list');

  wrapper.appendChild(thinking);
  wrapper.appendChild(toolsBlock);
  wrapper.appendChild(content);
  els.messages.appendChild(wrapper);
  scrollToBottom();
  return {
    wrapper,
    loading,
    thinking,
    thinkingLabel: thinking.querySelector('.thinking-label'),
    thinkingBody: thinking.querySelector('.thinking-body'),
    toolsBlock,
    toolsList,
    content,
  };
}

function scrollToBottom() {
  els.messages.scrollTop = els.messages.scrollHeight;
}

// ---------------------------------------------------------------------------
// Composer slash commands (/status, /tsk, /can, …)
// ---------------------------------------------------------------------------

const SLASH_COMMAND_DEFS = [
  { id: 'status', icon: '🚗', labelKey: 'slashCmdStatus', descKey: 'slashCmdStatusDesc', promptKey: 'qaVehiclePrompt', enrich: 'status' },
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
    openSettingsTab('secoc');
    hideComposerSlashMenu();
    els.chatInput.value = '';
    autoResize();
    return;
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
    openSettingsTab('secoc');
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
      openSettingsTab('secoc');
      return { blockSend: true, handled: true };
    }
    const msg = await buildTskSlashMessage(sub);
    return {
      displayText: trimmed,
      preview: t(tskItem.labelKey, `/tsk ${sub}`),
      historyContent: buildUserContent(msg, []),
    };
  }

  const cmdMatch = trimmed.match(/^\/([a-z]+)\s*$/i);
  if (!cmdMatch) return null;

  const def = findSlashDef(cmdMatch[1]);
  if (!def) return null;

  if (def.action === 'cabana') {
    openCabanaModal();
    return { blockSend: true, handled: true };
  }
  if (def.action === 'secoc') {
    openSettingsTab('secoc');
    return { blockSend: true, handled: true };
  }
  if (def.submenu) return { blockSend: true };

  let msg = def.promptKey ? t(def.promptKey) : trimmed;
  if (def.enrich === 'status') msg = await buildStatusSlashMessage();
  else if (def.enrich === 'help') msg = buildHelpSlashMessage();

  return {
    displayText: trimmed,
    preview: t(def.labelKey, `/${def.id}`),
    historyContent: buildUserContent(msg, []),
    workflow: def.workflow || '',
  };
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
}

// ---------------------------------------------------------------------------
// Streaming chat
// ---------------------------------------------------------------------------

async function sendChat(e) {
  e.preventDefault();
  let text = els.chatInput.value.trim();
  const images = pendingImages.slice();
  if (!text && images.length === 0) return;

  if (abortController) {
    abortActiveChat();
    return;
  }

  const slashResolved = await resolveSlashSend(text);
  if (slashResolved?.blockSend) {
    if (!slashResolved.handled) refreshComposerSlashMenu().catch(() => {});
    return;
  }

  let displayText = text;
  let historyContent = null;
  let sessionPreview = text || t('imageMessage', '图片消息');
  let slashWorkflow = '';

  if (slashResolved) {
    hideComposerSlashMenu();
    displayText = slashResolved.displayText || text;
    sessionPreview = slashResolved.preview || displayText;
    if (slashResolved.historyContent !== undefined) historyContent = slashResolved.historyContent;
    slashWorkflow = slashResolved.workflow || '';
  }

  const workflowForSend = slashWorkflow || pendingWorkflow;
  pendingWorkflow = '';

  SessionStore.ensureSessionOnSend(sessionPreview);
  renderSessionList();

  const content = buildUserContent(displayText, images);
  clearWelcomePanel();
  syncMessagesLayoutMode();
  appendUserMessage(content);
  els.chatInput.value = '';
  clearComposerAttachments();
  autoResize();

  const history = getCurrentMessages();
  let finalHistoryContent = historyContent || content;
  if (historyContent && images.length) {
    const msgText = typeof historyContent === 'string'
      ? historyContent
      : (Array.isArray(historyContent)
        ? (historyContent.find((p) => p?.type === 'text')?.text || '')
        : '');
    finalHistoryContent = buildUserContent(msgText, images);
  }
  history.push({ role: 'user', content: finalHistoryContent });
  saveCurrentMessages(history);
  syncSessionsToDevice().catch(() => {});

  pendingWorkflow = workflowForSend;
  await streamAssistantResponse(history);
  pendingWorkflow = '';
}

function savePartialAssistant(sessionId, assistantMessage) {
  if (SessionStore.activeId !== sessionId) return;
  if (!assistantMessageHasContent(assistantMessage)) return;
  const session = SessionStore.getActive();
  if (!session) return;
  const msgs = (session.messages || []).map(normalizeStoredMessage);
  const partial = {
    role: 'assistant',
    content: assistantMessage.content || '',
    reasoning_content: assistantMessage.reasoning_content || '',
    tool_calls: assistantMessage.tool_calls || [],
    tool_results: assistantMessage.tool_results || {},
  };
  if (msgs[msgs.length - 1]?.role === 'assistant') {
    msgs[msgs.length - 1] = partial;
  } else {
    msgs.push(partial);
  }
  SessionStore.updateMessages(sessionId, msgs.slice(-200));
  if (!_syncWsConnected) scheduleSessionSync();
}

function hydrateAssistantUi(ui, assistantMessage) {
  const text = messageText(assistantMessage.content) || assistantMessage.content || '';
  syncThinkingBlock(ui, assistantMessage);
  if (assistantMessage.tool_calls?.length) {
    hideAssistantLoading(ui);
    ui.toolsBlock.classList.remove('hidden');
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
}

async function handleChatStreamEvent(data, ctx) {
  const ui = reconcileStreamUi(ctx);
  const { assistantMessage, streamActive } = ctx;
  if (!streamActive()) return 'stop';

  if (data.type === 'error') {
    hideAssistantLoading(ui);
    ui.content.textContent = formatApiError(data.error);
    assistantMessage.content = ui.content.textContent;
    return 'error';
  }

  if (data.type === 'reasoning') {
    hideAssistantLoading(ui);
    if (!ctx.thinkingStarted) {
      ctx.thinkingStarted = true;
      ui.thinking.classList.remove('hidden');
      ui.thinkingLabel.textContent = t('thinkingActive', 'Thinking…');
    }
    assistantMessage.reasoning_content += data.delta;
    ui.thinkingBody.textContent += data.delta;
    scrollToBottom();
  }

  if (data.type === 'content') {
    hideAssistantLoading(ui);
    if (ctx.thinkingStarted) {
      ui.thinking.classList.add('collapsed');
      ui.thinkingLabel.textContent = t('thinking', 'Thinking');
    }
    ctx.contentStarted = true;
    assistantMessage.content += data.delta;
    ui.content.textContent += data.delta;
    scrollToBottom();
  }

  if (data.type === 'tool_call') {
    hideAssistantLoading(ui);
    if (ctx.thinkingStarted) {
      ui.thinking.classList.add('collapsed');
      ui.thinkingLabel.textContent = t('thinking', 'Thinking');
    } else {
      ui.thinking.classList.add('hidden');
    }
    ui.toolsBlock.classList.remove('hidden');
    renderToolCall(ui.toolsList, data.id, data.name, data.arguments, null);
    updateToolCallsSummary(ui.toolsBlock);
    if (!assistantMessage.tool_calls.some((tc) => tc.id === data.id)) {
      assistantMessage.tool_calls.push({
        id: data.id,
        type: 'function',
        function: { name: data.name, arguments: data.arguments },
      });
    }
  }

  if (data.type === 'tool_result') {
    hideAssistantLoading(ui);
    let result = data.result;
    if (result?.needs_confirmation && result.pending_id) {
      const { data: confirmed } = await api('POST', '/api/ai/write/confirm', { pending_id: result.pending_id });
      result = confirmed;
    }
    assistantMessage.tool_results[data.id] = result;
    updateToolCallResult(ui.toolsList, data.id, result);
  }

  if (data.type === 'usage') {
    renderUsage(ui.wrapper, data.usage);
    if (els.settingsSidebar?.classList.contains('open')) loadUsage();
  }

  if (data.type === 'done') {
    hideAssistantLoading(ui);
    syncThinkingBlock(ui, assistantMessage);
    if (data.resolvedModel) updateModelBadge(data.resolvedModel);
  }

  return 'continue';
}

function watchChatJob(jobId, sessionId, ctx) {
  ctx.lastSeq = Math.max(ctx.lastSeq || 0, ctx.since || 0);
  ctx.since = ctx.lastSeq;
  ctx._pollActive = false;
  registerChatJobCtx(jobId, sessionId, ctx);
  if (!_syncWsConnected) pollChatJob(jobId, sessionId, ctx);
}

function pollChatJob(jobId, sessionId, ctx) {
  if (_syncWsConnected) return;
  ctx._pollActive = true;
  let since = ctx.since || 0;
  let finished = false;

  const poll = async () => {
    if (finished) return;
    const streamActive = ctx.streamActive;
    if (!streamActive() && SessionStore.getActiveJobId(sessionId) !== jobId) {
      finished = true;
      return;
    }

    try {
      const { data } = await api('GET', `/api/ai/chat/jobs/${encodeURIComponent(jobId)}?since=${since}`);
      if (!data?.ok) {
        if (!streamActive()) finished = true;
        else _chatJobPollTimer = setTimeout(poll, 1000);
        return;
      }

      for (const ev of data.events || []) {
        since = Math.max(since, ev._seq || since);
        const result = await handleChatStreamEvent(ev, ctx);
        if (result === 'error') {
          finished = true;
          _chatJobContexts.delete(jobId);
          if (streamActive()) finishAssistant(ctx.ui, ctx.assistantMessage, sessionId);
          SessionStore.clearActiveJobId(sessionId);
          endChatStream(sessionId);
          syncSessionsToDevice().catch(() => {});
          return;
        }
        if (result === 'stop') {
          finished = true;
          return;
        }
      }

      if (streamActive()) savePartialAssistant(sessionId, ctx.assistantMessage);

      if (['done', 'error', 'cancelled'].includes(data.status)) {
        finished = true;
        _chatJobContexts.delete(jobId);
        if (data.status === 'done' && streamActive()) {
          finishAssistant(ctx.ui, ctx.assistantMessage, sessionId);
        } else if (data.status === 'error' && streamActive()) {
          ctx.assistantMessage.content = formatApiError(data.error || 'Error');
          finishAssistant(ctx.ui, ctx.assistantMessage, sessionId);
        } else if (data.status === 'cancelled' && streamActive() && ctx.ui.wrapper?.isConnected) {
          ctx.ui.wrapper.remove();
        }
        SessionStore.clearActiveJobId(sessionId);
        endChatStream(sessionId);
        syncSessionsToDevice().catch(() => {});
        return;
      }

      _chatJobPollTimer = setTimeout(poll, 400);
    } catch {
      if (!finished) _chatJobPollTimer = setTimeout(poll, 1000);
    }
  };

  poll();
}

async function streamAssistantResponse(messages) {
  const sessionId = SessionStore.activeId;
  streamSessionId = sessionId;
  abortController = { cancelled: false };
  els.sendBtn.textContent = t('stop', 'Stop');

  const streamActive = () => (
    SessionStore.activeId === sessionId
    && abortController
    && !abortController.cancelled
  );

  const hasImages = messages.some(
    (m) => m.role === 'user' && Array.isArray(m.content) && m.content.some((p) => p.type === 'image_url'),
  );
  const useTools = !hasImages;
  const maxToolRounds = 'infinite';
  const workflowId = pendingWorkflow;
  pendingWorkflow = '';

  const ui = appendAssistantMessage();
  showAssistantLoading(ui);
  markLiveStreamUi(ui);
  const assistantMessage = { role: 'assistant', content: '', reasoning_content: '', tool_calls: [], tool_results: {} };

  const ctx = {
    ui,
    assistantMessage,
    sessionId,
    streamActive,
    thinkingStarted: false,
    contentStarted: false,
    since: 0,
  };
  _chatJobContexts.set(`pending:${sessionId}`, ctx);

  try {
    const { data: startData } = await api('POST', '/api/ai/chat/jobs', {
      sessionId,
      messages: prepareMessagesForApi(messages),
      tools: useTools,
      mode: CHAT_MODE,
      workflow: workflowId || undefined,
      maxToolRounds,
    });

    if (!startData?.ok || !startData.jobId) {
      _chatJobContexts.delete(`pending:${sessionId}`);
      if (!streamActive()) return;
      hideAssistantLoading(ui);
      ui.content.textContent = formatApiError(startData?.error || 'Failed to start chat job');
      assistantMessage.content = ui.content.textContent;
      finishAssistant(ui, assistantMessage, sessionId);
      endChatStream(sessionId);
      return;
    }

    const jobId = startData.jobId;
    _activeChatJobId = jobId;
    SessionStore.setActiveJobId(sessionId, jobId);
    syncSessionsToDevice().catch(() => {});
    watchChatJob(jobId, sessionId, ctx);
  } catch (err) {
    _chatJobContexts.delete(`pending:${sessionId}`);
    if (streamActive()) {
      hideAssistantLoading(ui);
      ui.content.textContent = `Error: ${err.message}`;
      assistantMessage.content = ui.content.textContent;
      finishAssistant(ui, assistantMessage, sessionId);
    } else if (ui.wrapper?.isConnected) {
      ui.wrapper.remove();
    }
    endChatStream(sessionId);
  }
}

function commitAssistantMessage(sessionId, assistantMessage) {
  if (sessionId && SessionStore.activeId !== sessionId) return;
  const history = getCurrentMessages();
  const normalized = normalizeStoredMessage({ ...assistantMessage });
  if (history[history.length - 1]?.role === 'assistant') {
    history[history.length - 1] = normalized;
  } else {
    history.push(normalized);
  }
  saveCurrentMessages(history);
}

async function attachToChatJob(sessionId, jobId, initialData) {
  if (_activeChatJobId === jobId && abortController) return;
  if (isLocallyStreaming(sessionId) && findChatJobCtx(jobId, sessionId)) return;

  const messages = getCurrentMessages();
  const last = messages[messages.length - 1];
  let ui;
  let assistantMessage;

  if (last?.role === 'assistant' && assistantMessageHasContent(last)) {
    ui = getLiveStreamUi() || getLastAssistantUi() || appendAssistantMessage();
    assistantMessage = normalizeStoredMessage({ ...last });
    hydrateAssistantUi(ui, assistantMessage);
  } else if (last?.role === 'user') {
    ui = getLiveStreamUi() || appendAssistantMessage();
    if (!getLiveStreamUi()) showAssistantLoading(ui);
    assistantMessage = {
      role: 'assistant',
      content: '',
      reasoning_content: '',
      tool_calls: [],
      tool_results: {},
      ...(initialData?.assistant || {}),
    };
    if (initialData?.assistant) {
      hydrateAssistantUi(ui, assistantMessage);
    }
  } else if (last?.role === 'assistant') {
    ui = getLiveStreamUi() || appendAssistantMessage();
    if (!getLiveStreamUi()) showAssistantLoading(ui);
    assistantMessage = {
      role: 'assistant',
      content: '',
      reasoning_content: '',
      tool_calls: [],
      tool_results: {},
      ...(initialData?.assistant || {}),
    };
    if (initialData?.assistant) {
      hydrateAssistantUi(ui, assistantMessage);
    }
  } else {
    return;
  }

  markLiveStreamUi(ui);
  streamSessionId = sessionId;
  abortController = { cancelled: false };
  _activeChatJobId = jobId;
  if (els.sendBtn) els.sendBtn.textContent = t('stop', 'Stop');

  const since = initialData?.nextSince || 0;

  const streamCtx = {
    ui,
    assistantMessage,
    sessionId,
    streamActive: () => (
      SessionStore.activeId === sessionId
      && abortController
      && !abortController.cancelled
    ),
    thinkingStarted: Boolean(assistantMessage.reasoning_content),
    contentStarted: Boolean(assistantMessage.content),
    since,
    lastSeq: since,
  };

  if (initialData?.events?.length) {
    for (const ev of initialData.events) {
      const seq = ev._seq || 0;
      if (seq <= streamCtx.lastSeq) continue;
      streamCtx.lastSeq = seq;
      await handleChatStreamEvent(ev, streamCtx);
    }
  }

  watchChatJob(jobId, sessionId, streamCtx);
}

async function syncActiveSessionStreaming() {
  const sessionId = SessionStore.activeId;
  if (!sessionId) return;
  if (isChatUiLocked()) return;

  let jobId = SessionStore.getActiveJobId(sessionId);
  if (!jobId) {
    const { data: listData } = await api('GET', `/api/ai/chat/jobs?sessionId=${encodeURIComponent(sessionId)}`);
    jobId = listData?.jobs?.[0]?.id;
    if (jobId) SessionStore.setActiveJobId(sessionId, jobId);
  }
  if (!jobId) return;
  if (_activeChatJobId === jobId && abortController) return;

  const { data } = await api('GET', `/api/ai/chat/jobs/${encodeURIComponent(jobId)}?since=0`);
  if (!data?.ok) {
    SessionStore.clearActiveJobId(sessionId);
    return;
  }

  if (data.status === 'done') {
    commitAssistantMessage(sessionId, normalizeStoredMessage({
      role: 'assistant',
      content: '',
      reasoning_content: '',
      tool_calls: [],
      tool_results: {},
      ...(data.assistant || {}),
    }));
    SessionStore.clearActiveJobId(sessionId);
    renderStoredMessages();
    syncSessionsToDevice().catch(() => {});
    return;
  }

  if (data.status !== 'running') {
    SessionStore.clearActiveJobId(sessionId);
    return;
  }

  await attachToChatJob(sessionId, jobId, data);
}

function finishAssistant(ui, assistantMessage, sessionId) {
  if (sessionId && SessionStore.activeId !== sessionId) return;
  clearLiveStreamChrome(ui);
  hideAssistantLoading(ui);
  syncThinkingBlock(ui, assistantMessage);
  if (!assistantMessage.content && !assistantMessage.reasoning_content && assistantMessage.tool_calls.length === 0) {
    assistantMessage.content = t('noResponse', 'No response');
  }
  const text = messageText(assistantMessage.content) || assistantMessage.content || '';
  if (text) {
    renderMarkdownContent(ui.content, text);
  } else {
    ui.content.textContent = '';
  }
  if (ui?.wrapper) delete ui.wrapper.dataset.liveStream;
  commitAssistantMessage(sessionId, assistantMessage);
  syncSessionsToDevice().catch(() => {});
}

function updateToolCallsSummary(toolsBlock) {
  const list = toolsBlock.querySelector('.tool-calls-list');
  const count = list.querySelectorAll('.tool-call').length;
  const countEl = toolsBlock.querySelector('.tool-calls-count');
  if (countEl) {
    countEl.textContent = count ? `(${count})` : '';
  }
}

function renderToolCall(container, id, name, args, result) {
  const existing = container.querySelector(`[data-tool-id="${id}"]`);
  if (existing) {
    if (result !== undefined && result !== null) {
      updateToolCallResult(container, id, result);
    }
    return;
  }
  const div = document.createElement('div');
  div.className = 'tool-call collapsed';
  div.dataset.toolId = id;
  div.innerHTML = `
    <div class="tool-call-header"><span class="tool-icon">🔧</span><span class="tool-name">${escapeHtml(name)}</span><span class="chevron">▶</span></div>
    <div class="tool-call-body">
      <div class="tool-section"><label>${t('toolArgs', 'Arguments')}</label><pre class="tool-args"></pre></div>
      <div class="tool-section tool-result-section${result !== undefined && result !== null ? '' : ' hidden'}"><label>${t('toolResult', 'Result')}</label><pre class="tool-result"></pre></div>
    </div>
  `;
  div.querySelector('.tool-args').textContent = formatJson(args);
  if (result !== undefined && result !== null) {
    if (result.ui_card?.type === 'tsk') {
      updateToolCallResult(container, id, result);
      return;
    }
    div.querySelector('.tool-result').textContent = formatJson(result);
  }
  div.querySelector('.tool-call-header').addEventListener('click', () => {
    const wasCollapsed = div.classList.contains('collapsed');
    div.classList.toggle('collapsed');
    if (wasCollapsed) {
      requestAnimationFrame(() => {
        div.querySelector('.tool-call-body')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      });
    }
  });
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
  section.classList.remove('hidden');
  pre?.classList.remove('hidden');
  div.querySelector('.tsk-progress-card')?.remove();
  if (pre) pre.textContent = formatJson(result);
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
  el.querySelector('[data-open-secoc]')?.addEventListener('click', () => openSettingsTab('secoc'));
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

function renderUsage(wrapper, usage) {
  let el = wrapper.querySelector('.usage-badge');
  if (!el) {
    el = document.createElement('div');
    el.className = 'usage-badge';
    wrapper.appendChild(el);
  }
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

function getConfigPayload() {
  return {
    provider: els.providerSelect.value,
    model: modelManual ? els.modelInput.value.trim() : els.modelSelect.value,
    apiKey: els.apiKeyInput.value.trim(),
    baseUrl: els.baseUrlInput.value.trim(),
    systemPrompt: els.systemPromptInput.value.trim(),
    temperature: parseFloat(els.temperatureInput.value),
    topP: parseFloat(els.topPInput.value),
    maxTokens: parseInt(els.maxTokensInput.value, 10),
    thinkingEnabled: els.thinkingToggle.checked,
    thinkingKeep: '',
    webPin: els.webPinInput?.value?.trim() || '',
    timezone: els.timezoneSelect?.value || 'Asia/Shanghai',
    embeddingMode: els.embeddingModeSelect?.value || 'same',
    embeddingProvider: els.embeddingProviderSelect?.value || 'siliconflow',
    embeddingModel: embeddingModelManual
      ? (els.embeddingModelInput?.value?.trim() || '')
      : (els.embeddingModelSelect?.value || els.embeddingModelInput?.value?.trim() || ''),
    embeddingApiKey: els.embeddingApiKeyInput?.value?.trim() || '',
    embeddingBaseUrl: els.embeddingBaseUrlInput?.value?.trim() || '',
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

function updateConfigSaveHint() {
  const el = $('#changesHint');
  if (!el) return;
  const map = {
    idle: 'configHintManual',
    dirty: 'configHintDirty',
    saving: 'configHintSaving',
    saved: 'configHintSaved',
    error: 'configHintSaveError',
  };
  el.textContent = t(map[configSaveState] || 'configHintManual', t('changesStoppedHint'));
  el.className = `hint-box config-save-hint ${configSaveState}`;
}

function persistConfigDraft() {
  const draft = getConfigPayload();
  const safe = { ...draft };
  if (safe.apiKey?.startsWith('•')) delete safe.apiKey;
  if (safe.embeddingApiKey?.startsWith('•')) delete safe.embeddingApiKey;
  if (safe.webPin?.startsWith('•')) delete safe.webPin;
  LocalPrefs.setConfigDraft(safe);
  if (configSaveState !== 'saving') {
    configSaveState = 'dirty';
    updateConfigSaveHint();
  }
  showUnsavedConfigWarning();
}

function bindConfigPersistence() {
  const fields = [
    els.providerSelect,
    els.modelSelect,
    els.modelInput,
    els.apiKeyInput,
    els.baseUrlInput,
    els.systemPromptInput,
    els.temperatureInput,
    els.topPInput,
    els.maxTokensInput,
    els.thinkingToggle,
    els.webPinInput,
    els.timezoneSelect,
    els.embeddingModeSelect,
    els.embeddingProviderSelect,
    els.embeddingModelSelect,
    els.embeddingModelInput,
    els.embeddingApiKeyInput,
    els.embeddingBaseUrlInput,
  ].filter(Boolean);
  for (const field of fields) {
    const evt = field.tagName === 'SELECT' || field.type === 'checkbox' ? 'change' : 'input';
    field.addEventListener(evt, () => persistConfigDraft());
  }
}

function reconcileConfigDraft(serverConfig) {
  const draft = LocalPrefs.getConfigDraft();
  if (!draft || !serverConfig) return false;
  const keys = [
    'provider', 'model', 'baseUrl', 'systemPrompt', 'temperature', 'topP', 'maxTokens',
    'thinkingEnabled', 'embeddingMode', 'embeddingProvider', 'embeddingModel', 'embeddingBaseUrl',
  ];
  const differs = keys.some((k) => {
    const d = draft[k];
    const s = serverConfig[k];
    if (d === undefined || d === null || d === '') return false;
    return String(d) !== String(s ?? '');
  });
  const hasNewSecret = ['apiKey', 'embeddingApiKey', 'webPin'].some((k) => {
    const v = draft[k];
    return v && !String(v).startsWith('•');
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
  if (!modelManual) {
    const found = models.find((m) => (m.id || m) === target);
    if (found) {
      els.modelSelect.value = target;
      setModelMode(false);
      return;
    }
  }
  setModelMode(true);
  els.modelInput.value = target;
}

function canFetchModelsFromForm() {
  if (configured) return true;
  const payload = getConfigPayload();
  if (payload.provider === 'custom' && !payload.baseUrl) {
    return false;
  }
  const hasNewKey = payload.apiKey && !payload.apiKey.startsWith('•');
  const hasStoredKey = payload.apiKey && payload.apiKey.startsWith('•');
  return hasNewKey || hasStoredKey;
}

function primeModelsFromCatalog(provider) {
  const cat = catalogModelsForProvider(provider || els.providerSelect?.value);
  if (!cat.length) return;
  models = cat;
  renderModelSelect();
}

async function ensureModelsLoaded(savedModel, opts = {}) {
  const refresh = opts.refresh !== false;
  const provider = els.providerSelect?.value;
  const target = savedModel || defaults[provider] || '';
  if (!models.length) {
    primeModelsFromCatalog(provider);
  }
  if (refresh && canFetchModelsFromForm()) {
    await fetchModels({ savedModel: target });
  } else {
    await applySavedModelSelection(target);
  }
  const current = modelManual ? els.modelInput?.value?.trim() : els.modelSelect?.value;
  if (savedConfig?.model) updateModelBadgeFromSaved();
  else updateModelBadge(current || target);
}

function providerDisplayName(id) {
  if (providerLabels[id]) return providerLabels[id];
  const key = `provider_${id}`;
  const label = t(key, '');
  return label || id;
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
  if (!els.embeddingModelSelect) return;
  if (!embeddingModels.length) {
    els.embeddingModelSelect.innerHTML = `<option value="">${t('noModels', 'No models loaded')}</option>`;
    return;
  }
  const current = els.embeddingModelSelect.value || els.embeddingModelInput?.value || '';
  els.embeddingModelSelect.innerHTML = embeddingModels.map((m) => {
    const id = m.id || m;
    return `<option value="${id}">${id}</option>`;
  }).join('');
  if (current) els.embeddingModelSelect.value = current;
}

function setEmbeddingModelMode(manual) {
  embeddingModelManual = manual;
  els.embeddingModelSelect?.classList.toggle('hidden', manual);
  els.embeddingModelInput?.classList.toggle('hidden', !manual);
  if (els.embeddingModelModeBtn) {
    els.embeddingModelModeBtn.textContent = manual ? t('dropdown', 'Dropdown') : t('manual', 'Manual');
  }
}

function applyEmbeddingModelSelection(savedModel) {
  const provider = getActiveEmbeddingProvider();
  const separate = els.embeddingModeSelect?.value === 'separate';
  const target = savedModel || embeddingDefaults[provider] || '';
  if (!target) {
    if (embeddingModels.length && !embeddingModelManual) {
      els.embeddingModelSelect.value = embeddingModels[0].id || embeddingModels[0];
    }
    return;
  }
  if (!embeddingModelManual) {
    const found = embeddingModels.find((m) => (m.id || m) === target);
    if (found) {
      els.embeddingModelSelect.value = target;
      setEmbeddingModelMode(false);
      return;
    }
  }
  setEmbeddingModelMode(true);
  if (els.embeddingModelInput) els.embeddingModelInput.value = target;
}

function refreshEmbeddingModels() {
  const separate = els.embeddingModeSelect?.value === 'separate';
  const provider = getActiveEmbeddingProvider();
  embeddingModels = embeddingCatalogForProvider(provider, !separate);
  renderEmbeddingModelSelect();
  if (!embeddingModelManual && els.embeddingModelSelect && !els.embeddingModelSelect.value && embeddingModels.length) {
    els.embeddingModelSelect.value = embeddingModels[0].id || embeddingModels[0];
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
  if (modelManual) {
    if (!els.modelInput.value.trim()) {
      els.modelInput.value = defaultModel;
    }
  } else if (!els.modelSelect.value) {
    els.modelSelect.value = defaultModel;
  }
}

function showConfigureHint() {
  if (configured) {
    els.connectionResult.textContent = '';
    els.connectionResult.className = 'connection-result';
    return;
  }
  const msg = configureError || t('configureHint', 'Set API key and Base URL (for custom) then save.');
  els.connectionResult.textContent = msg;
  els.connectionResult.classList.add('warning');
}

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
  els.temperatureInput.value = c.temperature ?? 0.7;
  els.topPInput.value = c.topP ?? 1.0;
  els.maxTokensInput.value = c.maxTokens ?? 4096;
  els.thinkingToggle.checked = !!c.thinkingEnabled;
  if (els.webPinInput) els.webPinInput.value = c.webPin || '';
  if (els.timezoneSelect) {
    renderTimezoneSelect(c.timezone || 'Asia/Shanghai');
  }
  if (els.embeddingModeSelect) els.embeddingModeSelect.value = c.embeddingMode || 'same';
  if (els.embeddingModelInput) {
    els.embeddingModelInput.value = c.embeddingModel || '';
  }
  if (els.embeddingProviderSelect) {
    const ep = c.embeddingProvider || 'siliconflow';
    if (embeddingProviders.includes(ep)) els.embeddingProviderSelect.value = ep;
    else els.embeddingProviderSelect.value = 'siliconflow';
  }
  if (els.embeddingApiKeyInput) els.embeddingApiKeyInput.value = c.embeddingApiKey || '';
  if (els.embeddingBaseUrlInput) els.embeddingBaseUrlInput.value = c.embeddingBaseUrl || '';
  onEmbeddingModeChange();
  onProviderChange();
  refreshEmbeddingModels();
  applyEmbeddingModelSelection(c.embeddingModel || embeddingDefaults[getActiveEmbeddingProvider()] || '');
}

async function loadBootstrap() {
  const { data } = await api('GET', '/api/ai/bootstrap');
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
  pinRequired = !!data.pinRequired;
  hostEnvironment = data.hostEnvironment || hostEnvironment;
  applyHeaderChrome();
  applyStatusPill(data);
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
  await ensureModelsLoaded(savedModel, { refresh: !gotLiveModels });
  refreshEmbeddingModels();
  applyEmbeddingModelSelection(savedConfig?.embeddingModel || '');

  showConfigureHint();
  if (data.onboarding?.showWizard) {
    openOnboardingWizard();
  }
  await loadUsage();
}

async function loadConfig() {
  const { data } = await api('GET', '/api/ai/config');
  if (!data.ok) return;
  await applyServerConfig(data.config, { keepDraft: configSaveState === 'dirty' });

  const c = savedConfig;
  const savedModel = c.model || defaults[c.provider] || '';
  if (canFetchModelsFromForm()) {
    await fetchModels();
    await applySavedModelSelection(savedModel);
  } else if (savedModel) {
    await applySavedModelSelection(savedModel);
    renderModelSelect();
  } else {
    applyDefaultModelForProvider();
    renderModelSelect();
  }

  showConfigureHint();
  await loadUsage();
}

function setModelMode(manual) {
  modelManual = manual;
  els.modelSelect.classList.toggle('hidden', manual);
  els.modelInput.classList.toggle('hidden', !manual);
  els.modelModeBtn.textContent = manual ? t('dropdown', 'Dropdown') : t('manual', 'Manual');
  refreshUsageForCurrentModel();
  persistConfigDraft();
}

async function fetchModels(opts = {}) {
  const savedModel = opts.savedModel ?? (modelManual ? els.modelInput?.value?.trim() : els.modelSelect?.value) ?? '';
  if (!canFetchModelsFromForm()) {
    models = catalogModelsForProvider(els.providerSelect.value);
    renderModelSelect();
    if (savedModel) await applySavedModelSelection(savedModel);
    else applyDefaultModelForProvider();
    showConfigureHint();
    return;
  }

  els.modelSelect.innerHTML = `<option value="">${t('loadingModels', 'Loading...')}</option>`;
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
  renderModelSelect();
  if (savedModel) await applySavedModelSelection(savedModel);
  if (!data.ok && data.error) {
    els.connectionResult.textContent = data.error;
    els.connectionResult.className = 'connection-result error';
  } else {
    showConfigureHint();
  }
}

function renderModelSelect() {
  if (models.length === 0) {
    els.modelSelect.innerHTML = `<option value="">${t('noModels', 'No models loaded')}</option>`;
    return;
  }
  const current = els.modelSelect.value || els.modelInput.value;
  els.modelSelect.innerHTML = models.map(m => {
    const id = m.id || m;
    return `<option value="${id}">${id}</option>`;
  }).join('');
  if (current) els.modelSelect.value = current;
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
    if (!embeddingModelManual && els.embeddingModelSelect && !els.embeddingModelSelect.value) {
      applyEmbeddingModelSelection(embeddingDefaults[provider] || '');
    }
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
  applyEmbeddingModelSelection(els.embeddingModelInput?.value || els.embeddingModelSelect?.value || '');
}

function onEmbeddingProviderChange() {
  onEmbeddingModeChange();
}

async function saveConfig(opts = {}) {
  const silent = !!opts.silent;
  if (configSaveInFlight) return;
  const body = getConfigPayload();
  configSaveInFlight = true;
  configSaveState = 'saving';
  updateConfigSaveHint();
  const { status, data } = await api('POST', '/api/ai/config', body);
  configSaveInFlight = false;
  if (data.ok) {
    configured = !!data.configured;
    configureError = data.configureError || '';
    LocalPrefs.clearConfigDraft();
    await loadConfig();
    configSaveState = 'saved';
    updateConfigSaveHint();
    updateModelBadgeFromSaved();
    if (!silent) {
      showToast(t('saved', 'Saved'), 'success');
    }
    if (configured) {
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
    if (els.connectionResult) {
      els.connectionResult.textContent = msg;
      els.connectionResult.className = 'connection-result warning';
    }
    if (!silent) showToast(msg, 'warning');
    return false;
  }

  if (els.connectionResult) {
    els.connectionResult.textContent = t('testing', 'Testing...');
    els.connectionResult.className = 'connection-result';
  }
  const { data } = await api('POST', '/api/ai/test_connection', payload);
  if (!data.ok) {
    const msg = formatApiError(data.error || t('connectionFailed', 'Connection failed'));
    configureError = data.error || msg;
    configured = false;
    if (els.connectionResult) {
      els.connectionResult.textContent = msg;
      els.connectionResult.className = 'connection-result error';
    }
    if (!silent) showToast(msg.split('\n')[0], 'error');
    return false;
  }
  configured = true;
  configureError = '';
  if (els.connectionResult) {
    els.connectionResult.textContent = data.message || t('connectionOk', 'Connection OK');
    els.connectionResult.className = `connection-result ${data.model_available ? 'success' : 'warning'}`;
  }
  if (!silent) {
    showToast(data.message || t('connectionOk', 'Connection OK'), data.model_available ? 'success' : 'warning');
  }
  return true;
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
    ? `<p class="dev-env-hint muted">${t('devPackageInstallHint', '一键安装: curl -fsSL https://raw.githubusercontent.com/mouxangithub/ai/main/install/install.sh | bash')}</p>`
    : '';
  return rows + hint + installHint;
}

function renderForkDetectCard(fork) {
  if (!fork || !fork.ok) {
    return `<p class="dev-empty">${escapeHtml(fork?.error || t('devForkLoadFail', '无法扫描 fork'))}</p>`;
  }
  const scan = fork.scan || {};
  const analysis = fork.analysis || {};
  const lines = [
    ['识别', `${fork.fork_label || fork.fork_id} (${fork.confidence || '—'})`],
    ['模式', fork.mode === 'ai_cached' ? t('devForkModeAi', 'AI 已分析') : t('devForkModeScan', '仓库扫描')],
    ['分支', fork.git_branch || '—'],
    ['特征目录', (scan.distinctive_dirs || []).slice(0, 4).join(', ') || '—'],
    ['Param 前缀', Object.keys(scan.param_prefixes || {}).slice(0, 5).join(', ') || '—'],
  ];
  if (analysis.summary) {
    lines.push(['AI 摘要', analysis.summary.slice(0, 120)]);
  }
  const rows = lines.map(([label, val]) => `
    <div class="dev-kv">
      <span class="dev-kv-label">${escapeHtml(label)}</span>
      <span class="dev-kv-value">${escapeHtml(String(val))}</span>
    </div>`).join('');
  const reasons = (fork.reasons || []).slice(0, 3).join(' · ');
  const hint = reasons ? `<p class="dev-env-hint muted">${escapeHtml(reasons)}</p>` : '';
  const aiHint = fork.hint ? `<p class="dev-env-hint">${escapeHtml(fork.hint)}</p>` : '';
  return rows + hint + aiHint;
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
  if (els.forkDetectBox) els.forkDetectBox.innerHTML = renderForkDetectCard(fork);
  if (els.devForkBadge) els.devForkBadge.textContent = fork?.fork_id || '—';
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
  els.devForkSyncBtn.disabled = true;
  els.devForkRefreshBtn.disabled = true;
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
    els.devForkSyncBtn.disabled = false;
    els.devForkRefreshBtn.disabled = false;
  }
}

function openOnboardingWizard() {
  if (!els.onboardingModal) return;
  const sel = els.onboardingProvider;
  if (sel && providers.length) {
    sel.innerHTML = providers.map((p) => `<option value="${escapeHtml(p)}">${escapeHtml(providerLabels[p] || p)}</option>`).join('');
    const cur = els.providerSelect?.value || providers[0];
    if (providers.includes(cur)) sel.value = cur;
  }
  if (els.onboardingModel) {
    const p = sel?.value || 'opencode-zen';
    els.onboardingModel.value = defaults[p] || modelCatalog[p]?.[0] || 'deepseek-v4-flash';
  }
  if (els.onboardingResult) els.onboardingResult.textContent = '';
  els.onboardingModal.hidden = false;
}

function closeOnboardingWizard() {
  if (els.onboardingModal) els.onboardingModal.hidden = true;
}

async function saveOnboardingWizard() {
  const provider = els.onboardingProvider?.value || 'opencode-zen';
  const apiKey = els.onboardingApiKey?.value?.trim() || '';
  const model = els.onboardingModel?.value?.trim() || '';
  if (!apiKey || !model) {
    if (els.onboardingResult) els.onboardingResult.textContent = t('onboardingMissing', '请填写 API Key 和模型');
    return;
  }
  const payload = { provider, apiKey, model };
  const { data } = await api('POST', '/api/ai/config', payload);
  if (!data.ok) {
    if (els.onboardingResult) els.onboardingResult.textContent = data.error || t('saveFailed', '保存失败');
    return;
  }
  await api('POST', '/api/ai/onboarding/complete', {});
  configured = !!data.configured;
  closeOnboardingWizard();
  showToast(t('onboardingDone', '配置已保存，可以开始对话'));
  await loadBootstrap();
}

async function testOnboardingWizard() {
  const provider = els.onboardingProvider?.value || 'opencode-zen';
  const apiKey = els.onboardingApiKey?.value?.trim() || '';
  const model = els.onboardingModel?.value?.trim() || '';
  if (els.onboardingResult) els.onboardingResult.textContent = t('testing', '测试中…');
  const { data } = await api('POST', '/api/ai/test', { provider, apiKey, model });
  if (els.onboardingResult) {
    els.onboardingResult.textContent = data.ok
      ? t('connectionOk', '连接成功')
      : (data.error || t('connectionFail', '连接失败'));
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
    if (els.devPackageVersionBadge) {
      els.devPackageVersionBadge.textContent = pkg?.version ? `v${pkg.version}` : '—';
    }
    if (els.devPackageUpdateBtn) {
      els.devPackageUpdateBtn.hidden = !pkg?.update_available;
      els.devPackageUpdateBtn.disabled = false;
    }

    if (els.forkDetectBox) {
      els.forkDetectBox.innerHTML = renderForkDetectCard(fork);
    }
    if (els.devForkBadge) {
      els.devForkBadge.textContent = fork?.fork_id || '—';
    }

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
}

async function loadStatus() {
  const { data } = await api('GET', '/api/ai/status');
  if (!data.ok) return;
  state = data;
  applyStatusPill(data);
}

function startStatusPolling() {
  const tick = async () => {
    if (!_syncWsConnected && document.visibilityState === 'visible') {
      await loadStatus().catch(() => {});
    }
    const ms = _syncWsConnected ? 120000 : 15000;
    _statusPollTimer = setTimeout(tick, ms);
  };
  clearTimeout(_statusPollTimer);
  tick();
}

async function loadUsage() {
  if (!els.usageGrid) return;
  const { data } = await api('GET', '/api/ai/usage');
  if (!data.ok || !data.usage) return;
  usageData = data.usage;
  refreshUsageForCurrentModel();
  if (usageDetailOpen) renderUsageDetailModal();
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

function usageStatCols({ tokensAsM = true } = {}) {
  const fmtTok = tokensAsM ? fmtTokenNum : fmtUsageNum;
  return [
    { label: t('usageCalls'), render: (r) => fmtUsageNum(r.calls) },
    { label: t('usagePrompt'), render: (r) => fmtTok(r.prompt_tokens) },
    { label: t('usageCompletion'), render: (r) => fmtTok(r.completion_tokens) },
    { label: t('usageTotal'), render: (r) => fmtTok(r.total_tokens) },
  ];
}

function emptyUsageBucket() {
  return { calls: 0, prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 };
}

function getCurrentModelKey() {
  const provider = els.providerSelect?.value?.trim();
  const model = modelManual
    ? els.modelInput?.value?.trim()
    : els.modelSelect?.value?.trim();
  if (!provider || !model) return '';
  return `${provider}::${model}`;
}

function usageGridHtml(bucket) {
  const u = bucket || emptyUsageBucket();
  return `
    <div class="usage-cell"><span>${t('usageCalls')}</span><b>${fmtUsageNum(u.calls)}</b></div>
    <div class="usage-cell"><span>${t('usagePrompt')}</span><b>${fmtTokenNum(u.prompt_tokens)}</b></div>
    <div class="usage-cell"><span>${t('usageCompletion')}</span><b>${fmtTokenNum(u.completion_tokens)}</b></div>
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

function renderUsageDetailModal() {
  if (!usageData) return;
  const u = usageData;
  if (els.usageDetailTotals) {
    els.usageDetailTotals.innerHTML = `<div class="usage-grid usage-grid-inline">${usageGridHtml(u)}</div>`;
  }
  const statCols = usageStatCols();
  const providers = Object.entries(u.by_provider || {})
    .map(([id, row]) => ({ id, ...row }))
    .sort((a, b) => (b.total_tokens || 0) - (a.total_tokens || 0));
  if (els.usageByProviderTable) {
    els.usageByProviderTable.innerHTML = renderUsageDetailTable(
      providers,
      [{ label: t('usageProviderCol', '服务商'), render: (r) => r.provider || r.id }, ...statCols],
    );
  }
  const models = Object.entries(u.by_model || {})
    .map(([id, row]) => ({ id, ...row }))
    .sort((a, b) => (b.total_tokens || 0) - (a.total_tokens || 0));
  if (els.usageByModelTable) {
    els.usageByModelTable.innerHTML = renderUsageDetailTable(
      models,
      [
        { label: t('usageProviderCol', '服务商'), render: (r) => r.provider || String(r.id).split('::')[0] },
        { label: t('usageModelCol', '模型'), render: (r) => r.model || String(r.id).split('::').slice(1).join('::') },
        ...statCols,
      ],
    );
  }
}

function openUsageDetailModal() {
  if (!usageData) {
    loadUsage().then(() => {
      if (usageData) openUsageDetailModal();
    });
    return;
  }
  usageDetailOpen = true;
  setOverlayVisible(els.usageDetailModal, true);
  renderUsageDetailModal();
  syncBodyScrollLock();
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
  if (els.pinModal && !els.pinModal.hidden) return;
  if (els.writeConfirmModal && !els.writeConfirmModal.hidden) return;
  if (knowledgeOpen) { closeKnowledgeModal(); return; }
  if (usageDetailOpen) { closeUsageDetailModal(); return; }
  if (notificationsOpen) { closeNotificationsPanel(); return; }
  if (cabanaOpen) { closeCabanaModal(); return; }
  if (els.settingsSidebar?.classList.contains('open')) { closeSettings(); return; }
  if (els.sessionsPanel?.classList.contains('open')) { closeSessionsDrawer(); }
}

// ---------------------------------------------------------------------------
// Misc
// ---------------------------------------------------------------------------

function autoResize() {
  const mobile = window.matchMedia('(max-width: 767px)').matches;
  const maxH = mobile ? 88 : 120;
  if (!els.chatInput) return;
  els.chatInput.style.height = 'auto';
  const next = Math.min(els.chatInput.scrollHeight, maxH);
  els.chatInput.style.height = `${Math.max(mobile ? 36 : 44, next)}px`;
}

function onChatKeydown(e) {
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
    ui.thinkingBody.textContent = msg.reasoning_content;
    ui.thinking.classList.add('collapsed');
  }
  const toolResults = msg.tool_results || {};
  if (msg.tool_calls?.length) {
    ui.toolsBlock.classList.remove('hidden');
    ui.toolsBlock.classList.add('collapsed');
    for (const tc of msg.tool_calls) {
      const id = tc.id;
      const fn = tc.function || {};
      renderToolCall(ui.toolsList, id, fn.name || '', fn.arguments || '', toolResults[id]);
    }
    updateToolCallsSummary(ui.toolsBlock);
  }
  const text = messageText(msg.content) || (typeof msg.content === 'string' ? msg.content : '');
  if (text) {
    renderMarkdownContent(ui.content, text);
  } else if (!msg.tool_calls?.length) {
    ui.content.textContent = t('noResponse', 'No response');
  }
  return ui.wrapper;
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

  els.messages.appendChild(hero);
  els.messages.appendChild(banner);
  els.messages.appendChild(grid);
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

function renderStoredMessages() {
  if (isChatUiLocked()) return;
  const history = getCurrentMessages();
  els.messages.innerHTML = '';
  for (const msg of history) {
    if (msg.role === 'user') {
      appendUserMessage(msg.content);
    } else if (msg.role === 'assistant') {
      if (!assistantMessageHasContent(msg)) continue;
      renderAssistantFromHistory(msg);
    }
  }
  if (!hasVisibleChatHistory(history)) {
    renderWelcomePanel();
  }
  syncMessagesLayoutMode();
  scrollToBottom();
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
}

function onThemeToggle() {
  Theme.toggle();
  updateThemeIcon();
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

function bindUiEvents() {
  els.cabanaBtn?.addEventListener('click', toggleCabanaModal);
  els.cabanaClose?.addEventListener('click', closeCabanaModal);
  els.cabanaBackdrop?.addEventListener('click', closeCabanaModal);
  els.notificationsBtn?.addEventListener('click', toggleNotificationsPanel);
  els.notificationsCloseBtn?.addEventListener('click', closeNotificationsPanel);
  els.notificationsBackdrop?.addEventListener('click', closeNotificationsPanel);
  els.notificationsMarkReadBtn?.addEventListener('click', () => {
    markAllNotificationsRead().catch(console.error);
  });
  els.usageDetailBtn?.addEventListener('click', openUsageDetailModal);
  els.usageDetailClose?.addEventListener('click', closeUsageDetailModal);
  els.usageDetailBackdrop?.addEventListener('click', closeUsageDetailModal);
  els.knowledgeBtn?.addEventListener('click', toggleKnowledgeModal);
  els.settingsKnowledgeBtn?.addEventListener('click', toggleKnowledgeModal);
  els.knowledgeClose?.addEventListener('click', closeKnowledgeModal);
  els.knowledgeBackdrop?.addEventListener('click', closeKnowledgeModal);

  els.composer?.addEventListener('submit', sendChat);
  els.chatInput?.addEventListener('keydown', onChatKeydown);
  els.chatInput?.addEventListener('paste', onChatPaste);
  els.chatInput?.addEventListener('input', autoResize);
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
  els.devPackageCheckBtn?.addEventListener('click', () => renderDevPane());
  els.devPackageUpdateBtn?.addEventListener('click', async () => {
    if (!window.confirm(t('devPackageUpdateConfirm', '将 git pull 更新 op助手（/ai）。继续？'))) return;
    els.devPackageUpdateBtn.disabled = true;
    try {
      const { data } = await api('POST', '/api/ai/package/update', { confirm: true });
      if (data.ok) {
        showToast(t('devPackageUpdateOk', '更新完成，请重启 ai.aid'));
        renderDevPane();
      } else {
        showToast(data.error || t('devPackageUpdateFail', '更新失败'));
        els.devPackageUpdateBtn.disabled = false;
      }
    } catch {
      showToast(t('devPackageUpdateFail', '更新失败'));
      els.devPackageUpdateBtn.disabled = false;
    }
  });
  els.devForkRefreshBtn?.addEventListener('click', async () => {
    els.devForkRefreshBtn.disabled = true;
    try {
      await refreshForkDetectCard();
    } catch {
      showToast(t('devForkLoadFail', '无法扫描 fork'));
    } finally {
      els.devForkRefreshBtn.disabled = false;
    }
  });
  els.devForkSyncBtn?.addEventListener('click', async () => {
    if (!window.confirm(t('devForkAnalyzeConfirm', 'AI 将阅读整个 openpilot 项目并分析 fork，随后生成草稿（需人工审核）。继续？'))) return;
    await runForkAnalyzePipeline({ force: false });
  });
  els.onboardingBackdrop?.addEventListener('click', closeOnboardingWizard);
  els.onboardingTestBtn?.addEventListener('click', () => testOnboardingWizard());
  els.onboardingSaveBtn?.addEventListener('click', () => saveOnboardingWizard());
  els.onboardingProvider?.addEventListener('change', () => {
    const p = els.onboardingProvider.value;
    if (els.onboardingModel && !els.onboardingModel.value) {
      els.onboardingModel.value = defaults[p] || '';
    }
  });
  els.settingsBtn?.addEventListener('click', () => openSettings());
  els.settingsSidebarClose?.addEventListener('click', () => closeSettings());
  els.settingsBackdrop?.addEventListener('click', () => closeSettings());
  els.sessionsToggleBtn?.addEventListener('click', toggleSessionsPanel);
  els.sessionsCloseBtn?.addEventListener('click', closeSessionsDrawer);
  els.newSessionBtn?.addEventListener('click', createNewSession);
  els.sessionsBackdrop?.addEventListener('click', closeSessionsDrawer);
  els.providerSelect?.addEventListener('change', async () => {
    onProviderChange();
    persistConfigDraft();
    await fetchModels();
    refreshUsageForCurrentModel();
  });
  els.modelSelect?.addEventListener('change', refreshUsageForCurrentModel);
  els.modelInput?.addEventListener('input', refreshUsageForCurrentModel);
  els.baseUrlInput?.addEventListener('change', fetchModels);
  els.apiKeyInput?.addEventListener('change', fetchModels);
  els.langSelect?.addEventListener('change', onLangChange);
  els.chatInput?.addEventListener('input', onComposerInput);
  els.modelModeBtn?.addEventListener('click', () => setModelMode(!modelManual));
  els.saveBtn?.addEventListener('click', () => saveConfig({ silent: false }));
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
  els.ragReindexBtn?.addEventListener('click', reindexRag);
  els.embeddingModeSelect?.addEventListener('change', () => {
    onEmbeddingModeChange();
    persistConfigDraft();
  });
  els.embeddingProviderSelect?.addEventListener('change', () => {
    onEmbeddingProviderChange();
    persistConfigDraft();
  });
  els.embeddingModelModeBtn?.addEventListener('click', () => setEmbeddingModelMode(!embeddingModelManual));
  els.embeddingModelSelect?.addEventListener('change', persistConfigDraft);
  document.addEventListener('keydown', onOverlayKeydown);
  window.addEventListener('pagehide', flushSessionSyncOnUnload);
  window.addEventListener('beforeunload', flushSessionSyncOnUnload);
}

async function init() {
  SessionStore.load();
  bindSettingsTabs();
  bindUiEvents();
  if (typeof TskPanel !== 'undefined') TskPanel.bind();

  Theme.init();
  window.addEventListener('themechange', updateThemeIcon);
  updateThemeIcon();
  if (els.langSelect) els.langSelect.value = i18n.getLang();
  applyTranslations();
  applyCachedUiState();

  if (typeof CabanaPanel !== 'undefined') {
    ensureCabanaInited();
  }

  try {
    await loadBootstrap();
  } catch (e) {
    console.error('loadBootstrap failed', e);
    applyCachedUiState();
  }

  await refreshSessionViewFromRemote().catch((e) => {
    console.warn('initial session pull failed', e);
  });

  loadSessionMode();
  renderSessionList();
  renderStoredMessages();

  startSyncWebSocket();

  startStatusPolling();
  loadNotifications().catch(() => {});
  startNotificationsPolling();

  if (new URLSearchParams(location.search).get('cabana') === '1') {
    openCabanaModal();
  }

  const settingsTab = new URLSearchParams(location.search).get('settings');
  if (settingsTab) {
    openSettingsTab(settingsTab);
  }

  await dismissAppSplash();
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
