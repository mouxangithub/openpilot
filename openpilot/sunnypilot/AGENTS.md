# sunnypilot/ - FORK EXTENSION LAYER

Fork-specific code mirroring upstream layout. **Primary development target.** 263 tracked files (114 of them under `neural_network_data/`, a submodule). See parent [AGENTS.md](file:///Users/cyonsun/Documents/Code/sunnypilot/AGENTS.md) for project-wide conventions.

## STRUCTURE

```
sunnypilot/
├── selfdrive/      # Mirrors selfdrive/ - extends controlsd, selfdrived, car, locationd, pandad, ui
├── system/         # Mirrors system/ - hardware (c3 launcher), params_migration, sensord, updated
├── common/         # transformations (Cython EKF), version.h
├── mads/           # MADS - Modular Assistive Driving System (custom engagement)
├── sunnylink/      # Cloud services platform (40+ files) - separate AGENTS.md
├── mapd/           # MAPD - OSM speed-limit data + China provinces
├── modeld_v2/      # Tinygrad-based modeld (alternative to selfdrive/modeld/ SNPE)
├── models/         # Model bundle manager (download, select, hash-verify)
├── livedelay/      # Live steering latency estimator
├── navd/           # Nav helper stubs
├── neural_network_data/   # SUBMODULE - NNLC training data
├── tools/          # SP-specific dev tools (memory profiler, footage puller)
└── SConscript      # Builds: common/transformations + modeld_v2 + selfdrive/locationd
```

## EXTENSION PATTERN

sunnypilot **extends** upstream openpilot files via `*_ext.py` siblings. Stock files stay untouched; SP files import + wrap them.

| Stock file | SP extension |
|------------|--------------|
| `openpilot/selfdrive/controls/controlsd.py` | [controlsd_ext.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/sunnypilot/selfdrive/controls/controlsd_ext.py) |
| `openpilot/selfdrive/selfdrived/events.py` | [events.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/sunnypilot/selfdrive/selfdrived/events.py) (custom alerts) |
| `openpilot/selfdrive/locationd/torqued.py` | `openpilot/sunnypilot/selfdrive/locationd/torqued_ext.py` |
| `opendbc_repo/opendbc/car/{brand}/carstate.py` | `opendbc_repo/opendbc/sunnypilot/{brand}/carstate_ext.py` |

## PROCESS ADDITIONS

SP daemons registered in [openpilot/system/manager/process_config.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/system/manager/process_config.py) (search `# sunnypilot`):
- `manage_sunnylinkd` - sunnylink athena daemon
- `models_manager` - model download/select (offroad only)
- `modeld_tinygrad` - alternative modeld (when `Runner.tinygrad`)
- `mapd_manager`, `mapd` (native) - OSM data
- `locationd_llk` - live likelihood location
- `backup_manager` - encrypted device state backups
- `sunnylink_registration_manager`, `statsd_sp` - registration + telemetry

## CEREAL CONTRACTS (custom.capnp)

SP-specific structs use reserved IDs (DO NOT change identifiers):
- `SelfdriveStateSP @0x81c2f05a394cf4af` - MADS + ICBM
- `ModelManagerSP @0xaedffd8f31e7b55d` - model bundles + Runner enum
- `LongitudinalPlanSP @0xf35cc4560bbf6ec2` - DEC + SCC + SpeedLimit
- `OnroadEventSP @0xda96579883444c35` - SP event names
- `CarParamsSP @0x80ae746ee2596b11` - SP car flags + NNLC config
- `CarControlSP @0xa5cd762cd951a455` - per-frame SP control
- `CarStateSP @0xb86e6369214c01c8`, `LiveMapDataSP @0xf416ec09499d9d19`, `ModelDataV2SP @0xa1680744031fdb2d`, `BackupManagerSP @0xf98d843bfd7004a3`

## FEATURE FLAGS (Params)

Features are param-gated via [openpilot/common/params_keys.h](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/common/params_keys.h). Common SP keys: `Mads`, `MadsMainCruiseAllowed`, `MadsUnifiedEngagementMode`, `IntelligentCruiseButtonManagement`, `NeuralNetworkLateralControl`, `EnforceTorqueControl`, `SpeedLimitMode`, `LagdToggle`, `BlinkerPauseLateralControl`, `AutoLaneChangeTimer`, `LaneTurnDesire`, `DynamicExperimentalControl`, `SunnylinkEnabled`.

## ANTI-PATTERNS (THIS DIR)

- **NEVER modify stock cereal stock-message field semantics**. Add to `custom.capnp` instead.
- **NEVER duplicate upstream classes** - extend via `_ext.py`.
- **NEVER hardcode feature behavior** - gate via Params.
- **NEVER touch `openpilot/sunnypilot/neural_network_data/`** directly - it's a submodule.
- **DO NOT confuse modeld vs modeld_v2** - they are mutually exclusive at runtime, switched by `ModelManagerSP.Runner` enum.

## NOTES

- `openpilot/sunnypilot/` is the real source tree for namespace imports; edit files there directly.
- Two-channel build flag: `release_sp_channel` (sunnypilot release branch) vs `release_channel` (upstream).
- SP version lives in [openpilot/sunnypilot/common/version.h](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/sunnypilot/common/version.h) - this is what `common/version.py::get_version()` reads. The upstream [openpilot/common/version.h](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/common/version.h) is a separate file; do not confuse them.
- Tests here are plain `unittest` (subclass `OpenpilotTestCase`), run via `./tools/op.sh test openpilot/sunnypilot`. pytest was removed repo-wide.
