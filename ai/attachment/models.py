"""Attachment data model and MIME helpers."""

from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from typing import Any


# Common image types accepted by the harness reference.
IMAGE_MEDIA_TYPES: frozenset[str] = frozenset([
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/gif",
])

# Textual MIME prefixes that can be rendered inline as context.
TEXT_MEDIA_PREFIXES: tuple[str, ...] = (
  "text/",
  "application/json",
  "application/x-python-code",
  "application/javascript",
)


@dataclass(frozen=True)
class AttachmentRef:
  """Durable, serializable reference to one immutable attachment."""

  attachment_id: str
  mime_type: str
  size: int
  name: str | None = None
  width: int | None = None
  height: int | None = None

  def to_dict(self) -> dict[str, Any]:
    result: dict[str, Any] = {
      "attachmentId": self.attachment_id,
      "mimeType": self.mime_type,
      "size": self.size,
    }
    if self.name is not None:
      result["name"] = self.name
    if self.width is not None:
      result["width"] = self.width
    if self.height is not None:
      result["height"] = self.height
    return result

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> AttachmentRef:
    return cls(
      attachment_id=str(data["attachmentId"]),
      mime_type=str(data["mimeType"]),
      size=int(data["size"]),
      name=data.get("name"),
      width=int(data["width"]) if data.get("width") is not None else None,
      height=int(data["height"]) if data.get("height") is not None else None,
    )


def content_id(data: bytes) -> str:
  """Deterministic content-addressed attachment id."""
  return f"sha256:{hashlib.sha256(data).hexdigest()}"


def normalize_filename(value: str | None) -> str | None:
  """Strip path separators and control characters from a display name."""
  if value is None:
    return None
  leaf = value[max(value.rfind("/"), value.rfind("\\")) + 1:]
  clean = "".join(c for c in leaf if 0x20 <= ord(c) <= 0x7E).strip()
  return clean[:255] or None


def guess_mime_type(name: str | None, default: str = "application/octet-stream") -> str:
  """Guess MIME type from filename."""
  if not name:
    return default
  guessed, _ = mimetypes.guess_type(name)
  return guessed or default


def is_text_mime(mime_type: str) -> bool:
  """Whether the MIME type is treated as human-readable text."""
  return any(mime_type.startswith(p) for p in TEXT_MEDIA_PREFIXES)
