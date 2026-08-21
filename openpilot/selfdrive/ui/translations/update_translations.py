#!/usr/bin/env python3
from itertools import chain
import os
from openpilot.common.basedir import BASEDIR
from openpilot.system.ui.lib.multilang import SYSTEM_UI_DIR, UI_DIR, TRANSLATIONS_DIR, multilang
from openpilot.selfdrive.ui.translations.potools import extract_strings, generate_pot, merge_po, init_po

LANGUAGES_FILE = os.path.join(str(TRANSLATIONS_DIR), "languages.json")
POT_FILE = os.path.join(str(TRANSLATIONS_DIR), "app.pot")


def update_translations():
  files = []
  scan_dirs = [
    SYSTEM_UI_DIR,
    os.path.join(UI_DIR, "widgets"),
    os.path.join(UI_DIR, "layouts"),
    os.path.join(UI_DIR, "onroad"),
    os.path.join(UI_DIR, "mici"),
    os.path.join(UI_DIR, "sunnypilot"),
    os.path.join(BASEDIR, "system", "ui", "sunnypilot"),
  ]
  for root_dir in scan_dirs:
    for root, _, filenames in os.walk(root_dir):
      for filename in filenames:
        if filename.endswith(".py"):
          files.append(os.path.relpath(os.path.join(root, filename), BASEDIR))

  # Extract translatable strings and generate .pot template
  entries = extract_strings(sorted(set(files)), BASEDIR)
  generate_pot(entries, POT_FILE)

  # Generate/update translation files for each language
  for name in multilang.languages.values():
    po_file = os.path.join(str(TRANSLATIONS_DIR), f"app_{name}.po")
    if os.path.exists(po_file):
      merge_po(po_file, POT_FILE)
    else:
      init_po(POT_FILE, po_file, name)


if __name__ == "__main__":
  update_translations()
