"""API handlers — chat."""

from ai.server.handlers._api_common import *  # noqa: F403

async def _parse_chat_body(request: web.Request) -> tuple[dict[str, Any] | None, AIConfig | None, web.Response | None]:
  config = _read_ai_config()
  if not config.is_configured:
    return None, None, _json_response({
      "ok": False,
      "error": config.configuration_error or "AI not configured. Set provider, model, and API key first.",
    }, status=400)

  try:
    body = await request.json()
  except json.JSONDecodeError:
    return None, None, _json_response({"ok": False, "error": "Invalid JSON body."}, status=400)

  raw_messages = body.get("messages", [])
  if not isinstance(raw_messages, list) or not raw_messages:
    return None, None, _json_response({"ok": False, "error": "messages must be a non-empty list."}, status=400)

  # Owner slash commands: /调手感 → workflow + consumer mode
  try:
    from ai.tools.consumer_wizards import resolve_wizard_by_slash
    last = raw_messages[-1] if raw_messages else {}
    if last.get("role") == "user":
      content = last.get("content", "")
      text = content if isinstance(content, str) else str(content)
      wiz = resolve_wizard_by_slash(text)
      if wiz:
        body.setdefault("consumerMode", True)
        body.setdefault("workflow", wiz.get("workflow_id"))
        if text.strip() in (wiz.get("slash") or []) or len(text.strip().split()) <= 1:
          last["content"] = wiz.get("starter_prompt") or text
  except Exception:
    pass

  return body, config, None

def _prepare_chat_run(body: dict[str, Any]) -> dict[str, Any]:
  tools_enabled = bool(body.get("tools", True))
  tool_prefs = body.get("toolPrefs") or {}
  max_tool_rounds = _resolve_max_tool_rounds(body.get("maxToolRounds"))
  drive_state = _get_state_reader().update(timeout=0)
  try:
    from ai.system.host_env import is_pc_dev
    pc_dev = is_pc_dev()
  except Exception:
    pc_dev = os.name == "nt" or not os.path.isfile("/TICI")

  route = resolve_agent_route(
    body,
    driving=drive_state.is_driving,
    pc_dev=pc_dev,
    params=_PARAMS,
  )
  route_dict = route.to_dict()
  if route.workflow_id and not body.get("workflow"):
    body["workflow"] = route.workflow_id

  from ai.tools.toolsets import resolve_toolset
  toolset_id = resolve_toolset(
    drive_state.is_driving,
    agent_id=route.agent_id,
    explicit=str(body.get("toolset") or body.get("toolsetId") or "").strip(),
  )

  tools = _filter_tools(
    tools_enabled,
    tool_prefs,
    driving=drive_state.is_driving,
    toolset_id=toolset_id,
  ) if tools_enabled else None
  agent = get_agent(route.agent_id)
  if agent and tools:
    tools = filter_tools_for_agent(tools, agent)

  from ai.tools.deferred_loading import apply_deferred_filter, session_key as defer_session_key
  if tools:
    sk = defer_session_key(
      str(body.get("sessionId") or body.get("session_id") or ""),
      str(body.get("jobId") or body.get("_job_id") or ""),
    )
    tools = apply_deferred_filter(tools, sk, _PARAMS)

  orchestration_plan = None
  if route.agent_id == orchestrator_id() and route.reason == "default":
    plan = detect_orchestration_plan(
      body,
      driving=drive_state.is_driving,
      pc_dev=pc_dev,
      params=_PARAMS,
    )
    if plan:
      orchestration_plan = [p.to_dict() for p in plan]

  return {
    "tools": tools,
    "max_tool_rounds": max_tool_rounds,
    "route": route_dict,
    "orchestration_plan": orchestration_plan,
    "toolset": toolset_id,
  }

def _chat_tools_for_body(body: dict[str, Any]) -> tuple[list[dict[str, Any]] | None, int]:
  prep = _prepare_chat_run(body)
  return prep["tools"], prep["max_tool_rounds"]

