"""Build LLM context prompts from stored attachments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai.attachment.extract import extract_text
from ai.attachment.models import AttachmentRef
from ai.attachment.store import AttachmentStore


@dataclass
class AttachmentContextPart:
  """One attachment rendered as a prompt part."""

  ref: AttachmentRef
  text: str

  def to_dict(self) -> dict[str, Any]:
    return {
      "type": "attachment",
      "attachmentId": self.ref.attachment_id,
      "mimeType": self.ref.mime_type,
      "name": self.ref.name,
      "text": self.text,
    }


def build_attachment_context(
  store: AttachmentStore,
  attachment_ids: list[str],
  *,
  max_chars_per_attachment: int = 4000,
) -> list[AttachmentContextPart]:
  """Resolve attachment ids to prompt-ready text snippets."""
  parts: list[AttachmentContextPart] = []
  for attachment_id in attachment_ids:
    try:
      ref, data = store.get(attachment_id)
    except Exception as exc:
      parts.append(AttachmentContextPart(
        ref=AttachmentRef(attachment_id=attachment_id, mime_type="unknown", size=0),
        text=f"[Attachment {attachment_id} unavailable: {exc}]",
      ))
      continue

    extracted = extract_text(ref, data, max_chars=max_chars_per_attachment)
    snippet = extracted.text or extracted.error or "[No extractable text]"
    parts.append(AttachmentContextPart(ref=ref, text=snippet))
  return parts


def attachment_context_prompt(
  store: AttachmentStore,
  attachment_ids: list[str],
  *,
  max_chars_per_attachment: int = 4000,
) -> str:
  """Return a single text block describing the requested attachments."""
  parts = build_attachment_context(store, attachment_ids, max_chars_per_attachment=max_chars_per_attachment)
  if not parts:
    return ""
  lines: list[str] = ["--- Attachments ---"]
  for part in parts:
    name = part.ref.name or part.ref.attachment_id
    lines.append(f"File: {name} ({part.ref.mime_type}, {part.ref.size} bytes)")
    lines.append(part.text)
    lines.append("")
  return "\n".join(lines).rstrip() + "\n--- End attachments ---"
