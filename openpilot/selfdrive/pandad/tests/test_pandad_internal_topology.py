#!/usr/bin/env python3
"""Unit tests for the built-in Red Panda support in pandad.

Covers:
- _panda_hub_is_internal: sysfs USB topology resolution (tici internal root
  hub usb1 vs external usb3, unknown platform -> None, unknown hub -> None)
- check_panda_support: a built-in Red Panda (hub-internal but
  hw_type-external) becomes the active panda by default; an external Red
  Panda keeps the legacy UseRedPanda / aux-dos behavior and feeds the
  external-red-panda flag
- flash_panda: refuses to flash when the expected signature is unavailable
  (brick guard) and recovers a built-in Red Panda via the topology check
"""
import os
import sys
import types
from pathlib import Path
from unittest import mock

import unittest

# fcntl is Unix-only; openpilot.common.hardware.comma.hardware imports it via
# common.gpio at module load. Stub it so these pure-logic unit tests also run
# on non-device (e.g. Windows CI/dev) hosts. Nothing in these tests touches it.
if sys.platform == "win32" and "fcntl" not in sys.modules:
  sys.modules["fcntl"] = types.ModuleType("fcntl")

# libparams_c.so is only built on device; these tests never touch Params, so
# fall back to a minimal stand-in when the native lib is missing.
try:
  import openpilot.common.params
except OSError:
  sys.modules.pop("openpilot.common.params", None)
  _params_stub = types.ModuleType("openpilot.common.params")

  class _ParamsStub:
    def get_bool(self, key, encoding=None):
      return False

    def put_bool(self, key, val, block=False):
      pass

    def get(self, key, encoding=None):
      return None

    def put(self, key, val):
      pass

  _params_stub.Params = _ParamsStub
  sys.modules["openpilot.common.params"] = _params_stub

# rivian_long_flasher pulls cereal.messaging -> msgq (also device-only native).
# It is only used from main(); stub the module for these pure-logic tests.
try:
  import openpilot.sunnypilot.selfdrive.pandad.rivian_long_flasher  # noqa: F401
except (OSError, ModuleNotFoundError):
  _rivian_stub = types.ModuleType("openpilot.sunnypilot.selfdrive.pandad.rivian_long_flasher")
  _rivian_stub.flash_rivian_long = lambda serials: None
  sys.modules["openpilot.sunnypilot.selfdrive.pandad.rivian_long_flasher"] = _rivian_stub

from panda import Panda

import openpilot.selfdrive.pandad.pandad as pandad


HW_DOS = Panda.HW_TYPE_DOS
HW_RED = Panda.HW_TYPE_RED_PANDA
HW_BLACK = Panda.HW_TYPE_BLACK_PANDA


def make_sysfs(root: Path, mapping: dict[str, str]) -> None:
  """Fake /sys/bus/usb/devices: real sysfs exposes devices as FLAT links
  (1-1.2 -> .../usb1/1-1/1-1.2), so build the device under targets/ and link
  it at the top level like the kernel does."""
  for i, (serial, hub) in enumerate(mapping.items()):
    real = root / "targets" / hub / f"{i + 1}-1" / f"{i + 1}-1.{i + 2}"
    real.mkdir(parents=True)
    (real / "idVendor").write_text("bbaa\n")
    (real / "serial").write_text(serial + "\n")
    link = root / f"{i + 1}-1.{i + 2}"
    if sys.platform == "win32":
      # junctions need no privileges on Windows
      from _winapi import CreateJunction
      CreateJunction(str(real), str(link))
    else:
      os.symlink(real, link, target_is_directory=True)


