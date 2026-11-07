#!/usr/bin/env node
/**
 * Fetch SecOC reference repos into secoc_rag_pages.py
 * - https://github.com/optskug/docs
 * - https://github.com/lochuan/RH850_P1m-E
 *
 * Usage: node ai/scripts/fetch_secoc_rag.mjs [output.py]
 */
const MAX_CHUNK = 2200;

const SOURCES = [
  { repo: 'optskug/docs', branch: 'main', path: 'README.md', title: 'optskug SecOC Setup Guide', tags: ['secoc', 'optskug', 'toyota', 'setup'] },
  { repo: 'optskug/docs', branch: 'main', path: 'archive/auth_not_enc.md', title: 'optskug: auth_not_enc', tags: ['secoc', 'optskug', 'archive'] },
  { repo: 'optskug/docs', branch: 'main', path: 'archive/can_bus.md', title: 'optskug: CAN bus notes', tags: ['secoc', 'optskug', 'can', 'archive'] },
  { repo: 'optskug/docs', branch: 'main', path: 'archive/dump_milestone.md', title: 'optskug: dump milestone', tags: ['secoc', 'optskug', 'dataflash', 'archive'] },
  { repo: 'optskug/docs', branch: 'main', path: 'archive/rav4_prime_replace_rack.md', title: 'optskug: RAV4 Prime rack', tags: ['secoc', 'optskug', 'rav4', 'archive'] },
  { repo: 'optskug/docs', branch: 'main', path: 'archive/sienna_replace_rack.md', title: 'optskug: Sienna rack', tags: ['secoc', 'optskug', 'sienna', 'archive'] },
  { repo: 'lochuan/RH850_P1m-E', branch: 'main', path: 'README.md', title: 'RH850 P1m-E repo overview', tags: ['secoc', 'rh850', 'firmware'] },
  { repo: 'lochuan/RH850_P1m-E', branch: 'main', path: 'RESEARCH_REPORT_CN.md', title: 'RH850 SecOC 研究报告（中文）', tags: ['secoc', 'rh850', 'research', 'zh'] },
  { repo: 'lochuan/RH850_P1m-E', branch: 'main', path: 'RESEARCH_REPORT_EN.md', title: 'RH850 SecOC research report (EN)', tags: ['secoc', 'rh850', 'research', 'en'] },
  { repo: 'lochuan/RH850_P1m-E', branch: 'main', path: 'rekey-capture-design.md', title: 'RH850 rekey capture design', tags: ['secoc', 'rh850', 'rekey', 'capture'] },
];

function slug(s) {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 48);
}

function stripMd(md) {
  return md
    .replace(/!\[[^\]]*\]\([^)]+\)/g, '')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '$1 ($2)')
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
    chunks.push({ id: `builtin_secoc_${pageSlug}_${idx}`, text: t });
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
          id: `builtin_secoc_${pageSlug}_${idx}`,
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

async function fetchRaw(repo, branch, path) {
  const url = `https://raw.githubusercontent.com/${repo}/${branch}/${path}`;
  const res = await fetch(url, { headers: { 'User-Agent': 'op-assistant-secoc-rag/1.0' } });
  if (!res.ok) return null;
  return res.text();
}

async function main() {
  const docs = [];
  for (const src of SOURCES) {
    const raw = await fetchRaw(src.repo, src.branch, src.path);
    if (!raw || raw.length < 40) {
      process.stderr.write(`skip ${src.path} (empty or missing)\n`);
      continue;
    }
    const pageSlug = slug(`${src.repo}_${src.path}`);
    const plain = stripMd(raw);
    const chunks = chunkText(plain, pageSlug);
    const sourceUrl = `https://github.com/${src.repo}/blob/${src.branch}/${src.path}`;
    chunks.forEach((c, i) => {
      docs.push({
        id: c.id,
        title: chunks.length > 1 ? `${src.title} (${i + 1}/${chunks.length})` : src.title,
        tags: src.tags,
        refresh: false,
        text: `Source: ${src.repo} — ${src.path}\n${sourceUrl}\n\n${c.text}`,
      });
    });
    process.stderr.write(`ok ${src.repo}/${src.path} -> ${chunks.length} chunk(s)\n`);
  }

  const lines = [];
  lines.push('"""Auto-generated SecOC RAG chunks. Run fetch_secoc_rag.mjs to refresh."""');
  lines.push('');
  lines.push('from __future__ import annotations');
  lines.push('');
  lines.push('from typing import Any');
  lines.push('');
  lines.push('SECOC_RAG_PAGES: list[dict[str, Any]] = [');
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

  const outPath = process.argv[2] || 'ai/tools/secoc_rag_pages.py';
  const fs = await import('node:fs');
  fs.writeFileSync(outPath, lines.join('\n'), 'utf8');
  process.stderr.write(`\nWrote ${docs.length} docs -> ${outPath}\n`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
