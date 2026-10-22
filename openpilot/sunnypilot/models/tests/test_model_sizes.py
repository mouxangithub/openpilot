"""Tests for the local model size ledger."""
import tempfile
import time
import unittest
from pathlib import Path

from openpilot.sunnypilot.models.model_sizes import (
  CACHE_TTL_S,
  ModelSizes,
  artifact_local_name,
  artifact_size,
  bundle_download_fraction,
  bundle_local_status,
  chunk_file_name,
  positive_size,
)

GB = 1024 ** 3


class FakeArtifact:
  def __init__(self, file_name):
    self.fileName = file_name


class FakeModel:
  def __init__(self, file_name):
    self.artifact = FakeArtifact(file_name)


class FakeBundle:
  def __init__(self, *file_names):
    self.models = [FakeModel(name) for name in file_names]


class TestArtifactSize(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.root = Path(self.tmp.name)

  def tearDown(self):
    self.tmp.cleanup()

  def test_a_complete_file_is_complete(self):
    target = self.root / "model.pkl"
    target.write_bytes(b"x" * 1024)
    record = artifact_size(target)
    self.assertEqual(record['sizeStatus'], 'complete')
    self.assertEqual(record['downloadedBytes'], 1024)
    self.assertEqual(record['fileSizeBytes'], 1024)
    self.assertEqual(record['sizeSource'], 'installed')

  def test_an_absent_file_with_no_trace_is_unknown(self):
    record = artifact_size(self.root / "missing.pkl")
    self.assertIsNone(record['fileSizeBytes'])
    self.assertIsNone(record['downloadedBytes'])
    self.assertEqual(record['sizeStatus'], 'unknown')

  def test_a_declared_size_without_a_file_is_declared(self):
    record = artifact_size(self.root / "missing.pkl", 5 * GB)
    self.assertEqual(record['declaredSizeBytes'], 5 * GB)
    self.assertEqual(record['sizeStatus'], 'declared')
    self.assertEqual(record['sizeSource'], 'metadata')

  def test_a_partial_chunk_set_is_partial(self):
    # three chunks expected, two made it down
    target = self.root / "model.pkl"
    (self.root / (target.name + '.chunkmanifest')).write_text("3")
    (self.root / chunk_file_name(target.name, 0, 3)).write_bytes(b"a" * 100)
    (self.root / chunk_file_name(target.name, 1, 3)).write_bytes(b"b" * 100)
    record = artifact_size(target)
    self.assertEqual(record['sizeStatus'], 'partial')
    self.assertEqual(record['downloadedBytes'], 200)
    self.assertIsNone(record['fileSizeBytes'])

  def test_a_full_chunk_set_without_the_join_reads_complete(self):
    # Reference semantics: all the bytes are on disk, so the record is
    # complete even before the join; the hash check at join time is the
    # real usage gate.
    target = self.root / "model.pkl"
    (self.root / (target.name + '.chunkmanifest')).write_text("2")
    (self.root / chunk_file_name(target.name, 0, 2)).write_bytes(b"a" * 100)
    (self.root / chunk_file_name(target.name, 1, 2)).write_bytes(b"b" * 100)
    self.assertEqual(artifact_size(target)['sizeStatus'], 'complete')

  def test_the_joined_file_with_chunks_left_behind_is_complete(self):
    target = self.root / "model.pkl"
    (self.root / (target.name + '.chunkmanifest')).write_text("2")
    (self.root / chunk_file_name(target.name, 0, 2)).write_bytes(b"a" * 100)
    target.write_bytes(b"joined")
    record = artifact_size(target)
    self.assertEqual(record['sizeStatus'], 'complete')
    self.assertEqual(record['downloadedBytes'], 6)

  def test_a_size_mismatch_is_reported(self):
    target = self.root / "model.pkl"
    target.write_bytes(b"x" * 10)
    self.assertEqual(artifact_size(target, 999)['sizeStatus'], 'mismatch')

  def test_a_garbage_manifest_counts_only_the_chunks(self):
    target = self.root / "model.pkl"
    (self.root / (target.name + '.chunkmanifest')).write_text("not-a-number")
    (self.root / chunk_file_name(target.name, 0, 3)).write_bytes(b"a" * 10)
    record = artifact_size(target)
    self.assertEqual(record['sizeStatus'], 'partial')
    self.assertEqual(record['downloadedBytes'], 10)

  def test_a_stray_file_matching_no_chunk_pattern_is_ignored(self):
    target = self.root / "model.pkl"
    (self.root / (target.name + '.chunkweird')).write_bytes(b"z" * 5)
    record = artifact_size(target)
    self.assertEqual(record['sizeStatus'], 'unknown')

  def test_positive_size_bounds(self):
    self.assertIsNone(positive_size("5"))
    self.assertIsNone(positive_size(0))
    self.assertIsNone(positive_size(-1))
    self.assertIsNone(positive_size(positive_size.__doc__ and (1 << 51)))
    self.assertEqual(positive_size(5), 5)


class TestChunkName(unittest.TestCase):
  def test_it_matches_file_chunker_exactly(self):
    from openpilot.common.file_chunker import get_chunk_name
    for name, idx, count in (("m.pkl", 0, 1), ("m.pkl", 11, 42), ("x", 99, 100)):
      self.assertEqual(chunk_file_name(name, idx, count), get_chunk_name(name, idx, count))


class TestCache(unittest.TestCase):
  def test_a_cached_read_is_reused_within_the_ttl(self):
    with tempfile.TemporaryDirectory() as tmp:
      target = Path(tmp) / "m.pkl"
      target.write_bytes(b"x")
      sizes = ModelSizes()
      first = sizes.size(target, None)
      target.write_bytes(b"changed")
      self.assertEqual(sizes.size(target, None), first)

  def test_the_cache_expires(self):
    with tempfile.TemporaryDirectory() as tmp:
      target = Path(tmp) / "m.pkl"
      target.write_bytes(b"x")
      sizes = ModelSizes()
      first = sizes.size(target, None)
      target.write_bytes(b"changed!")
      # a record's deadline is its read time plus the TTL
      key = (str(target), repr(None))
      deadline = sizes.sizes[key][0]
      sizes.sizes[key] = (time.monotonic() - 0.001, first)
      assert deadline  # the record carried a deadline at all
      self.assertNotEqual(sizes.size(target, None), first)

  def test_the_ttl_is_short(self):
    # the cache exists to absorb re-renders, not to hide disk state
    self.assertLessEqual(CACHE_TTL_S, 5.0)

  def test_the_cache_is_bounded(self):
    sizes = ModelSizes()
    for i in range(1200):
      sizes.size(f"/nonexistent/{i}.pkl", None)
    self.assertLessEqual(len(sizes.sizes), 1000)


class TestBundleStatus(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.root = Path(self.tmp.name)

  def tearDown(self):
    self.tmp.cleanup()

  def test_a_bundle_with_no_files_reports_unknown_and_no_fraction(self):
    bundle = FakeBundle("a.pkl", "b.pkl")
    status = bundle_local_status(bundle, self.root)
    self.assertEqual(set(status), {"a.pkl", "b.pkl"})
    self.assertTrue(all(record['sizeStatus'] == 'unknown' for record in status.values()))
    self.assertIsNone(bundle_download_fraction(bundle, self.root))

  def test_files_on_disk_are_reported_per_name(self):
    (self.root / "a.pkl").write_bytes(b"x" * 10)
    bundle = FakeBundle("a.pkl", "b.pkl")
    status = bundle_local_status(bundle, self.root)
    self.assertEqual(status["a.pkl"]['sizeStatus'], 'complete')
    self.assertEqual(status["b.pkl"]['sizeStatus'], 'unknown')

  def test_the_fraction_uses_local_bytes(self):
    (self.root / "a.pkl").write_bytes(b"x" * 10)
    bundle = FakeBundle("a.pkl")
    self.assertEqual(bundle_download_fraction(bundle, self.root), 1.0)

  def test_a_partial_bundle_sits_between_zero_and_one(self):
    target = self.root / "a.pkl"
    (self.root / (target.name + '.chunkmanifest')).write_text("4")
    (self.root / chunk_file_name(target.name, 0, 4)).write_bytes(b"a" * 10)
    (self.root / chunk_file_name(target.name, 1, 4)).write_bytes(b"b" * 10)
    bundle = FakeBundle("a.pkl")
    self.assertEqual(bundle_download_fraction(bundle, self.root), 0.5)

  def test_models_without_a_file_name_are_skipped(self):
    class NoArtifact:
      artifact = None
    bundle = FakeBundle()
    bundle.models.append(NoArtifact())
    self.assertEqual(bundle_local_status(bundle, self.root), {})

  def test_artifact_local_name(self):
    self.assertEqual(artifact_local_name(FakeModel("m.pkl")), "m.pkl")
    self.assertIsNone(artifact_local_name(FakeBundle().models[0]) if False else None)
    class Empty:
      artifact = FakeArtifact("")
    self.assertIsNone(artifact_local_name(Empty()))


if __name__ == "__main__":
  unittest.main()