class TestPandaHubIsInternal(unittest.TestCase):
  def _root(self, tmp: str) -> Path:
    # wrap in a non-usb-named dir so no parent accidentally matches usb\\d+
    return Path(tmp) / "sysbus"

  def test_internal_hub_on_tici(self):
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
      root = self._root(tmp)
      make_sysfs(root, {"0f0e0d0c": "usb1", "11121314": "usb3"})
      assert pandad._panda_hub_is_internal("0f0e0d0c", root, "tici") is True
      assert pandad._panda_hub_is_internal("11121314", root, "tici") is False

  def test_unknown_platform_returns_none(self):
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
      root = self._root(tmp)
      make_sysfs(root, {"0f0e0d0c": "usb1"})
      # pc / unknown / comma 3X ("three x") must not be topology-checked
      for dt in ("pc", "unknown", "three x", ""):
        assert pandad._panda_hub_is_internal("0f0e0d0c", root, dt) is None

  def test_exact_match_not_substring(self):
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
      root = self._root(tmp)
      make_sysfs(root, {"0f0e0d0c": "usb1"})
      # "three" must match exactly, not the comma 3X's "three x"
      assert pandad._panda_hub_is_internal("0f0e0d0c", root, "three") is True
      assert pandad._panda_hub_is_internal("0f0e0d0c", root, "three x") is None

  def test_missing_serial_returns_none(self):
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
      root = self._root(tmp)
      make_sysfs(root, {"0f0e0d0c": "usb1"})
      assert pandad._panda_hub_is_internal("deadbeef", root, "tici") is None

  def test_missing_sysfs_returns_none(self):
    assert pandad._panda_hub_is_internal("0f0e0d0c", "/nonexistent/sysfs", "tici") is None

  def test_default_device_type_path(self):
    # with no explicit device_type, HARDWARE.get_device_type() is consulted;
    # on non-comma platforms this raises or returns a non-matching value
    with mock.patch.object(pandad.HARDWARE, "get_device_type", side_effect=OSError("no devicetree")):
      assert pandad._panda_hub_is_internal("0f0e0d0c") is None


class FakePanda:
  """Minimal Panda stand-in: serial -> (hw_type, is_internal)."""
  devices: dict[str, tuple] = {}
  instances: list = []

  def __init__(self, serial):
    dev = FakePanda.devices[serial]
    self.serial = serial
    self.hw_type, self.internal = dev[0], dev[1]
    self.bootstub = dev[2] if len(dev) > 2 else False
    self.stuck_bootstub = dev[3] if len(dev) > 3 else False
    self.flashed = False
    self.recovered = False
    self.closed = False
    FakePanda.instances.append(self)

  @classmethod
  def spi_list(cls):
    return []

  def get_type(self):
    return self.hw_type

  def is_internal(self):
    return self.internal

  def get_version(self):
    return "test-version"

  def get_signature(self):
    return b"\xaa" * 128

  def flash(self):
    self.flashed = True
    # simulate a flash that still does not boot when marked stuck
    if not self.stuck_bootstub:
      self.bootstub = False

  def recover(self, reset=True):
    self.recovered = True
    self.bootstub = False

  def close(self):
    self.closed = True


# pandad.py references Panda.HW_TYPE_* / SUPPORTED_DEVICES off the patched-in
# class, so mirror the real constants onto the fake
FakePanda.HW_TYPE_RED_PANDA = Panda.HW_TYPE_RED_PANDA
FakePanda.HW_TYPE_DOS = Panda.HW_TYPE_DOS
FakePanda.HW_TYPE_BLACK_PANDA = Panda.HW_TYPE_BLACK_PANDA
FakePanda.SUPPORTED_DEVICES = Panda.SUPPORTED_DEVICES


def _patch_env(monkeypatched: dict, topo: dict[str, bool | None], sig: bytes = b"\xaa" * 128):
  FakePanda.devices = monkeypatched
  return [
    mock.patch.object(pandad, "Panda", FakePanda),
    mock.patch.object(pandad, "_panda_hub_is_internal", side_effect=lambda s, **kw: topo.get(s)),
    mock.patch.object(pandad, "get_expected_signature", return_value=sig),
  ]


