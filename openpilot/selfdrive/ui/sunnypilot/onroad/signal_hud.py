"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Advisory signal HUD: outer ring = fresh evidence, centre dot = planner intervention.

Ported from carrot's ``selfdrive/ui/signal_status.py``, reading
``longitudinalPlanSP`` where carrot reads ``longitudinalPlan``. The ring carries
the fresh evidence recorded by the modeld tmpfs shadow, the centre dot carries
the action the planner actually applied, so a grey ring with a red dot is a
retained veto without fresh colour, and mixed evidence is amber rather than a
green "cleared to go".

All of it is advisory: a painted colour never means the car is responding to
the signal. The ring is only reachable at all when SignalAssistMode > 0,
because the planner leaves the action at 0 (unknown) below that.
"""
import pyray as rl

from openpilot.selfdrive.ui.signal_status import (
  POINT_COLOR_BACKDROP, POINT_COLOR_SHADOW, signal_action, signal_colors, signal_suspended, signal_visible,
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


class SignalHudRenderer:
  """Display-only signal indicator: render() only reads from the plan."""

  def __init__(self):
    self._font = gui_app.font(FontWeight.SEMI_BOLD)

  def render(self, rect: rl.Rectangle, sm) -> None:
    """Paint the ring and dot for the current evidence."""
    if not getattr(ui_state, 'carrot_signal_hud', False):
      return

    try:
      plan = sm['longitudinalPlanSP']
      action = signal_action(plan)
      suspended = signal_suspended(plan)
    except (AttributeError, KeyError, TypeError, ValueError):
      return

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

  def _draw_caption(self, cx: int, cy: int) -> None:
    """Centre a short label under the ring, shadowed for legibility over the road view."""
    size = measure_text_cached(self._font, SIGNAL_PAUSED_TEXT, SIGNAL_PAUSED_SIZE)
    x = cx - size.x / 2
    rl.draw_text_ex(self._font, SIGNAL_PAUSED_TEXT, rl.Vector2(x + 1, float(cy) + 1), SIGNAL_PAUSED_SIZE, 0,
                    rl.Color(*POINT_COLOR_SHADOW))
    rl.draw_text_ex(self._font, SIGNAL_PAUSED_TEXT, rl.Vector2(x, float(cy)), SIGNAL_PAUSED_SIZE, 0,
                    rl.Color(*SIGNAL_PAUSED_COLOR))
