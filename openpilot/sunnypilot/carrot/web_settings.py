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

Where a fork param has a Chinese title/description (carrot/tools/sp_param_labels.py), the panel
shows it above the raw key, so a remote session reads the same label as the on-device UI; keys
without a label still show the raw name. Pages whose work is not a param write (pairing a phone,
viewing a log) are listed under Actions.

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


_LABELS: dict[str, tuple[str, str]] | None = None


def param_labels() -> dict[str, tuple[str, str]]:
  """key -> (Chinese title, Chinese description) for the fork's labelled params.

  Loaded lazily from the same catalog the on-device UI's labels are generated from, so the
  web panel cannot drift from it. A module that fails to import leaves every key unlabelled
  rather than failing the page.
  """
  global _LABELS
  if _LABELS is None:
    try:
      from openpilot.sunnypilot.carrot.tools.sp_param_labels import PARAM_LABELS
      # (en_title, en_descr, zh_title, zh_descr) -> prefer the Chinese pair
      _LABELS = {key: (zh_title or en_title, zh_descr or en_descr)
                 for key, (en_title, en_descr, zh_title, zh_descr) in PARAM_LABELS.items()}
    except Exception:
      _LABELS = {}
  return _LABELS


def _label_html(key: str, labels: dict[str, tuple[str, str]]) -> str:
  """The Chinese title (bold) with the raw key underneath; just the key when unlabelled."""
  entry = labels.get(key)
  safe_key = html.escape(key)
  if not entry:
    return safe_key
  title, descr = html.escape(entry[0] or key, quote=True), html.escape(entry[1] or "", quote=True)
  label = f'<span class="t">{title}</span><br><span class="k">{safe_key}</span>'
  if descr:
    label += f'<br><span class="d2">{descr}</span>'
  return label


def render_control(key: str, kind: int, value: Any, labels: dict[str, tuple[str, str]] | None = None) -> str:
  """One row: the Chinese label (falling back to the raw key), a control sized to the declared
  type, and the type's name."""
  labels = labels if labels is not None else {}
  name = html.escape(f"p[{key}]", quote=True)
  label = _label_html(key, labels)
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
                *, index_href: str = "/settings", saved: int | None = None,
                labels: dict[str, tuple[str, str]] | None = None) -> str:
  labels = labels if labels is not None else {}
  rows = "\n".join(render_control(k, kinds.get(k, T_STRING), values.get(k), labels) for k in keys)
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

# Keys the browser never sees, whatever page they land in (the carrot server's
# counterpart of the upstream web app's `hidden` field flags). Everything here
# is either a documented off-UI override, a downloader state machine the
# manager owns, or jetlink's internal state: editing the raw value from a
# browser would desync the thing that actually manages it. The ones a driver
# legitimately controls from a browser get real controls on the dedicated
# /models page instead.
HIDDEN_KEYS: frozenset[str] = frozenset({
  # documented off-UI overrides (see docs/git-proxy-auto-source.md): the
  # on-device UI was deliberately removed from these
  "ModelManager_MirrorUrl",
  "ModelManager_GithubProxy",
  # jetlink's own state: the link setting is a four-way choice the /models
  # page drives; the rest are its runtime snapshots
  "JetlinkLink",
  "JetlinkSpec",
  "JetlinkModelPointers",
  "JetlinkChargePhone",
  "AcceleratorProgress",
  # the model manager's state machine: slots are switched by selecting a
  # model on /models (DownloadRef), never by pasting a bundle JSON
  "ModelManager_ActiveBundle",
  "ModelManager_ActiveBundleChestnut",
  "ModelManager_ModelsCache",
  "ModelManager_ModelsCache_Chestnut",
  "ModelManager_LastSyncTime",
  "ModelManager_LastSyncTime_Chestnut",
  "ModelManager_DownloadRef",
})


def filter_hidden(grouped: dict[str, list[str]]) -> dict[str, list[str]]:
  """Drop the hidden keys from every group; groups that lose everything go too."""
  kept: dict[str, list[str]] = {}
  for page, keys in grouped.items():
    visible = [k for k in keys if k not in HIDDEN_KEYS]
    if visible:
      kept[page] = visible
  return kept


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
  return filter_hidden(grouped), kinds, values


