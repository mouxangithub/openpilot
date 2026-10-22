# controls/ - STOCK CONTROL LAYER

Stock openpilot actuation: lateral/longitudinal controllers, the longitudinal MPC, and radar fusion. Fork feature logic lives in [sunnypilot/selfdrive/controls/lib/AGENTS.md](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/sunnypilot/selfdrive/controls/lib/AGENTS.md).

## STRUCTURE

```
controls/
├── controlsd.py            # Controls(ControlsExt) - 100 Hz; state_control() -> carControl + controlsState
├── plannerd.py             # main() only; drives LongitudinalPlanner + LaneDepartureWarning, 20 Hz on modelV2
├── radard.py               # RadarD, Track, KalmanParams, get_lead() -> radarState
└── lib/
    ├── latcontrol.py             # LatControl ABC: update(), reset(), _check_saturation()
    ├── latcontrol_angle.py       # LatControlAngle + STEER_ANGLE_SATURATION_THRESHOLD (2.5 deg)
    ├── latcontrol_curvature.py   # LatControlCurvature
    ├── latcontrol_pid.py         # LatControlPID
    ├── latcontrol_torque.py      # LatControlTorque - lat-accel-space PID + friction/jerk FF
    ├── longcontrol.py            # LongControl + long_control_state_trans() (off/pid/stopping)
    ├── longitudinal_planner.py   # LongitudinalPlanner(LongitudinalPlannerSP) - MPC vs cruise vs e2e min()
    ├── drive_helpers.py          # clip_curvature, get_accel_from_plan, CONTROL_N=17, MAX_CURVATURE
    ├── desire_helper.py, ldw.py
    └── longitudinal_mpc_lib/     # acados OCP: long_mpc.py + SConscript -> c_generated_code/
```

No `lateral_mpc_lib/` here. Lateral MPC was replaced by model-emitted `modelV2.action.desiredCurvature`; the only lateral solver left is the PID/torque loop.

## CONTROLLER SELECTION

Chosen once in `Controls.__init__` ([controlsd.py:62-69](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/selfdrive/controls/controlsd.py#L62-L69)), strictly in this order:

1. `CP.steerControlType == angle` -> `LatControlAngle`
2. `CP.steerControlType == curvature` -> `LatControlCurvature`
3. `CP.lateralTuning.which() == 'pid'` -> `LatControlPID`
4. `CP.lateralTuning.which() == 'torque'` -> `LatControlTorque`

Then, unconditionally, [controlsd.py:71](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/selfdrive/controls/controlsd.py#L71) passes the instance through `ControlsExt.initialize_lateral_control()`, which may swap it for `LatControlTorqueV0` based on Params `EnforceTorqueControl` + `TorqueControlTune`. That is the SP override seam. `lac_log` publishing branches on the same `steerControlType`/`lateralTuning` keys ([controlsd.py:228-236](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/selfdrive/controls/controlsd.py#L228-L236)) - adding a controller means touching both branch sites plus `ControlsState.lateralControlState` in cereal.

## MPC / ACADOS

[longitudinal_mpc_lib/SConscript](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/SConscript) declares one `Command` whose SCons dependency set is a literal `source_list`: `long_mpc.py`, `openpilot/selfdrive/modeld/constants.py`, and two acados headers. Nothing else. So if you edit a value that `long_mpc.py` *imports* from another module (rather than defining in its own constants block), SCons sees no changed source, skips `python3 long_mpc.py`, and links the previously generated solver. Build succeeds, numbers are stale, no warning. Same rule applies to any acados dir in this repo.

Force a regen: `touch openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py`, or `scons --clean` (the SConscript registers `lenv.Clean(generated_files, Dir(gen))`).

Generated output: `longitudinal_mpc_lib/c_generated_code/` + `acados_ocp_long.json`. Gitignored. Never commit, never hand-edit - the next regen wipes it.

## SP SEAMS

| Stock symbol | SP extension |
|---|---|
| `Controls` (controlsd.py) | base class `ControlsExt` - [controlsd_ext.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/sunnypilot/selfdrive/controls/controlsd_ext.py) |
| lat controller construction | `ControlsExt.initialize_lateral_control()` |
| `CC.latActive` gating | `ControlsExt.get_lat_active(sm)` (MADS, blinker pause) |
| `LatControlTorque.extension` | `LatControlTorqueExt` (NNLC, torque overrides) |
| `LongitudinalPlanner` | base class `LongitudinalPlannerSP`; `update_targets()`, `is_e2e()`, `publish_longitudinal_plan_sp()` |
| `RadarD` lead yRel | `get_custom_yrel()` in [radard.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/selfdrive/controls/radard.py#L185) |
| `run()` loop tail | `get_params_sp()` + `run_ext()` -> publishes `carControlSP` |

`self.sm`/`self.pm` service lists are extended by `sm_services_ext`/`pm_services_ext` from `ControlsExt`, not hardcoded.

## ANTI-PATTERNS (THIS DIR)

- **DO NOT bypass `clip_curvature()`** - it enforces the ISO lateral jerk/accel envelope and returns the `curvature_limited` flag that saturation detection depends on.
- **DO NOT add SP feature logic here.** Extend via the `_ext` seams above; stock files stay diffable against upstream.
- **DO NOT reorder the `steerControlType` checks** - `angle`/`curvature` cars also carry a `lateralTuning` union, so tuning-first ordering silently mis-selects.
- **DO NOT publish to `longitudinalPlan`** from SP code - use `longitudinalPlanSP`.
- **DO NOT import into `long_mpc.py` outside its constants block** without reading the MPC section above.
- **DO NOT read `sm['modelV2']` for lateral in `LatControlTorque`** directly - it arrives via `self.LaC.extension.update_model_v2()` from controlsd.

## NOTES

- `controlsd` runs at 100 Hz (`Ratekeeper(100)`, `DT_CTRL`); `plannerd` at model rate (`DT_MDL`, polls `modelV2`).
- Sign convention: `LatControlTorque.update()` returns `-output_torque`; "left is positive" is still a TODO upstream.
- `LongitudinalPlanner.update()` picks the **minimum** accel across MPC / cruise / e2e candidates, but `should_stop` is an **any()** across all of them.
- Torque params are live-updated from `lateralTorqueParameters` (torqued) only when `useParams` and `sm.all_checks()` pass; every update must be followed by `update_limits()`.
- Tests: `unittest.TestCase` under [tests/](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/selfdrive/controls/tests) (`test_latcontrol.py`, `test_longcontrol.py`, `test_leads.py`, `test_following_distance.py`, ...). Run with `tools/op.sh test`.
