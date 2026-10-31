#!/usr/bin/env python3
"""Extract per-param control metadata straight from the on-device settings pages.

Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

The 7000 catalog must show what the car's own UI shows: the same title, the same
description, the same button labels and the same numeric range. Those live in the
page sources as `tr("...")` strings and constructor arguments, so this module reads
them out with `ast` - no import of the pages (they need raylib), no hand-copied
second list to drift.

Recognised constructors (openpilot/system/ui/sunnypilot/widgets/list_view.py and
the mici button module):

  toggle_item_sp(title, description, ..., param="K")            -> bool
  multiple_button_item_sp(title, description, buttons, ...,
                          param="K")                            -> int index into buttons
  option_item_sp(title, param, min_value, max_value,
                 description, value_change_step, ...,
                 value_map=..., use_float_scaling=...)         -> int/float range
  BigParamControlSP(text, param, ..., description=...)          -> bool
  BigMultiParamToggle(text, param, options)                     -> int index into options

plus the dict shorthand several pages use::

  self._toggle_defs = {
      "KEY": (lambda: tr("Title"), tr("Description"), None),
      ...
  }

followed by a loop that feeds each entry to toggle_item_sp(param=param).

The output for one param is a plain dict with any of:

  title      English title (raw tr text, HTML stripped)
  descr      English description (raw tr text, HTML stripped)
  min/max    numeric range from option_item_sp
  step       value_change_step
  buttons    English button labels, in on-device order
  float_scaling  option_item_sp(use_float_scaling=True)

A param seen on several pages keeps the first definition; callers decide priority.
"""

import ast
import re
from pathlib import Path

# page constructors that take a param key; (positional title index or None, has description)
_TOGGLE_CALLS = {"toggle_item_sp"}
_BUTTON_CALLS = {"multiple_button_item_sp"}
_OPTION_CALLS = {"option_item_sp"}
_BIG_BOOL_CALLS = {"BigParamControlSP", "BigParamControl"}
_BIG_MULTI_CALLS = {"BigMultiParamToggle", "BigMultiParamToggleSP"}
_ALL_CALLS = _TOGGLE_CALLS | _BUTTON_CALLS | _OPTION_CALLS | _BIG_BOOL_CALLS | _BIG_MULTI_CALLS

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]*\n[ \t]*")


def _clean(text: str) -> str:
  """Page descriptions use <br> for line breaks; the catalog carries plain text."""
  out = _TAG_RE.sub(" ", text)
  out = _WS_RE.sub("\n", out).replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
  return re.sub(r" {2,}", " ", out).strip()


def _static_string(node: ast.AST) -> str | None:
  """A compile-time string: a literal, or tr("...") possibly concatenated."""
  if isinstance(node, ast.Constant) and isinstance(node.value, str):
    return node.value
  if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
    left, right = _static_string(node.left), _static_string(node.right)
    if left is not None and right is not None:
      return left + right
    return None
  if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("tr", "tr_noop"):
    if node.args:
      inner = _static_string(node.args[0])
      if inner is not None:
        return inner
  if isinstance(node, ast.Lambda):
    return _static_string(node.body)
  if isinstance(node, ast.IfExp):
    left, right = _static_string(node.body), _static_string(node.orelse)
    if left is not None and right is not None:
      return left  # both branches static; first is the common one
  return None


def _static_strings(node: ast.AST) -> list[str]:
  """Every static string in the node, in source order (labels, long descriptions)."""
  out: list[str] = []
  for sub in ast.walk(node):
    s = _static_string(sub) if isinstance(sub, (ast.Constant, ast.BinOp, ast.Call, ast.Lambda, ast.IfExp)) else None
    if s is not None:
      out.append(s)
  return out


_PARAM_KEY_RE = re.compile(r"^[A-Z][A-Za-z0-9_]*$")


def _param_key_node(node: ast.AST, known: set[str] | None) -> str | None:
  """A param-key constant: a quoted identifier, optionally filtered to declared keys."""
  if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
    return None
  key = node.value
  if not key.isidentifier() or not _PARAM_KEY_RE.match(key):
    return None
  if known is not None and key not in known:
    return None
  return key


def _kw(call: ast.Call, name: str) -> ast.AST | None:
  for kw in call.keywords:
    if kw.arg == name:
      return kw.value
  return None


def _arg(call: ast.Call, index: int, name: str) -> ast.AST | None:
  if index < len(call.args):
    return call.args[index]
  return _kw(call, name)


