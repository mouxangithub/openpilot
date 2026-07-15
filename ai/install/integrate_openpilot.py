#!/usr/bin/env python3
"""Integrate op助手 into an openpilot fork: params_keys.h, launch script, params_pyx.so."""

from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

VALID_PARAM_TYPES = {"STRING", "BOOL", "INT", "FLOAT", "TIME", "JSON", "BYTES"}
VALID_FLAGS = {
  "PERSISTENT",
  "CLEAR_ON_MANAGER_START",
  "CLEAR_ON_ONROAD_TRANSITION",
  "CLEAR_ON_OFFROAD_TRANSITION",
  "DONT_LOG",
  "DEVELOPMENT_ONLY",
  "CLEAR_ON_IGNITION_ON",
}
_PARAM_FIELDS = {"key", "flags", "param_type", "default"}

# Keys used by aid but not always listed in ai/common/params.py ITEMS.
EXTRA_AI_PARAMS: list[dict[str, str]] = [
  {"key": "ai_usage_log", "flags": "PERSISTENT", "param_type": "STRING", "default": ""},
  {"key": "ai_first_run_done", "flags": "PERSISTENT", "param_type": "BOOL", "default": "0"},
  {"key": "ai_fork_id", "flags": "PERSISTENT", "param_type": "STRING", "default": ""},
  {"key": "ai_fork_profile_applied", "flags": "PERSISTENT", "param_type": "STRING", "default": ""},
]

LAUNCH_MARKER = "start_op_assistant"

START_OP_ASSISTANT_FN = r'''  start_op_assistant() {
    local root="$DIR"
    local aid_py=python3.12
    command -v "$aid_py" >/dev/null 2>&1 || aid_py=python3
    local venv_site="/usr/local/venv/lib/python3.12/site-packages"
    local py_path="$root"
    [ -d "$venv_site" ] && py_path="$root:$venv_site"
    local so="$root/openpilot/common/params_pyx.so"
    [ -f "$so" ] || so="$root/common/params_pyx.so"
    if [ ! -f "$so" ]; then
      echo "[aid] params_pyx.so missing, skip ($(date))" >> /tmp/aid.log
      return 1
    fi
    if pgrep -f "[p]ython.* -m ai\.aid" >/dev/null 2>&1; then
      return 0
    fi
    echo "[aid] starting :5090 ($(date))" >> /tmp/aid.log
    (cd "$root" && PYTHONPATH="$py_path" "$aid_py" -m ai.aid >> /tmp/aid.log 2>&1 &)
  }
'''

START_OP_ASSISTANT_CALL = r'''  # op 助手（含 TSK）在 manager 之前启动，但必须在 scons 编译完成之后
  start_op_assistant
  (
    while true; do
      sleep 45
      start_op_assistant
    done
  ) &
'''


def _literal_or_none(node: ast.AST) -> Any:
  if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool)):
    return node.value
  return None


def _extract_items_node(tree: ast.AST) -> ast.List | None:
  for node in tree.body:
    if isinstance(node, ast.Assign):
      for target in node.targets:
        if isinstance(target, ast.Name) and target.id == "ITEMS":
          if isinstance(node.value, ast.List):
            return node.value
  return None


def _extract_param(dict_node: ast.Dict, source: str) -> dict[str, str] | None:
  fields: dict[str, str] = {}
  for k_node, v_node in zip(dict_node.keys, dict_node.values):
    if not (isinstance(k_node, ast.Constant) and isinstance(k_node.value, str)):
      continue
    name = k_node.value
    if name not in _PARAM_FIELDS:
      continue
    lit = _literal_or_none(v_node)
    if lit is None:
      raise ValueError(f"{source}: field {name!r} must be a literal")
    fields[name] = str(lit) if not isinstance(lit, bool) else ("1" if lit else "0")
  if "key" not in fields:
    return None
  return fields


