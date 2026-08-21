"""
PC dev bootstrap — mock openpilot so webuid can run on Windows/Linux without AGNOS.

Usage (from openpilot root):
  py -3 webui/dev/run_pc.py [--port 5080]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEBUI_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
  parser = argparse.ArgumentParser(description="op Web UI PC 开发预览服务")
  parser.add_argument("--port", type=int, default=5080)
  parser.add_argument("--host", type=str, default="127.0.0.1")
  parser.add_argument("--tls", action="store_true", help="HTTPS (for WebCodecs over LAN IP testing)")
  args = parser.parse_args()

  # Install mocks before any webui.server import
  sys.path.insert(0, str(WEBUI_ROOT.parent if (WEBUI_ROOT.parent / "webui").is_dir() else ROOT))
  from webui.webuid import ensure_runtime

  op_root = str(ROOT)
  if not (Path(op_root) / "openpilot").is_dir() and (Path(op_root).parent / "openpilot").is_dir():
    op_root = str(Path(op_root).parent)
  os.environ.setdefault("OPENPILOT_ROOT", op_root)
  ensure_runtime()

  from webui.server.app_factory import create_app
  from webui.server.run_server import run_web_app

  app = create_app()

  scheme = "https" if args.tls else "http"
  print()
  print(f"  op Web UI PC 预览: {scheme}://{args.host}:{args.port}/")
  if args.tls:
    print("  TLS: 可用 https://<本机局域网IP>:{port}/ 测试 WebCodecs（需信任自签证书）".format(port=args.port))
    print("  HTTP: http://<本机局域网IP>:{port}/ 会自动跳转到 HTTPS".format(port=args.port))
  print()
  print("  说明: Mock Params + 模拟行车状态；右下角 Dev 面板可切换离路/行驶、无屏模式等。")
  print("  与车机 1:1 差距见 webui/dev/README.md")
  print()
  run_web_app(app, host=args.host, port=args.port, tls=args.tls)


if __name__ == "__main__":
  main()
