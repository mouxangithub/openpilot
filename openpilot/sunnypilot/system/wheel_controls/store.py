"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Pure storage and parsing for the generic input layer (wheel controls).

Answers a different question than carrot.bluetooth: that module owns *paired Bluetooth
remotes* with a fixed cruise/lane action vocabulary; this layer lets ANY external input
device on an external bus (USB or Bluetooth HID gamepads, push-button panels) map its
buttons onto slots. Slot meaning:

- slots 0..2 execute the carrot favorite slots (delegated over HTTP to the carrot server,
  so the onroad/internal-session write guards are inherited, not reimplemented);
- slots 3..12 execute controller actions: the driving-personality cycle (a registered
  param, written directly) and pass-through cruise/lane actions published into the
  existing /dev/shm/carrot-bluetooth command channel, which cruise.py and
  desire_helper.py already consume. No new controls code, no new params.

Storage (deliberately param-free - zero new params_keys.h entries, zero libparams):
- ``<state>/wheel_controls.json``       persistent config: mappings, action slots,
  master switch, joystick device. Server-owned and edited via the web API; the daemon
  appends learned mappings. Both sides write with atomic replace, and edits are
  rare, user-driven and offroad-gated, so the read-modify-write overlap window is
  negligible (documented, accepted).
- ``/dev/shm/carrot-wheel/control.json`` server -> daemon requests (learn/test), volatile.
- ``/dev/shm/carrot-wheel/status.json``  daemon -> server liveness/learning state, volatile.

