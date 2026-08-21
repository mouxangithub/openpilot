"""Cabana car/DBC resolution helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from ai import cabana


class CabanaCarTest(unittest.TestCase):
  def test_resolve_car_params_prefers_route(self):
    route_cp = {
      "brand": "toyota",
      "carFingerprint": "TOYOTA_COROLLA",
      "openpilotLongitudinalControl": False,
      "source": "route",
      "route": "route-a",
    }
    device_cp = {
      "brand": "mock",
      "carFingerprint": "MOCK",
      "openpilotLongitudinalControl": False,
    }
    with patch.object(cabana, "_load_car_params_from_route", return_value=route_cp), patch.object(
      cabana, "_load_car_params", return_value=device_cp,
    ):
      cp = cabana._resolve_car_params("route-a")
    self.assertEqual(cp, route_cp)

  def test_resolve_car_params_falls_back_to_device(self):
    device_cp = {
      "brand": "mock",
      "carFingerprint": "MOCK",
      "openpilotLongitudinalControl": False,
    }
    with patch.object(cabana, "_load_car_params_from_route", return_value=None), patch.object(
      cabana, "_load_car_params", return_value=device_cp,
    ):
      cp = cabana._resolve_car_params("missing-route")
    self.assertEqual(cp["carFingerprint"], "MOCK")
    self.assertEqual(cp["source"], "device")


if __name__ == "__main__":
  unittest.main()
