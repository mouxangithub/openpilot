"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Web API surface for the wheel_controls input layer.

Thin orchestration over ``sunnypilot.system.wheel_controls.store`` (the pure module the
daemon also uses): config CRUD, learn/test requests via the volatile control file, and
status aggregation. All heavy validation lives in store; this layer only adds the
engaged-refusal and request-shape handling the web contract needs.
"""
import uuid
from typing import Any

from openpilot.sunnypilot.system.wheel_controls import store


class WheelControlsError(Exception):
  """Refusal with a machine-readable code for the client."""

  def __init__(self, code: str, message: str):
    super().__init__(message)
    self.code = code
    self.message = message


def _engaged_reader() -> bool:
  # Lazy: keeps this module importable on PC without the Params chain.
  try:
    from openpilot.common.params import Params  # pylint: disable=import-outside-toplevel

    return bool(Params().get_bool("IsEngaged"))
  except Exception:
    return False


def _refuse_if_engaged() -> None:
  if _engaged_reader():
    raise WheelControlsError("engaged", "disengage openpilot first")


def get_config() -> dict[str, Any]:
  return store.read_config()


def update_config(updates: dict[str, Any]) -> dict[str, Any]:
  _refuse_if_engaged()
  clean = store.update_config(updates)
  # A mapping-less layer does nothing, so an empty config is forced back to disabled -
  # mirrors StarPilot's "enabled = bool(mappings or joystick)" invariant.
  if not clean["mappings"] and not clean["joystick_device"]:
    clean = store.update_config({"enabled": False})
  return clean


def delete_mapping(identifier: str) -> dict[str, Any]:
  _refuse_if_engaged()
  config = store.read_config()
  kept = [mapping for mapping in config["mappings"] if mapping.get("id") != str(identifier)]
  if len(kept) == len(config["mappings"]):
    raise WheelControlsError("not_found", f"mapping {identifier} does not exist")
  config["mappings"] = kept
  return store.write_config(config)


def clear_mappings() -> dict[str, Any]:
  _refuse_if_engaged()
  return store.update_config({"mappings": [], "enabled": False})


def set_action_slot(index: int, key: str | None, label: str) -> dict[str, Any]:
  _refuse_if_engaged()
  if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < store.ACTION_SLOT_COUNT:
    raise WheelControlsError("bad_slot", f"action slot index must be 0..{store.ACTION_SLOT_COUNT - 1}")
  key = str(key or "").strip() or None
  if key is not None and key not in store.CONTROLLER_ACTION_KEYS:
    raise WheelControlsError("unknown_action", f"{key} is not an available controller action")
  config = store.read_config()
  slots = store.normalize_action_slots(config.get("action_slots"))
  slots[index] = {"enabled": key is not None, "key": key, "label": label if key else ""}
  return store.update_config({"action_slots": slots})


def _request_control(**updates: Any) -> dict[str, Any]:
  _refuse_if_engaged()
  control = store.read_control()
  control.update(updates)
  control["token"] = uuid.uuid4().hex
  return store.write_control(control)


def start_learning(slot: int) -> dict[str, Any]:
  if not isinstance(slot, int) or isinstance(slot, bool) or not 0 <= slot < store.MAPPING_SLOT_COUNT:
    raise WheelControlsError("bad_slot", f"slot must be 0..{store.MAPPING_SLOT_COUNT - 1}")
  return _request_control(learn_slot=slot + 1)


def cancel_learning() -> dict[str, Any]:
  return _request_control(learn_slot=None)


def set_testing(active: bool) -> dict[str, Any]:
  if not isinstance(active, bool):
    raise WheelControlsError("bad_request", "active must be a boolean")
  return _request_control(test_active=active)


def public_status(now=None) -> dict[str, Any]:
  """Merged view for the web client: daemon liveness + config + connected devices."""
  import time  # pylint: disable=import-outside-toplevel

  now = time.monotonic() if now is None else now
  status = store.read_status()
  updated_at = float(status.get("updated_at", 0.0) or 0.0)
  # CLOCK_MONOTONIC is system-wide on Linux, so a cross-process freshness check is valid.
  status["available"] = bool(updated_at and 0 <= now - updated_at < 3.0)
  config = store.read_config()
  status["config"] = config
  status["action_options"] = store.CONTROLLER_ACTION_OPTIONS
  if not status["available"]:
    status["devices"] = [source.serialize() for source in
                         store.connected_input_sources()]
  for device in status.get("devices", []):
    device["joystick_enabled"] = device.get("device_id") == config.get("joystick_device")
  status["joystick_device"] = config.get("joystick_device")
  return status
