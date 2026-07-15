# Copyright (c) 2026, Rick Lan
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, and/or sublicense,
# for non-commercial purposes only, subject to the following conditions:
#
# - The above copyright notice and this permission notice shall be included in
#   all copies or substantial portions of the Software.
# - Commercial use (e.g. use in a product, service, or activity intended to
#   generate revenue) is prohibited without explicit written permission from
#   the copyright holder.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""HTTP plumbing: a minimal request/response shim over the stdlib http.server,
the threaded server, and the request handler (routing, static + media serving
with Range support, and the SSE stream writer).

The endpoint functions live in handlers.py; the route table is passed into the
server at construction, so this module has no dependency on the handlers (keeps
the import graph acyclic)."""

import json
import mimetypes
import os
import re
import time
from functools import wraps
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, unquote, urlparse

from . import config
from .config import logger


# --- Minimal HTTP shim ---
# A thin request/response layer so the endpoint handlers read like framework
# handlers (request.query / request.match_info / request.json()) without pulling
# in a web framework. Responses are plain data objects the request handler
# serializes; HTTPError carries an explicit status + reason.
class HTTPError(Exception):
  """Raised by a handler to abort with a specific HTTP status (replaces the
  aiohttp web.HTTP* exceptions)."""

  def __init__(self, status, reason=""):
    self.status = status
    self.reason = reason
    super().__init__(reason)


class Response:
  """A buffered response: body bytes + status + content type (+ extra headers)."""

  def __init__(self, body=b"", status=200, content_type="application/json", headers=None):
    self.body = body.encode("utf-8") if isinstance(body, str) else body
    self.status = status
    self.content_type = content_type
    self.headers = headers or {}


def json_response(data, status=200):
  return Response(json.dumps(data).encode("utf-8"), status, "application/json")


def text_response(text, status=200, content_type="text/plain"):
  return Response(text, status, content_type)


class Request:
  """Wraps the active BaseHTTPRequestHandler for the slice of API the handlers
  use: path, parsed query, route match_info, JSON body, and app state."""

  def __init__(self, handler, method, path, query, match_info):
    self._handler = handler
    self.method = method
    self.path = path
    self.query = query
    self.match_info = match_info
    self.app = handler.server.app_state

  def json(self):
    length = int(self._handler.headers.get('Content-Length', 0) or 0)
    if length <= 0:
      return {}
    raw = self._handler.rfile.read(length)
    return json.loads(raw.decode('utf-8'))


def api_handler(func):
  """Decorator for API handlers with consistent error handling."""

  @wraps(func)
  def wrapper(request):
    try:
      return func(request)
    except HTTPError:
      raise
    except Exception as e:
      logger.error(f"{func.__name__} error: {e}", exc_info=True)
      return json_response({'error': str(e)}, status=500)

  return wrapper


def get_safe_path(requested_path):
  """Ensures the requested path is within DEFAULT_DIR."""
  combined_path = os.path.join(config.DEFAULT_DIR, requested_path.lstrip('/'))
  safe_path = os.path.realpath(combined_path)
  if os.path.commonpath((safe_path, config.DEFAULT_DIR)) == config.DEFAULT_DIR:
    return safe_path
  return None


def route_regex(path):
  """Compile a route pattern with {name} placeholders into an anchored regex."""
  parts = re.split(r'\{([^}]+)\}', path)
  rx = ''
  for i, part in enumerate(parts):
    rx += re.escape(part) if i % 2 == 0 else f'(?P<{part}>[^/]+)'
  return re.compile('^' + rx + '$')


_NO_CACHE_SUFFIXES = ('.html', '.js', '.css')
_STREAM_IDLE_PING = 750  # ~15s at the 20ms idle poll: comment ping keeps the SSE alive


class DashyRequestHandler(BaseHTTPRequestHandler):
  """Routes API requests to handler functions and serves static assets +
  drive-log media (with Range support for video seeking)."""

  protocol_version = "HTTP/1.1"
  server_version = "dashy"

  def log_message(self, fmt, *args):
    logger.debug("%s - %s", self.address_string(), fmt % args)

  def do_GET(self):
    self._dispatch('GET')

  def do_POST(self):
    self._dispatch('POST')

  # --- dispatch ---
  def _dispatch(self, method):
    parsed = urlparse(self.path)
    path = parsed.path
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))

    if method == 'GET' and path == '/api/stream':
      self._serve_sse()
      return

    for m, rx, fn in self.server.routes:
      if m != method:
        continue
      match = rx.match(path)
      if not match:
        continue
      request = Request(self, method, path, query, match.groupdict())
      try:
        resp = fn(request)
      except HTTPError as e:
        self._send_error(e.status, e.reason)
        return
      self._write_response(resp, path)
      return

    if method == 'GET':
      self._serve_get_static(path)
    else:
      self._send_error(404, 'Not Found')

  # --- response writers ---
  def _apply_no_cache(self, path):
    if path == '/' or path.lower().endswith(_NO_CACHE_SUFFIXES):
      self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
      self.send_header('Pragma', 'no-cache')
      self.send_header('Expires', '0')

  def _write_response(self, resp, path):
    self.send_response(resp.status)
    self.send_header('Content-Type', resp.content_type)
    self.send_header('Content-Length', str(len(resp.body)))
    for k, v in resp.headers.items():
      self.send_header(k, v)
    self._apply_no_cache(path)
    self.end_headers()
    if self.command != 'HEAD':
      self._safe_write(resp.body)

  def _send_error(self, status, reason):
    body = json.dumps({'error': reason or ''}).encode()
    # Close the connection after an error so an unread request body can't
    # desync a keep-alive connection.
    self.close_connection = True
    self.send_response(status)
    self.send_header('Content-Type', 'application/json')
    self.send_header('Content-Length', str(len(body)))
    self.end_headers()
    self._safe_write(body)

  def _safe_write(self, data):
    try:
      self.wfile.write(data)
    except (BrokenPipeError, ConnectionResetError, OSError):
      self.close_connection = True

  # --- static + media ---
  def _serve_get_static(self, path):
    if path.startswith('/media/') or path.startswith('/download/'):
      prefix = '/media/' if path.startswith('/media/') else '/download/'
      safe = get_safe_path(unquote(path[len(prefix) :]))
      if not safe or not os.path.isfile(safe):
        self._send_error(404, 'Not Found')
        return
      self._serve_file(safe, path)
      return

    if path == '/':
      self._serve_file(os.path.join(config.WEB_DIST_PATH, 'index.html'), path)
      return

    target = os.path.realpath(os.path.join(config.WEB_DIST_PATH, unquote(path.lstrip('/'))))
    if os.path.commonpath((target, config._WEB_DIST_REAL)) != config._WEB_DIST_REAL or not os.path.isfile(target):
      self._send_error(404, 'Not Found')
      return
    self._serve_file(target, path)

  def _serve_file(self, fullpath, path_for_cache):
    """Serve a file with Range support (needed for video seeking in the
    HLS player; aiohttp's static handler provided this for free)."""
    if not os.path.isfile(fullpath):
      self._send_error(404, 'Not Found')
      return
    ctype = mimetypes.guess_type(fullpath)[0] or 'application/octet-stream'
    size = os.path.getsize(fullpath)

    start, end, status = 0, size - 1, 200
    rng = self.headers.get('Range')
    if rng:
      m = re.match(r'bytes=(\d*)-(\d*)$', rng.strip())
      if m and (m.group(1) or m.group(2)):
        if not m.group(1):  # suffix: last N bytes
          start = max(0, size - int(m.group(2)))
        else:
          start = int(m.group(1))
          end = int(m.group(2)) if m.group(2) else size - 1
        end = min(end, size - 1)
        if start > end or start >= size:
          self.send_response(416)
          self.send_header('Content-Range', f'bytes */{size}')
          self.send_header('Content-Length', '0')
          self.end_headers()
          return
        status = 206

    length = end - start + 1
    self.send_response(status)
    self.send_header('Content-Type', ctype)
    self.send_header('Content-Length', str(length))
    self.send_header('Accept-Ranges', 'bytes')
    if status == 206:
      self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
    self._apply_no_cache(path_for_cache)
    self.end_headers()
    if self.command == 'HEAD':
      return
    with open(fullpath, 'rb') as f:
      f.seek(start)
      remaining = length
      while remaining > 0:
        chunk = f.read(min(64 * 1024, remaining))
        if not chunk:
          break
        try:
          self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError, OSError):
          self.close_connection = True
          break
        remaining -= len(chunk)

  # --- SSE stream ---
  def _serve_sse(self):
    """Stream the latest dashyState frame as `data: <json>\\n\\n`. Runs in
    this connection's own thread (ThreadingHTTPServer), looping until the
    client drops or the server shuts down."""
    app = self.server.app_state
    self.send_response(200)
    self.send_header('Content-Type', 'text/event-stream')
    self.send_header('Cache-Control', 'no-cache')
    self.send_header('X-Accel-Buffering', 'no')  # don't let a proxy buffer the stream
    self.send_header('Connection', 'keep-alive')
    self.end_headers()
    logger.info("SSE client connected")
    last, idle = -1, 0
    try:
      while not self.server.stop_event.is_set():
        seq = app['stream_seq']
        if seq != last and app['stream_latest'] is not None:
          last = seq
          self.wfile.write(b"data: " + app['stream_latest'] + b"\n\n")
          self.wfile.flush()
          idle = 0
        else:
          idle += 1
          if idle >= _STREAM_IDLE_PING:
            self.wfile.write(b": ping\n\n")
            self.wfile.flush()
            idle = 0
          time.sleep(0.02)
    except (BrokenPipeError, ConnectionResetError, OSError):
      pass
    except Exception as e:
      logger.debug(f"SSE client dropped: {e}")
    finally:
      self.close_connection = True
      logger.info("SSE client disconnected")


class DashyServer(ThreadingHTTPServer):
  """Threaded HTTP server: one thread per connection so a long-lived SSE
  stream never blocks REST requests."""

  daemon_threads = True
  allow_reuse_address = True

  def __init__(self, address, app_state, stop_event, routes):
    super().__init__(address, DashyRequestHandler)
    self.app_state = app_state
    self.stop_event = stop_event
    self.routes = routes
