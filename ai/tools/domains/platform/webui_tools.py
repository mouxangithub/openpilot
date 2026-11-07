"""op Web UI (:5080) health checks and QA helpers for op助手."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_DEFAULT_PORT = 5080
_CACHE_BUST_HINT = "78"

DEV_PRESETS = [
  "home", "onroad_engaged", "onroad_disengaged", "override", "lat_only",
  "alert_critical", "e2e_green", "standstill_timer", "long_only", "alert_full",
  "home_update", "home_alerts", "confidence_low", "confidence_high", "onroad_overlay",
]


def _openpilot_root() -> Path:
  return Path(__file__).resolve().parents[4]


def _webui_root() -> Path:
  return _openpilot_root() / "webui"


def _read_text(rel: str) -> str | None:
  path = _webui_root() / rel
  if not path.is_file():
    return None
  try:
    return path.read_text(encoding="utf-8", errors="replace")
  except OSError:
    return None


def _http_json(url: str, *, method: str = "GET", body: dict | None = None, timeout: float = 8.0) -> dict[str, Any]:
  data = None
  headers = {"Accept": "application/json"}
  if body is not None:
    data = json.dumps(body).encode("utf-8")
    headers["Content-Type"] = "application/json"
  req = urllib.request.Request(url, data=data, headers=headers, method=method)
  try:
    with urllib.request.urlopen(req, timeout=timeout) as resp:
      raw = resp.read()
      try:
        parsed = json.loads(raw.decode("utf-8", errors="replace"))
      except json.JSONDecodeError:
        parsed = {"raw": raw[:500].decode("utf-8", errors="replace")}
      return {"ok": True, "status": resp.status, "data": parsed}
  except urllib.error.HTTPError as exc:
    try:
      err_body = exc.read().decode("utf-8", errors="replace")[:400]
    except Exception:
      err_body = ""
    return {"ok": False, "status": exc.code, "error": err_body or str(exc)}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def _port_open(host: str, port: int) -> bool:
  try:
    with socket.create_connection((host, port), timeout=2.0):
      return True
  except OSError:
    return False


def _find_webui_pids() -> list[int]:
  try:
    out = subprocess.check_output(
      ["pgrep", "-f", r"webui\.webuid|webui/dev/run_pc"],
      text=True,
      stderr=subprocess.DEVNULL,
    )
    return [int(x) for x in out.split() if x.strip().isdigit()]
  except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
    return []


def webui_package_info() -> dict[str, Any]:
  ver = (_read_text("VERSION") or "").strip()
  return {
    "ok": True,
    "version": ver or None,
    "webui_root": str(_webui_root()),
    "cache_bust_hint": _CACHE_BUST_HINT,
    "docs": {
      "handoff": "webui/docs/OP_ASSISTANT_HANDOFF.md",
      "vehicle_qa": "webui/docs/VEHICLE_QA_CHECKLIST.md",
      "pc_device_scrcpy": "webui/docs/TESTING_PC_DEVICE_SCRCPY.md",
      "gui_alignment": "webui/docs/GUI_ALIGNMENT.md",
    },
  }


def webui_service_status(host: str = "127.0.0.1", port: int = _DEFAULT_PORT) -> dict[str, Any]:
  pids = _find_webui_pids()
  port_ok = _port_open(host, port)
  return {
    "ok": port_ok,
    "host": host,
    "port": port,
    "port_listening": port_ok,
    "pids": pids,
    "dev_pc": os.environ.get("WEBUI_DEV_PC") == "1",
    "hint": (
      "车机: python3.12 -m webui.webuid --host 0.0.0.0 --port 5080\n"
      "PC: py -3 webui/dev/run_pc.py --port 5080"
    ),
  }


def webui_health_check(
  host: str = "127.0.0.1",
  port: int = _DEFAULT_PORT,
  cache_bust: str = "",
) -> dict[str, Any]:
  base = f"http://{host}:{port}"
  bust = (cache_bust or _CACHE_BUST_HINT).strip()
  checks: list[dict[str, Any]] = []

  svc = webui_service_status(host=host, port=port)
  checks.append({
    "id": "port",
    "status": "ok" if svc.get("port_listening") else "fail",
    "summary": f"port {port} listening={svc.get('port_listening')}",
  })

  bootstrap = _http_json(f"{base}/api/opui/bootstrap")
  bdata = bootstrap.get("data") if bootstrap.get("ok") else {}
  checks.append({
    "id": "bootstrap",
    "status": "ok" if bootstrap.get("ok") and isinstance(bdata, dict) and bdata.get("ok") else "fail",
    "summary": "bootstrap ok" if bootstrap.get("ok") else bootstrap.get("error", "bootstrap failed"),
    "dev_pc": bool(bdata.get("dev_pc")) if isinstance(bdata, dict) else None,
    "version": bdata.get("version") if isinstance(bdata, dict) else None,
  })

  state = _http_json(f"{base}/api/opui/state")
  sdata = state.get("data") if state.get("ok") else {}
  checks.append({
    "id": "state",
    "status": "ok" if state.get("ok") and isinstance(sdata, dict) and sdata.get("ok") else "fail",
    "summary": (
      f"started={sdata.get('started')} engaged={sdata.get('engaged')} ui={sdata.get('ui_status')}"
      if isinstance(sdata, dict) else state.get("error", "state failed")
    ),
  })

  overlay = _http_json(f"{base}/api/opui/model/overlay?w=1600&h=900")
  odata = overlay.get("data") if overlay.get("ok") else {}
  lane_n = len(odata.get("lanes") or []) if isinstance(odata, dict) else 0
  checks.append({
    "id": "overlay",
    "status": "ok" if overlay.get("ok") and isinstance(odata, dict) and odata.get("ok") else "warn",
    "summary": (
      f"lanes={lane_n} leads={len(odata.get('leads') or [])}"
      if isinstance(odata, dict) else overlay.get("error")
    ),
    "dev_pc": bool(odata.get("dev_pc")) if isinstance(odata, dict) else None,
  })

  overall = "fail" if any(c["status"] == "fail" for c in checks) else (
    "warn" if any(c["status"] == "warn" for c in checks) else "ok"
  )
  dev_pc = bool(bdata.get("dev_pc")) if isinstance(bdata, dict) else False

  return {
    "ok": overall != "fail",
    "overall": overall,
    "url": f"{base}/?v={bust}" if bust else base,
    "cache_bust": bust,
    "checks": checks,
    "package": webui_package_info(),
    "next": [
      "启动 webui" if not svc.get("port_listening") else "浏览器强刷 ?v=" + bust,
      "PC 用 Dev 预设 onroad_overlay；上车按 VEHICLE_QA_CHECKLIST.md",
      "交接: webui/docs/OP_ASSISTANT_HANDOFF.md",
    ],
  }


def webui_apply_dev_preset(preset: str, host: str = "127.0.0.1", port: int = _DEFAULT_PORT) -> dict[str, Any]:
  preset = re.sub(r"[^\w_]+", "", preset or "").strip()
  if not preset:
    return {"ok": False, "error": "preset required"}
  url = f"http://{host}:{port}/api/opui/dev/preset/{preset}"
  res = _http_json(url, method="POST", body={})
  if not res.get("ok"):
    return {
      "ok": False,
      "error": res.get("error", "request failed"),
      "hint": "仅 WEBUI_DEV_PC=1 时可用",
    }
  data = res.get("data") or {}
  st = data.get("state") or {}
  return {
    "ok": bool(data.get("ok")),
    "preset": preset,
    "state_summary": {
      "started": st.get("started"),
      "engaged": st.get("engaged"),
      "ui_status": st.get("ui_status"),
      "confidence_ball": st.get("confidence_ball"),
    },
  }


def webui_qa_checklist(scope: str = "vehicle") -> dict[str, Any]:
  scope = (scope or "vehicle").strip().lower()
  files = {
    "vehicle": "docs/VEHICLE_QA_CHECKLIST.md",
    "pc": "docs/TESTING_PC_DEVICE_SCRCPY.md",
    "handoff": "docs/OP_ASSISTANT_HANDOFF.md",
  }
  rel = files.get(scope, files["vehicle"])
  text = _read_text(rel)
  if not text:
    return {"ok": False, "error": f"missing {rel}"}
  items = []
  section = ""
  for line in text.splitlines():
    if line.startswith("## "):
      section = line[3:].strip()
    m = re.match(r"^- \[ \] (.+)$", line.strip())
    if m:
      items.append({"section": section, "text": m.group(1), "done": False})
  return {
    "ok": True,
    "scope": scope,
    "source": rel,
    "item_count": len(items),
    "items": items[:120],
  }


def webui_report_template() -> dict[str, Any]:
  return {
    "ok": True,
    "template": (
      "## WebUI 上车验收报告\n"
      "- 日期 / 设备 / 分支 / webui VERSION / 浏览器 ?v=78\n"
      "### P0 overlay（与 scrcpy 对照）\n"
      "- [ ] 车道线  - [ ] 彩虹路径  - [ ] 前车 chevron\n"
      "### v78 抛光项（PC 可验）\n"
      "- [ ] 边框圆角 0.12  - [ ] onroad_fade 底纹  - [ ] SLA 箭头淡入\n"
      "- [ ] SCC 淡入  - [ ] E2E 脉冲  - [ ] Home UPDATE/ALERTS i18n\n"
      "### 状态机 / 设置 / 结论 pass|fail\n"
    ),
  }


def webui_list_dev_presets() -> dict[str, Any]:
  return {
    "ok": True,
    "presets": DEV_PRESETS,
    "recommended": ["onroad_overlay", "confidence_low", "confidence_high", "onroad_engaged", "e2e_green"],
    "hint": "PC only: webui_apply_dev_preset(preset=onroad_overlay)",
  }


def webui_onboarding_status() -> dict[str, Any]:
  try:
    from webui.server.bridge.onboarding_api import onboarding_status
    return onboarding_status()
  except Exception as exc:
    return {"ok": False, "error": str(exc), "completed": True}


def webui_headless_status(host: str = "127.0.0.1", port: int = _DEFAULT_PORT) -> dict[str, Any]:
  """Read WebuiHeadlessMode / effective headless state from WebUI API."""
  base = f"http://{host}:{port}"
  res = _http_json(f"{base}/api/opui/headless-mode")
  if not res.get("ok"):
    return {
      "ok": False,
      "error": res.get("error", "headless-mode request failed"),
      "hint": "Ensure webui.webuid is running on :5080",
    }
  data = res.get("data") if isinstance(res.get("data"), dict) else {}
  return {
    "ok": bool(data.get("ok", True)),
    "host": host,
    "port": port,
    "mode": data.get("mode"),
    "effective_headless": data.get("effective_headless"),
    "has_builtin_display": data.get("has_builtin_display"),
    "can_turn_off": data.get("can_turn_off"),
    "doc": "ai/docs/HEADLESS_WEBUI.md",
    "skill": "headless-webui",
  }
