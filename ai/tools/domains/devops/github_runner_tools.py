"""GitHub Actions self-hosted runner helpers for op助手 (C3 prebuilt CI)."""

from __future__ import annotations

import socket
import subprocess
from pathlib import Path
from typing import Any

from openpilot.common.params import Params

RUNNER_REL = Path("release/ci/install_github_runner.sh")
GITHUB_RUNNER_SH = Path("system/manager/github_runner.sh")
DEFAULT_REPO = "https://github.com/mouxangithub/openpilot"
WORKFLOW_PATH = ".github/workflows/build.yaml"


def _github_base_candidates() -> list[Path]:
  bases = [Path("/data/media/0/github"), Path("/data/github")]
  out: list[Path] = []
  for base in bases:
    if base not in out:
      out.append(base)
  return out


def github_base_dir() -> Path:
  for base in _github_base_candidates():
    if (base / "runner").is_dir():
      return base
  return Path("/data/github")


def runner_dir() -> Path:
  return github_base_dir() / "runner"


def resolve_service_name() -> str:
  svc_file = runner_dir() / ".service"
  if svc_file.is_file():
    return svc_file.read_text().strip()
  return f"actions.runner.sunnypilot.{socket.gethostname()}"


def legacy_service_name() -> str:
  return f"actions.runner.sunnypilot.{socket.gethostname()}"


def _read_bool(params: Params | None, key: str) -> bool | None:
  if params is None:
    return None
  try:
    if params.get(key) is None:
      return None
    return params.get_bool(key)
  except Exception:
    return None


def _systemctl_prop(service: str, prop: str) -> str | None:
  try:
    proc = subprocess.run(
      ["systemctl", "show", service, f"--property={prop}", "--value"],
      capture_output=True,
      text=True,
      timeout=8,
    )
    if proc.returncode != 0:
      return None
    val = (proc.stdout or "").strip()
    return val or None
  except Exception:
    return None


def _systemctl_status(service: str) -> dict[str, Any]:
  loaded = _systemctl_prop(service, "LoadState")
  active = _systemctl_prop(service, "ActiveState")
  sub = _systemctl_prop(service, "SubState")
  unit_file = _systemctl_prop(service, "UnitFileState")
  return {
    "known_to_systemd": loaded not in (None, "not-found"),
    "load_state": loaded,
    "active_state": active,
    "sub_state": sub,
    "unit_file_state": unit_file,
    "running": active == "active",
    "enabled_at_boot": unit_file in ("enabled", "enabled-runtime"),
  }


def _file_exists(path: Path) -> bool:
  try:
    return path.is_file()
  except OSError:
    return False


def _dir_exists(path: Path) -> bool:
  try:
    return path.is_dir()
  except OSError:
    return False


