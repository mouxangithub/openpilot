"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""A small, bounded view of live cereal for `/api/live_runtime`.

The app asks for this while parked, so it is deliberately narrow: a fixed allow-list of
services, the newest sample of each, and a JSON-safe conversion that cannot hand back a
megabyte of model output. Anything it cannot read it reports as unavailable rather than
failing the request, because a device with no zmq still has to answer the device tab.

`messaging` is injected, so this is importable (and testable) without zmq.
"""
import logging
import time

logger = logging.getLogger("openpilot.carrot.server.live_runtime")

# Small scalar-ish services only. modelV2 and the encode services are deliberately not
# here: at 20 Hz their JSON would dwarf everything else on the endpoint.
LIVE_RUNTIME_SERVICES = (
  "selfdriveState",
  "carState",
  "controlsState",
  "deviceState",
  "carrotManSP",
  "carrotNaviSP",
  "carrotNaviStateSP",
  "chestnutState",
)

CACHE_MAX_AGE_SEC = 1.0
MAX_LIST_ITEMS = 32
MAX_DEPTH = 6


def json_safe(value, depth: int = 0):
  """capnp readers are not JSON types; convert, and bound the result."""
  if depth > MAX_DEPTH:
    return None
  if value is None or isinstance(value, (bool, int, float, str)):
    return value
  if isinstance(value, bytes):
    return value.decode("utf-8", "replace")
  if isinstance(value, (list, tuple)):
    return [json_safe(item, depth + 1) for item in list(value)[:MAX_LIST_ITEMS]]
  if isinstance(value, dict):
    return {str(key): json_safe(item, depth + 1) for key, item in value.items()}
  try:
    return json_safe(value.to_dict(), depth + 1)
  except Exception:
    return str(value)


class LiveRuntime:
  """Newest-sample cache over a fixed service list."""

  def __init__(self, messaging, services=LIVE_RUNTIME_SERVICES):
    self._messaging = messaging
    self._services = tuple(services)
    self._sockets = {}
    self._last: dict = {}
    self._at = 0.0
    self._error = ""

  # ---- reading ------------------------------------------------------------ #

  def _socket(self, service):
    sock = self._sockets.get(service)
    if sock is not None:
      return sock
    try:
      sock = self._messaging.sub_sock(service, conflate=True)
    except Exception as exc:
      self._error = str(exc)
      return None
    self._sockets[service] = sock
    return sock

  @staticmethod
  def _payload(message):
    try:
      which = message.which()
    except Exception:
      return None
    return getattr(message, which, None) if which else None

  def poll(self) -> None:
    """Read the newest sample of every service. Called from one task only."""
    for service in self._services:
      sock = self._socket(service)
      if sock is None:
        continue
      try:
        message = self._messaging.recv_one_or_none(sock)
      except Exception as exc:
        self._error = str(exc)
        continue
      payload = self._payload(message)
      if payload is None:
        continue
      self._last[service] = json_safe(payload)
    self._at = time.monotonic()

  # ---- answering ---------------------------------------------------------- #

  def is_engaged(self) -> bool:
    """Engagement gate for reboot/poweroff/recalibrate."""
    state = self._last.get("selfdriveState")
    if isinstance(state, dict):
      for key in ("enabled", "active"):
        if state.get(key):
          return True
    try:
      from openpilot.common.params import Params

      return bool(Params().get_bool("IsEngaged"))
    except Exception:
      return False

  def snapshot(self, max_age_sec: float = CACHE_MAX_AGE_SEC) -> dict:
    if time.monotonic() - self._at > max_age_sec:
      try:
        self.poll()
      except Exception as exc:
        logger.warning("carrot_server: live runtime poll failed: %s", exc)
        self._error = str(exc)
    return {
      "ok": True,
      "meta": {
        "services": list(self._services),
        "snapshotAgeMs": int((time.monotonic() - self._at) * 1000.0) if self._at else None,
        "error": self._error or None,
      },
      "services": dict(self._last),
    }

  def close(self) -> None:
    for service in list(self._sockets):
      sock = self._sockets.pop(service, None)
      if sock is None:
        continue
      try:
        sock.close()
      except Exception:
        pass


class RuntimeHolder:
  """Owns the one `LiveRuntime` for the app, created on first use.

  aiohttp warns when an application's state is changed after it has started, and the
  routes that need the runtime can be the first thing a client asks for. Holding a
  mutable object - created while the app is still being built - keeps the app's own
  state untouched, and keeps the "cereal missing" answer in one place.
  """

  def __init__(self, services=LIVE_RUNTIME_SERVICES):
    self._services = services
    self._runtime = None
    self._error = ""

  def get(self):
    if self._runtime is None:
      try:
        from openpilot.cereal import messaging
      except Exception as exc:
        self._error = str(exc)
        return None
      self._runtime = LiveRuntime(messaging, self._services)
      self._error = ""
    return self._runtime

  def error(self) -> str:
    return self._error

  def close(self) -> None:
    if self._runtime is not None:
      self._runtime.close()
      self._runtime = None
