/**
 * op助手 quick actions — diagnostics & tune shortcuts.
 */
const OP_QUICK_ACTIONS = [
  {
    icon: '☁️',
    titleKey: 'qaKonik',
    descKey: 'qaKonikDesc',
    workflow: 'konik_connect',
    promptKey: 'qaKonikPrompt',
  },
  {
    icon: '🚗',
    titleKey: 'qaVehicle',
    descKey: 'qaVehicleDesc',
    promptKey: 'qaVehiclePrompt',
  },
  {
    icon: '🛣️',
    titleKey: 'qaAlka',
    descKey: 'qaAlkaDesc',
    promptKey: 'qaAlkaPrompt',
  },
  {
    icon: '🎯',
    titleKey: 'qaLon',
    descKey: 'qaLonDesc',
    promptKey: 'qaLonPrompt',
  },
  {
    icon: '⚡',
    titleKey: 'qaEvents',
    descKey: 'qaEventsDesc',
    promptKey: 'qaEventsPrompt',
  },
  {
    icon: '📋',
    titleKey: 'qaLogs',
    descKey: 'qaLogsDesc',
    promptKey: 'qaLogsPrompt',
  },
  {
    icon: '⚙️',
    titleKey: 'qaDpSettings',
    descKey: 'qaDpSettingsDesc',
    promptKey: 'qaDpSettingsPrompt',
  },
  {
    icon: '📊',
    titleKey: 'qaSystem',
    descKey: 'qaSystemDesc',
    promptKey: 'qaSystemLoadPrompt',
  },
  {
    icon: '🔐',
    titleKey: 'qaEngage',
    descKey: 'qaEngageDesc',
    workflow: 'engage_triage',
    promptKey: 'qaEngagePrompt',
  },
  {
    icon: '📝',
    titleKey: 'qaTripReview',
    descKey: 'qaTripReviewDesc',
    promptKey: 'qaTripReviewPrompt',
  },
  {
    icon: '🔧',
    titleKey: 'qaAdapt',
    descKey: 'qaAdaptDesc',
    workflow: 'vehicle_adaptation',
    promptKey: 'qaAdaptPrompt',
  },
  {
    icon: '🔄',
    titleKey: 'qaCpMigrate',
    descKey: 'qaCpMigrateDesc',
    workflow: 'cp_migration',
    promptKey: 'qaCpMigratePrompt',
  },
  {
    icon: '⏪',
    titleKey: 'qaRollback',
    descKey: 'qaRollbackDesc',
    workflow: 'tune_session',
    promptKey: 'qaRollbackPrompt',
  },
  {
    icon: '🔌',
    titleKey: 'qaCabana',
    descKey: 'qaCabanaDesc',
    promptKey: 'qaCabanaPrompt',
    action: 'cabana',
  },
  {
    icon: '📈',
    titleKey: 'qaCompareRoutes',
    descKey: 'qaCompareRoutesDesc',
    workflow: 'compare_routes_tune',
    promptKey: 'qaCompareRoutesPrompt',
  },
  {
    icon: '✅',
    titleKey: 'qaPostTune',
    descKey: 'qaPostTuneDesc',
    workflow: 'post_tune_validation',
    promptKey: 'qaPostTunePrompt',
  },
  {
    icon: '📦',
    titleKey: 'qaBatchRoutes',
    descKey: 'qaBatchRoutesDesc',
    workflow: 'batch_route_review',
    promptKey: 'qaBatchRoutesPrompt',
  },
];

/** 输入框上方紧凑快捷条（空会话时显示，对标 ClawPanel） */
const OP_COMPOSER_QUICK_KEYS = [
  'qaKonik',
  'qaVehicle',
  'qaEngage',
  'qaSystem',
  'qaLogs',
  'qaTripReview',
];
