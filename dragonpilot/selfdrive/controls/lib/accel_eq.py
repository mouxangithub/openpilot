"""
Copyright (c) 2026, Rick Lan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, and/or sublicense,
for non-commercial purposes only, subject to the following conditions:

- The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.
- Commercial use (e.g. use in a product, service, or activity intended to
  generate revenue) is prohibited without explicit written permission from
  the copyright holder.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Acceleration EQ — planner-side reader. Loads the active profile's max-accel
curve from the dp_lon_accel_profiles param (validated, with a stock fallback)
and exposes it to the longitudinal planner. The editor UI lives in dashy.
"""

import math
import os

import numpy as np

from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog
from opendbc.car.interfaces import ACCEL_MAX

PROFILES_KEY = "dp_lon_accel_profiles"
STOCK_NAME = "Stock"   # the protected default — a live mirror of injected stock, never a stored curve

SPEED_CEIL = 60.0
MIN_GAP = 0.5
MIN_PTS = 2
MAX_PTS = 12   # our own sanity bound (np.interp has no limit); must match dashy's MAX_PTS
MAX_ACCEL_CEIL = ACCEL_MAX


def _validate_curve(curve, ceil):
  """Return a sorted, clamped (bp, v) tuple, or None if unusable."""
  if not isinstance(curve, dict):
    return None
  bp, v = curve.get("bp"), curve.get("v")
  if not isinstance(bp, list) or not isinstance(v, list):
    return None
  if len(bp) != len(v) or not (MIN_PTS <= len(bp) <= MAX_PTS):
    return None
  try:
    pairs = sorted(((float(b), float(a)) for b, a in zip(bp, v, strict=True)), key=lambda p: p[0])
  except (TypeError, ValueError):
    return None
  if not all(math.isfinite(b) and math.isfinite(a) for b, a in pairs):
    return None
  out_bp, out_v = [], []
  for b, a in pairs:
    b = min(max(b, 0.0), SPEED_CEIL)
    if out_bp and b - out_bp[-1] < MIN_GAP:
      return None
    out_bp.append(b)
    out_v.append(min(max(a, 0.0), ceil))
  return out_bp, out_v


def _select_active(data, name):
  """The profile with exactly this name, or None (caller falls back to stock).
  No first-profile fallback — an unknown name means 'use stock'."""
  if not isinstance(data, dict) or not name:
    return None
  profiles = data.get("profiles")
  if not isinstance(profiles, list):
    return None
  return next((p for p in profiles
               if isinstance(p, dict) and p.get("name") == name), None)


def _resolve_active_name(data, personality):
  """Profile name to use: when use_personality is on, the personality-mapped name
  (None if unmapped → stock); otherwise the manual 'active' selection (None if
  unset → stock). The caller treats None / no match as 'use stock'."""
  if not isinstance(data, dict):
    return None
  if data.get("use_personality"):
    pmap = data.get("personality_map")
    name = pmap.get(str(personality)) if isinstance(pmap, dict) else None
  else:
    name = data.get("active")
  return name if isinstance(name, str) and name else None


class AccelEq:
  def __init__(self, stock_bp, stock_v, params=None):
    # Stock fallback is injected by the planner (its A_CRUISE_MAX_* table), so
    # there's a single source of truth and accel_eq stays a leaf — it never
    # imports the planner (which imports AccelEq → would be circular).
    self._stock_bp, self._stock_v = list(stock_bp), list(stock_v)
    self._params = params if params is not None else Params()
    self._personality = -1  # unknown sentinel → the first maybe_refresh() with a real value (0/1/2) forces a resolve
    self._doc = None       # cached parsed profiles JSON (re-read only on mtime change)
    self._max_bp, self._max_v = list(stock_bp), list(stock_v)
    self._reload_doc()
    self._last_mtime = self._mtime(PROFILES_KEY)

  def _mtime(self, key):
    try:
      return os.stat(self._params.get_param_path(key)).st_mtime
    except OSError:
      return None

  def maybe_refresh(self, personality):
    # The JSON read is the only expensive part, so gate it on the param mtime
    # and cache the parsed doc. A personality change (button press) doesn't
    # touch the param at all — just re-resolve the active curve from the cache.
    mtime = self._mtime(PROFILES_KEY)
    if mtime != self._last_mtime:
      self._last_mtime = mtime
      self._personality = personality
      self._reload_doc()                      # JSON changed → re-read + re-resolve
    elif personality != self._personality:
      self._personality = personality
      self._resolve()                         # selection changed → re-resolve cache, no I/O

  def _reload_doc(self):
    # Read + parse + cache the profiles JSON (the expensive step), then resolve.
    try:
      self._doc = self._params.get(PROFILES_KEY)  # parsed dict, or None
    except Exception as e:  # never let tuning data crash the planner
      cloudlog.warning(f"AccelEq: failed to read profiles, using stock: {e}")
      self._doc = None
    self._resolve()

  def _resolve(self):
    # Pick the active profile's curve from the cached doc. Pure in-memory — no
    # param access, so it's cheap to call on every personality change.
    max_bp, max_v = list(self._stock_bp), list(self._stock_v)
    try:
      data = self._doc
      if data:
        name = _resolve_active_name(data, self._personality)
        # Anything unresolved — unmapped personality, unset/empty active, no
        # matching profile, or the Stock baseline itself — falls through to the
        # injected stock. Stock is a live mirror of injected stock, so its stored
        # curve is ignored (a planner stock change always takes effect).
        if name and name != STOCK_NAME:
          prof = _select_active(data, name)
          if prof is not None:
            mc = _validate_curve(prof.get("max"), MAX_ACCEL_CEIL)
            if mc is not None:
              max_bp, max_v = mc
    except Exception as e:  # never let tuning data crash the planner
      cloudlog.warning(f"AccelEq: failed to resolve profile, using stock: {e}")
    self._max_bp, self._max_v = max_bp, max_v

  def max_accel(self, v_ego):
    return float(np.interp(v_ego, self._max_bp, self._max_v))
