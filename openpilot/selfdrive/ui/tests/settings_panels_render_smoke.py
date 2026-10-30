"""Headless smoke test that opens EVERY settings sidebar panel.

Why this exists
---------------
The ExperimentalMode KeyError (toggles.py) crashed the ui the moment the
sidebar switched to the Toggles panel - and only that panel. A render smoke
test of one layout cannot catch panel-specific breakage, so this test walks
the real sunnypilot SettingsLayout the way the sidebar does: construct the
layout, then for every panel call set_current_panel() -> show_event() ->
render(). Any KeyError / AttributeError / undefined-name that a panel trips
on open is a failure here.

Run from the repo root (no display, no capnp, no zmq needed):

    PYTHONPATH=.;opendbc_repo python openpilot/selfdrive/ui/tests/settings_panels_render_smoke.py

Exit status is 0 when every check passes.

NOTE: deliberately NOT named test_*.py - it installs sys.modules stubs
(fake pyray / application / params) and pytest must not collect it into a
shared session.
"""

from __future__ import annotations

import importlib
import sys
import types
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from carrot_tuning_render_smoke import (  # noqa: E402
  build_fake_application, build_fake_multilang, build_fake_params, build_fake_pyray, install_stubs,
)


class _AnyAttr:
  """Attribute chain that tolerates any access and any call."""

  def __getattr__(self, name: str) -> Any:
    if name.startswith("__"):
      raise AttributeError(name)
    return _AnyAttr()

  def __call__(self, *a, **k):
    return _AnyAttr()

  def __int__(self):
    return 0

  def __float__(self):
    return 0.0

  def __bool__(self):
    return False

  def __repr__(self):
    return "<AnyAttr>"

  def __hash__(self):
    return 0


class _FakeSM:
  """Minimal SubMaster stand-in: per-service sensible defaults, any-attr rest."""

  def __init__(self):
    self.updated = defaultdict(bool)
    self.valid = defaultdict(lambda: True)
    self.recv_frame = defaultdict(int)
    self.logMonoTime = defaultdict(int)
    self._defaults: dict[str, Any] = {
      "selfdriveState": types.SimpleNamespace(personality=1, enabled=False, active=False, awarenessStatus=1.0),
      "selfdriveStateSP": types.SimpleNamespace(
        mads=types.SimpleNamespace(enabled=False),
        zoompilot=types.SimpleNamespace(experimentalMode=True, madsLateralHeld=False, icbmHold=False),
      ),
      "deviceState": types.SimpleNamespace(started=False, deviceType="tici", networkType=1, memoryUsagePercent=50, networkMetered=False),
      "carState": types.SimpleNamespace(vEgo=0.0, gearShifter=None, gasPressed=False, brakePressed=False, standstill=True),
      "carParams": types.SimpleNamespace(openpilotLongitudinalControl=True),
      "controlsState": types.SimpleNamespace(longControlState=0, curvature=0.0, vCruise=0.0),
      "extrinsicsCalibration": types.SimpleNamespace(rpyCalib=[0.0, 0.0, 0.0], calStatus=1),
      "driverMonitoringState": types.SimpleNamespace(events=[], isActiveMode=False),
    }

  def __getitem__(self, service: str) -> Any:
    return self._defaults.get(service, _AnyAttr())


class _FakeDevice:
  def __init__(self):
    self.interactive_timeout = None
    self._awake = True  # firehose update-loop thread reads this every tick

  def set_override_interactive_timeout(self, timeout):
    self.interactive_timeout = timeout


