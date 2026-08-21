#!/usr/bin/env python3
"""Extract UI strings and merge Chinese translations into po files."""
import os
from itertools import chain
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "openpilot"
TRANSLATIONS = ROOT / "selfdrive/ui/translations"
SYSTEM_UI_DIR = ROOT / "system/ui"
UI_DIR = ROOT / "selfdrive/ui"

# Import potools without openpilot package
import importlib.util
spec = importlib.util.spec_from_file_location("potools", TRANSLATIONS / "potools.py")
potools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(potools)

from supplement_zh_translations import ZH_CHS, ZH_CHT, apply_translations  # noqa: E402


def collect_files():
  files = []
  for root, _, filenames in chain(
    os.walk(SYSTEM_UI_DIR),
    os.walk(UI_DIR / "widgets"),
    os.walk(UI_DIR / "layouts"),
    os.walk(UI_DIR / "onroad"),
    os.walk(UI_DIR / "sunnypilot"),
  ):
    for filename in filenames:
      if filename.endswith(".py"):
        files.append(os.path.relpath(os.path.join(root, filename), ROOT))
  return files


def merge_and_translate():
  files = collect_files()
  entries = potools.extract_strings(files, str(ROOT))
  potools.generate_pot(entries, TRANSLATIONS / "app.pot")

  for lang, mapping in [("zh-CHS", ZH_CHS), ("zh-CHT", ZH_CHT)]:
    po_path = TRANSLATIONS / f"app_{lang}.po"
    potools.merge_po(po_path, TRANSLATIONS / "app.pot")
    _, po_entries = potools.parse_po(po_path)
    for e in po_entries:
      if e.msgid in mapping and mapping[e.msgid]:
        e.msgstr = mapping[e.msgid]
    potools.write_po(po_path, potools._build_po_header(lang), po_entries)
    print(f"{lang}: merged {len(entries)} template strings")


if __name__ == "__main__":
  merge_and_translate()
  apply_translations(TRANSLATIONS / "app_zh-CHS.po", ZH_CHS)
  apply_translations(TRANSLATIONS / "app_zh-CHT.po", ZH_CHT)
