"""Cabana-aligned route listing for AI tools (same data as GET /api/cabana/routes)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai.services.cabana.routes_lite import list_routes_lite
from ai.system.paths import routes_dir


def list_cabana_routes(*, limit: int = 15, params: Any | None = None) -> dict[str, Any]:
  """List drive routes with qlog/rlog — matches Cabana web UI route picker."""
  rd = routes_dir()
  routes: list[dict[str, Any]]
  routes_path: str | None

  try:
    from openpilot.common.params import Params
    from ai.services.cabana.app import _get_routes_dir, _list_routes

    p = params if params is not None else Params()
    path = _get_routes_dir()
    if path is not None:
      routes = _list_routes(p)
      routes_path = str(path)
    else:
      routes, routes_path = list_routes_lite()
  except Exception:
    routes, routes_path = list_routes_lite()

  if routes_path is None or not Path(routes_path).is_dir():
    return {
      "ok": False,
      "routes": [],
      "routes_dir": rd,
      "count": 0,
      "error": "Routes directory not found",
      "hint": (
        "On comma device routes live under /data/media/0/realdata. "
        "On PC set OPENPILOT_ROUTES_DIR. Record a drive or copy route folders first."
      ),
    }

  capped = max(1, min(int(limit or 15), 100))
  return {
    "ok": True,
    "routes": routes[:capped],
    "routes_dir": routes_path,
    "count": len(routes),
    "hint": (
      "Each route has name, date, has_qlog/has_rlog. "
      "Next: analyze_route_summary(name), read_qlog_segment(name), or open Cabana UI (?cabana=1)."
    ),
  }
