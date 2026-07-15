"""
Whitelisted, read-only shell commands for the AI agent.

Only commands that cannot modify vehicle state are allowed. Each command runs
with a short timeout and has strict argument validation.
"""

import re
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AllowedCommand:
  name: str
  args: tuple[str, ...]
  timeout: int = 10
  max_output_lines: int = 200


# Whitelist of allowed commands. Arguments are fixed; user input can only choose
# which command to run, not inject arbitrary args.
ALLOWED_COMMANDS: dict[str, AllowedCommand] = {
  "uptime": AllowedCommand("uptime", ("uptime",)),
  "df": AllowedCommand("df", ("df", "-h")),
  "free": AllowedCommand("free", ("free", "-h")),
  "dmesg_tail": AllowedCommand("dmesg_tail", ("dmesg", "-T", "|", "tail", "-n", "100")),
  "journalctl_manager": AllowedCommand(
    "journalctl_manager",
    ("journalctl", "-u", "openpilot-manager", "-n", "100", "--no-pager"),
  ),
  "ps": AllowedCommand("ps", ("ps", "aux")),
  "ip_addr": AllowedCommand("ip_addr", ("ip", "addr")),
  "iwconfig": AllowedCommand("iwconfig", ("iwconfig",)),
  "netstat": AllowedCommand("netstat", ("ss", "-tunlp")),
  "param_dump": AllowedCommand("param_dump", ("python", "-c", "from openpilot.common.params import Params; p=Params(); [print(k) for k in sorted(p.keys())]")),
  "list_routes": AllowedCommand("list_routes", ("ls", "-1t", "__ROUTES_DIR__")),
  "tail_params_log": AllowedCommand(
    "tail_params_log",
    ("tail", "-n", "80", "/data/log/latest.log"),
  ),
  "list_adaptation_drafts": AllowedCommand(
    "list_adaptation_drafts",
    ("ls", "-la", "__ADAPTATION_DRAFTS__"),
    timeout=8,
  ),
  "grep_log_errors": AllowedCommand(
    "grep_log_errors",
    (
      "python",
      "-c",
      "import re;p='/data/log/latest.log'\n"
      "try:\n lines=open(p,encoding='utf-8',errors='replace').read().splitlines()[-300:]\n"
      " hits=[l for l in lines if re.search(r'error|warn|fault|crash',l,re.I)]\n"
      " print('\\n'.join(hits[-50:]) if hits else '(no matches)')\n"
      "except Exception as e: print(e)",
    ),
    timeout=12,
    max_output_lines=80,
  ),
}


def _resolve_args(command_name: str, args: tuple[str, ...]) -> tuple[str, ...]:
  from ai.system.paths import adaptation_drafts_dir, routes_dir

  resolved: list[str] = []
  for a in args:
    if a == "__ROUTES_DIR__":
      resolved.append(routes_dir())
    elif a == "__ADAPTATION_DRAFTS__":
      resolved.append(str(adaptation_drafts_dir()))
    else:
      resolved.append(a)
  return tuple(resolved)


def run_command(command_name: str) -> dict[str, Any]:
  """Run a whitelisted command and return its output."""
  allowed = ALLOWED_COMMANDS.get(command_name)
  if allowed is None:
    return {
      "ok": False,
      "error": f"Command '{command_name}' is not in the allowed whitelist.",
      "stdout": "",
      "stderr": "",
    }

  cmd_args = _resolve_args(command_name, allowed.args)

  try:
    # Pipe through tail for dmesg_tail is not a real single command; handle
    # that special case with shell=True but only using our fixed args.
    if allowed.name == "dmesg_tail":
      proc = subprocess.run(
        " ".join(shlex.quote(a) for a in cmd_args),
        shell=True,
        capture_output=True,
        text=True,
        timeout=allowed.timeout,
      )
    else:
      proc = subprocess.run(
        cmd_args,
        capture_output=True,
        text=True,
        timeout=allowed.timeout,
      )

    stdout_lines = proc.stdout.splitlines()
    if len(stdout_lines) > allowed.max_output_lines:
      stdout_lines = stdout_lines[:allowed.max_output_lines]
      stdout_lines.append("... (truncated)")

    return {
      "ok": proc.returncode == 0,
      "returncode": proc.returncode,
      "stdout": "\n".join(stdout_lines),
      "stderr": proc.stderr.strip(),
    }
  except subprocess.TimeoutExpired:
    return {"ok": False, "error": "Command timed out.", "stdout": "", "stderr": ""}
  except Exception as e:
    return {"ok": False, "error": str(e), "stdout": "", "stderr": ""}


def run_shell_command(
  command: str,
  *,
  timeout: int = 60,
  max_output_lines: int = 500,
  cwd: str | None = None,
) -> dict[str, Any]:
  """Run an arbitrary shell command (admin mode only)."""
  command = (command or "").strip()
  if not command:
    return {"ok": False, "error": "command is required", "stdout": "", "stderr": ""}
  from ai.system.paths import openpilot_root

  workdir = cwd or str(openpilot_root())
  try:
    proc = subprocess.run(
      command,
      shell=True,
      capture_output=True,
      text=True,
      timeout=timeout,
      cwd=workdir,
    )
    stdout_lines = (proc.stdout or "").splitlines()
    if len(stdout_lines) > max_output_lines:
      stdout_lines = stdout_lines[:max_output_lines]
      stdout_lines.append("... (truncated)")
    stderr = (proc.stderr or "").strip()
    if len(stderr) > 8000:
      stderr = stderr[:8000] + "\n... (truncated)"
    return {
      "ok": proc.returncode == 0,
      "returncode": proc.returncode,
      "stdout": "\n".join(stdout_lines),
      "stderr": stderr,
      "cwd": workdir,
    }
  except subprocess.TimeoutExpired:
    return {"ok": False, "error": "Command timed out.", "stdout": "", "stderr": ""}
  except Exception as e:
    return {"ok": False, "error": str(e), "stdout": "", "stderr": ""}
