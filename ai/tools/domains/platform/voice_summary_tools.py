"""Post-drive voice/text summary for op助手."""

from __future__ import annotations

import shutil
import subprocess
from typing import Any, Callable

from ai.tools.diagnostics_tools import trip_review


def build_post_drive_summary(
  params,
  get_state_reader: Callable,
  *,
  brand: str = "",
  route_name: str = "",
) -> dict[str, Any]:
  """Text summary suitable for TTS or notification."""
  review = trip_review(params, get_state_reader, brand=brand, route_name=route_name or None)
  recs = review.get("recommendations") or []
  lines = [
    "行程复盘。",
    f"路线：{review.get('route_name') or '最近一次'}。",
  ]
  if review.get("engage_rate") is not None:
    lines.append(f"辅助驾驶开启比例约 {int(float(review['engage_rate']) * 100)}%。")
  if recs:
    lines.append("建议：" + "；".join(str(r) for r in recs[:3]))
  else:
    lines.append("未发现明显异常。")
  text = "".join(lines)[:800]
  return {"ok": True, "text": text, "review": review}


def post_drive_voice_summary(
  params,
  get_state_reader: Callable,
  *,
  brand: str = "",
  route_name: str = "",
  speak: bool = False,
) -> dict[str, Any]:
  """Build summary; optionally speak via espeak/say if available."""
  built = build_post_drive_summary(params, get_state_reader, brand=brand, route_name=route_name)
  if not built.get("ok"):
    return built
  text = built.get("text", "")
  spoken = False
  tts_error = None
  if speak and text:
    for cmd in (
      ["espeak", "-s", "150", text[:400]],
      ["say", text[:400]],
    ):
      if shutil.which(cmd[0]):
        try:
          subprocess.run(cmd, timeout=30, check=False)
          spoken = True
          break
        except Exception as e:
          tts_error = str(e)
  return {**built, "spoken": spoken, "tts_error": tts_error}