class _FakeUiState:
  def __init__(self):
    self.params = None  # replaced by install() with the fake Params singleton
    self.sm = _FakeSM()
    self.CP = None
    self.CP_SP = None
    self.has_longitudinal_control = True
    self.engaged = False
    self.started = False
    self.personality = 1
    self.is_metric = False
    self.initial_cruise_speed = 0  # InitialCruiseSpeedKph default
    self.always_offroad = False
    self.status = 0
    self.started_frame = 0
    self.started_time = 0.0
    self._experimental_mode_setting = False
    self.prime_state = _AnyAttr()

  def set_experimental_mode(self, on: bool) -> None:
    """Mirror ui_state_zp.set_experimental_mode: param write + offroad cache."""
    self.params.put_bool("ExperimentalMode", on, block=True)
    self._experimental_mode_setting = on

    class _FakeSunnylinkState:
      def get_sponsor_tier(self):
        # real API returns a SponsorTier enum; ui reads .name
        return types.SimpleNamespace(name="NONE")

      def get_sponsor_tier_color(self):
        return (128, 128, 128, 255)

      def is_paired(self):
        return False

      def is_sponsor(self):
        return False

      def set_settings_open(self, *a, **k):
        pass

      def __getattr__(self, name):
        if name.startswith("__"):
          raise AttributeError(name)
        return _AnyAttr()

    self.sunnylink_state = _FakeSunnylinkState()
    self.active_bundle = None  # models panel reads it
    self.jetlink = None  # accelerator_link.link_toggle_meaningful branches on it
    self.adb_blocked = False  # developer panel status row
    self.torque_utilization = 0.0
    self.icbm_start_locked = False
    self.icbm_running = False
    self.experimental_mode = False
    self._callbacks: list = []

  def is_onroad(self):
    return False

  def is_offroad(self):
    return True

  def update(self):
    return None

  def update_params(self):
    return None

  def add_engaged_transition_callback(self, cb):
    self._callbacks.append(cb)

  def add_offroad_transition_callback(self, cb):
    self._callbacks.append(cb)

  def add_on_body_changed_callbacks(self, cb):
    self._callbacks.append(cb)

  def __getattr__(self, name):
    # Tolerant fallback for the long tail of ui_state attributes panels read
    # (jetlink_view, model_runner flags, ...). Explicit attributes above stay
    # authoritative; anything unlisted resolves to the any-attr stand-in so a
    # panel can at least open and render. Real AttributeError-class bugs are
    # caught by the on-device onroad simulation pass instead.
    if name.startswith("__"):
      raise AttributeError(name)
    return _AnyAttr()


