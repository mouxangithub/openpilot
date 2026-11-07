"""
Copyright (c) 2026-, mouxan.

Storage settings page, restored 1:1 from the webui storage panel
(webui/web/static/js/panels.js renderStoragePanel + webui/server/bridge/storage_api).

The webui panel is the truth source this page was copied from, so both the
numbers and the operations come from the very same backend module:
``webui.server.bridge.storage_api.snapshot_storage`` / ``clear_storage``.
When the webui package is not importable (a stripped tree), a minimal local
fallback keeps the page alive with the subset it can compute itself.

Structure mirrored from the webui panel, top to bottom:

- a usage summary ("used / total · free") plus an explicit Refresh button,
- one segmented, colour-coded usage bar over the eight space categories and
  the free remainder, with a full legend (dot, label, size, percent),
- an OTA staging note when the updater workspace is occupied,
- an External SSD section when one is mounted (bar + legend, routes only),
- low (<10% free) / critical (<2% free) space warnings,
- a Cleanup section with the seven webui actions in webui order, each showing
  "About {size} can be freed", confirmed with the webui wording, gated to
  offroad, and reporting "Freed {size}" through a status row (the webui toast).

Route recordings deliberately honour the uploader's own rules here - starred
(preserve xattr), preserved and locked segments are never touched - because
the deletion code is the webui's, not a re-implementation.
"""
import os
import platform
import threading

import pyray as rl

from openpilot.common.params import Params
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.selfdrive.ui.sunnypilot.layouts.settings.osm import MAP_PATH, delete_downloaded_maps
from openpilot.selfdrive.ui.sunnypilot.storage_info import (
  cached_bundle_sizes, directory_size, disk_usage, format_size, model_file_names, model_root_size,
)
from openpilot.system.ui.lib.application import gui_app, FontWeight, font_fallback
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.widgets import DialogResult, Widget
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog
from openpilot.system.ui.widgets.list_view import text_item, TextAction
from openpilot.system.ui.widgets.scroller_tici import Scroller

from openpilot.system.ui.sunnypilot.lib.styles import style
from openpilot.system.ui.sunnypilot.lib.utils import NoElideButtonAction
from openpilot.system.ui.sunnypilot.widgets.list_view import ListItemSP, section_heading_sp

try:
  # The webui submodule is the truth source for both the snapshot numbers and
  # the cleanup actions; importing it keeps the two UIs permanently in sync.
  from webui.server.bridge.storage_api import clear_storage, snapshot_storage
  HAS_WEBUI_BACKEND = True
except Exception:
  HAS_WEBUI_BACKEND = False

# statvfs needs a path that lives on the device's data filesystem.
from openpilot.common.hardware.hw import Paths
_DISK_PROBE_PATH = str(Paths.log_root())

# webui CAT_META colours (panels.js renderStoragePanel).
CATEGORY_COLORS = {
  "routes": rl.Color(74, 144, 217, 255),      # #4A90D9
  "models": rl.Color(155, 89, 182, 255),      # #9B59B6
  "maps": rl.Color(39, 174, 96, 255),         # #27AE60
  "software": rl.Color(142, 142, 147, 255),   # #8E8E93
  "logs": rl.Color(212, 172, 13, 255),        # #D4AC0D
  "ota_staging": rl.Color(230, 126, 34, 255),  # #E67E22
  "scons_cache": rl.Color(52, 152, 219, 255),  # #3498DB
  "other": rl.Color(85, 85, 85, 255),         # #555555
}
FREE_COLOR = rl.Color(58, 58, 58, 255)        # .opui-storage-bar-seg--free
LEGEND_TEXT_COLOR = rl.Color(200, 200, 200, 255)  # .opui-storage-legend-row
LEGEND_PCT_COLOR = rl.Color(136, 136, 136, 255)   # .opui-storage-legend-pct
WARN_COLOR = rl.Color(230, 126, 34, 255)
DANGER_COLOR = rl.Color(231, 76, 60, 255)

