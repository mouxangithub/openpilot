from pathlib import Path
import re
import unittest


PLANNERD = Path(__file__).parents[1] / "plannerd.py"
CARROT = Path(__file__).parents[3] / "sunnypilot" / "carrot" / "carrot_functions.py"


def _plannerd_subscriptions() -> set[str]:
  """Extract the static service list from plannerd's SubMaster(...) call."""
  text = PLANNERD.read_text(encoding="utf-8")
  m = re.search(r"SubMaster\(\[(.*?)\]", text, re.DOTALL)
  assert m is not None, "plannerd.py: SubMaster(...) list not found"
  # The list ends with a dynamic splice (gps param + live_tracks); keep the
  # statically named entries and assert those separately below.
  return set(re.findall(r"'([A-Za-z0-9_]+)'", m.group(1)))


def _carrot_strong_sm_keys() -> set[str]:
  """Every service carrot_functions dereferences via sm[...] / sm.attr[...].

  A missing key in the consumer's SubMaster raises KeyError at access time
  (not at startup), so an unwired service only explodes mid-drive under the
  right conditions - e.g. the deviceMotion lane-change-gap crash of
  2026-10-31 route 58 seg 1 (blinker + laneChangeState -> plannerd died,
  selfdrived SOFT_DISABLE for the rest of the segment).
  """
  text = CARROT.read_text(encoding="utf-8")
  pat = re.compile(r"sm(?:\.(?:valid|alive|logMonoTime|updated|seen))?\[\s*['\"]([A-Za-z0-9_]+)['\"]\s*\]")
  return set(pat.findall(text))


class TestPlannerdSubscriptionContract(unittest.TestCase):
  def test_device_motion_wired(self):
    """Regression: plannerd must subscribe deviceMotion (carrot gap tracker)."""
    self.assertIn("deviceMotion", _plannerd_subscriptions())

  def test_carrot_sm_keys_subscribed(self):
    """Every strong sm[key] in carrot_functions must exist in plannerd's SubMaster."""
    subs = _plannerd_subscriptions()
    keys = _carrot_strong_sm_keys()
    self.assertTrue(keys, "no sm[...] references parsed - regex drifted")
    missing = keys - subs
    self.assertEqual(missing, set(), f"carrot_functions reads services plannerd never subscribed: {sorted(missing)}")

  def test_core_control_services_present(self):
    """Core onroad services the carrot path depends on must stay subscribed."""
    for svc in ("carState", "modelV2", "radarState", "deviceMotion"):
      self.assertIn(svc, _plannerd_subscriptions())


if __name__ == "__main__":
  import unittest
  unittest.main()
