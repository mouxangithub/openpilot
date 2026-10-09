"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of zoompilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

Speed-binned learning in torqued: bin layout, point routing, the published message, the
toggle gates and the per-bin fit. The cache lives in test_torqued_cache_restore.py.
"""
import numpy as np
from unittest import mock

from opendbc.car.mazda.values import MazdaFlags
from openpilot.selfdrive.locationd.torqued import TorqueEstimator, TorqueBuckets, VERSION, MIN_FILTER_DECAY, POINTS_PER_BUCKET, \
  STEER_BUCKET_BOUNDS
from openpilot.sunnypilot.selfdrive.locationd.torqued_ext import (
  DEFAULT_SPEED_BIN_BOUNDS as SPEED_BIN_BOUNDS, DEFAULT_SPEED_BIN_CENTERS as SPEED_BIN_CENTERS,
  TorqueEstimatorExt,
)
from openpilot.sunnypilot.selfdrive.locationd.tests.speed_dep_helpers import (
  SPEED_DEP_CARS, SPEED_DEP_FINGERPRINT, NON_SPEED_DEP_FINGERPRINT, FakePubMaster, get_car_bins, make_cp,
)
from openpilot.common.test import OpenpilotTestCase


def _published(est, **kwargs):
  """get_msg through a captured PubMaster: (lateralTorqueParameters, liveTorqueParametersSP)."""
  est._pm = FakePubMaster()
  msg = est.get_msg(**kwargs)
  return msg.lateralTorqueParameters, est._pm.last()


needs_speed_dep_car = SPEED_DEP_FINGERPRINT is None


def _make_estimator(CP=None, fake_params=None):
  """Helper to construct a TorqueEstimator with FakeParams routed."""
  if fake_params is None:
    fake_params = FakeParams()
  with mock.patch.object(TorqueEstimator.__bases__[0].__bases__[0], 'Params', return_value=fake_params) if hasattr(TorqueEstimator.__bases__[0], '__bases__') else None:
    pass
  # Route Params for both torqued and torqued_ext
  import openpilot.selfdrive.locationd.torqued as torqued_mod
  import openpilot.sunnypilot.selfdrive.locationd.torqued_ext as torqued_ext_mod
  original_torqued_params = getattr(torqued_mod, 'Params', None)
  original_ext_params = getattr(torqued_ext_mod, 'Params', None)
  torqued_mod.Params = lambda: fake_params
  torqued_ext_mod.Params = lambda: fake_params
  try:
    est = TorqueEstimator(CP if CP is not None else make_cp())
  finally:
    if original_torqued_params is not None:
      torqued_mod.Params = original_torqued_params
    if original_ext_params is not None:
      torqued_ext_mod.Params = original_ext_params
  return est


class TestSpeedDepConfig(OpenpilotTestCase):
  """Config-level checks that need no estimator."""

  def test_speed_dep_config_has_entries(self):
    self.assertGreater(len(SPEED_DEP_CARS), 0)

  def test_version_exists(self):
    self.assertGreaterEqual(VERSION, 1)

  def test_speed_bin_bounds_cover_full_range(self):
    all_bounds = [b for bounds in SPEED_BIN_BOUNDS for b in bounds]
    self.assertEqual(min(all_bounds), 5)
    self.assertGreaterEqual(max(all_bounds), 35)

  def test_speed_bin_centers_match_bounds(self):
    for center, (lo, hi) in zip(SPEED_BIN_CENTERS, SPEED_BIN_BOUNDS):
      self.assertGreaterEqual(center, lo)
      self.assertLessEqual(center, hi)


class TestCentersToBounds(OpenpilotTestCase):

  def test_midpoints_between_centers(self):
    bounds = TorqueEstimatorExt._centers_to_bounds([10.0, 20.0, 30.0])
    self.assertEqual(bounds[0], (5, 15.0))   # lo=DEFAULT[0][0], hi=midpoint(10,20)
    self.assertEqual(bounds[1], (15.0, 25.0))
    self.assertEqual(bounds[2], (25.0, 40))  # hi=DEFAULT[-1][1]

  def test_single_center(self):
    bounds = TorqueEstimatorExt._centers_to_bounds([20.0])
    self.assertEqual(bounds, [(5, 40)])

  def test_edges_use_default_bounds(self):
    bounds = TorqueEstimatorExt._centers_to_bounds([7.0, 35.0])
    self.assertEqual(bounds[0][0], 5)    # DEFAULT_SPEED_BIN_BOUNDS[0][0]
    self.assertEqual(bounds[-1][1], 40)  # DEFAULT_SPEED_BIN_BOUNDS[-1][1]
    self.assertAlmostEqual(bounds[0][1], (7.0 + 35.0) / 2)
    self.assertAlmostEqual(bounds[1][0], (7.0 + 35.0) / 2)

  def test_contiguous_coverage(self):
    """Each bin's upper bound must equal the next bin's lower bound."""
    centers = [8.0, 15.0, 22.0, 30.0]
    bounds = TorqueEstimatorExt._centers_to_bounds(centers)
    for i in range(len(bounds) - 1):
      self.assertAlmostEqual(bounds[i][1], bounds[i + 1][0])


@unittest.skipIf(needs_speed_dep_car, "No cars in speed_dependent.toml")
class TestSpeedBinnedLearning(OpenpilotTestCase):
  """Self-tune on, on a configured car."""

  def setUp(self):
    super().setUp()
    self.fake_params = FakeParams()
    import openpilot.selfdrive.locationd.torqued as torqued_mod
    import openpilot.sunnypilot.selfdrive.locationd.torqued_ext as torqued_ext_mod
    self._patch_torqued = mock.patch.object(torqued_mod, 'Params', lambda: self.fake_params)
    self._patch_ext = mock.patch.object(torqued_ext_mod, 'Params', lambda: self.fake_params)
    self._patch_torqued.start()
    self._patch_ext.start()
    self.addCleanup(self._patch_torqued.stop)
    self.addCleanup(self._patch_ext.stop)

  def test_speed_bins_initialized(self):
    for fingerprint in SPEED_DEP_CARS:
      centers, bounds = get_car_bins(fingerprint)
      est = TorqueEstimator(make_cp(fingerprint=fingerprint))
      self.assertTrue(est.speed_binned)
      self.assertEqual(len(est.speed_bin_points), len(bounds))

  def test_speed_bin_routing(self):
    centers, bounds = get_car_bins(SPEED_DEP_FINGERPRINT)
    for bin_idx, (lo, hi) in enumerate(bounds):
      est = TorqueEstimator(make_cp())
      vego = (lo + hi) / 2.0
      est._on_torque_point(0.1, 0.3, vego)
      self.assertEqual(len(est.speed_bin_points[bin_idx]), 1,
        f"bin {bin_idx} ({lo}-{hi} m/s) should have 1 point at vego={vego}")
      for j in range(len(bounds)):
        if j != bin_idx:
          self.assertEqual(len(est.speed_bin_points[j]), 0,
            f"bin {j} should be empty when vego={vego}")

  def test_fork_message_fields(self):
    """The bins ride on the fork message published beside the upstream one, which stays
    upstream's own (no speed-bin fields on lateralTorqueParameters)."""
    for fingerprint in SPEED_DEP_CARS:
      centers, bounds = get_car_bins(fingerprint)
      est = TorqueEstimator(make_cp(fingerprint=fingerprint))
      ltp, sp = _published(est)
      self.assertFalse(hasattr(ltp, 'speedBinCenters'))
      self.assertEqual(sp.version, VERSION)
      self.assertEqual(len(sp.speedBinCenters), len(centers))
      self.assertEqual(len(sp.speedBinLatAccelFactors), len(bounds))
      self.assertEqual(len(sp.speedBinFrictions), len(bounds))
      self.assertEqual(len(sp.speedBinValid), len(bounds))
      self.assertEqual(len(sp.speedBinPoints), 0)

  def test_fork_message_once_per_frame_at_upstream_validity(self):
    """torqued calls get_msg twice on a cache frame; the fork message goes out once per
    frame, carrying the validity of the upstream message it accompanies."""
    est = TorqueEstimator(make_cp())
    est._pm = FakePubMaster()
    est.get_msg(valid=False)
    est.get_msg(valid=False, with_points=True)
    self.assertEqual(len(est._pm.sent), 1)
    self.assertIs(est._pm.sent[0][1].valid, False)
    est.frame += 1
    est.get_msg(valid=True)
    self.assertEqual(len(est._pm.sent), 2)
    self.assertIs(est._pm.sent[1][1].valid, True)

  def test_global_fit_unchanged(self):
    est = TorqueEstimator(make_cp(lat_accel_factor=1.25, friction=0.125))
    msg = est.get_msg()
    ltp = msg.lateralTorqueParameters
    self.assertAlmostEqual(ltp.latAccelFactorFiltered, 1.25, places=2)
    self.assertAlmostEqual(ltp.frictionCoefficientFiltered, 0.125, places=3)

  def test_global_buckets_still_require_min_vel(self):
    est = TorqueEstimator(make_cp())
    self.assertEqual(len(est.filtered_points), 0)


