#!/usr/bin/env python3
"""Merge WebUI-only i18n keys into openpilot app_*.po (shared with native GUI).

Usage (from repo root):
  py -3 webui/dev/sync_webui_i18n_to_po.py
  py -3 openpilot/selfdrive/ui/translations/fill_translations.py   # auto MT fill empty entries
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRANSLATIONS_DIR = ROOT / "openpilot" / "selfdrive" / "ui" / "translations"
SOURCE_REF = "webui/server/bridge/webui_i18n.py"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "openpilot"))

from selfdrive.ui.translations.potools import POEntry, parse_po, write_po  # noqa: E402
from webui.server.bridge.webui_i18n import _WEBUI_STRINGS  # noqa: E402

LOCALES = [
  "en", "de", "fr", "pt-BR", "es", "tr", "uk", "th", "zh-CHT", "zh-CHS", "ko", "ja",
]


def _seed_msgstr(po_code: str, msgid: str) -> str:
  manual = _WEBUI_STRINGS.get(po_code, {})
  if po_code == "en":
    return msgid
  val = manual.get(msgid, "").strip()
  if val and val != msgid:
    return manual[msgid]
  return ""


def sync_locale(po_code: str) -> tuple[int, int]:
  po_path = TRANSLATIONS_DIR / f"app_{po_code}.po"
  if not po_path.is_file():
    return 0, 0
  header, entries = parse_po(po_path)
  by_id = {e.msgid: e for e in entries}
  added = 0
  seeded = 0
  catalog = _WEBUI_STRINGS.get("en", {})

  for msgid in sorted(catalog):
    seed = _seed_msgstr(po_code, msgid)
    existing = by_id.get(msgid)
    if existing is None:
      entries.append(POEntry(
        msgid=msgid,
        msgstr=seed,
        source_refs=[SOURCE_REF],
        flags=["python-format"] if "{}" in msgid or "{" in msgid else [],
      ))
      added += 1
      if seed:
        seeded += 1
      continue
    if not (existing.msgstr or "").strip() and seed:
      existing.msgstr = seed
      seeded += 1
      if SOURCE_REF not in existing.source_refs:
        existing.source_refs.append(SOURCE_REF)

  entries.sort(key=lambda e: e.msgid)
  write_po(po_path, header, entries)
  return added, seeded


def main() -> None:
  if not TRANSLATIONS_DIR.is_dir():
    print(f"missing translations dir: {TRANSLATIONS_DIR}")
    sys.exit(1)
  total_add = total_seed = 0
  for po_code in LOCALES:
    added, seeded = sync_locale(po_code)
    total_add += added
    total_seed += seeded
    print(f"{po_code}: +{added} entries, seeded {seeded}")
  print(f"done — added {total_add}, pre-filled {total_seed}")
  print("Run fill_translations.py to machine-translate remaining empty msgstr entries.")


if __name__ == "__main__":
  main()
