"""G6 agent-level scheduler (at / cron / every), isolated from the existing
Web/on-offroad ``platform/scheduler.py``.

This module has no dependency on the platform scheduler. It maintains an
in-memory list of ``SchedulerJob`` and a pure-Python ``_tick`` that fire due
jobs. Tool registration is done by :func:`register_agent_scheduler_tools` into
an arbitrary handler ``dict`` so the caller decides how to route them.
"""
from __future__ import annotations

import asyncio
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ai.tools.domains.scheduler_cron import parse_cron

# Stable error code reused from ai.core.errors.
ERR_SCHEDULE_INVALID = "SCHEDULE_INVALID"


@dataclass
class SchedulerJob:
  id: str
  agent_id: str
  spec: str
  kind: str            # at | cron | every
  payload: dict[str, Any]
  enabled: bool = True
  last_run: int = 0
  next_run: int = 0

  def to_dict(self) -> dict[str, Any]:
    return {
      "id": self.id, "agentId": self.agent_id, "spec": self.spec,
      "kind": self.kind, "payload": dict(self.payload), "enabled": self.enabled,
      "lastRun": self.last_run, "nextRun": self.next_run,
    }


SpecKind = str


def _parse_spec(spec: str) -> tuple[SpecKind, Any]:
  """Return (kind, parsed). 'at HH:MM', 'cron <expr>', 'every <n><unit>'."""
  s = spec.strip()
  m = re.match(r"^at\s+(\d{1,2}):(\d{2})$", s, re.IGNORECASE)
  if m:
    return "at", (int(m.group(1)) % 24, int(m.group(2)))
  m = re.match(r"^cron\s+(.+)$", s, re.IGNORECASE)
  if m:
    expr = m.group(1).strip()
    parse_cron(expr)  # raises ValueError on bad syntax
    return "cron", expr
  m = re.match(r"^every\s+(\d+)\s*(s|m|h|d)$", s, re.IGNORECASE)
  if m:
    n = int(m.group(1))
    unit = m.group(2).lower()
    secs = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit] * n
    if secs <= 0:
      raise ValueError("interval must be positive")
    return "every", secs
  raise ValueError(f"unrecognized schedule spec: {spec!r}")


def _next_at(hhmm: tuple[int, int]) -> int:
  now = time.localtime()
  hh, mm = hhmm
  today = int(time.mktime((now.tm_year, now.tm_mon, now.tm_mday, hh, mm, 0, 0, 0, -1)))
  if today <= int(time.time()):
    return today + 86400
  return today


def _next_cron(expr: str, after: int) -> int:
  sched = parse_cron(expr)
  t = after
  for _ in range(60 * 24 * 366):
    t += 60
    lt = time.localtime(t)
    if sched.matches(lt.tm_min, lt.tm_hour, lt.tm_mday, lt.tm_mon, lt.tm_wday):
      return t
  return after + 3600


def _next(start: int, kind: str, parsed: Any) -> int:
  if kind == "at":
    return _next_at(parsed)
  if kind == "cron":
    return _next_cron(parsed, int(time.time()))
  return start + parsed  # every


class AgentScheduler:
  """In-memory agent scheduler. Ticking is driven by an external ``asyncio``
  event loop calling :meth:`_tick` or by scheduling the fire callback.
  """

  def __init__(self, params: Any = None) -> None:
    self.params = params
    self._jobs: dict[str, SchedulerJob] = {}
    self._handlers: dict[str, Callable[..., Awaitable[Any]]] = {}

  def set_handlers(self, handlers: dict[str, Callable[..., Awaitable[Any]]]) -> None:
    self._handlers = dict(handlers)

  def schedule(self, agent_id: str, spec: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
      kind, parsed = _parse_spec(spec)
    except ValueError as e:
      return {"ok": False, "error_code": ERR_SCHEDULE_INVALID, "message": str(e)}
    job = SchedulerJob(
      id=uuid.uuid4().hex,
      agent_id=agent_id,
      spec=spec,
      kind=kind,
      payload=dict(payload),
      next_run=_next(int(time.time()), kind, parsed),
    )
    self._jobs[job.id] = job
    return {"ok": True, "job": job.to_dict()}

  def cancel(self, job_id: str) -> bool:
    return self._jobs.pop(job_id, None) is not None

  def list(self, agent_id: str) -> list[dict[str, Any]]:
    return [j.to_dict() for j in self._jobs.values() if j.agent_id == agent_id]

  def due_jobs(self, now: int | None = None) -> list[SchedulerJob]:
    now = int(time.time()) if now is None else now
    return [j for j in self._jobs.values() if j.enabled and j.next_run and j.next_run <= now]

  async def _fire(self, job: SchedulerJob) -> None:
    handler = self._handlers.get("run_agent_schedule") or self._handlers.get("schedule")
    job.last_run = int(time.time())
    try:
      _, parsed = _parse_spec(job.spec)
      if job.kind == "every":
        job.next_run = int(time.time()) + parsed
      elif job.kind == "at":
        job.next_run = _next_at(parsed)
      else:
        job.next_run = _next_cron(parsed, int(time.time()))
    except ValueError:
      job.enabled = False
    if handler is None:
      return
    await handler(job)

  async def _tick(self) -> None:
    for job in self.due_jobs():
      await self._fire(job)

  async def run_forever(self, interval_seconds: float = 1.0, stop: asyncio.Event | None = None) -> None:
    while stop is None or not stop.is_set():
      await self._tick()
      await asyncio.sleep(interval_seconds)


def register_agent_scheduler_tools(handlers: dict[str, Callable[..., Awaitable[Any]]]) -> None:
  """Register at/cron/every/list_schedules/cancel_schedule tool closures."""
  scheduler = AgentScheduler()

  async def tool_at(agent_id: str, spec: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return scheduler.schedule(agent_id, f"at {spec}" if not spec.startswith("at ") else spec, payload or {})

  async def tool_cron(agent_id: str, expression: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return scheduler.schedule(agent_id, f"cron {expression}", payload or {})

  async def tool_every(agent_id: str, interval: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return scheduler.schedule(agent_id, f"every {interval}" if not interval.startswith("every ") else interval, payload or {})

  async def tool_list_schedules(agent_id: str) -> dict[str, Any]:
    return {"ok": True, "data": scheduler.list(agent_id)}

  async def tool_cancel_schedule(job_id: str) -> dict[str, Any]:
    return {"ok": scheduler.cancel(job_id)}

  handlers.update({
    "at": tool_at,
    "cron": tool_cron,
    "every": tool_every,
    "list_schedules": tool_list_schedules,
    "cancel_schedule": tool_cancel_schedule,
  })
  # Expose the runner for tests / wiring.
  handlers["_agent_scheduler"] = scheduler