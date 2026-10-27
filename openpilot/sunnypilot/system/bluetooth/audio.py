"""
A2DP audio output: streams soundd's PCM to a paired Bluetooth audio device
through `aplay` + the bluez-alsa ALSA plugin.

Ported from StarPilot's `starpilot/system/bluetooth/audio.py` unchanged except
for the module import paths. NOTE (AGNOS): `aplay -D bluealsa:DEV=...` requires
the bluez-alsa plugin, which AGNOS does not ship.
"""
import queue
import re
import shutil
import subprocess
import threading
import time

import numpy as np

from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog


ADDRESS_RE = re.compile(r"^(?:[0-9A-F]{2}:){5}[0-9A-F]{2}$")


class BluetoothAudioSink:
  def __init__(self, params: Params | None = None, popen_factory=subprocess.Popen, start_thread: bool = True):
    self.params = params or Params()
    self._popen_factory = popen_factory
    self._queue: queue.Queue[bytes] = queue.Queue(maxsize=3)
    self._lock = threading.Lock()
    self._process = None
    self._address = ""
    self._healthy = False
    self._last_write = 0.0
    self._exit = False
    self._aplay = shutil.which("aplay")
    self._thread = threading.Thread(target=self._run, daemon=True)
    if start_thread:
      self._thread.start()

  @property
  def healthy(self) -> bool:
    if not self._lock.acquire(blocking=False):
      return False
    try:
      process_alive = self._process is not None and self._process.poll() is None
      return self._healthy and process_alive and time.monotonic() - self._last_write < 1.0
    finally:
      self._lock.release()

  def close(self) -> None:
    self._exit = True
    self._stop_process()
    if self._thread.is_alive():
      self._thread.join(timeout=1.0)

  def desired_address(self) -> str:
    if not self.params.get_bool("BluetoothEnabled"):
      return ""
    address = (self.params.get("BluetoothAudioAddress", encoding="utf-8") or "").strip().upper()
    if isinstance(address, bytes):
      address = address.decode("utf-8", errors="ignore")
    return address if ADDRESS_RE.fullmatch(address) else ""

  @staticmethod
  def pcm_bytes(samples: np.ndarray) -> bytes:
    mono = np.clip(samples, -1.0, 1.0)
    pcm = (mono * 32767.0).astype(np.int16)
    return np.column_stack((pcm, pcm)).tobytes()

  def submit(self, samples: np.ndarray) -> bool:
    if self._aplay is None or not self._address:
      return False
    try:
      self._queue.put_nowait(self.pcm_bytes(samples))
    except queue.Full:
      with self._lock:
        self._healthy = False
      return False
    return self.healthy

  def _start_process(self, address: str) -> None:
    command = [
      self._aplay,
      "-q",
      "-D", f"bluealsa:DEV={address},PROFILE=a2dp",
      "-t", "raw",
      "-f", "S16_LE",
      "-c", "2",
      "-r", "48000",
    ]
    process = self._popen_factory(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, bufsize=0)
    with self._lock:
      self._process = process
      self._address = address
      self._healthy = False
      self._last_write = 0.0

  def _stop_process(self) -> None:
    with self._lock:
      process = self._process
      self._process = None
      self._address = ""
      self._healthy = False
      self._last_write = 0.0
    if process is not None:
      try:
        process.terminate()
        process.wait(timeout=1.0)
      except Exception:
        try:
          process.kill()
        except Exception:
          pass
    while True:
      try:
        self._queue.get_nowait()
      except queue.Empty:
        break

  def _run(self) -> None:
    while not self._exit:
      address = self.desired_address()
      with self._lock:
        current_address = self._address
        process = self._process
      if not address or self._aplay is None:
        if process is not None:
          self._stop_process()
        time.sleep(0.2)
        continue
      if process is None or process.poll() is not None or address != current_address:
        self._stop_process()
        try:
          self._start_process(address)
        except Exception:
          cloudlog.exception("Unable to start Bluetooth audio output")
          time.sleep(1.0)
          continue

      try:
        block = self._queue.get(timeout=0.5)
      except queue.Empty:
        continue
      try:
        with self._lock:
          process = self._process
        if process is None or process.stdin is None:
          raise BrokenPipeError
        process.stdin.write(block)
        with self._lock:
          self._healthy = True
          self._last_write = time.monotonic()
      except Exception:
        cloudlog.warning("Bluetooth audio output disconnected")
        self._stop_process()
        time.sleep(0.5)
