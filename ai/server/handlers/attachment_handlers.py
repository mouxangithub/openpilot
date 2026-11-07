"""HTTP handlers for the attachment API."""

from __future__ import annotations

from typing import Any

from aiohttp import web

from ai.attachment.store import AttachmentError, AttachmentStore
from ai.server.handlers._api_common import _json_response


def _attachment_store() -> AttachmentStore:
  from ai.system.paths import workspace_path

  base = workspace_path("ai_attachments")
  base.mkdir(parents=True, exist_ok=True)
  return AttachmentStore(base)


async def api_attachments_list(request: web.Request) -> web.Response:
  try:
    store = _attachment_store()
    refs = [ref.to_dict() for ref in store.list()]
    return _json_response({"ok": True, "attachments": refs})
  except Exception as e:
    return _json_response({"ok": False, "error": str(e)}, status=500)


async def api_attachments_upload(request: web.Request) -> web.Response:
  try:
    store = _attachment_store()
    reader = await request.multipart()
    uploaded: list[dict[str, Any]] = []
    async for part in reader:
      if part.name != "file":
        continue
      filename = part.filename
      mime_type = part.headers.get("Content-Type") or None
      data = await part.read(decode=False)
      if not isinstance(data, (bytes, bytearray)):
        data = data.encode("utf-8") if isinstance(data, str) else bytes(data)
      ref = store.upload(data, name=filename, mime_type=mime_type)
      uploaded.append(ref.to_dict())

    if not uploaded:
      return _json_response({"ok": False, "error": "No file field named 'file' found."}, status=400)

    return _json_response({"ok": True, "attachments": uploaded})
  except AttachmentError as e:
    return _json_response({"ok": False, "error": e.message, "code": e.code}, status=400)
  except Exception as e:
    return _json_response({"ok": False, "error": str(e)}, status=500)


async def api_attachments_get(request: web.Request) -> web.Response:
  attachment_id = request.match_info.get("attachment_id", "")
  try:
    store = _attachment_store()
    ref, data = store.get(attachment_id)
    download = request.query.get("download", "").lower() in ("1", "true", "yes")
    if download:
      resp = web.Response(body=data, content_type=ref.mime_type)
      disp = f"attachment; filename={ref.name or attachment_id}"
      resp.headers["Content-Disposition"] = disp
      return resp
    return _json_response({"ok": True, "attachment": ref.to_dict()})
  except AttachmentError as e:
    return _json_response({"ok": False, "error": e.message, "code": e.code}, status=404)
  except Exception as e:
    return _json_response({"ok": False, "error": str(e)}, status=500)


async def api_attachments_delete(request: web.Request) -> web.Response:
  attachment_id = request.match_info.get("attachment_id", "")
  try:
    store = _attachment_store()
    removed = store.delete(attachment_id)
    if not removed:
      return _json_response({"ok": False, "error": "Attachment not found."}, status=404)
    return _json_response({"ok": True, "deleted": True})
  except AttachmentError as e:
    return _json_response({"ok": False, "error": e.message, "code": e.code}, status=400)
  except Exception as e:
    return _json_response({"ok": False, "error": str(e)}, status=500)
