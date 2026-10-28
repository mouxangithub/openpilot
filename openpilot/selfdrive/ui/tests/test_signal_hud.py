"""Advisory signal HUD drawing (ported from carrot).

Needs a raylib context: ``signal_hud`` pulls in ``ui_state`` (cereal/opendbc) and
``text_measure`` (PIL). It runs as part of the device suite; the colour and
visibility decisions it renders are covered dependency-free in
``test_signal_status.py``.
"""
import unittest
from types import SimpleNamespace as NS

from openpilot.selfdrive.ui.sunnypilot.onroad import signal_hud
from openpilot.selfdrive.ui.ui_state import ui_state


class _FakeRL:
  """Records the raylib calls the HUD makes instead of touching the GPU."""

  def __init__(self):
    self.calls = []

  @staticmethod
  def Color(*args):
    return ('color',) + args

  @staticmethod
  def Rectangle(*args):
    return ('rect',) + args

  @staticmethod
  def Vector2(x, y=0.0):
    return NS(x=float(x), y=float(y))

  @property
  def WHITE(self):
    return ('white',)

  def draw_circle(self, *_args):
    self.calls.append('circle')

  def draw_circle_lines(self, *_args):
    self.calls.append('ring')

  def draw_rectangle_rounded(self, *_args):
    self.calls.append('box')

  def draw_text_ex(self, *_args):
    self.calls.append('text')


def _plan(action=0, suspended=False):
  return NS(signalAssistAction=action, signalDetectionSuspended=suspended)


def _rect():
  return NS(x=0.0, y=0.0, width=2160.0, height=1080.0)


class TestSignalHudRender(unittest.TestCase):
  def setUp(self):
    self._orig_flag = ui_state.carrot_signal_hud
    ui_state.carrot_signal_hud = True
    self._orig_rl = signal_hud.rl
    self._orig_measure = signal_hud.measure_text_cached
    self._fake = _FakeRL()
    signal_hud.rl = self._fake
    signal_hud.measure_text_cached = lambda font, text, size, spacing=0: NS(x=float(len(text)) * size * 0.5)
    self.renderer = signal_hud.SignalHudRenderer.__new__(signal_hud.SignalHudRenderer)
    self.renderer._font = None
    # Keep the throttled lead-brake-lamp and yolo reads inert unless a test enables them.
    self.renderer._brake_next_read = float('inf')
    self.renderer._brake_candidate = False
    self.renderer._yolo_next_read = float('inf')
    self.renderer._yolo_state = None
    self.renderer._yolo_reader = None

  def tearDown(self):
    ui_state.carrot_signal_hud = self._orig_flag
    signal_hud.rl = self._orig_rl
    signal_hud.measure_text_cached = self._orig_measure

  def test_disabled_draws_nothing(self):
    ui_state.carrot_signal_hud = False
    self.renderer.render(_rect(), {'longitudinalPlanSP': _plan(action=1)})
    self.assertEqual(self._fake.calls, [])

  def test_unknown_evidence_draws_nothing(self):
    self.renderer.render(_rect(), {'longitudinalPlanSP': _plan(action=0)})
    self.assertEqual(self._fake.calls, [])

  def test_known_evidence_draws_ring_and_dot(self):
    for action in (1, 2, 3):
      self._fake.calls.clear()
      self.renderer.render(_rect(), {'longitudinalPlanSP': _plan(action=action)})
      self.assertEqual(self._fake.calls.count('ring'), len(signal_hud.SIGNAL_RING_OFFSETS))
      self.assertEqual(self._fake.calls.count('circle'), 2)  # backdrop + dot

  def test_suspended_alone_still_draws_a_ring(self):
    self.renderer.render(_rect(), {'longitudinalPlanSP': _plan(suspended=True)})
    self.assertEqual(self._fake.calls.count('ring'), len(signal_hud.SIGNAL_RING_OFFSETS))
    self.assertTrue(self._fake.calls.count('text') >= 1)

  def test_missing_service_is_swallowed(self):
    self.renderer.render(_rect(), {})

  def test_broken_message_is_swallowed(self):
    self.renderer.render(_rect(), {'longitudinalPlanSP': object()})


