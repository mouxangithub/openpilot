import json
import math

import pyray as rl

from openpilot.cereal import log
from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.ui.mici.widgets.button import BigButton, BigParamControl
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.selfdrive.ui.mici.widgets.dialog import BigDialog
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.scroller import NavScroller


class ImuCalibrationInfo(Widget):
  """Simple read-only status widget for IMU calibration."""

  def __init__(self):
    super().__init__()
    self._status = tr("Not calibrated")
    self._angles = ""
    self._quality = ""

  def set_status(self, status: str, angles: str = "", quality: str = "") -> None:
    self._status = status
    self._angles = angles
    self._quality = quality

  def _render(self, rect: rl.Rectangle):
    rl.draw_rectangle_rounded(rect, 0.1, 20, rl.Color(55, 55, 55, 255))
    status_size = 48
    detail_size = 36
    status_y = rect.y + rect.height * 0.20
    angles_y = rect.y + rect.height * 0.50
    quality_y = rect.y + rect.height * 0.75
    font = gui_app.font("normal")
    status_width = measure_text_cached(font, self._status, status_size, 0).x
    rl.draw_text_ex(font, self._status,
                    rl.Vector2(rect.x + (rect.width - status_width) / 2, status_y),
                    status_size, 0, rl.WHITE)
    if self._angles:
      angles_width = measure_text_cached(font, self._angles, detail_size, 0).x
      rl.draw_text_ex(font, self._angles,
                      rl.Vector2(rect.x + (rect.width - angles_width) / 2, angles_y),
                      detail_size, 0, rl.Color(170, 170, 170, 255))
    if self._quality:
      quality_width = measure_text_cached(font, self._quality, detail_size, 0).x
      rl.draw_text_ex(font, self._quality,
                      rl.Vector2(rect.x + (rect.width - quality_width) / 2, quality_y),
                      detail_size, 0, rl.Color(170, 170, 170, 255))


class ImuCalibrationLayoutMici(NavScroller):
  def __init__(self):
    super().__init__()
    self._params = Params()
    self._status_widget = ImuCalibrationInfo()

    self._enabled_toggle = BigParamControl("use imu calibration", "ImuCalibrationEnabled",
                                           toggle_callback=self._on_enabled_changed)

    self._start_btn = BigButton("start imu calibration", "", gui_app.texture("icons_mici/settings/developer_icon.png", 64, 60))
    self._start_btn.set_click_callback(self._start_calibration)

    self._reset_btn = BigButton("reset imu calibration", "", gui_app.texture("icons_mici/settings/device/lkas.png", 64, 64))
    self._reset_btn.set_click_callback(self._reset_calibration)

    self._scroller.add_widgets([
      self._enabled_toggle,
      self._status_widget,
      self._start_btn,
      self._reset_btn,
    ])

    self._poll_counter = 0
    self._live_angles_text = ""
    self._live_quality_text = ""
    self._refresh_status()

  def _on_enabled_changed(self, enabled: bool) -> None:
    self._params.put_bool("ImuCalibrationEnabled", enabled)
    self._params.put_bool("OnroadCycleRequested", True)
    self._refresh_status()

  def _start_calibration(self) -> None:
    if ui_state.engaged:
      gui_app.push_widget(BigDialog("", tr("Disengage to start calibration")))
      return
    self._params.put_bool("ImuCalibrationEnabled", True)
    self._params.put_bool("ImuCalibrationRequested", True)
    self._enabled_toggle.set_checked(True)
    self._refresh_status()

  def _reset_calibration(self) -> None:
    if ui_state.engaged:
      gui_app.push_widget(BigDialog("", tr("Disengage to reset calibration")))
      return
    for key in ("ImuCalibrationMatrix", "ImuCalibrationStatus"):
      try:
        self._params.remove(key)
      except Exception:
        pass
    self._params.put_bool("ImuCalibrationRequested", False)
    self._params.put_bool("ImuCalibrationEnabled", False)
    self._params.put_bool("OnroadCycleRequested", True)
    self._enabled_toggle.set_checked(False)
    self._refresh_status()

  def _refresh_status(self) -> None:
    try:
      status_json = self._params.get("ImuCalibrationStatus") or b"{}"
      if isinstance(status_json, bytes):
        status_json = status_json.decode("utf-8")
      status = json.loads(status_json)
    except Exception:
      status = {"state": "idle", "progress": 0, "error": None, "yaw_std": 0.0, "valid_ratio": 0.0}

    state = status.get("state", "idle")
    progress = status.get("progress", 0)
    error = status.get("error")

    mapping = {
      "idle": tr("Idle"),
      "static_collecting": tr("Keep parked"),
      "dynamic_collecting": tr("Drive straight"),
      "computing": tr("Computing..."),
      "completed": tr("Completed"),
      "failed": tr("Failed"),
      "cancelled": tr("Cancelled"),
    }
    text = mapping.get(state, state)
    if state in ("static_collecting", "dynamic_collecting") and progress > 0:
      text += f" ({progress}%)"
    if error:
      text += f" — {error}"

    angles_text = ""
    quality_text = ""

    # During dynamic calibration the live preview is fed by imuCalibrationSP.
    # Avoid reading the saved matrix param while still collecting.
    if state in ("dynamic_collecting", "computing"):
      angles_text = self._live_angles_text
      quality_text = self._live_quality_text
    else:
      matrix_data = self._params.get("ImuCalibrationMatrix")
      if matrix_data and len(matrix_data) == 36:
        try:
          import numpy as np
          R = np.frombuffer(matrix_data, dtype=np.float32).reshape(3, 3)
          pitch = math.asin(-float(R[2, 0]))
          yaw = math.atan2(float(R[1, 0]), float(R[0, 0]))
          roll = math.atan2(float(R[2, 1]), float(R[2, 2]))
          angles_text = f"R {math.degrees(roll):.1f}°  P {math.degrees(pitch):.1f}°  Y {math.degrees(yaw):.1f}°"
        except Exception:
          cloudlog.exception("invalid ImuCalibrationMatrix")

      if state == "completed":
        yaw_std = status.get("yaw_std", 0.0)
        valid_ratio = status.get("valid_ratio", 0.0)
        quality_text = f"yaw std {math.degrees(yaw_std):.1f}°  inliers {valid_ratio:.0%}"

    self._status_widget.set_status(text, angles_text, quality_text)

    enabled = self._params.get_bool("ImuCalibrationEnabled")
    self._start_btn.set_visible(enabled)
    self._reset_btn.set_visible(enabled)
    self._enabled_toggle.set_checked(enabled)

  def _update_live_angles(self) -> None:
    sm = ui_state.sm
    if not sm.updated.get("imuCalibrationSP"):
      return
    msg = sm["imuCalibrationSP"]
    if msg.status not in (log.ImuCalibrationSP.Status.dynamicCollecting, log.ImuCalibrationSP.Status.computing):
      return
    rpy = msg.rpyCalib
    if len(rpy) < 3:
      return
    roll, pitch, yaw = rpy[0], rpy[1], rpy[2]
    self._live_angles_text = f"R {math.degrees(roll):.1f}°  P {math.degrees(pitch):.1f}°  Y {math.degrees(yaw):.1f}°"
    self._live_quality_text = f"yaw std {math.degrees(msg.yawStd):.1f}°  inliers {msg.validRatio:.0%}"

  def _update_state(self):
    super()._update_state()
    self._update_live_angles()
    self._poll_counter += 1
    if self._poll_counter >= 60:  # ~1 second at 60 fps
      self._poll_counter = 0
      self._refresh_status()
