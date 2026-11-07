"""API handlers — fork."""

from ai.server.handlers._api_common import *  # noqa: F403

async def api_fork_detect(request: web.Request) -> web.Response:
  try:
    from ai.fork.analyze_fork import analyze_fork_with_ai
    from ai.fork.detect_fork import detect_fork

    root = openpilot_root()
    loop = asyncio.get_running_loop()
    do_analyze = request.query.get("analyze", "0") in ("1", "true", "yes")
    if do_analyze:
      result = await analyze_fork_with_ai(_PARAMS, root, force=request.query.get("force") in ("1", "true"))
      if result.get("ok"):
        result["detect"] = await loop.run_in_executor(None, detect_fork, root)
      return _json_response(result, status=200 if result.get("ok") else 500)
    detected = await loop.run_in_executor(None, detect_fork, root)
    return _json_response(detected)
  except Exception as e:
    cloudlog.error(f"aid: api_fork_detect error: {e}")
    return _json_response({"ok": False, "error": str(e)}, status=500)

async def api_fork_analyze(request: web.Request) -> web.Response:
  try:
    from ai.fork.analyze_fork import analyze_fork_with_ai

    root = openpilot_root()
    try:
      body = await request.json()
    except (json.JSONDecodeError, ValueError, aiohttp.ClientPayloadError):
      body = {}
    force = bool(body.get("force"))
    result = await analyze_fork_with_ai(_PARAMS, root, force=force)
    if result.get("ok") and result.get("analysis"):
      fid = result["analysis"].get("fork_identity") or result.get("identity", {}).get("fork_id")
      if fid:
        write_param(_PARAMS, "ai_fork_id", str(fid))
        write_param(_PARAMS, "ai_fork_profile_applied", datetime.now(timezone.utc).isoformat())
    return _json_response(result, status=200 if result.get("ok") else 500)
  except Exception as e:
    cloudlog.error(f"aid: api_fork_analyze error: {e}")
    return _json_response({"ok": False, "error": str(e)}, status=500)

async def api_fork_sync(request: web.Request) -> web.Response:
  try:
    from ai.fork.fork_sync import generate_fork_drafts, list_fork_drafts

    try:
      body = await request.json()
    except (json.JSONDecodeError, ValueError, aiohttp.ClientPayloadError):
      body = {}
    if not body.get("confirm"):
      return _json_response({
        "ok": True,
        "needs_confirmation": True,
        "hint": "AI 将先阅读 openpilot 项目并分析 fork，再生成技能/文档草稿（需人工审核）。POST confirm=true。",
        "drafts": list_fork_drafts()[:5],
      })
    result = await generate_fork_drafts(
      _PARAMS,
      force_analyze=bool(body.get("force_analyze")),
    )
    if result.get("ok") and result.get("fork_id"):
      write_param(_PARAMS, "ai_fork_id", str(result["fork_id"]))
      write_param(_PARAMS, "ai_fork_profile_applied", datetime.now(timezone.utc).isoformat())
    return _json_response(result, status=200 if result.get("ok") else 500)
  except Exception as e:
    cloudlog.error(f"aid: api_fork_sync error: {e}")
    return _json_response({"ok": False, "error": str(e)}, status=500)

async def api_fork_run_stream(request: web.Request) -> web.Response:
  """SSE stream: scan → analyze → draft with phase/reasoning/content events."""
  try:
    from ai.fork.fork_sync import run_fork_pipeline

    try:
      body = await request.json()
    except (json.JSONDecodeError, ValueError, aiohttp.ClientPayloadError):
      body = {}
    if not body.get("confirm"):
      return _json_response({
        "ok": False,
        "needs_confirmation": True,
        "error": "POST confirm=true to start fork analysis pipeline.",
      }, status=400)

    root = openpilot_root()
    force = bool(body.get("force"))
    skip_draft = bool(body.get("skip_draft"))

    async def stream_response():
      response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={"Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-cache"},
      )
      await response.prepare(request)

      async def emit(event: dict[str, Any]) -> None:
        await response.write(_sse(event))

      result: dict[str, Any] = {"ok": False}
      try:
        result = await run_fork_pipeline(
          _PARAMS,
          root,
          force=force,
          skip_draft=skip_draft,
          emit=emit,
        )
        if result.get("ok") and result.get("fork_id"):
          write_param(_PARAMS, "ai_fork_id", str(result["fork_id"]))
          write_param(_PARAMS, "ai_fork_profile_applied", datetime.now(timezone.utc).isoformat())
        elif result.get("ok") and result.get("analysis"):
          fid = (result.get("analysis") or {}).get("fork_identity") or result.get("identity", {}).get("fork_id")
          if fid:
            write_param(_PARAMS, "ai_fork_id", str(fid))
            write_param(_PARAMS, "ai_fork_profile_applied", datetime.now(timezone.utc).isoformat())
      except Exception as e:
        cloudlog.error(f"aid: api_fork_run_stream pipeline error: {e}")
        await emit({"type": "error", "error": str(e)})
        await emit({"type": "done", "ok": False, "error": str(e)})
      await response.write_eof()
      return response

    return await stream_response()
  except Exception as e:
    cloudlog.error(f"aid: api_fork_run_stream error: {e}")
    return _json_response({"ok": False, "error": str(e)}, status=500)

async def api_integrate_openpilot(request: web.Request) -> web.Response:
  try:
    from ai.system.host_env import is_pc_dev
    from ai.install.integrate_openpilot import integrate

    state = _get_state_reader().update(timeout=0)
    if state.is_driving and not is_pc_dev():
      return _json_response({"ok": False, "error": "行驶中无法集成，请停车后重试。"}, status=403)
    root = openpilot_root()
    result = integrate(root, root / "ai", force_compile=bool(request.query.get("force")))
    return _json_response(result, status=200 if result.get("ok") else 500)
  except Exception as e:
    cloudlog.error(f"aid: api_integrate_openpilot error: {e}")
    return _json_response({"ok": False, "error": str(e)}, status=500)
