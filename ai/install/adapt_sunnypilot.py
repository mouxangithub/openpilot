#!/usr/bin/env python3
"""One-shot adapter: rewrite Dragonpilot-oriented ai/ assets for sunnypilot."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AI = ROOT / "ai"

PARAM_MAP = {
  "dp_dev_model_selected": "CarPlatformBundle",
  "dp_dev_beep": "SpDevBeep",
  "dp_dev_go_off_road": "OffroadMode",
}

# User-facing text only — never touch `openpilot.` import paths
TEXT_FILES = {".md", ".json", ".js", ".html", ".txt"}
TEXT_REPLACEMENTS = [
  ("Dragonpilot", "sunnypilot"),
  ("dragonpilot", "sunnypilot"),
  ("list_dp_settings", "list_sp_settings"),
  ("fetch_dashy_settings", "list_sp_settings"),
  ("dp-tuning", "sp-tuning"),
  ("dragonpilot-dashy", "sunnypilot-settings"),
  ("dp-brand-", "sp-brand-"),
  ("dp_dev_model_selected", "CarPlatformBundle"),
  ("dp_dev_beep", "SpDevBeep"),
  ("dp_dev_go_off_road", "OffroadMode"),
  ("op助手", "SP助手"),
]

SKIP_SUFFIXES = {".pyc", ".bin", ".png", ".jpg", ".svg", ".woff", ".woff2", ".ico", ".min.js", ".min.css"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", "vendor"}


def adapt_file(path: Path) -> bool:
  if path.suffix in SKIP_SUFFIXES:
    return False
  if path.suffix not in TEXT_FILES and path.suffix != ".py":
    return False
  if path.name in {"adapt_sunnypilot.py", "dp_settings.py", "sp_settings.py", "params_catalog.json"}:
    return False
  try:
    text = path.read_text(encoding="utf-8")
  except (UnicodeDecodeError, OSError):
    return False

  original = text
  for old, new in PARAM_MAP.items():
    text = text.replace(old, new)

  if path.suffix in TEXT_FILES or path.name.endswith(".py"):
    for old, new in TEXT_REPLACEMENTS:
      text = text.replace(old, new)

  if text != original:
    path.write_text(text, encoding="utf-8")
    return True
  return False


def rename_skill_dirs() -> None:
  skills = AI / "skills"
  renames = {
    "dp-tuning": "sp-tuning",
    "dragonpilot-dashy": "sunnypilot-settings",
  }
  for old, new in renames.items():
    src = skills / old
    dst = skills / new
    if src.is_dir() and not dst.exists():
      shutil.move(str(src), str(dst))

  for path in list(skills.glob("dp-brand-*")):
    dst = skills / path.name.replace("dp-brand-", "sp-brand-")
    if not dst.exists():
      shutil.move(str(path), str(dst))


def patch_registry() -> None:
  reg_path = AI / "skills" / "registry.json"
  if not reg_path.is_file():
    return
  data = json.loads(reg_path.read_text(encoding="utf-8"))
  for skill in data.get("skills", []):
    skill["id"] = skill["id"].replace("dp-tuning", "sp-tuning").replace("dragonpilot-dashy", "sunnypilot-settings").replace("dp-brand-", "sp-brand-")
    skill["name"] = skill.get("name", "").replace("Dragonpilot", "sunnypilot")
    skill["description"] = skill.get("description", "").replace("dp_*", "sunnypilot 参数").replace("Dragonpilot", "sunnypilot").replace("Dashy", "sunnypilot 设置")
    skill["path"] = skill["path"].replace("dp-tuning/", "sp-tuning/").replace("dragonpilot-dashy/", "sunnypilot-settings/").replace("dp-brand-", "sp-brand-")
    skill["requires_tools"] = [
      t.replace("list_dp_settings", "list_sp_settings").replace("fetch_dashy_settings", "list_sp_settings")
      for t in skill.get("requires_tools", [])
    ]
  data["version"] = max(data.get("version", 1), 18)
  reg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
  rename_skill_dirs()
  changed = 0
  for path in AI.rglob("*"):
    if path.is_dir():
      continue
    if any(part in SKIP_DIRS for part in path.parts):
      continue
    if adapt_file(path):
      changed += 1
  patch_registry()
  print(f"adapt_sunnypilot: updated {changed} files under {AI}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
