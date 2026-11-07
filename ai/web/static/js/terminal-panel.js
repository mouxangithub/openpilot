/**
 * Web terminal — xterm.js + PTY WebSocket + Hermes-style AI routing (centered modal).
 * AI replies stream inline in xterm; PTY is muted while AI is active.
 */
const TerminalPanel = (() => {
  let modal = null;
  let term = null;
  let ws = null;
  let fitAddon = null;
  let open = false;
  let onVisibilityChange = null;
  let aiOnly = false;
  let ptyMuted = false;

  function wsUrl() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${location.host}/api/ai/terminal/ws`;
  }

  function ensureDom() {
    modal = document.getElementById('terminalModal');
    const closeBtn = document.getElementById('terminalCloseBtn');
    const toggleBtn = document.getElementById('terminalToggleBtn');
    const backdrop = document.getElementById('terminalBackdrop');
    if (closeBtn && !closeBtn.dataset.bound) {
      closeBtn.dataset.bound = '1';
      closeBtn.addEventListener('click', () => setOpen(false));
    }
    if (backdrop && !backdrop.dataset.bound) {
      backdrop.dataset.bound = '1';
      backdrop.addEventListener('click', () => setOpen(false));
    }
    if (toggleBtn && !toggleBtn.dataset.bound) {
      toggleBtn.dataset.bound = '1';
      toggleBtn.addEventListener('click', () => setOpen(!open));
    }
  }

  function setOpen(v) {
    open = !!v;
    ensureDom();
    if (modal) {
      modal.classList.toggle('is-open', open);
      if (open) modal.removeAttribute('hidden');
      else modal.setAttribute('hidden', '');
    }
    document.getElementById('terminalToggleBtn')?.classList.toggle('active', open);
    onVisibilityChange?.(open);
    if (open) {
      connect();
      if (typeof TerminalSidecar !== 'undefined') TerminalSidecar.connect();
      setTimeout(() => fitTerminal(), 80);
    } else {
      disconnect();
      if (typeof TerminalSidecar !== 'undefined') TerminalSidecar.disconnect();
    }
  }

  function fitTerminal() {
    if (fitAddon && term) {
      try { fitAddon.fit(); } catch {}
      if (ws?.readyState === WebSocket.OPEN && term.cols && term.rows) {
        ws.send(`\x1b[RESIZE:${term.cols};${term.rows}]`);
      }
    }
  }

  function ensureTerm() {
    if (typeof Terminal === 'undefined') {
      console.warn('xterm.js not loaded');
      return false;
    }
    const host = document.getElementById('terminalHost');
    if (!host) return false;
    if (!term) {
      term = new Terminal({
        cursorBlink: true,
        fontSize: 13,
        lineHeight: 1.35,
        fontFamily: 'Consolas, "Cascadia Mono", "SF Mono", Menlo, monospace',
        theme: { background: '#0d1117', foreground: '#e6edf3' },
      });
      if (typeof FitAddon !== 'undefined') {
        fitAddon = new FitAddon.FitAddon();
        term.loadAddon(fitAddon);
      }
      term.open(host);
      window.addEventListener('resize', () => fitTerminal());
    }
    return true;
  }

  function setPtyMuted(muted) {
    ptyMuted = !!muted;
  }

  function attachInput() {
    if (typeof TerminalAi === 'undefined' || !term) return;
    TerminalAi.attach(term, ws, { aiOnly });
  }

  function enableAiOnlyMode({ clear = false, reason = '' } = {}) {
    aiOnly = true;
    if (!ensureTerm()) return;
    if (clear) term.clear();
    const msg = reason || '已切换 AI 模式（Shell 不可用，历史已保留）';
    term.writeln(`\x1b[33m${msg}\x1b[0m`);
    if (typeof TerminalAi !== 'undefined') TerminalAi.printHelp(term, { aiOnly: true });
    term.writeln('');
    attachInput();
    fitTerminal();
  }

  let connectTimer = null;

  function clearConnectTimer() {
    if (connectTimer) {
      clearTimeout(connectTimer);
      connectTimer = null;
    }
  }

  function startAiOnly() {
    enableAiOnlyMode({ clear: true, reason: 'op助手 Web 终端 — AI 模式（本机无 PTY）' });
  }

  function connect() {
    if (!ensureTerm()) return;
    disconnect();
    aiOnly = false;
    ptyMuted = false;
    term.clear();
    term.writeln('\x1b[33mop助手 Web 终端\x1b[0m — AGNOS/Linux PTY + AI');
    term.writeln('连接中…\r\n');

    try {
      ws = new WebSocket(wsUrl());
      ws.binaryType = 'arraybuffer';
    } catch (e) {
      term.writeln(`\x1b[31mWebSocket 失败: ${e.message}\x1b[0m`);
      startAiOnly();
      return;
    }

    clearConnectTimer();
    connectTimer = setTimeout(() => {
      if (!ws || ws.readyState === WebSocket.OPEN || aiOnly) return;
      try { ws.close(); } catch {}
      term.writeln('\r\n\x1b[33m连接超时 — 已切换 AI 模式（服务可能仍在启动）\x1b[0m');
      startAiOnly();
    }, 10000);

    ws.onopen = () => {
      clearConnectTimer();
      term.writeln('\x1b[32m已连接\x1b[0m');
      if (typeof TerminalAi !== 'undefined') TerminalAi.printHelp(term);
      term.writeln('');
      attachInput();
      fitTerminal();
    };
    ws.onmessage = (ev) => {
      if (ptyMuted) return;
      if (typeof ev.data === 'string') term.write(ev.data);
      else term.write(new Uint8Array(ev.data));
    };
    ws.onclose = () => {
      clearConnectTimer();
      if (!aiOnly) {
        term.writeln('\r\n\x1b[33mShell 连接已关闭 — 可继续用 AI，或关闭后重开尝试重连\x1b[0m');
        enableAiOnlyMode({ clear: false });
      }
    };
    ws.onerror = () => {
      clearConnectTimer();
      if (!aiOnly) {
        term.writeln('\r\n\x1b[31m终端连接错误\x1b[0m');
        enableAiOnlyMode({ clear: false });
      }
    };
  }

  function disconnect() {
    clearConnectTimer();
    if (ws) {
      try { ws.close(); } catch {}
      ws = null;
    }
    ptyMuted = false;
    if (typeof TerminalAi !== 'undefined') TerminalAi.cancel?.();
  }

  function init(opts = {}) {
    onVisibilityChange = opts.onVisibilityChange || null;
    ensureDom();
  }

  return {
    init,
    setOpen,
    connect,
    disconnect,
    isOpen: () => open,
    setPtyMuted,
    isPtyMuted: () => ptyMuted,
  };
})();
