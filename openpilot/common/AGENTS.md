# openpilot/common/

Shared library layer: the Params key-value store, hardware abstraction, test harness, geometry transforms, and small math/logging utilities used by every daemon.

## STRUCTURE

```
common/
├── params.{py,h,cc}     # Params store (Python = ctypes over libparams_c)
├── params_c.cc          # C ABI shim consumed by params.py
├── params_keys.h        # THE key registry (name -> flags, type, default)
├── test.py              # OpenpilotTestCase
├── prefix.{py,h}        # OpenpilotPrefix isolation sandbox
├── version.py           # BuildMetadata / channel classification
├── hardware/            # base.py|base.h, hw.h (Path::*), comma/, pc/, usb.py
├── transformations/     # Cython: coordinates, orientation, camera, model
├── api/, esim/, mock/   # comma API client, eSIM/LPA, cereal msg generators
├── tests/               # test_params.py, test_markdown.py, native_test.h, ...
└── util.*, yuv.*, queue.h, timing.h, swaglog.*, realtime.py, pid.py,
    simple_kalman.py, filter_simple.py, constants.py, basedir.py, git.py
```

## WHERE TO LOOK

| Task | Location |
|---|---|
| Add / change a Params key | [params_keys.h](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/common/params_keys.h) |
| Python Params API | [params.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/common/params.py) |
| C++ Params API | [params.h](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/common/params.h) / [params.cc](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/common/params.cc) |
| Detect device vs PC | [hardware/__init__.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/common/hardware/__init__.py) |
| Resolve a filesystem path | `Paths` in [hardware/hw.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/common/hardware/hw.py), `Path::*` in [hardware/hw.h](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/common/hardware/hw.h) |
| Write a test | subclass [test.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/common/test.py) `OpenpilotTestCase` |
| Version / branch / channel | [version.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/common/version.py) |
| Hardware daemons, manager | see [openpilot/system/AGENTS.md](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/system/AGENTS.md) |

## PARAMS

Persistent store at `Path::params()` (`/data/params` on device, `~/.comma/params` on PC), namespaced by the `OPENPILOT_PREFIX` env var. One file per key under `<params>/d`.

**Adding a key:** add one entry to the `keys` map in `params_keys.h`: `{"MyKey", {FLAGS, TYPE, optional_default}}`. Nothing else. Unregistered names raise `UnknownKeyName` from `Params.check_key`. sunnypilot keys go under the `// --- sunnypilot params --- //` block (line 137+), not scattered into the upstream block.

**`ParamKeyType`** (params.h:25): `STRING` (utf-8), `BOOL`, `INT`, `FLOAT`, `TIME` (ISO 8601), `JSON`, `BYTES`. Python casts through `CPP_2_PYTHON` / `PYTHON_2_CPP`; a write of the wrong Python type raises `TypeError`, a corrupt read logs a warning and falls back to the default.

**`ParamKeyFlag`** (params.h:13), OR'd together:

| Flag | Effect |
|---|---|
| `PERSISTENT` 0x02 | survives everything; never auto-cleared |
| `CLEAR_ON_MANAGER_START` 0x04 | wiped when manager boots |
| `CLEAR_ON_ONROAD_TRANSITION` 0x08 | wiped on offroad -> onroad |
| `CLEAR_ON_OFFROAD_TRANSITION` 0x10 | wiped on onroad -> offroad |
| `DONT_LOG` 0x20 | excluded from log/upload (secrets, e.g. `AccessToken`). **C++ only** |
| `DEVELOPMENT_ONLY` 0x40 | stripped on release channels |
| `CLEAR_ON_IGNITION_ON` 0x80 | wiped on ignition rising edge |
| `BACKUP` 0x100 | included in settings backup/restore |
| `ALL` 0xFFFFFFFF | selector for `clear_all` / `all_keys` |