def apply_updates(params, updates: dict[str, str], kinds: dict[str, int]) -> tuple[int, int]:
  """Writes the (key, string) pairs. Returns (written, skipped).

  Each value goes through the setter for the declared type, so the binary's own cast and
  validation decide, and a key whose type does not accept the text is skipped rather than
  written raw.
  """
  written = skipped = 0
  for key, raw in updates.items():
    if key in HIDDEN_KEYS:
      skipped += 1
      continue
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
td:first-child {{ font-size: 14px; }}
.t {{ font-weight: 600; }}
.k {{ font-family: ui-monospace, monospace; font-size: 12px; color: #888; }}
.d2 {{ display: block; color: #666; font-size: 12px; font-weight: normal; margin-top: 2px; }}
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
<p><a href="/models">模型</a> · <a href="/settings">返回设置索引</a> ·
<a href="/actions">操作</a> ·
<a href="/radar">雷达</a></p>
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
<p><a href="/actions">操作</a> · <a href="/nav_params">导航参数</a> · <a href="/radar">雷达</a></p>
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
<p><a href="/models">模型</a> · <a href="/settings">设置</a> · <a href="/nav_params">导航参数</a> · <a href="/radar">雷达</a></p>
</body>
</html>
"""


# ---- the models page: the on-device Models panel, in a browser ------------ #

# The on-device Models panel is a hand-built feature page (selectors, the
# Jetlink four-way switch, live download status, confirm dialogs), not a table
# of params, so the auto-scan cannot reproduce it. This section mirrors it
# 1:1 - same slots, same four Jetlink modes, same confirm wording, same
# Chinese labels - over browser-native controls, reading and writing exactly
# the keys and values the on-device page does.

_SOURCES = ("qcom", "chestnut")
_ACTIVE_KEYS = {"qcom": "ModelManager_ActiveBundle", "chestnut": "ModelManager_ActiveBundleChestnut"}
_CACHE_KEYS = {"qcom": "ModelManager_ModelsCache", "chestnut": "ModelManager_ModelsCache_Chestnut"}
_SYNC_KEYS = ("ModelManager_LastSyncTime", "ModelManager_LastSyncTime_Chestnut")
_DOWNLOAD_KEY = "ModelManager_DownloadRef"
_JETLINK_KEY = "JetlinkLink"
_JETLINK_MODES = ("off", "usb", "ios", "wifi")
# titles as the on-device multiple-button renders them (tr of LINK_MODE_TITLES)
_JETLINK_TITLES = {"off": "关", "usb": "USB", "ios": "iOS", "wifi": "Wi-Fi"}

_JETLINK_DESC = "在接入 comma 的电脑或手机上运行大模型。会关闭 ADB。大模型就绪前由小模型驾驶。"


def _bundle_folder(bundle) -> str:
  for override in getattr(bundle, "overrides", []) or []:
    if getattr(override, "key", "") == "folder":
      return getattr(override, "value", "")
  return ""


def collect_models(params) -> dict[str, Any]:
  """The models panel's live state from params only - no UI imports, no
  cereal messages. Bundle lists come from the manager's cached catalogs; when
  the manager has never fetched one the slot simply offers Default."""
  from openpilot.sunnypilot.models.helpers import get_selected_bundle
  from openpilot.sunnypilot.models.fetcher import get_cached_bundles
  from openpilot.sunnypilot.models.model_sizes import bundle_download_fraction
  from openpilot.common.hardware.hw import Paths
  from openpilot.selfdrive.ui.sunnypilot.storage_info import directory_size, format_size

  state: dict[str, Any] = {}

  def bundle_entry(bundle) -> dict[str, str]:
    return {"ref": bundle.ref, "name": bundle.displayName, "folder": _bundle_folder(bundle)}

  for source in _SOURCES:
    active = None
    try:
      active = get_selected_bundle(params, source)
    except Exception:
      pass
    bundles: list[dict[str, str]] = []
    try:
      bundles = [bundle_entry(b) for b in get_cached_bundles(params, source)]
    except Exception:
      pass
    state[f"{source}_active_name"] = active.displayName if active is not None else "Default"
    state[f"{source}_bundles"] = bundles

  # the in-flight download: which pick, and how much of it is on disk
  download_ref = params.get(_DOWNLOAD_KEY)
  if isinstance(download_ref, bytes):
    download_ref = download_ref.decode("utf-8", "replace")
  state["download_ref"] = download_ref or ""
  state["download_name"] = ""
  state["download_fraction"] = None
  if download_ref:
    for source in _SOURCES:
      for bundle in state[f"{source}_bundles"]:
        if bundle["ref"] == download_ref:
          state["download_name"] = bundle["name"]
          try:
            state["download_fraction"] = bundle_download_fraction(
              next(b for b in get_cached_bundles(params, source) if b.ref == download_ref),
              Paths.model_root())
          except Exception:
            pass
          break

  # the Jetlink switch: the stored index, and what its status line says.
  # The on-device line reads the params-pass snapshot; the browser reads the
  # same facts out of JetlinkSpec, the JSON jetlink persists for exactly that.
  index = params.get(_JETLINK_KEY, return_default=True)
  mode = _JETLINK_MODES[index] if isinstance(index, int) and 0 <= index < len(_JETLINK_MODES) else "off"
  state["jetlink_mode"] = mode
  state["jetlink_status"] = _jetlink_status(params)
  state["offroad"] = _truthy(params.get("IsOffroad")) or _truthy(params.get("OffroadMode"))

  state["cache_size"] = format_size(directory_size(Paths.model_root()))

  # the panel's toggles and sliders, as the on-device widgets hold them
  state["blendful"] = params.get_bool("Blendful")
  state["lane_turn_desire"] = params.get_bool("LaneTurnDesire")
  state["lagd"] = params.get_bool("LagdToggle")
  state["lane_turn_value"] = int(params.get("LaneTurnValue", return_default=True) or 0)
  state["lagd_delay"] = int(params.get("LagdToggleDelay", return_default=True) or 0)
  state["camera_offset"] = int(params.get("CameraOffset", return_default=True) or 0)
  return state


def _jetlink_status(params) -> str:
  """The one-line port status under the switch, the on-device wording.

  Read from JetlinkSpec (jetlink's persisted snapshot): Wi-Fi points at the
  hotspot, a connected host names its transport, and the CC pin says whether
  anything is plugged in.
  """
  spec_raw = params.get("JetlinkSpec")
  if isinstance(spec_raw, bytes):
    spec_raw = spec_raw.decode("utf-8", "replace")
  try:
    spec = json.loads(spec_raw) if isinstance(spec_raw, str) and spec_raw else {}
  except ValueError:
    spec = {}
  mode = spec.get("mode")
  if mode == "wifi":
    return "请接入手机热点，并在手机上打开 Jetlink。"
  port_state = spec.get("port_state") or ("connected" if spec.get("present") else None)
  if port_state is None and spec.get("port") is not None:
    port_state = "empty" if spec.get("port") == "empty" else "device"
  if port_state == "connected":
    transport = spec.get("transport") or ""
    return f"Jetlink 已连接：{transport}。"
  if port_state == "empty":
    return "USB 端口上没有设备。"
  if port_state == "device":
    return "USB 端口上有设备。"
  return ""


def _options_html(state: dict[str, Any], source: str) -> str:
  """A select's options: Default first, then the catalog grouped by folder."""
  groups: dict[str, list[dict[str, str]]] = {}
  for bundle in state[f"{source}_bundles"]:
    groups.setdefault(bundle["folder"], []).append(bundle)
  parts = [f'<option value="Default">{"Default"}</option>']
  for folder in sorted(groups):
    label = html.escape(folder or "其他")
    parts.append(f'<optgroup label="{label}">')
    for bundle in groups[folder]:
      selected = " selected" if state[f"{source}_active_name"] == bundle["name"] else ""
      parts.append(f'<option value="{html.escape(bundle["ref"], quote=True)}"{selected}>{html.escape(bundle["name"])}</option>')
    parts.append("</optgroup>")
  return "".join(parts)


def render_models_page(state: dict[str, Any], *, saved: int | None = None) -> str:
  """The Models panel as feature cards, in the on-device panel's own wording."""
  message = ""
  if saved == 1:
    message = '<p class="ok">已保存</p>'
  elif saved == 0:
    message = '<p class="err">保存失败</p>'

  def slot(source: str, title: str) -> str:
    active = html.escape(state[f"{source}_active_name"])
    options = _options_html(state, source)
    return (f'<div class="card"><div class="t">{title}</div>'
            f'<div class="cur">当前：{active}</div>'
            f'<form method="post" action="/models_save">'
            f'<input type="hidden" name="action" value="select_{source}">'
            f'<select name="ref">{options}</select>'
            f'<input type="submit" value="选择模型"></form></div>')

  jetlink_buttons = []
  for i, mode in enumerate(_JETLINK_MODES):
    checked = " checked" if state["jetlink_mode"] == mode else ""
    disabled = "" if state["offroad"] else " disabled"
    jetlink_buttons.append(
      f'<label class="rb"><input type="radio" name="jetlink" value="{i}"{checked}{disabled}> {_JETLINK_TITLES[mode]}</label>')
  jetlink_status = html.escape(state["jetlink_status"])
  jetlink_note = "" if state["offroad"] else '<div class="d2">熄火状态下才能切换（gadget 重绑会断开已连接的设备）。</div>'

  download = state["download_ref"]
  if download:
    frac = state["download_fraction"]
    percent = f"{frac * 100:.0f}%" if isinstance(frac, (int, float)) else "--"
    download_html = (
      f'<div class="card"><div class="t">下载中</div>'
      f'<div class="cur">{html.escape(state["download_name"] or download)} · {percent}（磁盘占用估算）</div>'
      f'<form method="post" action="/models_save"><input type="hidden" name="action" value="cancel_download">'
      f'<input type="submit" value="取消下载"></form></div>')
  else:
    download_html = (
      f'<div class="card"><div class="t">模型状态</div>'
      f'<div class="cur">没有正在进行的下载</div></div>')

  def checkbox(name: str, title: str, checked: bool, descr: str = "") -> str:
    d = f'<div class="d2">{html.escape(descr)}</div>' if descr else ""
    mark = " checked" if checked else ""
    return (f'<div class="row"><label><input type="checkbox" name="{name}" value="1"{mark}> '
            f'<span class="t">{title}</span></label>{d}</div>')

  def number(name: str, title: str, value: int, shown: str, descr: str) -> str:
    return (f'<div class="row"><form method="post" action="/models_save">'
            f'<input type="hidden" name="action" value="values">'
            f'<span class="t">{title}</span> '
            f'<input type="number" step="1" name="{name}" value="{value}"> '
            f'<span class="d2">{html.escape(shown)} · {html.escape(descr)}</span> '
            f'<input type="submit" value="保存"></form></div>')

  cache_size = html.escape(state["cache_size"])
  confirm = ("return confirm('这将从缓存中删除除当前活跃模型外的所有已下载模型，确定吗？');")
  models_page = f"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>sunnypilot · 模型</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body {{ font-family: -apple-system, system-ui, sans-serif; margin: 16px; max-width: 720px; }}
h1 {{ font-size: 18px; }}
h2 {{ font-size: 15px; margin: 18px 0 6px; color: #555; }}
.card, .row {{ border: 1px solid #ddd; border-radius: 8px; padding: 10px 12px; margin-bottom: 10px; }}
.row {{ border-radius: 6px; }}
.t {{ font-weight: 600; }}
.cur {{ margin: 6px 0; color: #444; }}
.d2 {{ color: #666; font-size: 12px; margin-top: 2px; }}
select, input[type=number] {{ padding: 4px 6px; }}
input[type=submit] {{ padding: 5px 12px; }}
.rb {{ margin-right: 14px; }}
.ok {{ color: #2c7; }} .err {{ color: #d33; }}
form {{ margin: 4px 0; }}
</style>
</head>
<body>
<h1>模型</h1>
{message}
<h2>模型选择</h2>
{slot("qcom", "小模型")}
{slot("chestnut", "大模型")}
{download_html}
<h2>外接算力连接</h2>
<div class="card">
  <div class="t">Jetlink</div>
  <div class="cur">{_JETLINK_DESC} {jetlink_status}</div>
  <form method="post" action="/models_save">
    <input type="hidden" name="action" value="jetlink">
    {''.join(jetlink_buttons)}
    <input type="submit" value="保存">
  </form>
  {jetlink_note}
</div>
<h2>操作</h2>
<div class="row">
  <form method="post" action="/models_save" onsubmit="{confirm}">
    <input type="hidden" name="action" value="clear_cache">
    <span class="t">清除模型缓存</span> <span class="d2">当前占用 {cache_size}</span>
    <input type="submit" value="清除">
  </form>
  <form method="post" action="/models_save">
    <input type="hidden" name="action" value="refresh">
    <span class="t">刷新模型列表</span>
    <input type="submit" value="刷新">
  </form>
</div>
<h2>转向与显示</h2>
<div class="card">
{checkbox("blendful", "融合车道（测试版）", state["blendful"],
          "在模型自身转向的基础上，轻柔地把车辆推回车道中央；车道线越清晰修正越强。遇到障碍会自动避让。默认模型不可用。")}
{checkbox("lane_turn_desire", "使用变道转向意图", state["lane_turn_desire"],
          "如果你以 32 km/h 或更低的速度行驶并打开转向灯，车辆将在最近的可行驶路径上规划该方向的转弯。")}
{checkbox("lagd", "自学习转向延迟", state["lagd"],
          "开启后车辆会学习并自适应转向响应时间。关闭则使用固定的转向响应时间。保持开启即原厂 openpilot 体验。")}
</div>
<div class="card">
{number("LaneTurnValue", "调整变道转向速度", state["lane_turn_value"],
        f"{round(state['lane_turn_value'] / 100 * 1.609344)} km/h", "变道转向意图的最大速度，默认 19 mph。")}
{number("LagdToggleDelay", "调整软件延迟", state["lagd_delay"],
        f"{state['lagd_delay'] / 100:.2f} s", "关闭自学习转向延迟时使用的软件延迟，默认 0.20s。")}
{number("CameraOffset", "调整相机偏移", state["camera_offset"],
        f"{state['camera_offset'] / 100:.2f} m", "虚拟移动相机视角，正值模型中心偏左，负值偏右。")}
</div>
<p><a href="/models">模型</a> · <a href="/settings">设置</a> · <a href="/actions">操作</a> · <a href="/nav_params">导航参数</a> · <a href="/radar">雷达</a></p>
</body>
</html>
"""
  return models_page


def apply_models_form(params, form: dict[str, list[str]]) -> tuple[bool, str]:
  """Run one models-page action. Every path goes through the same key the
  on-device widget writes, and every model ref is checked against the cached
  catalog before it is trusted."""
  action = (form.get("action", [""])[0] or "").strip()
  if action == "clear_cache":
    params.put_bool("ModelManager_ClearCache", True)
    return True, "已写入 ModelManager_ClearCache，车机随后清除（保留活跃模型）"
  if action == "cancel_download":
    params.remove(_DOWNLOAD_KEY)
    return True, "已取消下载"
  if action == "refresh":
    for key in _SYNC_KEYS:
      params.put(key, 0)
    return True, "已请求重新拉取模型目录"
  if action == "jetlink":
    raw = form.get("jetlink", ["0"])[0]
    try:
      index = int(raw)
    except ValueError:
      return False, "无效的模式"
    if not 0 <= index < len(_JETLINK_MODES):
      return False, "无效的模式"
    if not (_truthy(params.get("IsOffroad")) or _truthy(params.get("OffroadMode"))):
      return False, "车辆通电时不能切换外接算力（gadget 重绑会断开已连接的设备）"
    params.put(_JETLINK_KEY, index, block=True)
    return True, f"外接算力已切换为 {_JETLINK_TITLES[_JETLINK_MODES[index]]}"
  if action in ("select_qcom", "select_chestnut"):
    # imported here so the parameter-only actions never pull the cereal stack
    from openpilot.sunnypilot.models.helpers import ACTIVE_BUNDLE_KEYS
    from openpilot.sunnypilot.models.fetcher import get_cached_bundles
    source = action.removeprefix("select_")
    ref = (form.get("ref", [""])[0] or "").strip()
    if ref == "Default":
      params.remove(_ACTIVE_KEYS[source])
      return True, "已恢复默认模型"
    if not ref:
      return False, "未选择模型"
    valid = {b.ref for b in get_cached_bundles(params, source)}
    if ref not in valid:
      return False, "所选模型不在目录中（请先刷新模型列表）"
    params.put(_DOWNLOAD_KEY, ref)
    return True, "已开始下载所选模型"
  if action == "values":
    written = []
    for key in ("Blendful", "LaneTurnDesire", "LagdToggle"):
      params.put_bool(key, _truthy(form.get(key, ["0"])[0] or "0"))
      written.append(key)
    for key in ("LaneTurnValue", "LagdToggleDelay", "CameraOffset"):
      raw = (form.get(key, [""])[0] or "").strip()
      if not raw:
        continue
      try:
        params.put(key, int(raw), block=True)
        written.append(key)
      except (ValueError, TypeError, OverflowError):
        return False, f"{key} 的值无效"
    return True, "已保存 " + ", ".join(written)
  return False, "未知操作"
