"""Provider accounts, model pool, and chat routing (ClawPanel-style model hub)."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from openpilot.common.params import Params

from ai.core.llm.client import AIConfig, load_config_from_params
from ai.common.storage import read_param, write_param
from ai.core.llm.model_router import FALLBACKS_PARAM, load_fallback_entries, save_fallback_entries

HUB_PARAM = "ai_model_hub"
OPTIONAL_BASE_URL_PROVIDERS = frozenset({"qwen", "minimax", "mimo", "bigmodel"})


def _new_account_id() -> str:
  return f"acc_{uuid.uuid4().hex[:10]}"


def _mask_key(key: str) -> str:
  if not key:
    return ""
  if len(key) <= 8:
    return "••••"
  return f"••••{key[-4:]}"


def _provider_label(provider: str) -> str:
  labels = {
    "opencode-zen": "OpenCode Zen",
    "opencode-go": "OpenCode Go",
    "deepseek": "DeepSeek",
    "bigmodel": "智谱 BigModel",
    "qwen": "通义千问",
    "mimo": "小米 MiMo",
    "minimax": "MiniMax",
    "openrouter": "OpenRouter",
    "openai": "OpenAI",
    "kimi": "Kimi",
    "siliconflow": "硅基流动",
    "custom": "Custom",
  }
  return labels.get(provider, provider)


def _sanitize_account(item: dict[str, Any], *, existing: dict[str, Any] | None = None) -> dict[str, Any] | None:
  if not isinstance(item, dict):
    return None
  provider = str(item.get("provider") or "").strip()
  if not provider:
    return None
  acc_id = str(item.get("id") or (existing or {}).get("id") or _new_account_id()).strip()
  label = str(item.get("label") or (existing or {}).get("label") or _provider_label(provider)).strip()[:64]
  api_key = str(item.get("apiKey") or item.get("api_key") or "").strip()
  if api_key.startswith("•") and existing:
    api_key = str(existing.get("apiKey") or existing.get("api_key") or "")
  base_url = str(item.get("baseUrl") or item.get("base_url") or "").strip()
  models_in = item.get("models")
  models: list[str] = []
  if isinstance(models_in, list):
    models = [str(m).strip() for m in models_in if str(m).strip()]
  elif existing and isinstance(existing.get("models"), list):
    models = [str(m).strip() for m in existing.get("models") if str(m).strip()]
  emb_models_in = item.get("embeddingModels")
  embedding_models: list[str] = []
  if isinstance(emb_models_in, list):
    embedding_models = [str(m).strip() for m in emb_models_in if str(m).strip()]
  elif existing and isinstance(existing.get("embeddingModels"), list):
    embedding_models = [str(m).strip() for m in existing.get("embeddingModels") if str(m).strip()]
  out: dict[str, Any] = {
    "id": acc_id,
    "provider": provider,
    "label": label,
    "apiKey": api_key,
    "baseUrl": base_url,
    "enabled": item.get("enabled", (existing or {}).get("enabled", True)) is not False,
    "models": models,
    "embeddingModels": embedding_models,
  }
  fetched = item.get("modelsFetchedAt")
  if fetched is None and existing:
    fetched = existing.get("modelsFetchedAt")
  if fetched is not None:
    try:
      out["modelsFetchedAt"] = int(fetched)
    except (TypeError, ValueError):
      pass
  return out


def _empty_hub() -> dict[str, Any]:
  return {
    "version": 2,
    "accounts": [],
    "primary": None,
    "fallbacks": [],
    "embeddingPrimary": None,
    "embeddingFallbacks": [],
  }


def _hub_from_legacy(params: Params) -> dict[str, Any]:
  base = load_config_from_params(params)
  acc_id = "acc_default"
  account = {
    "id": acc_id,
    "provider": base.provider,
    "label": _provider_label(base.provider),
    "apiKey": base.api_key,
    "baseUrl": base.base_url,
    "enabled": True,
    "models": [base.model] if base.model else [],
  }
  accounts = [account]
  fallbacks: list[dict[str, Any]] = []
  account_index = {(base.provider, base.api_key, base.base_url): acc_id}

  def _get_or_create_account(provider: str, api_key: str, base_url: str) -> str:
    key = (provider, api_key, base_url)
    if key in account_index:
      return account_index[key]
    new_id = _new_account_id()
    accounts.append({
      "id": new_id,
      "provider": provider,
      "label": _provider_label(provider),
      "apiKey": api_key,
      "baseUrl": base_url,
      "enabled": True,
      "models": [],
    })
    account_index[key] = new_id
    return new_id

  for fb in load_fallback_entries(params):
    fb_provider = str(fb.get("provider") or base.provider).strip()
    fb_key = str(fb.get("apiKey") or fb.get("api_key") or base.api_key).strip()
    fb_url = str(fb.get("baseUrl") or fb.get("base_url") or base.base_url).strip()
    fb_model = str(fb.get("model") or "").strip()
    if not fb_model:
      continue
    aid = _get_or_create_account(fb_provider, fb_key, fb_url)
    for acc in accounts:
      if acc["id"] == aid and fb_model not in acc["models"]:
        acc["models"].append(fb_model)
    row: dict[str, Any] = {"accountId": aid, "model": fb_model}
    label = str(fb.get("label") or "").strip()
    if label:
      row["label"] = label[:64]
    fallbacks.append(row)

  hub = {
    "version": 2,
    "accounts": accounts,
    "primary": {"accountId": acc_id, "model": base.model},
    "fallbacks": fallbacks,
    "embeddingPrimary": None,
    "embeddingFallbacks": [],
  }
  _ensure_embedding_routes(hub, params)
  return hub


def _read_embedding_legacy(params: Params) -> tuple[str, str, str, str, str]:
  from ai.core.llm.client import _param_to_str
  mode = _param_to_str(read_param(params, "ai_embedding_mode"), "same").lower()
  provider = _param_to_str(read_param(params, "ai_embedding_provider"), "siliconflow")
  model = _param_to_str(read_param(params, "ai_embedding_model"))
  api_key = _param_to_str(read_param(params, "ai_embedding_api_key"))
  base_url = _param_to_str(read_param(params, "ai_embedding_base_url"))
  return mode, provider, model, api_key, base_url


def _ensure_embedding_routes(hub: dict[str, Any], params: Params | None) -> None:
  """Fill embeddingPrimary/Fallbacks from legacy params when hub has none."""
  if hub.get("embeddingPrimary"):
    return
  if not params:
    return
  from ai.core.llm.embedding import DEFAULT_EMBEDDING_MODELS

  mode, provider, model, api_key, base_url = _read_embedding_legacy(params)
  amap = _account_map(hub)
  chat_primary = hub.get("primary") if isinstance(hub.get("primary"), dict) else None
  chat_acc = amap.get(str(chat_primary.get("accountId") or "")) if chat_primary else None

  if mode == "same" and chat_acc:
    acc_id = str(chat_acc.get("id") or "")
    emb_model = model or DEFAULT_EMBEDDING_MODELS.get(str(chat_acc.get("provider") or ""), "")
    if acc_id and emb_model:
      hub["embeddingPrimary"] = {"accountId": acc_id, "model": emb_model}
    return

  if not provider:
    return
  acc_id = ""
  for acc in hub.get("accounts") or []:
    if str(acc.get("provider") or "") != provider:
      continue
    acc_key = str(acc.get("apiKey") or "")
    acc_url = str(acc.get("baseUrl") or "")
    if api_key and acc_key and acc_key != api_key:
      continue
    if base_url and acc_url and acc_url != base_url:
      continue
    acc_id = str(acc.get("id") or "")
    break
  if not acc_id:
    acc_id = _new_account_id()
    hub.setdefault("accounts", []).append({
      "id": acc_id,
      "provider": provider,
      "label": _provider_label(provider),
      "apiKey": api_key,
      "baseUrl": base_url,
      "enabled": True,
      "models": [],
      "embeddingModels": [],
    })
  emb_model = model or DEFAULT_EMBEDDING_MODELS.get(provider, DEFAULT_EMBEDDING_MODELS["openrouter"])
  if emb_model:
    hub["embeddingPrimary"] = {"accountId": acc_id, "model": emb_model}
    for acc in hub.get("accounts") or []:
      if acc.get("id") == acc_id:
        em = acc.setdefault("embeddingModels", [])
        if emb_model not in em:
          em.append(emb_model)


def load_model_hub(params: Params | None = None) -> dict[str, Any]:
  params = params or Params()
  raw = read_param(params, HUB_PARAM)
  if not raw:
    return _hub_from_legacy(params)
  try:
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    data = json.loads(raw)
  except Exception:
    return _hub_from_legacy(params)
  if not isinstance(data, dict):
    return _hub_from_legacy(params)
  accounts_in = data.get("accounts")
  if not isinstance(accounts_in, list) or not accounts_in:
    return _hub_from_legacy(params)
  accounts = []
  for item in accounts_in:
    acc = _sanitize_account(item)
    if acc:
      accounts.append(acc)
  if not accounts:
    return _hub_from_legacy(params)
  primary_in = data.get("primary") if isinstance(data.get("primary"), dict) else None
  primary = _sanitize_route(primary_in) if primary_in else None
  fallbacks = []
  for item in data.get("fallbacks") or []:
    row = _sanitize_route(item)
    if row:
      fallbacks.append(row)
  emb_primary_in = data.get("embeddingPrimary") if isinstance(data.get("embeddingPrimary"), dict) else None
  embedding_primary = _sanitize_route(emb_primary_in) if emb_primary_in else None
  embedding_fallbacks = []
  for item in data.get("embeddingFallbacks") or []:
    row = _sanitize_route(item)
    if row:
      embedding_fallbacks.append(row)
  hub = {
    "version": max(2, int(data.get("version") or 1)),
    "accounts": accounts,
    "primary": primary,
    "fallbacks": fallbacks,
    "embeddingPrimary": embedding_primary,
    "embeddingFallbacks": embedding_fallbacks,
  }
  _ensure_embedding_routes(hub, params)
  return hub


def hub_for_api(params: Params | None = None, *, mask_keys: bool = True) -> dict[str, Any]:
  hub = load_model_hub(params)
  accounts = []
  for acc in hub.get("accounts") or []:
    row = dict(acc)
    if mask_keys and row.get("apiKey"):
      row["apiKey"] = _mask_key(str(row["apiKey"]))
    accounts.append(row)
  return {
    "version": hub.get("version", 2),
    "accounts": accounts,
    "primary": hub.get("primary"),
    "fallbacks": hub.get("fallbacks") or [],
    "embeddingPrimary": hub.get("embeddingPrimary"),
    "embeddingFallbacks": hub.get("embeddingFallbacks") or [],
  }


def _account_map(hub: dict[str, Any]) -> dict[str, dict[str, Any]]:
  return {str(a.get("id")): a for a in hub.get("accounts") or [] if a.get("id")}


def account_to_config(account: dict[str, Any], model: str, *, base: AIConfig | None = None) -> AIConfig:
  base = base or AIConfig(provider="opencode-zen", model="", api_key="")
  return AIConfig(
    provider=str(account.get("provider") or base.provider),
    model=str(model or "").strip(),
    api_key=str(account.get("apiKey") or account.get("api_key") or ""),
    base_url=str(account.get("baseUrl") or account.get("base_url") or ""),
    system_prompt=base.system_prompt,
    temperature=base.temperature,
    top_p=base.top_p,
    max_tokens=base.max_tokens,
    thinking_enabled=base.thinking_enabled,
    thinking_keep=base.thinking_keep,
  )


def route_to_config(
  account: dict[str, Any],
  route: dict[str, Any],
  *,
  base: AIConfig | None = None,
) -> AIConfig:
  base = base or AIConfig(provider="opencode-zen", model="", api_key="")
  model = str(route.get("model") or "").strip()
  cfg = account_to_config(account, model, base=base)
  try:
    mt = int(route.get("maxTokens") or 0)
    if mt > 0:
      cfg.max_tokens = mt
  except (TypeError, ValueError):
    pass
  for attr, key in (("temperature", "temperature"), ("top_p", "topP")):
    raw = route.get(key)
    if raw is None or str(raw).strip() == "":
      continue
    try:
      setattr(cfg, attr, float(raw))
    except (TypeError, ValueError):
      pass
  if "thinkingEnabled" in route or "thinking_enabled" in route:
    raw_think = route.get("thinkingEnabled", route.get("thinking_enabled"))
    cfg.thinking_enabled = raw_think is not False and str(raw_think).lower() not in ("0", "false", "no", "off")
  return cfg


def _sanitize_route(item: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any] | None:
  if not isinstance(item, dict):
    return None
  prev = existing if isinstance(existing, dict) else {}
  aid = str(item.get("accountId") or item.get("account_id") or prev.get("accountId") or "").strip()
  model = str(item.get("model") or prev.get("model") or "").strip()
  if not aid or not model:
    return None
  row: dict[str, Any] = {"accountId": aid, "model": model}
  label = str(item.get("label") or prev.get("label") or "").strip()
  if label:
    row["label"] = label[:64]
  try:
    row["contextWindow"] = max(0, int(item.get("contextWindow", prev.get("contextWindow", 0)) or 0))
  except (TypeError, ValueError):
    row["contextWindow"] = 0
  for key in ("maxTokens",):
    raw = item.get(key, prev.get(key))
    if raw is not None and str(raw).strip() != "":
      try:
        val = int(raw)
        if val > 0:
          row[key] = val
      except (TypeError, ValueError):
        pass
  for key in ("temperature", "topP"):
    raw = item.get(key, prev.get(key))
    if raw is not None and str(raw).strip() != "":
      try:
        row[key] = float(raw)
      except (TypeError, ValueError):
        pass
  if "thinkingEnabled" in item or "thinking_enabled" in item:
    raw_think = item.get("thinkingEnabled", item.get("thinking_enabled"))
    row["thinkingEnabled"] = raw_think is not False and str(raw_think).lower() not in ("0", "false", "no", "off")
  elif "thinkingEnabled" in prev or "thinking_enabled" in prev:
    raw_think = prev.get("thinkingEnabled", prev.get("thinking_enabled"))
    row["thinkingEnabled"] = raw_think is not False and str(raw_think).lower() not in ("0", "false", "no", "off")
  return row


def route_context_window(route: dict[str, Any] | None, *, model: str = "") -> int:
  from ai.common.context_config import context_window_for_model
  if isinstance(route, dict):
    try:
      override = int(route.get("contextWindow") or 0)
      if override > 0:
        return override
    except (TypeError, ValueError):
      pass
  return context_window_for_model(model)


def resolve_primary_config(params: Params | None = None, base: AIConfig | None = None) -> AIConfig:
  params = params or Params()
  base = base or load_config_from_params(params)
  hub = load_model_hub(params)
  amap = _account_map(hub)
  primary = hub.get("primary") if isinstance(hub.get("primary"), dict) else None
  if primary:
    aid = str(primary.get("accountId") or primary.get("account_id") or "").strip()
    model = str(primary.get("model") or "").strip()
    acc = amap.get(aid)
    if acc and model:
      cfg = route_to_config(acc, primary, base=base)
      if cfg.api_key and cfg.model:
        return cfg
  return base


def resolve_fallback_configs(params: Params | None = None, base: AIConfig | None = None) -> list[AIConfig]:
  params = params or Params()
  base = base or resolve_primary_config(params)
  hub = load_model_hub(params)
  amap = _account_map(hub)
  out: list[AIConfig] = []
  seen: set[tuple[str, str]] = {(base.provider, base.model)}
  for item in hub.get("fallbacks") or []:
    if not isinstance(item, dict):
      continue
    aid = str(item.get("accountId") or item.get("account_id") or "").strip()
    model = str(item.get("model") or "").strip()
    acc = amap.get(aid)
    if not acc or not model:
      continue
    if acc.get("enabled") is False:
      continue
    key = (str(acc.get("provider")), model)
    if key in seen:
      continue
    seen.add(key)
    cfg = route_to_config(acc, item, base=base)
    if not cfg.api_key:
      continue
    if cfg.provider == "custom" and not cfg.base_url:
      continue
    out.append(cfg)
  if out:
    return out
  return _legacy_fallback_configs(params, base)


def _legacy_fallback_configs(params: Params, base: AIConfig) -> list[AIConfig]:
  from ai.core.llm.model_router import _parse_fallbacks
  return _parse_fallbacks(params, base)


def resolve_chat_chain(params: Params | None = None, base: AIConfig | None = None) -> list[AIConfig]:
  params = params or Params()
  primary = resolve_primary_config(params, base)
  return [primary, *resolve_fallback_configs(params, primary)]


def parse_chat_route(raw: dict[str, Any] | None) -> dict[str, str] | None:
  if not isinstance(raw, dict):
    return None
  aid = str(raw.get("accountId") or raw.get("account_id") or "").strip()
  model = str(raw.get("model") or "").strip()
  if not aid or not model:
    return None
  return {"accountId": aid, "model": model}


def resolve_config_from_chat_route(
  params: Params | None,
  route: dict[str, Any],
  *,
  base: AIConfig | None = None,
) -> AIConfig | None:
  parsed = parse_chat_route(route)
  if not parsed:
    return None
  params = params or Params()
  hub = load_model_hub(params)
  amap = _account_map(hub)
  acc = amap.get(parsed["accountId"])
  if not acc or acc.get("enabled") is False:
    return None
  base = base or load_config_from_params(params)
  cfg = route_to_config(acc, parsed, base=base)
  if not cfg.api_key or not cfg.model:
    return None
  return cfg


def resolve_chat_chain_with_route(
  params: Params | None = None,
  base: AIConfig | None = None,
  *,
  chat_route: dict[str, Any] | None = None,
) -> list[AIConfig]:
  chain = resolve_chat_chain(params, base)
  if not chat_route:
    return chain
  cfg = resolve_config_from_chat_route(params, chat_route, base=base)
  if not cfg:
    return chain
  rest = [c for c in chain if (c.provider, c.model) != (cfg.provider, cfg.model)]
  return [cfg, *rest]


def route_to_embedding_config(account: dict[str, Any], route: dict[str, Any]) -> "EmbeddingConfig":
  from ai.core.llm.embedding import EmbeddingConfig

  model = str(route.get("model") or "").strip()
  return EmbeddingConfig(
    provider=str(account.get("provider") or ""),
    model=model,
    api_key=str(account.get("apiKey") or account.get("api_key") or ""),
    base_url=str(account.get("baseUrl") or account.get("base_url") or ""),
  )


def resolve_embedding_primary_config(params: Params | None = None) -> "EmbeddingConfig":
  from ai.core.llm.embedding import DEFAULT_EMBEDDING_MODELS, EmbeddingConfig

  params = params or Params()
  hub = load_model_hub(params)
  amap = _account_map(hub)
  emb_primary = hub.get("embeddingPrimary") if isinstance(hub.get("embeddingPrimary"), dict) else None
  if emb_primary:
    aid = str(emb_primary.get("accountId") or "").strip()
    acc = amap.get(aid)
    if acc and acc.get("enabled") is not False:
      cfg = route_to_embedding_config(acc, emb_primary)
      if not cfg.model:
        cfg.model = DEFAULT_EMBEDDING_MODELS.get(cfg.provider, DEFAULT_EMBEDDING_MODELS["openrouter"])
      if cfg.is_configured:
        return cfg
  return EmbeddingConfig(provider="", model="", api_key="")


def resolve_embedding_fallback_configs(params: Params | None = None) -> list["EmbeddingConfig"]:
  from ai.core.llm.embedding import EmbeddingConfig

  params = params or Params()
  hub = load_model_hub(params)
  amap = _account_map(hub)
  primary = resolve_embedding_primary_config(params)
  out: list[EmbeddingConfig] = []
  seen: set[tuple[str, str]] = {(primary.provider, primary.model)} if primary.model else set()
  for item in hub.get("embeddingFallbacks") or []:
    if not isinstance(item, dict):
      continue
    aid = str(item.get("accountId") or "").strip()
    model = str(item.get("model") or "").strip()
    acc = amap.get(aid)
    if not acc or not model or acc.get("enabled") is False:
      continue
    key = (str(acc.get("provider")), model)
    if key in seen:
      continue
    seen.add(key)
    cfg = route_to_embedding_config(acc, item)
    if not cfg.api_key:
      continue
    if cfg.provider == "custom" and not cfg.base_url:
      continue
    out.append(cfg)
  return out


def resolve_embedding_chain(params: Params | None = None) -> list["EmbeddingConfig"]:
  params = params or Params()
  primary = resolve_embedding_primary_config(params)
  if not primary.is_configured:
    return []
  return [primary, *resolve_embedding_fallback_configs(params)]


def embedding_primary_signature(hub: dict[str, Any]) -> str:
  """Signature of the active indexing model (primary route only)."""
  emb_p = hub.get("embeddingPrimary")
  if not isinstance(emb_p, dict):
    return ""
  return f"{emb_p.get('accountId')}:{emb_p.get('model')}"


def embedding_hub_signature(hub: dict[str, Any]) -> str:
  """Full embedding route chain signature (primary + fallbacks)."""
  parts = []
  emb_p = hub.get("embeddingPrimary")
  if isinstance(emb_p, dict):
    parts.append(f"p:{emb_p.get('accountId')}:{emb_p.get('model')}")
  for item in hub.get("embeddingFallbacks") or []:
    if isinstance(item, dict):
      parts.append(f"f:{item.get('accountId')}:{item.get('model')}")
  return "|".join(parts)


def _sync_legacy_params(params: Params, hub: dict[str, Any]) -> None:
  amap = _account_map(hub)
  primary = hub.get("primary") if isinstance(hub.get("primary"), dict) else None
  if primary:
    aid = str(primary.get("accountId") or "").strip()
    model = str(primary.get("model") or "").strip()
    acc = amap.get(aid)
    if acc and model:
      write_param(params, "ai_provider", str(acc.get("provider") or ""))
      write_param(params, "ai_model", model)
      if acc.get("apiKey"):
        write_param(params, "ai_api_key", str(acc.get("apiKey")))
      write_param(params, "ai_base_url", str(acc.get("baseUrl") or ""))

  legacy_fallbacks = []
  for item in hub.get("fallbacks") or []:
    if not isinstance(item, dict):
      continue
    aid = str(item.get("accountId") or "").strip()
    model = str(item.get("model") or "").strip()
    acc = amap.get(aid)
    if not acc or not model:
      continue
    row: dict[str, Any] = {
      "provider": str(acc.get("provider") or ""),
      "model": model,
    }
    label = str(item.get("label") or "").strip()
    if label:
      row["label"] = label
    if acc.get("apiKey"):
      row["api_key"] = str(acc.get("apiKey"))
    if acc.get("baseUrl"):
      row["base_url"] = str(acc.get("baseUrl"))
    legacy_fallbacks.append(row)
  save_fallback_entries(params, legacy_fallbacks)

  from ai.core.llm.embedding import DEFAULT_EMBEDDING_MODELS

  emb_primary = hub.get("embeddingPrimary") if isinstance(hub.get("embeddingPrimary"), dict) else None
  if emb_primary:
    aid = str(emb_primary.get("accountId") or "").strip()
    model = str(emb_primary.get("model") or "").strip()
    acc = amap.get(aid)
    if acc and model:
      write_param(params, "ai_embedding_mode", "separate")
      write_param(params, "ai_embedding_provider", str(acc.get("provider") or ""))
      write_param(params, "ai_embedding_model", model)
      if acc.get("apiKey"):
        write_param(params, "ai_embedding_api_key", str(acc.get("apiKey")))
      write_param(params, "ai_embedding_base_url", str(acc.get("baseUrl") or ""))
  else:
    write_param(params, "ai_embedding_mode", "same")
    if primary and amap.get(str(primary.get("accountId") or "")):
      chat_acc = amap[str(primary.get("accountId"))]
      emb_model = DEFAULT_EMBEDDING_MODELS.get(str(chat_acc.get("provider") or ""), "")
      if emb_model:
        write_param(params, "ai_embedding_model", emb_model)


def save_model_hub(params: Params, incoming: dict[str, Any]) -> dict[str, Any]:
  existing = load_model_hub(params)
  existing_map = _account_map(existing)
  accounts = []
  for item in incoming.get("accounts") or []:
    if not isinstance(item, dict):
      continue
    acc_id = str(item.get("id") or "").strip()
    prev = existing_map.get(acc_id) if acc_id else None
    acc = _sanitize_account(item, existing=prev)
    if acc:
      accounts.append(acc)
  if not accounts:
    raise ValueError("至少需要一个服务商账户")

  primary_in = incoming.get("primary") if isinstance(incoming.get("primary"), dict) else None
  prev_primary = existing.get("primary") if isinstance(existing.get("primary"), dict) else None
  primary = _sanitize_route(primary_in, existing=prev_primary) if primary_in else None

  fallbacks = []
  prev_fallbacks = existing.get("fallbacks") or []
  prev_by_key = {
    f"{f.get('accountId')}::{f.get('model')}": f
    for f in prev_fallbacks
    if isinstance(f, dict) and f.get("accountId") and f.get("model")
  }
  for item in incoming.get("fallbacks") or []:
    if not isinstance(item, dict):
      continue
    aid = str(item.get("accountId") or item.get("account_id") or "").strip()
    model = str(item.get("model") or "").strip()
    prev = prev_by_key.get(f"{aid}::{model}") if aid and model else None
    row = _sanitize_route(item, existing=prev)
    if row:
      fallbacks.append(row)

  emb_primary_in = incoming.get("embeddingPrimary") if isinstance(incoming.get("embeddingPrimary"), dict) else None
  prev_emb_primary = existing.get("embeddingPrimary") if isinstance(existing.get("embeddingPrimary"), dict) else None
  embedding_primary = _sanitize_route(emb_primary_in, existing=prev_emb_primary) if emb_primary_in else None

  embedding_fallbacks = []
  prev_emb_fallbacks = existing.get("embeddingFallbacks") or []
  prev_emb_by_key = {
    f"{f.get('accountId')}::{f.get('model')}": f
    for f in prev_emb_fallbacks
    if isinstance(f, dict) and f.get("accountId") and f.get("model")
  }
  for item in incoming.get("embeddingFallbacks") or []:
    if not isinstance(item, dict):
      continue
    aid = str(item.get("accountId") or item.get("account_id") or "").strip()
    model = str(item.get("model") or "").strip()
    prev = prev_emb_by_key.get(f"{aid}::{model}") if aid and model else None
    row = _sanitize_route(item, existing=prev)
    if row:
      embedding_fallbacks.append(row)

  old_sig = embedding_primary_signature(existing)
  hub = {
    "version": 2,
    "accounts": accounts,
    "primary": primary,
    "fallbacks": fallbacks,
    "embeddingPrimary": embedding_primary,
    "embeddingFallbacks": embedding_fallbacks,
  }
  new_sig = embedding_primary_signature(hub)
  write_param(params, HUB_PARAM, json.dumps(hub, ensure_ascii=False))
  _sync_legacy_params(params, hub)
  result = hub_for_api(params, mask_keys=False)
  if old_sig != new_sig:
    result["_embeddingPrimaryChanged"] = True
  return result


def update_account_models(
  params: Params,
  account_id: str,
  models: list[str],
  *,
  kind: str = "chat",
) -> dict[str, Any]:
  hub = load_model_hub(params)
  amap = _account_map(hub)
  acc = amap.get(account_id)
  if not acc:
    raise ValueError("account not found")
  cleaned = [str(m).strip() for m in models if str(m).strip()]
  if kind == "embedding":
    acc["embeddingModels"] = cleaned
  else:
    acc["models"] = cleaned
  acc["modelsFetchedAt"] = int(time.time())
  write_param(params, HUB_PARAM, json.dumps(hub, ensure_ascii=False))
  return hub_for_api(params, mask_keys=False)


def account_config_by_id(params: Params, account_id: str) -> AIConfig | None:
  hub = load_model_hub(params)
  acc = _account_map(hub).get(account_id)
  if not acc:
    return None
  model = ""
  primary = hub.get("primary") if isinstance(hub.get("primary"), dict) else None
  if primary and str(primary.get("accountId")) == account_id:
    model = str(primary.get("model") or "")
  if not model and acc.get("models"):
    model = str(acc["models"][0])
  return account_to_config(acc, model)


def provider_needs_base_url(provider: str) -> bool:
  return provider == "custom"


def provider_optional_base_url(provider: str) -> bool:
  return provider in OPTIONAL_BASE_URL_PROVIDERS
