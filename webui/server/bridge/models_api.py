"""Model manager tree + download status, mirroring sunnypilot's on-device Models layout."""

from __future__ import annotations

import os
import re
import threading
import time
from typing import Any

# Lazily-initialized SubMaster instances. Creating a SubMaster on every request
# costs ~500-900 ms of cold import/initialization overhead, which makes the
# models panel feel sluggish. Re-use them across requests and only pay the
# update/poll cost.
_STATE_SM: Any = None
_MM_SM: Any = None
_SM_LOCK = threading.Lock()

# Cached latest readings so HTTP handlers can return immediately without waiting
# for the next live message. A background thread keeps these warm.
_STATE_CACHE: dict[str, Any] | None = None
_MM_CACHE: Any = None
_WARMER_STARTED = False
_WARMER_LOCK = threading.Lock()


def _get_state_sm() -> Any:
  global _STATE_SM
  if _STATE_SM is None:
    import openpilot.cereal.messaging as messaging
    # No poll=: a polled service is read non-blocking by update(), so
    # update(500) would return immediately without a message (deviceState
    # publishes at 2 Hz) and valid would stay False forever. Without poll,
    # update() blocks until the message or the timeout, whichever first.
    _STATE_SM = messaging.SubMaster(["deviceState"])
  return _STATE_SM


def _get_mm_sm() -> Any:
  global _MM_SM
  if _MM_SM is None:
    import openpilot.cereal.messaging as messaging
    _MM_SM = messaging.SubMaster(["modelManagerSP"], poll="modelManagerSP")
  return _MM_SM


_MDV2SP_SM: Any = None


def _get_mdv2sp_sm() -> Any:
  """modelDataV2SP carries acceleratorState — the ground truth for where the
  big model is actually running right now (jetlink joining/running vs the
  chestnut big bundle vs the on-device small model)."""
  global _MDV2SP_SM
  if _MDV2SP_SM is None:
    import openpilot.cereal.messaging as messaging
    _MDV2SP_SM = messaging.SubMaster(["modelDataV2SP"], poll="modelDataV2SP")
  return _MDV2SP_SM


def _warm_submasters() -> None:
  """Background thread: keep SubMaster sockets warm and cache latest values."""
  global _STATE_CACHE, _MM_CACHE
  try:
    state_sm = _get_state_sm()
    mm_sm = _get_mm_sm()
    while True:
      with _SM_LOCK:
        # deviceState publishes at 2 Hz — waiting less than ~500 ms per update
        # usually times out with no message, so valid stays False and the
        # cache is never filled (which sent every handler into its 400 ms
        # fallback poll).
        state_sm.update(500)
        if state_sm.valid.get("deviceState"):
          ds = state_sm["deviceState"]
          try:
            from openpilot.common.params import Params
            p = Params()
          except Exception:
            p = None
          try:
            _STATE_CACHE = {
              "started": bool(getattr(ds, "started", False)),
              "chestnutPresent": bool(getattr(ds, "chestnutPresent", False)),
              "usbgpuActive": p.get_bool("UsbGpuActive") if p else None,
              "usbgpuLoading": p.get_bool("UsbGpuLoading") if p else False,
            }
          except Exception:
            _STATE_CACHE = None
        mm_sm.update(100)
        if mm_sm.valid.get("modelManagerSP"):
          _MM_CACHE = mm_sm["modelManagerSP"]
      time.sleep(0.05)
  except Exception:
    pass


def _start_submaster_warmers() -> None:
  global _WARMER_STARTED
  with _WARMER_LOCK:
    if _WARMER_STARTED:
      return
    _WARMER_STARTED = True
    t = threading.Thread(target=_warm_submasters, daemon=True)
    t.start()


def start_warmers() -> None:
  """Public hook for the app factory to start SubMaster warmers early."""
  _start_submaster_warmers()


