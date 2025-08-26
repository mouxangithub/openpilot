"""
Copyright (c) 2021-, rav4kumar, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

from cereal import log, custom
import numpy as np
from openpilot.common.realtime import DT_MDL
from openpilot.common.params import Params

LongPersonality = log.LongitudinalPersonality
AccelPersonality = custom.LongitudinalPlanSP.AccelerationPersonality

# Acceleration Profiles mapped to AccelPersonality (eco/normal/sport)
MAX_ACCEL_PROFILES = {
  AccelPersonality.eco:       [2.00, 2.0,  1.80, 1.23, .52,  .28, .13, .088],  # eco
  AccelPersonality.normal:    [2.00, 2.0,  1.95, 1.55, .60,  .40, .30, .13],   # normal
  AccelPersonality.sport:     [2.00, 2.0,  1.99, 1.85, .70,  .50, .40, .2],   # sport
}
MAX_ACCEL_BREAKPOINTS =       [0.,   4.,   6.,   9.,   16.,  25., 30., 55.]

# Braking profiles mapped to LongPersonality (relaxed/standard/aggressive)
MIN_ACCEL_PROFILES = {
  LongPersonality.relaxed:    [-0.1, -1.1, -1.1],  # gentler braking
  LongPersonality.standard:   [-0.1, -1.2, -1.2],  # normal braking
  LongPersonality.aggressive: [-0.1, -1.2, -1.2],  # more aggressive braking
}
MIN_ACCEL_BREAKPOINTS =       [0.,  5.,  50.]

def get_T_FOLLOW_vibe(personality):
  """Get base T_FOLLOW value for each personality"""
  if personality == LongPersonality.relaxed:
    return 1.75
  elif personality == LongPersonality.standard:
    return 1.45
  elif personality == LongPersonality.aggressive:
    return 1.25
  else:
    return 1.45  # default to standard

def get_dynamic_personality(v_ego, personality):
  """Adjust T_FOLLOW based on vehicle speed (scales 0.75-1.0 from 0-36 m/s)."""
  scale_factor = np.clip(np.interp(v_ego, [0, 36], [0.75, 1.0]), 0.75, 1.0)
  return get_T_FOLLOW_vibe(personality) * scale_factor

class VibePersonalityController:
  """
  Controller for managing separated acceleration and distance controls:
  - AccelPersonality controls acceleration behavior (eco, normal, sport)
  - LongPersonality controls braking and following distance (relaxed, standard, aggressive)
  """

  def __init__(self):
    self.params = Params()
    self.frame = 0

    # Separate personalities for acceleration and distance control
    self.accel_personality = AccelPersonality.normal
    self.long_personality = LongPersonality.standard

    # Parameter keys
    self.param_keys = {
      'accel_personality': 'AccelPersonality',        # eco=0, normal=1, sport=2
      'long_personality': 'LongitudinalPersonality',  # relaxed=0, standard=1, aggressive=2
      'enabled': 'VibePersonalityEnabled',
      'accel_enabled': 'VibeAccelPersonalityEnabled',
      'follow_enabled': 'VibeFollowPersonalityEnabled'
    }

  def _update_from_params(self):
    """Update personalities from params (rate limited)"""
    if self.frame % int(1. / DT_MDL) != 0:
      return

    # Update AccelPersonality
    try:
      accel_personality_str = self.params.get(self.param_keys['accel_personality'], encoding='utf-8')
      if accel_personality_str:
        accel_personality_int = int(accel_personality_str)
        if accel_personality_int in [AccelPersonality.eco, AccelPersonality.normal, AccelPersonality.sport]:
          self.accel_personality = accel_personality_int
    except (ValueError, TypeError):
      pass

    # Update LongPersonality
    try:
      long_personality_str = self.params.get(self.param_keys['long_personality'], encoding='utf-8')
      if long_personality_str:
        long_personality_int = int(long_personality_str)
        if long_personality_int in [LongPersonality.relaxed, LongPersonality.standard, LongPersonality.aggressive]:
          self.long_personality = long_personality_int
    except (ValueError, TypeError):
      pass

  def _get_toggle_state(self, key: str, default: bool = True) -> bool:
    """Get toggle state with default fallback"""
    return self.params.get_bool(self.param_keys.get(key, key)) if key in self.param_keys else default

  def _set_toggle_state(self, key: str, value: bool):
    """Set toggle state in params"""
    if key in self.param_keys:
      self.params.put_bool(self.param_keys[key], value)

  # AccelPersonality Management (for acceleration)
  def set_accel_personality(self, personality: int) -> bool:
    """Set AccelPersonality (eco=0, normal=1, sport=2)"""
    if personality in [AccelPersonality.eco, AccelPersonality.normal, AccelPersonality.sport]:
      self.accel_personality = personality
      self.params.put(self.param_keys['accel_personality'], str(personality))
      return True
    return False

  def cycle_accel_personality(self) -> int:
    """Cycle through AccelPersonality: eco -> normal -> sport -> eco"""
    personalities = [AccelPersonality.eco, AccelPersonality.normal, AccelPersonality.sport]
    current_idx = personalities.index(self.accel_personality)
    next_personality = personalities[(current_idx + 1) % len(personalities)]
    self.set_accel_personality(next_personality)
    return int(next_personality)

  def get_accel_personality(self) -> int:
    """Get current AccelPersonality"""
    self._update_from_params()
    return int(self.accel_personality)

  # LongPersonality Management (for braking and following distance)
  def set_long_personality(self, personality: int) -> bool:
    """Set LongPersonality (relaxed=0, standard=1, aggressive=2)"""
    if personality in [LongPersonality.relaxed, LongPersonality.standard, LongPersonality.aggressive]:
      self.long_personality = personality
      self.params.put(self.param_keys['long_personality'], str(personality))
      return True
    return False

  def cycle_long_personality(self) -> int:
    """Cycle through LongPersonality: relaxed -> standard -> aggressive -> relaxed"""
    personalities = [LongPersonality.relaxed, LongPersonality.standard, LongPersonality.aggressive]
    current_idx = personalities.index(self.long_personality)
    next_personality = personalities[(current_idx + 1) % len(personalities)]
    self.set_long_personality(next_personality)
    return int(next_personality)

  def get_long_personality(self) -> int:
    """Get current LongPersonality"""
    self._update_from_params()
    return int(self.long_personality)

  # Toggle Functions
  def toggle_personality(self): return self._toggle_flag('enabled')
  def toggle_accel_personality(self): return self._toggle_flag('accel_enabled')
  def toggle_follow_distance_personality(self): return self._toggle_flag('follow_enabled')

  def _toggle_flag(self, key):
    current = self._get_toggle_state(key)
    self._set_toggle_state(key, not current)
    return not current

  def set_personality_enabled(self, enabled: bool): self._set_toggle_state('enabled', enabled)

  # Feature-specific enable checks
  def is_accel_enabled(self) -> bool:
    self._update_from_params()
    return self._get_toggle_state('enabled') and self._get_toggle_state('accel_enabled')

  def is_follow_enabled(self) -> bool:
    self._update_from_params()
    return self._get_toggle_state('enabled') and self._get_toggle_state('follow_enabled')

  def is_enabled(self) -> bool:
    self._update_from_params()
    return (self._get_toggle_state('enabled') and
            (self._get_toggle_state('accel_enabled') or self._get_toggle_state('follow_enabled')))

  def get_accel_limits(self, v_ego: float) -> tuple[float, float] | None:
    """
    Get acceleration limits based on current personalities.
    - Max acceleration from AccelPersonality (eco/normal/sport)
    - Min acceleration (braking) from LongPersonality (relaxed/standard/aggressive)
    Returns None if controller is disabled.
    """
    self._update_from_params()
    if not self.is_accel_enabled():
      return None

    try:
      # Max acceleration from AccelPersonality
      max_a = np.interp(v_ego, MAX_ACCEL_BREAKPOINTS, MAX_ACCEL_PROFILES[self.accel_personality])

      # Min acceleration (braking) from LongPersonality
      min_a = np.interp(v_ego, MIN_ACCEL_BREAKPOINTS, MIN_ACCEL_PROFILES[self.long_personality])

      return float(min_a), float(max_a)
    except (KeyError, IndexError):
      return None

  def get_follow_distance_multiplier(self, v_ego: float) -> float | None:
    """Get dynamic following distance based on speed and personality"""
    self._update_from_params()
    if not self.is_follow_enabled():
      return None

    try:
      return get_dynamic_personality(v_ego, self.long_personality)
    except (KeyError, IndexError):
      return None


  def get_min_accel(self, v_ego: float) -> float | None:
    """Get minimum acceleration (braking) from distance mode"""
    limits = self.get_accel_limits(v_ego)
    return limits[0] if limits else None

  def get_max_accel(self, v_ego: float) -> float | None:
    """Get maximum acceleration from drive mode"""
    limits = self.get_accel_limits(v_ego)
    return limits[1] if limits else None

  def reset(self):
    """Reset to default modes"""
    self.accel_personality = AccelPersonality.normal
    self.long_personality = LongPersonality.standard
    self.frame = 0

  def update(self):
    """Update frame counter"""
    self.frame += 1