def collect_ai_params(ai_dir: Path) -> dict[str, dict[str, str]]:
  params_py = ai_dir / "common" / "params.py"
  if not params_py.is_file():
    raise FileNotFoundError(f"Missing {params_py}")
  tree = ast.parse(params_py.read_text(encoding="utf-8"), filename=str(params_py))
  items_node = _extract_items_node(tree)
  if items_node is None:
    raise ValueError(f"No ITEMS in {params_py}")
  out: dict[str, dict[str, str]] = {}
  for elt in items_node.elts:
    if not isinstance(elt, ast.Dict):
      continue
    param = _extract_param(elt, str(params_py))
    if not param:
      continue
    key = param["key"]
    if not key.startswith("ai_"):
      continue
    flags = param.get("flags", "PERSISTENT")
    ptype = param.get("param_type", "STRING")
    if ptype not in VALID_PARAM_TYPES:
      raise ValueError(f"Invalid param_type {ptype!r} for {key}")
    for flag in re.split(r"\s*\|\s*", flags):
      if flag and flag not in VALID_FLAGS:
        raise ValueError(f"Invalid flag {flag!r} for {key}")
    out[key] = param
  for extra in EXTRA_AI_PARAMS:
    out.setdefault(extra["key"], extra)
  return out


def render_param_line(param: dict[str, str]) -> str:
  key = param["key"]
  flags = param["flags"]
  ptype = param["param_type"]
  default = param.get("default", "")
  if default == "":
    return f'    {{"{key}", {{{flags}, {ptype}}}}},'
  return f'    {{"{key}", {{{flags}, {ptype}, "{default}"}}}},'


def find_params_keys_h(root: Path) -> Path | None:
  for rel in ("common/params_keys.h", "openpilot/common/params_keys.h"):
    path = root / rel
    if path.is_file():
      return path
  return None


def find_launch_script(root: Path) -> Path | None:
  for name in ("launch_chffrplus.sh", "launch_openpilot.sh"):
    path = root / name
    if path.is_file():
      return path
  return None


def patch_params_keys_h(path: Path, params: dict[str, dict[str, str]], *, dry_run: bool = False) -> dict[str, Any]:
  content = path.read_text(encoding="utf-8")
  existing = set(re.findall(r'\{"([^"]+)"', content))
  new_keys = [k for k in sorted(params) if k not in existing]
  if not new_keys:
    return {"ok": True, "path": str(path), "added": [], "changed": False}

  backup = path.with_suffix(path.suffix + f".bak.{datetime.now().strftime('%Y%m%d%H%M%S')}")
  new_lines = [render_param_line(params[k]) for k in new_keys]
  lines = content.split("\n")
  inserted = False
  for i, line in enumerate(lines):
    if line.strip() == "};":
      lines[i:i] = new_lines
      inserted = True
      break
  if not inserted:
    return {"ok": False, "path": str(path), "error": "Could not find closing }; in params_keys.h"}

  new_content = "\n".join(lines)
  if dry_run:
    return {"ok": True, "path": str(path), "added": new_keys, "changed": True, "dry_run": True}

  if not backup.exists():
    shutil.copy2(path, backup)
  path.write_text(new_content, encoding="utf-8")
  return {"ok": True, "path": str(path), "backup": str(backup), "added": new_keys, "changed": True}


def patch_launch_script(path: Path, *, dry_run: bool = False) -> dict[str, Any]:
  content = path.read_text(encoding="utf-8")
  if LAUNCH_MARKER in content:
    return {"ok": True, "path": str(path), "changed": False, "note": "start_op_assistant already present"}

  backup = path.with_suffix(path.suffix + f".bak.{datetime.now().strftime('%Y%m%d%H%M%S')}")
  fn_block = START_OP_ASSISTANT_FN.rstrip() + "\n"
  call_block = START_OP_ASSISTANT_CALL.rstrip() + "\n"

  new_content = content
  if re.search(r"cd\s+system/manager", content):
    # Insert function before manager cd block; insert calls after build.py section.
    if "cd system/manager" in content and fn_block.strip() not in content:
      new_content = content.replace("  cd system/manager", fn_block + "\n  cd system/manager", 1)
    if "./manager.py" in new_content and call_block.strip() not in new_content:
      new_content = new_content.replace("  ./manager.py", call_block + "\n  ./manager.py", 1)
    elif "cd system/manager" in new_content and call_block.strip() not in new_content:
      # Prebuilt-only forks: after cd system/manager block's build check
      pattern = r"(cd system/manager\n(?:  if \[ ! -f \$DIR/prebuilt \]; then\n    \./build\.py\n  fi\n)?)"
      repl = r"\1\n" + call_block
      new_content, n = re.subn(pattern, repl, new_content, count=1)
      if n == 0:
        new_content = new_content.replace("  cd system/manager\n", "  cd system/manager\n\n" + call_block, 1)
  else:
  # Fallback: append before last closing brace of launch function
    idx = new_content.rfind("\n}")
    if idx < 0:
      return {"ok": False, "path": str(path), "error": "Unrecognized launch script layout"}
    injection = "\n" + fn_block + "\n" + call_block
    new_content = new_content[:idx] + injection + new_content[idx:]

  if new_content == content:
    return {"ok": False, "path": str(path), "error": "Failed to patch launch script"}

  if dry_run:
    return {"ok": True, "path": str(path), "changed": True, "dry_run": True}

  shutil.copy2(path, backup)
  path.write_text(new_content, encoding="utf-8")
  return {"ok": True, "path": str(path), "backup": str(backup), "changed": True}


