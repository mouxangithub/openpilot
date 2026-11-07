"""Platform backup / export / restore — config, memory, sessions, skills, MCP, workspace."""

from __future__ import annotations

import io
import json
import re
import tarfile
import time
from pathlib import Path
from typing import Any

from openpilot.common.params import Params

from ai.common.storage import read_param, write_param
from ai.mcp.host import MCP_SERVERS_KEY, _load_servers as _load_mcp
from ai.tools.domains.core.memory_store import NOTES_KEY, PROFILE_KEY, get_memory
from ai.tools.domains.platform.session_store import SESSIONS_KEY, get_sessions
from ai.tools.domains.platform.skill_learning import LEARNED_KEY, _load as _load_learned
from ai.core.wspace.store import _FILE_MAP, list_workspace_files, read_workspace_file, write_workspace_file

BUNDLE_VERSION = 2
OPBAK_SUFFIX = ".opbak"
BUNDLE_INNER_NAME = "bundle.json"
_EXPORTS_DIR = Path(__file__).resolve().parent.parent / "data" / "exports"

# Legacy Params keys still mirrored in some bundles.
_PARAM_KEYS = [
  "ai_context_window",
  "ai_compaction_enabled",
  "ai_compact_after_turns",
  "ai_keep_recent_turns",
  "ai_reserve_tokens",
  "ai_compaction_token_trigger",
  "ai_github_actions_pat",
  "ai_gitee_token",
  "ai_publish_config",
  "ai_issue_publish",
]

_SECRET_KEYS = {
  "ai_api_key",
  "ai_embedding_api_key",
  "ai_web_pin",
  "ai_github_actions_pat",
  "ai_gitee_token",
}


def _redact(value: str) -> str:
  if not value:
    return ""
  if len(value) <= 8:
    return "***"
  return value[:4] + "…" + value[-4:]


def _parse_model_hub_blob(raw: Any) -> dict[str, Any]:
  if isinstance(raw, dict):
    return raw
  if not raw:
    return {}
  try:
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    data = json.loads(str(raw))
    return data if isinstance(data, dict) else {}
  except Exception:
    return {}


def _redact_model_hub_blob(hub: dict[str, Any]) -> dict[str, Any]:
  out = json.loads(json.dumps(hub, ensure_ascii=False))
  for acc in out.get("accounts") or []:
    if not isinstance(acc, dict):
      continue
    key = str(acc.get("apiKey") or acc.get("api_key") or "").strip()
    if key:
      acc["apiKey"] = _redact(key)
      acc.pop("api_key", None)
  return out


def _hub_manifest_from_config(ai_cfg: dict[str, Any]) -> dict[str, Any]:
  hub = _parse_model_hub_blob(ai_cfg.get("ai_model_hub"))
  accounts = [a for a in (hub.get("accounts") or []) if isinstance(a, dict)]
  routes = 0
  primary = hub.get("primary") if isinstance(hub.get("primary"), dict) else None
  if primary and primary.get("accountId") and primary.get("model"):
    routes += 1
  for item in hub.get("fallbacks") or []:
    if isinstance(item, dict) and item.get("accountId") and item.get("model"):
      routes += 1
  primary_provider = ""
  primary_model = ""
  if primary:
    primary_model = str(primary.get("model") or "").strip()
    acc = next((a for a in accounts if str(a.get("id")) == str(primary.get("accountId"))), None)
    if acc:
      primary_provider = str(acc.get("provider") or "").strip()
  emb_routes = 0
  emb_primary = hub.get("embeddingPrimary") if isinstance(hub.get("embeddingPrimary"), dict) else None
  if emb_primary and emb_primary.get("accountId") and emb_primary.get("model"):
    emb_routes += 1
  for item in hub.get("embeddingFallbacks") or []:
    if isinstance(item, dict) and item.get("accountId") and item.get("model"):
      emb_routes += 1
  emb_model = ""
  if emb_primary:
    emb_model = str(emb_primary.get("model") or "").strip()
  return {
    "accounts": len(accounts),
    "routes": routes,
    "fallbacks": max(0, routes - 1) if routes else 0,
    "embeddingRoutes": emb_routes,
    "embeddingFallbacks": max(0, emb_routes - 1) if emb_routes else 0,
    "embeddingModel": emb_model,
    "primaryProvider": primary_provider,
    "primaryModel": primary_model,
    "configured": bool(accounts and routes),
  }


