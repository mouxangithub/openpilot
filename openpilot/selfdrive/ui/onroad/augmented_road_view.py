from __future__ import annotations

import numpy as np
import pyray as rl
from openpilot.cereal import log
from openpilot.cereal.visionipc import VisionStreamType
from openpilot.selfdrive.ui import UI_BORDER_SIZE
from openpilot.selfdrive.ui.ui_state import ui_state, UIStatus
from openpilot.selfdrive.ui.onroad.alert_renderer import AlertRenderer
from openpilot.selfdrive.ui.onroad.driver_state import DriverStateRenderer
from openpilot.selfdrive.ui.onroad.hud_renderer import HudRenderer
from openpilot.selfdrive.ui.onroad.model_renderer import ModelRenderer
from openpilot.selfdrive.ui.onroad.cameraview import CameraView
from openpilot.system.ui.lib.application import gui_app, FontWeight, MousePos
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.widgets.label import UnifiedLabel
from openpilot.common.params import Params
from openpilot.common.transformations.camera import DEVICE_CAMERAS, DeviceCameraConfig, view_frame_from_device_frame
from openpilot.common.transformations.orientation import rot_from_euler

if gui_app.sunnypilot_ui():
  from openpilot.selfdrive.ui.sunnypilot.onroad.alert_renderer import AlertRendererSP as AlertRenderer
  from openpilot.selfdrive.ui.sunnypilot.onroad.augmented_road_view import BORDER_COLORS_SP, AugmentedRoadViewSP
  from openpilot.selfdrive.ui.sunnypilot.onroad.driver_state import DriverStateRendererSP as DriverStateRenderer
  from openpilot.selfdrive.ui.sunnypilot.onroad.hud_renderer import HudRendererSP as HudRenderer
  from openpilot.selfdrive.ui.sunnypilot.ui_state import OnroadTimerStatus

OpState = log.SelfdriveState.OpenpilotState
CALIBRATED = log.ExtrinsicsCalibration.Status.calibrated
NARROW_ROAD_CAM = VisionStreamType.VISION_STREAM_NARROW_ROAD
WIDE_CAM = VisionStreamType.VISION_STREAM_WIDE_ROAD
DEFAULT_DEVICE_CAMERA = DEVICE_CAMERAS["tici", "ar0231"]

BORDER_COLORS = {
  UIStatus.DISENGAGED: rl.Color(0x12, 0x28, 0x39, 0xFF),  # Blue for disengaged state
  UIStatus.OVERRIDE: rl.Color(0x89, 0x92, 0x8D, 0xFF),  # Gray for override state
  UIStatus.ENGAGED: rl.Color(0x16, 0x7F, 0x40, 0xFF),  # Green for engaged state
  **BORDER_COLORS_SP,
}

WIDE_CAM_MAX_SPEED = 10.0  # m/s (22 mph)
ROAD_CAM_MIN_SPEED = 15.0  # m/s (34 mph)
INF_POINT = np.array([1000.0, 0.0, 0.0])

PREVIEW_BTN_W = 200
PREVIEW_BTN_H = 80
PREVIEW_BTN_PAD = 16


