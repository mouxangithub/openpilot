# Copyright (c) 2026, Rick Lan
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, and/or sublicense,
# for non-commercial purposes only, subject to the following conditions:
#
# - The above copyright notice and this permission notice shall be included in
#   all copies or substantial portions of the Software.
# - Commercial use (e.g. use in a product, service, or activity intended to
#   generate revenue) is prohibited without explicit written permission from
#   the copyright holder.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""Shared caching layer: Params access, CarParams parsing, and the settings
evaluation context, cached with a short TTL."""

import os
import time

from openpilot.common.params import Params
from openpilot.system.hardware import HARDWARE

from .config import CAR_PARAMS_CACHE_TTL, logger

try:
  from openpilot.system.version import get_build_metadata as _get_build_metadata
except Exception:
  _get_build_metadata = None


class MockParams:
  """In-memory params mock for dev mode."""

  _store = {}

  def get(self, key, default=None):
    return self._store.get(key, default)

  def get_bool(self, key, default=False):
    return bool(self._store.get(key)) if key in self._store else default

  def put(self, key, value):
    self._store[key] = value

  def put_bool(self, key, value):
    self._store[key] = value

  def remove(self, key):
    self._store.pop(key, None)

  def check_key(self, key):
    return True


class AppCache:
  """Centralized cache for expensive operations.

  Shared across request threads (ThreadingHTTPServer). Reads and single
  attribute assignments are atomic under the GIL, and the worst case of a
  race here is a redundant recompute or a briefly stale value (all caches are
  TTL-bounded and idempotent to rebuild), so no locking is needed for a
  single-client LAN app."""

  def __init__(self):
    self._params = None
    self._car_params = None
    self._car_params_time = 0
    self._context = None
    self._context_time = 0
    self._settings_cache = None
    self._settings_cache_time = 0

  @property
  def params(self):
    """Get shared Params instance (or mock if unavailable)."""
    if self._params is None:
      try:
        self._params = Params()
      except Exception as e:
        logger.warning(f"Params unavailable, using mock: {e}")
        self._params = MockParams()
    return self._params

  def get_car_params(self):
    """Get cached CarParams data (brand, longitudinal control)."""
    now = time.time()
    if self._car_params is None or (now - self._car_params_time) > CAR_PARAMS_CACHE_TTL:
      self._car_params = self._parse_car_params()
      self._car_params_time = now
    return self._car_params

  def _parse_car_params(self):
    """Parse CarParams from Params store."""
    result = {'brand': '', 'openpilot_longitudinal_control': False}
    try:
      # CarParams is cleared offroad/at boot; CarParamsPersistent keeps the last car's
      # params so brand/longitudinal-gated settings still show when configuring parked.
      car_params_bytes = self.params.get("CarParamsPersistent") or self.params.get("CarParams")
      if car_params_bytes:
        from cereal import car

        with car.CarParams.from_bytes(car_params_bytes) as cp:
          result['brand'] = cp.brand
          result['openpilot_longitudinal_control'] = cp.openpilotLongitudinalControl
    except Exception as e:
      logger.debug(f"Could not parse CarParams: {e}")
    return result

  def get_settings_context(self):
    """Get context dict for settings condition evaluation."""
    now = time.time()
    if self._context is None or (now - self._context_time) > CAR_PARAMS_CACHE_TTL:
      car_params = self.get_car_params()
      self._context = {
        'brand': car_params['brand'],
        'openpilotLongitudinalControl': car_params['openpilot_longitudinal_control'],
        'LITE': os.getenv("LITE") is not None,
        'MICI': self._check_mici(),
        # Upstream-mirror items gate on these.
        'DASHY': True,
        'IS_RELEASE': self._is_release_channel(),
      }
      self._context_time = now
    return self._context

  def _check_mici(self):
    """Check if device is MICI type."""
    try:
      return HARDWARE.get_device_type() == "mici"
    except Exception:
      return False

  def lang_switch_available(self):
    """Whether the dashy language switcher should be offered — always.

    Native language selection isn't device-gated, and the switcher is
    harmless even where a native one exists, so dashy offers it on every
    device (previously excluded comma 3/3x)."""
    return True

  def _is_release_channel(self):
    if _get_build_metadata is None:
      return False
    try:
      return bool(_get_build_metadata().release_channel)
    except Exception:
      return False

  def get_bool_safe(self, key, default=False):
    """Safely get a boolean param with default."""
    try:
      return self.params.get_bool(key)
    except Exception:
      return default

  def invalidate(self):
    """Invalidate all caches."""
    self._car_params = None
    self._context = None
    self._settings_cache = None
