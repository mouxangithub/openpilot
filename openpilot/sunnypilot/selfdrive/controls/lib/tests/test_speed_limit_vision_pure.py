"""
Pure-logic unit tests for the vision speed-limit daemon
(openpilot.sunnypilot.system.speed_limit_vision) and its CPU throttle helper.

These cover the importable-on-any-machine pure functions and constants only:
the daemon itself requires VisionIPC/cereal/ONNX runtime and is only exercised
on device. No cv2 or messaging is touched here.
"""

import numpy as np
import pytest

from openpilot.common.constants import CV
from openpilot.sunnypilot.common.cpu_throttle import (
  DEVICE_BUSY_AVG_CPU_USAGE_PERCENT as THROTTLE_AVG_CPU_USAGE_PERCENT,
  DEVICE_BUSY_HOT_CORE_COUNT as THROTTLE_HOT_CORE_COUNT,
  _compute_throttle_factor,
  device_cpu_throttle_factor,
)
from openpilot.sunnypilot.system.speed_limit_vision import (
  DEVICE_BUSY_AVG_CPU_USAGE_PERCENT,  # daemon busy gate constants (distinct from the cpu_throttle factor constants)
  DEVICE_BUSY_HOT_CORE_COUNT,
  MEMORY_CRITICAL_AVAILABLE_KB,
  MEMORY_CRITICAL_USAGE_PERCENT,
  MEMORY_PRESSURE_AVAILABLE_KB,
  MEMORY_PRESSURE_USAGE_PERCENT,
  SPEED_LIMIT_CLASSES,
  SpeedLimitVisionDaemon,
  US_CLASSIFIER_SPEED_VALUES,
  US_DETECTOR_CLASSES,
  VALID_SPEED_LIMITS_MPH,
  device_cpu_usage_busy,
  memory_pressure_level,
)


class TestConstants:
  def test_us_classifier_values_are_publishable(self):
    # every value the classifier can output must be a publishable mph limit
    assert set(US_CLASSIFIER_SPEED_VALUES) <= VALID_SPEED_LIMITS_MPH

  def test_legacy_model_classes_map_to_valid_limits(self):
    # legacy detector class ids must map onto mph values the OCR path accepts
    assert set(SPEED_LIMIT_CLASSES.values()) <= VALID_SPEED_LIMITS_MPH

  def test_detector_classes_use_expected_ids(self):
    # 0 = regulatory, 1 = advisory (skipped), 2 = school zone
    assert US_DETECTOR_CLASSES == {
      0: "regulatory_speed_limit",
      1: "advisory_speed_limit",
      2: "school_zone_speed_limit",
    }

  def test_valid_limits_span_5_to_120_in_steps_of_5(self):
    assert min(VALID_SPEED_LIMITS_MPH) == 5
    assert max(VALID_SPEED_LIMITS_MPH) == 120
    assert all(value % 5 == 0 for value in VALID_SPEED_LIMITS_MPH)


class TestMemoryPressure:
  def test_normal_when_no_inputs(self):
    assert memory_pressure_level(None, None) == "normal"

  def test_pressure_thresholds(self):
    assert memory_pressure_level(MEMORY_PRESSURE_AVAILABLE_KB, None) == "pressure"
    assert memory_pressure_level(MEMORY_PRESSURE_AVAILABLE_KB + 1, None) == "normal"
    assert memory_pressure_level(None, MEMORY_PRESSURE_USAGE_PERCENT) == "pressure"
    assert memory_pressure_level(None, MEMORY_PRESSURE_USAGE_PERCENT - 1) == "normal"

  def test_critical_thresholds(self):
    assert memory_pressure_level(MEMORY_CRITICAL_AVAILABLE_KB, None) == "critical"
    assert memory_pressure_level(None, MEMORY_CRITICAL_USAGE_PERCENT) == "critical"
    # critical wins over normal on the other axis
    assert memory_pressure_level(MEMORY_CRITICAL_AVAILABLE_KB, 1.0) == "critical"


class TestDeviceCpuBusy:
  def test_empty_usage_is_never_busy(self):
    assert device_cpu_usage_busy([]) is False

  def test_below_average_threshold_not_busy(self):
    assert device_cpu_usage_busy([10.0] * 8) is False

  def test_average_over_threshold_is_busy(self):
    usage = [DEVICE_BUSY_AVG_CPU_USAGE_PERCENT + 1.0] * 8
    assert device_cpu_usage_busy(usage) is True

  def test_hot_cores_trigger_busy_even_at_low_average(self):
    usage = [100.0] * DEVICE_BUSY_HOT_CORE_COUNT + [0.0] * 4
    assert sum(usage) / len(usage) < DEVICE_BUSY_AVG_CPU_USAGE_PERCENT
    assert device_cpu_usage_busy(usage) is True


