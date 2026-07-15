"""Route media export: clip, audio, ublox (tools/clip, tools/scripts)."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

from ai.tools.op_run import OPENPILOT_ROOT, resolve_route_ref, run_subprocess, validate_route_ref

_OUTPUT_ROOT = OPENPILOT_ROOT / "ai" / "data" / "exports"


def _import_logreader():
  try:
    from openpilot.tools.lib.logreader import LogReader, ReadMode
    return LogReader, ReadMode
  except ImportError:
    from tools.lib.logreader import LogReader, ReadMode  # type: ignore
    return LogReader, ReadMode


def route_export_clip(
  route: str,
  *,
  start_sec: int | None = None,
  end_sec: int | None = None,
  demo: bool = False,
  output: str | None = None,
  data_dir: str | None = None,
  title: str | None = None,
) -> dict[str, Any]:
  script = OPENPILOT_ROOT / "tools" / "clip" / "run.py"
  if not script.is_file():
    return {"ok": False, "error": f"Missing {script}"}

  _OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
  out_path = output or str(_OUTPUT_ROOT / f"clip_{int(time.time())}.mp4")

  cmd = [sys.executable, str(script)]
  route_arg = ""
  if demo:
    cmd.append("--demo")
  else:
    verr = validate_route_ref(route or "")
    if verr:
      return {"ok": False, "error": verr}
    route_arg = resolve_route_ref(route or "")
    if start_sec is not None and end_sec is not None:
      cmd.append(f"{route_arg}/{start_sec}/{end_sec}")
    else:
      cmd.append(route_arg)
  cmd.extend(["-o", out_path])
  if data_dir:
    cmd.extend(["-d", data_dir])
  if title:
    cmd.extend(["-t", title])

  res = run_subprocess(cmd, timeout=1800)
  exists = Path(out_path).is_file()
  return {
    **res,
    "ok": res.get("ok") and exists,
    "output_path": out_path if exists else None,
    "route": route_arg if route_arg else "demo",
    "script": "tools/clip/run.py",
    "hint": "Open MP4 on PC or download from device ai/data/exports.",
  }


def route_extract_audio(
  route: str,
  *,
  output: str | None = None,
) -> dict[str, Any]:
  err = validate_route_ref(route)
  if err:
    return {"ok": False, "error": err}
  route_arg = resolve_route_ref(route)

  try:
    import numpy as np
    LogReader, ReadMode = _import_logreader()
  except Exception as e:
    return {"ok": False, "error": str(e)}

  try:
    lr = LogReader(route_arg, ReadMode.AUTO)
    audio_messages = list(lr.filter("rawAudioData"))
    if not audio_messages:
      return {"ok": False, "error": "No rawAudioData in route", "route": route_arg}

    sample_rate = int(audio_messages[0].sampleRate)
    chunks = [np.frombuffer(m.data, dtype=np.int16) for m in audio_messages]
    full = np.concatenate(chunks)

    _OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    out_path = output or str(_OUTPUT_ROOT / f"audio_{int(time.time())}.wav")

    import wave
    with wave.open(out_path, "wb") as wav:
      wav.setnchannels(1)
      wav.setsampwidth(2)
      wav.setframerate(sample_rate)
      wav.writeframes(full.tobytes())

    return {
      "ok": True,
      "route": route_arg,
      "output_path": out_path,
      "sample_rate_hz": sample_rate,
      "frames": int(len(full)),
      "duration_sec": round(len(full) / sample_rate, 2),
      "script": "tools/scripts/extract_audio.py",
    }
  except Exception as e:
    return {"ok": False, "error": str(e), "route": route_arg}


def route_ublox_summary(route: str, *, max_messages: int = 5000) -> dict[str, Any]:
  err = validate_route_ref(route)
  if err:
    return {"ok": False, "error": err}
  route_arg = resolve_route_ref(route)

  try:
    LogReader, ReadMode = _import_logreader()
  except Exception as e:
    return {"ok": False, "error": str(e)}

  try:
    lr = LogReader(route_arg, ReadMode.AUTO)
    count = 0
    total_bytes = 0
    first_ts: float | None = None
    last_ts: float | None = None
    for msg in lr:
      if count >= max_messages:
        break
      if msg.which() != "ubloxRaw":
        continue
      count += 1
      raw = msg.ubloxRaw
      blob = raw if isinstance(raw, (bytes, bytearray)) else bytes(raw)
      total_bytes += len(blob)
      ts = msg.logMonoTime / 1e9
      if first_ts is None:
        first_ts = ts
      last_ts = ts

    if count == 0:
      return {"ok": False, "error": "No ubloxRaw messages", "route": route_arg}

    return {
      "ok": True,
      "route": route_arg,
      "ublox_message_count": count,
      "total_bytes": total_bytes,
      "avg_bytes_per_msg": round(total_bytes / count, 1),
      "time_span_sec": round((last_ts or 0) - (first_ts or 0), 2) if first_ts is not None else None,
      "script": "tools/scripts/save_ubloxraw_stream.py",
      "hint": "Use JotPluggler layout gps / ublox-debug for plots.",
    }
  except Exception as e:
    return {"ok": False, "error": str(e), "route": route_arg}
