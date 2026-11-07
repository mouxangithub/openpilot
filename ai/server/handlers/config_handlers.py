"""API handlers — config."""

from dataclasses import replace

from ai.server.handlers._api_common import *  # noqa: F403


def _body_account_id(body: dict[str, Any] | None) -> str:
  if not body:
    return ""
  return str(body.get("accountId") or body.get("account_id") or "").strip()


def _has_inline_hub_credentials(body: dict[str, Any] | None) -> bool:
  if not body:
    return False
  provider = str(body.get("provider") or "").strip()
  key = str(body.get("apiKey") or body.get("api_key") or "").strip()
  return bool(provider and key and not key.startswith("•"))


def _ensure_probe_model(config: AIConfig) -> AIConfig:
  if (config.model or "").strip():
    return config
  model = AI_DEFAULT_MODELS.get(config.provider) or ""
  if not model:
    catalog = AI_PROVIDER_MODEL_CATALOG.get(config.provider) or []
    model = catalog[0] if catalog else ""
  if not model:
    model = "gpt-4o-mini"
  return replace(config, model=model)


def _resolve_hub_account_config(
  saved: AIConfig,
  body: dict[str, Any] | None,
) -> tuple[AIConfig | None, str]:
  """Resolve model-hub test/fetch config; fall back to inline credentials if account id is stale."""
  account_id = _body_account_id(body)
  if account_id:
    cfg = account_config_by_id(_PARAMS, account_id)
    if cfg:
      return _ensure_probe_model(cfg), account_id
    if _has_inline_hub_credentials(body):
      return _ensure_probe_model(merge_config_from_body(saved, body)), ""
    return None, account_id
  if body:
    return _ensure_probe_model(merge_config_from_body(saved, body)), ""
  return _ensure_probe_model(saved), ""


async def api_bootstrap(request: web.Request) -> web.Response:
  """Single round-trip bootstrap: status + config + providers (faster page load)."""
  try:
    lite = request.query.get("lite", "1") in ("1", "true", "yes")
    reader = _get_state_reader()
    state = reader.update(timeout=0)
    from ai.server.bootstrap_payload import build_bootstrap_payload
    from ai.server.thread_pools import io_executor

    loop = asyncio.get_running_loop()
    payload = await loop.run_in_executor(
      io_executor(),
      lambda: build_bootstrap_payload(_PARAMS, state=state, lite=lite),
    )
    return _json_response(payload)
  except Exception as e:
    cloudlog.error(f"aid: api_bootstrap error: {e}")
    return _json_response({"ok": False, "error": str(e)}, status=500)

async def api_status(request: web.Request) -> web.Response:
  try:
    state = _get_state_reader().update(timeout=0)
    config = _read_ai_config()
  except Exception as e:
    return _json_response({"ok": False, "error": str(e)}, status=500)
  return _json_response({
    "ok": True,
    "driving": state.is_driving,
    "state": state.to_dict(),
    "ai": {
      "configured": config.is_configured,
      "provider": config.provider,
      "model": config.model,
    },
  })

async def api_providers(request: web.Request) -> web.Response:
  return _json_response({
    "ok": True,
    "providers": AI_PROVIDERS,
    "providerLabels": AI_PROVIDER_LABELS,
    "defaults": AI_DEFAULT_MODELS,
    "modelCatalog": AI_PROVIDER_MODEL_CATALOG,
    "embeddingProviders": AI_EMBEDDING_PROVIDERS,
    "embeddingProviderLabels": AI_EMBEDDING_PROVIDER_LABELS,
    "embeddingModelCatalog": AI_EMBEDDING_MODEL_CATALOG,
    "embeddingSameModeCatalog": AI_SAME_MODE_EMBEDDING_MODELS,
    "embeddingDefaults": DEFAULT_EMBEDDING_MODELS,
    "rules": {k: {"category": v.category.value, "description": v.description}
              for k, v in ACTION_RULES.items()},
  })

