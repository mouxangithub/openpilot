"""Fetch community wiki repos (GitHub / MediaWiki) into the RAG knowledge base."""

from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ai.fork.community_profiles import list_known_forks, match_community_profile
from ai.fork.repo_scan import scan_openpilot_repo
from ai.system.paths import openpilot_root

AI_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = AI_DIR / "data" / "wiki_cache"
USER_AGENT = "op-assistant-wiki-ingest/1.0"
MAX_CHUNK = 2000
MAX_FILES_DEFAULT = 0  # 0 = no per-source file cap (full wiki / repo)
SKIP_PATH_PARTS = ("/node_modules/", "/.git/", "/images/", "/assets/", "/_book/")


def _slice_by_max(items: list, max_files: int) -> list:
  if max_files <= 0:
    return items
  return items[:max_files]


def _list_limit(max_files: int) -> int:
  return 999_999 if max_files <= 0 else max_files


def _slug(text: str, *, max_len: int = 64) -> str:
  s = re.sub(r"[^\w\u4e00-\u9fff]+", "_", (text or "").strip().lower())
  return s.strip("_")[:max_len] or "doc"


def _http_get(url: str, *, accept: str = "*/*", timeout: int = 45) -> tuple[int, str]:
  req = urllib.request.Request(
    url,
    headers={
      "User-Agent": USER_AGENT,
      "Accept": accept,
    },
  )
  try:
    with urllib.request.urlopen(req, timeout=timeout) as resp:
      body = resp.read().decode("utf-8", errors="replace")
      return int(resp.status), body
  except urllib.error.HTTPError as exc:
    try:
      body = exc.read().decode("utf-8", errors="replace")
    except Exception:
      body = str(exc)
    return int(exc.code), body


def parse_wiki_source(url: str) -> dict[str, Any] | None:
  """Parse registry wiki URL into fetch plan."""
  url = (url or "").strip().rstrip("/")
  if not url:
    return None

  m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/wiki(?:/.*)?$", url, re.I)
  if m:
    return {
      "kind": "github_wiki",
      "owner": m.group(1),
      "repo": m.group(2),
      "slug": f"{m.group(1)}/{m.group(2)}-wiki",
    }

  m = re.match(r"https?://github\.com/([^/]+)/([^/]+)(?:/tree/([^/]+))?(?:/.*)?$", url, re.I)
  if m:
    return {
      "kind": "repo",
      "owner": m.group(1),
      "repo": m.group(2),
      "branch": m.group(3),
      "slug": f"{m.group(1)}/{m.group(2)}",
    }

  m = re.match(r"https?://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)$", url, re.I)
  if m:
    return {
      "kind": "raw_file",
      "owner": m.group(1),
      "repo": m.group(2),
      "branch": m.group(3),
      "path": m.group(4),
      "slug": f"{m.group(1)}/{m.group(2)}",
    }

  if "github.com" not in url.lower():
    discourse = _parse_discourse_url(url)
    if discourse:
      return discourse
    mw = _parse_mediawiki_url(url)
    if mw:
      return mw

  return None


def _parse_discourse_url(url: str) -> dict[str, Any] | None:
  m = re.match(r"https?://([^/]+)/c/[^/]+/(\d+)", url.strip(), re.I)
  if not m:
    return None
  host = m.group(1).lower()
  category_id = m.group(2)
  return {
    "kind": "discourse",
    "base_url": f"https://{host}",
    "category_id": category_id,
    "slug": f"{host.replace('.', '_')}_c_{category_id}",
  }


def _parse_mediawiki_url(url: str) -> dict[str, Any] | None:
  m = re.match(r"https?://([^/#?]+)", url.strip())
  if not m:
    return None
  host = m.group(1).lower()
  if not (host.endswith("wiki.gg") or host.endswith(".wiki") or "/wiki" in url.lower()):
    return None
  return {
    "kind": "mediawiki",
    "base_url": f"https://{host}",
    "slug": host.replace(".", "_"),
  }


