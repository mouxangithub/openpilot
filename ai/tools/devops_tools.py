"""Dev environment hints (webcam, devsync, openpilotci)."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from typing import Any

from ai.system.host_env import get_host_environment, is_pc_dev
from ai.system.paths import openpilot_root
from ai.tools.op_run import OPENPILOT_ROOT

_IP_RE = re.compile(r"^[\w.\-]+$")


def _validate_device_ip(device_ip: str | None) -> str | None:
  ip = (device_ip or "").strip()
  if not ip:
    return None
  if len(ip) > 253 or ".." in ip or "/" in ip or "\\" in ip or " " in ip:
    return "device_ip 格式无效"
  if not _IP_RE.match(ip):
    return "device_ip 格式无效"
  return None


def _run_check(cmd: list[str], *, timeout: int = 10) -> dict[str, Any]:
  try:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    return {
      "ok": proc.returncode == 0,
      "returncode": proc.returncode,
      "stdout": out[:500],
      "stderr": err[:500],
    }
  except subprocess.TimeoutExpired:
    return {"ok": False, "error": "timeout"}
  except FileNotFoundError:
    return {"ok": False, "error": "command not found"}
  except Exception as e:
    return {"ok": False, "error": str(e)}


def _local_devsync_tools() -> dict[str, bool]:
  return {
    "rsync": bool(shutil.which("rsync")),
    "git": bool(shutil.which("git")),
    "ssh": bool(shutil.which("ssh")),
  }


def get_webcam_dev_setup() -> dict[str, Any]:
  return {
    "ok": True,
    "requirements": [
      "Ubuntu 24.04 or macOS (not WSL2 for webcam)",
      "USB webcam 720p+",
      "comma panda + car harness",
      "scons -u build",
    ],
    "commands": [
      "USE_WEBCAM=1 system/manager/manager.py",
      "Optional: ROAD_CAM=0 DRIVER_CAM=1 WIDE_CAM=2",
    ],
    "script": "tools/webcam/README.md",
    "hint": "AI does not auto-start manager; closed course / bench only.",
  }


def get_devsync_hint(*, device_ip: str | None = None) -> dict[str, Any]:
  script = OPENPILOT_ROOT / "tools" / "scripts" / "devsync.py"
  tools = _local_devsync_tools()
  cmd = f"python {script}"
  if device_ip:
    cmd += f" {device_ip}"
  return {
    "ok": True,
    "script": str(script),
    "command": cmd,
    "has_rsync": tools["rsync"],
    "has_git": tools["git"],
    "has_ssh": tools["ssh"],
    "hint": "Syncs git-tracked files to comma@device; run manually on PC, not via AI auto-exec.",
    "device_ip": device_ip,
    "status_tool": "pc_devsync_status",
    "run_tool": "pc_devsync_run",
  }


def pc_devsync_status(
  *,
  device_ip: str | None = None,
  remote_path: str = "/data/openpilot",
  identity: str | None = None,
  probe_ssh: bool = True,
) -> dict[str, Any]:
  """Read-only preflight for tools/scripts/devsync.py — does not sync files."""
  if not is_pc_dev():
    return {
      "ok": False,
      "error": "此工具仅在 PC 开发环境可用（车机请直接编辑或使用其他同步方式）",
      "host": get_host_environment(),
    }

  ip_err = _validate_device_ip(device_ip)
  if ip_err:
    return {"ok": False, "error": ip_err}

  remote_path = (remote_path or "/data/openpilot").strip()
  if not remote_path.startswith("/") or ".." in remote_path or "\n" in remote_path:
    return {"ok": False, "error": "remote_path 无效（需为车机上的绝对路径）"}

  identity = (identity or "").strip() or None
  if identity and (".." in identity or "\n" in identity):
    return {"ok": False, "error": "identity 路径无效"}

  issues: list[str] = []
  root = openpilot_root()
  script = root / "tools" / "scripts" / "devsync.py"
  tools = _local_devsync_tools()
  tools["python"] = bool(sys.executable)

  for name, available in (("rsync", tools["rsync"]), ("git", tools["git"]), ("ssh", tools["ssh"])):
    if not available:
      issues.append(f"本机未安装 {name}，devsync 无法使用")

  if not script.is_file():
    issues.append(f"找不到 devsync 脚本: {script}")

  git_repo = False
  tracked_files: int | None = None
  if tools["git"]:
    git_check = _run_check(["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"])
    git_repo = git_check.get("ok") and git_check.get("stdout") == "true"
    if not git_repo:
      issues.append("当前 openpilot 目录不是 git 仓库")
    else:
      listed = _run_check(
        ["git", "-C", str(root), "ls-files", "--recurse-submodules"],
        timeout=20,
      )
      if listed.get("ok"):
        tracked_files = len([ln for ln in listed.get("stdout", "").splitlines() if ln.strip()])

  device_ip = (device_ip or "").strip() or None
  ssh_probe: dict[str, Any] | None = None
  remote_dir_exists: bool | None = None

  if device_ip:
    if not tools["ssh"]:
      issues.append("未安装 ssh，无法检测车机连通性")
    elif probe_ssh:
      ssh_cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=5",
        "-o", "StrictHostKeyChecking=accept-new",
      ]
      if identity:
        ssh_cmd += ["-i", identity]
      target = f"comma@{device_ip}"
      ssh_probe = _run_check(ssh_cmd + [target, "echo", "devsync_ok"], timeout=12)
      if not ssh_probe.get("ok"):
        issues.append(
          f"无法 SSH 到 {target}（请先在终端执行 ssh {target} 完成密钥/主机确认）"
        )
      else:
        dir_check = _run_check(ssh_cmd + [target, "test", "-d", remote_path], timeout=12)
        remote_dir_exists = bool(dir_check.get("ok"))
        if not remote_dir_exists:
          issues.append(f"车机远程目录不存在: {remote_path}")

  suggested = f"python {script}"
  if device_ip:
    suggested += f" {device_ip}"
  if remote_path != "/data/openpilot":
    suggested += f" --remote {remote_path}"
  if identity:
    suggested += f" -i {identity}"

  local_ready = (
    tools["rsync"] and tools["git"] and tools["ssh"] and script.is_file() and git_repo
  )
  if device_ip:
    device_ready = bool(
      ssh_probe and ssh_probe.get("ok") and remote_dir_exists is True
    )
  else:
    device_ready = None

  ready = local_ready and (device_ready if device_ip else True)

  return {
    "ok": True,
    "ready": ready,
    "local_ready": local_ready,
    "device_ready": device_ready,
    "issues": issues,
    "local_tools": tools,
    "openpilot_root": str(root),
    "devsync_script": str(script),
    "git_repo": git_repo,
    "git_tracked_files": tracked_files,
    "device_ip": device_ip,
    "remote_path": remote_path,
    "identity": identity,
    "ssh_reachable": ssh_probe.get("ok") if ssh_probe else None,
    "remote_dir_exists": remote_dir_exists,
    "ssh_detail": ssh_probe,
    "suggested_command": suggested,
    "hint": "只读体检，不会同步任何文件。ready 为 true 后，请在 PC 终端手动运行 suggested_command。",
    "script": "tools/scripts/devsync.py",
  }


def pc_devsync_run(
  *,
  device_ip: str,
  remote_path: str = "/data/openpilot",
  identity: str | None = None,
  dry_run: bool = False,
) -> dict[str, Any]:
  """One-shot rsync of git-tracked files to comma device (PC only)."""
  if not is_pc_dev():
    return {"ok": False, "error": "pc_devsync_run is PC-only"}

  ip_err = _validate_device_ip(device_ip)
  if ip_err:
    return {"ok": False, "error": ip_err}

  preflight = pc_devsync_status(
    device_ip=device_ip,
    remote_path=remote_path,
    identity=identity,
    probe_ssh=True,
  )
  if not preflight.get("ready"):
    return {
      "ok": False,
      "error": "devsync preflight not ready",
      "preflight": preflight,
    }

  root = openpilot_root()
  script = root / "tools" / "scripts" / "devsync.py"
  if not script.is_file():
    return {"ok": False, "error": f"devsync script missing: {script}"}

  if dry_run:
    return {
      "ok": True,
      "dry_run": True,
      "suggested_command": preflight.get("suggested_command"),
      "preflight": preflight,
    }

  cmd = [sys.executable, str(script), device_ip.strip()]
  if remote_path != "/data/openpilot":
    cmd += ["--remote", remote_path]
  if identity:
    cmd += ["-i", identity]

  try:
    proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=300)
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    return {
      "ok": proc.returncode == 0,
      "returncode": proc.returncode,
      "stdout": out[-8000:],
      "stderr": err[-4000:],
      "command": " ".join(cmd),
      "hint": "One-shot sync complete. For watch mode, run devsync.py manually in a terminal.",
    }
  except subprocess.TimeoutExpired:
    return {"ok": False, "error": "devsync timed out after 300s"}
  except Exception as e:
    return {"ok": False, "error": str(e)}


def openpilotci_segment_url(route_name: str, segment: int, filename: str) -> dict[str, Any]:
  route_name = (route_name or "").strip()
  filename = (filename or "").strip()
  if not route_name or segment < 0 or not filename:
    return {"ok": False, "error": "route_name, segment (int), filename required"}
  try:
    from openpilot.tools.lib.openpilotci import get_url
    url = get_url(route_name, segment, filename)
  except Exception as e:
    return {"ok": False, "error": str(e)}
  return {
    "ok": True,
    "url": url,
    "route_name": route_name,
    "segment": segment,
    "filename": filename,
    "script": "tools/lib/openpilotci.py",
    "hint": "Public CI blob; pair with search_car_segments.",
  }
