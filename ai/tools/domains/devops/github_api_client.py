"""Minimal GitHub REST client for Actions (no third-party deps)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
  from openpilot.common.params import Params

API_ACCEPT = "application/vnd.github+json"
API_VERSION = "2022-11-28"
PAT_KEY = "ai_github_actions_pat"
DEFAULT_REPO = "https://github.com/mouxangithub/openpilot"
ASSISTANT_REPO = "https://github.com/mouxangithub/ai"


def parse_repo_url(repo_url: str) -> tuple[str, str]:
  """Return (owner, repo) from URL or owner/repo."""
  text = (repo_url or DEFAULT_REPO).strip().rstrip("/")
  if text.startswith("http://") or text.startswith("https://"):
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", text, re.I)
    if not m:
      raise ValueError(f"unsupported repo URL: {repo_url}")
    return m.group(1), m.group(2)
  if "/" in text:
    owner, repo = text.split("/", 1)
    return owner, repo.removesuffix(".git")
  raise ValueError(f"unsupported repo: {repo_url}")


def get_pat(params: "Params | None" = None) -> str | None:
  del params  # stored in ai config.json, not openpilot Params
  try:
    from ai.common.config_store import get_config_store
    raw = get_config_store().get(PAT_KEY, "")
    token = str(raw or "").strip()
    return token or None
  except Exception:
    return None


def set_pat(params: "Params | None", token: str | None) -> None:
  del params
  from ai.common.storage import remove_param, write_param
  if token:
    write_param(None, PAT_KEY, token)
  else:
    remove_param(None, PAT_KEY)


def github_request(
  method: str,
  path: str,
  token: str,
  *,
  query: dict[str, Any] | None = None,
  body: dict[str, Any] | None = None,
  timeout: float = 30.0,
) -> dict[str, Any]:
  if not path.startswith("/"):
    path = "/" + path
  url = "https://api.github.com" + path
  if query:
    q = {k: v for k, v in query.items() if v is not None and v != ""}
    if q:
      url += "?" + urllib.parse.urlencode(q)
  data = None
  headers = {
    "Accept": API_ACCEPT,
    "X-GitHub-Api-Version": API_VERSION,
    "User-Agent": "openpilot-op-assistant",
    "Authorization": f"Bearer {token}",
  }
  if body is not None:
    data = json.dumps(body).encode("utf-8")
    headers["Content-Type"] = "application/json"
  req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
  try:
    with urllib.request.urlopen(req, timeout=timeout) as resp:
      raw = resp.read().decode("utf-8", errors="replace")
      if not raw:
        return {"ok": True, "status": resp.status}
      parsed = json.loads(raw)
      if isinstance(parsed, dict):
        parsed["_http_status"] = resp.status
      return parsed
  except urllib.error.HTTPError as e:
    detail = ""
    try:
      detail = e.read().decode("utf-8", errors="replace")
      parsed = json.loads(detail) if detail else {}
      msg = parsed.get("message") if isinstance(parsed, dict) else detail
    except Exception:
      msg = detail or str(e)
    return {
      "ok": False,
      "error": "github_api_error",
      "http_status": e.code,
      "message": msg,
    }
  except urllib.error.URLError as e:
    return {"ok": False, "error": "network_error", "message": str(e.reason)}
  except json.JSONDecodeError as e:
    return {"ok": False, "error": "invalid_json", "message": str(e)}


def _api_ok(data: dict[str, Any]) -> bool:
  return data.get("ok") is not False and "error" not in data


def summarize_workflow_run(run: dict[str, Any]) -> dict[str, Any]:
  return {
    "id": run.get("id"),
    "name": run.get("name"),
    "status": run.get("status"),
    "conclusion": run.get("conclusion"),
    "event": run.get("event"),
    "head_branch": run.get("head_branch"),
    "head_sha": (run.get("head_sha") or "")[:12] or None,
    "created_at": run.get("created_at"),
    "updated_at": run.get("updated_at"),
    "run_started_at": run.get("run_started_at"),
    "run_attempt": run.get("run_attempt"),
    "workflow_id": run.get("workflow_id"),
    "html_url": run.get("html_url"),
  }


def summarize_job(job: dict[str, Any]) -> dict[str, Any]:
  return {
    "id": job.get("id"),
    "name": job.get("name"),
    "status": job.get("status"),
    "conclusion": job.get("conclusion"),
    "started_at": job.get("started_at"),
    "completed_at": job.get("completed_at"),
    "runner_name": job.get("runner_name"),
    "runner_group_name": job.get("runner_group_name"),
    "labels": job.get("labels") or [],
    "html_url": job.get("html_url"),
  }


def summarize_runner(runner: dict[str, Any]) -> dict[str, Any]:
  return {
    "id": runner.get("id"),
    "name": runner.get("name"),
    "status": runner.get("status"),
    "busy": runner.get("busy"),
    "labels": [lb.get("name") for lb in (runner.get("labels") or []) if isinstance(lb, dict)],
    "os": runner.get("os"),
  }


def verify_token(token: str) -> dict[str, Any]:
  data = github_request("GET", "/user", token, timeout=15)
  if not _api_ok(data):
    return {"ok": False, "valid": False, **data}
  return {
    "ok": True,
    "valid": True,
    "login": data.get("login"),
    "name": data.get("name"),
  }


def list_workflow_runs(
  token: str,
  owner: str,
  repo: str,
  *,
  workflow: str | None = None,
  status: str | None = None,
  branch: str | None = None,
  per_page: int = 10,
) -> dict[str, Any]:
  per_page = max(1, min(int(per_page or 10), 30))
  if workflow:
    path = f"/repos/{owner}/{repo}/actions/workflows/{urllib.parse.quote(workflow, safe='')}/runs"
  else:
    path = f"/repos/{owner}/{repo}/actions/runs"
  data = github_request(
    "GET",
    path,
    token,
    query={"per_page": per_page, "status": status, "branch": branch},
  )
  if not _api_ok(data):
    return data
  runs = [summarize_workflow_run(r) for r in (data.get("workflow_runs") or [])]
  return {
    "ok": True,
    "total_count": data.get("total_count"),
    "runs": runs,
    "in_progress": [r for r in runs if r.get("status") in ("in_progress", "queued", "waiting", "requested", "pending")],
  }


def get_workflow_run(token: str, owner: str, repo: str, run_id: int) -> dict[str, Any]:
  run_data = github_request("GET", f"/repos/{owner}/{repo}/actions/runs/{run_id}", token)
  if not _api_ok(run_data):
    return run_data
  jobs_data = github_request("GET", f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs", token, query={"per_page": 100})
  jobs = []
  if _api_ok(jobs_data):
    jobs = [summarize_job(j) for j in (jobs_data.get("jobs") or [])]
  return {
    "ok": True,
    "run": summarize_workflow_run(run_data),
    "jobs": jobs,
    "active_jobs": [j for j in jobs if j.get("status") in ("in_progress", "queued", "waiting")],
  }


def cancel_workflow_run(token: str, owner: str, repo: str, run_id: int) -> dict[str, Any]:
  data = github_request("POST", f"/repos/{owner}/{repo}/actions/runs/{run_id}/cancel", token, body={})
  if not _api_ok(data):
    return data
  return {"ok": True, "cancelled_run_id": run_id, "http_status": data.get("_http_status", 202)}


def list_repo_runners(token: str, owner: str, repo: str) -> dict[str, Any]:
  data = github_request("GET", f"/repos/{owner}/{repo}/actions/runners", token, query={"per_page": 100})
  if not _api_ok(data):
    return data
  runners = [summarize_runner(r) for r in (data.get("runners") or [])]
  return {
    "ok": True,
    "total_count": data.get("total_count"),
    "runners": runners,
    "busy_runners": [r for r in runners if r.get("busy")],
    "offline_runners": [r for r in runners if r.get("status") != "online"],
  }


def trigger_workflow_dispatch(
  token: str,
  owner: str,
  repo: str,
  *,
  workflow: str,
  ref: str,
  inputs: dict[str, str] | None = None,
) -> dict[str, Any]:
  wf = urllib.parse.quote(workflow, safe="")
  body: dict[str, Any] = {"ref": ref}
  if inputs:
    body["inputs"] = inputs
  data = github_request(
    "POST",
    f"/repos/{owner}/{repo}/actions/workflows/{wf}/dispatches",
    token,
    body=body,
  )
  if not _api_ok(data):
    return data
  return {"ok": True, "workflow": workflow, "ref": ref, "http_status": data.get("_http_status", 204)}


def rerun_workflow_run(token: str, owner: str, repo: str, run_id: int) -> dict[str, Any]:
  data = github_request("POST", f"/repos/{owner}/{repo}/actions/runs/{run_id}/rerun", token, body={})
  if not _api_ok(data):
    return data
  return {"ok": True, "rerun_run_id": run_id, "http_status": data.get("_http_status", 201)}


def find_latest_run_for_ref(
  token: str,
  owner: str,
  repo: str,
  *,
  workflow: str,
  ref: str,
) -> dict[str, Any]:
  data = list_workflow_runs(token, owner, repo, workflow=workflow, branch=ref, per_page=1)
  if not data.get("ok", True) and data.get("error"):
    return data
  runs = data.get("runs") or []
  if not runs:
    return {"ok": False, "error": "no_runs_found", "workflow": workflow, "ref": ref}
  return {"ok": True, "run": runs[0]}


def summarize_pull_request(pr: dict[str, Any]) -> dict[str, Any]:
  return {
    "number": pr.get("number"),
    "title": pr.get("title"),
    "state": pr.get("state"),
    "draft": pr.get("draft"),
    "merged": pr.get("merged"),
    "head": (pr.get("head") or {}).get("ref"),
    "base": (pr.get("base") or {}).get("ref"),
    "user": (pr.get("user") or {}).get("login"),
    "created_at": pr.get("created_at"),
    "updated_at": pr.get("updated_at"),
    "html_url": pr.get("html_url"),
    "mergeable": pr.get("mergeable"),
    "mergeable_state": pr.get("mergeable_state"),
  }


def list_pull_requests(
  token: str,
  owner: str,
  repo: str,
  *,
  state: str = "open",
  head: str | None = None,
  base: str | None = None,
  per_page: int = 10,
) -> dict[str, Any]:
  per_page = max(1, min(int(per_page or 10), 30))
  data = github_request(
    "GET",
    f"/repos/{owner}/{repo}/pulls",
    token,
    query={"state": state, "head": head, "base": base, "per_page": per_page},
  )
  if not _api_ok(data):
    return data
  if not isinstance(data, list):
    return {"ok": False, "error": "unexpected_response"}
  prs = [summarize_pull_request(pr) for pr in data]
  return {"ok": True, "pulls": prs, "count": len(prs)}


def get_pull_request(token: str, owner: str, repo: str, pull_number: int) -> dict[str, Any]:
  data = github_request("GET", f"/repos/{owner}/{repo}/pulls/{pull_number}", token)
  if not _api_ok(data):
    return data
  files = github_request(
    "GET",
    f"/repos/{owner}/{repo}/pulls/{pull_number}/files",
    token,
    query={"per_page": 100},
  )
  file_list = []
  if isinstance(files, list):
    file_list = [
      {
        "filename": f.get("filename"),
        "status": f.get("status"),
        "additions": f.get("additions"),
        "deletions": f.get("deletions"),
        "changes": f.get("changes"),
      }
      for f in files
    ]
  return {
    "ok": True,
    "pull": summarize_pull_request(data),
    "body": (data.get("body") or "")[:8000],
    "files": file_list,
    "files_changed": len(file_list),
  }


def create_pull_request(
  token: str,
  owner: str,
  repo: str,
  *,
  title: str,
  head: str,
  base: str,
  body: str = "",
  draft: bool = False,
) -> dict[str, Any]:
  data = github_request(
    "POST",
    f"/repos/{owner}/{repo}/pulls",
    token,
    body={"title": title, "head": head, "base": base, "body": body, "draft": draft},
  )
  if not _api_ok(data):
    return data
  return {"ok": True, "pull": summarize_pull_request(data), "html_url": data.get("html_url")}


def create_pull_request_review(
  token: str,
  owner: str,
  repo: str,
  pull_number: int,
  *,
  body: str,
  event: str = "COMMENT",
) -> dict[str, Any]:
  event = (event or "COMMENT").upper()
  if event not in ("APPROVE", "REQUEST_CHANGES", "COMMENT"):
    return {"ok": False, "error": "event must be APPROVE, REQUEST_CHANGES, or COMMENT"}
  data = github_request(
    "POST",
    f"/repos/{owner}/{repo}/pulls/{pull_number}/reviews",
    token,
    body={"body": body, "event": event},
  )
  if not _api_ok(data):
    return data
  return {"ok": True, "review_id": data.get("id"), "state": data.get("state"), "pull_number": pull_number}


def merge_pull_request(
  token: str,
  owner: str,
  repo: str,
  pull_number: int,
  *,
  merge_method: str = "squash",
  commit_title: str = "",
) -> dict[str, Any]:
  method = (merge_method or "squash").lower()
  if method not in ("merge", "squash", "rebase"):
    return {"ok": False, "error": "merge_method must be merge, squash, or rebase"}
  body: dict[str, Any] = {"merge_method": method}
  if commit_title:
    body["commit_title"] = commit_title[:250]
  data = github_request(
    "PUT",
    f"/repos/{owner}/{repo}/pulls/{pull_number}/merge",
    token,
    body=body,
  )
  if not _api_ok(data):
    return data
  return {
    "ok": True,
    "merged": data.get("merged"),
    "sha": data.get("sha"),
    "pull_number": pull_number,
  }


def add_pull_request_labels(
  token: str,
  owner: str,
  repo: str,
  pull_number: int,
  labels: list[str],
) -> dict[str, Any]:
  clean = [str(l).strip() for l in labels if str(l).strip()]
  if not clean:
    return {"ok": True, "labels": [], "skipped": True}
  data = github_request(
    "POST",
    f"/repos/{owner}/{repo}/issues/{pull_number}/labels",
    token,
    body={"labels": clean[:10]},
  )
  if not _api_ok(data):
    return data
  if isinstance(data, list):
    return {"ok": True, "labels": [x.get("name") for x in data]}
  return {"ok": True, "labels": clean}


def get_combined_status(
  token: str,
  owner: str,
  repo: str,
  ref: str,
) -> dict[str, Any]:
  data = github_request("GET", f"/repos/{owner}/{repo}/commits/{ref}/status", token)
  if not _api_ok(data):
    return data
  return {
    "ok": True,
    "state": data.get("state"),
    "statuses": data.get("statuses") or [],
  }


def get_pull_request_labels(
  token: str,
  owner: str,
  repo: str,
  pull_number: int,
) -> dict[str, Any]:
  data = github_request("GET", f"/repos/{owner}/{repo}/issues/{pull_number}/labels", token)
  if not _api_ok(data):
    return data
  if not isinstance(data, list):
    return {"ok": False, "error": "unexpected_response"}
  return {"ok": True, "labels": [x.get("name") for x in data]}


def summarize_issue(issue: dict[str, Any]) -> dict[str, Any]:
  return {
    "number": issue.get("number"),
    "title": issue.get("title"),
    "state": issue.get("state"),
    "html_url": issue.get("html_url"),
    "labels": [l.get("name") for l in (issue.get("labels") or []) if isinstance(l, dict)],
  }


def create_issue(
  token: str,
  owner: str,
  repo: str,
  *,
  title: str,
  body: str = "",
  labels: list[str] | None = None,
) -> dict[str, Any]:
  payload: dict[str, Any] = {"title": title[:250], "body": body[:65000]}
  if labels:
    payload["labels"] = [str(l).strip() for l in labels if str(l).strip()][:10]
  data = github_request("POST", f"/repos/{owner}/{repo}/issues", token, body=payload)
  if not _api_ok(data):
    return data
  return {
    "ok": True,
    "issue": summarize_issue(data),
    "html_url": data.get("html_url"),
    "number": data.get("number"),
  }


def search_issues(
  token: str,
  owner: str,
  repo: str,
  *,
  query: str,
  state: str = "open",
  per_page: int = 10,
) -> dict[str, Any]:
  q = f"repo:{owner}/{repo} is:issue is:{state} {query}".strip()
  data = github_request(
    "GET",
    "/search/issues",
    token,
    query={"q": q, "per_page": max(1, min(per_page, 30))},
  )
  if not _api_ok(data):
    return data
  items = data.get("items") or []
  issues = [summarize_issue(x) for x in items if isinstance(x, dict)]
  return {"ok": True, "issues": issues, "count": data.get("total_count", len(issues))}


def list_directory(
  token: str,
  owner: str,
  repo: str,
  path: str,
  *,
  ref: str = "",
) -> dict[str, Any]:
  query = {"ref": ref} if ref else None
  data = github_request("GET", f"/repos/{owner}/{repo}/contents/{path.strip('/')}", token, query=query)
  if not _api_ok(data):
    return data
  if isinstance(data, list):
    return {"ok": True, "entries": data}
  return {"ok": True, "entries": [data]}


def get_file_content(
  token: str,
  owner: str,
  repo: str,
  path: str,
  *,
  ref: str = "",
) -> dict[str, Any]:
  query = {"ref": ref} if ref else None
  data = github_request("GET", f"/repos/{owner}/{repo}/contents/{path.strip('/')}", token, query=query)
  if not _api_ok(data):
    return data
  from ai.tools.domains.platform.issue_template_lib import decode_github_content
  return {"ok": True, "path": path, "text": decode_github_content(data)}
