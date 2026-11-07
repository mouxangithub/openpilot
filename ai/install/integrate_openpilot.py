#!/usr/bin/env python3
"""Integrate op助手 into an openpilot fork: launch script + optional fork Params."""

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
  "BACKUP",
}
_PARAM_FIELDS = {"key", "flags", "param_type", "default"}

# Fork Params that ai touches but are NOT stored in /data/ai/config.json
FORK_INTEGRATION_PARAMS: dict[str, dict[str, str]] = {
  "SpDevBeep": {"flags": "PERSISTENT", "param_type": "BOOL", "default": "0"},
}

LAUNCH_MARKER = "start_op_assistant"

START_OP_ASSISTANT_FN = r'''  start_op_assistant() {
    local root="$DIR"
    if [ ! -f "$root/ai/aid.py" ]; then
      return 0
    fi
    local aid_py=python3.12
    command -v "$aid_py" >/dev/null 2>&1 || aid_py=python3
    local venv_site="/usr/local/venv/lib/python3.12/site-packages"
    local pydeps="/data/.pydeps"
    local py_path="$root"
    [ -d "$venv_site" ] && py_path="$py_path:$venv_site"
    [ -d "$pydeps" ] && py_path="$py_path:$pydeps"
    if ! PYTHONPATH="$py_path" "$aid_py" -c "import aiohttp" 2>/dev/null; then
      if [ -d "$pydeps" ] || mkdir -p "$pydeps" 2>/dev/null; then
        if ! "$aid_py" -c "import pip" 2>/dev/null; then
          curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py 2>/dev/null && \
            "$aid_py" /tmp/get-pip.py --target="$pydeps" --no-warn-script-location >> /tmp/aid.log 2>&1 || true
        fi
        PYTHONPATH="$py_path" "$aid_py" -m pip install --target="$pydeps" aiohttp >> /tmp/aid.log 2>&1 || true
        py_path="$root"
        [ -d "$venv_site" ] && py_path="$py_path:$venv_site"
        py_path="$py_path:$pydeps"
      fi
    fi
    if pgrep -f "[p]ython.* -m ai\.aid" >/dev/null 2>&1; then
      return 0
    fi
    echo "[aid] starting :5090 ($(date))" >> /tmp/aid.log
    (cd "$root" && PYTHONPATH="$py_path" "$aid_py" -m ai.aid >> /tmp/aid.log 2>&1 &)
  }
'''

