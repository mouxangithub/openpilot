"""Background RAG reindex / wiki ingest jobs."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog

from ai.core.llm.embedding import EmbeddingConfig

_JOBS: dict[str, dict[str, Any]] = {}
_CURRENT: str | None = None


def _active_job() -> dict[str, Any] | None:
  if not _CURRENT:
    return None
  job = _JOBS.get(_CURRENT)
  return dict(job) if job else None


def job_poll_view() -> dict[str, Any]:
  """Flattened payload for the web UI job poller."""
  job = _active_job()
  if not job:
    return {"ok": True, "running": False, "status": "idle"}
  status = str(job.get("status") or "queued")
  running = status in {"queued", "running"}
  out: dict[str, Any] = {
    "ok": True,
    "running": running,
    "status": status,
    "phase": job.get("phase") or job.get("operation"),
    "jobId": job.get("id"),
  }
  if status == "error":
    out["error"] = job.get("error") or "rag job failed"
  if not running:
    result: dict[str, Any] = {}
    if "wiki" in job:
      result["wiki"] = job["wiki"]
    if "reindex" in job:
      result["reindex"] = job["reindex"]
    if result:
      out["result"] = result
    if job.get("progress"):
      out["progress"] = job["progress"]
  elif job.get("progress"):
    out["progress"] = job["progress"]
  return out


def job_status(job_id: str | None = None) -> dict[str, Any]:
  if job_id:
    job = _JOBS.get(job_id)
    if not job:
      return {"ok": False, "error": "job not found"}
    return {"ok": True, "job": dict(job)}
  active = _active_job()
  return {
    "ok": True,
    "currentJobId": _CURRENT,
    "job": active,
    "jobs": [dict(j) for j in _JOBS.values()][-5:],
  }


def is_running() -> bool:
  job = _active_job()
  return bool(job and job.get("status") in {"queued", "running"})


async def _run_job(
  job_id: str,
  params: Params,
  operation: str,
  *,
  wiki_options: dict[str, Any] | None = None,
  chain_reindex: bool = True,
) -> None:
  global _CURRENT
  job = _JOBS[job_id]
  try:
    job["status"] = "running"
    job["startedAt"] = int(time.time())
    if operation == "wiki_ingest":
      job["phase"] = "wiki_ingest"
      from ai.fork.wiki_ingest import ingest_wikis_for_current_fork

      opts = wiki_options or {}
      result = await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: ingest_wikis_for_current_fork(
          force=bool(opts.get("force")),
          all_registered=bool(opts.get("all_registered")),
          max_files_per_repo=int(opts.get("max_files_per_repo", 0) or 0),
        ),
      )
      job["wiki"] = result
      if chain_reindex:
        operation = "reindex"
        job["phase"] = "wiki_done"
    if operation == "reindex":
      job["phase"] = "reindex"
      from ai.tools.domains.core.rag_store import reindex_all

      embed_cfg = job.get("embed_config")

      def _progress(done: int, total: int, indexed: int) -> None:
        job["progress"] = {"done": done, "total": total, "indexed": indexed}

      result = await reindex_all(params, embed_cfg, on_progress=_progress)
      job["reindex"] = result
    job["status"] = "done"
    job["finishedAt"] = int(time.time())
  except Exception as e:
    cloudlog.error(f"aid: rag job {job_id} failed: {e}")
    job["status"] = "error"
    job["error"] = str(e)
    job["finishedAt"] = int(time.time())
  finally:
    if _CURRENT == job_id:
      _CURRENT = None


async def start_rag_job(
  params: Params,
  embed_cfg: EmbeddingConfig | None,
  *,
  operation: str = "reindex",
  wiki_options: dict[str, Any] | None = None,
  chain_reindex: bool = True,
) -> dict[str, Any]:
  global _CURRENT
  if is_running():
    return {"ok": False, "error": "已有任务在运行", "job": job_status(_CURRENT)}
  job_id = f"rag_{uuid.uuid4().hex[:10]}"
  _JOBS[job_id] = {
    "id": job_id,
    "operation": operation,
    "status": "queued",
    "phase": operation,
    "createdAt": int(time.time()),
    "embed_config": embed_cfg,
  }
  _CURRENT = job_id
  asyncio.create_task(_run_job(job_id, params, operation, wiki_options=wiki_options, chain_reindex=chain_reindex))
  return {"ok": True, "started": True, "jobId": job_id, "job": job_status(job_id)}
