"""G7 subagent lineage tree, reconstructable from SUBAGENT_START/END events."""
from __future__ import annotations
from typing import Any


class SubagentLineage:
  """In-memory directed tree of subagent task parent/child relationships.

  ``add_edge`` records a parent->child delegation with run metadata. The same
  tree can be rebuilt from an event stream via :meth:`rebuild_from_events`
  (SUBAGENT_START carrying child/parent ids, SUBAGENT_END carrying the run id).
  """

  def __init__(self) -> None:
    self._children: dict[str, list[dict[str, Any]]] = {}
    self._edges: dict[str, dict[str, Any]] = {}  # child_task -> edge meta
    self._parent_of: dict[str, str] = {}
    self._nodes: set[str] = set()

  def add_edge(self, parent_task: str, child_task: str, run_id: str, depth: int, origin: str) -> None:
    edge = {"parentTask": parent_task, "childTask": child_task, "runId": run_id,
            "depth": depth, "origin": origin}
    self._edges[child_task] = edge
    self._nodes.add(child_task)
    if not parent_task or parent_task == child_task:
      # No parent => root. Track it but don't claim a parent edge.
      self._nodes.add(child_task)
      self._parent_of.pop(child_task, None)
      return
    self._nodes.add(parent_task)
    self._parent_of[child_task] = parent_task
    self._children.setdefault(parent_task, []).append(edge)

  def roots(self) -> list[str]:
    return sorted(t for t in self._nodes if t not in self._parent_of)

  def children(self, parent_task: str) -> list[dict[str, Any]]:
    return list(self._children.get(parent_task, []))

  def all_edges(self) -> dict[str, dict[str, Any]]:
    return dict(self._edges)

  def parent(self, task_id: str) -> dict[str, Any] | None:
    return self._edges.get(task_id)

  def rebuild_from_events(self, events: list[dict[str, Any]]) -> None:
    self._children.clear()
    self._edges.clear()
    self._parent_of.clear()
    self._nodes.clear()
    starts: dict[str, dict[str, Any]] = {}
    for event in events:
      if not isinstance(event, dict):
        continue
      ev_type = event.get("type") or event.get("event_type")
      data = event.get("data") or {}
      if ev_type in ("SUBAGENT_START", "subagent/start"):
        starts[data.get("childTask") or data.get("taskId") or ""] = data
      elif ev_type in ("SUBAGENT_END", "subagent/end"):
        child = data.get("childTask") or data.get("taskId") or ""
        start = starts.get(child, {})
        self.add_edge(
          parent_task=str(start.get("parentTask") or data.get("parentTask") or ""),
          child_task=str(child),
          run_id=str(data.get("runId") or start.get("runId") or ""),
          depth=int(start.get("depth") or data.get("depth") or 0),
          origin=str(start.get("origin") or data.get("origin") or ""),
        )
