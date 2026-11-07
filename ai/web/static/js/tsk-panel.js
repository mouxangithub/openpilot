/**
 * Toyota SecOC / TSK — centered modal + header shortcut.
 */
const TskPanel = (() => {
  const $ = (id) => document.getElementById(id);

  let translate = (key, fallback) => fallback ?? key;

  function t(key, fallback) {
    return translate(key, fallback);
  }

  const state = {
    key: '',
    running: false,
    canReady: false,
    dfReady: false,
    dfPartial: false,
    dfBytes: 0,
    dfTotal: 32768,
    job: null,
    pandadProcess: 'pandad',
    onroad: false,
    flashAllowed: true,
    flashBlockedReason: '',
  };

  let pollTimer = null;

  function els() {
    return {
      keyLight: $('tskKeyLight'),
      keyTitle: $('tskKeyTitle'),
      keyDetail: $('tskKeyDetail'),
      canDot: $('tskCanDot'),
      canDetail: $('tskCanDetail'),
      dfDot: $('tskDfDot'),
      dfDetail: $('tskDfDetail'),
      canBtn: $('tskCanBtn'),
      dfBtn: $('tskDfBtn'),
      matcherBtn: $('tskMatcherBtn'),
      cleanerBtn: $('tskCleanerBtn'),
      uninstallBtn: $('tskUninstallBtn'),
      manualKeyInput: $('tskManualKeyInput'),
      manualInstallBtn: $('tskManualInstallBtn'),
      extractBtn: $('tskExtractBtn'),
      rebootDeviceBtn: $('tskRebootDeviceBtn'),
      restartManagerBtn: $('tskRestartManagerBtn'),
      restartPandadBtn: $('tskRestartPandadBtn'),
      flashPandaBtn: $('tskFlashPandaBtn'),
      pandaStatusDetail: $('tskPandaStatusDetail'),
      pandaGuidance: $('tskPandaGuidance'),
      cancelJobBtn: $('tskCancelJobBtn'),
      jobLog: $('tskJobLog'),
      jobTitle: $('tskJobTitle'),
      modal: $('tskModal'),
      modalTitle: $('tskModalTitle'),
      modalBody: $('tskModalBody'),
      modalActions: $('tskModalActions'),
      finding: $('tskFinding'),
    };
  }

  function formatKey(hex) {
    const groups = (hex || '').match(/.{1,4}/g) || [];
    const half = Math.ceil(groups.length / 2);
    return `${groups.slice(0, half).join(' ')}\n${groups.slice(half).join(' ')}`;
  }

  function setKey(key) {
    const e = els();
    state.key = key || '';
    if (!e.keyTitle) return;
    if (state.key) {
      e.keyLight?.classList.add('good');
      e.keyTitle.textContent = t('tskKeyInstalled', '密钥已安装');
      if (e.keyDetail) e.keyDetail.textContent = formatKey(state.key);
    } else {
      e.keyLight?.classList.remove('good');
      e.keyTitle.textContent = t('tskKeyNotInstalled', '密钥未安装');
      if (e.keyDetail) e.keyDetail.textContent = '';
    }
    if (e.uninstallBtn) {
      const show = !!state.key;
      e.uninstallBtn.hidden = !show;
      e.uninstallBtn.classList.toggle('hidden', !show);
      e.uninstallBtn.disabled = !show || state.running;
    }
    syncActionButtons();
  }

  function syncActionButtons() {
    const e = els();
    if (!e.matcherBtn) return;
    if (state.running) return;

    const hasDf = state.dfReady || state.dfPartial;
    const matcherReady = state.canReady && hasDf;
    e.matcherBtn.disabled = !matcherReady;
    e.matcherBtn.classList.toggle('primary', matcherReady);

    const needCan = !state.canReady;
    const needDf = !hasDf;
    if (matcherReady) {
      e.matcherBtn.textContent = t('tskMatcherBtn', '查找丰田 SecOC 密钥');
    } else if (needCan && needDf) {
      e.matcherBtn.textContent = t('tskMatcherNeedBoth', '查找密钥（需 CAN 与 DataFlash）');
    } else if (needCan) {
      e.matcherBtn.textContent = t('tskMatcherNeedCan', '查找密钥（需 CAN）');
    } else {
      e.matcherBtn.textContent = t('tskMatcherNeedDf', '查找密钥（需 DataFlash）');
    }

    const hasCache = state.canReady || state.dfReady || state.dfPartial;
    if (e.cleanerBtn) e.cleanerBtn.disabled = !hasCache;
  }

  function setRunning(running) {
    state.running = running;
    const e = els();
    const all = [e.canBtn, e.dfBtn, e.matcherBtn, e.cleanerBtn, e.uninstallBtn, e.manualInstallBtn, e.extractBtn, e.flashPandaBtn];
    if (running) {
      all.forEach((btn) => {
        if (btn) btn.disabled = true;
      });
      return;
    }
    [e.canBtn, e.dfBtn, e.extractBtn, e.manualInstallBtn].forEach((btn) => {
      if (btn) btn.disabled = false;
    });
    setKey(state.key);
    syncActionButtons();
  }

  async function readJsonResponse(res) {
    const text = await res.text();
    if (!text.trim()) return {};
    try {
      return JSON.parse(text);
    } catch (e) {
      const preview = text.slice(0, 160).replace(/\s+/g, ' ').trim();
      throw new Error(
        preview
          ? `服务器返回非 JSON（HTTP ${res.status}）：${preview}`
          : `服务器返回非 JSON（HTTP ${res.status}）`
      );
    }
  }

  async function fetchWithTimeout(url, options = {}, timeoutMs = 15000) {
    const ac = new AbortController();
    const timer = setTimeout(() => ac.abort(), timeoutMs);
    try {
      return await fetch(url, { ...options, signal: ac.signal });
    } finally {
      clearTimeout(timer);
    }
  }

  // Long-running operations (panda flash, firmware build) need a much larger
  // timeout than the 15s default. Pass an explicit `timeoutMs` per call site
  // when invoking `postJson` / `fetchJson` to avoid spurious AbortErrors.
  const FETCH_TIMEOUT_MS_DEFAULT = 15000;
  const FETCH_TIMEOUT_MS_FLASH = 5 * 60 * 1000; // 5 min — full F4/H7 flash + verify
  const FETCH_TIMEOUT_MS_BUILD = 10 * 60 * 1000; // 10 min — scons can be slow on first run

  async function fetchJson(url, opts = {}) {
    const timeoutMs = opts.timeoutMs ?? FETCH_TIMEOUT_MS_DEFAULT;
    const res = await fetchWithTimeout(url, { cache: 'no-store' }, timeoutMs);
    return readJsonResponse(res);
  }

  async function postJson(url, payload = {}, opts = {}) {
    const timeoutMs = opts.timeoutMs ?? FETCH_TIMEOUT_MS_DEFAULT;
    const res = await fetchWithTimeout(
      url,
      {
        method: 'POST',
        cache: 'no-store',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
      timeoutMs,
    );
    const result = await readJsonResponse(res);
    return { response: res, result };
  }

  function setDfDetail(df) {
    const e = els();
    if (!e.dfDetail) return;
    const status = df.status || 'idle';
    if (status === 'running') {
      e.dfDetail.textContent = `正在导出 ${df.bytes || 0} / ${df.total || 32768}`;
      e.dfDetail.className = 'tsk-step-detail';
    } else if (status === 'partial') {
      e.dfDetail.textContent = df.message || '部分导出，可尝试查找或重新导出';
      e.dfDetail.className = 'tsk-step-detail warn';
    } else if (status === 'key_missed') {
      e.dfDetail.textContent = df.message || '数据不足，请重新导出';
      e.dfDetail.className = 'tsk-step-detail err';
    } else if (df.ready) {
      e.dfDetail.textContent = '已完成';
      e.dfDetail.className = 'tsk-step-detail ok';
    } else {
      e.dfDetail.textContent = 'Not Ready to Drive 模式下导出';
      e.dfDetail.className = 'tsk-step-detail';
    }
  }

  function firmwareGuidanceText(guidance) {
    if (!guidance) return '';
    const lang = (document.documentElement.lang || 'zh').toLowerCase();
    const en = lang.startsWith('en');
    const summary = en ? (guidance.summary_en || guidance.summary_zh) : (guidance.summary_zh || guidance.summary_en);
    const mads = en ? (guidance.mads_en || guidance.mads_zh) : (guidance.mads_zh || guidance.mads_en);
    if (!summary && !mads) return '';
    return mads ? `${summary}\n${mads}` : summary;
  }

  function formatPandaStatus(data) {
    const pandas = data?.pandas || [];
    if (!pandas.length) return t('pandaStatusNone', '未检测到 Panda');
    return pandas.map((p) => {
      if (p.error) return `${p.serial}: ${p.error}`;
      const role = p.internal ? t('pandaInternal', '内置') : t('pandaExternal', '外接');
      const hw = p.hw_type_name || p.hw_type || '?';
      let match = '—';
      if (p.firmware_match === true) match = t('pandaFwMatch', '已匹配');
      else if (p.firmware_match === false) match = t('pandaFwMismatch', '需刷写');
      const sig = p.signature ? ` sig ${p.signature}` : '';
      return `${role} ${hw} · ${match}${sig}`;
    }).join('\n');
  }

  async function refreshPandaStatus() {
    const e = els();
    if (!e.pandaStatusDetail) return;
    try {
      const data = await fetchJson('/api/panda/status');
      state.onroad = !!data.onroad;
      state.flashAllowed = data.flash_allowed !== false;
      state.flashBlockedReason = data.flash_blocked_reason || '';
      let text = formatPandaStatus(data);
      if (!state.flashAllowed) {
        text += `\n\n${state.flashBlockedReason || t('pandaFlashOffroadBody', '当前 onroad，请在 offroad 下刷写。')}`;
      }
      e.pandaStatusDetail.textContent = text;
      if (e.pandaGuidance) {
        const guideText = firmwareGuidanceText(data.firmware_guidance);
        e.pandaGuidance.textContent = guideText;
        e.pandaGuidance.classList.toggle('hidden', !guideText);
      }
      if (e.flashPandaBtn) {
        e.flashPandaBtn.disabled = state.running || !data?.pandas?.length || !state.flashAllowed;
        e.flashPandaBtn.title = state.flashAllowed
          ? ''
          : (state.flashBlockedReason || t('pandaFlashOffroadBody', '当前 onroad，请在 offroad 下刷写。'));
      }
    } catch (err) {
      e.pandaStatusDetail.textContent = String(err);
    }
  }

  async function refresh() {
    try {
      const health = await fetchJson('/api/tsk/health');
      state.pandadProcess = health.pandad_process || 'pandad';
    } catch (_) { /* ignore */ }

    try {
      const status = await fetchJson('/api/tsk/status');
      setKey(status.key);
    } catch (_) { /* ignore */ }

    try {
      const [can, df] = await Promise.all([
        fetchJson('/api/tsk/can-status'),
        fetchJson('/api/tsk/dataflash-status'),
      ]);
      state.canReady = !!can.ready;
      state.dfReady = !!df.ready;
      state.dfPartial = df.status === 'partial';
      state.dfBytes = df.bytes || 0;
      state.dfTotal = df.total || 32768;

      const e = els();
      if (e.canDot) {
        e.canDot.classList.toggle('ready', state.canReady);
        e.canDot.classList.toggle('running', can.status === 'running');
      }
      if (e.canDetail) {
        e.canDetail.textContent = `Sync ${can.sync_count || 0}/50 · Protected ${can.protected_count || 0}/30`;
      }
      if (e.dfDot) {
        e.dfDot.classList.toggle('ready', state.dfReady);
        e.dfDot.classList.toggle('warn', state.dfPartial);
        e.dfDot.classList.toggle('running', df.status === 'running');
      }
      setDfDetail(df);
      syncActionButtons();
    } catch (_) { /* ignore */ }
    await refreshPandaStatus();
  }

  function logLine(text, cls) {
    const e = els();
    if (!e.jobLog) return;
    const line = document.createElement('div');
    line.className = cls ? `tsk-log-line ${cls}` : 'tsk-log-line';
    line.textContent = text;
    e.jobLog.appendChild(line);
    e.jobLog.scrollTop = e.jobLog.scrollHeight;
  }

  function clearLog() {
    const e = els();
    if (e.jobLog) e.jobLog.innerHTML = '';
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function showModal(title, body, buttons, { busy = false } = {}) {
    const e = els();
    if (!e.modal) return;
    if (e.modalTitle) e.modalTitle.textContent = title;
    if (e.modalBody) e.modalBody.textContent = body;
    e.modal.classList.toggle('is-busy', !!busy);
    if (e.modalActions) {
      e.modalActions.innerHTML = '';
      if (busy) {
        const busyEl = document.createElement('div');
        busyEl.className = 'tsk-modal-busy';
        busyEl.textContent = t('pandaFlashRunning', '正在刷写…');
        e.modalActions.appendChild(busyEl);
      } else {
        buttons.forEach((b) => {
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.className = `btn small ${b.kind || 'ghost'}`;
          btn.textContent = b.label;
          if (b.disabled) btn.disabled = true;
          btn.addEventListener('click', b.onClick);
          e.modalActions.appendChild(btn);
        });
      }
    }
    e.modal.hidden = false;
    e.modal.classList.remove('hidden');
  }

  function hideModal() {
    const e = els();
    if (e.modal) {
      e.modal.hidden = true;
      e.modal.classList.add('hidden');
      e.modal.classList.remove('is-busy');
    }
  }

  function notifyToast(msg, type = 'info') {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = msg;
    toast.className = `toast show ${type}`;
    toast.removeAttribute('aria-hidden');
    window.clearTimeout(notifyToast._timer);
    notifyToast._timer = window.setTimeout(() => {
      toast.classList.remove('show');
      toast.textContent = '';
      toast.setAttribute('aria-hidden', 'true');
    }, 3200);
  }

  function formatFlashResults(results) {
    if (!results?.length) return '';
    return results.map((r) => {
      if (r.ok && r.skipped) {
        return `${r.serial}: ${t('pandaFlashSkipped', '固件已是最新')}`;
      }
      if (r.ok) {
        return `${r.serial}: ${t('pandaFlashOk', '刷写完成')}`;
      }
      const err = r.error || t('pandaFlashFailed', '失败');
      const hint = /busy|LIBUSB/i.test(err)
        ? ` (${t('pandaFlashBusyHint', '可先重启 pandad 或 manager 后再试')})`
        : '';
      return `${r.serial}: ${err}${hint}`;
    }).join('\n');
  }

  function setPandaFlashProgress(active, text) {
    const e = els();
    if (!e.pandaStatusDetail) return;
    e.pandaStatusDetail.classList.toggle('is-flashing', !!active);
    if (text) e.pandaStatusDetail.textContent = text;
  }

  async function runCanCollect() {
    if (state.running) return;
    const e = els();
    if (e.jobTitle) e.jobTitle.textContent = '采集 CAN';
    clearLog();
    $('tskJobPanel')?.classList.remove('hidden');
    state.job = 'can';
    setRunning(true);

    let s = null;
    try {
      s = await fetchJson('/api/tsk/can-status');
    } catch (_) { /* */ }

    if (s?.status === 'complete') {
      logLine('采集已完成', 'ok');
      setRunning(false);
      await refresh();
      return;
    }

    if (s?.status !== 'running') {
      logLine('正在启动…');
      logLine('请车辆 READY 模式（混动已启动）', 'dim');
      try {
        const { response, result } = await postJson('/api/tsk/can-collect');
        if (!response.ok && result.status !== 'running') {
          logLine(result.message || '无法启动采集', 'err');
          setRunning(false);
          return;
        }
      } catch (err) {
        logLine(String(err), 'err');
        setRunning(false);
        return;
      }
    }

    let lastSec = -1;
    while (state.job === 'can') {
      await sleep(500);
      try {
        s = await fetchJson('/api/tsk/can-status');
      } catch (_) {
        continue;
      }
      if (s.status === 'running') {
        const sec = Math.round(s.seconds || 0);
        if (sec !== lastSec) {
          lastSec = sec;
          logLine(`${sec}s · sync ${s.sync_count}/50 · protected ${s.protected_count}/30`);
        }
        continue;
      }
      if (s.status === 'cancelled') {
        logLine(s.message || '已取消', 'dim');
        break;
      }
      if (s.status === 'complete') logLine('采集完成', 'ok');
      else logLine(s.message || '采集未成功', 'err');
      break;
    }
    setRunning(false);
    await refresh();
  }

  async function runDataflashDump() {
    if (state.running) return;
    const e = els();
    if (e.jobTitle) e.jobTitle.textContent = '导出 DataFlash';
    clearLog();
    $('tskJobPanel')?.classList.remove('hidden');
    state.job = 'df';
    setRunning(true);

    let s = null;
    try {
      s = await fetchJson('/api/tsk/dataflash-status');
    } catch (_) { /* */ }

    if (s?.ready || s?.status === 'partial') {
      logLine(s.message || '已有可用导出', 'ok');
      setRunning(false);
      await refresh();
      return;
    }

    if (s?.status !== 'running') {
      logLine('正在启动 DataFlash 导出…');
      logLine('请 Not Ready to Drive 模式', 'dim');
      try {
        const { response, result } = await postJson('/api/tsk/dataflash-dump');
        if (!response.ok && result.status !== 'running') {
          logLine(result.message || '无法启动导出', 'err');
          setRunning(false);
          return;
        }
      } catch (err) {
        logLine(String(err), 'err');
        setRunning(false);
        return;
      }
    }

    while (state.job === 'df') {
      await sleep(500);
      try {
        s = await fetchJson('/api/tsk/dataflash-status');
      } catch (_) {
        continue;
      }
      if (s.status === 'running') {
        logLine(`${s.bytes || 0} / ${s.total || 32768} 字节`);
        continue;
      }
      if (s.status === 'cancelled') {
        logLine(s.message || '已取消', 'dim');
        break;
      }
      if (s.status === 'complete') logLine('导出完成', 'ok');
      else if (s.status === 'partial') logLine(s.message || '部分导出', 'warn');
      else logLine(s.message || '导出未成功', 'err');
      break;
    }
    setRunning(false);
    await refresh();
  }

  async function runExtract() {
    if (state.running) return;
    const e = els();
    if (e.jobTitle) e.jobTitle.textContent = 'TSK 提取';
    clearLog();
    $('tskJobPanel')?.classList.remove('hidden');
    state.job = 'extract';
    setRunning(true);
    logLine('正在通过 UDS 提取 SecOC 密钥…', 'dim');
    logLine('请保持 offroad，勿挂挡', 'dim');
    try {
      const { response, result } = await postJson('/api/tsk/extract');
      const msg = result.message || (response.ok ? '完成' : '提取失败');
      msg.split('\n').forEach((line) => {
        if (line.trim()) logLine(line, response.ok ? 'ok' : 'err');
      });
      if (result.key) setKey(result.key);
      if (!response.ok && !result.key) {
        showModal('提取失败', msg, [{ label: '确定', onClick: hideModal }]);
      } else if (result.key) {
        showModal('提取成功', msg, [{ label: '确定', kind: 'primary', onClick: hideModal }]);
      }
    } catch (err) {
      logLine(String(err), 'err');
      showModal('错误', String(err), [{ label: '确定', onClick: hideModal }]);
    } finally {
      state.job = null;
      setRunning(false);
      await refresh();
    }
  }

  async function runManualInstall() {
    if (state.running) return;
    const e = els();
    const raw = (e.manualKeyInput?.value || '').trim();
    if (!raw) {
      showModal('请输入密钥', 'SecOC Key 为 32 位十六进制字符。', [{ label: '确定', onClick: hideModal }]);
      return;
    }
    setRunning(true);
    try {
      const { response, result } = await postJson('/api/tsk/install-key', { key: raw });
      if (response.ok && result.key) {
        setKey(result.key);
        if (e.manualKeyInput) e.manualKeyInput.value = '';
        showModal('安装成功', result.message || '密钥已安装', [
          { label: '确定', kind: 'primary', onClick: hideModal },
        ]);
      } else {
        showModal('安装失败', result.message || '请检查密钥格式', [
          { label: '确定', onClick: hideModal },
        ]);
      }
    } catch (err) {
      showModal('错误', String(err), [{ label: '确定', onClick: hideModal }]);
    } finally {
      setRunning(false);
      await refresh();
    }
  }

  async function runMatch() {
    if (state.running || els().matcherBtn?.disabled) return;
    setRunning(true);
    const e = els();
    if (e.finding) {
      e.finding.hidden = false;
      e.finding.classList.remove('hidden');
    }
    try {
      const { response, result } = await postJson('/api/tsk/match');
      if (result.status === 'found') {
        setKey(result.key);
        showModal('成功', result.message || '密钥已安装', [
          { label: '确定', kind: 'primary', onClick: hideModal },
        ]);
      } else if (!response.ok || result.status === 'error') {
        showModal('错误', result.message || '查找失败', [
          { label: '确定', kind: 'primary', onClick: hideModal },
        ]);
      } else {
        showModal('未找到密钥', result.message || '请重试或联系社区', [
          { label: '确定', onClick: hideModal },
        ]);
      }
    } catch (err) {
      showModal('错误', String(err), [{ label: '确定', onClick: hideModal }]);
    } finally {
      if (e.finding) {
        e.finding.hidden = true;
        e.finding.classList.add('hidden');
      }
      setRunning(false);
      await refresh();
    }
  }

  async function runUninstall() {
    if (state.running || !state.key) return;
    showModal('卸载密钥？', '将删除本机 SecOC 密钥文件', [
      { label: '取消', onClick: hideModal },
      {
        label: '卸载',
        kind: 'danger',
        onClick: async () => {
          hideModal();
          try {
            const { result } = await postJson('/api/tsk/uninstall');
            setKey(result.key);
          } catch (err) {
            showModal('错误', String(err), [{ label: '确定', onClick: hideModal }]);
          }
          await refresh();
        },
      },
    ]);
  }

  async function runClear() {
    if (state.running) return;
    showModal('清除提取缓存？', '删除 CAN 与 DataFlash 缓存，不删除已装密钥', [
      { label: '取消', onClick: hideModal },
      {
        label: '清除',
        kind: 'danger',
        onClick: async () => {
          hideModal();
          try {
            await postJson('/api/tsk/clear-cache');
          } catch (_) { /* */ }
          await refresh();
        },
      },
    ]);
  }

  function startPoll() {
    stopPoll();
    refresh();
    pollTimer = setInterval(refresh, 1500);
  }

  function stopPoll() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    state.job = null;
  }

  async function runDeviceAction(path, title, body, confirmLabel = '确定') {
    showModal(title, body, [
      { label: '取消', onClick: hideModal },
      {
        label: confirmLabel,
        kind: 'danger',
        onClick: async () => {
          hideModal();
          try {
            const { result } = await postJson(path);
            if (result.ok) {
              showModal('完成', result.message || '操作已提交', [
                { label: '确定', kind: 'primary', onClick: hideModal },
              ]);
            } else {
              showModal('错误', result.error || result.message || '操作失败', [
                { label: '确定', kind: 'primary', onClick: hideModal },
              ]);
            }
          } catch (err) {
            showModal('错误', String(err), [{ label: '确定', onClick: hideModal }]);
          }
        },
      },
    ]);
  }

  async function cancelJob() {
    if (!state.running || !state.job || state.job === 'extract') return;
    const job = state.job === 'df' ? 'dataflash' : 'can';
    logLine('正在取消…', 'dim');
    try {
      const { result } = await postJson('/api/tsk/cancel-job', { job });
      logLine(result.message || (result.ok ? '已取消' : '取消失败'), result.ok ? 'dim' : 'err');
    } catch (err) {
      logLine(String(err), 'err');
    }
    state.job = null;
    setRunning(false);
    await refresh();
  }

  async function runFlashPanda() {
    if (state.running) return;
    if (!state.flashAllowed) {
      showModal(
        t('pandaFlashOffroadTitle', '无法刷写'),
        state.flashBlockedReason || t('pandaFlashOffroadBody', '当前处于 onroad，Panda 刷写仅能在 offroad（停车）下进行。'),
        [{ label: t('ok', '确定'), kind: 'primary', onClick: hideModal }],
      );
      return;
    }
    let previewText = t('pandaFlashConfirmBody', '将用当前 openpilot 仓库固件刷写所有已连接 Panda（offroad）。刷机期间 USB 可能被占用。');
    try {
      const status = await fetchJson('/api/panda/status');
      if (status.flash_allowed === false) {
        showModal(
          t('pandaFlashOffroadTitle', '无法刷写'),
          status.flash_blocked_reason || t('pandaFlashOffroadBody', '当前 onroad，请在 offroad 下刷写。'),
          [{ label: t('ok', '确定'), kind: 'primary', onClick: hideModal }],
        );
        return;
      }
      previewText = `${formatPandaStatus(status)}\n\n${previewText}`;
    } catch (_) { /* ignore */ }
    showModal(
      t('pandaFlashConfirmTitle', '刷写 Panda 固件？'),
      previewText,
      [
        { label: t('cancel', '取消'), onClick: hideModal },
        {
          label: t('pandaFlashBtn', '刷写 Panda 固件'),
          kind: 'danger',
          onClick: async () => {
            const e = els();
            showModal(
              t('pandaFlashRunning', '正在刷写 Panda 固件'),
              t('pandaFlashRunningBody', '请稍候，刷机期间 USB 可能被占用。请勿关闭 SecOC 面板。'),
              [],
              { busy: true },
            );
            if (e.jobTitle) e.jobTitle.textContent = t('pandaFlashRunning', '刷写 Panda');
            clearLog();
            const jobPanel = $('tskJobPanel');
            jobPanel?.classList.remove('hidden');
            jobPanel?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            state.job = 'panda-flash';
            setRunning(true);
            setPandaFlashProgress(true, t('pandaFlashStarting', '正在刷写 Panda 固件…'));
            logLine(t('pandaFlashStarting', '正在刷写…'), 'dim');
            let flashOk = false;
            let resultBody = '';
            try {
              const { response, result } = await postJson(
                '/api/panda/flash',
                { confirm: true, all: true },
                { timeoutMs: 5 * 60 * 1000 },
              );
              if (response.status === 403 || result.onroad) {
                resultBody = result.error || t('pandaFlashOffroadBody', '当前 onroad，请在 offroad 下刷写。');
                logLine(resultBody, 'err');
                showModal(
                  t('pandaFlashOffroadTitle', '无法刷写'),
                  resultBody,
                  [{ label: t('ok', '确定'), kind: 'primary', onClick: hideModal }],
                );
                notifyToast(resultBody, 'error');
                return;
              }
              const results = result.results || [];
              if (results.length) {
                results.forEach((r) => {
                  const line = r.ok
                    ? `${r.serial}: ${r.skipped ? t('pandaFlashSkipped', '已是最新') : t('pandaFlashOk', '完成')}`
                    : `${r.serial}: ${r.error || t('pandaFlashFailed', '失败')}`;
                  logLine(line, r.ok ? 'ok' : 'err');
                  if (!r.ok && r.log) {
                    r.log.split('\n').slice(-4).forEach((ln) => {
                      if (ln.trim()) logLine(ln.trim(), 'dim');
                    });
                  }
                });
                resultBody = formatFlashResults(results);
                flashOk = result.ok && results.every((r) => r.ok);
              } else if (result.needs_confirmation) {
                resultBody = result.hint || 'needs confirmation';
                logLine(resultBody, 'warn');
                flashOk = false;
              } else if (!response.ok || !result.ok) {
                resultBody = result.error || result.message || t('pandaFlashFailed', '失败');
                logLine(resultBody, 'err');
                flashOk = false;
              } else if (result.skipped) {
                resultBody = t('pandaFlashSkipped', '固件已是最新，无需刷写');
                logLine(resultBody, 'ok');
                flashOk = true;
              } else {
                resultBody = t('pandaFlashOk', '刷写完成');
                logLine(resultBody, 'ok');
                flashOk = true;
              }
              if (flashOk) {
                const recovery = result.pandad_recovery;
                let doneBody = resultBody || t('pandaFlashOk', '刷写完成');
                if (recovery?.message) {
                  logLine(recovery.message, recovery.ok ? 'ok' : 'warn');
                  doneBody += `\n\n${recovery.message}`;
                }
                if (recovery && recovery.ok === false) {
                  doneBody += `\n\n${t('pandaFlashPandadHint', '若 openpilot 侧栏仍显示 Panda 否，请点「重启 manager」。')}`;
                }
                showModal(
                  t('pandaFlashDoneTitle', '刷写完成'),
                  doneBody,
                  [{ label: t('ok', '确定'), kind: 'primary', onClick: hideModal }],
                );
                notifyToast(t('pandaFlashOk', '刷写完成'), recovery?.ok === false ? 'warning' : 'success');
              } else {
                const busyHint = /busy|LIBUSB/i.test(resultBody)
                  ? `\n\n${t('pandaFlashBusyHint', 'USB 被占用时可先点「重启 pandad」或「重启 manager」后再刷写。')}`
                  : '';
                showModal(
                  t('pandaFlashFailedTitle', '刷写失败'),
                  `${resultBody || t('pandaFlashFailed', '失败')}${busyHint}`,
                  [{ label: t('ok', '确定'), kind: 'primary', onClick: hideModal }],
                );
                notifyToast(t('pandaFlashFailed', '刷写失败'), 'error');
              }
            } catch (err) {
              resultBody = String(err);
              logLine(resultBody, 'err');
              showModal(t('pandaFlashFailedTitle', '刷写失败'), resultBody, [
                { label: t('ok', '确定'), onClick: hideModal },
              ]);
              notifyToast(t('pandaFlashFailed', '刷写失败'), 'error');
            } finally {
              state.job = null;
              setRunning(false);
              setPandaFlashProgress(false);
              await refresh();
            }
          },
        },
      ],
    );
  }

  function bind() {
    els().canBtn?.addEventListener('click', () => runCanCollect());
    els().dfBtn?.addEventListener('click', () => runDataflashDump());
    els().matcherBtn?.addEventListener('click', () => runMatch());
    els().extractBtn?.addEventListener('click', () => runExtract());
    els().manualInstallBtn?.addEventListener('click', () => runManualInstall());
    els().uninstallBtn?.addEventListener('click', () => runUninstall());
    els().cleanerBtn?.addEventListener('click', () => runClear());
    els().cancelJobBtn?.addEventListener('click', () => cancelJob());
    els().rebootDeviceBtn?.addEventListener('click', () => {
      runDeviceAction(
        '/api/tsk/reboot-device',
        '重启设备？',
        '整机将在数秒后重启，连接会断开。请确认车辆已 offroad。',
        '重启',
      );
    });
    els().restartManagerBtn?.addEventListener('click', () => {
      runDeviceAction(
        '/api/tsk/restart-manager',
        '重启 manager？',
        '将停止并重新启动 openpilot manager，屏幕可能短暂无响应。',
        '重启 manager',
      );
    });
    els().restartPandadBtn?.addEventListener('click', () => {
      const proc = state.pandadProcess || 'pandad';
      runDeviceAction(
        '/api/tsk/restart-pandad',
        `重启 ${proc}？`,
        `将终止本机 ${proc} 进程（统一为 pandad）；若 manager 在运行通常会重新拉起。`,
        `重启 ${proc}`,
      );
    });
    els().flashPandaBtn?.addEventListener('click', () => runFlashPanda());
    $('tskModalClose')?.addEventListener('click', hideModal);
  }

  function applyTranslations(tFn) {
    if (typeof tFn === 'function') translate = tFn;
    setKey(state.key);
    syncActionButtons();
  }

  return { bind, startPoll, stopPoll, refresh, applyTranslations };
})();