`DONT_LOG` is absent from the Python `ParamKeyFlag` IntFlag ([params.py:13-21](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/common/params.py#L13-L21)), don't pass it from Python.

**Defaults** are the optional third field of `ParamKeyAttributes`. A missing key reads as `None` unless you ask: `get(key, return_default=True)` or `get_default_value(key)`. `get_bool` returns `False` for a missing key.

**Writes are atomic**: tmpfile -> write -> `fsync` -> take `<params>/.lock` -> `rename` -> `fsync` parent dir ([params.cc:132-169](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/common/params.cc#L132-L169)). So a reader never sees a torn value. `put(..., block=True)` waits for that to land; default `block=False` queues onto a lazily-spawned async writer thread (C++ `putNonBlocking`), fine for hot loops, but the value is not on disk when the call returns. `get(key, block=True)` spins at 10 Hz until the key is non-empty and raises `KeyboardInterrupt` on SIGINT/SIGTERM.

`Params` is not copyable in C++; in Python it's picklable via `__reduce__` (re-opens by path) and freed by a `weakref.finalize` that deliberately skips atexit so daemon threads can't touch a dead handle.

## TEST HARNESS

`OpenpilotTestCase` subclasses `unittest.TestCase` and wraps `run()`, not `setUp`, so subclasses may override `setUp`/`tearDown` freely without calling super. Per test you get for free: a `clean_env()` snapshot/restore of `os.environ`, an `OpenpilotPrefix` (unique `OPENPILOT_PREFIX`, private params dir, private `msgq` dir in `/dev/shm` or `/tmp` on macOS, private log root and download cache, all deleted on exit), `manager.manager_cleanup()`, and a GC re-enable.

Legacy hook shims: `setup_method`/`teardown_method` are re-bound to run inside the prefix; `setup_class`/`teardown_class` run from `setUpClass`/`tearDownClass`. Test methods may declare `mocker`, `monkeypatch`, or `subtests` parameters and get lightweight shims (`Mocker`, `MonkeyPatch`, `SubTests`); any other bare parameter name is resolved as a module-level factory function, generators supported.

Class attrs: `COMMA_HARDWARE_TEST = True` skips on PC and calls `HARDWARE.initialize_hardware()` + kills athena; `SHARED_DOWNLOAD_CACHE = True` sets `COMMA_CACHE` so the cache isn't wiped between tests. Run with `tools/op.sh test`.

## ANTI-PATTERNS (THIS DIR)

- **NEVER** read or write a params file path directly, always go through `Params`, or you bypass the lock and the prefix.
- **NEVER** use a key not registered in `params_keys.h`, and never repurpose an existing key's meaning; old values persist across updates.
- **NEVER** rely on `put()` having hit disk without `block=True` (reboot/shutdown paths especially).
- **NEVER** use `TICI` / `larch64` for runtime checks, that naming is gone. Use `AGNOS`, `COMMA_HARDWARE`, `PC` from `common/hardware/__init__.py`.
- **NEVER** hardcode `/data/...` or `~/.comma/...`, use `Paths` / `Path::` so `OPENPILOT_PREFIX` is honored.
- **NEVER** mutate global state in a test without the harness; a bare `unittest.TestCase` here leaks params into the real store.
- **NEVER** hand-edit `*_pyx.cpp` from `transformations/`; edit the `.pyx` and rebuild.

## NOTES

- `params.py` dlopens `libparams_c{.so,.dylib}` next to itself, a stale build gives an import error, not a wrong answer. Rebuild before debugging.
- Two version headers: `common/version.h` (upstream) and `sunnypilot/common/version.h` (the SP string `get_version()` actually reads).
- `version.py` also owns channel classification (`release_channel`, `tested_channel`, `channel_type`) and the `SP_BRANCH_MIGRATIONS` / `CHESTNUT_BRANCHES` maps.
- `get_build_metadata()` prefers `build.json` at repo root, falls back to live git, else raises.
- `OpenpilotMetadata.comma_remote` gates release metrics upstream, don't touch it to silence the startup alert.
