from __future__ import annotations
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

"""
WebInterface - small HTTP control plane for the carrot module.

The CarrotPilot web UI exposes two screens:

* ``/radar`` - live visualisation of the four-corner radar + Amap blind
  spot data; and
* ``/nav_params`` - read/edit form for the carrot navigation tunings.

We provide an equivalent here using the Python standard library so the
component works on PC dev previews (where systemd / nginx is not
available) and on the device.  The server is started in a daemon thread
and can be torn down with :meth:`WebInterface.stop`.
"""

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from openpilot.sunnypilot.carrot.amap_navi import AmapNaviServ
from openpilot.sunnypilot.carrot.config import UnifiedParams

_LOG = logging.getLogger("sunnypilot.carrot.web")


_HTML_NAVPARAMS_HEAD = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>sunnypilot · Carrot 参数</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body { font-family: -apple-system, system-ui, sans-serif; margin: 16px; max-width: 720px; }
h1 { font-size: 18px; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; }
input[type=number] { width: 100%; box-sizing: border-box; }
input[type=submit] { padding: 8px 12px; }
</style>
</head>
<body>
<h1>sunnypilot · Carrot / Amap 导航参数</h1>
<p>以下参数优先从系统 Params 读取，未注册的键会回退到 nav_params.json。</p>
<form method="post" action="/nav_params_save">
<table>
<thead><tr><th>参数</th><th>值</th><th>类型</th></tr></thead>
<tbody>
"""


_HTML_NAVPARAMS_TAIL = """</tbody>
</table>
<p><input type="submit" value="保存"></p>
</form>
</body>
</html>
"""


_HTML_RADAR_HEAD = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>sunnypilot · 雷达视图</title>
<style>
body { font-family: -apple-system, system-ui, sans-serif; margin: 16px; }
.b { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.card { border: 1px solid #ddd; padding: 10px; border-radius: 6px; }
.t { font-weight: 600; margin-bottom: 6px; }
.ok { color: #2c7; }
.warn { color: #d33; }
</style>
</head>
<body>
<h1>四角雷达 + Amap 盲区</h1>
<div class="b">
"""


_HTML_RADAR_TAIL = """</div>
<p><a href="/nav_params">导航参数</a></p>
</body>
</html>
"""


class _CarrotWebHandler(BaseHTTPRequestHandler):
  server: WebInterface

  # Quieter access log.
  def log_message(self, format, *args):  # noqa: A002 - signature is fixed
    return

  def _write(self, body: bytes, status: int = 200, content_type: str = "text/html; charset=utf-8") -> None:
    try:
      self.send_response(status)
      self.send_header("Content-Type", content_type)
      self.send_header("Cache-Control", "no-store")
      self.send_header("Content-Length", str(len(body)))
      self.end_headers()
      self.wfile.write(body)
    except (BrokenPipeError, ConnectionResetError):
      pass

  def _redirect(self, location: str) -> None:
    try:
      self.send_response(303)
      self.send_header("Location", location)
      self.end_headers()
    except (BrokenPipeError, ConnectionResetError):
      pass

  def do_GET(self) -> None:
    parsed = urlparse(self.path)
    path = parsed.path

    if path == "/" or path == "/nav_params":
      self._write(self.server.render_nav_params_page())
    elif path == "/radar":
      self._write(self.server.render_radar_page())
    elif path == "/radar_data":
      body = json.dumps(self.server.snapshot_radar_data()).encode("utf-8")
      self._write(body, content_type="application/json; charset=utf-8")
    elif path == "/nav_params_data":
      body = json.dumps(self.server.snapshot_nav_params()).encode("utf-8")
      self._write(body, content_type="application/json; charset=utf-8")
    elif path == "/health":
      self._write(b"ok", content_type="text/plain; charset=utf-8")
    else:
      self._write(b"<h1>404</h1>", status=404)

  def do_POST(self) -> None:
    parsed = urlparse(self.path)
    if parsed.path == "/nav_params_save":
      length = int(self.headers.get("Content-Length", "0") or "0")
      body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
      self.server.apply_form_update(parse_qs(body))
      self._redirect("/nav_params")
      return
    self._write(b"<h1>404</h1>", status=404)


