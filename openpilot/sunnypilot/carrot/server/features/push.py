"""Web Push + PWA endpoints (Galaxy-inspired, StarPilot MIT).

The phone installs the panel as a PWA and subscribes to push; the server holds
subscriptions in Params and can notify on events (offroad errors, updates).
The payload encryption lives in services/web_push.py; this feature only wires
the HTTP surface.
"""
from __future__ import annotations

import asyncio
import json
import os

import aiohttp
from aiohttp import web

from ..config import WEB_DIR
from ..services.web_push import ensure_vapid_keys, send_push
from .params import PARAMS_KEY

_MAX_SUBSCRIPTIONS = 8


def _params(request: web.Request):
  return request.app[PARAMS_KEY]


def _load_subscriptions(params) -> list[dict]:
  raw = params.get("WebPushSubscriptions")
  if not raw:
    return []
  try:
    subs = json.loads(raw)
    return subs if isinstance(subs, list) else []
  except ValueError:
    return []


def _save_subscriptions(params, subscriptions: list[dict]) -> None:
  params.put("WebPushSubscriptions", json.dumps(subscriptions))


async def handle_status(request: web.Request) -> web.Response:
  params = _params(request)
  return web.json_response({
    "vapidPublicKey": ensure_vapid_keys(params)["public_key"],
    "subscriptions": len(_load_subscriptions(params)),
  })


async def handle_subscribe(request: web.Request) -> web.Response:
  params = _params(request)
  try:
    body = await request.json()
  except ValueError:
    return web.json_response({"error": "invalid json"}, status=400)
  endpoint = str(body.get("endpoint", ""))
  keys = body.get("keys") or {}
  if not endpoint.startswith("https://") or not keys.get("p256dh") or not keys.get("auth"):
    return web.json_response({"error": "endpoint and keys.p256dh/keys.auth required"}, status=400)

  subscriptions = [s for s in _load_subscriptions(params) if s.get("endpoint") != endpoint]
  subscriptions.append({"endpoint": endpoint, "keys": keys})
  if len(subscriptions) > _MAX_SUBSCRIPTIONS:
    subscriptions = subscriptions[-_MAX_SUBSCRIPTIONS:]
  _save_subscriptions(params, subscriptions)
  return web.json_response({"ok": True, "subscriptions": len(subscriptions)})


async def handle_unsubscribe(request: web.Request) -> web.Response:
  params = _params(request)
  try:
    body = await request.json()
  except ValueError:
    return web.json_response({"error": "invalid json"}, status=400)
  endpoint = str(body.get("endpoint", ""))
  remaining = [s for s in _load_subscriptions(params) if s.get("endpoint") != endpoint]
  _save_subscriptions(params, remaining)
  return web.json_response({"ok": True, "subscriptions": len(remaining)})


async def handle_test(request: web.Request) -> web.Response:
  params = _params(request)
  try:
    body = await request.json()
  except ValueError:
    body = {}
  title = str(body.get("title", "carrot"))[:64]
  text = str(body.get("body", "push test"))[:200]
  payload = json.dumps({"title": title, "body": text})

  vapid_keys = ensure_vapid_keys(params)
  subscriptions = _load_subscriptions(params)
  if not subscriptions:
    return web.json_response({"error": "no subscriptions"}, status=404)
  results = []
  async with aiohttp.ClientSession() as session:
    for sub in subscriptions:
      try:
        status, text_out = await send_push(sub, payload, vapid_keys, session)
        results.append({"endpoint": sub.get("endpoint", "")[:80], "status": status})
      except Exception as exc:  # network/encryption failures are per-subscriber
        results.append({"endpoint": sub.get("endpoint", "")[:80], "error": type(exc).__name__})
        await asyncio.sleep(0)
  return web.json_response({"ok": True, "results": results})


async def handle_service_worker(request: web.Request) -> web.Response:
  sw_path = os.path.join(WEB_DIR, "sw.js")
  text = await asyncio.to_thread(_read_file_text, sw_path)
  return web.Response(text=text, content_type="application/javascript",
                      headers={"Cache-Control": "no-cache"})


async def handle_manifest(request: web.Request) -> web.Response:
  manifest_path = os.path.join(WEB_DIR, "manifest.webmanifest")
  text = await asyncio.to_thread(_read_file_text, manifest_path)
  return web.Response(text=text, content_type="application/manifest+json",
                      headers={"Cache-Control": "no-cache"})


def _read_file_text(path: str) -> str:
  with open(path, encoding="utf-8") as f:
    return f.read()


def register(app: web.Application) -> None:
  app.router.add_get("/sw.js", handle_service_worker)
  app.router.add_get("/manifest.webmanifest", handle_manifest)
  app.router.add_get("/api/push/status", handle_status)
  app.router.add_post("/api/push/subscribe", handle_subscribe)
  app.router.add_post("/api/push/unsubscribe", handle_unsubscribe)
  app.router.add_post("/api/push/test", handle_test)
