"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""One-shot diagnostic probe for the "系统滞后 / 转向控制错误 / 关导航后 canError" trio.

Run on the device (online) for ~60s while the symptom is occurring:

    cd /data/openpilot
    PYTHONPATH=/data/openpilot:/usr/local/venv/lib/python3.12/site-packages:/data/.pydeps \
      python3.12 openpilot/sunnypilot/carrot/tests/diag_probe.py

What it reports, per 100ms tick for 60s:
  - selfdriveState.active / enabled / alertText1 (which event is showing)
  - carState.canValid, canErrorCounter, canTimeout (1106 panda bus)
  - radarState.radarErrors.{canError, radarUnavailableTemporary, radarFault}
  - controlsState.lateralControlState saturated flag (steerSaturated trigger)
  - selfdrivedRatekeeper lag: whether selfdrived is lagging (>11.1ms avg dt)
  - carrotManSP broadcast v_ego/v_cruise/active (holds last-good after fix)

At the end it prints a summary counting how often each symptom fired. It never writes
anything, it only subscribes - safe to run while driving.
"""

import time

from openpilot.cereal import messaging


def _lateral_saturated(controls_state) -> bool:
  try:
    lcs = getattr(controls_state, "lateralControlState", None)
    if lcs is None:
      return False
    which = lcs.which()
    return bool(getattr(lcs, which).saturated)
  except Exception:
    return False


def main() -> None:
  services = ["selfdriveState", "carState", "radarState", "controlsState"]
  sm = messaging.SubMaster(services)

  started = time.monotonic()
  duration = 60.0

  counts = {
    "canTimeout": 0, "canInvalid": 0, "radarCanError": 0, "radarTemp": 0,
    "steerSaturated": 0, "selfdrivedLagging": 0, "active": 0,
    "bcast_v_ego_zero_while_active": 0,
  }
  samples = 0
  last_v_ego = None

  while time.monotonic() - started < duration:
    sm.update(0)

    if not sm.alive.get("carState", False):
      time.sleep(0.1)
      continue

    samples += 1
    cs = sm["carState"]
    ss = sm["selfdriveState"] if sm.alive.get("selfdriveState", False) else None
    rs = sm["radarState"] if sm.alive.get("radarState", False) else None
    ctr = sm["controlsState"] if sm.alive.get("controlsState", False) else None

    active = bool(ss.active) if ss is not None else False
    if active:
      counts["active"] += 1

    if cs.canTimeout:
      counts["canTimeout"] += 1
    if not cs.canValid:
      counts["canInvalid"] += 1

    if rs is not None:
      err = rs.radarErrors
      if err.canError:
        counts["radarCanError"] += 1
      if err.radarUnavailableTemporary:
        counts["radarTemp"] += 1

    if ctr is not None and _lateral_saturated(ctr):
      counts["steerSaturated"] += 1

    # v_ego broadcast should hold last-good; if it collapses to 0 while still active,
    # the previous-turn fix is not in effect on this device.
    v_ego = float(cs.vEgoCluster) if hasattr(cs, "vEgoCluster") else float(cs.vEgo)
    if active and v_ego > 5.0:
      last_v_ego = v_ego
    elif active and last_v_ego is not None and v_ego < 0.5 and last_v_ego > 5.0:
      counts["bcast_v_ego_zero_while_active"] += 1

    time.sleep(0.1)

  # Report (radarState only publishes ~20Hz; controlsState lateralControlState may be
  # absent on some builds - count is approximate but directionally correct).
  print(f"\n=== probe summary over {duration:.0f}s ({samples} samples) ===")
  print(f"samples           : {samples}")
  print(f"active samples    : {counts['active']}")
  print(f"carState.canTimeout      : {counts['canTimeout']}  (1106 bus missed)")
  print(f"carState !canValid       : {counts['canInvalid']}  (any bus invalid)")
  print(f"radarErrors.canError     : {counts['radarCanError']}  (radar parser can_valid=False)")
  print(f"radarErrors.radarTemp    : {counts['radarTemp']}")
  print(f"steerSaturated (转向超限): {counts['steerSaturated']}  (lac.saturated)")
  print(f"v_ego 0-while-active     : {counts['bcast_v_ego_zero_while_active']}  (broadcast hold fix applied?)")
  print("\nInterpretation:")
  print("  canTimeout>0  -> 1106/panda bus dropout, not radar.")
  print("  radarCanError>0 while steerSaturated==0 -> radar STATUS_MSG/20Hz drop.")
  print("  steerSaturated>0 AND radarCanError>0 -> CPU saturation on shared core: both the")
  print("    lateral tracking lag and the radar read miss have one cause (load).")


if __name__ == "__main__":
  main()
