"""
Copyright (c) 2026-, mouxan.

Unit tests for openpilot.sunnypilot.models.chunked_download.

All cases are offline: chunk bodies and manifests are faked in a temp directory
and the HTTP layer is stubbed out, so nothing touches the network.
"""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

from openpilot.common.file_chunker import get_chunk_name, get_manifest_path
from openpilot.sunnypilot.models.chunked_download import (ChunkedDownloadError, delete_chunked_artifact, fetch_chunk_manifest,
                                                          try_download_chunked)


def make_chunks(directory: Path, name: str, body: bytes, chunk_size: int) -> int:
  """Write body as file_chunker chunks + manifest; returns the chunk count."""
  count = (len(body) + chunk_size - 1) // chunk_size
  for i in range(count):
    (directory / get_chunk_name(name, i, count)).write_bytes(body[i * chunk_size:(i + 1) * chunk_size])
  (directory / get_manifest_path(name)).write_text(str(count))
  return count


class _FakeResponse:
  def __init__(self, payload: bytes = b"", status_code: int = 200, text: str = ""):
    self.payload = payload
    self.status_code = status_code
    self.text = text
    self.headers = {"Content-Length": str(len(payload))}

  def raise_for_status(self):
    if self.status_code >= 400:
      raise requests.HTTPError(f"HTTP {self.status_code}")

  def iter_content(self, chunk_size):
    for i in range(0, len(self.payload), chunk_size):
      yield self.payload[i:i + chunk_size]

  def __enter__(self):
    return self

  def __exit__(self, *args):
    return False


class OfflineChunkedTest(unittest.TestCase):
  def setUp(self):
    self._tmp = tempfile.TemporaryDirectory()
    self.dir = Path(self._tmp.name)
    self.body = bytes(range(256)) * 64  # 16 KiB
    self.chunk_size = 6 * 1024
    self.count = make_chunks(self.dir, "model.pkl", self.body, self.chunk_size)
    self.base = "https://hf.example/models/model.pkl"

  def tearDown(self):
    self._tmp.cleanup()

  def _patch_requests(self):
    """Route every fake URL onto the files written in setUp."""
    def fake_get(url, *args, **kwargs):
      name = url.rsplit("/", 1)[-1]
      path = self.dir / name
      if url.endswith(".chunkmanifest"):
        if not path.is_file():
          return _FakeResponse(status_code=404)
        return _FakeResponse(text=path.read_text())
      if not path.is_file():
        return _FakeResponse(status_code=404)
      return _FakeResponse(payload=path.read_bytes())

    fake_head = lambda url, *args, **kwargs: _FakeResponse(payload=(self.dir / url.rsplit("/", 1)[-1]).read_bytes())  # noqa: E731
    return mock.patch("openpilot.sunnypilot.models.chunked_download.requests.get", side_effect=fake_get), \
           mock.patch("openpilot.sunnypilot.models.chunked_download.requests.head", side_effect=fake_head)

  def test_manifest_parse(self):
    with mock.patch("openpilot.sunnypilot.models.chunked_download.requests.get", return_value=_FakeResponse(text="3\n")):
      self.assertEqual(fetch_chunk_manifest(self.base), 3)
    with mock.patch("openpilot.sunnypilot.models.chunked_download.requests.get", return_value=_FakeResponse(status_code=404)):
      self.assertIsNone(fetch_chunk_manifest(self.base))
    with mock.patch("openpilot.sunnypilot.models.chunked_download.requests.get", return_value=_FakeResponse(text="not-a-number")):
      self.assertIsNone(fetch_chunk_manifest(self.base))
    with mock.patch("openpilot.sunnypilot.models.chunked_download.requests.get", return_value=_FakeResponse(text="0")):
      self.assertIsNone(fetch_chunk_manifest(self.base))
    with mock.patch("openpilot.sunnypilot.models.chunked_download.requests.get", return_value=_FakeResponse(text="99999")):
      self.assertIsNone(fetch_chunk_manifest(self.base))

  def test_download_reassembles_in_order(self):
    get_patch, head_patch = self._patch_requests()
    destination = self.dir / "downloaded.pkl"
    with get_patch, head_patch:
      progress = []
      result = try_download_chunked(destination, [self.base], expected_size=len(self.body),
                                    expected_sha256=hashlib.sha256(self.body).hexdigest(),
                                    progress_cb=progress.append)
    self.assertTrue(result)
    manifest = Path(get_manifest_path(destination))
    self.assertEqual(manifest.read_text(), str(self.count))
    chunks = [Path(get_chunk_name(destination, i, self.count)).read_bytes() for i in range(self.count)]
    self.assertEqual(b"".join(chunks), self.body)  # reassembly order matches the source bytes
    # sp's own read path (helpers._compute_hash) must accept the downloaded layout
    from openpilot.common.file_chunker import open_file_chunked
    with open_file_chunked(destination) as f:
      self.assertEqual(hashlib.file_digest(f, "sha256").hexdigest(), hashlib.sha256(self.body).hexdigest())
    self.assertGreaterEqual(progress[-1], 100)

  def test_sha256_mismatch_raises(self):
    get_patch, head_patch = self._patch_requests()
    destination = self.dir / "bad.pkl"
    with get_patch, head_patch:
      with self.assertRaises(ChunkedDownloadError):
        try_download_chunked(destination, [self.base], expected_sha256="0" * 64)
    # a failed verification leaves no half-promoted chunk state behind
    self.assertFalse(Path(get_manifest_path(destination)).exists())
    self.assertFalse(list(destination.parent.glob(f"{destination.name}.chunk*of*")))

  def test_no_manifest_falls_back(self):
    get_patch, head_patch = self._patch_requests()
    # same dir but no manifest -> module must report None so callers use the plain path
    (self.dir / get_manifest_path("model.pkl")).unlink()
    destination = self.dir / "fallback.pkl"
    with get_patch, head_patch:
      self.assertIsNone(try_download_chunked(destination, [self.base]))

  def test_fallback_url_order(self):
    get_patch, head_patch = self._patch_requests()
    # first source has no manifest; the second (GitHub-style) one does
    (self.dir / get_manifest_path("model.pkl")).unlink()
    make_chunks(self.dir, "mirror.pkl", self.body, self.chunk_size)
    fallback = "https://gh.example/models/model.pkl"
    urls = []
    destination = self.dir / "ordered.pkl"

    def fake_get(url, *args, **kwargs):
      urls.append(url)
      if url.endswith(".chunkmanifest"):
        if url.startswith(fallback):
          return _FakeResponse(text=str(self.count))
        return _FakeResponse(status_code=404)
      return _FakeResponse(payload=(self.dir / url.rsplit("/", 1)[-1]).read_bytes())

    with mock.patch("openpilot.sunnypilot.models.chunked_download.requests.get", side_effect=fake_get), head_patch:
      self.assertTrue(try_download_chunked(destination, [self.base, fallback], expected_sha256=hashlib.sha256(self.body).hexdigest()))
    self.assertTrue(urls[0].startswith(self.base))  # primary probed first
    self.assertTrue(urls[len(urls) - self.count - 1].startswith(fallback))

  def test_cancel_and_delete(self):
    get_patch, head_patch = self._patch_requests()
    destination = self.dir / "cancelled.pkl"
    with get_patch, head_patch:
      self.assertFalse(try_download_chunked(destination, [self.base], cancel_cb=lambda: True))
    self.assertFalse(destination.exists())

    # a complete artifact is fully removed by delete_chunked_artifact
    make_chunks(self.dir, "gone.pkl", self.body, self.chunk_size)
    gone = self.dir / "gone.pkl"
    delete_chunked_artifact(gone)
    self.assertFalse(gone.exists())
    self.assertFalse(Path(get_manifest_path(gone)).exists())
    self.assertFalse(list(self.dir.glob("gone.pkl.chunk*of*")))

  def test_corrupt_chunk_size(self):
    get_patch, head_patch = self._patch_requests()
    # head lies about the size of chunk 1 -> transfer must fail, not verify
    def fake_head(url, *args, **kwargs):
      response = _FakeResponse(payload=(self.dir / url.rsplit("/", 1)[-1]).read_bytes())
      if "chunk01of" in url:
        response.headers["Content-Length"] = "1"
      return response

    destination = self.dir / "sizemismatch.pkl"
    with get_patch, mock.patch("openpilot.sunnypilot.models.chunked_download.requests.head", side_effect=fake_head):
      self.assertFalse(try_download_chunked(destination, [self.base], expected_sha256=hashlib.sha256(self.body).hexdigest()))


