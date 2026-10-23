"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""wheel_controlsd: generic external-input daemon (USB / Bluetooth HID devices).

Reads /dev/input/event* directly with the stdlib (os.open + struct on the kernel's
input_event) - no evdev package, no C extension, nothing device-specific to install.
Only devices on an external bus (USB / Bluetooth, from /sys modalias) are accepted, so
the built-in touchscreen is invisible to this daemon by construction.

Heavy imports (Params, cereal) are deferred into functions/bodies so the module imports
cleanly on a development host and tests can drive the daemon with fakes.

Coexistence with carrot_bluetooth: that daemon owns paired Bluetooth *remotes* with a
fixed mapping; this daemon is opt-in (config "enabled"), and a device configured in one
should not be mapped in the other - both daemons receive every event of a node.
"""
import json
import logging
import os
import selectors
import time
import urllib.request
from pathlib import Path

from openpilot.sunnypilot.system.wheel_controls import store
from openpilot.sunnypilot.system.wheel_controls.store import (
  ACTION_CYCLE_PERSONALITY,
  CONTROL_POLL_SECONDS,
  DEVICE_SCAN_INTERVAL_SECONDS,
  EV_ABS,
  EV_KEY,
  FAVORITE_SLOT_COUNT,
  KEY_DOWN,
  LEARN_TIMEOUT_SECONDS,
  MAPPING_SLOT_COUNT,
  STATUS_INTERVAL_SECONDS,
  InputSource,
  hat_event_code,
  normalize_mappings,
  peer_address,
)

logger = logging.getLogger("openpilot.sunnypilot.system.wheel_controls")


def cycle_driving_personality(params) -> bool:
  """Select the next longitudinal personality. Ported from StarPilot's wheel_controls:
  refused in Safe Mode and without longitudinal control; the key is registered and
  designed for live (onroad) changes, so no restart or offroad gate is needed."""
  try:
    if params.get_bool("SafeMode"):
      return False
    from cereal import car, log  # pylint: disable=import-outside-toplevel  # device-only

    cp_bytes = params.get("CarParams" if params.get_bool("IsOnroad") else "CarParamsPersistent")
    if not cp_bytes:
      return False
    with car.CarParams.from_bytes(cp_bytes) as cp:
      available = params.get_bool("AlphaLongitudinalEnabled") if cp.alphaLongitudinalAvailable else cp.openpilotLongitudinalControl
    if not available:
      return False

    profiles = (int(log.LongitudinalPersonality.aggressive),
                int(log.LongitudinalPersonality.standard),
                int(log.LongitudinalPersonality.relaxed))
    current = params.get_int("LongitudinalPersonality")
    if current not in profiles:
      return False
    if params.get_bool("SafeMode"):  # re-checked after the slow reads
      return False
    params.put_int("LongitudinalPersonality", profiles[(profiles.index(current) + 1) % len(profiles)])
    return True
  except Exception:
    logger.exception("wheel controls: personality cycle failed")
    return False


class WheelControlsDaemon:
  def __init__(self, input_root="/dev/input", sysfs_root="/sys/class/input", *,
               config_path=None, control_path=None, status_path=None,
               params=None, clock=time.monotonic, publisher=None, apply_favorite=None):
    self.input_root = Path(input_root)
    self.sysfs_root = sysfs_root
    self.config_path = config_path or store.default_config_path()
    self.control_path = control_path
    self.status_path = status_path
    self._params = params
    self.clock = clock
    self.publisher = publisher
    self.apply_favorite = apply_favorite

    self.selector = selectors.DefaultSelector()
    self.sources: dict[int, InputSource] = {}
    self.buffers: dict[int, bytearray] = {}
    self.hat_values: dict[tuple[int, int], int] = {}
    self.pressed_keys: set[tuple[int, int]] = set()

    self.last_control_token: str | None = None
    self.learning_slot: int | None = None
    self.learning_deadline = 0.0
    self.last_learned: dict | None = None
    self.last_tested: dict | None = None
    self.testing = False
    self.last_action: dict | None = None
    self.last_error: str | None = None
    self.last_scan = 0.0
    self.last_status = 0.0
    self.last_control_poll = 0.0

  # ------------------------------- seams --------------------------------------

  @property
  def params(self):
    if self._params is None:
      from openpilot.common.params import Params  # pylint: disable=import-outside-toplevel
      self._params = Params()
    return self._params

  def _publisher(self):
    if self.publisher is None:
      self.publisher = store.MergingCommandWriter()
    return self.publisher

  def _apply_favorite_slot(self, slot: int) -> bool:
    if self.apply_favorite is not None:
      return self.apply_favorite(slot)
    # Delegate to the carrot server: the apply endpoint funnels through
    # services.params.set_param_value, so every write guard is inherited here.
    try:
      from openpilot.sunnypilot.carrot.server.config import DEFAULT_PORT  # pylint: disable=import-outside-toplevel
      port = int(os.getenv("CARROT_WEB_PORT", DEFAULT_PORT))
    except Exception:
      port = 7000
    request = urllib.request.Request(
      f"http://127.0.0.1:{port}/api/setting_favorites/apply",
      data=json.dumps({"slot": slot}).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=10.0) as response:  # noqa: S310 - localhost
      payload = json.load(response)
    if not payload.get("ok", False):
      raise RuntimeError(payload.get("error") or "favorite slot apply refused")
    return True

  def is_offroad(self) -> bool:
    try:
      return self.params.get_bool("IsOffroad")
    except Exception:
      return True  # cannot read: behave like the safe offroad default for learning gates

  # ------------------------------- lifecycle ----------------------------------

  def close(self) -> None:
    for fd in list(self.sources):
      self._remove(fd)
    self.selector.close()

  def _remove(self, fd: int) -> None:
    try:
      self.selector.unregister(fd)
    except Exception:
      pass
    try:
      os.close(fd)
    except OSError:
      pass
    self.sources.pop(fd, None)
    self.buffers.pop(fd, None)
    self.hat_values = {key: value for key, value in self.hat_values.items() if key[0] != fd}
    self.pressed_keys = {key for key in self.pressed_keys if key[0] != fd}

  # ------------------------------- device scan --------------------------------

  def _scan_devices(self) -> None:
    current_paths = {source.path for source in self.sources.values()}
    existing_paths = set(self.input_root.glob("event*")) if self.input_root.is_dir() else set()
    for fd, source in list(self.sources.items()):
      if Path(source.path) not in existing_paths:
        self._remove(fd)

    for path in sorted(existing_paths):
      path_text = str(path)
      if path_text in current_paths:
        continue
      source = store.inspect_input_source(path_text, self.sysfs_root)
      if source is None:
        continue
      try:
        fd = os.open(path_text, os.O_RDONLY | os.O_NONBLOCK)
        self.selector.register(fd, selectors.EVENT_READ)
      except OSError:
        continue
      self.sources[fd] = source
      self.buffers[fd] = bytearray()
      logger.info("wheel controls: watching %s (%s)", path_text, source.name)

  # ------------------------------- learn / test -------------------------------

  def _update_control(self, now: float) -> None:
    if now - self.last_control_poll < CONTROL_POLL_SECONDS:
      return
    self.last_control_poll = now
    control = store.read_control(self.control_path)
    token = control.get("token")
    if not token or token == self.last_control_token:
      return
    self.last_control_token = token

    slot = control.get("learn_slot")
    if slot is None:
      self.learning_slot = None
    else:
      try:
        slot = int(slot)
      except (TypeError, ValueError):
        slot = 0
      if 1 <= slot <= MAPPING_SLOT_COUNT:
        self.learning_slot = slot - 1
        self.learning_deadline = now + LEARN_TIMEOUT_SECONDS
      else:
        self.learning_slot = None

    self.testing = bool(control.get("test_active"))
    if self.testing:
      self.last_tested = None

  def _update_learning(self, now: float) -> None:
    if not self.is_offroad() and self.learning_slot is not None:
      self.learning_slot = None  # onroad cancels learning; no control write needed
    if self.learning_slot is not None and now >= self.learning_deadline:
      self.learning_slot = None

  # ------------------------------- execution ----------------------------------

  def _record_action(self, description: dict) -> None:
    self.last_action = {**description, "at": self.clock()}

  def _execute_action(self, key: str, source: InputSource) -> bool:
    if key == ACTION_CYCLE_PERSONALITY:
      applied = cycle_driving_personality(self.params)
      self._record_action({"key": key, "applied": applied})
      return applied
    if key in store.PASSTHROUGH_ACTIONS:
      self._publisher().send_merged(peer_address(source.device_id), key, self.clock())
      self._record_action({"key": key, "applied": True})
      return True
    return False

  def _execute_slot(self, slot: int, source: InputSource) -> None:
    config = store.read_config(self.config_path)
    if slot < FAVORITE_SLOT_COUNT:
      try:
        applied = self._apply_favorite_slot(slot)
        self._record_action({"key": f"favorite:{slot}", "applied": applied})
      except Exception as exc:
        self.last_error = f"favorite slot {slot}: {exc}"
        logger.exception("wheel controls: favorite slot apply failed")
      return
    index = slot - FAVORITE_SLOT_COUNT
    slots = config.get("action_slots") or []
    if index >= len(slots):
      return
    slot_config = slots[index]
    if not slot_config.get("enabled") or not slot_config.get("key"):
      return
    if not config.get("enabled"):
      return
    key = str(slot_config["key"])
    if not self._execute_action(key, source):
      self.last_error = f"action {key} not applied"

  def _capture_mapping(self, source: InputSource, code: int) -> None:
    config = store.read_config(self.config_path)
    mappings = [mapping for mapping in (config.get("mappings") or [])
                if not (mapping["device_id"] == source.device_id and mapping["event_code"] == code)]
    learned = {
      "id": store.mapping_id(source.device_id, code),
      "device_id": source.device_id,
      "device_name": source.name,
      "event_code": code,
      "event_name": store.event_name(code),
      "slot": self.learning_slot,
    }
    mappings.append(learned)
    config["mappings"] = mappings
    config["enabled"] = True  # a learned mapping implies the layer is wanted
    store.write_config(config, self.config_path)
    self.last_learned = learned
    self.learning_slot = None
    self._record_action({"key": f"learn:{learned['id']}", "applied": True})

  def _handle_key(self, source: InputSource, code: int) -> None:
    config = store.read_config(self.config_path)
    if source.device_id == config.get("joystick_device"):
      return
    if self.learning_slot is not None:
      self._capture_mapping(source, code)
      return

    mappings = normalize_mappings(config.get("mappings"))
    if self.testing:
      mapping = next((item for item in mappings
                      if item["device_id"] == source.device_id and item["event_code"] == code), None)
      self.last_tested = {
        "mapped": mapping is not None,
        "device_name": source.name,
        "event_code": code,
        "event_name": store.event_name(code),
        "slot": mapping["slot"] if mapping is not None else None,
      }
      return

    if not config.get("enabled"):
      return
    for mapping in mappings:
      if mapping["device_id"] == source.device_id and mapping["event_code"] == code:
        try:
          self._execute_slot(mapping["slot"], source)
        except Exception:
          logger.exception("wheel control action failed")
        return

  # ------------------------------- event pump ---------------------------------

  def _read_events(self, fd: int) -> None:
    try:
      chunk = os.read(fd, store.INPUT_EVENT.size * 32)
    except BlockingIOError:
      return
    except OSError:
      self._remove(fd)
      return
    if not chunk:
      self._remove(fd)
      return

    buffer = self.buffers.get(fd)
    source = self.sources.get(fd)
    if buffer is None or source is None:
      return
    buffer.extend(chunk)
    while len(buffer) >= store.INPUT_EVENT.size:
      raw = bytes(buffer[:store.INPUT_EVENT.size])
      del buffer[:store.INPUT_EVENT.size]
      _seconds, _microseconds, event_type, code, value = store.INPUT_EVENT.unpack(raw)
      if event_type == EV_KEY:
        key = (fd, code)
        if value == 0:
          self.pressed_keys.discard(key)
        elif value == KEY_DOWN:
          if key not in self.pressed_keys:
            self.pressed_keys.add(key)
            self._handle_key(source, code)
      elif event_type == EV_ABS and store.ABS_HAT0X <= code <= store.ABS_HAT3Y:
        previous = self.hat_values.get((fd, code), 0)
        self.hat_values[(fd, code)] = value
        if value and value != previous:
          self._handle_key(source, hat_event_code(code, value))

  def _publish_status(self, now: float) -> None:
    remaining = max(0, round(self.learning_deadline - now, 1)) if self.learning_slot is not None else 0
    status = {
      "updated_at": now,
      "offroad": self.is_offroad(),
      "devices": [source.serialize() for source in sorted(self.sources.values(), key=lambda item: item.name.casefold())],
      "learning": self.learning_slot is not None,
      "learning_slot": self.learning_slot,
      "remaining_seconds": remaining,
      "last_learned": self.last_learned,
      "testing": self.testing,
      "last_tested": self.last_tested,
      "last_action": self.last_action,
      "last_error": self.last_error,
    }
    self._write_status(status)

  def _write_status(self, status: dict) -> None:
    from openpilot.sunnypilot.carrot.bluetooth.model import atomic_json  # pylint: disable=import-outside-toplevel
    target = Path(self.status_path) if self.status_path else store.STATUS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(target, status)

  def run(self) -> None:
    try:
      while True:
        now = self.clock()
        self._update_control(now)
        self._update_learning(now)
        if now - self.last_scan >= DEVICE_SCAN_INTERVAL_SECONDS:
          self._scan_devices()
          self.last_scan = now
        for key, _mask in self.selector.select(timeout=0.1):
          try:
            self._read_events(key.fd)
          except (KeyError, OSError):
            self._remove(key.fd)
        now = self.clock()
        if now - self.last_status >= STATUS_INTERVAL_SECONDS:
          self._publish_status(now)
          self.last_status = now
    finally:
      self.close()


def main() -> None:
  logging.basicConfig(level=logging.INFO)
  WheelControlsDaemon().run()


if __name__ == "__main__":
  main()