def install() -> None:
  install_stubs()
  import importlib as _il

  # Replace the minimal ui_state stub from carrot_tuning_render_smoke with the
  # richer one (panels are imported AFTER this, so they bind our fake).
  mods = build_fake_params()
  mods.UnknownKeyName = type("UnknownKeyName", (KeyError,), {})
  ui = _FakeUiState()
  ui.params = mods.Params()

  import enum as _enum

  class ChestnutState(_enum.Enum):
    # mirrors openpilot.selfdrive.ui.ui_state.ChestnutState
    DISCONNECTED = "disconnected"
    UNCOMPILED = "uncompiled"
    READY = "ready"
    LOADING = "loading"
    ACTIVE = "active"
    FAILED = "failed"
    WAITING = "waiting"

  ui.chestnut_state = ChestnutState.DISCONNECTED
  ui.chestnut_present = False
  ui.chestnut_active = False
  ui.chestnut_loading = False
  ui.jetlink = None  # accelerator_link.link_toggle_meaningful branches on it
  ui_mod = types.ModuleType("openpilot.selfdrive.ui.ui_state")
  ui_mod.ui_state = ui
  ui_mod.device = _FakeDevice()
  ui_mod.ChestnutState = ChestnutState
  ui_mod.PrimeState = _AnyAttr
  sys.modules["openpilot.selfdrive.ui.ui_state"] = ui_mod

  sys.modules["pyray"] = build_fake_pyray()
  sys.modules["openpilot.system.ui.lib.application"] = build_fake_application()
  sys.modules["openpilot.system.ui.lib.multilang"] = build_fake_multilang()
  sys.modules["openpilot.common.params"] = mods

  # network panel wires WifiManagerUI against the real manager API; give the
  # stub every method the widget calls instead of chasing them one by one.
  class _FakeWifiManager:
    def __init__(self, *a, **k):
      self.networks = []
      # string-valued attributes read by network info rows
      self.ipv4_address = "192.168.1.2"
      self.ipv6_address = ""
      self.ssid = "fake-ssid"
      self.connected_ssid = "fake-ssid"
      self.wifi_state = 0
      self.tethering_password = ""
      self.current_network_metered = False

    def add_callbacks(self, **k):
      pass

    def set_active(self, v):
      pass

    def startLocalScan(self):
      pass

    def process_callbacks(self):
      pass

    def connect_to_network(self, *a, **k):
      pass

    def activate_connection(self, *a, **k):
      pass

    def forget_connection(self, *a, **k):
      pass

    def is_connection_saved(self, *a, **k):
      return False

    def is_tethering_active(self):
      return False

    def set_tethering_active(self, *a, **k):
      pass

    def set_tethering_password(self, *a, **k):
      pass

    def set_current_network_metered(self, *a, **k):
      pass

    def set_ipv4_forward(self, *a, **k):
      pass

    def __getattr__(self, name):
      if name.startswith("__"):
        raise AttributeError(name)
      # unknown attributes read as text rows return an empty string
      return ""

  wifi = types.ModuleType("openpilot.system.ui.lib.wifi_manager")
  wifi.WifiManager = _FakeWifiManager
  wifi.SecurityType = types.SimpleNamespace(OPEN=0, WPA2=1, UNSUPPORTED=2)
  wifi.Network = _AnyAttr
  wifi.MeteredType = _AnyAttr
  wifi.normalize_ssid = lambda s: s
  sys.modules["openpilot.system.ui.lib.wifi_manager"] = wifi

  for name in ("openpilot.common.swaglog", "openpilot.common.wifi_manager"):
    m = types.ModuleType(name)
    m.cloudlog = _AnyAttr()
    sys.modules.setdefault(name, m)

  # cereal.messaging pulls in the msgq native lib (absent on a bare PC); the
  # chestnut panel imports it at module scope. Panels only need the names to
  # resolve - no messaging happens in a headless render.
  cereal = types.ModuleType("openpilot.cereal")
  cereal.__path__ = []  # mark as package so openpilot.cereal.X imports resolve to stubs below
  cereal_mod = types.ModuleType("openpilot.cereal.messaging")
  cereal_mod.messaging = _AnyAttr()
  cereal_mod.log = _AnyAttr()
  # calibrationd et al. reference messaging.PubMaster in class-body annotations;
  # chestnut constructs SubMaster([...]) directly
  cereal_mod.PubMaster = lambda *a, **k: _AnyAttr()
  cereal_mod.SubMaster = lambda *a, **k: _FakeSM()
  cereal_mod.new_message = lambda *a, **k: _AnyAttr()

  # selfdrived.events builds EVENT_NAME from log.EventName at module scope;
  # hardware/base.py reaches log.DeviceState.NetworkType the same way.
  class _CapnpEnumStub:
    def __init__(self):
      object.__setattr__(self, "schema", types.SimpleNamespace(enumerants={}))

    def __getattr__(self, name):
      if name.startswith("__"):
        raise AttributeError(name)
      # nested struct access (DeviceState.NetworkType) yields another stub
      return _CapnpEnumStub()

  cereal_log = types.ModuleType("openpilot.cereal.log")
  cereal_log.EventName = _CapnpEnumStub()
  cereal_log.Event = _AnyAttr
  cereal_log.CarParams = _AnyAttr
  cereal_log.DeviceState = _CapnpEnumStub()
  # any other log.<Struct> access (SelfdriveState.AlertSize, ...) is covered by
  # a module-level __getattr__ fallback
  cereal_log.__getattr__ = lambda name: _CapnpEnumStub()
  cereal_custom = types.ModuleType("openpilot.cereal.custom")
  cereal_custom.__getattr__ = lambda name: _CapnpEnumStub()
  sys.modules["openpilot.cereal.custom"] = cereal_custom
  cereal.custom = cereal_custom
  cereal.log = cereal_log
  sys.modules["openpilot.cereal.log"] = cereal_log

  class _VisionStreamType:
    def __getattr__(self, name):
      return name

  cereal_vision = types.ModuleType("openpilot.cereal.visionipc")
  cereal_vision.VisionStreamType = _VisionStreamType()
  cereal_vision.VisionIpcClient = _AnyAttr()
  cereal_vision.visionipc_connect = lambda *_a, **_k: None

  msgq_pkg = types.ModuleType("msgq")
  msgq_pkg.__path__ = []
  msgq_vision = types.ModuleType("msgq.visionipc")
  msgq_vision.VisionIpcClient = _AnyAttr()
  msgq_vision.VisionBuf = _AnyAttr()
  msgq_vision.VisionStreamType = _VisionStreamType()
  msgq_pkg.visionipc = msgq_vision
  sys.modules["msgq"] = msgq_pkg
  sys.modules["msgq.visionipc"] = msgq_vision

  # openpilot.common.gpio imports fcntl at module scope (Linux-only); the
  # comma hardware module chain pulls it in. Provide import-level fakes.
  fcntl_fake = types.ModuleType("fcntl")
  fcntl_fake.flock = lambda *_a, **_k: None
  fcntl_fake.LOCK_EX = 2
  fcntl_fake.LOCK_NB = 4
  fcntl_fake.LOCK_UN = 8
  sys.modules.setdefault("fcntl", fcntl_fake)
  sys.modules.setdefault("termios", types.ModuleType("termios"))
  cereal.messaging = cereal_mod
  cereal.visionipc = cereal_vision
  sys.modules["openpilot.cereal"] = cereal
  sys.modules["openpilot.cereal.messaging"] = cereal_mod
  sys.modules["openpilot.cereal.visionipc"] = cereal_vision
  sys.modules["cereal"] = cereal
  sys.modules["cereal.messaging"] = cereal_mod
  sys.modules["cereal.visionipc"] = cereal_vision

  # openpilot.common.hardware.base imports cereal.log and pycryptodome-free deps;
  # the chestnut panel and modeld helpers need usb constants - cover any name.
  hw = types.ModuleType("openpilot.common.hardware.usb")
  hw.get_usb_state = lambda: _AnyAttr()
  hw.is_chestnut_usb_id = lambda *_a, **_k: False
  hw.__getattr__ = lambda name: _AnyAttr()
  sys.modules["openpilot.common.hardware.usb"] = hw

  # openpilot.common.hardware.usb stub (above) covers chestnut; drive_stats pulls
  # the tools logreader chain whose url_file module calls os.register_at_fork
  # (absent on Windows) - stub the whole chain for a headless render.
  logreader_stub = types.ModuleType("openpilot.tools.lib.logreader")
  logreader_stub.LogReader = _AnyAttr
  logreader_stub.AutoResumeStream = _AnyAttr
  logreader_stub.ReadMode = _AnyAttr
  sys.modules["openpilot.tools.lib.logreader"] = logreader_stub
  ds = types.ModuleType("openpilot.selfdrive.ui.sunnypilot.lib.drive_stats")
  ds.refresh_local_drive_stats = lambda *_a, **_k: None
  ds.fetch_cloud_drive_stats = lambda *_a, **_k: None
  sys.modules["openpilot.selfdrive.ui.sunnypilot.lib.drive_stats"] = ds

  for pkg in ("openpilot", "openpilot.system", "openpilot.system.ui", "openpilot.system.ui.lib",
              "openpilot.system.ui.widgets", "openpilot.system.ui.sunnypilot",
              "openpilot.system.ui.sunnypilot.widgets", "openpilot.common",
              "openpilot.selfdrive", "openpilot.selfdrive.ui",
              "openpilot.selfdrive.ui.sunnypilot",
              "openpilot.selfdrive.ui.sunnypilot.layouts",
              "openpilot.selfdrive.ui.sunnypilot.layouts.settings"):
    if pkg in sys.modules:
      continue
    try:
      _il.import_module(pkg)
    except Exception as exc:  # pragma: no cover
      print(f"  [warn] could not import {pkg}: {exc}")


