"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Device facts the companion app shows: network addresses and calibration state.

Read-only, and deliberately cheap: the app polls these while parked, so nothing here
shells out per request more than it has to and every read degrades to an empty result
rather than an exception.
"""
import logging
import socket
import time

logger = logging.getLogger("openpilot.carrot.server.device_info")

NETWORK_REFRESH_INTERVAL_SEC = 30.0

_CACHE: dict = {"at": 0.0, "network": None}


def _interfaces() -> list:
  try:
    import psutil
  except ImportError:
    return []
  out = []
  try:
    addresses = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
  except Exception:
    return []
  for name in sorted(addresses):
    entry = {"name": name, "up": False, "ipv4": [], "ipv6": [], "mac": ""}
    stat = stats.get(name)
    entry["up"] = bool(getattr(stat, "isup", False))
    for addr in addresses.get(name) or ():
      family = getattr(addr, "family", None)
      value = getattr(addr, "address", "")
      if family == socket.AF_INET:
        entry["ipv4"].append(value)
      elif family == socket.AF_INET6:
        entry["ipv6"].append(value.split("%")[0])
      elif family == getattr(psutil, "AF_LINK", None) and value:
        entry["mac"] = value
    out.append(entry)
  return out


def _default_route() -> str:
  """The interface carrying the default route, which is the one the app can reach."""
  try:
    with open("/proc/net/route", encoding="utf-8") as handle:
      for line in handle.read().splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "00000000":
          return parts[0]
  except OSError:
    pass
  return ""


def listening_ports(ports) -> dict:
  """Which of the carrot ports have a socket bound. Read-only, from /proc.

  Used to answer "is the carrot nav channel up" without trying to open the port, which
  would either steal a datagram or block on a TCP handshake.
  """
  wanted = {int(port) for port in ports}
  found = dict.fromkeys(wanted, False)
  for kind in ("tcp", "tcp6", "udp", "udp6"):
    try:
      with open(f"/proc/net/{kind}", encoding="utf-8") as handle:
        lines = handle.read().splitlines()[1:]
    except OSError:
      continue
    for line in lines:
      parts = line.split()
      if len(parts) < 2 or ":" not in parts[1]:
        continue
      try:
        port = int(parts[1].rsplit(":", 1)[1], 16)
      except ValueError:
        continue
      if port in found:
        found[port] = True
  return found


def _hostname() -> str:
  try:
    return socket.gethostname()
  except Exception:
    return ""


def refresh_device_network() -> dict:
  """Re-read the network state. Cached by `get_device_network_snapshot`."""
  network = {
    "hostname": _hostname(),
    "interfaces": _interfaces(),
    "defaultInterface": _default_route(),
    "updatedAt": time.monotonic(),
  }
  _CACHE["at"] = time.monotonic()
  _CACHE["network"] = network
  return network


def get_device_network_snapshot(max_age_sec: float = NETWORK_REFRESH_INTERVAL_SEC) -> dict:
  cached = _CACHE.get("network")
  age = time.monotonic() - float(_CACHE.get("at") or 0.0)
  if cached is None or age > max_age_sec:
    try:
      return refresh_device_network()
    except Exception as exc:
      logger.warning("carrot_server: network refresh failed: %s", exc)
      return cached or {"hostname": _hostname(), "interfaces": [], "defaultInterface": "", "updatedAt": 0.0}
  return cached


def _live_calibration(messaging) -> dict:
  """Prefer the live service; fall back to the persisted calibration result."""
  try:
    sock = messaging.sub_sock("liveCalibration", conflate=True)
  except Exception:
    return {}
  try:
    message = messaging.recv_one_or_none(sock)
    if message is None:
      return {}
    which = message.which()
    state = getattr(message, which, None) if which else None
    if state is None:
      return {}
    return {
      "calPerc": int(getattr(state, "calPerc", 0) or 0),
      "calStatus": int(getattr(state, "calStatus", 0) or 0),
      "source": "liveCalibration",
    }
  except Exception:
    return {}
  finally:
    try:
      sock.close()
    except Exception:
      pass


def _persisted_calibration() -> dict:
  try:
    from openpilot.common.params import Params
  except Exception:
    return {}
  try:
    raw = Params().get("CalibrationParams")
  except Exception:
    return {}
  if not raw:
    return {}
  try:
    import json

    parsed = json.loads(raw)
  except Exception:
    return {}
  if not isinstance(parsed, dict):
    return {}
  return {
    "calPerc": int(parsed.get("calPerc", 0) or 0),
    "calStatus": int(parsed.get("calStatus", 0) or 0),
    "source": "CalibrationParams",
  }


def get_calibration_status(messaging=None) -> dict:
  """Calibration percentage/status, or an empty dict when neither source answers."""
  if messaging is not None:
    live = _live_calibration(messaging)
    if live:
      return live
  persisted = _persisted_calibration()
  if persisted:
    return persisted
  return {"calPerc": 0, "calStatus": 0, "source": "unavailable"}
