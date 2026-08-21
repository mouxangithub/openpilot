#!/usr/bin/env python3
"""
Openpilot AI Agent service.

Serves a LAN-accessible web UI for configuring and chatting with the AI agent,
plus a small REST API consumed by the device UI.
"""

import argparse

from aiohttp import web

from openpilot.common.swaglog import cloudlog

from ai.server.app_factory import create_app
from ai.server.deps import DEFAULT_PORT


def main() -> None:
  parser = argparse.ArgumentParser(description="Openpilot AI Agent service")
  parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Listen port")
  parser.add_argument("--host", type=str, default="0.0.0.0", help="Listen host")
  args = parser.parse_args()

  from ai.services.tsk.routes import init_tsk_for_aid
  init_tsk_for_aid(args.port)

  app = create_app()
  cloudlog.info(f"aid: starting on {args.host}:{args.port} (SecOC in settings sidebar)")
  web.run_app(app, host=args.host, port=args.port)


if __name__ == "__main__":
  main()