# Mirror sunnypilot/models/helpers.py — kept in sync so webui picks the same key the
# device manager writes.
_SOURCE_KEYS: dict[str, str] = {
  "qcom": "ModelManager_ActiveBundle",
  "usbgpu": "ModelManager_ActiveBundleChestnut",
}

# The webui uses "usbgpu" to refer to the external big-model source, but the
# openpilot model manager/fetcher internally calls it "chestnut". Map here so
# the rest of the code can stay aligned with the device-side naming.
_SOURCE_TO_BACKEND: dict[str, str] = {
  "qcom": "qcom",
  "usbgpu": "chestnut",
}

_MODEL_TYPES = {
  "supercombo": "Driving Model",
  "vision": "Vision Model",
  "policy": "Policy Model",
  "offPolicy": "Off-Policy Model",
  "onPolicy": "On-Policy Model",
  "navigation": "Navigation Model",
}


def _cache_size_mb() -> float:
  try:
    from openpilot.sunnypilot.models.runners.constants import CUSTOM_MODEL_PATH
    if not os.path.exists(CUSTOM_MODEL_PATH):
      return 0.0
    total = sum(os.path.getsize(os.path.join(CUSTOM_MODEL_PATH, f)) for f in os.listdir(CUSTOM_MODEL_PATH))
    return total / (1024 ** 2)
  except Exception:
    return 0.0


# -- Accelerator Link (jetlink) -------------------------------------------------
# Mirrors the native Models panel's Accelerator Link row: the mode setting, why
# an enabled link cannot run, and the live connection status. An Android phone
# rides the USB mode exactly like a Jetson or a Mac (jetlink docs/android-app.md).

def _adapter() -> Any | None:
  """The jetlink adapter module, or None where it cannot import. The adapter is
  built to degrade safely (an absent jetlink checkout is a normal state), so the
  import itself only fails on a broken checkout."""
  try:
    from openpilot.sunnypilot import jetlink_adapter
    return jetlink_adapter
  except Exception:
    return None


def _accelerator_mode(p: Any, modes: list[str], link_param: str) -> str:
  try:
    index = p.get(link_param, return_default=True)
  except Exception:
    index = None
  return modes[index] if isinstance(index, int) and 0 <= index < len(modes) else "off"


def _big_model_source(p: Any, state: dict[str, Any] | None, accel: dict[str, Any] | None) -> str:
  """Where the big driving model is running right now: 'jetlink' (off-board
  accelerator), 'chestnut' (on the eGPU), or 'device' (on-device small model).
  Judged from modelDataV2SP.acceleratorState first — that is what modeld is
  actually driving with — then falling back to the chestnut state."""
  try:
    sm = _get_mdv2sp_sm()
    with _SM_LOCK:
      sm.update(30)
    state_name = str(sm["modelDataV2SP"].acceleratorState)
    if state_name in ("running", "joining"):
      return "jetlink"
  except Exception:
    pass

  usbgpu = bool(state and state.get("chestnutPresent")) or _usbgpu_present()
  if usbgpu:
    usbgpu_active = state.get("usbgpuActive")
    usbgpu_loading = state.get("usbgpuLoading")
    started = state.get("started")
    big_active = usbgpu_active is True or usbgpu_loading or (not started)
    if big_active:
      return "chestnut"

  return "device"


def _accelerator_status_text(s: Any) -> dict[str, Any]:
  """Structured form of the native accelerator_link.link_status() one-liner; the
  frontend translates the key and interpolates the transport."""
  if s.present:
    return {"key": "accelerator_connected", "transport": s.transport}
  if getattr(s, "mode", None) == "wifi":
    # nothing on the port to report: the link is the hotspot the comma joined
    return {"key": "accelerator_wifi"}
  if s.port is None:
    return {"key": ""}
  return {"key": "port_empty" if s.port == "empty" else "port_device"}


