from types import SimpleNamespace

import numpy as np

from openpilot.common.constants import CV
from openpilot.sunnypilot.selfdrive.controls.lib.lateral_lane_assist import (
  CURVE_OUTWARD_DEADZONE,
  LANE_CENTER_FADE_SPEED_BP,
  LANE_CENTER_MAX_CURV,
  LateralLaneAssist,
  LaneCentering,
  apply_curve_outward_bias,
)


class FakeParams:
  def __init__(self, curve=False, centering=False, lane_line_curve_speed=0):
    self.values = {
      "LateralCurveCuttingCorrection": curve,
      "LateralLaneCentering": centering,
      "UseLaneLineCurveSpeed": lane_line_curve_speed,
    }

  def get_bool(self, key):
    return self.values[key]

  def get_int(self, key):
    return self.values[key]


def make_model(offset_left=0.0, heading_left=0.0, width=3.6, probs=(0.9, 0.9), lane_change=0):
  x = np.arange(0.0, 30.0, 2.0)
  center_right = offset_left + np.tan(heading_left) * x
  lines = [
    SimpleNamespace(x=x, y=center_right - width / 2 - 3.0),
    SimpleNamespace(x=x, y=center_right - width / 2),
    SimpleNamespace(x=x, y=center_right + width / 2),
    SimpleNamespace(x=x, y=center_right + width / 2 + 3.0),
  ]
  return SimpleNamespace(laneLines=lines, laneLineProbs=[0.1, probs[0], probs[1], 0.1],
                         meta=SimpleNamespace(laneChangeState=lane_change))


def test_curve_cutting_correction_is_outward_only_and_speed_scheduled():
  curvature = 0.01
  assert apply_curve_outward_bias(curvature, 30 * CV.KPH_TO_MS) == curvature
  assert apply_curve_outward_bias(CURVE_OUTWARD_DEADZONE / 2, 100 * CV.KPH_TO_MS) == CURVE_OUTWARD_DEADZONE / 2
  for k in (curvature, -curvature):
    corrected = apply_curve_outward_bias(k, 100 * CV.KPH_TO_MS)
    assert 0.0 < abs(corrected) < abs(k)
    assert corrected * k > 0.0


def test_lane_centering_corrects_offset_with_bounded_smooth_request():
  speed = 100 * CV.KPH_TO_MS
  controller = LaneCentering(dt=0.01)
  outputs = [controller.update(make_model(offset_left=0.4), speed, True, False) for _ in range(400)]
  assert outputs[-1] > 0.0  # car left of centre -> positive (right) curvature
  assert max(abs(v) for v in outputs) <= LANE_CENTER_MAX_CURV
  max_step = controller.dt * 0.25 / speed ** 2
  assert max(abs(b - a) for a, b in zip(outputs, outputs[1:], strict=False)) <= max_step + 1e-12


def test_lane_centering_rejects_uncertain_lines_driver_input_and_lane_changes():
  speed = 100 * CV.KPH_TO_MS
  controller = LaneCentering(dt=0.01)
  assert controller.update(make_model(offset_left=0.5, probs=(0.1, 0.1)), speed, True, False) == 0.0
  assert controller.update(make_model(offset_left=0.5), speed, True, True) == 0.0
  assert controller.update(make_model(offset_left=0.5, lane_change=1), speed, True, False) == 0.0


def test_lane_centering_fades_in_above_highway_threshold_and_unwinds_when_inactive():
  speed_low = LANE_CENTER_FADE_SPEED_BP[0] - 1.0
  controller = LaneCentering(dt=0.01)
  assert controller.update(make_model(offset_left=0.5), speed_low, True, False) == 0.0
  speed_high = LANE_CENTER_FADE_SPEED_BP[1] + 1.0
  outputs = [controller.update(make_model(offset_left=0.5), speed_high, True, False) for _ in range(400)]
  assert outputs[-1] > 0.0
  unwound = [controller.update(make_model(offset_left=0.5), speed_high, False, False) for _ in range(100)]
  assert abs(unwound[-1]) < abs(outputs[-1])