class TestCpuThrottleFactor:
  # The throttle factor uses cpu_throttle's own constants (74/89), not the
  # daemon busy-gate constants (78/92) imported above.
  def test_idle_usage_gives_unit_factor(self):
    assert _compute_throttle_factor(THROTTLE_AVG_CPU_USAGE_PERCENT - 1, 0) == 1.0

  def test_average_over_threshold_scales_linearly(self):
    average = THROTTLE_AVG_CPU_USAGE_PERCENT + 8.0
    assert _compute_throttle_factor(average, 0) == pytest.approx(2.0)

  def test_hot_cores_add_half_a_step_each(self):
    assert _compute_throttle_factor(0.0, THROTTLE_HOT_CORE_COUNT) == pytest.approx(1.5)
    assert _compute_throttle_factor(0.0, THROTTLE_HOT_CORE_COUNT + 1) == pytest.approx(2.0)

  def test_factor_is_clamped_to_four(self):
    assert _compute_throttle_factor(200.0, 50) == 4.0

  def test_low_pass_filter_rises_and_recovers(self):
    busy = [100.0] * 8
    for _ in range(10):
      factor = device_cpu_throttle_factor(busy, name="test_rise", cores=None)
    assert factor > 1.0

    idle = [0.0] * 8
    for _ in range(100):
      factor = device_cpu_throttle_factor(idle, name="test_rise", cores=None)
    assert factor == pytest.approx(1.0, abs=0.1)


class TestClassifierOutputNormalization:
  def test_softmax_sums_to_one(self):
    scores = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    probabilities = SpeedLimitVisionDaemon._softmax(scores)
    assert probabilities.sum() == pytest.approx(1.0)
    assert probabilities[-1] == pytest.approx(np.exp(2.0) / (np.exp(0.0) + np.exp(1.0) + np.exp(2.0)))

  def test_softmax_shift_invariance(self):
    scores = np.array([1000.0, 1001.0, 1002.0], dtype=np.float32)
    probabilities = SpeedLimitVisionDaemon._softmax(scores)
    assert np.all(np.isfinite(probabilities))
    assert probabilities.sum() == pytest.approx(1.0)

  def test_already_normalized_scores_pass_through(self):
    scores = np.array([0.2, 0.3, 0.5], dtype=np.float32)
    probabilities = SpeedLimitVisionDaemon._normalize_classifier_output(scores)
    assert probabilities.sum() == pytest.approx(1.0)
    assert probabilities[2] == pytest.approx(0.5)

  def test_unnormalized_scores_get_softmaxed(self):
    scores = np.array([0.2, 0.3, 0.9], dtype=np.float32)
    probabilities = SpeedLimitVisionDaemon._normalize_classifier_output(scores)
    assert probabilities.sum() == pytest.approx(1.0)
    # argmax must be preserved
    assert int(np.argmax(probabilities)) == 2

  def test_empty_scores(self):
    assert SpeedLimitVisionDaemon._normalize_classifier_output(np.array([], dtype=np.float32)).size == 0


class TestGeometryHelpers:
  def test_crop_by_ratio_clips_to_image(self):
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    crop = SpeedLimitVisionDaemon._crop_by_ratio(image, 0.1, 0.2, 0.9, 0.8)
    assert crop is not None
    assert crop.shape == (60, 160, 3)

  def test_crop_by_ratio_invalid_region_returns_none(self):
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    assert SpeedLimitVisionDaemon._crop_by_ratio(image, 0.9, 0.9, 0.1, 0.1) is None
    assert SpeedLimitVisionDaemon._crop_by_ratio(image, 0.5, 0.5, 0.5, 0.5) is None

  def test_clamp_track_bbox_clips_and_rejects_empty_boxes(self):
    assert SpeedLimitVisionDaemon._clamp_track_bbox((-5, -5, 50, 40), 100, 80) == (0, 0, 50, 40)
    assert SpeedLimitVisionDaemon._clamp_track_bbox((50, 50, 150, 100), 100, 80) == (50, 50, 100, 80)
    assert SpeedLimitVisionDaemon._clamp_track_bbox((60, 60, 55, 80), 100, 80) is None

  def test_speed_conversions_match_cv(self):
    # the daemon converts published mph values through the CV table
    assert CV.MPH_TO_MS * 60 == pytest.approx(26.8224)
    assert CV.MS_TO_KPH == pytest.approx(3.6)
    assert CV.KPH_TO_MS * CV.MS_TO_KPH == pytest.approx(1.0)
