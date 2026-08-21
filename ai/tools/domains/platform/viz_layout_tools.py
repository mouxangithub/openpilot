"""PlotJuggler / JotPluggler layout inventory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai.system.paths import rel_tools, tools_path


def _list_layout_files(directory: Path, extensions: tuple[str, ...]) -> list[dict[str, Any]]:
  if not directory.is_dir():
    return []
  items: list[dict[str, Any]] = []
  for path in sorted(directory.iterdir()):
    if path.suffix.lower() in extensions and path.is_file():
      items.append({
        "name": path.stem,
        "file": path.name,
        "path": str(path),
      })
  return items


def list_plotjuggler_layouts() -> dict[str, Any]:
  layout_dir = tools_path("plotjuggler", "layouts")
  layouts = _list_layout_files(layout_dir, (".xml",))
  script = rel_tools("plotjuggler", "juggle.py")
  return {
    "ok": True,
    "count": len(layouts),
    "layouts": layouts,
    "script": script,
    "hint": "Use layout name with pc_launch_plotjuggler(layout='tuning') → layouts/tuning.xml",
    "common": ["tuning", "gps_vs_llk", "controls_mismatch_debug", "system_lag_debug"],
  }


def plotjuggler_apply_layout(
  layout: str,
  *,
  route: str = "",
) -> dict[str, Any]:
  """Resolve PlotJuggler layout file and launch hints."""
  name = (layout or "").strip()
  if not name:
    return {"ok": False, "error": "layout name required"}
  listing = list_plotjuggler_layouts()
  layouts = listing.get("layouts") or []
  match = None
  for item in layouts:
    if item.get("name") == name or item.get("file") == f"{name}.xml":
      match = item
      break
  if not match:
    return {
      "ok": False,
      "error": f"Layout '{name}' not found",
      "available": [x.get("name") for x in layouts[:12]],
    }
  out: dict[str, Any] = {
    "ok": True,
    "layout": name,
    "path": match.get("path"),
    "script": rel_tools("plotjuggler", "juggle.py"),
    "pc_command": f"{rel_tools('plotjuggler', 'juggle.py')} --layout {name}" + (f" {route}" if route else ""),
    "hint": "PC: pc_launch_plotjuggler(route=..., layout=...); device: plotjuggler_data_summary.",
  }
  if route:
    out["route"] = route
  return out


def list_jotpluggler_layouts() -> dict[str, Any]:
  layout_dir = tools_path("jotpluggler", "layouts")
  layouts = _list_layout_files(layout_dir, (".json",))
  # include layout metadata title if present
  enriched = []
  for item in layouts:
    entry = dict(item)
    try:
      data = json.loads(Path(item["path"]).read_text(encoding="utf-8"))
      if isinstance(data, dict) and data.get("title"):
        entry["title"] = data["title"]
    except Exception:
      pass
    enriched.append(entry)
  return {
    "ok": True,
    "count": len(enriched),
    "layouts": enriched,
    "script": rel_tools("jotpluggler", "jotpluggler"),
    "hint": "Use layout stem with pc_launch_jotpluggler(layout='gps')",
    "common": ["gps", "ublox-debug", "cameras-and-map"],
  }
