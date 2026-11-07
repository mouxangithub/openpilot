"""`/api/lan_services` - the other HTTP services this device exposes.

The panel runs on 7000, the webui submodule on 5080 and the OP assistant
(`ai.aid`) on 5090. They are separate processes on the same LAN address, so the
browser cannot probe them directly (different origin, and neither enables CORS).
This route probes them from the device instead and hands the page a URL plus an
online/offline flag per service, which is all the shortcut needs.
"""

import asyncio

from aiohttp import web

PROBE_TIMEOUT_SECONDS = 1.5

# (id, label, port) - 7000 is this panel and is online by definition.
LAN_SERVICES: tuple[tuple[str, str, int], ...] = (
  ("carrot", "Carrot Web", 7000),
  ("webui", "WebUI", 5080),
  ("op", "OP 助手", 5090),
)


def _host_of(request: web.Request) -> str:
  # Host header already carries whatever the user typed to reach the panel
  # (LAN IP, localhost, or a hostname) - reuse it so every shortcut points at
  # the same address the browser is currently on.
  host = request.headers.get("Host", "")
  if host.startswith("["):  # [::1]:7000
    return host.rsplit("]", 1)[0] + "]"
  return host.split(":", 1)[0]


async def _reachable(host: str, port: int) -> bool:
  if not host:
    return False
  try:
    async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
      _reader, writer = await asyncio.open_connection(host, port)
      writer.close()
      try:
        await writer.wait_closed()
      except Exception:
        pass
      return True
  except Exception:
    return False


async def api_lan_services(request: web.Request) -> web.Response:
  host = _host_of(request)
  results = await asyncio.gather(*(_reachable(host, port) for _id, _label, port in LAN_SERVICES))
  services = [
    {
      "id": service_id,
      "label": label,
      "port": port,
      "url": f"http://{host}:{port}" if host else "",
      "online": bool(online),
    }
    for (service_id, label, port), online in zip(LAN_SERVICES, results, strict=True)
  ]
  return web.json_response({"ok": bool(host), "host": host, "services": services})


def register(app: web.Application) -> None:
  app.router.add_get("/api/lan_services", api_lan_services)