class TestSelfTuneGate(OpenpilotTestCase):
  """Speed-dep runs wherever self-tune does, with no toggle of its own."""

  def _cp(self, brand):
    return make_cp(fingerprint=NON_SPEED_DEP_FINGERPRINT, brand=brand)

  def test_follows_self_tune_toyota(self):
    """toyota self-tunes bare (upstream brand gate)."""
    fake_params_off = FakeParams(self_tune_on=False)
    import openpilot.selfdrive.locationd.torqued as torqued_mod
    import openpilot.sunnypilot.selfdrive.locationd.torqued_ext as torqued_ext_mod
    with mock.patch.object(torqued_mod, 'Params', lambda: fake_params_off):
      with mock.patch.object(torqued_ext_mod, 'Params', lambda: fake_params_off):
        self.assertTrue(TorqueEstimator(self._cp('toyota')).speed_binned)
        fake_params_off.bools.add("EnforceTorqueControl")
        self.assertFalse(TorqueEstimator(self._cp('toyota')).speed_binned)
        fake_params_off.bools.add("LiveTorqueParamsToggle")
        self.assertTrue(TorqueEstimator(self._cp('toyota')).speed_binned)

  def test_follows_self_tune_mazda(self):
    """mazda does not self-tune bare (no steer-to-zero EPS)."""
    fake_params_off = FakeParams(self_tune_on=False)
    import openpilot.selfdrive.locationd.torqued as torqued_mod
    import openpilot.sunnypilot.selfdrive.locationd.torqued_ext as torqued_ext_mod
    with mock.patch.object(torqued_mod, 'Params', lambda: fake_params_off):
      with mock.patch.object(torqued_ext_mod, 'Params', lambda: fake_params_off):
        self.assertFalse(TorqueEstimator(self._cp('mazda')).speed_binned)

  def test_manual_override_keeps_bins(self):
    """The override pauses the learner's output, not the learner."""
    fake_params = FakeParams()
    fake_params.bools.update({"CustomTorqueParams", "TorqueParamsOverrideEnabled"})
    fake_params.store.update({"TorqueParamsOverrideLatAccelFactor": 2.0, "TorqueParamsOverrideFriction": 0.1})
    import openpilot.selfdrive.locationd.torqued as torqued_mod
    import openpilot.sunnypilot.selfdrive.locationd.torqued_ext as torqued_ext_mod
    with mock.patch.object(torqued_mod, 'Params', lambda: fake_params):
      with mock.patch.object(torqued_ext_mod, 'Params', lambda: fake_params):
        est = TorqueEstimator(make_cp(fingerprint=NON_SPEED_DEP_FINGERPRINT))
        self.assertTrue(est.speed_binned)
        self.assertFalse(est.use_params)


