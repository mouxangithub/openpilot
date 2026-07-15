#!/usr/bin/env python3

"""
Copyright (c) 2026, Rick Lan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, and/or sublicense,
for non-commercial purposes only, subject to the following conditions:

- The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.
- Commercial use (e.g. use in a product, service, or activity intended to
  generate revenue) is prohibited without explicit written permission from
  the copyright holder.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Dashy HTTP Server — entry point.

Provides a REST API + static file serving + a one-way SSE telemetry stream for
the dashy web UI. The implementation lives in the dashy_server package; this
module only wires it together and runs it.
"""

import argparse
import logging
import threading

# serverd runs in two contexts: as a package module on-device
# (dragonpilot.dashy.serverd, via the process manager's importlib) and as a
# plain script in dev/tests (python serverd.py / import serverd, with this
# directory on sys.path). Relative imports work in the former, absolute in the
# latter — try relative first, fall back to absolute.
try:
  from .dashy_server import handlers, stream
  from .dashy_server.cache import AppCache
  from .dashy_server.config import logger
  from .dashy_server.http import DashyServer
except ImportError:
  from dashy_server import handlers, stream
  from dashy_server.cache import AppCache
  from dashy_server.config import logger
  from dashy_server.http import DashyServer


def main():
  parser = argparse.ArgumentParser(description="Dashy Server")
  parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to listen on")
  parser.add_argument("--port", type=int, default=5088, help="Port to listen on")
  parser.add_argument("--debug", action="store_true", help="Enable debug mode")
  args = parser.parse_args()

  logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

  # Shared state for request threads + the publisher: the AppCache and the
  # latest telemetry frame. stream_latest is set before stream_seq is bumped.
  app_state = {'cache': AppCache(), 'stream_latest': None, 'stream_seq': 0}
  stop_event = threading.Event()

  publisher = threading.Thread(
    target=stream._publisher_loop,
    args=(app_state, stop_event),
    name="dashy-publisher",
    daemon=True,
  )
  publisher.start()

  httpd = DashyServer((args.host, args.port), app_state, stop_event, handlers.build_routes())
  logger.info(f"Dashy server started on {args.host}:{args.port}")
  try:
    httpd.serve_forever()
  except KeyboardInterrupt:
    pass
  finally:
    stop_event.set()
    httpd.shutdown()
    httpd.server_close()
    logger.info("Dashy server stopped")


if __name__ == "__main__":
  main()
