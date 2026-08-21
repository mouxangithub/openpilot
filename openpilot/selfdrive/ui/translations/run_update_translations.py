#!/usr/bin/env python3
"""Standalone translation updater — runs without full openpilot package install."""
import json
import os
import sys

BASEDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, BASEDIR)

from selfdrive.ui.translations.potools import extract_strings, generate_pot, merge_po, init_po  # noqa: E402

TRANSLATIONS_DIR = os.path.join(BASEDIR, "selfdrive", "ui", "translations")
POT_FILE = os.path.join(TRANSLATIONS_DIR, "app.pot")
LANGUAGES_FILE = os.path.join(TRANSLATIONS_DIR, "languages.json")

SCAN_DIRS = [
  os.path.join(BASEDIR, "system", "ui"),
  os.path.join(BASEDIR, "system", "ui", "sunnypilot"),
  os.path.join(BASEDIR, "selfdrive", "ui", "widgets"),
  os.path.join(BASEDIR, "selfdrive", "ui", "layouts"),
  os.path.join(BASEDIR, "selfdrive", "ui", "onroad"),
  os.path.join(BASEDIR, "selfdrive", "ui", "mici"),
  os.path.join(BASEDIR, "selfdrive", "ui", "sunnypilot"),
]


def main():
  files = []
  for root_dir in SCAN_DIRS:
    if not os.path.isdir(root_dir):
      continue
    for root, _, filenames in os.walk(root_dir):
      for filename in filenames:
        if filename.endswith(".py"):
          files.append(os.path.relpath(os.path.join(root, filename), BASEDIR))

  entries = extract_strings(sorted(set(files)), BASEDIR)
  generate_pot(entries, POT_FILE)
  print(f"Generated {POT_FILE} with {len(entries)} entries")

  with open(LANGUAGES_FILE, encoding="utf-8") as f:
    languages = json.load(f)

  for name in languages.values():
    po_file = os.path.join(TRANSLATIONS_DIR, f"app_{name}.po")
    if os.path.exists(po_file):
      merge_po(po_file, POT_FILE)
    else:
      init_po(POT_FILE, po_file, name)
    print(f"Updated {po_file}")


if __name__ == "__main__":
  main()
