"""
OpenAI-compatible embedding client for op助手 RAG.

Routing via model hub (embeddingPrimary + embeddingFallbacks).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiohttp

from ai.core.llm.client import DEFAULT_ENDPOINTS, _param_to_str

try:
  from ai.common.params import AI_OPTIONAL_BASE_URL_PROVIDERS
except Exception:
  AI_OPTIONAL_BASE_URL_PROVIDERS = frozenset({"qwen", "minimax", "mimo", "bigmodel"})

DEFAULT_EMBEDDING_MODELS = {
  "opencode-zen": "",
  "opencode-go": "",
  "deepseek": "",
  "bigmodel": "embedding-3",
  "qwen": "text-embedding-v3",
  "mimo": "",
  "minimax": "",
  "openrouter": "openai/text-embedding-3-small",
  "openai": "text-embedding-3-small",
  "kimi": "moonshot-v1-embedding",
  "siliconflow": "BAAI/bge-m3",
  "custom": "text-embedding-3-small",
}


@dataclass
class EmbeddingConfig:
  provider: str
  model: str
  api_key: str
  base_url: str = ""

  @property
  def endpoint(self) -> str:
    if self.provider == "custom":
      return (self.base_url or "").rstrip("/")
    if self.base_url.strip() and self.provider in AI_OPTIONAL_BASE_URL_PROVIDERS:
      return self.base_url.rstrip("/")
    return DEFAULT_ENDPOINTS.get(self.provider, DEFAULT_ENDPOINTS["openrouter"])

  @property
  def is_configured(self) -> bool:
    return bool(self.api_key and self.model and self.endpoint)


def load_embedding_config(params: Any, chat_config: Any | None = None) -> EmbeddingConfig:
  """Resolve primary embedding config from model hub (legacy params migrated on load)."""
  del chat_config
  from openpilot.common.params import Params
  from ai.core.llm.model_accounts import resolve_embedding_primary_config

  p = params if isinstance(params, Params) else Params()
  return resolve_embedding_primary_config(p)


def load_embedding_config_chain(params: Any) -> list[EmbeddingConfig]:
  from openpilot.common.params import Params
  from ai.core.llm.model_accounts import resolve_embedding_chain

  p = params if isinstance(params, Params) else Params()
  return resolve_embedding_chain(p)


def normalize_embedding_usage(raw: dict[str, Any] | None) -> dict[str, int]:
  if not isinstance(raw, dict):
    return {}
  prompt = int(raw.get("prompt_tokens", 0) or 0)
  total = int(raw.get("total_tokens", 0) or 0)
  if not total:
    total = prompt
  if not prompt and total:
    prompt = total
  if not total:
    return {}
  return {"prompt_tokens": prompt, "completion_tokens": 0, "total_tokens": total}


async def embed_texts(
  config: EmbeddingConfig,
  texts: list[str],
  *,
  params: Any | None = None,
  source: str = "embedding",
) -> tuple[list[list[float]] | None, str | None]:
  if not config.is_configured:
    return None, "Embedding not configured (API key / model / endpoint)."
  if not texts:
    return [], None

  url = f"{config.endpoint}/embeddings"
  headers = {
    "Authorization": f"Bearer {config.api_key}",
    "Content-Type": "application/json",
  }
  if config.provider == "openrouter":
    headers["HTTP-Referer"] = "https://github.com/commaai/openpilot"
    headers["X-Title"] = "op-assistant-rag"

  payload: dict[str, Any] = {"model": config.model, "input": texts}
  try:
    async with aiohttp.ClientSession() as session:
      async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as resp:
        body = await resp.json()
        if resp.status != 200:
          err = body.get("error", body) if isinstance(body, dict) else body
          return None, f"Embedding HTTP {resp.status}: {err}"
        data = body.get("data") or []
        vectors: list[list[float]] = []
        for item in sorted(data, key=lambda x: x.get("index", 0)):
          emb = item.get("embedding")
          if not isinstance(emb, list):
            return None, "Invalid embedding response"
          vectors.append([float(x) for x in emb])
        if len(vectors) != len(texts):
          return None, f"Expected {len(texts)} embeddings, got {len(vectors)}"
        usage = normalize_embedding_usage(body.get("usage") if isinstance(body, dict) else None)
        if params is not None and usage:
          from ai.core.llm.usage import record_embedding_usage

          record_embedding_usage(
            params,
            usage,
            provider=config.provider,
            model=config.model,
            source=source,
          )
        return vectors, None
  except Exception as e:
    return None, str(e)


async def embed_texts_with_failover(
  params: Any,
  texts: list[str],
  *,
  source: str = "embedding",
) -> tuple[list[list[float]] | None, EmbeddingConfig | None, str | None]:
  """Try embedding chain until one succeeds."""
  chain = load_embedding_config_chain(params)
  if not chain:
    return None, None, "Embedding not configured"
  last_error = ""
  for cfg in chain:
    vectors, err = await embed_texts(cfg, texts, params=params, source=source)
    if err:
      last_error = err
      continue
    return vectors, cfg, None
  return None, None, last_error or "All embedding models failed"
