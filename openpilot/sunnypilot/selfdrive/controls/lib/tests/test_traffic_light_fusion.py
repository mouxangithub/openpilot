"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""
Unit tests for TrafficLightFusion.

The fusion module avoids importing cereal, so these tests need no compiled
capnp runtime. The core ``fuse`` method is exercised with primitive inputs and
``update`` is exercised with a dict-backed fake SubMaster.
"""
from types import SimpleNamespace

import numpy as np
from openpilot.common.test import OpenpilotTestCase

from openpilot.sunnypilot.selfdrive.controls.lib.traffic_light_fusion import (
  RawLight, FusedState, FusedSource, TrafficLightFusion,
)


def _run(fusion: TrafficLightFusion, carrot: RawLight, amap: RawLight,
         vision_red: bool, vision_green: bool, distance: float, n: int = 10) -> None:
  """Feed the same frame n times to build up confirmation counters."""
  for _ in range(n):
    fusion.fuse(carrot, amap, vision_red, vision_green, distance)


class TestTrafficLightFusionFuse(OpenpilotTestCase):
  def test_nav_only_red_is_caution_by_default(self) -> None:
    fusion = TrafficLightFusion()
    _run(fusion, RawLight.RED, RawLight.OFF, False, False, 50.0)
    # Default: nav-only red never commands a stop assist -> caution RED.
    assert fusion.state == FusedState.RED
    assert fusion.source == FusedSource.CARROT

  def test_nav_only_red_stop_assist_when_enabled(self) -> None:
    fusion = TrafficLightFusion()
    fusion._fusion_enabled = True
    fusion._nav_caution_only = False
    _run(fusion, RawLight.RED, RawLight.OFF, False, False, 50.0)
    assert fusion.state == FusedState.RED_CONFIRMED
    assert fusion.source == FusedSource.FUSED

  def test_vision_red_is_confirmed(self) -> None:
    fusion = TrafficLightFusion()
    _run(fusion, RawLight.OFF, RawLight.OFF, True, False, 30.0)
    assert fusion.state == FusedState.RED_CONFIRMED
    assert fusion.source == FusedSource.VISION

  def test_vision_green_is_confirmed(self) -> None:
    fusion = TrafficLightFusion()
    _run(fusion, RawLight.OFF, RawLight.OFF, False, True, 30.0)
    assert fusion.state == FusedState.GREEN_CONFIRMED

  def test_nav_only_green_is_caution(self) -> None:
    fusion = TrafficLightFusion()
    _run(fusion, RawLight.GREEN, RawLight.OFF, False, False, 50.0)
    assert fusion.state == FusedState.GREEN

  def test_amap_red_counts_as_nav(self) -> None:
    fusion = TrafficLightFusion()
    _run(fusion, RawLight.OFF, RawLight.RED, False, False, 50.0)
    assert fusion.state == FusedState.RED
    assert fusion.source == FusedSource.AMAP

  def test_conflict_vision_green_nav_red_is_unknown(self) -> None:
    fusion = TrafficLightFusion()
    # Vision green confirmed + nav red (no vision red) -> ambiguous -> unknown.
    _run(fusion, RawLight.RED, RawLight.OFF, False, True, 30.0)
    assert fusion.state == FusedState.UNKNOWN
    assert fusion.source == FusedSource.FUSED

  def test_all_off_is_unknown(self) -> None:
    fusion = TrafficLightFusion()
    _run(fusion, RawLight.OFF, RawLight.OFF, False, False, 0.0)
    assert fusion.state == FusedState.UNKNOWN

  def test_single_frame_does_not_confirm(self) -> None:
    fusion = TrafficLightFusion()
    fusion.fuse(RawLight.RED, RawLight.OFF, False, False, 50.0)
    # One frame is not enough to confirm (needs >= 5).
    assert fusion.state == FusedState.UNKNOWN

  def test_left_turn_treated_as_go(self) -> None:
    fusion = TrafficLightFusion()
    _run(fusion, RawLight.LEFT, RawLight.OFF, False, False, 50.0)
    # Left-turn green is a "go" hint -> caution GREEN (not a stop).
    assert fusion.state == FusedState.GREEN


class TestTrafficLightFusionUpdate(OpenpilotTestCase):
  def _fake_sm(self, traffic_state: int, model_stop: bool) -> dict:
    # carrotManSP carries the phone red/green (0/1/2/3).
    carrot = SimpleNamespace(trafficState=traffic_state, trafficCountdown=0)
    # modelV2 stop-line detection: a near, slow end-of-path point => red.
    if model_stop:
      x = [0.0] * 32 + [10.0]
      v = [0.0] * 32 + [1.0]
    else:
      x = [0.0] * 32 + [300.0]
      v = [0.0] * 32 + [20.0]
    model = SimpleNamespace(position=SimpleNamespace(x=x), velocity=SimpleNamespace(x=v))
    return {"carrotManSP": carrot, "carrotNaviSP": None, "modelV2": model}

  def test_update_detects_vision_red(self) -> None:
    fusion = TrafficLightFusion()
    fusion._fusion_enabled = True
    fusion._nav_caution_only = False
    sm = self._fake_sm(traffic_state=0, model_stop=True)
    for _ in range(10):
      fusion.update(sm, v_ego=10.0)
    assert fusion.state == FusedState.RED_CONFIRMED
    assert fusion.source == FusedSource.VISION

  def test_update_carrot_red_without_vision_is_caution(self) -> None:
    fusion = TrafficLightFusion()
    # Default caution-only behavior, independent of real params on the device.
    fusion._fusion_enabled = False
    fusion._nav_caution_only = True
    sm = self._fake_sm(traffic_state=1, model_stop=False)
    for _ in range(10):
      fusion.update(sm, v_ego=10.0)
    # No vision confirmation -> caution RED, never a stop assist.
    assert fusion.state == FusedState.RED
    assert fusion.source == FusedSource.CARROT