def _accelerator_state(p: Any, chestnut_present: bool | None = None) -> dict[str, Any]:
  adapter = _adapter()
  modes = list(adapter.MODES) if adapter is not None else ["off", "usb", "ios", "wifi"]
  link_param = str(adapter.KEYS.link) if adapter is not None else "JetlinkLink"

  mode = _accelerator_mode(p, modes, link_param)

  s = None
  if adapter is not None:
    try:
      s = adapter.status()
    except Exception:
      s = None

  if chestnut_present is None:
    chestnut_present = bool((_device_state() or {}).get("chestnutPresent"))
  # native link_toggle_meaningful(): hidden beside a chestnut, which runs the
  # big model itself; offered while the link is on even if jetlink cannot run
  meaningful = (not chestnut_present) and (s is not None or mode != "off")

  status: dict[str, Any] = {"key": ""}
  progress: dict[str, Any] | None = None
  reason: str | None = None
  model: str | None = None
  default_model: str | None = None
  standin: str | None = None
  ready = False
  if s is not None:
    try:
      status = _accelerator_status_text(s)
      progress = dict(s.progress) if s.progress else None
      reason = s.reason
      model = s.model
      default_model = s.default_model
      standin = getattr(s, "standin", None)
      ready = bool(getattr(s, "ready", False))
    except Exception:
      pass

  return {
    "modes": modes,
    "mode": mode,
    "meaningful": meaningful,
    "status": status,
    "progress": progress,
    "reason": reason,
    "model": model,
    "default_model": default_model,
    "standin": standin,
    "ready": ready,
    # native _enforce_usb_port: the link holds the port (and takes ADB with it)
    # in every mode but Wi-Fi, which leaves the port alone
    "adb_blocked": bool(s is not None and getattr(s, "enabled", False) and mode != "wifi"),
  }


def accelerator_link_set(mode: str) -> dict[str, Any]:
  """Write the Accelerator Link setting (an index into the adapter's MODES), the
  same param the native multiple_button_item_sp and jetlinkd both read."""
  adapter = _adapter()
  if adapter is None:
    return {"ok": False, "error": "jetlink adapter unavailable"}
  modes = list(adapter.MODES)
  if mode not in modes:
    return {"ok": False, "error": f"unknown mode: {mode}"}
  try:
    from openpilot.common.params import Params
    p = Params()
    p.put(str(adapter.KEYS.link), modes.index(mode))
    # Turning the link on has to free the USB port in the same breath: AGNOS's ADB
    # gadget (g1) holds the only device controller while AdbEnabled is set, and
    # jetlink refuses to take it.
    from webui.server.bridge.param_constraints import _enforce_usb_port
    _enforce_usb_port(p)
  except Exception as exc:
    return {"ok": False, "error": str(exc)}
  return {"ok": True, "mode": mode}


def _default_model_label(source: str) -> str:
  try:
    if source == "usbgpu":
      from openpilot.sunnypilot.models.model_name import DEFAULT_BIG_MODEL
      return f"{DEFAULT_BIG_MODEL} (Default)"
    from openpilot.sunnypilot.models.model_name import DEFAULT_MODEL
    return f"{DEFAULT_MODEL} (Default)"
  except Exception:
    return "Default (Default)"


def _usbgpu_present() -> bool:
  try:
    from openpilot.selfdrive.modeld.helpers import usbgpu_present
    return bool(usbgpu_present())
  except Exception:
    return False


_DEVICE_STATE_CACHE: dict[str, Any] | None = None
_DEVICE_STATE_TS: float = 0.0
_DEVICE_STATE_TTL = 0.3  # s — deviceState is 2 Hz; poll at most ~3x a second


