"""
OpenAI-compatible embedding client for op助手 RAG.

Supports same provider as chat or a separate embedding configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiohttp

from ai.client import DEFAULT_ENDPOINTS, _param_to_str

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
  mode: str  # "same" | "separate"
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
  mode = _param_to_str(params.get("ai_embedding_mode"), "same").lower()
  if mode not in ("same", "separate"):
    mode = "same"

  if mode == "same" and chat_config is not None:
    provider = chat_config.provider
    model = _param_to_str(params.get("ai_embedding_model")) or DEFAULT_EMBEDDING_MODELS.get(
      provider, DEFAULT_EMBEDDING_MODELS["openrouter"],
    )
    return EmbeddingConfig(
      mode=mode,
      provider=provider,
      model=model,
      api_key=chat_config.api_key,
      base_url=chat_config.base_url or "",
    )

  provider = _param_to_str(params.get("ai_embedding_provider"), "siliconflow")
  model = _param_to_str(params.get("ai_embedding_model")) or DEFAULT_EMBEDDING_MODELS.get(
    provider, DEFAULT_EMBEDDING_MODELS["openrouter"],
  )
  api_key = _param_to_str(params.get("ai_embedding_api_key"))
  if not api_key and chat_config is not None:
    api_key = chat_config.api_key
  base_url = _param_to_str(params.get("ai_embedding_base_url"))
  return EmbeddingConfig(mode=mode, provider=provider, model=model, api_key=api_key, base_url=base_url)


async def embed_texts(config: EmbeddingConfig, texts: list[str]) -> tuple[list[list[float]] | None, str | None]:
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
    headers["HTTP-Referer"] = "https://github.com/dragonpilot/openpilot"
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
        return vectors, None
  except Exception as e:
    return None, str(e)