class _PageVisitor(ast.NodeVisitor):
  def __init__(self, known_params: set[str] | None = None) -> None:
    self.controls: dict[str, dict] = {}
    self.known = known_params
    # module/class level string dicts (DESCRIPTIONS = {"key": "text"}), for
    # descriptions the pages hand over as tr(DESCRIPTIONS["key"])
    self.string_dicts: dict[str, dict[str, str]] = {}

  # -- dict shorthand: "KEY": (title, description, callback) ------------- #
  def visit_Assign(self, node) -> None:
    self._maybe_dict_defs(node)
    self.generic_visit(node)

  def visit_AnnAssign(self, node) -> None:
    self._maybe_dict_defs(node)
    self.generic_visit(node)

  def _maybe_dict_defs(self, node) -> None:
    value = getattr(node, "value", None)
    if not (isinstance(value, ast.Dict) and value.keys):
      return
    targets = []
    if isinstance(node, ast.Assign):
      targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
      targets = [node.target.id]
    for name in targets:
      texts = {}
      for key, val in zip(value.keys, value.values, strict=True):
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
          s = _static_string(val)
          if s is not None:
            texts[key.value] = s
      if texts:  # partial is fine: only the keys the page actually resolves matter
        self.string_dicts.setdefault(name, {}).update(texts)

    # toggle-def dicts: "KEY": (lambda: tr("Title"), tr("Description"), None)
    if len(value.keys) < 2:  # a settings dict has several keys; a single one is likely a label map
      return
    for key, val in zip(value.keys, value.values, strict=True):
      if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
        continue
      if not (isinstance(val, ast.Tuple) and val.elts and isinstance(val.elts[0], (ast.Lambda, ast.Call))):
        continue
      entry: dict = {}
      title = _static_string(val.elts[0])
      if title:
        entry["title"] = _clean(title)
        entry["_raw_title"] = title
      if len(val.elts) > 1:
        descr = _static_string(val.elts[1])
        if descr:
          entry["descr"] = _clean(descr)
          entry["_raw_descr"] = descr
      if entry and (self.known is None or key.value in self.known):
        self.controls.setdefault(key.value, entry)

  # -- constructor calls -------------------------------------------------- #
  def visit_Call(self, node: ast.Call) -> None:
    if isinstance(node.func, ast.Name) and node.func.id in _ALL_CALLS:
      self._consume_call(node.func.id, node)
    self.generic_visit(node)

  def _consume_call(self, name: str, call: ast.Call) -> None:
    param_node = _kw(call, "param") or _kw(call, "param_key")
    entry: dict = {}

    if name in _OPTION_CALLS:
      # (title, param, min_value, max_value, description, value_change_step, ...)
      param_node = param_node or (call.args[1] if len(call.args) > 1 else None)
      entry["min"] = self._num(_arg(call, 2, "min_value"))
      entry["max"] = self._num(_arg(call, 3, "max_value"))
      step = self._num(_arg(call, 5, "value_change_step"))
      if step not in (None, 1):
        entry["step"] = step
      value_map = _kw(call, "value_map")
      if value_map is not None and entry["min"] is not None and entry["max"] is not None:
        # the control cycles the mapped values; the range follows them
        keys = [self._num(k) for k in getattr(value_map, "keys", [])]
        if keys and all(k is not None for k in keys):
          entry["min"], entry["max"] = min(keys), max(keys)
      float_scaling = _kw(call, "use_float_scaling")
      if float_scaling is not None and getattr(float_scaling, "value", None) is True:
        entry["float_scaling"] = True
      title_node = _arg(call, 0, "title")
      descr_node = _arg(call, 4, "description")
    elif name in _BUTTON_CALLS:
      # (title, description, buttons, ..., param=)
      title_node = _arg(call, 0, "title")
      descr_node = _arg(call, 1, "description")
      buttons = _arg(call, 2, "buttons") or _kw(call, "buttons")
      if isinstance(buttons, (ast.List, ast.Tuple)):
        labels = [_static_string(elt) for elt in buttons.elts]
        if all(l is not None for l in labels):
          entry["buttons"] = [_clean(l) for l in labels]
    elif name in _BIG_MULTI_CALLS:
      # (text, param, options)
      param_node = param_node or (call.args[1] if len(call.args) > 1 else None)
      options = _arg(call, 2, "options")
      if isinstance(options, (ast.List, ast.Tuple)):
        labels = [_static_string(elt) for elt in options.elts]
        if all(l is not None for l in labels):
          entry["buttons"] = [_clean(l) for l in labels]
      title_node = _arg(call, 0, "text")
      descr_node = _kw(call, "description")
    else:  # toggles: (title, description, ...) or Big(text, param, ..., description=)
      if name in _BIG_BOOL_CALLS:
        title_node = _arg(call, 0, "text")
        descr_node = _kw(call, "description")
      else:
        title_node = _arg(call, 0, "title")
        descr_node = _arg(call, 1, "description")

    if param_node is None:
      # callback-bound toggles carry the key only inside a nested call
      # (`initial_state=ui_state.params.get_bool("KEY")`, `callback=...put_bool("KEY", ...)`).
      for sub in ast.walk(call):
        if isinstance(sub, ast.Call) and sub is not call:
          for a in sub.args:
            key = _param_key_node(a, self.known)
            if key:
              param_node = ast.Constant(value=key)
              break
        if param_node is not None:
          break
    key = _param_key_node(param_node, self.known) if param_node is not None else None
    if key is None:
      return

    def _resolve(node) -> str | None:
      while isinstance(node, ast.Lambda):  # title=lambda: tr(...)
        node = node.body
      s = _static_string(node) if node is not None else None
      if s is not None:
        return s
      # tr(DESCRIPTIONS["key"]) - resolve through the module's string dicts
      if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr" and node.args:
        arg = node.args[0]
        if isinstance(arg, ast.Subscript) and isinstance(arg.value, ast.Name) and \
            isinstance(arg.slice, ast.Constant) and isinstance(arg.slice.value, str):
          return self.string_dicts.get(arg.value.id, {}).get(arg.slice.value)
      return None

    title = _resolve(title_node)
    descr = _resolve(descr_node)
    if title:
      entry["title"] = _clean(title)
      entry["_raw_title"] = title
    if descr:
      entry["descr"] = _clean(descr)
      entry["_raw_descr"] = descr

    existing = self.controls.get(key)
    if existing:
      # first definition wins for labels, but range/labels from a dedicated
      # constructor fill holes a dict shorthand entry left open
      for k, v in entry.items():
        existing.setdefault(k, v)
    else:
      self.controls[key] = entry

  def _num(self, node) -> int | float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
      return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and \
        isinstance(node.operand, ast.Constant) and isinstance(node.operand.value, (int, float)):
      return -node.operand.value
    return None


