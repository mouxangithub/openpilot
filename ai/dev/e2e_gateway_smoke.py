"""Gateway E2E smoke — bootstrap, sessions CRUD, sync schema."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:5090"


def get(path: str) -> dict:
  with urllib.request.urlopen(f"{BASE}{path}", timeout=8) as r:
    return json.loads(r.read())


def post(path: str, body: dict) -> dict:
  data = json.dumps(body).encode()
  req = urllib.request.Request(
    f"{BASE}{path}",
    data=data,
    headers={"Content-Type": "application/json"},
    method="POST",
  )
  with urllib.request.urlopen(req, timeout=8) as r:
    return json.loads(r.read())


def main() -> int:
  errors: list[str] = []
  try:
    boot = get("/api/ai/bootstrap")
    if not boot.get("ok"):
      errors.append(f"bootstrap not ok: {boot}")
    else:
      print("bootstrap ok, providers=", len(boot.get("providers") or []))

    schema = get("/api/ai/sync/schema")
    msg_schema = (schema.get("schema") or {}).get("messages")
    if not msg_schema:
      errors.append("sync schema missing messages")
    else:
      print("sync schema ok, messages=", len(msg_schema))

    sess = get("/api/ai/sessions")
    v0 = int(sess.get("stateVersion") or 0)
    print("sessions initial count=", len(sess.get("sessions") or []), "v=", v0)

    posted = post("/api/ai/sessions", {
      "sessions": [{
        "id": "e2e_gateway_smoke",
        "title": "gateway smoke",
        "messages": [{"role": "user", "content": "hello gateway"}],
        "updatedAt": 999001,
      }],
      "activeId": "e2e_gateway_smoke",
    })
    if not posted.get("ok"):
      errors.append(f"post sessions failed: {posted}")
    else:
      v1 = int(posted.get("stateVersion") or 0)
      print("post ok stateVersion=", v1)
      if v1 <= v0:
        errors.append(f"stateVersion did not increment: {v0} -> {v1}")

    verify = get("/api/ai/sessions")
    ids = [s.get("id") for s in verify.get("sessions") or []]
    if "e2e_gateway_smoke" not in ids:
      errors.append("posted session not found on GET")
    else:
      print("verify ok, sessions=", len(ids), "stateVersion=", verify.get("stateVersion"))

    cfg = get("/api/ai/config")
    if not cfg.get("ok"):
      errors.append(f"config not ok: {cfg}")
    else:
      print("config ok, provider=", cfg.get("config", {}).get("provider"))

  except urllib.error.URLError as e:
    errors.append(f"connection failed: {e}")
  except Exception as e:
    errors.append(str(e))

  if errors:
    print("FAILED:")
    for err in errors:
      print(" -", err)
    return 1
  print("ALL PASSED")
  return 0


if __name__ == "__main__":
  sys.exit(main())