async def api_chat(request: web.Request) -> web.Response:
  try:
    body, config, err = await _parse_chat_body(request)
    if err is not None:
      return err
    assert body is not None and config is not None

    prep = _prepare_chat_run(body)
    run_body = {**body, "_config": config, "_agent_route": prep["route"]}
    if prep.get("orchestration_plan"):
      run_body["_orchestration_plan"] = prep["orchestration_plan"]

    async def stream_response():
      response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={"Content-Type": "text/event-stream; charset=utf-8"},
      )
      await response.prepare(request)

      async def emit(event: dict[str, Any]) -> None:
        await response.write(_sse(event))

      try:
        await run_chat_with_agents(
          run_body,
          _PARAMS,
          emit,
          get_state_reader=_get_state_reader,
          get_tool_handlers=_get_tool_handlers,
          tools=prep["tools"],
          max_tool_rounds=prep["max_tool_rounds"],
        )
      except ChatCancelled:
        pass
      await response.write_eof()
      return response

    return await stream_response()
  except Exception as e:
    cloudlog.error(f"aid: api_chat error: {e}")
    return _json_response({"ok": False, "error": f"Internal error: {e}"}, status=500)

async def api_chat_jobs(request: web.Request) -> web.Response:
  """POST: start background job. GET ?sessionId=: list active jobs."""
  if request.method == "GET":
    session_id = str(request.query.get("sessionId", "") or "").strip()
    jobs = list_active_jobs(session_id or None)
    from ai.core.chat.command_queue import list_queued
    return _json_response({"ok": True, "jobs": jobs, "queue": list_queued(session_id or None)})

  try:
    body, config, err = await _parse_chat_body(request)
    if err is not None:
      return err
    assert body is not None and config is not None

    session_id = str(body.get("sessionId", "") or "").strip()
    prep = _prepare_chat_run(body)
    body = {
      **body,
      "_agent_route": prep["route"],
      **({"_orchestration_plan": prep["orchestration_plan"]} if prep.get("orchestration_plan") else {}),
    }
    queue_mode = str(body.get("queueMode") or body.get("queue_mode") or "steer").strip()
    body["queueMode"] = queue_mode
    drive_state = _get_state_reader().update(timeout=0)

    async def _start(b: dict[str, Any]) -> str:
      return await start_chat_job(
        session_id,
        b,
        _PARAMS,
        get_state_reader=_get_state_reader,
        get_tool_handlers=_get_tool_handlers,
        tools=prep["tools"],
        max_tool_rounds=prep["max_tool_rounds"],
        config=config,
      )

    submit = await submit_chat_request(
      session_id,
      body,
      driving=drive_state.is_driving,
      queue_mode=queue_mode,
      start_fn=_start,
      cancel_session_fn=cancel_jobs_for_session,
    )
    job_id = submit.get("jobId")
    wait = str(request.query.get("wait", "") or body.get("wait", "")).lower() in ("1", "true", "yes")
    timeout_ms = int(request.query.get("timeoutMs") or body.get("timeoutMs") or 60000)
    result: dict[str, Any] = {
      "ok": True,
      "jobId": job_id,
      "sessionId": session_id,
      "runId": job_id,
      "queueMode": submit.get("queueMode"),
      "queued": submit.get("queued", False),
      "queuePosition": submit.get("queuePosition"),
      "action": submit.get("action"),
    }
    if wait and job_id:
      waited = await wait_for_job(job_id, timeout_ms=timeout_ms)
      if waited:
        result["job"] = waited
        result["status"] = waited.get("status")
    return _json_response(result)
  except Exception as e:
    cloudlog.error(f"aid: api_chat_jobs error: {e}")
    return _json_response({"ok": False, "error": f"Internal error: {e}"}, status=500)

async def api_chat_job_detail(request: web.Request) -> web.Response:
  job_id = request.match_info.get("job_id", "")
  if request.method == "DELETE":
    ok = await cancel_job(job_id)
    if not ok:
      return _json_response({"ok": False, "error": "Job not found"}, status=404)
    return _json_response({"ok": True, "cancelled": True})

  since = int(request.query.get("since", "0") or "0")
  job = get_job(job_id, since=since)
  if not job:
    return _json_response({"ok": False, "error": "Job not found"}, status=404)

  wait = str(request.query.get("wait", "")).lower() in ("1", "true", "yes")
  if wait and job.get("status") == "running":
    timeout_ms = int(request.query.get("timeoutMs", "60000") or "60000")
    waited = await wait_for_job(job_id, timeout_ms=timeout_ms)
    if waited:
      job = waited
  return _json_response(job)
