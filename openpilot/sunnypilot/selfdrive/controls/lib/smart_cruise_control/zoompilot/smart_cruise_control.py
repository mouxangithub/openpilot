"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of zoompilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import openpilot.cereal.messaging as messaging
from openpilot.sunnypilot.selfdrive.controls.lib.smart_cruise_control.zoompilot.vision_controller import SmartCruiseControlVision
from openpilot.sunnypilot.selfdrive.controls.lib.smart_cruise_control.zoompilot.map_controller import SmartCruiseControlMap


class SmartCruiseControl:
  def __init__(self, CP):
    self.vision = SmartCruiseControlVision(CP)
    self.map = SmartCruiseControlMap(CP)

  def update(self, sm: messaging.SubMaster, long_enabled: bool, long_override: bool, v_ego: float, a_ego: float, v_cruise: float) -> None:
    self.map.update(long_enabled, long_override, v_ego, a_ego, v_cruise)
    self.vision.update(sm, long_enabled, long_override, v_ego, a_ego, v_cruise)
