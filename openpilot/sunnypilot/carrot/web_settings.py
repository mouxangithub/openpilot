"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

Web settings for the carrot web panel (port 8088): the on-device settings, in a browser.

The on-device UI groups its settings into pages by hand. This module gives the web panel the
same reach without a second copy of that grouping: it reads the on-device page sources and
uses each page's own param keys as the section, so the two cannot drift. Every control is
rendered from the type the params binary declares for the key, and nothing here writes a key
the binary does not declare.

The on-device pages' *labels* are not reproduced - the panel shows the key, the declared type
and the live value, which is what a browser session needs to change a setting remotely. Pages
whose work is not a param write (pairing a phone, viewing a log) are listed under Actions.

The scanning and rendering helpers are pure so they can be tested without a Params handle.
"""
from __future__ import annotations

import html
import os
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

# ---- on-device page scan (pure) -------------------------------------------- #

# the constructors the on-device pages hand a key to
_PARAM_KW_RE = re.compile(r'\bparam\s*=\s*"([A-Za-z0-9_]+)"')
_PARAM_KW2_RE = re.compile(r'\bparam_key\s*=\s*"([A-Za-z0-9_]+)"')
_PARAM_POS_RE = re.compile(r'(?:ParamControlSP|BigParamControlSP|ParamControl)\s*\(\s*[^,()]*,\s*"([A-Za-z0-9_]+)"')
_KEYWORD_ARG_RE = re.compile(r'"([A-Za-z0-9_]+)"')

# helper modules that are not pages of their own; the items module belongs to carrot_tuning
_NOT_PAGES = ("settings",)
_FOLD_INTO = {"carrot_tuning_items": "carrot_tuning"}


def scan_ui_pages(settings_dir: str | os.PathLike[str]) -> dict[str, list[str]]:
  """{page stem: param keys} from the on-device settings sources.

  A page's keys come from its own file plus the sub-layout it splits itself into
  (`<stem>_sub_layouts/`) and, for a page that is a package, its own directory. A page whose
  work is not a param write (pairing a phone, scanning for devices) has no keys and is left
  out; those live under Actions. Order is the file order, and a key listed twice is kept once.
  """
  root = Path(settings_dir)
  if not root.is_dir():
    return {}

  pages: dict[str, list[str]] = {}

  def collect(keys: list[str], *sources: Path) -> list[str]:
    for src in sources:
      if src.is_file() and src.suffix == ".py":
        keys.extend(_keys_in(src))
    seen: list[str] = []
    for k in keys:
      if k not in seen:
        seen.append(k)
    return seen

  for src in sorted(root.glob("*.py")):
    if src.name.startswith("__") or src.stem in _NOT_PAGES:
      continue
    keys = collect([], src)
    for extra in (root / f"{src.stem}_sub_layouts", root / src.stem):
      if extra.is_dir():
        keys = collect(keys, *sorted(extra.rglob("*.py")))
    for helper, owner in _FOLD_INTO.items():
      if src.stem == owner:
        keys = collect(keys, root / f"{helper}.py")
    if keys:
      pages[src.stem] = keys

  for child in sorted(root.iterdir()):
    if not child.is_dir() or child.name.startswith("__") or child.name.endswith("_sub_layouts"):
      continue
    keys = collect([], *sorted(child.rglob("*.py")))
    if keys:
      pages.setdefault(child.name, keys)

  return pages


def _keys_in(path: Path) -> list[str]:
  """Every identifier-shaped string literal in the page source.

  The pages hand their keys to the widgets in several ways (`param=`, `param_key=`, a second
  positional argument, a helper's own argument list), so the source is read for all of them
  and the declared-key filter in group_keys() drops the strings that are not keys. A key the
  page only mentions in passing still lands under that page, which is the page the driver
  would look in.
  """
  try:
    text = path.read_text(encoding="utf-8", errors="ignore")
  except OSError:
    return []
  return _KEYWORD_ARG_RE.findall(text)


def group_keys(pages: dict[str, list[str]], declared: Iterable[str]) -> dict[str, list[str]]:
  """The declared keys arranged by page, with everything the pages do not name last.

  `declared` is what the params binary knows, so a page whose key was removed from the
  binary simply loses it here rather than rendering a control that cannot be written.
  """
  known = set(declared)
  grouped: dict[str, list[str]] = {}
  used: set[str] = set()
  for page, keys in pages.items():
    kept = [k for k in keys if k in known and k not in used]
    used.update(kept)
    if kept:
      grouped[page] = kept
  rest = sorted(known - used)
  if rest:
    grouped["other"] = rest
  return grouped


# ---- rendering (pure) ------------------------------------------------------ #

# what the params binary declares; mirrors ParamKeyType
T_STRING, T_BOOL, T_INT, T_FLOAT, T_TIME, T_JSON, T_BYTES = range(7)

_TYPE_NAMES = {T_STRING: "str", T_BOOL: "bool", T_INT: "int", T_FLOAT: "float",
               T_TIME: "time", T_JSON: "json", T_BYTES: "bytes"}


def type_name(kind: int) -> str:
  return _TYPE_NAMES.get(kind, "?")


def render_control(key: str, kind: int, value: Any) -> str:
  """One row: the key, a control sized to the declared type, and the type's name."""
  name = html.escape(f"p[{key}]", quote=True)
  label = html.escape(key)
  kind_name = type_name(kind)
  open_cell = f'<tr><td>{label}</td>'
  tail = f'<td>{kind_name}</td></tr>'
  if kind == T_BOOL:
    checked = " checked" if _truthy(value) else ""
    return open_cell + f'<td><input type="checkbox" name="{name}" value="1"{checked}></td>' + tail
  if kind in (T_INT, T_FLOAT, T_TIME):
    step = "1" if kind == T_INT else "any"
    shown = html.escape("" if value is None else str(value), quote=True)
    return open_cell + f'<td><input type="number" step="{step}" name="{name}" value="{shown}"></td>' + tail
  if kind == T_JSON:
    shown = html.escape("" if value is None else str(value))
    return open_cell + f'<td><textarea name="{name}" rows="3">{shown}</textarea></td>' + tail
  if kind == T_BYTES:
    return open_cell + f'<td><input type="text" name="{name}" value="" placeholder="(binary; leave blank)"></td>' + tail
  shown = html.escape("" if value is None else str(value), quote=True)
  return open_cell + f'<td><input type="text" name="{name}" value="{shown}"></td>' + tail


def _truthy(value: Any) -> bool:
  return str(value).strip() in ("1", "true", "True")


def parse_form_updates(form: dict[str, list[str]], kinds: dict[str, int]) -> dict[str, str]:
  """The raw (key, string) pairs a settings form carries, for the declared keys only.

  A checkbox that is not sent at all means off, so every declared bool on the page is
  reported; the caller writes only what changed.
  """
  updates: dict[str, str] = {}
  for raw_key, values in form.items():
    if not raw_key.startswith("p[") or not raw_key.endswith("]"):
      continue
    key = raw_key[2:-1]
    if key not in kinds:
      continue
    updates[key] = values[0] if values else ""
  return updates


def render_page(page: str, keys: list[str], kinds: dict[str, int], values: dict[str, Any],
                *, index_href: str = "/settings", saved: int | None = None) -> str:
  rows = "\n".join(render_control(k, kinds.get(k, T_STRING), values.get(k)) for k in keys)
  message = ""
  if saved == 1:
    message = '<p class="ok">已保存</p>'
  elif saved == 0:
    message = '<p class="err">保存失败（键未声明或类型不符）</p>'
  return _PAGE_HEAD.format(title=html.escape(page), message=message, index=html.escape(index_href)) + rows + _PAGE_TAIL


def render_index(grouped: dict[str, list[str]], *, href_fmt: str = "/settings?page={page}") -> str:
  items = []
  for page, keys in grouped.items():
    label = OTHER_LABEL if page == OTHER else page
    href = html.escape(href_fmt.format(page=html.escape(page, quote=True)), quote=True)
    items.append(f'<li><a href="{href}">{html.escape(label)}</a> <span class="n">({len(keys)})</span></li>')
  return _INDEX_HEAD + "\n".join(items) + _INDEX_TAIL


# the group that holds keys no on-device page names: reachable, but not a page setting
OTHER = "other"
OTHER_LABEL = "内部参数（车机设置页未暴露，谨慎修改）"


# ---- live state (needs a params handle) ------------------------------------ #

def ui_settings_dir() -> Path:
  """The on-device settings pages, next to this module's package (openpilot/sunnypilot/carrot)."""
  return Path(__file__).resolve().parents[2] / "selfdrive" / "ui" / "sunnypilot" / "layouts" / "settings"


def collect(params) -> tuple[dict[str, list[str]], dict[str, int], dict[str, Any]]:
  """(grouped pages, key -> declared type, key -> live value) from a params handle.

  The binary's key list is the source of truth: a page key it does not declare is dropped
  rather than rendered as a control that could never be written.
  """
  declared = list(params.all_keys())
  kinds: dict[str, int] = {}
  values: dict[str, Any] = {}
  for key in declared:
    try:
      kinds[key] = int(params.get_type(key))
    except Exception:
      kinds[key] = T_STRING
    try:
      values[key] = params.get(key)
    except Exception:
      values[key] = None
  grouped = group_keys(scan_ui_pages(ui_settings_dir()), declared)
  return grouped, kinds, values


def apply_updates(params, updates: dict[str, str], kinds: dict[str, int]) -> tuple[int, int]:
  """Writes the (key, string) pairs. Returns (written, skipped).

  Each value goes through the setter for the declared type, so the binary's own cast and
  validation decide, and a key whose type does not accept the text is skipped rather than
  written raw.
  """
  written = skipped = 0
  for key, raw in updates.items():
    kind = kinds.get(key, T_STRING)
    try:
      if kind == T_BOOL:
        params.put_bool(key, _truthy(raw))
      elif kind == T_INT:
        params.put(key, int(raw), block=True)
      elif kind in (T_FLOAT, T_TIME):
        params.put(key, float(raw), block=True)
      elif kind == T_BYTES:
        continue  # not editable as text
      else:
        params.put(key, raw, block=True)
      written += 1
    except (ValueError, TypeError, OverflowError):
      skipped += 1
  return written, skipped


# ---- the on-device operations that are not a param write ------------------- #

ACTIONS: tuple[tuple[str, str, str], ...] = (
  # (action id, label, description)
  ("view_error_log", "查看 Error Log", "读取车机 Developer 页同一个 error.log"),
  ("refresh_models", "刷新模型列表", "写入 ModelManager_ClearCache=1，车机随后重新拉取目录"),
  ("clear_mapd_cache", "清除地图缓存", "写入 Mapd_ClearCache=1"),
  ("check_osm_updates", "检查地图数据更新", "写入 OsmDbUpdatesCheck=1"),
  ("backup_now", "立即备份", "写入 BackupManager_CreateBackup=1"),
  ("offroad_on", "强制离车模式", "写入 OffroadMode=1"),
  ("offroad_off", "退出离车模式", "写入 OffroadMode=0"),
)


def _action_row(action: str, label: str, desc: str) -> str:
  form = '<form method="post" action="/action_run">'
  form += f'<input type="hidden" name="action" value="{html.escape(action, quote=True)}">'
  form += '<input type="submit" value="执行"></form>'
  return f'<tr><td>{html.escape(label)}</td><td class="d">{html.escape(desc)}</td><td>{form}</td></tr>'


def render_actions(*, saved: int | None = None, detail: str = "") -> str:
  rows = "\n".join(_action_row(aid, label, desc) for aid, label, desc in ACTIONS)
  message = ""
  if saved is not None:
    body = f"<pre>{html.escape(detail)}</pre>" if "\n" in detail else html.escape(detail)
    cls = "ok" if saved == 1 else "err"
    message = f'<p class="{cls}">{"已完成" if saved == 1 else "失败"}：</p>{body}'
  return _ACTIONS_HEAD.format(message=message) + rows + _ACTIONS_TAIL


_PAGE_HEAD = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>sunnypilot · 设置 · {title}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body {{ font-family: -apple-system, system-ui, sans-serif; margin: 16px; }}
h1 {{ font-size: 18px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: left; vertical-align: top; }}
td:first-child {{ font-family: ui-monospace, monospace; font-size: 13px; }}
input[type=number], input[type=text], textarea {{ width: 100%; box-sizing: border-box; }}
.ok {{ color: #2c7; }} .err {{ color: #d33; }}
</style>
</head>
<body>
<h1>设置 · {title}</h1>
{message}
<form method="post" action="/settings_save">
<input type="hidden" name="page" value="{title}">
<table>
<thead><tr><th>参数</th><th>值</th><th>类型</th></tr></thead>
<tbody>
"""

_PAGE_TAIL = """</tbody>
</table>
<p><input type="submit" value="保存"></p>
</form>
<p><a href="/settings">返回设置索引</a> ·
<a href="/nav_params">导航参数</a> · <a href="/actions">操作</a> ·
<a href="/radar">雷达</a> · <a href="/models">模型镜像</a></p>
</body>
</html>
"""

_INDEX_HEAD = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>sunnypilot · 设置</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body { font-family: -apple-system, system-ui, sans-serif; margin: 16px; max-width: 720px; }
h1 { font-size: 18px; }
ul { line-height: 1.9; padding-left: 20px; }
.n { color: #888; font-size: 13px; }
</style>
</head>
<body>
<h1>设置（与车机设置页一一对应）</h1>
<p>分组来自车机各设置页自身的参数定义，因此不会与车机脱节。点进任一分组即可读写。</p>
<ul>
"""

_INDEX_TAIL = """</ul>
<p><a href="/actions">操作</a> · <a href="/nav_params">导航参数</a> · <a href="/radar">雷达</a> · <a href="/models">模型镜像</a></p>
</body>
</html>
"""

_ACTIONS_HEAD = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>sunnypilot · 操作</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body {{ font-family: -apple-system, system-ui, sans-serif; margin: 16px; max-width: 720px; }}
h1 {{ font-size: 18px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: left; vertical-align: top; }}
.d {{ color: #666; font-size: 13px; }}
pre {{ background: #f6f6f6; border: 1px solid #ddd; padding: 8px; overflow: auto; }}
.ok {{ color: #2c7; }} .err {{ color: #d33; }}
</style>
</head>
<body>
<h1>操作（与车机按钮一一对应）</h1>
{message}
<table>
<thead><tr><th>操作</th><th>说明</th><th></th></tr></thead>
<tbody>
"""

_ACTIONS_TAIL = """</tbody>
</table>
<p><a href="/settings">设置</a> · <a href="/nav_params">导航参数</a> · <a href="/radar">雷达</a> · <a href="/models">模型镜像</a></p>
</body>
</html>
"""
