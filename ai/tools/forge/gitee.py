"""Gitee API v5 adapter for pull requests."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API_BASE = "https://gitee.com/api/v5"


def _request(
  method: str,
  path: str,
  token: str,
  *,
  query: dict[str, Any] | None = None,
  body: dict[str, Any] | None = None,
  timeout: float = 30.0,
) -> dict[str, Any]:
  q = {"access_token": token}
  if query:
    q.update({k: v for k, v in query.items() if v is not None and v != ""})
  url = API_BASE + path + "?" + urllib.parse.urlencode(q)
  data = None
  headers = {"User-Agent": "openpilot-op-assistant", "Accept": "application/json"}
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
        parsed["ok"] = True
      return parsed if isinstance(parsed, dict) else {"ok": True, "data": parsed}
  except urllib.error.HTTPError as e:
    detail = ""
    try:
      detail = e.read().decode("utf-8", errors="replace")
      parsed = json.loads(detail) if detail else {}
      msg = parsed.get("message") if isinstance(parsed, dict) else detail
    except Exception:
      msg = detail or str(e)
    return {"ok": False, "error": "gitee_api_error", "http_status": e.code, "message": msg}
  except urllib.error.URLError as e:
    return {"ok": False, "error": "network_error", "message": str(e.reason)}


class GiteeForge:
  name = "gitee"

  def verify_token(self, token: str) -> dict[str, Any]:
    data = _request("GET", "/user", token, timeout=15)
    if not data.get("ok", True) and data.get("error"):
      return {"ok": False, "valid": False, **data}
    if data.get("login") or data.get("name"):
      return {"ok": True, "valid": True, "login": data.get("login"), "name": data.get("name")}
    return {"ok": False, "valid": False, "message": data.get("message") or "invalid token"}

  def create_merge_request(
    self,
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
    del draft  # Gitee has no draft PR in v5 basic API
    payload = {
      "title": title[:250],
      "head": head,
      "base": base,
      "body": body[:65000],
    }
    data = _request("POST", f"/repos/{owner}/{repo}/pulls", token, body=payload)
    if not data.get("ok", True) and data.get("error"):
      return data
    html_url = data.get("html_url") or data.get("url")
    return {
      "ok": True,
      "html_url": html_url,
      "pull": {
        "number": data.get("number") or data.get("id"),
        "title": data.get("title"),
        "state": data.get("state"),
        "html_url": html_url,
      },
    }

  def list_merge_requests(
    self,
    token: str,
    owner: str,
    repo: str,
    *,
    state: str = "open",
    per_page: int = 10,
  ) -> dict[str, Any]:
    data = _request(
      "GET",
      f"/repos/{owner}/{repo}/pulls",
      token,
      query={"state": state, "per_page": max(1, min(per_page, 30))},
    )
    if isinstance(data, list):
      pulls = [
        {
          "number": pr.get("number") or pr.get("id"),
          "title": pr.get("title"),
          "state": pr.get("state"),
          "html_url": pr.get("html_url") or pr.get("url"),
        }
        for pr in data
      ]
      return {"ok": True, "pulls": pulls, "count": len(pulls)}
    if not data.get("ok", True) and data.get("error"):
      return data
    return {"ok": True, "pulls": [], "count": 0}

  def create_issue(
    self,
    token: str,
    owner: str,
    repo: str,
    *,
    title: str,
    body: str = "",
    labels: list[str] | None = None,
  ) -> dict[str, Any]:
    payload = {"title": title[:250], "body": body[:65000]}
    if labels:
      payload["labels"] = ",".join(str(l).strip() for l in labels if str(l).strip())[:200]
    data = _request("POST", f"/repos/{owner}/{repo}/issues", token, body=payload)
    if not data.get("ok", True) and data.get("error"):
      return data
    html_url = data.get("html_url") or data.get("url")
    return {
      "ok": True,
      "issue": {
        "number": data.get("number") or data.get("id"),
        "title": data.get("title"),
        "state": data.get("state"),
        "html_url": html_url,
      },
      "html_url": html_url,
      "number": data.get("number") or data.get("id"),
    }

  def search_issues(
    self,
    token: str,
    owner: str,
    repo: str,
    *,
    query: str,
    state: str = "open",
    per_page: int = 10,
  ) -> dict[str, Any]:
    data = _request(
      "GET",
      f"/repos/{owner}/{repo}/issues",
      token,
      query={"state": state, "per_page": max(1, min(per_page, 30)), "q": query},
    )
    if isinstance(data, list):
      issues = [
        {
          "number": it.get("number") or it.get("id"),
          "title": it.get("title"),
          "state": it.get("state"),
          "html_url": it.get("html_url") or it.get("url"),
        }
        for it in data
        if query.lower() in str(it.get("title", "")).lower()
      ]
      return {"ok": True, "issues": issues, "count": len(issues)}
    if not data.get("ok", True) and data.get("error"):
      return data
    return {"ok": True, "issues": [], "count": 0}

  def list_issue_templates(self, token: str, owner: str, repo: str) -> dict[str, Any]:
    del token, owner, repo
    return {"ok": True, "templates": [], "count": 0}