class TestBackwardCompatibility(OpenpilotTestCase):
  """Cars without self-tune are unaffected."""

  def setUp(self):
    super().setUp()
    self.fake_params_off = FakeParams(self_tune_on=False)
    import openpilot.selfdrive.locationd.torqued as torqued_mod
    import openpilot.sunnypilot.selfdrive.locationd.torqued_ext as torqued_ext_mod
    self._patch_torqued = mock.patch.object(torqued_mod, 'Params', lambda: self.fake_params_off)
    self._patch_ext = mock.patch.object(torqued_ext_mod, 'Params', lambda: self.fake_params_off)
    self._patch_torqued.start()
    self._patch_ext.start()
    self.addCleanup(self._patch_torqued.stop)
    self.addCleanup(self._patch_ext.stop)

  def test_unconfigured_car_no_speed_bins(self):
    est = TorqueEstimator(make_cp(fingerprint=NON_SPEED_DEP_FINGERPRINT))
    self.assertFalse(est.speed_binned)

  def test_unconfigured_car_publishes_empty_bins(self):
    """The fork message still goes out (consumers check it alive), with no bins."""
    est = TorqueEstimator(make_cp(fingerprint=NON_SPEED_DEP_FINGERPRINT))
    _, sp = _published(est)
    self.assertEqual(sp.version, VERSION)
    self.assertEqual(len(sp.speedBinCenters), 0)
    self.assertEqual(len(sp.speedBinLatAccelFactors), 0)
    self.assertEqual(len(sp.speedBinFrictions), 0)
    self.assertEqual(len(sp.speedBinValid), 0)

  def test_unconfigured_car_global_params_still_work(self):
    est = TorqueEstimator(make_cp(fingerprint=NON_SPEED_DEP_FINGERPRINT, lat_accel_factor=2.0, friction=0.15))
    msg = est.get_msg()
    ltp = msg.lateralTorqueParameters
    self.assertAlmostEqual(ltp.latAccelFactorFiltered, 2.0, places=2)
    self.assertAlmostEqual(ltp.frictionCoefficientFiltered, 0.15, places=3)
    self.assertFalse(est.speed_binned)

  def test_unconfigured_car_no_speed_bin_attributes(self):
    est = TorqueEstimator(make_cp(fingerprint=NON_SPEED_DEP_FINGERPRINT))
    self.assertFalse(hasattr(est, 'speed_bin_points'))
    self.assertFalse(hasattr(est, 'speed_bin_filtered'))

  def test_cal_percent_works_for_both(self):
    fake_params = FakeParams()
    import openpilot.selfdrive.locationd.torqued as torqued_mod
    import openpilot.sunnypilot.selfdrive.locationd.torqued_ext as torqued_ext_mod
    with mock.patch.object(torqued_mod, 'Params', lambda: fake_params):
      with mock.patch.object(torqued_ext_mod, 'Params', lambda: fake_params):
        fingerprints = [NON_SPEED_DEP_FINGERPRINT]
        if SPEED_DEP_FINGERPRINT:
          fingerprints.append(SPEED_DEP_FINGERPRINT)
        for fp in fingerprints:
          est = TorqueEstimator(make_cp(fingerprint=fp))
          msg = est.get_msg()
          self.assertEqual(msg.lateralTorqueParameters.calPerc, 0)


