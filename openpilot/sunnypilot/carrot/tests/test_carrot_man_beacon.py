"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Regression tests for the UDP 7705 discovery beacon.

The phone app finds the unit by reading the `ip` field of a UDP 7705 datagram, then opens
the 7714 v2 link. CarrotPilot runs carrot_man with `always_run` and starts the beacon thread
from `__init__`, so the beacon is live no matter what the feature switches say. This fork had
drifted three times, each time leaving a default device invisible to the app
("7705 未激活"):

  * the process was gated on `CarrotEnabled`, which defaults to "0";
  * `tick()` returned at the `if not self._enabled` gate *before* the block that starts the
    broadcast thread, and cleared `_is_running` on the way out (the broadcast thread returns
    immediately while that flag is false);
  * `get_broadcast_address()` used a hard-coded interface list, so on any other interface
    (USB / tethering) the datagram went out as 255.255.255.255 via the default route.

All three are pinned here. carrot_man is inspected as source (AST) rather than imported: on PC
it pulls in `fcntl` and native cereal/opendbc modules, and the sibling test module works
around that with process-wide `sys.modules` stubs that must not be relied on here.
"""
import ast
import re
import unittest
from pathlib import Path

CARROT_DIR = Path(__file__).resolve().parents[1]
CARROT_MAN = CARROT_DIR / "carrot_man.py"
PROCESS_CONFIG = Path(__file__).resolve().parents[3] / "system" / "manager" / "process_config.py"


def _method_node(method_name: str) -> ast.FunctionDef:
  tree = ast.parse(CARROT_MAN.read_text(encoding="utf-8"))
  for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == "CarrotManager":
      for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
          return item
  raise AssertionError(f"CarrotManager.{method_name} not found in {CARROT_MAN}")


def _method_code(method_name: str) -> str:
  """Statements of the method without the docstring or comments.

  Dropping the docstring matters: the docstrings explain *why* these guards exist and
  legitimately name the very tokens the assertions below must not find.
  """
  node = _method_node(method_name)
  body = list(node.body)
  if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
    body = body[1:]
  return ast.unparse(ast.Module(body=body, type_ignores=[]))


class TestBeaconProcessGate(unittest.TestCase):
  def test_carrot_man_uses_always_run(self):
    src = PROCESS_CONFIG.read_text(encoding="utf-8")
    match = re.search(r'PythonProcess\(\s*["\']carrot_man["\']\s*,\s*[^,]+,\s*([A-Za-z_][A-Za-z0-9_]*)', src)
    self.assertIsNotNone(match, "carrot_man PythonProcess entry not found")
    self.assertEqual(
      match.group(1), "always_run",
      "carrot_man must use always_run: it is the only 7705 discovery advertiser on this fork, "
      "and the app cannot enable anything until it has found the unit. CarrotEnabled defaults to off.")


class TestCarrotProcessFleetIsUngated(unittest.TestCase):
  """CarrotPilot runs every carrot_* process with `always_run`.

  A process gate is the wrong home for these switches: the phone app drives the
  feature at runtime, and the manager only re-evaluates its gates on the manager
  cycle, so a gated process cannot come up at the moment the app connects. Only
  carrot_man used to be always_run here, which is why a default device answered
  on 7705 but had no 7714 v2 link (carrot_navi) and no Bluetooth remote
  (carrot_bluetooth).
  """

  def _process_args(self, name: str) -> str:
    """The gate + kwargs of a `PythonProcess("name", "module", <here>),` entry."""
    src = PROCESS_CONFIG.read_text(encoding="utf-8")
    match = re.search(rf'PythonProcess\(\s*["\']{name}["\']\s*,\s*[^,\n]+,\s*([^)]*)\)', src)
    self.assertIsNotNone(match, f"PythonProcess entry for {name!r} not found")
    return match.group(1)

  def test_carrot_navi_is_always_run(self):
    args = self._process_args("carrot_navi")
    self.assertTrue(
      args.startswith("always_run"),
      f"carrot_navi must use always_run (CarrotPilot: 'carrot_navi permanently owns TCP 7714'), "
      f"got {args!r}. Whether its stream reaches the driving stack is the CarrotNaviV2Enabled "
      f"behaviour switch in card.py, not a process gate.")

  def test_carrot_bluetooth_is_always_run_on_comma_hardware(self):
    args = self._process_args("carrot_bluetooth")
    self.assertTrue(
      args.startswith("always_run"),
      f"carrot_bluetooth must use always_run (CarrotPilot: 'always_run, enabled=TICI'), got {args!r}. "
      f"Gating it on CarrotEnabled meant a unit with the master switch off could not pair its remote.")
    self.assertIn(
      "enabled=COMMA_HARDWARE", args,
      "CarrotPilot restricts the Bluetooth daemon to TICI hardware; this fork has no TICI symbol, "
      "so COMMA_HARDWARE (AGNOS present) is the equivalent - without it the daemon would also try "
      "to run on PC dev machines, where evdev Bluetooth HID nodes do not exist.")

  def test_v2_killswitch_is_no_longer_a_process_gate(self):
    src = PROCESS_CONFIG.read_text(encoding="utf-8")
    self.assertNotIn(
      "carrot_navi_v2_enabled", src,
      "the CarrotNaviV2Enabled process gate must stay deleted: carrot_navi is always_run now, and "
      "carrot_man.carrot_man.process_config must not grow a second, contradicting definition of "
      "what that param means.")


class TestBeaconThreadIsNotGated(unittest.TestCase):
  def test_beacon_starts_before_the_enabled_gate(self):
    code = _method_code("tick")
    self.assertIn("_start_background_threads()", code)
    self.assertLess(
      code.index("_start_background_threads()"),
      code.index("if not self._enabled:"),
      "the broadcast / ZMQ / route threads must be started before the `if not self._enabled` "
      "early return, otherwise a disabled device is silent on UDP 7705")

  def test_disabled_branch_does_not_stop_the_beacon(self):
    code = _method_code("tick")
    lines = code.splitlines()
    gate = next(i for i, line in enumerate(lines) if "if not self._enabled:" in line)
    gate_indent = len(lines[gate]) - len(lines[gate].lstrip())
    branch = [lines[gate]]
    for line in lines[gate + 1:]:
      if line.strip() and (len(line) - len(line.lstrip())) <= gate_indent:
        break
      branch.append(line)
    self.assertNotIn(
      "_is_running = False", "\n".join(branch),
      "the disabled branch must not clear _is_running: the beacon thread returns immediately "
      "while that flag is false")

  def test_helper_starts_the_discovery_threads(self):
    code = _method_code("_start_background_threads")
    for name in ("carrot-broadcast", "carrot-zmq", "carrot-route"):
      self.assertIn(name, code, f"{name} thread must be started by _start_background_threads")
    self.assertIn("broadcast_version_info", code,
                  "the 7705 beacon thread (broadcast_version_info) must be started there")


class TestBeaconReachability(unittest.TestCase):
  def test_broadcast_address_enumerates_all_interfaces(self):
    code = _method_code("get_broadcast_address")
    self.assertIn("psutil.net_if_addrs", code,
                  "the beacon must enumerate every interface; a hard-coded interface list "
                  "misses USB / tethering links and the app never sees UDP 7705")
    self.assertNotIn("wlan0", code, "the hard-coded interface list must not come back")
    self.assertIn("netmask", code,
                  "interfaces without an explicit broadcast address must fall back to "
                  "computing it from the netmask")

  def test_network_address_is_published_for_the_web_panel(self):
    code = _method_code("broadcast_version_info")
    self.assertIn("NetworkAddress", code,
                  "the carrot web QR dialog reads NetworkAddress from Params; nothing wrote it, "
                  "so the QR code rendered empty")


if __name__ == "__main__":
  unittest.main()
