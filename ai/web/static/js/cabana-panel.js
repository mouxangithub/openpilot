/**
 * Embedded Cabana panel for op助手 — simplified CAN viewer with AI signal explain.
 */
const CabanaPanel = (() => {
  let root = null;
  let t = (k, fb) => fb || k;
  let onSendToChat = null;
  let getLang = () => 'zh';
  let tf = (key, vars, fallback) => t(key, fallback);

  let signals = [];
  const signalsByAddress = new Map();
  let ws = null;
  const latestFrames = new Map();
  let dbcName = '';
  let dbcNames = [];
  let dbcCatalog = {};
  let dbcPickerOpen = false;
  let dbcBlurTimer = null;
  const GENERIC_LABELS = new Set(['车身', '其他']);
  const EXPLAIN_STORE_KEY = 'cabana-explain-labels-v3';
  const explainCache = new Map();
  let serverLabelStore = {};
  let maxRows = 300;
  let bulkExplainTimer = null;
  let bulkExplainToken = 0;
  const BULK_EXPLAIN_MAX = 500;
  const EXPLAIN_CHUNK = 25;
  const VIRTUAL_ROW_H = 34;
  const FILTER_CHIP_IDS = ['all', 'labeled', 'unlabeled', '巡航', '转向', '刹车', '油门', '车速', '雷达'];
  const TAG_CLASS_MAP = {
    巡航: 'cab-tag-cruise',
    转向: 'cab-tag-steer',
    刹车: 'cab-tag-brake',
    油门: 'cab-tag-throttle',
    车速: 'cab-tag-speed',
    雷达: 'cab-tag-radar',
    认证: 'cab-tag-auth',
  };
  const tableRows = new Map();
  let sortCol = 'name';
  let sortAsc = true;
  let filterChip = 'all';
  let autoLabelEnabled = true;
  let aiAnalyzeRunning = false;
  let virtualRenderScheduled = false;
  let bulkExplainRunning = false;

  const SIGNAL_LABEL_RULES = [
    [/brake|brk|brakepressed|brakelight/i, '刹车'],
    [/gas.?pedal|gas_pedal|throttle|pedal/i, '油门'],
    [/accel(?!er)|throttle/i, '油门'],
    [/acc_?control|adaptive|cruise/i, '巡航'],
    [/steer|steering|steer_|angle_sensor|_lka|lkas|eps/i, '转向'],
    [/wheel.*speed|veh.*spd|vehicle.?speed|wheel_speed/i, '车速'],
    [/gear|shifter|trans/i, '档位'],
    [/turn|blink|indicator/i, '转向灯'],
    [/wiper/i, '雨刷'],
    [/door|hood|trunk/i, '车门'],
    [/seatbelt|buckle/i, '安全带'],
    [/esp|abs|stability|yaw/i, '稳定'],
    [/rpm|engine.?speed/i, '转速'],
    [/battery|hv|12v|volt/i, '电源'],
    [/temp|coolant/i, '温度'],
    [/fuel/i, '油量'],
    [/odometer|mileage/i, '里程'],
    [/park|epb|handbrake/i, '驻车'],
    [/horn/i, '喇叭'],
    [/light|headlamp|beam/i, '灯光'],
    [/radar|lead|dist|pre_collision|fcw/i, '雷达'],
    [/pcm|powertrain|engine/i, '动力'],
    [/hybrid|hev/i, '混动'],
    [/torque/i, '扭矩'],
    [/secoc|auth|mac_sync/i, '认证'],
    [/button|switch|btn|cancel/i, '按键'],
    [/display|hud|cluster/i, '仪表'],
    [/airbag|srs/i, '气囊'],
  ];
  let offlineWs = null;
  let replayRoute = '';
  let replayMeta = null;
  let replayPaused = true;
  let replaySpeed = 1;
  let replayDuration = 0;
  let replayProgress = 0;
  let replayStartMono = 0;
  let panelMode = 'live';

  function $(sel) {
    return (root?.querySelector(sel)) || document.querySelector(sel);
  }

  async function api(method, path, body, { signal, timeoutMs } = {}) {
    const opts = { method, headers: {} };
    if (body) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    let timer;
    let ctrl;
    if (timeoutMs && !signal) {
      ctrl = new AbortController();
      opts.signal = ctrl.signal;
      timer = setTimeout(() => ctrl.abort(), timeoutMs);
    } else if (signal) {
      opts.signal = signal;
    }
    try {
      const res = await fetch(path, opts);
      return await res.json().catch(() => ({ ok: false, error: 'bad response' }));
    } catch (e) {
      if (e?.name === 'AbortError') return { ok: false, error: 'request timeout' };
      return { ok: false, error: String(e?.message || e) };
    } finally {
      if (timer) clearTimeout(timer);
    }
  }

  function wsUrl(path) {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${location.host}${path}`;
  }

  function buildSignalIndex() {
    signalsByAddress.clear();
    for (const sig of signals) {
      const addr = Number(sig.address);
      if (!Number.isFinite(addr)) continue;
      if (!signalsByAddress.has(addr)) signalsByAddress.set(addr, []);
      signalsByAddress.get(addr).push(sig);
    }
  }

  function frameKey(frame) {
    const bus = Number(frame.bus) || 0;
    const addr = Number(frame.address);
    return `${bus}:${addr}`;
  }

  function rowDomId(key) {
    return `cab-row-${String(key).replace(/:/g, '-')}`;
  }

  function addrHex(addr) {
    return `0x${Number(addr).toString(16).toUpperCase().padStart(3, '0')}`;
  }

  function hexBucketHint(addr) {
    const n = Number(addr) || 0;
    const prefix = (n >> 8) & 0xFF;
    return `${prefix.toString(16).toUpperCase()}xx`;
  }

  function truncateHex(s, max = 18) {
    const t = String(s || '');
    if (t.length <= max) return t;
    return `${t.slice(0, 8)}…${t.slice(-6)}`;
  }

  function tagClassForLabel(label) {
    return TAG_CLASS_MAP[label] || 'cab-tag-default';
  }

  function labelCellHtml(label, { pending = false, hexHint = '' } = {}) {
    if (label) {
      const cls = tagClassForLabel(label);
      return `<span class="cab-explain-text ${cls}">${label}</span>`;
    }
    if (pending) {
      const hint = hexHint ? `<span class="cab-explain-hex">${hexHint}</span> ` : '';
      return `${hint}<span class="cab-explain-pending">${t('cabanaExplainPending', '待解释…')}</span>`;
    }
    return '—';
  }

  function buildRowRecord(frame, opts = {}) {
    const key = frameKey(frame);
    const sigs = signalsByAddress.get(Number(frame.address));
    const msgName = sigs?.[0]?.message;
    const hex = addrHex(frame.address);
    const nameCol = msgName ? `${msgName} · ${hex}` : hex;
    let valueText = '';
    if (opts.replay || opts.live) {
      valueText = frame.data ? String(frame.data) : '';
    } else {
      const decoded = decodeFrame(frame);
      valueText = decoded.text || frame.data || '';
    }
    const relTime = opts.replay ? formatReplayRowTime(frame) : frame.time.toFixed(2);
    const item = { id: key, message: msgName || hex, signal: sigs?.[0]?.signal || '' };
    const cached = explainCache.get(key);
    const label = (cached && !GENERIC_LABELS.has(cached))
      ? cached
      : (resolveLabelForItem(item) || '');
    const prev = tableRows.get(key);
    return {
      key,
      frame,
      relTime,
      nameCol,
      searchHay: `${nameCol} ${valueText} ${hex}`.toLowerCase(),
      valueText,
      label: label || prev?.label || '',
      pending: !(label || prev?.label),
      hexHint: !msgName ? hexBucketHint(frame.address) : '',
      live: !!opts.live,
      replay: !!opts.replay,
    };
  }

  function upsertTableRow(frame, opts = {}) {
    const key = frameKey(frame);
    latestFrames.set(key, frame);
    const prev = tableRows.get(key);
    const rec = buildRowRecord(frame, opts);
    if (prev?.label && !rec.label) {
      rec.label = prev.label;
      rec.pending = false;
    }
    tableRows.set(key, rec);
    if (rec.label) explainCache.set(key, rec.label);
    scheduleVirtualRender();
    updateLabelProgress();
    if (rec.pending && autoLabelEnabled) scheduleBulkExplainAll();
  }

  function getFilteredSortedKeys() {
    const q = (els.filter?.value || '').toLowerCase().trim();
    let keys = Array.from(tableRows.keys());
    keys = keys.filter((k) => {
      const row = tableRows.get(k);
      if (!row) return false;
      if (q && !row.searchHay.includes(q)) return false;
      if (filterChip === 'labeled') return !!row.label;
      if (filterChip === 'unlabeled') return !row.label;
      if (filterChip !== 'all' && row.label !== filterChip) return false;
      return true;
    });
    const col = sortCol;
    keys.sort((a, b) => {
      const ra = tableRows.get(a);
      const rb = tableRows.get(b);
      let va;
      let vb;
      if (col === 'time') {
        va = Number(ra?.frame?.time) || 0;
        vb = Number(rb?.frame?.time) || 0;
      } else if (col === 'label') {
        va = ra?.label || '～';
        vb = rb?.label || '～';
      } else {
        va = ra?.nameCol || '';
        vb = rb?.nameCol || '';
      }
      if (va < vb) return sortAsc ? -1 : 1;
      if (va > vb) return sortAsc ? 1 : -1;
      return a.localeCompare(b);
    });
    return keys;
  }

  function scheduleVirtualRender() {
    if (virtualRenderScheduled) return;
    virtualRenderScheduled = true;
    requestAnimationFrame(() => {
      virtualRenderScheduled = false;
      renderVirtualTable();
    });
  }

  function renderVirtualTable() {
    if (!els.tbody || !els.tableWrap) return;
    const keys = getFilteredSortedKeys();
    const scrollTop = els.tableWrap.scrollTop || 0;
    const viewH = els.tableWrap.clientHeight || 320;
    const start = Math.max(0, Math.floor(scrollTop / VIRTUAL_ROW_H) - 3);
    const count = Math.ceil(viewH / VIRTUAL_ROW_H) + 8;
    const end = Math.min(keys.length, start + count);
    const topH = start * VIRTUAL_ROW_H;
    const bottomH = Math.max(0, (keys.length - end) * VIRTUAL_ROW_H);

    const topSpacer = els.tbody.querySelector('.cab-virtual-spacer-top');
    const bottomSpacer = els.tbody.querySelector('.cab-virtual-spacer-bottom');
    if (topSpacer) {
      const td = topSpacer.querySelector('td');
      if (td) td.style.height = `${topH}px`;
    }
    if (bottomSpacer) {
      const td = bottomSpacer.querySelector('td');
      if (td) td.style.height = `${bottomH}px`;
    }

    const existing = new Map();
    for (const tr of els.tbody.querySelectorAll('tr.cab-data-row')) {
      existing.set(tr.dataset.key, tr);
    }
    const frag = document.createDocumentFragment();
    for (let i = start; i < end; i++) {
      const key = keys[i];
      const row = tableRows.get(key);
      if (!row) continue;
      let tr = existing.get(key);
      if (tr) existing.delete(key);
      else {
        tr = document.createElement('tr');
        tr.className = 'cab-data-row';
        tr.dataset.key = key;
        tr.id = rowDomId(key);
        tr.innerHTML = '<td class="cab-col-time"></td><td class="cab-col-name"></td><td class="cab-col-value"></td><td class="cab-col-label"></td>';
      }
      tr.children[0].textContent = row.replay ? `+${row.relTime}s` : row.relTime;
      tr.children[1].textContent = row.nameCol;
      tr.children[1].title = row.nameCol;
      tr.children[2].textContent = truncateHex(row.valueText);
      tr.children[2].title = row.valueText || '';
      tr.children[3].innerHTML = labelCellHtml(row.label, { pending: row.pending, hexHint: row.hexHint });
      frag.appendChild(tr);
    }
    for (const [, tr] of existing) tr.remove();
    if (bottomSpacer) els.tbody.insertBefore(frag, bottomSpacer);
    else els.tbody.appendChild(frag);
    updateReplayStats();
  }

  function updateLabelProgress() {
    if (!els.labelProgress) return;
    const total = tableRows.size;
    if (!total) {
      els.labelProgress.hidden = true;
      return;
    }
    let labeled = 0;
    for (const row of tableRows.values()) {
      if (row.label) labeled += 1;
    }
    labeledCount = labeled;
    els.labelProgress.hidden = false;
    els.labelProgress.textContent = tf('cabanaLabelProgress', { labeled, total });
  }

  function updateReplayStats() {
    if (!els.replayStats) return;
    if (panelMode !== 'replay') {
      els.replayStats.textContent = '';
      return;
    }
    els.replayStats.textContent = tf('cabanaReplayStats', {
      rows: tableRows.size,
      labeled: labeledCount,
    });
  }

  function clearTableRows() {
    tableRows.clear();
    if (els.tbody) {
      for (const tr of els.tbody.querySelectorAll('tr.cab-data-row')) tr.remove();
    }
    scheduleVirtualRender();
    updateLabelProgress();
  }

  function renderFilterChips() {
    if (!els.filterChips) return;
    els.filterChips.innerHTML = '';
    const labels = {
      all: t('cabanaChipAll', '全部'),
      labeled: t('cabanaChipLabeled', '已标注'),
      unlabeled: t('cabanaChipUnlabeled', '未标注'),
    };
    for (const id of FILTER_CHIP_IDS) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = `cab-filter-chip${filterChip === id ? ' active' : ''}`;
      btn.textContent = labels[id] || id;
      btn.addEventListener('click', () => {
        filterChip = id;
        renderFilterChips();
        scheduleVirtualRender();
      });
      els.filterChips.appendChild(btn);
    }
  }

  function normalizeFrame(raw) {
    if (!raw || raw.address == null) return null;
    return {
      ...raw,
      bus: Number(raw.bus) || 0,
      address: Number(raw.address),
      data: raw.data != null ? String(raw.data) : '',
      time: Number(raw.time) || 0,
    };
  }

  function hexToBytes(hex) {
    const clean = String(hex).replace(/\s/g, '');
    if (clean.length < 2) return null;
    const parts = clean.match(/.{1,2}/g);
    if (!parts) return null;
    return new Uint8Array(parts.map((b) => parseInt(b, 16)));
  }

  function decodeSignal(data, sig) {
    try {
      const bytes = new Uint8Array(8);
      bytes.set(data.slice(0, 8));
      let val = 0n;
      for (let i = 0; i < 8; i++) val |= BigInt(bytes[i]) << BigInt(i * 8);
      let raw = 0n;
      const size = BigInt(sig.size);
      if (sig.little_endian) {
        raw = (val >> BigInt(sig.start_bit)) & ((1n << size) - 1n);
      } else {
        const beBits = [];
        for (let byte = 0; byte < 8; byte++) {
          for (let bit = 7; bit >= 0; bit++) beBits.push(byte * 8 + bit);
        }
        const idx = beBits.indexOf(sig.start_bit);
        if (idx < 0 || idx + sig.size > beBits.length) return null;
        for (let i = 0; i < sig.size; i++) {
          const seqBit = BigInt(beBits[idx + i]);
          raw |= ((val >> seqBit) & 1n) << BigInt(sig.size - 1 - i);
        }
      }
      if (sig.signed && raw & (1n << (size - 1n))) raw -= 1n << size;
      return Number(raw) * sig.factor + sig.offset;
    } catch {
      return null;
    }
  }

  function decodeFrameLite(frame) {
    const sigs = signalsByAddress.get(Number(frame.address));
    if (!sigs?.length || !frame.data) return { text: frame.data || '', primary: null };
    const data = hexToBytes(frame.data);
    if (!data) return { text: frame.data || '', primary: null };
    const sig = sigs[0];
    const val = decodeSignal(data, sig);
    if (val === null) return { text: frame.data || '', primary: null };
    let s = `${sig.signal}=${val.toFixed(2)}`;
    if (sig.unit) s += sig.unit;
    return {
      text: s,
      primary: { message: sig.message, signal: sig.signal, value: s, decoded: s },
    };
  }

  function decodeFrame(frame) {
    const sigs = signalsByAddress.get(Number(frame.address));
    if (!sigs || !frame.data) return { text: '', primary: null };
    const data = hexToBytes(frame.data);
    if (!data) return { text: '', primary: null };
    const parts = [];
    let primary = null;
    for (const sig of sigs) {
      const val = decodeSignal(data, sig);
      if (val === null) continue;
      let s = `${sig.signal}=${val.toFixed(2)}`;
      if (sig.unit) s += sig.unit;
      parts.push(s);
      if (!primary) primary = { message: sig.message, signal: sig.signal, value: s, decoded: parts.join(', ') };
    }
    return { text: parts.join(' · '), primary };
  }

  let replayLoading = false;
  let replayIndexReady = false;
  let replayPendingByKey = new Map();
  let replayConnecting = false;
  let replayPlayPending = false;
  const replayRowCache = new Map();
  const replayDirtyKeys = new Set();
  let replayUiFlushScheduled = false;
  let lastReplayUiPaintAt = 0;
  let lastAiButtonsAt = 0;
  const REPLAY_UI_MIN_INTERVAL_MS = 200;
  const REPLAY_MAX_FRAMES_PER_MSG = 64;
  const REPLAY_WS_MAX_MSGS_PER_FLUSH = 2;
  const REPLAY_MAX_DOM_ROWS = 220;
  const REPLAY_MAX_KEYS_PER_FLUSH = 24;
  let replayWsBuffer = [];
  let replayWsFlushTimer = null;
  let livePendingFrames = [];
  let liveFlushScheduled = false;
  let lastProgressPaintAt = 0;
  let liveConnectedAt = 0;
  let liveFrameBatches = 0;
  let lastAiResult = '';

  function setReplayLoading(on, text) {
    replayLoading = !!on;
    if (els.replayLoading) {
      if (on) els.replayLoading.removeAttribute('hidden');
      else els.replayLoading.setAttribute('hidden', '');
    }
    if (els.replayLoadingText && text) {
      els.replayLoadingText.textContent = text;
    }
    const lockControls = on && !replayIndexReady;
    if (els.replayPauseBtn) els.replayPauseBtn.disabled = lockControls;
    if (els.routeSelect) els.routeSelect.disabled = lockControls;
    if (els.progress) els.progress.disabled = lockControls;
    if (on && !replayIndexReady && els.replayPlayBtn) {
      els.replayPlayBtn.textContent = t('cabanaReplayLoadingShort', '索引中…');
    } else if (els.replayPlayBtn) {
      els.replayPlayBtn.textContent = t('cabanaPlayShort', '播放');
    }
  }

  function formatLoadingText(msg) {
    if (msg.phase === 'start') {
      return t('cabanaReplayLoadingStart', '正在打开日志…');
    }
    if (msg.phase === 'cache_hit') {
      const n = msg.can_frames != null ? msg.can_frames.toLocaleString() : '—';
      return `${t('cabanaReplayLoadingCache', '命中缓存')} · ${tf('cabanaCanFrames', { n })}`;
    }
    if (msg.phase === 'fast_qlog') {
      return t('cabanaReplayLoadingFastQlog', '正在读取 qlog（快速模式，不读视频）…');
    }
    if (msg.phase === 'fast_rlog') {
      return t('cabanaReplayLoadingFastRlog', '直接读取 rlog（跳过 qlog）…');
    }
    if (msg.phase === 'parallel') {
      return t('cabanaReplayLoadingParallel', '并行读取多段日志…') + (msg.files ? ` ×${msg.files}` : '');
    }
    if (msg.phase === 'fallback_rlog') {
      return t('cabanaReplayLoadingRlog', 'qlog CAN 过少，正在读取 rlog…');
    }
    if (msg.phase === 'ready') {
      const n = msg.can_frames != null ? msg.can_frames.toLocaleString() : '—';
      return `${t('cabanaReplayLoadingReady', '索引完成')} · ${tf('cabanaCanFrames', { n })}`;
    }
    if (msg.phase === 'scanning' || msg.heartbeat) {
      const file = msg.file ? ` · ${msg.file}` : '';
      const msgs = msg.msgs != null ? msg.msgs.toLocaleString() : '—';
      const frames = msg.can_frames != null ? msg.can_frames.toLocaleString() : '0';
      return `${t('cabanaReplayLoadingScan', '正在索引日志')}${file} · ${t('cabanaReplayLoadingMsgs', '已读')} ${msgs} · ${tf('cabanaCanFrames', { n: frames })}`;
    }
    return t('cabanaReplayLoadingStart', '正在打开日志…');
  }

  function clearReplayLoading() {
    setReplayLoading(false);
  }

  function resetReplayQueue() {
    replayPendingByKey.clear();
    replayRowCache.clear();
    replayDirtyKeys.clear();
  }

  function setCellText(row, idx, value) {
    const cell = row.children[idx];
    const next = value == null ? '' : String(value);
    if (cell && cell.textContent !== next) cell.textContent = next;
  }

  function getReplayRow(key) {
    let row = replayRowCache.get(key);
    if (row && row.isConnected) return row;
    row = document.getElementById(rowDomId(key));
    if (row) replayRowCache.set(key, row);
    return row || null;
  }

  function scheduleReplayUiFlush() {
    if (replayUiFlushScheduled) return;
    replayUiFlushScheduled = true;
    requestAnimationFrame(flushReplayUi);
  }

  function flushReplayUi() {
    replayUiFlushScheduled = false;
    if (!els.tbody || !replayPendingByKey.size) return;
    const now = performance.now();
    if (now - lastReplayUiPaintAt < REPLAY_UI_MIN_INTERVAL_MS) {
      scheduleReplayUiFlush();
      return;
    }
    lastReplayUiPaintAt = now;

    const keys = Array.from(replayDirtyKeys);
    replayDirtyKeys.clear();
    const slice = keys.length > REPLAY_MAX_KEYS_PER_FLUSH ? keys.slice(0, REPLAY_MAX_KEYS_PER_FLUSH) : keys;
    if (keys.length > REPLAY_MAX_KEYS_PER_FLUSH) {
      for (const key of keys.slice(REPLAY_MAX_KEYS_PER_FLUSH)) replayDirtyKeys.add(key);
      scheduleReplayUiFlush();
    }
    if (!slice.length) return;

    for (const key of slice) {
      const frame = replayPendingByKey.get(key);
      if (!frame) continue;
      try {
        upsertTableRow(frame, { replay: true });
      } catch (e) {
        console.error('cabana replay row', e, frame);
      }
    }
    scheduleAiButtonsUpdate();
    if (autoLabelEnabled) scheduleBulkExplainAll();
  }

  function scheduleAiButtonsUpdate() {
    const now = performance.now();
    if (now - lastAiButtonsAt < 400) return;
    lastAiButtonsAt = now;
    updateAiButtons();
  }

  function flushReplayWsBuffer() {
    replayWsFlushTimer = null;
    if (!replayWsBuffer.length) return;
    let processed = 0;
    while (replayWsBuffer.length && processed < REPLAY_WS_MAX_MSGS_PER_FLUSH) {
      const raw = replayWsBuffer.shift();
      processed += 1;
      try {
        handleOfflineWsMessage(JSON.parse(raw));
      } catch (e) {
        console.error('cabana replay ws', e);
      }
    }
    if (replayWsBuffer.length) {
      replayWsFlushTimer = window.setTimeout(flushReplayWsBuffer, 48);
    }
  }

  function queueReplayWsMessage(raw) {
    replayWsBuffer.push(raw);
    if (replayWsFlushTimer != null) return;
    replayWsFlushTimer = window.setTimeout(flushReplayWsBuffer, 120);
  }

  function applyReplayCanBatch(frames) {
    if (!Array.isArray(frames) || !frames.length) return;
    const slice = frames.length > REPLAY_MAX_FRAMES_PER_MSG
      ? frames.slice(0, REPLAY_MAX_FRAMES_PER_MSG)
      : frames;
    for (const raw of slice) {
      const frame = normalizeFrame(raw);
      if (!frame) continue;
      const key = frameKey(frame);
      replayPendingByKey.set(key, frame);
      latestFrames.set(key, frame);
      replayDirtyKeys.add(key);
    }
    while (replayPendingByKey.size > 1200) {
      const oldest = replayPendingByKey.keys().next().value;
      replayPendingByKey.delete(oldest);
      replayRowCache.delete(oldest);
    }
    scheduleReplayUiFlush();
  }

  function enqueueCanFrames(frames, { replay = false } = {}) {
    if (!frames?.length) return;
    if (replay) {
      applyReplayCanBatch(frames);
      while (replayPendingByKey.size > 2500) {
        const oldest = replayPendingByKey.keys().next().value;
        replayPendingByKey.delete(oldest);
      }
      return;
    }
    livePendingFrames.push(...frames);
    if (!liveFlushScheduled) {
      liveFlushScheduled = true;
      requestAnimationFrame(flushLiveFrames);
    }
  }

  function enqueueReplayFrames(frames) {
    enqueueCanFrames(frames, { replay: true });
  }

  function flushLiveFrames() {
    liveFlushScheduled = false;
    if (!livePendingFrames.length) return;
    liveFrameBatches += 1;
    const batch = livePendingFrames;
    livePendingFrames = [];
    const latest = new Map();
    for (const frame of batch) {
      latest.set(`${frame.bus}:${frame.address}`, frame);
    }
    for (const frame of latest.values()) {
      upsertTableRow(frame, { live: true });
    }
    updateAiButtons();
  }

  function updateReplayProgress(progress) {
    if (typeof progress !== 'number' || Number.isNaN(progress)) return;
    replayProgress = Math.max(0, progress);
    if (progress > replayDuration) replayDuration = progress;
    const now = performance.now();
    if (now - lastProgressPaintAt < 80) return;
    lastProgressPaintAt = now;
    updateProgressUI();
  }

  function formatReplayTime(sec) {
    const s = Math.max(0, Math.floor(sec || 0));
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${m}:${String(r).padStart(2, '0')}`;
  }

  function updateProgressUI() {
    if (!els.progress || !els.progressLabel) return;
    const ratio = replayDuration > 0 ? replayProgress / replayDuration : 0;
    els.progress.value = String(Math.round(Math.min(1, Math.max(0, ratio)) * 1000));
    const logLabel = t('cabanaLogTime', '日志');
    els.progressLabel.textContent = `${logLabel} ${formatReplayTime(replayProgress)} / ${formatReplayTime(replayDuration)}`;
  }

  function explainPersistKeys(item) {
    const keys = [];
    if (item?.id) keys.push(String(item.id));
    const msg = (item?.message || '').trim();
    if (msg) {
      keys.push(msg.toUpperCase());
      keys.push(msg);
    }
    return keys;
  }

  function readLocalLabelStore() {
    try {
      const raw = localStorage.getItem(EXPLAIN_STORE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  }

  function writeLocalLabelStore(store) {
    try {
      localStorage.setItem(EXPLAIN_STORE_KEY, JSON.stringify(store));
    } catch { /* ignore quota */ }
  }

  function scrubLabelStore(store) {
    if (!store || typeof store !== 'object') return {};
    const out = { ...store };
    for (const k of Object.keys(out)) {
      if (GENERIC_LABELS.has(out[k])) delete out[k];
    }
    return out;
  }

  function lookupStoredLabel(item) {
    if (!item) return null;
    const dbc = dbcName || '_default';
    for (const key of explainPersistKeys(item)) {
      const fromServer = serverLabelStore[key];
      if (fromServer && !GENERIC_LABELS.has(fromServer)) return fromServer;
      const localBucket = readLocalLabelStore()[dbc];
      const fromLocal = localBucket?.[key];
      if (fromLocal && !GENERIC_LABELS.has(fromLocal)) return fromLocal;
    }
    return null;
  }

  function persistExplainLabel(item, label) {
    if (!item || !label || GENERIC_LABELS.has(label)) return;
    const dbc = dbcName || '_default';
    const store = readLocalLabelStore();
    const bucket = store[dbc] || {};
    for (const key of explainPersistKeys(item)) {
      bucket[key] = label;
      serverLabelStore[key] = label;
    }
    store[dbc] = bucket;
    writeLocalLabelStore(store);
  }

  async function preloadServerLabelCache() {
    if (!dbcName) return;
    try {
      const data = await api('GET', `/api/cabana/explain_cache?dbc=${encodeURIComponent(dbcName)}`);
      if (data.ok && data.labels) {
        serverLabelStore = scrubLabelStore({ ...serverLabelStore, ...data.labels });
      }
    } catch { /* offline */ }
  }

  function resolveLabelForItem(item) {
    if (!item) return null;
    return guessLabelLocal(item.message, item.signal)
      || lookupStoredLabel(item);
  }

  function guessLabelLocal(message, signal = '') {
    const hay = `${message || ''} ${signal || ''}`;
    for (const [re, label] of SIGNAL_LABEL_RULES) {
      if (re.test(hay)) return label;
    }
    return null;
  }

  function explainItemForKey(key) {
    const frame = latestFrames.get(key);
    if (!frame) return null;
    const sigs = signalsByAddress.get(Number(frame.address));
    const message = sigs?.[0]?.message
      || `0x${Number(frame.address).toString(16).toUpperCase()}`;
    const signal = sigs?.[0]?.signal || '';
    return { id: key, message, signal, address: `0x${Number(frame.address).toString(16).toUpperCase()}` };
  }

  function resetBulkExplain() {
    if (bulkExplainTimer) clearTimeout(bulkExplainTimer);
    bulkExplainTimer = null;
    bulkExplainToken += 1;
  }

  function scheduleBulkExplainAll() {
    if (bulkExplainTimer) clearTimeout(bulkExplainTimer);
    bulkExplainTimer = window.setTimeout(() => {
      bulkExplainTimer = null;
      runBulkExplainAll().catch(console.error);
    }, 160);
  }

  function repaintAllExplainCells() {
    for (const key of tableRows.keys()) {
      const label = explainCache.get(key);
      const row = tableRows.get(key);
      if (!row || !label) continue;
      row.label = label;
      row.pending = false;
    }
    scheduleVirtualRender();
    updateLabelProgress();
  }

  async function runBulkExplainAll() {
    if (!autoLabelEnabled) return;
    if (bulkExplainRunning) return;
    const token = bulkExplainToken;
    const keys = Array.from(latestFrames.keys()).slice(0, BULK_EXPLAIN_MAX);
    const pending = keys.filter((k) => {
      const cached = explainCache.get(k);
      if (cached && !GENERIC_LABELS.has(cached)) return false;
      if (cached && GENERIC_LABELS.has(cached)) explainCache.delete(k);
      return true;
    });
    if (!pending.length) return;

    const items = [];
    const needAiKeys = [];
    for (const key of pending) {
      const item = explainItemForKey(key);
      if (!item) continue;
      const cached = resolveLabelForItem(item);
      if (cached) {
        applyExplainLabel(key, cached, { persist: false });
        continue;
      }
      const row = tableRows.get(key);
      if (row) row.pending = true;
      items.push({
        id: key,
        message: item.message,
        signal: item.signal,
        address: item.address,
      });
      needAiKeys.push(key);
    }
    scheduleVirtualRender();

    if (!items.length || token !== bulkExplainToken) return;

    bulkExplainRunning = true;
    if (els.autoLabelBtn) els.autoLabelBtn.disabled = true;
    try {
      for (let i = 0; i < items.length; i += EXPLAIN_CHUNK) {
        if (token !== bulkExplainToken) return;
        const chunkItems = items.slice(i, i + EXPLAIN_CHUNK);
        const chunkKeys = needAiKeys.slice(i, i + EXPLAIN_CHUNK);
        const data = await api('POST', '/api/cabana/explain_batch', {
          dbc: dbcName,
          items: chunkItems,
          lang: getLang(),
        }, { timeoutMs: 90000 });
        if (token !== bulkExplainToken) return;
        const labels = data.ok ? parseExplainBatchLabels(data, chunkKeys) : new Map();
        for (const key of chunkKeys) {
          const item = explainItemForKey(key);
          const fromAi = labels.get(key);
          const local = item ? guessLabelLocal(item.message, item.signal) : null;
          const stored = item ? lookupStoredLabel(item) : null;
          const finalLabel = local || (fromAi && !GENERIC_LABELS.has(fromAi) ? fromAi : null) || stored;
          if (finalLabel) {
            applyExplainLabel(key, finalLabel, { persist: Boolean(fromAi && !GENERIC_LABELS.has(fromAi)) });
          }
        }
        updateLabelProgress();
        if (!data.ok && els.hint) {
          els.hint.textContent = data.error || t('cabanaExplainFail', '失败');
        }
        await new Promise((r) => setTimeout(r, 0));
      }
    } finally {
      bulkExplainRunning = false;
      for (const key of needAiKeys) {
        const row = tableRows.get(key);
        if (row?.pending && !explainCache.get(key)) row.pending = false;
      }
      if (els.autoLabelBtn) els.autoLabelBtn.disabled = false;
      scheduleVirtualRender();
    }
  }

  function applyExplainLabel(key, label, { persist = true } = {}) {
    if (!label) return;
    const short = String(label).replace(/\s+/g, '').slice(0, 8);
    explainCache.set(key, short);
    const row = tableRows.get(key);
    if (row) {
      row.label = short;
      row.pending = false;
    }
    if (persist) {
      const item = explainItemForKey(key);
      if (item) persistExplainLabel(item, short);
    }
    scheduleVirtualRender();
    updateLabelProgress();
  }

  function parseExplainBatchLabels(payload, fallbackKeys) {
    const map = new Map();
    const labels = payload?.labels;
    if (labels && typeof labels === 'object') {
      for (const [k, v] of Object.entries(labels)) {
        if (v) map.set(String(k), String(v).replace(/\s+/g, '').slice(0, 8));
      }
      return map;
    }
    const text = String(payload?.response || '');
    if (!text) return map;
    try {
      const j = JSON.parse(text);
      if (j && typeof j === 'object') {
        for (const [k, v] of Object.entries(j)) {
          if (v) map.set(String(k), String(v).replace(/\s+/g, '').slice(0, 8));
        }
        return map;
      }
    } catch {
      const m = text.match(/\{[\s\S]*\}/);
      if (m) {
        try {
          const j = JSON.parse(m[0]);
          for (const [k, v] of Object.entries(j)) {
            if (v) map.set(String(k), String(v).replace(/\s+/g, '').slice(0, 8));
          }
          return map;
        } catch { /* ignore */ }
      }
    }
    for (const key of fallbackKeys) {
      if (!map.has(key)) map.set(key, '其他');
    }
    return map;
  }

  async function fetchExplain(key, primary) {
    const data = await api('POST', '/api/cabana/explain', {
      id: key,
      dbc: dbcName,
      message: primary.message,
      signal: primary.signal,
      address: key.split(':')[1],
      decoded: primary.decoded || primary.value || '',
      value: primary.value || primary.decoded || '',
    });
    if (!data.ok) return null;
    explainCache.set(key, data.response);
    return data.response;
  }

  function replayRowPrimary(frame) {
    const sigs = signalsByAddress.get(Number(frame.address));
    if (!sigs?.length) return null;
    const sig = sigs[0];
    return { message: sig.message, signal: sig.signal, value: '', decoded: '' };
  }

  function formatReplayRowTime(frame) {
    if (replayStartMono > 0) {
      return Math.max(0, frame.time - replayStartMono).toFixed(2);
    }
    return frame.time.toFixed(2);
  }

  async function explainRow(key, primary, btn) {
    if (explainCache.has(key)) {
      applyExplainLabel(key, explainCache.get(key), { persist: false });
      return;
    }
    if (btn) {
      btn.disabled = true;
      btn.textContent = t('cabanaAnalyzing', '分析中…');
    }
    const data = await api('POST', '/api/cabana/explain', {
      id: key,
      dbc: dbcName,
      message: primary.message,
      signal: primary.signal,
      address: key.split(':')[1],
      decoded: primary.decoded || primary.value || '',
      value: primary.value || primary.decoded || '',
    }, { timeoutMs: 60000 });
    if (btn) {
      btn.disabled = false;
      btn.textContent = t('cabanaExplainBtn', 'AI 解释');
    }
    if (!data.ok) {
      if (btn) {
        btn.textContent = t('cabanaExplainFail', '失败');
        btn.title = data.error || '';
      }
      if (els.hint) els.hint.textContent = data.error || t('cabanaExplainFail', '失败');
      return;
    }
    applyExplainLabel(key, data.response);
  }

  async function loadDbc(name) {
    if (!name) return;
    const data = await api('GET', `/api/cabana/dbc/${encodeURIComponent(name)}`);
    if (!data.ok) {
      if (els.metaBar) els.metaBar.textContent = data.error || t('cabanaDbcLoadFailed', 'DBC load failed');
      return;
    }
    dbcName = name;
    serverLabelStore = {};
    await preloadServerLabelCache();
    if (els.dbcSearch) els.dbcSearch.value = name;
    signals = data.signals || [];
    buildSignalIndex();
    if (els.metaBar) {
      els.metaBar.textContent = `${t('cabanaDbcLoaded', '已加载')} ${name} · ${signals.length} ${t('cabanaSignals', '个信号')}`;
    }
    renderDbcList(filterDbcNames(els.dbcSearch?.value || ''));
    updateAiButtons();
    scheduleBulkExplainAll();
  }

  const QUERY_ALIASES = {
    丰田: 'toyota',
    雷克萨斯: 'lexus',
    凌志: 'lexus',
    本田: 'honda',
    讴歌: 'acura',
    大众: 'volkswagen',
    奥迪: 'audi',
    特斯拉: 'tesla',
    斯巴鲁: 'subaru',
    日产: 'nissan',
    现代: 'hyundai',
    起亚: 'kia',
    福特: 'ford',
    马自达: 'mazda',
    雪佛兰: 'chevrolet',
    卡罗拉: 'corolla',
    凯美瑞: 'camry',
    荣放: 'rav4',
    普锐斯: 'prius',
    汉兰达: 'highlander',
    思域: 'civic',
    雅阁: 'accord',
  };

  function expandQueryAliases(query) {
    const extras = [];
    for (const [alias, en] of Object.entries(QUERY_ALIASES)) {
      if (query.includes(alias)) extras.push(en);
    }
    return extras.length ? `${query} ${extras.join(' ')}` : query;
  }

  function getDbcEntry(name) {
    return dbcCatalog[name] || null;
  }

  function getDbcHaystacks(name) {
    const entry = getDbcEntry(name);
    const searchText = entry?.searchText || '';
    const labels = (entry?.labels || []).join(' ');
    const blob = `${name} ${searchText} ${labels}`;
    return {
      compact: normalizeDbcCompact(blob),
      spaced: normalizeDbcSpaced(blob),
      entry,
    };
  }

  function dbcItemSubtitle(name) {
    const entry = getDbcEntry(name);
    if (!entry) return '';
    if (entry.labels?.length) return entry.labels.slice(0, 2).join(' · ');
    if (entry.models?.length) return entry.models.slice(0, 3).join(' · ');
    if (entry.makes?.length) return entry.makes.slice(0, 2).join(' · ');
    return entry.brands?.[0] || '';
  }

  function fillDbcListItem(li, name) {
    const sub = dbcItemSubtitle(name);
    li.replaceChildren();
    const title = document.createElement('span');
    title.className = 'cabana-dbc-item-name';
    title.textContent = name;
    li.appendChild(title);
    if (sub) {
      const hint = document.createElement('span');
      hint.className = 'cabana-dbc-item-sub';
      hint.textContent = sub;
      li.appendChild(hint);
    }
  }

  function normalizeDbcCompact(s) {
    return (s || '').toLowerCase().replace(/[_\-\s.]+/g, '');
  }

  function normalizeDbcSpaced(s) {
    return (s || '').toLowerCase().replace(/[_\-\.]+/g, ' ').replace(/\s+/g, ' ').trim();
  }

  function splitDbcTokens(query) {
    return (query || '').toLowerCase().split(/[\s_\-./]+/).map((t) => t.trim()).filter(Boolean);
  }

  function levenshtein(a, b) {
    if (a === b) return 0;
    if (!a.length) return b.length;
    if (!b.length) return a.length;
    const cols = b.length + 1;
    const dp = new Array(cols);
    for (let j = 0; j < cols; j++) dp[j] = j;
    for (let i = 1; i <= a.length; i++) {
      let prev = dp[0];
      dp[0] = i;
      for (let j = 1; j <= b.length; j++) {
        const tmp = dp[j];
        const cost = a[i - 1] === b[j - 1] ? 0 : 1;
        dp[j] = Math.min(dp[j] + 1, dp[j - 1] + 1, prev + cost);
        prev = tmp;
      }
    }
    return dp[b.length];
  }

  function isSubsequence(hay, needle) {
    let h = 0;
    for (let i = 0; i < needle.length; i++) {
      const idx = hay.indexOf(needle[i], h);
      if (idx < 0) return false;
      h = idx + 1;
    }
    return true;
  }

  function maxEditDistance(len) {
    if (len <= 3) return 1;
    if (len <= 6) return 2;
    return Math.max(2, Math.floor(len / 3));
  }

  function bestFuzzyInHay(hay, token) {
    if (!token) return 0;
    if (hay.includes(token)) return 0;
    const maxDist = maxEditDistance(token.length);
    let best = maxDist + 1;
    const minLen = Math.max(1, token.length - maxDist);
    const maxLen = token.length + maxDist;
    for (let start = 0; start < hay.length; start++) {
      const endMax = Math.min(hay.length, start + maxLen);
      for (let len = minLen; len <= endMax - start; len++) {
        best = Math.min(best, levenshtein(token, hay.slice(start, start + len)));
        if (best === 0) return 0;
      }
    }
    return best;
  }

  function fuzzyTokenScore(name, token) {
    const t = normalizeDbcCompact(token);
    if (!t) return 100;

    const { compact: hay, spaced } = getDbcHaystacks(name);

    const segments = spaced.split(' ').filter(Boolean);

    if (hay.includes(t)) {
      return 130 + Math.min(40, t.length * 4);
    }

    if (spaced.includes(token.toLowerCase())) {
      return 115 + Math.min(30, t.length * 3);
    }

    for (const seg of segments) {
      const segCompact = normalizeDbcCompact(seg);
      if (segCompact === t || segCompact.includes(t)) {
        return 105 + Math.min(25, t.length * 3);
      }
      if (isSubsequence(segCompact, t)) {
        return 80 + Math.min(20, t.length * 2);
      }
      const segDist = bestFuzzyInHay(segCompact, t);
      const segMax = maxEditDistance(t.length);
      if (segDist <= segMax) {
        return 65 - segDist * 10;
      }
    }

    if (isSubsequence(hay, t)) {
      return 75 + Math.min(20, t.length * 2);
    }

    const dist = bestFuzzyInHay(hay, t);
    const maxDist = maxEditDistance(t.length);
    if (dist <= maxDist) {
      return 50 - dist * 12;
    }

    return 0;
  }

  function fuzzyMatchDbc(query, name) {
    const q = expandQueryAliases((query || '').trim());
    if (!q) return 1;

    const { compact: hay, entry } = getDbcHaystacks(name);
    const qCompact = normalizeDbcCompact(q);
    if (qCompact && hay.includes(qCompact)) {
      return 220 + qCompact.length;
    }

    if (entry?.labels?.some((label) => label.toLowerCase().includes(q.toLowerCase()))) {
      return 210;
    }

    const tokens = splitDbcTokens(q);
    if (!tokens.length) return 0;

    let total = 0;
    for (const token of tokens) {
      const score = fuzzyTokenScore(name, token);
      if (score <= 0) return 0;
      total += score;
    }
    return total / tokens.length;
  }

  function filterDbcNames(query) {
    const q = (query || '').trim();
    if (!q) return dbcNames;
    return dbcNames
      .map((name) => ({ name, score: fuzzyMatchDbc(q, name) }))
      .filter((item) => item.score > 0)
      .sort((a, b) => b.score - a.score || a.name.localeCompare(b.name))
      .map((item) => item.name);
  }

  function renderDbcList(names) {
    const list = els.dbcList;
    if (!list) return;
    list.innerHTML = '';
    if (!names.length) {
      const empty = document.createElement('li');
      empty.className = 'cabana-dbc-empty';
      empty.textContent = t('cabanaDbcEmpty', '无匹配结果');
      list.appendChild(empty);
      return;
    }
    const maxShow = 100;
    const shown = names.slice(0, maxShow);
    for (const name of shown) {
      const li = document.createElement('li');
      li.className = `cabana-dbc-item${name === dbcName ? ' selected' : ''}`;
      fillDbcListItem(li, name);
      li.setAttribute('role', 'option');
      li.tabIndex = -1;
      li.addEventListener('mousedown', (e) => e.preventDefault());
      li.addEventListener('click', async () => {
        await selectDbc(name);
        closeDbcPicker();
      });
      list.appendChild(li);
    }
    if (names.length > maxShow) {
      const more = document.createElement('li');
      more.className = 'cabana-dbc-more';
      more.textContent = tf('cabanaDbcMore', { n: names.length - maxShow });
      list.appendChild(more);
    }
  }

  function openDbcPicker() {
    if (!els.dbcList || !els.dbcSearch) return;
    dbcPickerOpen = true;
    els.dbcList.removeAttribute('hidden');
    els.dbcSearch.setAttribute('aria-expanded', 'true');
    renderDbcList(filterDbcNames(els.dbcSearch.value));
  }

  function closeDbcPicker() {
    if (!els.dbcList || !els.dbcSearch) return;
    dbcPickerOpen = false;
    els.dbcList.setAttribute('hidden', '');
    els.dbcSearch.setAttribute('aria-expanded', 'false');
    if (dbcName) els.dbcSearch.value = dbcName;
  }

  async function selectDbc(name) {
    if (!name || !dbcNames.includes(name)) return;
    await loadDbc(name);
  }

  async function setDbcCatalog(catalog, preferred) {
    const items = Array.isArray(catalog) ? catalog : [];
    dbcCatalog = {};
    dbcNames = [];
    for (const item of items) {
      const name = typeof item === 'string' ? item : item?.name;
      if (!name) continue;
      dbcNames.push(name);
      dbcCatalog[name] = typeof item === 'string' ? { name, searchText: name } : item;
    }
    if (els.dbcSearch) {
      const count = dbcNames.length;
      const hint = count ? ` (${count})` : '';
      els.dbcSearch.placeholder = `${t('cabanaDbcSearch', '模糊搜索 DBC 或车型…')}${hint}`;
    }
    const pref = preferred && dbcNames.includes(preferred) ? preferred : dbcNames[0];
    if (pref) await selectDbc(pref);
    else if (els.dbcSearch) els.dbcSearch.value = '';
  }

  function onDbcSearchInput() {
    renderDbcList(filterDbcNames(els.dbcSearch?.value || ''));
    openDbcPicker();
  }

  async function onDbcSearchKeydown(e) {
    if (e.key === 'Escape') {
      closeDbcPicker();
      els.dbcSearch?.blur();
      return;
    }
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const matches = filterDbcNames(els.dbcSearch?.value || '');
    if (!matches.length) return;
    await selectDbc(matches[0]);
    closeDbcPicker();
    els.dbcSearch?.blur();
  }

  async function loadCar() {
    const dbcs = await api('GET', '/api/cabana/dbcs');
    const catalog = dbcs.ok
      ? (dbcs.catalog || (dbcs.dbcs || []).map((name) => ({ name, searchText: name })))
      : [];
    const data = await api('GET', '/api/cabana/car');
    if (!data.ok) {
      const hint = data.hint || data.error || t('cabanaNoCarParams', '无车型信息');
      if (els.metaBar) els.metaBar.textContent = `${hint} · ${t('cabanaOfflineHint', '可手动选择 DBC')}`;
      await setDbcCatalog(catalog, catalog[0]?.name);
      return;
    }
    const { car, suggested_dbc } = data;
    if (els.metaBar) els.metaBar.textContent = `${car.brand} · ${car.carFingerprint}`;
    await setDbcCatalog(catalog, suggested_dbc || catalog[0]?.name);
  }

  function disconnectLive() {
    livePendingFrames = [];
    liveFlushScheduled = false;
    liveConnectedAt = 0;
    liveFrameBatches = 0;
    if (ws) {
      ws.close();
      ws = null;
    }
  }

  function disconnectReplay() {
    if (offlineWs) {
      offlineWs.onclose = null;
      offlineWs.onmessage = null;
      offlineWs.close();
      offlineWs = null;
    }
    replayConnecting = false;
    replayPlayPending = false;
    replayPaused = true;
    replayIndexReady = false;
    resetReplayQueue();
    lastReplayUiPaintAt = 0;
    if (replayWsFlushTimer != null) {
      clearTimeout(replayWsFlushTimer);
      replayWsFlushTimer = null;
    }
    replayWsBuffer = [];
    clearTableRows();
    clearReplayLoading();
  }

  function sendReplayControl(payload) {
    if (offlineWs?.readyState === WebSocket.OPEN) {
      offlineWs.send(JSON.stringify(payload));
    }
  }

  function setPanelMode(mode) {
    panelMode = mode === 'replay' ? 'replay' : 'live';
    els.modeTabs?.forEach((tab) => {
      tab.classList.toggle('active', tab.dataset.mode === panelMode);
    });
    const replay = panelMode === 'replay';
    if (root) {
      root.classList.toggle('cabana-mode-replay', replay);
      root.classList.toggle('cabana-mode-live', !replay);
    }
    if (els.replayBar) els.replayBar.hidden = !replay;
    if (els.connectBtn) els.connectBtn.hidden = replay;
    if (els.routeChatBtn) els.routeChatBtn.hidden = !replay;
    if (els.deepAnalyzeBtn) els.deepAnalyzeBtn.hidden = false;
    if (replay) {
      disconnectLive();
      els.status.textContent = t('cabanaReplay', '回放');
      els.status.className = 'cab-status';
      loadRoutes().catch(console.error);
    } else {
      disconnectReplay();
      clearReplayLoading();
      if (els.replayLoading) els.replayLoading.setAttribute('hidden', '');
      els.status.textContent = t('cabanaOffline', '离线');
      els.status.className = 'cab-status';
    }
    updateAiButtons();
  }

  function formatRouteOption(r) {
    const flags = [
      r.has_qlog ? 'qlog' : null,
      r.has_rlog ? 'rlog' : null,
    ].filter(Boolean).join(' · ');
    const date = r.date ? `${r.date} · ` : '';
    const tail = flags ? ` (${flags})` : '';
    return `${date}${r.name}${tail}`;
  }

  async function loadRoutes() {
    const data = await api('GET', '/api/cabana/routes');
    if (!els.routeSelect) return;
    els.routeSelect.innerHTML = '';
    if (!data.ok || !data.routes?.length) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = t('cabanaNoRoutes', '无可用路线');
      els.routeSelect.appendChild(opt);
      return;
    }
    for (const r of data.routes) {
      if (!r.has_qlog && !r.has_rlog) continue;
      const opt = document.createElement('option');
      opt.value = r.name;
      opt.textContent = formatRouteOption(r);
      els.routeSelect.appendChild(opt);
    }
    replayRoute = els.routeSelect.value;
  }

  function connectReplay() {
    const route = els.routeSelect?.value;
    if (!route) {
      els.hint.textContent = t('cabanaSelectRoute', '请先选择路线');
      return;
    }
    if (offlineWs?.readyState === WebSocket.OPEN) {
      if (replayIndexReady) {
        replayPaused = false;
        sendReplayControl({ action: 'play' });
        return;
      }
    }
    if (offlineWs?.readyState === WebSocket.CONNECTING || replayConnecting) {
      replayPaused = false;
      replayPlayPending = true;
      els.hint.textContent = t('cabanaReplayConnecting', '正在连接回放…');
      return;
    }

    replayRoute = route;
    replayPaused = false;
    replayPlayPending = true;
    if (offlineWs) {
      offlineWs.onclose = null;
      offlineWs.close();
      offlineWs = null;
    }
    replayConnecting = true;
    replayIndexReady = false;
    resetBulkExplain();
    resetReplayQueue();
    latestFrames.clear();
    if (els.tbody) els.tbody.innerHTML = '';
    setReplayLoading(true, t('cabanaReplayLoadingStart', '正在打开日志…'));

    const speed = parseFloat(els.replaySpeed?.value || '1') || 1;
    replaySpeed = speed;
    const qs = new URLSearchParams({ route, speed: String(speed), start_time: '0', autoplay: '0' });
    if (els.replayFull?.checked) qs.set('full', '1');
    offlineWs = new WebSocket(wsUrl(`/api/cabana/offline/ws?${qs}`));

    offlineWs.onopen = () => {
      replayConnecting = false;
      els.status.textContent = t('cabanaReplayLoading', '索引中');
      els.status.className = 'cab-status live';
      replayPaused = false;
      if (replayPlayPending) {
        replayPlayPending = false;
        sendReplayControl({ action: 'play' });
      }
    };

    offlineWs.onerror = () => {
      replayConnecting = false;
      replayPlayPending = false;
      clearReplayLoading();
      els.hint.textContent = t('cabanaReplayError', '回放失败');
    };

    offlineWs.onmessage = (ev) => {
      queueReplayWsMessage(ev.data);
    };

    offlineWs.onclose = () => {
      offlineWs = null;
      replayConnecting = false;
      replayPlayPending = false;
      clearReplayLoading();
      if (els.replayPlayBtn) els.replayPlayBtn.disabled = false;
      if (els.replayPauseBtn) els.replayPauseBtn.disabled = false;
      if (panelMode === 'replay' && !replayPaused) {
        els.status.textContent = t('cabanaOffline', '离线');
        els.status.className = 'cab-status';
      }
    };
  }

  function handleOfflineWsMessage(msg) {
      if (msg.type === 'loading') {
        if (!replayIndexReady) {
          setReplayLoading(true, formatLoadingText(msg));
        }
        return;
      }
      if (msg.type === 'metadata_update') {
        replayDuration = msg.duration || replayDuration;
        updateProgressUI();
        return;
      }
      if (msg.type === 'metadata') {
        clearReplayLoading();
        replayIndexReady = true;
        replayMeta = msg;
        replayDuration = msg.duration || 0;
        replayStartMono = msg.start_time || 0;
        replayProgress = 0;
        lastProgressPaintAt = 0;
        updateProgressUI();
        els.status.textContent = t('cabanaReplay', '回放');
        let hint;
        if (msg.cached) {
          hint = t('cabanaReplayFromCache', '已从缓存加载 CAN，可直接播放');
        } else if (msg.source === 'rlog' || msg.full_can) {
          hint = t('cabanaReplayFromRlog', '已从 rlog 加载完整 CAN（首次索引可能较慢）');
        } else if (msg.source === 'qlog') {
          hint = t('cabanaReplayFromQlog', '快速模式（仅 qlog CAN，不读视频）');
        } else {
          hint = t('cabanaPanelHint', '行驶中也可只读查看；点击「AI 解释」了解每个信号含义');
        }
        if (msg.decimated) {
          hint += ` · ${t('cabanaReplayDecimated', '长路线已抽样显示')}`;
        }
        if (msg.streaming) {
          hint += ` · ${t('cabanaReplayStreaming', '后台继续索引，可先播放')}`;
        }
        els.hint.textContent = hint;
        if (els.replayPlayBtn) els.replayPlayBtn.disabled = false;
        if (els.replayPauseBtn) els.replayPauseBtn.disabled = false;
        const shouldAutoPlay = replayPlayPending || !replayPaused;
        replayPlayPending = false;
        if (shouldAutoPlay) {
          replayPaused = false;
          sendReplayControl({ action: 'play' });
        } else {
          replayPaused = true;
        }
        scheduleBulkExplainAll();
        return;
      }
      if (msg.type === 'can') {
        if (replayLoading) clearReplayLoading();
        if (Array.isArray(msg.frames) && msg.frames.length) {
          applyReplayCanBatch(msg.frames);
          if (msg.preview) scheduleBulkExplainAll();
        }
        if (typeof msg.progress === 'number') {
          updateReplayProgress(msg.progress);
        }
        return;
      }
      if (msg.type === 'seeked' && typeof msg.time === 'number') {
        resetReplayQueue();
        clearTableRows();
        replayProgress = msg.time;
        lastProgressPaintAt = 0;
        updateProgressUI();
        return;
      }
      if (msg.type === 'done') {
        replayPaused = true;
        if (els.replayPlayBtn) els.replayPlayBtn.disabled = false;
        if (els.replayPauseBtn) els.replayPauseBtn.disabled = true;
        els.hint.textContent = t('cabanaReplayDone', '回放结束');
        scheduleBulkExplainAll();
      }
      if (msg.type === 'error') {
        clearReplayLoading();
        const err = msg.error || '';
        if (err.includes('No qlog/rlog')) {
          els.hint.textContent = t('cabanaReplayNoLogs', '该路线没有 qlog/rlog，无法回放');
        } else {
          els.hint.textContent = err || t('cabanaReplayError', '回放失败');
        }
        els.status.textContent = t('cabanaOffline', '离线');
      }
  }

  function connectLive() {
    if (panelMode !== 'live') return;
    disconnectLive();
    ws = new WebSocket(wsUrl('/api/cabana/ws'));
    ws.onopen = () => {
      liveConnectedAt = Date.now();
      liveFrameBatches = 0;
      els.status.textContent = t('cabanaLive', '实时');
      els.status.className = 'cab-status live';
      updateAiButtons();
    };
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === 'can') enqueueCanFrames(msg.frames);
    };
    ws.onclose = () => {
      ws = null;
      liveConnectedAt = 0;
      liveFrameBatches = 0;
      if (panelMode === 'live') {
        els.status.textContent = t('cabanaOffline', '离线');
        els.status.className = 'cab-status';
      }
      updateAiButtons();
    };
  }

  function formatDurationMs(ms) {
    const s = Math.max(0, Math.floor(ms / 1000));
    const m = Math.floor(s / 60);
    const r = s % 60;
    return m > 0 ? tf('cabanaDurationMinSec', { m, s: r }) : tf('cabanaDurationSec', { s: r });
  }

  function collectFramesText(limit = 30) {
    return Array.from(latestFrames.values()).slice(-limit).map((f) => {
      const sigs = signalsByAddress.get(f.address);
      const name = sigs?.[0]?.message || `0x${f.address.toString(16)}`;
      const bus = f.bus != null ? ` bus${f.bus}` : '';
      return `${name}${bus}: ${f.data || ''}`;
    }).join('\n');
  }

  function compactRouteSummary(summary) {
    const s = summary.summary || summary;
    return JSON.stringify({
      route: s.route || replayRoute,
      duration: s.duration,
      can_frames: s.can_frames,
      dbc: s.dbc || dbcName,
    });
  }

  function buildLiveContextLine() {
    if (panelMode !== 'live' || !ws || ws.readyState !== WebSocket.OPEN) return '';
    const elapsed = liveConnectedAt ? formatDurationMs(Date.now() - liveConnectedAt) : '—';
    return tf('cabanaLiveContext', {
      elapsed,
      batches: liveFrameBatches,
      frames: latestFrames.size,
    });
  }

  function buildCabanaAiContext() {
    const lines = [];
    if (dbcName) lines.push(`DBC: ${dbcName}`);
    const route = replayRoute || els.routeSelect?.value;
    if (route) lines.push(`${t('cabanaRouteLabel', 'Route')}: ${route}`);
    if (panelMode === 'replay' && replayDuration > 0) {
      lines.push(`${t('cabanaReplayProgressLabel', 'Replay')}: ${formatReplayTime(replayProgress)} / ${formatReplayTime(replayDuration)}`);
    }
    const liveLine = buildLiveContextLine();
    if (liveLine) lines.push(liveLine);
    return lines.join('\n');
  }

  function showAiResult(text, { analyzing = false, noScroll = false } = {}) {
    lastAiResult = text || '';
    if (!els.aiResult || !els.aiResultText) return;
    if (!text && !analyzing) {
      els.aiResult.setAttribute('hidden', '');
      els.aiResult.classList.remove('analyzing');
      return;
    }
    els.aiResult.removeAttribute('hidden');
    els.aiResult.classList.toggle('analyzing', analyzing);
    els.aiResultText.textContent = text || t('cabanaAnalyzing', '分析中…');
    if (!noScroll) {
      requestAnimationFrame(() => {
        els.aiResult?.scrollIntoView({ behavior: 'auto', block: 'nearest' });
      });
    }
  }

  function buildAnalyzeQuestion() {
    if (panelMode === 'replay') {
      const route = replayRoute || els.routeSelect?.value || '';
      if (route && replayDuration > 0) {
        return tf('cabanaAnalyzeReplayAt', { route, time: formatReplayTime(replayProgress) });
      }
      return t('cabanaAnalyzeReplay', 'Analyze current replay CAN samples for anomalies and key signals.');
    }
    return t('cabanaAnalyzeLive', 'Analyze current live CAN samples for anomalies and key signals.');
  }

  async function runDeepAnalyze() {
    if (aiAnalyzeRunning) return;
    const framesText = collectFramesText(30);
    if (!framesText.trim()) {
      els.hint.textContent = panelMode === 'live'
        ? t('cabanaAiNeedLive', '请先连接实时 CAN 并等待采样')
        : t('cabanaAiNeedReplay', '请先选择路线并等待 CAN 数据加载');
      return;
    }
    aiAnalyzeRunning = true;
    if (els.deepAnalyzeBtn) els.deepAnalyzeBtn.disabled = true;
    showAiResult(t('cabanaDeepAnalyzing', '正在深度分析，请稍候…'), { analyzing: true, noScroll: true });
    await new Promise((r) => setTimeout(r, 0));

    try {
      const context = buildCabanaAiContext();
      const question = buildAnalyzeQuestion();
      const userParts = [question];
      if (context) userParts.push(`\n${t('cabanaContextLabel', 'Context')}:\n${context}`);
      if (panelMode === 'replay') {
        const route = replayRoute || els.routeSelect?.value;
        if (route) {
          const summary = await api('GET', `/api/cabana/route/${encodeURIComponent(route)}/summary`, null, { timeoutMs: 15000 });
          if (summary.ok) {
            userParts.push(`\n${t('cabanaRouteSummaryLabel', 'Route summary')}:\n${compactRouteSummary(summary)}`);
          }
        }
      } else if (dbcName) {
        userParts.push(`\nDBC: ${dbcName}`);
      }
      userParts.push(`\n${t('cabanaCanSamplesLabel', 'CAN samples')}:\n${framesText}`);
      const data = await api('POST', '/api/cabana/analyze', {
        lang: getLang(),
        messages: [
          { role: 'system', content: t('cabanaAiSystemPrompt') },
          { role: 'user', content: userParts.join('') },
        ],
      }, { timeoutMs: 300000 });
      if (!data.ok) {
        showAiResult(data.error || t('cabanaExplainFail', '失败'));
        return;
      }
      showAiResult(data.response || '');
    } catch (e) {
      showAiResult(String(e?.message || e));
    } finally {
      aiAnalyzeRunning = false;
      if (els.deepAnalyzeBtn) els.deepAnalyzeBtn.disabled = false;
    }
  }

  function sendFramesToChat() {
    if (!onSendToChat) return;
    const framesText = collectFramesText(40);
    if (!framesText.trim()) {
      els.hint.textContent = panelMode === 'live'
        ? t('cabanaAiNeedLive', '请先连接实时 CAN 并等待采样')
        : t('cabanaAiNeedReplay', '请先选择路线并等待 CAN 数据加载');
      return;
    }
    const ctx = buildCabanaAiContext();
    let prompt;
    if (panelMode === 'live') {
      prompt = t('cabanaAnalyzeLive', '分析当前实时 CAN 采样，指出异常与关键信号。');
    } else if (replayDuration > 0 && replayRoute) {
      prompt = tf('cabanaAnalyzeReplayAt', {
        route: replayRoute,
        time: formatReplayTime(replayProgress),
      });
    } else {
      prompt = t('cabanaAnalyzeReplay', '分析当前回放 CAN 采样，指出异常与关键信号。');
    }
    const parts = [prompt];
    if (ctx) parts.push(`\n${t('cabanaContextLabel', '上下文')}:\n${ctx}`);
    parts.push(`\n${t('cabanaCanSamplesLabel', 'CAN 采样')}:\n${framesText}`);
    onSendToChat(parts.join(''), { keepCabanaOpen: true });
  }

  async function sendRouteToChat() {
    if (!onSendToChat) return;
    const route = replayRoute || els.routeSelect?.value;
    if (!route) {
      els.hint.textContent = t('cabanaSelectRoute', '请先选择路线');
      return;
    }
    const start = Math.max(0, Math.floor(replayProgress - 15));
    const end = replayDuration > 0
      ? Math.min(Math.ceil(replayDuration), Math.ceil(replayProgress + 15))
      : Math.ceil(replayProgress + 15);
    const parts = [t('cabanaRouteChatPrompt')];
    parts.push(`\n${t('cabanaRouteLabel', '路线')}: ${route}`);
    if (dbcName) parts.push(`DBC: ${dbcName}`);
    if (replayDuration > 0) {
      parts.push(`${t('cabanaReplayProgressLabel', '回放')}: ${formatReplayTime(replayProgress)} / ${formatReplayTime(replayDuration)}`);
      parts.push(tf('cabanaReadSegmentHint', { start, end }));
    }
    parts.push(`\n${t('cabanaRouteLogsHint')}`);

    const framesText = collectFramesText(30);
    if (framesText.trim()) {
      parts.push(`\n${t('cabanaCanSamplesLabel', 'CAN 采样')}:\n${framesText}`);
    }

    if (els.routeChatBtn) els.routeChatBtn.disabled = true;
    try {
      const summary = await api('GET', `/api/cabana/route/${encodeURIComponent(route)}/summary`, null, { timeoutMs: 12000 });
      if (summary.ok) {
        parts.push(`\n${t('cabanaRouteSummaryLabel', '路线摘要')}:\n${compactRouteSummary(summary)}`);
      }
    } catch { /* optional */ }
    if (els.routeChatBtn) els.routeChatBtn.disabled = false;

    onSendToChat(parts.join('\n'), { keepCabanaOpen: true });
  }

  function sendAiResultToChat() {
    if (!onSendToChat || !lastAiResult.trim()) return;
    const ctx = buildCabanaAiContext();
    onSendToChat(
      `${t('cabanaAiResultChatPrompt', 'Cabana AI 分析结果：')}\n\n${ctx ? `${ctx}\n\n` : ''}${lastAiResult}`,
      { keepCabanaOpen: true },
    );
  }

  function updateAiButtons() {
    const hasFrames = latestFrames.size > 0;
    const liveReady = panelMode === 'live' && ws?.readyState === WebSocket.OPEN;
    const replayReady = panelMode === 'replay' && replayRoute;
    if (els.deepAnalyzeBtn) {
      els.deepAnalyzeBtn.disabled = aiAnalyzeRunning || (!hasFrames && !liveReady && !replayReady);
    }
    if (els.autoLabelBtn) {
      els.autoLabelBtn.classList.toggle('active', autoLabelEnabled);
      els.autoLabelBtn.disabled = bulkExplainRunning;
    }
    if (els.sendChatBtn) {
      els.sendChatBtn.disabled = !hasFrames && !liveReady && !replayReady;
    }
    if (els.routeChatBtn) {
      els.routeChatBtn.hidden = panelMode !== 'replay';
      els.routeChatBtn.disabled = !replayRoute;
    }
  }

  function toggleAutoLabel() {
    autoLabelEnabled = !autoLabelEnabled;
    updateAiButtons();
    if (autoLabelEnabled) scheduleBulkExplainAll();
  }

  function onSortHeaderClick(col) {
    if (sortCol === col) sortAsc = !sortAsc;
    else {
      sortCol = col;
      sortAsc = true;
    }
    root?.querySelectorAll('#cabanaTable th[data-sort]').forEach((th) => {
      th.classList.remove('sorted-asc', 'sorted-desc');
      if (th.dataset.sort === sortCol) {
        th.classList.add(sortAsc ? 'sorted-asc' : 'sorted-desc');
      }
    });
    scheduleVirtualRender();
  }

  function onCabanaKeydown(e) {
    const modal = document.getElementById('cabanaModal');
    if (!modal || modal.hidden) return;
    if (panelMode !== 'replay') return;
    if (e.target?.matches('input, textarea, select')) return;
    if (e.code === 'Space') {
      e.preventDefault();
      if (replayPaused) connectReplay();
      else {
        sendReplayControl({ action: 'pause' });
        replayPaused = true;
      }
    }
    if (e.code === 'ArrowRight' && replayDuration > 0) {
      e.preventDefault();
      replayProgress = Math.min(replayDuration, replayProgress + 1);
      sendReplayControl({ action: 'seek', time: replayProgress });
      updateProgressUI();
    }
    if (e.code === 'ArrowLeft' && replayDuration > 0) {
      e.preventDefault();
      replayProgress = Math.max(0, replayProgress - 1);
      sendReplayControl({ action: 'seek', time: replayProgress });
      updateProgressUI();
    }
  }

  function applyTranslations() {
    if (els.title) els.title.textContent = t('cabanaPanelTitle', 'CAN 总线分析');
    if (els.tabLive) els.tabLive.textContent = t('cabanaTabLiveShort', '实时');
    if (els.tabReplay) els.tabReplay.textContent = t('cabanaTabReplay', '回放');
    if (els.connectBtn) els.connectBtn.textContent = t('cabanaConnectLive', '连接实时 CAN');
    if (els.autoLabelBtn) els.autoLabelBtn.textContent = t('cabanaAutoLabel', '自动标注');
    if (els.sendChatBtn) els.sendChatBtn.textContent = t('cabanaSendSegment', '片段→聊天');
    if (els.routeChatBtn) els.routeChatBtn.textContent = t('cabanaAnalyzeRoute', '分析 route');
    if (els.deepAnalyzeBtn) els.deepAnalyzeBtn.textContent = t('cabanaDeepAnalyze', '深度分析');
    if (els.replayPlayBtn) els.replayPlayBtn.textContent = t('cabanaPlayShort', '播放');
    if (els.replayPauseBtn) els.replayPauseBtn.textContent = t('cabanaPauseShort', '暂停');
    if (els.aiResultTitle) els.aiResultTitle.textContent = t('cabanaDeepAnalyzeTitle', '深度分析');
    if (els.aiResultToChat) els.aiResultToChat.textContent = t('cabanaSendToChat', '发到聊天');
    if (els.filter) els.filter.placeholder = t('cabanaFilterPlain', '搜索报文名或信号…');
    if (els.dbcSearch) {
      const count = dbcNames.length;
      const hint = count ? ` (${count})` : '';
      els.dbcSearch.placeholder = `${t('cabanaDbcSearch', '模糊搜索 DBC 或车型…')}${hint}`;
    }
    if (els.thTime) els.thTime.textContent = t('cabanaThTime', '时间');
    if (els.thName) els.thName.textContent = t('cabanaThNamePlain', '报文');
    if (els.thValue) els.thValue.textContent = t('cabanaThValue', '当前值');
    if (els.thExplain) els.thExplain.textContent = t('cabanaThFunction', '功能');
    if (els.progress) {
      els.progress.title = t('cabanaReplayProgressHint', '拖动定位 CAN 日志时间（非视频）');
    }
    if (els.replaySpeed) {
      els.replaySpeed.title = t('cabanaReplaySpeedHint', 'CAN 数据回放倍速');
    }
    if (els.hint) els.hint.textContent = panelMode === 'replay'
      ? t('cabanaReplayPanelHint2', '回放自动标注功能标签；深度分析用于异常检测。空格播放/暂停，←→ 快进')
      : t('cabanaLivePanelHint2', '实时模式显示 CAN 报文；连接后自动标注功能');
    renderFilterChips();
    updateLabelProgress();
  }

  function bindDom() {
    els.metaBar = $('#cabanaMetaBar');
    els.labelProgress = $('#cabanaLabelProgress');
    els.autoLabelBtn = $('#cabanaAutoLabelBtn');
    els.sendChatBtn = $('#cabanaSendChatBtn');
    els.routeChatBtn = $('#cabanaRouteChatBtn');
    els.deepAnalyzeBtn = $('#cabanaDeepAnalyzeBtn');
    els.filterChips = $('#cabanaFilterChips');
    els.tableWrap = $('#cabanaTableWrap');
    els.replayStats = $('#cabanaReplayStats');
    els.dbcSearch = $('#cabanaDbcSearch');
    els.dbcList = $('#cabanaDbcList');
    els.dbcPicker = $('#cabanaDbcPicker');
    els.connectBtn = $('#cabanaConnectBtn');
    els.filter = $('#cabanaFilter');
    els.tbody = $('#cabanaTableBody') || $('#cabanaTable tbody');
    els.status = $('#cabanaStatus');
    els.title = $('#cabanaPanelTitle');
    els.hint = $('#cabanaPanelHint');
    els.thTime = $('#cabThTime');
    els.thName = $('#cabThName');
    els.thValue = $('#cabThValue');
    els.thExplain = $('#cabThExplain');
    els.modeTabs = root?.querySelectorAll('.cabana-mode-tab');
    els.tabLive = $('#cabanaTabLive');
    els.tabReplay = $('#cabanaTabReplay');
    els.replayBar = $('#cabanaReplayBar');
    els.routeSelect = $('#cabanaRouteSelect');
    els.replayPlayBtn = $('#cabanaReplayPlayBtn');
    els.replayPauseBtn = $('#cabanaReplayPauseBtn');
    els.replaySpeed = $('#cabanaReplaySpeed');
    els.replayFull = $('#cabanaReplayFull');
    els.progress = $('#cabanaProgress');
    els.progressLabel = $('#cabanaProgressLabel');
    els.aiResult = $('#cabanaAiResult');
    els.aiResultTitle = $('#cabanaAiResultTitle');
    els.aiResultText = $('#cabanaAiResultText');
    els.aiResultToChat = $('#cabanaAiResultToChat');
    els.aiResultClose = $('#cabanaAiResultClose');
    els.replayLoading = $('#cabanaReplayLoading');
    els.replayLoadingText = $('#cabanaReplayLoadingText');

    renderFilterChips();
    root?.querySelectorAll('#cabanaTable th[data-sort]').forEach((th) => {
      th.addEventListener('click', () => onSortHeaderClick(th.dataset.sort));
    });
    els.tableWrap?.addEventListener('scroll', () => scheduleVirtualRender(), { passive: true });
    els.filter?.addEventListener('input', () => scheduleVirtualRender());
    document.addEventListener('keydown', onCabanaKeydown);

    els.modeTabs?.forEach((tab) => {
      tab.addEventListener('click', () => setPanelMode(tab.dataset.mode || 'live'));
    });

    els.dbcSearch?.addEventListener('focus', () => {
      clearTimeout(dbcBlurTimer);
      openDbcPicker();
      requestAnimationFrame(() => els.dbcSearch?.select());
    });
    els.dbcSearch?.addEventListener('input', onDbcSearchInput);
    els.dbcSearch?.addEventListener('keydown', onDbcSearchKeydown);
    els.dbcSearch?.addEventListener('blur', () => {
      dbcBlurTimer = setTimeout(closeDbcPicker, 160);
    });
    els.connectBtn?.addEventListener('click', connectLive);
    els.autoLabelBtn?.addEventListener('click', toggleAutoLabel);
    els.sendChatBtn?.addEventListener('click', () => sendFramesToChat());
    els.routeChatBtn?.addEventListener('click', () => sendRouteToChat().catch(console.error));
    els.deepAnalyzeBtn?.addEventListener('click', () => runDeepAnalyze().catch(console.error));
    els.replayPlayBtn?.addEventListener('click', () => connectReplay());
    els.replayPauseBtn?.addEventListener('click', () => {
      sendReplayControl({ action: 'pause' });
      replayPaused = true;
    });
    els.replaySpeed?.addEventListener('change', () => {
      replaySpeed = parseFloat(els.replaySpeed.value) || 1;
      sendReplayControl({ action: 'speed', value: replaySpeed });
    });
    els.routeSelect?.addEventListener('change', () => {
      replayRoute = els.routeSelect.value;
      disconnectReplay();
      replayProgress = 0;
      clearTableRows();
      updateProgressUI();
    });
    els.progress?.addEventListener('input', () => {
      if (!replayDuration) return;
      const ratio = parseInt(els.progress.value, 10) / 1000;
      replayProgress = replayDuration * ratio;
      els.progressLabel.textContent = `${t('cabanaLogTime', '日志')} ${formatReplayTime(replayProgress)} / ${formatReplayTime(replayDuration)}`;
    });
    els.progress?.addEventListener('change', () => {
      if (!replayDuration) return;
      const ratio = parseInt(els.progress.value, 10) / 1000;
      const seekTime = replayDuration * ratio;
      replayProgress = seekTime;
      if (offlineWs?.readyState === WebSocket.OPEN) {
        sendReplayControl({ action: 'seek', time: seekTime });
      } else {
        connectReplay();
      }
    });
    els.aiResultToChat?.addEventListener('click', sendAiResultToChat);
    els.aiResultClose?.addEventListener('click', () => showAiResult(''));
  }

  async function refresh() {
    applyTranslations();
    await loadCar();
  }

  function init(options = {}) {
    root = options.root || document.getElementById('cabanaPanelRoot');
    t = options.t || t;
    tf = options.tf || tf;
    onSendToChat = options.onSendToChat || null;
    getLang = options.getLang || getLang;
    if (!root) return;
    bindDom();
    applyTranslations();
    setPanelMode(panelMode);
    updateAiButtons();
    onSortHeaderClick(sortCol);
  }

  return { init, refresh, reloadRoutes: loadRoutes, connectLive, disconnectLive, disconnectReplay, syncMode: () => setPanelMode(panelMode) };
})();
