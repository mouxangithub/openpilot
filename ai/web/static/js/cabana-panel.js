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
  const DBC_PIN_KEY = 'cabana-dbc-pin-v1';
  let dbcUserPinned = false;
  let lastCarFingerprint = '';
  let lastCar = null;
  const GENERIC_LABELS = new Set(['车身', '其他']);
  const EXPLAIN_STORE_KEY = 'cabana-explain-labels-v3';
  const explainCache = new Map();
  let serverLabelStore = {};
  let maxRows = 300;
  let bulkExplainTimer = null;
  let bulkExplainToken = 0;
  const BULK_EXPLAIN_MAX = 150;
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
  let autoLabelEnabled = false;
  let aiAnalyzeRunning = false;
  let virtualRenderScheduled = false;
  let sortedKeysCache = null;
  let sortedKeysCacheSig = '';
  let plotRenderScheduled = false;
  let dbcSearchTimer = null;
  let localLabelStoreCache = null;
  let bulkExplainRunning = false;
  let els = {};
  let labeledCount = 0;

  const frameHistory = new Map();
  const msgStats = new Map();
  const HISTORY_MAX = 32;
  const PLOT_MAX_POINTS = 1200;
  let selectedKey = null;
  let plotSignalName = null;
  let plotSeriesList = [];
  const PLOT_COLORS = ['#4ecdc4', '#ff6b6b', '#ffd93d', '#6bcbff', '#c77dff', '#95e06c'];
  let plotInstance = null;
  let plotResizeObserver = null;
  let hideUnchanged = false;
  let signalFilterQuery = '';
  const prevPayloadByKey = new Map();

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
  let hasQcamera = false;
  let videoPreviewEnabled = false;
  let thumbDebounceTimer = null;
  let thumbAbort = null;
  let lastThumbKey = '';
  let thumbObjectUrl = null;
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
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        return { ok: false, error: body.error || `HTTP ${res.status}`, status: res.status };
      }
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
    const bus = Number(frame.bus) || 0;
    const nameCol = msgName ? `${msgName} · ${hex}` : hex;
    const { display: valueText, title: valueTitle } = frameValuePresentation(frame, { lite: !!opts.replay });
    const stats = msgStats.get(key);
    const freqText = stats?.hz > 0 ? stats.hz.toFixed(1) : '—';
    const countText = stats?.count ? String(stats.count) : '0';
    const prevData = prevPayloadByKey.get(key);
    const valueHtml = valueHtmlForFrame(frame, prevData);
    if (frame.data != null) prevPayloadByKey.set(key, String(frame.data));
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
      bus,
      freqText,
      relTime,
      nameCol,
      searchHay: `${nameCol} ${valueText} ${hex} bus${bus}`.toLowerCase(),
      valueText,
      valueTitle,
      valueHtml,
      countText,
      label: label || prev?.label || '',
      pending: !(label || prev?.label),
      hexHint: !msgName ? hexBucketHint(frame.address) : '',
      live: !!opts.live,
      replay: !!opts.replay,
    };
  }

  function pushFrameHistory(frame) {
    const key = frameKey(frame);
    let hist = frameHistory.get(key);
    if (!hist) {
      hist = [];
      frameHistory.set(key, hist);
    }
    const last = hist[hist.length - 1];
    if (last && last.time === frame.time && last.data === frame.data) return;
    hist.push({
      bus: frame.bus,
      address: frame.address,
      data: frame.data,
      time: frame.time,
    });
    if (hist.length > HISTORY_MAX) hist.shift();
  }

  function updateMsgStats(frame) {
    const key = frameKey(frame);
    const now = Number(frame.time) || 0;
    let stats = msgStats.get(key);
    if (!stats) {
      stats = { count: 0, hz: 0, windowStart: now, windowCount: 0 };
      msgStats.set(key, stats);
    }
    stats.count += 1;
    if (now - stats.windowStart > 2) {
      stats.windowStart = now;
      stats.windowCount = 0;
    }
    stats.windowCount += 1;
    const span = Math.max(0.05, now - stats.windowStart);
    stats.hz = stats.windowCount / span;
  }

  function findSignalForKey(key, signalName) {
    const frame = latestFrames.get(key);
    if (!frame) return null;
    const sigs = signalsByAddress.get(Number(frame.address)) || [];
    if (signalName) return sigs.find((s) => s.signal === signalName) || null;
    return sigs[0] || null;
  }

  function decodeSignalValue(frame, sig) {
    if (!sig || !frame?.data) return null;
    const data = hexToBytes(frame.data);
    if (!data) return null;
    return decodeSignal(data, sig);
  }

  function destroyPlot() {
    if (plotResizeObserver) {
      plotResizeObserver.disconnect();
      plotResizeObserver = null;
    }
    if (plotInstance) {
      plotInstance.destroy();
      plotInstance = null;
    }
    if (els.plotChart) els.plotChart.innerHTML = '';
  }

  function plotAccentStroke() {
    const accent = getComputedStyle(root || document.documentElement).getPropertyValue('--accent').trim();
    return accent || '#4ecdc4';
  }

  function valueHtmlForFrame(frame, prevHex) {
    const rawHex = frame.data ? String(frame.data).replace(/\s/g, '') : '';
    const bytes = hexToBytes(rawHex);
    if (!bytes) {
      return truncateHex(formatHexBytes(rawHex));
    }
    const prevBytes = prevHex ? hexToBytes(String(prevHex).replace(/\s/g, '')) : null;
    const parts = [];
    for (let i = 0; i < bytes.length; i++) {
      const b = bytes[i].toString(16).toUpperCase().padStart(2, '0');
      const changed = !prevBytes || i >= prevBytes.length || prevBytes[i] !== bytes[i];
      parts.push(changed ? `<span class="cab-byte-changed">${b}</span>` : b);
    }
    return parts.join(' ');
  }

  function plotSeriesId(key, signalName) {
    return `${key}::${signalName}`;
  }

  function findPlotSeries(key, signalName) {
    const id = plotSeriesId(key, signalName);
    return plotSeriesList.find((s) => s.id === id) || null;
  }

  function renderPlotChart() {
    if (!els.plotChart) return;
    const active = plotSeriesList.filter((s) => s.times.length > 0);
    const hasData = active.length > 0;
    if (els.plotEmpty) els.plotEmpty.hidden = hasData;
    if (!hasData) {
      destroyPlot();
      return;
    }
    const width = Math.max(240, els.plotChart.clientWidth || els.plotWrap?.clientWidth || 600);
    const times = active[0].times;
    const data = [times];
    const series = [{}];
    const labels = [];
    active.forEach((s, idx) => {
      data.push(s.values);
      const color = PLOT_COLORS[idx % PLOT_COLORS.length];
      series.push({ label: s.label, stroke: color, width: 2 });
      labels.push(s.label);
    });
    if (els.plotTitle) {
      els.plotTitle.textContent = labels.length > 1
        ? `${t('cabanaPlotMulti', '多信号曲线')} (${labels.length})`
        : labels[0];
    }
    const muted = getComputedStyle(root || document.documentElement).getPropertyValue('--text-muted').trim() || '#8a9aaa';
    const opts = {
      width,
      height: 180,
      fmt: (u, v) => (v == null ? '-' : Number(v).toFixed(2)),
      axes: [
        { stroke: muted, grid: { stroke: 'rgba(128,128,128,0.15)' } },
        { stroke: muted, grid: { stroke: 'rgba(128,128,128,0.15)' }, size: 52 },
      ],
      series,
    };
    if (plotInstance) {
      plotInstance.setData(data);
      return;
    }
    if (typeof uPlot === 'undefined') return;
    destroyPlot();
    plotInstance = new uPlot(opts, data, els.plotChart);
    if (!plotResizeObserver && typeof ResizeObserver !== 'undefined') {
      plotResizeObserver = new ResizeObserver(() => {
        if (!plotInstance || !els.plotChart) return;
        const w = Math.max(240, els.plotChart.clientWidth || 600);
        plotInstance.setSize({ width: w, height: 180 });
      });
      plotResizeObserver.observe(els.plotChart);
    }
  }

  function seedPlotFromHistory(key, signalName, { add = false } = {}) {
    const sig = findSignalForKey(key, signalName);
    if (!sig) {
      if (!add) plotSeriesList = [];
      destroyPlot();
      if (els.plotEmpty) els.plotEmpty.hidden = false;
      return;
    }
    plotSignalName = sig.signal;
    let series = findPlotSeries(key, sig.signal);
    if (!series) {
      if (!add) plotSeriesList = [];
      if (add && plotSeriesList.length >= 6) return;
      series = {
        id: plotSeriesId(key, sig.signal),
        key,
        signalName: sig.signal,
        label: `${sig.message || key} · ${sig.signal}`,
        times: [],
        values: [],
      };
      plotSeriesList.push(series);
    } else if (!add) {
      plotSeriesList = [series];
    }
    series.times = [];
    series.values = [];
    const hist = frameHistory.get(key) || [];
    for (const frame of hist) {
      const val = decodeSignalValue(frame, sig);
      if (val === null) continue;
      series.times.push(replayPlotTime(frame));
      series.values.push(val);
    }
    if (els.plotWrap) els.plotWrap.hidden = false;
    renderPlotChart();
  }

  function schedulePlotRender() {
    if (plotRenderScheduled) return;
    plotRenderScheduled = true;
    requestAnimationFrame(() => {
      plotRenderScheduled = false;
      renderPlotChart();
    });
  }

  function appendPlotPoint(frame) {
    if (!plotSeriesList.length) return;
    const key = frameKey(frame);
    for (const series of plotSeriesList) {
      if (series.key !== key) continue;
      const sig = findSignalForKey(series.key, series.signalName);
      if (!sig) continue;
      const val = decodeSignalValue(frame, sig);
      if (val === null) continue;
      const plotT = replayPlotTime(frame);
      const lastT = series.times[series.times.length - 1];
      if (lastT === plotT) {
        series.values[series.values.length - 1] = val;
      } else {
        series.times.push(plotT);
        series.values.push(val);
      }
      if (series.times.length > PLOT_MAX_POINTS) {
        series.times.shift();
        series.values.shift();
      }
    }
    schedulePlotRender();
  }

  function clearSelection() {
    selectedKey = null;
    plotSignalName = null;
    plotSeriesList = [];
    destroyPlot();
    if (els.detailWrap) els.detailWrap.hidden = true;
    if (els.plotWrap) els.plotWrap.hidden = true;
    if (els.detailBinary) els.detailBinary.hidden = true;
  }

  function clearAuxState() {
    frameHistory.clear();
    msgStats.clear();
    prevPayloadByKey.clear();
    clearSelection();
  }

  function renderBinaryView(frame, highlightSig) {
    if (!els.detailBinary) return;
    const bytes = hexToBytes(frame?.data);
    if (!bytes || !bytes.length) {
      els.detailBinary.hidden = true;
      return;
    }
    const bitSet = new Set();
    if (highlightSig) {
      const start = Number(highlightSig.start_bit ?? highlightSig.start) || 0;
      const len = Number(highlightSig.size ?? highlightSig.length) || 0;
      for (let b = start; b < start + len && b < 64; b++) bitSet.add(b);
    }
    const rows = [];
    for (let byteIdx = 0; byteIdx < bytes.length; byteIdx++) {
      const b = bytes[byteIdx];
      let bits = '';
      for (let bit = 7; bit >= 0; bit--) {
        const globalBit = byteIdx * 8 + bit;
        const on = (b >> bit) & 1;
        const cls = bitSet.has(globalBit) ? 'cab-bit-signal' : (on ? 'cab-bit-on' : 'cab-bit-off');
        bits += `<span class="${cls}">${on}</span>`;
      }
      rows.push(`<div class="cab-bin-row"><span class="cab-bin-idx">B${byteIdx}</span><span class="cab-bin-bits">${bits}</span></div>`);
    }
    els.detailBinary.innerHTML = `<div class="cab-bin-head">${t('cabanaBinaryView', '二进制视图')}</div>${rows.join('')}`;
    els.detailBinary.hidden = false;
  }

  function matchesSignalFilter(key, row) {
    const q = signalFilterQuery.trim();
    if (!q) return true;
    const frame = latestFrames.get(key);
    if (!frame) return false;
    const low = q.toLowerCase();
    const decoded = decodeFrame(frame);
    if (decoded.text && decoded.text.toLowerCase().includes(low)) return true;
    const cmp = q.match(/^([<>=!]+)\s*(-?\d+(?:\.\d+)?)$/);
    if (cmp && decoded.values) {
      const op = cmp[1];
      const target = Number(cmp[2]);
      return Object.values(decoded.values).some((v) => {
        const n = Number(v);
        if (!Number.isFinite(n)) return false;
        if (op === '>') return n > target;
        if (op === '>=') return n >= target;
        if (op === '<') return n < target;
        if (op === '<=') return n <= target;
        if (op === '!=') return n !== target;
        return n === target;
      });
    }
    const sigs = signalsByAddress.get(Number(frame.address)) || [];
    return sigs.some((s) => s.signal.toLowerCase().includes(low));
  }

  function isUnchangedMessage(key) {
    const hist = frameHistory.get(key);
    if (!hist || hist.length < 2) return false;
    const last = hist[hist.length - 1];
    const prev = hist[hist.length - 2];
    return last.data === prev.data;
  }

  function downloadTextFile(filename, text) {
    const blob = new Blob([text], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  function exportTableCsv() {
    const keys = getFilteredSortedKeys();
    const lines = ['time,bus,address,name,hex,count,hz,label'];
    for (const key of keys) {
      const row = tableRows.get(key);
      if (!row) continue;
      const frame = row.frame;
      const stats = msgStats.get(key);
      const esc = (s) => `"${String(s ?? '').replace(/"/g, '""')}"`;
      lines.push([
        esc(row.replay ? `+${row.relTime}s` : row.relTime),
        esc(row.bus ?? 0),
        esc(addrHex(frame.address)),
        esc(row.nameCol),
        esc(formatHexBytes(frame.data)),
        esc(stats?.count ?? 0),
        esc(stats?.hz ? stats.hz.toFixed(2) : ''),
        esc(row.label || ''),
      ].join(','));
    }
    downloadTextFile(`cabana-${panelMode}-${Date.now()}.csv`, lines.join('\n'));
  }

  function exportHistoryCsv() {
    if (!selectedKey) return;
    const hist = frameHistory.get(selectedKey) || [];
    const lines = ['time,hex,dec,decoded'];
    const esc = (s) => `"${String(s ?? '').replace(/"/g, '""')}"`;
    for (const h of hist) {
      lines.push([
        esc(formatDetailTime(h)),
        esc(formatHexBytes(h.data)),
        esc(formatDecBytes(h.data)),
        esc(decodeFrame(h).text || ''),
      ].join(','));
    }
    downloadTextFile(`cabana-history-${selectedKey.replace(':', '-')}-${Date.now()}.csv`, lines.join('\n'));
  }

  function copyFrameHex(hex, hint) {
    const text = formatHexBytes(hex);
    if (!text) return;
    navigator.clipboard?.writeText(text).catch(() => {});
    if (els.hint) els.hint.textContent = hint || t('cabanaCopiedHex', '已复制 HEX');
  }

  function copySelectedHex() {
    const frame = selectedKey ? latestFrames.get(selectedKey) : null;
    if (!frame?.data) return;
    copyFrameHex(frame.data);
  }

  function formatDetailTime(frame) {
    if (panelMode === 'replay') return `+${formatReplayRowTime(frame)}s`;
    return Number(frame.time).toFixed(2);
  }

  function renderDetailPanel() {
    if (!els.detailWrap) return;
    if (!selectedKey) {
      els.detailWrap.hidden = true;
      return;
    }
    const frame = latestFrames.get(selectedKey);
    const row = tableRows.get(selectedKey);
    if (!frame) {
      els.detailWrap.hidden = true;
      return;
    }
    els.detailWrap.hidden = false;
    const sigs = signalsByAddress.get(Number(frame.address)) || [];
    const msgName = sigs[0]?.message || addrHex(frame.address);
    const stats = msgStats.get(selectedKey);
    if (els.detailTitle) {
      els.detailTitle.textContent = `${msgName} · ${addrHex(frame.address)}`;
    }
    if (els.detailMeta) {
      const parts = [
        `bus ${frame.bus ?? 0}`,
        stats?.hz > 0 ? `${stats.hz.toFixed(1)} Hz` : null,
        stats?.count ? `${stats.count} cnt` : null,
      ].filter(Boolean);
      els.detailMeta.textContent = parts.join(' · ');
    }
    if (els.detailSignals) {
      els.detailSignals.innerHTML = '';
      if (sigs.length) {
        for (const sig of sigs) {
          const btn = document.createElement('button');
          btn.type = 'button';
          const active = findPlotSeries(selectedKey, sig.signal);
          btn.className = `cab-signal-pick${active ? ' active' : ''}`;
          const val = decodeSignalValue(frame, sig);
          const valText = val == null ? '—' : `${val.toFixed(2)}${sig.unit || ''}`;
          btn.textContent = `${sig.signal}=${valText}`;
          btn.title = t('cabanaPlotHint', '点击绘图，Shift+点击叠加');
          btn.addEventListener('click', (e) => {
            e.stopPropagation();
            plotSignalName = sig.signal;
            seedPlotFromHistory(selectedKey, sig.signal, { add: e.shiftKey });
            renderBinaryView(frame, sig);
            renderDetailPanel();
          });
          els.detailSignals.appendChild(btn);
        }
      }
    }
    if (els.detailHistoryBody) {
      els.detailHistoryBody.innerHTML = '';
      const hist = (frameHistory.get(selectedKey) || []).slice().reverse();
      if (!hist.length) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = 5;
        td.textContent = t('cabanaDetailNoHistory', '暂无历史帧');
        td.style.color = 'var(--text-muted)';
        tr.appendChild(td);
        els.detailHistoryBody.appendChild(tr);
      } else {
        for (const h of hist) {
          const tr = document.createElement('tr');
          const decoded = decodeFrame(h);
          const cells = [
            formatDetailTime(h),
            formatHexBytes(h.data),
            formatDecBytes(h.data),
            decoded.text || '—',
          ];
          cells.forEach((text, idx) => {
            const td = document.createElement('td');
            td.textContent = text;
            if (idx > 0 && idx < 3) td.className = 'mono';
            tr.appendChild(td);
          });
          const tdCopy = document.createElement('td');
          const copyBtn = document.createElement('button');
          copyBtn.type = 'button';
          copyBtn.className = 'btn small ghost cab-hist-copy';
          copyBtn.textContent = t('cabanaCopyFrame', '复制');
          copyBtn.title = t('cabanaCopyFrameHint', '复制该帧 HEX');
          copyBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            copyFrameHex(h.data, t('cabanaCopiedFrame', '已复制该帧 HEX'));
          });
          tdCopy.appendChild(copyBtn);
          tr.appendChild(tdCopy);
          els.detailHistoryBody.appendChild(tr);
        }
      }
    }
    const highlightSig = plotSignalName ? findSignalForKey(selectedKey, plotSignalName) : (sigs[0] || null);
    renderBinaryView(frame, highlightSig);
    if (row?.label && els.detailTitle) {
      els.detailTitle.textContent += ` · ${row.label}`;
    }
  }

  function selectRow(key) {
    if (!key || !latestFrames.has(key)) return;
    if (selectedKey === key) {
      clearSelection();
      scheduleVirtualRender();
      return;
    }
    selectedKey = key;
    const sigs = signalsByAddress.get(Number(latestFrames.get(key).address)) || [];
    if (sigs.length) {
      if (!plotSignalName || !sigs.some((s) => s.signal === plotSignalName)) {
        plotSignalName = sigs[0].signal;
      }
      seedPlotFromHistory(key, plotSignalName);
    } else {
      plotSignalName = null;
      plotSeriesList = [];
      destroyPlot();
      if (els.plotWrap) els.plotWrap.hidden = true;
    }
    renderDetailPanel();
    scheduleVirtualRender();
  }

  function shouldAutoLabel() {
    return autoLabelEnabled && panelMode !== 'replay';
  }

  function upsertTableRow(frame, opts = {}) {
    const key = frameKey(frame);
    latestFrames.set(key, frame);
    pushFrameHistory(frame);
    updateMsgStats(frame);
    const prev = tableRows.get(key);
    const rec = buildRowRecord(frame, opts);
    if (prev?.label && !rec.label) {
      rec.label = prev.label;
      rec.pending = false;
    }
    tableRows.set(key, rec);
    if (rec.label) explainCache.set(key, rec.label);
    if (panelMode === 'live' && tableRows.size > maxRows) pruneTableRows();
    if (selectedKey === key) {
      appendPlotPoint(frame);
      renderDetailPanel();
    }
    if (!opts.deferRender) {
      scheduleVirtualRender();
      updateLabelProgress();
    }
    if (rec.pending && shouldAutoLabel()) scheduleBulkExplainAll();
  }

  function pruneTableRows() {
    if (tableRows.size <= maxRows) return;
    const scored = Array.from(tableRows.keys()).map((k) => ({
      k,
      count: msgStats.get(k)?.count || 0,
      time: Number(tableRows.get(k)?.frame?.time) || 0,
    }));
    scored.sort((a, b) => a.count - b.count || a.time - b.time);
    const removeCount = tableRows.size - maxRows;
    for (let i = 0; i < removeCount; i++) {
      const k = scored[i].k;
      tableRows.delete(k);
      latestFrames.delete(k);
      frameHistory.delete(k);
      msgStats.delete(k);
      explainCache.delete(k);
      prevPayloadByKey.delete(k);
    }
    if (selectedKey && !tableRows.has(selectedKey)) clearSelection();
    invalidateSortCache();
  }

  function sortCacheSignature() {
    return [
      sortCol,
      sortAsc,
      filterChip,
      hideUnchanged,
      els.filter?.value || '',
      signalFilterQuery,
      tableRows.size,
    ].join('|');
  }

  function invalidateSortCache() {
    sortedKeysCache = null;
    sortedKeysCacheSig = '';
  }

  function getFilteredSortedKeys() {
    const sig = sortCacheSignature();
    if (sortedKeysCache && sortedKeysCacheSig === sig) return sortedKeysCache;
    const q = (els.filter?.value || '').toLowerCase().trim();
    let keys = Array.from(tableRows.keys());
    keys = keys.filter((k) => {
      const row = tableRows.get(k);
      if (!row) return false;
      if (q && !row.searchHay.includes(q)) return false;
      if (filterChip === 'labeled') return !!row.label;
      if (filterChip === 'unlabeled') return !row.label;
      if (filterChip !== 'all' && row.label !== filterChip) return false;
      if (hideUnchanged && isUnchangedMessage(k)) return false;
      if (!matchesSignalFilter(k, row)) return false;
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
      } else if (col === 'bus') {
        va = Number(ra?.bus) || 0;
        vb = Number(rb?.bus) || 0;
        if (va === vb) {
          va = Number(ra?.frame?.address) || 0;
          vb = Number(rb?.frame?.address) || 0;
        }
      } else if (col === 'freq') {
        va = msgStats.get(a)?.hz || 0;
        vb = msgStats.get(b)?.hz || 0;
      } else if (col === 'count') {
        va = msgStats.get(a)?.count || 0;
        vb = msgStats.get(b)?.count || 0;
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
    sortedKeysCache = keys;
    sortedKeysCacheSig = sig;
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
        tr.innerHTML = '<td class="cab-col-time"></td><td class="cab-col-bus"></td><td class="cab-col-name"></td><td class="cab-col-value"></td><td class="cab-col-count"></td><td class="cab-col-freq"></td><td class="cab-col-label"></td>';
      }
      tr.classList.toggle('selected', key === selectedKey);
      tr.children[0].textContent = row.replay ? `+${row.relTime}s` : row.relTime;
      tr.children[1].textContent = String(row.bus ?? 0);
      tr.children[2].textContent = row.nameCol;
      tr.children[2].title = row.nameCol;
      tr.children[3].innerHTML = row.valueHtml || truncateHex(row.valueText);
      tr.children[3].title = row.valueTitle || row.valueText || '';
      tr.children[4].textContent = row.countText || '0';
      tr.children[5].textContent = row.freqText || '—';
      tr.children[6].innerHTML = labelCellHtml(row.label, { pending: row.pending, hexHint: row.hexHint });
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

  function ensureVirtualSpacers() {
    if (!els.tbody) return;
    let top = els.tbody.querySelector('.cab-virtual-spacer-top');
    let bottom = els.tbody.querySelector('.cab-virtual-spacer-bottom');
    if (!top) {
      top = document.createElement('tr');
      top.className = 'cab-virtual-spacer cab-virtual-spacer-top';
      top.setAttribute('aria-hidden', 'true');
      top.innerHTML = '<td colspan="7"></td>';
      els.tbody.prepend(top);
    }
    if (!bottom) {
      bottom = document.createElement('tr');
      bottom.className = 'cab-virtual-spacer cab-virtual-spacer-bottom';
      bottom.setAttribute('aria-hidden', 'true');
      bottom.innerHTML = '<td colspan="7"></td>';
      els.tbody.append(bottom);
    }
  }

  function clearReplayDataRows() {
    if (!els.tbody) return;
    for (const tr of els.tbody.querySelectorAll('tr.cab-data-row')) tr.remove();
    ensureVirtualSpacers();
  }

  function clearTableRows() {
    tableRows.clear();
    latestFrames.clear();
    clearAuxState();
    clearReplayDataRows();
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
        invalidateSortCache();
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

  function formatHexBytes(hex) {
    const clean = String(hex || '').replace(/\s/g, '');
    if (!clean) return '';
    const parts = clean.match(/.{1,2}/g);
    if (!parts) return clean.toUpperCase();
    return parts.map((b) => b.toUpperCase()).join(' ');
  }

  function formatDecBytes(hex) {
    const bytes = hexToBytes(hex);
    if (!bytes) return '';
    return Array.from(bytes, (b) => String(b)).join(' ');
  }

  /** Human-readable CAN payload: decoded signals when DBC exists, else spaced hex. */
  function frameValuePresentation(frame, { lite = false } = {}) {
    const rawHex = frame.data ? String(frame.data) : '';
    const hexSpaced = formatHexBytes(rawHex);
    const decSpaced = formatDecBytes(rawHex);
    const tooltipParts = [];
    if (hexSpaced) tooltipParts.push(`HEX: ${hexSpaced}`);
    if (decSpaced) tooltipParts.push(`DEC: ${decSpaced}`);

    const sigs = signalsByAddress.get(Number(frame.address));
    if (sigs?.length && rawHex) {
      const decoded = lite ? decodeFrameLite(frame) : decodeFrame(frame);
      if (decoded.text) {
        return {
          display: decoded.text,
          title: tooltipParts.join('\n'),
        };
      }
    }

    return {
      display: hexSpaced || rawHex,
      title: tooltipParts.join('\n') || hexSpaced || rawHex,
    };
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
  const REPLAY_WS_MAX_MSGS_PER_FLUSH = 8;
  const REPLAY_WS_BUFFER_MAX = 128;
  const REPLAY_MAX_DOM_ROWS = 220;
  const REPLAY_MAX_KEYS_PER_FLUSH = 24;
  const REPLAY_LOADING_KEYS_PER_FLUSH = 6;
  let replayWsBuffer = [];
  let replayWsFlushTimer = null;
  let replayIndexWatchdog = null;
  const REPLAY_INDEX_TIMEOUT_MS = 120000;
  let replayLoadingUiCoalesceAt = 0;
  let dbcLoadSerial = 0;
  let loadCarToken = 0;
  let routesLoadToken = 0;
  let routesLoading = false;
  const REPLAY_LOADING_UI_MIN_MS = 450;
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
    if (els.replayPlayBtn) {
      if (on && !replayIndexReady) {
        els.replayPlayBtn.disabled = true;
        els.replayPlayBtn.textContent = t('cabanaReplayLoadingShort', '索引中…');
      } else if (!replayConnecting) {
        els.replayPlayBtn.disabled = false;
        els.replayPlayBtn.textContent = t('cabanaPlayShort', '播放');
      }
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
    if (replayIndexWatchdog != null) {
      clearTimeout(replayIndexWatchdog);
      replayIndexWatchdog = null;
    }
    setReplayLoading(false);
  }

  function armReplayIndexWatchdog() {
    if (replayIndexWatchdog != null) clearTimeout(replayIndexWatchdog);
    replayIndexWatchdog = window.setTimeout(() => {
      replayIndexWatchdog = null;
      if (!replayIndexReady && replayLoading) {
        replayIndexReady = true;
        clearReplayLoading();
        els.status.textContent = t('cabanaReplay', '回放');
        ensureVirtualSpacers();
        scheduleVirtualRender();
        if (els.hint) {
          els.hint.textContent = t('cabanaReplayIndexTimeout', '索引耗时较长，已显示已加载的数据');
        }
        if (els.replayPlayBtn) els.replayPlayBtn.disabled = false;
        if (els.replayPauseBtn) els.replayPauseBtn.disabled = false;
      }
    }, REPLAY_INDEX_TIMEOUT_MS);
  }

  function unlockReplayIndexUi(hint) {
    if (!replayIndexReady) {
      replayIndexReady = true;
      clearReplayLoading();
      scheduleReplayUiFlush();
      els.status.textContent = t('cabanaReplay', '回放');
      if (hint && els.hint) els.hint.textContent = hint;
      if (els.replayPlayBtn) els.replayPlayBtn.disabled = false;
      if (els.replayPauseBtn) els.replayPauseBtn.disabled = false;
      if (replayPlayPending && offlineWs?.readyState === WebSocket.OPEN) {
        replayPlayPending = false;
        replayPaused = false;
        sendReplayControl({ action: 'play' });
      }
    }
    ensureVirtualSpacers();
    scheduleVirtualRender();
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

  function clearReplayWsState() {
    if (replayWsFlushTimer != null) {
      clearTimeout(replayWsFlushTimer);
      replayWsFlushTimer = null;
    }
    replayWsBuffer = [];
  }

  function flushReplayUiNow() {
    replayUiFlushScheduled = false;
    lastReplayUiPaintAt = 0;
    flushReplayUi(true);
  }

  function scheduleReplayUiFlush() {
    if (replayUiFlushScheduled) return;
    replayUiFlushScheduled = true;
    requestAnimationFrame(() => flushReplayUi(false));
  }

  function flushReplayUi(force = false) {
    replayUiFlushScheduled = false;
    if (!els.tbody || (!replayDirtyKeys.size && !replayPendingByKey.size)) return;
    const now = performance.now();
    if (!force && tableRows.size > 0 && now - lastReplayUiPaintAt < REPLAY_UI_MIN_INTERVAL_MS) {
      scheduleReplayUiFlush();
      return;
    }
    lastReplayUiPaintAt = now;

    const keys = Array.from(replayDirtyKeys);
    replayDirtyKeys.clear();
    const maxKeys = replayLoading ? REPLAY_LOADING_KEYS_PER_FLUSH : REPLAY_MAX_KEYS_PER_FLUSH;
    const slice = keys.length > maxKeys ? keys.slice(0, maxKeys) : keys;
    if (keys.length > maxKeys) {
      for (const key of keys.slice(maxKeys)) replayDirtyKeys.add(key);
      scheduleReplayUiFlush();
    }
    if (!slice.length) return;

    for (const key of slice) {
      const frame = replayPendingByKey.get(key);
      if (!frame) continue;
      try {
        upsertTableRow(frame, { replay: true, deferRender: true });
      } catch (e) {
        console.error('cabana replay row', e, frame);
      }
    }
    scheduleVirtualRender();
    updateLabelProgress();
    scheduleAiButtonsUpdate();
  }

  function scheduleAiButtonsUpdate() {
    const now = performance.now();
    if (now - lastAiButtonsAt < 400) return;
    lastAiButtonsAt = now;
    updateAiButtons();
  }

  function appendMergedFrames(target, frames) {
    if (!Array.isArray(frames) || !frames.length) return;
    const limit = Math.min(frames.length, REPLAY_MAX_FRAMES_PER_MSG * 4);
    for (let i = 0; i < limit; i++) target.push(frames[i]);
  }

  function flushReplayWsBuffer() {
    replayWsFlushTimer = null;
    if (!replayWsBuffer.length) return;
    let processed = 0;
    let mergedFrames = [];
    let mergedPreview = false;
    let mergedProgress = null;

    const flushMergedCan = () => {
      if (mergedFrames.length) {
        handleOfflineWsMessage({
          type: 'can',
          frames: mergedFrames,
          progress: mergedProgress,
          preview: mergedPreview || undefined,
        });
      } else if (typeof mergedProgress === 'number') {
        handleOfflineWsMessage({ type: 'progress', progress: mergedProgress });
      }
      mergedFrames = [];
      mergedPreview = false;
      mergedProgress = null;
    };

    while (replayWsBuffer.length && processed < REPLAY_WS_MAX_MSGS_PER_FLUSH) {
      const msg = replayWsBuffer.shift();
      processed += 1;
      try {
        if (msg.type === 'can') {
          if (typeof msg.progress === 'number') mergedProgress = msg.progress;
          if (msg.preview) mergedPreview = true;
          appendMergedFrames(mergedFrames, msg.frames);
          continue;
        }
        if (msg.type === 'progress' && typeof msg.progress === 'number') {
          mergedProgress = msg.progress;
          continue;
        }
        flushMergedCan();
        handleOfflineWsMessage(msg);
      } catch (e) {
        console.error('cabana replay ws', e);
      }
    }
    flushMergedCan();
    if (replayWsBuffer.length) {
      replayWsFlushTimer = window.setTimeout(flushReplayWsBuffer, replayIndexReady ? 16 : 32);
    }
  }

  function queueReplayWsMessage(msg) {
    if (replayWsBuffer.length >= REPLAY_WS_BUFFER_MAX) {
      replayWsBuffer.shift();
    }
    replayWsBuffer.push(msg);
    if (replayWsFlushTimer != null) return;
    replayWsFlushTimer = window.setTimeout(flushReplayWsBuffer, replayIndexReady ? 16 : 0);
  }

  function dispatchOfflineWsRaw(raw) {
    let msg;
    try {
      msg = typeof raw === 'string' ? JSON.parse(raw) : raw;
    } catch (e) {
      console.error('cabana replay ws parse', e);
      return;
    }
    const type = msg?.type;
    if (type === 'metadata' || type === 'error' || type === 'done' || type === 'seeked' || type === 'metadata_update') {
      handleOfflineWsMessage(msg);
      return;
    }
    if (type === 'loading') {
      const phase = msg.phase;
      const critical = phase === 'start' || phase === 'ready' || phase === 'cache_hit'
        || phase === 'fast_qlog' || phase === 'fast_rlog' || phase === 'parallel' || phase === 'fallback_rlog';
      if (critical) {
        handleOfflineWsMessage(msg);
        return;
      }
      const now = performance.now();
      if (now - replayLoadingUiCoalesceAt >= REPLAY_LOADING_UI_MIN_MS) {
        replayLoadingUiCoalesceAt = now;
        handleOfflineWsMessage(msg);
      }
      return;
    }
    if (type === 'can' || type === 'progress') {
      queueReplayWsMessage(msg);
      return;
    }
    handleOfflineWsMessage(msg);
  }

  function applyReplayCanBatch(frames, { immediate = false } = {}) {
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
    if (immediate || tableRows.size === 0) {
      if (replayLoading) scheduleReplayUiFlush();
      else flushReplayUiNow();
    } else {
      scheduleReplayUiFlush();
    }
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
    if (replayDuration > 0) replayProgress = Math.min(replayProgress, replayDuration);
    const now = performance.now();
    if (now - lastProgressPaintAt < 50) return;
    lastProgressPaintAt = now;
    updateProgressUI();
    scheduleVideoThumbnail();
  }

  function revokeThumbObjectUrl() {
    if (thumbObjectUrl) {
      URL.revokeObjectURL(thumbObjectUrl);
      thumbObjectUrl = null;
    }
  }

  function setVideoPlaceholder(text) {
    if (!els.videoPlaceholder) return;
    els.videoPlaceholder.textContent = text || '';
    els.videoPlaceholder.hidden = false;
    if (els.videoImg) els.videoImg.hidden = true;
  }

  function showVideoPreviewImage(blob) {
    if (!els.videoImg) return;
    revokeThumbObjectUrl();
    thumbObjectUrl = URL.createObjectURL(blob);
    els.videoImg.src = thumbObjectUrl;
    els.videoImg.hidden = false;
    if (els.videoPlaceholder) els.videoPlaceholder.hidden = true;
  }

  function scheduleVideoThumbnail({ immediate = false } = {}) {
    if (!videoPreviewEnabled || !hasQcamera || !replayRoute || panelMode !== 'replay') return;
    if (thumbDebounceTimer) clearTimeout(thumbDebounceTimer);
    const delay = immediate ? 0 : (replayPaused ? 120 : 350);
    thumbDebounceTimer = window.setTimeout(() => {
      thumbDebounceTimer = null;
      fetchVideoThumbnail(replayProgress).catch(console.error);
    }, delay);
  }

  async function fetchVideoThumbnail(relSec) {
    if (!videoPreviewEnabled || !hasQcamera || !replayRoute) return;
    const key = `${replayRoute}:${relSec.toFixed(1)}`;
    if (key === lastThumbKey) return;
    if (thumbAbort) thumbAbort.abort();
    thumbAbort = new AbortController();
    setVideoPlaceholder(t('cabanaVideoLoading', '加载预览…'));
    try {
      const url = `/api/cabana/route/${encodeURIComponent(replayRoute)}/thumbnail?time=${encodeURIComponent(relSec.toFixed(2))}`;
      const res = await fetch(url, { signal: thumbAbort.signal });
      if (!res.ok) {
        setVideoPlaceholder(t('cabanaVideoNoFrame', '该时刻无预览帧'));
        return;
      }
      const blob = await res.blob();
      showVideoPreviewImage(blob);
      lastThumbKey = key;
    } catch (e) {
      if (e?.name === 'AbortError') return;
      setVideoPlaceholder(t('cabanaVideoError', '预览加载失败'));
    } finally {
      thumbAbort = null;
    }
  }

  async function refreshRouteMedia(route) {
    hasQcamera = false;
    if (els.videoToggle) {
      els.videoToggle.disabled = true;
      els.videoToggle.checked = false;
    }
    videoPreviewEnabled = false;
    if (els.videoPreview) els.videoPreview.hidden = true;
    if (!route) return;
    try {
      const data = await api('GET', `/api/cabana/route/${encodeURIComponent(route)}/media`, null, { timeoutMs: 8000 });
      hasQcamera = !!(data.ok && data.segments?.some((s) => s.type === 'qcamera'));
    } catch {
      hasQcamera = false;
    }
    if (els.videoToggle) {
      els.videoToggle.disabled = !hasQcamera;
      els.videoToggle.title = hasQcamera
        ? t('cabanaVideoPreviewHint', '低清 qcamera 缩略图，与 CAN 日志时间对齐')
        : t('cabanaNoVideo', '此路线无 qcamera.ts，仅 CAN 回放');
    }
  }

  function setVideoPreviewEnabled(on) {
    videoPreviewEnabled = !!on && hasQcamera;
    if (els.videoToggle) els.videoToggle.checked = videoPreviewEnabled;
    if (els.videoPreview) els.videoPreview.hidden = !videoPreviewEnabled;
    if (!videoPreviewEnabled) {
      revokeThumbObjectUrl();
      lastThumbKey = '';
      if (thumbAbort) thumbAbort.abort();
      return;
    }
    lastThumbKey = '';
    scheduleVideoThumbnail({ immediate: true });
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
    if (!shouldAutoLabel()) return;
    if (panelMode === 'replay' && (replayLoading || replayConnecting || !replayIndexReady)) return;
    if (bulkExplainTimer) clearTimeout(bulkExplainTimer);
    bulkExplainTimer = window.setTimeout(() => {
      bulkExplainTimer = null;
      runBulkExplainAll().catch(console.error);
    }, panelMode === 'replay' ? 480 : 160);
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
    if (!shouldAutoLabel()) return;
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
    if (els.autoLabelBtn) {
      els.autoLabelBtn.disabled = true;
      els.autoLabelBtn.classList.add('is-loading');
    }
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
      if (els.autoLabelBtn) {
        els.autoLabelBtn.disabled = false;
        els.autoLabelBtn.classList.remove('is-loading');
      }
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

  function replayPlotTime(frame) {
    const t = Number(frame?.time) || 0;
    if (panelMode === 'replay' && replayStartMono > 0) {
      return Math.max(0, t - replayStartMono);
    }
    return t;
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
    const serial = ++dbcLoadSerial;
    const deferTableRebuild = replayLoading || replayConnecting;
    const data = await api('GET', `/api/cabana/dbc/${encodeURIComponent(name)}`, null, { timeoutMs: 20000 });
    if (serial !== dbcLoadSerial) return;
    if (!data.ok) {
      if (els.metaBar) els.metaBar.textContent = data.error || t('cabanaDbcLoadFailed', 'DBC load failed');
      return;
    }
    dbcName = name;
    serverLabelStore = {};
    if (!deferTableRebuild) await preloadServerLabelCache();
    if (serial !== dbcLoadSerial) return;
    if (els.dbcSearch) els.dbcSearch.value = name;
    signals = data.signals || [];
    buildSignalIndex();
    if (els.metaBar) {
      els.metaBar.textContent = `${t('cabanaDbcLoaded', '已加载')} ${name} · ${signals.length} ${t('cabanaSignals', '个信号')}`;
    }
    if (dbcPickerOpen) renderDbcList(filterDbcNames(els.dbcSearch?.value || ''));
    if (deferTableRebuild) {
      updateAiButtons();
      return;
    }
    for (const [key, row] of tableRows) {
      const frame = latestFrames.get(key);
      if (!frame) continue;
      const rec = buildRowRecord(frame, { live: row.live, replay: row.replay });
      rec.label = row.label;
      rec.pending = row.pending;
      tableRows.set(key, rec);
    }
    if (selectedKey) selectRow(selectedKey);
    updateAiButtons();
    if (shouldAutoLabel()) scheduleBulkExplainAll();
    scheduleVirtualRender();
    preloadServerLabelCache().catch(() => {});
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
        await selectDbc(name, { manual: true });
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

  function loadPinnedDbc() {
    try {
      const v = sessionStorage.getItem(DBC_PIN_KEY);
      return v && typeof v === 'string' ? v : '';
    } catch (_) {
      return '';
    }
  }

  function pinDbc(name) {
    if (!name) return;
    dbcUserPinned = true;
    try {
      sessionStorage.setItem(DBC_PIN_KEY, name);
    } catch (_) { /* ignore */ }
  }

  function clearDbcPin() {
    dbcUserPinned = false;
    try {
      sessionStorage.removeItem(DBC_PIN_KEY);
    } catch (_) { /* ignore */ }
  }

  function scoreDbcEntry(name, item, car) {
    if (!name) return 0;
    const fp = (car?.carFingerprint || '').toLowerCase();
    const brand = (car?.brand || '').toLowerCase();
    const search = `${item?.searchText || ''} ${name}`.toLowerCase();
    let score = 0;
    const fps = item?.fingerprints || [];
    if (fp && fps.some((f) => String(f).toLowerCase() === fp)) score += 120;
    if (fp && search.includes(fp)) score += 60;
    if (brand && search.includes(brand)) score += 25;
    if (fp) {
      for (const token of fp.split(/[^a-z0-9]+/i).filter((t) => t.length >= 3)) {
        if (search.includes(token)) score += token.length;
      }
    }
    if (/_pt|_pt_generated/.test(name)) score += 8;
    if (name.toLowerCase() === 'esr' && !/esr/i.test(fp)) score -= 40;
    return score;
  }

  function resolvePreferredDbc(catalog, { suggested, car, dbcDict } = {}) {
    const names = [];
    for (const item of catalog || []) {
      const n = typeof item === 'string' ? item : item?.name;
      if (n) names.push(n);
    }
    if (!names.length) return '';

    if (suggested && names.includes(suggested)) return suggested;

    if (dbcDict && typeof dbcDict === 'object') {
      for (const val of Object.values(dbcDict)) {
        if (val && names.includes(val)) return val;
      }
    }

    const pinned = dbcUserPinned ? loadPinnedDbc() : '';
    if (pinned && names.includes(pinned)) return pinned;

    if (dbcName && names.includes(dbcName)) return dbcName;

    let best = '';
    let bestScore = 0;
    for (const item of catalog) {
      const name = typeof item === 'string' ? item : item?.name;
      if (!name) continue;
      const s = scoreDbcEntry(name, typeof item === 'string' ? { name, searchText: name } : item, car);
      if (s > bestScore) {
        bestScore = s;
        best = name;
      }
    }
    if (best && bestScore > 0) return best;

    const pt = names.find((n) => /_pt|_pt_generated/.test(n));
    return pt || '';
  }

  async function selectDbc(name, { manual = false } = {}) {
    if (!name || !dbcNames.includes(name)) return;
    if (manual) pinDbc(name);
    await loadDbc(name);
  }

  async function setDbcCatalog(catalog, preferred, { force = false, car = null, dbcDict = null } = {}) {
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

    const pinned = loadPinnedDbc();
    if (pinned) dbcUserPinned = true;

    const carCtx = car || lastCar;
    let pref = '';
    if (force) {
      pref = preferred && dbcNames.includes(preferred) ? preferred : '';
    } else if (dbcUserPinned && pinned && dbcNames.includes(pinned)) {
      pref = pinned;
    } else {
      pref = resolvePreferredDbc(items, {
        suggested: preferred,
        car: carCtx,
        dbcDict: dbcDict || undefined,
      });
      if (!pref && preferred && dbcNames.includes(preferred)) pref = preferred;
    }

    if (pref && pref === dbcName && signals.length) {
      if (els.dbcSearch) els.dbcSearch.value = dbcName;
      return;
    }
    if (pref) await selectDbc(pref);
    else if (els.dbcSearch) els.dbcSearch.value = dbcName || '';
  }

  function onDbcSearchInput() {
    if (dbcSearchTimer) clearTimeout(dbcSearchTimer);
    dbcSearchTimer = setTimeout(() => {
      dbcSearchTimer = null;
      renderDbcList(filterDbcNames(els.dbcSearch?.value || ''));
      openDbcPicker();
    }, 200);
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
    await selectDbc(matches[0], { manual: true });
    closeDbcPicker();
    els.dbcSearch?.blur();
  }

  async function loadCar(routeName) {
    const token = ++loadCarToken;
    const route = (routeName || '').trim();
    const carPath = route
      ? `/api/cabana/car?route=${encodeURIComponent(route)}`
      : '/api/cabana/car';
    const reqOpts = { timeoutMs: 15000 };
    if (els.metaBar) els.metaBar.textContent = t('cabanaCarLoading', '加载中…');
    try {
      const [dbcs, data] = await Promise.all([
        api('GET', '/api/cabana/dbcs?quick=1', null, reqOpts),
        api('GET', carPath, null, reqOpts),
      ]);
      if (token !== loadCarToken) return;
      const catalog = dbcs.ok
        ? (dbcs.catalog || (dbcs.dbcs || []).map((name) => ({ name, searchText: name })))
        : [];
      if (!dbcs.ok && els.metaBar) {
        const err = dbcs.error || t('cabanaDbcLoadFailed', 'DBC load failed');
        els.metaBar.textContent = `${err} · ${t('cabanaOfflineHint', '可手动选择 DBC')}`;
      }
      const car = data.car || null;
      const suggested = data.suggested_dbc || '';
      const dbcDict = data.dbc_dict || {};
      const fp = car?.carFingerprint || '';
      const fingerprintChanged = fp && fp !== lastCarFingerprint;
      if (fp) {
        lastCarFingerprint = fp;
        lastCar = car;
      }

      if (!data.ok) {
        const hint = data.hint || data.error || t('cabanaNoCarParams', '无车型信息');
        if (els.metaBar) {
          els.metaBar.textContent = `${hint} · ${t('cabanaOfflineHint', '可手动选择 DBC')}`;
        }
        const pref = resolvePreferredDbc(catalog, { suggested, car, dbcDict });
        await setDbcCatalog(catalog, pref, { force: Boolean(pref && fingerprintChanged), car, dbcDict });
        return;
      }
      const src = data.source || car?.source || 'device';
      if (els.metaBar) {
        const routeHint = src === 'route' && car?.route ? ` · ${car.route}` : '';
        els.metaBar.textContent = `${car.brand} · ${car.carFingerprint}${routeHint}`;
      }
      const pref = resolvePreferredDbc(catalog, { suggested, car, dbcDict });
      await setDbcCatalog(catalog, pref, {
        force: fingerprintChanged && !dbcUserPinned,
        car,
        dbcDict,
      });
    } catch (e) {
      if (token !== loadCarToken) return;
      console.error('loadCar failed', e);
      if (els.metaBar) {
        els.metaBar.textContent = `${t('cabanaDbcLoadFailed', 'DBC load failed')} · ${t('cabanaOfflineHint', '可手动选择 DBC')}`;
      }
    }
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
    clearReplayWsState();
    revokeThumbObjectUrl();
    lastThumbKey = '';
    videoPreviewEnabled = false;
    if (els.videoToggle) els.videoToggle.checked = false;
    if (els.videoPreview) els.videoPreview.hidden = true;
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
    const token = ++routesLoadToken;
    routesLoading = true;
    if (els.metaBar) els.metaBar.textContent = t('cabanaCarLoading', '加载中…');
    try {
      const data = await api('GET', '/api/cabana/routes', null, { timeoutMs: 20000 });
      if (token !== routesLoadToken) return;
      if (!els.routeSelect) return;
      els.routeSelect.innerHTML = '';
      if (!data.ok || !data.routes?.length) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = t('cabanaNoRoutes', '无可用路线');
        els.routeSelect.appendChild(opt);
        if (els.metaBar) {
          els.metaBar.textContent = `${t('cabanaNoRoutes', '无可用路线')} · ${t('cabanaOfflineHint', '可手动选择 DBC')}`;
        }
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
      if (replayRoute) {
        await refreshRouteMedia(replayRoute);
        if (token !== routesLoadToken) return;
        await loadCar(replayRoute);
      }
    } finally {
      if (token === routesLoadToken) routesLoading = false;
    }
  }

  function connectReplay() {
    const route = els.routeSelect?.value;
    if (!route) {
      els.hint.textContent = t('cabanaSelectRoute', '请先选择路线');
      return;
    }

    const wsState = offlineWs?.readyState;
    if (wsState === WebSocket.OPEN) {
      replayPaused = false;
      replayPlayPending = true;
      if (els.replayPlayBtn) els.replayPlayBtn.disabled = !replayIndexReady;
      if (replayIndexReady) {
        replayPlayPending = false;
        sendReplayControl({ action: 'play' });
        if (els.replayPlayBtn) els.replayPlayBtn.disabled = false;
      } else {
        els.hint.textContent = t('cabanaReplayIndexing', '正在索引，请稍候…');
      }
      return;
    }
    if (wsState === WebSocket.CONNECTING || replayConnecting) {
      replayPaused = false;
      replayPlayPending = true;
      if (els.replayPlayBtn) els.replayPlayBtn.disabled = true;
      els.hint.textContent = t('cabanaReplayConnecting', '正在连接回放…');
      return;
    }

    replayRoute = route;
    refreshRouteMedia(route).catch(console.error);
    replayPaused = false;
    replayPlayPending = true;
    if (offlineWs) {
      offlineWs.onclose = null;
      offlineWs.onmessage = null;
      offlineWs.close();
      offlineWs = null;
    }
    replayConnecting = true;
    replayIndexReady = false;
    clearReplayWsState();
    resetBulkExplain();
    resetReplayQueue();
    tableRows.clear();
    clearAuxState();
    latestFrames.clear();
    clearReplayDataRows();
    setReplayLoading(true, t('cabanaReplayLoadingStart', '正在打开日志…'));
    armReplayIndexWatchdog();
    if (els.replayPlayBtn) els.replayPlayBtn.disabled = true;
    if (els.replayPauseBtn) els.replayPauseBtn.disabled = true;

    const speed = parseFloat(els.replaySpeed?.value || '1') || 1;
    replaySpeed = speed;
    const qs = new URLSearchParams({
      route,
      speed: String(speed),
      start_time: String(Math.max(0, replayProgress || 0)),
      autoplay: '0',
    });
    if (els.replayFull?.checked) qs.set('full', '1');
    offlineWs = new WebSocket(wsUrl(`/api/cabana/offline/ws?${qs}`));

    offlineWs.onopen = () => {
      replayConnecting = false;
      els.status.textContent = t('cabanaReplayLoading', '索引中');
      els.status.className = 'cab-status live';
      replayPaused = true;
    };

    offlineWs.onerror = () => {
      replayConnecting = false;
      replayPlayPending = false;
      replayIndexReady = false;
      clearReplayLoading();
      if (els.replayPlayBtn) els.replayPlayBtn.disabled = false;
      els.hint.textContent = t('cabanaReplayError', '回放失败');
    };

    offlineWs.onmessage = (ev) => {
      dispatchOfflineWsRaw(ev.data);
    };

    offlineWs.onclose = () => {
      offlineWs = null;
      replayConnecting = false;
      replayPlayPending = false;
      clearReplayWsState();
      clearReplayLoading();
      if (els.replayPlayBtn) els.replayPlayBtn.disabled = false;
      if (els.replayPauseBtn) els.replayPauseBtn.disabled = false;
      if (!replayIndexReady && panelMode === 'replay') {
        els.hint.textContent = t('cabanaReplayError', '回放失败');
      } else if (panelMode === 'replay' && !replayPaused) {
        els.status.textContent = t('cabanaOffline', '离线');
        els.status.className = 'cab-status';
      }
    };
  }

  function handleOfflineWsMessage(msg) {
      if (msg.type === 'loading') {
        if (!replayIndexReady) {
          setReplayLoading(true, formatLoadingText(msg));
          if (msg.phase === 'ready') {
            const n = msg.can_frames != null ? Number(msg.can_frames) : 0;
            if (n > 0) {
              unlockReplayIndexUi();
            }
          }
        }
        return;
      }
      if (msg.type === 'progress' && typeof msg.progress === 'number') {
        updateReplayProgress(msg.progress);
        return;
      }
      if (msg.type === 'metadata_update') {
        replayDuration = msg.duration || replayDuration;
        updateProgressUI();
        return;
      }
      if (msg.type === 'metadata') {
        replayMeta = msg;
        replayDuration = msg.duration || 0;
        replayStartMono = msg.start_time || 0;
        replayProgress = 0;
        lastProgressPaintAt = 0;
        if (Array.isArray(msg.init_frames) && msg.init_frames.length) {
          applyReplayCanBatch(msg.init_frames, { immediate: false });
        }
        clearReplayWsState();
        updateProgressUI();
        unlockReplayIndexUi();
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
        return;
      }
      if (msg.type === 'can') {
        if (typeof msg.progress === 'number') {
          updateReplayProgress(msg.progress);
        }
        if (Array.isArray(msg.frames) && msg.frames.length) {
          applyReplayCanBatch(msg.frames, { immediate: !!msg.preview });
          if (msg.preview && !replayIndexReady) {
            unlockReplayIndexUi(t('cabanaReplayFromCache', '已从缓存加载 CAN，可直接播放'));
          }
        } else if (replayLoading) {
          clearReplayLoading();
        }
        return;
      }
      if (msg.type === 'seeked' && typeof msg.time === 'number') {
        resetReplayQueue();
        clearTableRows();
        replayProgress = msg.time;
        lastProgressPaintAt = 0;
        updateProgressUI();
        scheduleVideoThumbnail({ immediate: true });
        return;
      }
      if (msg.type === 'done') {
        replayPaused = true;
        replayIndexReady = true;
        if (els.replayPlayBtn) els.replayPlayBtn.disabled = false;
        if (els.replayPauseBtn) els.replayPauseBtn.disabled = true;
        els.hint.textContent = t('cabanaReplayDone', '回放结束 · 可再次播放');
        if (shouldAutoLabel()) scheduleBulkExplainAll();
        return;
      }
      if (msg.type === 'error') {
        replayIndexReady = false;
        clearReplayLoading();
        if (els.replayPlayBtn) els.replayPlayBtn.disabled = false;
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
    if (els.connectBtn) els.connectBtn.disabled = true;
    if (els.status) {
      els.status.textContent = t('cabanaConnecting', '连接中…');
      els.status.className = 'cab-status connecting';
    }
    if (els.hint) els.hint.textContent = '';
    ws = new WebSocket(wsUrl('/api/cabana/ws'));
    ws.onopen = () => {
      liveConnectedAt = Date.now();
      liveFrameBatches = 0;
      els.status.textContent = t('cabanaLive', '实时');
      els.status.className = 'cab-status live';
      if (els.connectBtn) els.connectBtn.disabled = false;
      updateAiButtons();
    };
    ws.onmessage = (ev) => {
      let msg;
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (msg.type === 'error') {
        const hint = msg.code === 'live_can_unavailable'
          ? t('cabanaLiveUnavailable', '实时 CAN 需要 comma 设备与 cereal 进程；PC 预览请切换到「回放」模式。')
          : (msg.error || msg.message || t('cabanaWsFailed', '连接失败'));
        if (els.hint) els.hint.textContent = hint;
        if (els.status) {
          els.status.textContent = t('cabanaOffline', '离线');
          els.status.className = 'cab-status';
        }
        disconnectLive();
        if (els.connectBtn) els.connectBtn.disabled = false;
        updateAiButtons();
        return;
      }
      if (msg.type === 'can') enqueueCanFrames(msg.frames);
    };
    ws.onerror = () => {
      if (els.hint) els.hint.textContent = t('cabanaWsFailed', 'WebSocket 连接失败');
      if (els.status) {
        els.status.textContent = t('cabanaOffline', '离线');
        els.status.className = 'cab-status';
      }
      if (els.connectBtn) els.connectBtn.disabled = false;
    };
    ws.onclose = () => {
      ws = null;
      liveConnectedAt = 0;
      liveFrameBatches = 0;
      if (els.connectBtn) els.connectBtn.disabled = false;
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
    if (els.deepAnalyzeBtn) {
      els.deepAnalyzeBtn.disabled = true;
      els.deepAnalyzeBtn.classList.add('is-loading');
    }
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
      if (els.deepAnalyzeBtn) {
        els.deepAnalyzeBtn.disabled = false;
        els.deepAnalyzeBtn.classList.remove('is-loading');
      }
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
    if (autoLabelEnabled) {
      if (panelMode === 'replay' && els.hint) {
        els.hint.textContent = t('cabanaReplayAutoLabelWarn', '回放自动标注较慢，建议先播放查看');
      }
      scheduleBulkExplainAll();
    }
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
    invalidateSortCache();
    scheduleVirtualRender();
  }

  function onCabanaKeydown(e) {
    const modal = document.getElementById('cabanaModal');
    if (!modal || modal.hidden) return;
    if (e.key === 'Escape' && selectedKey) {
      e.preventDefault();
      clearSelection();
      renderDetailPanel();
      scheduleVirtualRender();
      return;
    }
    if (e.target?.matches('input, textarea, select')) return;
    if (panelMode !== 'replay') return;
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
    if (els.thBus) els.thBus.textContent = t('cabanaThBus', '总线');
    if (els.thName) els.thName.textContent = t('cabanaThNamePlain', '报文');
    if (els.thValue) els.thValue.textContent = t('cabanaThValue', '当前值');
    if (els.thCount) els.thCount.textContent = t('cabanaThCount', 'Count');
    if (els.thFreq) els.thFreq.textContent = t('cabanaThFreq', 'Hz');
    if (els.thExplain) els.thExplain.textContent = t('cabanaThFunction', '功能');
    if (els.signalFilter) {
      els.signalFilter.placeholder = t('cabanaSignalFilterPlaceholder', '信号/物理值过滤…');
      els.signalFilter.title = t('cabanaSignalFilterTitle', '例如 BRK 或 > 0');
    }
    if (els.hideUnchangedLabel) {
      els.hideUnchangedLabel.textContent = t('cabanaHideUnchanged', '隐藏不变');
    }
    if (els.exportCsvBtn) els.exportCsvBtn.textContent = t('cabanaExportCsv', '导出表格 CSV');
    if (els.copyHexBtn) els.copyHexBtn.textContent = t('cabanaCopyHex', '复制 HEX');
    if (els.exportHistCsvBtn) els.exportHistCsvBtn.textContent = t('cabanaExportHistCsv', '导出历史 CSV');
    if (els.histThCopy) els.histThCopy.textContent = t('cabanaHistThCopy', '操作');
    if (els.plotTitle) els.plotTitle.textContent = t('cabanaPlotTitle', '信号曲线');
    if (els.plotClear) els.plotClear.textContent = t('cabanaPlotClear', '清空曲线');
    if (els.plotEmpty) {
      els.plotEmpty.textContent = t('cabanaPlotEmpty', '点击表格行选择报文，播放或连接后将显示信号曲线');
    }
    if (els.detailTitle) els.detailTitle.textContent = t('cabanaDetailTitle', '报文详情');
    if (els.detailHistoryHead) els.detailHistoryHead.textContent = t('cabanaDetailHistory', '最近帧');
    if (els.histThTime) els.histThTime.textContent = t('cabanaThTime', '时间');
    if (els.histThHex) els.histThHex.textContent = t('cabanaThHex', 'HEX');
    if (els.histThDec) els.histThDec.textContent = 'DEC';
    if (els.histThDecoded) els.histThDecoded.textContent = t('cabanaThSignals', '解码');
    if (els.videoToggleLabel) els.videoToggleLabel.textContent = t('cabanaVideoPreview', '路况预览');
    if (els.progress) {
      els.progress.title = t('cabanaReplayProgressHint', '拖动定位 CAN 日志时间（非视频）');
    }
    if (els.replaySpeed) {
      els.replaySpeed.title = t('cabanaReplaySpeedHint', 'CAN 数据回放倍速');
    }
    if (els.hint) els.hint.textContent = panelMode === 'replay'
      ? t('cabanaReplayPanelHint3', '点击报文查看历史与曲线；空格播放/暂停，←→ 快进')
      : t('cabanaLivePanelHint3', '点击报文查看历史与曲线；连接后自动标注功能');
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
    els.signalFilter = $('#cabanaSignalFilter');
    els.hideUnchanged = $('#cabanaHideUnchanged');
    els.hideUnchangedLabel = $('#cabanaHideUnchangedLabel');
    els.exportCsvBtn = $('#cabanaExportCsvBtn');
    els.tbody = $('#cabanaTableBody') || $('#cabanaTable tbody');
    els.status = $('#cabanaStatus');
    els.title = $('#cabanaPanelTitle');
    els.hint = $('#cabanaPanelHint');
    els.thTime = $('#cabThTime');
    els.thBus = $('#cabThBus');
    els.thName = $('#cabThName');
    els.thValue = $('#cabThValue');
    els.thCount = $('#cabThCount');
    els.thFreq = $('#cabThFreq');
    els.thExplain = $('#cabThExplain');
    els.plotWrap = $('#cabanaPlotWrap');
    els.plotTitle = $('#cabanaPlotTitle');
    els.plotChart = $('#cabanaPlotChart');
    els.plotEmpty = $('#cabanaPlotEmpty');
    els.plotClear = $('#cabanaPlotClear');
    els.detailWrap = $('#cabanaDetailWrap');
    els.detailTitle = $('#cabanaDetailTitle');
    els.detailMeta = $('#cabanaDetailMeta');
    els.detailSignals = $('#cabanaDetailSignals');
    els.detailHistoryHead = $('#cabanaDetailHistoryHead');
    els.detailHistoryBody = $('#cabanaDetailHistoryBody');
    els.detailBinary = $('#cabanaDetailBinary');
    els.copyHexBtn = $('#cabanaCopyHexBtn');
    els.exportHistCsvBtn = $('#cabanaExportHistCsvBtn');
    els.detailClose = $('#cabanaDetailClose');
    els.histThTime = $('#cabanaHistThTime');
    els.histThHex = $('#cabanaHistThHex');
    els.histThDec = $('#cabanaHistThDec');
    els.histThDecoded = $('#cabanaHistThDecoded');
    els.histThCopy = $('#cabanaHistThCopy');
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
    els.videoToggle = $('#cabanaVideoToggle');
    els.videoToggleLabel = $('#cabanaVideoToggleLabel');
    els.videoPreview = $('#cabanaVideoPreview');
    els.videoImg = $('#cabanaVideoImg');
    els.videoPlaceholder = $('#cabanaVideoPlaceholder');

    renderFilterChips();
    root?.querySelectorAll('#cabanaTable th[data-sort]').forEach((th) => {
      th.addEventListener('click', () => onSortHeaderClick(th.dataset.sort));
    });
    els.tableWrap?.addEventListener('scroll', () => scheduleVirtualRender(), { passive: true });
    els.tbody?.addEventListener('click', (e) => {
      const tr = e.target.closest('tr.cab-data-row');
      if (!tr?.dataset.key) return;
      selectRow(tr.dataset.key);
    });
    els.filter?.addEventListener('input', () => {
      invalidateSortCache();
      scheduleVirtualRender();
    });
    els.signalFilter?.addEventListener('input', () => {
      signalFilterQuery = els.signalFilter?.value || '';
      invalidateSortCache();
      scheduleVirtualRender();
    });
    els.hideUnchanged?.addEventListener('change', () => {
      hideUnchanged = !!els.hideUnchanged?.checked;
      invalidateSortCache();
      scheduleVirtualRender();
    });
    els.exportCsvBtn?.addEventListener('click', exportTableCsv);
    els.copyHexBtn?.addEventListener('click', copySelectedHex);
    els.exportHistCsvBtn?.addEventListener('click', exportHistoryCsv);
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
      refreshRouteMedia(replayRoute).catch(console.error);
      loadCar(replayRoute).catch(console.error);
      clearTableRows();
      updateProgressUI();
    });
    els.progress?.addEventListener('input', () => {
      if (!replayDuration) return;
      const ratio = parseInt(els.progress.value, 10) / 1000;
      replayProgress = replayDuration * ratio;
      els.progressLabel.textContent = `${t('cabanaLogTime', '日志')} ${formatReplayTime(replayProgress)} / ${formatReplayTime(replayDuration)}`;
      scheduleVideoThumbnail({ immediate: true });
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
    els.plotClear?.addEventListener('click', () => {
      plotSeriesList = [];
      destroyPlot();
      if (els.plotEmpty) els.plotEmpty.hidden = false;
    });
    els.detailClose?.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      clearSelection();
      renderDetailPanel();
      scheduleVirtualRender();
    });
    els.videoToggle?.addEventListener('change', () => {
      setVideoPreviewEnabled(els.videoToggle.checked);
    });
  }

  async function refresh() {
    applyTranslations();
    const route = panelMode === 'replay' ? (els.routeSelect?.value || replayRoute || '') : '';
    await loadCar(route);
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
