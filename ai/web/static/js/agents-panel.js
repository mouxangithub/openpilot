/**
 * Builtin agents UI — settings, stream events, office usage (extracted from ai.js).
 * Agent handoff UI is rendered inside each assistant message (agent-calls-block).
 */
const AgentsPanel = (() => {
  let deps = {};
  let builtinAgents = [];
  let currentActiveAgentId = 'op';
  let orchestrationActive = false;

  function init(options = {}) {
    deps = options;
  }

  function getCurrentAgentId() {
    return currentActiveAgentId;
  }

  function setOrchestrationActive(active) {
    orchestrationActive = !!active;
  }

  function applyBuiltinAgents(data) {
    if (Array.isArray(data?.agents)) {
      builtinAgents = data.agents;
      if (typeof OfficePanel !== 'undefined') OfficePanel.setAgents(builtinAgents);
    }
    if (data?.office && typeof OfficePanel !== 'undefined') {
      OfficePanel.applyOffice(data.office);
    }
  }

  async function refreshOfficeUsage() {
    try {
      const { data } = await deps.api('GET', '/api/ai/usage');
      if (data.ok && data.usage && typeof OfficePanel !== 'undefined') {
        OfficePanel.setUsageTokens(data.usage.total_tokens || 0);
      }
    } catch (_) { /* ignore */ }
  }

  function handleStreamEvent(data) {
    if (!data?.type) return;
    if (data.type === 'orchestration_start') {
      orchestrationActive = true;
      if (data.office && typeof OfficePanel !== 'undefined') {
        OfficePanel.applyOffice(data.office);
      }
    }
    if (data.type === 'agent_handoff') {
      currentActiveAgentId = data.agent_id || data.agentId || 'op';
      if (data.office && typeof OfficePanel !== 'undefined') OfficePanel.applyOffice(data.office);
    }
    if (data.type === 'agent_office' && data.office) {
      if (typeof OfficePanel !== 'undefined') OfficePanel.applyOffice(data.office);
    }
    if (data.type === 'agent_status' && data.office) {
      if (typeof OfficePanel !== 'undefined') OfficePanel.applyOffice(data.office);
    }
    if (data.type === 'agent_done') {
      if (data.office && typeof OfficePanel !== 'undefined') OfficePanel.applyOffice(data.office);
      if (!orchestrationActive) currentActiveAgentId = 'op';
    }
    if (data.type === 'done') {
      orchestrationActive = false;
      currentActiveAgentId = 'op';
    }
  }

  return {
    init,
    applyBuiltinAgents,
    refreshOfficeUsage,
    handleStreamEvent,
    getCurrentAgentId,
    setOrchestrationActive,
  };
})();
