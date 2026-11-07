"""Shared aiohttp runner for webuid / run_pc."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import ssl
from pathlib import Path

from aiohttp import web

from webui.server.tls_util import build_ssl_context, ensure_tls_files

log = logging.getLogger("webuid")

_TLS_RECORD_BYTE = 0x16


def build_https_redirect_location(
  request_line: str,
  headers: list[str],
  *,
  public_port: int,
) -> str:
  """Build https:// redirect target from a minimal HTTP/1.x request."""
  parts = request_line.split(" ")
  path = parts[1] if len(parts) >= 2 else "/"

  host: str | None = None
  for line in headers:
    if line.lower().startswith("host:"):
      host = line.split(":", 1)[1].strip()
      break

  if not host:
    host = "localhost"
    if public_port not in (80, 443):
      host = f"{host}:{public_port}"
  elif ":" not in host and public_port not in (80, 443):
    host = f"{host}:{public_port}"

  return f"https://{host}{path}"


def format_http_redirect_response(location: str) -> bytes:
  return (
    "HTTP/1.1 301 Moved Permanently\r\n"
    f"Location: {location}\r\n"
    "Content-Type: text/plain; charset=utf-8\r\n"
    "Content-Length: 0\r\n"
    "Connection: close\r\n\r\n"
  ).encode()


def _tls_redirect_http_enabled(value: bool | None) -> bool:
  if value is not None:
    return value
  return os.environ.get("WEBUI_TLS_REDIRECT_HTTP", "1").lower() in ("1", "true", "yes")


async def _serve_http_redirect(
  reader: asyncio.StreamReader,
  writer: asyncio.StreamWriter,
  first_byte: bytes,
  *,
  public_port: int,
) -> None:
  try:
    buf = first_byte
    while b"\r\n\r\n" not in buf and len(buf) < 8192:
      chunk = await reader.read(4096)
      if not chunk:
        break
      buf += chunk

    text = buf.decode("latin-1", errors="ignore")
    lines = text.split("\r\n")
    req_line = lines[0] if lines else ""
    location = build_https_redirect_location(req_line, lines[1:], public_port=public_port)
    writer.write(format_http_redirect_response(location))
    await writer.drain()
  finally:
    writer.close()


async def _proxy_to_backend(
  reader: asyncio.StreamReader,
  writer: asyncio.StreamWriter,
  first_byte: bytes,
  backend_port: int,
) -> None:
  try:
    backend_reader, backend_writer = await asyncio.open_connection("127.0.0.1", backend_port)
    backend_writer.write(first_byte)
    await backend_writer.drain()

    async def forward(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
      try:
        while True:
          data = await src.read(65536)
          if not data:
            break
          dst.write(data)
          await dst.drain()
      except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
        pass
      finally:
        try:
          dst.close()
        except Exception:
          pass

    await asyncio.gather(
      forward(reader, backend_writer),
      forward(backend_reader, writer),
      return_exceptions=True,
    )
  finally:
    writer.close()


async def _mux_client_handler(
  reader: asyncio.StreamReader,
  writer: asyncio.StreamWriter,
  *,
  backend_port: int,
  public_port: int,
) -> None:
  try:
    first = await reader.read(1)
    if not first:
      return
    if first[0] == _TLS_RECORD_BYTE:
      await _proxy_to_backend(reader, writer, first, backend_port)
    else:
      await _serve_http_redirect(reader, writer, first, public_port=public_port)
  finally:
    try:
      writer.close()
    except Exception:
      pass


async def _run_tls_with_http_redirect(
  app: web.Application,
  *,
  host: str,
  port: int,
  ssl_context: ssl.SSLContext,
) -> None:
  runner = web.AppRunner(app)
  await runner.setup()
  site = web.TCPSite(runner, "127.0.0.1", 0, ssl_context=ssl_context, reuse_address=True)
  await site.start()
  server = site._server
  if server is None or not server.sockets:
    await runner.cleanup()
    raise RuntimeError("failed to bind internal HTTPS server")

  internal_port = server.sockets[0].getsockname()[1]
  mux = await asyncio.start_server(
    lambda r, w: _mux_client_handler(r, w, backend_port=internal_port, public_port=port),
    host,
    port,
    reuse_address=True,
  )
  log.info(
    "HTTPS on 127.0.0.1:%s; HTTP→HTTPS redirect on %s:%s",
    internal_port,
    host,
    port,
  )

  stop = asyncio.Event()
  loop = asyncio.get_running_loop()
  for sig in (signal.SIGINT, signal.SIGTERM):
    try:
      loop.add_signal_handler(sig, stop.set)
    except NotImplementedError:
      pass

  try:
    await stop.wait()
  finally:
    mux.close()
    await mux.wait_closed()
    await runner.cleanup()


def run_web_app(
  app: web.Application,
  *,
  host: str,
  port: int,
  tls: bool = False,
  tls_cert: str | None = None,
  tls_key: str | None = None,
  tls_dir: str | None = None,
  tls_redirect_http: bool | None = None,
) -> None:
  ssl_context: ssl.SSLContext | None = None
  if tls:
    if tls_cert and tls_key:
      ssl_context = build_ssl_context(Path(tls_cert), Path(tls_key))
    else:
      cert, key = ensure_tls_files(Path(tls_dir) if tls_dir else None)
      ssl_context = build_ssl_context(cert, key)

    if _tls_redirect_http_enabled(tls_redirect_http):
      try:
        asyncio.run(_run_tls_with_http_redirect(app, host=host, port=port, ssl_context=ssl_context))
      except KeyboardInterrupt:
        pass
      return

  web.run_app(app, host=host, port=port, ssl_context=ssl_context)