async def api_get_config(request: web.Request) -> web.Response:
  from ai.common.context_config import compaction_settings
  from ai.common.evolution_config import evolution_settings
  from ai.common.rag_config import rag_settings
  from ai.core.llm.model_accounts import load_model_hub, route_context_window
  from ai.infra.timezone import read_ai_timezone_name

  config = _read_ai_config()
  embed_cfg = load_embedding_config(_PARAMS, config)
  hub = load_model_hub(_PARAMS)
  primary_route = hub.get("primary") if isinstance(hub.get("primary"), dict) else {}
  route_cw = 0
  try:
    route_cw = int(primary_route.get("contextWindow") or 0)
  except (TypeError, ValueError):
    route_cw = 0
  ctx = compaction_settings(model=config.model, context_window=route_cw)
  evo = evolution_settings()
  rag = rag_settings()
  return _json_response({
    "ok": True,
    "config": {
      "provider": config.provider,
      "model": config.model,
      "apiKey": config.api_key,
      "baseUrl": config.base_url,
      "modelFallbacks": fallbacks_for_api(_PARAMS, config),
      "modelHub": hub_for_api(_PARAMS, mask_keys=False),
      "systemPrompt": config.system_prompt,
      "temperature": config.temperature,
      "topP": config.top_p,
      "maxTokens": config.max_tokens,
      "thinkingEnabled": config.thinking_enabled,
      "thinkingKeep": config.thinking_keep,
      "timezone": read_ai_timezone_name(_PARAMS),
      "configured": config.is_configured,
      "configureError": config.configuration_error,
      "embeddingProvider": embed_cfg.provider,
      "embeddingModel": embed_cfg.model,
      "embeddingConfigured": embed_cfg.is_configured,
      "contextWindow": ctx.get("contextWindow"),
      "compactionEnabled": ctx.get("enabled"),
      "compactAfterTurns": ctx.get("compactAfterTurns"),
      "keepRecentTurns": ctx.get("keepRecentTurns"),
      "reserveTokens": ctx.get("reserveTokens"),
      "compactionTokenTrigger": ctx.get("tokenTrigger"),
      "compactThresholdTokens": ctx.get("compactThresholdTokens"),
      "evolutionEnabled": evo.get("enabled"),
      "evolutionAutoPropose": evo.get("autoPropose"),
      "evolutionAutoWorkspace": evo.get("autoWorkspace"),
      "evolutionAutoMemory": evo.get("autoMemory"),
      "evolutionLlmReflect": evo.get("llmReflect"),
      "evolutionToolDesc": evo.get("toolDescEvolution"),
      "skillsDisclosureMax": evo.get("skillsDisclosureMax"),
      "evolutionCandidates": evo.get("evolutionCandidates"),
      "evolutionGepaEnabled": evo.get("gepaEnabled"),
      "evolutionGepaIterations": evo.get("gepaIterations"),
      "evolutionEvalCases": evo.get("evalCases"),
      "evolutionUseDspy": evo.get("useDspy"),
      "ragSearchLimit": rag.get("ragSearchLimit"),
      "ragMaxDocs": rag.get("ragMaxDocs"),
      "ragMaxChunks": rag.get("ragMaxChunks"),
      "wikiMaxFilesPerRepo": rag.get("wikiMaxFilesPerRepo"),
    },
  })