def github_runner_status(params: Params | None = None) -> dict[str, Any]:
  """Collect runner install paths, Param gates, and systemd state."""
  if params is None:
    try:
      params = Params()
    except Exception:
      params = None
  base = github_base_dir()
  rd = runner_dir()
  service = resolve_service_name()
  legacy = legacy_service_name()
  install_script = Path("/data/openpilot") / RUNNER_REL

  installed_markers = {
    "runner_dir": _dir_exists(rd),
    "credentials": _file_exists(rd / ".credentials"),
    "service_file": _file_exists(rd / ".service"),
    "runner_json": _file_exists(rd / ".runner"),
  }
  installed = bool(installed_markers["credentials"] and installed_markers["service_file"])

  svc = _systemctl_status(service) if installed else {"known_to_systemd": False}
  legacy_svc = None
  if legacy != service:
    legacy_svc = _systemctl_status(legacy)

  manager_sh = Path("/data/openpilot") / GITHUB_RUNNER_SH
  gates = {
    "EnableGithubRunner": _read_bool(params, "EnableGithubRunner"),
    "ShowAdvancedControls": _read_bool(params, "ShowAdvancedControls"),
    "NetworkMetered": _read_bool(params, "NetworkMetered"),
    "GithubRunnerSufficientVoltage": _read_bool(params, "GithubRunnerSufficientVoltage"),
  }
  gate_ok = (
    gates.get("EnableGithubRunner") is True
    and gates.get("NetworkMetered") is not True
    and gates.get("GithubRunnerSufficientVoltage") is not False
  )

  out: dict[str, Any] = {
    "ok": True,
    "installed": installed,
    "install_markers": installed_markers,
    "github_base_dir": str(base),
    "runner_dir": str(rd),
    "builds_dir": str(base / "builds"),
    "logs_dir": str(base / "logs"),
    "openpilot_bind_dir": str(base / "openpilot"),
    "service_name": service,
    "legacy_service_name": legacy,
    "service_name_mismatch": service != legacy and legacy_svc and legacy_svc.get("known_to_systemd"),
    "systemd": svc,
    "legacy_systemd": legacy_svc,
    "param_gates": gates,
    "manager_would_start": gate_ok and installed and svc.get("known_to_systemd"),
    "github_runner_sh_present": manager_sh.is_file(),
    "install_script_present": install_script.is_file(),
    "default_repo": DEFAULT_REPO,
    "workflow": WORKFLOW_PATH,
    "ui": {
      "path": "Settings → Developer → Show advanced controls → GitHub Runner Service",
      "param": "EnableGithubRunner",
      "hidden_on_release_branch": True,
    },
    "doc": "ai/docs/GITHUB_RUNNER.md",
    "skill": "github-runner",
  }
  try:
    from ai.tools.domains.devops.github_actions_tools import github_actions_auth_status, github_api_snapshot

    auth = github_actions_auth_status(params)
    out["github_actions_pat"] = {
      "configured": auth.get("configured"),
      "valid": auth.get("valid"),
      "github_user": auth.get("github_user"),
    }
    if auth.get("configured") and auth.get("valid"):
      snap = github_api_snapshot(params)
      if snap:
        out["github_api"] = snap
  except Exception:
    pass
  return out


def github_runner_recovery_hint(params: Params | None = None, *, get_state_reader=None) -> dict[str, Any]:
  """Suggest next steps when CI build is Pending or runner won't start."""
  status = github_runner_status(params)
  steps: list[str] = ["github_runner_status"]

  if not status.get("installed"):
    steps.extend([
      "未安装：GitHub → Settings → Actions → Runners → New self-hosted runner 复制 token",
      f"SSH: cd /data/openpilot && sudo ./release/ci/install_github_runner.sh --token <TOKEN> --repo {DEFAULT_REPO}",
      "安装后确认 Runner 标签含 tici；见 ai/docs/GITHUB_RUNNER.md",
    ])
    return {**status, "recommended_steps": steps, "issue": "not_installed"}

  gates = status.get("param_gates") or {}
  svc = status.get("systemd") or {}

  if gates.get("EnableGithubRunner") is not True:
    steps.append(
      "打开 UI：开发者 → 显示高级控制项 → GitHub Runner Service；或 set_device_settings(EnableGithubRunner=true, confirm=true)"
    )

  if gates.get("GithubRunnerSufficientVoltage") is False:
    steps.append("电压 < 9V：桌面供电时 GithubRunnerSufficientVoltage=false，接车载 12V 或暂时忽略（仅 offroad 启停）")

  if gates.get("NetworkMetered") is True:
    steps.append("NetworkMetered=true：关闭计量网络或换 WiFi 后再开 EnableGithubRunner")

  if not svc.get("known_to_systemd"):
    steps.extend([
      "systemd 未识别服务：cd /data/github/runner && sudo ./svc.sh install github-runner",
      "或重装：release/ci/install_github_runner.sh --restore --token <TOKEN>",
    ])
  elif not svc.get("running"):
    if status.get("manager_would_start"):
      steps.extend([
        "Param 已满足但服务未运行：list_managed_processes 查 github_runner_start",
        f"手动：sudo systemctl start {status.get('service_name')}",
        "grep_log github_runner|actions.runner",
      ])
    else:
      steps.append("manager 未满足启停条件（需 offroad + EnableGithubRunner + 电压/网络门控）")

  if status.get("service_name_mismatch"):
    steps.append(
      "服务名与旧版 github_runner.sh 默认不一致；已修复为读取 runner/.service（需同步最新 openpilot）"
    )

  if svc.get("enabled_at_boot") and gates.get("EnableGithubRunner") is not True:
    steps.append("若安装时用了 --start-at-boot，Runner 可能开机自启；完全由 GUI 控制请 systemctl disable <service>")

  steps.extend([
    "CI Pending：GitHub Actions → sunnypilot prebuilt → 确认 build job 等待 tici runner",
    "已配置 PAT：list_github_workflow_runs(status=in_progress)、list_github_runners",
    "编译日志：/data/github/logs 或 Actions 网页 / get_github_workflow_run",
    "PC 触发：Actions → Run workflow（branch master-c3）",
    "文档：ai/docs/GITHUB_RUNNER.md；用户手册 release/ci/README.md",
  ])

  issue = "ok"
  if not status.get("installed"):
    issue = "not_installed"
  elif not svc.get("running"):
    issue = "service_not_running"
  elif not status.get("manager_would_start"):
    issue = "gates_blocked"

  return {
    "ok": True,
    "issue": issue,
    "recommended_steps": steps,
    "status_summary": {
      "installed": status.get("installed"),
      "service_running": (status.get("systemd") or {}).get("running"),
      "enable_param": gates.get("EnableGithubRunner"),
      "service_name": status.get("service_name"),
    },
    "skill": "github-runner",
    "doc": "ai/docs/GITHUB_RUNNER.md",
  }


