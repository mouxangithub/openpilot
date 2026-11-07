"""GitHub forge adapter (wraps github_api_client)."""

from __future__ import annotations

from typing import Any

from ai.tools import github_api_client as gh


class GitHubForge:
  name = "github"

  def verify_token(self, token: str) -> dict[str, Any]:
    return gh.verify_token(token)

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
    return gh.create_pull_request(
      token, owner, repo, title=title, head=head, base=base, body=body, draft=draft,
    )

  def list_merge_requests(
    self,
    token: str,
    owner: str,
    repo: str,
    *,
    state: str = "open",
    per_page: int = 10,
  ) -> dict[str, Any]:
    return gh.list_pull_requests(token, owner, repo, state=state, per_page=per_page)

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
    return gh.create_issue(token, owner, repo, title=title, body=body, labels=labels)

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
    return gh.search_issues(token, owner, repo, query=query, state=state, per_page=per_page)

  def list_issue_templates(
    self,
    token: str,
    owner: str,
    repo: str,
  ) -> dict[str, Any]:
    from ai.tools.issue_template_lib import _parse_github_issue_yaml

    listing = gh.list_directory(token, owner, repo, ".github/ISSUE_TEMPLATE")
    if not listing.get("ok"):
      return listing
    templates: list[dict[str, Any]] = []
    for entry in listing.get("entries") or []:
      if not isinstance(entry, dict):
        continue
      name = entry.get("name") or ""
      if not name.endswith((".yml", ".yaml")):
        continue
      path = entry.get("path") or f".github/ISSUE_TEMPLATE/{name}"
      file_data = gh.get_file_content(token, owner, repo, path)
      if not file_data.get("ok"):
        continue
      parsed = _parse_github_issue_yaml(file_data.get("text") or "", name)
      if parsed:
        parsed["path"] = path
        templates.append(parsed)
    return {"ok": True, "templates": templates, "count": len(templates)}
