"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Latest-only cereal relay behind `/ws/raw_multiplex` and `/ws/raw/{service}`.

Reads the fork's own cereal directly - `messaging.sub_sock(service, conflate=True)` plus
`receive(non_blocking=True)` returns the raw capnp payload - so no second data plane is
introduced: the same services every daemon already publishes are what the app receives.

Differences from CarrotPilot's hub, on purpose:

* no per-service display cadence table. One conflated socket is polled at a fixed low rate
  and whatever is newest is forwarded, which is the same "latest-only" behaviour without
  carrying a rate for every service;
* no compact/native encoding mode (that needs `compact_state_pyx`, still unported), no
  single-service mode differences beyond the frame prefix;
* a slow client cannot stall the poll loop: each socket has its own bounded, coalesced
  queue drained by its own sender task, and a send that exceeds the timeout disconnects
  that client only.

`messaging` is injected rather than imported so this module stays importable (and testable)
without zmq.
"""
import asyncio
import logging
from collections import OrderedDict

from .raw_protocol import encode_raw_multiplex_frame

logger = logging.getLogger("openpilot.carrot.server.raw_relay")


class RawRelayHub:
  POLL_INTERVAL = 0.02      # 50 Hz: a conflated read is cheap and bounds added latency
  EMPTY_READ_RETRY = 0.005  # re-check sooner when a publisher happened to be idle
  IDLE_SLEEP = 0.05
  IDLE_STOP_SEC = 30.0      # park the poll task when nobody is watching
  SEND_TIMEOUT = 0.75
  MAX_SERVICES_PER_CLIENT = 32
  CLOSE_SEND_TIMEOUT = 1011

  def __init__(self, messaging):
    self._messaging = messaging
    self._clients: dict[str, set] = {}
    self._sockets: dict[str, object] = {}
    self._next_read: dict[str, float] = {}
    self._ws_services: dict[object, set] = {}
    self._ws_names: dict[object, dict] = {}
    self._pending: dict[object, OrderedDict] = {}
    self._events: dict[object, asyncio.Event] = {}
    self._senders: dict[object, asyncio.Task] = {}
    self._poll_task: asyncio.Task | None = None
    self._lock = asyncio.Lock()

  # ---- registration ------------------------------------------------------- #

  def client_count(self, service: str | None = None) -> int:
    if service is None:
      return len(self._ws_services)
    return len(self._clients.get(service, ()))

  async def register(self, resolved, ws) -> None:
    """`resolved` is [(client_name, device_service)] from `raw_services.resolve_services`."""
    resolved = list(resolved)[:self.MAX_SERVICES_PER_CLIENT]
    if not resolved:
      return
    self._ws_services[ws] = {device for _, device in resolved}
    self._ws_names[ws] = {device: client for client, device in resolved}
    self._pending.setdefault(ws, OrderedDict())
    self._events.setdefault(ws, asyncio.Event())
    for _, device in resolved:
      self._clients.setdefault(device, set()).add(ws)
    await self._ensure_poll_task()

  async def unregister(self, ws) -> None:
    for device in self._ws_services.pop(ws, set()):
      self._clients.get(device, set()).discard(ws)
    self._ws_names.pop(ws, None)
    self._pending.pop(ws, None)
    self._events.pop(ws, None)
    sender = self._senders.pop(ws, None)
    if sender is not None and sender is not asyncio.current_task():
      sender.cancel()
      try:
        await sender
      except (asyncio.CancelledError, Exception):
        pass

  async def close(self) -> None:
    for ws in list(self._ws_services):
      await self.unregister(ws)
    task = self._poll_task
    self._poll_task = None
    if task is not None:
      task.cancel()
      try:
        await task
      except (asyncio.CancelledError, Exception):
        pass
    self._close_sockets()

  # ---- polling ------------------------------------------------------------ #

  def _close_sockets(self, services=None) -> None:
    for device in list(self._sockets) if services is None else list(services):
      sock = self._sockets.pop(device, None)
      self._next_read.pop(device, None)
      if sock is not None:
        try:
          sock.close()
        except Exception:
          pass

  async def _ensure_poll_task(self) -> None:
    if self._poll_task is None or self._poll_task.done():
      self._poll_task = asyncio.create_task(self._poll_loop())

  async def _poll_loop(self) -> None:
    idle_since = None
    loop = asyncio.get_running_loop()
    try:
      while True:
        active = {device for device, clients in self._clients.items() if clients}
        if not active:
          if idle_since is None:
            idle_since = loop.time()
          elif loop.time() - idle_since >= self.IDLE_STOP_SEC:
            break
          await asyncio.sleep(self.IDLE_SLEEP)
          continue
        idle_since = None
        self._close_sockets(set(self._sockets) - active)

        now = loop.time()
        next_due = now + self.IDLE_SLEEP
        for device in active:
          if now < self._next_read.get(device, 0.0):
            next_due = min(next_due, self._next_read[device])
            continue
          sock = self._sockets.get(device)
          if sock is None:
            try:
              sock = self._messaging.sub_sock(device, conflate=True)
              self._sockets[device] = sock
            except Exception as exc:
              logger.warning("carrot_server: cannot subscribe to %s: %s", device, exc)
              self._next_read[device] = now + self.IDLE_SLEEP
              next_due = min(next_due, self._next_read[device])
              continue
          try:
            payload = sock.receive(non_blocking=True)
          except Exception:
            payload = None
          if payload is None:
            self._next_read[device] = now + self.EMPTY_READ_RETRY
          else:
            self._next_read[device] = now + self.POLL_INTERVAL
            self._broadcast(device, payload)
          next_due = min(next_due, self._next_read[device])

        sleep_for = max(0.001, min(self.IDLE_SLEEP, next_due - loop.time()))
        await asyncio.sleep(sleep_for)
    except asyncio.CancelledError:
      raise
    except Exception:
      logger.exception("carrot_server: raw relay poll loop stopped")
    finally:
      self._close_sockets()
      async with self._lock:
        if self._poll_task is asyncio.current_task():
          self._poll_task = None

  # ---- delivery ----------------------------------------------------------- #

  def _broadcast(self, device: str, payload: bytes) -> None:
    for ws in list(self._clients.get(device, ())):
      client_name = self._ws_names.get(ws, {}).get(device, device)
      try:
        wire = encode_raw_multiplex_frame(service=client_name, payload=payload)
      except Exception:
        continue
      self._queue(ws, device, wire)

  def _queue(self, ws, device: str, wire: bytes) -> None:
    if ws not in self._ws_services:
      return
    pending = self._pending.get(ws)
    event = self._events.get(ws)
    if pending is None or event is None:
      return
    pending[device] = wire          # latest-only per service
    pending.move_to_end(device)
    while len(pending) > self.MAX_SERVICES_PER_CLIENT:
      pending.popitem(last=False)
    event.set()
    task = self._senders.get(ws)
    if task is None or task.done():
      self._senders[ws] = asyncio.create_task(self._sender_loop(ws))

  async def _sender_loop(self, ws) -> None:
    try:
      while ws in self._ws_services and not getattr(ws, "closed", True):
        pending = self._pending.get(ws)
        event = self._events.get(ws)
        if pending is None or event is None:
          break
        if not pending:
          event.clear()
          if not pending:
            await event.wait()
          continue
        _device, wire = pending.popitem(last=False)
        try:
          await asyncio.wait_for(ws.send_bytes(wire), timeout=self.SEND_TIMEOUT)
        except Exception:
          logger.info("carrot_server: dropping slow raw client")
          await self.unregister(ws)
          try:
            await ws.close(code=self.CLOSE_SEND_TIMEOUT, message=b"send_timeout")
          except Exception:
            pass
          break
    except asyncio.CancelledError:
      raise
    except Exception:
      logger.exception("carrot_server: raw sender loop stopped")
    finally:
      if self._senders.get(ws) is asyncio.current_task():
        self._senders.pop(ws, None)
