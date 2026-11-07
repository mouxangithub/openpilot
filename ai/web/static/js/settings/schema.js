(function (global) {
  const app = global.SettingsApp = global.SettingsApp || {};
  app.schema = app.schema || {};
  const R = app.registry;
  const f = (cfg) => Object.assign({ type: 'string', label: cfg.key, description: '', default: null, restart: false, secret: false, min: null, max: null, enum: null, placeholder: '' }, cfg);
  app.schema.f = f;
  app.schema.registerDefault = function registerDefault() {
    if (app.schema._registered) return; app.schema._registered = true;
    R.register({
      id: 'conversation', label: '对话', icon: '💬', desc: '模型账户、生成上下文与用量', gated: false,
      cards: [
        { id: 'account', title: '账户', subtitle: '服务商、模型与密钥', fields: [
          f({ key: 'provider', type: 'enum', label: '服务商', enum: ['openai','anthropic','deepseek','qwen','zhipu','local','custom'], default: '' }),
          f({ key: 'model', type: 'string', label: '模型', placeholder: '如 gpt-4o' }),
          f({ key: 'apiKey', type: 'secret', label: 'API Key', secret: true }),
          f({ key: 'baseUrl', type: 'string', label: 'Base URL', placeholder: 'https://api.example.com/v1' }),
        ] },
        { id: 'context', title: '生成上下文', subtitle: '温度、采样、上下文窗口与压缩', fields: [
          f({ key: 'temperature', type: 'number', label: 'Temperature', min: 0, max: 2, default: 0.7 }),
          f({ key: 'topP', type: 'number', label: 'Top P', min: 0, max: 1, default: 1 }),
          f({ key: 'maxTokens', type: 'number', label: 'Max Tokens', min: 1, default: 2048 }),
          f({ key: 'contextWindow', type: 'number', label: '上下文窗口', min: 0, default: 0 }),
          f({ key: 'compactionEnabled', type: 'boolean', label: '启用上下文压缩', default: true }),
          f({ key: 'compactAfterTurns', type: 'number', label: '多少轮后压缩', min: 1, default: 12 }),
          f({ key: 'keepRecentTurns', type: 'number', label: '保留最近轮次', min: 1, default: 8 }),
          f({ key: 'reserveTokens', type: 'number', label: '预留 Token', min: 0, default: 0 }),
          f({ key: 'thinkingEnabled', type: 'boolean', label: '启用深度思考', default: false }),
          f({ key: 'thinkingKeep', type: 'number', label: '思考保留轮次', min: 0, default: 2 }),
        ] },
        { id: 'persona', title: '系统人设', subtitle: '系统提示词与基础偏好', fields: [
          f({ key: 'systemPrompt', type: 'textarea', label: '系统提示词（人设）', description: '留空使用默认人设' }),
          f({ key: 'timezone', type: 'string', label: '时区', placeholder: '如 Asia/Shanghai' }),
        ] },
      ],
    });
    R.register({
      id: 'evolution', label: '学习与进化', icon: '🧠', desc: '记忆、技能披露与 GEPA 进化', gated: false,
      cards: [
        { id: 'evolution', title: '进化开关', subtitle: '自动进化与记忆写入', fields: [
          f({ key: 'evolutionEnabled', type: 'boolean', label: '启用学习进化', default: true }),
          f({ key: 'evolutionAutoPropose', type: 'boolean', label: '自动提案', default: true }),
          f({ key: 'evolutionAutoWorkspace', type: 'boolean', label: '自动写入工作区', default: false }),
          f({ key: 'evolutionAutoMemory', type: 'boolean', label: '自动写入记忆', default: false }),
          f({ key: 'evolutionLlmReflect', type: 'boolean', label: 'LLM 反思', default: true }),
          f({ key: 'evolutionToolDesc', type: 'boolean', label: '工具描述进化', default: true }),
        ] },
        { id: 'gepa', title: 'GEPA 进化', subtitle: '候选、迭代与评测', fields: [
          f({ key: 'evolutionCandidates', type: 'number', label: '候选数', min: 1, default: 3 }),
          f({ key: 'evolutionGepaEnabled', type: 'boolean', label: '启用 GEPA', default: false }),
          f({ key: 'evolutionGepaIterations', type: 'number', label: '迭代轮数', min: 1, default: 2 }),
          f({ key: 'evolutionEvalCases', type: 'number', label: '评测用例数', min: 0, default: 3 }),
          f({ key: 'evolutionUseDspy', type: 'boolean', label: '使用 DSPy', default: false }),
        ] },
        { id: 'skills', title: '技能披露', subtitle: '已学技能披露上限', fields: [
          f({ key: 'skillsDisclosureMax', type: 'number', label: '最大披露数', min: 0, default: 5 }),
        ] },
      ],
    });
    R.register({
      id: 'vehicle', label: '车辆与安全', icon: '🚗', desc: '车辆安全相关设置（后端 registry 同步后启用）', gated: false,
      cards: [
        { id: 'safety', title: '安全策略', subtitle: '车辆安全相关阈值', fields: [
          f({ key: 'ai_vehicle_speed_warn', type: 'number', label: '超速提醒阈值(km/h)', min: 0, default: 120 }),
          f({ key: 'ai_vehicle_blindspot_warn', type: 'boolean', label: '盲区提醒', default: true }),
          f({ key: 'ai_vehicle_event_upload', type: 'boolean', label: '事件上报', default: true }),
        ] },
      ],
    });
    R.register({
      id: 'data_backup', label: '数据与备份', icon: '💾', desc: 'RAG 检索与备份设置', gated: false,
      cards: [
        { id: 'rag', title: '检索配置', subtitle: 'RAG 检索范围', fields: [
          f({ key: 'ragSearchLimit', type: 'number', label: '检索条数', min: 1, default: 5 }),
          f({ key: 'ragMaxDocs', type: 'number', label: '最大文档数', min: 1, default: 10 }),
          f({ key: 'ragMaxChunks', type: 'number', label: '最大分块数', min: 1, default: 20 }),
          f({ key: 'wikiMaxFilesPerRepo', type: 'number', label: '每仓库最大文件数', min: 1, default: 50 }),
        ] },
        { id: 'backup', title: '备份与恢复', subtitle: '工作区与 .opbak 备份', kind: 'action' },
      ],
    });
    R.register({
      id: 'scheduler', label: '定时任务', icon: '⏰', desc: '独立的任务管理视图', gated: false, standalone: true,
      cards: [],
    });
    R.register({
      id: 'dev_diagnostics', label: '开发与诊断', icon: '🛠️', desc: '开发、诊断与危险操作', gated: true,
      cards: [
        { id: 'diagnostics', title: '启动诊断', subtitle: '依赖与配置诊断', kind: 'action' },
        { id: 'danger', title: '危险操作', subtitle: '预览→确认→审计', kind: 'danger' },
      ],
    });
  };
})(window);
