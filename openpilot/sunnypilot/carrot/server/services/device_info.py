"""Device support services that are not plain Params reads."""
from __future__ import annotations

import re

import math
import subprocess
import threading
import time
from datetime import datetime, UTC
from copy import deepcopy
from typing import Any

from .params import HAS_PARAMS, Params, get_param_value, get_param_values
from .ssh_keys import get_ssh_key_status


# ── calibration ──────────────────────────────────────────────
def get_calibration_status() -> dict[str, Any]:
  """Parse CalibrationParams and return human-readable status."""
  if not HAS_PARAMS:
    return {"calibrated": False, "pitch": None, "yaw": None}

  params = Params()
  try:
    calib_bytes = params.get("CalibrationParams")
    if not calib_bytes:
      return {"calibrated": False, "pitch": None, "yaw": None}

    import openpilot.cereal.messaging as messaging
    from openpilot.cereal import log
    calib = messaging.log_from_bytes(calib_bytes, log.Event).liveCalibration

    uncal = 0  # cereal::LiveCalibrationData::Status::UNCALIBRATED
    try:
      uncal = log.LiveCalibrationData.Status.uncalibrated
    except Exception:
      pass

    if calib.calStatus == uncal:
      return {"calibrated": False, "pitch": None, "yaw": None}

    pitch = round(math.degrees(calib.rpyCalib[1]), 1)
    yaw = round(math.degrees(calib.rpyCalib[2]), 1)
    return {"calibrated": True, "pitch": pitch, "yaw": yaw}
  except Exception:
    return {"calibrated": False, "pitch": None, "yaw": None}

# Single source for the Device tab's parameters.
#
# The group -> parameter mapping used to exist twice: here as a flat default
# map, and again in web/js/pages/setting_device_config.js as four arrays. The
# two never disagreed, but nothing stopped them from doing so silently. The
# groups below are shipped to the browser in the settings snapshot so the web
# reads its parameter names from this list instead of restating them.
#
# Order matters: it is the order the rows are rendered in.
DEVICE_SETTING_GROUPS: tuple[tuple[str, tuple[tuple[str, Any], ...]], ...] = (
  ("Device", (
    ("DeviceType", "unknown"),
    ("DongleId", ""),
    ("HardwareSerial", ""),
    ("LanguageSetting", "main_en"),
    ("SoftwareMenu", 1),
  )),
  ("Software", (
    ("UpdaterCurrentDescription", ""),
    ("UpdaterState", ""),
    ("UpdateAvailable", False),
    ("UpdaterFetchAvailable", False),
    ("UpdateFailedCount", 0),
    ("UpdaterTargetBranch", ""),
    ("GitBranch", ""),
    ("UpdaterAvailableBranches", ""),
    ("LastUpdateTime", ""),
    ("UpdaterNewDescription", ""),
  )),
  ("Toggles", (
    ("OpenpilotEnabledToggle", False),
    ("ExperimentalMode", False),
    ("ExperimentalModeConfirmed", False),
    ("DisengageOnAccelerator", False),
    ("IsLdwEnabled", False),
    ("AlwaysOnDM", False),
    ("RecordFront", False),
    ("RecordAudio", False),
    ("IsMetric", False),
    ("LongitudinalPersonality", 1),
  )),
  ("Developer", (
    ("AdbEnabled", False),
    ("SshEnabled", False),
    ("JoystickDebugMode", False),
    ("LongitudinalManeuverMode", False),
    ("AlphaLongitudinalEnabled", False),
    ("GithubUsername", ""),
    ("GithubSshKeys", ""),
  )),
)

DEVICE_SETTING_DEFAULTS: dict[str, Any] = {
  name: default
  for _group, entries in DEVICE_SETTING_GROUPS
  for name, default in entries
}

