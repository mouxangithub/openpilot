"""NavDestination param parsing must fail safe on corrupted writes."""
import unittest

from openpilot.selfdrive.navigation.helpers import parse_destination_coordinate


class TestParseDestinationCoordinate(unittest.TestCase):
  def test_valid_destination(self):
    self.assertEqual((12.345, -67.89), parse_destination_coordinate({'longitude': 12.345, 'latitude': -67.89}))

  def test_numeric_strings_are_coerced(self):
    self.assertEqual((12.0, 34.0), parse_destination_coordinate({'longitude': '12', 'latitude': '34'}))

  def test_malformed_destinations_return_none(self):
    for name, destination in (
      ('missing_lon', {'latitude': 12.0}),
      ('missing_lat', {'longitude': 12.0}),
      ('non_numeric', {'longitude': 'abc', 'latitude': 'def'}),
      ('none_values', {'longitude': None, 'latitude': None}),
      ('nan_lat', {'longitude': 12.0, 'latitude': float('nan')}),
      ('inf_lon', {'longitude': float('inf'), 'latitude': 12.0}),
      ('lat_out_of_range', {'longitude': 12.0, 'latitude': 85.06}),
      ('lon_out_of_range', {'longitude': 180.5, 'latitude': 12.0}),
      ('not_a_dict', ['longitude', 'latitude']),
      ('none_input', None),
    ):
      with self.subTest(case=name):
        self.assertIsNone(parse_destination_coordinate(destination))

  def test_range_boundaries_accepted(self):
    self.assertIsNotNone(parse_destination_coordinate({'longitude': 180.0, 'latitude': 85.05112878}))
    self.assertIsNotNone(parse_destination_coordinate({'longitude': -180.0, 'latitude': -85.05112878}))


if __name__ == '__main__':
  unittest.main()
