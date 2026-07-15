# Copyright (c) 2026, Rick Lan
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, and/or sublicense,
# for non-commercial purposes only, subject to the following conditions:
#
# - The above copyright notice and this permission notice shall be included in
#   all copies or substantial portions of the Software.
# - Commercial use (e.g. use in a product, service, or activity intended to
#   generate revenue) is prohibited without explicit written permission from
#   the copyright holder.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""SETTINGS-derived param allowlist, sandboxed condition evaluation, and typed
param read/write helpers. Everything here operates on a passed-in Params object;
no request or server state."""

import ast
import json
import operator

from dragonpilot.settings import SETTINGS

from .config import logger

_CMP_OPS = {
  ast.Eq: operator.eq,
  ast.NotEq: operator.ne,
  ast.Lt: operator.lt,
  ast.LtE: operator.le,
  ast.Gt: operator.gt,
  ast.GtE: operator.ge,
}


def _eval_node(node, context):
  """Evaluate a tightly restricted AST node against a context dict.

  Only the operators that SETTINGS conditions actually use are supported:
  Name lookup, literal Constants, and / or / not, and the six numeric
  comparisons. No function calls, attribute access, subscripts, or
  arithmetic — those would re-open the eval-sandbox escape paths.
  """
  if isinstance(node, ast.Expression):
    return _eval_node(node.body, context)
  if isinstance(node, ast.Constant):
    return node.value
  if isinstance(node, ast.Name):
    return context.get(node.id, False)
  if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
    return not _eval_node(node.operand, context)
  if isinstance(node, ast.BoolOp):
    values = [_eval_node(v, context) for v in node.values]
    if isinstance(node.op, ast.And):
      return all(values)
    if isinstance(node.op, ast.Or):
      return any(values)
  if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
    op_type = type(node.ops[0])
    if op_type in _CMP_OPS:
      left = _eval_node(node.left, context)
      right = _eval_node(node.comparators[0], context)
      return _CMP_OPS[op_type](left, right)
  raise ValueError(f"Unsupported node: {type(node).__name__}")


def eval_condition(condition, context):
  """Evaluate a SETTINGS condition expression in a sandboxed AST walker."""
  if not condition:
    return True
  try:
    tree = ast.parse(condition, mode='eval')
    return bool(_eval_node(tree, context))
  except Exception as e:
    logger.debug(f"Condition evaluation failed: {condition}, error: {e}")
    return False


def resolve_value(value):
  """Resolve callable values (lambdas) for JSON serialization."""
  return value() if callable(value) else value


# Map of settings-declared param keys to their setting dict.
# Used as an allowlist for /api/settings/params/{name} read/write so
# LAN clients can only touch keys that the UI knowingly exposes.
def _build_param_setting_map():
  out = {}
  for section in SETTINGS:
    for setting in section.get('settings', []):
      key = setting.get('key')
      if not key:
        continue
      # action_item entries use `key` as the action name, not a real
      # param — skip so they don't leak into the param read/write
      # allowlist.
      if setting.get('type') == 'action_item':
        continue
      out[key] = setting
  return out


_PARAM_SETTINGS = _build_param_setting_map()

# Control-tab / one-off params the UI legitimately reads or writes that
# are not part of the SETTINGS schema. Kept as an explicit allowlist so
# the broader 'unknown param' guard still blocks arbitrary writes.
_CONTROL_PARAMS = {
  'dp_dev_go_off_road',  # Controls tab: force-offroad toggle
  'DoReboot',  # Controls tab: reboot button
  'ExperimentalMode',  # Tesla HUD: tap set-speed circle to toggle
  'LanguageSetting',  # Settings tab: language switch (comma-4; "main_<code>")
  'dp_lon_accel_profiles',  # Accel EQ: profile library (JSON) — includes the active selection
}

# Control params whose value is a string/JSON, not a bool. The generic
# control-param GET path reads bools (get_bool); these must be read as
# their raw string so the web UI gets the actual value back. POST already
# stores them as strings via _save_param's default branch.
_RAW_STRING_PARAMS = {
  'dp_lon_accel_profiles',
}

assert _RAW_STRING_PARAMS <= _CONTROL_PARAMS, "raw-string params must also be allowlisted in _CONTROL_PARAMS"


def _param_allowed(key):
  return key in _PARAM_SETTINGS or key in _CONTROL_PARAMS


def _get_setting_value(params, setting):
  """Get current value for a setting from Params."""
  key = setting['key']
  setting_type = setting['type']
  default = setting.get('default', 0)

  try:
    if setting_type == 'toggle_item':
      return params.get_bool(key)
    elif setting_type == 'double_spin_button_item':
      value = params.get(key)
      return float(value) if value is not None else float(default)
    elif setting_type in ('text_input_item', 'text_display_item'):
      value = params.get(key)
      if value is None:
        return ''
      return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else str(value)
    elif setting_type == 'action_item':
      # Pure action buttons have no stored value; return None so the
      # UI treats it as display-only.
      return None
    else:  # spin_button_item, text_spin_button_item
      value = params.get(key)
      return int(value) if value is not None else int(default)
  except Exception as e:
    logger.warning(f"Error getting value for {key}: {e}")
    if setting_type == 'toggle_item':
      return False
    elif setting_type == 'double_spin_button_item':
      return float(default)
    elif setting_type in ('text_input_item', 'text_display_item'):
      return ''
    elif setting_type == 'action_item':
      return None
    return int(default)


def _save_param(params, key, value):
  """Save a single param value with proper type handling."""
  try:
    param_type = params.get_type(key)

    if param_type == 1:  # BOOL
      params.put_bool(key, bool(value))
    elif param_type == 2:  # INT
      params.put(key, int(value))
    elif param_type == 3:  # FLOAT
      params.put(key, float(value))
    elif param_type == 5:  # JSON
      # Parse an incoming JSON string to a dict/list so Params.put's
      # (dict|list, JSON) caster (json.dumps) stores it; put() has no
      # (str, JSON) caster and would raise. Malformed JSON raises here and
      # is surfaced to the client. Already-parsed bodies pass through.
      params.put(key, json.loads(value) if isinstance(value, str) else value)
    elif isinstance(value, bool):
      params.put_bool(key, value)
    else:
      params.put(key, str(value) if not isinstance(value, str) else value)

    logger.debug(f"Saved {key}={value} (type={param_type})")
  except Exception as e:
    logger.error(f"Error saving param {key}={value}: {e}")
    raise


def _get_param_value(params, key):
  """Get a single param value via its declared setting type, or as a
  bool for control-only params that have no SETTINGS entry."""
  setting = _PARAM_SETTINGS.get(key)
  if setting is not None:
    return _get_setting_value(params, setting)
  if key in _RAW_STRING_PARAMS:
    try:
      raw = params.get(key)
      if raw is None:
        return None
      # JSON-typed params (e.g. dp_lon_accel_profiles) come back from
      # Params.get already json.loads'd into a dict/list — re-serialize so
      # the web gets valid JSON, not Python repr (str(dict) → single quotes,
      # which JSON.parse can't read → client silently falls back to seed).
      if isinstance(raw, (dict, list)):
        return json.dumps(raw)
      return raw.decode('utf-8', errors='replace') if isinstance(raw, bytes) else str(raw)
    except Exception:
      return None
  if key in _CONTROL_PARAMS:
    try:
      return params.get_bool(key)
    except Exception:
      return False
  return None