START_OP_ASSISTANT_CALL = r'''  # op 助手（含 TSK）：ai 配置在 /data/ai/config.json，不依赖 params 编译
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
  """Schema for ai_* keys (stored in /data/ai/config.json, not params_keys.h)."""
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
    out[key] = param
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
  """Resolve params_keys.h for flat or nested openpilot layouts."""
  root = root.resolve()
  nested = root / "openpilot"
  source_root = nested if (nested / "common" / "params_keys.h").is_file() else root
  candidates = [
    source_root / "common" / "params_keys.h",
    root / "common" / "params_keys.h",
    root / "openpilot" / "common" / "params_keys.h",
  ]
  seen: set[str] = set()
  for path in candidates:
    key = str(path)
    if key in seen:
      continue
    seen.add(key)
    if path.is_file():
      return path
  try:
    from ai.system.paths import openpilot_source_root

    extra = openpilot_source_root() / "common" / "params_keys.h"
    if extra.is_file():
      return extra
  except Exception:
    pass
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


def _upgrade_start_op_assistant(content: str) -> tuple[str, bool]:
  if LAUNCH_MARKER not in content:
    return content, False
  if ".pydeps" in content:
    return content, False
  if '[ ! -f "$root/ai/aid.py" ]' not in content:
    return content, False
  pattern = r"  start_op_assistant\(\) \{.*?^\  \}"
  new_fn = START_OP_ASSISTANT_FN.rstrip()
  new_content, n = re.subn(pattern, new_fn, content, count=1, flags=re.MULTILINE | re.DOTALL)
  if n == 0:
    return content, False
  new_content = new_content.replace(
    "# op 助手（含 TSK）在 manager 之前启动，但必须在 scons 编译完成之后",
    "# op 助手（含 TSK）：ai 配置在 /data/ai/config.json，不依赖 params 编译",
  )
  return new_content, True


def patch_launch_script(path: Path, *, dry_run: bool = False) -> dict[str, Any]:
  content = path.read_text(encoding="utf-8")

  # New-style launch script already auto-starts ai via keep_alive; skip legacy patch.
  if "keep_alive aid" in content and LAUNCH_MARKER not in content:
    return {"ok": True, "path": str(path), "changed": False, "note": "new-style launch script already starts ai via keep_alive"}

  upgraded, was_upgraded = _upgrade_start_op_assistant(content)
  if was_upgraded:
    if dry_run:
      return {"ok": True, "path": str(path), "changed": True, "dry_run": True, "note": "upgraded start_op_assistant"}
    backup = path.with_suffix(path.suffix + f".bak.{datetime.now().strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(path, backup)
    path.write_text(upgraded, encoding="utf-8")
    return {"ok": True, "path": str(path), "backup": str(backup), "changed": True, "note": "upgraded start_op_assistant"}

  if LAUNCH_MARKER in content:
    return {"ok": True, "path": str(path), "changed": False, "note": "start_op_assistant already present"}

  backup = path.with_suffix(path.suffix + f".bak.{datetime.now().strftime('%Y%m%d%H%M%S')}")
  fn_block = START_OP_ASSISTANT_FN.rstrip() + "\n"
  call_block = START_OP_ASSISTANT_CALL.rstrip() + "\n"

  new_content = content
  manager_cd = None
  if "cd openpilot/system/manager" in content:
    manager_cd = "cd openpilot/system/manager"
  elif re.search(r"cd\s+system/manager", content):
    manager_cd = "cd system/manager"

  if manager_cd:
    if manager_cd in content and fn_block.strip() not in content:
      new_content = content.replace(f"  {manager_cd}", fn_block + f"\n  {manager_cd}", 1)
    if "./manager.py" in new_content and call_block.strip() not in new_content:
      new_content = new_content.replace("  ./manager.py", call_block + "\n  ./manager.py", 1)
    elif manager_cd in new_content and call_block.strip() not in new_content:
      pattern = rf"({re.escape(manager_cd)}\n(?:  if \[ ! -f \$DIR/prebuilt \]; then\n    \./build\.py\n  fi\n)?)"
      repl = r"\1\n" + call_block
      new_content, n = re.subn(pattern, repl, new_content, count=1)
      if n == 0:
        new_content = new_content.replace(f"  {manager_cd}\n", f"  {manager_cd}\n\n" + call_block, 1)
  else:
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


from ai.common.op_params import (
  detect_params_native_kind,
  find_params_native_so,
  scons_native_targets,
)


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


def compile_params_native(root: Path, *, force: bool = False) -> dict[str, Any]:
  existing = find_params_native_so(root)
  prebuilt = (root / "prebuilt").is_file()
  sconstruct = (root / "SConstruct").is_file()
  common_sconscript = (
    (root / "common" / "SConscript").is_file()
    or (root / "openpilot" / "common" / "SConscript").is_file()
  )

  if existing and not force:
    return {
      "ok": True,
      "skipped": True,
      "reason": "Params native library already exists",
      "so_path": str(existing),
    }

  attempts: list[dict[str, Any]] = []

  if shutil.which("scons") and sconstruct:
    kind = detect_params_native_kind(root)
    for target in scons_native_targets(kind):
      for args in (["scons", "-j4", target], ["scons", "-j1", target], ["scons", target]):
        result = _run(args, cwd=root)
        attempts.append(result)
        so = find_params_native_so(root)
        if result["ok"] and so:
          return {"ok": True, "method": " ".join(args), "so_path": str(so), "attempts": attempts}
        if so and not force:
          return {"ok": True, "method": "existing after partial build", "so_path": str(so), "attempts": attempts}

  build_py = root / "system" / "manager" / "build.py"
  if not build_py.is_file():
    build_py = root / "openpilot" / "system" / "manager" / "build.py"
  if build_py.is_file() and not prebuilt:
    result = _run([sys.executable, str(build_py)], cwd=build_py.parent, timeout=1800)
    attempts.append(result)
    so = find_params_native_so(root)
    if so:
      return {"ok": True, "method": "system/manager/build.py", "so_path": str(so), "attempts": attempts}

  so = find_params_native_so(root)
  if so:
    return {
      "ok": True,
      "skipped": True,
      "reason": "using existing Params native library (no rebuild)",
      "so_path": str(so),
      "attempts": attempts,
    }

  kind = detect_params_native_kind(root)
  lib_hint = "libparams_c.so" if kind != "params_pyx" else "params_pyx.so"
  hint = (
    f"无法编译 {lib_hint}："
    + ("检测到 prebuilt 发行版且无 SConstruct。" if prebuilt and not sconstruct else "")
    + ("缺少 common/SConscript。" if not common_sconscript else "")
    + f" 请在有编译环境的机器上运行: cd $OPENPILOT_ROOT && scons -j4 {scons_native_targets(kind)[0]}"
    + " 或: cd openpilot/system/manager && ./build.py"
  )
  return {"ok": False, "error": hint, "attempts": attempts, "prebuilt": prebuilt}


compile_params_pyx = compile_params_native


def integrate(
  root: Path,
  ai_dir: Path | None = None,
  *,
  dry_run: bool = False,
  skip_compile: bool = True,
  force_compile: bool = False,
  patch_fork_params: bool = True,
) -> dict[str, Any]:
  ai_dir = ai_dir or (root / "ai")
  report: dict[str, Any] = {
    "ok": True,
    "openpilot_root": str(root),
    "ai_dir": str(ai_dir),
    "ai_config_store": "/data/ai/config.json",
  }

  try:
    ai_schema = collect_ai_params(ai_dir)
    report["ai_param_count"] = len(ai_schema)
    report["ai_config"] = {
      "ok": True,
      "storage": "json",
      "note": "ai_* keys are NOT added to params_keys.h",
    }
  except Exception as exc:
    return {"ok": False, "error": f"collect_ai_params: {exc}"}

  params_h = find_params_keys_h(root)
  if patch_fork_params and params_h:
    report["params_keys"] = patch_params_keys_h(params_h, FORK_INTEGRATION_PARAMS, dry_run=dry_run)
    if not report["params_keys"].get("ok"):
      report["ok"] = False
  elif patch_fork_params:
    report["params_keys"] = {
      "ok": True,
      "skipped": True,
      "warning": "params_keys.h not found — SpDevBeep not patched (add manually if beepd is needed)",
      "searched_root": str(root),
    }
  else:
    report["params_keys"] = {"ok": True, "skipped": True, "reason": "patch_fork_params=false"}

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

  fork_keys_changed = bool(report.get("params_keys", {}).get("changed"))
  if skip_compile and not force_compile:
    report["compile"] = {
      "ok": True,
      "skipped": True,
      "reason": "ai_* use config.json; compile not required unless --force-compile or new fork Param added",
    }
    if fork_keys_changed and not dry_run:
      report["compile"]["warning"] = (
        "SpDevBeep was added to params_keys.h — rebuild Params native lib (libparams_c.so or params_pyx.so) if beepd toggle is needed"
      )
  else:
    report["compile"] = compile_params_pyx(root, force=force_compile or fork_keys_changed)
    if not report["compile"].get("ok"):
      report["ok"] = False

  try:
    from ai.fork.detect_fork import detect_fork

    report["fork"] = detect_fork(root)
    if not report["fork"].get("ok"):
      report["warnings"] = report.get("warnings", []) + [
        f"fork detect: {report['fork'].get('error', 'unknown')}",
      ]
  except Exception as exc:
    report["fork"] = {
      "ok": True,
      "skipped": True,
      "warning": str(exc),
      "hint": "fork 扫描失败不影响 launch 集成；请更新 ai/ 后重试 integrate",
    }
    report["warnings"] = report.get("warnings", []) + [f"fork detect exception: {exc}"]

  if not dry_run:
    try:
      from ai.fork.post_install import run_post_install_learn

      report["post_install_learn"] = run_post_install_learn(root)
    except Exception as exc:
      report["post_install_learn"] = {"ok": False, "error": str(exc)}

  return report


def main() -> int:
  parser = argparse.ArgumentParser(description="Integrate op助手 into openpilot fork")
  parser.add_argument("--root", type=Path, default=None, help="openpilot root (default: OPENPILOT_ROOT or parent of ai/)")
  parser.add_argument("--ai-dir", type=Path, default=None, help="ai package dir")
  parser.add_argument("--dry-run", action="store_true")
  parser.add_argument("--skip-compile", action="store_true", default=True, help="Skip Params native lib compile (default)")
  parser.add_argument("--compile", dest="skip_compile", action="store_false", help="Attempt libparams_c.so / params_pyx.so compile")
  parser.add_argument("--force-compile", action="store_true")
  parser.add_argument("--no-patch-fork-params", action="store_true", help="Do not patch SpDevBeep into params_keys.h")
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
    patch_fork_params=not args.no_patch_fork_params,
  )
  if args.as_json:
    print(json.dumps(result, ensure_ascii=False, indent=2))
  else:
    for section in ("ai_config", "params_keys", "launch", "compile", "fork"):
      block = result.get(section)
      if not block:
        continue
      line = f"[{section}] {json.dumps(block, ensure_ascii=False)}"
      try:
        print(line)
      except UnicodeEncodeError:
        print(line.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
          sys.stdout.encoding or "utf-8", errors="replace"
        ))
    if result.get("ok"):
      print("integrate: OK")
    else:
      print(f"integrate: FAILED — {result.get('error', 'see sections above')}", file=sys.stderr)
  return 0 if result.get("ok") else 1


if __name__ == "__main__":
  raise SystemExit(main())
