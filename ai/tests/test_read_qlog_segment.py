"""read_qlog_segment route name validation (stdlib only)."""

from __future__ import annotations

import unittest


def _valid_route_name(route_name: str) -> bool:
  return bool(route_name) and ".." not in route_name and "/" not in route_name and "\\" not in route_name


class ReadQlogSegmentValidationTest(unittest.TestCase):
  def test_rejects_path_traversal(self):
    self.assertFalse(_valid_route_name("../secret"))
    self.assertFalse(_valid_route_name("a/b"))

  def test_accepts_normal_route(self):
    self.assertTrue(_valid_route_name("2026-07-08--14-30-00--abc--0"))


if __name__ == "__main__":
  unittest.main()
