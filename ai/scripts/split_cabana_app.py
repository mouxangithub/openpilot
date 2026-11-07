#!/usr/bin/env python3
"""Mechanical split of cabana app_monolith into submodules."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "services" / "cabana" / "app_monolith.py.bak"
OUT = ROOT / "services" / "cabana"

SECTIONS: list[tuple[str, int, int]] = [
  ("car_params.py", 70, 201),
  ("dbc.py", 203, 517),
  ("live.py", 519, 586),
  ("replay.py", 589, 1141),
  ("handlers.py", 1144, 1275),
  ("replay_ws.py", 1296, 1691),
  ("ai_explain.py", 1694, 2288),
]

DEPS = '''\
"""Shared imports for Cabana submodules."""
from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import os
import re
import subprocess
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from aiohttp import web

from ai.services.cabana.replay_util import (
  REPLAY_SNAPSHOT_INTERVAL,
  build_replay_snapshots as _build_replay_snapshots,
  compact_can_batch as _compact_can_batch,
  latest_frames_at_rel as _latest_frames_at_rel,
)

from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog

try:
  from cereal import messaging
except ImportError:
  messaging = None  # type: ignore

try:
  from opendbc.can.dbc import DBC
  from opendbc.car.values import PLATFORMS
except ImportError:
  DBC = None  # type: ignore
  PLATFORMS = {}  # type: ignore

try:
  from opendbc import DBC_PATH, get_generated_dbcs
except ImportError:
  DBC_PATH = ""  # type: ignore
  def get_generated_dbcs() -> dict[str, str]:  # type: ignore
    return {}

try:
  from openpilot.tools.lib.logreader import LogReader
except ImportError:
  LogReader = None  # type: ignore
'''

FRAME = '''\
"""CAN frame helpers."""
from __future__ import annotations
from typing import Any


def can_frame_to_dict(cf, mono_time: float | None = None) -> dict[str, Any]:
  return {
    "address": int(cf.address),
    "bus": int(cf.src),
    "data": cf.dat.hex(),
    "time": mono_time if mono_time is not None else 0.0,
  }


# Legacy alias
_can_frame_to_dict = can_frame_to_dict
'''

HTTP = '''\
"""HTTP response helpers."""
from __future__ import annotations
import json
from typing import Any
from aiohttp import web


def json_response(data: Any, status: int = 200) -> web.Response:
  return web.Response(
    text=json.dumps(data, ensure_ascii=False, default=str),
    status=status,
    content_type="application/json",
  )


_json_response = json_response
'''

ROUTES = '''\
"""Cabana route registration."""
from __future__ import annotations
from pathlib import Path
from aiohttp import web

from ai.services.cabana.handlers import (
  api_analyze,
  api_car,
  api_dbc,
  api_dbcs,
  api_explain_batch,
  api_explain_cache,
  api_explain_signal,
  api_route_file,
  api_route_media,
  api_route_summary,
  api_route_thumbnail,
  api_routes,
)
from ai.services.cabana.live import ws_live
from ai.services.cabana.replay_ws import ws_offline


def register_routes(app: web.Application, static_root: Path) -> None:
  """Register Cabana API routes (UI is embedded in op助手 main page)."""

  async def _cabana_redirect(_request: web.Request) -> web.HTTPFound:
    return web.HTTPFound(location="/?cabana=1")

  app.router.add_get("/cabana", _cabana_redirect)
  app.router.add_get("/cabana/", _cabana_redirect)

  app.router.add_get("/api/cabana/car", api_car)
  app.router.add_get("/api/cabana/dbcs", api_dbcs)
  app.router.add_get("/api/cabana/dbc/{name}", api_dbc)
  app.router.add_get("/api/cabana/routes", api_routes)
  app.router.add_get("/api/cabana/route/{name}/media", api_route_media)
  app.router.add_get("/api/cabana/route/{name}/thumbnail", api_route_thumbnail)
  app.router.add_get("/api/cabana/route/{name}/summary", api_route_summary)
  app.router.add_get("/api/cabana/route/{name}/file", api_route_file)
  app.router.add_get("/api/cabana/ws", ws_live)
  app.router.add_get("/api/cabana/offline/ws", ws_offline)
  app.router.add_post("/api/cabana/analyze", api_analyze)
  app.router.add_post("/api/cabana/explain", api_explain_signal)
  app.router.add_post("/api/cabana/explain_batch", api_explain_batch)
  app.router.add_get("/api/cabana/explain_cache", api_explain_cache)
'''

APP_FACADE = '''\
"""Cabana backend facade — re-exports for tools and server registration."""

from ai.services.cabana.routes import register_routes
from ai.services.cabana.dbc import warm_dbc_catalog
from ai.services.cabana.live import LIVE_CAN, LiveCanBroadcaster, ws_live
from ai.services.cabana.ai_explain import cabana_analyze_tool, cabana_explain_signal_tool
from ai.services.cabana.replay import (
  _find_qlogs,
  _find_rlogs,
  _get_routes_dir,
  _list_dbc_names,
  _list_route_media,
  _list_routes,
  _load_dbc_content,
  _parse_dbc_signals,
  _replay_log_paths,
  _route_date_label,
  _route_dir,
)

# Public alias used by tools
_pick_can_log_paths = _replay_log_paths

__all__ = [
  "register_routes",
  "warm_dbc_catalog",
  "LIVE_CAN",
  "LiveCanBroadcaster",
  "cabana_analyze_tool",
  "cabana_explain_signal_tool",
]
'''

EXTRA_IMPORTS: dict[str, str] = {
  "car_params.py": "from ai.services.cabana.deps import *\n",
  "dbc.py": (
    "from ai.services.cabana.deps import *\n"
    "from ai.services.cabana.frame import can_frame_to_dict as _can_frame_to_dict\n"
  ),
  "live.py": (
    "from ai.services.cabana.deps import *\n"
    "from ai.services.cabana.frame import can_frame_to_dict as _can_frame_to_dict\n\n"
  ),
  "replay.py": (
    "from ai.services.cabana.deps import *\n"
    "from ai.services.cabana.frame import can_frame_to_dict as _can_frame_to_dict\n"
    "from ai.services.cabana.car_params import _resolve_car_params\n"
    "from ai.services.cabana.dbc import _suggest_dbc_for_car\n\n"
  ),
  "handlers.py": (
    "from ai.services.cabana.deps import *\n"
    "from ai.services.cabana.http import json_response as _json_response\n"
    "from ai.services.cabana.car_params import _resolve_car_params\n"
    "from ai.services.cabana.dbc import (\n"
    "  _build_dbc_catalog,\n"
    "  _dbc_catalog_cache,\n"
    "  _get_dbc_dict,\n"
    "  _load_dbc_content,\n"
    "  _parse_dbc_signals,\n"
    "  _pick_preferred_dbc,\n"
    "  _quick_dbc_catalog,\n"
    "  _suggest_dbc_for_fingerprint,\n"
    "  warm_dbc_catalog,\n"
    ")\n"
    "from ai.services.cabana.replay import (\n"
    "  _list_route_media,\n"
    "  _list_routes,\n"
    "  _media_payload,\n"
    "  _qcamera_thumbnail_at_time,\n"
    "  _route_dir,\n"
    ")\n\n"
  ),
  "replay_ws.py": (
    "from ai.services.cabana.deps import *\n"
    "from ai.services.cabana.frame import can_frame_to_dict as _can_frame_to_dict\n"
    "from ai.services.cabana.replay import (\n"
    "  CACHE_VERSION,\n"
    "  MAX_REPLAY_FRAMES,\n"
    "  QLOG_CACHE_MAX_FRAMES,\n"
    "  REPLAY_FRAME_QUEUE_SIZE,\n"
    "  REPLAY_START_BUFFER,\n"
    "  REPLAY_STREAM_BATCH,\n"
    "  _cabana_cache_dir,\n"
    "  _collect_can_frames,\n"
    "  _find_qlogs,\n"
    "  _find_rlogs,\n"
    "  _get_routes_dir,\n"
    "  _iter_can_batches,\n"
    "  _load_route_cache,\n"
    "  _replay_log_paths,\n"
    "  _route_cache_file,\n"
    "  _save_route_cache,\n"
    "  _threadsafe_queue_put,\n"
    ")\n"
    "from ai.services.cabana.dbc import _parse_dbc_signals, _suggest_dbc_for_car\n"
    "from ai.services.cabana.car_params import _resolve_car_params\n\n"
  ),
  "ai_explain.py": (
    "from ai.services.cabana.deps import *\n"
    "from ai.services.cabana.http import json_response as _json_response\n"
    "from ai.services.cabana.dbc import _parse_dbc_signals\n\n"
  ),
}


def main() -> int:
  if not SRC.is_file():
    print(f"missing {SRC}")
    return 1
  lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)
  (OUT / "deps.py").write_text(DEPS, encoding="utf-8")
  (OUT / "frame.py").write_text(FRAME, encoding="utf-8")
  (OUT / "http.py").write_text(HTTP, encoding="utf-8")
  (OUT / "routes.py").write_text(ROUTES, encoding="utf-8")

  for name, start, end in SECTIONS:
    body = "".join(lines[start - 1 : end])
    header = EXTRA_IMPORTS.get(name, "from ai.services.cabana.deps import *\n\n")
    (OUT / name).write_text(f'"""Cabana {name.replace(".py", "")} module."""\n{header}{body}', encoding="utf-8")
    print(f"wrote {name}")

  # ws_live lives after handlers in monolith — append to live.py
  ws_live_body = "".join(lines[1277:1293])
  live_path = OUT / "live.py"
  live_path.write_text(live_path.read_text(encoding="utf-8") + "\n" + ws_live_body, encoding="utf-8")
  print("appended ws_live to live.py")

  (OUT / "app.py").write_text(APP_FACADE, encoding="utf-8")
  print("wrote app.py facade")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
