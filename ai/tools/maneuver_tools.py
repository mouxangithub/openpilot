"""Wrappers for tools/longitudinal_maneuvers and tools/lateral_maneuvers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ai.tools.op_run import OPENPILOT_ROOT, parse_report_path, resolve_route_ref, run_subprocess, validate_route_ref


def maneuver_mode_status() -> dict[str, Any]:
  try:
    from openpilot.common.params import Params
  except Exception as e:
    return {"ok": False, "error": f"Params unavailable: {e}"}

  p = Params()

  def _flag(key: str) -> bool:
    try:
      v = p.get(key)
      if v is None:
        return False
      if isinstance(v, bytes):
        return v in (b"1", b"true", b"True")
      return str(v).strip() in ("1", "true", "True")
    except Exception:
      return False

  return {
    "ok": True,
    "longitudinal_maneuver_mode": _flag("LongitudinalManeuverMode"),
    "lateral_maneuver_mode": _flag("LateralManeuverMode"),
    "hint": "Closed-course only. Enable via Settings > Developer or Param; AI does not auto-enable.",
    "docs": {
      "longitudinal": "tools/longitudinal_maneuvers/README.md",
      "lateral": "tools/lateral_maneuvers/README.md",
    },
  }


def _maneuver_report_summary(html_path: Path) -> str:
  if not html_path.is_file():
    return ""
  try:
    text = html_path.read_text(encoding="utf-8", errors="replace")
  except Exception:
    return ""
  text = re.sub(r"<[^>]+>", " ", text)
  text = re.sub(r"\s+", " ", text).strip()
  return text[:4000] + ("..." if len(text) > 4000 else "")


def long_maneuver_report(route: str, description: str | None = None) -> dict[str, Any]:
  err = validate_route_ref(route)
  if err:
    return {"ok": False, "error": err}
  route_arg = resolve_route_ref(route)
  script = OPENPILOT_ROOT / "tools" / "longitudinal_maneuvers" / "generate_report.py"
  if not script.is_file():
    return {"ok": False, "error": f"Script not found: {script}"}

  import sys
  cmd = [sys.executable, str(script), route_arg]
  if description:
    cmd.append(description)
  res = run_subprocess(cmd, timeout=600)
  report_path = parse_report_path(res.get("stdout", ""))
  summary = _maneuver_report_summary(Path(report_path)) if report_path else ""
  return {
    **res,
    "route": route_arg,
    "report_path": report_path,
    "summary_text": summary,
    "script": "tools/longitudinal_maneuvers/generate_report.py",
    "hint": "Open HTML on dev machine; tune pcm accel / longitudinal on PC.",
  }


def mpc_longitudinal_tuning_report(output_path: str | None = None) -> dict[str, Any]:
  """Run tools/longitudinal_maneuvers/mpc_longitudinal_tuning_report.py (simulation HTML)."""
  script = OPENPILOT_ROOT / "tools" / "longitudinal_maneuvers" / "mpc_longitudinal_tuning_report.py"
  if not script.is_file():
    return {"ok": False, "error": f"Script not found: {script}"}

  import sys
  import time

  reports_dir = OPENPILOT_ROOT / "ai" / "data" / "reports"
  reports_dir.mkdir(parents=True, exist_ok=True)
  out = output_path or str(reports_dir / f"mpc_long_tune_{int(time.time())}.html")

  cmd = [sys.executable, str(script), out]
  res = run_subprocess(cmd, timeout=900)
  summary = _maneuver_report_summary(Path(out)) if res.get("ok") else ""
  return {
    **res,
    "report_path": out if res.get("ok") else None,
    "summary_text": summary,
    "script": "tools/longitudinal_maneuvers/mpc_longitudinal_tuning_report.py",
    "hint": "MPC longitudinal simulation scenarios (no route required). Open HTML on dev machine.",
  }


def lat_maneuver_report(route: str, description: str | None = None) -> dict[str, Any]:
  err = validate_route_ref(route)
  if err:
    return {"ok": False, "error": err}
  route_arg = resolve_route_ref(route)
  script = OPENPILOT_ROOT / "tools" / "lateral_maneuvers" / "generate_report.py"
  if not script.is_file():
    return {"ok": False, "error": f"Script not found: {script}"}

  import sys
  cmd = [sys.executable, str(script), route_arg]
  if description:
    cmd.append(description)
  res = run_subprocess(cmd, timeout=600)
  report_path = parse_report_path(res.get("stdout", ""))
  summary = _maneuver_report_summary(Path(report_path)) if report_path else ""
  return {
    **res,
    "route": route_arg,
    "report_path": report_path,
    "summary_text": summary,
    "script": "tools/lateral_maneuvers/generate_report.py",
    "hint": "Open HTML on dev machine; tune lateral torque / ALKA on PC.",
  }


def maneuversd_status(get_state_reader) -> dict[str, Any]:
  """Longitudinal/lateral maneuver daemon status from managerState + Params."""
  from ai.tools.maneuver_tools import maneuver_mode_status

  modes = maneuver_mode_status()
  procs: list[dict[str, Any]] = []
  try:
    reader = get_state_reader()
    reader.update(timeout=0)
    data = reader.latest()
    procs = (data or {}).get("processes") or []
  except Exception:
    pass

  watch = {"maneuversd", "lateral_maneuversd"}
  maneuver_procs = [p for p in procs if p.get("name") in watch]
  return {
    "ok": True,
    "param_modes": modes,
    "maneuver_processes": maneuver_procs,
    "script": "tools/longitudinal_maneuvers/maneuversd.py",
    "hint": "Closed course only; AI does not enable ManeuverMode params.",
  }