class TestUnconfiguredCarSelfTuneOn(OpenpilotTestCase):
  """An unconfigured car with self-tune on gets the default bins and the offline seeds."""

  def setUp(self):
    super().setUp()
    self.fake_params = FakeParams()
    import openpilot.selfdrive.locationd.torqued as torqued_mod
    import openpilot.sunnypilot.selfdrive.locationd.torqued_ext as torqued_ext_mod
    self._patch_torqued = mock.patch.object(torqued_mod, 'Params', lambda: self.fake_params)
    self._patch_ext = mock.patch.object(torqued_ext_mod, 'Params', lambda: self.fake_params)
    self._patch_torqued.start()
    self._patch_ext.start()
    self.addCleanup(self._patch_torqued.stop)
    self.addCleanup(self._patch_ext.stop)

  def test_default_bins_created(self):
    est = TorqueEstimator(make_cp(fingerprint=NON_SPEED_DEP_FINGERPRINT))
    self.assertTrue(est.speed_binned)
    est._on_torque_point(0.1, 0.3, 10.0)
    self.assertEqual(len(est.speed_bin_bounds), len(SPEED_BIN_BOUNDS))
    self.assertEqual(est.speed_bin_centers, list(SPEED_BIN_CENTERS))

  def test_seeded_with_offline_values(self):
    est = TorqueEstimator(make_cp(fingerprint=NON_SPEED_DEP_FINGERPRINT, lat_accel_factor=2.5, friction=0.18))
    est._on_torque_point(0.1, 0.3, 10.0)
    for i in range(len(SPEED_BIN_BOUNDS)):
      self.assertAlmostEqual(est.speed_bin_filtered[i]['latAccelFactor'].x, 2.5)
      self.assertAlmostEqual(est.speed_bin_filtered[i]['frictionCoefficient'].x, 0.18)