# sunnypilot sections shown on the Device tab, in sidebar order. Membership is
# read from the same settings catalog the CarrotPilot tab serves (the
# SUNNYPILOT menu node), so the two tabs cannot disagree about which params a
# section owns. The client renders these groups generically from the catalog's
# per-param metadata; only the names are shipped here.
SP_DEVICE_MENU_GROUPS: tuple[tuple[str, str], ...] = (
  ("Models", "CARROT_SP_UI_MODELS"),
  ("Vehicle", "CARROT_SP_UI_VEHICLE"),
  ("Steering", "CARROT_SP_UI_STEERING"),
  ("Cruise", "CARROT_SP_UI_CRUISE"),
  ("Visuals", "CARROT_SP_UI_VISUALS"),
  ("Display", "CARROT_SP_UI_DISPLAY"),
  ("Navigation", "CARROT_SP_UI_NAVIGATION"),
  ("Osm", "CARROT_SP_UI_OSM"),
  ("Maps", "CARROT_SP_MAPS"),
  ("Trips", "CARROT_SP_UI_TRIPS"),
  ("Imu", "CARROT_SP_IMU"),
)

_sp_device_groups_cache: dict[str, list[str]] | None = None

# The catalog marks status-only entries in its own descriptions ("... (read-only).")
# and a few entries are actions owned by a dedicated manager block on this panel.
# Neither is a setting the user tunes, so they are dropped here - shipping them
# made the sections read as a wall of uneditable rows.
_READ_ONLY_MARKER = re.compile(r"\(read-?only\)", re.IGNORECASE)
_MANAGED_ELSEWHERE = frozenset({
  # model manager block: selection, favourites and cache live in its own UI
  "ModelManager_DownloadRef",
  "ModelManager_Favs",
  "ModelManager_ClearCache",
  # region picker / trips source / IMU start are manager-block actions
  "OsmStateName",
  "TripsDataSource",
  "ImuCalibrationRequested",
})


def _is_device_setting(entry: dict[str, Any]) -> bool:
  name = entry.get("name")
  if not name or name in _MANAGED_ELSEWHERE:
    return False
  text = f"{entry.get('descr') or ''} {entry.get('edescr') or ''}"
  return not _READ_ONLY_MARKER.search(text)


def _sp_device_setting_groups() -> dict[str, list[str]]:
  """`{groupId: [param, ...]}` for the sunnypilot sections, from the catalog menu.

  A section that is missing from the catalog (regenerated away, file absent)
  simply does not ship - the browser hides a group with no names.
  """
  global _sp_device_groups_cache
  if _sp_device_groups_cache is not None:
    return _sp_device_groups_cache

  wanted = {menu_id: group_id for group_id, menu_id in SP_DEVICE_MENU_GROUPS}
  out: dict[str, list[str]] = {}
  try:
    import json

    from openpilot.sunnypilot.carrot.server.config import DEFAULT_SETTINGS_PATH
    with open(DEFAULT_SETTINGS_PATH, encoding="utf-8") as f:
      catalog = json.load(f)
  except Exception:
    _sp_device_groups_cache = out
    return out

  by_name = {p.get("name"): p for p in catalog.get("params", []) if p.get("name")}

  def walk(nodes: Any) -> None:
    for node in nodes or []:
      group_id = wanted.get(node.get("id"))
      if group_id and group_id not in out:
        names = [
          n for n in node.get("params", [])
          if n in by_name and _is_device_setting(by_name[n])
        ]
        if names:
          out[group_id] = names
      walk(node.get("groups"))

  walk(catalog.get("menu") or [])
  # keep the sidebar order from SP_DEVICE_MENU_GROUPS, drop empty sections
  _sp_device_groups_cache = {gid: out[gid] for gid, _menu_id in SP_DEVICE_MENU_GROUPS if out.get(gid)}
  return _sp_device_groups_cache


# The Tools > Info dialog is a read-only support snapshot, not a Params
# settings group.  Keep its data contract here so it can add hardware values
# (IMEI, modem status) without pretending they are writable Params.
TOOL_DEVICE_INFO_PARAM_DEFAULTS: dict[str, Any] = {
  "DongleId": "",
  "HardwareSerial": "",
  "DevicePosition": "",
  "GitBranch": "",
  "GitCommit": "",
  "GitCommitDate": "",
  "GitPullTime": "",
}


def _text(value: Any) -> str:
  return str(value or "").strip()


def _first_text(value: Any) -> str:
  if isinstance(value, (list, tuple)):
    return next((_text(item) for item in value if _text(item)), "")
  return _text(value)


def _hardware_value(hardware: Any, method: str, default: Any = "") -> Any:
  try:
    return getattr(hardware, method)()
  except Exception:
    return default


