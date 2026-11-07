"""Onroad navigation card API.

The card itself is driven by the `nav_card` block in the state payload; this
module backs the GET snapshot (used on panel loads) and the long-press cancel.

Cancel mirrors navigation_card.py::_cancel_navigation: remove NavDestination
(navd never rewrites it, so removal sticks until a new route is pushed) and
blank NavInstructionState so carrot_man's live guidance stops rendering.
"""

from __future__ import annotations

from typing import Any


def navcard_snapshot() -> dict[str, Any]:
  try:
    from openpilot.common.params import Params
    p = Params()
    raw = p.get("NavInstructionState")
    instruction = None
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", "replace")
    if isinstance(raw, str) and raw:
      import json
      try:
        instruction = json.loads(raw)
      except ValueError:
        instruction = None
    elif isinstance(raw, dict):
      instruction = raw
    return {
      "ok": True,
      "enabled": p.get_bool("NavigationCardEnabled"),
      "valid": bool(instruction) and p.get("NavDestination") is not None,
      "collapsed": p.get_bool("NavInstructionCollapsed"),
      "instruction": instruction if isinstance(instruction, dict) else None,
    }
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def cancel_navigation() -> dict[str, Any]:
  try:
    from openpilot.common.params import Params
    p = Params()
    p.remove("NavDestination")
    p.put("NavInstructionState", "{}")
    return {"ok": True}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}
