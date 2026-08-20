"""Scheduler action dispatch + device helpers."""

from __future__ import annotations

from typing import Any

from openpilot.common.swaglog import cloudlog

from ai.server.deps import get_state_reader, params, read_ai_config
from ai.core.sync.hub import broadcast_notifications
from ai.tools.memory_store import append_note, get_memory
from ai.tools.notifications import push_notification
from ai.tools.scheduler_actions import execute_scheduler_action
from ai.system.shell import run_command
from ai.core.llm.usage import load_usage

_PARAMS = params()


async def notify_push(title: str, body: str, *, level: str = "info") -> None:
  push_notification(title, body, level=level)
  try:
    await broadcast_notifications()
  except Exception as e:
    cloudlog.warning(f"aid: broadcast_notifications failed: {e}")


def device_wifi_connected() -> bool:
  try:
    out = run_command("ip_addr")
    text = out.get("stdout", "") or ""
    return "wlan" in text and "UP" in text
  except Exception:
    return False


async def scheduler_execute_action(action: str, _payload: dict[str, Any]) -> str:
  if action == "read_last_log":
    from ai.tools.diagnostics_tools import read_manager_log
    res = read_manager_log(_PARAMS, lines=80)
    text = res.get("log", "") or ""
    src = res.get("source", "")
    return (f"[{src}] " if src else "") + text[:400] or "empty"
  if action == "read_usage":
    u = load_usage(_PARAMS)
    return f"calls={u.get('calls')} tokens={u.get('total_tokens')}"
  if action == "read_tune_snapshot":
    from ai.tools.sp_settings import list_sp_settings
    state = get_state_reader().update(timeout=0)
    snap = list_sp_settings(_PARAMS, brand=state.brand)
    return f"{snap.get('setting_count', 0)} settings"
  if action == "memory_ping":
    m = get_memory(_PARAMS)
    return f"notes={len(m.get('notes', []))}"
  if action == "snapshot_tune":
    from ai.tools.diagnostics_tools import snapshot_tune_state
    from ai.tools.tune_snapshot_store import save_tune_snapshot
    state = get_state_reader().update(timeout=0)
    save_tune_snapshot(_PARAMS, label="scheduler", brand=state.brand or "")
    snap = snapshot_tune_state(_PARAMS, brand=state.brand)
    return f"params={snap.get('param_count', 0)}"
  if action == "trip_review_offroad":
    from ai.tools.diagnostics_tools import trip_review
    state = get_state_reader().update(timeout=0)
    review = trip_review(_PARAMS, get_state_reader, brand=state.brand or "")
    summary = "; ".join(review.get("recommendations") or [])[:300]
    append_note(_PARAMS, f"[offroad] {summary}", tags=["auto", "trip_review"])
    return summary or "trip_review ok"
  if action == "reindex_rag_wifi":
    from ai.core.llm.embedding import load_embedding_config
    from ai.tools.rag_jobs import is_running, start_rag_job
    config = read_ai_config()
    embed_cfg = load_embedding_config(_PARAMS, config)
    if not embed_cfg.is_configured:
      return "embedding not configured"
    if is_running():
      return "rag job already running"
    await start_rag_job(_PARAMS, embed_cfg, operation="reindex")
    return "rag reindex started in background"
  if action == "ingest_community_wiki_wifi":
    from ai.core.llm.embedding import load_embedding_config
    from ai.tools.rag_jobs import is_running, start_rag_job
    config = read_ai_config()
    embed_cfg = load_embedding_config(_PARAMS, config)
    if is_running():
      return "rag job already running"
    await start_rag_job(
      _PARAMS,
      embed_cfg,
      operation="wiki_ingest",
      wiki_options={"max_files_per_repo": 0, "force": False, "all_registered": False},
      chain_reindex=False,
    )
    return "wiki ingest started in background"
  if action == "check_critical_events":
    from ai.tools.diagnostics_tools import read_onroad_events
    ev = read_onroad_events(get_state_reader)
    critical = [e.get("name") for e in (ev.get("events") or []) if e.get("no_entry") or e.get("immediate_disable")]
    if critical:
      names = ", ".join(critical[:5])
      await notify_push("onroad 事件", names, level="warn")
      return f"critical: {names}"
    return "no critical events"
  if action == "post_drive_review_offroad":
    from ai.tools.voice_summary_tools import build_post_drive_summary
    state = get_state_reader().update(timeout=0)
    built = build_post_drive_summary(_PARAMS, get_state_reader, brand=state.brand or "")
    append_note(_PARAMS, f"[offroad] {built.get('text', '')[:300]}", tags=["auto", "voice_summary"])
    return built.get("text", "")[:300] or "post_drive ok"
  if action == "check_param_watchlist_offroad":
    from ai.tools.tune_passport_store import check_param_watchlist
    res = check_param_watchlist(_PARAMS)
    if res.get("drifted"):
      names = ", ".join(list((res.get("changes") or {}).keys())[:5])
      await notify_push("参数漂移", names, level="info")
      return f"drift: {names}"
    return "watchlist ok"
  if action == "git_fetch_wifi":
    from ai.tools.git_tools import git_fetch
    res = git_fetch()
    return f"fetch ok={res.get('ok')}"
  if action == "heartbeat_tick":
    from ai.core.runtime.heartbeat import run_heartbeat
    res = await run_heartbeat(_PARAMS, get_state_reader=get_state_reader)
    acts = ", ".join(res.get("actions") or [])
    return f"driving={res.get('driving')} notified={res.get('notified')} {acts}"[:300]
  if action == "chat_notify":
    prompt = str((_payload or {}).get("prompt") or "").strip()
    if not prompt:
      return "chat_notify: empty prompt"
    from ai.server.deps import read_ai_config
    from ai.core.llm.model_router import chat_completion_collect_with_failover
    config = read_ai_config(_PARAMS)
    if not config.is_configured:
      return "chat_notify: AI not configured"
    content, _, _, err = await chat_completion_collect_with_failover(
      config,
      _PARAMS,
      [
        {"role": "system", "content": "You are op助手. Reply in concise Chinese."},
        {"role": "user", "content": prompt},
      ],
      max_tokens=600,
      timeout_total=90,
    )
    summary = (content or err or "no response")[:400]
    await notify_push("定时任务", summary, level="info")
    append_note(_PARAMS, f"[scheduler] {summary}", tags=["auto", "chat_notify"])
    return summary
  extra = await execute_scheduler_action(
    action,
    _payload,
    params=_PARAMS,
    get_state_reader=get_state_reader,
    notify_push=notify_push,
    append_note=append_note,
  )
  if extra:
    return extra
  return f"unknown action {action}"