def _mediawiki_query(base_url: str, params: dict[str, str]) -> dict[str, Any]:
  q = {"format": "json", **params}
  url = f"{base_url.rstrip('/')}/api.php?{urllib.parse.urlencode(q)}"
  status, body = _http_get(url, accept="application/json")
  if status != 200:
    return {}
  try:
    data = json.loads(body)
    return data if isinstance(data, dict) else {}
  except json.JSONDecodeError:
    return {}


def _list_mediawiki_pages(base_url: str, *, limit: int = 80) -> list[str]:
  titles: list[str] = []
  unlimited = limit <= 0
  effective_limit = _list_limit(limit)
  apcontinue: str | None = None
  while unlimited or len(titles) < effective_limit:
    page_size = 50 if unlimited else min(50, effective_limit - len(titles))
    params: dict[str, str] = {
      "action": "query",
      "list": "allpages",
      "aplimit": str(page_size),
      "apnamespace": "0",
    }
    if apcontinue:
      params["apcontinue"] = apcontinue
    data = _mediawiki_query(base_url, params)
    for page in (data.get("query") or {}).get("allpages") or []:
      title = str(page.get("title") or "").strip()
      if title and not title.startswith("Talk:"):
        titles.append(title)
    apcontinue = (data.get("continue") or {}).get("apcontinue")
    if not apcontinue:
      break
  return titles if unlimited else titles[:effective_limit]


def _fetch_mediawiki_page(base_url: str, title: str) -> str:
  data = _mediawiki_query(
    base_url,
    {
      "action": "query",
      "prop": "revisions",
      "rvprop": "content",
      "rvslots": "main",
      "titles": title,
    },
  )
  pages = (data.get("query") or {}).get("pages") or {}
  for _pid, page in pages.items():
    revs = page.get("revisions") or []
    if not revs:
      continue
    slots = revs[0].get("slots") or {}
    main = slots.get("main") or {}
    content = main.get("content")
    if isinstance(content, str):
      return content
  return ""


def _strip_wikitext(text: str) -> str:
  text = text or ""
  text = re.sub(r"<[^>]+>", " ", text)
  text = re.sub(r"\{\{[^}]+\}\}", "", text)
  text = re.sub(r"\[\[([^|\]]+\|)?([^\]]+)\]\]", r"\2", text)
  text = re.sub(r"'''+?", "", text)
  text = re.sub(r"^=+\s*", "", text, flags=re.M)
  text = re.sub(r"\n{3,}", "\n\n", text)
  return text.strip()


def _discourse_get_json(base_url: str, path: str) -> dict[str, Any]:
  url = f"{base_url.rstrip('/')}{path}"
  status, body = _http_get(url, accept="application/json")
  if status != 200:
    return {}
  try:
    data = json.loads(body)
    return data if isinstance(data, dict) else {}
  except json.JSONDecodeError:
    return {}


def _topic_tag_slugs(topic: dict[str, Any]) -> set[str]:
  out: set[str] = set()
  for tag in topic.get("tags") or []:
    if isinstance(tag, dict):
      out.add(str(tag.get("slug") or tag.get("name") or ""))
    else:
      out.add(str(tag))
  return {t for t in out if t}


def _discourse_listing_is_doc(
  topic: dict[str, Any],
  *,
  doc_filter: bool,
  doc_tags: set[str],
  max_posts: int,
) -> bool:
  if not doc_filter:
    return True
  if topic.get("pinned"):
    return True
  if doc_tags & _topic_tag_slugs(topic):
    return True
  if int(topic.get("posts_count") or 0) <= max(1, max_posts):
    return True
  return False


