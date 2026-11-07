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

  def test_unknown_topology_falls_back_to_supported_panda(self):
    # non-tici platform (topology None), no internal panda found: any
    # supported external USB panda becomes active instead of dead-looping
    # (C3XL compatibility, ported from mr-one); the Red Panda is still
    # flagged external, and UseRedPanda keeps working
    for patcher in _patch_env({"red1": (HW_RED, False)}, {"red1": None}):
      patcher.start()
    active, aux, ext_red = pandad.check_panda_support(["red1"])
    assert active == ["red1"]
    assert aux is None
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

  def test_recover_internal_usb_panda_no_dfu_raises(self):
    # BOOT0/RST pulsed, but the board never enumerates in DFU -> RuntimeError
    # instead of an infinite wait
    with mock.patch.object(pandad, "PandaDFU") as fake_dfu, \
         mock.patch.object(pandad.HARDWARE, "recover_internal_panda") as recover, \
         mock.patch.object(pandad, "cloudlog"), \
         mock.patch("openpilot.selfdrive.pandad.pandad.time.sleep"):
      fake_dfu.usb_list.return_value = []
      with self.assertRaises(RuntimeError):
        pandad.recover_internal_usb_panda("r1")
    recover.assert_called_once()

  def test_recover_internal_usb_panda_flashes_bootstub(self):
    # DFU present: bootstub gets flashed, then the function reconnects and
    # only returns once the panda answers in bootstub mode
    recovered = {"dfu": False}
    fake_dfu_obj = mock.MagicMock()
    fake_dfu_obj.__enter__ = lambda s: s
    fake_dfu_obj.__exit__ = lambda s, *a: None
    fake_dfu_obj.recover.side_effect = lambda: recovered.__setitem__("dfu", True)

    reopened = {"n": 0}
    panda = FakePanda("r1")
    panda.bootstub = True

    def fake_panda_ctor(serial):
      reopened["n"] += 1
      if reopened["n"] >= 2:
        panda.bootstub = True  # answers in bootstub mode after recovery
      return panda

    with mock.patch.object(pandad, "PandaDFU") as fake_dfu_cls, \
         mock.patch.object(pandad, "Panda", side_effect=fake_panda_ctor), \
         mock.patch.object(pandad, "cloudlog"), \
         mock.patch("openpilot.selfdrive.pandad.pandad.time.sleep"):
      fake_dfu_cls.usb_list.return_value = ["dfu1"]
      fake_dfu_cls.side_effect = lambda serial: fake_dfu_obj
      out = pandad.recover_internal_usb_panda("r1")
    assert recovered["dfu"] is True
    assert out is panda

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
    # hw_type says external, topology says internal -> a stuck bootstub must
    # be recovered through the DFU path (recover_internal_usb_panda); 4th
    # tuple slot: firmware stays in bootstub after flashing
    FakePanda.devices = {"r1": (HW_RED, False, True, True)}
    FakePanda.instances = []

    def fake_recover(serial):
      p = FakePanda(serial)
      p.bootstub = False  # DFU recovery + reflash: app boots afterwards
      return p

    with mock.patch.object(pandad, "Panda", FakePanda), \
         mock.patch.object(pandad, "_panda_hub_is_internal", side_effect=lambda s, **kw: True), \
         mock.patch.object(pandad, "get_expected_signature", return_value=b"\xaa" * 128), \
         mock.patch.object(pandad, "cloudlog"), \
         mock.patch.object(pandad, "recover_internal_usb_panda", side_effect=fake_recover) as recover:
      pandad.flash_panda("r1")
    assert len(FakePanda.instances) == 2  # initial panda + post-recovery panda
    first, second = FakePanda.instances
    assert first.flashed
    assert first.closed
    recover.assert_called_once_with("r1")
    assert second.flashed
    assert second.closed


class TestSpiRecoveryChain(unittest.TestCase):
  def tearDown(self):
    mock.patch.stopall()

  def test_recover_internal_spi_panda_no_device_raises(self):
    # without a SPI device answering the ST ROM bootloader (the normal case on
    # tici / non-SPI hosts), the recovery must give up after the configured
    # attempts, pulsing the GPIO lines each round
    with mock.patch.object(pandad.HARDWARE, "recover_internal_panda") as recover, \
         mock.patch.object(pandad.HARDWARE, "reset_internal_panda"), \
         mock.patch.object(pandad, "STBootloaderSPIHandle", side_effect=pandad.PandaSpiException("no spi")), \
         mock.patch.object(pandad, "cloudlog"), \
         mock.patch.object(pandad.time, "sleep"):
      with self.assertRaises(RuntimeError):
        pandad.recover_internal_spi_panda(None)
    assert recover.call_count == 3

  def test_recover_internal_panda_any_falls_back_to_spi(self):
    # USB DFU chain fails (no DFU enumeration) -> SPI ROM chain must run and
    # its result is used for the app flash
    FakePanda.devices = {"sp1": (HW_RED, True, True, False)}
    FakePanda.instances = []

    def fake_flash(self):
      # only the initial (unrecovered) panda fails to flash
      if len(FakePanda.instances) == 1:
        raise Exception("flasher busy")
      self.flashed = True
      self.bootstub = False

    def fake_spi_recover(serial):
      p = FakePanda(serial)
      p.bootstub = False  # fresh bootstub, ready for the app flash
      return p

    with mock.patch.object(pandad, "Panda", FakePanda), \
         mock.patch.object(FakePanda, "flash", fake_flash), \
         mock.patch.object(pandad, "get_expected_signature", return_value=b"\xaa" * 128), \
         mock.patch.object(pandad, "cloudlog"), \
         mock.patch.object(pandad, "recover_internal_usb_panda", side_effect=RuntimeError("no DFU")), \
         mock.patch.object(pandad, "recover_internal_spi_panda", side_effect=fake_spi_recover) as spi_recover:
      pandad.flash_panda("sp1")
    spi_recover.assert_called_once_with("sp1")
    initial, recovered = FakePanda.instances
    assert initial.closed  # failed panda must be closed before recovery
    assert recovered.flashed
    assert recovered.closed


if __name__ == "__main__":
  unittest.main()