def _page_sources(settings_dir: Path) -> list[tuple[str, Path]]:
  """(page name, source file) pairs, mirroring web_settings.scan_ui_pages()."""
  out: list[tuple[str, Path]] = []
  for src in sorted(settings_dir.glob("*.py")):
    if src.name.startswith("__"):
      continue
    out.append((src.stem, src))
    for extra in (settings_dir / f"{src.stem}_sub_layouts", settings_dir / src.stem):
      if extra.is_dir():
        out.extend((src.stem, p) for p in sorted(extra.rglob("*.py")))
  for child in sorted(settings_dir.iterdir()):
    if not child.is_dir() or child.name.startswith("__") or child.name.endswith("_sub_layouts"):
      continue
    out.extend((child.name, p) for p in sorted(child.rglob("*.py")))
  return out


def extract_page_controls(settings_dir: str | Path, known_params: set[str] | None = None) -> dict[str, dict]:
  """`{param: {title?, descr?, min?, max?, step?, buttons?, float_scaling?}}` for the page.

  Labels stay untranslated: the caller maps the English text through the UI's own
  translation files when it needs the other locales. `known_params` (the keys the
  params binary declares) keeps callback-bound keys from mis-binding to unrelated
  constants.
  """
  root = Path(settings_dir)
  if not root.is_dir():
    return {}
  visitor = _PageVisitor(known_params)
  for _page, src in _page_sources(root):
    try:
      tree = ast.parse(src.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
      continue
    visitor.visit(tree)
  return visitor.controls


def po_translations(po_path: str | Path) -> dict[str, str]:
  """msgid -> msgstr from a gettext .po file (standard two-entry form).

  Read by hand rather than through a library: the tool must run on a bare
  checkout and the catalog build has no gettext dependency.
  """
  path = Path(po_path)
  if not path.is_file():
    return {}
  try:
    text = path.read_text(encoding="utf-8", errors="ignore")
  except OSError:
    return {}

  out: dict[str, str] = {}
  msgid: list[str] | None = None
  msgstr: list[str] | None = None
  fuzzy = False
  entry_fuzzy = False

  def _flush() -> None:
    nonlocal msgid, msgstr, entry_fuzzy
    if msgid and msgstr is not None and msgstr and not entry_fuzzy:
      out["".join(msgid)] = "".join(msgstr)
    msgid, msgstr, entry_fuzzy = None, None, False

  for line in text.splitlines():
    stripped = line.strip()
    if stripped.startswith("#,") and "fuzzy" in stripped:
      fuzzy = True
    elif stripped.startswith("msgid "):
      _flush()
      msgid, msgstr = [_decode(stripped[6:])], None
      entry_fuzzy, fuzzy = fuzzy, False
    elif stripped.startswith("msgstr "):
      if msgid is not None:
        msgstr = [_decode(stripped[7:])]
    elif stripped.startswith('"') and msgid is not None:
      chunk = _decode(stripped)
      if msgstr is None:
        msgid.append(chunk)
      else:
        msgstr.append(chunk)
  _flush()
  return out


def _decode(token: str) -> str:
  token = token.strip()
  if token.startswith('"') and token.endswith('"'):
    token = token[1:-1]
  return token.encode("utf-8").decode("unicode_escape") if "\\u" in token or "\\x" in token or "\\'" in token or '\\"' in token else token
