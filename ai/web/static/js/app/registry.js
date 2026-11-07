/**
 * Front-end module registry (load order documented in index.html).
 */
const AppRegistry = {
  lib: ['i18n', 'theme', 'markdown', 'web-api', 'local-prefs', 'web-sync-ws'],
  sessions: ['sessions', 'session-sync', 'session-model-picker'],
  chat: ['chat/model-tag', 'web-chat-jobs'],
  settings: ['model-hub', 'model-combobox', 'fallback-models', 'web-config'],
  panels: ['tsk-panel', 'cabana-panel', 'office-panel', 'platform-panel', 'agents-panel'],
  app: ['app/globals', 'ai'],
};
