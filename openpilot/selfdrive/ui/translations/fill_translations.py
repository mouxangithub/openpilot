#!/usr/bin/env python3
"""Fill empty .po translations using openpilot reference + machine translation."""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

BASEDIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BASEDIR))

from deep_translator import GoogleTranslator, MyMemoryTranslator  # noqa: E402
from selfdrive.ui.translations.potools import parse_po, write_po  # noqa: E402

TRANSLATIONS_DIR = BASEDIR / "selfdrive" / "ui" / "translations"
OP_TRANSLATIONS_DIR = Path("E:/openpilot/selfdrive/ui/translations")

LANG_TARGETS = {
  "de": ("de", "de-DE"),
  "fr": ("fr", "fr-FR"),
  "pt-BR": ("pt", "pt-BR"),
  "es": ("es", "es-ES"),
  "tr": ("tr", "tr-TR"),
  "uk": ("uk", "uk-UA"),
  "th": ("th", "th-TH"),
  "zh-CHS": ("zh-CN", "zh-CN"),
  "zh-CHT": ("zh-TW", "zh-TW"),
  "ko": ("ko", "ko-KR"),
  "ja": ("ja", "ja-JP"),
}

PLACEHOLDER_RE = re.compile(r"(\{\}|%[sn]|\{[^{}]+\})")
PROTECTED_TERMS = (
  "sunnypilot", "openpilot", "sunnylink", "sunnyhaibin", "comma", "GitHub",
  "Wi-Fi", "WiFi", "OSM", "MADS", "SCC-V", "SCC-M", "N·dm", "m/s^2",
)


def _protect(text: str) -> tuple[str, dict[str, str]]:
  tokens: dict[str, str] = {}
  idx = 0

  def repl(match: re.Match) -> str:
    nonlocal idx
    key = f"__PH{idx}__"
    tokens[key] = match.group(0)
    idx += 1
    return key

  protected = PLACEHOLDER_RE.sub(repl, text)
  for term in PROTECTED_TERMS:
    if term in protected:
      key = f"__TERM{idx}__"
      tokens[key] = term
      protected = protected.replace(term, key)
      idx += 1
  return protected, tokens


def _restore(text: str, tokens: dict[str, str]) -> str:
  for key, value in tokens.items():
    text = text.replace(key, value)
  return text


def translate_text(text: str, google_target: str, mymemory_target: str) -> str:
  if not text.strip():
    return text
  protected, tokens = _protect(text)
  for translator_cls, target in ((GoogleTranslator, google_target), (MyMemoryTranslator, mymemory_target)):
    try:
      translator = translator_cls(source="en", target=target)
      translated = translator.translate(protected)
      if translated:
        return _restore(translated, tokens)
    except Exception:
      time.sleep(0.5)
      continue
  return text


def load_op_map(lang: str) -> dict[str, str]:
  op_po = OP_TRANSLATIONS_DIR / f"app_{lang}.po"
  if not op_po.exists():
    return {}
  _, entries = parse_po(op_po)
  return {e.msgid: e.msgstr for e in entries if e.msgstr and not e.is_plural}


def fill_language(lang: str) -> int:
  po_path = TRANSLATIONS_DIR / f"app_{lang}.po"
  header, entries = parse_po(po_path)
  op_map = load_op_map(lang)
  filled = 0

  if lang == "en":
    for entry in entries:
      if entry.is_plural or entry.msgstr:
        continue
      entry.msgstr = entry.msgid
      filled += 1
    write_po(po_path, header, entries)
    return filled

  google_target, mymemory_target = LANG_TARGETS[lang]
  cache: dict[str, str] = {}

  for entry in entries:
    if entry.is_plural or entry.msgstr:
      continue
    if entry.msgid in op_map:
      entry.msgstr = op_map[entry.msgid]
      filled += 1
      continue
    if entry.msgid in cache:
      entry.msgstr = cache[entry.msgid]
      filled += 1
      continue
    entry.msgstr = translate_text(entry.msgid, google_target, mymemory_target)
    cache[entry.msgid] = entry.msgstr
    filled += 1
    time.sleep(0.1)

  write_po(po_path, header, entries)
  return filled


def main():
  langs = sys.argv[1:] or list(LANG_TARGETS.keys()) + ["en"]
  for lang in langs:
    count = fill_language(lang)
    print(f"{lang}: filled {count}")


if __name__ == "__main__":
  main()
