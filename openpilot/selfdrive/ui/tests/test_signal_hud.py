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


if __name__ == "__main__":
  unittest.main()
