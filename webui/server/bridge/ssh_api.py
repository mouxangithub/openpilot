"""SSH keys (Developer panel)."""

from __future__ import annotations

from typing import Any

import requests


def ssh_status() -> dict[str, Any]:
  try:
    from openpilot.common.params import Params
    p = Params()
    return {
      "ok": True,
      "username": p.get("GithubUsername") or "",
      "keys": p.get("GithubSshKeys") or "",
      "ssh_enabled": p.get_bool("SshEnabled"),
    }
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def ssh_fetch_keys(username: str) -> dict[str, Any]:
  username = username.strip()
  if not username:
    return {"ok": False, "error": "username required"}
  try:
    from openpilot.common.params import Params
    resp = requests.get(f"https://github.com/{username}.keys", timeout=15)
    resp.raise_for_status()
    keys = resp.text.strip()
    if not keys:
      return {"ok": False, "error": "no SSH keys found"}
    p = Params()
    p.put("GithubUsername", username, block=True)
    p.put("GithubSshKeys", keys, block=True)
    return {"ok": True, "username": username, "keys": keys}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def ssh_remove_keys() -> dict[str, Any]:
  try:
    from openpilot.common.params import Params
    p = Params()
    p.remove("GithubUsername")
    p.remove("GithubSshKeys")
    return {"ok": True}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}
