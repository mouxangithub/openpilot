"""Route event timeline for engage/diagnostic review."""

from __future__ import annotations

from typing import Any

from ai.tools.op_run import resolve_route_ref, validate_route_ref


def _import_logreader():
  try:
    from openpilot.tools.lib.logreader import LogReader, ReadMode
    return LogReader, ReadMode
  except ImportError:
    from tools.lib.logreader import LogReader, ReadMode  # type: ignore
    return LogReader, ReadMode


_EVENT_TOPICS = ("selfdriveState", "onroadEvents", "controlsState", "carState", "managerState")


def route_event_timeline(
  route: str,
  *,
  max_events: int = 80,
  max_messages: int = 12000,
) -> dict[str, Any]:
  """Chronological engage/disengage and onroad events from route qlog."""
  err = validate_route_ref(route)
  if err:
    return {"ok": False, "error": err}
  route_arg = resolve_route_ref(route)

  try:
    LogReader, ReadMode = _import_logreader()
  except Exception as e:
    return {"ok": False, "error": str(e)}

  events: list[dict[str, Any]] = []
  prev_enabled: bool | None = None
  scanned = 0

  try:
    lr = LogReader(route_arg, ReadMode.AUTO)
    for msg in lr:
      if scanned >= max_messages or len(events) >= max_events:
        break
      scanned += 1
      which = msg.which()
      t_sec = round(msg.logMonoTime / 1e9, 2)

      if which == "controlsState":
        try:
          enabled = bool(msg.controlsState.enabled)
          if prev_enabled is not None and enabled != prev_enabled:
            events.append({
              "t_sec": t_sec,
              "type": "engage" if enabled else "disengage",
              "source": "controlsState",
            })
          prev_enabled = enabled
        except Exception:
          pass

      elif which == "onroadEvents":
        try:
          for evt in msg.onroadEvents:
            name = getattr(evt, "name", None)
            if name:
              events.append({
                "t_sec": t_sec,
                "type": "onroad_event",
                "name": str(name),
                "no_entry": bool(getattr(evt, "noEntry", False)),
                "immediate_disable": bool(getattr(evt, "immediateDisable", False)),
              })
        except Exception:
          pass

      elif which == "selfdriveState":
        try:
          ss = msg.selfdriveState
          state = getattr(ss, "state", None)
          if state is not None:
            events.append({
              "t_sec": t_sec,
              "type": "selfdrive_state",
              "state": str(state),
            })
        except Exception:
          pass

      elif which == "managerState":
        try:
          for proc in msg.managerState.processes:
            if proc.shouldBeRunning and not proc.running:
              events.append({
                "t_sec": t_sec,
                "type": "process_down",
                "name": proc.name,
              })
        except Exception:
          pass

    events.sort(key=lambda e: e.get("t_sec", 0))
    events = events[:max_events]

    engage_count = sum(1 for e in events if e.get("type") == "engage")
    disengage_count = sum(1 for e in events if e.get("type") == "disengage")
    critical = [e for e in events if e.get("no_entry") or e.get("immediate_disable")]

    return {
      "ok": True,
      "route": route_arg,
      "messages_scanned": scanned,
      "event_count": len(events),
      "engage_count": engage_count,
      "disengage_count": disengage_count,
      "critical_events": critical[:15],
      "timeline": events,
      "hint": "Align t_sec with PlotJuggler time axis for root-cause analysis.",
    }
  except Exception as e:
    return {"ok": False, "error": str(e), "route": route_arg}
