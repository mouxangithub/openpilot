"""
Onroad personality quick-switch button, adapted from StarPilot's
``personality_button.py``.

Differences from the original:
- StarPilot swaps the driving personality through its own theme assets and
  toggle bridge; sunnypilot stores the personality in the registered
  ``LongitudinalPersonality`` param (enum values straight from cereal's
  ``log.LongitudinalPersonality``), so this button cycles that param and
  renders the state programmatically (coloured ring + short label) instead of
  loading texture icons that do not exist in this fork's asset set.
- StarPilot's traffic-mode icon branch is dropped (no equivalent state here).
- Position: mounted below the existing ExpButton (top-right corner) so the two
  buttons stack in the same column (see HudRendererSP._render).
- Gated by the unregistered param ``ShowPersonalityButton`` (code default OFF).
"""
import time

import pyray as rl

from openpilot.cereal import log
from openpilot.selfdrive.ui.sunnypilot.onroad.param_guards import safe_get_bool
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import FontWeight, gui_app
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget

BTN_SIZE = 192
PARAM_REFRESH_INTERVAL = 0.25  # seconds; params are not per-frame data

# cereal LongitudinalPersonality: aggressive @0, standard @1, relaxed @2
AGGRESSIVE = int(log.LongitudinalPersonality.aggressive)
STANDARD = int(log.LongitudinalPersonality.standard)
RELAXED = int(log.LongitudinalPersonality.relaxed)

# cycle order and per-personality accent colours / labels
PERSONALITY_CYCLE = (AGGRESSIVE, STANDARD, RELAXED)
PERSONALITY_STYLE = {
  AGGRESSIVE: (rl.Color(255, 80, 80, 255), "AGGR"),
  STANDARD: (rl.Color(255, 255, 255, 255), "STD"),
  RELAXED: (rl.Color(80, 160, 255, 255), "RELAX"),
}

BLACK_BG = rl.Color(0, 0, 0, 166)


class PersonalityButton(Widget):
  """Round button that cycles the LongitudinalPersonality param on tap."""

  def __init__(self):
    super().__init__()
    self._font = gui_app.font(FontWeight.SEMI_BOLD)
    self._personality: int = STANDARD
    self._enabled = False
    self._last_param_refresh = float("-inf")
    self._rect = rl.Rectangle(0, 0, BTN_SIZE, BTN_SIZE)
    self.set_visible(lambda: self._enabled and ui_state.has_longitudinal_control)

  def set_rect(self, rect: rl.Rectangle) -> None:
    self._rect.x, self._rect.y = rect.x, rect.y
    self._rect.width, self._rect.height = rect.width, rect.height

  def _refresh_params(self):
    now = rl.get_time()
    if now - self._last_param_refresh < PARAM_REFRESH_INTERVAL:
      return
    self._last_param_refresh = now
    self._enabled = safe_get_bool(ui_state.params, "ShowPersonalityButton", False)

  def _update_state(self):
    self._refresh_params()
    sm = ui_state.sm
    if sm.valid.get("selfdriveState", False) and sm.recv_frame["selfdriveState"] >= ui_state.started_frame:
      # pycapnp >= 0.8: message-field enumerants come back as _DynamicEnum,
      # which raises on int(); only .raw yields the underlying ordinal
      self._personality = int(getattr(sm["selfdriveState"].personality, "raw", sm["selfdriveState"].personality))

  def _handle_mouse_release(self, _):
    super()._handle_mouse_release(_)
    if not ui_state.has_longitudinal_control:
      return
    # cycle to the next personality and persist it; selfdrived picks the param
    # up within a second (same flow as the settings profile editor)
    current = self._personality if self._personality in PERSONALITY_CYCLE else STANDARD
    nxt = PERSONALITY_CYCLE[(PERSONALITY_CYCLE.index(current) + 1) % len(PERSONALITY_CYCLE)]
    ui_state.params.put("LongitudinalPersonality", nxt, block=True)
    # show the tapped mode until selfdrived publishes it
    self._personality = nxt

  def _render(self, rect: rl.Rectangle):
    center_x = int(self._rect.x + self._rect.width / 2)
    center_y = int(self._rect.y + self._rect.height / 2)

    color, label = PERSONALITY_STYLE.get(self._personality, PERSONALITY_STYLE[STANDARD])
    ring_color = rl.Color(color.r, color.g, color.b, 180 if self.is_pressed else 255)

    rl.draw_circle(center_x, center_y, self._rect.width / 2, BLACK_BG)
    rl.draw_circle_lines(center_x, center_y, self._rect.width / 2 - 4, ring_color)

    font_size = 44
    text_size = measure_text_cached(self._font, label, font_size)
    while font_size > 20 and text_size.x > self._rect.width - 48:
      font_size -= 2
      text_size = measure_text_cached(self._font, label, font_size)
    rl.draw_text_ex(
      self._font, label,
      rl.Vector2(center_x - text_size.x / 2, center_y - text_size.y / 2),
      font_size, 0, ring_color,
    )
