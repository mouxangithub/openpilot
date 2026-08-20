"""Device panel extras: calibration summary, languages, regulatory HTML."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from webui.server.bridge.headless_util import is_headless_mode
from webui.server.bridge.qr_data_url import qr_data_url as _qr_data_url

# Fallback when languages.json is unavailable (codes match openpilot GUI).
LANGUAGES = [
  ("en", "English"),
  ("zh-CHS", "中文（简体）"),
  ("de", "Deutsch"),
  ("es", "Español"),
  ("fr", "Français"),
  ("ja", "日本語"),
  ("ko", "한국어"),
  ("pt-BR", "Português"),
  ("th", "ไทย"),
  ("tr", "Türkçe"),
]


def _languages_json_path() -> Path | None:
  candidates = [
    Path(__file__).resolve().parents[3] / "openpilot" / "selfdrive" / "ui" / "translations" / "languages.json",
    Path(__file__).resolve().parents[4] / "openpilot" / "selfdrive" / "ui" / "translations" / "languages.json",
  ]
  for c in candidates:
    if c.is_file():
      return c
  return None


def _language_options() -> list[dict[str, str]]:
  path = _languages_json_path()
  if path:
    try:
      data = json.loads(path.read_text(encoding="utf-8"))
      return [{"id": code, "label": name} for name, code in data.items()]
    except Exception:
      pass
  return [{"id": k, "label": v} for k, v in LANGUAGES]


def _normalize_lang_id(lang: str) -> str:
  lang = (lang or "en").strip().removeprefix("main_")
  aliases = {
    "main": "en",
    "zh": "zh-CHS",
    "pt": "pt-BR",
  }
  return aliases.get(lang, lang)


def _fcc_path() -> Path | None:
  candidates = [
    Path(__file__).resolve().parents[3] / "openpilot" / "selfdrive" / "assets" / "offroad" / "fcc.html",
    Path(__file__).resolve().parents[4] / "openpilot" / "selfdrive" / "assets" / "offroad" / "fcc.html",
  ]
  for c in candidates:
    if c.is_file():
      return c
  return None


def _read_calibration_extra(p) -> dict[str, Any]:
  """Mirror openpilot selfdrive/ui/layouts/settings/device.py _update_calib_description."""
  cal: dict[str, Any] = {
    "has_mount_angles": False,
    "lag_perc": None,
    "torque_applicable": False,
    "torque_perc": None,
  }
  try:
    from cereal import log
    import openpilot.cereal.messaging as messaging

    calib_bytes = p.get("CalibrationParams")
    if calib_bytes:
      try:
        calib = messaging.log_from_bytes(calib_bytes, log.Event).extrinsicsCalibration
        if calib.calStatus != log.ExtrinsicsCalibration.Status.uncalibrated:
          cal["has_mount_angles"] = True
          cal["pitch_deg"] = math.degrees(calib.rpyCalib[1])
          cal["yaw_deg"] = math.degrees(calib.rpyCalib[2])
      except Exception:
        pass

    lag_bytes = p.get("LiveDelay")
    if lag_bytes:
      try:
        cal["lag_perc"] = int(messaging.log_from_bytes(lag_bytes, log.Event).lateralDelay.calPerc)
      except Exception:
        pass

    torque_bytes = p.get("LiveTorqueParameters")
    if torque_bytes:
      try:
        torque = messaging.log_from_bytes(torque_bytes, log.Event).lateralTorqueParameters
        if torque.useParams:
          cal["torque_applicable"] = True
          cal["torque_perc"] = int(torque.calPerc)
      except Exception:
        pass
  except Exception:
    pass
  return cal


def regulatory_html() -> dict[str, Any]:
  path = _fcc_path()
  if not path:
    return {"ok": False, "error": "fcc.html not found"}
  try:
    import re
    raw = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"<body[^>]*>(.*)</body>", raw, re.I | re.S)
    html = match.group(1).strip() if match else raw
    return {"ok": True, "html": html}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def device_extras() -> dict[str, Any]:
  try:
    from openpilot.common.params import Params
    p = Params()
    lang = _normalize_lang_id(str(p.get("LanguageSetting") or "en"))
    offroad_mode = p.get_bool("OffroadMode")
  except Exception:
    lang = "en"
    offroad_mode = False

  if os.environ.get("WEBUI_DEV_PC") == "1":
    return {
      "ok": True,
      "calibration": {
        "has_mount_angles": True,
        "pitch_deg": 1.2,
        "yaw_deg": -0.5,
        "lag_perc": 100,
        "torque_applicable": True,
        "torque_perc": 85,
      },
      "languages": _language_options(),
      "current_language": _normalize_lang_id(lang),
      "driver_camera_available": True,
      "offroad_mode": offroad_mode,
      "dev_pc": True,
      "headless": is_headless_mode(),
      "driver_view_enabled": False,
    }
  try:
    from openpilot.common.params import Params

    p = Params()
    cal = _read_calibration_extra(p)
    lang = _normalize_lang_id(str(p.get("LanguageSetting") or "en"))
    return {
      "ok": True,
      "calibration": cal,
      "languages": _language_options(),
      "current_language": lang,
      "driver_camera_available": True,
      "offroad_mode": p.get_bool("OffroadMode"),
      "headless": is_headless_mode(),
      "driver_view_enabled": p.get_bool("IsDriverViewEnabled"),
    }
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def set_language(lang_id: str) -> dict[str, Any]:
  lang_id = _normalize_lang_id(lang_id)
  valid = {opt["id"] for opt in _language_options()}
  if lang_id not in valid:
    return {"ok": False, "error": f"unsupported language: {lang_id}"}
  try:
    from openpilot.common.params import Params
    Params().put("LanguageSetting", lang_id, block=True)
    return {"ok": True, "language": lang_id}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def driver_view_status() -> dict[str, Any]:
  try:
    from openpilot.common.params import Params
    p = Params()
    return {
      "ok": True,
      "driver_view_enabled": p.get_bool("IsDriverViewEnabled"),
      "headless": is_headless_mode(),
    }
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def set_driver_view(enabled: bool) -> dict[str, Any]:
  try:
    from webui.server.bridge.offroad_guard import require_offroad
    blocked = require_offroad()
    if blocked:
      return blocked
    from openpilot.common.params import Params
    p = Params()
    p.put_bool("IsDriverViewEnabled", bool(enabled), block=True)
    return {
      "ok": True,
      "driver_view_enabled": p.get_bool("IsDriverViewEnabled"),
      "headless": is_headless_mode(),
    }
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def device_pair_url() -> dict[str, Any]:
  """Mirror PairingDialog QR URL (connect.comma.ai)."""
  try:
    if os.environ.get("WEBUI_DEV_PC") == "1":
      url = "https://connect.comma.ai/?pair=dev-preview"
      return {"ok": True, "url": url, "qr_data_url": _qr_data_url(url), "dev_pc": True}

    from openpilot.common.api import Api
    from openpilot.common.params import Params

    dongle_id = Params().get("DongleId") or ""
    token = Api(dongle_id).get_token({"pair": True})
    url = f"https://connect.comma.ai/?pair={token}"
    return {"ok": True, "url": url, "qr_data_url": _qr_data_url(url)}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}
