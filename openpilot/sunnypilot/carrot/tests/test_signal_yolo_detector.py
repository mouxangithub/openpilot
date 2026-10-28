"""Traffic-light detector: decoding, lamp grouping and the record shape.

These tests pin the behaviour the consumer relies on: a housing is the tracked
unit, a lamp only colours a housing that contains it, and a housing whose lamps
disagree never becomes a colour. The unsafe direction - turning ambiguous
evidence into a red or a green - must fail.
"""
import unittest

import numpy as np

from openpilot.sunnypilot.carrot.signal_yolo_detector import (
  CLASSES, GREEN, HOUSING, INPUT_SIZE, LEFT, RED, RIGHT, YELLOW,
  Detection, HousingObservation, HousingTracker, decode_output, detect, group_housings,
  resize_params, observation_record, valid_box,
)


def _head(rows, width=INPUT_SIZE):
  """Build a raw YOLOv8 head: (1, 4 + nc, N) with [cx, cy, w, h] then scores."""
  nc = len(CLASSES)
  out = np.zeros((1, 4 + nc, len(rows)), np.float32)
  for index, (cx, cy, w, h, cls, score) in enumerate(rows):
    out[0, 0, index] = cx
    out[0, 1, index] = cy
    out[0, 2, index] = w
    out[0, 3, index] = h
    out[0, 4 + CLASSES.index(cls), index] = score
  return out


class TestResize(unittest.TestCase):
  def test_wide_frame_is_squashed_to_the_square_input(self):
    # The frame is squashed, not letterboxed: the network was trained on
    # squashed frames and the letterboxed path loses 14 accuracy points.
    self.assertEqual(resize_params(1344, 760), (0, 0, INPUT_SIZE, INPUT_SIZE))

  def test_square_frame_has_no_padding(self):
    self.assertEqual(resize_params(640, 640), (0, 0, INPUT_SIZE, INPUT_SIZE))

  def test_invalid_size_rejected(self):
    for width, height in ((0, 760), (1344, 0), (-1, 10)):
      with self.assertRaises(ValueError):
        resize_params(width, height)


class TestDecode(unittest.TestCase):
  def test_head_shape_is_validated(self):
    with self.assertRaises(ValueError):
      decode_output(np.zeros((1, 3, 10), np.float32), left=0, top=0, net_w=416, net_h=416,
                    source_w=416, source_h=416)

  def test_box_maps_back_to_source_pixels(self):
    out = _head([(208, 208, 40, 60, HOUSING, .9)])
    dets = decode_output(out, left=0, top=0, net_w=416, net_h=416, source_w=416, source_h=416)
    self.assertEqual(len(dets), 1)
    self.assertEqual(dets[0].cls, HOUSING)
    self.assertAlmostEqual(dets[0].box[0], 188., places=3)
    self.assertAlmostEqual(dets[0].box[2], 228., places=3)
    self.assertAlmostEqual(dets[0].box[1], 178., places=3)
    self.assertAlmostEqual(dets[0].box[3], 238., places=3)

  def test_low_confidence_is_dropped(self):
    out = _head([(208, 208, 40, 60, HOUSING, .1)])
    self.assertEqual(decode_output(out, left=0, top=0, net_w=416, net_h=416,
                                   source_w=416, source_h=416), [])

  def test_housing_and_lamp_do_not_suppress_each_other(self):
    # Class-wise NMS: the lamp inside the housing is a different class.
    out = _head([(208, 208, 100, 120, HOUSING, .9), (208, 190, 20, 20, RED, .8)])
    dets = decode_output(out, left=0, top=0, net_w=416, net_h=416, source_w=416, source_h=416)
    self.assertEqual({d.cls for d in dets}, {HOUSING, RED})

  def test_same_class_duplicates_are_suppressed(self):
    out = _head([(208, 208, 100, 120, HOUSING, .9), (212, 210, 100, 120, HOUSING, .8)])
    dets = decode_output(out, left=0, top=0, net_w=416, net_h=416, source_w=416, source_h=416)
    self.assertEqual(len(dets), 1)


