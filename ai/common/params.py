"""
AI Agent param definitions.

Schema for ai_* keys. Runtime storage: /data/ai/config.json (see common/config_store.py).
Openpilot fork Params (e.g. SpDevBeep, CarPlatformBundle) still use params_keys.h.
"""

# Provider presets used by both the device UI and the web config page.
AI_PROVIDERS = [
  "opencode-zen",
  "opencode-go",
  "deepseek",
  "bigmodel",
  "qwen",
  "mimo",
  "minimax",
  "openrouter",
  "openai",
  "kimi",
  "siliconflow",
  "custom",
]

AI_PROVIDER_LABELS = {
  "opencode-zen": "OpenCode Zen",
  "opencode-go": "OpenCode Go",
  "deepseek": "DeepSeek",
  "bigmodel": "智谱 BigModel",
  "qwen": "通义千问",
  "mimo": "小米 MiMo",
  "minimax": "MiniMax",
  "openrouter": "OpenRouter",
  "openai": "OpenAI",
  "kimi": "Kimi (Moonshot)",
  "siliconflow": "硅基流动 SiliconFlow",
  "custom": "Custom",
}

# Providers where ai_base_url optionally overrides the preset endpoint.
AI_OPTIONAL_BASE_URL_PROVIDERS = frozenset({"qwen", "minimax", "mimo", "bigmodel"})

# Default model suggestions per provider (chat/completions compatible).
AI_DEFAULT_MODELS = {
  "opencode-zen": "deepseek-v4-flash",
  "opencode-go": "deepseek-v4-flash",
  "deepseek": "deepseek-v4-flash",
  "bigmodel": "glm-5.2",
  "qwen": "qwen-plus",
  "mimo": "mimo-v2.5",
  "minimax": "MiniMax-M3",
  "openrouter": "openai/gpt-4o-mini",
  "openai": "gpt-4o-mini",
  "kimi": "moonshot-v1-8k",
  "siliconflow": "deepseek-ai/DeepSeek-V3",
  "custom": "",
}

# Fallback model list when /v1/models is unavailable (ids only).
AI_PROVIDER_MODEL_CATALOG = {
  "opencode-zen": [
    "deepseek-v4-flash",
    "deepseek-v4-flash-free",
    "deepseek-v4-pro",
    "mimo-v2.5-free",
    "north-mini-code-free",
    "nemotron-3-ultra-free",
    "big-pickle",
    "minimax-m3",
    "minimax-m2.7",
    "glm-5.2",
    "glm-5.1",
    "kimi-k2.5",
    "kimi-k2.6",
    "kimi-k2.7-code",
    "grok-4.5",
  ],
  "opencode-go": [
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "glm-5.2",
    "glm-5.1",
    "kimi-k2.7-code",
    "kimi-k2.6",
    "mimo-v2.5",
    "mimo-v2.5-pro",
    "minimax-m3",
    "minimax-m2.7",
    "qwen3.7-max",
    "qwen3.7-plus",
    "qwen3.6-plus",
  ],
  "deepseek": [
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "deepseek-chat",
    "deepseek-reasoner",
  ],
  "bigmodel": [
    "glm-5.2",
    "glm-4-plus",
    "glm-4-air",
    "glm-4-airx",
    "glm-4-flash",
    "glm-4-long",
    "glm-4.5",
    "glm-4.5-air",
    "glm-4.5-flash",
  ],
  "qwen": [
    "qwen-max",
    "qwen-plus",
    "qwen-turbo",
    "qwen-long",
    "qwen3.5-plus",
    "qwen3.6-plus",
    "qwen3.7-plus",
    "qwen3.7-max",
    "qwq-plus",
    "qwq-32b-preview",
  ],
  "mimo": [
    "mimo-v2.5",
    "mimo-v2.5-pro",
  ],
  "minimax": [
    "MiniMax-M3",
    "MiniMax-M2.7",
    "MiniMax-M2.5",
    "MiniMax-M2.1",
    "MiniMax-Text-01",
  ],
  "openrouter": [],
  "openai": [],
  "kimi": [
    "moonshot-v1-8k",
    "moonshot-v1-32k",
    "moonshot-v1-128k",
    "moonshot-v1-auto",
    "kimi-k2.5",
    "kimi-k2.6",
    "kimi-k2.7",
    "kimi-k2.7-code",
    "kimi-k3",
  ],
  "siliconflow": [
    "deepseek-ai/DeepSeek-V3",
    "Qwen/Qwen2.5-7B-Instruct",
    "BAAI/bge-m3",
    "Qwen/Qwen3-Embedding-8B",
    "Qwen/Qwen2-VL-Embedding",
  ],
  "custom": [],
}