def _device_state() -> dict[str, Any] | None:
  """Best-effort device state for the Models panel.

  The warmer cache serves deviceState when it is publishing normally. But
  hardware_thread paces itself on pandaStates, and with no panda attached
  that loop slows far below deviceState's nominal 2 Hz — a subscriber can
  wait seconds without a frame. So never block: peek non-blocking, then
  fall back to Params (IsOffroad mirrors `started`; the chestnut is probed
  on USB directly).
  """
  global _DEVICE_STATE_CACHE, _DEVICE_STATE_TS
  _start_submaster_warmers()
  try:
    if _STATE_CACHE is not None:
      return _STATE_CACHE
    if _DEVICE_STATE_CACHE is not None and time.monotonic() - _DEVICE_STATE_TS < _DEVICE_STATE_TTL:
      return _DEVICE_STATE_CACHE
    sm = _get_state_sm()
    with _SM_LOCK:
      sm.update(30)  # peek: a blocking wait here stalls the whole event loop
    if sm.valid.get("deviceState"):
      ds = sm["deviceState"]
      try:
        from openpilot.common.params import Params
        p = Params()
      except Exception:
        p = None
      _DEVICE_STATE_CACHE = {
        "started": bool(getattr(ds, "started", False)),
        "chestnutPresent": bool(getattr(ds, "chestnutPresent", False)),
        "usbgpuActive": p.get_bool("UsbGpuActive") if p else None,
        "usbgpuLoading": p.get_bool("UsbGpuLoading") if p else False,
      }
      _DEVICE_STATE_TS = time.monotonic()
      return _DEVICE_STATE_CACHE

    from openpilot.common.params import Params
    from openpilot.selfdrive.modeld.helpers import chestnut_present
    p = Params()
    state = {
      "started": not p.get_bool("IsOffroad"),
      "chestnutPresent": chestnut_present(),
      "usbgpuActive": p.get_bool("UsbGpuActive"),
      "usbgpuLoading": p.get_bool("UsbGpuLoading"),
    }
    _DEVICE_STATE_CACHE = state
    _DEVICE_STATE_TS = time.monotonic()
    return state
  except Exception:
    pass
  return _DEVICE_STATE_CACHE


def _active_source(state: dict[str, Any] | None) -> str:
  """Mirror sunnypilot get_active_source — defaults to qcom on any read failure."""
  usbgpu = bool(state and state.get("chestnutPresent")) or _usbgpu_present()
  if not usbgpu:
    return "qcom"
  if not state:
    return "usbgpu"
  usbgpu_active = state.get("usbgpuActive")
  usbgpu_loading = state.get("usbgpuLoading")
  started = state.get("started")
  big_active = usbgpu_active is True or usbgpu_loading or (not started)
  return "usbgpu" if big_active else "qcom"


_MM_CACHE_TS: float = 0.0
_MM_CACHE_TTL = 0.3  # s — modelManagerSP is high-frequency; a 300 ms cache is fresh


def _read_live_model_manager(timeout_ms: int = 1000) -> Any | None:
  """Return the latest modelManagerSP message.

  Uses the background warmer cache when available; otherwise takes a short
  non-blocking peek (modelManagerSP is published at high frequency, so a
  peek is enough) and caches the result. Never blocks the event loop.
  """
  global _MM_CACHE_TS
  _start_submaster_warmers()
  try:
    if _MM_CACHE is not None and time.monotonic() - _MM_CACHE_TS < _MM_CACHE_TTL:
      return _MM_CACHE
    sm = _get_mm_sm()
    deadline = time.monotonic() + 0.1  # cap the wait: modelManagerSP is ~1 Hz, the next poll retries
    while time.monotonic() < deadline:
      with _SM_LOCK:
        sm.update(30)
      if sm.valid.get("modelManagerSP"):
        _MM_CACHE = sm["modelManagerSP"]
        _MM_CACHE_TS = time.monotonic()
        break
    return _MM_CACHE
  except Exception:
    pass
  return None


def _cached_bundles(params: Any, source: str) -> list[Any]:
  """Read cached bundles for a source. Matches sunnypilot's get_cached_bundles."""
  try:
    from openpilot.sunnypilot.models.fetcher import ModelFetcher, ModelParser
    backend_source = _SOURCE_TO_BACKEND.get(source, source)
    if backend_source not in ModelFetcher.MODEL_SOURCES:
      return []
    _, suffix = ModelFetcher.MODEL_SOURCES[backend_source]
    raw = params.get(f"ModelManager_ModelsCache{suffix}")
    if not raw:
      return []
    try:
      return ModelParser.parse_models(raw)
    except Exception:
      return []
  except Exception:
    return []


