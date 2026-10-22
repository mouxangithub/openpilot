"""Allocation-lifetime regression for DPathRadarD's radarState builder.

Cap'n Proto arenas cannot reclaim replaced lists/structs, so keeping one builder
across frames retains every overwritten lead list and radarErrors struct for the
whole drive. The published messages stay small and functionally correct, so
neither ``total_size()`` nor message length can observe it - only the sum of
allocated ``to_segments()`` bytes can.

These run the real update() with a recording controller, so the assertions are
about actual arena growth rather than a mocked approximation.
"""
import unittest
from types import SimpleNamespace

from opendbc.car.structs import car

from openpilot.cereal import log
import openpilot.cereal.messaging as messaging
from openpilot.sunnypilot.carrot.radar import radard_dpath


def _allocated_bytes(builder) -> int:
  # Not total_size(): that walks only reachable objects and misses allocations
  # orphaned by list replacement inside a reused arena.
  return sum(map(len, builder.to_segments()))


class _RecordingController:
  """Stands in for DPathRadarController; the arena growth is the subject here."""

  def __init__(self):
    self.updates = 0

  def update(self, *, time_s, v_ego, radar_points, model, yaw_rate_rad_s, radar_to_model_time_s):
    self.updates += 1
    lead = radard_dpath.empty_lead()
    lead['status'] = True
    lead['dRel'] = 10.0 + (self.updates % 3)
    lead['yRel'] = 0.1
    many = [dict(lead, radarTrackId=i) for i in range(self.updates % 4)]
    return SimpleNamespace(lead_one=lead, lead_two=radard_dpath.empty_lead(),
                           lead_left=None, lead_right=None, lead_cutin_risk=None,
                           leads_left=many, leads_center=[], leads_right=[],
                           leads_cutin=[], leads_left2=[], leads_right2=[])


class _Sm:
  """Minimal SubMaster surface used by DPathRadarD.update()."""

  def __init__(self, log_mono_time):
    self.logMonoTime = log_mono_time
    self.logMonoTimeValues = list(log_mono_time.values())
    car_state = SimpleNamespace(vEgo=10.0)
    device_motion = SimpleNamespace(angularVelocityDevice=SimpleNamespace(valid=False, z=0.0),
                                    inputsOK=True, sensorsOK=True)
    model = SimpleNamespace(timestampEof=1_000_000_000)
    self._messages = {'carState': car_state, 'deviceMotion': device_motion, 'modelV2': model}

  def __getitem__(self, key):
    return self._messages[key]

  def all_checks(self, *args, **kwargs):
    return True


def _radar_data():
  """A real RadarData message: radarErrors is a struct, not a list."""
  rr = car.RadarData.new_message()
  rr.radarTrackFlipped = False
  rr.hasDisplayData = False
  rr.errors.canError = False
  rr.errors.radarFault = False
  rr.errors.wrongConfig = False
  rr.errors.radarUnavailableTemporary = False
  return rr


class TestRadarStateAllocations(unittest.TestCase):
  def setUp(self):
    self.daemon = radard_dpath.DPathRadarD.__new__(radard_dpath.DPathRadarD)
    self.daemon.controller = _RecordingController()
    self.daemon.radar_state = log.RadarState.new_message()
    self.daemon.radar_state_valid = False
    self.sm = _Sm({'modelV2': 1_000_000_000, 'carState': 1_000_000_100,
                   'liveTracks': 1_000_000_050, 'deviceMotion': 1_000_000_200})

  def _run(self, frames):
    for _ in range(frames):
      self.daemon.update(self.sm, _radar_data())
    return _allocated_bytes(self.daemon.radar_state)

  def test_repeated_update_does_not_grow_the_arena(self):
    # One warm-up frame so the schema-filtered first assignment is not counted.
    self._run(1)
    baseline = _allocated_bytes(self.daemon.radar_state)
    message = "radarState arena grew across frames: reusing one Cap'n Proto builder retains every replaced list"
    for extra in (100, 500, 2000):
      with self.subTest(frames=extra):
        self.assertLessEqual(self._run(extra), baseline, message)

  def test_arena_is_bounded_with_varying_lead_counts(self):
    self._run(1)
    baseline = _allocated_bytes(self.daemon.radar_state)
    # 0..3 leads each frame is the pattern that leaked even with empty lists.
    self.assertLessEqual(self._run(600), baseline)

  def test_published_message_stays_small_and_valid(self):
    self._run(3)
    # Round-trip through the wire format the publish path uses.
    msg = log.Event.new_message(radarState=self.daemon.radar_state)
    state = messaging.log_from_bytes(msg.to_bytes()).radarState
    self.assertTrue(state.leadOne.present)
    self.assertEqual(len(state.leadsLeft), self.daemon.controller.updates % 4)
    self.assertEqual(state.mdMonoTime, self.sm.logMonoTime['modelV2'])
    self.assertFalse(state.radarErrors.canError)

  def test_serialized_output_is_stable_across_rebuilds(self):
    """A per-frame rebuild must not change any published field."""
    frames = []
    for _ in range(6):
      self.daemon.update(self.sm, _radar_data())
      frames.append((self.daemon.radar_state.to_dict(), self.daemon.radar_state_valid))
    # Run the same timeline again against a fresh daemon.
    other = radard_dpath.DPathRadarD.__new__(radard_dpath.DPathRadarD)
    other.controller = _RecordingController()
    other.radar_state = log.RadarState.new_message()
    other.radar_state_valid = False
    replay = []
    for _ in range(6):
      other.update(self.sm, _radar_data())
      replay.append((other.radar_state.to_dict(), other.radar_state_valid))
    self.assertEqual(frames, replay)


if __name__ == '__main__':
  unittest.main()
