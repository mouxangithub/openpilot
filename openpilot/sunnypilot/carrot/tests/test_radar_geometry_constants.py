"""The radar->camera frame offset must be one physical constant everywhere.

``RADAR_TO_CAMERA`` (1.52 m) was copied into six modules. The carrot production
path now imports one source (``carrot.radar_geometry``), while the upstream
``radard.py`` keeps its own copy (the upstream tree must not import sunnypilot)
and the offline replay tools keep literals (they deliberately avoid importing
the live tree). A copy that drifts makes vision and radar disagree on distance
silently - no error, just a wrong lead distance. This test pins every copy to
the same value and forces an explicit update here if one moves.
"""
import ast
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
CARROT = os.path.join(REPO, "openpilot", "sunnypilot", "carrot")
CONTROLS = os.path.join(REPO, "openpilot", "selfdrive", "controls")

EXPECTED = 1.52

# module-relative path -> how the value is declared there. The live path
# imports the single source; radard and the offline tools keep a literal that
# must agree with it.
LITERAL_COPIES = (
  (CONTROLS, "radard.py", r"^RADAR_TO_CAMERA\s*=\s*([0-9.]+)"),
  (CARROT, os.path.join("radar", "route_replay", "config.py"), r"^RADAR_TO_CAMERA_M\s*=\s*([0-9.]+)"),
  (CARROT, os.path.join("radar", "tools", "radar_validation_replay.py"), r"^RADAR_TO_CAMERA\s*=\s*([0-9.]+)"),
  (CARROT, os.path.join("radar_motion", "primary.py"), None),  # now an import, must not define
  (CARROT, "carrot_functions.py", None),                       # now an import, must not define
)


def _read(path):
  with open(path, encoding="utf-8") as f:
    return f.read()


class TestRadarCameraOffset(unittest.TestCase):
  def test_single_source_value(self):
    # Import the source without pulling the whole controls package.
    import sys
    if REPO not in sys.path:
      sys.path.insert(0, REPO)
    from openpilot.sunnypilot.carrot.radar_geometry import RADAR_TO_CAMERA_M
    self.assertEqual(RADAR_TO_CAMERA_M, EXPECTED)

  def test_literal_copies_agree(self):
    for directory, rel, pattern in LITERAL_COPIES:
      path = os.path.join(directory, rel)
      self.assertTrue(os.path.exists(path), f"missing {rel}")
      text = _read(path)
      if pattern is None:
        # Live modules must import the constant, not redefine the 1.52 literal.
        self.assertNotIn("= 1.52", text, f"{rel} redefines the radar offset; import it")
        continue
      match = re.search(pattern, text, re.M)
      self.assertIsNotNone(match, f"{rel}: no RADAR_TO_CAMERA assignment found")
      self.assertAlmostEqual(float(match.group(1)), EXPECTED,
                             msg=f"{rel} drifted from carrot.radar_geometry")


if __name__ == "__main__":
  unittest.main()