class TestOnTorquePointWhenOff(OpenpilotTestCase):

  def setUp(self):
    super().setUp()
    self.fake_params_off = FakeParams(self_tune_on=False)
    import openpilot.selfdrive.locationd.torqued as torqued_mod
    import openpilot.sunnypilot.selfdrive.locationd.torqued_ext as torqued_ext_mod
    self._patch_torqued = mock.patch.object(torqued_mod, 'Params', lambda: self.fake_params_off)
    self._patch_ext = mock.patch.object(torqued_ext_mod, 'Params', lambda: self.fake_params_off)
    self._patch_torqued.start()
    self._patch_ext.start()
    self.addCleanup(self._patch_torqued.stop)
    self.addCleanup(self._patch_ext.stop)

  def test_no_bins_created_when_off(self):
    est = TorqueEstimator(make_cp(fingerprint=NON_SPEED_DEP_FINGERPRINT))
    est._on_torque_point(0.1, 0.3, 10.0)
    self.assertFalse(hasattr(est, 'speed_bin_points'))


@unittest.skipIf(needs_speed_dep_car, "No cars in speed_dependent.toml")
class TestSpeedBinInitIdempotency(OpenpilotTestCase):
  """Lazy speed-bin init (triggered by _on_torque_point) must not re-init on later points."""

  def setUp(self):
    super().setUp()
    self.fake_params = FakeParams()
    import openpilot.selfdrive.locationd.torqued as torqued_mod
    import openpilot.sunnypilot.selfdrive.locationd.torqued_ext as torqued_ext_mod
    self._patch_torqued = mock.patch.object(torqued_mod, 'Params', lambda: self.fake_params)
    self._patch_ext = mock.patch.object(torqued_ext_mod, 'Params', lambda: self.fake_params)
    self._patch_torqued.start()
    self._patch_ext.start()
    self.addCleanup(self._patch_torqued.stop)
    self.addCleanup(self._patch_ext.stop)

  def test_second_call_preserves_points(self):
    est = TorqueEstimator(make_cp())
    centers, bounds = get_car_bins(SPEED_DEP_FINGERPRINT)
    vego = (bounds[0][0] + bounds[0][1]) / 2
    est._on_torque_point(0.1, 0.3, vego)
    self.assertEqual(len(est.speed_bin_points[0]), 1)

    est._on_torque_point(0.2, 0.4, vego)
    self.assertEqual(len(est.speed_bin_points[0]), 2)


