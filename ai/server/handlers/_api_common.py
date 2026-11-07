"""HTTP API handlers (extracted from aid.py)."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

from openpilot.common.swaglog import cloudlog

from ai.core.llm.model_router import fallbacks_for_api, load_fallback_entries, save_fallback_entries
from ai.core.llm.model_accounts import (
  account_config_by_id,
  hub_for_api,
  load_model_hub,
  save_model_hub,
  update_account_models,
)
from ai.server.deps import (
  filter_tools,
  get_state_reader,
  get_tool_handlers,
  json_response,
  mask_key,
  openpilot_root,
  params,
  read_ai_config,
  read_param_bool_val,
  read_param_str,
  resolve_max_tool_rounds,
  sse,
)
from ai.core.llm.client import AIConfig, merge_config_from_body, test_connection, list_models
from ai.common.storage import format_persist_error
from ai.common.params import (
  AI_DEFAULT_MODELS,
  AI_EMBEDDING_MODEL_CATALOG,
  AI_EMBEDDING_PROVIDER_LABELS,
  AI_EMBEDDING_PROVIDERS,
  AI_PROVIDER_LABELS,
  AI_PROVIDER_MODEL_CATALOG,
  AI_PROVIDERS,
  AI_SAME_MODE_EMBEDDING_MODELS,
)
from ai.common.storage import write_param, write_param_bool
from ai.core.llm.embedding import DEFAULT_EMBEDDING_MODELS, load_embedding_config
from ai.core.wspace.persona import ensure_default_persona
from ai.skills.loader import list_skills, load_enabled_skill_ids, save_enabled_skill_ids
from ai.system.admin import is_admin_mode
from ai.system.host_env import get_host_environment
from ai.system.safety import ACTION_RULES, is_action_allowed
from ai.system.shell import run_command
from ai.agents.config import agents_enabled_payload
from ai.agents.office import office_snapshot as get_office_snapshot
from ai.agents.orchestrator import detect_orchestration_plan, run_chat_with_agents
from ai.agents.registry import filter_tools_for_agent, get_agent, list_agents, orchestrator_id
from ai.agents.router import resolve_agent_route
from ai.core.chat.jobs import cancel_job, cancel_jobs_for_session, get_job, list_active_jobs, start_chat_job, wait_for_job
from ai.core.chat.command_queue import submit_chat_request
from ai.core.chat.runner import ChatCancelled
from ai.core.sync.hub import broadcast_config, broadcast_notifications, broadcast_sessions
from ai.tools.agent_tools import tool_meta_for_host
from ai.tools.memory_store import (
  append_note,
  delete_note,
  get_memory,
  update_vehicle_profile,
  sync_vehicle_profile_from_state,
)
from ai.tools.notifications import list_notifications, mark_notifications_read
from ai.tools.rag_store import (
  list_documents,
  remove_document,
  search_documents,
  upsert_document,
  reindex_all,
)
from ai.tools.scheduler import list_tasks, remove_task, upsert_task
from ai.tools.session_store import get_sessions, save_sessions
from ai.tools.workflows import list_workflows
from ai.tools.consumer_tools import consumer_bootstrap_payload
from ai.tools.write_pending import confirm_pending, list_pending
from ai.core.llm.usage import load_embedding_usage, load_usage

_PARAMS = params()
_get_state_reader = get_state_reader
_json_response = json_response
_sse = sse
_read_param_str = read_param_str
_read_param_bool = read_param_bool_val
_mask_key = mask_key
_read_ai_config = read_ai_config
_get_tool_handlers = get_tool_handlers
_resolve_max_tool_rounds = resolve_max_tool_rounds
_filter_tools = filter_tools

# Star-imported by handler modules — include _-prefixed aliases explicitly.
__all__ = [name for name in globals() if not name.startswith("__")]
