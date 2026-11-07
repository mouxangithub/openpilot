#!/usr/bin/env python3
import json
import sys
sys.path.insert(0, "/data/openpilot")
from pathlib import Path
from ai.tools.publish_units import discover_publish_units, _read_gitmodules
from ai.common.repo_targets import assistant_repo_path
from ai.system.paths import openpilot_root

op = openpilot_root().resolve()
ai = assistant_repo_path().resolve()
print("op_root:", op)
print("ai_path:", ai)
print("gitmodules:", _read_gitmodules(op))
for entry in _read_gitmodules(op):
    rel = entry.get("path", "").strip()
    sub = (op / rel).resolve()
    print(f"  sub {rel} -> {sub} same_as_ai={sub == ai}")
data = discover_publish_units()
print("units:", json.dumps([{k: u.get(k) for k in ("id", "display_name", "kind", "git_root", "root")} for u in data["units"]], indent=2))
