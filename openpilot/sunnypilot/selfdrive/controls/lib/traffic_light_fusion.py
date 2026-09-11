from __future__ import annotations
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""
Three-source traffic-light fusion.

Fuses the carrot phone navigation signal (``carrotManSP`` 7706 /
``carrotNaviSP`` 7714), the Amap Web navigation hint (``amapNaviSP``) and the
openpilot vision stop-line detection (``modelV2``) into a single fused state.

Safety model (see traffic_fusion_safety_design_2026-09-11.md and the safety
review):
  * Vision is the final authority at close range.
  * A navigation-only red light is a *caution* (warn) unless
    ``CarrotTrafficLightFusionEnabled`` is on AND ``TrafficLightNavCautionOnly``
    is off; by default it never commands a stop assist.
  * All transitions require multi-frame confirmation to suppress single-frame
    misdetections (oncoming green, shadow, billboard).

This module deliberately avoids importing cereal so it can be unit-tested
without a compiled capnp runtime; the cereal ``TrafficLightState`` mapping is
done by the caller (``LongitudinalPlannerSP``) which already imports custom.
"""

from enum import Enum
from typing import Any

from openpilot.sunnypilot.carrot.config import UnifiedParams


class RawLight(Enum):
  """Raw per-source light state (avoids a cereal import)."""
  OFF = 0
  RED = 1
  GREEN = 2
  LEFT = 3   # left-turn green (carrot / amap only; vision cannot confirm)


class FusedState(Enum):
  """Fused traffic-light state exposed to the longitudinal planner."""
  UNKNOWN = 0
  RED = 1              # navigation-only red -> caution, no stop assist
  GREEN = 2            # navigation-only green -> caution
  RED_CONFIRMED = 3    # vision (or nav-with-assist) confirmed red
  GREEN_CONFIRMED = 4  # vision confirmed green


class FusedSource(Enum):
  """Source attribution for the fused state."""
  NONE = 0
  CARROT = 1
  AMAP = 2
  VISION = 3
  FUSED = 4


# Confirmation frame counts (frames @ ~20 Hz model ticks). These are safety
# critical and intentionally NOT params (the killswitch params stay off by default).
_NAV_RED_CONFIRM_FRAMES = 5
_NAV_GREEN_CONFIRM_FRAMES = 3
_VISION_RED_CONFIRM_FRAMES = 5
_VISION_GREEN_CONFIRM_FRAMES = 5


class TrafficLightFusion:
  """Fuse carrot / Amap / vision traffic lights into a single ``FusedState``."""

  def __init__(self) -> None:
    self._params = UnifiedParams()
    self.state = FusedState.UNKNOWN
    self.source = FusedSource.NONE
    self.confidence = 0.0
    self.distance = 0.0
    # Per-source sustained-frame counters.
    self._carrot_red = 0
    self._carrot_green = 0
    self._amap_red = 0
    self._amap_green = 0
    self._vision_red = 0
    self._vision_green = 0
    # Killswitch state (refreshed in update(); overridable for unit tests).
    self._fusion_enabled = False
    self._nav_caution_only = True

  # -- parameter refresh ------------------------------------------------- #

  def _refresh_params(self) -> None:
    self._fusion_enabled = self._params.get_bool("CarrotTrafficLightFusionEnabled")
    self._nav_caution_only = self._params.get_bool("TrafficLightNavCautionOnly", True)

  # -- source extraction (from a SubMaster snapshot) --------------------- #

  def _read_carrot(self, sm: Any) -> tuple[RawLight, float]:
    """Return (raw_state, distance_m) from the carrot phone navi."""
    state = RawLight.OFF
    distance = 0.0
    try:
      carrot = sm["carrotManSP"]
    except Exception:
      carrot = None
    if carrot is not None:
      ts = int(getattr(carrot, "trafficState", 0) or 0)
      if ts in (1, 2, 3):
        state = RawLight(ts)
      cd = int(getattr(carrot, "trafficCountdown", 0) or 0)
      if cd > 0:
        distance = max(distance, float(cd))
    # 7714 v2 channel (richer, preferred when present).
    try:
      navi = sm["carrotNaviSP"]
    except Exception:
      navi = None
    if navi is not None:
      sig = getattr(navi, "trafficSignal", None)
      if sig is not None and getattr(sig, "visible", False):
        d = float(getattr(sig, "distanceM", 0) or 0)
        if d > 0:
          distance = d
        if getattr(sig, "redValid", False) and getattr(sig, "redOn", False):
          state = RawLight.RED
        elif getattr(sig, "greenValid", False) and getattr(sig, "greenOn", False):
          state = RawLight.GREEN
        elif getattr(sig, "leftValid", False) and getattr(sig, "leftOn", False):
          state = RawLight.LEFT
    return state, distance

  def _read_amap(self, sm: Any) -> tuple[RawLight, float]:
    """Return (raw_state, distance_m) from the Amap Web navi.

    ``AmapNaviSP`` currently exposes no traffic-light fields (the data-path gap
    documented in the safety review). If a future field is added it will be read
    here via getattr, keeping this forward-compatible without a schema change.
    """
    state = RawLight.OFF
    distance = 0.0
    try:
      amap = sm["amapNaviSP"]
    except Exception:
      amap = None
    if amap is not None:
      ts = int(getattr(amap, "trafficState", 0) or 0)
      if ts in (1, 2, 3):
        state = RawLight(ts)
    return state, distance

  def _detect_vision(self, sm: Any, v_ego: float) -> tuple[bool, bool, float]:
    """Lightweight vision stop-line detection from ``modelV2``.

    Returns (red, green, distance_m). Kept independent of ``CarrotPlanner`` so
    the fusion module can be reasoned about and tested on its own.
    """
    red = False
    green = False
    distance = 0.0
    try:
      model = sm["modelV2"]
      x = model.position.x
      v = model.velocity.x
      if len(x) and len(v):
        x_last = float(x[-1])
        v_last = float(v[-1])
        v_ego_kph = v_ego * 3.6
        if v_ego_kph < 1.0:
          red = x_last < 20.0 and v_last < 10.0
        elif v_ego_kph < 82.0:
          # Only treat the end-of-path point as a traffic-light signal when it
          # is close enough to be a stop line. Far-away path points are normal
          # road geometry, not a green-light "go" indication.
          near = x_last < 100.0
          red = near and v_last < 3.0
          green = near and v_last > 5.0
        distance = x_last
    except Exception:
      pass
    return red, green, distance

  # -- core fusion ------------------------------------------------------- #

  def fuse(self, carrot_state: RawLight, amap_state: RawLight, vision_red: bool,
           vision_green: bool, distance: float, v_ego: float = 0.0) -> None:
    """Combine the three raw sources into ``self.state`` / ``source`` / etc.

    Pure and testable: takes primitive inputs, no cereal / SubMaster dependency.
    """
    # Sustain-frame counters (reset to 0 on a non-matching frame).
    self._carrot_red = self._carrot_red + 1 if carrot_state == RawLight.RED else 0
    self._carrot_green = self._carrot_green + 1 if carrot_state in (RawLight.GREEN, RawLight.LEFT) else 0
    self._amap_red = self._amap_red + 1 if amap_state == RawLight.RED else 0
    self._amap_green = self._amap_green + 1 if amap_state in (RawLight.GREEN, RawLight.LEFT) else 0
    self._vision_red = self._vision_red + 1 if vision_red else 0
    self._vision_green = self._vision_green + 1 if vision_green else 0

    vision_red_c = self._vision_red >= _VISION_RED_CONFIRM_FRAMES
    vision_green_c = self._vision_green >= _VISION_GREEN_CONFIRM_FRAMES
    carrot_red_c = self._carrot_red >= _NAV_RED_CONFIRM_FRAMES
    carrot_green_c = self._carrot_green >= _NAV_GREEN_CONFIRM_FRAMES
    amap_red_c = self._amap_red >= _NAV_RED_CONFIRM_FRAMES
    amap_green_c = self._amap_green >= _NAV_GREEN_CONFIRM_FRAMES

    nav_red = carrot_red_c or amap_red_c
    nav_green = carrot_green_c or amap_green_c

    # Conflict rule: vision green + nav red (no vision red) is ambiguous -> we
    # must not auto-start nor command a stop; downgrade to a caution.
    if vision_green_c and nav_red and not vision_red_c:
      self.state = FusedState.UNKNOWN
      self.source = FusedSource.FUSED
      self.confidence = 0.3
      self.distance = distance
      return

    # Vision is the final authority at close range.
    if vision_red_c:
      self.state = FusedState.RED_CONFIRMED
      self.source = FusedSource.VISION
      self.confidence = 0.9
      self.distance = distance
      return
    if vision_green_c:
      self.state = FusedState.GREEN_CONFIRMED
      self.source = FusedSource.VISION
      self.confidence = 0.9
      self.distance = distance
      return

    # Navigation-only (no vision confirmation) -> caution, no stop assist by
    # default. A stop assist is only allowed when the fusion killswitch is on and
    # the caution-only guard is explicitly disabled.
    if nav_red:
      if self._fusion_enabled and not self._nav_caution_only:
        self.state = FusedState.RED_CONFIRMED
        self.source = FusedSource.FUSED
        self.confidence = 0.6
      else:
        self.state = FusedState.RED
        self.source = FusedSource.CARROT if carrot_red_c else FusedSource.AMAP
        self.confidence = 0.5
      self.distance = distance
      return
    if nav_green:
      self.state = FusedState.GREEN
      self.source = FusedSource.CARROT if carrot_green_c else FusedSource.AMAP
      self.confidence = 0.5
      self.distance = distance
      return

    self.state = FusedState.UNKNOWN
    self.source = FusedSource.NONE
    self.confidence = 0.0
    self.distance = distance

  # -- public update ----------------------------------------------------- #

  def update(self, sm: Any, v_ego: float) -> None:
    """Pull raw states from a SubMaster snapshot and fuse them."""
    self._refresh_params()
    carrot_state, carrot_dist = self._read_carrot(sm)
    amap_state, amap_dist = self._read_amap(sm)
    vision_red, vision_green, vision_dist = self._detect_vision(sm, v_ego)
    distance = max(carrot_dist, amap_dist, vision_dist)
    self.fuse(carrot_state, amap_state, vision_red, vision_green, distance, v_ego)
