/**
 * Hermes-style terminal AI — natural language routes to op助手.
 * Replies stream inline in xterm (PTY muted during AI to avoid layout clash).
 */
const TerminalAi = (() => {
  let deps = {};
  let running = false;
  let activeJobId = null;
  let lineBuffer = '';
  let pendingConfirm = null;

  const ANSI = {
    reset: '\x1b[0m',
    dim: '\x1b[90m',
    bold: '\x1b[1m',
    italic: '\x1b[3m',
    cyan: '\x1b[36m',
    brightCyan: '\x1b[96m',
    green: '\x1b[32m',
    yellow: '\x1b[33m',
    red: '\x1b[31m',
    blue: '\x1b[34m',
  };

  function init(d = {}) {
    deps = d;
  }

  function isRunning() {
    return running;
  }

  function sanitizeText(s) {
    return String(s || '')
      .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')
      .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, '');
  }

  /** Remove function-call syntax some models leak into content. */
  function stripLeakedToolCalls(text) {
    if (!text) return '';
    let s = String(text);
    let out = '';
    let i = 0;
    while (i < s.length) {
      const rest = s.slice(i);
      const m = rest.match(/(?:^|\s)(functions\.[a-zA-Z_][\w.]*)\s*:/);
      if (!m || m.index === undefined) {
        out += rest;
        break;
      }
      const lead = m[0].startsWith(' ') ? 1 : 0;
      const start = i + m.index + lead;
      out += s.slice(i, start);
      i = start + m[1].length + 1;
      while (i < s.length && s[i] !== '\n') i += 1;
    }
    return out.replace(/\n{3,}/g, '\n\n').trimEnd();
  }

  function formatToolLabel(name) {
    const n = String(name || 'tool');
    return n.replace(/^functions\./, '').replace(/_/g, ' ');
  }

  function formatInlineMarkdown(text) {
    const R = ANSI.reset;
    let out = String(text || '');
    out = out.replace(/`([^`\n]+)`/g, `${ANSI.brightCyan}$1${R}`);
    out = out.replace(/\*\*([^*\n]+)\*\*/g, `${ANSI.bold}$1${R}`);
    out = out.replace(/__([^_\n]+)__/g, `${ANSI.bold}$1${R}`);
    out = out.replace(/(^|[^*])\*([^*\n]+)\*([^*]|$)/g, `$1${ANSI.italic}$2${R}$3`);
    return out;
  }

  function formatTerminalLine(line) {
    const raw = String(line || '').trimEnd();
    if (!raw.trim()) return '';

    const plain = raw.trim();
    if (/^[-*_]{3,}$/.test(plain)) {
      return `${ANSI.dim}${'─'.repeat(Math.min(plain.length, 48))}${ANSI.reset}`;
    }

    const heading = plain.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const color = level <= 2 ? ANSI.bold + ANSI.cyan : ANSI.cyan;
      return `${color}${formatInlineMarkdown(heading[2])}${ANSI.reset}`;
    }

    const bullet = plain.match(/^(\s*)[-*+]\s+(.+)$/);
    if (bullet) {
      const pad = bullet[1].replace(/\t/g, '  ');
      return `${pad}${ANSI.yellow}•${ANSI.reset} ${formatInlineMarkdown(bullet[2])}`;
    }

    const numbered = plain.match(/^(\s*)(\d+)[.)]\s+(.+)$/);
    if (numbered) {
      return `${numbered[1]}${ANSI.yellow}${numbered[2]}.${ANSI.reset} ${formatInlineMarkdown(numbered[3])}`;
    }

    const quote = plain.match(/^>\s?(.+)$/);
    if (quote) {
      return `${ANSI.dim}│ ${formatInlineMarkdown(quote[1])}${ANSI.reset}`;
    }

    if (/^(建议|结论|总结|注意|提示|状态|结果)[:：]/.test(plain)) {
      return `${ANSI.bold}${formatInlineMarkdown(plain)}${ANSI.reset}`;
    }

    return formatInlineMarkdown(plain);
  }

  class TermInlineWriter {
    constructor(term) {
      this.term = term;
      this.buf = { content: '', reasoning: '' };
      this.processing = false;
      this.replyStarted = false;
      this.inCodeBlock = false;
    }

    cols() {
      return Math.max(40, (this.term?.cols || 80) - 2);
    }

    scrollBottom() {
      try {
        this.term?.scrollToBottom?.();
      } catch {}
    }

    clearProcessingLine() {
      if (!this.processing || !this.term) return;
      try {
        this.term.write('\x1b[1A\x1b[2K');
      } catch {}
      this.processing = false;
    }

    beginReply() {
      if (this.replyStarted) return;
      this.clearProcessingLine();
      this.replyStarted = true;
      this.term?.writeln(`${ANSI.cyan}${ANSI.bold}[op助手]${ANSI.reset}`);
    }

    writeFormattedLine(rawLine, { isReasoning = false } = {}) {
      if (!this.term) return;
      if (!String(rawLine || '').trim()) {
        this.term.writeln('');
        this.scrollBottom();
        return;
      }

      const cleaned = stripLeakedToolCalls(rawLine);
      if (!cleaned.trim()) return;

      if (cleaned.trim().startsWith('```')) {
        this.inCodeBlock = !this.inCodeBlock;
        this.term.writeln(
          this.inCodeBlock
            ? `${ANSI.dim}  ┌─ code ─${ANSI.reset}`
            : `${ANSI.dim}  └────────${ANSI.reset}`,
        );
        this.scrollBottom();
        return;
      }

      const wrapIndent = isReasoning ? 10 : 2;
      const max = Math.max(20, this.cols() - wrapIndent);

      const wrap = (text) => {
        const out = [];
        let remaining = String(text || '').replace(/\r/g, '');
        while (remaining.length > 0) {
          if (remaining.length <= max) {
            out.push(remaining);
            break;
          }
          let breakAt = max;
          const slice = remaining.slice(0, max + 1);
          const lastSpace = slice.lastIndexOf(' ');
          if (lastSpace > max * 0.35) breakAt = lastSpace;
          out.push(remaining.slice(0, breakAt).trimEnd());
          remaining = remaining.slice(breakAt).trimStart();
        }
        return out.length ? out : [''];
      };

      if (this.inCodeBlock) {
        for (const part of wrap(cleaned)) {
          this.term.writeln(`${ANSI.dim}  │ ${part}${ANSI.reset}`);
        }
      } else {
        for (const part of wrap(cleaned)) {
          const formatted = formatTerminalLine(part);
          if (isReasoning) {
            this.term.writeln(`${ANSI.dim}  [思考] ${formatted}${ANSI.reset}`);
          } else {
            this.term.writeln(`  ${formatted}`);
          }
        }
      }
      this.scrollBottom();
    }

    flushBuf(key) {
      const buf = this.buf[key];
      const nl = buf.indexOf('\n');
      if (nl === -1) return;
      const line = buf.slice(0, nl);
      this.buf[key] = buf.slice(nl + 1);

      if (key === 'reasoning') {
        this.writeFormattedLine(line, { isReasoning: true });
      } else {
        this.beginReply();
        this.writeFormattedLine(line);
      }
      if (this.buf[key]) this.flushBuf(key);
    }

    append(delta, type) {
      const key = type === 'reasoning' ? 'reasoning' : 'content';
      this.buf[key] += sanitizeText(delta);
      this.flushBuf(key);
    }

    flushAll() {
      for (const key of ['reasoning', 'content']) {
        const text = this.buf[key];
        if (!text) continue;
        if (key === 'reasoning') {
          const trimmed = text.trim();
          if (trimmed) this.writeFormattedLine(trimmed, { isReasoning: true });
        } else {
          this.beginReply();
          for (const line of text.split('\n')) {
            this.writeFormattedLine(line);
          }
        }
        this.buf[key] = '';
      }
      this.scrollBottom();
    }

    toolCall(name) {
      if (!this.term) return;
      this.beginReply();
      const label = formatToolLabel(name);
      this.term.writeln(`${ANSI.dim}  ▸ ${label}${ANSI.reset}`);
      this.scrollBottom();
    }

    toolResult(ok) {
      if (!this.term) return;
      const mark = ok ? `${ANSI.green}✓` : `${ANSI.red}✗`;
      this.term.writeln(`${ANSI.dim}    ${mark}${ANSI.reset}`);
      this.scrollBottom();
    }

    error(msg) {
      this.clearProcessingLine();
      this.term?.writeln(`${ANSI.red}  [错误] ${msg}${ANSI.reset}`);
      this.scrollBottom();
    }

    done(statusText) {
      this.clearProcessingLine();
      if (statusText) {
        this.term?.writeln(`${ANSI.dim}  [op助手] ${statusText}${ANSI.reset}`);
      }
    }

    markProcessing() {
      this.processing = true;
    }
  }

  function shouldRouteToAi(line) {
    const t = (line || '').trim();
    if (!t) return false;
    if (t.startsWith('!')) return false;
    if (/^op(\s|$)/i.test(t)) return false;
    if (t === '/help' || t === 'help' || t === '?') return true;
    if (t.startsWith('?') || t.startsWith('/ai ') || t.startsWith('ai:')) return true;
    if (/[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]/.test(t)) return true;
    if (/^(help|what|how|why|who|when|where|list|show|find|check|explain|diagnose|排查|分析|查看|怎么|为什么|如何)\b/i.test(t)) {
      return true;
    }
    if (/\s/.test(t) && !/^[a-z0-9_./\\-]+$/i.test(t)) return true;
    return false;
  }

  function normalizeAiQuery(line) {
    let t = (line || '').trim();
    if (t === '/help' || t === 'help' || t === '?') return '';
    if (t.startsWith('!')) t = t.slice(1).trim();
    if (t.startsWith('?')) t = t.slice(1).trim();
    if (t.startsWith('/ai ')) t = t.slice(4).trim();
    if (t.toLowerCase().startsWith('ai:')) t = t.slice(3).trim();
    return t;
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function write(term, text) {
    if (term && text) term.write(text);
  }

  function writeln(term, text) {
    if (term) term.writeln(text);
  }

  function shellHint(term, text) {
    if (!term) return;
    writeln(term, `\x1b[90m${text}\x1b[0m`);
  }

  function prepareMessages(session, userText) {
    const base = Array.isArray(session?.messages) ? session.messages.slice(-40) : [];
    const prepared = typeof deps.prepareMessagesForApi === 'function'
      ? deps.prepareMessagesForApi(base)
      : base;
    return [...prepared, { role: 'user', content: userText }];
  }

  async function cancel() {
    if (!activeJobId || !deps.api) return;
    const jobId = activeJobId;
    try {
      await deps.api('DELETE', `/api/ai/chat/jobs/${encodeURIComponent(jobId)}`);
    } catch {}
  }

  async function streamOpEvents(body, writer, term) {
    const res = await fetch('/api/ai/terminal/op', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      let err = `HTTP ${res.status}`;
      try {
        const j = await res.json();
        err = j.error || err;
      } catch {}
      writer.error(err);
      return;
    }
    const reader = res.body?.getReader();
    if (!reader) {
      writer.error('无流式响应');
      return;
    }
    const decoder = new TextDecoder();
    let buf = '';
    while (running) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop() || '';
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith('data:')) continue;
        let ev;
        try {
          ev = JSON.parse(trimmed.slice(5).trim());
        } catch {
          continue;
        }
        if (ev.type === 'reasoning') {
          writer.append(ev.delta || ev.content || '', 'reasoning');
        } else if (ev.type === 'content') {
          writer.append(ev.delta || ev.content || '', 'content');
        } else if (ev.type === 'tool_call') {
          writer.flushAll();
          writer.toolCall(ev.name || 'tool');
        } else if (ev.type === 'tool_result') {
          const result = ev.result || {};
          if (result.needs_confirmation && result.pending_id) {
            writer.flushAll();
            printConsumerConfirm(term, result);
            pendingConfirm = { pendingId: result.pending_id, writer };
            running = false;
            return;
          }
          const ok = result.ok !== false && !result.error;
          writer.toolResult(ok);
        } else if (ev.type === 'error') {
          writer.flushAll();
          writer.error(ev.error || 'error');
        } else if (ev.type === 'done') {
          writer.flushAll();
          if (ev.ok === false) writer.error(ev.error || 'failed');
        }
      }
    }
    writer.flushAll();
  }

  function printConsumerConfirm(term, result) {
    const cp = result.consumer_preview || {};
    const rows = cp.rows || [];
    writeln(term, `\x1b[33m[op] 需要您确认以下设置变更（车辆需静止）\x1b[0m`);
    if (cp.summary) writeln(term, `\x1b[90m${cp.summary}\x1b[0m`);
    for (const r of rows) {
      writeln(term, `  \x1b[1m${r.label || r.key}\x1b[0m: ${r.before} → \x1b[32m${r.after}\x1b[0m`);
    }
    writeln(term, '\x1b[90m输入 y 确认应用，n 取消\x1b[0m');
  }

  async function handlePendingConfirm(line, term, { aiOnly = false } = {}) {
    if (!pendingConfirm) return false;
    const ans = (line || '').trim().toLowerCase();
    const { pendingId, writer } = pendingConfirm;
    pendingConfirm = null;
    if (ans === 'y' || ans === 'yes' || ans === '是') {
      try {
        const { data } = await deps.api('POST', '/api/ai/terminal/op/confirm', { pending_id: pendingId });
        writer.toolResult(!!data?.ok);
        if (!data?.ok) writer.error(data?.error || '确认失败');
      } catch (e) {
        writer.error(e?.message || String(e));
      }
    } else {
      shellHint(term, '[op] 已取消');
    }
    running = false;
    deps.onAiActivity?.(false);
    if (aiOnly) writePrompt(term);
    return true;
  }

  async function runQuery(rawLine, term, { aiOnly = false } = {}) {
    const query = normalizeAiQuery(rawLine);
    if (rawLine.trim() === '/help' || rawLine.trim() === 'help' || rawLine.trim() === '?') {
      printHelp(term, { aiOnly });
      return;
    }
    if (!query || running) return;
    if (!deps.api || !deps.SessionStore) {
      shellHint(term, '[op] AI 未初始化');
      return;
    }

    const writer = new TermInlineWriter(term);
    running = true;
    activeJobId = null;
    deps.onAiActivity?.(true);
    deps.SessionStore.ensureSessionOnSend?.(query);
    const session = deps.SessionStore.getActive?.();
    const sessionId = session?.id;
    if (!sessionId) {
      writer.error('无活动会话');
      running = false;
      deps.onAiActivity?.(false);
      if (aiOnly) writePrompt(term);
      return;
    }

    writeln(term, `\x1b[36m[你]\x1b[0m ${query}`);
    shellHint(term, '[op] 处理中…');
    writer.markProcessing();

    try {
      const messages = prepareMessages(session, query);
      await streamOpEvents({
        sessionId,
        messages,
        tools: true,
        consumerMode: true,
        source: 'terminal-op',
      }, writer, term);
      deps.syncSessionsToDevice?.().catch(() => {});
      if (writer.replyStarted) writeln(term, '');
    } catch (e) {
      writer.error(e?.message || String(e));
    } finally {
      if (!pendingConfirm) {
        running = false;
        deps.onAiActivity?.(false);
        if (aiOnly) writePrompt(term);
      }
    }
  }

  function resetLineBuffer() {
    lineBuffer = '';
  }

  function processInput(data, ws, term, { aiOnly = false } = {}) {
    let i = 0;
    while (i < data.length) {
      const ch = data[i];

      if (ch === '\x1b') {
        const chunk = data.slice(i);
        if (!aiOnly && ws?.readyState === WebSocket.OPEN && !deps.ptyMuted?.() && !pendingConfirm) {
          ws.send(chunk);
        }
        return;
      }

      if (ch === '\r' || ch === '\n') {
        const line = lineBuffer;
        lineBuffer = '';
        if (aiOnly) term.write('\r\n');
        if (pendingConfirm) {
          handlePendingConfirm(line, term, { aiOnly });
          i += 1;
          continue;
        }
        if (shouldRouteToAi(line)) {
          if (!aiOnly && ws?.readyState === WebSocket.OPEN) {
            ws.send('\x15');
            ws.send('\r');
          }
          runQuery(line, term, { aiOnly });
        } else if (aiOnly) {
          shellHint(term, '（AI 模式：自然语言，或 ! 前缀强制 Shell）');
          writePrompt(term);
        } else if (ws?.readyState === WebSocket.OPEN && !deps.ptyMuted?.()) {
          ws.send(ch);
        }
        i += 1;
        continue;
      }

      if (ch === '\x7f' || ch === '\b') {
        lineBuffer = lineBuffer.slice(0, -1);
        if (aiOnly) term.write('\b \b');
      } else if (ch === '\x03') {
        lineBuffer = '';
        if (running) cancel();
        if (aiOnly) {
          term.write('^C\r\n');
          writePrompt(term);
        } else if (ws?.readyState === WebSocket.OPEN && !deps.ptyMuted?.()) {
          ws.send(ch);
        }
        i += 1;
        continue;
      } else if (ch >= ' ' || ch === '\t') {
        lineBuffer += ch;
        if (aiOnly) term.write(ch);
      }

      if (!aiOnly && ws?.readyState === WebSocket.OPEN && !deps.ptyMuted?.() && !pendingConfirm) {
        ws.send(ch);
      }
      i += 1;
    }
  }

  function writePrompt(term) {
    write(term, '\x1b[32mop>\x1b[0m ');
  }

  function attach(term, ws, opts = {}) {
    if (!term) return;
    resetLineBuffer();
    term.onData((data) => {
      processInput(data, ws, term, opts);
    });
  }

  function printHelp(term, { aiOnly = false } = {}) {
    writeln(term, '\x1b[33mOP 终端\x1b[0m：');
    writeln(term, '  \x1b[36mop status|tune|doctor|adapt|chat "…"\x1b[0m — Shell 中直接敲');
    writeln(term, '  自然语言 / \x1b[36m?\x1b[0m / \x1b[36m/ai\x1b[0m — 等价 \x1b[36mop chat\x1b[0m');
    writeln(term, '  \x1b[36m!\x1b[0m 前缀 — 强制 Shell；改参时会提示 y/n 确认');
    if (aiOnly) writePrompt(term);
  }

  return {
    init,
    attach,
    runQuery,
    cancel,
    isRunning,
    shouldRouteToAi,
    printHelp,
    resetLineBuffer,
  };
})();