def _boot_time() -> str:
  """Return the current OS boot timestamp without persisting device metadata."""
  try:
    with open("/proc/stat", encoding="utf-8") as stat_file:
      for line in stat_file:
        key, _, value = line.partition(" ")
        if key != "btime":
          continue
        timestamp = float(value.strip())
        return datetime.fromtimestamp(timestamp, tz=UTC).isoformat().replace("+00:00", "Z")
  except (OSError, OverflowError, ValueError):
    pass
  return ""


def get_tools_device_info() -> dict[str, Any]:
  """Return the compact, local-only device support snapshot for Tools.

  The IMEI deliberately comes from HARDWARE rather than Params: it is a modem
  identity, not a user setting, and should never enter setting history or a
  writable parameter endpoint.  Every field is best-effort so an unavailable
  modem leaves the rest of the support card usable.
  """
  values = get_param_values(list(TOOL_DEVICE_INFO_PARAM_DEFAULTS), TOOL_DEVICE_INFO_PARAM_DEFAULTS)
  device_type = "unknown"
  imei = ""
  hardware_serial = ""
  modem_version = ""
  network: dict[str, Any] = {}
  sim: dict[str, Any] = {}
  hardware = None
  try:
    from openpilot.system.hardware import HARDWARE
    hardware = HARDWARE
  except Exception:
    # Web info must remain available while hardware services are starting.
    pass
  if hardware is not None:
    device_type = _text(_hardware_value(hardware, "get_device_type", device_type)) or device_type
    try:
      imei = _text(hardware.get_imei(0))
    except Exception:
      pass
    hardware_serial = _text(_hardware_value(hardware, "get_serial"))
    modem_version = _text(_hardware_value(hardware, "get_modem_version"))
    network_value = _hardware_value(hardware, "get_network_info", {})
    sim_value = _hardware_value(hardware, "get_sim_info", {})
    network = network_value if isinstance(network_value, dict) else {}
    sim = sim_value if isinstance(sim_value, dict) else {}

  serial = _text(values.get("HardwareSerial")) or hardware_serial
  return {
    "identity": {
      "device_type": device_type,
      "imei": imei,
      "imei_available": bool(imei),
      "dongle_id": _text(values.get("DongleId")),
      "hardware_serial": serial,
      "position": _text(values.get("DevicePosition")),
    },
    "software": {
      "branch": _text(values.get("GitBranch")),
      "commit": _text(values.get("GitCommit")),
      "commit_date": _text(values.get("GitCommitDate")),
      "last_update": _text(values.get("GitPullTime")),
    },
    "connectivity": {
      "carrier": _text(network.get("operator")),
      "technology": _text(network.get("technology")),
      "state": _text(network.get("state")),
      "sim_state": _first_text(sim.get("sim_state")),
      "modem_version": modem_version,
    },
    "runtime": {
      "boot_time": _boot_time(),
    },
  }


def get_device_setting_group_names() -> dict[str, list]:
  """Group -> parameter names, for the browser to read its groups from.

  The five base groups own their rows; the sunnypilot sections ride along from
  the settings catalog so the Device tab and the CarrotPilot tab stay in sync.
  """
  groups = {group: [name for name, _default in entries] for group, entries in DEVICE_SETTING_GROUPS}
  groups.update(_sp_device_setting_groups())
  return groups

DEVICE_NETWORK_REFRESH_INTERVAL_SEC = 15.0
_network_cache_lock = threading.Lock()
_network_cache: dict[str, Any] = {
  "monotonic": 0.0,
  "data": None,
}


def get_device_setting_values(ssh_status: dict[str, Any] | None = None) -> dict[str, Any]:
  """Read every value needed to render the Device settings groups."""
  names = [
    name for name in DEVICE_SETTING_DEFAULTS
    if name not in ("DeviceType", "GithubUsername", "GithubSshKeys")
  ]
  values = get_param_values(names, DEVICE_SETTING_DEFAULTS)
  try:
    from openpilot.system.hardware import HARDWARE
    values["DeviceType"] = HARDWARE.get_device_type()
  except Exception:
    values["DeviceType"] = DEVICE_SETTING_DEFAULTS["DeviceType"]

  status = ssh_status if isinstance(ssh_status, dict) else get_ssh_key_status()
  values["GithubUsername"] = status.get("username", values.get("GithubUsername", ""))
  # The UI only needs presence, so the public snapshot never carries key bodies.
  values["GithubSshKeys"] = "1" if status.get("has_keys") else ""
  return values