def _redact_token(text: str, token: str) -> str:
  if not text or not token:
    return text
  return text.replace(token, "<REDACTED>")


def install_github_runner_preview(
  *,
  token: str = "",
  repo_url: str = DEFAULT_REPO,
  start_at_boot: bool = False,
  restore: bool = False,
  confirm: bool = False,
  params: Params | None = None,
) -> dict[str, Any]:
  """Preview or run install_github_runner.sh (offroad, needs root). Never logs full token."""
  token = (token or "").strip()
  repo_url = (repo_url or DEFAULT_REPO).strip()
  script = Path("/data/openpilot") / RUNNER_REL
  mode = "restore" if restore else "install"
  preview = {
    "mode": mode,
    "script": str(script),
    "repo_url": repo_url,
    "start_at_boot": start_at_boot,
    "restore": restore,
    "token_provided": bool(token),
    "command": (
      f"cd /data/openpilot && sudo ./release/ci/install_github_runner.sh "
      + ("--restore " if restore else "")
      + f"--token <REDACTED> --repo {repo_url}"
      + (" --start-at-boot" if start_at_boot else "")
    ),
    "doc": "ai/docs/GITHUB_RUNNER.md",
    "hint": (
      "GitHub → Settings → Actions → Runners → New self-hosted runner → 复制 registration token。"
      "用户提供 token 并说「安装/确认」时，调用本工具且 confirm=true。"
    ),
  }
  if not confirm:
    hint = preview["hint"]
    if token:
      hint = "已收到 registration token。用户确认后请设 confirm=true 执行安装（约 5–10 分钟）。"
    return {
      "ok": True,
      "needs_confirmation": True,
      "preview": preview,
      "hint": hint,
    }
  if not token:
    return {"ok": False, "error": "token required when confirm=true"}
  if not script.is_file():
    return {"ok": False, "error": f"install script missing: {script}"}
  cmd = ["sudo", str(script), "--token", token, "--repo", repo_url]
  if restore:
    cmd.append("--restore")
  if start_at_boot:
    cmd.append("--start-at-boot")
  try:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd="/data/openpilot")
    stdout = _redact_token(proc.stdout or "", token)
    stderr = _redact_token(proc.stderr or "", token)
    result: dict[str, Any] = {
      "ok": proc.returncode == 0,
      "returncode": proc.returncode,
      "stdout_tail": stdout[-4000:],
      "stderr_tail": stderr[-2000:],
      "preview": {**preview, "token_provided": True},
      "next_steps": [
        "github_runner_status",
        "若未自动接单：set_device_settings(EnableGithubRunner=true)",
        "GitHub Actions 页确认 runner 标签含 tici",
      ],
    }
    if proc.returncode == 0:
      result["status_after_install"] = github_runner_status(params)
    return result
  except subprocess.TimeoutExpired:
    return {"ok": False, "error": "install timed out (600s)"}
  except Exception as e:
    return {"ok": False, "error": str(e), "preview": preview}
