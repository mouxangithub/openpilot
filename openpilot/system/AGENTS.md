# system/ - SYSTEM SERVICES

OS-level services, hardware abstraction, process supervision. See parent [AGENTS.md](file:///Users/cyonsun/Documents/Code/sunnypilot/AGENTS.md) for global conventions.

## STRUCTURE

```
system/
├── manager/         # THE process supervisor - manager.py + process_config.py + process.py
├── hardware/        # Runtime HW daemons (hardwared, fan_controller, power_monitoring). Abstraction lives in common/hardware/
├── athena/          # comma connect remote daemon (athenad)
├── camerad/         # C++ camera daemon (+ webcam/ Python variant when WEBCAM=1)
├── loggerd/         # Log writer + encoderd + uploader + deleter + bootlog
├── sensord/         # IMU/sensor daemon
├── ubloxd/          # u-blox GPS (ubloxd, pigeond)
├── qcomgpsd/        # Qualcomm GPS daemon
├── updated/         # OTA updater (casync overlay-based)
├── webrtc/          # WebRTC bridge daemon
├── ui/              # Standalone UI lib (raylib wrappers + widgets) - NOT same as selfdrive/ui
├── sentry.py        # Sentry init (selfdrive vs panda projects)
├── micd.py / journald.py / proclogd.py / timed.py / tombstoned.py / logmessaged.py
└── tests/
```

## PROCESS MANAGER (CRITICAL)

[manager/manager.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/system/manager/manager.py) is the supervisor. All daemons live in [manager/process_config.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/system/manager/process_config.py) - the **single source of truth** for what runs.

Process types in [manager/process.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/system/manager/process.py):
- `PythonProcess` - Python module (`python -m openpilot.X`)
- `NativeProcess` - compiled binary
- `DaemonProcess` - long-lived process with PID tracked in Params

Run-condition functions: `always_run`, `only_onroad`, `only_offroad`, `iscar`, `notcar`, `driverview`, `joystick`. Combine via `and_(...)`, `or_(...)`.

```python
PythonProcess("controlsd", "openpilot.selfdrive.controls.controlsd", and_(not_joystick, iscar))
```

`manager_thread()` polls `deviceState.started` and ignition; calls `ensure_running(...)` each tick to start/stop processes.

## KEY DAEMONS

| Daemon | Type | Module | Notes |
|--------|------|--------|-------|
| `manager_athenad` | Daemon | openpilot.system.athena.manage_athenad | Comma connect (always) |
| `manage_sunnylinkd` | Daemon | openpilot.sunnypilot.sunnylink.athena.manage_sunnylinkd | SP cloud |
| `pandad` (Python) | Python | openpilot.selfdrive.pandad.pandad | Always |
| `_pandad` (Native) | Native | openpilot/selfdrive/pandad | Disabled (managed by Python pandad) |
| `loggerd` | Native | openpilot.system.loggerd | Onroad + logging param |
| `camerad` | Native | openpilot/system/camerad | `or_(driverview, livestream)`, `enabled=not WEBCAM` |
| `hardwared` | Python | openpilot.system.hardware.hardwared | Always |
| `updated` | Python | openpilot.system.updated.updated | Offroad only |

## HARDWARE ABSTRACTION

[common/hardware/base.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/common/hardware/base.py) defines `HardwareBase`. Concrete impls:
- [common/hardware/comma/](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/common/hardware/comma) - comma 3/3X (AGNOS updater, GPU, modem). There is no `tici/` dir anymore.
- [common/hardware/pc/](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/common/hardware/pc) - desktop fallback

Constants in [common/hardware/__init__.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/common/hardware/__init__.py): `AGNOS = isfile('/AGNOS')`, `COMMA_HARDWARE = AGNOS`, `PC = not COMMA_HARDWARE`. The `TICI` boolean and `/TICI` marker are gone - AGNOS-only daemons use `enabled=not PC`.

`system/hardware/` keeps the runtime daemons: [hardwared.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/system/hardware/hardwared.py), [fan_controller.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/system/hardware/fan_controller.py), [power_monitoring.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/system/hardware/power_monitoring.py).

## PARAM MIGRATION

On manager init, [openpilot/sunnypilot/system/params_migration.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/sunnypilot/system/params_migration.py) runs - migrates legacy SP param keys to new schema. Add migrations here when renaming/restructuring params.

## ANTI-PATTERNS (THIS DIR)

- **NEVER add a daemon outside [process_config.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/system/manager/process_config.py)** - manager won't supervise it.
- **NEVER call `time.time()`** - banned (TID251). Use `time.monotonic()`.
- **NEVER spawn subprocesses bypassing manager** - they won't be cleaned up.
- **NEVER block in `manager_thread()`** - 1s tick is the heartbeat for `power_watchdog` (line ~184).
- **DO NOT modify `ParamKeyFlag.CLEAR_ON_*` semantics in params_keys.h** without auditing manager_init.
- **DO NOT touch loggerd encryption keys / casync chunk format** - breaks log compat with comma servers.
- **DO NOT add system libraries to camerad/loggerd builds** - SCons whitelist enforced (allowed: `EGL GLESv2 GL Qt5* dl drm gbm m pthread`).

## NOTES

- Manager preimports all processes (`p.prepare()`) before main loop - import errors at boot, not runtime.
- AGNOS overlay updates land in `/data/safe_staging/finalized/` - launch_chffrplus.sh swaps directories.
- `openpilot/common/version.py::get_build_metadata()` returns channel info (release/dev/tested/release_sp). UI uses this for branding.
- `tombstoned` only runs on AGNOS (`enabled=not PC`) - PC has no kernel core dumps.
- Sentry is initialized PER PROCESS via `sentry.init(SentryProject.{SELFDRIVE,PANDA})`.
