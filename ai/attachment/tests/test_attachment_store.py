"""Tests for ai.attachment.store."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ai.attachment.store import AttachmentError, AttachmentLimits, AttachmentStore, ImageVariantSpec


@pytest.fixture
def store(tmp_path: Path):
  return AttachmentStore(tmp_path)


def test_upload_and_get(store: AttachmentStore):
  data = b"hello world"
  ref = store.upload(data, name="hello.txt", mime_type="text/plain")
  assert ref.attachment_id.startswith("sha256:")
  assert ref.mime_type == "text/plain"
  assert ref.size == 11
  loaded_ref, loaded_data = store.get(ref.attachment_id)
  assert loaded_data == data
  assert loaded_ref.size == ref.size


def test_upload_invalid_id(store: AttachmentStore):
  with pytest.raises(AttachmentError) as exc:
    store._object_path("bad-id")
  assert exc.value.code == "INVALID_ATTACHMENT_ID"


def test_upload_many_batch_limits(tmp_path: Path):
  limits = AttachmentLimits(max_count=2)
  store = AttachmentStore(tmp_path, limits=limits)
  items = [(b"a", "a.txt", "text/plain"), (b"b", "b.txt", "text/plain"), (b"c", "c.txt", "text/plain")]
  with pytest.raises(AttachmentError) as exc:
    store.upload_many(items)
  assert exc.value.code == "TOO_MANY_ATTACHMENTS"


def test_list_and_delete(store: AttachmentStore):
  ref1 = store.upload(b"one", name="one.txt")
  ref2 = store.upload(b"two", name="two.txt")
  assert len(store.list()) == 2
  assert store.delete(ref1.attachment_id) is True
  assert len(store.list()) == 1
  assert store.get_meta(ref2.attachment_id).size == 3


def test_content_addressed_dedup(store: AttachmentStore):
  ref1 = store.upload(b"dup", name="a.txt")
  ref2 = store.upload(b"dup", name="b.txt")
  assert ref1.attachment_id == ref2.attachment_id


def test_image_variant_without_pillow(store: AttachmentStore, monkeypatch):
  """Without Pillow, get_variant should fall back to original bytes."""
  monkeypatch.setattr("ai.attachment.store._has_pillow", lambda: False)
  ref = store.upload(b"fake-image", name="img.png", mime_type="image/png")
  v_ref, v_data = store.get_variant(ref.attachment_id, ImageVariantSpec())
  assert v_data == b"fake-image"
  assert v_ref.attachment_id == ref.attachment_id


def test_object_path(store: AttachmentStore):
  ref = store.upload(b"x", name="x.txt")
  path = store.object_path(ref.attachment_id)
  assert path.exists()
  assert path.name == ref.attachment_id[7:]


def test_get_meta_roundtrip(store: AttachmentStore):
  data = b"meta roundtrip"
  ref = store.upload(data, name="m.txt", mime_type="text/plain")
  meta = store.get_meta(ref.attachment_id)
  assert meta.attachment_id == ref.attachment_id
  assert meta.mime_type == "text/plain"
