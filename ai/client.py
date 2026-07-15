"""
OpenAI-compatible chat client used by the AI agent.

Supports OpenCode Zen/Go, DeepSeek, 智谱, 千问, MiMo, MiniMax, OpenRouter, OpenAI, Kimi, and custom endpoints.
Streams content, reasoning_content, tool_calls, and usage.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal

import aiohttp


DEFAULT_ENDPOINTS = {
  "opencode-zen": "https://opencode.ai/zen/v1",
  "opencode-go": "https://opencode.ai/zen/go/v1",
  "deepseek": os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com"),
  "bigmodel": os.environ.get("BIGMODEL_API_BASE", os.environ.get("ZHIPU_API_BASE", "https://open.bigmodel.cn/api/paas/v4")),
  "qwen": os.environ.get("QWEN_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
  "mimo": os.environ.get("MIMO_API_BASE", "https://api.xiaomimimo.com/v1"),
  "minimax": os.environ.get("MINIMAX_API_BASE", "https://api.minimaxi.com/v1"),
  "openrouter": "https://openrouter.ai/api/v1",
  "openai": "https://api.openai.com/v1",
  "kimi": "https://api.moonshot.cn/v1",
  "siliconflow": os.environ.get("SILICONFLOW_API_BASE", "https://api.siliconflow.cn/v1"),
}

REASONING_CONTENT_PROVIDERS = frozenset({"kimi", "minimax", "deepseek", "mimo", "bigmodel"})

ThinkingMode = Literal["user", "omit", "enabled", "disabled"]

# Models that do not accept temperature (or require temperature=1).
THINKING_MODELS = {
  "kimi-k2.7-code",
  "kimi-k2.7-code-highspeed",
  "kimi-k2.6",
  "kimi-k2.5",
  "minimax-m3",
  "minimax-m2",
  "mimo-v2.5",
  "deepseek-v4-pro",
  "deepseek-reasoner",
  "deepseek-r1",
  "qwq",
  "glm-5",
  "glm-4.5",
  "o1",
  "o1-mini",
  "o3",
  "o3-mini",
}


@dataclass
class AIConfig:
  provider: str
  model: str
  api_key: str
  base_url: str = ""
  system_prompt: str = ""
  temperature: float = 0.7
  top_p: float = 1.0
  max_tokens: int = 4096
  thinking_enabled: bool = True
  thinking_keep: str = ""

  @property
  def endpoint(self) -> str:
    if self.provider == "custom":
      return self.base_url.rstrip("/")
    try:
      from ai.common.params import AI_OPTIONAL_BASE_URL_PROVIDERS
      optional = self.provider in AI_OPTIONAL_BASE_URL_PROVIDERS
    except Exception:
      optional = self.provider in ("qwen", "minimax", "mimo", "bigmodel")
    if optional and self.base_url.strip():
      return self.base_url.rstrip("/")
    return DEFAULT_ENDPOINTS.get(self.provider, DEFAULT_ENDPOINTS["opencode-zen"])

  @property
  def is_configured(self) -> bool:
    return self.configuration_error is None

  @property
  def configuration_error(self) -> str | None:
    if not self.api_key:
      return "API key is required"
    if self.provider == "custom" and not self.base_url:
      return "Custom provider requires a Base URL"
    if not self.model:
      return "Model is required"
    return None

  def is_thinking_model(self) -> bool:
    m = (self.model or "").lower()
    return any(t in m for t in THINKING_MODELS)


def _param_to_str(val: Any, default: str = "") -> str:
  if val is None:
    return default
  if isinstance(val, bytes):
    return val.decode()
  return str(val)


def _param_to_float(val: Any, default: float = 0.0) -> float:
  try:
    return float(_param_to_str(val, str(default)))
  except (ValueError, TypeError):
    return default


def _param_to_int(val: Any, default: int = 0) -> int:
  try:
    return int(_param_to_str(val, str(default)))
  except (ValueError, TypeError):
    return default


def _param_to_bool(val: Any, default: bool = False) -> bool:
  if val is None:
    return default
  if isinstance(val, bytes):
    val = val.decode()
  if isinstance(val, bool):
    return val
  return str(val).lower() in ("1", "true", "yes", "on")


def load_config_from_params(params: Any) -> AIConfig:
  try:
    from openpilot.common.params import Params
    if not isinstance(params, Params):
      params = Params()
    provider = _param_to_str(params.get("ai_provider"), "opencode-zen")
    if provider == "zhipu":
      provider = "bigmodel"
    return AIConfig(
      provider=provider,
      model=_param_to_str(params.get("ai_model"), "deepseek-v4-flash"),
      api_key=_param_to_str(params.get("ai_api_key")),
      base_url=_param_to_str(params.get("ai_base_url")),
      system_prompt=_param_to_str(params.get("ai_system_prompt")),
      temperature=_param_to_float(params.get("ai_temperature"), 0.7),
      top_p=_param_to_float(params.get("ai_top_p"), 1.0),
      max_tokens=_param_to_int(params.get("ai_max_tokens"), 4096),
      thinking_enabled=_param_to_bool(params.get("ai_thinking_enabled"), True),
      thinking_keep=_param_to_str(params.get("ai_thinking_keep")),
    )
  except Exception as e:
    import warnings
    warnings.warn(f"load_config_from_params failed: {e}")
    return AIConfig(provider="opencode-zen", model="deepseek-v4-flash", api_key="")


@dataclass
class ChatChunk:
  """A single chunk from a streaming chat completion."""
  content: str = ""
  reasoning_content: str = ""
  tool_calls: list[dict[str, Any]] = field(default_factory=list)
  usage: dict[str, Any] | None = None
  done: bool = False
  error: str = ""


def expand_messages_for_api(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Expand UI chat history into OpenAI-compatible tool message chains.

  The web UI stores tool results on the assistant message as ``tool_results``.
  Providers require assistant(tool_calls) followed by tool(tool_call_id) messages.
  """
  out: list[dict[str, Any]] = []
  for m in messages:
    role = m.get("role")
    if role != "assistant":
      out.append({k: v for k, v in m.items() if k not in ("tool_results",)})
      continue

    tool_calls = m.get("tool_calls") or []
    tool_results = m.get("tool_results") or {}

    assistant: dict[str, Any] = {"role": "assistant"}
    content = m.get("content")
    if content:
      assistant["content"] = content
    elif tool_calls:
      assistant["content"] = None
    else:
      assistant["content"] = ""
    if m.get("reasoning_content"):
      assistant["reasoning_content"] = m["reasoning_content"]

    normalized_tcs: list[dict[str, Any]] = []
    for i, tc in enumerate(tool_calls):
      fn = tc.get("function") or {}
      tid = tc.get("id") or f"{fn.get('name', 'tool')}:{i}"
      normalized_tcs.append({
        "id": tid,
        "type": tc.get("type", "function"),
        "function": {
          "name": fn.get("name", ""),
          "arguments": fn.get("arguments") or "{}",
        },
      })
    if normalized_tcs:
      assistant["tool_calls"] = normalized_tcs
    out.append(assistant)

    result_values = list(tool_results.values())
    for i, tc in enumerate(normalized_tcs):
      tid = tc["id"]
      result = tool_results.get(tid)
      if result is None and i < len(result_values):
        result = result_values[i]
      if isinstance(result, str):
        content_str = result
      else:
        payload = result if result is not None else {"ok": False, "error": "Tool result missing"}
        content_str = json.dumps(payload, ensure_ascii=False, default=str)
      out.append({"role": "tool", "tool_call_id": tid, "content": content_str})
  return out