def _list_discourse_category_topics(
  base_url: str,
  category_id: str,
  *,
  limit: int = 80,
  doc_filter: bool = True,
  doc_tags: set[str] | None = None,
  max_posts: int = 3,
) -> list[dict[str, Any]]:
  tags = doc_tags or {"docs-auto-sync"}
  topics: list[dict[str, Any]] = []
  page = 0
  while len(topics) < limit and page < 12:
    data = _discourse_get_json(base_url, f"/c/{category_id}.json?page={page}")
    batch = (data.get("topic_list") or {}).get("topics") or []
    if not batch:
      break
    for topic in batch:
      if not _discourse_listing_is_doc(
        topic, doc_filter=doc_filter, doc_tags=tags, max_posts=max_posts
      ):
        continue
      topics.append(topic)
      if len(topics) >= limit:
        break
    if not (data.get("topic_list") or {}).get("more_topics_url"):
      break
    page += 1
  return topics[:limit]


def _fetch_discourse_topic_op(base_url: str, topic_id: int, topic_slug: str) -> tuple[str, str]:
  data = _discourse_get_json(base_url, f"/t/{topic_slug}/{topic_id}.json")
  posts = (data.get("post_stream") or {}).get("posts") or []
  if not posts:
    return "", ""
  cooked = str(posts[0].get("cooked") or "")
  title = str(data.get("title") or topic_slug)
  plain = _strip_html(cooked)
  return title, plain


def _strip_html(raw: str) -> str:
  text = raw or ""
  text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
  text = re.sub(r"</p>", "\n", text, flags=re.I)
  text = re.sub(r"</h[1-6]>", "\n", text, flags=re.I)
  text = re.sub(r"</li>", "\n", text, flags=re.I)
  text = re.sub(r"</tr>", "\n", text, flags=re.I)
  text = re.sub(r"<td[^>]*>", " | ", text, flags=re.I)
  text = re.sub(r"<th[^>]*>", " | ", text, flags=re.I)
  text = re.sub(r"<[^>]+>", " ", text)
  text = html.unescape(text)
  text = re.sub(r"[ \t]+\n", "\n", text)
  text = re.sub(r"\n{3,}", "\n\n", text)
  text = re.sub(r" +", " ", text)
  return text.strip()


def _repo_default_branch(owner: str, repo: str) -> str:
  status, body = _http_get(
    f"https://api.github.com/repos/{owner}/{repo}",
    accept="application/vnd.github+json",
  )
  if status != 200:
    return "main"
  try:
    data = json.loads(body)
    return str(data.get("default_branch") or "main")
  except json.JSONDecodeError:
    return "main"


def _list_repo_markdown(owner: str, repo: str, branch: str) -> tuple[str, list[str]]:
  def _fetch_tree(ref: str) -> tuple[int, dict[str, Any]]:
    status, body = _http_get(
      f"https://api.github.com/repos/{owner}/{repo}/git/trees/{ref}?recursive=1",
      accept="application/vnd.github+json",
    )
    if status != 200:
      return status, {}
    try:
      return status, json.loads(body)
    except json.JSONDecodeError:
      return status, {}

  status, data = _fetch_tree(branch)
  if status != 200:
    fallback = _repo_default_branch(owner, repo)
    if fallback and fallback != branch:
      status, data = _fetch_tree(fallback)
      if status == 200:
        branch = fallback
  if status != 200:
    return "", []
  tree_sha = str(data.get("sha") or "")
  paths: list[str] = []
  for item in data.get("tree") or []:
    if item.get("type") != "blob":
      continue
    path = str(item.get("path") or "")
    if not path.lower().endswith(".md"):
      continue
    low = path.lower()
    if any(part in low for part in SKIP_PATH_PARTS):
      continue
    if path.lower() in ("license.md",):
      continue
    paths.append(path)
  return tree_sha, sorted(paths)


# Fallback when GitHub wiki git tree is unavailable.
_GITHUB_WIKI_PAGES: dict[str, list[str]] = {
  "commaai/openpilot": [
    "Home", "FAQ", "Troubleshooting", "SSH", "Tuning", "comma-three", "Installing-openpilot",
  ],
}


