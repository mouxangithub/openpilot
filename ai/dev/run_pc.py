"""
PC dev bootstrap — mock openpilot runtime so aid can start on Windows/Linux without AGNOS build.

Usage (from openpilot root):
  py -3 ai/dev/run_pc.py [--port 5090]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _install_openpilot_mocks() -> None:
  """Install minimal openpilot.* modules before ai imports."""
  if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

  log = logging.getLogger("aid")
  logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

  class MockParams:
    _data: dict[str, bytes | str] = {}

    def __init__(self) -> None:
      pass

    def check_key(self, key: str) -> bool:
      return True

    def keys(self):
      return list(self._data.keys())

    def get(self, key: str, block: bool = False, default=None):
      val = self._data.get(key)
      if val is None:
        return default
      return val

    def get_bool(self, key: str, block: bool = False) -> bool:
      raw = self.get(key, block=block)
      if raw is None:
        return False
      if isinstance(raw, bytes):
        raw = raw.decode(errors="replace")
      return str(raw).strip().lower() in ("1", "true", "yes", "on")

    def put(self, key: str, val, block: bool = False) -> None:
      self._data[key] = val if isinstance(val, (bytes, bytearray)) else str(val).encode()

    def put_bool(self, key: str, val: bool, block: bool = False) -> None:
      self.put(key, b"1" if val else b"0", block=block)

    def remove(self, key: str) -> None:
      self._data.pop(key, None)

  class _CloudLog:
    def info(self, msg: str, *a, **k) -> None:
      log.info(msg)

    def warning(self, msg: str, *a, **k) -> None:
      log.warning(msg)

    def error(self, msg: str, *a, **k) -> None:
      log.error(msg)

    def debug(self, msg: str, *a, **k) -> None:
      log.debug(msg)

  op = types.ModuleType("openpilot")
  common = types.ModuleType("openpilot.common")
  params_mod = types.ModuleType("openpilot.common.params")
  params_mod.Params = MockParams
  swaglog_mod = types.ModuleType("openpilot.common.swaglog")
  swaglog_mod.cloudlog = _CloudLog()

  sys.modules["openpilot"] = op
  sys.modules["openpilot.common"] = common
  sys.modules["openpilot.common.params"] = params_mod
  sys.modules["openpilot.common.swaglog"] = swaglog_mod

  op.common = common
  common.params = params_mod
  common.swaglog = swaglog_mod

  os.environ.setdefault("AI_DEV_PC", "1")
  os.environ.setdefault("OPENPILOT_ROOT", str(ROOT))


def main() -> None:
  parser = argparse.ArgumentParser(description="op助手 PC 开发预览服务")
  parser.add_argument("--port", type=int, default=5090)
  parser.add_argument("--host", type=str, default="127.0.0.1")
  args = parser.parse_args()

  _install_openpilot_mocks()

  from aiohttp import web
  from ai.server.app_factory import create_app

  app = create_app()
  print(f"\n  op助手 PC 预览: http://{args.host}:{args.port}/\n")
  print("  说明: Mock Params + 无 cereal；配置 API Key 后可测试聊天。\n")
  web.run_app(app, host=args.host, port=args.port)


if __name__ == "__main__":
  main()
