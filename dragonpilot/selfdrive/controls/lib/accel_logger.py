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

from cereal import car
from openpilot.common.constants import CV
from openpilot.common.realtime import DT_MDL
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.controls.lib.longcontrol import LongCtrlState

V_MIN = 1.0          # m/s — exclude creep/stop
TTC_MIN = 0.5        # s   — lead must be at least this far in time
LAT_ACCEL_MAX = 1.0  # m/s² — exclude curves
FLUSH_DT = 60.0      # s   — append the buffer to disk at most this often

# Accel-log data is observational telemetry, not config, so it lives as a CSV on the
# drive-log partition (where rlogs live) rather than in the params store.
LOG_PATH = "/data/media/0/realdata/accel_log.csv"


def _should_log(long_off, gas, brake, blinker, in_drive, moving, a_ego, lead_ttc, lat_accel):
  """True only for a clean, free, straight-line human-acceleration sample."""
  return (long_off and gas and a_ego > 0.0
          and not brake and not blinker
          and in_drive and moving
          and lead_ttc > TTC_MIN and lat_accel < LAT_ACCEL_MAX)


class AccelLogger:
  """Logs the driver's natural acceleration — clean, free, straight-line manual
  samples — to a CSV (columns: vEgo m/s, aEgo m/s²). Samples are buffered in RAM
  and appended once a minute to spare the flash; up to FLUSH_DT of samples are
  lost on an ungraceful shutdown, which is negligible for an aggregate. The gate
  makes clean samples rare, so the file grows very slowly (no cap needed).
  Fully exception-isolated — it can never perturb the planner."""

  def __init__(self, CP, path=None):
    self._CP = CP
    self._enabled = CP.openpilotLongitudinalControl  # accel-eq only applies under OP long
    self._path = path if path is not None else LOG_PATH
    self._buf = []
    self._frames = 0
    self._flush_every = max(1, int(FLUSH_DT / DT_MDL))

  def _flush(self):
    # Take + clear the buffer first, so RAM stays bounded even if the write
    # fails (e.g. path not writable) — those rows are simply dropped.
    rows, self._buf = self._buf, []
    try:
      with open(self._path, "a") as f:
        f.writelines(f"{v:.3f},{a:.3f}\n" for v, a in rows)
    except Exception as e:
      cloudlog.warning(f"AccelLogger: write failed (dropped {len(rows)} rows): {e}")

  def update(self, sm):
    if not self._enabled:
      return
    try:
      self._frames += 1
      cs = sm['carState']
      v_ego = cs.vEgo
      long_off = sm['controlsState'].longControlState == LongCtrlState.off
      in_drive = cs.gearShifter == car.CarState.GearShifter.drive
      moving = (not cs.standstill) and v_ego > V_MIN
      blinker = cs.leftBlinker or cs.rightBlinker
      lat_accel = abs(v_ego ** 2 * cs.steeringAngleDeg * CV.DEG_TO_RAD
                      / (self._CP.steerRatio * self._CP.wheelbase))
      lead = sm['radarState'].leadOne
      lead_ttc = (lead.dRel / max(v_ego, 0.1)) if lead.status else float('inf')

      if _should_log(long_off, cs.gasPressed, cs.brakePressed,
                     blinker, in_drive, moving, cs.aEgo, lead_ttc, lat_accel):
        self._buf.append((v_ego, cs.aEgo))

      if self._buf and self._frames % self._flush_every == 0:
        self._flush()
    except Exception as e:
      cloudlog.warning(f"AccelLogger.update failed (ignored): {e}")
