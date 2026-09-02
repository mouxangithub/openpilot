#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import json
import socket
import threading

from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper, config_realtime_process
from openpilot.common.swaglog import cloudlog
import openpilot.cereal.messaging as messaging


UDP_BUFFER_SIZE = 4096
DEFAULT_RATE = 10.  # Hz
PACKET_TIMEOUT_SEC = 3.0  # reset state if no packet arrives within this window

# Expected JSON keys from the Amap phone/app UDP sender.  The protocol is
# intentionally minimal: the app publishes the lane/blind-spot state that it
# derives from the streamed camera/vehicle data.
LEFT_BLIND_KEY = "leftBlind"
RIGHT_BLIND_KEY = "rightBlind"
LINE_VALID_KEY = "lineValid"
LEFT_LINE_KEY = "leftLine"
RIGHT_LINE_KEY = "rightLine"

# Optional metadata keys used for stale-packet detection.
SEQ_KEY = "seq"
TIMESTAMP_KEY = "timestamp"


class AmapNaviServer:
  """UDP receiver for Amap navigation / ADAS data.

  Listens on the port configured by ``AmapNaviUdpPort`` and publishes
  ``amapNaviSP`` at ``DEFAULT_RATE`` whenever ``AmapEnabled`` is true.

  The wire format is UTF-8 JSON.  Required fields:

  - ``leftBlind`` (int): 0 = clear, >0 = vehicle/object detected in the left
    blind spot.
  - ``rightBlind`` (int): same for the right side.
  - ``lineValid`` (bool): whether lane-line information is valid.
  - ``leftLine`` (int): left lane-line type / state code.
  - ``rightLine`` (int): right lane-line type / state code.

  Optional fields:

  - ``seq`` (int): monotonically increasing sequence number (per sender).
  - ``timestamp`` (float): sender epoch time in seconds; used to detect stale
    packets when the sender clock is reliable.
  """

  def __init__(self):
    self.params = Params()
    self.pm = messaging.PubMaster(['amapNaviSP'])

    self._sock: socket.socket | None = None
    self._port = 0
    self._lock = threading.Lock()
    self._last_packet_mono = 0.0
    self._last_seq: int | None = None

    self._state = {
      'leftBlind': 0,
      'rightBlind': 0,
      'lineValid': False,
      'leftLine': 0,
      'rightLine': 0,
    }

  def _ensure_socket(self, port: int) -> bool:
    with self._lock:
      if self._sock is not None and self._port == port:
        return True

      if self._sock is not None:
        try:
          self._sock.close()
        except Exception:
          pass
        self._sock = None

      try:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(('0.0.0.0', port))
        self._sock.setblocking(False)
        self._port = port
        cloudlog.info(f"mapd_amap: listening on UDP port {port}")
        return True
      except Exception as e:
        cloudlog.error(f"mapd_amap: failed to bind UDP port {port}: {e}")
        self._sock = None
        return False

  def _close_socket(self) -> None:
    with self._lock:
      if self._sock is not None:
        try:
          self._sock.close()
        except Exception:
          pass
        self._sock = None
        self._port = 0

  def _parse_packet(self, data: bytes) -> dict | None:
    try:
      decoded = data.decode('utf-8')
      msg = json.loads(decoded)
      if not isinstance(msg, dict):
        return None
      return msg
    except Exception:
      return None

  def _update_state(self, msg: dict, recv_mono: float) -> None:
    """Apply a parsed UDP packet, ignoring obvious out-of-order duplicates."""
    seq = msg.get(SEQ_KEY)
    if isinstance(seq, (int, float)):
      seq = int(seq)
      if self._last_seq is not None and 0 <= seq < self._last_seq:
        # Accept the packet but do not treat it as a fresh update; this avoids
        # blinking state when the sender restarts and sequence wraps.
        return
      self._last_seq = seq

    def _int_or_default(value, default: int) -> int:
      if isinstance(value, bool):
        return int(value)
      if isinstance(value, (int, float)):
        return int(value)
      return default

    def _bool_or_default(value, default: bool) -> bool:
      if isinstance(value, bool):
        return value
      if isinstance(value, (int, float)):
        return bool(value)
      return default

    self._state['leftBlind'] = _int_or_default(msg.get(LEFT_BLIND_KEY), self._state['leftBlind'])
    self._state['rightBlind'] = _int_or_default(msg.get(RIGHT_BLIND_KEY), self._state['rightBlind'])
    self._state['lineValid'] = _bool_or_default(msg.get(LINE_VALID_KEY), self._state['lineValid'])
    self._state['leftLine'] = _int_or_default(msg.get(LEFT_LINE_KEY), self._state['leftLine'])
    self._state['rightLine'] = _int_or_default(msg.get(RIGHT_LINE_KEY), self._state['rightLine'])
    self._last_packet_mono = recv_mono

  def _maybe_expire_state(self, now_mono: float) -> None:
    """Clear stale ADAS state if the sender has gone silent."""
    if self._last_packet_mono == 0.0:
      return
    if now_mono - self._last_packet_mono > PACKET_TIMEOUT_SEC:
      self._state = {
        'leftBlind': 0,
        'rightBlind': 0,
        'lineValid': False,
        'leftLine': 0,
        'rightLine': 0,
      }
      self._last_packet_mono = 0.0
      self._last_seq = None
      cloudlog.info("mapd_amap: state expired due to packet timeout")

  def _drain_packets(self) -> None:
    with self._lock:
      if self._sock is None:
        return

    while True:
      try:
        with self._lock:
          if self._sock is None:
            break
          data, _ = self._sock.recvfrom(UDP_BUFFER_SIZE)
        msg = self._parse_packet(data)
        if msg is not None:
          self._update_state(msg, self._mono_now())
      except BlockingIOError:
        break
      except Exception as e:
        cloudlog.error(f"mapd_amap: UDP receive error: {e}")
        break

  def _publish(self) -> None:
    msg = messaging.new_message('amapNaviSP')
    msg.valid = True
    navi = msg.amapNaviSP
    navi.leftBlind = self._state['leftBlind']
    navi.rightBlind = self._state['rightBlind']
    navi.lineValid = self._state['lineValid']
    navi.leftLine = self._state['leftLine']
    navi.rightLine = self._state['rightLine']
    self.pm.send('amapNaviSP', msg)

  def _mono_now(self) -> float:
    # openpilot bans time.time() except for Raylib; all daemon timing uses
    # time.monotonic().
    import time as _time
    return _time.monotonic()

  def tick(self) -> None:
    enabled = self.params.get_bool("AmapEnabled")
    port = self.params.get("AmapNaviUdpPort", return_default=True) or 0

    if not enabled or port <= 0:
      self._close_socket()
      return

    if not self._ensure_socket(port):
      return

    self._drain_packets()
    self._maybe_expire_state(self._mono_now())
    self._publish()


def main_thread():
  config_realtime_process([0, 1, 2, 3], 5)

  server = AmapNaviServer()
  rk = Ratekeeper(DEFAULT_RATE, print_delay_threshold=None)

  while True:
    server.tick()
    rk.keep_time()


def main():
  main_thread()


if __name__ == "__main__":
  main()
