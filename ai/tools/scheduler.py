"""Scheduled read-only / offroad tasks for op助手."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Awaitable, Callable, TYPE_CHECKING

if TYPE_CHECKING:
  from openpilot.common.params import Params


def _default_params():
  from openpilot.common.params import Params
  return Params()

TASKS_KEY = "ai_scheduled_tasks"
STATE_KEY = "ai_scheduler_state"
MAX_TASKS = 20

VALID_ACTIONS = frozenset({
  "read_last_log", "read_usage", "read_tune_snapshot", "memory_ping", "snapshot_tune",
  "trip_review_offroad", "reindex_rag_wifi", "check_critical_events",
  "post_drive_review_offroad", "check_param_watchlist_offroad", "git_fetch_wifi",
})
VALID_TRIGGERS = frozenset({"interval", "on_offroad", "on_ignition", "on_wifi", "daily_at"})


def _load_tasks(params: Params) -> list[dict[str, Any]]:
  try:
    raw = params.get(TASKS_KEY)
    if not raw:
      return []
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    data = json.loads(raw)
    return data if isinstance(data, list) else []
  except Exception:
    return []


def _save_tasks(params: Params, tasks: list[dict[str, Any]]) -> None:
  params.put(TASKS_KEY, json.dumps(tasks[:MAX_TASKS], ensure_ascii=False))


def _load_state(params: Params) -> dict[str, Any]:
  try:
    raw = params.get(STATE_KEY)
    if not raw:
      return {}
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}
  except Exception:
    return {}


def _save_state(params: Params, state: dict[str, Any]) -> None:
  params.put(STATE_KEY, json.dumps(state, ensure_ascii=False))


def list_tasks(params: Params | None = None) -> dict[str, Any]:
  params = params or _default_params()
  return {"ok": True, "tasks": _load_tasks(params)}


def upsert_task(
  params: Params,
  *,
  task_id: str | None,
  name: str,
  action: str,
  interval_minutes: int = 60,
  enabled: bool = True,
  payload: dict[str, Any] | None = None,
  trigger: str = "interval",
) -> dict[str, Any]:
  trigger = trigger or "interval"
  if trigger not in VALID_TRIGGERS:
    return {"ok": False, "error": f"trigger must be one of {sorted(VALID_TRIGGERS)}"}
  if trigger == "interval" and interval_minutes < 5:
    return {"ok": False, "error": "interval_minutes must be >= 5 for interval trigger"}
  if trigger == "daily_at":
    hour = int((payload or {}).get("hour", 8))
    minute = int((payload or {}).get("minute", 0))
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
      return {"ok": False, "error": "daily_at requires hour 0-23 and minute 0-59 in payload"}
  if action not in VALID_ACTIONS:
    return {"ok": False, "error": f"Unknown action '{action}'"}
  tasks = _load_tasks(params)
  tid = task_id or f"t_{uuid.uuid4().hex[:10]}"
  now = int(time.time())
  entry = {
    "id": tid,
    "name": name or action,
    "action": action,
    "trigger": trigger,
    "interval_minutes": interval_minutes,
    "enabled": enabled,
    "payload": payload or {},
    "last_run": 0,
    "last_result": "",
    "created_at": now,
  }
  replaced = False
  for i, t in enumerate(tasks):
    if t.get("id") == tid:
      entry["created_at"] = t.get("created_at", now)
      entry["last_run"] = t.get("last_run", 0)
      entry["last_result"] = t.get("last_result", "")
      tasks[i] = entry
      replaced = True
      break
  if not replaced:
    tasks.append(entry)
  _save_tasks(params, tasks)
  return {"ok": True, "task": entry}


def remove_task(params: Params, task_id: str) -> dict[str, Any]:
  tasks = _load_tasks(params)
  new_tasks = [t for t in tasks if t.get("id") != task_id]
  _save_tasks(params, new_tasks)
  return {"ok": True, "removed": len(tasks) - len(new_tasks)}


def _should_run_daily_at(task: dict[str, Any], now: int) -> bool:
  import datetime
  payload = task.get("payload") or {}
  hour = int(payload.get("hour", 8))
  minute = int(payload.get("minute", 0))
  dt = datetime.datetime.fromtimestamp(now)
  if dt.hour != hour or dt.minute != minute:
    return False
  last = int(task.get("last_run", 0))
  return now - last >= 3600


def ensure_default_scheduler_tasks(params: Params) -> dict[str, Any]:
  """Seed a few useful tasks when scheduler is empty."""
  tasks = _load_tasks(params)
  if tasks:
    return {"ok": True, "seeded": 0, "reason": "tasks already exist"}
  defaults = [
    {"name": "每日用量", "action": "read_usage", "trigger": "daily_at", "interval_minutes": 1440, "payload": {"hour": 9, "minute": 0}},
    {"name": "停车复盘", "action": "post_drive_review_offroad", "trigger": "on_offroad", "interval_minutes": 60, "payload": {}},
    {"name": "WiFi 拉取 Git", "action": "git_fetch_wifi", "trigger": "on_wifi", "interval_minutes": 60, "payload": {}},
    {"name": "参数漂移检查", "action": "check_param_watchlist_offroad", "trigger": "on_offroad", "interval_minutes": 60, "payload": {}},
  ]
  for spec in defaults:
    upsert_task(
      params,
      task_id=None,
      name=spec["name"],
      action=spec["action"],
      interval_minutes=spec["interval_minutes"],
      enabled=True,
      payload=spec.get("payload"),
      trigger=spec["trigger"],
    )
  return {"ok": True, "seeded": len(defaults)}


def _should_run_interval(task: dict[str, Any], now: int) -> bool:
  interval = int(task.get("interval_minutes", 60)) * 60
  last = int(task.get("last_run", 0))
  return now - last >= interval


async def run_due_tasks(
  params: Params,
  *,
  is_driving: Callable[[], bool],
  is_ignition: Callable[[], bool],
  is_wifi: Callable[[], bool],
  execute_action: Callable[[str, dict[str, Any]], Awaitable[str]],
) -> list[dict[str, Any]]:
  now = int(time.time())
  tasks = _load_tasks(params)
  results: list[dict[str, Any]] = []
  changed = False

  prev = _load_state(params)
  driving = is_driving()
  ignition = is_ignition()
  wifi = is_wifi()

  for task in tasks:
    if not task.get("enabled"):
      continue

    trigger = task.get("trigger", "interval")
    should_run = False
    if trigger == "interval":
      should_run = _should_run_interval(task, now)
    elif trigger == "on_offroad":
      should_run = bool(prev.get("driving")) and not driving
    elif trigger == "on_ignition":
      should_run = (not bool(prev.get("ignition"))) and ignition
    elif trigger == "on_wifi":
      should_run = (not bool(prev.get("wifi"))) and wifi
    elif trigger == "daily_at":
      should_run = _should_run_daily_at(task, now)

    if not should_run:
      continue

    action = task.get("action", "")
    if action in ("read_tune_snapshot", "snapshot_tune") and driving:
      task["last_result"] = "skipped: driving"
      changed = True
      continue

    try:
      msg = await execute_action(action, task.get("payload") or {})
      task["last_run"] = now
      task["last_result"] = msg[:500]
      results.append({"id": task.get("id"), "action": action, "trigger": trigger, "result": msg[:200]})
      changed = True
    except Exception as e:
      task["last_run"] = now
      task["last_result"] = f"error: {e}"
      changed = True

  _save_state(params, {"driving": driving, "ignition": ignition, "wifi": wifi, "at": now})

  if changed:
    _save_tasks(params, tasks)
  return results