class WebInterface:
  """HTTP control plane for the carrot module.

  The class is intentionally self-contained: the carrot module
  (``CarrotManager``) holds a reference and starts the server during
  initialization.  ``stop()`` is idempotent and safe to call from any
  thread.
  """

  DEFAULT_PORT = 8088

  def __init__(self, amap_navi: AmapNaviServ, params: UnifiedParams | None = None,
               port: int = DEFAULT_PORT) -> None:
    self._amap_navi = amap_navi
    self._params = params or UnifiedParams()
    self._port = port
    self._server: ThreadingHTTPServer | None = None
    self._thread: threading.Thread | None = None
    self._lock = threading.Lock()

  # ---- lifecycle -------------------------------------------------------- #

  def start(self) -> None:
    with self._lock:
      if self._server is not None:
        return
      try:
        handler_cls = type(
          "_BoundCarrotWebHandler",
          (_CarrotWebHandler,),
          {"server": self},
        )
        server = ThreadingHTTPServer(("0.0.0.0", self._port), handler_cls)
      except OSError as exc:
        _LOG.warning("web interface failed to bind port %s: %s", self._port, exc)
        return
      self._server = server
      thread = threading.Thread(
        target=server.serve_forever, name="carrot-web", daemon=True,
      )
      self._thread = thread
      thread.start()
      _LOG.info("carrot web interface listening on port %s", self._port)

  def stop(self) -> None:
    with self._lock:
      if self._server is None:
        return
      try:
        self._server.shutdown()
        self._server.server_close()
      except Exception:
        pass
      self._server = None
      self._thread = None

  # ---- rendering -------------------------------------------------------- #

  def render_nav_params_page(self) -> bytes:
    rows: list[str] = []
    for key in sorted(self._params.keys()):
      value = self._params.get(key, "")
      kind = self._infer_kind(key, value)
      rows.append(self._render_row(key, value, kind))
    body = _HTML_NAVPARAMS_HEAD + "\n".join(rows) + _HTML_NAVPARAMS_TAIL
    return body.encode("utf-8")

  def _render_row(self, key: str, value: Any, kind: str) -> str:
    name = f'p[{key}]'
    safe_key = key.replace('"', "&quot;")
    if kind == "bool":
      checked = " checked" if int(value or 0) else ""
      return f'<tr><td>{safe_key}</td><td><input type="checkbox" name="{name}"{checked} value="1"></td><td>bool</td></tr>'
    if kind == "float":
      return f'<tr><td>{safe_key}</td><td><input type="number" step="0.01" name="{name}" value="{value}"></td><td>float</td></tr>'
    return f'<tr><td>{safe_key}</td><td><input type="number" step="1" name="{name}" value="{value}"></td><td>int</td></tr>'

  def _infer_kind(self, key: str, value: Any) -> str:
    if isinstance(value, bool) or key.endswith("Enabled"):
      return "bool"
    if isinstance(value, float):
      return "float"
    return "int"

  def render_radar_page(self) -> bytes:
    sd = self._amap_navi.shared_data
    cards = [
      self._card("左前", sd.camera_left, sd.lidar_left, sd.lf_drel),
      self._card("右前", sd.camera_right, sd.lidar_right, sd.rf_drel),
      self._card("左后", sd.lidar_car_left_blind, sd.lidar_left_blind, sd.lb_drel),
      self._card("右后", sd.lidar_car_right_blind, sd.lidar_right_blind, sd.rb_drel),
    ]
    return (_HTML_RADAR_HEAD + "".join(cards) + _HTML_RADAR_TAIL).encode("utf-8")

  def _card(self, name: str, cam: bool, lidar: bool, samples: dict) -> str:
    state_cls = "warn" if (cam or lidar) else "ok"
    state = "检测到盲区" if (cam or lidar) else "正常"
    sample_count = len(samples)
    return (
      f'<div class="card"><div class="t">{name}</div>' +
      f'<div>摄像头: <span class="{state_cls}">{state}</span></div>' +
      f'<div>激光雷达: {lidar}</div>' +
      f'<div>距离样本: {sample_count}</div></div>'
    )

  # ---- JSON snapshots --------------------------------------------------- #

  def snapshot_radar_data(self) -> dict[str, Any]:
    sd = self._amap_navi.shared_data
    return {
      "left_blind": sd.left_blind,
      "right_blind": sd.right_blind,
      "lidar_l": sd.lidar_left,
      "lidar_r": sd.lidar_right,
      "camera_l": sd.camera_left,
      "camera_r": sd.camera_right,
      "lf_drel": dict(sd.lf_drel),
      "lb_drel": dict(sd.lb_drel),
      "rf_drel": dict(sd.rf_drel),
      "rb_drel": dict(sd.rb_drel),
      "lf_vrel": sd.lf_vrel,
      "lb_vrel": sd.lb_vrel,
      "rf_vrel": sd.rf_vrel,
      "rb_vrel": sd.rb_vrel,
      "op_blocked": sd.op_blocked,
      "road_blocked": sd.road_blocked,
      "ext_blinker": sd.ext_blinker,
    }

  def snapshot_nav_params(self) -> dict[str, Any]:
    return {key: self._params.get(key, "") for key in sorted(self._params.keys())}

  # ---- form handling ---------------------------------------------------- #

  def apply_form_update(self, form: dict[str, list[str]]) -> None:
    for raw_key, values in form.items():
      if not raw_key.startswith("p["):
        continue
      key = raw_key[2:-1]
      if not values:
        continue
      value = values[0]
      if value in ("0", "1") and self._infer_kind(key, self._params.get(key, "")) == "bool":
        self._params.put_bool(key, value == "1")
      else:
        try:
          if "." in value:
            self._params.put_float(key, float(value))
          else:
            self._params.put_int(key, int(value))
        except ValueError:
          continue
