"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""
Regression test for S1 / E1 of the speed-limit unification.

The carrot phone "SPEED" remote command writer (``VCruiseHelper.process_carrot_speed_cmd``)
was removed: sunnypilot's Speed Limit Assist (SLA) is the single executor of the
road-speed-limit target, so no competing writer may silently change ``CS.vCruise``.

The other ``carrotCmd`` commands (LANECHANGE / OVERTAKE in ``desire_helper.py``,
DISPLAY, heartbeat) intentionally remain and are not touched by this change.
"""
from openpilot.common.test import OpenpilotTestCase
from openpilot.selfdrive.car.cruise import VCruiseHelper


class TestCarrotSpeedCommandRemoved(OpenpilotTestCase):
  def test_process_carrot_speed_cmd_is_gone(self) -> None:
    # The removed writer must not exist on VCruiseHelper, otherwise it could
    # again lower/raise CS.vCruise from a phone "SPEED" command.
    assert not hasattr(VCruiseHelper, "process_carrot_speed_cmd")
