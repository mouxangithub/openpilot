# NOTE: cp-side LongitudinalMpc wiring tests (exact wiring parity, reset clears state,
# stop-distance pass-through, braking slack trial) are NOT ported: sp long_mpc is the
# zp-lineage implementation with a different API/structure than the cp MPC these target.
from copy import copy

import numpy as np
import pytest

from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_gap_recovery import (
  LeadGapState, advance_headroom, distance_recovery_weight, gap_reference, displayed_follow_distance,
)
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_braking_gap import LeadComfortState, braking_gap_reference, comfort_path_has_reserve


def step(state, **kwargs):
  # Legacy dynamics fixtures stay inside the hold band. Distance-band cases
  # below explicitly use realistic 4/6 m stop gaps instead of this large gap.
  args = {'level': 0, 'track_id': 49, 'enabled': True, 'dt': .05, 'ego_speed': 10., 'lead_speed': 10.,
          'distance': 40., 'desired_distance': 20., 'base_tf': .6, 'stop_distance': 34.}
  args.update(kwargs)
  args.setdefault('relative_speed', args['lead_speed'] - args['ego_speed'])
  return state.update(**args)


@pytest.mark.parametrize('ratio,expected', [(0., 0.), (1.2, 0.), (1.35, .5), (1.5, 1.), (3., 1.)])
@pytest.mark.parametrize('ego_speed,base_tf,stop_distance', [(0., .9, 6.), (3., .9, 4.), (20., 1.2, 8.)])
def test_distance_band_uses_tf_plus_configured_stop_gap(ratio, expected, ego_speed, base_tf, stop_distance):
  distance = ratio * (ego_speed * base_tf + stop_distance)
  assert distance_recovery_weight(distance, ego_speed, base_tf, stop_distance) == pytest.approx(expected)


def test_distance_band_has_zero_endpoint_slopes_and_handles_zero_reference():
  h = 1e-5
  for boundary in (1.2, 1.5):
    left = distance_recovery_weight((boundary-h)*6., 0., .9, 6.)
    right = distance_recovery_weight((boundary+h)*6., 0., .9, 6.)
    assert abs(right-left)/(2*h) < .001
  assert distance_recovery_weight(10., 0., 0., 0.) == 1.


@pytest.mark.parametrize('lead_speed', [0., 1., 10.])
@pytest.mark.parametrize('relative_speed', [-1., 0., 1.])
def test_far_gap_releases_at_level_rate_regardless_of_speed_or_opening(lead_speed, relative_speed):
  state = LeadGapState()
  args = {'level': 3, 'ego_speed': 3., 'lead_speed': lead_speed, 'relative_speed': relative_speed,
              'distance': 20., 'desired_distance': 20., 'base_tf': .9, 'stop_distance': 6.}
  step(state, **args)
  state.extra_tf = state.recovery_tf = .8
  for _ in range(100):
    step(state, **args)
  # Level 3 has k=1/s: equal initial states release through two filter stages.
  assert state.extra_tf == pytest.approx(.8 * 6. * np.exp(-5.))
  assert state.recovery_tf == pytest.approx(.8 * np.exp(-5.))


@pytest.mark.parametrize('lead_speed,relative_speed', [(0., -1.), (1., 1.), (10., 1.)])
def test_hold_weakens_progressively_across_distance_band(lead_speed, relative_speed):
  remaining = []
  for ratio in (1.2, 1.25, 1.35, 1.45, 1.5):
    state = LeadGapState()
    distance = ratio * (3.*.9 + 6.)
    args = {'level': 3, 'ego_speed': 3., 'lead_speed': lead_speed, 'relative_speed': relative_speed,
                'distance': distance, 'desired_distance': distance, 'base_tf': .9, 'stop_distance': 6.}
    step(state, **args)
    state.extra_tf = state.recovery_tf = .8
    for _ in range(100):
      step(state, **args)
    remaining.append(state.extra_tf)
  assert remaining[0] == pytest.approx(.8)
  assert all(a > b for a, b in zip(remaining, remaining[1:], strict=False))


def test_far_opening_does_not_replenish_after_buffer_has_released():
  state = LeadGapState()
  args = {'level': 3, 'ego_speed': 3., 'lead_speed': 4., 'relative_speed': 1.,
              'distance': 20., 'desired_distance': 6., 'base_tf': .9, 'stop_distance': 6.}
  step(state, **args)
  for _ in range(400):
    step(state, **args)
  assert state.candidate > 1.
  assert state.extra_tf < 1e-6


