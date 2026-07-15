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

Param-only settings entry for the Acceleration EQ feature.
No UI fields (section/type/title), so the native dp settings panel skips
these; generate_settings.py still emits them into common/params_keys.h.
The editor UI lives in the dashy web repo.
"""

import os

from cereal import car
from openpilot.common.constants import CV
from openpilot.common.realtime import DT_MDL
from openpilot.common.swaglog import cloudlog

V_MIN = 1.0          # m/s — exclude creep/stop
TTC_MIN = 1.0        # s   — lead must be at least this far in time (~aggressive follow gap)
LAT_ACCEL_MAX = 1.0  # m/s² — exclude curves
FLUSH_DT = 60.0      # s   — append the buffer to disk at most this often
LOG_HEADER = "# dp_accel_log v3"   # first line; bump version to force a self-migration

# Accel-log data is observational telemetry, not config, so it lives as a CSV on the
# drive-log partition (where rlogs live) rather than in the params store.
LOG_PATH = "/data/media/0/realdata/accel_log.csv"


def _should_log(gas, brake, blinker, in_drive, moving, a_ego, lead_ttc, lat_accel):
  """True only for a clean, free, straight-line driver-DEMANDED acceleration sample.
  Gated on gasPressed — logs whenever the driver is on the gas (manual OR ACC override),
  which naturally excludes OP's own cruising (no gas)."""
  return (gas and a_ego > 0.0
          and not brake and not blinker
          and in_drive and moving
          and lead_ttc > TTC_MIN and lat_accel < LAT_ACCEL_MAX)


class AccelLogger:
  """Logs the driver's demanded acceleration — clean, free, straight-line samples,
  whether OP is off (manual) or engaged (gas override) — to a CSV (columns: vEgo m/s,
  aEgo m/s² grade-corrected) with a versioned header. Buffered in RAM, appended once a
  minute to spare the flash. Fully exception-isolated — it can never perturb the planner."""

  def __init__(self, CP, path=None):
    self._CP = CP
    self._enabled = CP.openpilotLongitudinalControl  # accel-eq only applies under OP long
    self._path = path if path is not None else LOG_PATH
    self._buf = []
    self._frames = 0
    self._flush_every = max(1, int(FLUSH_DT / DT_MDL))
    if self._enabled:
      self._ensure_header()

  def _ensure_header(self):
    # Version the file. If the first line isn't our header (older/absent format), archive
    # any existing file and start fresh, so new rows aren't mixed with differently-gated data.
    try:
      if os.path.exists(self._path):
        with open(self._path) as f:
          first = f.readline().rstrip("\n")
        if first == LOG_HEADER:
          return
        os.replace(self._path, os.path.splitext(self._path)[0] + ".pre_v3.csv")
      with open(self._path, "w") as f:
        f.write(LOG_HEADER + "\n")
    except Exception as e:
      cloudlog.warning(f"AccelLogger: header/migrate failed: {e}")

  def _flush(self):
    # Take + clear the buffer first, so RAM stays bounded even if the write fails.
    rows, self._buf = self._buf, []
    try:
      with open(self._path, "a") as f:
        f.writelines(f"{v:.3f},{a:.3f}\n" for v, a in rows)
    except Exception as e:
      cloudlog.warning(f"AccelLogger: write failed (dropped {len(rows)} rows): {e}")

  def update(self, sm, grade_accel=None):
    if not self._enabled:
      return
    try:
      self._frames += 1
      cs = sm['carState']
      v_ego = cs.vEgo
      in_drive = cs.gearShifter == car.CarState.GearShifter.drive
      moving = (not cs.standstill) and v_ego > V_MIN
      blinker = cs.leftBlinker or cs.rightBlinker
      lat_accel = abs(v_ego ** 2 * cs.steeringAngleDeg * CV.DEG_TO_RAD
                      / (self._CP.steerRatio * self._CP.wheelbase))
      lead = sm['radarState'].leadOne
      lead_ttc = (lead.dRel / max(v_ego, 0.1)) if lead.status else float('inf')

      # grade_accel is the planner's live gravity-along-road correction
      # (get_coast_accel(pitch) - get_coast_accel(0)). None when road pitch is
      # unavailable -> fail closed. Otherwise log the flat-ground-equivalent accel.
      if grade_accel is not None:
        a_flat = cs.aEgo - grade_accel
        if _should_log(cs.gasPressed, cs.brakePressed,
                       blinker, in_drive, moving, a_flat, lead_ttc, lat_accel):
          self._buf.append((v_ego, a_flat))

      if self._buf and self._frames % self._flush_every == 0:
        self._flush()
    except Exception as e:
      cloudlog.warning(f"AccelLogger.update failed (ignored): {e}")