CATEGORY_ORDER = ("routes", "models", "maps", "software", "logs", "ota_staging", "scons_cache", "other")
BAR_HEIGHT = 44  # webui: 32px at its 40px body font; this UI runs 50px rows
BAR_MIN_SEG = 3  # webui: max(0.4%, min-width 2px) - keep every present category visible
STARRED_LIST_MAX = 6

KB = 1024
MB = 1024 ** 2
GB = 1024 ** 3


def _fmt_bytes(num_bytes) -> str:
  """webui formatStorageBytes: 1 decimal GB/MB, rounded KB, raw bytes."""
  n = num_bytes or 0
  if not isinstance(n, (int, float)) or n < 0:
    return "-"
  if n >= GB:
    return f"{n / GB:.1f} GB"
  if n >= MB:
    return f"{n / MB:.1f} MB"
  if n >= KB:
    return f"{round(n / KB)} KB"
  return f"{n} B"


class _SegmentedBar(Widget):
  """webui .opui-storage-bar: rounded bar, one coloured segment per category + free."""

  def __init__(self):
    super().__init__()
    self._segments: list[tuple[rl.Color, float]] = []
    self._free_fraction = 1.0

  def update(self, segments: list[tuple[rl.Color, float]], free_fraction: float):
    self._segments = segments
    self._free_fraction = max(0.0, free_fraction)

  def set_parent_rect(self, parent_rect: rl.Rectangle) -> None:
    super().set_parent_rect(parent_rect)
    self._rect.width = parent_rect.width - 2 * style.ITEM_PADDING
    self._rect.height = BAR_HEIGHT

  def _render(self, _):
    if not self.is_visible or self._parent_rect is None:
      return
    inner = rl.Rectangle(self._rect.x + 4, self._rect.y + 4, self._rect.width - 8, self._rect.height - 8)
    if inner.width <= 0:
      return
    rl.draw_rectangle_rounded(self._rect, 0.5, 10, rl.Color(26, 26, 26, 255))
    x = inner.x
    for color, fraction in self._segments:
      if fraction <= 0:
        continue
      w = max(BAR_MIN_SEG, inner.width * fraction)
      w = min(w, inner.x + inner.width - x)
      if w <= 0:
        break
      rl.draw_rectangle_rounded(rl.Rectangle(x, inner.y, w, inner.height), 0.35, 8, color)
      x += w + 2
    if self._free_fraction > 0 and x < inner.x + inner.width:
      w = max(BAR_MIN_SEG, inner.width * self._free_fraction)
      rl.draw_rectangle_rounded(rl.Rectangle(x, inner.y, min(w, inner.x + inner.width - x), inner.height), 0.35, 8, FREE_COLOR)


class _LegendRow(Widget):
  """webui .opui-storage-legend-row: colour dot, label, size, percent."""

  def __init__(self, label: str, color: rl.Color, free: bool = False):
    super().__init__()
    self._label = label
    self._color = color
    self._free = free
    self._size_text = "-"
    self._pct_text = "0%"

  def update(self, size_text: str, pct_text: str):
    self._size_text = size_text
    self._pct_text = pct_text

  def set_parent_rect(self, parent_rect: rl.Rectangle) -> None:
    super().set_parent_rect(parent_rect)
    self._rect.width = parent_rect.width
    self._rect.height = 56

  def _render(self, _):
    if not self.is_visible or self._parent_rect is None:
      return
    font = gui_app.font(FontWeight.NORMAL)
    pad = style.ITEM_PADDING + 10
    cy = self._rect.y + self._rect.height / 2
    # dot (free dot gets the webui's darker fill + outline)
    if self._free:
      rl.draw_circle(int(self._rect.x + pad + 10), int(cy), 10, FREE_COLOR)
      rl.draw_circle_lines(int(self._rect.x + pad + 10), int(cy), 10, rl.Color(85, 85, 85, 255))
    else:
      rl.draw_circle(int(self._rect.x + pad + 10), int(cy), 10, self._color)
    # label
    lx = self._rect.x + pad + 34
    rl.draw_text_ex(font_fallback(font, self._label), self._label, rl.Vector2(lx, cy - style.ITEM_TEXT_FONT_SIZE / 2),
                    style.ITEM_TEXT_FONT_SIZE, 0, LEGEND_TEXT_COLOR)
    # size, then percent at the right edge
    size_w = measure_text_cached(font, self._size_text, style.ITEM_TEXT_FONT_SIZE).x
    pct_w = measure_text_cached(font, self._pct_text, style.ITEM_TEXT_FONT_SIZE).x
    rl.draw_text_ex(font_fallback(font, self._size_text), self._size_text,
                    rl.Vector2(self._rect.x + self._rect.width - pad - pct_w - 30 - size_w, cy - style.ITEM_TEXT_FONT_SIZE / 2),
                    style.ITEM_TEXT_FONT_SIZE, 0, LEGEND_TEXT_COLOR)
    rl.draw_text_ex(font_fallback(font, self._pct_text), self._pct_text,
                    rl.Vector2(self._rect.x + self._rect.width - pad - pct_w, cy - style.ITEM_TEXT_FONT_SIZE / 2),
                    style.ITEM_TEXT_FONT_SIZE, 0, LEGEND_PCT_COLOR)