def _list_github_wiki_page_names(owner: str, repo: str) -> list[str]:
  wiki_repo = f"{repo}.wiki"
  branch = _repo_default_branch(owner, wiki_repo)
  _tree_sha, paths = _list_repo_markdown(owner, wiki_repo, branch)
  if paths:
    names: list[str] = []
    for path in paths:
      if path.lower().endswith(".md"):
        names.append(path[:-3])
      else:
        names.append(path)
    return names
  return list(_GITHUB_WIKI_PAGES.get(f"{owner}/{repo}", ["Home", "FAQ", "Troubleshooting"]))


def _strip_markdown(md: str) -> str:
  text = md or ""
  text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
  text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
  text = re.sub(r"```[\s\S]*?```", lambda m: m.group(0).replace("```", ""), text)
  text = re.sub(r"^#+\s*", "", text, flags=re.M)
  text = re.sub(r"[*_`]", "", text)
  text = re.sub(r"\n{3,}", "\n\n", text)
  return text.strip()


def _chunk_text(text: str, *, doc_slug: str) -> list[dict[str, str]]:
  text = text.strip()
  if not text:
    return []
  if len(text) <= MAX_CHUNK:
    return [{"id_suffix": "0", "text": text}]

  parts = re.split(r"\n(?=## )", text)
  chunks: list[dict[str, str]] = []
  buf = ""
  idx = 0

  def flush() -> None:
    nonlocal buf, idx
    t = buf.strip()
    if t:
      chunks.append({"id_suffix": str(idx), "text": t})
      idx += 1
    buf = ""

  for part in parts:
    if len(part) > MAX_CHUNK:
      flush()
      start = 0
      while start < len(part):
        piece = part[start : start + MAX_CHUNK].strip()
        if piece:
          chunks.append({"id_suffix": str(idx), "text": piece})
          idx += 1
        start += MAX_CHUNK
      continue
    candidate = f"{buf}\n{part}".strip() if buf else part
    if len(candidate) > MAX_CHUNK and buf:
      flush()
      buf = part
    else:
      buf = candidate
    if len(buf) >= MAX_CHUNK:
      flush()
  flush()

  if not chunks:
    return [{"id_suffix": "0", "text": text[:MAX_CHUNK]}]
  return chunks


def _manifest_path(source_slug: str) -> Path:
  safe = source_slug.replace("/", "__")
  return CACHE_DIR / safe / "manifest.json"


def _load_manifest(source_slug: str) -> dict[str, Any]:
  path = _manifest_path(source_slug)
  if not path.is_file():
    return {}
  try:
    return json.loads(path.read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError):
    return {}


def _save_manifest(source_slug: str, payload: dict[str, Any]) -> None:
  path = _manifest_path(source_slug)
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _fetch_repo_file(owner: str, repo: str, branch: str, path: str) -> str:
  encoded = "/".join(urllib.request.quote(seg) for seg in path.split("/"))
  url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{encoded}"
  status, body = _http_get(url)
  if status != 200 or len(body) < 40:
    return ""
  return body


def _fetch_repo_json(owner: str, repo: str, branch: str, path: str) -> str:
  raw = _fetch_repo_file(owner, repo, branch, path)
  if not raw:
    return ""
  try:
    data = json.loads(raw)
    return json.dumps(data, ensure_ascii=False, indent=2)
  except json.JSONDecodeError:
    return raw