def _selected_bundle(params: Any, source: str) -> Any | None:
  try:
    from openpilot.sunnypilot.models.helpers import get_selected_bundle
    backend_source = _SOURCE_TO_BACKEND.get(source, source)
    return get_selected_bundle(params, backend_source)
  except Exception:
    return None


def _bundles_for_source(params: Any, source: str, mm: Any | None) -> list[Any]:
  """Mirror sunnypilot bundles_for_source: live for the active source, cache otherwise."""
  if mm is not None:
    try:
      available = list(mm.availableBundles) if mm.availableBundles is not None else []
    except Exception:
      available = []
    if available:
      return available
  return _cached_bundles(params, source)


def _bundle_entry(bundle: Any, favorites: set[str]) -> tuple[dict[str, Any], str]:
  folder = ""
  generation = ""
  try:
    for ov in bundle.overrides or []:
      if ov.key == "folder":
        folder = ov.value
      if ov.key == "generation":
        generation = ov.value
  except Exception:
    pass
  return {
    "ref": getattr(bundle, "ref", "") or "",
    "name": getattr(bundle, "displayName", "") or "",
    "internal": getattr(bundle, "internalName", "") or "",
    "index": getattr(bundle, "index", -1),
    "generation": generation,
    "fav": getattr(bundle, "ref", "") in favorites,
  }, folder


def _folder_display_name(folder: str, folder_bundles: list[dict[str, Any]]) -> str:
  if not folder:
    return "Models"
  if not folder_bundles:
    return folder
  m = re.search(r"\(([^)]*)\)[^(]*$", folder_bundles[0]["name"])
  if m:
    return f"{folder} - (Updated: {m.group(1)})"
  return folder


def _build_source_tree(bundles: list[Any], favorites: set[str], source: str) -> list[dict[str, Any]]:
  """Mirror sunnypilot's _open_source_dialog tree: Default root + folders + favorites."""
  tree: list[dict[str, Any]] = [
    {
      "name": "",
      "ref": "",
      "bundles": [{"ref": "Default", "name": _default_model_label(source), "index": -1, "generation": ""}],
    }
  ]
  folders: dict[str, list[dict[str, Any]]] = {}
  fav_bundles: list[dict[str, Any]] = []

  for bundle in bundles:
    entry, folder = _bundle_entry(bundle, favorites)
    folders.setdefault(folder, []).append(entry)
    if entry["ref"] and entry["ref"] in favorites:
      fav_bundles.append(entry)

  for folder, folder_bundles in sorted(
    folders.items(),
    key=lambda item: max((bundle["index"] for bundle in item[1]), default=-1),
    reverse=True,
  ):
    folder_bundles.sort(key=lambda bundle: bundle["index"], reverse=True)
    tree.append({
      "name": _folder_display_name(folder, folder_bundles),
      "ref": folder,
      "bundles": folder_bundles,
    })

  if fav_bundles:
    tree.insert(1, {"name": "Favorites", "ref": "Favorites", "bundles": fav_bundles})
  return tree


def _bundle_download(mm: Any | None) -> dict[str, Any]:
  if mm is None:
    return {}
  selected = getattr(mm, "selectedBundle", None)
  if selected is None or not getattr(selected, "models", None):
    return {}
  try:
    models = []
    verifying = False
    for m in selected.models:
      try:
        art = getattr(m, "artifact", None)
        dp = getattr(art, "downloadProgress", None) if art else None
        progress = float(getattr(dp, "progress", 0) or 0)
        status = getattr(dp, "status", "")
        if status:
          try:
            from openpilot.cereal import custom
            verifying = verifying or (getattr(status, "raw", status) == custom.ModelManagerSP.DownloadStatus.verifying)
          except Exception:
            pass
      except Exception:
        progress = float(getattr(m, "progress", 0) or 0)
      models.append({"type": str(getattr(m, "type", "")), "progress": progress})
    return {
      "status": str(getattr(selected, "status", "")),
      "name": getattr(selected, "displayName", "") or "",
      "internal": getattr(selected, "internalName", "") or "",
      "ref": getattr(selected, "ref", "") or "",
      "models": models,
      "verifying": verifying,
    }
  except Exception:
    return {}


