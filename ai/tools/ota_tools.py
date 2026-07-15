"""OTA / update status for op助手."""

from __future__ import annotations

from typing import Any

from ai.tools.system_info_tools import get_build_info


def ota_status(params=None) -> dict[str, Any]:
  """Read openpilot/AGNOS update state from Params and build metadata."""
  from openpilot.common.params import Params

  params = params or Params()
  info = get_build_info()
  out: dict[str, Any] = {
    "ok": True,
    "build": info.get("git"),
    "branch": info.get("branch"),
    "commit": info.get("commit"),
  }

  keys = (
    "Version",
    "AGNOSVersion",
    "GitBranch",
    "GitCommit",
    "UpdateAvailable",
    "DongleId",
    "IsOffroad",
    "IsOnroad",
  )
  for key in keys:
    try:
      raw = params.get(key)
      if raw is None:
        continue
      if isinstance(raw, bytes):
        raw = raw.decode(errors="replace")
      out[key] = raw
    except Exception:
      pass

  update_avail = out.get("UpdateAvailable")
  out["update_pending"] = str(update_avail).lower() in ("1", "true", "yes")
  out["hint"] = (
    "UpdateAvailable=1 表示 manager 检测到新版本；offroad 时可在 Dashy 触发更新。"
    if out.get("update_pending")
    else "当前无待安装更新标记；可用 git_status 查看源码分支。"
  )
  return out