# Embedding-only providers (separate from chat providers).
AI_EMBEDDING_PROVIDERS = [
  "siliconflow",
  "openrouter",
  "openai",
  "bigmodel",
  "qwen",
  "custom",
]

AI_EMBEDDING_PROVIDER_LABELS = {
  "siliconflow": "硅基流动 SiliconFlow",
  "openrouter": "OpenRouter",
  "openai": "OpenAI",
  "bigmodel": "智谱 BigModel",
  "qwen": "通义千问",
  "custom": "Custom",
}

# Curated embedding model IDs per embedding provider.
AI_EMBEDDING_MODEL_CATALOG = {
  "siliconflow": [
    "BAAI/bge-m3",
    "BAAI/bge-large-zh-v1.5",
    "netease-youdao/bce-embedding-base_v1",
    "Qwen/Qwen3-Embedding-8B",
    "Pro/BAAI/bge-m3",
  ],
  "openrouter": [
    "openai/text-embedding-3-small",
    "openai/text-embedding-3-large",
    "qwen/qwen3-embedding-8b",
  ],
  "openai": [
    "text-embedding-3-small",
    "text-embedding-3-large",
    "text-embedding-ada-002",
  ],
  "bigmodel": [
    "embedding-3",
    "embedding-2",
  ],
  "qwen": [
    "text-embedding-v3",
    "text-embedding-v2",
  ],
  "custom": [
    "text-embedding-3-small",
  ],
}

# When embedding mode is "same", suggest models per chat provider.
AI_SAME_MODE_EMBEDDING_MODELS = {
  "bigmodel": ["embedding-3", "embedding-2"],
  "qwen": ["text-embedding-v3", "text-embedding-v2"],
  "openrouter": ["openai/text-embedding-3-small", "openai/text-embedding-3-large"],
  "openai": ["text-embedding-3-small", "text-embedding-3-large"],
  "kimi": ["moonshot-v1-embedding"],
  "custom": ["text-embedding-3-small"],
}