def _big_model_state(state: dict[str, Any] | None) -> str | None:
  """Mirror sunnypilot big_model_state: 'failed' | 'loading' | None."""
  if not state:
    return None
  usbgpu_present_hw = bool(state.get("chestnutPresent"))
  started = bool(state.get("started"))
  if not usbgpu_present_hw:
    return None
  if started and state.get("usbgpuActive") is False:
    return "failed"
  if state.get("usbgpuLoading"):
    return "loading"
  return None


def _queued_name(current_ref: str, p: Any) -> str | None:
  """Name of the queued model when DownloadRef differs from the active download."""
  try:
    ref = p.get("ModelManager_DownloadRef")
    if not ref or ref == current_ref:
      return None
    resolved = _resolve_ref(ref, p)
    if resolved is None:
      return None
    bundle, _source = resolved
    return getattr(bundle, "internalName", "") or getattr(bundle, "displayName", "") or None
  except Exception:
    return None


def _models_status_impl() -> dict[str, Any]:
  from openpilot.common.params import Params
  p = Params()
  state = _device_state()
  active = _active_source(state)
  mm = _read_live_model_manager()

  favs_raw = p.get("ModelManager_Favs") or ""
  favorites = {f for f in str(favs_raw).split(";") if f}
  usbgpu_enabled = bool(state and state.get("chestnutPresent")) or _usbgpu_present()

  slots: dict[str, dict[str, Any]] = {}
  for source in ("qcom", "usbgpu"):
    bundles = _bundles_for_source(p, source, mm if source == active else None)
    selected = _selected_bundle(p, source)
    entry, _ = _bundle_entry(selected, favorites) if selected is not None else ({}, "")
    slots[source] = {
      "bundles": [_bundle_entry(bundle, favorites)[0] for bundle in bundles],
      "tree": _build_source_tree(bundles, favorites, source),
      "selected": entry,
      "active_ref": getattr(selected, "ref", "") or "Default",
      "default_label": _default_model_label(source),
    }

  big_state = _big_model_state(state)

  # Carry: the slot actually driving — matches sunnypilot carrying_model().
  carry_source = active
  carry_slot = slots[active]
  carry_display = carry_slot["selected"].get("name") or carry_slot["default_label"]
  carry_internal = carry_slot["selected"].get("internal") or carry_slot["default_label"]

  download = _bundle_download(mm)
  accel_state = _accelerator_state(p, chestnut_present=bool(state and state.get("chestnutPresent")))
  return {
    "ok": True,
    "active_source": active,
    "big_model_source": _big_model_source(p, state, accel_state),
    "usbgpu_enabled": usbgpu_enabled,
    "big_state": big_state,
    "carry_source": carry_source,
    "carry_display": carry_display,
    "carry_internal": carry_internal,
    "slots": slots,
    "download": download,
    "queued_name": _queued_name(download.get("ref", ""), p),
    "last_sync": p.get("ModelManager_LastSyncTime") or "",
    "last_sync_chestnut": p.get("ModelManager_LastSyncTime_Chestnut") or "",
    "cache_clear_pending": p.get_bool("ModelManager_ClearCache"),
    "cache_size_mb": _cache_size_mb(),
    "model_manager_online": mm is not None,
    "started": bool(state and state.get("started")),
    "accelerator": accel_state,
    "mirror": _mirror_state(p),
    "download_ref": p.get("ModelManager_DownloadRef") or "",
  }