class LfsPointerTest(unittest.TestCase):
  """A Git LFS pointer must never be published as a model.

  The pointer is a ~130 byte text file. When the expected size is unknown it
  passes the size check, so the download would look successful and leave a
  model that is not a model.
  """

  POINTER = b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"a" * 64 + b"\nsize 766040736\n"

  def setUp(self):
    self._tmp = tempfile.TemporaryDirectory()
    self.dir = Path(self._tmp.name)
    self.base = "https://example.invalid/pointer.pkl"
    make_chunks(self.dir, "pointer.pkl", self.POINTER, 64)

  def tearDown(self):
    self._tmp.cleanup()

  def _patch_requests(self):
    def fake_get(url, *args, **kwargs):
      name = url.rsplit("/", 1)[-1]
      path = self.dir / name
      if url.endswith(".chunkmanifest"):
        if not path.is_file():
          return _FakeResponse(status_code=404)
        return _FakeResponse(text=path.read_text())
      if not path.is_file():
        return _FakeResponse(status_code=404)
      return _FakeResponse(payload=path.read_bytes())

    def fake_head(url, *args, **kwargs):
      name = url.rsplit("/", 1)[-1]
      path = self.dir / name
      if not path.is_file():
        return _FakeResponse(status_code=404)
      return _FakeResponse(payload=path.read_bytes())

    return (mock.patch("openpilot.sunnypilot.models.chunked_download.requests.get", side_effect=fake_get),
            mock.patch("openpilot.sunnypilot.models.chunked_download.requests.head", side_effect=fake_head))

  def test_a_pointer_is_rejected(self):
    get_patch, head_patch = self._patch_requests()
    destination = self.dir / "pointer.pkl"
    with get_patch, head_patch:
      with self.assertRaises(ChunkedDownloadError):
        try_download_chunked(destination, [self.base])
    # nothing was published
    self.assertFalse(destination.exists())
    self.assertFalse(Path(get_manifest_path(destination)).exists())
    self.assertFalse(list(self.dir.glob("pointer.pkl.chunk*of*")))

  def test_a_real_artifact_still_downloads(self):
    body = b"real model bytes" * 32
    make_chunks(self.dir, "pointer.pkl", body, 64)
    get_patch, head_patch = self._patch_requests()
    destination = self.dir / "pointer.pkl"
    with get_patch, head_patch:
      self.assertTrue(try_download_chunked(destination, [self.base]))
    self.assertTrue(Path(get_manifest_path(destination)).exists())


if __name__ == "__main__":
  unittest.main()