@unittest.skipIf(needs_speed_dep_car, "No cars in speed_dependent.toml")
class TestNaNHandling(OpenpilotTestCase):
  """Bin behavior when the SVD fails. The bucket is a MagicMock here on purpose: it forces
  the failure path without needing thousands of points."""

  def setUp(self):
    super().setUp()
    self.fake_params = FakeParams()
    import openpilot.selfdrive.locationd.torqued as torqued_mod
    import openpilot.sunnypilot.selfdrive.locationd.torqued_ext as torqued_ext_mod
    self._patch_torqued = mock.patch.object(torqued_mod, 'Params', lambda: self.fake_params)
    self._patch_ext = mock.patch.object(torqued_ext_mod, 'Params', lambda: self.fake_params)
    self._patch_torqued.start()
    self._patch_ext.start()
    self.addCleanup(self._patch_torqued.stop)
    self.addCleanup(self._patch_ext.stop)

  def _failing_bucket(self, est, target_bin, valid):
    bucket = mock.MagicMock()
    bucket.is_calculable.return_value = True
    bucket.is_valid.return_value = valid
    bucket.get_points.return_value = np.zeros((10, 3))
    est.speed_bin_points[target_bin] = bucket
    return bucket

  def test_svd_failure_returns_false(self):
    est = TorqueEstimator(make_cp())
    self._failing_bucket(est, 1, valid=False)
    with mock.patch('numpy.linalg.svd', side_effect=np.linalg.LinAlgError):
      results = est._estimate_params_speed_binned()
    self.assertIs(dict(results)[1], False)

  def test_valid_bin_svd_failure_resets_bin(self):
    """A bin with enough data that produces NaN/error is reset."""
    est = TorqueEstimator(make_cp())
    bucket = self._failing_bucket(est, 1, valid=True)
    with mock.patch('numpy.linalg.svd', side_effect=np.linalg.LinAlgError):
      est._estimate_params_speed_binned()
    self.assertIsNot(est.speed_bin_points[1], bucket)
    self.assertIsInstance(est.speed_bin_points[1], TorqueBuckets)
    self.assertEqual(est.speed_bin_decays[1], MIN_FILTER_DECAY)

  def test_non_valid_bin_svd_failure_preserves_bin(self):
    """A bin that is calculable but not valid is NOT reset on SVD failure."""
    est = TorqueEstimator(make_cp())
    bucket = self._failing_bucket(est, 1, valid=False)
    with mock.patch('numpy.linalg.svd', side_effect=np.linalg.LinAlgError):
      est._estimate_params_speed_binned()
    self.assertIs(est.speed_bin_points[1], bucket)


@unittest.skipIf(needs_speed_dep_car, "No cars in speed_dependent.toml")
class TestFullBinKeepsLearning(OpenpilotTestCase):
  """A bin's buckets are ring buffers: once all eight hold POINTS_PER_BUCKET its length stops
  changing while new points keep replacing old ones. The fit must still rerun on them."""

  def setUp(self):
    super().setUp()
    self.fake_params = FakeParams()
    import openpilot.selfdrive.locationd.torqued as torqued_mod
    import openpilot.sunnypilot.selfdrive.locationd.torqued_ext as torqued_ext_mod
    self._patch_torqued = mock.patch.object(torqued_mod, 'Params', lambda: self.fake_params)
    self._patch_ext = mock.patch.object(torqued_ext_mod, 'Params', lambda: self.fake_params)
    self._patch_torqued.start()
    self._patch_ext.start()
    self.addCleanup(self._patch_torqued.stop)
    self.addCleanup(self._patch_ext.stop)

  def test_a_full_bin_refits_on_new_points(self):
    est = TorqueEstimator(make_cp())
    i = 1
    lo, hi = est.speed_bin_bounds[i]
    rng = np.random.default_rng(0)
    bucket = est.speed_bin_points[i]
    for blo, bhi in STEER_BUCKET_BOUNDS:
      steer = rng.uniform(blo, bhi, POINTS_PER_BUCKET)
      bucket.load_points(np.c_[steer, 2.2 * steer + rng.normal(0.0, 0.05, len(steer))].tolist())
    full = len(STEER_BUCKET_BOUNDS) * POINTS_PER_BUCKET
    self.assertEqual(len(bucket), full)
    est._estimate_params_speed_binned()
    before = est.speed_bin_filtered[i]['latAccelFactor'].x
    for steer in rng.uniform(-0.45, 0.45, 50):
      est._on_torque_point(float(steer), 3.0 * float(steer), (lo + hi) / 2)
    self.assertEqual(len(bucket), full)
    est._estimate_params_speed_binned()
    self.assertNotEqual(est.speed_bin_filtered[i]['latAccelFactor'].x, before)

  def test_no_refit_without_new_points(self):
    est = TorqueEstimator(make_cp())
    bucket = est.speed_bin_points[0]
    bucket.load_points([[s, 2.0 * s] for s in np.linspace(-0.45, 0.45, 400)])
    est._estimate_params_speed_binned()
    before = est.speed_bin_filtered[0]['latAccelFactor'].x
    est._estimate_params_speed_binned()
    self.assertEqual(est.speed_bin_filtered[0]['latAccelFactor'].x, before)


import unittest


