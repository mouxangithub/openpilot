# PROJECT KNOWLEDGE BASE

**Generated:** 2026-08-24 SGT
**Commit:** db88db7ad9
**Branch:** mazda-port

## OVERVIEW

sunnypilot is a fork of comma.ai openpilot (Level-2 driver assistance). Multi-language: Python 3.12 + C++17 + Cython + STM32 C firmware. Build = SCons. Pkg mgr = uv. SCons arch tags: `comma_arm64` (comma 3/3X on AGNOS), `x86_64`/`aarch64` (Linux PC), `Darwin` (macOS arm64; x86 unsupported).

## STRUCTURE

```
sunnypilot/
├── openpilot/      # Real source tree (common, selfdrive, system, sunnypilot, cereal, third_party, tools)
│   ├── cereal/     # Cap'n Proto messaging spec - see openpilot/cereal/README.md
│   ├── common/     # Shared C++/Python utils + Params (key-value persistent store)
│   ├── selfdrive/  # Driving stack (controlsd, plannerd, modeld, locationd, ui)
│   ├── sunnypilot/ # Fork-specific code (MADS, sunnylink, mapd, modeld_v2, NNLC, ...)
│   ├── system/     # System services (manager, hardware, loggerd, athena, updated)
│   ├── third_party/ # ONLY copyparty + mapd_pfeiferj. Native deps come from `comma-deps-*` wheels
│   └── tools/      # openpilot tools (cabana, replay, sim)
├── tools/          # Root dev tools (op.sh, car_porting/, release/, scripts/)
├── msgq_repo/      # SUBMODULE - IPC backend
├── opendbc_repo/   # SUBMODULE (FORK: conversun/opendbc) - car interfaces + safety
├── panda/          # SUBMODULE (FORK: conversun/panda) - STM32 firmware
├── rednose_repo/   # SUBMODULE - EKF library
├── tinygrad_repo/  # SUBMODULE (FORK: sunnypilot/tinygrad) - ML inference
├── teleoprtc_repo/ # SUBMODULE - WebRTC for body
├── docs/           # User + migration docs
├── release/        # Release build/CI scripts
├── site_scons/     # Custom SCons builders (cython, compilation_db, rednose_filter)
├── scripts/lint/   # lint.sh + check_*.sh
├── SConstruct      # Root build orchestrator
├── pyproject.toml  # Python deps, ruff, ty, codespell, uv sources. NO pytest config
├── tools/test_runner.py   # THE test runner (custom parallel unittest) - replaced pytest
├── launch_openpilot.sh    # Device entry; routes to hardware-specific launcher
├── launch_chffrplus.sh    # Main launcher (overlay updates -> manager.py)
└── launch_env.sh   # Thread caps, AGNOS_VERSION
```

## WHERE TO LOOK

