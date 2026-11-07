"""Tests for the generated CARS_INDEX vehicle support data module."""

from __future__ import annotations

import unittest

import ai.tests.bootstrap_pc  # noqa: F401 — side effect: openpilot mocks

from ai.tools.domains.vehicle.cars_index import CARS_INDEX, lookup_cars

_FIELDS = (
  "make",
  "model",
  "years",
  "package",
  "acc",
  "acc_min_mph",
  "alc_min_mph",
  "steer_torque_stars",
  "resume_stars",
  "hardware_summary",
)


class TestCarsIndex(unittest.TestCase):
  def test_index_nonempty(self):
    self.assertGreaterEqual(len(CARS_INDEX), 300)

  def test_lookup_toyota_rav4(self):
    rows = lookup_cars("Toyota", "RAV4")
    self.assertGreaterEqual(len(rows), 1)
    self.assertTrue(all(r.get("make") == "Toyota" for r in rows))

  def test_lookup_case_insensitive_and_partial(self):
    self.assertEqual(lookup_cars("toyota", "rav4"), lookup_cars("Toyota", "RAV4"))
    self.assertGreaterEqual(len(lookup_cars("honda", "")), 1)
    self.assertEqual(len(lookup_cars(None, None)), len(CARS_INDEX))

  def test_all_fields_are_str(self):
    for row in CARS_INDEX:
      for key in _FIELDS:
        self.assertIsInstance(row.get(key), str, f"{row.get('make')} {row.get('model')} field {key}")

  def test_acc_values_recognized(self):
    known = {"openpilot", "openpilot available", "stock", "dashcam"}
    for row in CARS_INDEX:
      acc = str(row.get("acc", "")).lower()
      if acc:
        self.assertTrue(
          any(acc.startswith(k) for k in known),
          f"unexpected acc value: {row.get('acc')}",
        )


if __name__ == "__main__":
  unittest.main()