def _model_configured(ai_cfg: dict[str, Any]) -> bool:
  hub_info = _hub_manifest_from_config(ai_cfg)
  if hub_info.get("configured"):
    if hub_info.get("primaryProvider") and hub_info.get("primaryModel"):
      return True
    return bool(hub_info.get("accounts"))
  provider = str(ai_cfg.get("ai_provider") or "").strip().lower()
  model = str(ai_cfg.get("ai_model") or "").strip()
  if provider in ("opencode-zen", "opencode-go"):
    return bool(model)
  if str(ai_cfg.get("ai_api_key") or "").strip() and not ai_cfg.get("ai_api_key__redacted"):
    return bool(model)
  if ai_cfg.get("ai_api_key__redacted"):
    return bool(model)
  try:
    from ai.common.config_store import get_config_store
    return bool(str(get_config_store().read_all().get("ai_api_key") or "").strip()) and bool(model)
  except Exception:
    return False


def _export_ai_config(*, include_secrets: bool) -> dict[str, Any]:
  """Full ai_* config from config store (model, embedding, evolution, etc.)."""
  try:
    from ai.common.config_store import get_config_store
    raw = get_config_store().read_all()
  except Exception:
    raw = {}
  out: dict[str, Any] = {}
  for key, value in raw.items():
    text = "" if value is None else str(value)
    if key == "ai_model_hub" and text:
      hub = _parse_model_hub_blob(text)
      if hub and not include_secrets:
        out[key] = json.dumps(_redact_model_hub_blob(hub), ensure_ascii=False)
        out[f"{key}__redacted"] = True
      else:
        out[key] = text
      continue
    if key in _SECRET_KEYS and text and not include_secrets:
      out[key] = _redact(text)
      out[f"{key}__redacted"] = True
    else:
      out[key] = text
  return out


def _restore_ai_config(data: dict[str, Any]) -> None:
  if not isinstance(data, dict) or not data:
    return
  try:
    from ai.common.config_store import get_config_store
    store = get_config_store()
  except Exception:
    return
  for key, value in data.items():
    if not isinstance(key, str) or key.endswith("__redacted"):
      continue
    if data.get(f"{key}__redacted"):
      continue
    if not key.startswith("ai_"):
      continue
    try:
      store.put(key, value)
    except Exception:
      continue


def _read_param_map(params: Params, *, include_secrets: bool) -> dict[str, str]:
  out: dict[str, str] = {}
  for key in _PARAM_KEYS:
    raw = read_param(params, key)
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    text = str(raw or "")
    if key in _SECRET_KEYS and text and not include_secrets:
      out[key] = _redact(text)
      out[f"{key}__redacted"] = True
    else:
      out[key] = text
  return out


def _workspace_bundle() -> dict[str, str]:
  files: dict[str, str] = {}
  for logical in _FILE_MAP:
    content = read_workspace_file(logical)
    if content:
      files[logical] = content
  return files


def _learned_skill_files(params: Params) -> dict[str, str]:
  base = Path(__file__).resolve().parent.parent
  out: dict[str, str] = {}
  for entry in _load_learned(params):
    rel = str(entry.get("path") or "")
    if not rel:
      continue
    path = base / rel
    if path.is_file():
      out[rel.replace("\\", "/")] = path.read_text(encoding="utf-8", errors="replace")
  return out


def _enabled_skills(params: Params) -> list[str]:
  try:
    from ai.skills.loader import load_enabled_skill_ids
    ids = load_enabled_skill_ids(params)
    return sorted(ids) if ids else []
  except Exception:
    return []


def _restore_enabled_skills(params: Params, skills: list[str]) -> None:
  if not skills:
    return
  try:
    from ai.skills.loader import save_enabled_skill_ids
    save_enabled_skill_ids(params, list(skills))
  except Exception:
    pass


def _export_model_hub_section(params: Params, *, include_secrets: bool) -> dict[str, Any]:
  """Explicit model hub snapshot for backup manifest / cross-version restore."""
  try:
    from ai.core.llm.model_accounts import hub_for_api, load_model_hub

    hub = load_model_hub(params)
    if include_secrets:
      return hub
    return hub_for_api(params, mask_keys=True)
  except Exception:
    return {}