class TestLegacyFirmwareBins(OpenpilotTestCase):
  """Legacy-firmware cars keep the bins above their speed floor."""

  def setUp(self):
    super().setUp()
    self.fake_params = FakeParams()
    import openpilot.selfdrive.locationd.torqued as torqued_mod
    import openpilot.sunnypilot.selfdrive.locationd.torqued_ext as torqued_ext_mod
    self._patch_torqued = mock.patch.object(torqued_mod, 'Params', lambda: self.fake_params)
    self._patch_ext = mock.patch.object(torqued_ext_mod, 'Params', lambda: self.fake_params)
    self._patch_torqued.start()
    self._patch_ext.start()
    self.addCleanup(self._patch_torqued.stop)
    self.addCleanup(self._patch_ext.stop)

  def test_first_kept_bin_starts_at_its_own_edge(self):
    # a legacy-firmware CX-5 2022 keeps the bins above its 45 kph floor; the first of them must
    # not reach down over the floor and the firmware's dead band to the default 5 m/s
    CP = make_cp('MAZDA_CX5_2022')
    CP.minSteerSpeed = 45 / 3.6
    est = TorqueEstimator(CP)
    full = SPEED_DEP_CARS['MAZDA_CX5_2022']['speed_bp']
    first = full.index(est.speed_bin_centers[0])
    self.assertAlmostEqual(est.speed_bin_bounds[0][0], (full[first - 1] + full[first]) / 2)
    self.assertGreater(est.speed_bin_bounds[0][0], CP.minSteerSpeed)


class TestCustomTorqueParamsScale(OpenpilotTestCase):
  """The custom offline values share the manual override's params, typed on upstream's scale."""

  def setUp(self):
    super().setUp()
    self.fake_params = FakeParams()
    import openpilot.selfdrive.locationd.torqued as torqued_mod
    import openpilot.sunnypilot.selfdrive.locationd.torqued_ext as torqued_ext_mod
    self._patch_torqued = mock.patch.object(torqued_mod, 'Params', lambda: self.fake_params)
    self._patch_ext = mock.patch.object(torqued_ext_mod, 'Params', lambda: self.fake_params)
    self._patch_torqued.start()
    self._patch_ext.start()
    self.addCleanup(self._patch_torqued.stop)
    self.addCleanup(self._patch_ext.stop)

  def test_offline_values_on_steer_max_mazda(self):
    fake_params = FakeParams()
    fake_params.store.update(TorqueParamsOverrideLatAccelFactor='1.2', TorqueParamsOverrideFriction='0.15')
    fake_params.bools.add('CustomTorqueParams')
    import openpilot.selfdrive.locationd.torqued as torqued_mod
    import openpilot.sunnypilot.selfdrive.locationd.torqued_ext as torqued_ext_mod
    with mock.patch.object(torqued_mod, 'Params', lambda: fake_params):
      with mock.patch.object(torqued_ext_mod, 'Params', lambda: fake_params):
        CP = make_cp('MAZDA_CX5_2022', brand='mazda')
        CP.flags = int(MazdaFlags.GEN1 | MazdaFlags.STEER_TO_ZERO_EPS)
        est = TorqueEstimator(CP)
        self.assertAlmostEqual(est.offline_latAccelFactor, 1.8, places=5)
        self.assertAlmostEqual(est.offline_friction, 0.1, places=5)

  def test_offline_values_on_steer_max_toyota(self):
    fake_params = FakeParams()
    fake_params.store.update(TorqueParamsOverrideLatAccelFactor='1.2', TorqueParamsOverrideFriction='0.15')
    fake_params.bools.add('CustomTorqueParams')
    import openpilot.selfdrive.locationd.torqued as torqued_mod
    import openpilot.sunnypilot.selfdrive.locationd.torqued_ext as torqued_ext_mod
    with mock.patch.object(torqued_mod, 'Params', lambda: fake_params):
      with mock.patch.object(torqued_ext_mod, 'Params', lambda: fake_params):
        CP = make_cp('MAZDA_CX5_2022', brand='toyota')
        est = TorqueEstimator(CP)
        self.assertAlmostEqual(est.offline_latAccelFactor, 1.2, places=5)
        self.assertAlmostEqual(est.offline_friction, 0.15, places=5)
