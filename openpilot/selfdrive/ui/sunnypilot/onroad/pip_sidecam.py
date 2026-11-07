"""
StarPilot side-camera picture-in-picture, ported to sunnypilot.

Original: StarPilot ``selfdrive/ui/onroad/starpilot/pip_sidecam.py`` - draws the
adjacent side window as a circular "bubble" over the road view when the
blinker is on or a blind-spot is detected.

!!! HARDWARE NOTE (Lite build) !!!
This widget consumes the ``VISION_STREAM_CABIN`` stream from camerad (the
driver-facing camera). The target vehicle runs Lite hardware with NO driver
camera, so on this car there is no publisher for that stream: the client never
connects and the widget renders nothing. The port is kept complete so it
becomes usable the moment a side/driver camera is fitted and published on the
driver stream. Param default is OFF (and it is inert without hardware anyway).

Adaptations for sunnypilot:
- StarPilot required both ``PIPPreviewEnabled`` and ``GalaxyDeveloperMode``;
  the latter is not registered here, so ``PIPPreviewEnabled`` alone gates the
  widget (still default OFF).
- StarPilot's ``get_fresh_vasm_state`` (Galaxy VASM blind-spot state) is
  replaced by the signals available here: ``carState.leftBlindspot`` /
  ``rightBlindspot`` plus the carrot LiDAR hints
  (``carStateSP.carrotLeftBlindHint`` / ``carrotRightBlindHint``).
- ``ui_state.params_memory`` does not exist on this UIState, so memory params
  use the memory params directory.
- The mask/crop JSON param ``PIPPreviewMask`` is unchanged; without a
  configured mask no bubble is drawn.
"""
from __future__ import annotations

import json
import platform
import weakref

import pyray as rl

from msgq.visionipc import VisionIpcClient
from openpilot.cereal.visionipc import VisionStreamType
from openpilot.common.params import Params
from openpilot.selfdrive.ui.sunnypilot.onroad.param_guards import safe_get_bool
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.widgets import Widget

PIP_SHADER_VERSION = """
#version 300 es
precision mediump float;
"""
if platform.system() == "Darwin":
  PIP_SHADER_VERSION = """
    #version 330 core
  """

PIP_VERTEX_SHADER = PIP_SHADER_VERSION + """
in vec3 vertexPosition;
in vec2 vertexTexCoord;
in vec3 vertexNormal;
in vec4 vertexColor;
uniform mat4 mvp;
out vec2 fragTexCoord;
out vec4 fragColor;
void main() {
  fragTexCoord = vertexTexCoord;
  fragColor = vertexColor;
  gl_Position = mvp * vec4(vertexPosition, 1.0);
}
"""

PIP_FRAGMENT_SHADER = PIP_SHADER_VERSION + """
in vec2 fragTexCoord;
uniform sampler2D texture0;
uniform sampler2D texture1;
uniform vec2 uCropMin;
uniform vec2 uCropSize;
uniform int uFlipX;
out vec4 fragColor;

const float BUBBLE_REFRACTION = 0.016;
const float BUBBLE_EDGE_DARKEN = 0.15;
const float BUBBLE_HIGHLIGHT = 0.12;
const float BUBBLE_RIM = 0.10;
const float BUBBLE_EDGE_TRANSPARENCY = 0.12;

void main() {
  // Calculate the mask before sampling: fragments outside the bubble do no texture work.
  vec2 p = fragTexCoord * 2.0 - 1.0;
  float radius = length(p);
  float aa = max(fwidth(radius), 0.00001);
  float alpha = 1.0 - smoothstep(1.0 - aa, 1.0 + aa, radius);
  if (radius > 1.0 + aa) {
    discard;
  }

  // A shallow hemisphere gives the image a convex bubble surface without a mesh or pass.
  float z = sqrt(max(0.0, 1.0 - dot(p, p)));
  vec2 sampleCoord = clamp(
    fragTexCoord + p * BUBBLE_REFRACTION * (1.0 - z),
    0.001,
    0.999
  );

  vec2 cropCoord = sampleCoord;
  if (uFlipX == 1) {
    cropCoord.x = 1.0 - cropCoord.x;
  }
  vec2 uv = uCropMin + cropCoord * uCropSize;
  float y = texture(texture0, uv).r;
  vec2 c = texture(texture1, uv).ra - 0.5;
  vec3 rgb = vec3(y + 1.402 * c.y, y - 0.344 * c.x - 0.714 * c.y, y + 1.772 * c.x);

  // Keep the interior gradient and use cheap analytic lighting instead of specular math.
  float edgeShade = smoothstep(0.22, 0.98, radius);
  rgb *= mix(1.0, 1.0 - BUBBLE_EDGE_DARKEN, edgeShade);

  vec2 highlightOffset = p - vec2(-0.28, -0.34);
  float highlight = 1.0 - smoothstep(0.0, 0.22, dot(highlightOffset, highlightOffset));
  rgb += vec3(1.0) * highlight * z * BUBBLE_HIGHLIGHT;

  // Let the rim blend into the camera image and the UI underneath it.
  float rim = smoothstep(0.60, 0.99, radius);
  rgb = mix(rgb, vec3(0.48, 0.70, 1.0), rim * BUBBLE_RIM);
  float surfaceAlpha = alpha * (1.0 - rim * BUBBLE_EDGE_TRANSPARENCY);
  fragColor = vec4(rgb, surfaceAlpha);
}
"""