def main() -> int:
  install()

  from openpilot.selfdrive.ui.layouts.settings.settings import PanelType  # noqa: E402
  from openpilot.selfdrive.ui.sunnypilot.layouts.settings.settings import SettingsLayoutSP as SettingsLayout  # noqa: E402

  # On a PC without git-lfs smudging, car_list.json is a 61-byte pointer file
  # and the Vehicle panel would die on json.load. Point the selector at the
  # opendbc source copy instead (device repos have the real file).
  try:
    import openpilot.selfdrive.ui.sunnypilot.layouts.settings.vehicle.platform_selector as _ps
    _real = Path(_ps.__file__).resolve().parents[7] / "opendbc_repo" / "opendbc" / "sunnypilot" / "car" / "car_list.json"
    if _real.exists() and _real.read_text(encoding="utf-8").startswith("{"):
      _ps.CAR_LIST_JSON_OUT = str(_real)
  except Exception:
    pass

  from openpilot.system.ui.lib.application import gui_app  # noqa: E402

  from carrot_tuning_render_smoke import DRAWN  # noqa: E402

  failures: list[str] = []
  checks = 0

  def check(label, fn):
    nonlocal checks
    checks += 1
    try:
      fn()
      print(f"  ok  {label}")
    except Exception as exc:
      failures.append(f"{label}: {type(exc).__name__}: {exc}")
      print(f"  FAIL {label}: {type(exc).__name__}: {exc}")

  content_rect = types.SimpleNamespace(x=460, y=0, width=1700, height=1080)
  full = types.SimpleNamespace(x=0, y=0, width=2160, height=1080)

  print("== settings layout + every sidebar panel ==")
  layout = SettingsLayout()
  layout.set_parent_rect(full)

  def layout_renders():
    DRAWN.clear()
    layout.render(full)
    assert DRAWN, "settings layout drew nothing"

  check("settings layout renders (device panel default)", layout_renders)

  def sidebar_lists_all_panels():
    assert layout._panels, "no panels registered"
    rows = getattr(layout, "_panel_rows", None) or getattr(layout, "_nav_rows", None)
    if rows is not None:
      assert len(rows) == len(layout._panels), f"{len(rows)} sidebar rows vs {len(layout._panels)} panels"

  check(f"sidebar registers {len(layout._panels)} panels", sidebar_lists_all_panels)

  # Open every panel the way a sidebar tap does: set_current_panel -> show_event
  # -> render. This is the exact path that crashed on the toggles panel.
  # Iterate the registered dict, not the PanelType enum: the SP layout extends
  # the dict beyond the base enum members.
  for panel_type in list(layout._panels):
    info = layout._panels.get(panel_type)
    if info is None:
      continue

    panel_label = getattr(panel_type, "name", str(panel_type))

    def panel_opens(pt=panel_type, label=panel_label):
      layout.set_current_panel(pt)
      layout._panels[pt].instance.show_event()
      DRAWN.clear()
      layout.render(full)
      assert DRAWN, f"{label} panel drew nothing"
      # A second render must not crash either (state settled).
      layout.render(full)

    check(f"panel {panel_label} opens + renders", panel_opens)

    # show_event twice in a row: idempotency guards against state built up per-open.
    def panel_reopens(pt=panel_type, label=panel_label):
      layout._panels[pt].instance.show_event()
      layout._panels[pt].instance.show_event()
      layout.render(full)

    check(f"panel {panel_label} reopens cleanly", panel_reopens)

  # Click-flow for the experimental mode switch (Cruise panel, the single home
  # after the zp sync): unconfirmed -> confirm dialog -> acknowledged state
  # machine write -> disable keeps the bit -> confirmed enable skips the dialog.
  # This is the path that shipped the DialogResult NameError.
  def exp_toggle_flow():
    cruise_key = next(k for k in layout._panels
                      if "CRUISE" in str(getattr(k, "name", k)).upper())
    cruise_panel = layout._panels[cruise_key].instance
    alpha = getattr(cruise_panel, "_alpha_long", None)
    assert alpha is not None, "cruise panel has no AlphaLongitudinalToggles"

    from openpilot.selfdrive.ui.ui_state import ui_state as _ui
    store = sys.modules["openpilot.common.params"].store
    assert _ui.params is not None
    for key in ("ExperimentalMode", "ExperimentalModeConfirmed"):
      store.pop(key, None)
    # the state machine refuses mode changes with an unknown road state;
    # selfdrived keeps these flags live on a real device.
    store["IsOffroad"] = True
    store["IsOnroad"] = False
    gui_app.pushed_widgets.clear()

    alpha._on_experimental_mode(True)
    assert gui_app.pushed_widgets, "no confirm dialog pushed for unconfirmed enable"
    assert not store.get("ExperimentalMode"), "store written before confirmation"

    alpha._apply_experimental_mode(True, acknowledged=True)
    assert store.get("ExperimentalMode"), "acknowledged enable did not write the mode"
    assert store.get("ExperimentalModeConfirmed"), "acknowledgement bit not recorded"

    alpha._on_experimental_mode(False)
    assert not store.get("ExperimentalMode"), "disable did not clear the mode"
    assert store.get("ExperimentalModeConfirmed"), "disable must keep the acknowledgement bit"

    gui_app.pushed_widgets.clear()
    alpha._on_experimental_mode(True)
    assert not gui_app.pushed_widgets, "confirmed enable must not re-prompt"
    assert store.get("ExperimentalMode"), "confirmed enable did not write the mode"

  check("experimental mode switch click flow (cruise panel)", exp_toggle_flow)

  print()
  if failures:
    print(f"FAILED {len(failures)}/{checks} checks:")
    for f in failures:
      print(f"  - {f}")
    return 1
  print(f"PASSED {checks}/{checks} checks")
  return 0


if __name__ == "__main__":
  sys.exit(main())
