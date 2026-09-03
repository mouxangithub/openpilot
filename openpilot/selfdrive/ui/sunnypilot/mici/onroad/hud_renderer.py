"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import pyray as rl

from openpilot.selfdrive.ui.mici.onroad.hud_renderer import HudRenderer
from openpilot.selfdrive.ui.sunnypilot.onroad.amap_lane_indicators import AmapLaneIndicators
from openpilot.selfdrive.ui.sunnypilot.onroad.blind_spot_indicators import BlindSpotIndicators


class HudRendererSP(HudRenderer):
  def __init__(self):
    super().__init__()
    self.blind_spot_indicators = BlindSpotIndicators()
    self.amap_lane_indicators = AmapLaneIndicators()

  def _update_state(self) -> None:
    super()._update_state()
    self.blind_spot_indicators.update()
    self.amap_lane_indicators.update()

  def _render(self, rect: rl.Rectangle) -> None:
    super()._render(rect)
    self.blind_spot_indicators.render(rect)
    self.amap_lane_indicators.render(rect)

  def _has_blind_spot_detected(self) -> bool:
    return self.blind_spot_indicators.detected
