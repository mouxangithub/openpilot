"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of zoompilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import pytest

from openpilot.sunnypilot.selfdrive.car.intelligent_cruise_button_management.helpers import icbm_moves_speed_limits
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.common import Mode


@pytest.mark.parametrize(("has_long", "has_icbm", "mode", "moves"), [
  (True, True, Mode.assist, True),
  (True, True, Mode.warning, False),  # warn never moves the set speed
  (True, False, Mode.assist, False),  # alpha long alone: the planner prompts
  (False, True, Mode.assist, False),  # stock ACC: ICBM owns everything, no split to show
])
def test_icbm_moves_speed_limits(has_long, has_icbm, mode, moves):
  assert icbm_moves_speed_limits(has_long, has_icbm, mode) is moves


@pytest.mark.parametrize("mode", [3, None])
def test_mode_as_stored_param(mode):
  # the MICI layout passes the raw param int, the TICI one ui_state's value (None until read)
  assert icbm_moves_speed_limits(True, True, mode) is (mode == 3)