class AugmentedRoadView(CameraView, AugmentedRoadViewSP):
  def __init__(self, stream_type: VisionStreamType = VisionStreamType.VISION_STREAM_NARROW_ROAD):
    CameraView.__init__(self, "camerad", stream_type)
    AugmentedRoadViewSP.__init__(self)
    self._set_placeholder_color(BORDER_COLORS[UIStatus.DISENGAGED])

    self.device_camera: DeviceCameraConfig | None = None
    self.view_from_calib = view_frame_from_device_frame.copy()
    self.view_from_wide_calib = view_frame_from_device_frame.copy()

    self._matrix_cache_key = (0, 0.0, 0.0, stream_type)
    self._cached_matrix: np.ndarray | None = None
    self._content_rect = rl.Rectangle()

    self._params = Params()
    self._preview_button_rects: dict[str, rl.Rectangle] = {}
    self._preview_button_pressed: str | None = None
    label_color = rl.Color(255, 255, 255, 230)
    self._preview_label_road = UnifiedLabel(tr("road"), 36, FontWeight.BOLD, text_color=label_color,
                                            alignment=rl.GuiTextAlignment.TEXT_ALIGN_CENTER,
                                            alignment_vertical=rl.GuiTextAlignmentVertical.TEXT_ALIGN_MIDDLE)
    self._preview_label_wide = UnifiedLabel(tr("wide"), 36, FontWeight.BOLD, text_color=label_color,
                                            alignment=rl.GuiTextAlignment.TEXT_ALIGN_CENTER,
                                            alignment_vertical=rl.GuiTextAlignmentVertical.TEXT_ALIGN_MIDDLE)
    self._preview_label_exit = UnifiedLabel(tr("exit"), 36, FontWeight.BOLD, text_color=label_color,
                                            alignment=rl.GuiTextAlignment.TEXT_ALIGN_CENTER,
                                            alignment_vertical=rl.GuiTextAlignmentVertical.TEXT_ALIGN_MIDDLE)

    self.model_renderer = ModelRenderer()
    self._hud_renderer = HudRenderer()
    self.alert_renderer = AlertRenderer()
    self.driver_state_renderer = DriverStateRenderer()

  def _render(self, rect):
    # Only render when system is started to avoid invalid data access
    if not ui_state.started:
      return

    self._switch_stream_if_needed(ui_state.sm)

    # Update calibration before rendering
    self._update_calibration()

    # Create inner content area with border padding
    self._content_rect = rl.Rectangle(
      rect.x + UI_BORDER_SIZE,
      rect.y + UI_BORDER_SIZE,
      rect.width - 2 * UI_BORDER_SIZE,
      rect.height - 2 * UI_BORDER_SIZE,
    )

    # Enable scissor mode to clip all rendering within content rectangle boundaries
    # This creates a rendering viewport that prevents graphics from drawing outside the border
    rl.begin_scissor_mode(
      int(self._content_rect.x),
      int(self._content_rect.y),
      int(self._content_rect.width),
      int(self._content_rect.height)
    )

    # Render the base camera view
    super()._render(self._content_rect)

    # Draw all UI overlays
    self.model_renderer.render(self._content_rect)
    AugmentedRoadViewSP.update_fade_out_bottom_overlay(self, self._content_rect)
    self._hud_renderer.render(self._content_rect)
    self.alert_renderer.render(self._content_rect)
    self.driver_state_renderer.render(self._content_rect)

    # Custom UI extension point - add custom overlays here
    # Use self._content_rect for positioning within camera bounds

    # End clipping region
    rl.end_scissor_mode()

    # Draw colored border based on driving state
    self._draw_border(rect)

    if self._params.get_bool("IsOnroadPreview"):
      self._draw_preview_controls()

  def _draw_preview_controls(self):
    if not ui_state.started:
      return
    total_width = 3 * PREVIEW_BTN_W + 2 * PREVIEW_BTN_PAD
    base_x = self._content_rect.x + (self._content_rect.width - total_width) / 2
    base_y = self._content_rect.y + self._content_rect.height - PREVIEW_BTN_H - PREVIEW_BTN_PAD
    is_road = self.stream_type == NARROW_ROAD_CAM

    wide_rect = rl.Rectangle(base_x, base_y, PREVIEW_BTN_W, PREVIEW_BTN_H)
    self._preview_button_rects["wide"] = wide_rect
    self._draw_preview_button(wide_rect, self._preview_label_wide, not is_road)

    road_rect = rl.Rectangle(base_x + PREVIEW_BTN_W + PREVIEW_BTN_PAD, base_y, PREVIEW_BTN_W, PREVIEW_BTN_H)
    self._preview_button_rects["road"] = road_rect
    self._draw_preview_button(road_rect, self._preview_label_road, is_road)

    exit_rect = rl.Rectangle(base_x + 2 * (PREVIEW_BTN_W + PREVIEW_BTN_PAD), base_y, PREVIEW_BTN_W, PREVIEW_BTN_H)
    self._preview_button_rects["exit"] = exit_rect
    self._draw_preview_button(exit_rect, self._preview_label_exit, False, bg_color=rl.Color(180, 60, 60, 200))

  def _draw_preview_button(self, rect: rl.Rectangle, label: UnifiedLabel, active: bool, bg_color: rl.Color | None = None):
    bg = bg_color if bg_color is not None else (rl.Color(0, 120, 60, 220) if active else rl.Color(40, 40, 40, 180))
    pressed_rect = self._preview_button_rects.get(self._preview_button_pressed)
    if pressed_rect is not None and pressed_rect == rect:
      bg = rl.Color(min(255, bg.r + 40), min(255, bg.g + 40), min(255, bg.b + 40), bg.a)
    rl.draw_rectangle_rounded(rect, 0.25, 8, bg)
    label.render(rect)

  def _handle_mouse_press(self, mouse_pos: MousePos):
    if self._params.get_bool("IsOnroadPreview"):
      for name, rect in self._preview_button_rects.items():
        if rl.check_collision_point_rec(rl.Vector2(mouse_pos.x, mouse_pos.y), rect):
          self._preview_button_pressed = name
          return

    if not self._hud_renderer.user_interacting() and self._click_callback is not None:
      self._click_callback()

  def _handle_mouse_release(self, mouse_pos: MousePos):
    pressed = self._preview_button_pressed
    self._preview_button_pressed = None
    if pressed is None or not self._params.get_bool("IsOnroadPreview"):
      return
    rect = self._preview_button_rects.get(pressed)
    if rect is None or not rl.check_collision_point_rec(rl.Vector2(mouse_pos.x, mouse_pos.y), rect):
      return
    if pressed == "road":
      self.switch_stream(NARROW_ROAD_CAM)
    elif pressed == "wide":
      self.switch_stream(WIDE_CAM)
    elif pressed == "exit":
      self._params.put_bool("IsOnroadPreview", False)

  def _draw_border(self, rect: rl.Rectangle):
    rl.draw_rectangle_lines_ex(rect, UI_BORDER_SIZE, rl.BLACK)
    border_roundness = 0.12
    border_color = BORDER_COLORS.get(ui_state.status, BORDER_COLORS[UIStatus.DISENGAGED])
    border_rect = rl.Rectangle(rect.x + UI_BORDER_SIZE, rect.y + UI_BORDER_SIZE,
                               rect.width - 2 * UI_BORDER_SIZE, rect.height - 2 * UI_BORDER_SIZE)
    rl.draw_rectangle_rounded_lines_ex(border_rect, border_roundness, 10, UI_BORDER_SIZE, border_color)

  def _switch_stream_if_needed(self, sm):
    # In onroad preview the user controls the camera manually.
    if self._params.get_bool("IsOnroadPreview"):
      return

    if sm['selfdriveState'].experimentalMode and WIDE_CAM in self.available_streams:
      v_ego = sm['carState'].vEgo
      if v_ego < WIDE_CAM_MAX_SPEED:
        target = WIDE_CAM
      elif v_ego > ROAD_CAM_MIN_SPEED:
        target = NARROW_ROAD_CAM
      else:
        # Hysteresis zone - keep current stream
        target = self.stream_type
    else:
      target = NARROW_ROAD_CAM

    if self.stream_type != target:
      self.switch_stream(target)

  def _update_calibration(self):
    # Update device camera if not already set
    sm = ui_state.sm
    if not self.device_camera and sm.seen['narrowRoadCameraState'] and sm.seen['deviceState']:
      self.device_camera = DEVICE_CAMERAS[(str(sm['deviceState'].deviceType), str(sm['narrowRoadCameraState'].sensor))]

    # Check if camera calibration data is available and valid
    if not (sm.updated["extrinsicsCalibration"] and sm.valid['extrinsicsCalibration']):
      return

    calib = sm['extrinsicsCalibration']
    if len(calib.rpyCalib) != 3 or calib.calStatus != CALIBRATED:
      return

    # Update view_from_calib matrix
    device_from_calib = rot_from_euler(calib.rpyCalib)
    self.view_from_calib = view_frame_from_device_frame @ device_from_calib

    # Update wide calibration if available
    if hasattr(calib, 'wideFromDeviceEuler') and len(calib.wideFromDeviceEuler) == 3:
      wide_from_device = rot_from_euler(calib.wideFromDeviceEuler)
      self.view_from_wide_calib = view_frame_from_device_frame @ wide_from_device @ device_from_calib

  def _calc_frame_matrix(self, rect: rl.Rectangle) -> np.ndarray:
    # Check if we can use cached matrix
    cache_key = (
      ui_state.sm.recv_frame['extrinsicsCalibration'],
      self._content_rect.width,
      self._content_rect.height,
      self.stream_type
    )
    if cache_key == self._matrix_cache_key and self._cached_matrix is not None:
      return self._cached_matrix

    # Get camera configuration
    device_camera = self.device_camera or DEFAULT_DEVICE_CAMERA
    is_wide_camera = self.stream_type == WIDE_CAM
    intrinsic = device_camera.wide_road.intrinsics if is_wide_camera else device_camera.narrow_road.intrinsics
    calibration = self.view_from_wide_calib if is_wide_camera else self.view_from_calib
    zoom = 2.0 if is_wide_camera else 1.1

    # Calculate transforms for vanishing point
    calib_transform = intrinsic @ calibration
    kep = calib_transform @ INF_POINT

    # Calculate center points and dimensions
    x, y = self._content_rect.x, self._content_rect.y
    w, h = self._content_rect.width, self._content_rect.height
    cx, cy = intrinsic[0, 2], intrinsic[1, 2]

    # Ensure zoom views the whole area
    zoom = max(zoom, w / (2 * cx), h / (2 * cy))

    # Calculate max allowed offsets with margins
    margin = 5
    max_x_offset = max(0.0, cx * zoom - w / 2 - margin)
    max_y_offset = max(0.0, cy * zoom - h / 2 - margin)

    # Calculate and clamp offsets to prevent out-of-bounds issues
    try:
      if abs(kep[2]) > 1e-6:
        x_offset = np.clip((kep[0] / kep[2] - cx) * zoom, -max_x_offset, max_x_offset)
        y_offset = np.clip((kep[1] / kep[2] - cy) * zoom, -max_y_offset, max_y_offset)
      else:
        x_offset, y_offset = 0, 0
    except (ZeroDivisionError, OverflowError):
      x_offset, y_offset = 0, 0

    # Cache the computed transformation matrix to avoid recalculations
    self._matrix_cache_key = cache_key
    self._cached_matrix = np.array([
      [zoom * 2 * cx / w, 0, -x_offset / w * 2],
      [0, zoom * 2 * cy / h, -y_offset / h * 2],
      [0, 0, 1.0]
    ])

    video_transform = np.array([
      [zoom, 0.0, (w / 2 + x - x_offset) - (cx * zoom)],
      [0.0, zoom, (h / 2 + y - y_offset) - (cy * zoom)],
      [0.0, 0.0, 1.0]
    ])
    self.model_renderer.set_transform(video_transform @ calib_transform)

    return self._cached_matrix

  def show_event(self):
    if gui_app.sunnypilot_ui():
      ui_state.reset_onroad_sleep_timer(OnroadTimerStatus.RESUME)

  def hide_event(self):
    if gui_app.sunnypilot_ui():
      ui_state.reset_onroad_sleep_timer(OnroadTimerStatus.PAUSE)


if __name__ == "__main__":
  gui_app.init_window("OnRoad Camera View")
  road_camera_view = AugmentedRoadView(NARROW_ROAD_CAM)
  gui_app.push_widget(road_camera_view)
  print("***press space to switch camera view***")
  try:
    for _ in gui_app.render():
      ui_state.update()
      if rl.is_key_released(rl.KeyboardKey.KEY_SPACE):
        if WIDE_CAM in road_camera_view.available_streams:
          stream = NARROW_ROAD_CAM if road_camera_view.stream_type == WIDE_CAM else WIDE_CAM
          road_camera_view.switch_stream(stream)
  finally:
    road_camera_view.close()