def _sanitize_messages(config: AIConfig, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Remove provider-specific fields that would cause errors on other providers."""
  out = []
  for m in messages:
    cm = dict(m)
    if "tool_results" in cm:
      del cm["tool_results"]
    # Only some providers accept reasoning_content in multi-turn history.
    if config.provider not in REASONING_CONTENT_PROVIDERS and "reasoning_content" in cm:
      del cm["reasoning_content"]
    out.append(cm)
  return out


def _thinking_type_for_mode(config: AIConfig, thinking_mode: ThinkingMode) -> str | None:
  """Map Cabana/user thinking mode to API thinking.type. None => omit field."""
  if thinking_mode == "omit":
    return None
  if thinking_mode == "enabled":
    return "enabled"
  if thinking_mode == "disabled":
    return "disabled"
  return "enabled" if config.thinking_enabled else "disabled"


def _apply_thinking_payload(payload: dict[str, Any], config: AIConfig, thinking_mode: ThinkingMode) -> None:
  thinking_model = config.is_thinking_model()
  if not thinking_model:
    return
  thinking_type = _thinking_type_for_mode(config, thinking_mode)
  if thinking_type is None:
    return
  if config.provider == "kimi":
    if "kimi-k2.5" in config.model.lower():
      payload["thinking"] = {"type": thinking_type}
    elif "kimi-k2.6" in config.model.lower() or "kimi-k2.7" in config.model.lower():
      payload["thinking"] = {
        "type": thinking_type,
        "keep": config.thinking_keep or None,
      }
    return
  if config.provider in ("deepseek", "mimo"):
    payload["thinking"] = {"type": thinking_type}


def _build_payload(
  config: AIConfig,
  messages: list[dict[str, Any]],
  tools: list[dict[str, Any]] | None,
  temperature: float | None,
  max_tokens: int | None,
  *,
  thinking_mode: ThinkingMode = "user",
) -> dict[str, Any]:
  """Build the request payload, handling thinking-model restrictions."""
  payload: dict[str, Any] = {
    "model": config.model,
    "messages": _sanitize_messages(config, messages),
    "stream": True,
  }

  if tools:
    payload["tools"] = tools
    payload["tool_choice"] = "auto"

  thinking_model = config.is_thinking_model()

  if not thinking_model:
    # Non-thinking models respect the configured temperature/top_p.
    payload["temperature"] = temperature if temperature is not None else config.temperature
    payload["top_p"] = config.top_p
  else:
    # Thinking models do not accept temperature; some accept top_p.
    # For safety we omit temperature entirely.
    pass

  mt = max_tokens if max_tokens is not None else config.max_tokens
  if mt:
    payload["max_tokens"] = mt

  _apply_thinking_payload(payload, config, thinking_mode)

  return payload


def _extract_delta(data: dict[str, Any]) -> ChatChunk:
  """Extract a ChatChunk from a streaming SSE data object."""
  chunk = ChatChunk()
  choices = data.get("choices", [])
  if not choices:
    chunk.usage = data.get("usage")
    return chunk

  choice = choices[0]
  delta = choice.get("delta", {}) or {}

  # Reasoning content (Kimi thinking models).
  if "reasoning_content" in delta:
    chunk.reasoning_content = delta["reasoning_content"] or ""

  # Regular content.
  if "content" in delta:
    chunk.content = delta["content"] or ""

  # Tool calls.
  if "tool_calls" in delta and delta["tool_calls"]:
    chunk.tool_calls = delta["tool_calls"]

  # Usage may appear in the final chunk.
  chunk.usage = choice.get("usage") or data.get("usage")
  return chunk


async def chat_completion(
  config: AIConfig,
  messages: list[dict[str, Any]],
  tools: list[dict[str, Any]] | None = None,
  temperature: float | None = None,
  max_tokens: int | None = None,
  *,
  thinking_mode: ThinkingMode = "user",
  timeout_total: float = 120,
) -> AsyncIterator[ChatChunk]:
  """Stream chat completion chunks from the configured provider."""
  if not config.is_configured:
    yield ChatChunk(
      error=config.configuration_error or "AI is not configured. Please set provider, model, and API key on the AI settings page."
    )
    return

  url = f"{config.endpoint}/chat/completions"
  headers = {
    "Authorization": f"Bearer {config.api_key}",
    "Content-Type": "application/json",
  }
  if config.provider == "mimo":
    headers["api-key"] = config.api_key
  if config.provider == "openrouter":
    headers["HTTP-Referer"] = "https://openpilot.com/"
    headers["X-Title"] = "Openpilot AI Agent"

  payload = _build_payload(config, messages, tools, temperature, max_tokens, thinking_mode=thinking_mode)

  timeout = aiohttp.ClientTimeout(total=timeout_total, connect=15)
  try:
    async with aiohttp.ClientSession(timeout=timeout) as session:
      async with session.post(url, headers=headers, json=payload) as resp:
        if resp.status != 200:
          text = await resp.text()
          yield ChatChunk(error=f"API error {resp.status}: {text[:500]}")
          return

        async for line in resp.content:
          try:
            line = line.decode("utf-8").strip()
          except UnicodeDecodeError:
            continue
          if not line or line == "data: [DONE]":
            continue
          if line.startswith("data: "):
            line = line[6:]
          try:
            data = json.loads(line)
          except json.JSONDecodeError:
            continue
          yield _extract_delta(data)
  except aiohttp.ClientError as e:
    yield ChatChunk(error=f"Network error: {e}")
  except Exception as e:
    yield ChatChunk(error=f"Unexpected error: {e}")


def is_thinking_request_error(error: str) -> bool:
  """True when the provider rejected our thinking payload (retry with another mode)."""
  text = (error or "").lower()
  return "api error 400" in text and "thinking" in text


async def chat_completion_collect(
  config: AIConfig,
  messages: list[dict[str, Any]],
  *,
  tools: list[dict[str, Any]] | None = None,
  temperature: float | None = None,
  max_tokens: int | None = None,
  thinking_mode: ThinkingMode = "user",
  timeout_total: float = 120,
) -> tuple[str, str, str | None]:
  """Collect a full completion. Returns (content, reasoning, error)."""
  content_parts: list[str] = []
  reasoning_parts: list[str] = []
  async for chunk in chat_completion(
    config,
    messages,
    tools=tools,
    temperature=temperature,
    max_tokens=max_tokens,
    thinking_mode=thinking_mode,
    timeout_total=timeout_total,
  ):
    if chunk.error:
      return "", "", chunk.error
    if chunk.reasoning_content:
      reasoning_parts.append(chunk.reasoning_content)
    if chunk.content:
      content_parts.append(chunk.content)
  return "".join(content_parts), "".join(reasoning_parts), None


def merge_config_from_body(saved: AIConfig, body: dict[str, Any] | None) -> AIConfig:
  """Merge optional request body fields onto the saved config for preview/testing."""
  if not body:
    return saved

  provider = body.get("provider")
  model = body.get("model")
  api_key = body.get("apiKey", body.get("api_key"))
  base_url = body.get("baseUrl", body.get("base_url"))

  return AIConfig(
    provider=str(provider) if provider else saved.provider,
    model=str(model) if model else saved.model,
    api_key=str(api_key) if api_key and not str(api_key).startswith("•") else saved.api_key,
    base_url=str(base_url) if base_url is not None else saved.base_url,
    system_prompt=saved.system_prompt,
    temperature=saved.temperature,
    top_p=saved.top_p,
    max_tokens=saved.max_tokens,
    thinking_enabled=saved.thinking_enabled,
    thinking_keep=saved.thinking_keep,
  )


def _catalog_models(provider: str) -> list[dict[str, Any]]:
  try:
    from ai.common.params import AI_PROVIDER_MODEL_CATALOG
    ids = AI_PROVIDER_MODEL_CATALOG.get(provider) or []
  except Exception:
    ids = []
  return [{"id": mid} for mid in ids if mid]


async def list_models(config: AIConfig) -> dict[str, Any]:
  """Return available models from the provider's /v1/models endpoint."""
  err = config.configuration_error
  if err:
    catalog = _catalog_models(config.provider)
    if catalog:
      return {"ok": True, "models": catalog, "source": "catalog"}
    return {"ok": False, "error": err, "models": []}

  url = f"{config.endpoint}/models"
  headers = {"Authorization": f"Bearer {config.api_key}"}
  timeout = aiohttp.ClientTimeout(total=30, connect=10)
  try:
    async with aiohttp.ClientSession(timeout=timeout) as session:
      async with session.get(url, headers=headers) as resp:
        if resp.status in (401, 403):
          text = await resp.text()
          catalog = _catalog_models(config.provider)
          return {
            "ok": False,
            "error": f"API 密钥无效或未授权（HTTP {resp.status}）。请确认服务商与密钥匹配后重新保存。{text[:200]}",
            "models": catalog,
            "source": "auth_error",
          }
        if resp.status != 200:
          text = await resp.text()
          catalog = _catalog_models(config.provider)
          if catalog:
            return {
              "ok": True,
              "models": catalog,
              "source": "catalog",
              "warning": f"API error {resp.status}: {text[:200]}",
            }
          return {"ok": False, "error": f"API error {resp.status}: {text[:500]}"}
        data = await resp.json()
        models = data.get("data", [])
        if not models:
          catalog = _catalog_models(config.provider)
          if catalog:
            return {"ok": True, "models": catalog, "source": "catalog"}
        return {"ok": True, "models": models}
  except Exception as e:
    catalog = _catalog_models(config.provider)
    if catalog:
      return {"ok": True, "models": catalog, "source": "catalog", "warning": str(e)}
    return {"ok": False, "error": str(e)}


async def test_connection(config: AIConfig) -> dict[str, Any]:
  """Test the provider connection by listing models (cheap, no charge)."""
  result = await list_models(config)
  if not result.get("ok"):
    return result
  models = result.get("models", [])
  found = any(m.get("id") == config.model for m in models)
  return {
    "ok": True,
    "model_available": found,
    "models_count": len(models),
    "message": "Connection OK" if found else f"Connected but model '{config.model}' not found in available models.",
  }
