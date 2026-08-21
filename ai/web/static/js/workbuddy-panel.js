/**
 * WorkBuddy panel — harness config, experts, audit trail (settings→平台).
 */
const WorkbuddyPanel = (() => {
  let api = null;
  let showToast = null;
  let currentModelTier = 'auto';

  const TIER_META = {
    auto: { key: 'modelTierAuto', fallback: '自动' },
    lite: { key: 'modelTierLite', fallback: '轻量' },
    default: { key: 'modelTierDefault', fallback: '标准' },
    craft: { key: 'modelTierCraft', fallback: '深度' },
  };

  function tr(key, fallback) {
    return (typeof t === 'function') ? t(key, fallback) : fallback;
  }

  function tierLabel(tier) {
    const meta = TIER_META[tier] || TIER_META.auto;
    return tr(meta.key, meta.fallback);
  }

  function refreshTierMenuLabels() {
    document.querySelectorAll('.composer-tier-option').forEach((opt) => {
      const tier = opt.dataset.tier || 'auto';
      opt.textContent = tierLabel(tier);
    });
  }

  function setModelTier(tier, opts = {}) {
    currentModelTier = tier || 'auto';
    const btn = document.getElementById('modelTierBtn');
    const harnessTier = document.getElementById('harnessModelTier');
    if (btn) {
      btn.textContent = tierLabel(currentModelTier);
      btn.title = `${tr('modelTierLabel', '模型档位')}: ${tierLabel(currentModelTier)}`;
    }
    document.querySelectorAll('.composer-tier-option').forEach((opt) => {
      opt.classList.toggle('active', opt.dataset.tier === currentModelTier);
    });
    if (harnessTier && !opts.skipHarness) harnessTier.value = currentModelTier;
  }

  function toast(msg, type = 'info') {
    if (typeof showToast === 'function') showToast(msg, type);
  }

  function esc(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  async function loadHarnessConfig() {
    if (!api) return;
    const { data } = await api('GET', '/api/ai/harness/config');
    if (!data?.ok) return;
    const def = document.getElementById('harnessDeferredToggle');
    const ext = document.getElementById('harnessExternalizeToggle');
    const thr = document.getElementById('harnessExternalizeThreshold');
    const tier = document.getElementById('harnessModelTier');
    if (def) def.checked = !!data.deferredTools;
    if (ext) ext.checked = !!data.externalizeResults;
    if (thr) thr.value = String(data.externalizeThreshold || 8192);
    if (tier) tier.value = data.modelTier || 'auto';
    const btn = document.getElementById('modelTierBtn');
    if (btn && !btn.dataset.userSet) setModelTier(data.modelTier || 'auto', { skipHarness: true });
  }

  async function saveHarnessConfig() {
    const btn = document.getElementById('harnessConfigSave');
    if (btn) btn.disabled = true;
    try {
      const { data } = await api('POST', '/api/ai/harness/config', {
        deferredTools: !!document.getElementById('harnessDeferredToggle')?.checked,
        externalizeResults: !!document.getElementById('harnessExternalizeToggle')?.checked,
        externalizeThreshold: parseInt(document.getElementById('harnessExternalizeThreshold')?.value || '8192', 10),
        modelTier: document.getElementById('harnessModelTier')?.value || 'auto',
      });
      if (data?.ok) toast(tr('saved', '已保存'), 'success');
      else toast(data?.error || tr('saveFailed', '保存失败'), 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function refreshExperts() {
    const box = document.getElementById('platformExpertsList');
    if (!box || !api) return;
    const { data } = await api('GET', '/api/ai/agents');
    box.innerHTML = '';
    const disabled = new Set(data?.disabled || []);
    for (const a of (data?.agents || [])) {
      if (a.is_orchestrator) continue;
      const row = document.createElement('label');
      row.className = 'platform-check-row platform-expert-row';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = !disabled.has(a.id);
      cb.dataset.agentId = a.id;
      cb.addEventListener('change', () => saveExperts().catch(console.error));
      const span = document.createElement('span');
      span.textContent = `${a.icon || '🤖'} ${a.name || a.id} — ${(a.description || '').slice(0, 60)}`;
      row.appendChild(cb);
      row.appendChild(span);
      box.appendChild(row);
    }
  }

  async function saveExperts() {
    const box = document.getElementById('platformExpertsList');
    if (!box) return;
    const disabled = [];
    box.querySelectorAll('input[type=checkbox]').forEach((cb) => {
      if (!cb.checked) disabled.push(cb.dataset.agentId);
    });
    const { data } = await api('POST', '/api/ai/agents', { disabled });
    if (data?.ok) toast(tr('platformExpertsSaved', '专员设置已保存'), 'success');
    else toast(data?.error || tr('saveFailed', '保存失败'), 'error');
  }

  async function refreshAudit() {
    const list = document.getElementById('platformAuditList');
    const status = document.getElementById('platformAuditStatus');
    const badge = document.getElementById('platformAuditChainBadge');
    if (!list || !api) return;
    const { data } = await api('GET', '/api/ai/audit?limit=40');
    if (!data?.ok) {
      if (status) status.textContent = data?.error || '';
      return;
    }
    const chainOk = data.chain_ok !== false;
    if (badge) {
      badge.textContent = chainOk ? '✓' : '!';
      badge.classList.toggle('err', !chainOk);
    }
    if (status) {
      status.textContent = chainOk
        ? tr('platformAuditChainOk', '哈希链验证通过')
        : tr('platformAuditChainBroken', '哈希链异常，请检查日志');
    }
    list.innerHTML = '';
    for (const e of (data.entries || [])) {
      const li = document.createElement('li');
      li.className = 'dev-item';
      const ts = e.ts ? new Date(e.ts).toLocaleString() : '';
      const ok = e.ok !== false ? '✓' : '✗';
      li.innerHTML = `<span class="audit-ok">${ok}</span> <code>${esc(e.tool || e.action)}</code> <time>${esc(ts)}</time>`;
      list.appendChild(li);
    }
    if (!data.entries?.length) {
      list.innerHTML = `<li class="field-hint">${tr('platformAuditEmpty', '暂无审计记录')}</li>`;
    }
  }

  async function verifyAudit() {
    const status = document.getElementById('platformAuditStatus');
    const { data } = await api('GET', '/api/ai/audit?limit=200');
    if (!data?.ok) {
      toast(data?.error || tr('saveFailed', '失败'), 'error');
      return;
    }
    const chain = data.chain || {};
    const msg = chain.ok && !chain.broken
      ? `${tr('platformAuditVerified', '已验证')} ${chain.verified || 0} ${tr('platformAuditEntries', '条')}`
      : (chain.error || tr('platformAuditChainBroken', '哈希链异常'));
    if (status) status.textContent = msg;
    toast(msg, chain.ok ? 'success' : 'error');
    refreshAudit().catch(() => {});
  }

  async function refreshSchedulerBoard() {
    const box = document.getElementById('schedulerTaskBoard');
    if (!box || !api) return;
    const { data } = await api('GET', '/api/ai/scheduler');
    const tasks = data?.tasks || data?.items || [];
    if (!tasks.length) {
      box.innerHTML = `<p class="field-hint">${tr('schedulerBoardEmpty', '暂无定时任务')}</p>`;
      return;
    }
    box.innerHTML = tasks.map((task) => {
      const name = esc(task.name || task.id || 'task');
      const enabled = task.enabled !== false;
      const last = task.last_run || task.lastRun || '—';
      const status = enabled ? tr('schedulerEnabled', '启用') : tr('schedulerDisabled', '禁用');
      return `<div class="scheduler-board-row">
        <strong>${name}</strong>
        <span class="scheduler-board-meta">${status} · ${esc(String(last))}</span>
      </div>`;
    }).join('');
  }

  function bindModelTierSelect() {
    const root = document.getElementById('composerTierPicker');
    const btn = document.getElementById('modelTierBtn');
    const menu = document.getElementById('modelTierMenu');
    if (!root || !btn || !menu || root.dataset.bound) return;
    root.dataset.bound = '1';
    refreshTierMenuLabels();
    setModelTier(currentModelTier, { skipHarness: true });

    const closeMenu = () => {
      menu.classList.add('hidden');
      btn.setAttribute('aria-expanded', 'false');
    };

    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (menu.classList.contains('hidden')) {
        refreshTierMenuLabels();
        menu.classList.remove('hidden');
        btn.setAttribute('aria-expanded', 'true');
      } else {
        closeMenu();
      }
    });

    menu.querySelectorAll('.composer-tier-option').forEach((opt) => {
      opt.addEventListener('click', async () => {
        const tier = opt.dataset.tier || 'auto';
        btn.dataset.userSet = '1';
        setModelTier(tier);
        closeMenu();
        if (api) {
          await api('POST', '/api/ai/harness/config', { modelTier: tier });
        }
      });
    });

    document.addEventListener('click', (e) => {
      if (!root.contains(e.target)) closeMenu();
    });
  }

  async function refreshUsageSummary() {
    const box = document.getElementById('platformUsageSummary');
    if (!box || !api) return;
    const { data } = await api('GET', '/api/ai/usage/summary?groupBy=model&limit=10');
    if (!data?.ok) {
      box.innerHTML = `<p class="field-hint">${esc(data?.error || '')}</p>`;
      return;
    }
    box.innerHTML = (data.rows || []).map((r) =>
      `<div class="platform-list-item"><code>${esc(r.key)}</code> — ${r.calls} calls · ${r.total_tokens} tokens</div>`
    ).join('') || `<p class="field-hint">${tr('platformUsageEmpty', '暂无用量记录')}</p>`;
  }

  async function refreshProfileSync() {
    const box = document.getElementById('platformProfileSyncStatus');
    if (!box || !api) return;
    const { data } = await api('GET', '/api/ai/profile/sync');
    if (!data?.ok) return;
    const m = data.manifest || {};
    box.textContent = `${tr('profileSyncUpdated', '更新时间')}: ${m.updatedAt ? new Date(m.updatedAt * 1000).toLocaleString() : '—'}`;
  }

  async function exportProfileManifest() {
    const ta = document.getElementById('platformProfileSyncJson');
    const { data } = await api('GET', '/api/ai/profile/sync');
    if (ta && data?.manifest) ta.value = JSON.stringify(data.manifest, null, 2);
  }

  async function importProfileManifest() {
    const ta = document.getElementById('platformProfileSyncJson');
    const mode = document.getElementById('platformProfileSyncMode')?.value || 'merge';
    if (!ta?.value?.trim()) {
      toast(tr('profileSyncPaste', '请粘贴 manifest JSON'), 'warning');
      return;
    }
    let manifest;
    try { manifest = JSON.parse(ta.value); } catch {
      toast(tr('profileSyncInvalid', 'JSON 无效'), 'error');
      return;
    }
    const { data } = await api('POST', '/api/ai/profile/sync', { manifest, mode });
    if (data?.ok) {
      toast(`${tr('profileSyncApplied', '已应用')}: ${(data.applied || []).join(', ')}`, 'success');
      loadHarnessConfig().catch(() => {});
      refreshExperts().catch(() => {});
    } else {
      toast(data?.error || tr('saveFailed', '失败'), 'error');
    }
  }

  async function refreshTranscriptViewer() {
    const box = document.getElementById('platformTranscriptList');
    const sid = typeof SessionStore !== 'undefined' ? SessionStore.activeId : '';
    if (!box || !api || !sid) {
      if (box) box.innerHTML = `<p class="field-hint">${tr('transcriptNoSession', '请先选择会话')}</p>`;
      return;
    }
    const { data } = await api('GET', `/api/ai/transcript?sessionId=${encodeURIComponent(sid)}&limit=80`);
    if (!data?.ok) {
      box.innerHTML = `<p class="field-hint">${esc(data?.error || '')}</p>`;
      return;
    }
    box.innerHTML = (data.events || []).slice().reverse().map((e) => {
      const ts = e.ts ? new Date(e.ts).toLocaleString() : '';
      return `<div class="platform-list-item transcript-row"><code>${esc(e.type)}</code> <time>${esc(ts)}</time></div>`;
    }).join('') || `<p class="field-hint">${tr('transcriptEmpty', '暂无 transcript')}</p>`;
  }

  async function recoverActiveTranscript() {
    const sid = typeof SessionStore !== 'undefined' ? SessionStore.activeId : '';
    if (!sid || typeof TranscriptRecovery === 'undefined') return;
    const { data } = await api('GET', `/api/ai/transcript/recover?sessionId=${encodeURIComponent(sid)}`);
    if (data?.ok && data.recoverable) TranscriptRecovery.applyRecovery(sid, data);
    else toast(tr('transcriptNotRecoverable', '当前会话无可恢复内容'), 'info');
  }

  function bind() {
    document.getElementById('harnessConfigSave')?.addEventListener('click', () => saveHarnessConfig().catch(console.error));
    document.getElementById('platformAuditRefresh')?.addEventListener('click', () => refreshAudit().catch(console.error));
    document.getElementById('platformAuditVerify')?.addEventListener('click', () => verifyAudit().catch(console.error));
    document.getElementById('platformProfileSyncExport')?.addEventListener('click', () => exportProfileManifest().catch(console.error));
    document.getElementById('platformProfileSyncImport')?.addEventListener('click', () => importProfileManifest().catch(console.error));
    document.getElementById('platformTranscriptRefresh')?.addEventListener('click', () => refreshTranscriptViewer().catch(console.error));
    document.getElementById('platformTranscriptRecover')?.addEventListener('click', () => recoverActiveTranscript().catch(console.error));
    bindModelTierSelect();
  }

  function onSettingsOpen(tab) {
    if (tab === 'platform') {
      loadHarnessConfig().catch(() => {});
      refreshExperts().catch(() => {});
      refreshAudit().catch(() => {});
      refreshUsageSummary().catch(() => {});
      refreshProfileSync().catch(() => {});
      refreshTranscriptViewer().catch(() => {});
      if (typeof WorkflowEditor !== 'undefined') WorkflowEditor.onSettingsOpen();
    }
    if (tab === 'scheduler') {
      refreshSchedulerBoard().catch(() => {});
    }
  }

  function getModelTier() {
    return currentModelTier || 'auto';
  }

  function init(deps = {}) {
    api = deps.api || (typeof WebApi !== 'undefined' ? WebApi.api : null);
    showToast = deps.showToast || null;
    bind();
    loadHarnessConfig().catch(() => {});
  }

  function onLangChange() {
    refreshTierMenuLabels();
    setModelTier(currentModelTier, { skipHarness: true });
  }

  return { init, onSettingsOpen, getModelTier, refreshAudit, refreshSchedulerBoard, onLangChange };
})();