def ingest_wiki_source(
  params: Any,
  source: dict[str, Any],
  *,
  community_id: str,
  community_name: str = "",
  tags: list[str] | None = None,
  max_files: int = MAX_FILES_DEFAULT,
  force: bool = False,
) -> dict[str, Any]:
  """Ingest one wiki source into RAG (sync, keyword store; embed on next reindex)."""
  from ai.tools.rag_store import upsert_document_sync

  kind = source.get("kind")
  slug = str(source.get("slug") or "wiki")
  base_tags = ["wiki", "community", _slug(community_id or slug, max_len=32)]
  if community_name:
    base_tags.append(_slug(community_name, max_len=24))
  if tags:
    base_tags.extend(tags)

  indexed = 0
  skipped = 0
  errors: list[str] = []
  tree_sha = ""
  files: list[tuple[str, str]] = []

  if kind == "discourse":
    base_url = str(source.get("base_url") or "")
    category_id = str(source.get("category_id") or "")
    if not base_url or not category_id:
      return {"ok": False, "error": "invalid discourse source", "source": source}
    doc_filter = bool(source.get("discourse_doc_filter", True))
    max_posts = int(source.get("discourse_max_posts") or 3)
    doc_tags = {str(t) for t in (source.get("discourse_tags") or ["docs-auto-sync"]) if t}
    topic_rows = _list_discourse_category_topics(
      base_url,
      category_id,
      limit=_list_limit(max_files),
      doc_filter=doc_filter,
      doc_tags=doc_tags,
      max_posts=max_posts,
    )
    tree_sha = "-".join(
      f"{t.get('id')}:{t.get('bumped_at')}" for t in topic_rows[: _list_limit(max_files)]
    ) or f"discourse-{category_id}-empty"
    prev = _load_manifest(slug)
    if not force and prev.get("tree_sha") == tree_sha and prev.get("indexed", 0) > 0:
      return {"ok": True, "skipped": True, "reason": "unchanged", "slug": slug, "indexed": 0}
    for topic in topic_rows:
      topic_id = int(topic.get("id") or 0)
      topic_slug = str(topic.get("slug") or topic_id)
      if not topic_id:
        continue
      title, plain = _fetch_discourse_topic_op(base_url, topic_id, topic_slug)
      if not plain:
        continue
      body = f"# {title}\n\n{plain}" if title else plain
      files.append((f"{topic_slug}::{topic_id}", body))
    owner = ""
    repo = ""
    branch = ""
  elif kind == "mediawiki":
    base_url = str(source.get("base_url") or "")
    if not base_url:
      return {"ok": False, "error": "invalid mediawiki source", "source": source}
    titles = _list_mediawiki_pages(base_url, limit=max_files)
    tree_sha = f"mw-{len(titles)}"
    prev = _load_manifest(slug)
    if not force and prev.get("tree_sha") == tree_sha and prev.get("indexed", 0) > 0:
      return {"ok": True, "skipped": True, "reason": "unchanged", "slug": slug, "indexed": 0}
    for title in titles:
      raw = _fetch_mediawiki_page(base_url, title)
      plain = _strip_wikitext(raw)
      if len(plain) >= 80:
        files.append((title, plain))
    owner = ""
    repo = ""
    branch = ""
  else:
    owner = source.get("owner")
    repo = source.get("repo")
    if not owner or not repo:
      return {"ok": False, "error": "invalid source", "source": source}

    slug = str(source.get("slug") or f"{owner}/{repo}")
    branch = str(source.get("branch") or _repo_default_branch(owner, repo))

    if kind == "github_wiki":
      pages = _list_github_wiki_page_names(owner, repo)
      tree_sha = f"wiki-pages-{len(pages)}"
      prev = _load_manifest(slug)
      if not force and prev.get("tree_sha") == tree_sha and prev.get("indexed", 0) > 0:
        return {"ok": True, "skipped": True, "reason": "unchanged", "slug": slug, "indexed": 0}
      for page in _slice_by_max(pages, max_files):
        status, raw = _http_get(f"https://raw.githubusercontent.com/wiki/{owner}/{repo}/{page}.md")
        if status != 200 or len(raw) < 80:
          continue
        files.append((page, raw))
    elif kind == "raw_file":
      path = str(source.get("path") or "README.md")
      raw = _fetch_repo_file(owner, repo, branch, path)
      if raw:
        files.append((path, raw))
      tree_sha = f"raw-{path}"
    else:
      tree_sha, paths = _list_repo_markdown(owner, repo, branch)
      extra_paths = [str(p) for p in (source.get("extra_paths") or []) if p]
      for path in extra_paths:
        if path not in paths:
          paths.append(path)
      if not paths:
        return {"ok": False, "error": f"no markdown in {owner}/{repo}@{branch}", "slug": slug}
      prev = _load_manifest(slug)
      if not force and prev.get("tree_sha") == tree_sha and prev.get("indexed", 0) > 0:
        return {"ok": True, "skipped": True, "reason": "unchanged", "slug": slug, "tree_sha": tree_sha}
      for path in _slice_by_max(paths, max_files):
        if path.lower().endswith(".json"):
          raw = _fetch_repo_json(owner, repo, branch, path)
        else:
          raw = _fetch_repo_file(owner, repo, branch, path)
        if raw:
          files.append((path, raw))

  for rel_path, raw in files:
    if kind in ("mediawiki", "discourse"):
      plain = raw
    else:
      plain = _strip_markdown(raw) if not rel_path.lower().endswith(".json") else raw
    if len(plain) < 80:
      skipped += 1
      continue
    page_slug = _slug(rel_path.replace(".md", "").replace(".json", "").replace("/", "_"))
    if kind == "discourse":
      topic_slug = rel_path.split("::", 1)[0] if "::" in rel_path else rel_path
      source_url = f"{source.get('base_url')}/t/{topic_slug}"
    elif kind == "mediawiki":
      source_url = f"{source.get('base_url')}/wiki/{urllib.parse.quote(rel_path.replace(' ', '_'))}"
    elif kind == "github_wiki":
      source_url = f"https://github.com/{owner}/{repo}/wiki/{rel_path}"
    elif kind == "raw_file":
      source_url = f"https://github.com/{owner}/{repo}/blob/{branch}/{rel_path}"
    else:
      source_url = f"https://github.com/{owner}/{repo}/blob/{branch}/{rel_path}"
    header = f"Source: {community_name or slug} — {rel_path}\n{source_url}\n\n"
    chunks = _chunk_text(plain, doc_slug=page_slug)
    for i, chunk in enumerate(chunks):
      suffix = chunk["id_suffix"]
      doc_id = f"wiki_{_slug(community_id or slug, max_len=40)}_{page_slug}_{suffix}"[:96]
      title = rel_path.replace(".md", "").replace(".json", "").replace("/", " / ")
      if kind == "discourse" and plain.startswith("# "):
        title = plain.split("\n", 1)[0].lstrip("# ").strip() or title
      if len(chunks) > 1:
        title = f"{title} ({i + 1}/{len(chunks)})"
      res = upsert_document_sync(
        params,
        title=f"Wiki: {title}",
        text=header + chunk["text"],
        tags=base_tags,
        doc_id=doc_id,
      )
      if res.get("ok"):
        indexed += 1
      else:
        errors.append(f"{rel_path}: {res.get('error')}")

  manifest = {
    "slug": slug,
    "community_id": community_id,
    "owner": owner or None,
    "repo": repo or None,
    "branch": branch or None,
    "kind": kind,
    "base_url": source.get("base_url"),
    "tree_sha": tree_sha,
    "indexed": indexed,
    "skipped": skipped,
    "at": int(time.time()),
    "errors": errors[:5],
  }
  _save_manifest(slug, manifest)
  return {
    "ok": len(errors) == 0 or indexed > 0,
    "slug": slug,
    "community_id": community_id,
    "indexed": indexed,
    "skipped": skipped,
    "tree_sha": tree_sha,
    "files_seen": len(files),
    "errors": errors[:5],
  }