async def api_post_config(request: web.Request) -> web.Response:
  state = _get_state_reader().update(timeout=0)
  allowed, reason = is_action_allowed("write_ai_config", state, admin=is_admin_mode(_PARAMS))
  if not allowed:
    return _json_response({"ok": False, "error": reason}, status=403)

  try:
    body = await request.json()
  except json.JSONDecodeError:
    return _json_response({"ok": False, "error": "Invalid JSON body."}, status=400)

  def _put(key: str, value: Any) -> None:
    if value is None:
      return
    if isinstance(value, bool):
      write_param_bool(_PARAMS, key, value)
    else:
      write_param(_PARAMS, key, str(value))

  embedding_routes_changed = False
  try:
    _put("ai_provider", body.get("provider"))
    _put("ai_model", body.get("model"))
    api_key = body.get("apiKey", "")
    if api_key and not str(api_key).startswith("•"):
      _put("ai_api_key", str(api_key).strip())
    _put("ai_base_url", body.get("baseUrl"))
    _put("ai_system_prompt", body.get("systemPrompt"))
    _put("ai_temperature", body.get("temperature"))
    _put("ai_top_p", body.get("topP"))
    _put("ai_max_tokens", body.get("maxTokens"))
    _put("ai_context_window", body.get("contextWindow"))
    _put("ai_compaction_enabled", body.get("compactionEnabled"))
    _put("ai_compact_after_turns", body.get("compactAfterTurns"))
    _put("ai_keep_recent_turns", body.get("keepRecentTurns"))
    _put("ai_reserve_tokens", body.get("reserveTokens"))
    _put("ai_compaction_token_trigger", body.get("compactionTokenTrigger"))
    _put("ai_evolution_enabled", body.get("evolutionEnabled"))
    _put("ai_evolution_auto_propose", body.get("evolutionAutoPropose"))
    _put("ai_evolution_auto_workspace", body.get("evolutionAutoWorkspace"))
    _put("ai_evolution_auto_memory", body.get("evolutionAutoMemory"))
    _put("ai_evolution_llm_reflect", body.get("evolutionLlmReflect"))
    _put("ai_evolution_tool_desc", body.get("evolutionToolDesc"))
    _put("ai_skills_disclosure_max", body.get("skillsDisclosureMax"))
    _put("ai_evolution_candidates", body.get("evolutionCandidates"))
    _put("ai_evolution_gepa_enabled", body.get("evolutionGepaEnabled"))
    _put("ai_evolution_gepa_iterations", body.get("evolutionGepaIterations"))
    _put("ai_evolution_eval_cases", body.get("evolutionEvalCases"))
    _put("ai_evolution_use_dspy", body.get("evolutionUseDspy"))
    _put("ai_rag_search_limit", body.get("ragSearchLimit"))
    _put("ai_rag_max_docs", body.get("ragMaxDocs"))
    _put("ai_rag_max_chunks", body.get("ragMaxChunks"))
    _put("ai_wiki_max_files_per_repo", body.get("wikiMaxFilesPerRepo"))
    _put("ai_thinking_enabled", body.get("thinkingEnabled"))
    _put("ai_thinking_keep", body.get("thinkingKeep"))
    tz = body.get("timezone")
    if tz is not None and str(tz).strip():
      _put("ai_timezone", str(tz).strip())
    embedding_routes_changed = False
    if "modelHub" in body and isinstance(body.get("modelHub"), dict):
      hub_result = save_model_hub(_PARAMS, body["modelHub"])
      embedding_routes_changed = bool(hub_result.get("_embeddingPrimaryChanged"))
    elif "modelFallbacks" in body:
      existing = load_fallback_entries(_PARAMS)
      incoming = body.get("modelFallbacks") or []
      merged: list[dict[str, Any]] = []
      for i, row in enumerate(incoming):
        if not isinstance(row, dict):
          continue
        item = dict(row)
        api_key = str(item.get("apiKey") or item.get("api_key") or "").strip()
        if api_key.startswith("•") and i < len(existing):
          item["apiKey"] = existing[i].get("apiKey") or existing[i].get("api_key") or ""
        merged.append(item)
      save_fallback_entries(_PARAMS, merged)
  except Exception as e:
    cloudlog.error(f"aid: api_post_config failed: {e}")
    return _json_response({"ok": False, "error": format_persist_error(e)}, status=500)

  if embedding_routes_changed:
    try:
      from ai.tools.rag_store import reindex_all
      from ai.tools.memory_vectors import index_memory_notes

      await reindex_all(_PARAMS)
      await index_memory_notes(_PARAMS)
    except Exception as e:
      cloudlog.warning(f"aid: embedding reindex after hub save failed: {e}")

  config = _read_ai_config()
  try:
    from ai.server.bootstrap_payload import invalidate_bootstrap_cache
    invalidate_bootstrap_cache()
    await broadcast_config(_PARAMS)
  except Exception as e:
    cloudlog.warning(f"aid: broadcast_config failed: {e}")
  return _json_response({
    "ok": True,
    "configured": config.is_configured,
    "configureError": config.configuration_error,
    "modelHub": hub_for_api(_PARAMS, mask_keys=False),
  })

async def api_models(request: web.Request) -> web.Response:
  try:
    saved = _read_ai_config()
    body = None
    if request.method == "POST":
      try:
        body = await request.json()
      except json.JSONDecodeError:
        return _json_response({"ok": False, "error": "Invalid JSON body."}, status=400)
    config, account_id = _resolve_hub_account_config(saved, body)
    if config is None:
      return _json_response({"ok": False, "error": "账户不存在，请先保存账户或重新填写 API 密钥"}, status=404)
    result = await list_models(config)
    models = result.get("models") or []
    if account_id and result.get("ok") and models:
      ids = [str(m.get("id") if isinstance(m, dict) else m) for m in models]
      ids = [m for m in ids if m]
      if ids:
        update_account_models(_PARAMS, account_id, ids)
    payload: dict[str, Any] = {
      "ok": bool(result.get("ok")),
      "error": result.get("error"),
      "models": models,
      "configured": config.is_configured,
      "configureError": config.configuration_error,
      "source": result.get("source"),
    }
    if account_id:
      payload["modelHub"] = hub_for_api(_PARAMS, mask_keys=False)
    return _json_response(payload)
  except Exception as e:
    cloudlog.error(f"aid: api_models error: {e}")
    return _json_response({"ok": False, "error": f"Internal error: {e}", "models": []}, status=500)

