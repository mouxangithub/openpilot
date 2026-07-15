/**
 * Toyota SecOC / TSK — embedded in op 助手 settings sidebar.
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
    if (e.uninstallBtn) {
      e.uninstallBtn.disabled = !state.key;
      e.uninstallBtn.classList.toggle('danger', !!state.key);
    }
  }

  function setRunning(running) {
    state.running = running;
    const e = els();
    const all = [e.canBtn, e.dfBtn, e.matcherBtn, e.cleanerBtn, e.uninstallBtn, e.manualInstallBtn, e.extractBtn];
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

  async function fetchJson(url) {
    const res = await fetch(url, { cache: 'no-store' });
    return res.json();
  }

  async function postJson(url, payload = {}) {
    const res = await fetch(url, {
      method: 'POST',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const result = await res.json();
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

  function showModal(title, body, buttons) {
    const e = els();
    if (!e.modal) return;
    if (e.modalTitle) e.modalTitle.textContent = title;
    if (e.modalBody) e.modalBody.textContent = body;
    if (e.modalActions) {
      e.modalActions.innerHTML = '';
      buttons.forEach((b) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `btn small ${b.kind || 'ghost'}`;
        btn.textContent = b.label;
        btn.addEventListener('click', b.onClick);
        e.modalActions.appendChild(btn);
      });
    }
    e.modal.hidden = false;
    e.modal.classList.remove('hidden');
  }

  function hideModal() {
    const e = els();
    if (e.modal) {
      e.modal.hidden = true;
      e.modal.classList.add('hidden');
    }
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
        `将终止本机 ${proc} 进程（C3 为 pandad_tici，C3X/C4 为 pandad）；若 manager 在运行通常会重新拉起。`,
        `重启 ${proc}`,
      );
    });
    $('tskModalClose')?.addEventListener('click', hideModal);
  }

  function applyTranslations(tFn) {
    if (typeof tFn === 'function') translate = tFn;
    setKey(state.key);
    syncActionButtons();
  }

  return { bind, startPoll, stopPoll, refresh, applyTranslations };
})();
