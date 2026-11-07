"""Realtime scheduling contract for the isolated control cores.

Lesson from 2026-10-31 route 55 (lane-change soft-disables): radarcan shared
core 7 with plannerd at the same SCHED_FIFO priority. Same-priority FIFO tasks
never round-robin, so radarcan's CAN batch bursts - which swell exactly when
the driver signals a lane change - could postpone plannerd past whole modelV2
frames; the conflated frames dropped longitudinalPlan + driverAssistance (both
published by plannerd) below their 16 Hz frequency floor and selfdrived raised
commIssueAvgFreq, soft-disabling control for seconds at a time mid lane change.

The contract: a free-running process whose workload grows with traffic must
never share a SCHED_FIFO priority with another publisher on its core. It sits
strictly below them and consumes only idle time.
"""
import re
import unittest
from pathlib import Path

from openpilot.common.realtime import Priority

OPENPILOT = Path(__file__).resolve().parents[2]

# (file, expected priority) for the processes sharing isolated core 7;
# the pin core itself is asserted too, so a silent re-pin fails loudly
CORE7 = [
  ("selfdrive/modeld/modeld.py", 54),
  ("sunnypilot/modeld_v2/modeld.py", 54),
  ("selfdrive/controls/plannerd.py", Priority.CTRL_LOW),
  ("sunnypilot/carrot/radar/radarcan.py", Priority.TRACKING_LOW),
]


def _pinned_priority(rel: str):
  """The (core, priority-expr) of the file's operative config_realtime_process call."""
  src = (OPENPILOT / rel).read_text(encoding="utf-8")
  calls = re.findall(r"config_realtime_process\(([^)]+)\)", src)
  if not calls:
    raise AssertionError(f"{rel} lost its config_realtime_process call")
  # the last call in main() is the operative one (modeld_v2 pins after load)
  core, prio = calls[-1].split(",", 1)
  return core.strip(), prio.strip()


class TestIsolatedCorePriorityContract(unittest.TestCase):
  def test_priority_ordering(self):
    self.assertLess(Priority.TRACKING_LOW, Priority.CTRL_LOW)
    self.assertLess(Priority.CTRL_LOW, Priority.CTRL_HIGH)

  def test_core7_free_runner_sits_below_every_publisher(self):
    """radarcan (free-running, traffic-proportional) must be strictly below
    every other RT process pinned to core 7. Same-priority FIFO on one core
    lets a CAN burst postpone plannerd past whole modelV2 frames."""
    resolved = {}
    for rel, expected_prio in CORE7:
      core, prio_expr = _pinned_priority(rel)
      self.assertEqual(core, "7", f"{rel} silently re-pinned off core 7")
      try:
        prio = int(prio_expr)
      except ValueError:
        self.assertTrue(prio_expr.startswith("Priority."), f"{rel}: unexpected priority expr {prio_expr!r}")
        prio = getattr(Priority, prio_expr.split(".", 1)[1].strip())
      self.assertEqual(prio, expected_prio, f"{rel} priority drifted from the core-7 contract")
      resolved[rel] = prio

    free_runner = "sunnypilot/carrot/radar/radarcan.py"
    msg = ("must sit strictly below {rel} on core 7; same-priority SCHED_FIFO never round-robins and\n" +
           "CAN bursts would postpone the publisher past whole modelV2 frames")
    for rel in resolved:
      if rel != free_runner:
        self.assertLess(resolved[free_runner], resolved[rel], msg.format(rel=rel))

  def test_core7_pins_unchanged(self):
    """The pins are part of the contract: a silent re-pin invalidates the
    ordering analysis above."""
    self.assertEqual(_pinned_priority("selfdrive/controls/plannerd.py"), ("7", "Priority.CTRL_LOW"))
    self.assertIn("TRACKING_LOW", _pinned_priority("sunnypilot/carrot/radar/radarcan.py")[1])
    self.assertEqual(_pinned_priority("selfdrive/modeld/modeld.py"), ("7", "54"))


if __name__ == "__main__":
  unittest.main()

