/**
 * Custom workflow editor — settings → platform (WorkBuddy workflow UI).
 */
const WorkflowEditor = (() => {
  let api = null;
  let custom = {};
  let selectedId = null;

  function tr(key, fallback) {
    return (typeof t === 'function') ? t(key, fallback) : fallback;
  }

  function esc(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  async function load() {
    if (!api) return;
    const { data } = await api('GET', '/api/ai/workflows/custom');
    if (!data?.ok) return;
    custom = data.custom || {};
    renderList();
    if (selectedId && custom[selectedId]) renderEditor(selectedId);
  }

  function renderList() {
    const list = document.getElementById('workflowEditorList');
    if (!list) return;
    const ids = Object.keys(custom);
    if (!ids.length) {
      list.innerHTML = `<p class="field-hint">${tr('workflowEditorEmpty', '暂无自定义工作流，点击下方添加')}</p>`;
      return;
    }
    list.innerHTML = ids.map((id) => {
      const w = custom[id];
      const active = id === selectedId ? ' is-active' : '';
      return `<button type="button" class="workflow-editor-item${active}" data-id="${esc(id)}">${esc(w.name || id)}</button>`;
    }).join('');
    list.querySelectorAll('.workflow-editor-item').forEach((btn) => {
      btn.addEventListener('click', () => {
        selectedId = btn.dataset.id;
        renderList();
        renderEditor(selectedId);
      });
    });
  }

  function renderEditor(id) {
    const pane = document.getElementById('workflowEditorPane');
    if (!pane) return;
    const w = custom[id] || { name: id, mode: 'execute', steps: [], prompt: '' };
    pane.innerHTML = `
      <label class="field"><span class="field-label">ID</span><input type="text" id="wfEditId" value="${esc(id)}" readonly></label>
      <label class="field"><span class="field-label">${tr('schedNameLabel', '名称')}</span><input type="text" id="wfEditName" value="${esc(w.name || '')}"></label>
      <label class="field"><span class="field-label">${tr('workflowStepsLabel', '步骤（每行一条）')}</span>
        <textarea id="wfEditSteps" rows="6" class="platform-editor">${esc((w.steps || []).join('\n'))}</textarea></label>
      <label class="field"><span class="field-label">Prompt</span>
        <textarea id="wfEditPrompt" rows="5" class="platform-editor">${esc(w.prompt || '')}</textarea></label>
      <div class="platform-toolbar">
        <button type="button" class="btn small primary" id="wfEditSave">${tr('save', '保存')}</button>
        <button type="button" class="btn small" id="wfEditDelete">${tr('delete', '删除')}</button>
      </div>
    `;
    pane.querySelector('#wfEditSave')?.addEventListener('click', () => saveEditor(id));
    pane.querySelector('#wfEditDelete')?.addEventListener('click', () => deleteWorkflow(id));
  }

  async function saveEditor(oldId) {
    const name = document.getElementById('wfEditName')?.value?.trim() || oldId;
    const stepsRaw = document.getElementById('wfEditSteps')?.value || '';
    const prompt = document.getElementById('wfEditPrompt')?.value || '';
    const steps = stepsRaw.split('\n').map((s) => s.trim()).filter(Boolean);
    const next = { ...custom };
    if (oldId !== selectedId) delete next[oldId];
    next[selectedId || oldId] = { name, mode: 'execute', steps, prompt };
    custom = next;
    const { data } = await api('PUT', '/api/ai/workflows/custom', { workflows: custom });
    if (data?.ok) {
      selectedId = oldId;
      renderList();
      renderEditor(selectedId);
    }
  }

  async function deleteWorkflow(id) {
    const next = { ...custom };
    delete next[id];
    custom = next;
    selectedId = null;
    await api('PUT', '/api/ai/workflows/custom', { workflows: custom });
    document.getElementById('workflowEditorPane').innerHTML = '';
    renderList();
  }

  function addNew() {
    const id = `custom_${Date.now().toString(36)}`;
    custom[id] = { name: tr('workflowNew', '新工作流'), mode: 'execute', steps: [], prompt: '' };
    selectedId = id;
    renderList();
    renderEditor(id);
  }

  function bind() {
    document.getElementById('workflowEditorAdd')?.addEventListener('click', addNew);
    document.getElementById('workflowEditorReload')?.addEventListener('click', () => load().catch(console.error));
  }

  function init(deps = {}) {
    api = deps.api || (typeof WebApi !== 'undefined' ? WebApi.api : null);
    bind();
  }

  function onSettingsOpen() {
    load().catch(() => {});
  }

  return { init, onSettingsOpen, load };
})();