class TestGroupHousings(unittest.TestCase):
  def test_red_lamp_inside_housing_gives_red(self):
    dets = [Detection(HOUSING, .9, (100., 100., 200., 200.)),
            Detection(RED, .8, (120., 120., 160., 160.))]
    obs = group_housings(dets)
    self.assertEqual(len(obs), 1)
    self.assertEqual(obs[0].state, 'red')

  def test_green_lamp_inside_housing_gives_green(self):
    dets = [Detection(HOUSING, .9, (100., 100., 200., 200.)),
            Detection(GREEN, .8, (120., 120., 160., 160.))]
    self.assertEqual(group_housings(dets)[0].state, 'green')

  def test_lamp_outside_housing_is_dropped(self):
    dets = [Detection(HOUSING, .9, (100., 100., 200., 200.)),
            Detection(RED, .8, (300., 300., 340., 340.))]
    obs = group_housings(dets)
    self.assertEqual(len(obs), 1)
    self.assertEqual(obs[0].state, 'unknown')
    self.assertEqual(obs[0].lamps, [])

  def test_lamp_only_partly_inside_is_not_evidence(self):
    # The lamp hangs half out of the housing, so it is not a reliable read.
    dets = [Detection(HOUSING, .9, (100., 100., 200., 200.)),
            Detection(RED, .8, (180., 120., 240., 160.))]
    self.assertEqual(group_housings(dets)[0].state, 'unknown')

  def test_disagreeing_lamps_stay_unknown(self):
    dets = [Detection(HOUSING, .9, (100., 100., 200., 200.)),
            Detection(RED, .8, (110., 110., 150., 150.)),
            Detection(GREEN, .7, (150., 150., 190., 190.))]
    self.assertEqual(group_housings(dets)[0].state, 'unknown')

  def test_yellow_lamp_is_not_an_action_colour(self):
    dets = [Detection(HOUSING, .9, (100., 100., 200., 200.)),
            Detection(YELLOW, .8, (120., 120., 160., 160.))]
    self.assertEqual(group_housings(dets)[0].state, 'unknown')

  def test_arrow_lamp_is_not_an_action_colour(self):
    for arrow in (LEFT, RIGHT):
      dets = [Detection(HOUSING, .9, (100., 100., 200., 200.)),
              Detection(arrow, .8, (120., 120., 160., 160.))]
      self.assertEqual(group_housings(dets)[0].state, 'unknown')

  def test_housing_without_lamp_is_still_an_observation(self):
    dets = [Detection(HOUSING, .9, (100., 100., 200., 200.))]
    obs = group_housings(dets)
    self.assertEqual(len(obs), 1)
    self.assertEqual(obs[0].state, 'unknown')

  def test_lamp_without_housing_is_dropped(self):
    dets = [Detection(RED, .8, (120., 120., 160., 160.))]
    self.assertEqual(group_housings(dets), [])


class TestObservationRecord(unittest.TestCase):
  def test_record_shape_matches_the_existing_transport(self):
    obs = [HousingObservation(conf=.9, box=(10., 20., 30., 40.), state='red',
                              lamps=[Detection(RED, .8, (12., 22., 18., 28.))])]
    record = observation_record(obs, frame_id=7, timestamp=1.5, session_id='s', width=1344, height=760)
    self.assertEqual(record['version'], 1)
    self.assertEqual(record['stream'], 'road')
    self.assertEqual(record['size'], [1344, 760])
    self.assertEqual(record['frame_id'], 7)
    self.assertEqual(record['session'], 's')
    self.assertEqual(len(record['tracks']), 1)
    track = record['tracks'][0]
    self.assertEqual(track['id'], 1)
    self.assertEqual(track['box'], [10., 20., 30., 40.])
    self.assertEqual(track['state'], 'red')
    self.assertEqual(track['observations'], 1)
    self.assertEqual(track['evidence'], {'raw': 'red'})
    self.assertEqual(track['lamps'][0]['cls'], RED)

  def test_record_is_json_serialisable(self):
    import json
    obs = [HousingObservation(box=(1., 2., 3., 4.), state='unknown')]
    record = observation_record(obs, 1, 0., 's', width=1344, height=760)
    json.dumps(record, allow_nan=False)


def _obs(box, state='red'):
  return HousingObservation(conf=.9, box=box, state=state)