class TestCheckPandaSupport(unittest.TestCase):
  def tearDown(self):
    mock.patch.stopall()

  def test_builtin_red_panda_is_active_by_default(self):
    # comma three with the dos swapped for a red panda: hw_type says external,
    # USB topology says internal -> must become the active panda
    for patcher in _patch_env({"rr11": (HW_RED, False)}, {"rr11": True}):
      patcher.start()
    active, aux, ext_red = pandad.check_panda_support(["rr11"])
    assert active == ["rr11"]
    assert aux is None
    assert ext_red is False

  def test_builtin_red_panda_with_use_red_panda_has_no_aux(self):
    # UseRedPanda on a built-in Red Panda device must not select the same
    # panda as both active and aux
    for patcher in _patch_env({"rr11": (HW_RED, False)}, {"rr11": True}):
      patcher.start()
    active, aux, ext_red = pandad.check_panda_support(["rr11"], use_red_panda=True)
    assert active == ["rr11"]
    assert aux is None
    assert ext_red is False

  def test_external_red_panda_plus_dos_legacy(self):
    # the classic setup: internal dos + external Red Panda. Default keeps the
    # dos active; UseRedPanda promotes the Red Panda with the dos as aux.
    devices = {"dos1": (HW_DOS, True), "red1": (HW_RED, False)}
    topo = {"dos1": True, "red1": False}
    for patcher in _patch_env(devices, topo):
      patcher.start()
    active, aux, ext_red = pandad.check_panda_support(["red1", "dos1"])
    assert active == ["dos1"]
    assert aux is None
    assert ext_red is True

    active, aux, ext_red = pandad.check_panda_support(["red1", "dos1"], use_red_panda=True)
    assert active == ["red1"]
    assert aux == "dos1"
    assert ext_red is True

  def test_unknown_topology_keeps_legacy_red_panda_behavior(self):
    # non-tici platform (topology None): the Red Panda is treated as external
    # like before, and is only selectable via UseRedPanda
    for patcher in _patch_env({"red1": (HW_RED, False)}, {"red1": None}):
      patcher.start()
    active, aux, ext_red = pandad.check_panda_support(["red1"])
    assert active == []
    assert ext_red is True

    active, aux, ext_red = pandad.check_panda_support(["red1"], use_red_panda=True)
    assert active == ["red1"]
    assert aux is None
    assert ext_red is True

  def test_dos_only_unchanged(self):
    for patcher in _patch_env({"dos1": (HW_DOS, True)}, {"dos1": True}):
      patcher.start()
    active, aux, ext_red = pandad.check_panda_support(["dos1"])
    assert active == ["dos1"]
    assert aux is None
    assert ext_red is False

  def test_builtin_red_panda_true_topo_without_tici_would_be_external(self):
    # if the topology check says False/None explicitly, a Red Panda stays
    # external even on tici (plugged into the typec port)
    devices = {"dos1": (HW_DOS, True), "red1": (HW_RED, False)}
    topo = {"dos1": True, "red1": False}
    for patcher in _patch_env(devices, topo):
      patcher.start()
    active, aux, ext_red = pandad.check_panda_support(["red1", "dos1"])
    assert ext_red is True
    assert active == ["dos1"]


class TestFlashPandaGuards(unittest.TestCase):
  def tearDown(self):
    mock.patch.stopall()

  def test_refuses_to_flash_without_expected_signature(self):
    # brick guard: a blank expected signature must never trigger panda.flash()
    FakePanda.devices = {"r1": (HW_RED, False, False)}
    FakePanda.instances = []
    with mock.patch.object(pandad, "Panda", FakePanda), \
         mock.patch.object(pandad, "_panda_hub_is_internal", side_effect=lambda s, **kw: True), \
         mock.patch.object(pandad, "get_expected_signature", return_value=b""), \
         mock.patch.object(pandad, "cloudlog"):
      pandad.flash_panda("r1")
    assert len(FakePanda.instances) == 1
    fp = FakePanda.instances[0]
    assert not fp.flashed
    assert fp.closed

  def test_builtin_red_panda_bootstub_recovered_via_topology(self):
    # hw_type says external, topology says internal -> recover_internal_panda
    # must run; 4th tuple slot: firmware stays in bootstub after flashing
    FakePanda.devices = {"r1": (HW_RED, False, True, True)}
    FakePanda.instances = []
    with mock.patch.object(pandad, "Panda", FakePanda), \
         mock.patch.object(pandad, "_panda_hub_is_internal", side_effect=lambda s, **kw: True), \
         mock.patch.object(pandad, "get_expected_signature", return_value=b"\xaa" * 128), \
         mock.patch.object(pandad, "cloudlog"), \
         mock.patch.object(pandad.HARDWARE, "recover_internal_panda") as recover, \
         mock.patch.object(pandad.HARDWARE, "reset_internal_panda"):
      pandad.flash_panda("r1")
    assert len(FakePanda.instances) == 1
    fp = FakePanda.instances[0]
    assert fp.flashed
    assert fp.recovered
    recover.assert_called_once()


if __name__ == "__main__":
  unittest.main()
