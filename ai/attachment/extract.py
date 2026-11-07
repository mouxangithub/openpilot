"""Lightweight text/content extraction helpers for attachments.

These helpers are dependency-optional: when ``Pillow`` or ``PyPDF2`` are not
installed they fall back to a safe placeholder so tests and offline hosts
still work.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any

from ai.attachment.models import AttachmentRef, is_text_mime


@dataclass
class ExtractedContent:
  """Result of extracting human-readable content from an attachment."""

  ref: AttachmentRef
  text: str | None = None
  dimensions: dict[str, int] | None = None
  pages: int | None = None
  error: str | None = None

  def to_dict(self) -> dict[str, Any]:
    result: dict[str, Any] = {"attachmentId": self.ref.attachment_id}
    if self.text is not None:
      result["text"] = self.text
    if self.dimensions is not None:
      result["dimensions"] = self.dimensions
    if self.pages is not None:
      result["pages"] = self.pages
    if self.error is not None:
      result["error"] = self.error
    return result


def _image_info(data: bytes) -> tuple[int, int] | None:
  try:
    from PIL import Image
    with Image.open(BytesIO(data)) as img:  # type: ignore[misc]
      return img.width, img.height
  except Exception:
    return None


def extract_text(ref: AttachmentRef, data: bytes, *, max_chars: int = 8000) -> ExtractedContent:
  """Extract text-like content from an attachment, truncating to ``max_chars``."""
  if is_text_mime(ref.mime_type):
    try:
      text = data.decode("utf-8", errors="replace")
      truncated = len(text) > max_chars
      return ExtractedContent(
        ref=ref,
        text=text[:max_chars] + ("\n... (truncated)" if truncated else ""),
      )
    except Exception as exc:
      return ExtractedContent(ref=ref, error=f"Could not decode text: {exc}")

  if ref.mime_type.startswith("image/"):
    dims = _image_info(data)
    desc = f"Image ({ref.mime_type})"
    if dims:
      desc += f", {dims[0]}x{dims[1]}"
    return ExtractedContent(ref=ref, text=desc, dimensions={"width": dims[0], "height": dims[1]} if dims else None)

  if ref.mime_type == "application/pdf":
    pages, text = _extract_pdf(data, max_chars=max_chars)
    return ExtractedContent(ref=ref, text=text, pages=pages)

  return ExtractedContent(ref=ref, error=f"Extraction not implemented for {ref.mime_type}")


def _extract_pdf(data: bytes, *, max_chars: int) -> tuple[int | None, str | None]:
  try:
    from PyPDF2 import PdfReader
    from io import BytesIO
    reader = PdfReader(BytesIO(data))
    pages = len(reader.pages)
    chunks: list[str] = []
    remaining = max_chars
    for page in reader.pages:
      if remaining <= 0:
        break
      try:
        text = page.extract_text() or ""
      except Exception:
        text = ""
      chunks.append(text[:remaining])
      remaining -= len(text)
    full = "\n".join(chunks)
    return pages, full[:max_chars] + ("\n... (truncated)" if len(full) > max_chars else "")
  except Exception as exc:
    return None, f"PDF extraction unavailable: {exc}"
