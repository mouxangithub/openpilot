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

"""Static configuration + shared constants for the dashy server."""

import logging
import os

from openpilot.system.hardware import PC

logger = logging.getLogger("dashy")

_HERE = os.path.dirname(__file__)

# --- Configuration ---
# DASHY_DATA_DIR overrides the drive-log/data directory (used by the file
# browser and the accel-log habit reader). Set only in tests to isolate against
# a temp dir; unset in production, so behavior there is unchanged.
DEFAULT_DIR = os.path.realpath(os.environ.get("DASHY_DATA_DIR") or (os.path.join(_HERE, '..', '..') if PC else '/data/media/0/realdata'))
# Built web assets live at <dashy>/web/dist (this package is <dashy>/dashy_server).
WEB_DIST_PATH = os.path.realpath(os.path.join(_HERE, '..', 'web', 'dist'))
_WEB_DIST_REAL = WEB_DIST_PATH
CAR_PARAMS_CACHE_TTL = 30  # seconds

# Accel-EQ contract constants — single source of truth is the planner's
# accel_eq.py. Served to the web UI so its model can't drift from the
# planner (a curve the planner would reject must be un-authorable in the editor).
# Guarded: standalone/dev dashy without the dragonpilot tree falls back to the
# web model's own built-in defaults (ACCEL_EQ_CONFIG stays None → /api endpoint
# 404s → JS keeps defaults).
try:
  from dragonpilot.selfdrive.controls.lib import accel_eq as _AC

  # Only the scalar contract constants accel_eq still owns. Turn and the
  # schema version were dropped; stock is no longer an accel_eq constant —
  # it's injected into AccelEq from the planner's A_CRUISE_MAX table, so it
  # isn't served here (the dashy model keeps its built-in stock default,
  # which matches A_CRUISE_MAX).
  ACCEL_EQ_CONFIG = {
    "max_pts": _AC.MAX_PTS,
    "min_pts": _AC.MIN_PTS,
    "min_gap": _AC.MIN_GAP,
    "speed_ceil": _AC.SPEED_CEIL,
    "max_accel_ceil": _AC.MAX_ACCEL_CEIL,
  }
except Exception:
  ACCEL_EQ_CONFIG = None