ITEMS = [
  # Selected provider preset.
  {
    "key": "ai_provider",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "opencode-zen",
  },
  # Model name / ID passed to the provider's /chat/completions endpoint.
  {
    "key": "ai_model",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "deepseek-v4-flash",
  },
  {
    "key": "ai_model_fast",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "",
  },
  {
    "key": "ai_model_deep",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "",
  },
  {
    "key": "ai_model_routing",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "auto",
  },
  # API key. Marked DONT_LOG so it never ends up in logs or qlogs.
  {
    "key": "ai_api_key",
    "flags": "PERSISTENT | DONT_LOG",
    "param_type": "STRING",
    "default": "",
  },
  # Custom base URL, used when ai_provider == "custom".
  {
    "key": "ai_base_url",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "",
  },
  # Custom system prompt.
  {
    "key": "ai_system_prompt",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "",
  },
  # Sampling temperature.
  {
    "key": "ai_temperature",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "0.7",
  },
  # Top-p nucleus sampling.
  {
    "key": "ai_top_p",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "1.0",
  },
  # Maximum tokens per response.
  {
    "key": "ai_max_tokens",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "4096",
  },
  {
    "key": "ai_context_window",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "0",
  },
  {
    "key": "ai_compaction_enabled",
    "flags": "PERSISTENT",
    "param_type": "BOOL",
    "default": "1",
  },
  {
    "key": "ai_compact_after_turns",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "24",
  },
  {
    "key": "ai_keep_recent_turns",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "8",
  },
  {
    "key": "ai_reserve_tokens",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "8000",
  },
  {
    "key": "ai_compaction_token_trigger",
    "flags": "PERSISTENT",
    "param_type": "BOOL",
    "default": "1",
  },
  {
    "key": "ai_evolution_enabled",
    "flags": "PERSISTENT",
    "param_type": "BOOL",
    "default": "1",
  },
  {
    "key": "ai_evolution_auto_propose",
    "flags": "PERSISTENT",
    "param_type": "BOOL",
    "default": "0",
  },
  {
    "key": "ai_evolution_auto_workspace",
    "flags": "PERSISTENT",
    "param_type": "BOOL",
    "default": "1",
  },
  {
    "key": "ai_evolution_auto_memory",
    "flags": "PERSISTENT",
    "param_type": "BOOL",
    "default": "1",
  },
  {
    "key": "ai_evolution_llm_reflect",
    "flags": "PERSISTENT",
    "param_type": "BOOL",
    "default": "1",
  },
  {
    "key": "ai_evolution_tool_desc",
    "flags": "PERSISTENT",
    "param_type": "BOOL",
    "default": "1",
  },
  {
    "key": "ai_skills_disclosure_max",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "10",
  },
  {
    "key": "ai_evolution_candidates",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "3",
  },
  {
    "key": "ai_evolution_gepa_enabled",
    "flags": "PERSISTENT",
    "param_type": "BOOL",
    "default": "1",
  },
  {
    "key": "ai_evolution_gepa_iterations",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "3",
  },
  {
    "key": "ai_evolution_eval_cases",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "8",
  },
  {
    "key": "ai_evolution_use_dspy",
    "flags": "PERSISTENT",
    "param_type": "BOOL",
    "default": "0",
  },
  {
    "key": "ai_tool_desc_overrides",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "",
  },
  {
    "key": "ai_evolution_pipeline_log",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "",
  },
  # Enable thinking / reasoning mode (Kimi k2.x and similar models).
  {
    "key": "ai_thinking_enabled",
    "flags": "PERSISTENT",
    "param_type": "BOOL",
    "default": "1",
  },
  # Preserve reasoning_content across turns (Kimi: "all" or empty).
  {
    "key": "ai_thinking_keep",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "",
  },
  {
    "key": "ai_memory_notes",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "",
  },
  {
    "key": "ai_vehicle_profile",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "",
  },
  {
    "key": "ai_scheduled_tasks",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "",
  },
  {
    "key": "ai_deferred_tools",
    "flags": "PERSISTENT",
    "param_type": "BOOL",
    "default": True,
  },
  {
    "key": "ai_externalize_results",
    "flags": "PERSISTENT",
    "param_type": "BOOL",
    "default": True,
  },
  {
    "key": "ai_externalize_threshold",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "8192",
  },
  {
    "key": "ai_model_tier",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "auto",
  },
  {
    "key": "ai_profile_sync_manifest",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "",
  },
  {
    "key": "ai_skills_enabled",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "",
  },
  {
    "key": "ai_rag_documents",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "",
  },
  {
    "key": "ai_rag_max_docs",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "20000",
  },
  {
    "key": "ai_rag_max_chunks",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "100000",
  },
  {
    "key": "ai_rag_max_total_chars",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "50000000",
  },
  {
    "key": "ai_rag_search_limit",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "20",
  },
  {
    "key": "ai_wiki_max_files_per_repo",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "0",
  },
  {
    "key": "ai_embedding_mode",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "same",
  },
  {
    "key": "ai_embedding_provider",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "siliconflow",
  },
  {
    "key": "ai_embedding_model",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "",
  },
  {
    "key": "ai_embedding_api_key",
    "flags": "PERSISTENT | DONT_LOG",
    "param_type": "STRING",
    "default": "",
  },
  {
    "key": "ai_embedding_base_url",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "",
  },
  {
    "key": "ai_web_pin",
    "flags": "PERSISTENT | DONT_LOG",
    "param_type": "STRING",
    "default": "",
  },
  {
    "key": "ai_write_pending",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "",
  },
  {
    "key": "ai_scheduler_state",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "",
  },
  {
    "key": "ai_web_sessions",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "",
  },
  {
    "key": "ai_admin_mode",
    "flags": "PERSISTENT",
    "param_type": "BOOL",
    "default": "1",
  },
  {
    "key": "ai_timezone",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "Asia/Shanghai",
  },
  {
    "key": "ai_first_run_done",
    "flags": "PERSISTENT",
    "param_type": "BOOL",
    "default": "0",
  },
  {
    "key": "ai_fork_id",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "",
  },
  {
    "key": "ai_fork_profile_applied",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "",
  },
  # GitHub PAT for Actions / PR tools (not openpilot Params).
  {
    "key": "ai_github_actions_pat",
    "flags": "PERSISTENT | DONT_LOG",
    "param_type": "STRING",
    "default": "",
  },
  {
    "key": "ai_assistant_repo_url",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "https://github.com/mouxangithub/ai",
  },
  {
    "key": "ai_openpilot_repo_url",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "https://github.com/mouxangithub/openpilot",
  },
  {
    "key": "ai_assistant_repo_path",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "",
  },
  {
    "key": "ai_assistant_default_branch",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "main",
  },
  {
    "key": "ai_openpilot_default_branch",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "master-c3",
  },
  {
    "key": "ai_gitee_token",
    "flags": "PERSISTENT | DONT_LOG",
    "param_type": "STRING",
    "default": "",
  },
  {
    "key": "ai_gitlab_token",
    "flags": "PERSISTENT | DONT_LOG",
    "param_type": "STRING",
    "default": "",
  },
  {
    "key": "ai_publish_settings",
    "flags": "PERSISTENT",
    "param_type": "STRING",
    "default": "",
  },
]
