"""Tests for the camera geometry that feeds the signal control chain.

The whole signal geometry chain is written against one reference road-camera
frame (1344x760 at focal 1141.5, the comma 3X). These tests pin the mapping
that lets a different camera feed the same chain. The non-negotiable
invariant is angular: an extent subtending a given angle must map to the
same reference pixels on every camera, so the housing-size windows and ray
maths keep their physical meaning.
"""
import math
import unittest

from openpilot.sunnypilot.carrot.signal_geometry import (
  C3_FOCAL, C3_HEIGHT, C3_WIDTH, REFERENCE_FOCAL, REFERENCE_HEIGHT, REFERENCE_WIDTH,
  SignalGeometry, geometry_for_camera, geometry_for_size, to_reference_tracks,
)


class TestGeometryLookup(unittest.TestCase):
  def test_reference_size_is_identity_geometry(self):
    geom = geometry_for_size(REFERENCE_WIDTH, REFERENCE_HEIGHT)
    self.assertIsNotNone(geom)
    self.assertEqual(geom.size, (REFERENCE_WIDTH, REFERENCE_HEIGHT))
    self.assertAlmostEqual(geom.focal, REFERENCE_FOCAL)
    self.assertAlmostEqual(geom.scale, 1.0)

  def test_c3_size_is_known(self):
    geom = geometry_for_size(C3_WIDTH, C3_HEIGHT)
    self.assertIsNotNone(geom)
    self.assertEqual(geom.size, (C3_WIDTH, C3_HEIGHT))
    self.assertAlmostEqual(geom.focal, C3_FOCAL)

  def test_unknown_size_is_refused_not_guessed(self):
    self.assertIsNone(geometry_for_size(1280, 720))
    self.assertIsNone(geometry_for_size(0, 0))

  def test_invalid_construction_is_rejected(self):
    for kwargs in ({'width': 0, 'height': 760, 'focal': 1.}, {'width': 1344, 'height': 0, 'focal': 1.},
                   {'width': 1344, 'height': 760, 'focal': 0.}, {'width': -1, 'height': 760, 'focal': 1.}):
      with self.assertRaises(ValueError):
        SignalGeometry(**kwargs)

  def test_geometry_for_camera_uses_narrow_road(self):
    class Cam:
      def __init__(self, size, focal):
        self.size = size
        self.focal_length = focal

    class Device:
      narrow_road = Cam((C3_WIDTH, C3_HEIGHT), C3_FOCAL)

    geom = geometry_for_camera(Device())
    self.assertEqual(geom.size, (C3_WIDTH, C3_HEIGHT))
    self.assertIsNone(geometry_for_camera(None))

    class NoNarrow:
      pass

    self.assertIsNone(geometry_for_camera(NoNarrow()))


class TestAngularMapping(unittest.TestCase):
  def setUp(self):
    self.ref = geometry_for_size(REFERENCE_WIDTH, REFERENCE_HEIGHT)
    self.c3 = geometry_for_size(C3_WIDTH, C3_HEIGHT)

  def test_scale_is_angular_focal_ratio(self):
    self.assertAlmostEqual(self.c3.scale, REFERENCE_FOCAL / C3_FOCAL)
    # C3 has the longer focal, so one camera pixel is a smaller angle and
    # maps to fewer reference pixels.
    self.assertLess(self.c3.scale, 1.0)

  def test_centre_maps_to_reference_centre_exactly(self):
    cx, cy = self.c3.center
    rx1, ry1, rx2, ry2 = self.c3.to_reference_box((cx - 50., cy - 20., cx + 50., cy + 20.))
    self.assertAlmostEqual((rx1 + rx2) / 2., REFERENCE_WIDTH / 2.)
    self.assertAlmostEqual((ry1 + ry2) / 2., REFERENCE_HEIGHT / 2.)

  def test_same_angle_maps_to_same_reference_extent(self):
    # An angular extent measured in camera pixels maps to focal_other/focal
    # times as many reference pixels. Pick a box centred on the principal
    # point on each camera and confirm the mapped reference width matches the
    # angular conversion, and that the two cameras agree in reference space.
    def central_box(geom, camera_half_width):
      cx, cy = geom.center
      return geom.to_reference_box((cx - camera_half_width, cy - 10., cx + camera_half_width, cy + 10.))

    # Same physical angle: half_width = focal * tan(theta). Use a small theta.
    theta = math.radians(1.0)
    ref_half = REFERENCE_FOCAL * math.tan(theta)
    c3_half = C3_FOCAL * math.tan(theta)
    r = central_box(self.ref, ref_half)
    c = central_box(self.c3, c3_half)
    ref_width = r[2] - r[0]
    c3_width = c[2] - c[0]
    self.assertAlmostEqual(ref_width, c3_width, delta=0.05)

  def test_reference_geometry_is_pixel_identical_about_centre(self):
    # On the reference camera the mapping is the identity in pixels.
    box = (300., 200., 400., 260.)
    mapped = self.ref.to_reference_box(box)
    for got, want in zip(mapped, box, strict=True):
      self.assertAlmostEqual(got, want)

  def test_known_angular_extent_value(self):
    # Pin the concrete C3 factor so a future change to either focal length
    # shows up here. 100 C3 pixels subtend 100/2648 rad -> ~43.1 ref pixels.
    self.assertAlmostEqual(self.c3.to_reference(100.0), 100.0 * REFERENCE_FOCAL / C3_FOCAL, places=5)
    self.assertAlmostEqual(self.c3.to_reference(100.0), 43.108, places=2)


class TestTrackMapping(unittest.TestCase):
  def test_tracks_are_remapped_and_other_fields_kept(self):
    geom = geometry_for_size(C3_WIDTH, C3_HEIGHT)
    cx, cy = geom.center
    tracks = [{'id': 1, 'box': [cx - 50., cy - 10., cx + 50., cy + 10.],
               'state': 'red', 'evidence': {'raw': 'red'}}]
    mapped = to_reference_tracks(tracks, geom)
    self.assertEqual(mapped[0]['id'], 1)
    self.assertEqual(mapped[0]['state'], 'red')
    self.assertEqual(mapped[0]['evidence'], {'raw': 'red'})
    # The box moved off the C3 centre onto the reference centre.
    self.assertAlmostEqual((mapped[0]['box'][0] + mapped[0]['box'][2]) / 2., REFERENCE_WIDTH / 2.)

  def test_none_geometry_passes_tracks_through(self):
    tracks = [{'id': 1, 'box': [1., 2., 3., 4.]}]
    self.assertEqual(to_reference_tracks(tracks, None), tracks)

  def test_malformed_track_is_passed_through_not_dropped(self):
    # A bad box must not silently vanish or raise; the consumer's own bounds
    # checks reject it.
    geom = geometry_for_size(C3_WIDTH, C3_HEIGHT)
    bad = [{'id': 2}]
    mapped = to_reference_tracks(bad, geom)
    self.assertEqual(mapped[0], bad[0])


if __name__ == '__main__':
  unittest.main()
