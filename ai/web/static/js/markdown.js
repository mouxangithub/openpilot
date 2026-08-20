/**
 * Chat Markdown — markdown-it (OpenClaw) + ClawPanel lite fallback.
 * Vendor: OpMarkdown bundle, DOMPurify, highlight.js.
 */
(function (global) {
  'use strict';

  const ALLOWED_TAGS = [
    'a', 'b', 'blockquote', 'br', 'button', 'code', 'del', 'div', 'em', 'h1', 'h2', 'h3', 'h4',
    'hr', 'i', 'input', 'li', 'ol', 'p', 'pre', 's', 'span', 'strong', 'table', 'tbody', 'td',
    'th', 'thead', 'tr', 'ul',
  ];
  const ALLOWED_ATTR = ['target', 'rel', 'class', 'type', 'disabled', 'checked', 'start', 'href', 'data-code'];

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function parseTableRow(line) {
    return String(line || '').trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
  }

  function isDashSepLine(line) {
    const parts = String(line || '').trim().split(/\s+/).filter(Boolean);
    return parts.length >= 2 && parts.every((p) => /^-{3,}:?$/.test(p));
  }

  function parseTwoColHeader(line) {
    const t = String(line || '').trim();
    if (!t || t.includes('|')) return null;
    const m = t.match(/^(\S+)\s+(\S+)$/);
    if (m) return [m[1], m[2]];
    const parts = t.split(/\s{2,}/);
    if (parts.length >= 2) return [parts[0], parts.slice(1).join(' ')];
    return null;
  }

  function repairDashSeparatedTables(markdown) {
    let s = String(markdown);
    s = s.replace(
      /(项目|字段|项|属性)\s+(状态|值|说明|内容)\s+((?:-{3,}\s*)+)\s*/g,
      '\n| $1 | $2 |\n| --- | --- |\n',
    );
    const lines = s.split('\n');
    const out = [];
    let i = 0;
    while (i < lines.length) {
      const hdr = parseTwoColHeader(lines[i]);
      const next = (lines[i + 1] || '').trim();
      if (hdr && isDashSepLine(next)) {
        out.push(`| ${hdr[0]} | ${hdr[1]} |`, '| --- | --- |');
        i += 2;
        while (i < lines.length) {
          const row = parseTwoColHeader(lines[i]);
          if (!row) break;
          out.push(`| ${row[0]} | ${row[1]} |`);
          i += 1;
        }
        continue;
      }
      out.push(lines[i]);
      i += 1;
    }
    return out.join('\n');
  }

  /** Split multiple table rows glued on one line (`... | false || 点火 | ...`). */
  function splitGluedPipeRows(line) {
    let s = String(line || '');
    if (!s.includes('|')) return s;
    if (s.includes('||')) {
      s = s.replace(/\|\s*\|(?=\s*[^\s|:\-])/g, '|\n|');
    }
    // One-line tables only: "|row| |---|---| |row2|" — never split normal "| a | b |" rows.
    if (!s.includes('\n') && /\|[-:]{3,}/.test(s)) {
      s = s.replace(/\|\s+(\|[-:\s|]+\|)/g, '|\n$1');
    }
    return s;
  }

  function isDashCell(text) {
    return /^[-:]{2,}$/.test(String(text || '').trim());
  }

  function isTableSepLine(line) {
    const t = String(line || '').trim();
    return /^\s*\|[\s\-:|]+\|\s*$/.test(t)
      || /^\s*\|?\s*\-{3,}\s*(\|\s*\-{3,}\s*)+\|?\s*$/.test(t)
      || /^\s*\-{3,}\s*\|\s*\-{3,}\s*$/.test(t);
  }

  function isCompleteTableRow(line) {
    const t = String(line || '').trim();
    return t.startsWith('|') && t.endsWith('|') && parseTableRow(t).length >= 2;
  }

  function isTableBlockStart(lines, index) {
    const line = String(lines[index] || '').trim();
    if (!line.includes('|')) return false;
    return index + 1 < lines.length && isTableSepLine(lines[index + 1]);
  }

  /** Merge multiline / list continuations into the previous table row. */
  function repairFragmentedTableRows(markdown) {
    const lines = String(markdown).split('\n');
    const out = [];
    let i = 0;
    while (i < lines.length) {
      if (!isTableBlockStart(lines, i)) {
        out.push(lines[i]);
        i += 1;
        continue;
      }
      out.push(lines[i], lines[i + 1]);
      i += 2;
      while (i < lines.length) {
        const raw = lines[i];
        const trimmed = raw.trim();
        if (!trimmed) break;
        if (isTableSepLine(trimmed)) {
          out.push(raw);
          i += 1;
          continue;
        }
        if (isTableBlockStart(lines, i)) break;
        if (isCompleteTableRow(trimmed)) {
          out.push(raw);
          i += 1;
          continue;
        }
        if (!trimmed.startsWith('|') && out.length < 3) break;

        let merged = trimmed.startsWith('|') ? trimmed : `| ${trimmed}`;
        i += 1;
        while (i < lines.length) {
          const next = lines[i];
          const nt = next.trim();
          if (!nt) break;
          if (isTableSepLine(nt) || isTableBlockStart(lines, i)) break;
          if (isCompleteTableRow(nt)) break;
          const piece = nt.replace(/^\|\s*/, '').replace(/\|\s*$/, '');
          merged = `${merged.replace(/\|\s*$/, '')}<br>${piece}`;
          i += 1;
          if (nt.endsWith('|')) {
            merged = `${merged} |`;
            break;
          }
        }
        if (!merged.trim().endsWith('|')) merged = `${merged.trim()} |`;
        out.push(merged);
      }
      out.push('');
    }
    return out.join('\n');
  }

  function repairSeparatorLines(markdown) {
    return String(markdown).replace(/^(\s*)\|?(-{3,}:?\s*\|)+-{3,}:?\|?\s*$/gm, (line) => {
      const count = (line.match(/-{3,}/g) || []).length;
      const cols = Math.max(2, count);
      return `| ${Array(cols).fill('---').join(' | ')} |`;
    });
  }

  function looksLikeMarkdownTable(text) {
    return /\|[^|\n]+\|/.test(text) || /^\s*[^|\n]+\s+\|/m.test(text);
  }

  function isKvValueHeader(text) {
    return /^(当前值|详情|值|说明|状态|内容|结果)$/u.test(String(text || '').trim());
  }

  function isPlaceholderTableRow(line) {
    const cells = parseTableRow(line);
    if (cells.length < 2) return false;
    return cells.every((c) => {
      const t = c.trim();
      return !t || /^\.{2,}$|^…+$|^[—\-－―]+$/u.test(t);
    });
  }

  function dropPlaceholderTableRows(markdown) {
    return String(markdown).split('\n').filter((line) => {
      const trimmed = line.trim();
      if (!isCompleteTableRow(trimmed)) return true;
      return !isPlaceholderTableRow(trimmed);
    }).join('\n');
  }

  function repairOrphanKvHeader(markdown) {
    const lines = String(markdown).split('\n');
    const out = [];
    for (let i = 0; i < lines.length; i++) {
      const trimmed = lines[i].trim();
      const next = (lines[i + 1] || '').trim();
      if (isCompleteTableRow(trimmed)) {
        const cells = parseTableRow(trimmed);
        if (cells.length === 1 && cells[0] && isKvValueHeader(next)) {
          out.push(`| ${cells[0]} | ${next} |`);
          i += 1;
          continue;
        }
        if (cells.length === 2 && cells[0] && !cells[1] && isKvValueHeader(next)) {
          out.push(`| ${cells[0]} | ${next} |`);
          i += 1;
          continue;
        }
      }
      if (!trimmed.includes('|') && isKvValueHeader(trimmed) && out.length) {
        const prev = out[out.length - 1].trim();
        if (isCompleteTableRow(prev)) {
          const prevCells = parseTableRow(prev);
          if (prevCells.length === 1 && prevCells[0]) {
            out[out.length - 1] = `| ${prevCells[0]} | ${trimmed} |`;
            continue;
          }
          if (prevCells.length === 2 && prevCells[0] && !prevCells[1]) {
            out[out.length - 1] = `| ${prevCells[0]} | ${trimmed} |`;
            continue;
          }
        }
      }
      out.push(lines[i]);
    }
    return out.join('\n');
  }

  function repairTrailingEmDash(markdown) {
    return String(markdown)
      .replace(/[：:]\s*[—\-―－]{2,}\s*$/gm, ':\n\n<hr>\n')
      .replace(/^\s*[—\-―－]{2,}\s*$/gm, '<hr>\n');
  }

  function splitGluedKvCell(text) {
    const t = String(text || '').trim();
    if (!t) return null;
    const m = t.match(/^(.+?)\s+(null|true|false|-?\d+(?:\.\d+)?(?:\s*(?:km\/h|km|m\/s|%))?)$/i);
    if (m) return [m[1].trim(), m[2].trim()];
    const parts = t.split(/\s{2,}/).map((p) => p.trim()).filter(Boolean);
    if (parts.length === 2) return parts;
    return null;
  }

  function normalizeTableColumnCounts(markdown) {
    const lines = String(markdown).split('\n');
    const out = [];
    let i = 0;
    while (i < lines.length) {
      if (!isTableBlockStart(lines, i)) {
        out.push(lines[i]);
        i += 1;
        continue;
      }
      const headerCols = parseTableRow(lines[i].trim()).length;
      out.push(lines[i]);
      i += 1;
      if (i < lines.length && isTableSepLine(lines[i].trim())) {
        out.push(lines[i]);
        i += 1;
      }
      while (i < lines.length) {
        const raw = lines[i];
        const trimmed = raw.trim();
        if (!trimmed) {
          out.push('');
          i += 1;
          break;
        }
        if (isTableBlockStart(lines, i)) break;
        if (!trimmed.includes('|')) {
          const parts = trimmed.split(/\s{2,}|\t+/).map((p) => p.trim()).filter(Boolean);
          if (parts.length >= 2 && headerCols >= 2) {
            while (parts.length < headerCols) parts.push('');
            out.push(`| ${parts.slice(0, headerCols).join(' | ')} |`);
            i += 1;
            continue;
          }
          out.push(raw);
          i += 1;
          break;
        }
        let cells = parseTableRow(trimmed);
        if (cells.length === 1 && headerCols >= 2) {
          const split = splitGluedKvCell(cells[0]);
          if (split) cells = split;
        }
        while (cells.length < headerCols) cells.push('');
        if (cells.length > headerCols) cells = cells.slice(0, headerCols);
        out.push(`| ${cells.join(' | ')} |`);
        i += 1;
      }
    }
    return out.join('\n');
  }

  function tableColCountFromHtml(inner) {
    const firstRow = String(inner || '').match(/<tr[^>]*>([\s\S]*?)<\/tr>/i);
    if (!firstRow) return 0;
    return (firstRow[1].match(/<t[hd][^>]*>/gi) || []).length;
  }

  function isKvTableHtml(inner) {
    const colCount = tableColCountFromHtml(inner);
    if (colCount !== 2) return false;
    const rows = String(inner || '').match(/<tr[^>]*>[\s\S]*?<\/tr>/gi) || [];
    return rows.length > 0 && rows.every((row) => (row.match(/<t[hd][^>]*>/gi) || []).length === 2);
  }

  function wrapMarkdownTables(html) {
    let s = String(html);
    s = s.replace(
      /<div class="md-table-wrap">\s*<table class="md-table([^"]*)">([\s\S]*?)<\/table>\s*<\/div>/gi,
      (_, cls, inner) => {
        const kv = cls.includes('md-kv-table') || isKvTableHtml(inner) ? ' md-kv-table' : '';
        return `<div class="markdown-table${kv}"><div class="markdown-table__viewport"><table class="md-table${cls}${kv ? ' md-kv-table' : ''}">${inner}</table></div></div>`;
      },
    );
    // Bare tables from markdown-it without custom wrapper
    s = s.replace(
      /<table(?![^>]*class="[^"]*md-table)([^>]*)>([\s\S]*?)<\/table>/gi,
      (_, attrs, inner) => {
        const kv = isKvTableHtml(inner) ? ' md-kv-table' : '';
        return `<div class="markdown-table${kv}"><div class="markdown-table__viewport"><table class="md-table${kv}"${attrs}>${inner}</table></div></div>`;
      },
    );
    return s;
  }

  function formatReasoningMarkdown(text) {
    const lines = String(text || '').trim().split('\n').filter(Boolean);
    if (!lines.length) return '';
    return `_Reasoning:_\n\n${lines.map((line) => `_${line.replace(/^[-*]\s+/, '')}_`).join('\n')}`;
  }
  function compactRowCells(cells) {
    const trimmed = cells.map((c) => String(c || '').trim());
    if (trimmed.length && trimmed.every(isDashCell)) return [];
    const withoutDash = trimmed.filter((c) => c && !isDashCell(c));
    if (withoutDash.length >= 2 && withoutDash.length < trimmed.length) return withoutDash;
    const nonEmpty = trimmed.filter(Boolean);
    if (nonEmpty.length >= 2 && nonEmpty.length < trimmed.length) return nonEmpty;
    return trimmed;
  }

  function collapseTableBlocks(markdown) {
    const lines = String(markdown).split('\n');
    const out = [];
    let i = 0;
    while (i < lines.length) {
      const trimmed = (lines[i] || '').trim();
      if (!isTableBlockStart(lines, i)) {
        out.push(lines[i]);
        i += 1;
        continue;
      }
      let headerCells = compactRowCells(parseTableRow(trimmed));
      if (!headerCells.length) {
        out.push(lines[i]);
        i += 1;
        continue;
      }
      while (headerCells.length && !headerCells[headerCells.length - 1]) headerCells.pop();
      const colCount = Math.max(2, headerCells.length);
      out.push(`| ${headerCells.slice(0, colCount).join(' | ')} |`);
      i += 1;
      if (i < lines.length && isTableSepLine(lines[i].trim())) {
        out.push(`| ${Array(colCount).fill('---').join(' | ')} |`);
        i += 1;
      }
      while (i < lines.length) {
        const rowTrim = lines[i].trim();
        if (!rowTrim) break;
        if (isTableBlockStart(lines, i)) break;
        if (!isCompleteTableRow(rowTrim) && !isTableSepLine(rowTrim)) break;
        if (isTableSepLine(rowTrim)) {
          i += 1;
          continue;
        }
        let cells = compactRowCells(parseTableRow(rowTrim));
        if (!cells.length) {
          i += 1;
          continue;
        }
        while (cells.length && !cells[cells.length - 1]) cells.pop();
        if (cells.length > colCount) {
          const head = cells.slice(0, colCount - 1);
          const tail = cells.slice(colCount - 1).filter(Boolean).join(' ');
          cells = [...head, tail];
        }
        while (cells.length < colCount) cells.push('');
        out.push(`| ${cells.slice(0, colCount).join(' | ')} |`);
        i += 1;
      }
      out.push('');
    }
    return out.join('\n');
  }

  function repairMissingTableSeparators(markdown) {
    const lines = String(markdown).split('\n');
    const out = [];
    for (let i = 0; i < lines.length; i++) {
      const trimmed = lines[i].trim();
      out.push(lines[i]);
      if (!isCompleteTableRow(trimmed)) continue;
      const next = (lines[i + 1] || '').trim();
      if (!next || isTableSepLine(next) || !isCompleteTableRow(next)) continue;
      const prev = (out.length >= 2 ? out[out.length - 2] : '').trim();
      if (isCompleteTableRow(prev) || isTableSepLine(prev)) continue;
      const cols = parseTableRow(trimmed).length;
      if (cols >= 2) out.push(`| ${Array(cols).fill('---').join(' | ')} |`);
    }
    return out.join('\n');
  }

  /** Ensure blank line before pipe tables (markdown-it GFM requirement). */
  function ensureTableBlockSpacing(markdown) {
    return String(markdown)
      .replace(/([^\n|])\n(\|[^|\n]+\|)/g, '$1\n\n$2')
      .replace(/(\n#{1,4}[^\n]+)\n(\|)/g, '$1\n\n$2');
  }

  function tagKvTables(html) {
    return String(html).replace(
      /<div class="md-table-wrap">\s*<table class="md-table([^"]*)">([\s\S]*?)<\/table>\s*<\/div>/gi,
      (block, cls, inner) => {
        if (isKvTableHtml(inner)) {
          return block.replace('class="md-table', 'class="md-table md-kv-table');
        }
        return block;
      },
    );
  }

  /** Turn consecutive pipe-only lines (no GFM separator) into proper tables. */
  function repairLoosePipeTableRows(markdown) {
    const lines = String(markdown).split('\n');
    const out = [];
    let i = 0;
    while (i < lines.length) {
      const trimmed = (lines[i] || '').trim();
      if (!isCompleteTableRow(trimmed) || isTableBlockStart(lines, i)) {
        out.push(lines[i]);
        i += 1;
        continue;
      }
      const rows = [];
      let j = i;
      while (j < lines.length) {
        const t = (lines[j] || '').trim();
        if (!t) break;
        if (isTableBlockStart(lines, j)) break;
        if (!isCompleteTableRow(t) || isTableSepLine(t)) break;
        let cells = compactRowCells(parseTableRow(t));
        if (cells.length === 3 && !cells[1]) cells = [cells[0], cells[2]];
        if (cells.length >= 2) rows.push(cells);
        j += 1;
      }
      if (rows.length >= 1) {
        const cols = Math.max(...rows.map((r) => r.length));
        const headers = cols === 2
          ? ['项目', '返回值']
          : cols === 3
            ? ['项目', '返回值', '说明']
            : Array.from({ length: cols }, (_, idx) => `列${idx + 1}`);
        out.push(`| ${headers.slice(0, cols).join(' | ')} |`);
        out.push(`| ${Array(cols).fill('---').join(' | ')} |`);
        for (const row of rows) {
          const cells = [...row];
          while (cells.length < cols) cells.push('');
          out.push(`| ${cells.slice(0, cols).join(' | ')} |`);
        }
        out.push('');
        i = j;
        continue;
      }
      out.push(lines[i]);
      i += 1;
    }
    return out.join('\n');
  }

  function repairStreamingTail(markdown) {
    let s = String(markdown || '');
    const fenceCount = (s.match(/```/g) || []).length;
    if (fenceCount % 2 === 1) s += '\n```';
    const lines = s.split('\n');
    const last = lines[lines.length - 1] || '';
    if (last.includes('|') && !last.trim().endsWith('|') && !last.trim().startsWith('```')) {
      lines[lines.length - 1] = `${last.trim()} |`;
      s = lines.join('\n');
    }
    return s;
  }

  function promoteChatSectionHeadlines(markdown) {
    const emojiLead = /^(?:[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}]|[\uD83C-\uDBFF][\uDC00-\uDFFF])/u;
    return String(markdown).split('\n').map((line) => {
      const t = line.trim();
      if (!t || t.includes('|') || /^#{1,6}\s/.test(t) || /^[-*]\s/.test(t) || /^\d+\.\s/.test(t)) return line;
      if (/^[0-9]{1,2}️⃣\s+\S/.test(t) && t.length <= 120) return `#### ${t}`;
      if (emojiLead.test(t) && t.length <= 48 && !/[。！？.!?]$/.test(t)) return `### ${t}`;
      return line;
    }).join('\n');
  }

  /** OpenClaw-style: minimal normalize — preserve block structure for GFM tables. */
  function normalizeMarkdownInput(markdown) {
    let s = String(markdown || '').replace(/\r\n/g, '\n');
    if (!s.trim()) return '';

    s = repairTrailingEmDash(s);

    s = s.replace(/(#{1,6})([^\s#\n|])/g, '$1 $2');
    s = s.replace(/([^\n#])\s*(#{1,3}\s+)/g, '$1\n\n$2');
    s = s.replace(/(#{1,3}\s+)([^|\n]+?)(\|)/g, '$1$2\n\n$3');
    s = s.replace(/^([^|\n#][^|\n]{0,120}?)\s+(\|[^|\n]+\|)/gm, '$1\n\n$2');

    const lines = [];
    for (const line of s.split('\n')) {
      for (const part of splitGluedPipeRows(line).split('\n')) lines.push(part);
    }
    s = lines.join('\n');

    s = repairDashSeparatedTables(s);
    s = repairMissingTableSeparators(s);
    s = repairFragmentedTableRows(s);
    s = collapseTableBlocks(s);
    s = repairSeparatorLines(s);
    s = ensureTableBlockSpacing(s);
    s = s.replace(/^(#{1,3}\s+[^\n]+)\n(\|)/gm, '$1\n\n$2');
    s = promoteChatSectionHeadlines(s);

    return s;
  }

  function inlineFormat(text) {
    return String(text)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`([^`\n]+)`/g, (_, code) => `<code>${escapeHtml(code)}</code>`)
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, url) => {
        const safe = /^https?:|^mailto:/i.test(url.trim()) ? url.trim() : '#';
        return `<a href="${escapeHtml(safe)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`;
      });
  }

  function renderLiteTable(rows) {
    if (!rows || rows.length < 2) return '';
    const parts = ['<div class="md-table-wrap"><table class="md-table">'];
    let headerDone = false;
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i].trim();
      if (!row) continue;
      const isSep = /^\s*\|[\s\-:|]+\|\s*$/.test(row) || /^\s*[\-:]+(\s*\|\s*[\-:]+)+\s*$/.test(row);
      if (isSep) {
        headerDone = true;
        continue;
      }
      let cells = [];
      if (row.startsWith('|') && row.endsWith('|')) cells = row.slice(1, -1).split('|');
      else cells = row.split('|');
      cells = cells.map((c) => inlineFormat(c.trim()));
      if (!cells.length) continue;
      const tag = !headerDone ? 'th' : 'td';
      parts.push('<tr>');
      for (const cell of cells) parts.push(`<${tag}>${cell}</${tag}>`);
      parts.push('</tr>');
      if (!headerDone && i + 1 < rows.length) {
        const next = rows[i + 1].trim();
        if (/^\s*\|[\s\-:|]+\|\s*$/.test(next)) headerDone = true;
      }
    }
    parts.push('</table></div>');
    return parts.join('');
  }

  /** ClawPanel-style fallback when markdown-it is unavailable. */
  function renderLite(markdown) {
    const text = normalizeMarkdownInput(markdown);
    if (!text.trim()) return '';

    let html = text.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
      const highlighted = highlightCode(code.trimEnd(), lang);
      const langLabel = lang ? `<span class="md-code-lang">${escapeHtml(lang)}</span>` : '';
      const encoded = encodeURIComponent(code.trimEnd());
      return `<div class="md-code-wrap"><div class="md-code-head">${langLabel}<button type="button" class="md-code-copy" data-code="${encoded}">复制</button></div><pre class="md-pre"><code>${highlighted}</code></pre></div>`;
    });

    const lines = html.split('\n');
    const out = [];
    let inList = false;
    let listType = '';
    let tableRows = [];
    let inTable = false;

    function flushTable() {
      if (!tableRows.length) return;
      out.push(renderLiteTable(tableRows));
      tableRows = [];
      inTable = false;
    }

    for (let i = 0; i < lines.length; i++) {
      let line = lines[i];
      if (line.startsWith('<div class="md-code-wrap"')) {
        flushTable();
        if (inList) { out.push(`</${listType}>`); inList = false; }
        out.push(line);
        while (i < lines.length - 1 && !lines[i].includes('</pre></div>')) { i += 1; out.push(lines[i]); }
        continue;
      }

      const isTableRow = /^\s*\|.*\|\s*$/.test(line) || /^\s*[^\|]+\s*\|\s*[^\|]+/.test(line);
      const nextSep = i + 1 < lines.length && (/^\s*\|[\s\-:|]+\|\s*$/.test(lines[i + 1]) || /^\s*[\-:]+(\s*\|\s*[\-:]+)+\s*$/.test(lines[i + 1]));

      if (inTable) {
        if (isTableRow && line.trim()) {
          tableRows.push(line);
          continue;
        }
        flushTable();
      } else if (isTableRow && nextSep) {
        if (inList) { out.push(`</${listType}>`); inList = false; }
        inTable = true;
        tableRows.push(line);
        continue;
      }

      const heading = line.match(/^(#{1,4})\s+(.+)$/);
      if (heading) {
        flushTable();
        if (inList) { out.push(`</${listType}>`); inList = false; }
        const level = Math.min(4, heading[1].length);
        out.push(`<h${level}>${inlineFormat(heading[2])}</h${level}>`);
        continue;
      }

      const ul = line.match(/^[\s]*[-*]\s+(.+)$/);
      if (ul) {
        flushTable();
        if (!inList || listType !== 'ul') {
          if (inList) out.push(`</${listType}>`);
          out.push('<ul>'); inList = true; listType = 'ul';
        }
        out.push(`<li>${inlineFormat(ul[1])}</li>`);
        continue;
      }

      const ol = line.match(/^[\s]*\d+\.\s+(.+)$/);
      if (ol) {
        flushTable();
        if (!inList || listType !== 'ol') {
          if (inList) out.push(`</${listType}>`);
          out.push('<ol>'); inList = true; listType = 'ol';
        }
        out.push(`<li>${inlineFormat(ol[1])}</li>`);
        continue;
      }

      if (inList) { out.push(`</${listType}>`); inList = false; }
      if (!line.trim()) { out.push(''); continue; }
      if (!line.startsWith('<')) out.push(`<p>${inlineFormat(line)}</p>`);
      else out.push(line);
    }

    if (inList) out.push(`</${listType}>`);
    flushTable();
    return out.join('\n');
  }

  function highlightCode(text, lang) {
    const hljs = global.hljs;
    if (!hljs) return escapeHtml(text);
    try {
      const language = String(lang || '').trim().toLowerCase();
      if (language && hljs.getLanguage(language)) {
        return hljs.highlight(text, { language, ignoreIllegals: true }).value;
      }
      if (!language && text.trim() && hljs.highlightAuto) {
        const result = hljs.highlightAuto(text);
        if (result.relevance >= 2) return result.value;
      }
    } catch (_) { /* ignore */ }
    return escapeHtml(text);
  }

  let mdInstance = null;

  function getMarkdownIt() {
    if (mdInstance) return mdInstance;
    if (!global.OpMarkdown || typeof global.OpMarkdown.createMarkdownIt !== 'function') return null;
    const md = global.OpMarkdown.createMarkdownIt();

    const origTableOpen = md.renderer.rules.table_open || ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options));
    md.renderer.rules.table_open = (tokens, idx, options, env, self) => {
      tokens[idx].attrJoin('class', 'md-table');
      return `<div class="md-table-wrap">${origTableOpen(tokens, idx, options, env, self)}`;
    };
    const origTableClose = md.renderer.rules.table_close || ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options));
    md.renderer.rules.table_close = (tokens, idx, options, env, self) => `${origTableClose(tokens, idx, options, env, self)}</div>`;

    md.renderer.rules.fence = (tokens, idx) => {
      const token = tokens[idx];
      const lang = token.info ? token.info.trim().split(/\s+/)[0] : '';
      const code = token.content.endsWith('\n') ? token.content.slice(0, -1) : token.content;
      const highlighted = highlightCode(code, lang);
      const hljsClass = highlighted.includes('hljs-') ? 'hljs ' : '';
      const langClass = lang ? `language-${escapeHtml(lang)} ` : '';
      const langLabel = lang ? `<span class="md-code-lang">${escapeHtml(lang)}</span>` : '';
      const encoded = encodeURIComponent(code);
      return `<div class="md-code-wrap">${langLabel || encoded ? `<div class="md-code-head">${langLabel}<button type="button" class="md-code-copy" data-code="${encoded}">复制</button></div>` : ''}<pre class="md-pre"><code class="${hljsClass}${langClass}">${highlighted}</code></pre></div>`;
    };

    const origLinkOpen = md.renderer.rules.link_open || ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options));
    md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
      const token = tokens[idx];
      if (token.attrIndex('target') < 0) token.attrPush(['target', '_blank']);
      if (token.attrIndex('rel') < 0) token.attrPush(['rel', 'noopener noreferrer']);
      return origLinkOpen(tokens, idx, options, env, self);
    };

    mdInstance = md;
    return md;
  }

  function sanitizeHtml(html) {
    if (!html) return '';
    const purify = global.DOMPurify;
    if (!purify || typeof purify.sanitize !== 'function') return html;
    return purify.sanitize(html, {
      ALLOWED_TAGS,
      ALLOWED_ATTR,
      ADD_TAGS: ['input'],
    });
  }

  function renderMarkdownHtml(markdown, options) {
    const streaming = Boolean(options && options.streaming);
    let input = normalizeMarkdownInput(markdown);
    if (streaming) input = repairStreamingTail(input);
    if (!input.trim()) return '';

    const md = getMarkdownIt();
    if (md) {
      try {
        let html = sanitizeHtml(md.render(input));
        if (looksLikeMarkdownTable(input) && !html.includes('<table')) {
          const loose = repairLoosePipeTableRows(input);
          if (loose !== input) {
            html = sanitizeHtml(md.render(ensureTableBlockSpacing(loose)));
          } else {
            html = sanitizeHtml(renderLite(input));
          }
        }
        return wrapMarkdownTables(tagKvTables(html));
      } catch (err) {
        console.warn('[markdown] markdown-it failed, using lite renderer:', err);
      }
    }
    return wrapMarkdownTables(tagKvTables(sanitizeHtml(renderLite(input))));
  }

  function render(markdown) {
    return renderMarkdownHtml(markdown);
  }

  function renderNormalized(markdown, options) {
    return renderMarkdownHtml(markdown, options);
  }

  /** Stream: normalize + repair tail, then render. */
  function toStreamingHtml(markdown) {
    return renderNormalized(markdown, { streaming: true });
  }

  function findStableStreamingMarkdownBoundary(markdown) {
    const input = String(markdown || '');
    return input.length;
  }

  function renderToElement(el, markdown, options) {
    if (!el) return;
    const text = String(markdown || '');
    const streaming = Boolean(options && options.streaming);
    if (!text.trim()) {
      el.textContent = '';
      return;
    }
    el.classList.add('md-content', 'chat-text');
    let html = renderNormalized(text, { streaming });
    if (streaming && options?.cursor !== false) {
      html += '<span class="md-stream-cursor" aria-hidden="true">▊</span>';
    }
    el.innerHTML = html;
  }

  function bindCopyButtons(root) {
    if (!root || root.dataset.mdCopyBound === '1') return;
    root.dataset.mdCopyBound = '1';
    root.addEventListener('click', (e) => {
      const btn = e.target.closest('.md-code-copy');
      if (!btn) return;
      e.preventDefault();
      let code = '';
      try {
        code = decodeURIComponent(btn.getAttribute('data-code') || '');
      } catch (_) {
        code = btn.getAttribute('data-code') || '';
      }
      if (!code) return;
      const done = () => {
        const prev = btn.textContent;
        btn.textContent = '已复制';
        setTimeout(() => { btn.textContent = prev; }, 1200);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(code).then(done).catch(() => {});
      }
    });
  }

  global.Markdown = {
    render,
    escapeHtml,
    normalizeMarkdownInput,
    renderToElement,
    toStreamingHtml,
    findStableStreamingMarkdownBoundary,
    formatReasoningMarkdown,
    bindCopyButtons,
    VERSION: '20260820d',
  };

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => bindCopyButtons(document.getElementById('messages')));
    } else {
      bindCopyButtons(document.getElementById('messages'));
    }
  }
})(typeof window !== 'undefined' ? window : globalThis);
