"""Model manager tree + download status."""

from __future__ import annotations

import os
import re
import time
from typing import Any


def _cache_size_mb() -> float:
  try:
    from openpilot.sunnypilot.models.runners.constants import CUSTOM_MODEL_PATH
    if not os.path.exists(CUSTOM_MODEL_PATH):
      return 0.0
    total = sum(os.path.getsize(os.path.join(CUSTOM_MODEL_PATH, f)) for f in os.listdir(CUSTOM_MODEL_PATH))
    return total / (1024 ** 2)
  except Exception:
    return 0.0


def _default_model_label() -> str:
  try:
    from openpilot.sunnypilot.models.model_name import DEFAULT_MODEL
    return f"{DEFAULT_MODEL} (Default)"
  except Exception:
    return "Default (Default)"


def _default_tree_root() -> dict[str, Any]:
  return {
    "name": "",
    "ref": "",
    "bundles": [{"ref": "Default", "name": _default_model_label(), "index": -1, "generation": ""}],
  }


def _bundle_entry(bundle: Any, favorites: set[str]) -> tuple[dict[str, Any], str]:
  folder = ""
  generation = ""
  for ov in bundle.overrides:
    if ov.key == "folder":
      folder = ov.value
    if ov.key == "generation":
      generation = ov.value
  return {
    "ref": bundle.ref,
    "name": bundle.displayName,
    "internal": bundle.internalName,
    "index": bundle.index,
    "generation": generation,
    "fav": bundle.ref in favorites,
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


def _build_model_tree(mm: Any, favorites: set[str]) -> list[dict[str, Any]]:
  """Mirror sunnypilot on-device Models tree (Default root + folders + favorites)."""
  tree: list[dict[str, Any]] = [_default_tree_root()]
  folders: dict[str, list[dict[str, Any]]] = {}
  fav_bundles: list[dict[str, Any]] = []

  for bundle in mm.availableBundles:
    entry, folder = _bundle_entry(bundle, favorites)
    folders.setdefault(folder, []).append(entry)
    if bundle.ref in favorites:
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


def _read_model_manager(timeout_ms: int = 2500) -> Any | None:
  import openpilot.cereal.messaging as messaging

  sm = messaging.SubMaster(["modelManagerSP"], poll="modelManagerSP")
  deadline = time.monotonic() + timeout_ms / 1000.0
  while time.monotonic() < deadline:
    sm.update(200)
    if sm.valid.get("modelManagerSP"):
      return sm["modelManagerSP"]
  return None


def models_status() -> dict[str, Any]:
  if os.environ.get("WEBUI_DEV_PC") == "1":
    return _mock_models()

  try:
    from openpilot.common.params import Params

    p = Params()
    mm = _read_model_manager()
    tree = [_default_tree_root()]
    active_ref = "Default"
    active_name = _default_model_label()
    active_generation = ""
    download: dict[str, Any] = {}
    download_index = p.get("ModelManager_DownloadIndex")
    favs_raw = p.get("ModelManager_Favs") or ""
    favorites = {f for f in str(favs_raw).split(";") if f}
    model_manager_online = mm is not None

    if mm is not None:
      tree = _build_model_tree(mm, favorites)
      if mm.activeBundle and mm.activeBundle.ref:
        active_ref = mm.activeBundle.ref
        active_name = mm.activeBundle.internalName or mm.activeBundle.displayName
        for ov in mm.activeBundle.overrides:
          if ov.key == "generation":
            active_generation = ov.value
      if mm.selectedBundle:
        def _part_progress(model: Any) -> float:
          try:
            art = getattr(model, "artifact", None)
            if art is not None:
              dp = getattr(art, "downloadProgress", None)
              if dp is not None:
                return float(getattr(dp, "progress", 0) or 0)
          except Exception:
            pass
          return float(getattr(model, "progress", 0) or 0)

        download = {
          "status": str(mm.selectedBundle.status),
          "name": mm.selectedBundle.displayName,
          "models": [{"type": str(m.type), "progress": _part_progress(m)} for m in mm.selectedBundle.models],
        }

    return {
      "ok": True,
      "active_ref": active_ref,
      "active_name": active_name,
      "active_generation": active_generation,
      "tree": tree,
      "download": download,
      "download_index": download_index,
      "last_sync": p.get("ModelManager_LastSyncTime") or "",
      "cache_clear_pending": p.get_bool("ModelManager_ClearCache"),
      "cache_size_mb": _cache_size_mb(),
      "custom_model_active": p.get("ModelManager_ActiveBundle") is not None,
      "model_manager_online": model_manager_online,
    }
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def models_select(ref: str, index: int | None = None) -> dict[str, Any]:
  try:
    from openpilot.common.params import Params
    p = Params()
    prev_gen = ""
    mm = _read_model_manager()
    if mm and mm.activeBundle:
      for ov in mm.activeBundle.overrides:
        if ov.key == "generation":
          prev_gen = ov.value
    new_gen = ""
    needs_reset_cal = False
    if ref == "Default":
      p.remove("ModelManager_ActiveBundle")
      needs_reset_cal = True
    elif index is not None:
      p.put("ModelManager_DownloadIndex", index, block=True)
      if mm:
        for bundle in mm.availableBundles:
          if bundle.index == index:
            for ov in bundle.overrides:
              if ov.key == "generation":
                new_gen = ov.value
            break
        if new_gen and prev_gen and new_gen != prev_gen:
          needs_reset_cal = True
    return {"ok": True, "ref": ref, "needs_reset_cal": needs_reset_cal}
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
  return {
    "ok": True,
    "active_ref": "Default",
    "active_name": "Default (Default)",
    "tree": [
      {"name": "", "bundles": [{"ref": "Default", "name": "Default (Default)", "index": -1}]},
      {"name": "Favorites", "bundles": [{"ref": "mock-1", "name": "supercombo-test", "index": 1}]},
      {"name": "Release", "bundles": [{"ref": "mock-2", "name": "release-main", "index": 2}]},
    ],
    "download": {
      "status": "downloading",
      "name": "mock-bundle",
      "models": [
        {"type": "supercombo", "progress": 0.42},
        {"type": "vision", "progress": 0.65},
        {"type": "policy", "progress": 0.1},
        {"type": "offPolicy", "progress": 0},
        {"type": "onPolicy", "progress": 0},
      ],
    },
    "cache_size_mb": 12.5,
    "model_manager_online": True,
    "dev_pc": True,
  }
