#!/usr/bin/env python3
"""IndicatorLayer must tolerate a missing carrotManSP feed.

carrotManSP is an observational-only input to selfdrived (the indicator
layer's ATC mirror). carrot_man may not be running yet / at all on cold boot,
and a transient msgq blip must never make selfdrived raise KeyError or count
the live 10 Hz feed as a process comm issue.
"""
import unittest
from types import SimpleNamespace

from openpilot.selfdrive.selfdrived.indicator_layer import IndicatorLayer


class _FakeSM:
  """Minimal SubMaster surface: carrotManSP is intentionally absent."""

  def __init__(self):
    self.seen = {}
    self.valid = {}
    self.alive = {}
    self.recv_time = {}
    self._data = {}

  def __getitem__(self, key):
    return self._data[key]


class TestIndicatorLayerCarrotOptional(unittest.TestCase):
  def _enabled_layer(self):
    layer = IndicatorLayer(params=SimpleNamespace(
      get_int=lambda *_a, **_k: 0,
      get_bool=lambda *_a, **_k: False,
    ))
    # Force the layer past the `if not self.enabled` early-out without params.
    layer.model_desire_indicator_enabled = True
    return layer

  def test_missing_carrot_feed_does_not_raise(self):
    layer = self._enabled_layer()
    sm = _FakeSM()  # no carrotManSP, no modelV2 needed because carrot guard runs first path
    cs = SimpleNamespace(leftBlinker=False, rightBlinker=False)
    # With enabled but no carrot seen, it must return cleanly, not KeyError.
    # modelV2 is read before the carrot guard, so provide a minimal one.
    sm.seen = {}
    sm._data['modelV2'] = SimpleNamespace(
      valid=True, frameId=1,
      meta=SimpleNamespace(laneChangeState=0, laneChangeDirection=0),
    )
    sm.valid = {'carState': True, 'carControl': True}
    sm.alive = {'carState': True, 'carControl': True}
    sm.recv_time = {'carState': 0.0, 'carControl': 0.0}
    sm._data['carState'] = SimpleNamespace()
    sm._data['carControl'] = SimpleNamespace(latActive=False, actuators=SimpleNamespace(curvature=0.0))
    layer.update(sm, cs)  # must not raise

  def test_present_carrot_feed_passes_guard(self):
    layer = self._enabled_layer()
    sm = _FakeSM()
    sm.seen = {'carrotManSP': True}
    sm._data['modelV2'] = SimpleNamespace(
      valid=True, frameId=1,
      meta=SimpleNamespace(laneChangeState=0, laneChangeDirection=0),
    )
    sm.valid = {'carState': True, 'carControl': True}
    sm.alive = {'carState': True, 'carControl': True}
    sm.recv_time = {'carState': 0.0, 'carControl': 0.0}
    sm._data['carState'] = SimpleNamespace()
    sm._data['carControl'] = SimpleNamespace(latActive=False, actuators=SimpleNamespace(curvature=0.0))
    sm._data['carrotManSP'] = SimpleNamespace(activeCarrot=0)
    sm._data['modelDataV2SP'] = SimpleNamespace(laneTurnDirection=0)
    cs = SimpleNamespace(leftBlinker=False, rightBlinker=False)
    # Should proceed past the carrot guard (may exercise more of update, but
    # must not raise on the missing-service KeyError under test).
    try:
      layer.update(sm, cs)
    except KeyError as e:
      self.fail(f"unexpected KeyError for a present/guarded feed: {e}")


if __name__ == "__main__":
  unittest.main()
