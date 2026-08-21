#!/usr/bin/env python3
"""Fill remaining empty translations for ja/ko/th using Google Translate with resume cache."""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

BASEDIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BASEDIR))

from deep_translator import GoogleTranslator  # noqa: E402
from selfdrive.ui.translations.potools import parse_po, write_po  # noqa: E402

TRANSLATIONS_DIR = BASEDIR / "selfdrive" / "ui" / "translations"
CACHE_FILE = TRANSLATIONS_DIR / ".translate_cache.json"

LANG_TARGETS = {
  "ja": "ja",
  "ko": "ko",
  "th": "th",
}

PLACEHOLDER_RE = re.compile(r"(\{\}|\{[^{}]+\}|%[sn]|\{:\.\d+f\}|\{:\d+d\})")
PROTECTED_TERMS = (
  "sunnypilot", "openpilot", "sunnylink", "sunnyhaibin", "comma", "GitHub",
  "Wi-Fi", "WiFi", "OSM", "MADS", "SCC-V", "SCC-M", "N·dm", "m/s^2",
  "ETH", "LTE", "2G", "3G", "5G", "PANDA", "MB", "GB", "km/h", "mph",
)


def load_cache() -> dict[str, dict[str, str]]:
  if CACHE_FILE.exists():
    return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
  return {}


def save_cache(cache: dict[str, dict[str, str]]) -> None:
  CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def protect(text: str) -> tuple[str, dict[str, str]]:
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


def restore(text: str, tokens: dict[str, str]) -> str:
  for key, value in tokens.items():
    text = text.replace(key, value)
  return text


def translate_one(text: str, target: str, cache: dict[str, str]) -> str:
  if not text.strip():
    return text
  if text in cache:
    return cache[text]

  protected, tokens = protect(text)
  for attempt in range(5):
    try:
      translator = GoogleTranslator(source="en", target=target)
      result = translator.translate(protected)
      if result:
        translated = restore(result, tokens)
        cache[text] = translated
        return translated
    except Exception:
      time.sleep(1.5 * (attempt + 1))
  cache[text] = text
  return text


SKIP_IDENTICAL = {
  "%", "--", "---", "2G", "3G", "5G", "ETH", "GB", "LTE", "MB", "N·dm", "PANDA",
  "SCC-M", "SCC-V", "km/h", "mph", "m", "ft", "mi", "km", "s", "{} %", "{} s",
  "m/s^2", "N", "NE", "E", "SE", "S", "SW", "W", "NW", "OFF", "OFF | -",
  "comma prime", "sunnylink", "m/s^2",
}


def needs_translation(entry) -> bool:
  if entry.is_plural:
    return False
  if not entry.msgstr:
    return True
  if entry.msgid in SKIP_IDENTICAL:
    return False
  return entry.msgstr == entry.msgid and len(entry.msgid) > 2


def fill_language(lang: str, cache: dict[str, dict[str, str]]) -> int:
  po_path = TRANSLATIONS_DIR / f"app_{lang}.po"
  header, entries = parse_po(po_path)
  lang_cache = cache.setdefault(lang, {})
  target = LANG_TARGETS[lang]
  filled = 0
  pending = [e for e in entries if needs_translation(e)]
  total = len(pending)

  for entry in pending:
    # Drop stale English cache entries so we can retranslate.
    if entry.msgid in lang_cache and lang_cache[entry.msgid] == entry.msgid:
      del lang_cache[entry.msgid]
    entry.msgstr = translate_one(entry.msgid, target, lang_cache)
    filled += 1
    if filled % 25 == 0:
      save_cache(cache)
      write_po(po_path, header, entries)
      print(f"  {lang}: {filled}/{total}", flush=True)
    time.sleep(0.12)

  write_po(po_path, header, entries)
  save_cache(cache)
  return filled


def main():
  langs = sys.argv[1:] or list(LANG_TARGETS.keys())
  cache = load_cache()
  for lang in langs:
    if lang not in LANG_TARGETS:
      print(f"skip unknown language: {lang}")
      continue
    print(f"filling {lang}...")
    count = fill_language(lang, cache)
    print(f"{lang}: filled {count}")
  save_cache(cache)


if __name__ == "__main__":
  main()
