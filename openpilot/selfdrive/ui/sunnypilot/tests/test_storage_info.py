"""
Copyright (c) 2026-, mouxan.

Pure-logic tests for the storage usage helpers. These run on a PC (they only
touch temp directories; disk_usage is exercised against the local FS too).
"""
import os
import sys
import tempfile
import unittest

from openpilot.selfdrive.ui.sunnypilot.storage_info import (
  GB, MB, cached_bundle_sizes, directory_size, disk_usage, format_size, model_root_size,
)


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


class _FakeArtifact:
  def __init__(self, file_name, file_size_bytes=0):
    self.fileName = file_name
    self.fileSizeBytes = file_size_bytes


class _FakeBundle:
  def __init__(self, *artifacts):
    self.artifacts = list(artifacts)


class TestModelRootSize(unittest.TestCase):
  def test_matches_recursive_walk(self):
    with tempfile.TemporaryDirectory() as d:
      os.makedirs(os.path.join(d, "sub"))
      for rel, size in (("a.thneed", 1000), (os.path.join("sub", "b.thneed"), 2000)):
        with open(os.path.join(d, rel), "wb") as f:
          f.write(b"x" * size)
      self.assertEqual(model_root_size(d), directory_size(d))
      self.assertEqual(model_root_size(d), 3000)

  def test_missing_root_is_zero(self):
    self.assertEqual(model_root_size("/no/such/model/root"), 0)


class TestCachedBundleSizes(unittest.TestCase):
  def test_attributes_complete_files_per_source(self):
    with tempfile.TemporaryDirectory() as d:
      for rel, size in (("small.dlc", 1000), ("big.dlc", 4000)):
        with open(os.path.join(d, rel), "wb") as f:
          f.write(b"x" * size)
      bundles = {
        "qcom": [_FakeBundle(_FakeArtifact("small.dlc", 1000))],
        "chestnut": [_FakeBundle(_FakeArtifact("big.dlc", 4000))],
      }
      sizes = cached_bundle_sizes(d, bundles)
      self.assertEqual(sizes["qcom"], 1000)
      self.assertEqual(sizes["chestnut"], 4000)

  def test_shared_artifact_counts_for_each_source_but_total_does_not_double(self):
    # one file listed by both catalogs is attributed to both; the directory
    # total (the row actually shown) walks the FS once, so it stays 500.
    with tempfile.TemporaryDirectory() as d:
      with open(os.path.join(d, "shared.dlc"), "wb") as f:
        f.write(b"x" * 500)
      bundle = _FakeBundle(_FakeArtifact("shared.dlc", 500))
      sizes = cached_bundle_sizes(d, {"qcom": [bundle], "chestnut": [bundle]})
      self.assertEqual(sizes["qcom"], 500)
      self.assertEqual(sizes["chestnut"], 500)
      self.assertEqual(model_root_size(d), 500)

  def test_missing_artifact_and_unknown_source(self):
    with tempfile.TemporaryDirectory() as d:
      bundles = {"qcom": [_FakeBundle(_FakeArtifact("absent.dlc"))], "chestnut": []}
      sizes = cached_bundle_sizes(d, bundles)
      self.assertEqual(sizes, {"qcom": 0, "chestnut": 0})


if __name__ == "__main__":
  unittest.main()