This module is stdlib-only and PC-importable: no Params, no cereal, no hardware.
"""
import hashlib
import json
import os
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openpilot.sunnypilot.carrot.bluetooth.model import ACTIONS, COMMAND_TTL, CommandWriter, atomic_json, read_json

# ------------------------------- constants -----------------------------------

FAVORITE_SLOT_COUNT = 3
ACTION_SLOT_COUNT = 10
MAPPING_SLOT_COUNT = FAVORITE_SLOT_COUNT + ACTION_SLOT_COUNT

ACTION_CYCLE_PERSONALITY = "cyclePersonality"
# Pass-through actions: the exact vocabulary the existing consumers accept
# (openpilot/selfdrive/car/cruise.py CommandReader('cruise') and
# openpilot/selfdrive/controls/lib/desire_helper.py CommandReader('lane')).
PASSTHROUGH_ACTIONS = tuple(action for action in ACTIONS if action != "none")
CONTROLLER_ACTION_KEYS = {ACTION_CYCLE_PERSONALITY, *PASSTHROUGH_ACTIONS}

CONTROLLER_ACTION_OPTIONS = (
  {"key": ACTION_CYCLE_PERSONALITY, "label": "Cycle Driving Personality",
   "description": "Cycles aggressive -> standard -> relaxed. Requires longitudinal control; refused in Safe Mode."},
  *[{"key": action, "label": action, "description": "Published to the carrot cruise/lane command channel"}
    for action in PASSTHROUGH_ACTIONS],
)

LEARN_TIMEOUT_SECONDS = 20.0
DEVICE_SCAN_INTERVAL_SECONDS = 1.0
STATUS_INTERVAL_SECONDS = 0.5
CONTROL_POLL_SECONDS = 0.25

EV_KEY = 1
EV_ABS = 3
KEY_DOWN = 1
ABS_HAT0X = 16
ABS_HAT3Y = 23
HAT_EVENT_BASE = 0x10000
# Only external buses: 0x0003 = USB, 0x0005 = Bluetooth. The built-in touchscreen sits on
# an internal bus and is filtered out here - that is the whole "don't fight the panel" story.
EXTERNAL_INPUT_BUSES = {0x0003, 0x0005}
INPUT_EVENT = struct.Struct("@llHHi")
MODALIAS_RE = re.compile(r"input:b([0-9a-f]{4})v([0-9a-f]{4})p([0-9a-f]{4})e([0-9a-f]{4})", re.IGNORECASE)

try:
  from inputs import KEYS_AND_BUTTONS  # pylint: disable=import-outside-toplevel
  KEY_NAMES: dict[int, str] = dict(KEYS_AND_BUTTONS)
except ImportError:
  KEY_NAMES = {}

# ------------------------------- filesystem ----------------------------------


def _state_root() -> str:
  # Same layout decision as carrot/server/config.py: /data/carrot/state on device,
  # CARROT_DATA_DIR override, temp-dir fallback on a development host.
  override = os.getenv("CARROT_DATA_DIR")
  if override:
    return os.path.join(override, "state")
  if os.path.isdir("/data"):
    return "/data/carrot/state"
  return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".state")


def default_config_path() -> str:
  return os.path.join(_state_root(), "wheel_controls.json")


RUNTIME_ROOT = Path("/dev/shm/carrot-wheel")
CONTROL_PATH = RUNTIME_ROOT / "control.json"
STATUS_PATH = RUNTIME_ROOT / "status.json"

DEFAULT_CONFIG: dict[str, Any] = {
  "mappings": [],
  "action_slots": [{"enabled": False, "key": None, "label": "", "value": None} for _ in range(ACTION_SLOT_COUNT)],
  "enabled": False,
  "joystick_device": "",
}

# A wheel-commands peer address: the readers do not validate addresses, but a distinct
# prefix keeps events attributable and stops the bluetooth daemon's cancellation
# bookkeeping from ever matching ours.
PEER_ADDRESS_PREFIX = "wheel:"


# ------------------------------- normalization --------------------------------


def mapping_id(device_id: str, code: int) -> str:
  return hashlib.sha256(f"{device_id}:{code}".encode()).hexdigest()[:16]


def event_name(code: int) -> str:
  if HAT_EVENT_BASE <= code < HAT_EVENT_BASE + (ABS_HAT3Y - ABS_HAT0X + 1) * 2:
    offset = code - HAT_EVENT_BASE
    axis = ABS_HAT0X + offset // 2
    positive = bool(offset % 2)
    hat = (axis - ABS_HAT0X) // 2
    vertical = bool((axis - ABS_HAT0X) % 2)
    direction = ("DOWN" if positive else "UP") if vertical else ("RIGHT" if positive else "LEFT")
    return f"DPAD_{direction}" if hat == 0 else f"HAT_{hat}_{direction}"
  return KEY_NAMES.get(code, f"KEY_{code}")


def hat_event_code(axis: int, value: int) -> int:
  return HAT_EVENT_BASE + (axis - ABS_HAT0X) * 2 + int(value > 0)


def normalize_mappings(value: Any) -> list[dict[str, Any]]:
  if isinstance(value, bytes):
    value = value.decode("utf-8", errors="replace")
  if isinstance(value, str):
    try:
      value = json.loads(value)
    except json.JSONDecodeError:
      return []
  if not isinstance(value, list):
    return []

  normalized: list[dict[str, Any]] = []
  seen: set[tuple[str, int]] = set()
  for raw in value:
    if not isinstance(raw, dict):
      continue
    device_id = str(raw.get("device_id") or "").strip()
    name = str(raw.get("device_name") or "External input").strip()[:96]
    try:
      code = int(raw.get("event_code"))
      slot = int(raw.get("slot"))
    except (TypeError, ValueError):
      continue
    if not device_id or code < 0 or not 0 <= slot < MAPPING_SLOT_COUNT:
      continue
    signature = (device_id, code)
    if signature in seen:
      continue
    seen.add(signature)
    normalized.append({
      "id": mapping_id(device_id, code),
      "device_id": device_id,
      "device_name": name,
      "event_code": code,
      "event_name": str(raw.get("event_name") or event_name(code))[:64],
      "slot": slot,
    })
  return normalized


def default_action_slots() -> list[dict[str, Any]]:
  return [{"enabled": False, "key": None, "label": ""} for _ in range(ACTION_SLOT_COUNT)]


def normalize_action_slots(value: Any) -> list[dict[str, Any]]:
  if isinstance(value, bytes):
    value = value.decode("utf-8", errors="replace")
  if isinstance(value, str):
    try:
      value = json.loads(value)
    except json.JSONDecodeError:
      value = []
  if not isinstance(value, list):
    value = []

  slots = default_action_slots()
  for index, raw in enumerate(value[:ACTION_SLOT_COUNT]):
    if not isinstance(raw, dict):
      continue
    key = str(raw.get("key") or "").strip() or None
    if key is not None and key not in CONTROLLER_ACTION_KEYS:
      key = None
    label = str(raw.get("label") or "").strip()[:64] if key else ""
    slots[index] = {"enabled": key is not None, "key": key, "label": label}
  return slots


def sanitize_config(raw: dict[str, Any] | None) -> dict[str, Any]:
  raw = raw if isinstance(raw, dict) else {}
  return {
    "mappings": normalize_mappings(raw.get("mappings")),
    "action_slots": normalize_action_slots(raw.get("action_slots")),
    "enabled": bool(raw.get("enabled")),
    "joystick_device": str(raw.get("joystick_device") or "").strip()[:128],
  }


def read_config(path: str | Path | None = None) -> dict[str, Any]:
  try:
    with open(path or default_config_path(), encoding="utf-8") as f:
      raw = json.load(f)
  except Exception:
    return json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
  return sanitize_config(raw if isinstance(raw, dict) else {})


def write_config(config: dict[str, Any], path: str | Path | None = None) -> dict[str, Any]:
  clean = sanitize_config(config)
  target = str(path or default_config_path())
  os.makedirs(os.path.dirname(target), exist_ok=True)
  atomic_json(Path(target), clean)
  return clean


def update_config(updates: dict[str, Any], path: str | Path | None = None) -> dict[str, Any]:
  updates = updates if isinstance(updates, dict) else {}
  current = read_config(path)
  for key in ("mappings", "action_slots", "enabled", "joystick_device"):
    if key in updates:
      current[key] = updates[key]
  return write_config(current, path)


def read_control(path: str | Path | None = None) -> dict[str, Any]:
  value = read_json(Path(path) if path else CONTROL_PATH, {})
  return value if isinstance(value, dict) else {}


def write_control(control: dict[str, Any], path: str | Path | None = None) -> dict[str, Any]:
  target = Path(path) if path else CONTROL_PATH
  target.parent.mkdir(parents=True, exist_ok=True)
  atomic_json(target, control)
  return control


def read_status(path: str | Path | None = None) -> dict[str, Any]:
  value = read_json(Path(path) if path else STATUS_PATH, {})
  return value if isinstance(value, dict) else {}


# ------------------------------- device discovery -----------------------------


@dataclass(frozen=True)
class InputSource:
  path: str
  device_id: str
  name: str
  bus: int
  vendor: int
  product: int
  phys: str = ""
  uniq: str = ""
  joystick_capable: bool = False

  def serialize(self) -> dict[str, Any]:
    return {
      "path": self.path,
      "device_id": self.device_id,
      "name": self.name,
      "bus": self.bus,
      "vendor": self.vendor,
      "product": self.product,
      "joystick_capable": self.joystick_capable,
    }


def _read_text(path: Path) -> str:
  try:
    return path.read_text(encoding="utf-8", errors="replace").strip()
  except OSError:
    return ""


def inspect_input_source(path: str, sysfs_root: str = "/sys/class/input") -> InputSource | None:
  event_name_ = Path(path).name
  sysfs = Path(sysfs_root) / event_name_ / "device"
  match = MODALIAS_RE.match(_read_text(sysfs / "modalias"))
  if match is None:
    return None

  bus, vendor, product, _version = (int(value, 16) for value in match.groups())
  if bus not in EXTERNAL_INPUT_BUSES:
    return None

  name = _read_text(sysfs / "name") or "External input"
  identity = f"{bus:04x}:{vendor:04x}:{product:04x}:{name.casefold()}:{_read_text(sysfs / 'uniq').casefold()}"
  device_id = hashlib.sha256(identity.encode()).hexdigest()[:20]
  joystick_capable = any(sysfs.resolve().glob("js*"))
  return InputSource(path, device_id, name, bus, vendor, product,
                     _read_text(sysfs / "phys"), _read_text(sysfs / "uniq"), joystick_capable)


def connected_input_sources(input_root: str = "/dev/input", sysfs_root: str = "/sys/class/input") -> list[InputSource]:
  if not Path(input_root).is_dir():
    return []
  return [source for path in sorted(Path(input_root).glob("event*"))
          if (source := inspect_input_source(str(path), sysfs_root)) is not None]


# ------------------------------- command channel ------------------------------


class MergingCommandWriter(CommandWriter):
  """CommandWriter that preserves events other writers (the bluetooth daemon) put in
  the same journal instead of clobbering them: read, drop expired, append, replace."""

  def send_merged(self, address: str, action: str, now: float) -> None:
    channel = "lane" if action in ("laneLeft", "laneRight") else "cruise"
    path = self.root / f"{channel}.json"
    payload = read_json(path, {})
    events = payload.get("events") if isinstance(payload, dict) and isinstance(payload.get("events"), list) else []
    kept = [event for event in events
            if isinstance(event, dict) and isinstance(event.get("time"), (int, float))
            and 0 <= now - event["time"] <= COMMAND_TTL]
    self.events[channel] = kept
    self.send(address, action, now)


def peer_address(device_id: str) -> str:
  return f"{PEER_ADDRESS_PREFIX}{device_id}"
