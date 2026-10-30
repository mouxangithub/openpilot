"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Advisory signal HUD: an outer ring and a centre dot, both showing evidence.

Ported from carrot's ``selfdrive/ui/signal_status.py``, reading
``longitudinalPlanSP`` where carrot reads ``longitudinalPlan``.

The ring and the dot are drawn from the same value. This fork publishes
``signalAssistAction`` as the *observed light evidence* recorded by the modeld
tmpfs shadow (0 unknown, 1 red, 2 green, 3 mixed) and never publishes a
separate planner action, so the ring and the dot can only differ in shape, not
in meaning. Mixed evidence is amber rather than a green "cleared to go".

Carrot's design has two independent channels: the ring carries the evidence
and the dot carries the action the planner applied, which makes "a grey ring
with a red dot" reachable there. It is not reachable here, and copying
carrot's rendering verbatim would mislabel this fork's evidence as an action.

All of it is advisory: a painted colour never means the car is responding to
the signal. The ring is only reachable at all when SignalAssistMode > 0,
because the planner leaves the action at 0 (unknown) below that.
"""
import time

import pyray as rl

from openpilot.selfdrive.ui.signal_status import (
  POINT_COLOR_BACKDROP, POINT_COLOR_SHADOW, SIGNAL_PALETTE, signal_action, signal_colors,
  signal_suspended, signal_visible,
)
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import FontWeight, gui_app
from openpilot.system.ui.lib.text_measure import measure_text_cached


SIGNAL_RADIUS = 22
SIGNAL_RING_OFFSETS = (-3, -2, -1)
SIGNAL_DOT_BACKDROP_RATIO = 0.32
SIGNAL_DOT_RATIO = 0.23
# Top centre: the MAX box sits at the left edge and the exp button top right.
SIGNAL_CENTER_Y_OFFSET = 96
SIGNAL_CAPTION_GAP = 6
# A dimmed ring alone does not read as "parked", so it gets a short caption.
SIGNAL_PAUSED_TEXT = 'PAUSED'
SIGNAL_PAUSED_SIZE = 30
SIGNAL_PAUSED_COLOR = (215, 220, 225, 235)
# Lead brake-lamp observation caption (display only; candidate means "BRAKE?",
# never verified braking). Orange echoes the cluster-style lamp accent.
BRAKE_CANDIDATE_TEXT = 'BRAKE?'
BRAKE_CANDIDATE_COLOR = (255, 100, 40, 255)
BRAKE_CAPTION_SIZE = 30

# YOLO traffic-light observer dot (display only): sits to the right of the
# planner-evidence ring so the two sources can never be mistaken for one
# another. Direct palette colours, no amber swap — this is the detector's own
# reading, not a plan. Only red/green are shown; an unknown or yellow reading
# stays silent.
YOLO_DOT_OFFSET_X = 56
YOLO_DOT_RADIUS = 9
YOLO_DOT_BACKDROP_RATIO = 1.7
YOLO_DOT_COLORS = {'red': SIGNAL_PALETTE[1], 'green': SIGNAL_PALETTE[2]}

# YOLO per-housing boxes on the road view (display only). Boxes map from the
# observer's road-camera coordinates into the widget rect with the same
# aspect-preserving fit the camera preview uses (cameraview._calc_frame_matrix).
# The label carries the observed signal in the driver's language; an unknown
# housing still gets a box so a silent box never looks like a rendering bug.
YOLO_BOX_STROKE = 3
YOLO_BOX_ROUNDNESS = 0.25
YOLO_BOX_LABEL_SIZE = 26
YOLO_BOX_LABEL_GAP = 4
YOLO_BOX_COLORS = {
  'red': (255, 70, 70, 255),
  'green': (90, 220, 100, 255),
  'yellow': (255, 200, 40, 255),
  'unknown': (200, 205, 210, 220),
}
YOLO_SIGNAL_LABELS = {
  'red': '红灯',
  'green': '绿灯',
  'yellow': '黄灯',
  'traffic_light': '信号灯',
  'left_light': '左转灯',
  'right_light': '右转灯',
}
# Lamp classes the detector reports inside a housing; used when the housing's
# own state is unknown but a lamp still says what the signal is showing.
YOLO_LAMP_LABEL_KEYS = ('yellow_light', 'left_light', 'right_light')


class SignalHudRenderer:
  """Display-only signal indicator: render() only reads from the plan."""

  def __init__(self):
    self._font = gui_app.font(FontWeight.SEMI_BOLD)
    self._brake_next_read = 0.
    self._brake_candidate = False
    self._yolo_reader = None
    self._yolo_next_read = 0.
    self._yolo_state: str | None = None
    self._yolo_tracks: list = []
    self._yolo_frame_size: tuple[int, int] = (0, 0)

  def _update_brake_candidate(self, now: float | None = None) -> None:
    """Throttled (10 Hz) read of the modeld lead-brake-lamp tmpfs record.

    Purely advisory: the record itself carries control_permission False and a
    missing/stale/oversized file clears the caption rather than holding it.
    """
    now = time.monotonic() if now is None else now
    if now >= self._brake_next_read:
      self._brake_next_read = now + .1
      try:
        from openpilot.sunnypilot.carrot.lead_brake_lights import requested, ui_candidate
        self._brake_candidate = bool(requested()) and (ui_candidate(now=now) or {}).get('state') == 'candidate'
      except Exception:
        self._brake_candidate = False

  def _update_yolo_observation(self, now: float | None = None) -> None:
    """Throttled (5 Hz) read of the YOLO traffic-light observer's record.

    Display only: the observer's own opt-in gates it, staleness clears it, and
    only an agreed red/green reading is shown. Never imported when the signal
    modules are absent (e.g. stripped UI builds).
    """
    now = time.monotonic() if now is None else now
    if now < self._yolo_next_read:
      return
    self._yolo_next_read = now + .2
    self._yolo_state = None
    self._yolo_tracks = []
    self._yolo_frame_size = (0, 0)
    try:
      from openpilot.sunnypilot.carrot.signal_yolo_display import YoloObservationReader
      if self._yolo_reader is None:
        self._yolo_reader = YoloObservationReader()
      record = self._yolo_reader.read(now=now)
      if not isinstance(record, dict):
        return
      state = record.get('prediction')
      self._yolo_state = state if state in YOLO_DOT_COLORS else None
      size = record.get('size') or (0, 0)
      if size[0] > 0 and size[1] > 0:
        self._yolo_frame_size = (int(size[0]), int(size[1]))
        self._yolo_tracks = [t for t in record.get('tracks', []) if isinstance(t, dict) and t.get('box')]
    except Exception:
      self._yolo_state = None
      self._yolo_tracks = []
      self._yolo_frame_size = (0, 0)

  def render(self, rect: rl.Rectangle, sm) -> None:
    """Paint the ring and dot for the current evidence."""
    self._update_brake_candidate()
    self._update_yolo_observation()

    if self._yolo_tracks and self._yolo_frame_size[0] > 0:
      self._draw_yolo_boxes(rect)
    if self._yolo_state:
      self._draw_yolo_dot(rect)

    try:
      plan = sm['longitudinalPlanSP']
      action = signal_action(plan)
      suspended = signal_suspended(plan)
    except (AttributeError, KeyError, TypeError, ValueError):
      return

    if not getattr(ui_state, 'carrot_signal_hud', False):
      return
    if self._brake_candidate:
      self._draw_brake_caption(rect)
    if not signal_visible(action, suspended):
      return

    cx, cy = int(rect.x + rect.width / 2), int(rect.y + SIGNAL_CENTER_Y_OFFSET)
    ring, dot = signal_colors(action, suspended)
    for offset in SIGNAL_RING_OFFSETS:
      rl.draw_circle_lines(cx, cy, SIGNAL_RADIUS + offset, rl.Color(*ring))
    if dot:
      rl.draw_circle(cx, cy, SIGNAL_RADIUS * SIGNAL_DOT_BACKDROP_RATIO, rl.Color(*POINT_COLOR_BACKDROP))
      rl.draw_circle(cx, cy, SIGNAL_RADIUS * SIGNAL_DOT_RATIO, rl.Color(*dot))
    if suspended:
      self._draw_caption(cx, cy + SIGNAL_RADIUS + SIGNAL_CAPTION_GAP)

  def _draw_yolo_dot(self, rect: rl.Rectangle) -> None:
    """Observer dot beside the planner ring; independent of that ring's gates."""
    cx = int(rect.x + rect.width / 2) + YOLO_DOT_OFFSET_X
    cy = int(rect.y + SIGNAL_CENTER_Y_OFFSET)
    rl.draw_circle(cx, cy, YOLO_DOT_RADIUS * YOLO_DOT_BACKDROP_RATIO, rl.Color(*POINT_COLOR_BACKDROP))
    rl.draw_circle_lines(cx, cy, YOLO_DOT_RADIUS, rl.Color(*POINT_COLOR_SHADOW))
    rl.draw_circle(cx, cy, YOLO_DOT_RADIUS, rl.Color(*YOLO_DOT_COLORS[self._yolo_state]))

  @staticmethod
  def _yolo_box_screen_rect(box, rect: rl.Rectangle, frame_w: int, frame_h: int) -> rl.Rectangle:
    """Map a road-camera pixel box onto the camera preview rect.

    Same aspect-preserving fit as the camera view (cameraview._calc_frame_matrix):
    the frame is zoomed to cover the widget on one axis and centred on the other,
    so the mapping mirrors what the driver actually sees.
    """
    frame_ar = frame_w / frame_h
    widget_ar = rect.width / rect.height
    zx = min(frame_ar / widget_ar, 1.0)
    zy = min(widget_ar / frame_ar, 1.0)
    scale_x = rect.width * zx
    scale_y = rect.height * zy
    x_off = rect.x + (rect.width - scale_x) / 2
    y_off = rect.y + (rect.height - scale_y) / 2
    x1, y1, x2, y2 = box
    sx = x_off + (x1 / frame_w) * scale_x
    sy = y_off + (y1 / frame_h) * scale_y
    sw = ((x2 - x1) / frame_w) * scale_x
    sh = ((y2 - y1) / frame_h) * scale_y
    return rl.Rectangle(sx, sy, sw, sh)

  def _draw_yolo_boxes(self, rect: rl.Rectangle) -> None:
    """Detector boxes on the road view with the observed signal under each.

    Purely advisory: boxes come from the observer's own tmpfs record (stale
    records are already dropped by the reader), and the colour is what the
    detector read, never what the planner applied.
    """
    frame_w, frame_h = self._yolo_frame_size
    for track in self._yolo_tracks:
      x1, y1, x2, y2 = track['box']
      if x2 <= x1 or y2 <= y1:
        continue
      state = track.get('state')
      cls = 'traffic_light'
      lamps = track.get('lamps') or []
      if lamps and isinstance(lamps[0], dict):
        cls = lamps[0].get('cls') or cls
      if state not in YOLO_BOX_COLORS:
        state = 'unknown'
      # Prefer the state label; fall back through lamp classes to the housing.
      if state in ('red', 'green', 'yellow'):
        label = YOLO_SIGNAL_LABELS[state]
      else:
        lamp_cls = next((l.get('cls') for l in lamps
                         if isinstance(l, dict) and l.get('cls') in YOLO_LAMP_LABEL_KEYS), None)
        label = YOLO_SIGNAL_LABELS.get(lamp_cls or cls, YOLO_SIGNAL_LABELS['traffic_light'])

      srect = self._yolo_box_screen_rect((x1, y1, x2, y2), rect, frame_w, frame_h)
      color = YOLO_BOX_COLORS[state]
      shadow = rl.Color(0, 0, 0, 140)
      # Shadowed stroke for legibility over the bright road scene.
      rl.draw_rectangle_rounded_lines_ex(
        rl.Rectangle(srect.x - 1, srect.y - 1, srect.width + 2, srect.height + 2),
        YOLO_BOX_ROUNDNESS, 6, YOLO_BOX_STROKE + 2, shadow)
      rl.draw_rectangle_rounded_lines_ex(srect, YOLO_BOX_ROUNDNESS, 6, YOLO_BOX_STROKE, color)

      # Label centred under the box, on a translucent backdrop.
      text_size = measure_text_cached(self._font, label, YOLO_BOX_LABEL_SIZE)
      lx = srect.x + srect.width / 2 - text_size.x / 2
      ly = srect.y + srect.height + YOLO_BOX_LABEL_GAP
      backdrop = rl.Rectangle(lx - 8, ly - 3, text_size.x + 16, text_size.y + 6)
      rl.draw_rectangle_rounded(backdrop, 0.4, 8, rl.Color(0, 0, 0, 120))
      rl.draw_text_ex(self._font, label, rl.Vector2(lx + 1, ly + 1), YOLO_BOX_LABEL_SIZE, 0,
                      rl.Color(0, 0, 0, 160))
      rl.draw_text_ex(self._font, label, rl.Vector2(lx, ly), YOLO_BOX_LABEL_SIZE, 0, color)

  def _draw_brake_caption(self, rect: rl.Rectangle) -> None:
    """Shadowed BRAKE? caption at the top edge of the signal ring area."""
    cx = int(rect.x + rect.width / 2)
    cy = int(rect.y + SIGNAL_CENTER_Y_OFFSET - SIGNAL_RADIUS - BRAKE_CAPTION_SIZE - SIGNAL_CAPTION_GAP)
    size = measure_text_cached(self._font, BRAKE_CANDIDATE_TEXT, BRAKE_CAPTION_SIZE)
    x = cx - size.x / 2
    rl.draw_text_ex(self._font, BRAKE_CANDIDATE_TEXT, rl.Vector2(x + 1, float(cy) + 1), BRAKE_CAPTION_SIZE, 0,
                    rl.Color(*POINT_COLOR_SHADOW))
    rl.draw_text_ex(self._font, BRAKE_CANDIDATE_TEXT, rl.Vector2(x, float(cy)), BRAKE_CAPTION_SIZE, 0,
                    rl.Color(*BRAKE_CANDIDATE_COLOR))

  def _draw_caption(self, cx: int, cy: int) -> None:
    """Centre a short label under the ring, shadowed for legibility over the road view."""
    size = measure_text_cached(self._font, SIGNAL_PAUSED_TEXT, SIGNAL_PAUSED_SIZE)
    x = cx - size.x / 2
    rl.draw_text_ex(self._font, SIGNAL_PAUSED_TEXT, rl.Vector2(x + 1, float(cy) + 1), SIGNAL_PAUSED_SIZE, 0,
                    rl.Color(*POINT_COLOR_SHADOW))
    rl.draw_text_ex(self._font, SIGNAL_PAUSED_TEXT, rl.Vector2(x, float(cy)), SIGNAL_PAUSED_SIZE, 0,
                    rl.Color(*SIGNAL_PAUSED_COLOR))