| Task | Location |
|------|----------|
| Add a managed daemon | [openpilot/system/manager/process_config.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/system/manager/process_config.py) |
| Add a cereal message | [openpilot/cereal/log.capnp](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/cereal/log.capnp) (stock) or [openpilot/cereal/custom.capnp](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/cereal/custom.capnp) (fork-only) |
| Add a Params key | [openpilot/common/params_keys.h](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/common/params_keys.h) |
| Add a sunnypilot feature | `openpilot/sunnypilot/...` mirroring upstream layout, with `_ext.py` suffix to extend |
| Add safety logic | [opendbc_repo/opendbc/safety/](file:///Users/cyonsun/Documents/Code/sunnypilot/opendbc_repo/opendbc/safety) (C, MISRA) - tests MUST pass with 100% coverage |
| Add a car port | [opendbc_repo/opendbc/car/{brand}/](file:///Users/cyonsun/Documents/Code/sunnypilot/opendbc_repo/opendbc/car) + [opendbc_repo/opendbc/sunnypilot/{brand}/](file:///Users/cyonsun/Documents/Code/sunnypilot/opendbc_repo/opendbc/sunnypilot) for SP extensions |
| Modify UI | [openpilot/selfdrive/ui/](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/selfdrive/ui) (Raylib Python) + [openpilot/selfdrive/ui/sunnypilot/](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/selfdrive/ui/sunnypilot) for SP screens |
| Modify settings UI | [openpilot/sunnypilot/sunnylink/settings_ui_src/](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/sunnypilot/sunnylink/settings_ui_src) -> compile via [openpilot/sunnypilot/sunnylink/tools/compile_settings_ui.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/sunnypilot/sunnylink/tools/compile_settings_ui.py) |
| Add a test | Co-locate `tests/test_*.py` next to module; subclass `OpenpilotTestCase` |
| Run on PC | [tools/op.sh](file:///Users/cyonsun/Documents/Code/sunnypilot/tools/op.sh) - `setup build lint test sim replay cabana juggle clip esim venv check switch start stop restart adb ssh script auth post-commit` |
| Deeper context on a subtree | Nested `AGENTS.md` in `cereal/`, `common/`, `selfdrive/{,controls,ui}/`, `system/{,ui}/`, `sunnypilot/{,sunnylink,selfdrive/controls/lib}/` |

## CONVENTIONS (DEVIATIONS FROM STANDARD)

### Python
- **Indent: 2 spaces** (NOT 4). Lines: 160 max. Quote style: `preserve`.
- **Type checker: `ty`** (Astral) - NOT mypy. `unresolved-import` + `unresolved-attribute` globally ignored (Cython/capnp) - [pyproject.toml:161-168](file:///Users/cyonsun/Documents/Code/sunnypilot/pyproject.toml#L161-L168).
- **Test runner: [tools/test_runner.py](file:///Users/cyonsun/Documents/Code/sunnypilot/tools/test_runner.py)** - custom parallel `unittest` runner. **pytest was REMOVED** (upstream `98e7c4f987`). There is NO `conftest.py`, no fixtures, no `testpaths`, no `-m 'not slow'`.
- **Tests are `unittest.TestCase`** - subclass [`OpenpilotTestCase`](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/common/test.py) to get per-test `OpenpilotPrefix` + clean env + `manager_cleanup()`. It shims legacy `mocker`/`monkeypatch`/`subtests` params and `setup_method`/`setup_class` hooks.
- **Imports: absolute, rooted at `openpilot.`** (`from openpilot.common.realtime import DT_CTRL`). Submodules root at `opendbc.`, `msgq.`, `panda.`, `tinygrad.`.
- **NEVER use `time.time()`** - use `time.monotonic()` (banned via TID251, the ONLY non-raylib ban).
- **Lint scope is `openpilot/` ONLY** (`ruff check openpilot`, `ty check openpilot`, `git ls-files openpilot`). Root `tools/`, `scripts/`, `release/`, `site_scons/` are NOT linted.

### Raylib UI (banned APIs - use wrappers)
- `pyray.measure_text_ex` -> `openpilot.system.ui.lib.text_measure`
- `pyray.is_mouse_button_pressed/released` -> `Widget._handle_mouse_press/release`
- `pyray.draw_text` -> use a function taking `font` argument (e.g., `rl.draw_font_ex`)
- `pyray.draw_texture` -> `rl.draw_texture_ex`
- Raylib now ships via the `comma-deps-raylib` wheel. C++ uses a bare `#include "raylib.h"` ([installer.cc](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/selfdrive/ui/installer/installer.cc#L9)) - there is no `third_party/raylib/` or `system/ui/raylib/` path anymore.

### C++
- **Werror enforced.** `-std=c++1z` (C++17), `-std=gnu11` (C). `-Wshadow` (full on `Darwin`/`comma_arm64`, `-Wshadow=local` elsewhere).
- **System library whitelist enforced** by SConstruct - see [SConstruct:83-92](file:///Users/cyonsun/Documents/Code/sunnypilot/SConstruct#L83-L92). Allowed: `EGL GLESv2 GL Qt5{Charts,Core,Gui,Widgets} dl drm gbm m pthread`. Anything else MUST be vendored.
- Linker flags: `-Wl,--as-needed -Wl,--no-undefined` (Linux only).

### Cython
- `.pyx` compiles to `.cpp` (NOT `.c`). Suffix: `CYTHONCFILESUFFIX=".cpp"`.
- Cython env REMOVES `-Werror`. Use `# cython: language_level = 3`.
- Generated `*_pyx.cpp` files are gitignored - DO NOT commit.

### Lint Pipeline ([scripts/lint/lint.sh](file:///Users/cyonsun/Documents/Code/sunnypilot/scripts/lint/lint.sh))
1. `ruff check openpilot`
2. `check_indentation.py` - 2-space enforcement on Python files
3. `check_added_large_files --maxkb=120`
4. `check_shebang_scripts_are_executable`
5. `check_shebang_format` (Python: `#!/usr/bin/env python3`, Bash: `#!/usr/bin/env bash`)
6. `check_nomerge_comments` - see Anti-patterns
7. `ty check openpilot` (skipped with `--fast`)
8. `codespell` (skipped with `--fast`)

Skips `openpilot/third_party/`. Run a subset: `op lint ty ruff`. Skip a subset: `op lint --skip ty`.
Post-commit hook auto-runs `op lint --fast`. Install via `op post-commit`.

### CI Gates (.github/workflows/tests.yaml)
`build release` (+ dirty-tree + submodule check) | `build macOS` | `static analysis` (lint.sh) | `unit tests` (`op test`) | `process replay`. Cereal changes additionally run [cereal_validation.yaml](file:///Users/cyonsun/Documents/Code/sunnypilot/.github/workflows/cereal_validation.yaml) against upstream openpilot.

## ANTI-PATTERNS (THIS PROJECT)

### SAFETY-CRITICAL (banned -> fork loses comma.ai access)
- **NEVER disable/nerf driver monitoring** - [docs/SAFETY.md:38](file:///Users/cyonsun/Documents/Code/sunnypilot/docs/SAFETY.md#L38)
- **NEVER disable/nerf excessive actuation checks** - [docs/SAFETY.md:39](file:///Users/cyonsun/Documents/Code/sunnypilot/docs/SAFETY.md#L39)
- **NEVER modify `opendbc_repo/opendbc/safety/` without preserving full test suite + 100% coverage** - [docs/SAFETY.md:40-42](file:///Users/cyonsun/Documents/Code/sunnypilot/docs/SAFETY.md#L40-L42)

### CEREAL SCHEMA (breaks log compat)
- **NEVER change Cap'n Proto identifiers** (e.g. `@0x81c2f05a394cf4af`) or field IDs (`@107`)
- **NEVER change which struct a field points to**
- **NEVER modify stock message struct field semantics** in a fork - create new structs in [openpilot/cereal/custom.capnp](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/cereal/custom.capnp) instead
- All cereal fields MUST be SI units unless name says otherwise

### CODE / WORKFLOW
- **NO `# NOMERGE`/`// NOMERGE` comments** - lint blocks them ([scripts/lint/check_nomerge_comments.sh](file:///Users/cyonsun/Documents/Code/sunnypilot/scripts/lint/check_nomerge_comments.sh))
- **NO files >120 KB** committed (lint blocks)
- **NO `time.time()`** - use `time.monotonic()`
- **NO blanket `# type: ignore` / `# noqa`** to silence ty or ruff - fix the type or narrow the rule
- **DO NOT add deps outside `commaai/dependencies` whitelist** - non-vendored system libs raise `UserError` from SConstruct
- **DO NOT include unsupported cars in upstream platforms** - put in `opendbc/sunnypilot/`
- **NO 500+ line PRs** ([docs/CONTRIBUTING.md:33](file:///Users/cyonsun/Documents/Code/sunnypilot/docs/CONTRIBUTING.md#L33))

### MPC SOLVERS (silent staleness)
- [openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/selfdrive/controls/lib/longitudinal_mpc_lib): the SConscript depends on a literal source list, so constants pulled in via `import` do NOT trigger a solver rebuild. Touch `long_mpc.py` or run `scons --clean`. (There is no `lateral_mpc_lib/` - lateral MPC was replaced by direct model curvature output.)

## COMMANDS

```bash
# First-time setup
./tools/op.sh setup                  # apt deps + uv sync + submodules + LFS

# Daily dev
source .venv/bin/activate
scons -j$(nproc)                     # Full build
scons --minimal                      # Skip tests/tools (fast)
scons --verbose                      # Show full compiler invocations
./tools/op.sh build                  # PC: scons -u | AGNOS: openpilot/system/manager/build.py

# Lint
./tools/op.sh lint                   # Full (ruff + ty + codespell + checks)
./tools/op.sh lint --fast            # Skip ty + codespell

# Test (pytest is GONE - do not use it)
./tools/op.sh test                             # everything, parallel across all CPUs
./tools/op.sh test openpilot/sunnypilot        # a directory
./tools/op.sh test path/to/test_x.py::Class::test_method
./tools/op.sh test -k blinker -v -s            # filter / verbose / no capture
./tools/op.sh test -j4 --durations 0 -W ignore

# Safety tests (different framework!)
cd opendbc_repo/opendbc/safety/tests && bash test.sh   # unittest + 100% coverage gate

# Process replay regression (EXCLUDED from op test)
openpilot/selfdrive/test/process_replay/test_processes.py -j$(nproc)

# Sim
./tools/op.sh sim                    # MetaDrive bridge + UI

# Tools
./tools/op.sh cabana                 # CAN visualizer
./tools/op.sh replay                 # Route replay
./tools/op.sh juggle                 # plotjuggler
```

## NOTES

- **`openpilot/` is the real source tree** -> contains `common/`, `selfdrive/`, `system/`, `sunnypilot/`, `cereal/`, `third_party/`, and `tools/`. Edit files there directly.
- **`opendbc_repo/opendbc/` and `msgq_repo/msgq/` are the checked-out submodules at root**. Both are forks (URL: `conversun/opendbc`, `conversun/panda`).
- **Process manager `manager.py` is the supervisor** - all daemons defined in [openpilot/system/manager/process_config.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/system/manager/process_config.py). To run a single daemon for testing: `python -m openpilot.selfdrive.controls.controlsd` (after `op_activate_venv`).
- **Two model runners coexist**: stock `openpilot/selfdrive/modeld/` (SNPE/PC) and sunnypilot's `openpilot/sunnypilot/modeld_v2/` (tinygrad). Switched via `ModelManagerSP.Runner` cereal enum.
- **Generated files (DO NOT commit, DO NOT edit):** `*_pyx.cpp`, `openpilot/cereal/gen/`, `openpilot/cereal/services.h`, `openpilot/selfdrive/locationd/models/generated/`, `panda/board/obj/`, `compile_commands.json`, `c_generated_code/` (acados).
- **AGNOS = comma 3/3X OS.** `/AGNOS` file marks the device; `COMMA_HARDWARE = AGNOS` and `PC = not COMMA_HARDWARE` in [common/hardware/__init__.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/common/hardware/__init__.py). The old `TICI`/`larch64` naming is gone - the SCons arch tag is `comma_arm64`.
- **Two `version.h` files**: SP version in [openpilot/sunnypilot/common/version.h](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/sunnypilot/common/version.h) (read by `common/version.py::get_version`), upstream in [openpilot/common/version.h](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/common/version.h).
- **Pinned on purpose**: `scons==4.10.1` (4.11 dropped the qt3 tool Cabana needs), `pycapnp==2.1.0` (2.2 leaks). Do NOT bump casually.
- Docs build with `python docs/serve.py --build` (zensical/mkdocs config removed).
- **Safety message lag = automatic disengage**: any monitored CAN msg lagging >1s causes `controls_allowed=false`. Affects feature additions reading new messages.
- **Submodule URLs are FORKED** for panda + opendbc + tinygrad. `git submodule update --remote` will pull from sunnypilot/conversun forks, not commaai upstream.
- Pre-existing branch `mazda-port` is in-progress car port work - see [docs/migration/](file:///Users/cyonsun/Documents/Code/sunnypilot/docs/migration).
