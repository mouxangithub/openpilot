#!/usr/bin/env python3
"""Merge tools/domains/<name>.py MODULES into <name>/__init__.py and remove sibling file."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "tools" / "domains"

for domain_py in sorted(ROOT.glob("*.py")):
  if domain_py.name == "__init__.py":
    continue
  name = domain_py.stem
  pkg = ROOT / name
  if not pkg.is_dir():
    continue
  init = pkg / "__init__.py"
  content = domain_py.read_text(encoding="utf-8")
  m = re.search(r"MODULES\s*=\s*\((.*?)\)", content, re.S)
  if not m:
    print(f"skip {domain_py.name}: no MODULES")
    continue
  modules_block = m.group(0)
  init.write_text(
    f'"""{name.title()} tools domain."""\n\nfrom __future__ import annotations\n\n{modules_block}\n\n__all__ = ["MODULES"]\n',
    encoding="utf-8",
  )
  domain_py.unlink()
  print(f"merged {name}.py -> {name}/__init__.py")