def models_status() -> dict[str, Any]:
  if os.environ.get("WEBUI_DEV_PC") == "1":
    return _mock_models()
  try:
    return _models_status_impl()
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def _generation(bundle: Any) -> str:
  try:
    for ov in bundle.overrides or []:
      if ov.key == "generation":
        return ov.value or ""
  except Exception:
    pass
  return ""


def _resolve_ref(ref: str, p: Any) -> tuple[Any, str] | None:
  """Find bundle + source for a ref across cached/live bundles."""
  try:
    from openpilot.sunnypilot.models.helpers import resolve_bundle_by_ref
    mm = _read_live_model_manager()
    source_bundles: dict[str, list[Any]] = {}
    for src in ("qcom", "usbgpu"):
      source_bundles[src] = _bundles_for_source(p, src, mm if src == _active_source(_device_state()) else None)
    # resolve_bundle_by_ref keys only matter for lookup; keep webui source names.
    return resolve_bundle_by_ref(ref, source_bundles)
  except Exception:
    return None


def models_select(ref: str, index: int | None = None, source: str = "qcom") -> dict[str, Any]:
  """Mirror sunnypilot _on_model_selected: Default resets the slot; otherwise queue DownloadRef."""
  try:
    from openpilot.common.params import Params
    p = Params()
    if source not in _SOURCE_KEYS:
      return {"ok": False, "error": f"unknown model source: {source}"}

    key = _SOURCE_KEYS[source]
    active = _selected_bundle(p, source)
    prev_gen = _generation(active) if active is not None else ""

    needs_reset_cal = False
    if ref == "Default":
      p.remove(key)
      needs_reset_cal = True
    else:
      resolved = _resolve_ref(ref, p)
      if resolved is None:
        return {"ok": False, "error": f"model not found: {ref}"}
      bundle, _resolved_source = resolved
      new_gen = _generation(bundle)
      if new_gen and prev_gen and new_gen != prev_gen:
        needs_reset_cal = True
      p.put("ModelManager_DownloadRef", ref, block=True)
    return {"ok": True, "ref": ref, "source": source, "needs_reset_cal": needs_reset_cal}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def _mirror_state(p: Any) -> dict[str, Any]:
  """The Model Download Mirror / Model List Source rows, so the web panel can show
  and edit the same two settings the native Models page does."""
  try:
    import openpilot.sunnypilot.models.mirror as mirror
    hf_raw = (p.get(mirror.HF_MIRROR_PARAM) or "").strip()
    gh_raw = (p.get(mirror.GITHUB_PROXY_PARAM) or "").strip()
    if hf_raw == "off":
      hf_mode = "direct"
    elif mirror.normalize_base_url(hf_raw):
      hf_mode = "custom"
    else:
      hf_mode = "mirror"
    if gh_raw == mirror.PROXY_DIRECT_VALUE:
      gh_mode = "direct"
    elif mirror.normalize_base_url(gh_raw):
      gh_mode = "proxy"
    else:
      gh_mode = "auto"
    return {
      "hf_param": mirror.HF_MIRROR_PARAM,
      "gh_param": mirror.GITHUB_PROXY_PARAM,
      "hf_mode": hf_mode,
      "gh_mode": gh_mode,
      "hf_custom": mirror.normalize_base_url(hf_raw) or "",
      "gh_custom": mirror.normalize_base_url(gh_raw) or "",
      "hf_effective": mirror.describe_hf_mirror(p),
      "gh_effective": mirror.describe_github_proxy(p),
    }
  except Exception:
    return {}


