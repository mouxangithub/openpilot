"""
PC dev bootstrap — mock openpilot runtime so the webui can start on Windows/Linux without AGNOS build.

Usage (from openpilot root):
  py -3 webui/dev/run_pc.py [--port 5080]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
  parser = argparse.ArgumentParser(description="openpilot webui PC 开发预览服务")
  parser.add_argument("--port", type=int, default=5080)
  parser.add_argument("--host", type=str, default="127.0.0.1")
  args = parser.parse_args()

  if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

  logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

  from webui.dev.mock_runtime import install_openpilot_mocks
  install_openpilot_mocks(str(ROOT))

  from aiohttp import web
  from webui.server.routes import register_routes

  app = web.Application(client_max_size=32 * 1024 * 1024)
  register_routes(app)

  from webui.server.bridge.state_hub import start_state_hub
  start_state_hub()

  print(f"\n  openpilot webui PC 预览: http://{args.host}:{args.port}/\n")
  print("  说明: Mock Params + 模拟状态；在浏览器打开上方链接即可预览 UI。\n")
  web.run_app(app, host=args.host, port=args.port)


if __name__ == "__main__":
  main()