class TestHousingTracker(unittest.TestCase):
  def test_same_housing_keeps_its_id_across_frames(self):
    tracker = HousingTracker()
    first = tracker.update([_obs((100., 50., 140., 110.), 'red')])
    second = tracker.update([_obs((101., 51., 141., 111.), 'red')])
    self.assertEqual(first[0]['id'], second[0]['id'])
    self.assertEqual(second[0]['observations'], 2)
    self.assertEqual(second[0]['age'], 0)
    self.assertEqual(second[0]['state'], 'red')

  def test_two_housings_get_distinct_stable_ids(self):
    tracker = HousingTracker()
    tracker.update([_obs((100., 50., 140., 110.)), _obs((600., 50., 640., 110.), 'green')])
    rows = tracker.update([_obs((600., 50., 640., 110.), 'green'), _obs((100., 50., 140., 110.))])
    ids = {row['state']: row['id'] for row in rows}
    self.assertNotEqual(ids['red'], ids['green'])
    self.assertEqual({row['observations'] for row in rows}, {2})

  def test_moved_housing_stays_matched_within_the_iou_gate(self):
    tracker = HousingTracker()
    first = tracker.update([_obs((100., 50., 140., 110.))])
    # IoU(100,50,140,110 vs 110,55,150,115) ~= .52, matched;
    # a teleport is a new one.
    second = tracker.update([_obs((110., 55., 150., 115.))])
    third = tracker.update([_obs((900., 60., 940., 120.))])
    self.assertEqual(first[0]['id'], second[0]['id'])
    self.assertNotEqual(second[0]['id'], third[0]['id'])

  def test_state_flip_is_carried_by_the_track(self):
    tracker = HousingTracker()
    tracker.update([_obs((100., 50., 140., 110.), 'red')])
    row = tracker.update([_obs((100., 50., 140., 110.), 'green')])
    self.assertEqual(row[0]['state'], 'green')
    self.assertEqual(row[0]['evidence'], {'raw': 'green'})

  def test_unseen_track_is_forgotten_after_max_age(self):
    tracker = HousingTracker(max_age=2)
    first = tracker.update([_obs((100., 50., 140., 110.))])
    tracker.update([])  # miss 1
    tracker.update([])  # miss 2
    tracker.update([])  # miss 3 exceeds max_age: the track is forgotten
    row = tracker.update([_obs((100., 50., 140., 110.))])
    self.assertNotEqual(row[0]['id'], first[0]['id'])
    self.assertEqual(row[0]['observations'], 1)

  def test_only_current_frame_tracks_are_published(self):
    tracker = HousingTracker()
    tracker.update([_obs((100., 50., 140., 110.))])
    rows = tracker.update([])
    self.assertEqual(rows, [])

  def test_invalid_configuration_is_rejected(self):
    for kwargs in ({'iou_threshold': 0.}, {'iou_threshold': 1.5}, {'max_age': 0}):
      with self.assertRaises(ValueError):
        HousingTracker(**kwargs)

  def test_tracked_record_is_json_serialisable(self):
    import json
    tracker = HousingTracker()
    record = observation_record([_obs((1., 2., 3., 4.))], 1, 0., 's', width=1344, height=760, tracker=tracker)
    json.dumps(record, allow_nan=False)


class TestValidBox(unittest.TestCase):
  def test_inside_the_frame_is_valid(self):
    self.assertTrue(valid_box((0., 0., 1344., 760.), 1344, 760))

  def test_outside_or_inverted_is_invalid(self):
    self.assertFalse(valid_box((-1., 0., 10., 10.), 1344, 760))
    self.assertFalse(valid_box((0., 0., 1400., 10.), 1344, 760))
    self.assertFalse(valid_box((10., 0., 5., 10.), 1344, 760))

  def test_non_finite_is_invalid(self):
    self.assertFalse(valid_box((0., 0., float('nan'), 10.), 1344, 760))
    self.assertFalse(valid_box((0., 0., float('inf'), 10.), 1344, 760))


class TestDetect(unittest.TestCase):
  @unittest.skipUnless(__import__('importlib').util.find_spec('cv2') is not None, 'needs cv2')
  def test_detect_runs_on_a_blank_frame_without_inventing_signals(self):
    import cv2
    net = cv2.dnn.readNetFromONNX(
      str(__import__('pathlib').Path(__file__).resolve().parents[3] /
          'sunnypilot/assets/vision_models/signal_light_detector.onnx'))
    frame = np.zeros((760, 1344, 3), np.uint8)
    self.assertEqual(detect(frame, net), [])


if __name__ == '__main__':
  unittest.main()
