"""Shared SSE event helpers for fork analysis pipeline."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

EmitFn = Callable[[dict[str, Any]], Awaitable[None]] | None

PHASE_LABELS: dict[str, str] = {
  "scan": "扫描 openpilot 仓库",
  "cache": "检查分析缓存",
  "read_files": "读取关键文件",
  "llm_analyze": "AI 分析 fork",
  "parse": "解析分析结果",
  "save_analysis": "保存分析缓存",
  "llm_draft": "生成技能与文档草稿",
  "save_drafts": "写入草稿文件",
}


async def emit_event(emit: EmitFn, event: dict[str, Any]) -> None:
  if emit is not None:
    await emit(event)


async def emit_phase(
  emit: EmitFn,
  phase_id: str,
  status: str,
  *,
  message: str | None = None,
  detail: Any = None,
) -> None:
  payload: dict[str, Any] = {
    "type": "phase",
    "id": phase_id,
    "label": PHASE_LABELS.get(phase_id, phase_id),
    "status": status,
  }
  if message:
    payload["message"] = message
  if detail is not None:
    payload["detail"] = detail
  await emit_event(emit, payload)


async def stream_llm_completion(
  config: Any,
  messages: list[dict[str, Any]],
  *,
  emit: EmitFn,
  phase_id: str,
  timeout_total: float = 240,
) -> tuple[str, str, str | None]:
  """Stream chat completion; emit reasoning/content deltas. Returns (content, reasoning, error)."""
  from ai.client import chat_completion

  content_parts: list[str] = []
  reasoning_parts: list[str] = []
  await emit_phase(emit, phase_id, "active")
  async for chunk in chat_completion(config, messages, timeout_total=timeout_total):
    if chunk.error:
      await emit_event(emit, {"type": "error", "phase": phase_id, "error": chunk.error})
      await emit_phase(emit, phase_id, "error", message=chunk.error)
      return "", "", chunk.error
    if chunk.reasoning_content:
      reasoning_parts.append(chunk.reasoning_content)
      await emit_event(
        emit,
        {"type": "reasoning", "phase": phase_id, "delta": chunk.reasoning_content},
      )
    if chunk.content:
      content_parts.append(chunk.content)
      await emit_event(emit, {"type": "content", "phase": phase_id, "delta": chunk.content})
  await emit_phase(emit, phase_id, "done")
  return "".join(content_parts), "".join(reasoning_parts), None
