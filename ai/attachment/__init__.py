"""Attachment package for op助手.

Ports the durable attachment concepts from ``@deepseek-ai/dsh-attachment`` to
Python with a local, dependency-light backend.
"""

from ai.attachment.context import (
  AttachmentContextPart,
  attachment_context_prompt,
  build_attachment_context,
)
from ai.attachment.extract import ExtractedContent, extract_text
from ai.attachment.models import (
  IMAGE_MEDIA_TYPES,
  TEXT_MEDIA_PREFIXES,
  AttachmentRef,
  content_id,
  guess_mime_type,
  is_text_mime,
  normalize_filename,
)
from ai.attachment.store import AttachmentError, AttachmentLimits, AttachmentStore

__all__ = [
  "AttachmentContextPart",
  "AttachmentError",
  "AttachmentLimits",
  "AttachmentRef",
  "AttachmentStore",
  "ExtractedContent",
  "IMAGE_MEDIA_TYPES",
  "TEXT_MEDIA_PREFIXES",
  "attachment_context_prompt",
  "build_attachment_context",
  "content_id",
  "extract_text",
  "guess_mime_type",
  "is_text_mime",
  "normalize_filename",
]
