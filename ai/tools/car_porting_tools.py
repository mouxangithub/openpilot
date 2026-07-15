"""
Wrappers for openpilot tools/car_porting/ — used by op助手 vehicle-adaptation skill.

Read-only: does not write to opendbc/. Output can be saved via save_adaptation_draft.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from collections import defaultdict
from typing import Any

from ai.tools.op_run import OPENPILOT_ROOT, ROUTES_DIR, run_subprocess, validate_route_ref
from ai.tools.op_run import resolve_route_ref as resolve_car_porting_route

_ROUTES_DIR = ROUTES_DIR
_OPENPILOT_ROOT = OPENPILOT_ROOT
_MAX_OUTPUT_CHARS = 48_000
_TEST_TIMEOUT_SEC = 360


def _validate_route_ref(route: str) -> str | None:
  return validate_route_ref(route)


def _import_logreader():
  try:
    from openpilot.tools.lib.logreader import LogReader, ReadMode
    return LogReader, ReadMode
  except ImportError:
    from tools.lib.logreader import LogReader, ReadMode  # type: ignore
    return LogReader, ReadMode


def car_porting_auto_fingerprint(route: str, platform: str | None = None) -> dict[str, Any]:
  """
  Run tools/car_porting/auto_fingerprint.py logic on a route (qlog carParams + FW versions).
  """
  err = _validate_route_ref(route)
  if err:
    return {"ok": False, "error": err}

  route_arg = resolve_car_porting_route(route)
  try:
    from opendbc.car.debug.format_fingerprints import format_brand_fw_versions
    from opendbc.car.fingerprints import MIGRATION
    from opendbc.car.fw_versions import MODEL_TO_BRAND, match_fw_to_car
    LogReader, ReadMode = _import_logreader()
  except Exception as e:
    return {"ok": False, "error": f"car_porting dependencies unavailable: {e}"}

  try:
    lr = LogReader(route_arg, ReadMode.QLOG)
    CP = lr.first("carParams")
    if CP is None:
      return {"ok": False, "error": "No carParams in route qlog", "route": route_arg}

    car_platform = MIGRATION.get(CP.carFingerprint, CP.carFingerprint)
    resolved_platform = (platform or "").strip() or None

    if resolved_platform is not None:
      plat = resolved_platform
    elif car_platform != "MOCK":
      plat = car_platform
    else:
      _, matches = match_fw_to_car(CP.carFw, CP.carVin, log=False)
      if len(matches) != 1:
        return {
          "ok": False,
          "error": f"Unable to auto-determine platform (matches={list(matches)})",
          "route": route_arg,
          "car_fingerprint": CP.carFingerprint,
          "hint": "Pass platform explicitly, e.g. TOYOTA_COROLLA.",
        }
      plat = list(matches)[0]

    brand = MODEL_TO_BRAND.get(plat)
    if not brand:
      return {"ok": False, "error": f"Unknown platform: {plat}", "route": route_arg}

    fw_versions: dict[str, dict[tuple, list[bytes]]] = defaultdict(lambda: defaultdict(list))
    fw_rows: list[dict[str, Any]] = []
    for fw in CP.carFw:
      if fw.brand == brand and not fw.logging:
        addr = fw.address
        sub_addr = None if fw.subAddress == 0 else fw.subAddress
        key = (fw.ecu.raw, addr, sub_addr)
        fw_versions[plat][key].append(fw.fwVersion)
        fw_rows.append({
          "ecu": fw.ecu.raw,
          "address": addr,
          "sub_address": sub_addr,
          "fw_version": fw.fwVersion.decode("utf-8", errors="replace") if isinstance(fw.fwVersion, bytes) else str(fw.fwVersion),
        })

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
      format_brand_fw_versions(brand, fw_versions)
    output = buf.getvalue().strip()
    if len(output) > _MAX_OUTPUT_CHARS:
      output = output[:_MAX_OUTPUT_CHARS] + "\n... [truncated] ..."

    return {
      "ok": True,
      "route": route_arg,
      "platform": plat,
      "brand": brand,
      "car_fingerprint": CP.carFingerprint,
      "vin": CP.carVin or "",
      "fw_count": len(fw_rows),
      "fw_versions_output": output,
      "fw_rows": fw_rows[:80],
      "script": "tools/car_porting/auto_fingerprint.py",
      "hint": "Review fw_versions_output; merge into opendbc on dev machine or save_adaptation_draft.",
    }
  except Exception as e:
    return {"ok": False, "error": str(e), "route": route_arg}


def car_porting_test_route(route: str, car_model: str | None = None) -> dict[str, Any]:
  """
  Run tools/car_porting/test_car_model.py (TestCarModel unittest suite) on a route segment.
  """
  err = _validate_route_ref(route)
  if err:
    return {"ok": False, "error": err}

  route_arg = resolve_car_porting_route(route)
  script = _OPENPILOT_ROOT / "tools" / "car_porting" / "test_car_model.py"
  if not script.is_file():
    return {"ok": False, "error": f"Script not found: {script}"}

  cmd = [sys.executable, str(script), route_arg]
  model = (car_model or "").strip()
  if model:
    cmd.extend(["--car", model])

  res = run_subprocess(cmd, timeout=_TEST_TIMEOUT_SEC)
  stdout = res.get("stdout", "")
  stderr = res.get("stderr", "")
  passed = res.get("ok", False)
  failures = stdout.count("FAIL") + stdout.count("ERROR")
  return {
    "ok": passed,
    "route": route_arg,
    "car_model": model or None,
    "returncode": res.get("returncode"),
    "stdout": stdout,
    "stderr": stderr,
    "error": res.get("error"),
    "failures_hint": failures if not passed else 0,
    "script": "tools/car_porting/test_car_model.py",
    "hint": "Fix DBC/CarState/CarController on dev machine; re-run after port changes.",
  }


def car_porting_test_interfaces(brand: str | None = None) -> dict[str, Any]:
  """Run pytest selfdrive/car/tests/test_car_interfaces.py (optionally -k brand)."""
  test_file = _OPENPILOT_ROOT / "selfdrive" / "car" / "tests" / "test_car_interfaces.py"
  if not test_file.is_file():
    return {"ok": False, "error": f"Test file not found: {test_file}"}

  cmd = [sys.executable, "-m", "pytest", str(test_file), "-q", "--tb=short", "--no-header"]
  filt = (brand or "").strip()
  if filt:
    cmd.extend(["-k", filt.lower()])

  res = run_subprocess(cmd, timeout=_TEST_TIMEOUT_SEC)
  passed = res.get("ok", False)
  return {
    **res,
    "brand_filter": filt or None,
    "script": "selfdrive/car/tests/test_car_interfaces.py",
    "hint": "Fix interface.py / values.py on dev machine before in-car testing.",
  }


def car_porting_steering_accuracy(route: str, group: str = "all") -> dict[str, Any]:
  """Offline steering accuracy stats from route (tools/car_porting/measure_steering_accuracy.py)."""
  err = _validate_route_ref(route)
  if err:
    return {"ok": False, "error": err}
  route_arg = resolve_car_porting_route(route)

  try:
    LogReader, _ = _import_logreader()
  except Exception as e:
    return {"ok": False, "error": str(e)}

  all_groups = {
    "germany": 45, "veryfast": 35, "fast": 25, "medium": 15, "slow": 5, "crawl": 0,
  }
  display = list(all_groups.keys()) if group == "all" else ([group] if group in all_groups else None)
  if not display:
    return {"ok": False, "error": f"Invalid group; use: {', '.join(all_groups)} or all"}

  from collections import defaultdict
  speed_group_stats: dict[str, dict] = {
    g: defaultdict(lambda: {"err": 0.0, "cnt": 0, "=": 0, "+": 0, "-": 0, "steer": 0.0, "limited": 0, "saturated": 0, "dpp": 0.0})
    for g in all_groups
  }
  cnt = 0
  msg_cnt = 0
  sm: dict[str, Any] = {}

  try:
    lr = LogReader(route_arg, sort_by_time=True)
    for msg in lr:
      w = msg.which()
      if w == "carState":
        sm["carState"] = msg.carState
      elif w == "carControl":
        sm["carControl"] = msg.carControl
      elif w == "controlsState":
        sm["controlsState"] = msg.controlsState
      elif w == "modelV2":
        sm["modelV2"] = msg.modelV2
      elif w == "carOutput":
        sm["carOutput"] = msg.carOutput

      if w != "carControl" or not all(k in sm for k in ("carState", "controlsState", "modelV2", "carOutput")):
        continue

      msg_cnt += 1
      lateral = sm["controlsState"].lateralControlState
      control_type = list(lateral.to_dict().keys())[0]
      control_state = lateral.__getattr__(control_type)
      v_ego = sm["carState"].vEgo
      active = sm["controlsState"].active
      steer = sm["carOutput"].actuatorsOutput.torque
      standstill = sm["carState"].standstill
      steer_limited = abs(sm["carControl"].actuators.torque - sm["carControl"].actuatorsOutput.torque) > 1e-2
      overriding = sm["carState"].steeringPressed
      changing_lanes = sm["modelV2"].meta.laneChangeState != 0

      if active and not standstill and not overriding and not changing_lanes:
        cnt += 1
        if cnt >= 500:
          actual_angle = control_state.steeringAngleDeg
          desired_angle = control_state.steeringAngleDesiredDeg
          angle_error = round(abs(desired_angle - actual_angle), 2)
          actual_angle = round(actual_angle, 1)
          desired_angle = round(desired_angle, 1)
          angle_abs = int(abs(round(desired_angle, 0)))
          for gname, threshold in all_groups.items():
            if v_ego > threshold:
              bucket = speed_group_stats[gname][angle_abs]
              bucket["cnt"] += 1
              bucket["err"] += angle_error
              bucket["steer"] += abs(steer)
              if len(sm["modelV2"].position.y):
                bucket["dpp"] += abs(sm["modelV2"].position.y[0])
              if steer_limited:
                bucket["limited"] += 1
              if control_state.saturated:
                bucket["saturated"] += 1
              if actual_angle == desired_angle:
                bucket["="] += 1
              else:
                overshoot = desired_angle == 0.0 or (
                  (desired_angle > 0 and desired_angle < actual_angle) or
                  (desired_angle < 0 and desired_angle > actual_angle)
                )
                bucket["+" if overshoot else "-"] += 1
              break
      else:
        cnt = 0

    result_groups: dict[str, list[dict[str, Any]]] = {}
    for gname in display:
      rows = []
      for angle, v in sorted(speed_group_stats[gname].items()):
        if v["cnt"] <= 0:
          continue
        c = v["cnt"]
        rows.append({
          "desired_angle_deg": angle,
          "samples": c,
          "mean_error_deg": round(v["err"] / c, 3),
          "mean_steer_pct": int(v["steer"] / c * 100),
          "exact_pct": int(v["="] / c * 100),
          "undershoot_pct": int(v["-"] / c * 100),
          "overshoot_pct": int(v["+"] / c * 100),
          "limited_count": v["limited"],
          "saturated_count": v["saturated"],
          "mean_path_dev_m": round(v["dpp"] / c, 3) if v["dpp"] else 0,
        })
      result_groups[gname] = rows[:30]

    return {
      "ok": True,
      "route": route_arg,
      "messages_processed": msg_cnt,
      "groups": result_groups,
      "script": "tools/car_porting/measure_steering_accuracy.py",
      "hint": "Lower mean_error_deg and higher exact_pct = better lateral tracking.",
    }
  except Exception as e:
    return {"ok": False, "error": str(e), "route": route_arg}


def car_porting_fingerprint_to_draft(
  *,
  project_id: str,
  route: str,
  platform: str | None = None,
  notes: str = "",
) -> dict[str, Any]:
  """auto_fingerprint + save to adaptation_drafts/ (no opendbc write)."""
  fp = car_porting_auto_fingerprint(route, platform=platform)
  if not fp.get("ok"):
    return fp

  from ai.tools.adaptation import save_adaptation_draft

  meta = {
    "source": "tools/car_porting/auto_fingerprint.py",
    "route": fp.get("route"),
    "platform": fp.get("platform"),
    "brand": fp.get("brand"),
    "car_fingerprint": fp.get("car_fingerprint"),
  }
  files = {
    "car_porting_fw_versions.txt": fp.get("fw_versions_output", ""),
    "car_porting_meta.json": json.dumps(meta, ensure_ascii=False, indent=2),
  }
  draft_notes = notes or f"FW fingerprint from route {fp.get('route')} ({fp.get('platform')})"
  return save_adaptation_draft(
    project_id=project_id,
    fingerprint=str(fp.get("car_fingerprint", "")),
    files=files,
    notes=draft_notes,
    metadata=meta,
  )
