"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of zoompilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

The tici models panel's driving options, for the comma 4 models panel.
"""
from collections.abc import Callable

from openpilot.common.constants import CV
from openpilot.selfdrive.ui.sunnypilot.mici.widgets.button import BigParamControlSP, BigParamOption, speed_unit
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.multilang import tr


def _per_mph() -> float:
  """Display units per mph: LaneTurnValue is stored in mph."""
  return CV.MPH_TO_KPH if ui_state.is_metric else 1


def _hundredths(v: int) -> str:
  return f"{v / 100:.2f}"


def _option(title: str, param: str, fmt: Callable[[int], str], unit: str | Callable[[], str], **kwargs) -> BigParamOption:
  """A float param, x100 in the picker, whose button reads the picker label and the unit."""
  unit_text = unit if callable(unit) else lambda: unit
  return BigParamOption(title, param, float_param=True, label_callback=lambda v: f"{fmt(v)} {unit_text()}",
                        picker_label_callback=fmt, picker_unit=unit, **kwargs)


class ModelOptions:
  def __init__(self):
    # modeld_v2 runs Blendful and the camera offset; stock modeld, which runs the Default model, does neither
    self.lane_center = BigParamControlSP(tr("lane center assist"), "Blendful", depends_on=lambda: ui_state.active_runner_tinygrad,
                                         description=tr("Alpha. Nudges the car toward the middle of the lane, more when the lines are clear.\n" +
                                                        "Yields around obstacles. Not with the Default model."))

    self.lane_turn = BigParamControlSP(tr("lane turn desires"), "LaneTurnDesire",
                                       description=tr("With the blinker on below the lane turn speed, plans the turn that way.\n" +
                                                      "Stops the car picking the wrong turn at a red light."))
    # a metric step of 0.62 mph lands on each whole km/h, as the tici panel steps it
    self.lane_turn_speed = _option(tr("lane turn speed"), "LaneTurnValue", lambda v: str(round(v / 100 * _per_mph())), speed_unit,
                                   min_value=500, max_value=2000, value_change_step=lambda: round(100 / _per_mph()),
                                   description=tr("Lane turn desires work at or below this speed."))
    self.lane_turn_speed.set_enabled(lambda: self.lane_turn._checked)

    self.live_delay = BigParamControlSP(tr("live steer delay"), "LagdToggle",
                                        description=tr("Learns how long your car takes to respond to steering as you drive.\n" +
                                                       "On is stock openpilot."))
    self.steer_delay = _option(tr("manual steer delay"), "LagdToggleDelay", _hundredths, "s", min_value=5, max_value=50,
                               description=tr("The software delay used while live steer delay is off.\nDefault is 0.20 s."))
    self.steer_delay.set_enabled(lambda: not self.live_delay._checked)

    self.camera_offset = _option(tr("camera offset"), "CameraOffset", _hundredths, "m", min_value=-35, max_value=35,
                                 description=tr("Shifts where the model thinks the camera sits.\n" +
                                                "Positive moves the car left, negative right. Not with the Default model."))
    self.camera_offset.set_enabled(lambda: ui_state.active_runner_tinygrad)

    # between the panel's jetlink and refresh models rows; lane_center sits above them
    self.items = [self.lane_turn, self.lane_turn_speed, self.live_delay, self.steer_delay, self.camera_offset]

  def refresh(self):
    for item in self.items:
      item.refresh()