async def api_test_connection(request: web.Request) -> web.Response:
  try:
    saved = _read_ai_config()
    body = None
    if request.method == "POST":
      try:
        body = await request.json()
      except json.JSONDecodeError:
        return _json_response({"ok": False, "error": "Invalid JSON body."}, status=400)
    config, account_id = _resolve_hub_account_config(saved, body)
    if config is None:
      return _json_response({"ok": False, "error": "账户不存在，请先保存账户或重新填写 API 密钥"}, status=404)
    if not config.api_key:
      return _json_response({
        "ok": False,
        "error": "请填写 API 密钥",
        "configured": False,
        "configureError": "API key is required",
      })
    result = await test_connection(config)
    return _json_response({
      "ok": bool(result.get("ok")),
      "error": result.get("error"),
      "model_available": result.get("model_available"),
      "models_count": result.get("models_count"),
      "message": result.get("message"),
      "configured": True,
    })
  except Exception as e:
    cloudlog.error(f"aid: api_test_connection error: {e}")
    return _json_response({"ok": False, "error": f"Internal error: {e}"}, status=500)

async def api_model_hub_fetch(request: web.Request) -> web.Response:
  """Fetch models for a provider account and optionally cache on the account."""
  try:
    body = await request.json()
  except json.JSONDecodeError:
    body = {}
  saved = read_ai_config()
  config, account_id = _resolve_hub_account_config(saved, body)
  if config is None:
    return _json_response({"ok": False, "error": "账户不存在，请先保存账户或重新填写 API 密钥"}, status=404)
  result = await list_models(config)
  models = result.get("models") or []
  if account_id and result.get("ok") and models:
    ids = [str(m.get("id") if isinstance(m, dict) else m) for m in models]
    ids = [m for m in ids if m]
    if ids:
      update_account_models(_PARAMS, account_id, ids)
  return _json_response({
    "ok": bool(result.get("ok")),
    "error": result.get("error"),
    "models": models,
    "source": result.get("source"),
    "modelHub": hub_for_api(_PARAMS, mask_keys=False),
  })

async def api_model_hub_test(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except json.JSONDecodeError:
    body = {}
  saved = read_ai_config()
  config, _account_id = _resolve_hub_account_config(saved, body)
  if config is None:
    return _json_response({"ok": False, "error": "账户不存在，请先保存账户或重新填写 API 密钥"}, status=404)
  if not config.api_key:
    return _json_response({"ok": False, "error": "请填写 API 密钥", "configured": False})
  result = await test_connection(config)
  return _json_response({
    "ok": bool(result.get("ok")),
    "error": result.get("error"),
    "configured": True,
    "models_count": result.get("models_count"),
    "message": result.get("message"),
  })

async def api_onboarding_profile(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except json.JSONDecodeError:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  profile = body.get("vehicle_profile")
  if not isinstance(profile, dict):
    return _json_response({"ok": False, "error": "vehicle_profile must be an object"}, status=400)
  result = update_vehicle_profile(_PARAMS, profile)
  goals = body.get("goals")
  if isinstance(goals, list) and goals:
    skill_map = {
      "tuning": "sp-tuning",
      "engage": "engage-troubleshooting",
      "adaptation": "vehicle-adaptation",
      "secoc": "secoc-toyota",
      "routes": "route-diagnostics",
    }
    enabled = set(load_enabled_skill_ids(_PARAMS))
    for g in goals:
      sid = skill_map.get(str(g).strip().lower())
      if sid:
        enabled.add(sid)
    save_enabled_skill_ids(_PARAMS, sorted(enabled))
    result["enabled_skills"] = sorted(enabled)
  return _json_response(result)

async def api_onboarding_complete(request: web.Request) -> web.Response:
  try:
    write_param_bool(_PARAMS, "ai_first_run_done", True)
    config = _read_ai_config()
    return _json_response({
      "ok": True,
      "configured": config.is_configured,
      "configureError": config.configuration_error,
    })
  except Exception as e:
    return _json_response({"ok": False, "error": str(e)}, status=500)