def find_params_pyx_so(root: Path) -> Path | None:
  for rel in ("common/params_pyx.so", "openpilot/common/params_pyx.so"):
    path = root / rel
    if path.is_file():
      return path
  return None


def _run(cmd: list[str], *, cwd: Path, timeout: int = 600) -> dict[str, Any]:
  try:
    proc = subprocess.run(
      cmd,
      cwd=str(cwd),
      capture_output=True,
      text=True,
      timeout=timeout,
      env={**__import__("os").environ, "PWD": str(cwd)},
    )
  except (OSError, subprocess.TimeoutExpired) as exc:
    return {"ok": False, "cmd": cmd, "error": str(exc)}
  out = ((proc.stdout or "") + (proc.stderr or "")).strip()
  return {"ok": proc.returncode == 0, "cmd": cmd, "exit_code": proc.returncode, "output": out[-8000:]}


def compile_params_pyx(root: Path, *, force: bool = False) -> dict[str, Any]:
  existing = find_params_pyx_so(root)
  prebuilt = (root / "prebuilt").is_file()
  sconstruct = (root / "SConstruct").is_file()
  common_sconscript = (root / "common" / "SConscript").is_file()

  if existing and not force:
    return {
      "ok": True,
      "skipped": True,
      "reason": "params_pyx.so already exists",
      "so_path": str(existing),
    }

  attempts: list[dict[str, Any]] = []

  if shutil.which("scons") and sconstruct:
    for target in ("common/params_pyx.so", "openpilot/common/params_pyx.so"):
      for args in (["scons", "-j4", target], ["scons", "-j1", target], ["scons", target]):
        result = _run(args, cwd=root)
        attempts.append(result)
        so = find_params_pyx_so(root)
        if result["ok"] and so:
          return {"ok": True, "method": " ".join(args), "so_path": str(so), "attempts": attempts}
        if so and not force:
          return {"ok": True, "method": "existing after partial build", "so_path": str(so), "attempts": attempts}

  build_py = root / "system" / "manager" / "build.py"
  if build_py.is_file() and not prebuilt:
    result = _run([sys.executable, str(build_py)], cwd=build_py.parent, timeout=1800)
    attempts.append(result)
    so = find_params_pyx_so(root)
    if so:
      return {"ok": True, "method": "system/manager/build.py", "so_path": str(so), "attempts": attempts}

  so = find_params_pyx_so(root)
  if so:
    return {
      "ok": True,
      "skipped": True,
      "reason": "using existing params_pyx.so (no rebuild)",
      "so_path": str(so),
      "attempts": attempts,
      "warning": "params_keys.h may be stale until you rebuild on a machine with scons",
    }

  hint = (
    "无法编译 params_pyx.so："
    + ("检测到 prebuilt 发行版且无 SConstruct。" if prebuilt and not sconstruct else "")
    + ("缺少 common/SConscript。" if not common_sconscript else "")
    + " 请在有编译环境的 PC 上运行: cd $OPENPILOT_ROOT && scons -j4 common/params_pyx.so"
  )
  return {"ok": False, "error": hint, "attempts": attempts, "prebuilt": prebuilt}