def collect_wiki_sources_for_profile(profile: dict[str, Any] | None) -> list[dict[str, Any]]:
  if not profile:
    return []
  out: list[dict[str, Any]] = []
  seen: set[str] = set()
  for item in profile.get("wiki_repos") or []:
    if isinstance(item, dict):
      url = str(item.get("url") or "")
      explicit_kind = item.get("kind")
      branch = item.get("branch")
      max_files = item.get("max_files")
      extra_paths = item.get("extra_paths")
      discourse_doc_filter = item.get("discourse_doc_filter")
      discourse_max_posts = item.get("discourse_max_posts")
      discourse_tags = item.get("discourse_tags")
    else:
      url = str(item)
      explicit_kind = branch = max_files = extra_paths = None
      discourse_doc_filter = discourse_max_posts = discourse_tags = None

    if explicit_kind == "discourse":
      parsed = _parse_discourse_url(url)
    elif explicit_kind == "mediawiki":
      parsed = _parse_mediawiki_url(url)
    else:
      parsed = parse_wiki_source(url)
    if not parsed:
      continue
    if branch:
      parsed["branch"] = str(branch)
    if max_files:
      parsed["max_files"] = int(max_files)
    if extra_paths:
      parsed["extra_paths"] = list(extra_paths)
    if discourse_doc_filter is not None:
      parsed["discourse_doc_filter"] = bool(discourse_doc_filter)
    if discourse_max_posts is not None:
      parsed["discourse_max_posts"] = int(discourse_max_posts)
    if discourse_tags:
      parsed["discourse_tags"] = list(discourse_tags)
    key = parsed.get("slug") or url
    if key in seen:
      continue
    seen.add(key)
    out.append(parsed)
  return out


