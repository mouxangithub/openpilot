# Offline radar validation toolchain

Ported from CarrotPilot (`E:/cp`, `selfdrive/carrot/radar/tools`) for offline
radar cut-in / lead-model replay, validation and review. This is a **developer
toolchain only**: nothing here is registered in `manager`, writes CAN, or runs
on the driving path. It operates over recorded routes.

## Layout

| Path | Origin | Purpose |
| --- | --- | --- |
| `radar/tools/` (9 files, ~8.7k lines) | cp `radar/tools/` | CLI tools: route replay, lead validation, occupancy v2/v3 comparison, group3 SCC replay, web/video review export |
| `radar/route_replay/` (6 files, ~6.8k lines) | cp `cluster/{cluster_config,cluster_models,cluster_trip_report,cluster_utils,cluster_route_replay}.py` | The UI-independent slice of the cluster bundle: route log parsing, geometry/state models and trip reporting. The raylib/GLES/USB/H264 display layers were deliberately excluded. |
| `radar/data/` (2 JSON, ~229 KB) | cp `cluster/{cutin_validation_cases,radar_trajectory_labels}.json` | Validation case set and trajectory labels. |
| `radar_motion/cutin_alert.py`, `cutin_helpers.py` | cp `selfdrive/controls/lib/cutin_*` | Pure numpy/stdlib cut-in tracking helpers used by the replay engine. Placed inside `radar_motion` so they sit next to the code they support. |

## Adaptations applied during the port

- Import roots `openpilot.selfdrive.carrot.*` -> `openpilot.sunnypilot.carrot.*`.
- The flat `import cluster_route_replay` sys.path hack became a normal package
  import: `openpilot.sunnypilot.carrot.radar.route_replay.route_replay`.
- Data files moved from `cluster/` to `radar/data/`; all default-case/label
  paths updated accordingly.
- Video-review font path now resolves via `REPO_ROOT/openpilot/selfdrive/assets`.
- `radar_web_export.source_version()` fingerprints `radar/route_replay`
  instead of the non-existent `cluster/` and `selfdrive/controls/lib` trees.
- Block indentation converted 4-space -> 2-space to satisfy the repo-wide
  `check_indentation.py` gate; the vendored per-file ruff ignores in
  `pyproject.toml` cover remaining upstream style habits (string concat,
  zip/frozen-dataclass defaults).

## Running

```bash
# from repo root, with opendbc importable on the device/venv
python -m openpilot.sunnypilot.carrot.radar.tools.radar_validation_replay --help
python -m openpilot.sunnypilot.carrot.radar.tools.validate_radar_lead_model --help
python -m openpilot.sunnypilot.carrot.radar.tools.compare_radar_occupancy_v2 --help
```

Only `radar_group3_replay` needs the Hyundai group-3 SCC DBC path; it imports
`opendbc.car.hyundai.radar_group3` lazily and the standalone launchers prepend
`opendbc_repo/` to `sys.path` themselves.

## Verification status

- Local (Windows, numpy + pycapnp): all 12 modules import; every CLI `--help`
  works; source fingerprinting and data/schema-root path resolution verified;
  `tests/test_cutin_alert.py` (8 cases) passes; ruff + indentation gate pass.
- Not run locally: full route replay (requires zmq/cereal device runtime) and
  ffmpeg/Pillow contact-sheet export. Validate on device against a known route
  before trusting review output.
