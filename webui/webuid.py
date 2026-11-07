"""
Web UI server — same entry as launch_chffrplus.sh (`python -m webui.webuid`).

On PC without compiled openpilot Params, auto-installs dev mocks (same as run_pc.py).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path


def _openpilot_root() -> Path:
  here = Path(__file__).resolve().parent
  root = here.parent
  if (root / "openpilot").is_dir():
    return root
  if (root.parent / "openpilot").is_dir():
    return root.parent
  return root


def ensure_runtime() -> bool:
  """Return True when PC dev mocks are active."""
  root = str(_openpilot_root())
  if root not in sys.path:
    sys.path.insert(0, root)
  venv_site = "/usr/local/venv/lib/python3.12/site-packages"
  if os.path.isdir(venv_site) and venv_site not in sys.path:
    sys.path.append(venv_site)
  for pydeps in (os.path.join(root, ".pydeps"), "/data/.pydeps"):
    if os.path.isdir(pydeps) and pydeps not in sys.path:
      sys.path.append(pydeps)

  # After an overlay update the compiled Params shared library may still be
  # building. Wait for it instead of immediately falling back to dev mocks.
  params_so = os.path.join(root, "openpilot", "common", "libparams_c.so")
  if not os.path.isfile(params_so):
    logger = logging.getLogger("webuid")
    logger.info("Waiting for %s to appear...", params_so)
    waited = 0
    while not os.path.isfile(params_so) and waited < 120:
      import time
      time.sleep(1)
      waited += 1
    if os.path.isfile(params_so):
      logger.info("Found libparams_c.so after %ss", waited)
    else:
      logger.warning("Timed out waiting for libparams_c.so after %ss", waited)

  try:
    from openpilot.common.params import Params

    Params()
    return False
  except Exception as exc:
    logging.getLogger("webuid").warning("Params import failed: %s", exc, exc_info=True)
  from webui.dev.mock_runtime import install_openpilot_mocks

  install_openpilot_mocks(root)
  logging.getLogger("webuid").info("PC dev mocks enabled (Params/cereal unavailable)")
  return True


def main() -> None:
  parser = argparse.ArgumentParser(description="openpilot Web UI server")
  parser.add_argument("--port", type=int, default=int(os.environ.get("WEBUI_PORT", "5080")))
  parser.add_argument("--host", type=str, default=os.environ.get("WEBUI_HOST", "0.0.0.0"))
  parser.add_argument("--tls", action="store_true", default=os.environ.get("WEBUI_TLS", "").lower() in ("1", "true", "yes"))
  parser.add_argument("--tls-cert", type=str, default=os.environ.get("WEBUI_TLS_CERT", ""))
  parser.add_argument("--tls-key", type=str, default=os.environ.get("WEBUI_TLS_KEY", ""))
  parser.add_argument("--tls-dir", type=str, default=os.environ.get("WEBUI_TLS_DIR", ""))
  args = parser.parse_args()

  dev_pc = ensure_runtime()

  from webui.server.app_factory import create_app
  from webui.server.run_server import run_web_app

  app = create_app()
  scheme = "https" if args.tls else "http"
  print()
  print(f"  op Web UI: {scheme}://127.0.0.1:{args.port}/")
  if args.tls:
    print(f"  TLS: 局域网请用 {scheme}://<车机IP>:{args.port}/ （首次需在浏览器信任自签证书）")
    print(f"  HTTP: http://<车机IP>:{args.port}/ 会自动跳转到 HTTPS")
    print("  说明: HTTPS 可启用 WebCodecs；HTTP 局域网 IP 仅支持 Video 元素解码")
  elif not dev_pc:
    print("  提示: 局域网 WebCodecs 需 HTTPS，启动时加 --tls 或设置 WEBUI_TLS=1")
  if dev_pc:
    print("  模式: PC 预览 (Mock Params + 模拟状态)")
    print("  提示: 右下角 Dev 面板可切换离路/行驶；与车机差异见 webui/dev/README.md")
  print()
  run_web_app(
    app,
    host=args.host,
    port=args.port,
    tls=args.tls,
    tls_cert=args.tls_cert or None,
    tls_key=args.tls_key or None,
    tls_dir=args.tls_dir or None,
  )


if __name__ == "__main__":
  main()
