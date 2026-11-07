# Skill: Panda Harness Diagnosis

## Description

Diagnose comma Panda / car harness detection issues from openpilot runtime state.  
Surfaces `pandaStates[].carHarnessStatus`, `ignitionLine`, and `ignitionCan` so the agent can tell whether the wiring harness is detected and whether ignition is present.

## When to use

- User reports panda shows “否” / no panda / built-in panda DOS cannot connect.
- User plugged/unplugged the wiring harness and wants to know if openpilot detects it.
- `panda_status` or `device_health` suggests a harness problem.

## Required data

Use the vehicle-state snapshot already collected by `selfdrive/state.py` (accessed via `get_vehicle_state`).  The fields needed are:

- `pandaStates[].carHarnessStatus` — enum:
  - `0` = not connected / statusNotStarted
  - `1` = statusOK
  - `2` = statusTemporary
  - `3` = statusBootStub
  - `4` = statusNeedRefund (legacy)
  - `5` = statusNoHarness / harness not detected
  - other values = unknown / error
- `pandaStates[].ignitionLine` — `true` if ignition line is high.
- `pandaStates[].ignitionCan` — `true` if ignition is detected on CAN.
- `pandaStates[].controlsAllowed` — whether OP is allowed to control.
- `pandaStates[].safetyModel` — current safety model.
- `pandaStates[].faultStatus` — fault status string.
- `pandaStates[].heartbeatLost` — whether panda heartbeat was lost.
- `pandaStates[].voltage` — car battery voltage (mV).

## Diagnostic flow

1. Read `get_vehicle_state`.
2. If `pandaStates` is missing or empty:
   - Run `panda_status` / `device_health`.
   - Run `list_all_pandas` to see USB enumeration.
   - If no panda on USB, check cable/device; suggest `reboot_device` or `recover_dos_panda`.
3. If `pandaStates[0].carHarnessStatus == 0 or 5`:
   - The panda does not see the car harness.
   - Ask user to:
     - Confirm harness is fully clicked into the panda / OBD/CAM side.
     - Check harness LED (usually should be on/blinking when connected).
     - Try reseating the harness on both ends.
     - Try a different known-good harness if available.
   - If still `0/5` after reseating, suggest `tsk_restart_pandad` or `reboot_device`.
   - If it persists, the harness or panda harness port may be hardware-faulty.
4. If `carHarnessStatus >= 1` (OK/Temporary/BootStub) but `ignitionLine == false` and `ignitionCan == false`:
   - Harness is detected but the car is not sending ignition.
   - Tell user to turn the car to ACC/ON (not READY/running needed; just ignition on).
   - If ignition still false while car is on, check:
     - Wrong car harness type (e.g., CAM vs OBD-II).
     - CAN bus wiring/pinout.
     - Car-specific ignition source not connected.
5. If `heartbeatLost == true` or `faultStatus != "none"`:
   - Run `read_manager_log` and `grep_log` for panda faults.
   - Suggest `tsk_restart_pandad`, then `reboot_device` if it repeats.
6. If voltage is very low (< 11000 mV) or 0:
   - Check 12 V power / OBD power pin.

## Output style

- State the numeric `carHarnessStatus` and what it means in plain Chinese/English.
- Show `ignitionLine` / `ignitionCan` clearly.
- Give one concrete next action (reseating, restart pandad, reboot, or check cable).
- Do not write Params or send control commands from this skill.

## Safety

Read-only. This skill only inspects runtime state and suggests actions; it never modifies vehicle parameters.