class TestYoloDot(unittest.TestCase):
  """Observer dot: independent of the planner ring's gates, colour-direct."""

  def setUp(self):
    self._orig_flag = ui_state.carrot_signal_hud
    ui_state.carrot_signal_hud = False  # the yolo dot must not need the ring gate
    self._orig_rl = signal_hud.rl
    self._orig_measure = signal_hud.measure_text_cached
    self._fake = _FakeRL()
    signal_hud.rl = self._fake
    signal_hud.measure_text_cached = lambda font, text, size, spacing=0: NS(x=float(len(text)) * size * 0.5)
    self.renderer = signal_hud.SignalHudRenderer.__new__(signal_hud.SignalHudRenderer)
    self.renderer._font = None
    self.renderer._brake_next_read = float('inf')
    self.renderer._brake_candidate = False
    self.renderer._yolo_next_read = float('inf')
    self.renderer._yolo_reader = None
    self.renderer._yolo_state = None

  def tearDown(self):
    ui_state.carrot_signal_hud = self._orig_flag
    signal_hud.rl = self._orig_rl
    signal_hud.measure_text_cached = self._orig_measure

  def test_red_state_draws_backdrop_outline_and_dot(self):
    self.renderer._yolo_state = 'red'
    self.renderer.render(_rect(), {'longitudinalPlanSP': _plan(action=0)})
    self.assertEqual(self._fake.calls.count('circle'), 2)  # backdrop + dot
    self.assertEqual(self._fake.calls.count('ring'), 1)  # dark outline
    self.assertEqual(self._fake.calls.count('text'), 0)

  def test_unknown_state_draws_nothing(self):
    self.renderer._yolo_state = None
    self.renderer.render(_rect(), {'longitudinalPlanSP': _plan(action=0)})
    self.assertEqual(self._fake.calls, [])

  def test_dot_ignores_the_ring_gate(self):
    self.renderer._yolo_state = 'green'
    ui_state.carrot_signal_hud = False
    self.renderer.render(_rect(), {'longitudinalPlanSP': _plan(action=0)})
    self.assertEqual(self._fake.calls.count('circle'), 2)

  def test_throttled_read_failure_is_swallowed(self):
    self.renderer._yolo_next_read = 0.
    self.renderer.render(_rect(), {'longitudinalPlanSP': _plan(action=0)})
    self.assertIsNone(self.renderer._yolo_state)


class TestBrakeCaption(unittest.TestCase):
  """Lead brake-lamp caption: display only, candidate-gated, never holds."""

  def setUp(self):
    self._orig_flag = ui_state.carrot_signal_hud
    ui_state.carrot_signal_hud = True
    self._orig_rl = signal_hud.rl
    self._orig_measure = signal_hud.measure_text_cached
    self._fake = _FakeRL()
    signal_hud.rl = self._fake
    signal_hud.measure_text_cached = lambda font, text, size, spacing=0: NS(x=float(len(text)) * size * 0.5)
    self.renderer = signal_hud.SignalHudRenderer.__new__(signal_hud.SignalHudRenderer)
    self.renderer._font = None
    self.renderer._brake_next_read = float('inf')
    self.renderer._brake_candidate = False
    self.renderer._yolo_next_read = float('inf')
    self.renderer._yolo_state = None
    self.renderer._yolo_reader = None

  def tearDown(self):
    ui_state.carrot_signal_hud = self._orig_flag
    signal_hud.rl = self._orig_rl
    signal_hud.measure_text_cached = self._orig_measure

  def test_candidate_draws_caption_even_without_ring(self):
    self.renderer._brake_candidate = True
    self.renderer.render(_rect(), {'longitudinalPlanSP': _plan(action=0)})  # no ring evidence
    self.assertGreaterEqual(self._fake.calls.count('text'), 2)  # stroke + fill

  def test_unknown_never_draws_caption(self):
    self.renderer._brake_candidate = False
    self.renderer.render(_rect(), {'longitudinalPlanSP': _plan(action=0)})
    self.assertEqual(self._fake.calls, [])

  def test_hud_disabled_clears_caption(self):
    ui_state.carrot_signal_hud = False
    self.renderer._brake_candidate = True
    self.renderer.render(_rect(), {'longitudinalPlanSP': _plan(action=0)})
    self.assertEqual(self._fake.calls, [])

  def test_throttled_read_failure_is_swallowed(self):
    from openpilot.sunnypilot.carrot import lead_brake_lights
    original = lead_brake_lights.requested
    lead_brake_lights.requested = lambda: 1 / 0
    try:
      self.renderer._brake_next_read = 0.
      self.renderer.render(_rect(), {'longitudinalPlanSP': _plan(action=0)})
    finally:
      lead_brake_lights.requested = original
    self.assertFalse(self.renderer._brake_candidate)


if __name__ == "__main__":
  unittest.main()
