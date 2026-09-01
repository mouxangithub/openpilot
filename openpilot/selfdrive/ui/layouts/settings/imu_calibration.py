import json
import math

from openpilot.cereal import log
from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr, tr_noop
from openpilot.system.ui.widgets import Widget, DialogResult
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog, alert_dialog
from openpilot.system.ui.widgets.list_view import text_item, button_item, toggle_item
from openpilot.system.ui.widgets.scroller_tici import Scroller


class ImuCalibrationLayout(Widget):
  def __init__(self):
    super().__init__()
    self._params = Params()
    self._status = {"state": "idle", "progress": 0, "error": None}
    self._angles: dict[str, float] | None = None
    self._calibrated = False
    self._poll_counter = 0

    self._toggle = toggle_item(
      lambda: tr("Use IMU Calibration"),
      lambda: tr("Enable auto-calibration for devices mounted at large or arbitrary angles."),
      initial_state=self._params.get_bool("ImuCalibrationEnabled"),
      callback=self._on_enabled_changed,
    )

    self._start_btn = button_item(
      lambda: tr("Start IMU Calibration"),
      lambda: tr("START"),
      lambda: tr("Park on level ground, then drive straight to calibrate the device orientation."),
      callback=self._start_calibration,
    )

    self._reset_btn = button_item(
      lambda: tr("Reset IMU Calibration"),
      lambda: tr("RESET"),
      lambda: tr("Clear the IMU calibration and switch back to stock calibration."),
      callback=self._reset_calibration_prompt,
    )

    self._status_item = text_item(lambda: tr("Status"), lambda: self._status_text())
    self._angles_item = text_item(lambda: tr("Orientation"), lambda: self._angles_text())

    items = [
      self._toggle,
      self._status_item,
      self._angles_item,
      self._start_btn,
      self._reset_btn,
    ]
    self._scroller = Scroller(items, line_separator=True, spacing=0)

    self._refresh_status()

  def _status_text(self) -> str:
    state = self._status.get("state", "idle")
    progress = self._status.get("progress", 0)
    error = self._status.get("error")
    mapping = {
      "idle": tr("Idle"),
      "static_collecting": tr("Collecting static data — keep parked"),
      "dynamic_collecting": tr("Collecting dynamic data — drive straight"),
      "computing": tr("Computing calibration..."),
      "completed": tr("Calibration completed"),
      "failed": tr("Calibration failed"),
      "cancelled": tr("Calibration cancelled"),
    }
    text = mapping.get(state, state)
    if state in ("static_collecting", "dynamic_collecting") and progress > 0:
      text += f" ({progress}%)"
    if error:
      text += f" — {error}"
    return text

  def _angles_text(self) -> str:
    if not self._angles:
      return tr("Not calibrated")
    roll = self._angles.get("roll_deg", 0.0)
    pitch = self._angles.get("pitch_deg", 0.0)
    yaw = self._angles.get("yaw_deg", 0.0)
    return f"R {roll:.1f}°  P {pitch:.1f}°  Y {yaw:.1f}°"

  def _on_enabled_changed(self, enabled: bool) -> None:
    self._params.put_bool("ImuCalibrationEnabled", enabled)
    self._params.put_bool("OnroadCycleRequested", True)

  def _start_calibration(self) -> None:
    if ui_state.engaged:
      gui_app.push_widget(alert_dialog(tr("Disengage to start calibration")))
      return
    self._params.put_bool("ImuCalibrationEnabled", True)
    self._params.put_bool("ImuCalibrationRequested", True)
    self._toggle.action_item.set_state(True)

  def _reset_calibration_prompt(self) -> None:
    if ui_state.engaged:
      gui_app.push_widget(alert_dialog(tr("Disengage to reset calibration")))
      return

    def reset_calibration(result: DialogResult):
      if ui_state.engaged or result != DialogResult.CONFIRM:
        return
      for key in ("ImuCalibrationMatrix", "ImuCalibrationStatus"):
        try:
          self._params.remove(key)
        except Exception:
          pass
      self._params.put_bool("ImuCalibrationRequested", False)
      self._params.put_bool("ImuCalibrationEnabled", False)
      self._params.put_bool("OnroadCycleRequested", True, block=True)
      self._toggle.action_item.set_state(False)
      self._refresh_status()

    dialog = ConfirmDialog(tr("Are you sure you want to clear the IMU calibration?"), tr("Reset"), callback=reset_calibration)
    gui_app.push_widget(dialog)

  def _refresh_status(self) -> None:
    try:
      status_json = self._params.get("ImuCalibrationStatus") or b"{}"
      if isinstance(status_json, bytes):
        status_json = status_json.decode("utf-8")
      self._status = json.loads(status_json)
    except Exception:
      self._status = {"state": "idle", "progress": 0, "error": None}

    self._angles = None
    self._calibrated = False
    matrix_data = self._params.get("ImuCalibrationMatrix")
    if matrix_data and len(matrix_data) == 36:
      try:
        import numpy as np
        R = np.frombuffer(matrix_data, dtype=np.float32).reshape(3, 3)
        pitch = math.asin(-float(R[2, 0]))
        yaw = math.atan2(float(R[1, 0]), float(R[0, 0]))
        roll = math.atan2(float(R[2, 1]), float(R[2, 2]))
        self._angles = {
          "roll_deg": math.degrees(roll),
          "pitch_deg": math.degrees(pitch),
          "yaw_deg": math.degrees(yaw),
        }
        self._calibrated = self._status.get("state") == "completed"
      except Exception:
        cloudlog.exception("invalid ImuCalibrationMatrix")

    enabled = self._params.get_bool("ImuCalibrationEnabled")
    self._toggle.action_item.set_state(enabled)
    self._start_btn.set_visible(enabled)
    self._reset_btn.set_visible(enabled)

  def show_event(self):
    super().show_event()
    self._scroller.show_event()
    self._refresh_status()

  def hide_event(self):
    super().hide_event()
    self._scroller.hide_event()

  def _update_state(self):
    super()._update_state()
    self._poll_counter += 1
    if self._poll_counter >= 60:  # ~1 second at 60 fps
      self._poll_counter = 0
      self._refresh_status()

  def _render(self, rect):
    self._scroller.render(rect)