def models_set_mirror(which: str, mode: str, url: str = "") -> dict[str, Any]:
  """Set one mirror row. `which` is 'hf' (model files) or 'gh' (catalog list);
  mode 'mirror'/'auto' clears the param back to the built-in default, 'direct'
  stores the off/direct sentinel, 'custom'/'proxy' validates and stores a base URL."""
  try:
    from openpilot.common.params import Params
    import openpilot.sunnypilot.models.mirror as mirror
    p = Params()
    if which == "hf":
      param = mirror.HF_MIRROR_PARAM
      if mode == "mirror":
        value = ""
      elif mode == "direct":
        value = "off"
      elif mode == "custom":
        base = mirror.normalize_base_url(url)
        if base is None:
          return {"ok": False, "error": "mirror must be an http(s) URL without spaces"}
        value = base
      else:
        return {"ok": False, "error": f"unknown mirror mode: {mode}"}
    elif which == "gh":
      param = mirror.GITHUB_PROXY_PARAM
      if mode == "auto":
        value = ""
      elif mode == "direct":
        value = mirror.PROXY_DIRECT_VALUE
      elif mode == "proxy":
        base = mirror.normalize_base_url(url)
        if base is None:
          return {"ok": False, "error": "proxy must be an http(s) URL without spaces"}
        value = base
      else:
        return {"ok": False, "error": f"unknown catalog mode: {mode}"}
    else:
      return {"ok": False, "error": f"unknown setting: {which}"}
    p.put(param, value, block=True)
    return {"ok": True, "param": param, "value": value}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def models_toggle_favorite(ref: str) -> dict[str, Any]:
  ref = (ref or "").strip()
  if not ref or ref == "Default":
    return {"ok": False, "error": "invalid model ref"}
  try:
    from openpilot.common.params import Params
    p = Params()
    favs_raw = p.get("ModelManager_Favs") or ""
    favorites = [f for f in str(favs_raw).split(";") if f]
    if ref in favorites:
      favorites = [f for f in favorites if f != ref]
    else:
      favorites.append(ref)
    p.put("ModelManager_Favs", ";".join(favorites), block=True)
    return {"ok": True, "ref": ref, "favorites": favorites}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def _mock_models() -> dict[str, Any]:
  qcom_tree = [
    {"name": "", "bundles": [{"ref": "Default", "name": "Stock (Default)", "index": -1, "generation": ""}]},
    {"name": "Favorites", "bundles": [{"ref": "mock-1", "name": "supercombo-test", "index": 1, "fav": True}]},
    {"name": "Release", "bundles": [{"ref": "mock-2", "name": "release-main", "index": 2}]},
  ]
  big_tree = [
    {"name": "", "bundles": [{"ref": "Default", "name": "Big Stock (Default)", "index": -1, "generation": ""}]},
    {"name": "Big Test", "bundles": [{"ref": "mock-big-1", "name": "tinygrad-test", "index": 5, "fav": True}]},
  ]
  return {
    "ok": True,
    "active_source": "qcom",
    "big_model_source": "device",
    "usbgpu_enabled": False,
    "big_state": None,
    "carry_source": "qcom",
    "carry_display": "Stock (Default)",
    "carry_internal": "Stock (Default)",
    "slots": {
      "qcom": {
        "tree": qcom_tree,
        "selected": {},
        "active_ref": "Default",
        "default_label": "Stock (Default)",
      },
      "usbgpu": {
        "tree": big_tree,
        "selected": {},
        "active_ref": "Default",
        "default_label": "Big Stock (Default)",
      },
    },
    "download": {
      "status": "downloading",
      "name": "mock-bundle",
      "ref": "mock-1",
      "models": [
        {"type": "supercombo", "progress": 0.42},
        {"type": "vision", "progress": 0.65},
        {"type": "policy", "progress": 0.1},
        {"type": "offPolicy", "progress": 0},
        {"type": "onPolicy", "progress": 0},
      ],
    },
    "last_sync": "",
    "cache_clear_pending": False,
    "cache_size_mb": 12.5,
    "model_manager_online": True,
    "started": False,
    "dev_pc": True,
    "accelerator": {
      "modes": ["off", "usb", "ios"],
      "mode": "off",
      "meaningful": True,
      "status": {"key": ""},
      "progress": None,
      "reason": None,
      "model": None,
      "default_model": None,
    },
  }