def test_partial_distance_release_is_stable_across_planner_intervals():
  remaining = []
  for dt in (.02, .05, .1):
    state = LeadGapState()
    args = {'level': 3, 'dt': dt, 'ego_speed': 3., 'lead_speed': 0., 'relative_speed': 1.,
                'distance': 1.35*8.7, 'desired_distance': 20., 'base_tf': .9, 'stop_distance': 6.}
    step(state, **args)
    state.extra_tf = state.recovery_tf = .8
    for _ in range(round(5./dt)):
      step(state, **args)
    remaining.append(state.extra_tf)
  assert max(remaining)-min(remaining) < .002


def test_projection_crosses_distance_band_like_live_updates_without_mutating_state():
  state = LeadGapState()
  args = {'level': 3, 'ego_speed': 3., 'lead_speed': 4., 'relative_speed': 1.,
              'distance': 7., 'desired_distance': 6., 'base_tf': .9, 'stop_distance': 4.}
  step(state, **args)
  times = np.arange(101)*.05
  saved = vars(state).copy()
  margins = state.margins(level=3, times=times, ego_speeds=np.full_like(times, 3.),
                          lead_speeds=np.full_like(times, 4.), base_tf=.9, stop_distance=4.,
                          lead_distances=7.+times, desired_distances=np.full_like(times, 6.))
  assert vars(state) == saved
  expected = [margins[0]]
  for t in times[1:]:
    expected.append(3.*step(state, **dict(args, distance=7.+t)))
  np.testing.assert_allclose(margins, expected, rtol=0, atol=1e-12)
  assert margins[-1] < max(margins)*.5


@pytest.mark.parametrize('stop_distance', [-1., np.nan, np.inf])
def test_invalid_stop_gap_clears_state(stop_distance):
  state = LeadGapState()
  step(state)
  assert step(state, stop_distance=stop_distance) == 0.
  assert state.key is None


def test_close_stopped_cutin_discards_far_lead_headroom():
  state = LeadGapState()
  args = {'level': 3, 'ego_speed': 4., 'lead_speed': 5., 'relative_speed': 1.,
          'distance': 20., 'desired_distance': 10., 'base_tf': .9, 'stop_distance': 6.}
  for _ in range(20):
    step(state, **args)
  assert state.extra_tf > 0.
  # New stopped lead lies inside its ordinary braking-aware target distance.
  args.update(track_id=50, lead_speed=0., relative_speed=-4., distance=8., desired_distance=4.**2/4.8+.9*4.+6.)
  assert step(state, **args) == 0.
  assert state.extra_tf == state.recovery_tf == 0.
  times = np.arange(13)*.1
  margins = state.margins(level=3, times=times, ego_speeds=np.full_like(times, 4.),
                          lead_speeds=np.zeros_like(times), base_tf=.9, stop_distance=6.)
  np.testing.assert_array_equal(margins, 0.)


@pytest.mark.parametrize('boundary', [1.2, 1.5])
def test_small_distance_noise_cannot_reset_or_jump_applied_tf(boundary):
  state = LeadGapState()
  args = {'level': 3, 'dt': .001, 'ego_speed': 3., 'lead_speed': 0., 'relative_speed': 1.,
          'distance': boundary*8.7, 'desired_distance': 20., 'base_tf': .9, 'stop_distance': 6.}
  step(state, **args)
  state.extra_tf = state.recovery_tf = .8
  for i in range(100):
    before = state.extra_tf
    step(state, **dict(args, distance=(boundary+(-1 if i%2 else 1)*1e-5)*8.7))
    assert 0. <= state.extra_tf <= before + 1e-12
    assert before-state.extra_tf < .001


def test_half_of_excess_is_captured_once_not_replenished_by_a_large_gap():
  state = LeadGapState()
  step(state)
  assert state.extra_tf == pytest.approx(1.)
  for _ in range(100):
    step(state, distance=60.)
  assert .40 < state.extra_tf < .41
  for _ in range(1000):
    step(state, distance=60. + .1*np.sin(_))
  assert state.extra_tf < .0001


def test_matched_gap_adds_nothing_and_existing_long_tf_is_not_shortened():
  state = LeadGapState()
  assert step(state, distance=20.) == 0.
  assert step(state, track_id=50, base_tf=3.) == 0.