def build_platform_bundle(params: Params | None = None, *, include_secrets: bool = False) -> dict[str, Any]:
  """Assemble a portable bundle of platform state."""
  params = params or Params()
  mem = get_memory(params)
  sessions = get_sessions(params)
  return {
    "ok": True,
    "bundle": {
      "version": BUNDLE_VERSION,
      "exportedAt": int(time.time()),
      "includeSecrets": include_secrets,
      "ai_config": _export_ai_config(include_secrets=include_secrets),
      "model_hub": _export_model_hub_section(params, include_secrets=include_secrets),
      "enabled_skills": _enabled_skills(params),
      "memory": {
        "notes": mem.get("notes") or [],
        "vehicle_profile": mem.get("vehicle_profile") or {},
      },
      "sessions": {
        "sessions": sessions.get("sessions") or [],
        "activeId": sessions.get("activeId"),
        "savedAt": sessions.get("savedAt"),
      },
      "learned_skills": _load_learned(params),
      "learned_skill_files": _learned_skill_files(params),
      "mcp_servers": _load_mcp(params),
      "workspace": _workspace_bundle(),
      "params": _read_param_map(params, include_secrets=include_secrets),
    },
    "manifest": backup_manifest(params),
  }


def backup_manifest(params: Params | None = None) -> dict[str, Any]:
  params = params or Params()
  mem = get_memory(params)
  ws = list_workspace_files()
  ai_cfg = _export_ai_config(include_secrets=False)
  hub_info = _hub_manifest_from_config(ai_cfg)
  configured = _model_configured(ai_cfg)
  provider = hub_info.get("primaryProvider") or ai_cfg.get("ai_provider") or ""
  model = hub_info.get("primaryModel") or ai_cfg.get("ai_model") or ""
  return {
    "version": BUNDLE_VERSION,
    "modelConfigured": configured,
    "provider": provider,
    "model": model,
    "modelHubAccounts": hub_info.get("accounts", 0),
    "modelHubRoutes": hub_info.get("routes", 0),
    "modelHubFallbacks": hub_info.get("fallbacks", 0),
    "embeddingRoutes": hub_info.get("embeddingRoutes", 0),
    "embeddingFallbacks": hub_info.get("embeddingFallbacks", 0),
    "embeddingModel": hub_info.get("embeddingModel") or ai_cfg.get("ai_embedding_model") or "",
    "memoryNotes": len(mem.get("notes") or []),
    "sessions": len((get_sessions(params).get("sessions") or [])),
    "learnedSkills": len(_load_learned(params)),
    "enabledSkills": len(_enabled_skills(params)),
    "mcpServers": len(_load_mcp(params)),
    "workspaceFiles": sum(1 for f in ws if f.get("exists")),
    "workspaceKeys": [f.get("key") for f in ws if f.get("exists")],
  }


def pack_opbak(bundle: dict[str, Any]) -> bytes:
  """Pack bundle JSON into gzip tar with .opbak convention (not zip)."""
  payload = json.dumps(bundle, ensure_ascii=False, indent=2).encode("utf-8")
  buf = io.BytesIO()
  with tarfile.open(fileobj=buf, mode="w:gz") as tar:
    info = tarfile.TarInfo(name=BUNDLE_INNER_NAME)
    info.size = len(payload)
    tar.addfile(info, io.BytesIO(payload))
  return buf.getvalue()


def unpack_opbak(data: bytes) -> dict[str, Any]:
  """Extract bundle dict from .opbak bytes."""
  with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
    member = tar.getmember(BUNDLE_INNER_NAME)
    extracted = tar.extractfile(member)
    if extracted is None:
      raise ValueError("missing bundle.json in archive")
    inner = json.loads(extracted.read().decode("utf-8"))
  if not isinstance(inner, dict):
    raise ValueError("invalid bundle.json")
  return inner


def export_platform_bundle(
  params: Params | None = None,
  *,
  include_secrets: bool = False,
  write_file: bool = True,
) -> dict[str, Any]:
  """Export bundle; optionally persist under ai/data/exports for download."""
  params = params or Params()
  result = build_platform_bundle(params, include_secrets=include_secrets)
  bundle = result["bundle"]
  if not write_file:
    return {**result, "download": None}

  _EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
  stamp = time.strftime("%Y%m%d-%H%M%S")
  name = f"opassist-backup-{stamp}{OPBAK_SUFFIX}"
  path = _EXPORTS_DIR / name
  path.write_bytes(pack_opbak(bundle))
  return {
    **result,
    "download": {
      "filename": name,
      "path": str(path),
      "url": f"/api/ai/dev-assets/exports/{name}",
      "bytes": path.stat().st_size,
      "format": "opbak",
    },
  }