class StorageLayout(Widget):
  def __init__(self):
    super().__init__()
    self._mem_params = Params("/dev/shm/params") if platform.system() != "Darwin" else ui_state.params
    self._sizes: dict[str, int] = {"qcom": 0, "chestnut": 0}
    self._model_clearable: dict[str, int] = {"qcom": 0, "chestnut": 0}
    self._data: dict | None = None
    self._busy: set[str] = set()
    self._scanning = False
    self._initialize_items()
    self._scroller = Scroller(self.items, line_separator=True, spacing=0)
    self._refresh()

  # ------------------------------------------------------------------ items
  def _initialize_items(self):
    self._disk_item = text_item(tr("Storage Used"), tr("Calculating..."))
    self._refresh_btn = ListItemSP(
      tr("Refresh"),
      description=tr("Rescan the storage usage now. The scan walks every directory and can take a moment."),
      action_item=NoElideButtonAction(tr("SCAN"), enabled=lambda: not self._scanning),
      callback=self._on_refresh,
    )

    self._bar = _SegmentedBar()
    self._legend_rows = {cid: _LegendRow(_category_label(cid), CATEGORY_COLORS[cid]) for cid in CATEGORY_ORDER}
    self._legend_free = _LegendRow(tr("Free"), FREE_COLOR, free=True)

    self._ota_note = text_item(
      tr("OTA Staging"),
      "",
      description=tr("OTA update workspace used by the system updater. Usually released after an update is applied."))
    self._ota_note.action_item.set_text("")

    self._warn_item = ListItemSP(tr("Storage is running low (less than 10% free)."), title_color=WARN_COLOR)

    # External SSD section (hidden until the webui snapshot reports one mounted)
    self._ext_heading = section_heading_sp(tr("External SSD"))
    self._ext_disk_item = text_item(tr("Storage Used"), tr("Calculating..."))
    self._ext_bar = _SegmentedBar()
    self._ext_legend_routes = _LegendRow(tr("Routes"), CATEGORY_COLORS["routes"])
    self._ext_legend_free = _LegendRow(tr("Free"), FREE_COLOR, free=True)

    # Cleanup rows, webui CLEAR_ACTIONS order. Description lambdas keep the
    # estimate line ("About {size} can be freed") live as data refreshes.
    self._action_defs = [
      ("routes", tr("Clear route recordings"), self._routes_desc),
      ("routes_starred", tr("Clear starred routes"), self._starred_desc),
      ("maps", tr("Clear map cache"), self._plain_desc(
        tr("Removes downloaded OSM map data. Maps can be downloaded again from OSM settings."))),
      ("models_cache", tr("Clear model cache"), self._plain_desc(
        tr("Removes downloaded models except the one currently in use."))),
      ("logs", tr("Clear logs"), self._plain_desc(
        tr("Removes system logs and crash dumps."))),
      ("scons_cache", tr("Clear build cache"), self._plain_desc(
        tr("Removes the scons build cache. The next compile will take significantly longer."))),
      ("download_cache", tr("Clear download cache"), self._plain_desc(
        tr("Removes temporary download files. Safe to clear."))),
    ]
    self._action_rows: dict[str, ListItemSP] = {}
    for category, title, desc in self._action_defs:
      row = ListItemSP(
        title,
        description=desc,
        action_item=NoElideButtonAction(tr("CLEAR"), enabled=lambda c=category: self._can_clear(c)),
        callback=lambda c=category: self._clear_category(c),
      )
      row.action_item.set_value("")
      self._action_rows[category] = row

    # sp-specific split of the model cache (small = qcom, big = chestnut):
    # per-source sizes plus a per-source clear that keeps the bundle in use
    self._model_rows: dict[str, ListItemSP] = {}
    for source, title in (("qcom", tr("Small Model")), ("chestnut", tr("Big Model"))):
      row = ListItemSP(
        title,
        description=self._model_desc(source),
        action_item=NoElideButtonAction(tr("CLEAR"), enabled=lambda s=source: self._can_clear_model(s)),
        callback=lambda s=source: self._clear_model_source(s),
      )
      row.action_item.set_value("")
      self._model_rows[source] = row

    # starred routes list under the routes_starred action (webui: up to 6 + more)
    self._starred_rows = [ListItemSP("", action_item=TextAction("")) for _ in range(STARRED_LIST_MAX)]
    self._starred_more = ListItemSP("", action_item=TextAction(""))

    self._status_item = text_item(tr("Last Cleanup"), tr("Nothing cleared yet"))
    self._offroad_hint = ListItemSP(tr("Cleanup is only available while offroad."), title_color=WARN_COLOR)

    self.items = [
      section_heading_sp(tr("Device Storage")),
      self._disk_item,
      self._refresh_btn,
      self._bar,
      *[self._legend_rows[cid] for cid in CATEGORY_ORDER],
      self._legend_free,
      self._ota_note,
      self._warn_item,
      self._ext_heading,
      self._ext_disk_item,
      self._ext_bar,
      self._ext_legend_routes,
      self._ext_legend_free,
      section_heading_sp(tr("Cleanup")),
      self._action_rows["routes"],
      self._action_rows["routes_starred"],
      *self._starred_rows,
      self._starred_more,
      self._action_rows["maps"],
      self._action_rows["models_cache"],
      self._model_rows["qcom"],
      self._model_rows["chestnut"],
      self._action_rows["logs"],
      self._action_rows["scons_cache"],
      self._action_rows["download_cache"],
      self._status_item,
      self._offroad_hint,
    ]
    self._ext_heading.set_visible(False)
    self._ext_disk_item.set_visible(False)
    self._ext_bar.set_visible(False)
    self._ext_legend_routes.set_visible(False)
    self._ext_legend_free.set_visible(False)
    self._ota_note.set_visible(False)
    self._warn_item.set_visible(False)
    for row in self._starred_rows + [self._starred_more]:
      row.set_visible(False)
    self._offroad_hint.set_visible(not self._offroad)

  # ------------------------------------------------------- description text
  def _est_text(self, category: str) -> str:
    est = (self._data or {}).get("clearable", {}).get(category)
    if est:
      return tr("About {size} can be freed").format(size=_fmt_bytes(est))
    return tr("Nothing to clear")

  def _routes_desc(self) -> str:
    desc = (tr("Deletes non-preserved driving segments. Starred and recent routes are kept.") + " " +
            tr("Routes auto-delete when free space is below 10% or 5 GB (oldest first). Upload is not required. Starred routes are kept."))
    ext_bytes = (self._data or {}).get("routes_external_bytes", 0)
    if ext_bytes:
      desc += " " + tr("Includes {size} on external SSD.").format(size=_fmt_bytes(ext_bytes))
    return desc

  def _starred_desc(self) -> str:
    desc = tr("Deletes route recordings you bookmarked while driving. Other routes are not affected.")
    count = (self._data or {}).get("starred_routes", {}).get("count", 0)
    if count:
      desc += " " + tr("{count} starred routes on device.").format(count=count)
    return desc

  def _plain_desc(self, base: str):
    return lambda: base

  # ------------------------------------------------------------------- data
  @property
  def _offroad(self) -> bool:
    try:
      return not ui_state.params.get_bool("IsOnroad")
    except Exception:
      return True

  def _can_clear(self, category: str) -> bool:
    if category in self._busy or not self._offroad:
      return False
    est = (self._data or {}).get("clearable", {}).get(category)
    return bool(est)

  def _refresh(self, force: bool = False):
    threading.Thread(target=self._load_snapshot, args=(force,), daemon=True).start()

  def _on_refresh(self):
    self._refresh(force=True)

  def _load_snapshot(self, force: bool = False):
    self._scanning = True
    try:
      try:
        data = snapshot_storage(force=force) if HAS_WEBUI_BACKEND else self._legacy_snapshot()
      except Exception:
        # e.g. a host without statvfs: degrade to the local subset, never crash
        data = self._legacy_snapshot() if HAS_WEBUI_BACKEND else None
      if data:
        self._apply_data(data)
      self._compute_model_split()
    finally:
      self._scanning = False

  def _legacy_snapshot(self) -> dict:
    """Fallback without the webui package: the subset this page can compute."""
    usage = disk_usage(_DISK_PROBE_PATH)
    models = model_root_size(Paths.model_root())
    maps = directory_size(str(MAP_PATH))
    total = usage.total if usage else 0
    used = usage.used if usage else 0
    free = usage.free if usage else 0
    cats = {"routes": 0, "models": models, "maps": maps, "software": 0, "logs": 0,
            "ota_staging": 0, "scons_cache": 0, "other": max(0, used - models - maps)}
    return {
      "ok": True,
      "total_bytes": total, "used_bytes": used, "free_bytes": free,
      "free_percent": round(100.0 * free / total, 1) if total else 0,
      "low_space": (free / total < 0.10) if total else False,
      "critical_space": (free / total < 0.02) if total else False,
      "categories": [{"id": cid, "bytes": cats[cid], "percent": round(100.0 * cats[cid] / total, 1) if total else 0}
                     for cid in CATEGORY_ORDER],
      "external": None,
      "routes_external_bytes": 0,
      "starred_routes": {"count": 0, "bytes": 0, "items": []},
      "clearable": {"routes": 0, "routes_starred": 0, "maps": maps, "models_cache": models,
                    "logs": 0, "scons_cache": 0, "download_cache": 0},
    }

  def _apply_data(self, data: dict):
    self._data = data
    total = data.get("total_bytes", 0)

    # summary row + internal bar / legend
    self._disk_item.action_item.set_text(
      f"{_fmt_bytes(data.get('used_bytes'))} / {_fmt_bytes(total)}  ·  {tr('{} free').format(_fmt_bytes(data.get('free_bytes')))}")
    segments = []
    for cat in data.get("categories", []):
      cid = cat.get("id")
      frac = (cat.get("bytes", 0) / total) if total else 0
      if cat.get("bytes", 0) > 0:
        segments.append((CATEGORY_COLORS[cid], frac))
      self._legend_rows[cid].update(_fmt_bytes(cat.get("bytes", 0)), f"{cat.get('percent', 0)}%")
    free_frac = (data.get("free_bytes", 0) / total) if total else 1.0
    self._bar.update(segments, free_frac)
    self._legend_free.update(_fmt_bytes(data.get("free_bytes", 0)), f"{data.get('free_percent', 0)}%")

    # OTA staging note
    ota = next((c for c in data.get("categories", []) if c.get("id") == "ota_staging"), None)
    self._ota_note.set_visible(bool(ota and ota.get("bytes", 0) > 0))
    self._ota_note.action_item.set_text(_fmt_bytes(ota.get("bytes", 0)) if ota else "")

    # low / critical warning (webui wording)
    if data.get("critical_space"):
      self._warn_item.set_title(tr("Free up storage (less than 2% space remaining)"))
      self._warn_item.title_color = DANGER_COLOR
      self._warn_item.set_visible(True)
    elif data.get("low_space"):
      self._warn_item.set_title(tr("Storage is running low (less than 10% free)."))
      self._warn_item.title_color = WARN_COLOR
      self._warn_item.set_visible(True)
    else:
      self._warn_item.set_visible(False)

    # external SSD section
    ext = data.get("external")
    ext_on = bool(ext and ext.get("mounted"))
    self._ext_heading.set_visible(ext_on)
    self._ext_disk_item.set_visible(ext_on)
    self._ext_bar.set_visible(ext_on)
    self._ext_legend_routes.set_visible(ext_on)
    self._ext_legend_free.set_visible(ext_on)
    if ext_on and ext.get("total_bytes"):
      self._ext_disk_item.action_item.set_text(
        f"{_fmt_bytes(ext.get('used_bytes'))} / {_fmt_bytes(ext.get('total_bytes'))}  ·  {tr('{} free').format(_fmt_bytes(ext.get('free_bytes')))}")
      routes_bytes = ext.get("routes_bytes", 0)
      ext_total = ext.get("total_bytes", 1)
      ext_segs = [(CATEGORY_COLORS["routes"], routes_bytes / ext_total)] if routes_bytes > 0 else []
      self._ext_bar.update(ext_segs, max(0.0, ext.get("free_bytes", 0) / ext_total))
      self._ext_legend_routes.update(_fmt_bytes(routes_bytes), f"{ext.get('categories', [{}])[0].get('percent', 0)}%")
      self._ext_legend_free.update(_fmt_bytes(ext.get("free_bytes", 0)), f"{ext.get('free_percent', 0)}%")

    # cleanup rows: estimate as the value, button gated on offroad + estimate
    for category, row in self._action_rows.items():
      est = data.get("clearable", {}).get(category)
      row.action_item.set_value(self._est_text(category) if est is not None else "")
      row.action_item.set_enabled(self._can_clear(category))

    # starred routes list
    starred = data.get("starred_routes") or {}
    items = starred.get("items") or []
    for i, row in enumerate(self._starred_rows):
      if i < len(items):
        item = items[i]
        vol = tr("External SSD") if item.get("volume") == "external" else tr("Internal storage")
        row.set_title(item.get("id", ""))
        row.action_item.set_text(f"{vol} · {_fmt_bytes(item.get('bytes', 0))}")
        row.set_visible(True)
      else:
        row.set_visible(False)
    more = len(items) - STARRED_LIST_MAX
    self._starred_more.set_visible(more > 0)
    if more > 0:
      self._starred_more.set_title(tr("and {count} more…").format(count=more))

    self._offroad_hint.set_visible(not self._offroad)

  def _compute_model_split(self):
    """Per-source breakdown under the models total (sp-specific rows)."""
    model_root = str(Paths.model_root())
    self._sizes = {"models": model_root_size(model_root)}
    try:
      from openpilot.sunnypilot.models.fetcher import get_cached_bundles

      bundles = {source: get_cached_bundles(ui_state.params, source) for source in ("qcom", "chestnut")}
      self._sizes.update(cached_bundle_sizes(model_root, bundles))
      self._model_clearable = {source: self._model_clearable_bytes(model_root, source, bundles) for source in bundles}
    except Exception:
      self._sizes.setdefault("qcom", 0)
      self._sizes.setdefault("chestnut", 0)
      self._model_clearable = {"qcom": 0, "chestnut": 0}
    self._update_model_rows()

  def _model_clearable_bytes(self, model_root: str, source: str, bundles: dict[str, list]) -> int:
    """Bytes a per-source clear would actually free for `source`.

    A file qualifies when the source's catalog lists it and the other source's
    does not (shared names serve both slots, so only the full model-cache clear
    may take them), and when neither source's selected bundle needs it - the
    slots currently in use are untouchable, matching clear_model_cache."""
    try:
      from openpilot.common.params import Params
      from openpilot.sunnypilot.models.helpers import get_selected_bundle
      from openpilot.sunnypilot.models.model_sizes import artifact_size

      params = ui_state.params if ui_state.params is not None else Params()
      protected: set[str] = set()
      for s in bundles:
        if selected := get_selected_bundle(params, s):
          for model in getattr(selected, "models", []) or []:
            for artifact in (getattr(model, "artifact", None), getattr(model, "metadata", None)):
              name = getattr(artifact, "fileName", "") or ""
              if name:
                protected.add(name)

      other = next(s for s in bundles if s != source)
      other_files: set[str] = set()
      for bundle in bundles.get(other, []) or []:
        other_files |= model_file_names(bundle)

      total = 0
      for bundle in bundles.get(source, []) or []:
        for name in model_file_names(bundle):
          if name in protected or name in other_files:
            continue
          artifact = next((a for m in getattr(bundle, "models", []) or []
                           for a in (getattr(m, "artifact", None), getattr(m, "metadata", None))
                           if (getattr(a, "fileName", "") or "") == name), None)
          declared = getattr(artifact, "fileSizeBytes", None) if artifact is not None else None
          on_disk = artifact_size(os.path.join(model_root, name), declared).get("downloadedBytes")
          if on_disk:
            total += int(on_disk)
      return total
    except Exception:
      return 0

  def _update_model_rows(self):
    for source, row in self._model_rows.items():
      size = self._sizes.get(source, 0)
      row.action_item.set_value(format_size(size) if size else "")
      row.action_item.set_enabled(self._can_clear_model(source))

  def _model_desc(self, source: str):
    def _desc() -> str:
      base = (tr("Downloaded files from the small-model catalog, except the one in use. Files the other slot shares are kept.")
              if source == "qcom" else
              tr("Downloaded files from the big-model catalog, except the one in use. Files the other slot shares are kept."))
      est = self._model_clearable.get(source, 0)
      if est:
        base += " " + tr("About {size} can be freed").format(size=format_size(est))
      return base
    return _desc

  def _can_clear_model(self, source: str) -> bool:
    return self._offroad and f"model:{source}" not in self._busy and bool(self._model_clearable.get(source))

  def _clear_model_source(self, source: str):
    if not self._can_clear_model(source):
      return
    size_text = format_size(self._model_clearable.get(source, 0))
    message = (tr("This will delete downloaded small-model files except the one in use (about {size}). Continue?")
               if source == "qcom" else
               tr("This will delete downloaded big-model files except the one in use (about {size}). Continue?")).format(size=size_text)

    def _on_confirm(response):
      if response != DialogResult.CONFIRM:
        return
      self._busy.add(f"model:{source}")
      self._model_rows[source].action_item.set_enabled(False)

      def _run():
        try:
          freed = self._clear_model_files(source)
          self._status_item.action_item.set_text(tr("Freed {size}").format(size=_fmt_bytes(freed)))
        except Exception as exc:
          self._status_item.action_item.set_text(str(exc))
        finally:
          self._busy.discard(f"model:{source}")
          self._compute_model_split()
          self._refresh()

      threading.Thread(target=_run, daemon=True).start()

    gui_app.push_widget(ConfirmDialog(message, tr("Clear"), callback=_on_confirm))

  def _clear_model_files(self, source: str) -> int:
    """Delete the per-source candidates _model_clearable_bytes identified,
    together with their chunk files (the same base.split('.chunk') rule
    clear_model_cache applies)."""
    import os

    model_root = str(Paths.model_root())
    from openpilot.sunnypilot.models.fetcher import get_cached_bundles
    from openpilot.sunnypilot.models.helpers import get_selected_bundle

    bundles = {s: get_cached_bundles(ui_state.params, s) for s in ("qcom", "chestnut")}
    protected: set[str] = set()
    for s in bundles:
      if selected := get_selected_bundle(ui_state.params, s):
        for model in getattr(selected, "models", []) or []:
          for artifact in (getattr(model, "artifact", None), getattr(model, "metadata", None)):
            name = getattr(artifact, "fileName", "") or ""
            if name:
              protected.add(name)

    other = next(s for s in bundles if s != source)
    other_files: set[str] = set()
    for bundle in bundles.get(other, []) or []:
      other_files |= model_file_names(bundle)

    freed = 0
    for bundle in bundles.get(source, []) or []:
      for name in model_file_names(bundle):
        if name in protected or name in other_files:
          continue
        base = os.path.join(model_root, name)
        directory = os.path.dirname(base) or model_root
        for filename in ([name] if os.path.isfile(base) else []) + \
                        [f for f in os.listdir(directory) if f.startswith(name + ".chunk")]:
          fp = os.path.join(directory, filename)
          try:
            freed += os.path.getsize(fp)
            os.remove(fp)
          except OSError:
            pass
    self._sizes[source] = max(0, self._sizes.get(source, 0) - freed)
    return freed

  # ---------------------------------------------------------------- actions
  def _confirm_and_clear(self, category: str, message: str):
    def _on_confirm(response):
      if response != DialogResult.CONFIRM:
        return
      self._busy.add(category)
      self._action_rows[category].action_item.set_enabled(False)

      def _run():
        try:
          if HAS_WEBUI_BACKEND:
            res = clear_storage(category)
          else:
            res = self._legacy_clear(category)
          freed = res.get("freed_bytes", 0) if res.get("ok") else 0
          if res.get("ok"):
            self._status_item.action_item.set_text(tr("Freed {size}").format(size=_fmt_bytes(freed)))
          else:
            self._status_item.action_item.set_text(res.get("error", tr("Save failed")))
        except Exception as exc:
          self._status_item.action_item.set_text(str(exc))
        finally:
          self._busy.discard(category)
          self._refresh()

      threading.Thread(target=_run, daemon=True).start()

    gui_app.push_widget(ConfirmDialog(message, tr("Clear"), callback=_on_confirm))

  def _clear_category(self, category: str):
    if not self._offroad:
      return
    est = (self._data or {}).get("clearable", {}).get(category) or 0
    size_text = _fmt_bytes(est)
    if category == "routes_starred":
      count = (self._data or {}).get("starred_routes", {}).get("count", 0)
      message = tr("This will permanently delete {count} starred routes ({size}). Continue?").format(
        count=count, size=size_text or _fmt_bytes((self._data or {}).get("starred_routes", {}).get("bytes", 0)))
    elif category == "scons_cache":
      message = tr("Clearing the build cache frees space, but the next compile will take significantly longer. Continue?")
    else:
      message = tr("This will free about {size}. Continue?").format(size=size_text)
    self._confirm_and_clear(category, message)

  def _legacy_clear(self, category: str) -> dict:
    """Fallback without the webui package: the two old actions only."""
    import shutil
    freed = 0
    if category == "models_cache":
      self._mem_params.put_bool("ModelManager_ClearCache", True)
      model_root = str(Paths.model_root())
      active = (ui_state.params.get("ActiveModel") or "").strip()
      for name in os.listdir(model_root):
        if name == active:
          continue
        fp = os.path.join(model_root, name)
        freed += directory_size(fp)
        shutil.rmtree(fp, ignore_errors=True)
      self._compute_model_split()
    elif category == "maps":
      delete_downloaded_maps(ui_state.params, self._mem_params)
      freed = directory_size(str(MAP_PATH))
      self._compute_model_split()
    return {"ok": True, "category": category, "freed_bytes": freed}

  # ----------------------------------------------------------------- render
  def show_event(self):
    self._scroller.show_event()
    self._refresh()

  def _render(self, rect):
    self._scroller.render(rect)


def _category_label(category: str) -> str:
  """Translate a category id through its webui label (extraction-friendly)."""
  labels = {
    "routes": tr("Routes"),
    "models": tr("Models"),
    "maps": tr("Maps"),
    "software": tr("Software"),
    "logs": tr("Logs"),
    "ota_staging": tr("OTA staging"),
    "scons_cache": tr("Build cache"),
    "other": tr("Other"),
  }
  return labels[category]