@pytest.mark.parametrize('speed', [0., .01, .2, 1., 30.])
def test_low_speed_capture_is_finite_and_capped(speed):
  state = LeadGapState()
  step(state, ego_speed=speed, lead_speed=0., distance=1000.)
  assert np.isfinite(state.extra_tf)
  assert state.extra_tf == pytest.approx(1.9)


def test_stopped_lead_holds_tf_but_stopping_ego_loses_distance_margin():
  state = LeadGapState()
  step(state, lead_speed=0.)
  initial = state.extra_tf
  for _ in range(500):
    step(state, ego_speed=max(0., 10.-_*0.05), lead_speed=0.)
  assert state.extra_tf == initial
  step(state, lead_speed=0.)  # Align the live speed with the horizon's first node.
  times, speeds = np.array([0., 1., 2., 3.]), np.array([10., 5., 1., 0.])
  margin = state.margins(level=0, times=times, ego_speeds=speeds, lead_speeds=np.zeros(4), base_tf=.6, stop_distance=34.)
  np.testing.assert_allclose(margin, speeds*initial)
  assert margin[-1] == 0.


def test_slow_lead_recovers_more_slowly_and_tiers_are_ordered():
  values = []
  for level in range(6):
    state = LeadGapState()
    for _ in range(101):
      step(state, level=level)
    values.append(state.extra_tf)
  assert values[0] > values[1] > values[2] > values[3] > values[4] > values[5] == 0.
  state = LeadGapState()
  for _ in range(101):
    step(state, lead_speed=1.)
  assert values[0] < state.extra_tf < 1.


def test_filter_respects_elapsed_time_at_different_planner_rates():
  values = []
  for dt in (.02, .05, .1):
    state = LeadGapState()
    step(state, dt=dt)
    for _ in range(round(5./dt)):
      step(state, dt=dt)
    values.append(state.extra_tf)
  assert max(values)-min(values) < .004


def test_opening_recaptures_after_departure_and_later_reacceleration():
  state = LeadGapState()
  step(state, ego_speed=0., lead_speed=0., distance=6., desired_distance=6.)
  for i in range(120):
    step(state, ego_speed=1., lead_speed=2., distance=6. + .05*(i+1), desired_distance=6.)
  captured = state.extra_tf
  assert captured > .3
  for _ in range(100):
    step(state, ego_speed=10., lead_speed=10., distance=12.)
  assert state.extra_tf < captured
  without_opening = copy(state)
  for i in range(160):
    step(state, ego_speed=10., lead_speed=12., distance=12. + .1*(i+1), desired_distance=6.)
    step(without_opening, ego_speed=10., lead_speed=12., distance=12., desired_distance=6.)
  assert state.extra_tf > without_opening.extra_tf + .1


def test_opening_holds_headroom_even_after_candidate_falls():
  state = LeadGapState()
  step(state, relative_speed=1., lead_speed=11.)
  initial = state.extra_tf
  for _ in range(100):
    step(state, relative_speed=1., lead_speed=11., distance=20.)
  assert state.extra_tf == initial
  times = np.array([0., 1., 2., 3.])
  margins = state.margins(level=0, times=times, ego_speeds=np.full(4, 10.), lead_speeds=np.full(4, 11.), base_tf=.6, stop_distance=34.)
  np.testing.assert_allclose(margins, initial * 10.)
  # Once the lead matches speed, the buffer releases rather than holding
  # permanently just because the actual distance is still large.
  for _ in range(120):
    step(state, relative_speed=0., lead_speed=10., distance=60.)
  assert 0.0 < state.extra_tf < initial * .5


def test_relative_speed_noise_and_single_spike_do_not_replenish():
  state = LeadGapState()
  step(state, distance=20.)
  for i in range(200):
    step(state, distance=40., relative_speed=.06*np.sin(i))
  assert state.extra_tf == 0.
  step(state, distance=40., relative_speed=.4)
  assert state.extra_tf == 0.
  for _ in range(20):
    step(state, distance=40., relative_speed=1.)
  assert state.extra_tf > 0.  # sustained opening can replenish existing headroom


def test_capture_rise_is_limited_and_a_track_change_clears_opening_filter():
  state = LeadGapState()
  step(state, distance=20.)
  for i in range(160):
    before = state.extra_tf
    step(state, distance=20. + .1*(i+1), relative_speed=2.)
    assert state.extra_tf - before <= .025 + 1e-10
  assert state.extra_tf > .1
  step(state, track_id=50, distance=20., relative_speed=-2.)
  assert state.extra_tf == 0.
  assert state.filtered_relative_speed == -2.
  for _ in range(30):
    step(state, track_id=50, distance=100., relative_speed=-2.)
  assert state.extra_tf == 0.


