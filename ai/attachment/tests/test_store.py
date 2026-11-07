"""Unit tests for ai.attachment.store."""

from __future__ import annotations

import tempfile
import unittest

from ai.attachment.models import content_id
from ai.attachment.store import AttachmentError, AttachmentLimits, AttachmentStore


class TestAttachmentStore(unittest.TestCase):
  def setUp(self) -> None:
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.store = AttachmentStore(self.tmp.name)

  def test_upload_text(self) -> None:
    data = b"hello world"
    ref = self.store.upload(data, name="hello.txt", mime_type="text/plain")
    self.assertEqual(ref.attachment_id, content_id(data))
    self.assertEqual(ref.mime_type, "text/plain")
    self.assertEqual(ref.size, 11)
    self.assertEqual(ref.name, "hello.txt")

  def test_upload_guesses_mime(self) -> None:
    data = b"fake image bytes"
    ref = self.store.upload(data, name="img.png")
    self.assertEqual(ref.mime_type, "image/png")

  def test_list_and_get(self) -> None:
    data = b"content"
    ref = self.store.upload(data, name="a.txt", mime_type="text/plain")
    refs = self.store.list()
    self.assertEqual(len(refs), 1)
    self.assertEqual(refs[0].attachment_id, ref.attachment_id)

    loaded_ref, loaded_data = self.store.get(ref.attachment_id)
    self.assertEqual(loaded_ref.attachment_id, ref.attachment_id)
    self.assertEqual(loaded_data, data)

  def test_get_missing(self) -> None:
    with self.assertRaises(AttachmentError) as ctx:
      self.store.get("sha256:" + "00" * 32)
    self.assertEqual(ctx.exception.code, "ATTACHMENT_NOT_FOUND")

  def test_delete(self) -> None:
    data = b"to delete"
    ref = self.store.upload(data, name="d.txt", mime_type="text/plain")
    self.assertTrue(self.store.delete(ref.attachment_id))
    self.assertEqual(self.store.list(), [])
    self.assertFalse(self.store.delete(ref.attachment_id))

  def test_batch_limits(self) -> None:
    limits = AttachmentLimits(max_count=2, max_total_bytes=100)
    store = AttachmentStore(self.tmp.name, limits=limits)
    with self.assertRaises(AttachmentError) as ctx:
      store.upload_many([
        (b"a", "a.txt", "text/plain"),
        (b"b", "b.txt", "text/plain"),
        (b"c", "c.txt", "text/plain"),
      ])
    self.assertEqual(ctx.exception.code, "TOO_MANY_ATTACHMENTS")

  def test_unsupported_media_type(self) -> None:
    limits = AttachmentLimits(allowed_media_types=frozenset(["image/png"]))
    store = AttachmentStore(self.tmp.name, limits=limits)
    with self.assertRaises(AttachmentError) as ctx:
      store.upload(b"x", name="x.txt", mime_type="text/plain")
    self.assertEqual(ctx.exception.code, "UNSUPPORTED_MEDIA_TYPE")

  def test_invalid_id(self) -> None:
    with self.assertRaises(AttachmentError):
      self.store.get("not-an-id")


if __name__ == "__main__":
  unittest.main()