def _merge_notes(existing: list, incoming: list, *, mode: str) -> list:
  if mode == "replace":
    return incoming
  seen = {n.get("id") for n in existing if n.get("id")}
  merged = list(existing)
  for n in incoming:
    if n.get("id") and n["id"] in seen:
      continue
    merged.append(n)
  return merged[:80]


def restore_platform_bundle(
  params: Params,
  bundle: dict[str, Any],
  *,
  mode: str = "merge",
  sections: list[str] | None = None,
  confirm: bool = False,
) -> dict[str, Any]:
  """Restore from bundle. mode: merge | replace. sections limits what is applied."""
  if not confirm:
    inner = bundle.get("bundle") if isinstance(bundle.get("bundle"), dict) else bundle
    return {
      "ok": True,
      "needs_confirmation": True,
      "preview": {
        "version": inner.get("version"),
        "exportedAt": inner.get("exportedAt"),
        "sections": sections or [
          "ai_config", "model_hub", "enabled_skills", "memory", "sessions",
          "learned_skills", "mcp_servers", "workspace", "params",
        ],
        "manifest": {
          "provider": (inner.get("ai_config") or {}).get("ai_provider"),
          "model": (inner.get("ai_config") or {}).get("ai_model"),
          "modelHubAccounts": len((inner.get("model_hub") or {}).get("accounts") or []),
          "modelHubRoutes": (
            (1 if (inner.get("model_hub") or {}).get("primary") else 0)
            + len((inner.get("model_hub") or {}).get("fallbacks") or [])
          ),
          "embeddingModel": (inner.get("ai_config") or {}).get("ai_embedding_model"),
          "memoryNotes": len((inner.get("memory") or {}).get("notes") or []),
          "sessions": len((inner.get("sessions") or {}).get("sessions") or []),
          "learnedSkills": len(inner.get("learned_skills") or []),
          "enabledSkills": len(inner.get("enabled_skills") or []),
          "mcpServers": len(inner.get("mcp_servers") or []),
          "workspaceFiles": len(inner.get("workspace") or {}),
        },
      },
      "hint": "Set confirm=true to apply restore.",
    }

  data = bundle.get("bundle") if isinstance(bundle.get("bundle"), dict) else bundle
  if not isinstance(data, dict):
    return {"ok": False, "error": "invalid bundle"}
  ver = int(data.get("version") or 0)
  if ver not in (1, BUNDLE_VERSION):
    return {"ok": False, "error": f"unsupported bundle version (expected 1 or {BUNDLE_VERSION})"}

  allowed = set(sections or [
    "ai_config", "model_hub", "enabled_skills", "memory", "sessions",
    "learned_skills", "mcp_servers", "workspace", "params",
  ])
  applied: list[str] = []

  if "ai_config" in allowed and isinstance(data.get("ai_config"), dict):
    if mode == "replace" or data.get("ai_config"):
      _restore_ai_config(data["ai_config"])
      applied.append("ai_config")

  if "model_hub" in allowed and isinstance(data.get("model_hub"), dict) and data.get("model_hub"):
    try:
      from ai.core.llm.model_accounts import save_model_hub

      save_model_hub(params, data["model_hub"])
      applied.append("model_hub")
    except Exception:
      pass

  if "enabled_skills" in allowed and isinstance(data.get("enabled_skills"), list):
    if mode == "replace":
      _restore_enabled_skills(params, data["enabled_skills"])
    else:
      cur = set(_enabled_skills(params))
      cur.update(str(s) for s in data["enabled_skills"])
      _restore_enabled_skills(params, sorted(cur))
    applied.append("enabled_skills")

  if "memory" in allowed and isinstance(data.get("memory"), dict):
    mem = data["memory"]
    cur = get_memory(params)
    notes = mem.get("notes") or []
    profile = mem.get("vehicle_profile") or {}
    if mode == "replace":
      write_param(params, NOTES_KEY, json.dumps(notes[:80], ensure_ascii=False))
      write_param(params, PROFILE_KEY, json.dumps(profile, ensure_ascii=False))
    else:
      cur_notes = cur.get("notes") or []
      merged = _merge_notes(cur_notes, notes, mode="merge")
      write_param(params, NOTES_KEY, json.dumps(merged, ensure_ascii=False))
      cur_profile = cur.get("vehicle_profile") or {}
      cur_profile.update({k: v for k, v in profile.items() if v is not None})
      write_param(params, PROFILE_KEY, json.dumps(cur_profile, ensure_ascii=False))
    applied.append("memory")

  if "sessions" in allowed and isinstance(data.get("sessions"), dict):
    sess = data["sessions"]
    if mode == "replace":
      write_param(params, SESSIONS_KEY, json.dumps(sess, ensure_ascii=False))
    else:
      cur = get_sessions(params)
      cur_ids = {s.get("id") for s in cur.get("sessions") or []}
      merged_sessions = list(cur.get("sessions") or [])
      for s in sess.get("sessions") or []:
        if s.get("id") not in cur_ids:
          merged_sessions.append(s)
      write_param(params, SESSIONS_KEY, json.dumps({
        "sessions": merged_sessions[:30],
        "activeId": cur.get("activeId") or sess.get("activeId"),
        "savedAt": int(time.time()),
      }, ensure_ascii=False))
    applied.append("sessions")

  if "learned_skills" in allowed:
    skills = data.get("learned_skills") or []
    if mode == "replace":
      write_param(params, LEARNED_KEY, json.dumps(skills[:24], ensure_ascii=False))
    else:
      cur = _load_learned(params)
      cur_ids = {s.get("id") for s in cur}
      for s in skills:
        if s.get("id") not in cur_ids:
          cur.insert(0, s)
      write_param(params, LEARNED_KEY, json.dumps(cur[:24], ensure_ascii=False))
    base = Path(__file__).resolve().parent.parent
    for rel, content in (data.get("learned_skill_files") or {}).items():
      path = base / rel
      path.parent.mkdir(parents=True, exist_ok=True)
      if mode == "replace" or not path.is_file():
        path.write_text(content, encoding="utf-8")
    applied.append("learned_skills")

  if "mcp_servers" in allowed:
    servers = data.get("mcp_servers") or []
    if mode == "replace":
      write_param(params, MCP_SERVERS_KEY, json.dumps(servers[:16], ensure_ascii=False))
    else:
      cur = _load_mcp(params)
      cur_ids = {s.get("id") for s in cur}
      for s in servers:
        if s.get("id") not in cur_ids:
          cur.append(s)
      write_param(params, MCP_SERVERS_KEY, json.dumps(cur[:16], ensure_ascii=False))
    applied.append("mcp_servers")

  if "workspace" in allowed and isinstance(data.get("workspace"), dict):
    for key, content in data["workspace"].items():
      if mode == "replace" or not read_workspace_file(key).strip():
        write_workspace_file(key, str(content or ""))
    applied.append("workspace")

  if "params" in allowed and isinstance(data.get("params"), dict):
    for key, value in data["params"].items():
      if key.endswith("__redacted"):
        continue
      if key in _SECRET_KEYS and data["params"].get(f"{key}__redacted"):
        continue
      if key in _PARAM_KEYS and value is not None:
        write_param(params, key, str(value))
    applied.append("params")

  try:
    from ai.tools.domains.platform.session_index import rebuild_from_params
    rebuild_from_params(params)
  except Exception:
    pass

  try:
    from ai.common.config_store import get_config_store
    get_config_store().reload()
  except Exception:
    pass

  return {"ok": True, "applied": applied, "mode": mode}


