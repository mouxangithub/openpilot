"""Resolve @-mention context: URLs, git branch diff, past sessions."""

from __future__ import annotations

import html
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

_MAX_URL_CHARS = 48_000
_MAX_SESSION_CHARS = 48_000
_MAX_BRANCH_CHARS = 48_000
_URL_TIMEOUT_SEC = 20


class _TextExtractor(HTMLParser):
  def __init__(self) -> None:
    super().__init__()
    self._chunks: list[str] = []
    self._skip = False

  def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
    if tag in {"script", "style", "noscript"}:
      self._skip = True

  def handle_endtag(self, tag: str) -> None:
    if tag in {"script", "style", "noscript"}:
      self._skip = False
    if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"}:
      self._chunks.append("\n")

  def handle_data(self, data: str) -> None:
    if not self._skip and data.strip():
      self._chunks.append(data.strip())

  def text(self) -> str:
    return re.sub(r"\n{3,}", "\n\n", "\n".join(self._chunks)).strip()


def _normalize_url(raw: str) -> str | None:
  text = (raw or "").strip()
  if not text:
    return None
  if not re.match(r"^https?://", text, re.I):
    if re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", text, re.I):
      text = f"https://{text}"
    else:
      return None
  parsed = urlparse(text)
  if parsed.scheme not in {"http", "https"} or not parsed.netloc:
    return None
  return text


def fetch_url_context(url: str, *, max_chars: int = _MAX_URL_CHARS) -> dict[str, Any]:
  normalized = _normalize_url(url)
  if not normalized:
    return {"ok": False, "error": "invalid url"}
  max_chars = max(500, min(int(max_chars or _MAX_URL_CHARS), 100_000))
  req = urllib.request.Request(
    normalized,
    headers={"User-Agent": "op-assistant/1.0 (+https://github.com/commaai/openpilot)"},
  )
  try:
    with urllib.request.urlopen(req, timeout=_URL_TIMEOUT_SEC) as resp:
      ctype = str(resp.headers.get("Content-Type") or "")
      raw = resp.read(2_000_000)
  except urllib.error.HTTPError as exc:
    return {"ok": False, "error": f"HTTP {exc.code}", "url": normalized}
  except Exception as exc:
    return {"ok": False, "error": str(exc), "url": normalized}

  charset = "utf-8"
  m = re.search(r"charset=([\w-]+)", ctype, re.I)
  if m:
    charset = m.group(1)
  try:
    body = raw.decode(charset, errors="replace")
  except LookupError:
    body = raw.decode("utf-8", errors="replace")

  title = ""
  title_m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
  if title_m:
    title = html.unescape(re.sub(r"\s+", " ", title_m.group(1))).strip()

  if "html" in ctype.lower() or "<html" in body[:500].lower():
    parser = _TextExtractor()
    parser.feed(body)
    content = parser.text()
  else:
    content = body.strip()

  truncated = False
  if len(content) > max_chars:
    content = content[:max_chars] + "\n\n... [truncated]"
    truncated = True

  return {
    "ok": True,
    "type": "url",
    "url": normalized,
    "title": title or normalized,
    "content": content,
    "truncated": truncated,
  }


def fetch_branch_context(*, branch: str = "", max_chars: int = _MAX_BRANCH_CHARS) -> dict[str, Any]:
  from ai.tools.domains.devops.git_tools import _git, git_diff, git_status

  max_chars = max(500, min(int(max_chars or _MAX_BRANCH_CHARS), 100_000))
  status = git_status()
  if not status.get("ok"):
    return {"ok": False, "error": status.get("error") or "git status failed"}

  current = (branch or status.get("branch") or "").strip() or "HEAD"
  lines = [
    f"# Branch: {current}",
    f"HEAD: {status.get('head') or '—'}",
    f"Dirty files: {status.get('dirty_count', 0)}",
    "",
  ]

  merged = False
  for base in ("origin/main", "origin/master", "origin/master-c3", "main", "master", "master-c3"):
    mb = _git(["merge-base", base, "HEAD"], timeout=20)
    if not mb.get("ok") or not mb.get("stdout"):
      continue
    diff = _git(["diff", f"{mb['stdout']}...HEAD"], timeout=60)
    if diff.get("stdout"):
      lines.append(f"## Diff vs {base} ({mb['stdout'][:12]})")
      lines.append(diff["stdout"])
      merged = True
      break

  wt = git_diff()
  if wt.get("stdout"):
    lines.append("## Uncommitted changes")
    lines.append(wt["stdout"])

  stat = git_diff(stat=True)
  if stat.get("stdout") and not merged:
    lines.append("## Diff stat")
    lines.append(stat["stdout"])

  content = "\n".join(lines).strip()
  truncated = False
  if len(content) > max_chars:
    content = content[:max_chars] + "\n\n... [truncated]"
    truncated = True

  return {
    "ok": True,
    "type": "branch",
    "branch": current,
    "title": current,
    "content": content or f"(no diff on branch {current})",
    "truncated": truncated,
  }


def fetch_session_context(session_id: str, *, max_chars: int = _MAX_SESSION_CHARS) -> dict[str, Any]:
  from ai.tools.session_store import get_session_by_id
  from openpilot.common.params import Params

  sid = (session_id or "").strip()
  if not sid:
    return {"ok": False, "error": "session_id required"}

  result = get_session_by_id(Params(), sid)
  if not result.get("ok"):
    return result

  session = result.get("session") or {}
  title = str(session.get("title") or session.get("preview") or sid)
  messages = session.get("messages") or []
  lines = [f"# Past chat: {title}", f"session_id: {sid}", ""]
  for msg in messages[-40:]:
    role = str(msg.get("role") or "unknown")
    content = msg.get("content")
    if isinstance(content, list):
      text = "\n".join(
        str(p.get("text") or "")
        for p in content
        if isinstance(p, dict) and p.get("type") == "text"
      ).strip()
    else:
      text = str(content or "").strip()
    if not text:
      continue
    lines.append(f"**{role}**: {text[:2000]}")

  content = "\n\n".join(lines)
  truncated = False
  max_chars = max(500, min(int(max_chars or _MAX_SESSION_CHARS), 100_000))
  if len(content) > max_chars:
    content = content[:max_chars] + "\n\n... [truncated]"
    truncated = True

  return {
    "ok": True,
    "type": "session",
    "session_id": sid,
    "title": title,
    "content": content,
    "truncated": truncated,
  }
