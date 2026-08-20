"""Track PC-native tool launches and captured route context for op助手."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from ai.tools.op_run import resolve_route_ref

_SESSIONS_DIR = Path(__file__).resolve().parents[1] / "data" / "pc_tool_sessions"
_MAX_SESSIONS = 40
_DEMO_ROUTE = "5beb9b58bd12b691/0000010a--a51155e496"


def _sessions_file() -> Path:
  try:
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
  except FileExistsError:
    if not _SESSIONS_DIR.is_dir():
      raise
  return _SESSIONS_DIR / "sessions.json"


def _load_all() -> list[dict[str, Any]]:
  path = _sessions_file()
  if not path.is_file():
    return []
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []
  except Exception:
    return []


def _save_all(sessions: list[dict[str, Any]]) -> None:
  trimmed = sessions[:_MAX_SESSIONS]
  _sessions_file().write_text(json.dumps(trimmed, ensure_ascii=False, indent=2), encoding="utf-8")


def route_folder_name(route: str) -> str:
  ref = resolve_route_ref(route)
  if "/" in ref:
    return ref.rsplit("/", 1)[0]
  return ref


def pid_alive(pid: int | None) -> bool:
  if not pid or pid <= 0:
    return False
  try:
    os.kill(pid, 0)
    return True
  except OSError:
    return False


def _import_logreader():
  try:
    from openpilot.tools.lib.logreader import LogReader, ReadMode
    return LogReader, ReadMode
  except ImportError:
    from tools.lib.logreader import LogReader, ReadMode  # type: ignore
    return LogReader, ReadMode


def extract_route_car_params(route: str) -> dict[str, Any]:
  route_arg = resolve_route_ref(route)
  try:
    LogReader, ReadMode = _import_logreader()
    from opendbc.car.fingerprints import MIGRATION
  except Exception as e:
    return {"ok": False, "error": str(e), "route": route_arg}

  try:
    lr = LogReader(route_arg, ReadMode.QLOG)
    CP = lr.first("carParams")
    if CP is None:
      lr2 = LogReader(route_arg, ReadMode.AUTO)
      CP = lr2.first("carParams")
    if CP is None:
      return {"ok": False, "error": "No carParams in route", "route": route_arg}

    platform = MIGRATION.get(CP.carFingerprint, CP.carFingerprint)
    fw_sample = []
    for fw in list(CP.carFw)[:12]:
      ver = fw.fwVersion
      if isinstance(ver, bytes):
        ver = ver.decode("utf-8", errors="replace")
      fw_sample.append({
        "ecu": fw.ecu.raw,
        "address": fw.address,
        "fw_version": str(ver),
      })
    return {
      "ok": True,
      "route": route_arg,
      "car_fingerprint": CP.carFingerprint,
      "platform": platform,
      "car_name": getattr(CP, "carName", "") or "",
      "vin": (CP.carVin or "")[:8] + "…" if CP.carVin else "",
      "openpilot_longitudinal": bool(getattr(CP, "openpilotLongitudinalControl", False)),
      "secoc_required": bool(getattr(CP, "secOcRequired", False)),
      "fw_count": len(CP.carFw),
      "fw_sample": fw_sample,
    }
  except Exception as e:
    return {"ok": False, "error": str(e), "route": route_arg}


def list_route_topics(route: str, *, max_messages: int = 800) -> dict[str, Any]:
  route_arg = resolve_route_ref(route)
  try:
    LogReader, ReadMode = _import_logreader()
  except Exception as e:
    return {"ok": False, "error": str(e), "route": route_arg}

  try:
    lr = LogReader(route_arg, ReadMode.AUTO)
    counts: dict[str, int] = {}
    scanned = 0
    for msg in lr:
      if scanned >= max_messages:
        break
      scanned += 1
      name = msg.which()
      counts[name] = counts.get(name, 0) + 1
    topics = sorted(counts.keys())
    return {
      "ok": True,
      "route": route_arg,
      "messages_scanned": scanned,
      "topic_count": len(topics),
      "topics": topics,
      "topic_counts": {k: counts[k] for k in topics[:40]},
    }
  except Exception as e:
    return {"ok": False, "error": str(e), "route": route_arg}


def infer_juggle_context(route: str) -> dict[str, Any]:
  """Mirror tools/plotjuggler/juggle.py DBC/platform inference."""
  route_arg = resolve_route_ref(route)
  try:
    LogReader, ReadMode = _import_logreader()
    from opendbc.car.fingerprints import MIGRATION
    from openpilot.tools.cabana.dbc.generate_dbc_json import generate_dbc_dict
  except Exception as e:
    return {"ok": False, "error": str(e), "route": route_arg}

  try:
    lr = LogReader(route_arg, ReadMode.AUTO)
    CP = lr.first("carParams")
    if CP is None:
      return {"ok": False, "error": "No carParams for DBC inference", "route": route_arg}
    platform = MIGRATION.get(CP.carFingerprint, CP.carFingerprint)
    dbc_map = generate_dbc_dict()
    dbc = dbc_map.get(platform)
    return {
      "ok": True,
      "route": route_arg,
      "platform": platform,
      "dbc": dbc,
      "juggle_script": "tools/plotjuggler/juggle.py",
    }
  except Exception as e:
    return {"ok": False, "error": str(e), "route": route_arg}


def capture_route_context(
  route: str,
  *,
  include_signal_summary: bool = True,
  include_topics: bool = True,
  include_folder_summary: bool = True,
) -> dict[str, Any]:
  route_arg = resolve_route_ref(route)
  folder = route_folder_name(route_arg)
  ctx: dict[str, Any] = {
    "ok": True,
    "route_ref": route_arg,
    "route_folder": folder,
    "captured_at": time.time(),
  }

  ctx["car_params"] = extract_route_car_params(route_arg)
  ctx["juggle_context"] = infer_juggle_context(route_arg)

  if include_folder_summary:
    try:
      from ai.tools.diagnostics_tools import analyze_route_summary
      from ai.tools.route_tools import route_video_info

      folder_only = folder.split("|")[-1] if "|" in folder else folder
      ctx["route_summary"] = analyze_route_summary(folder_only)
      ctx["video_info"] = route_video_info(folder_only)
    except Exception as e:
      ctx["route_summary"] = {"ok": False, "error": str(e)}
      ctx["video_info"] = {"ok": False, "error": str(e)}

  if include_topics:
    ctx["topics"] = list_route_topics(route_arg)

  if include_signal_summary:
    try:
      from ai.tools.plotjuggler_tools import plotjuggler_data_summary
      ctx["signal_summary"] = plotjuggler_data_summary(route_arg, max_messages=6000)
    except Exception as e:
      ctx["signal_summary"] = {"ok": False, "error": str(e)}

  return ctx


def create_session(
  *,
  tool: str,
  launch_params: dict[str, Any],
  command: list[str],
  pid: int | None,
  route: str | None = None,
  capture_data: bool = True,
) -> dict[str, Any]:
  session_id = uuid.uuid4().hex[:12]
  now = time.time()
  data_snapshot: dict[str, Any] | None = None
  effective_route = route
  if launch_params.get("demo") and not effective_route:
    effective_route = _DEMO_ROUTE

  if capture_data and effective_route:
    try:
      data_snapshot = capture_route_context(effective_route)
    except Exception as e:
      data_snapshot = {"ok": False, "error": str(e)}

  record = {
    "session_id": session_id,
    "tool": tool,
    "pid": pid,
    "alive": pid_alive(pid),
    "launch_params": launch_params,
    "command": command,
    "route": effective_route,
    "created_at": now,
    "updated_at": now,
    "data_snapshot": data_snapshot,
  }
  sessions = _load_all()
  sessions.insert(0, record)
  _save_all(sessions)
  return record


def list_sessions(*, limit: int = 20) -> dict[str, Any]:
  sessions = _load_all()[: max(1, min(limit, _MAX_SESSIONS))]
  items = []
  for s in sessions:
    items.append({
      "session_id": s.get("session_id"),
      "tool": s.get("tool"),
      "pid": s.get("pid"),
      "alive": pid_alive(s.get("pid")),
      "route": s.get("route"),
      "created_at": s.get("created_at"),
      "launch_params": s.get("launch_params"),
      "has_data_snapshot": bool(s.get("data_snapshot")),
    })
  return {"ok": True, "count": len(items), "sessions": items}


def get_session(
  session_id: str,
  *,
  refresh_process: bool = True,
  refresh_data: bool = False,
) -> dict[str, Any]:
  sessions = _load_all()
  for i, s in enumerate(sessions):
    if s.get("session_id") != session_id:
      continue
    if refresh_process:
      s["alive"] = pid_alive(s.get("pid"))
      s["updated_at"] = time.time()
      sessions[i] = s
      _save_all(sessions)
    if refresh_data and s.get("route"):
      s["data_snapshot"] = capture_route_context(s["route"])
      s["updated_at"] = time.time()
      sessions[i] = s
      _save_all(sessions)
    return {"ok": True, **s}
  return {"ok": False, "error": f"Session not found: {session_id}"}
