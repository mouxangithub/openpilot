"""aid doctor — dependency / runtime probe for local (PC) development.

Checks the pieces that most commonly block ``ai.aid`` from starting on a
Windows/Linux dev box:

- required third-party packages (aiohttp, pyzmq, zstandard, jinja2, ...)
- openpilot submodule import paths on PYTHONPATH (opendbc_repo, panda, ...)
- whether the PC mock bootstrap (``ai.dev.run_pc``) is usable

Usage (from repo root):
  py -3 ai/dev/aid_doctor.py
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# name -> install hint
REQUIRED_PACKAGES: list[tuple[str, str]] = [
  ("aiohttp", "pip install aiohttp"),
  ("zmq", "pip install pyzmq"),
  ("zstandard", "pip install zstandard"),
  ("jinja2", "pip install jinja2"),
  ("numpy", "pip install numpy"),
  ("requests", "pip install requests"),
]

# openpilot submodules that must be importable for aid to boot.
SUBMODULE_PATHS: list[tuple[str, str]] = [
  ("opendbc_repo", "opendbc"),
  ("panda", "panda"),
  ("msgq_repo", "msgq"),
  ("rednose_repo", "rednose"),
  ("tinygrad_repo", "tinygrad"),
  ("teleoprtc_repo", "teleoprtc"),
]


def _check_packages() -> list[str]:
  problems: list[str] = []
  for name, hint in REQUIRED_PACKAGES:
    try:
      importlib.import_module(name)
    except Exception as e:
      problems.append(f"[dep] {name}: import failed ({e}); hint: {hint}")
  return problems


def _check_submodules() -> list[str]:
  problems: list[str] = []
  for dirname, pkg in SUBMODULE_PATHS:
    d = ROOT / dirname
    if not d.is_dir():
      problems.append(f"[submodule] {dirname} missing at {d}")
  # The modules themselves are importable only if PYTHONPATH includes them.
  for dirname, pkg in SUBMODULE_PATHS:
    p = ROOT / dirname
    if p.is_dir() and str(p) not in sys.path and str(ROOT) not in sys.path:
      problems.append(f"[path] {pkg} not on PYTHONPATH ({p})")
  return problems


def main() -> int:
  print(f"aid doctor — root={ROOT}")
  problems = _check_packages() + _check_submodules()

  # PC mock bootstrap sanity.
  try:
    from ai.dev.run_pc import _install_openpilot_mocks  # noqa: F401
    print("[pc] ai.dev.run_pc importable: yes")
  except Exception as e:
    problems.append(f"[pc] ai.dev.run_pc import failed ({e})")

  if problems:
    print("\nProblems found:")
    for p in problems:
      print("  " + p)
    print("\nAfter fixing, start aid with:")
    print(f"  cd {ROOT}")
    print("  py -3 ai/dev/run_pc.py --port 5090")
    return 1

  print("All checks passed.")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
