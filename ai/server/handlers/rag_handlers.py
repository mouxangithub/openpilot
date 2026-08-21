"""API handlers — rag."""

from ai.server.handlers._api_common import *  # noqa: F403

async def api_rag(request: web.Request) -> web.Response:
  config = _read_ai_config()
  embed_cfg = load_embedding_config(_PARAMS, config)
  if request.method == "GET":
    if request.query.get("job") or request.query.get("operation") == "job_status":
      from ai.tools.rag_jobs import job_poll_view

      return _json_response(job_poll_view())
    q = request.query.get("q", "")
    if q:
      return _json_response(await search_documents(_PARAMS, q, embed_config=embed_cfg))
    compact = request.query.get("compact") in ("1", "true", "yes")
    return _json_response(list_documents(_PARAMS, compact=compact))
  try:
    body = await request.json()
  except json.JSONDecodeError:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  op = body.get("operation", "upsert")
  if op == "remove":
    return _json_response(remove_document(_PARAMS, str(body.get("doc_id", ""))))
  if op in ("reindex", "wiki_ingest"):
    from ai.tools.rag_jobs import job_status, start_rag_job

    if body.get("background", True):
      if op == "wiki_ingest":
        return _json_response(
          await start_rag_job(
            _PARAMS,
            embed_cfg,
            operation="wiki_ingest",
            wiki_options={
              "force": bool(body.get("force")),
              "all_registered": bool(body.get("all_registered")),
              "max_files_per_repo": int(body.get("max_files_per_repo", 0) or 0),
            },
            chain_reindex=bool(body.get("chain_reindex", True)),
          )
        )
      return _json_response(
        await start_rag_job(_PARAMS, embed_cfg, operation="reindex")
      )

    return _json_response(
      {"ok": False, "error": "请使用后台任务模式（background: true）", "job": job_status()},
      status=409,
    )
  return _json_response(await upsert_document(
    _PARAMS,
    title=str(body.get("title", "")),
    text=str(body.get("text", "")),
    tags=body.get("tags"),
    doc_id=body.get("doc_id"),
    embed_config=embed_cfg,
    reindex=body.get("reindex", True),
  ))
