"""
Copyright (c) 2026-, mouxan.

Pure-logic tests for the storage usage helpers. These run on a PC (they only
touch temp directories; disk_usage is exercised against the local FS too).
"""
import os
import sys
import tempfile
import unittest

from openpilot.selfdrive.ui.sunnypilot.storage_info import GB, MB, directory_size, disk_usage, format_size


class TestDirectorySize(unittest.TestCase):
  def test_missing_dir_is_zero(self):
    self.assertEqual(directory_size("/no/such/path/here"), 0)

  def test_counts_files_recursively(self):
    with tempfile.TemporaryDirectory() as d:
      os.makedirs(os.path.join(d, "sub", "deep"))
      for rel, size in (("a.bin", 1000), (os.path.join("sub", "b.bin"), 2000),
                        (os.path.join("sub", "deep", "c.bin"), 4000)):
        with open(os.path.join(d, rel), "wb") as f:
          f.write(b"x" * size)
      self.assertEqual(directory_size(d), 7000)

  def test_empty_dir_is_zero(self):
    with tempfile.TemporaryDirectory() as d:
      self.assertEqual(directory_size(d), 0)

  @unittest.skipIf(sys.platform == "win32", "symlink creation needs privilege on Windows")
  def test_symlink_not_double_counted(self):
    with tempfile.TemporaryDirectory() as d:
      target = os.path.join(d, "real.bin")
      with open(target, "wb") as f:
        f.write(b"x" * 500)
      os.symlink(target, os.path.join(d, "link.bin"))
      self.assertEqual(directory_size(d), 500)


class TestDiskUsage(unittest.TestCase):
  def test_real_filesystem_reports_usage(self):
    # statvfs is POSIX-only; on Windows the helper returns None by design
    usage = disk_usage(tempfile.gettempdir())
    if sys.platform == "win32":
      self.assertIsNone(usage)
      return
    self.assertIsNotNone(usage)
    self.assertGreater(usage.total, 0)
    self.assertGreaterEqual(usage.used + usage.free, 0)
    self.assertGreaterEqual(usage.used, 0)
    self.assertTrue(0.0 <= usage.used_fraction <= 1.0)

  @unittest.skipIf(sys.platform == "win32", "statvfs is POSIX-only")
  def test_missing_path_is_none(self):
    self.assertIsNone(disk_usage("/no/such/mount/point/xyz"))


class TestFormatSize(unittest.TestCase):
  def test_mb_below_gigabyte(self):
    self.assertEqual(format_size(500 * MB), "500.00 MB")
    self.assertTrue(format_size(12 * MB + 340 * 1024 * 100).endswith("MB"))

  def test_gigabyte_and_up(self):
    self.assertTrue(format_size(GB).startswith("1.00"))
    self.assertTrue(format_size(GB).endswith("GB"))

  def test_zero_is_mb(self):
    self.assertEqual(format_size(0), "0.00 MB")


if __name__ == "__main__":
  unittest.main()