def test_assist_settings_are_independent_and_off_by_default():
  disabled = LateralLaneAssist(dt=0.01, params=FakeParams())
  curvature = 0.01
  assert disabled.update(curvature, 100 * CV.KPH_TO_MS, True, False, make_model(offset_left=0.5)) == curvature

  curve_only = LateralLaneAssist(dt=0.01, params=FakeParams(curve=True))
  assert curve_only.update(curvature, 100 * CV.KPH_TO_MS, True, False, make_model()) != curvature
  assert curve_only.update(curvature, 100 * CV.KPH_TO_MS, True, False, make_model(lane_change=1)) == curvature


def test_use_lane_line_curve_speed_gates_the_assist_in_slow_bends():
  """Ported from cp's `lanefull_mode_enabled` coupling.

  `UseLaneLineCurveSpeed` is a km/h threshold on carrot's curve speed. Above it (a
  fast, shallow bend) the lane-line correction still applies; at or below it (a slow,
  tight bend) the model path guides and the correction is suppressed. 0 disables the
  gate, which is the stock default.
  """
  curvature = 0.01
  speed = 100 * CV.KPH_TO_MS
  gate = 30.0  # km/h

  assist = LateralLaneAssist(dt=0.01, params=FakeParams(curve=True, lane_line_curve_speed=gate))
  assert assist.lane_line_curve_speed == gate
  # Fast bend: curve speed above the threshold -> correction still applies.
  assert assist.update(curvature, speed, True, False, make_model(), curve_speed_kph=gate + 20.0) != curvature
  # Slow bend: at or below the threshold -> suppressed, curvature passes through.
  assert assist.update(curvature, speed, True, False, make_model(), curve_speed_kph=gate) == curvature
  assert assist.update(curvature, speed, True, False, make_model(), curve_speed_kph=gate - 20.0) == curvature
  # Sign is irrelevant: only the magnitude of carrot's signed curve speed matters.
  assert assist.update(curvature, speed, True, False, make_model(), curve_speed_kph=-(gate - 20.0)) == curvature
  assert assist.update(-curvature, speed, True, False, make_model(), curve_speed_kph=-(gate + 20.0)) != -curvature


def test_use_lane_line_curve_speed_zero_disables_the_gate():
  """0 (the default) must behave exactly as before the coupling existed."""
  curvature = 0.01
  speed = 100 * CV.KPH_TO_MS
  assist = LateralLaneAssist(dt=0.01, params=FakeParams(curve=True))
  assert assist.lane_line_curve_speed == 0.0
  for curve_kph in (0.0, 5.0, 1e6, float('nan')):
    assert assist.update(curvature, speed, True, False, make_model(), curve_speed_kph=curve_kph) != curvature


def test_curve_speed_gate_reader_tolerates_a_missing_or_bogus_value():
  """An unset param reads back as 0/None on some stores; the gate must stay open."""
  class BadParams(FakeParams):
    def get_int(self, key):
      raise TypeError("not an int")

  assert LateralLaneAssist(dt=0.01, params=BadParams(curve=True)).lane_line_curve_speed == 0.0


def test_update_curve_speed_gate_releases_the_integral_in_slow_bends():
  """A slow bend must not leave the centering integral pushing into the turn."""
  speed = 100 * CV.KPH_TO_MS
  assist = LateralLaneAssist(dt=0.01, params=FakeParams(centering=True, lane_line_curve_speed=30.0))
  for _ in range(200):
    assist.update(0.0, speed, True, False, make_model(offset_left=0.4), curve_speed_kph=90.0)
  assert assist.lane_centering.integral != 0.0
  assist.update_curve_speed_gate(10.0)
  assert assist.lane_centering.integral == 0.0
  # A gate-less configuration is a no-op, so it cannot disturb an untouched device.
  ungated = LateralLaneAssist(dt=0.01, params=FakeParams(centering=True))
  ungated.lane_centering.integral = 0.5
  ungated.update_curve_speed_gate(10.0)
  assert ungated.lane_centering.integral == 0.5
