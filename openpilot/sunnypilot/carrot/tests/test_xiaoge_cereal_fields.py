"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Regression tests for xiaoge cereal-field compatibility.

Three crashes so far have had the same shape: a CarrotPilot (cp) model / car-state
extension is read straight off a capnp reader, but this fork's schema does not define
it.  pycapnp then raises ``AttributeError: struct has no such member`` at runtime, which
``py_compile`` and static imports cannot catch:

  * ``xiaoge_data.py``   -> ``carState.leftLatDist``
  * ``xiaoge_data.py``   -> ``modelV2.meta.distanceToRoadEdgeLeft`` / ``...Right``
  * ``v_asm_server.py``  -> ``modelV2.meta.laneWidthLeft`` / ``...Right`` (killed the
    wide-road camera thread on the first lane change)

So there are two jobs here: pin the fail-closed behaviour of the lane-width reader, and
fail if any carrot source starts raw-accessing a known cp-only field again.
"""
import re
import unittest
from pathlib import Path

from openpilot.sunnypilot.carrot.xiaoge.xiaoge_vision import lane_width_meters

VASM_MIN_LANE_WIDTH_METERS = 3.0

CARROT_ROOT = Path(__file__).resolve().parents[1]

# cp-only cereal members that this fork's schemas do not define.  Keep in sync with the
# field list produced by diffing cp's car.capnp / log.capnp against this fork's.
CP_ONLY_FIELDS = (
  "leftLatDist",
  "rightLatDist",
  "distanceToRoadEdgeLeft",
  "distanceToRoadEdgeRight",
  "laneWidthLeft",
  "laneWidthRight",
)

# ``.field`` (not ``"field"``): only a real attribute access trips this, so the
# ``getattr(x, "field", default)`` and ``lane_width_meters(x, "field")`` patterns stay legal.
RAW_ACCESS_RE = re.compile(r"\.(" + "|".join(CP_ONLY_FIELDS) + r")\b")


class StubReader:
  """Mimics pycapnp's _DynamicStructReader: unknown members raise AttributeError."""

  def __init__(self, **fields):
    self.__dict__.update(fields)

  def __getattr__(self, name):
    raise AttributeError(f"capnp/schema.c++:511: failed: struct has no such member; name = {name}")


class TestLaneWidthMeters(unittest.TestCase):
  def test_missing_field_fails_closed(self):
    # The on-device case: cp defines laneWidthLeft, this fork's ModelDataV2.MetaData does not.
    reader = StubReader(laneChangeDirection=1)
    self.assertEqual(lane_width_meters(reader, "laneWidthLeft"), 0.0)

  def test_present_field_is_returned(self):
    reader = StubReader(laneWidthLeft=3.4, laneWidthRight=2.8)
    self.assertEqual(lane_width_meters(reader, "laneWidthLeft"), 3.4)
    self.assertEqual(lane_width_meters(reader, "laneWidthRight"), 2.8)

  def test_none_and_garbage_values_fall_back_to_zero(self):
    self.assertEqual(lane_width_meters(StubReader(laneWidthLeft=None), "laneWidthLeft"), 0.0)
    self.assertEqual(lane_width_meters(StubReader(laneWidthLeft="warp"), "laneWidthLeft"), 0.0)

  def test_gate_stays_inactive_when_width_is_unavailable(self):
    # fail-closed: without a verifiable lane width the VASM blindspot gate must not open.
    width = lane_width_meters(StubReader(laneChangeDirection=1), "laneWidthLeft")
    self.assertFalse(width >= VASM_MIN_LANE_WIDTH_METERS)

  def test_gate_opens_only_for_wide_enough_lanes(self):
    reader = StubReader(laneWidthLeft=3.4, laneWidthRight=2.8)
    self.assertTrue(lane_width_meters(reader, "laneWidthLeft") >= VASM_MIN_LANE_WIDTH_METERS)
    self.assertFalse(lane_width_meters(reader, "laneWidthRight") >= VASM_MIN_LANE_WIDTH_METERS)


class TestNoRawCpOnlyFieldAccess(unittest.TestCase):
  """A source-level guard for the recurring schema-drift crash."""

  def test_carrot_sources_wrap_cp_only_fields(self):
    offenders = []
    for path in sorted(CARROT_ROOT.rglob("*.py")):
      if "tests" in path.parts:
        continue
      for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("#"):
          continue
        match = RAW_ACCESS_RE.search(line)
        if match:
          offenders.append(f"{path.relative_to(CARROT_ROOT.parent.parent)}:{lineno}: {line.strip()}")
    self.assertEqual(offenders, [], "raw cp-only cereal access found; use getattr(...) or lane_width_meters(...): \n" + "\n".join(offenders))


if __name__ == "__main__":
  unittest.main()