def test_unchanged_opening_candidate_holds_buffer_without_accumulating():
  state = LeadGapState()
  for _ in range(100):
    step(state, level=1, distance=28., relative_speed=1., lead_speed=11.)
  before = state.extra_tf
  for _ in range(80):
    step(state, level=1, distance=28., relative_speed=1., lead_speed=11.)
  assert state.extra_tf == before == pytest.approx(.4)
  assert state.recovery_tf == pytest.approx(.4)


def test_braking_distance_and_speed_changes_alone_do_not_trigger_capture():
  state = LeadGapState()
  step(state, distance=20., relative_speed=0.)
  for i in range(60):
    step(state, distance=20., desired_distance=20.-i*.1, ego_speed=10.-i*.05, relative_speed=0.)
  assert state.recovery_tf == state.extra_tf == 0.


@pytest.mark.parametrize('level', range(5))
def test_recovery_starts_with_zero_slope_and_no_overshoot(level):
  state = LeadGapState()
  step(state, level=level)
  initial = state.extra_tf
  step(state, level=level, dt=.001)
  assert 0 <= initial - state.extra_tf < 3e-6
  previous = state.extra_tf
  for _ in range(1000):
    step(state, level=level)
    assert 0 <= state.extra_tf <= previous
    previous = state.extra_tf
  assert state.extra_tf < .0001


@pytest.mark.parametrize('opening', [False, True])
@pytest.mark.parametrize('lead_speed', [0., 1., 11.])
def test_horizon_matches_updates_including_entry_and_new_capture(opening, lead_speed):
  state = LeadGapState()
  v_rel = 1. if opening else 0.
  step(state, level=1, distance=28., relative_speed=v_rel, lead_speed=lead_speed)
  times = np.arange(81)*.05
  distances = 28. + v_rel*times
  desired = np.full_like(times, 20.)
  # Includes acquisition ramp: horizon must not freeze its current strength.
  saved = vars(state).copy()
  margins = state.margins(level=1, times=times, ego_speeds=np.full_like(times, 10.),
                          lead_speeds=np.full_like(times, lead_speed), base_tf=.6,
                          lead_distances=28. + (lead_speed - 10.)*times, desired_distances=desired, stop_distance=34.)
  assert vars(state) == saved
  live = copy(state)
  expected = [margins[0]]
  for distance in distances[1:]:
    expected.append(10.*step(live, level=1, distance=distance, relative_speed=v_rel, lead_speed=lead_speed))
  np.testing.assert_allclose(margins, expected, rtol=0, atol=1e-12)


def test_candidate_jump_is_rate_limited_and_does_not_accumulate_past_cap():
  state = LeadGapState()
  step(state, distance=20., relative_speed=2., lead_speed=12., stop_distance=1000.)
  step(state, distance=1000., relative_speed=2., lead_speed=12., stop_distance=1000.)
  assert state.recovery_tf == pytest.approx(.025)  # reservoir rise <= 0.5 TF/s
  assert 0.0 < state.extra_tf < state.recovery_tf
  for _ in range(1000):
    step(state, distance=1000., relative_speed=2., lead_speed=12., stop_distance=1000.)
    assert 0.0 <= state.extra_tf <= state.recovery_tf <= 1.9
  assert state.extra_tf == pytest.approx(1.9)


def test_horizon_distance_and_relative_speed_share_the_measured_anchor():
  state = LeadGapState()
  step(state, level=1, ego_speed=12., lead_speed=11., relative_speed=1., distance=28.)
  times = np.arange(81)*.05
  # Planned ego speed suggests closing, but the measured gap is still opening.
  # Both the relative speed AND the gap forecast must use the measured anchor.
  predicted = state.margins(level=1, times=times, ego_speeds=np.full_like(times, 12.),
                           lead_speeds=np.full_like(times, 11.), base_tf=.6,
                           lead_distances=28.-times, desired_distances=np.full_like(times, 20.), stop_distance=34.)
  expected = [predicted[0]]
  for t in times[1:]:
    expected.append(12.*step(state, level=1, ego_speed=12., lead_speed=11., relative_speed=1., distance=28.+t))
  np.testing.assert_allclose(predicted, expected, rtol=0, atol=1e-12)


