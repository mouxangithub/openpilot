"""API handlers — bundle/profile listing and expansion (P1-2)."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from aiohttp import web

from openpilot.common.params import Params

from ai.system.paths import workspace_path


def _json(data: Any, status: int = 200) -> web.Response:
  return web.Response(
    text=json.dumps(data, ensure_ascii=False, default=str),
    status=status,
    content_type="application/json",
  )


def _bundle_store():
  from ai.bundle.store import BundleStore
  return BundleStore(store_dir=workspace_path("ai_bundles", mkdir=True))


def _current_profile(params: Params | None) -> dict[str, Any]:
  from ai.common.storage import read_param_bool, read_param, read_param_str
  return {
    "sandboxMode": read_param(params, "ai_sandbox_mode", "read-only"),
    "sandboxShell": read_param_bool(params, "ai_sandbox_shell", True),
    "externalizeResults": read_param_bool(params, "ai_externalize_results", True),
    "externalizeThreshold": read_param(params, "ai_externalize_threshold", 8192),
    "mcpServers": read_param(params, "ai_mcp_servers", "[]"),
    "agentLoop": read_param_bool(params, "ai_use_agent_loop", True),
  }


async def api_bundle(request: web.Request) -> web.Response:
  """GET: list bundles. POST: install or save a bundle."""
  store = _bundle_store()
  if request.method == "GET":
    return _json({"ok": True, "bundles": [m.to_dict() for m in store.list_bundles()]})

  try:
    body = await request.json()
  except Exception:
    return _json({"ok": False, "error": "Invalid JSON"}, status=400)
  if not isinstance(body, dict):
    return _json({"ok": False, "error": "Invalid JSON"}, status=400)

  op = str(body.get("operation") or "install").strip()

  if op == "install":
    bundle_id = str(body.get("bundleId") or body.get("bundle_id") or "").strip()
    install_dir = str(body.get("installDir") or body.get("install_dir") or "").strip()
    if not bundle_id:
      return _json({"ok": False, "error": "bundleId required"}, status=400)
    try:
      target = install_dir or str(workspace_path("ai_bundle_runtime", mkdir=True))
      manifest = store.install_bundle(bundle_id, target, clean=True)
      return _json({"ok": True, "bundle": manifest.to_dict(), "installDir": target})
    except Exception as e:
      return _json({"ok": False, "error": str(e)}, status=400)

  if op == "save":
    from ai.bundle.manifest import BundleManifest
    from ai.bundle.packer import BundlePacker
    manifest_data = body.get("manifest") or {}
    manifest = BundleManifest.from_dict(manifest_data)
    if not manifest.id:
      return _json({"ok": False, "error": "manifest.id required"}, status=400)
    files = body.get("files") or {}
    if not isinstance(files, dict):
      return _json({"ok": False, "error": "files must be a dict of relative-path -> content"}, status=400)
    tmp = Path(tempfile.mkdtemp())
    try:
      src = tmp / "src"
      src.mkdir()
      for rel_path, content in files.items():
        dst = src / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(str(content), encoding="utf-8")
      (src / "bundle.json").write_text(json.dumps(manifest.to_dict(), ensure_ascii=False), encoding="utf-8")
      store.save_bundle(src, manifest=manifest)
      return _json({"ok": True, "bundle": manifest.to_dict()})
    finally:
      shutil.rmtree(tmp, ignore_errors=True)

  return _json({"ok": False, "error": f"unknown operation: {op}"}, status=400)


async def api_bundle_detail(request: web.Request) -> web.Response:
  """GET/DELETE a single bundle by id."""
  store = _bundle_store()
  bundle_id = request.match_info.get("bundle_id", "").strip()
  if not bundle_id:
    return _json({"ok": False, "error": "bundle_id required"}, status=400)

  if request.method == "DELETE":
    removed = store.remove_bundle(bundle_id)
    if not removed:
      return _json({"ok": False, "error": "bundle not found"}, status=404)
    return _json({"ok": True, "removed": True, "bundleId": bundle_id})

  manifest = store.get_bundle(bundle_id)
  if manifest is None:
    return _json({"ok": False, "error": "bundle not found"}, status=404)
  return _json({"ok": True, "bundle": manifest.to_dict()})


async def api_profile_current(request: web.Request) -> web.Response:
  """GET: current effective profile (sandbox, spill, mcp, agent loop)."""
  params: Params = request.app.get("params") or Params()
  return _json({"ok": True, "profile": _current_profile(params)})


async def api_profiles(request: web.Request) -> web.Response:
  """GET: list profiles. POST: compose a profile's patch layers."""
  from ai.bundle.profile import list_profiles, compose_profile, profiles_root

  if request.method == "GET":
    return _json({"ok": True, "profiles": list_profiles()})

  try:
    body = await request.json()
  except Exception:
    return _json({"ok": False, "error": "Invalid JSON"}, status=400)
  if not isinstance(body, dict):
    return _json({"ok": False, "error": "Invalid JSON"}, status=400)

  name = str(body.get("name") or "").strip()
  if not name:
    return _json({"ok": False, "error": "name required"}, status=400)
  try:
    store = _bundle_store()
    result = compose_profile(name, store=store)
    return _json(result)
  except Exception as e:
    return _json({"ok": False, "error": str(e)}, status=400)