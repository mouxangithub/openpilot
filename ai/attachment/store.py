"""Local, content-addressed attachment store.

Files are persisted under ``<base_dir>/objects/<2-char-prefix>/<sha256>`` and
metadata is kept in ``<base_dir>/meta/<sha256>.json`` so the store can be listed
and inspected without re-reading every object.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ai.attachment.models import (
  AttachmentRef,
  content_id,
  guess_mime_type,
  normalize_filename,
)

BROAD_MEDIA_TYPES: frozenset[str] = frozenset([
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/gif",
  "text/plain",
  "text/markdown",
  "text/x-python",
  "application/json",
  "application/pdf",
])


def _has_pillow() -> bool:
  """Probe Pillow availability without importing at module load time."""
  try:
    import PIL.Image  # noqa: F401
    return True
  except Exception:
    return False


class AttachmentError(Exception):
  """Raised when attachment validation or storage fails."""

  def __init__(self, message: str, code: str, *, cause: Exception | None = None) -> None:
    super().__init__(message)
    self.message = message
    self.code = code
    self.cause = cause


@dataclass
class AttachmentLimits:
  """Admission limits for one upload batch."""

  max_bytes: int = 20 * 1024 * 1024
  max_count: int = 20
  max_total_bytes: int = 200 * 1024 * 1024
  max_image_pixels: int = 64_000_000
  max_image_dimension: int = 8192
  allowed_media_types: frozenset[str] = field(default_factory=lambda: BROAD_MEDIA_TYPES)

  def check_batch(self, total_count: int, total_bytes: int) -> None:
    if total_count > self.max_count:
      raise AttachmentError("Attachment batch exceeds the configured count limit.", "TOO_MANY_ATTACHMENTS")
    if total_bytes > self.max_total_bytes:
      raise AttachmentError("Attachment batch exceeds the configured aggregate byte limit.", "BATCH_TOO_LARGE")

  def check(self, mime_type: str, size: int, *, total_count: int, total_bytes: int) -> None:
    self.check_batch(total_count, total_bytes)
    if mime_type not in self.allowed_media_types:
      raise AttachmentError(f"Media type {mime_type} is not accepted.", "UNSUPPORTED_MEDIA_TYPE")
    if size > self.max_bytes:
      raise AttachmentError("Attachment exceeds the configured byte limit.", "ATTACHMENT_TOO_LARGE")


@dataclass
class ImageVariantSpec:
  """Requested image variant."""

  max_size: tuple[int, int] = (512, 512)
  grayscale: bool = False
  fmt: str = "PNG"


def _sha256_prefix(attachment_id: str) -> tuple[str, str]:
  """Validate a sha256: attachment id and return (digest, prefix)."""
  if not attachment_id.startswith("sha256:") or len(attachment_id) != 71:
    raise AttachmentError("Invalid attachment id.", "INVALID_ATTACHMENT_ID")
  digest = attachment_id[7:]
  return digest, digest[:2]


class AttachmentStore:
  """Content-addressed file attachment backend.

  Supports optional image normalization when Pillow is available. Without
  Pillow, image uploads are stored as opaque blobs (metadata only).
  """

  def __init__(
    self,
    base_dir: str | os.PathLike[str],
    *,
    limits: AttachmentLimits | None = None,
  ) -> None:
    self.base_dir = Path(base_dir).resolve()
    self.limits = limits or AttachmentLimits()
    self.objects_dir = self.base_dir / "objects"
    self.meta_dir = self.base_dir / "meta"
    self.variants_dir = self.base_dir / "variants"
    self.objects_dir.mkdir(parents=True, exist_ok=True)
    self.meta_dir.mkdir(parents=True, exist_ok=True)
    self.variants_dir.mkdir(parents=True, exist_ok=True)

  def _object_path(self, attachment_id: str) -> Path:
    digest, prefix = _sha256_prefix(attachment_id)
    return self.objects_dir / prefix / digest

  def _meta_path(self, attachment_id: str) -> Path:
    digest, prefix = _sha256_prefix(attachment_id)
    return self.meta_dir / f"{digest}.json"

  def _variant_path(self, attachment_id: str, spec: ImageVariantSpec) -> Path:
    digest, prefix = _sha256_prefix(attachment_id)
    fmt = spec.fmt.lower()
    gray = "g" if spec.grayscale else "c"
    size_tag = f"{spec.max_size[0]}x{spec.max_size[1]}"
    return self.variants_dir / prefix / f"{digest}_{size_tag}_{gray}.{fmt}"

  def _load_meta(self, attachment_id: str) -> AttachmentRef:
    path = self._meta_path(attachment_id)
    try:
      data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
      raise AttachmentError("Attachment not found.", "ATTACHMENT_NOT_FOUND") from exc
    except json.JSONDecodeError as exc:
      raise AttachmentError("Attachment metadata is corrupt.", "ATTACHMENT_CORRUPT") from exc
    return AttachmentRef.from_dict(data)

  def _atomic_write_bytes(self, path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    try:
      tmp_path.write_bytes(data)
      tmp_path.replace(path)
    except OSError as exc:
      raise AttachmentError("Unable to persist attachment.", "ATTACHMENT_WRITE_FAILED") from exc
    finally:
      tmp_path.unlink(missing_ok=True)

  def _atomic_write_text(self, path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    try:
      tmp_path.write_text(text, encoding="utf-8")
      tmp_path.replace(path)
    except OSError as exc:
      raise AttachmentError("Unable to persist attachment metadata.", "ATTACHMENT_WRITE_FAILED") from exc
    finally:
      tmp_path.unlink(missing_ok=True)

  def _is_image(self, mime_type: str) -> bool:
    return mime_type.startswith("image/")

  def _normalize_image(
    self,
    data: bytes,
    mime_type: str,
    spec: ImageVariantSpec,
  ) -> bytes | None:
    """Return normalized image bytes if Pillow is available, else None."""
    if not self._is_image(mime_type):
      return None
    if not _has_pillow():
      return None
    try:
      import PIL.Image
      source = PIL.Image.open(io.BytesIO(data))
      source = source.convert("RGB") if source.mode not in ("RGB", "RGBA", "L") else source
      if spec.grayscale:
        source = source.convert("L")
      source.thumbnail(spec.max_size, PIL.Image.Resampling.LANCZOS)
      fmt = spec.fmt.upper() if spec.fmt.upper() in ("PNG", "JPEG", "WEBP") else "PNG"
      out = io.BytesIO()
      source.save(out, format=fmt)
      return out.getvalue()
    except Exception:
      # Normalization is best-effort; return None to fall back to original.
      return None

  def upload(
    self,
    data: bytes,
    *,
    name: str | None = None,
    mime_type: str | None = None,
    _batch_totals: tuple[int, int] | None = None,
  ) -> AttachmentRef:
    """Validate and durably commit one attachment.

    ``_batch_totals`` is an internal hook for ``upload_many`` to enforce batch
    limits without recomputing running totals.
    """
    if not isinstance(data, (bytes, bytearray)):
      raise AttachmentError("Attachment data must be bytes.", "INVALID_ATTACHMENT_DATA")
    size = len(data)
    if size == 0:
      raise AttachmentError("Attachment is empty.", "EMPTY_ATTACHMENT")

    filename = normalize_filename(name)
    resolved_mime = mime_type or guess_mime_type(filename)
    total_count, total_bytes = _batch_totals or (1, size)
    self.limits.check(
      resolved_mime,
      size,
      total_count=total_count,
      total_bytes=total_bytes,
    )

    attachment_id = content_id(data)
    object_path = self._object_path(attachment_id)
    meta_path = self._meta_path(attachment_id)

    if not object_path.exists():
      self._atomic_write_bytes(object_path, bytes(data))

    ref = AttachmentRef(
      attachment_id=attachment_id,
      mime_type=resolved_mime,
      size=size,
      name=filename,
    )

    if not meta_path.exists():
      self._atomic_write_text(meta_path, json.dumps(ref.to_dict(), ensure_ascii=False))

    return ref

  def upload_many(self, items: list[tuple[bytes, str | None, str | None]]) -> list[AttachmentRef]:
    """Validate and commit a batch of attachments atomically (metadata-only)."""
    total_count = len(items)
    total_bytes = sum(len(data) for data, _, _ in items if isinstance(data, (bytes, bytearray)))
    self.limits.check_batch(total_count, total_bytes)

    refs: list[AttachmentRef] = []
    for data, name, mime_type in items:
      ref = self.upload(data, name=name, mime_type=mime_type, _batch_totals=(total_count, total_bytes))
      refs.append(ref)
    return refs

  def list(self) -> list[AttachmentRef]:
    """Return metadata for every stored attachment."""
    refs: list[AttachmentRef] = []
    if not self.meta_dir.exists():
      return refs
    for path in self.meta_dir.iterdir():
      if path.suffix != ".json":
        continue
      try:
        refs.append(AttachmentRef.from_dict(json.loads(path.read_text(encoding="utf-8"))))
      except Exception:
        continue
    return refs

  def get(self, attachment_id: str) -> tuple[AttachmentRef, bytes]:
    """Read one attachment and verify its bytes match the reference id."""
    ref = self._load_meta(attachment_id)
    path = self._object_path(attachment_id)
    try:
      data = path.read_bytes()
    except FileNotFoundError as exc:
      raise AttachmentError("Attachment object is missing.", "ATTACHMENT_NOT_FOUND") from exc
    if len(data) != ref.size:
      raise AttachmentError("Attachment size does not match reference.", "ATTACHMENT_CORRUPT")
    if content_id(data) != attachment_id:
      raise AttachmentError("Attachment digest does not match reference.", "ATTACHMENT_CORRUPT")
    return ref, data

  def get_meta(self, attachment_id: str) -> AttachmentRef:
    """Return only the metadata for an attachment."""
    return self._load_meta(attachment_id)

  def get_variant(
    self,
    attachment_id: str,
    spec: ImageVariantSpec | None = None,
  ) -> tuple[AttachmentRef, bytes]:
    """Return a request-image variant, creating it on first access.

    Falls back to the original bytes if Pillow is unavailable or normalization
    fails. The variant is cached under ``variants/``.
    """
    spec = spec or ImageVariantSpec()
    ref, data = self.get(attachment_id)
    normalized = self._normalize_image(data, ref.mime_type, spec)
    if normalized is None:
      return ref, data

    variant_path = self._variant_path(attachment_id, spec)
    if not variant_path.exists():
      self._atomic_write_bytes(variant_path, normalized)
    else:
      normalized = variant_path.read_bytes()

    variant_ref = AttachmentRef(
      attachment_id=attachment_id,
      mime_type=guess_mime_type(str(variant_path)),
      size=len(normalized),
      name=ref.name,
    )
    return variant_ref, normalized

  def get_thumbnail(
    self,
    attachment_id: str,
    size: tuple[int, int] = (256, 256),
  ) -> tuple[AttachmentRef, bytes]:
    """Convenience accessor for a thumbnail variant."""
    return self.get_variant(attachment_id, ImageVariantSpec(max_size=size, grayscale=False))

  def get_grayscale(
    self,
    attachment_id: str,
    size: tuple[int, int] = (512, 512),
  ) -> tuple[AttachmentRef, bytes]:
    """Convenience accessor for a grayscale variant."""
    return self.get_variant(attachment_id, ImageVariantSpec(max_size=size, grayscale=True))

  def delete(self, attachment_id: str) -> bool:
    """Remove an attachment's metadata and object if no other reference exists.

    Returns ``True`` when the metadata file existed and was removed.
    """
    meta_path = self._meta_path(attachment_id)
    object_path = self._object_path(attachment_id)
    removed = False
    try:
      meta_path.unlink()
      removed = True
    except FileNotFoundError:
      pass
    try:
      object_path.unlink()
    except FileNotFoundError:
      pass
    if self.variants_dir.exists():
      digest, prefix = _sha256_prefix(attachment_id)
      variant_dir = self.variants_dir / prefix
      if variant_dir.exists():
        for path in variant_dir.iterdir():
          if path.name.startswith(digest):
            try:
              path.unlink()
            except FileNotFoundError:
              pass
    return removed

  def object_path(self, attachment_id: str) -> Path:
    """Absolute host path for a stored attachment, or raise if invalid."""
    return self._object_path(attachment_id)
