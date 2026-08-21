"""Application factory — extracted from aid.py."""

from __future__ import annotations

import asyncio

from aiohttp import web

from openpilot.common.swaglog import cloudlog

from ai.services.cabana.app import register_routes as register_cabana_routes
from ai.core.llm.embedding import load_embedding_config
from ai.server.deps import WEB_DIR, json_response, params, read_ai_config
from ai.server.runtime import scheduler_loop, status_watch_loop
from ai.server.routes import register_routes as register_server_routes
from ai.core.sync.hub import register_sync_routes
from ai.tools.rag_store import reindex_all
from ai.tools.scheduler import ensure_default_scheduler_tasks
from ai.infra.auth.web import ai_auth_middleware

_PARAMS = params()


async def _startup_rag_seed_and_reindex() -> None:
  """Seed built-in RAG off the event loop, then optionally reindex vectors."""
  await asyncio.sleep(45)
  loop = asyncio.get_event_loop()
  try:
    from ai.tools.rag_sync_tools import sync_knowledge_from_docs
    doc_sync = await loop.run_in_executor(
      None, lambda: sync_knowledge_from_docs(_PARAMS, max_files=60)
    )
    if doc_sync.get("indexed"):
      cloudlog.info(f"aid: doc sync indexed={doc_sync.get('indexed')}")
  except Exception as e:
    cloudlog.warning(f"aid: doc sync skipped: {e}")
  try:
    from ai.tools.rag_seed import ensure_builtin_rag_docs
    from ai.tools.rag_extra_seed import ensure_extra_rag_docs
    result = await loop.run_in_executor(None, ensure_builtin_rag_docs, _PARAMS)
    extra = await loop.run_in_executor(None, ensure_extra_rag_docs, _PARAMS)
    if result.get("seeded") or result.get("refreshed") or extra.get("seeded"):
      cloudlog.info(
        f"aid: RAG seed builtin={result.get('seeded')} refreshed={result.get('refreshed')} "
        f"stored={result.get('stored')} extra={extra.get('seeded')} v={extra.get('version')}"
      )
  except Exception as e:
    cloudlog.warning(f"aid: builtin RAG seed skipped: {e}")
  try:
    from ai.fork.wiki_ingest import ingest_wikis_for_current_fork

    wiki = await loop.run_in_executor(
      None,
      lambda: ingest_wikis_for_current_fork(_PARAMS, max_files_per_repo=0, force=False),
    )
    if wiki.get("indexed"):
      cloudlog.info(
        f"aid: community wiki ingest indexed={wiki.get('indexed')} mode={wiki.get('mode')}"
      )
  except Exception as e:
    cloudlog.warning(f"aid: community wiki ingest skipped: {e}")
  try:
    config = read_ai_config()
    embed_cfg = load_embedding_config(_PARAMS, config)
    if not embed_cfg.is_configured:
      return
    from ai.tools.domains.core.rag_vectors import chunk_count, vector_index_meta
    from ai.tools.domains.core.rag_store import _load_docs

    def _warm_only() -> None:
      vector_index_meta()

    if chunk_count() == 0 and len(_load_docs(_PARAMS)) > 0:
      res = await reindex_all(_PARAMS, embed_cfg)
      cloudlog.info(f"aid: RAG auto-reindex indexed={res.get('indexed')}/{res.get('total')}")
    else:
      await loop.run_in_executor(None, _warm_only)
      cloudlog.info(f"aid: RAG vectors present chunks={chunk_count()}, skip auto-reindex")
  except Exception as e:
    cloudlog.warning(f"aid: RAG auto-reindex skipped: {e}")
  try:
    from ai.tools.domains.core.rag_vectors import _meta_path, vector_index_meta

    def _warm_vector_meta() -> None:
      if not _meta_path().is_file():
        vector_index_meta(rebuild=True)
      else:
        vector_index_meta()

    await loop.run_in_executor(None, _warm_vector_meta)
    cloudlog.info("aid: RAG vector meta cache ready")
  except Exception as e:
    cloudlog.warning(f"aid: RAG vector meta warm skipped: {e}")


async def _startup_session_index() -> None:
  try:
    from ai.tools.session_index import rebuild_from_params
    loop = asyncio.get_running_loop()
    res = await loop.run_in_executor(None, rebuild_from_params, _PARAMS)
    cloudlog.info(
      f"aid: session FTS index sessions={res.get('sessions')} messages={res.get('messagesIndexed')}"
    )
  except Exception as e:
    cloudlog.warning(f"aid: session index skipped: {e}")


async def _startup_memory_index() -> None:
  try:
    config = read_ai_config()
    embed_cfg = load_embedding_config(_PARAMS, config)
    if not embed_cfg.is_configured:
      return
    from ai.tools.memory_vectors import index_memory_notes
    res = await index_memory_notes(_PARAMS, embed_cfg)
    cloudlog.info(f"aid: memory vector index indexed={res.get('indexed', 0)}")
  except Exception as e:
    cloudlog.warning(f"aid: memory index skipped: {e}")


