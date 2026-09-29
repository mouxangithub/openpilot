"""Single-schema capnp field audit. ONE schema per process (pycapnp crashes
when two are loaded in one interpreter - see the module-long note in the skill).

  python audit_one_schema.py <schema.capnp> <StructName>=<varName> [more...]

Example:
  python audit_one_schema.py opendbc_repo/opendbc/car/car.capnp CS=CarState CC=CarControl
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import capnp

ROOT = Path(__file__).resolve().parents[4]
schema_path = sys.argv[1]
pairs = [a.split('=', 1) for a in sys.argv[2:]]

schema = capnp.load(str(ROOT / schema_path), imports=[str((ROOT / schema_path).parent)])

TARGETS = [
  ROOT / 'openpilot/selfdrive/car/cruise.py',
  ROOT / 'openpilot/selfdrive/car/card.py',
  ROOT / 'openpilot/selfdrive/ui/sunnypilot/layouts/settings/navigation.py',
  ROOT / 'openpilot/selfdrive/ui/widgets/carrot_web_dialog.py',
  ROOT / 'openpilot/selfdrive/ui/carrot_web.py',
  ROOT / 'openpilot/sunnypilot/carrot/carrot_man.py',
]

problems = []
for var, struct_name in pairs:
  node = getattr(schema, struct_name, None)
  if node is None:
    print(f'WARN: {struct_name} not in {schema_path}')
    continue
  fields = set(node.schema.fields.keys())
  pat = re.compile(r'\b' + re.escape(var) + r'\.(\w+)')
  for path in TARGETS:
    src = path.read_text(encoding='utf-8')
    lines = src.split('\n')
    # Byte offset of each line start, so we can tell code from prose.
    starts, acc = [], 0
    for ln in lines:
      starts.append(acc)
      acc += len(ln) + 1
    for m in pat.finditer(src):
      line_no = src[:m.start()].count('\n')
      stripped = lines[line_no].lstrip()
      # Skip comments and docstring prose - they mention fields that are gone.
      if stripped.startswith('#'):
        continue
      if m.group(1) in fields:
        continue
      # `self.CI.CS` / `self.CI.CC` are CarInterface Python objects, not capnp
      # structs (secoc_key lives in opendbc/car/interfaces.py). Skip those.
      prefix = src[max(0, m.start() - 8):m.start()]
      if prefix.endswith('CI.'):
        continue
      # CS_SP is a different struct; `CS.` must not match inside it.
      if src[max(0, m.start() - 1):m.start() + len(var)] == '_' + var:
        continue
      line = src[:m.start()].count('\n') + 1
      problems.append(f'{path.name}:{line} {var}.{m.group(1)} not in {struct_name}')

if problems:
  print(f'FOUND {len(problems)}:')
  for p in problems:
    print('  -', p)
  sys.exit(1)
print(f'OK - {", ".join(f"{v}:{s}" for v, s in pairs)}')
