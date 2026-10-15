# controls/lib/ - SP CONTROL FEATURE LIBRARIES

sunnypilot's per-feature control logic. All features are **param-gated** and integrate via [controlsd_ext.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/sunnypilot/selfdrive/controls/controlsd_ext.py) + [longitudinal_planner.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/sunnypilot/selfdrive/controls/lib/longitudinal_planner.py).

## STRUCTURE

```
lib/
├── dec/                      # DEC - Dynamic Experimental Controller (blended ACC)
├── nnlc/                     # NNLC - Neural Network Lateral Control (ML torque feedforward)
├── smart_cruise_control/     # SCC-V (vision) + SCC-M (map) cruise enhancements
├── speed_limit/              # SLA - Speed Limit Assist (resolver + adapter)
├── auto_lane_change.py       # Blinker-triggered ALC (nudgeless, configurable timer)
├── blinker_pause_lateral.py  # Pause steering during blinker
├── lane_turn_desire.py       # Use model turn-direction for lane turn intersections
├── latcontrol_torque_v0.py           # Legacy torque tune (param-selectable)
├── latcontrol_torque_ext.py          # Extended torque controller w/ NNLC integration
├── latcontrol_torque_ext_base.py     # Base for ext torque
├── latcontrol_torque_ext_override.py # Override variant
├── latcontrol_torque_versions.json   # Version selector mapping
├── longitudinal_planner.py   # SP planner integrating DEC + SCC + SLA + E2E alerts
├── e2e_alerts_helper.py      # End-to-end model alerts (green light, lead departure)
└── tests/                    # blinker_pause, lane_turn, auto_lane_change, latcontrol_v0
```

## FEATURE INTEGRATION POINTS

| Feature | Integration | Param gate |
|---------|-------------|------------|
| **DEC** | longitudinal_planner.py | `DynamicExperimentalControl` |
| **NNLC** | latcontrol_torque_ext.py via `CarParamsSP.NeuralNetworkLateralControl` | `NeuralNetworkLateralControl` |
| **SCC-V/M** | longitudinal_planner.py | `SmartCruiseControlVision`, `SmartCruiseControlMap` |
| **SLA** | longitudinal_planner.py via [speed_limit/resolver.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/sunnypilot/selfdrive/controls/lib/speed_limit) | `SpeedLimitMode` |
| **Auto Lane Change** | controlsd_ext.py | `AutoLaneChangeTimer` |
| **Blinker Pause** | controlsd_ext.py | `BlinkerPauseLateralControl`, `BlinkerPauseLateralControlSpeed`, `BlinkerPauseLateralControlReengageDelay` |
| **Lane Turn Desire** | controlsd_ext.py via `ModelDataV2SP.laneTurnDirection` | `LaneTurnDesire` |
| **Torque v0** | `latcontrol_torque_versions.json` selector | `EnforceTorqueControl` + version key |

## DEC (Dynamic Experimental Controller)

Blended ACC: switches between `acc` (cruise) and `blended` (e2e) longitudinal modes. Output written to `LongitudinalPlanSP.dec.{state, enabled, active}` and consumed by controlsd. Uses Kalman-filtered state estimate.

## NNLC (Neural Network Lateral Control)

ML model produces torque feedforward from `roll, pitch, lateral_accel, jerk_error`. Model file is per-platform - selected via `CarParamsSP.neuralNetworkLateralControl.model.{path,name}`. Training data from submodule [openpilot/sunnypilot/neural_network_data/](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/sunnypilot/neural_network_data).

## SCC (Smart Cruise Control)

Two parallel sub-systems:
- **SCC-V (Vision)**: predicts upcoming lateral accel from model, slows for turns
- **SCC-M (Map)**: uses MAPD road curvature

Both write to `LongitudinalPlanSP.smartCruiseControl.{vision,map}`. State machines: `disabled -> enabled -> entering -> turning -> leaving -> overriding`.

## SLA (Speed Limit Assist)

Resolver pulls from car CAN, MAPD, or override. Assist applies the resolved limit to cruise. State machine: `disabled -> inactive -> preActive -> pending -> adapting -> active`.

## ANTI-PATTERNS (THIS DIR)

- **NEVER add new lateral controllers without integrating via `latcontrol_torque_ext_base`** - bypasses NNLC + override flows.
- **NEVER bypass `controls_allowed`** - all output must respect the safety state from cereal.
- **NEVER hardcode model paths** - read from `CarParamsSP.neuralNetworkLateralControl.model.path`.
- **NEVER write to `LongitudinalPlan` (stock)** from SP code - write to `LongitudinalPlanSP` (custom.capnp).
- **NEVER tune for one car in shared DEC/SCC code** - use `CarParamsSP.flags` per-platform.
- **DO NOT enable a feature by default** - all SP features must be Param-gated and default-off unless safety-vetted.

## NOTES

- `latcontrol_torque_versions.json` lets users select between tune revisions (v0 = upstream pre-2026 tune).
- `e2e_alerts_helper.py` reads from `ModelDataV2SP` for green-light + lead-departure detection - emits via `LongitudinalPlanSP.e2eAlerts`.
- Tests in `tests/` are plain `unittest` (subclass `OpenpilotTestCase`). Run one subtree: `./tools/op.sh test openpilot/sunnypilot/selfdrive/controls/lib/nnlc`.
- The MPC solver caveat from parent applies: imports outside the constants block do NOT trigger rebuild.