# ── network viewer data ────────────────────────────────────
def _split_nmcli_line(line: str) -> list[str]:
  parts: list[str] = []
  buf: list[str] = []
  escaped = False
  for ch in line:
    if escaped:
      buf.append(ch)
      escaped = False
    elif ch == "\\":
      escaped = True
    elif ch == ":":
      parts.append("".join(buf))
      buf = []
    else:
      buf.append(ch)
  parts.append("".join(buf))
  return parts


def get_wifi_networks() -> list[dict[str, Any]]:
  """Read visible Wi-Fi networks without connecting, forgetting, or editing."""
  try:
    proc = subprocess.run(
      ["nmcli", "-t", "-f", "ACTIVE,SSID,SECURITY,SIGNAL", "dev", "wifi", "list", "--rescan", "auto"],
      check=False,
      capture_output=True,
      encoding="utf-8",
      errors="replace",
      timeout=3,
    )
  except Exception:
    return []

  if proc.returncode != 0:
    return []

  seen: dict[str, dict[str, Any]] = {}
  for raw in proc.stdout.splitlines():
    parts = _split_nmcli_line(raw)
    if len(parts) < 4:
      continue
    active, ssid, security, signal = parts[:4]
    ssid = ssid.strip()
    if not ssid:
      continue
    try:
      signal_value = int(signal)
    except Exception:
      signal_value = None
    entry = {
      "ssid": ssid,
      "connected": active.strip().lower() == "yes",
      "security": security.strip(),
      "signal": signal_value,
      "secure": bool(security.strip() and security.strip() != "--"),
    }
    prev = seen.get(ssid)
    if prev is None or (entry["connected"] and not prev.get("connected")) or ((entry["signal"] or 0) > (prev.get("signal") or 0)):
      seen[ssid] = entry

  return sorted(seen.values(), key=lambda n: (not n.get("connected"), -(n.get("signal") or -1), n.get("ssid") or ""))


def get_wifi_ip_address() -> str:
  try:
    proc = subprocess.run(
      ["nmcli", "-t", "-f", "IP4.ADDRESS", "dev", "show", "wlan0"],
      check=False,
      capture_output=True,
      encoding="utf-8",
      errors="replace",
      timeout=2,
    )
  except Exception:
    return ""

  if proc.returncode != 0:
    return ""

  for raw in proc.stdout.splitlines():
    if ":" not in raw:
      continue
    value = raw.split(":", 1)[1].strip()
    if value:
      return value.split("/", 1)[0]
  return ""


def _network_param_values() -> dict[str, Any]:
  return {
    "tethering_enabled": get_param_value("HotspotOnBoot", False),
    "roaming_enabled": get_param_value("GsmRoaming", False),
    "gsm_metered": get_param_value("GsmMetered", False),
    "apn": get_param_value("GsmApn", ""),
  }


def get_device_network_snapshot() -> dict[str, Any]:
  """Return immediately without running NetworkManager commands."""
  with _network_cache_lock:
    cached = _network_cache.get("data")
    snapshot = deepcopy(cached) if isinstance(cached, dict) else None
  if snapshot is not None:
    snapshot.update(_network_param_values())
    return snapshot
  return {
    "wifi": [],
    "ip_address": "",
    **_network_param_values(),
  }


def refresh_device_network() -> dict[str, Any]:
  """Refresh the slow NetworkManager data for future request snapshots."""
  data = {
    "wifi": get_wifi_networks(),
    "ip_address": get_wifi_ip_address(),
    **_network_param_values(),
  }
  with _network_cache_lock:
    _network_cache["monotonic"] = time.monotonic()
    _network_cache["data"] = deepcopy(data)
  return deepcopy(data)


def get_device_network(force: bool = False) -> dict[str, Any]:
  """Compatibility entry point: only an explicit force may perform I/O."""
  return refresh_device_network() if force else get_device_network_snapshot()


# --- from this fork: which carrot ports have a socket bound -----------------
# CarrotPilot does not need this (it reads the ports it owns directly), but the carrot
# navi status endpoint here answers "is the nav channel up" without opening the port,
# which would steal a datagram or block on a TCP handshake.
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
