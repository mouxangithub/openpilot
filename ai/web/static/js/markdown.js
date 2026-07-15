/**
 * Lightweight Markdown → HTML for op助手 chat (offline-safe, no CDN).
 */
(function (global) {
  'use strict';

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function inlineFormat(text) {
    let s = escapeHtml(text);
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    return s;
  }

  function isTableRow(line) {
    return /^\s*\|.+\|\s*$/.test(line);
  }

  function isTableSep(line) {
    return /^\s*\|?[\s:-]+\|[\s|:-]+\|?\s*$/.test(line);
  }

  function parseTableRow(line) {
    return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
  }

  function renderTable(lines) {
    const header = parseTableRow(lines[0]);
    const bodyLines = lines.slice(2);
    let html = '<div class="md-table-wrap"><table class="md-table"><thead><tr>';
    for (const cell of header) {
      html += `<th>${inlineFormat(cell)}</th>`;
    }
    html += '</tr></thead><tbody>';
    for (const line of bodyLines) {
      if (!isTableRow(line)) continue;
      const cells = parseTableRow(line);
      html += '<tr>';
      for (const cell of cells) {
        html += `<td>${inlineFormat(cell)}</td>`;
      }
      html += '</tr>';
    }
    html += '</tbody></table></div>';
    return html;
  }

  function render(markdown) {
    if (!markdown) return '';
    const lines = String(markdown).replace(/\r\n/g, '\n').split('\n');
    const out = [];
    let i = 0;
    let inCode = false;
    let codeBuf = [];
    let listType = null;

    function flushList() {
      if (!listType) return;
      out.push(listType === 'ol' ? '</ol>' : '</ul>');
      listType = null;
    }

    while (i < lines.length) {
      const line = lines[i];

      if (line.trim().startsWith('```')) {
        flushList();
        if (!inCode) {
          inCode = true;
          codeBuf = [];
        } else {
          inCode = false;
          out.push(`<pre class="md-pre"><code>${escapeHtml(codeBuf.join('\n'))}</code></pre>`);
          codeBuf = [];
        }
        i += 1;
        continue;
      }

      if (inCode) {
        codeBuf.push(line);
        i += 1;
        continue;
      }

      if (isTableRow(line) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
        flushList();
        const tableLines = [line, lines[i + 1]];
        i += 2;
        while (i < lines.length && isTableRow(lines[i])) {
          tableLines.push(lines[i]);
          i += 1;
        }
        out.push(renderTable(tableLines));
        continue;
      }

      const h3 = line.match(/^###\s+(.+)$/);
      const h2 = line.match(/^##\s+(.+)$/);
      const h1 = line.match(/^#\s+(.+)$/);
      if (h3 || h2 || h1) {
        flushList();
        const level = h3 ? 3 : h2 ? 2 : 1;
        const text = (h3 || h2 || h1)[1];
        out.push(`<h${level} class="md-h${level}">${inlineFormat(text)}</h${level}>`);
        i += 1;
        continue;
      }

      const ul = line.match(/^\s*[-*]\s+(.+)$/);
      const ol = line.match(/^\s*\d+\.\s+(.+)$/);
      if (ul || ol) {
        const type = ol ? 'ol' : 'ul';
        const text = (ul || ol)[1];
        if (listType !== type) {
          flushList();
          listType = type;
          out.push(type === 'ol' ? '<ol class="md-list">' : '<ul class="md-list">');
        }
        out.push(`<li>${inlineFormat(text)}</li>`);
        i += 1;
        continue;
      }

      if (line.trim() === '') {
        flushList();
        i += 1;
        continue;
      }

      flushList();
      out.push(`<p>${inlineFormat(line)}</p>`);
      i += 1;
    }

    flushList();
    if (inCode && codeBuf.length) {
      out.push(`<pre class="md-pre"><code>${escapeHtml(codeBuf.join('\n'))}</code></pre>`);
    }
    return out.join('\n');
  }

  global.Markdown = { render, escapeHtml };
})(typeof window !== 'undefined' ? window : globalThis);