async def index(request: web.Request) -> web.Response:
  index_path = WEB_DIR / "index.html"
  if not index_path.is_file():
    cloudlog.error(f"aid: missing web UI at {index_path}")
    return json_response({
      "ok": False,
      "error": (
        "op助手 Web 资源缺失。请在 openpilot 根目录执行: "
        "git submodule update --init ai "
        "或运行 ai/install/install.sh"
      ),
    }, status=503)
  resp = web.FileResponse(index_path)
  resp.headers["Cache-Control"] = "no-cache, must-revalidate"
  return resp


@web.middleware
async def static_dev_cache_middleware(request: web.Request, handler):
  resp = await handler(request)
  path = request.path or ""
  if path.startswith("/static/") and path.rsplit(".", 1)[-1] in ("js", "css", "mjs"):
    resp.headers["Cache-Control"] = "no-cache, must-revalidate"
  return resp


@web.middleware
async def error_middleware(request: web.Request, handler):
  try:
    return await handler(request)
  except web.HTTPRequestEntityTooLarge:
    return json_response({
      "ok": False,
      "error": "请求体过大（对话历史或工具结果过长）。请新建会话，或在设置中开启会话压缩后重试。",
    }, status=413)
  except web.HTTPException:
    raise
  except Exception as e:
    cloudlog.error(f"aid: unhandled {request.method} {request.path}: {e}")
    msg = str(e)
    if "Request Entity Too Large" in msg or "entity too large" in msg.lower():
      return json_response({
        "ok": False,
        "error": "请求体过大（对话历史或工具结果过长）。请新建会话，或在设置中开启会话压缩后重试。",
      }, status=413)
    return json_response({"ok": False, "error": str(e)}, status=500)


def create_app() -> web.Application:
  from ai.server.deps import get_state_reader

  # Chat jobs send full message history + tool_results; default 1MB is too small.
  app = web.Application(
    middlewares=[static_dev_cache_middleware, error_middleware, ai_auth_middleware],
    client_max_size=32 * 1024 * 1024,
  )
  app["params"] = _PARAMS

  async def _on_startup(application: web.Application) -> None:
    application["get_state_reader"] = get_state_reader
    application["scheduler_task"] = asyncio.create_task(scheduler_loop(application))
    application["status_watch_task"] = asyncio.create_task(status_watch_loop(application))
    try:
      from ai.core.wspace.store import ensure_default_workspace_files
      ensure_default_workspace_files()
    except Exception as e:
      cloudlog.warning(f"aid: workspace seed skipped: {e}")
    try:
      ensure_default_scheduler_tasks(_PARAMS)
      application["memory_index_task"] = asyncio.create_task(_startup_memory_index())
      application["session_index_task"] = asyncio.create_task(_startup_session_index())
    except Exception as e:
      cloudlog.warning(f"aid: default scheduler skipped: {e}")
    application["rag_reindex_task"] = asyncio.create_task(_startup_rag_seed_and_reindex())
    try:
      from ai.skills.snapshot import warm_skills_snapshot
      from ai.core.chat.jobs import ensure_stuck_watchdog
      from ai.hooks.builtin import register_builtin_hooks
      register_builtin_hooks()
      loop = asyncio.get_running_loop()
      n = await loop.run_in_executor(None, warm_skills_snapshot, _PARAMS)
      cloudlog.info(f"aid: skills snapshot warmed entries={n}")
      try:
        from ai.tools.file_search import warm_file_index

        file_n = await loop.run_in_executor(None, warm_file_index)
        cloudlog.info(f"aid: composer file index warmed entries={file_n}")
      except Exception as e:
        cloudlog.warning(f"aid: composer file index warm skipped: {e}")
      ensure_stuck_watchdog()
    except Exception as e:
      cloudlog.warning(f"aid: skills snapshot / stuck watchdog skipped: {e}")
    try:
      from ai.services.cabana.app import warm_dbc_catalog

      async def _warm_dbc_catalog() -> None:
        loop = asyncio.get_running_loop()
        n = await loop.run_in_executor(None, warm_dbc_catalog)
        if n:
          cloudlog.info(f"aid: dbc catalog warmed entries={n}")

      application["dbc_warm_task"] = asyncio.create_task(_warm_dbc_catalog())
    except Exception as e:
      cloudlog.warning(f"aid: dbc catalog warm skipped: {e}")

  async def _on_cleanup(application: web.Application) -> None:
    for key in ("scheduler_task", "status_watch_task", "memory_index_task", "session_index_task", "rag_reindex_task", "dbc_warm_task"):
      task = application.get(key)
      if task:
        task.cancel()

  app.on_startup.append(_on_startup)
  app.on_cleanup.append(_on_cleanup)

  register_server_routes(app, json_response=json_response)
  app.router.add_get("/", index)
  app.router.add_static("/static/", path=WEB_DIR, name="static")
  register_cabana_routes(app, WEB_DIR)
  register_sync_routes(app)
  from ai.server.terminal import register_terminal_routes
  register_terminal_routes(app)
  from ai.core.runtime.sidecar_hub import register_sidecar_routes
  register_sidecar_routes(app)
  try:
    from ai.services.tsk.routes import register_tsk_routes
    register_tsk_routes(app)
  except Exception as e:
    cloudlog.warning(f"aid: tsk routes skipped: {e}")
  try:
    from ai.services.panda.routes import register_panda_routes
    register_panda_routes(app)
  except Exception as e:
    cloudlog.warning(f"aid: panda routes skipped: {e}")
  return app
