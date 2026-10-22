#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Entry point for the carrot API server (port 7000).

Started by the manager as the `carrot_server` process, exactly like CarrotPilot's
`selfdrive/carrot/carrot_server.py` (also port 7000). CarrotPilot is the companion app's
expected API host, so this is what turns the app's "设备未连接" into a working link.

Kept importable without aiohttp: if the dependency is missing the process reports it and
exits non-zero rather than tracebacking on import, and the manager's process log shows the
one-line reason.
"""

import argparse
import logging
import os
import sys


def _cores() -> list[int]:
  raw = os.environ.get("CARROT_WEB_CORES", "")
  cores = [int(part) for part in raw.split(",") if part.strip().isdigit()]
  if cores:
    return cores
  from openpilot.sunnypilot.carrot.server.config import DEFAULT_CORES

  return list(DEFAULT_CORES)


def main() -> int:
  try:
    from aiohttp import web
  except ImportError as exc:
    print(f"[carrot_server] aiohttp unavailable: {exc}", flush=True)
    return 1

  from openpilot.sunnypilot.carrot.server.config import DEFAULT_HOST, DEFAULT_PORT

  parser = argparse.ArgumentParser()
  parser.add_argument("--host", type=str, default=DEFAULT_HOST)
  parser.add_argument("--port", type=int, default=DEFAULT_PORT)
  args = parser.parse_args()

  # Stay off the realtime control core (4): card/controlsd/selfdrived own it, and it runs
  # at ~99% while driving. Same policy as CarrotPilot's carrot_server.
  try:
    from openpilot.common.realtime import set_core_affinity

    set_core_affinity(_cores())
  except Exception as exc:
    print(f"[carrot_server] failed to set core affinity: {exc}", flush=True)

  from openpilot.sunnypilot.carrot.server.app import create_app

  logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
  print(f"[carrot_server] serving carrot API on {args.host}:{args.port}", flush=True)
  web.run_app(create_app(), host=args.host, port=args.port)
  return 0


if __name__ == "__main__":
  sys.exit(main())
