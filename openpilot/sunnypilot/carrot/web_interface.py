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
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from collections.abc import Callable

from openpilot.sunnypilot.carrot.amap_navi import AmapNaviServ
from openpilot.sunnypilot.carrot.config import UnifiedParams
from openpilot.sunnypilot.carrot.server.services.params import _USB_PORT_KEYS, _enforce_usb_port
from openpilot.common.params import Params
from openpilot.sunnypilot.models.mirror import (DEFAULT_HF_MIRROR, DIRECT_VALUE, GITHUB_PROXY_PARAM, HF_MIRROR_PARAM,
                                                PROXY_DIRECT_VALUE, describe_github_proxy, describe_hf_mirror,
                                                get_hf_mirror_base, normalize_base_url)

_LOG = logging.getLogger("sunnypilot.carrot.web")


def html_escape(value: str, attribute: bool = False) -> str:
  """Minimal escaping for interpolating untrusted strings into the hand-rolled HTML."""
  value = (value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
  if attribute:
    value = value.replace('"', "&quot;").replace("'", "&#x27;")
  return value


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
<p><a href="/models">模型下载镜像设置</a> · <a href="/radar">雷达视图</a></p>
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


_HTML_MODELS_HEAD = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>sunnypilot · 模型下载镜像</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body { font-family: -apple-system, system-ui, sans-serif; margin: 16px; max-width: 720px; }
h1 { font-size: 18px; }
p, li { font-size: 14px; line-height: 1.6; }
label { display: block; margin-top: 14px; font-weight: 600; }
input[type=text] { width: 100%; box-sizing: border-box; padding: 8px; margin-top: 4px; }
.hint { color: #666; font-weight: 400; font-size: 13px; }
.eff { background: #f6f6f6; border: 1px solid #ddd; border-radius: 6px; padding: 8px 10px; font-size: 13px; }
.ok { color: #2c7; } .err { color: #d33; }
input[type=submit] { padding: 8px 14px; margin-top: 14px; }
</style>
</head>
<body>
<h1>模型下载镜像设置</h1>
__MESSAGE__
<div class="eff">当前生效：模型文件走 <b>__MIRROR_EFF__</b>；模型列表走 <b>__CATALOG_EFF__</b></div>
<form method="post" action="/models_save">
<label>模型文件镜像站（huggingface.co 替换前缀）
  <input type="text" name="mirror_url" value="__MIRROR_VALUE__" placeholder="留空 = 默认 __DEFAULT_MIRROR__；填 off = 直连">
</label>
<p class="hint">大模型与小模型的文件都托管在 huggingface.co。此处填一个镜像站基础地址（如 https://hf-mirror.com），下载时会替换
https://huggingface.co 前缀；填 <b>off</b> 表示直连。文件带 sha256 校验，镜像不会破坏完整性。更改对下一次下载生效。</p>
<label>模型列表来源（raw.githubusercontent.com）
  <input type="text" name="github_proxy" value="__PROXY_VALUE__" placeholder="留空 = 自动（直连失败后自动切换 CDN）；填 direct = 仅直连；或填代理前缀">
</label>
<p class="hint">模型目录 JSON 托管在 raw.githubusercontent.com。「自动」会在直连失败后改用 jsDelivr CDN 同一文件（目录带 ed25519 签名校验）。
也可填 ghproxy 类代理前缀（如 https://gh-proxy.com），将始终以 前缀 + 完整URL 的形式请求。改完请回车机「Refresh Model List」。</p>
<p><input type="submit" value="保存"></p>
</form>
<p><a href="/nav_params">返回导航参数</a></p>
</body>
</html>
"""


class _CarrotHTTPServer(ThreadingHTTPServer):
  """ThreadingHTTPServer that carries the WebInterface instance.

  ``BaseRequestHandler.__init__`` assigns ``self.server = <raw server>``
  on every handler instance, shadowing any class attribute, so the
  interface must be exposed through a dedicated attribute.
  """

  def __init__(self, address: tuple[str, int], handler_cls, interface: "WebInterface") -> None:
    super().__init__(address, handler_cls)
    self.interface = interface


class _CarrotWebHandler(BaseHTTPRequestHandler):
  interface: "WebInterface"

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
      self._write(self.server.interface.render_nav_params_page())
    elif path == "/radar":
      self._write(self.server.interface.render_radar_page())
    elif path == "/radar_data":
      body = json.dumps(self.server.interface.snapshot_radar_data()).encode("utf-8")
      self._write(body, content_type="application/json; charset=utf-8")
    elif path == "/nav_params_data":
      body = json.dumps(self.server.interface.snapshot_nav_params()).encode("utf-8")
      self._write(body, content_type="application/json; charset=utf-8")
    elif path == "/models":
      self._write(self.server.interface.render_models_page(parse_qs(parsed.query)))
    elif path == "/health":
      self._write(b"ok", content_type="text/plain; charset=utf-8")
    else:
      self._write(b"<h1>404</h1>", status=404)

  def do_POST(self) -> None:
    parsed = urlparse(self.path)
    if parsed.path == "/nav_params_save":
      length = int(self.headers.get("Content-Length", "0") or "0")
      body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
      self.server.interface.apply_form_update(parse_qs(body))
      self._redirect("/nav_params")
      return
    if parsed.path == "/models_save":
      length = int(self.headers.get("Content-Length", "0") or "0")
      body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
      ok, message = self.server.interface.apply_models_form(parse_qs(body))
      self._redirect(f"/models?saved={'1' if ok else '0'}&msg={message}")
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
               port: int = DEFAULT_PORT,
               radar_source: Callable[[], dict[str, Any]] | None = None) -> None:
    self._amap_navi = amap_navi
    self._params = params or UnifiedParams()
    self._models_params: Params | None = None
    self._port = port
    self._radar_source = radar_source
    self._server: ThreadingHTTPServer | None = None
    self._thread: threading.Thread | None = None
    self._lock = threading.Lock()

  # ---- lifecycle -------------------------------------------------------- #

  def start(self) -> None:
    with self._lock:
      if self._server is not None:
        return
      try:
        server = _CarrotHTTPServer(("0.0.0.0", self._port), _CarrotWebHandler, self)
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
    data: dict[str, Any] = {
      "timestamp": time.time(),
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
    if self._radar_source is not None:
      try:
        radar = self._radar_source()
        data["points"] = radar.get("points", [])
        data["tracks"] = radar.get("tracks", [])
        data["leads"] = radar.get("leads", [])
        data["radar_timestamp"] = radar.get("timestamp", data["timestamp"])
      except Exception:
        # Fall back to the four-corner snapshot if the source errors out.
        pass
    return data

  def snapshot_nav_params(self) -> dict[str, Any]:
    return {key: self._params.get(key, "") for key in sorted(self._params.keys())}

  # ---- form handling ---------------------------------------------------- #

  def apply_form_update(self, form: dict[str, list[str]]) -> None:
    touched_usb_port = False
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
      touched_usb_port = touched_usb_port or key in _USB_PORT_KEYS

    if touched_usb_port:
      _enforce_usb_port()

  # ---- model download mirror ------------------------------------------- #

  def render_models_page(self, query: dict[str, list[str]] | None = None) -> bytes:
    self._init_models_params()
    params = self._models_params
    mirror_raw = params.get(HF_MIRROR_PARAM) or ""
    proxy_raw = params.get(GITHUB_PROXY_PARAM) or ""
    message = ""
    if query:
      if query.get("saved", [""])[0] == "1":
        from urllib.parse import unquote_plus
        message = f'<p class="ok">已保存：{html_escape(unquote_plus(query.get("msg", [""])[0]))}</p>'
      elif query.get("saved", [""])[0] == "0":
        from urllib.parse import unquote_plus
        message = f'<p class="err">保存失败：{html_escape(unquote_plus(query.get("msg", [""])[0]))}</p>'
    html = (_HTML_MODELS_HEAD
            .replace("__MESSAGE__", message)
            .replace("__MIRROR_EFF__", html_escape(describe_hf_mirror(params)))
            .replace("__CATALOG_EFF__", html_escape(describe_github_proxy(params)))
            .replace("__MIRROR_VALUE__", html_escape(mirror_raw, attribute=True))
            .replace("__PROXY_VALUE__", html_escape(proxy_raw, attribute=True))
            .replace("__DEFAULT_MIRROR__", DEFAULT_HF_MIRROR))
    return html.encode("utf-8")

  def apply_models_form(self, form: dict[str, list[str]]) -> tuple[bool, str]:
    """Validates and stores the two mirror settings. Returns (ok, urlencoded_message)."""
    from urllib.parse import quote_plus

    self._init_models_params()
    params = self._models_params
    mirror_raw = (form.get("mirror_url", [""])[0] or "").strip()
    proxy_raw = (form.get("github_proxy", [""])[0] or "").strip()

    if mirror_raw and mirror_raw.lower() != DIRECT_VALUE:
      if normalize_base_url(mirror_raw) is None:
        return False, quote_plus("模型镜像站必须是 http(s) 地址（或 off / 留空）")
    if proxy_raw and proxy_raw.lower() != PROXY_DIRECT_VALUE:
      if normalize_base_url(proxy_raw) is None:
        return False, quote_plus("模型列表代理必须是 http(s) 地址（或 direct / 留空）")

    params.put(HF_MIRROR_PARAM, mirror_raw)
    params.put(GITHUB_PROXY_PARAM, proxy_raw)
    mirror_effective = get_hf_mirror_base(params) or "huggingface.co（直连）"
    return True, quote_plus(f"模型文件走 {mirror_effective}，模型列表走 {describe_github_proxy(params)}")

  def _init_models_params(self) -> None:
    if self._models_params is None:
      self._models_params = Params()
