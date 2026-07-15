"""Dragonpilot settings schema + current values (no Dashy server required)."""

from __future__ import annotations

import ast
import operator
from typing import Any

from openpilot.common.params import Params

try:
  from dragonpilot.settings import SETTINGS, SECTION_CONDITIONS
except ImportError:
  SETTINGS = []
  SECTION_CONDITIONS = {}


_OPS = {
  ast.Eq: operator.eq,
  ast.NotEq: operator.ne,
  ast.Lt: operator.lt,
  ast.LtE: operator.le,
  ast.Gt: operator.gt,
  ast.GtE: operator.ge,
  ast.And: lambda a, b: a and b,
  ast.Or: lambda a, b: a or b,
}


def _eval_node(node, context: dict[str, Any]):
  if isinstance(node, ast.BoolOp):
    vals = [_eval_node(v, context) for v in node.values]
    if isinstance(node.op, ast.And):
      return all(vals)
    return any(vals)
  if isinstance(node, ast.Compare):
    left = _eval_node(node.left, context)
    for op, comp in zip(node.ops, node.comparators):
      fn = _OPS.get(type(op))
      if fn is None:
        return False
      right = _eval_node(comp, context)
      if not fn(left, right):
        return False
      left = right
    return True
  if isinstance(node, ast.Constant):
    return node.value
  if isinstance(node, ast.Name):
    return context.get(node.id)
  if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
    return not _eval_node(node.operand, context)
  return False


def eval_condition(expr: str | None, context: dict[str, Any]) -> bool:
  if not expr:
    return True
  try:
    tree = ast.parse(expr, mode="eval")
    return bool(_eval_node(tree.body, context))
  except Exception:
    return False


def _resolve(val):
  return val() if callable(val) else val


def _get_setting_value(params: Params, setting: dict[str, Any]) -> Any:
  key = setting["key"]
  setting_type = setting["type"]
  default = setting.get("default", 0)
  try:
    if setting_type == "toggle_item":
      return params.get_bool(key)
    if setting_type == "double_spin_button_item":
      value = params.get(key)
      return float(value) if value is not None else float(default)
    if setting_type in ("text_input_item", "text_display_item"):
      value = params.get(key)
      if value is None:
        return ""
      return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)
    if setting_type == "action_item":
      return None
    value = params.get(key)
    return int(value) if value is not None else int(default)
  except Exception:
    if setting_type == "toggle_item":
      return False
    if setting_type == "double_spin_button_item":
      return float(default)
    if setting_type in ("text_input_item", "text_display_item"):
      return ""
    return int(default) if str(default).lstrip("-").isdigit() else default


def build_settings_context(params: Params, brand: str = "", extra: dict[str, Any] | None = None) -> dict[str, Any]:
  ctx: dict[str, Any] = {
    "brand": brand or "",
    "DASHY": True,
    "IS_RELEASE": False,
    "LITE": False,
    "MICI": False,
    "openpilotLongitudinalControl": False,
  }
  if extra:
    ctx.update(extra)
  try:
    from openpilot.system.hardware import HARDWARE
    ctx["MICI"] = bool(getattr(HARDWARE, "MICI", False))
  except Exception:
    pass
  return ctx


def list_dp_settings(params: Params | None = None, brand: str = "") -> dict[str, Any]:
  """Return Dragonpilot SETTINGS sections with current values."""
  params = params or Params()
  context = build_settings_context(params, brand=brand)
  sections_out: list[dict[str, Any]] = []

  for section in SETTINGS:
    title = section.get("title", "")
    cond = section.get("condition") or SECTION_CONDITIONS.get(title)
    if not eval_condition(cond, context):
      continue

    items: list[dict[str, Any]] = []
    for setting in section.get("settings", []):
      if not eval_condition(setting.get("condition"), context):
        continue
      if setting.get("type") == "action_item":
        continue
      key = setting.get("key")
      if not key:
        continue
      items.append({
        "key": key,
        "section": title,
        "type": setting.get("type"),
        "title": _resolve(setting.get("title")),
        "description": _resolve(setting.get("description")),
        "default": setting.get("default"),
        "min_val": setting.get("min_val"),
        "max_val": setting.get("max_val"),
        "current_value": _get_setting_value(params, setting),
        "depends_on": setting.get("depends_on"),
        "brands": setting.get("brands"),
      })

    if items:
      sections_out.append({"title": title, "settings": items})

  return {"ok": True, "brand": brand, "sections": sections_out, "setting_count": sum(len(s["settings"]) for s in sections_out)}
