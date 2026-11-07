#!/usr/bin/env node
/**
 * Fetch commaai/openpilot GitHub wiki (raw markdown) and emit wiki_rag_pages.py
 * Usage: node ai/scripts/fetch_op_wiki_rag.mjs > ai/tools/wiki_rag_pages.py
 */
const BASE = 'https://raw.githubusercontent.com/wiki/commaai/openpilot';

const PAGES = [
  'Home',
  'FAQ',
  'Troubleshooting',
  'SSH',
  'Tuning',
  'Development',
  'Installing-openpilot',
  'Installation-Guides',
  'General-Terms',
  'comma-three',
  'Cabana',
  'OpenDBC',
  'Honda-Acura',
  'Toyota-Lexus',
  'Ford',
  'GM',
  'FCA',
  'Hyundai-Kia-Genesis',
  'Volkswagen-Audi-Porsche',
  'Subaru',
  'Nissan-Infiniti',
  'Mazda',
  'Volvo',
  'Rivian',
  'comma-body',
];

const MAX_CHUNK = 2200;

function slug(s) {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
}

function stripMd(md) {
  return md
    .replace(/!\[[^\]]*\]\([^)]+\)/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/```[\s\S]*?```/g, (m) => m.replace(/```\w*\n?/g, '').replace(/```/g, ''))
    .replace(/^#+\s*/gm, '')
    .replace(/[*_`]/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function chunkText(text, pageSlug) {
  const parts = text.split(/\n(?=## )/);
  const chunks = [];
  let buf = '';
  let idx = 0;
  const flush = () => {
    const t = buf.trim();
    if (!t) return;
    chunks.push({ id: `builtin_wiki_${pageSlug}_${idx}`, text: t });
    idx += 1;
    buf = '';
  };
  for (const part of parts) {
    if ((buf + '\n' + part).length > MAX_CHUNK && buf) flush();
    if (part.length > MAX_CHUNK) {
      flush();
      let start = 0;
      while (start < part.length) {
        chunks.push({
          id: `builtin_wiki_${pageSlug}_${idx}`,
          text: part.slice(start, start + MAX_CHUNK).trim(),
        });
        idx += 1;
        start += MAX_CHUNK;
      }
    } else {
      buf = buf ? `${buf}\n${part}` : part;
      if (buf.length >= MAX_CHUNK) flush();
    }
  }
  flush();
  return chunks;
}

async function fetchPage(name) {
  const url = `${BASE}/${name}.md`;
  const res = await fetch(url, { headers: { 'User-Agent': 'op-assistant-wiki-rag/1.0' } });
  if (!res.ok) return null;
  return res.text();
}

async function main() {
  const docs = [];
  for (const page of PAGES) {
    const raw = await fetchPage(page);
    if (!raw || raw.length < 80) continue;
    const pageSlug = slug(page);
    const plain = stripMd(raw);
    const titleBase = page.replace(/-/g, ' ');
    const chunks = chunkText(plain, pageSlug);
    const sourceUrl = `https://github.com/commaai/openpilot/wiki/${page}`;
    chunks.forEach((c, i) => {
      docs.push({
        id: c.id,
        title: chunks.length > 1 ? `Wiki: ${titleBase} (${i + 1}/${chunks.length})` : `Wiki: ${titleBase}`,
        tags: ['wiki', 'openpilot', 'comma', pageSlug.split('_')[0]],
        refresh: false,
        text: `Source: openpilot Wiki — ${titleBase}\n${sourceUrl}\n\n${c.text}`,
      });
    });
    process.stderr.write(`ok ${page} -> ${chunks.length} chunk(s)\n`);
  }

  const lines = [];
  lines.push('"""Auto-generated openpilot Wiki RAG chunks. Run fetch_op_wiki_rag.mjs to refresh."""');
  lines.push('');
  lines.push('from __future__ import annotations');
  lines.push('');
  lines.push('from typing import Any');
  lines.push('');
  lines.push('WIKI_RAG_PAGES: list[dict[str, Any]] = [');
  for (const d of docs) {
    const text = d.text.replace(/\\/g, '\\\\').replace(/"""/g, '\\"\\"\\"');
    const tags = JSON.stringify(d.tags);
    lines.push('  {');
    lines.push(`    "id": ${JSON.stringify(d.id)},`);
    lines.push(`    "title": ${JSON.stringify(d.title)},`);
    lines.push(`    "tags": ${tags},`);
    lines.push('    "refresh": False,');
    lines.push(`    "text": """${text}""",`);
    lines.push('  },');
  }
  lines.push(']');
  lines.push('');

  const outPath = process.argv[2] || 'ai/tools/wiki_rag_pages.py';
  const fs = await import('node:fs');
  fs.writeFileSync(outPath, lines.join('\n'), 'utf8');
  process.stderr.write(`\nWrote ${docs.length} docs -> ${outPath}\n`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
