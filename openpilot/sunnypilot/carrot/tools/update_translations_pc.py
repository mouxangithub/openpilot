#!/usr/bin/env python3
"""PC-side driver for update_translations.py without the device runtime.

update_translations.py imports multilang, which pulls swaglog -> zmq and dies on
Windows. This replicates its exact file set and calls the same potools functions.
"""
import os
import sys

BASEDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, BASEDIR)

from openpilot.selfdrive.ui.translations.potools import extract_strings, generate_pot, merge_po

TRANSLATIONS_DIR = os.path.join(BASEDIR, "openpilot", "selfdrive", "ui", "translations")
POT_FILE = os.path.join(TRANSLATIONS_DIR, "app.pot")


def main() -> int:
  ui_dir = os.path.join(BASEDIR, "openpilot", "selfdrive", "ui")
  files = []
  roots = [
    os.path.join(BASEDIR, "openpilot", "system", "ui"),
    ui_dir,
    os.path.join(BASEDIR, "openpilot", "selfdrive", "selfdrived"),
    os.path.join(BASEDIR, "openpilot", "sunnypilot", "selfdrive", "selfdrived"),
  ]
  for root in roots:
    for dirpath, _, filenames in os.walk(root):
      for filename in filenames:
        if filename.endswith(".py"):
          files.append(os.path.relpath(os.path.join(dirpath, filename), BASEDIR))

  entries = extract_strings(sorted(set(files)), BASEDIR)
  generate_pot(entries, POT_FILE)

  for name in os.listdir(TRANSLATIONS_DIR):
    if name.startswith("app_") and name.endswith(".po"):
      merge_po(os.path.join(TRANSLATIONS_DIR, name), POT_FILE)
      print("merged", name)
  print(f"pot: {len(entries)} strings")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