def ingest_wikis_for_profile(
  params: Any,
  profile: dict[str, Any],
  *,
  max_files_per_repo: int = MAX_FILES_DEFAULT,
  force: bool = False,
) -> dict[str, Any]:
  sources = collect_wiki_sources_for_profile(profile)
  if not sources:
    return {"ok": True, "indexed": 0, "repos": [], "message": "no wiki_repos in profile"}

  results: list[dict[str, Any]] = []
  total = 0
  for source in sources:
    per_repo_max = int(source.get("max_files") or max_files_per_repo)
    res = ingest_wiki_source(
      params,
      source,
      community_id=str(profile.get("id") or source.get("slug")),
      community_name=str(profile.get("name") or ""),
      tags=[_slug(a) for a in (profile.get("aliases") or [])[:3]],
      max_files=per_repo_max,
      force=force,
    )
    results.append(res)
    total += int(res.get("indexed") or 0)

  return {
    "ok": any(r.get("ok") for r in results) or total == 0,
    "community_id": profile.get("id"),
    "community_name": profile.get("name"),
    "indexed": total,
    "repos": results,
  }


def ingest_wikis_for_current_fork(
  params: Any,
  *,
  max_files_per_repo: int = MAX_FILES_DEFAULT,
  force: bool = False,
  include_all_registered: bool = False,
) -> dict[str, Any]:
  """Ingest wiki for detected community, or all registry entries if include_all_registered."""
  root = openpilot_root()
  scan = scan_openpilot_repo(root)
  profile = match_community_profile(scan)

  if include_all_registered:
    results = []
    total = 0
    for entry in list_known_forks():
      if not (entry.get("wiki_repos") or []):
        continue
      res = ingest_wikis_for_profile(
        params, entry, max_files_per_repo=max_files_per_repo, force=force
      )
      results.append(res)
      total += int(res.get("indexed") or 0)
    return {"ok": True, "mode": "all_registered", "indexed": total, "communities": results}

  if not profile:
    return {
      "ok": True,
      "indexed": 0,
      "message": "no community profile match; skip wiki ingest",
      "fork_scan": scan.get("remote_identity"),
    }

  res = ingest_wikis_for_profile(
    params, profile, max_files_per_repo=max_files_per_repo, force=force
  )
  res["mode"] = "current_fork"
  return res
