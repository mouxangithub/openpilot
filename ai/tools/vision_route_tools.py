"""Route vision context (frame extract + basic image stats)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def analyze_route_vision(
  route: str,
  *,
  segment: int = 0,
  frame: int = 0,
  camera: str = "front",
) -> dict[str, Any]:
  """Extract a route frame and return path + brightness stats for vision review."""
  from ai.tools.route_tools import route_fetch_frame

  fetched = route_fetch_frame(route, segment=segment, frame=frame, camera=camera)
  if not fetched.get("ok"):
    return fetched

  path = fetched.get("path") or fetched.get("local_path") or ""
  stats: dict[str, Any] = {}
  if path and Path(path).is_file():
    try:
      from PIL import Image
      import statistics
      with Image.open(path) as img:
        gray = img.convert("L")
        pixels = list(gray.getdata())
        stats = {
          "width": img.width,
          "height": img.height,
          "mode": img.mode,
          "brightness_mean": round(statistics.mean(pixels), 1),
          "brightness_stdev": round(statistics.pstdev(pixels), 1) if len(pixels) > 1 else 0,
        }
        stats["likely_dark"] = stats["brightness_mean"] < 40
        stats["likely_overexposed"] = stats["brightness_mean"] > 220
    except ImportError:
      stats["note"] = "Install Pillow for brightness stats; frame path still valid."
    except Exception as e:
      stats["error"] = str(e)

  hint = "Attach frame in multimodal chat or inspect locally for lane/camera issues."
  if stats.get("likely_dark"):
    hint = "Frame appears dark — check camera cover, night exposure, or roadCamera index."
  elif stats.get("likely_overexposed"):
    hint = "Frame appears overexposed — check sun glare or HDR settings."

  return {
    "ok": True,
    "route": fetched.get("route") or route,
    "segment": segment,
    "frame": frame,
    "camera": camera,
    "frame_path": path,
    "image_stats": stats,
    "hint": hint,
  }
