"""
Copyright (c) 2026-, mouxan.

Storage settings page: how the device's flash is used and the safe cleanup
actions. Mirrors what the dedicated pages already do, in one place:

- a disk overview (used / total, free),
- the downloaded driving-model cache, cleared through the same
  ModelManager_ClearCache flag the Models page uses (the active model is kept),
- the downloaded offline maps, cleared through the exact OSM wipe.

Driving footage is intentionally not deletable here: loggerd owns that
directory and reclaims it automatically; a manual wipe racing a recording is
the kind of action that belongs nowhere near a settings list.
"""
import platform
import threading

from openpilot.common.hardware.hw import Paths
from openpilot.common.params import Params
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.selfdrive.ui.sunnypilot.layouts.settings.osm import MAP_PATH, delete_downloaded_maps
from openpilot.selfdrive.ui.sunnypilot.storage_info import (
  cached_bundle_sizes, directory_size, disk_usage, format_size, model_root_size,
)
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.widgets import DialogResult, Widget
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog
from openpilot.system.ui.widgets.list_view import text_item
from openpilot.system.ui.widgets.scroller_tici import Scroller

from openpilot.system.ui.sunnypilot.lib.utils import NoElideButtonAction
from openpilot.system.ui.sunnypilot.widgets.list_view import ListItemSP, section_heading_sp
from openpilot.system.ui.sunnypilot.widgets.progress_bar import progress_item

# statvfs needs a path that lives on the device's data filesystem.
_DISK_PROBE_PATH = str(Paths.log_root())


class StorageLayout(Widget):
  def __init__(self):
    super().__init__()
    self._mem_params = Params("/dev/shm/params") if platform.system() != "Darwin" else ui_state.params
    self._sizes: dict[str, int] = {}
    self._initialize_items()
    self._scroller = Scroller(self.items, line_separator=True, spacing=0)
    self._refresh_sizes()

  def _initialize_items(self):
    self._disk_item = text_item(tr("Storage Used"), tr("Calculating..."))
    self._disk_bar = progress_item(tr("Used Space"))
    self._disk_bar.action_item.update(0.0, "", show_progress=True)

    self._model_cache_btn = ListItemSP(
      tr("Driving Model Cache"),
      action_item=NoElideButtonAction(tr("CLEAR")),
      callback=self._clear_model_cache,
    )
    # Per-source breakdown under the total: small (qcom) and big (chestnut)
    # models share one directory and differ only by catalog, so each is a
    # read-only value row (clearing is the single action on the total above).
    # TextAction resolves a callable every frame, so the row fills in when the
    # off-UI-thread size walk lands.
    self._small_model_item = text_item(tr("Small Model"), lambda: format_size(self._sizes.get("qcom", 0)))
    self._big_model_item = text_item(tr("Big Model"), lambda: format_size(self._sizes.get("chestnut", 0)))
    self._maps_btn = ListItemSP(
      tr("Downloaded Maps"),
      action_item=NoElideButtonAction(tr("DELETE")),
      callback=self._delete_maps,
    )

    self.items = [
      section_heading_sp(tr("Device Storage")),
      self._disk_item,
      self._disk_bar,
      section_heading_sp(tr("Downloaded Data")),
      self._model_cache_btn,
      self._small_model_item,
      self._big_model_item,
      self._maps_btn,
    ]

  # ---- sizing, computed off the UI thread (a walk over the model dir can hit hundreds of MB) ----
  def _compute_sizes(self):
    model_root = Paths.model_root()
    # The total walks the directory (recursive), the exact same number the web UI quotes.
    models_total = model_root_size(model_root)
    maps = directory_size(str(MAP_PATH))
    self._sizes = {"models": models_total, "maps": maps}
    self._model_cache_btn.action_item.set_value(format_size(models_total))
    self._maps_btn.action_item.set_value(format_size(maps))

    # Attribute bytes to each source from its cached bundle catalog; an
    # unknown source or a panel on a PC without the fetcher just shows 0.
    try:
      from openpilot.sunnypilot.models.fetcher import get_cached_bundles

      bundles = {source: get_cached_bundles(ui_state.params, source) for source in ("qcom", "chestnut")}
      self._sizes.update(cached_bundle_sizes(model_root, bundles))
    except Exception:
      self._sizes.setdefault("qcom", 0)
      self._sizes.setdefault("chestnut", 0)

    usage = disk_usage(_DISK_PROBE_PATH)
    if usage is not None:
      self._disk_item.action_item.set_text(
        f"{format_size(usage.used)} / {format_size(usage.total)}  ·  {tr('{} free').format(format_size(usage.free))}")
      percent = usage.used_fraction * 100.0
      self._disk_bar.action_item.update(percent, f"{percent:.0f}%", show_progress=True)
    else:
      self._disk_item.action_item.set_text(tr("Unavailable"))

  def _refresh_sizes(self):
    threading.Thread(target=self._compute_sizes, daemon=True).start()

  # ---- model cache (same flag + confirm wording as the Models page) ----
  def _clear_model_cache(self):
    def _on_confirm(response):
      if response != DialogResult.CONFIRM:
        return
      ui_state.params.put_bool("ModelManager_ClearCache", True)
      # The manager does the actual delete; re-walk shortly so the row reflects it.
      threading.Timer(1.5, self._refresh_sizes).start()

    gui_app.push_widget(ConfirmDialog(
      tr("This will delete ALL downloaded models from the cache except the currently active model. Are you sure?"),
      tr("Clear Cache"), callback=_on_confirm))

  # ---- offline maps (exact shared wipe with the OSM page) ----
  def _delete_maps(self):
    def _on_confirm(response):
      if response != DialogResult.CONFIRM:
        return
      delete_downloaded_maps(ui_state.params, self._mem_params)
      self._refresh_sizes()

    gui_app.push_widget(ConfirmDialog(
      tr("This will delete ALL downloaded maps\n\nAre you sure you want to delete all maps?"),
      tr("Yes, delete all maps"), callback=_on_confirm))

  def show_event(self):
    self._scroller.show_event()

  def _render(self, rect):
    self._scroller.render(rect)