UNIFORM_VEC2 = rl.ShaderUniformDataType.SHADER_UNIFORM_VEC2
UNIFORM_INT = rl.ShaderUniformDataType.SHADER_UNIFORM_INT

# The driver camera image is mirrored relative to the vehicle, so image-left is
# the vehicle's right side.
IMAGE_TO_VEHICLE_SIDE = {
  "left": "right",
  "right": "left",
}

CONNECTION_RETRY_INTERVAL = 0.2
PARAM_REFRESH_INTERVAL = 2.0

# Bubble geometry
BUBBLE_RADIUS_FRACTION = 0.3
BUBBLE_RADIUS_MIN = 180
BUBBLE_RADIUS_MAX = 420
BUBBLE_MARGIN = 24


class PipSideCamera(Widget):
  """Overlays the adjacent side window from the driver camera as a bubble.

  NOTE (Lite hardware): there is no driver camera on this car, so the
  VISION_STREAM_CABIN client never connects and the widget stays invisible.
  See the module docstring.
  """

  def __init__(self):
    super().__init__()
    self.client = VisionIpcClient("camerad", VisionStreamType.VISION_STREAM_CABIN, conflate=True)
    self._stream_type = VisionStreamType.VISION_STREAM_CABIN
    self._last_connection_attempt = 0.0
    self.frame = None
    self._last_frame_id = -1
    self._texture_needs_update = True
    self.texture_y: rl.Texture | None = None
    self.texture_uv: rl.Texture | None = None
    self._closed = False

    # memory params: the mask and enable flags are transient tuning values
    self._params = ui_state.params

    self._enabled = False
    self._show_on_blinker = False
    self._show_on_bsm = False
    self._mask: dict = {}
    self._last_param_refresh = float("-inf")
    self._side_activation_time: dict[str, float] = {}
    self._active_sides: set[str] = set()
    self.set_visible(lambda: self._enabled)

    self.shader = rl.load_shader_from_memory(PIP_VERTEX_SHADER, PIP_FRAGMENT_SHADER)
    self._texture1_loc = rl.get_shader_location(self.shader, "texture1")
    self._crop_min_loc = rl.get_shader_location(self.shader, "uCropMin")
    self._crop_size_loc = rl.get_shader_location(self.shader, "uCropSize")
    self._flip_x_loc = rl.get_shader_location(self.shader, "uFlipX")
    self._flip_x_value = rl.ffi.new("int[1]", [1])

    self_ref = weakref.ref(self)

    def offroad_transition_callback():
      if (ref := self_ref()) is not None:
        ref._offroad_transition()

    self._offroad_transition_callback = offroad_transition_callback
    ui_state.add_offroad_transition_callback(self._offroad_transition_callback)

  def _offroad_transition(self):
    self._clear_textures()
    self.frame = None
    self._last_frame_id = -1
    self._last_connection_attempt = 0.0
    self.client = VisionIpcClient("camerad", self._stream_type, conflate=True)

  def close(self):
    if getattr(self, "_closed", False):
      return
    self._closed = True
    if getattr(self, "_offroad_transition_callback", None) is not None:
      ui_state.remove_offroad_transition_callback(self._offroad_transition_callback)
      self._offroad_transition_callback = None
    self._clear_textures()
    if (shader := getattr(self, "shader", None)) is not None and shader.id:
      rl.unload_shader(shader)
      shader.id = 0
    self.frame = None
    self.client = None

  def __del__(self):
    self.close()

  def _update_state(self):
    # runs before the visibility gate in Widget.render, so the throttled param
    # read can flip the widget on/off between frames
    self._refresh_config()

  def _refresh_config(self, force: bool = False):
    now = rl.get_time()
    if not force and now - self._last_param_refresh < PARAM_REFRESH_INTERVAL:
      return
    self._last_param_refresh = now
    self._enabled = safe_get_bool(self._params, "PIPPreviewEnabled", False)
    self._show_on_blinker = safe_get_bool(self._params, "PIPPreviewShowOnBlinker", False)
    self._show_on_bsm = safe_get_bool(self._params, "PIPPreviewShowOnBSM", False)
    self._flip_x_value[0] = 1 if safe_get_bool(self._params, "PIPPreviewInvert", False) else 0
    try:
      raw = self._params.get("PIPPreviewMask")
      if isinstance(raw, (bytes, str)):
        raw = json.loads(raw)
      self._mask = raw if isinstance(raw, dict) else {}
    except Exception:
      self._mask = {}

  def _blind_spot(self, side: str) -> bool:
    """Blind-spot state for a vehicle side, carrot hints included."""
    sm = ui_state.sm
    car_blind = False
    if sm.valid.get("carState", False) and sm.recv_frame["carState"] >= ui_state.started_frame:
      car_state = sm["carState"]
      car_blind = bool(car_state.leftBlindspot) if side == "left" else bool(car_state.rightBlindspot)
    carrot_hint = False
    if sm.valid.get("carStateSP", False) and sm.recv_frame["carStateSP"] >= ui_state.started_frame:
      car_state_sp = sm["carStateSP"]
      carrot_hint = bool(car_state_sp.carrotLeftBlindHint) if side == "left" else bool(car_state_sp.carrotRightBlindHint)
    return car_blind or carrot_hint

  def active_sides(self) -> list[str]:
    """Return vehicle-side keys whose preview bubble should show.

    The driver camera is not mirrored in the snapshot. Its image-left side is
    the vehicle's right side, so translate the image-relative mask keys before
    applying vehicle signals and blind-spot state.
    """
    if not ui_state.started:
      return []
    self._refresh_config()
    if not self._enabled or not self._mask:
      return []

    sm = ui_state.sm
    if not sm.valid.get("carState", False) or sm.recv_frame["carState"] < ui_state.started_frame:
      return []

    car_state = sm["carState"]
    left_blinker = bool(car_state.leftBlinker)
    right_blinker = bool(car_state.rightBlinker)
    left_bsm = self._blind_spot("left")
    right_bsm = self._blind_spot("right")

    sides = []
    for image_side, vehicle_side, blinker, blindspot in (
      ("left", IMAGE_TO_VEHICLE_SIDE["left"], right_blinker, right_bsm),
      ("right", IMAGE_TO_VEHICLE_SIDE["right"], left_blinker, left_bsm),
    ):
      if self._mask.get(f"center_{image_side}") and (
        (self._show_on_blinker and blinker) or (self._show_on_bsm and blindspot)
      ):
        sides.append(vehicle_side)
    return sides

  def _crop_rect(self, vehicle_side: str) -> rl.Rectangle | None:
    image_side = IMAGE_TO_VEHICLE_SIDE[vehicle_side]
    center = self._mask.get(f"center_{image_side}")
    size = self._mask.get("crop_size")
    if not center or len(center) < 2 or not size:
      return None
    try:
      cx, cy = float(center[0]), float(center[1])
      half = float(size) / 2.0
    except (TypeError, ValueError):
      return None
    if half <= 0:
      return None
    return rl.Rectangle(cx - half, cy - half, size, size)

  def _bubble_rect(self, content_rect: rl.Rectangle, side: str) -> rl.Rectangle:
    radius = int(min(content_rect.width, content_rect.height) * BUBBLE_RADIUS_FRACTION)
    radius = max(BUBBLE_RADIUS_MIN, min(radius, BUBBLE_RADIUS_MAX))
    margin = BUBBLE_MARGIN
    cx = content_rect.x + margin + radius if side == "left" else content_rect.x + content_rect.width - margin - radius
    cy = content_rect.y + content_rect.height - margin - radius
    return rl.Rectangle(cx - radius, cy - radius, radius * 2, radius * 2)

  def _acquire_frame(self) -> bool:
    """Ensure connection and refresh the Y/UV textures from the latest driver frame."""
    if not self._ensure_connection():
      return False

    buffer = self.client.recv(timeout_ms=0)
    if buffer:
      self.frame = buffer
      self._last_frame_id = int(getattr(buffer, "frame_id", -1))
      self._texture_needs_update = True
    if self.frame is None:
      return False

    if not self.texture_y or not self.texture_uv:
      return False

    if self._texture_needs_update:
      y_data = self.frame.data[: self.frame.uv_offset]
      uv_data = self.frame.data[self.frame.uv_offset:]
      rl.update_texture(self.texture_y, rl.ffi.cast("void *", rl.ffi.from_buffer(y_data)))
      rl.update_texture(self.texture_uv, rl.ffi.cast("void *", rl.ffi.from_buffer(uv_data)))
      self._texture_needs_update = False
    return True

  def _render(self, content_rect: rl.Rectangle):
    """Fetch the current driver frame, then draw a bubble per active side."""
    if not ui_state.started:
      return None

    sides = self.active_sides()
    if not sides or not self._acquire_frame():
      return None

    for side in sides:
      crop = self._crop_rect(side)
      if crop is None:
        continue
      bubble = self._bubble_rect(content_rect, side)
      self._draw_bubble(bubble, crop)
    return None

  def _draw_bubble(self, bubble: rl.Rectangle, crop: rl.Rectangle):
    tex_w = float(self.texture_y.width)
    tex_h = float(self.texture_y.height)
    crop_min = rl.Vector2(crop.x / tex_w, crop.y / tex_h)
    crop_size = rl.Vector2(crop.width / tex_w, crop.height / tex_h)

    src_rect = rl.Rectangle(0, 0, tex_w, tex_h)
    dst_rect = rl.Rectangle(bubble.x, bubble.y, bubble.width, bubble.height)

    rl.begin_shader_mode(self.shader)
    rl.set_shader_value(self.shader, self._crop_min_loc, crop_min, UNIFORM_VEC2)
    rl.set_shader_value(self.shader, self._crop_size_loc, crop_size, UNIFORM_VEC2)
    rl.set_shader_value(self.shader, self._flip_x_loc, self._flip_x_value, UNIFORM_INT)
    rl.set_shader_value_texture(self.shader, self._texture1_loc, self.texture_uv)
    rl.draw_texture_pro(self.texture_y, src_rect, dst_rect, rl.Vector2(0, 0), 0.0, rl.WHITE)
    rl.end_shader_mode()

  def _ensure_connection(self) -> bool:
    if not self.client.is_connected():
      self.frame = None
      self._last_frame_id = -1

      now = rl.get_time()
      if now - self._last_connection_attempt < CONNECTION_RETRY_INTERVAL:
        return False
      self._last_connection_attempt = now

      self._clear_textures()
      if not self.client.connect(False) or not self.client.num_buffers:
        return False
      self._initialize_textures()
    return True

  def _initialize_textures(self):
    self._clear_textures()
    self.texture_y = rl.load_texture_from_image(rl.Image(None, int(self.client.stride),
      int(self.client.height), 1, rl.PixelFormat.PIXELFORMAT_UNCOMPRESSED_GRAYSCALE))
    self.texture_uv = rl.load_texture_from_image(rl.Image(None, int(self.client.stride // 2),
      int(self.client.height // 2), 1, rl.PixelFormat.PIXELFORMAT_UNCOMPRESSED_GRAY_ALPHA))

  def _clear_textures(self):
    if (texture_y := getattr(self, "texture_y", None)) is not None and texture_y.id:
      rl.unload_texture(texture_y)
      self.texture_y = None
    if (texture_uv := getattr(self, "texture_uv", None)) is not None and texture_uv.id:
      rl.unload_texture(texture_uv)
      self.texture_uv = None
