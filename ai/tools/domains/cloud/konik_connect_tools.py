"""Konik Connect — 替代 Comma Connect 的设备配对工具（connect-killer 前三步）."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from ai.system.paths import is_comma_device, openpilot_root, rel_source, source_path

KONIK_PAIR_URL = "https://stable.konik.ai"
KONIK_API_HOST = "https://api.konik.ai"
KONIK_ATHENA_HOST = "wss://athena.konik.ai"
CONNECT_KILLER_REF = "https://github.com/MoreTore/connect-killer"

_PERSIST_RSA = Path("/persist/comma/id_rsa")
_PERSIST_RSA_PUB = Path("/persist/comma/id_rsa.pub")
_PERSIST_DONGLE = Path("/persist/comma/dongle_id")
_PARAMS_DONGLE = Path("/data/params/d/DongleId")
_IP_RE = re.compile(r"^[\w.\-]+$")


def _offroad_guard(
  get_state_reader: Callable[..., Any] | None,
  *,
  device_ip: str = "",
) -> dict[str, Any] | None:
  if is_comma_device() and get_state_reader:
    try:
      state = get_state_reader().update(timeout=0)
      if getattr(state, "started", False) and not getattr(state, "force_offroad", False):
        return {"ok": False, "error": "Konik 配对操作仅能在 offroad（停车）下进行。"}
    except Exception:
      pass
    return None

  ip = (device_ip or "").strip()
  if ip:
    chk = _ssh_run(ip, _device_python('print(int(Params().get_bool("IsOnroad") or False))'))
    if not chk.get("ok"):
      return {"ok": False, "error": f"无法经 SSH 检查行车状态: {chk.get('error') or chk.get('stderr')}"}
    if (chk.get("stdout") or "").strip() == "1":
      return {"ok": False, "error": "设备当前 onroad，请在停车 offroad 后再执行 Konik 配对操作。"}
    return None

  if not is_comma_device():
    return {
      "ok": False,
      "error": "写操作需在 comma 车机上执行，或在 PC 上提供 device_ip 经 SSH 操作。",
    }
  return None


def _device_python(body: str) -> str:
  return (
    'python3 -c "from openpilot.common.params import Params; '
    + body
    + '"'
  )


def _ssh_run(host: str, command: str, *, timeout: int = 120) -> dict[str, Any]:
  host = (host or "").strip()
  if not host or not _IP_RE.match(host):
    return {"ok": False, "error": "invalid device_ip"}
  ssh = shutil.which("ssh")
  if not ssh:
    return {"ok": False, "error": "ssh not installed"}
  args = [
    ssh,
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=8",
    "-o", "StrictHostKeyChecking=accept-new",
    f"comma@{host}",
    command,
  ]
  try:
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    return {
      "ok": proc.returncode == 0,
      "returncode": proc.returncode,
      "stdout": out[:6000],
      "stderr": err[:2000],
      "host": host,
    }
  except subprocess.TimeoutExpired:
    return {"ok": False, "error": f"SSH timed out after {timeout}s"}
  except Exception as e:
    return {"ok": False, "error": str(e)}


def _run_local(cmd: list[str], *, timeout: int = 180, cwd: str | None = None) -> dict[str, Any]:
  try:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    return {
      "ok": proc.returncode == 0,
      "returncode": proc.returncode,
      "stdout": out[:6000],
      "stderr": err[:2000],
    }
  except subprocess.TimeoutExpired:
    return {"ok": False, "error": "timeout"}
  except Exception as e:
    return {"ok": False, "error": str(e)}


def _file_brief(path: Path) -> dict[str, Any]:
  if not path.is_file():
    return {"exists": False, "path": str(path)}
  try:
    st = path.stat()
    return {
      "exists": True,
      "path": str(path),
      "size": st.st_size,
      "mtime": int(st.st_mtime),
    }
  except OSError as e:
    return {"exists": False, "path": str(path), "error": str(e)}


def _pub_fingerprint(path: Path) -> str:
  if not path.is_file():
    return ""
  try:
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest()[:16]
  except OSError:
    return ""


UNREGISTERED = "UnregisteredDevice"


def _konik_python_env() -> dict[str, str]:
  root = str(openpilot_root())
  env = dict(os.environ)
  env["PYTHONPATH"] = root
  venv_site = "/usr/local/venv/lib/python3.12/site-packages"
  if Path(venv_site).is_dir():
    env["PYTHONPATH"] = root + ":" + venv_site
  env.setdefault("API_HOST", KONIK_API_HOST)
  env.setdefault("ATHENA_HOST", KONIK_ATHENA_HOST)
  return env


def _is_registered_dongle(dongle_id: str | None) -> bool:
  return bool(dongle_id) and dongle_id not in (UNREGISTERED, "UnregisteredDevice")


def _read_dongle_id() -> str | None:
  try:
    from openpilot.common.params import Params
    dongle = Params().get("DongleId")
    if dongle:
      return str(dongle)
  except Exception:
    pass
  if _PERSIST_DONGLE.is_file():
    try:
      return _PERSIST_DONGLE.read_text(encoding="utf-8", errors="replace").strip() or None
    except OSError:
      pass
  return None


def _read_dongle_id_remote(device_ip: str) -> str | None:
  ip = (device_ip or "").strip()
  if not ip:
    return None
  cmd = (
    "cd /data/openpilot && PYTHONPATH=/data/openpilot python3.12 -c "
    "'from openpilot.common.params import Params; print(Params().get(\"DongleId\") or \"\")'"
  )
  result = _ssh_run(ip, cmd, timeout=20)
  if not result.get("ok"):
    return None
  val = (result.get("stdout") or "").strip()
  return val or None


def _step_register(device_ip: str = "") -> dict[str, Any]:
  dongle_id = _read_dongle_id()
  if not dongle_id and (device_ip or "").strip():
    dongle_id = _read_dongle_id_remote(device_ip)
  registered = _is_registered_dongle(dongle_id)
  return {
    "step": 4,
    "title": "向 Konik 注册设备",
    "done": registered,
    "dongle_id": dongle_id,
    "detail": (
      f"已注册 DongleId: {dongle_id}"
      if registered
      else "运行 konik_register_device(confirm=true) 或重启 manager 自动注册"
    ),
    "note": "manager 启动时也会调用 system/athena/registration.py 的 register()",
  }


def _konik_launch_configured() -> dict[str, Any]:
  env_api = (os.environ.get("API_HOST") or "").strip()
  env_athena = (os.environ.get("ATHENA_HOST") or "").strip()
  launch = openpilot_root() / "launch_openpilot.sh"
  launch_text = ""
  if launch.is_file():
    try:
      launch_text = launch.read_text(encoding="utf-8", errors="replace")
    except OSError:
      pass
  launch_has_api = KONIK_API_HOST in launch_text
  launch_has_athena = KONIK_ATHENA_HOST in launch_text
  return {
    "api_host_env": env_api or None,
    "athena_host_env": env_athena or None,
    "launch_openpilot_sh": str(launch),
    "launch_exports_konik": launch_has_api and launch_has_athena,
    "expected_api_host": KONIK_API_HOST,
    "expected_athena_host": KONIK_ATHENA_HOST,
    "note": "步骤 4/5（API_HOST、ATHENA_HOST、配对站）已在本 fork 内置，无需自部署实例。",
  }


def _step_ssh(device_ip: str) -> dict[str, Any]:
  if is_comma_device():
    return {
      "step": 1,
      "title": "SSH 进入设备",
      "done": True,
      "detail": "当前已在 comma 设备上运行 op 助手。",
    }
  ip = (device_ip or "").strip()
  if not ip:
    return {
      "step": 1,
      "title": "SSH 进入设备",
      "done": False,
      "detail": "在 PC 上请提供 device_ip，或终端执行 ssh comma@<IP>",
      "hint": "可用 network_diagnostics(device_ip=...) 检测 SSH",
    }
  ping_ok = False
  ssh_ok = False
  if shutil.which("ping"):
    ping = _run_local(["ping", "-c", "1", "-W", "2", ip], timeout=8)
    ping_ok = bool(ping.get("ok"))
  if shutil.which("ssh"):
    ssh = _ssh_run(ip, "echo konik-ssh-ok", timeout=15)
    ssh_ok = bool(ssh.get("ok") and "konik-ssh-ok" in (ssh.get("stdout") or ""))
  return {
    "step": 1,
    "title": "SSH 进入设备",
    "done": ssh_ok,
    "device_ip": ip,
    "ping_ok": ping_ok,
    "ssh_ok": ssh_ok,
    "detail": "SSH 可用" if ssh_ok else "请先配置 ssh comma@<IP> 并完成主机密钥信任",
  }


def _step_keys() -> dict[str, Any]:
  priv = _file_brief(_PERSIST_RSA)
  pub = _file_brief(_PERSIST_RSA_PUB)
  done = bool(priv.get("exists") and pub.get("exists"))
  return {
    "step": 2,
    "title": "生成设备 RSA 密钥（克隆机必做）",
    "done": done,
    "private_key": priv,
    "public_key": pub,
    "public_key_fingerprint": _pub_fingerprint(_PERSIST_RSA_PUB) if done else "",
    "script": str(openpilot_root() / "1.sh"),
    "detail": "密钥已就绪" if done else "运行 konik_generate_device_keys(confirm=true) 或 bash 1.sh",
    "cloned_device_note": "克隆 comma 设备必须生成唯一密钥，否则无法正确注册。",
  }


def _step_dongle_reset() -> dict[str, Any]:
  params_exists = _PARAMS_DONGLE.is_file()
  persist_exists = _PERSIST_DONGLE.is_file()
  dongle_id = _read_dongle_id()
  needs_reset = params_exists or persist_exists or bool(dongle_id)
  return {
    "step": 3,
    "title": "清除旧 Dongle ID",
    "done": not needs_reset,
    "dongle_id": dongle_id,
    "params_file": _file_brief(_PARAMS_DONGLE),
    "persist_file": _file_brief(_PERSIST_DONGLE),
    "detail": "已清除，重启 manager 后将向 Konik 重新注册" if not needs_reset else "运行 konik_reset_dongle_id(confirm=true)",
  }


def konik_connect_status(*, device_ip: str = "") -> dict[str, Any]:
  """Konik Connect 配对进度：SSH、密钥、DongleId、注册与内置 Konik 端点."""
  steps = [_step_ssh(device_ip), _step_keys(), _step_dongle_reset(), _step_register(device_ip)]
  prep_done = all(s.get("done") for s in steps[:3])
  registered = bool(steps[3].get("done"))
  next_steps: list[str] = []
  for s in steps[:3]:
    if not s.get("done"):
      next_steps.append(f"步骤{s['step']}: {s['title']} — {s.get('detail', '')}")

  if prep_done and not registered:
    next_steps.append("步骤4: konik_register_device(confirm=true) 或 konik_connect_pipeline(confirm=true) 一条龙")
  if prep_done and registered:
    next_steps.append(f"在浏览器打开 {KONIK_PAIR_URL} 扫码配对（非 comma connect）")
    next_steps.append("配对后建议 manager_control(action=restart) 或重启设备")

  return {
    "ok": True,
    "brand": "Konik Connect",
    "tagline": "Konik 替换 openpilot Connect 服务",
    "pair_url": KONIK_PAIR_URL,
    "reference": CONNECT_KILLER_REF,
    "is_comma_device": is_comma_device(),
    "device_ip": (device_ip or "").strip() or None,
    "dongle_id": steps[3].get("dongle_id") or _read_dongle_id(),
    "registered": registered,
    "konik_endpoints": _konik_launch_configured(),
    "steps": steps,
    "ready_for_pairing": prep_done and registered,
    "prep_ready": prep_done,
    "next_steps": next_steps,
    "ai_rule": "一条龙用 konik_connect_pipeline(confirm=true)。勿输出完整私钥。步骤 4/5 端点已内置。",
  }


def _resolve_key_script() -> Path:
  script = openpilot_root() / "1.sh"
  if script.is_file():
    return script
  alt = Path("/data/openpilot/1.sh")
  if alt.is_file():
    return alt
  return script


def konik_generate_device_keys(
  *,
  confirm: bool = False,
  device_ip: str = "",
  get_state_reader: Callable[..., Any] | None = None,
) -> dict[str, Any]:
  """Offroad: 运行 1.sh 在 /persist/comma 生成 RSA 密钥对（connect-killer 步骤 2）."""
  if not confirm:
    status = konik_connect_status(device_ip=device_ip)
    return {
      "ok": True,
      "needs_confirmation": True,
      "hint": "将在 /persist/comma 生成新的 id_rsa / id_rsa.pub（克隆 comma 必做）。设置 confirm=true 执行。",
      "current": status.get("steps", [None, {}])[1] if len(status.get("steps", [])) > 1 else {},
    }

  err = _offroad_guard(get_state_reader, device_ip=device_ip)
  if err:
    return err

  script = _resolve_key_script()
  if is_comma_device():
    if not script.is_file():
      return {"ok": False, "error": f"未找到密钥脚本: {script}"}
    result = _run_local(["bash", str(script)], timeout=180, cwd=str(script.parent))
  else:
    ip = (device_ip or "").strip()
    remote_script = "/data/openpilot/1.sh"
    result = _ssh_run(ip, f"bash {remote_script}", timeout=180)

  pub_fp = _pub_fingerprint(_PERSIST_RSA_PUB)
  payload: dict[str, Any] = {
    "ok": bool(result.get("ok")),
    "action": "generate_device_keys",
    "script": str(script),
    "result": {k: result[k] for k in ("ok", "returncode", "stderr") if k in result},
    "public_key_fingerprint": pub_fp,
    "next": "执行 konik_connect_pipeline(confirm=true) 一条龙，或 konik_reset_dongle_id + konik_register_device",
  }
  if not result.get("ok"):
    payload["error"] = result.get("error") or result.get("stderr") or "密钥生成失败"
  if result.get("stdout"):
    # 仅保留 PEM 头尾提示，避免泄露完整公钥
    lines = [ln for ln in (result.get("stdout") or "").splitlines() if ln.strip()]
    payload["stdout_preview"] = "\n".join(lines[:3] + (["..."] if len(lines) > 6 else []) + lines[-2:])
  return payload


def konik_reset_dongle_id(
  *,
  confirm: bool = False,
  device_ip: str = "",
  get_state_reader: Callable[..., Any] | None = None,
) -> dict[str, Any]:
  """Offroad: 删除 DongleId（connect-killer 步骤 3），便于向 Konik 重新注册."""
  if not confirm:
    return {
      "ok": True,
      "needs_confirmation": True,
      "hint": "将删除 /data/params/d/DongleId 与 /persist/comma/dongle_id。设置 confirm=true 执行。",
      "current_dongle_id": _read_dongle_id(),
    }

  err = _offroad_guard(get_state_reader, device_ip=device_ip)
  if err:
    return err

  removed: list[str] = []
  errors: list[str] = []

  if is_comma_device():
    try:
      from openpilot.common.params import Params
      if Params().get("DongleId") is not None:
        Params().remove("DongleId")
        removed.append("Params:DongleId")
    except Exception as e:
      errors.append(f"Params.remove: {e}")
    for path in (_PARAMS_DONGLE, _PERSIST_DONGLE):
      if path.is_file():
        try:
          path.unlink()
          removed.append(str(path))
        except OSError as e:
          errors.append(f"{path}: {e}")
  else:
    ip = (device_ip or "").strip()
    cmd = (
      "rm -f /data/params/d/DongleId /persist/comma/dongle_id && "
      + _device_python('p=Params(); p.remove("DongleId") if p.get("DongleId") else None')
    )
    result = _ssh_run(ip, cmd, timeout=30)
    if result.get("ok"):
      removed.extend(["/data/params/d/DongleId", "/persist/comma/dongle_id"])
    else:
      errors.append(result.get("error") or result.get("stderr") or "SSH 删除失败")

  ok = len(errors) == 0
  return {
    "ok": ok,
    "action": "reset_dongle_id",
    "removed": removed,
    "errors": errors,
    "dongle_id_after": _read_dongle_id(),
    "next": f"manager_control(action=restart) 或重启设备，然后在 {KONIK_PAIR_URL} 扫码配对",
    "pair_url": KONIK_PAIR_URL,
  }


def _run_registration(*, device_ip: str = "") -> dict[str, Any]:
  reg_script = source_path("system", "athena", "registration.py")
  remote_script = "/data/openpilot/" + rel_source("system", "athena", "registration.py")
  env = _konik_python_env()

  if is_comma_device():
    if not reg_script.is_file():
      return {"ok": False, "error": f"未找到注册脚本: {reg_script}"}
    try:
      proc = subprocess.run(
        ["python3.12", str(reg_script)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(openpilot_root()),
        env=env,
      )
      result = {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "").strip()[:2000],
        "stderr": (proc.stderr or "").strip()[:2000],
      }
    except subprocess.TimeoutExpired:
      return {"ok": False, "error": "注册超时（120s），请检查 WiFi 与 api.konik.ai 连通性"}
    except Exception as e:
      return {"ok": False, "error": str(e)}
  else:
    ip = (device_ip or "").strip()
    if not ip:
      return {"ok": False, "error": "PC 侧需提供 device_ip 经 SSH 注册"}
    cmd = (
      f"cd /data/openpilot && API_HOST={KONIK_API_HOST} "
      f"PYTHONPATH=/data/openpilot python3.12 {remote_script}"
    )
    try:
      proc = subprocess.run(
        [
          shutil.which("ssh") or "ssh",
          "-o", "BatchMode=yes",
          "-o", "ConnectTimeout=10",
          "-o", "StrictHostKeyChecking=accept-new",
          f"comma@{ip}",
          cmd,
        ],
        capture_output=True,
        text=True,
        timeout=130,
      )
      result = {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "").strip()[:2000],
        "stderr": (proc.stderr or "").strip()[:2000],
      }
    except subprocess.TimeoutExpired:
      return {"ok": False, "error": "SSH 注册超时，请检查网络"}
    except Exception as e:
      return {"ok": False, "error": str(e)}

  dongle_id = (result.get("stdout") or "").strip().splitlines()[-1].strip() if result.get("stdout") else None
  if not dongle_id:
    dongle_id = _read_dongle_id()
    if not dongle_id and (device_ip or "").strip():
      dongle_id = _read_dongle_id_remote(device_ip)

  registered = _is_registered_dongle(dongle_id)
  ok = bool(result.get("ok")) and registered
  payload: dict[str, Any] = {
    "ok": ok,
    "action": "register_device",
    "dongle_id": dongle_id,
    "registered": registered,
    "api_host": env.get("API_HOST"),
    "result": {k: result[k] for k in ("ok", "returncode", "stderr") if k in result},
    "pair_url": KONIK_PAIR_URL,
    "next": f"打开 {KONIK_PAIR_URL} 扫码，将设备绑定到你的 Konik 账号",
  }
  if not ok:
    payload["error"] = (
      result.get("error")
      or result.get("stderr")
      or ("注册失败，DongleId=" + str(dongle_id))
    )
  return payload


def konik_register_device(
  *,
  confirm: bool = False,
  device_ip: str = "",
  get_state_reader: Callable[..., Any] | None = None,
) -> dict[str, Any]:
  """Offroad: 调用 registration.register() 向 Konik API 注册（获取新 DongleId）."""
  if not confirm:
    return {
      "ok": True,
      "needs_confirmation": True,
      "hint": "将调用 system/athena/registration.py 向 api.konik.ai 注册。需已生成密钥且已清除旧 DongleId。confirm=true 执行。",
      "current": _step_register(device_ip),
      "status": konik_connect_status(device_ip=device_ip),
    }

  err = _offroad_guard(get_state_reader, device_ip=device_ip)
  if err:
    return err

  keys = _step_keys()
  if not keys.get("done"):
    return {"ok": False, "error": "缺少 /persist/comma 密钥，请先 konik_generate_device_keys(confirm=true)"}

  return _run_registration(device_ip=device_ip)


def konik_connect_pipeline(
  *,
  confirm: bool = False,
  device_ip: str = "",
  regenerate_keys: bool = False,
  get_state_reader: Callable[..., Any] | None = None,
) -> dict[str, Any]:
  """一条龙：生成密钥（可选）→ 清 DongleId → Konik 注册 → 返回配对链接."""
  preview = konik_connect_status(device_ip=device_ip)
  if not confirm:
    return {
      "ok": True,
      "needs_confirmation": True,
      "brand": "Konik Connect 一条龙",
      "hint": "将依次：生成密钥（缺密钥或 regenerate_keys=true）→ 清除 DongleId → registration.register()。confirm=true 执行。",
      "regenerate_keys": regenerate_keys,
      "status": preview,
    }

  err = _offroad_guard(get_state_reader, device_ip=device_ip)
  if err:
    return err

  stages: list[dict[str, Any]] = []
  keys = _step_keys()
  if regenerate_keys or not keys.get("done"):
    stage = konik_generate_device_keys(
      confirm=True,
      device_ip=device_ip,
      get_state_reader=get_state_reader,
    )
    stages.append({"stage": "generate_keys", **stage})
    if not stage.get("ok"):
      return {
        "ok": False,
        "error": "密钥生成失败",
        "stages": stages,
        "status": konik_connect_status(device_ip=device_ip),
      }

  stage = konik_reset_dongle_id(
    confirm=True,
    device_ip=device_ip,
    get_state_reader=get_state_reader,
  )
  stages.append({"stage": "reset_dongle_id", **stage})
  if not stage.get("ok"):
    return {
      "ok": False,
      "error": "清除 DongleId 失败",
      "stages": stages,
      "status": konik_connect_status(device_ip=device_ip),
    }

  stage = _run_registration(device_ip=device_ip)
  stages.append({"stage": "register", **stage})
  final = konik_connect_status(device_ip=device_ip)
  ok = bool(stage.get("ok")) and bool(final.get("registered"))

  return {
    "ok": ok,
    "brand": "Konik Connect 一条龙",
    "dongle_id": stage.get("dongle_id"),
    "registered": final.get("registered"),
    "pair_url": KONIK_PAIR_URL,
    "stages": stages,
    "status": final,
    "next": (
      f"注册完成。请在浏览器打开 {KONIK_PAIR_URL} 扫码配对；"
      "完成后可 manager_control(action=restart)"
      if ok
      else "注册未完成，请检查网络与 konik_connect_status"
    ),
  }
