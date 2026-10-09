"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""SSH keys and Mapbox tokens.

SSH keys go through sunnypilot's own store rather than a file: the device already has
`GithubSshKeys` / `GithubUsername` parameters and its sshd consumes them, so writing
anywhere else would produce a key the device ignores. That is also why `refresh` is a
re-download from GitHub and not a no-op pretending to be one.

Mapbox tokens are secrets, so the list never returns the token itself - only a fingerprint
and a masked tail, which is enough to tell two saved tokens apart.
"""

import asyncio
import hashlib
import json
import os

from aiohttp import web

from ..config import CARROT_MAPBOX_TOKENS_PATH
from ..services.params import ParamWriteError, set_param_value
from .params import PARAMS_KEY

GITHUB_KEYS_URL = "https://github.com/{username}.keys"
MAX_USERNAME_LEN = 64
MAX_TOKENS = 20


def _read_tokens() -> list:
  try:
    with open(CARROT_MAPBOX_TOKENS_PATH, encoding="utf-8") as f:
      data = json.load(f)
  except Exception:
    return []
  items = data.get("tokens") if isinstance(data, dict) else []
  return [item for item in items if isinstance(item, dict) and item.get("token")][:MAX_TOKENS]


def _write_tokens(tokens: list) -> None:
  os.makedirs(os.path.dirname(CARROT_MAPBOX_TOKENS_PATH), exist_ok=True)
  tmp_path = CARROT_MAPBOX_TOKENS_PATH + ".tmp"
  with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump({"tokens": tokens[:MAX_TOKENS]}, f, ensure_ascii=False, indent=2, sort_keys=True)
    f.write("\n")
    f.flush()
    os.fsync(f.fileno())
  os.replace(tmp_path, CARROT_MAPBOX_TOKENS_PATH)


def _mask(token: str) -> dict:
  digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
  return {"id": digest[:12], "tail": token[-4:] if len(token) > 4 else "", "length": len(token)}


# ------------------------------- ssh keys -----------------------------------


async def api_ssh_keys_status(request: web.Request) -> web.Response:
  params = request.app[PARAMS_KEY]
  keys = ""
  username = ""
  try:
    keys = params.get("GithubSshKeys") or ""
  except Exception:
    pass
  try:
    username = params.get("GithubUsername") or ""
  except Exception:
    pass
  if isinstance(keys, bytes):
    keys = keys.decode("utf-8", "replace")
  return web.json_response({
    "ok": True,
    "installed": bool(keys.strip()),
    "count": len([line for line in keys.splitlines() if line.strip()]),
    "username": str(username),
  })


async def api_ssh_keys(request: web.Request) -> web.Response:
  """Body: {"action": "add"|"remove"|"refresh", "username": "..."}."""
  try:
    body = await request.json()
  except Exception:
    return web.json_response({"ok": False, "error": "invalid json"}, status=400)
  if not isinstance(body, dict):
    return web.json_response({"ok": False, "error": "body must be a JSON object"}, status=400)

  action = str(body.get("action") or "").strip().lower()
  params = request.app[PARAMS_KEY]

  if action == "remove":
    for key in ("GithubSshKeys", "GithubUsername"):
      try:
        params.remove(key)
      except Exception:
        pass
    return web.json_response({"ok": True, "installed": False, "count": 0, "username": ""})

  if action not in ("add", "refresh"):
    return web.json_response({"ok": False, "error": "bad action"}, status=400)

  username = str(body.get("username") or "").strip()
  if not username:
    try:
      username = str(params.get("GithubUsername") or "").strip()
    except Exception:
      username = ""
  if not username or len(username) > MAX_USERNAME_LEN:
    return web.json_response({"ok": False, "error": "missing or invalid username"}, status=400)

  url = GITHUB_KEYS_URL.format(username=username)
  try:
    keys = await _download(url)
  except Exception as exc:
    return web.json_response({"ok": False, "error": f"could not fetch {url}: {exc}"}, status=502)

  if not keys.strip():
    return web.json_response({"ok": False, "error": f"GitHub has no public keys for {username}"}, status=404)

  try:
    set_param_value(params, "GithubUsername", username)
    set_param_value(params, "GithubSshKeys", keys)
  except ParamWriteError as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=400)

  return web.json_response({
    "ok": True,
    "installed": True,
    "count": len([line for line in keys.splitlines() if line.strip()]),
    "username": username,
  })


async def _download(url: str) -> str:
  import aiohttp

  timeout = aiohttp.ClientTimeout(total=10)
  async with aiohttp.ClientSession(timeout=timeout) as session:
    async with session.get(url) as resp:
      resp.raise_for_status()
      return await resp.text()


# ------------------------------- mapbox -------------------------------------


async def api_mapbox_tokens(request: web.Request) -> web.Response:
  tokens = await asyncio.to_thread(_read_tokens)
  return web.json_response({"ok": True, "tokens": [_mask(item["token"]) for item in tokens]})


async def api_mapbox_token_set(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    return web.json_response({"ok": False, "error": "invalid json"}, status=400)
  if not isinstance(body, dict):
    return web.json_response({"ok": False, "error": "body must be a JSON object"}, status=400)
  token = str(body.get("token") or "").strip()
  if not token:
    return web.json_response({"ok": False, "error": "missing token"}, status=400)

  tokens = await asyncio.to_thread(_read_tokens)
  existing = [item for item in tokens if item.get("token") != token]
  existing.append({"token": token, "label": str(body.get("label") or "").strip()})
  await asyncio.to_thread(_write_tokens, existing)
  return web.json_response({"ok": True, "token": _mask(token), "count": len(existing)})


async def api_mapbox_token_delete(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    return web.json_response({"ok": False, "error": "invalid json"}, status=400)
  if not isinstance(body, dict):
    return web.json_response({"ok": False, "error": "body must be a JSON object"}, status=400)
  token_id = str(body.get("id") or "").strip()
  if not token_id:
    return web.json_response({"ok": False, "error": "missing id"}, status=400)

  tokens = await asyncio.to_thread(_read_tokens)
  remaining = [item for item in tokens if _mask(item["token"])["id"] != token_id]
  if len(remaining) == len(tokens):
    return web.json_response({"ok": False, "error": "token not found"}, status=404)
  await asyncio.to_thread(_write_tokens, remaining)
  return web.json_response({"ok": True, "count": len(remaining)})


async def api_mapbox_token_validate(request: web.Request) -> web.Response:
  """Check a token against Mapbox's token endpoint. Refuses to run with no token stored."""
  try:
    body = await request.json()
  except Exception:
    body = {}
  token = str((body or {}).get("token") or "").strip()
  if not token:
    tokens = await asyncio.to_thread(_read_tokens)
    if not tokens:
      return web.json_response({"ok": False, "error": "no token to validate"}, status=400)
    token = tokens[-1]["token"]
  try:
    import aiohttp

    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
      async with session.get(f"https://api.mapbox.com/tokens/v2?access_token={token}") as resp:
        valid = resp.status == 200
        status = resp.status
  except Exception as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=502)
  return web.json_response({"ok": True, "valid": valid, "status": status})


def register(app: web.Application) -> None:
  app.router.add_get("/api/ssh_keys", api_ssh_keys_status)
  app.router.add_post("/api/ssh_keys", api_ssh_keys)
  app.router.add_get("/api/mapbox/tokens", api_mapbox_tokens)
  app.router.add_post("/api/mapbox/token", api_mapbox_token_set)
  app.router.add_delete("/api/mapbox/token", api_mapbox_token_delete)
  app.router.add_post("/api/mapbox/token/validate", api_mapbox_token_validate)