def integrate(
  root: Path,
  ai_dir: Path | None = None,
  *,
  dry_run: bool = False,
  skip_compile: bool = False,
  force_compile: bool = False,
) -> dict[str, Any]:
  ai_dir = ai_dir or (root / "ai")
  report: dict[str, Any] = {"ok": True, "openpilot_root": str(root), "ai_dir": str(ai_dir)}

  try:
    params = collect_ai_params(ai_dir)
    report["ai_param_count"] = len(params)
  except Exception as exc:
    return {"ok": False, "error": f"collect_ai_params: {exc}"}

  params_h = find_params_keys_h(root)
  if params_h:
    report["params_keys"] = patch_params_keys_h(params_h, params, dry_run=dry_run)
    if not report["params_keys"].get("ok"):
      report["ok"] = False
  else:
    report["params_keys"] = {"ok": False, "error": "params_keys.h not found"}
    report["ok"] = False

  launch = find_launch_script(root)
  if launch and launch.name == "launch_openpilot.sh" and (root / "launch_chffrplus.sh").is_file():
    launch = root / "launch_chffrplus.sh"
  if launch:
    report["launch"] = patch_launch_script(launch, dry_run=dry_run)
    if not report["launch"].get("ok"):
      report["ok"] = False
  else:
    report["launch"] = {"ok": False, "error": "launch_chffrplus.sh not found"}
    report["ok"] = False

  if skip_compile:
    report["compile"] = {"ok": True, "skipped": True, "reason": "--skip-compile"}
  else:
    keys_changed = bool(report.get("params_keys", {}).get("changed"))
    report["compile"] = compile_params_pyx(root, force=force_compile or keys_changed)
    if not report["compile"].get("ok"):
      report["ok"] = False

  # Fork detection (P4) — best effort
  try:
    from ai.fork.detect_fork import detect_fork

    report["fork"] = detect_fork(root)
  except Exception as exc:
    report["fork"] = {"ok": False, "error": str(exc)}

  return report


def main() -> int:
  parser = argparse.ArgumentParser(description="Integrate op助手 into openpilot fork")
  parser.add_argument("--root", type=Path, default=None, help="openpilot root (default: OPENPILOT_ROOT or parent of ai/)")
  parser.add_argument("--ai-dir", type=Path, default=None, help="ai package dir")
  parser.add_argument("--dry-run", action="store_true")
  parser.add_argument("--skip-compile", action="store_true")
  parser.add_argument("--force-compile", action="store_true")
  parser.add_argument("--json", action="store_true", dest="as_json")
  args = parser.parse_args()

  ai_dir = args.ai_dir
  if ai_dir is None:
    ai_dir = Path(__file__).resolve().parent.parent
  root = args.root
  if root is None:
    import os

    env_root = (os.environ.get("OPENPILOT_ROOT") or "").strip()
    root = Path(env_root).resolve() if env_root else ai_dir.parent.resolve()

  if str(ai_dir.parent.resolve()) != str(root.resolve()):
    # Allow ai_dir inside root only
    try:
      ai_dir.resolve().relative_to(root.resolve())
    except ValueError:
      print(f"ai_dir {ai_dir} is not under openpilot root {root}", file=sys.stderr)
      return 2

  if str(root) not in sys.path:
    sys.path.insert(0, str(root))

  result = integrate(
    root,
    ai_dir,
    dry_run=args.dry_run,
    skip_compile=args.skip_compile,
    force_compile=args.force_compile,
  )
  if args.as_json:
    print(json.dumps(result, ensure_ascii=False, indent=2))
  else:
    for section in ("params_keys", "launch", "compile", "fork"):
      block = result.get(section)
      if not block:
        continue
      print(f"[{section}] {json.dumps(block, ensure_ascii=False)}")
    if result.get("ok"):
      print("integrate: OK")
    else:
      print(f"integrate: FAILED — {result.get('error', 'see sections above')}", file=sys.stderr)
  return 0 if result.get("ok") else 1


if __name__ == "__main__":
  raise SystemExit(main())
