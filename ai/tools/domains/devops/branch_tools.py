"""Prebuilt branch / OTA helpers for op助手."""

from __future__ import annotations

from pathlib import Path
from typing import Any, TYPE_CHECKING

from ai.tools.domains.devops.git_tools import _git, git_status
from ai.tools.domains.devops.ota_tools import ota_status
from ai.tools.domains.platform.system_info_tools import get_build_info

if TYPE_CHECKING:
  from openpilot.common.params import Params

DEFAULT_DEV_BRANCH = "master-c3"
DEFAULT_PREBUILT_SUFFIX = "-prebuilt"


def _prebuilt_branch(dev_branch: str) -> str:
  b = (dev_branch or DEFAULT_DEV_BRANCH).strip()
  if b.endswith(DEFAULT_PREBUILT_SUFFIX):
    return b
  return f"{b}{DEFAULT_PREBUILT_SUFFIX}"


def prebuilt_branch_status(
  *,
  dev_branch: str = DEFAULT_DEV_BRANCH,
  remote: str = "origin",
) -> dict[str, Any]:
  """Compare current checkout vs dev/prebuilt branches."""
  status = git_status()
  prebuilt = _prebuilt_branch(dev_branch)
  fetch = _git(["fetch", remote, dev_branch, prebuilt], timeout=120)
  local_head = status.get("head")
  branch = status.get("branch")

  dev_rev = _git(["rev-parse", f"{remote}/{dev_branch}"], timeout=15)
  pre_rev = _git(["rev-parse", f"{remote}/{prebuilt}"], timeout=15)
  ahead = _git(["rev-list", "--count", f"{remote}/{prebuilt}..{remote}/{dev_branch}"], timeout=15)
  behind = _git(["rev-list", "--count", f"{remote}/{dev_branch}..HEAD"], timeout=15) if local_head else {"stdout": "?"}

  prebuilt_file = Path("/data/openpilot/prebuilt")
  return {
    "ok": True,
    "current_branch": branch,
    "current_head": local_head,
    "dev_branch": dev_branch,
    "prebuilt_branch": prebuilt,
    "remote_dev": dev_rev.get("stdout") if dev_rev.get("ok") else None,
    "remote_prebuilt": pre_rev.get("stdout") if pre_rev.get("ok") else None,
    "commits_dev_ahead_of_prebuilt": ahead.get("stdout") if ahead.get("ok") else None,
    "local_dirty": status.get("dirty_count", 0) > 0,
    "prebuilt_file_present": prebuilt_file.is_file(),
    "fetch_ok": fetch.get("ok"),
    "hint": (
      f"开发分支 {dev_branch} 推送后 CI 发布 {prebuilt}；"
      f"车机快速启动应 checkout {prebuilt} 并确认 prebuilt 文件存在。"
    ),
  }


def checkout_prebuilt_branch(
  *,
  dev_branch: str = DEFAULT_DEV_BRANCH,
  remote: str = "origin",
  confirm: bool = False,
) -> dict[str, Any]:
  """git fetch + reset --hard origin/<branch>-prebuilt and verify prebuilt marker."""
  prebuilt = _prebuilt_branch(dev_branch)
  preview = {
    "action": "checkout_prebuilt",
    "branch": prebuilt,
    "remote": remote,
    "commands": [
      f"git fetch {remote} {prebuilt}",
      f"git reset --hard {remote}/{prebuilt}",
      "git submodule update --init --recursive",
      "test -f prebuilt",
    ],
  }
  if not confirm:
    return {"ok": True, "needs_confirmation": True, "preview": preview}

  st = git_status()
  if st.get("dirty_count", 0) > 0:
    return {"ok": False, "error": "working tree dirty; stash or commit first", "dirty_count": st.get("dirty_count")}

  steps: list[dict[str, Any]] = []
  for args in (
    ["fetch", remote, prebuilt],
    ["reset", "--hard", f"{remote}/{prebuilt}"],
    ["submodule", "update", "--init", "--recursive"],
  ):
    res = _git(args, timeout=300)
    steps.append({"git": args, "ok": res.get("ok"), "stderr": (res.get("stderr") or "")[-500:]})
    if not res.get("ok"):
      return {"ok": False, "error": f"git {' '.join(args)} failed", "steps": steps}

  prebuilt_path = Path("/data/openpilot/prebuilt")
  verified = prebuilt_path.is_file()
  return {
    "ok": verified,
    "branch": prebuilt,
    "prebuilt_file": str(prebuilt_path),
    "prebuilt_present": verified,
    "steps": steps,
    "next": "reboot_device" if verified else "github_runner_recovery_hint",
    "status": prebuilt_branch_status(dev_branch=dev_branch, remote=remote),
  }


def ota_preflight_checklist(params: "Params | None" = None) -> dict[str, Any]:
  """Health checklist before OTA or branch switch."""
  from ai.tools.domains.platform.device_health_tools import device_health
  from ai.tools.domains.devops.github_runner_tools import github_runner_status
  from ai.tools.domains.platform.panda_flash_tools import list_all_pandas

  ota = ota_status(params)
  health = device_health()
  runner = github_runner_status(params)
  pandas = list_all_pandas()
  build = get_build_info()

  checks: list[dict[str, Any]] = []
  disk = (health.get("disk") or {})
  free_gb = disk.get("free_gb")
  if free_gb is not None and float(free_gb) < 5:
    checks.append({"id": "disk_low", "ok": False, "detail": f"free_gb={free_gb}"})
  else:
    checks.append({"id": "disk", "ok": True})

  temp = health.get("max_temp_c")
  if temp is not None and float(temp) > 85:
    checks.append({"id": "thermal", "ok": False, "detail": f"max_temp_c={temp}"})
  else:
    checks.append({"id": "thermal", "ok": True})

  if ota.get("update_pending"):
    checks.append({"id": "ota_pending", "ok": True, "detail": "UpdateAvailable=1"})
  else:
    checks.append({"id": "ota_pending", "ok": True, "detail": "no pending OTA flag"})

  panda_ok = bool((pandas.get("pandas") or pandas.get("devices")) or pandas.get("ok"))
  checks.append({"id": "panda", "ok": panda_ok, "detail": pandas.get("summary", "")[:120]})

  checks.append({
    "id": "runner",
    "ok": bool(runner.get("installed")),
    "detail": "installed" if runner.get("installed") else "not installed (CI only)",
  })

  failed = [c for c in checks if not c.get("ok")]
  return {
    "ok": len(failed) == 0,
    "ready": len(failed) == 0,
    "checks": checks,
    "blockers": [c["id"] for c in failed],
    "ota": ota,
    "build": build.get("git") if isinstance(build, dict) else build,
    "hint": "全部通过后再执行 OTA 或 checkout_prebuilt_branch。",
  }