def test_rising_candidate_is_consistent_across_update_intervals():
  results = []
  for dt in (.02, .05, .1):
    state = LeadGapState()
    step(state, level=1, dt=dt, distance=28., relative_speed=1., lead_speed=11.)
    for i in range(round(5./dt)):
      step(state, level=1, dt=dt, distance=28.+(i+1)*dt, relative_speed=1., lead_speed=11.)
    results.append(state.extra_tf)
  np.testing.assert_allclose(results, results[0], rtol=0., atol=.004)


def test_constant_envelope_charge_hold_release_is_interval_independent():
  results = []
  for dt in (.02, .05, .1, 1.):
    reservoir = extra = 0.
    for target, duration in ((1., 6.), (None, 4.)):
      for _ in range(round(duration / dt)):
        reservoir, extra = advance_headroom(reservoir, extra, target, dt, 10., 4., 1.9)
    results.append((reservoir, extra))
  np.testing.assert_allclose(results, [results[0]] * len(results), rtol=0., atol=1e-12)


@pytest.mark.parametrize('reservoir,extra', [(1., 1.), (1., .6), (.3, .6)])
def test_opening_to_release_preserves_output_slope(reservoir, extra):
  dt = 1e-5
  charged = advance_headroom(reservoir, extra, 1., dt, 10., 4., 1.9)[1]
  released = advance_headroom(reservoir, extra, None, dt, 10., 4., 1.9)[1]
  assert (charged - extra) / dt == pytest.approx((released - extra) / dt, abs=3e-6)


def test_level_one_keeps_opening_buffer_then_recovers_gradually():
  state = LeadGapState()
  step(state, level=1, distance=20., relative_speed=2., lead_speed=12.)
  # Existing excess is an absolute charge target, not a one-shot increment.
  for _ in range(160):
    step(state, level=1, distance=40., relative_speed=2., lead_speed=12.)
  assert .96 < state.extra_tf < 1.
  held = state.extra_tf
  # The lead's acceleration may be zero while vRel is still positive.
  for _ in range(80):
    step(state, level=1, distance=40., relative_speed=2., lead_speed=12.)
  assert held < state.extra_tf <= 1.
  for _ in range(100):
    step(state, level=1, distance=40., relative_speed=0., lead_speed=10.)
  assert .3 < state.extra_tf < .4


@pytest.mark.parametrize('kwargs', [{'enabled': False}, {'track_id': -1}, {'distance': np.nan},
                                   {'relative_speed': np.inf}, {'dt': 0.}, {'level': 5}])
def test_invalidation_clears_headroom(kwargs):
  state = LeadGapState()
  step(state)
  assert state.extra_tf > 0.
  assert step(state, **kwargs) == 0.
  assert state.key is None and state.extra_tf == 0.


def test_new_track_and_level_do_not_inherit_previous_extra_tf():
  state = LeadGapState()
  step(state, distance=100.)
  assert state.extra_tf > 1.
  assert step(state, track_id=50, distance=20.) == 0.
  assert step(state, level=1, distance=20.) == 0.


def test_reference_preserves_physical_obstacles_and_obeys_closer_cruise_target():
  obstacles = np.array([[100., 200., 110., 1000.], [100., 200., 80., 1000.]])
  saved = obstacles.copy()
  reference = gap_reference(obstacles, np.array([[6., 0.], [6., 0.]]), np.array([20., 20.]))
  np.testing.assert_array_equal(obstacles, saved)
  np.testing.assert_allclose(reference, [.2, 0.])








def test_displayed_target_includes_headroom_and_uses_restrictive_valid_lead():
  assert displayed_follow_distance([20., 30.], [60., 70.], [60., 70.], [5., 25.], [True, True]) == 55.
  assert displayed_follow_distance([20., 30.], [60., 70.], [60., 70.], [5., 25.], [True, False]) == 25.
  assert displayed_follow_distance([20., 30.], [60., 70.], [60., 70.], [5., 25.], [False, False]) == 0.


def test_displayed_target_accounts_for_existing_relief_without_changing_inputs():
  obstacles = np.array([60., 70.])
  margins = np.array([5., 0.])
  assert displayed_follow_distance([20., 30.], [58., 70.], obstacles, margins, [True, False]) == 23.
  assert obstacles == pytest.approx([60., 70.])
  assert margins == pytest.approx([5., 0.])