def parse_uploaded_bundle(text: str) -> dict[str, Any]:
  try:
    data = json.loads(text)
  except json.JSONDecodeError as exc:
    return {"ok": False, "error": f"invalid JSON: {exc}"}
  if isinstance(data, dict) and "bundle" in data:
    return {"ok": True, "bundle": data}
  if isinstance(data, dict) and data.get("version"):
    return {"ok": True, "bundle": {"bundle": data}}
  return {"ok": False, "error": "not a platform backup bundle"}


def parse_uploaded_payload(payload: bytes | str) -> dict[str, Any]:
  """Parse .opbak archive or legacy JSON backup."""
  if isinstance(payload, str):
    return parse_uploaded_bundle(payload)
  if not payload:
    return {"ok": False, "error": "empty backup file"}
  if payload[:2] == b"\x1f\x8b":
    try:
      inner = unpack_opbak(payload)
      return {"ok": True, "bundle": {"bundle": inner}}
    except Exception as exc:
      return {"ok": False, "error": f"invalid {OPBAK_SUFFIX}: {exc}"}
  try:
    text = payload.decode("utf-8")
  except UnicodeDecodeError:
    return {"ok": False, "error": "unsupported backup format (use .opbak or JSON)"}
  return parse_uploaded_bundle(text)
