"""WiFi / network bridge via WifiManager."""

from __future__ import annotations

import threading
from typing import Any

_wifi: Any = None
_wifi_lock = threading.Lock()


def _manager():
  global _wifi
  with _wifi_lock:
    if _wifi is None:
      from openpilot.system.ui.lib.wifi_manager import WifiManager
      _wifi = WifiManager()
      _wifi.set_active(True)
    return _wifi


def wifi_status() -> dict[str, Any]:
  import os
  if os.environ.get("WEBUI_DEV_PC") == "1":
    from webui.dev.mock_runtime import mock_wifi_networks
    nets = mock_wifi_networks()
    connected = next((n["ssid"] for n in nets if n["connected"]), None)
    return {"ok": True, "connected": connected, "ipv4": "192.168.1.100", "dev_pc": True}
  try:
    wm = _manager()
    wm.set_active(True)
    wm.process_callbacks()
    ssid = wm.connected_ssid
    return {
      "ok": True,
      "connected": ssid,
      "ipv4": wm.ipv4_address if hasattr(wm, "ipv4_address") else "",
    }
  except Exception as exc:
    return {"ok": False, "error": str(exc), "networks": []}


def wifi_scan(trigger: bool = False) -> dict[str, Any]:
  import os
  if os.environ.get("WEBUI_DEV_PC") == "1":
    from webui.dev.mock_runtime import mock_wifi_networks
    return {"ok": True, "networks": mock_wifi_networks(), "dev_pc": True}
  try:
    wm = _manager()
    wm.set_active(True)
    if trigger:
      wm._request_scan()
      threading.Thread(target=wm._update_networks, kwargs={"block": False}, daemon=True).start()
    wm.process_callbacks()
    networks = []
    connected = wm.connected_ssid
    for n in wm.networks:
      networks.append({
        "ssid": n.ssid,
        "strength": n.strength,
        "security": int(n.security_type),
        "connected": connected == n.ssid,
        "saved": wm.is_connection_saved(n.ssid),
      })
    networks.sort(key=lambda x: -x["strength"])
    return {"ok": True, "networks": networks}
  except Exception as exc:
    return {"ok": False, "error": str(exc), "networks": []}


def wifi_connect(ssid: str, password: str = "") -> dict[str, Any]:
  try:
    wm = _manager()
    wm.set_active(True)
    wm.connect_to_network(ssid, password, hidden=False)
    return {"ok": True, "ssid": ssid}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def wifi_forget(ssid: str) -> dict[str, Any]:
  try:
    wm = _manager()
    wm.forget_connection(ssid, block=True)
    return {"ok": True, "ssid": ssid}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def network_advanced_status() -> dict[str, Any]:
  import os
  if os.environ.get("WEBUI_DEV_PC") == "1":
    return {
      "ok": True,
      "ipv4": "10.255.128.121",
      "tethering": False,
      "wifi_metered": 0,
      "wifi_metered_enabled": True,
      "dev_pc": True,
    }
  try:
    from openpilot.system.ui.lib.wifi_manager import MeteredType
    wm = _manager()
    wm.set_active(True)
    wm.process_callbacks()
    tethering = wm.is_tethering_active()
    ipv4 = wm.ipv4_address if hasattr(wm, "ipv4_address") else ""
    metered = int(wm.current_network_metered)
    if metered not in (MeteredType.UNKNOWN, MeteredType.YES, MeteredType.NO):
      metered = int(MeteredType.UNKNOWN)
    return {
      "ok": True,
      "ipv4": ipv4,
      "tethering": tethering,
      "wifi_metered": metered,
      "wifi_metered_enabled": bool(ipv4) and not tethering,
    }
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def wifi_set_tethering(active: bool) -> dict[str, Any]:
  try:
    wm = _manager()
    wm.set_active(True)
    wm.set_tethering_active(active)
    return {"ok": True, "active": active}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def wifi_set_tethering_password(password: str) -> dict[str, Any]:
  try:
    wm = _manager()
    wm.set_active(True)
    wm.set_tethering_password(password)
    return {"ok": True}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def wifi_set_metered(metered: int) -> dict[str, Any]:
  try:
    from openpilot.system.ui.lib.wifi_manager import MeteredType
    wm = _manager()
    wm.set_active(True)
    mapping = {0: MeteredType.UNKNOWN, 1: MeteredType.YES, 2: MeteredType.NO}
    wm.set_current_network_metered(mapping.get(metered, MeteredType.UNKNOWN))
    return {"ok": True, "metered": metered}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def wifi_connect_hidden(ssid: str, password: str = "") -> dict[str, Any]:
  try:
    wm = _manager()
    wm.set_active(True)
    wm.connect_to_network(ssid, password, hidden=True)
    return {"ok": True, "ssid": ssid}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}
