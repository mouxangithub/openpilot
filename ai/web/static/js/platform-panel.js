/**
 * Platform settings — workspace, MCP, learned skills, session search, debug toggles.
 */
const PlatformPanel = (() => {
  let api = null;
  let showToast = null;
  let tuneRoutesLoaded = false;

  function tr(key, fallback) {
    return (typeof t === 'function') ? t(key, fallback) : fallback;
  }

  function toast(msg, type = 'info') {
    if (typeof showToast === 'function') showToast(msg, type);
  }

  function busyBtn(btn, busy, busyLabel) {
    if (typeof UiBusy !== 'undefined') {
      UiBusy.setButtonBusy(btn, busy, busyLabel ? { busyLabel } : {});
      return;
    }
    if (!btn) return;
    btn.disabled = busy;
  }

  async function withBusy(btn, fn, busyLabel) {
    if (typeof UiBusy !== 'undefined') {
      return UiBusy.withButtonBusy(btn, fn, busyLabel ? { busyLabel } : {});
    }
    if (!btn) return fn();
    btn.disabled = true;
    try {
      return await fn();
    } finally {
      btn.disabled = false;
    }
  }

  function esc(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function init(deps = {}) {
    api = deps.api || (typeof WebApi !== 'undefined' ? WebApi.api : null);
    showToast = deps.showToast || null;
    bind();
    loadDebugToggles();
  }

  function loadDebugToggles() {
    const prefs = (typeof LocalPrefs !== 'undefined' && LocalPrefs.getChatDebugPrefs)
      ? LocalPrefs.getChatDebugPrefs()
      : { verbose: false, trace: false };
    const verbose = document.getElementById('chatVerboseToggle');
    const trace = document.getElementById('chatTraceToggle');
    if (verbose) verbose.checked = !!prefs.verbose;
    if (trace) trace.checked = !!prefs.trace;
  }

  function saveDebugToggles() {
    if (typeof LocalPrefs === 'undefined' || !LocalPrefs.setChatDebugPrefs) return;
    LocalPrefs.setChatDebugPrefs({
      verbose: !!document.getElementById('chatVerboseToggle')?.checked,
      trace: !!document.getElementById('chatTraceToggle')?.checked,
    });
  }

  async function loadWorkspace() {
    const btn = document.getElementById('platformWorkspaceLoad');
    const editor = document.getElementById('platformWorkspaceEditor');
    const key = document.getElementById('platformWorkspaceKey')?.value || 'user';
    await withBusy(btn, async () => {
      if (typeof UiBusy !== 'undefined' && editor) {
        UiBusy.showPanelLoading(editor, tr('uiLoading', '加载中…'));
      }
      const { data } = await api('GET', `/api/ai/workspace?key=${encodeURIComponent(key)}`);
      if (editor && data?.ok) editor.value = data.content || '';
      if (typeof UiBusy !== 'undefined') UiBusy.clearPanelBusy(editor);
      if (!data?.ok) toast(data?.error || tr('platformWorkspaceLoadFail', '加载失败'), 'error');
    }, tr('uiLoading', '加载中…'));
  }

  async function saveWorkspace() {
    const btn = document.getElementById('platformWorkspaceSave');
    const key = document.getElementById('platformWorkspaceKey')?.value || 'user';
    const content = document.getElementById('platformWorkspaceEditor')?.value || '';
    await withBusy(btn, async () => {
      const { data } = await api('POST', '/api/ai/workspace', { key, content });
      if (data?.ok) toast(tr('saved', '已保存'), 'success');
      else toast(data?.error || tr('saveFailed', '保存失败'), 'error');
    }, tr('uiSaving', '保存中…'));
  }

  async function refreshMcp() {
    const box = document.getElementById('platformMcpList');
    if (!box) return;
    const { data } = await api('GET', '/api/ai/mcp');
    box.innerHTML = '';
    for (const s of (data?.servers || [])) {
      const row = document.createElement('div');
      row.className = 'platform-list-item';
      row.textContent = `${s.id} · ${s.command || ''} · tools=${s.toolCount || 0}`;
      box.appendChild(row);
    }
  }

  async function addMcp() {
    const btn = document.getElementById('platformMcpAdd');
    const id = document.getElementById('platformMcpId')?.value?.trim();
    const command = document.getElementById('platformMcpCmd')?.value?.trim();
    if (!id || !command) {
      toast(tr('platformMcpMissing', '请填写 ID 与命令'), 'warning');
      return;
    }
    await withBusy(btn, async () => {
      const { data } = await api('POST', '/api/ai/mcp', { id, command, enabled: true });
      if (data?.ok) {
        toast(tr('platformMcpAdded', 'MCP 已添加'), 'success');
        await refreshMcp();
      } else {
        toast(data?.error || tr('saveFailed', '保存失败'), 'error');
      }
    }, tr('uiSaving', '保存中…'));
  }

  async function refreshLearned() {
    const box = document.getElementById('platformLearnedList');
    if (!box) return;
    if (typeof UiBusy !== 'undefined') {
      UiBusy.showPanelLoading(box, tr('uiLoading', '加载中…'));
    }
    const { data } = await api('GET', '/api/ai/learned-skills');
    if (typeof UiBusy !== 'undefined') UiBusy.clearPanelBusy(box);
    box.innerHTML = '';
    for (const s of (data?.skills || [])) {
      const row = document.createElement('div');
      row.className = 'platform-list-item';
      const title = document.createElement('span');
      title.textContent = `${s.title || s.id} [${s.status}]`;
      row.appendChild(title);
      if (s.status === 'pending') {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn small';
        btn.textContent = tr('platformLearnedApprove', '批准');
        btn.addEventListener('click', async () => {
          await withBusy(btn, async () => {
            const { data: res } = await api('POST', '/api/ai/learned-skills', { skill_id: s.id });
            if (res?.ok) {
              toast(tr('platformLearnedApproved', '技能已批准'), 'success');
              refreshLearned();
            } else {
              toast(res?.error || tr('saveFailed', '保存失败'), 'error');
            }
          }, tr('uiWorking', '处理中…'));
        });
        row.appendChild(btn);
      }
      box.appendChild(row);
    }
  }

  async function searchSessions() {
    const btn = document.getElementById('platformSessionSearch');
    const q = document.getElementById('platformSessionQuery')?.value?.trim();
    const box = document.getElementById('platformSessionHits');
    if (!box) return;
    if (!q) {
      toast(tr('platformSessionQueryRequired', '请输入搜索词'), 'warning');
      return;
    }
    await withBusy(btn, async () => {
      if (typeof UiBusy !== 'undefined') {
        UiBusy.showPanelLoading(box, tr('uiSearching', '搜索中…'));
      }
      const { data } = await api('GET', `/api/ai/sessions/search?q=${encodeURIComponent(q)}`);
      box.innerHTML = '';
      const hits = data?.hits || [];
      if (!hits.length) {
        box.innerHTML = `<p class="field-hint">${tr('platformSessionNoHits', '无匹配结果')}</p>`;
        return;
      }
      for (const hit of hits) {
        const row = document.createElement('div');
        row.className = 'platform-list-item';
        row.textContent = `${hit.sessionTitle || hit.sessionId}: ${hit.snippet || ''}`;
        box.appendChild(row);
      }
      if (typeof UiBusy !== 'undefined') UiBusy.clearPanelBusy(box);
    }, tr('uiSearching', '搜索中…'));
  }

  async function loadMemoryAndPassport() {
    const profileBox = document.getElementById('platformMemoryProfile');
    const notesBox = document.getElementById('platformMemoryNotes');
    const passportList = document.getElementById('platformPassportList');
    const passportCount = document.getElementById('platformPassportCount');
    const [{ data: mem }, { data: passport }] = await Promise.all([
      api('GET', '/api/ai/memory').catch(() => ({ data: {} })),
      api('GET', '/api/ai/tune_passport?limit=20').catch(() => ({ data: {} })),
    ]);
    const profile = mem?.vehicle_profile || {};
    if (profileBox) {
      const lines = Object.entries(profile)
        .filter(([k, v]) => k !== 'updated_at' && v)
        .map(([k, v]) => `<div><b>${k}</b>: ${String(v)}</div>`);
      profileBox.innerHTML = lines.length
        ? lines.join('')
        : `<p class="field-hint">${typeof t === 'function' ? t('platformMemoryEmpty', '暂无车型档案') : '暂无车型档案'}</p>`;
    }
    if (notesBox) {
      const notes = mem?.notes || [];
      notesBox.innerHTML = notes.length
        ? notes.slice(0, 12).map((n) => {
            const when = n.at ? new Date(n.at * 1000).toLocaleString() : '';
            return `<li class="dev-item"><div>${(n.text || '').replace(/</g, '&lt;')}</div><span class="field-hint">${when}</span></li>`;
          }).join('')
        : `<li class="dev-empty">${typeof t === 'function' ? t('platformMemoryEmpty', '暂无记忆备注') : '暂无记忆备注'}</li>`;
    }
    const entries = passport?.entries || [];
    if (passportList) {
      passportList.innerHTML = entries.length
        ? entries.map((e) => {
            const when = e.at ? new Date(e.at * 1000).toLocaleString() : '';
            const params = Object.keys(e.params_changed || {}).join(', ') || '—';
            return `<li class="dev-item"><div><b>${e.action || ''}</b> <span class="field-hint">${when}</span></div><div class="field-hint">${params}</div></li>`;
          }).join('')
        : `<li class="dev-empty">${typeof t === 'function' ? t('tunePassportEmpty', '暂无调参记录') : '暂无调参记录'}</li>`;
    }
    if (passportCount) passportCount.textContent = String(passport?.count ?? entries.length);
  }

  function fillRouteSelect(sel, routes, placeholder) {
    if (!sel) return;
    sel.innerHTML = '';
    const ph = document.createElement('option');
    ph.value = '';
    ph.textContent = placeholder;
    sel.appendChild(ph);
    for (const r of routes) {
      const opt = document.createElement('option');
      opt.value = r.name;
      const label = r.date ? `${r.date} · ${r.name}` : r.name;
      opt.textContent = label.length > 72 ? `${label.slice(0, 69)}…` : label;
      sel.appendChild(opt);
    }
  }

  async function loadTuneRouteOptions() {
    const selA = document.getElementById('platformTuneRouteA');
    const selB = document.getElementById('platformTuneRouteB');
    if (!selA || !selB || !api) return;
    const { data } = await api('GET', '/api/cabana/routes', null, { timeoutMs: 15000 }).catch(() => ({ data: {} }));
    const routes = (data?.routes || []).slice(0, 80);
    const ph = tr('platformTuneRoutePlaceholder', '选择路线…');
    fillRouteSelect(selA, routes, ph);
    fillRouteSelect(selB, routes, ph);
    if (routes.length >= 2) {
      selA.value = routes[1].name;
      selB.value = routes[0].name;
    }
    tuneRoutesLoaded = true;
  }

  function renderTuneCompareResult(data) {
    const box = document.getElementById('platformTuneCompareResult');
    if (!box) return;
    const cmp = data?.compare || {};
    const session = data?.session || {};
    const highlights = cmp.tune_highlights || session.tune_highlights || [];
    const recs = cmp.tune_recommendations || [];
    const labelA = cmp.label_a || 'before';
    const labelB = cmp.label_b || 'after';

    let html = '';
    if (session.ok) {
      const passCls = session.passed ? 'tune-ab-pass' : 'tune-ab-fail';
      html += `<div class="tune-ab-scores ${passCls}">`;
      html += `<div><span class="tune-ab-score-label">${tr('platformTuneScoreBefore', '调参前')}</span> <b>${esc(session.score_before)}</b> (${esc(session.grade_before || '—')})</div>`;
      html += `<div><span class="tune-ab-score-label">${tr('platformTuneScoreAfter', '调参后')}</span> <b>${esc(session.score_after)}</b> (${esc(session.grade_after || '—')})</div>`;
      html += `<div>Δ <b>${esc(session.score_delta)}</b> · ${session.passed ? tr('platformTunePassed', '通过') : tr('platformTuneFailed', '未通过')}</div>`;
      if (session.recommendation) html += `<p class="field-hint">${esc(session.recommendation)}</p>`;
      html += '</div>';
    }

    if (highlights.length) {
      html += `<table class="tune-ab-table"><thead><tr><th>${tr('platformTuneColSignal', '信号')}</th><th>${esc(labelA)}</th><th>${esc(labelB)}</th><th>Δ</th></tr></thead><tbody>`;
      for (const h of highlights) {
        html += `<tr><td>${esc(h.label || h.field)}<span class="field-hint"> ${esc(h.topic || '')}</span></td>`;
        html += `<td>${esc(h[labelA] ?? h.before ?? '—')}</td>`;
        html += `<td>${esc(h[labelB] ?? h.after ?? '—')}</td>`;
        html += `<td>${esc(h.delta_mean)}</td></tr>`;
      }
      html += '</tbody></table>';
    } else {
      html += `<p class="field-hint">${tr('platformTuneNoHighlights', '两路线信号差异较小')}</p>`;
    }

    if (recs.length) {
      html += `<ul class="tune-ab-recs">${recs.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>`;
    }

    box.innerHTML = html;
    box.hidden = false;
  }

  async function runTuneCompare() {
    const routeA = document.getElementById('platformTuneRouteA')?.value?.trim();
    const routeB = document.getElementById('platformTuneRouteB')?.value?.trim();
    const status = document.getElementById('platformTuneCompareStatus');
    const result = document.getElementById('platformTuneCompareResult');
    const btn = document.getElementById('platformTuneCompareBtn');
    if (!routeA || !routeB) {
      if (status) {
        status.hidden = false;
        status.textContent = tr('platformTunePickRoutes', '请选择两条路线');
      }
      toast(tr('platformTunePickRoutes', '请选择两条路线'), 'warning');
      return;
    }
    await withBusy(btn, async () => {
      if (status) {
        status.hidden = false;
        status.textContent = tr('platformTuneComparing', '正在对比…');
      }
      if (result) result.hidden = true;
      try {
        const { data } = await api('POST', '/api/ai/tune/compare', {
          route_a: routeA,
          route_b: routeB,
          label_a: 'before',
          label_b: 'after',
          with_scores: true,
        }, { timeoutMs: 120000 });
        if (!data?.ok) {
          const err = data?.error || tr('platformTuneCompareError', '对比失败');
          if (status) status.textContent = err;
          toast(err, 'error');
          return;
        }
        if (status) status.hidden = true;
        renderTuneCompareResult(data);
        toast(tr('platformTuneCompareDone', '对比完成'), 'success');
      } catch (e) {
        const err = String(e?.message || e);
        if (status) status.textContent = err;
        toast(err, 'error');
      }
    }, tr('platformTuneComparing', '正在对比…'));
  }

  async function addSchedulerFromNl() {
    const btn = document.getElementById('schedNlBtn');
    const text = document.getElementById('schedNlInput')?.value?.trim();
    if (!text || !api) {
      toast(tr('schedNlMissing', '请输入自然语言描述'), 'warning');
      return;
    }
    await withBusy(btn, async () => {
      const { data } = await api('POST', '/api/ai/scheduler', { nl: text });
      if (data?.ok) {
        document.getElementById('schedNlInput').value = '';
        toast(tr('schedAdded'), 'success');
        if (typeof loadSchedulerPanel === 'function') await loadSchedulerPanel();
      } else {
        toast(data?.error || tr('saveFailed', '保存失败'), 'error');
      }
    }, tr('uiWorking', '处理中…'));
  }

  function applyPlatformTranslations() {
    const map = [
      ['platformMemoryTitle', '设备记忆'],
      ['platformPassportTitle', '调参护照'],
      ['platformTuneCompareTitle', '调参 A/B 对比'],
      ['platformTuneRouteALabel', '路线 A（调参前）'],
      ['platformTuneRouteBLabel', '路线 B（调参后）'],
    ];
    for (const [id, fb] of map) {
      const el = document.getElementById(id);
      if (el) el.textContent = tr(id, fb);
    }
    const btn = document.getElementById('platformTuneCompareBtn');
    if (btn) btn.textContent = tr('platformTuneCompareBtn', '开始对比');
  }

  async function bootstrapWorkspace() {
    const btn = document.getElementById('platformWorkspaceBootstrap');
    await withBusy(btn, async () => {
      const { data } = await api('POST', '/api/ai/platform/workspace-health', { operation: 'bootstrap' });
      if (data?.ok) {
        toast(tr('platformWorkspaceBootstrapped', '模板已写入'), 'success');
        await loadWorkspace();
        await refreshWorkspaceHealth();
      } else {
        toast(data?.error || tr('saveFailed', '保存失败'), 'error');
      }
    }, tr('uiWorking', '处理中…'));
  }

  async function refreshWorkspaceHealth() {
    const status = document.getElementById('platformWorkspaceHealthStatus');
    const { data } = await api('GET', '/api/ai/platform/workspace-health');
    if (!status) return;
    const sparse = data?.sparse || [];
    if (!sparse.length) {
      status.textContent = tr('platformWorkspaceHealthy', '工作区内容充足');
      return;
    }
    status.textContent = tr('platformWorkspaceSparse', '待补充') + ': ' + sparse.map((s) => s.filename).join(', ');
  }

  async function refreshBackupManifest() {
    const box = document.getElementById('platformBackupManifest');
    if (!box) return;
    const { data } = await api('GET', '/api/ai/platform/backup');
    const m = data?.manifest || {};
    const hubAccounts = m.modelHubAccounts ?? 0;
    const hubRoutes = m.modelHubRoutes ?? 0;
    const hubFallbacks = m.modelHubFallbacks ?? 0;
    const embRoutes = m.embeddingRoutes ?? 0;
    const embFallbacks = m.embeddingFallbacks ?? 0;
    const modelLine = m.modelConfigured
      ? (hubRoutes > 1
        ? `${m.provider || ''} / ${m.model || ''} (+${hubFallbacks} ${tr('modelHubFallbacks', '备用')})`
        : `${m.provider || ''} / ${m.model || ''}`)
      : tr('platformBackupModelMissing', '未配置模型');
    const hubLine = hubAccounts
      ? `${hubAccounts} ${tr('modelHubAccountsTitle', '服务商账户')} · ${hubRoutes} ${tr('modelHubListTitle', '模型')}`
      : '—';
    box.innerHTML = [
      `<div class="platform-list-item">${tr('platformBackupModel', '模型')}: ${esc(modelLine)}</div>`,
      `<div class="platform-list-item">${tr('modelHubTitle', '模型中心')}: ${esc(hubLine)}</div>`,
      `<div class="platform-list-item">${tr('platformBackupEmbedding', 'Embedding')}: ${esc(m.embeddingModel || '—')}${embRoutes > 1 ? ` (+${embFallbacks} ${tr('modelHubFallbacks', '备用')})` : ''}</div>`,
      `<div class="platform-list-item">${tr('platformBackupMemory', '记忆')}: ${m.memoryNotes ?? 0}</div>`,
      `<div class="platform-list-item">${tr('platformBackupSessions', '会话')}: ${m.sessions ?? 0}</div>`,
      `<div class="platform-list-item">${tr('platformBackupSkills', '技能')}: ${m.learnedSkills ?? 0} (+${m.enabledSkills ?? 0} 启用)</div>`,
      `<div class="platform-list-item">MCP: ${m.mcpServers ?? 0}</div>`,
      `<div class="platform-list-item">${tr('platformBackupWorkspace', '工作区')}: ${m.workspaceFiles ?? 0}</div>`,
    ].join('');
  }

  function triggerBlobDownload(blob, filename) {
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = objectUrl;
    a.download = filename.endsWith('.opbak') ? filename : `${filename}.opbak`;
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(objectUrl);
  }

  function parseDownloadFilename(res, fallback) {
    const disp = res.headers?.get?.('content-disposition') || '';
    const match = /filename\*?=(?:UTF-8''|")?([^";\n]+)"?/i.exec(disp);
    const raw = match?.[1] ? decodeURIComponent(match[1].trim()) : '';
    return raw || fallback || `opassist-backup-${Date.now()}.opbak`;
  }

  async function exportBackup() {
    const btn = document.getElementById('platformBackupExport');
    const includeSecrets = !!document.getElementById('platformBackupIncludeSecrets')?.checked;
    const link = document.getElementById('platformBackupDownload');
    await withBusy(btn, async () => {
      const headers = {
        ...((typeof WebApi !== 'undefined' && WebApi.getApiHeaders) ? WebApi.getApiHeaders() : {}),
        'Content-Type': 'application/json',
      };
      let data = null;
      try {
        const res = await fetch('/api/ai/platform/backup', {
          method: 'POST',
          headers,
          body: JSON.stringify({
            operation: 'export',
            include_secrets: includeSecrets,
            direct_download: true,
          }),
        });
        const contentType = (res.headers.get('content-type') || '').toLowerCase();
        if (res.ok && !contentType.includes('application/json')) {
          const blob = await res.blob();
          const filename = parseDownloadFilename(res, `opassist-backup-${Date.now()}.opbak`);
          triggerBlobDownload(blob, filename);
          if (link) link.hidden = true;
          toast(tr('platformBackupExported', '备份已导出'), 'success');
          refreshBackupManifest().catch(() => {});
          return;
        }
        data = await res.json();
      } catch (e) {
        console.error('backup export', e);
        toast(tr('saveFailed', '保存失败'), 'error');
        return;
      }
      if (!data?.ok) {
        toast(data?.error || tr('saveFailed', '保存失败'), 'error');
        return;
      }
      const dl = data?.download;
      if (dl?.url && dl?.filename) {
        try {
          const dlHeaders = (typeof WebApi !== 'undefined' && WebApi.getApiHeaders) ? WebApi.getApiHeaders() : {};
          const res = await fetch(dl.url, { headers: dlHeaders });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const blob = await res.blob();
          triggerBlobDownload(blob, dl.filename);
        } catch (e) {
          console.error('backup download', e);
          if (link) {
            link.href = dl.url;
            link.download = dl.filename;
            link.textContent = tr('platformBackupDownload', '下载') + ` (${dl.filename})`;
            link.hidden = false;
          }
          toast(tr('platformBackupExported', '备份已导出') + ' — ' + tr('platformBackupDownload', '下载'), 'success');
          refreshBackupManifest().catch(() => {});
          return;
        }
      }
      if (link && dl?.url) {
        link.href = dl.url;
        link.download = dl.filename || 'backup.opbak';
        link.textContent = tr('platformBackupDownload', '下载') + (dl.filename ? ` (${dl.filename})` : '');
        link.hidden = false;
      }
      toast(tr('platformBackupExported', '备份已导出'), 'success');
      refreshBackupManifest().catch(() => {});
    }, tr('uiWorking', '处理中…'));
  }

  function bindFilePicker(inputId, nameId, buttonId) {
    const input = document.getElementById(inputId);
    const nameEl = document.getElementById(nameId);
    const btn = document.getElementById(buttonId);
    if (!input) return;
    const defaultLabel = tr('platformBackupNoFile', '未选择文件');
    const update = () => {
      const file = input.files?.[0];
      if (nameEl) {
        nameEl.textContent = file ? file.name : defaultLabel;
        nameEl.classList.toggle('has-file', !!file);
      }
    };
    btn?.addEventListener('click', () => input.click());
    input.addEventListener('change', update);
    update();
  }

  async function uploadBackupFile(file, { mode = 'merge', confirm = false } = {}) {
    if (!file || !api) return { data: { ok: false, error: 'no file' } };
    const form = new FormData();
    form.append('file', file);
    form.append('mode', mode);
    form.append('confirm', confirm ? 'true' : 'false');
    const headers = (typeof WebApi !== 'undefined' && WebApi.getApiHeaders) ? WebApi.getApiHeaders() : {};
    const res = await fetch('/api/ai/platform/backup', { method: 'POST', headers, body: form });
    const text = await res.text();
    let data;
    try { data = JSON.parse(text); } catch { data = { ok: false, error: text }; }
    return { status: res.status, data };
  }

  function getRestoreBundleFromJsonField() {
    const raw = document.getElementById('platformBackupRestoreJson')?.value?.trim();
    if (!raw) return null;
    try {
      const bundle = JSON.parse(raw);
      return bundle.bundle ? bundle : { bundle };
    } catch {
      return null;
    }
  }

  async function restoreBackupPreview() {
    const file = document.getElementById('platformBackupRestoreFile')?.files?.[0];
    const status = document.getElementById('platformBackupRestoreStatus');
    const mode = document.getElementById('platformBackupRestoreMode')?.value || 'merge';
    if (file) {
      const { data } = await uploadBackupFile(file, { mode, confirm: false });
      if (status) {
        status.textContent = data?.preview
          ? JSON.stringify(data.preview, null, 2)
          : (data?.error || '');
      }
      if (!data?.preview && data?.error) toast(data.error, 'error');
      return;
    }
    const bundle = getRestoreBundleFromJsonField();
    if (!bundle) {
      toast(tr('platformBackupPickFile', '请选择 .opbak 文件或粘贴 JSON'), 'warning');
      return;
    }
    const { data } = await api('POST', '/api/ai/platform/backup', {
      operation: 'restore',
      bundle,
      mode,
      confirm: false,
    });
    if (status) {
      status.textContent = data?.preview
        ? JSON.stringify(data.preview, null, 2)
        : (data?.error || '');
    }
  }

  async function restoreBackupApply() {
    const btn = document.getElementById('platformBackupRestoreApply');
    const file = document.getElementById('platformBackupRestoreFile')?.files?.[0];
    const mode = document.getElementById('platformBackupRestoreMode')?.value || 'merge';
    await withBusy(btn, async () => {
      let data;
      if (file) {
        ({ data } = await uploadBackupFile(file, { mode, confirm: true }));
      } else {
        const bundle = getRestoreBundleFromJsonField();
        if (!bundle) {
          toast(tr('platformBackupPickFile', '请选择 .opbak 文件或粘贴 JSON'), 'warning');
          return;
        }
        ({ data } = await api('POST', '/api/ai/platform/backup', {
          operation: 'restore',
          bundle,
          mode,
          confirm: true,
        }));
      }
      if (data?.ok) {
        toast(tr('platformBackupRestored', '恢复完成') + `: ${(data.applied || []).join(', ')}`, 'success');
        refreshBackupManifest().catch(() => {});
        refreshLearned().catch(() => {});
        loadWorkspace().catch(() => {});
        refreshMcp().catch(() => {});
        loadMemoryAndPassport().catch(() => {});
      } else {
        toast(data?.error || tr('saveFailed', '保存失败'), 'error');
      }
    }, tr('uiWorking', '处理中…'));
  }

  async function refreshEvolutionStatus() {
    const box = document.getElementById('platformEvolutionStatus');
    if (!box) return;
    const { data } = await api('GET', '/api/ai/platform/evolution');
    box.innerHTML = [
      `<div class="platform-list-item">${tr('platformEvolutionPending', '待批准')}: ${data?.pendingSkills ?? 0}</div>`,
      `<div class="platform-list-item">${tr('platformEvolutionHotspots', '热点轨迹')}: ${data?.hotspots ?? 0}</div>`,
    ].join('');
  }

  async function scanEvolutionTraces() {
    const btn = document.getElementById('platformEvolutionScan');
    const box = document.getElementById('platformEvolutionTraces');
    await withBusy(btn, async () => {
      const { data } = await api('GET', '/api/ai/platform/evolution?view=traces');
      if (!box) return;
      box.innerHTML = '';
      for (const t of (data?.hotspots || [])) {
        const row = document.createElement('div');
        row.className = 'platform-list-item';
        row.textContent = `${t.title} (score=${t.score}) — ${(t.signals || []).slice(0, 4).join(', ')}`;
        box.appendChild(row);
      }
      if (!data?.hotspots?.length) {
        box.innerHTML = `<p class="field-hint">${tr('platformEvolutionNoHotspots', '暂无显著失败信号')}</p>`;
      }
    }, tr('uiSearching', '搜索中…'));
  }

  async function proposeEvolution() {
    const btn = document.getElementById('platformEvolutionPropose');
    await withBusy(btn, async () => {
      const { data } = await api('POST', '/api/ai/platform/evolution', {});
      if (data?.ok) {
        toast(tr('platformEvolutionProposed', '进化提案已创建，请在「已学技能」批准'), 'success');
        refreshLearned().catch(() => {});
        refreshEvolutionStatus().catch(() => {});
      } else {
        toast(data?.error || tr('saveFailed', '保存失败'), 'error');
      }
    }, tr('uiWorking', '处理中…'));
  }

  function bind() {
    document.getElementById('platformWorkspaceBootstrap')?.addEventListener('click', () => bootstrapWorkspace().catch(console.error));
    document.getElementById('platformWorkspaceHealth')?.addEventListener('click', () => refreshWorkspaceHealth().catch(console.error));
    document.getElementById('platformBackupExport')?.addEventListener('click', () => exportBackup().catch(console.error));
    document.getElementById('platformBackupRestorePreview')?.addEventListener('click', () => restoreBackupPreview().catch(console.error));
    document.getElementById('platformBackupRestoreApply')?.addEventListener('click', () => restoreBackupApply().catch(console.error));
    bindFilePicker('platformBackupRestoreFile', 'platformBackupRestoreFileName', 'platformBackupRestorePick');
    document.getElementById('platformEvolutionScan')?.addEventListener('click', () => scanEvolutionTraces().catch(console.error));
    document.getElementById('platformEvolutionPropose')?.addEventListener('click', () => proposeEvolution().catch(console.error));
    document.getElementById('platformWorkspaceLoad')?.addEventListener('click', () => loadWorkspace().catch(console.error));
    document.getElementById('platformWorkspaceSave')?.addEventListener('click', () => saveWorkspace().catch(console.error));
    document.getElementById('platformWorkspaceKey')?.addEventListener('change', () => loadWorkspace().catch(console.error));
    document.getElementById('platformMcpAdd')?.addEventListener('click', () => addMcp().catch(console.error));
    document.getElementById('platformSessionSearch')?.addEventListener('click', () => searchSessions().catch(console.error));
    document.getElementById('chatVerboseToggle')?.addEventListener('change', saveDebugToggles);
    document.getElementById('chatTraceToggle')?.addEventListener('change', saveDebugToggles);
    document.getElementById('platformTuneCompareBtn')?.addEventListener('click', () => runTuneCompare().catch(console.error));
    document.getElementById('schedNlBtn')?.addEventListener('click', () => addSchedulerFromNl().catch(console.error));
  }

  function onSettingsOpen(tab) {
    if (tab !== 'platform') return;
    loadWorkspace().catch(() => {});
    refreshWorkspaceHealth().catch(() => {});
    refreshBackupManifest().catch(() => {});
    refreshEvolutionStatus().catch(() => {});
    refreshMcp().catch(() => {});
    refreshLearned().catch(() => {});
    loadMemoryAndPassport().catch(() => {});
    if (!tuneRoutesLoaded) loadTuneRouteOptions().catch(() => {});
    applyPlatformTranslations();
    loadDebugToggles();
  }

  return {
    init,
    onSettingsOpen,
    bindFilePicker,
    restoreFromFile: (file, opts) => uploadBackupFile(file, { mode: opts?.mode || 'merge', confirm: !!opts?.confirm }),
    getChatDebugPrefs: () => (
      (typeof LocalPrefs !== 'undefined' && LocalPrefs.getChatDebugPrefs)
        ? LocalPrefs.getChatDebugPrefs()
        : { verbose: false, trace: false }
    ),
  };
})();
