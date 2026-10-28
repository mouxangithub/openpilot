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


class SignalHudRenderer:
  """Display-only signal indicator: render() only reads from the plan."""

  def __init__(self):
    self._font = gui_app.font(FontWeight.SEMI_BOLD)
    self._brake_next_read = 0.
    self._brake_candidate = False
    self._yolo_reader = None
    self._yolo_next_read = 0.
    self._yolo_state: str | None = None

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
    try:
      from openpilot.sunnypilot.carrot.signal_yolo_display import YoloObservationReader
      if self._yolo_reader is None:
        self._yolo_reader = YoloObservationReader()
      record = self._yolo_reader.read(now=now)
      state = record.get('prediction') if isinstance(record, dict) else None
      self._yolo_state = state if state in YOLO_DOT_COLORS else None
    except Exception:
      self._yolo_state = None

  def render(self, rect: rl.Rectangle, sm) -> None:
    """Paint the ring and dot for the current evidence."""
    self._update_brake_candidate()
    self._update_yolo_observation()

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
