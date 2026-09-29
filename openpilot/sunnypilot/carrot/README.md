# Carrot (sunnypilot fork)

`openpilot/sunnypilot/carrot` is the port of CarrotPilot's (`E:/cp`) `selfdrive/carrot`
into this fork. This file is the **parity map**: what is here, what is deliberately
absent, and what the phone app can reach.

Upstream layout and web-app structure are documented in CarrotPilot's own
`selfdrive/carrot/README.md`; the 7714 wire protocol is in
[`carrot_navi_api.md`](./carrot_navi_api.md).

## Port surface

Everything the Android app can reach is present and at parity. The one behavioural
difference is the extra `port` field on the 7705 beacon (inert — see the note in
`carrot_navi_api.md`).

| Port | Proto | Owner (this fork) | Gate | Purpose |
|---|---|---|---|---|
| 7705 | UDP out | `carrot_man`, `carrot_navi` | `always_run` | discovery beacon (`ip`, `navi_debug`) |
| 7706 | UDP | `carrot_man` | `always_run` | 7706 navi / radar / TMC payload stream |
| 7709 | TCP | `carrot_man` (`_route_port`) | `always_run` | `carrot_route` destination points |
| 7711 | TCP | `xiaoge_data` | `carrot_enabled` | xiaoge vision result stream |
| 7713 | HTTP | `carrot_man` (`_navi_http_port`) | `always_run` | navi HTTP side channel |
| 7714 | TCP/WS | `carrot_navi` | `always_run` | WebSocket **v2** control + json + image + render |
| 8082 | HTTP | `xiaoge/v_asm_server.py` | `carrot_enabled` | wide-angle ASM/LKA debug page |
| 8088 | HTTP | `carrot_man` → `web_interface.py` | **`CarrotWebEnabled` (opt-in)** | nav-params editor + radar view |

Not present, because the subsystem that owns them is not ported:

| Port | Owner upstream | Missing because |
|---|---|---|
| 6999 | `recovery/server.py` | `recovery/` (2,562 lines) not ported |
| 7000 | `carrot_server.py` | `server/` + `web/` (see below) not ported |

## Process gating model

CarrotPilot runs every `carrot_*` process with `always_run` and has no master switch; the
app drives the feature at runtime. This fork now matches that for the discovery/navi
backbone:

```
carrot_man        always_run                              restart_if_crash
carrot_navi       always_run                              restart_if_crash
carrot_bluetooth  always_run, enabled=COMMA_HARDWARE      restart_if_crash
xiaoge_data       carrot_enabled                          restart_if_crash
```

A **process gate is the wrong home for a user switch**: the manager only re-evaluates its
gates on the manager cycle, so a process parked behind `CarrotEnabled` (default `"0"`)
could not come up at the moment the app connected. That is what produced the
"7705 未激活" report.

The switches that remain are **behaviour** switches, evaluated every tick by their
consumer:

| Param | Consumer | Meaning |
|---|---|---|
| `CarrotEnabled` | `carrot_man.tick`, `card.py`, `carrot_serv`, `carrot_controls`, `map_controller` | master behaviour switch: merge carrot data into the driving stack |
| `CarrotNaviV2Enabled` | `card.py` | consume the 7714 v2 stream for lane-blocking (`carrot_navi` itself always runs) |
| `CarrotNavLaneGuideBlockEnabled` | `card.py` | let the 7706 `navLaneGuide` array block lanes |
| `CarrotWebEnabled` | `carrot_man` | start the 8088 HTTP control plane |
| `CarrotAmapBlindSpotEnabled` | `carrot_man` | parse 7706 blind-spot / LiDAR fields |

Card-side switches are refreshed in `card.py::params_thread`, so flipping them takes
effect without a reboot.

### Deliberate divergence: the 8088 control plane is opt-in

CarrotPilot's `carrot_server` (port 7000) is `always_run` unless `CARROT_WEB_EXTERNAL=1`.
This fork's equivalent, `web_interface.py`, binds `0.0.0.0:8088` and serves an
**unauthenticated, writable** nav-params form (`/nav_params`). It therefore stays behind
`CarrotWebEnabled` (default `"0"`). Enable it only on a trusted network.

## Alignment matrix vs. CarrotPilot

### Ported (content-verified, different module path than upstream)

| CarrotPilot | This fork | Note |
|---|---|---|
| `cruise_gap.py` | `openpilot/sunnypilot/selfdrive/car/cruise_helpers.py` | same three helpers (`supported_gap_levels`, `cruise_gap_levels`, `next_gap_personality`), covered by `test_cruise_gap_personality.py` |
| `driving_mode.py` | `openpilot/sunnypilot/carrot/carrot_functions.py` | `DrivingMode`, `DrivingModeDetector`, `get_mode_lead_response`, `get_driving_mode_factors`, wired to `MyDrivingMode` / `MyDrivingModeAuto` |
| `t_follow.py` | `openpilot/sunnypilot/carrot/t_follow.py` | fork keeps only the helpers its planner uses |
| `xiaoge/` | `openpilot/sunnypilot/carrot/xiaoge/` | all files present; upstream ships an extra `README.md` |
| `carrot_navi_api.md` | `carrot_navi_api.md` | vendored, 2 path references adapted |

### Not ported — large, self-contained subsystems

Sizes are the upstream file counts, useful for scoping. None of these block the app's
navi link, which is complete.

| Subsystem | Upstream size | What it is | Why it is not here |
|---|---|---|---|
| `cluster/` | 36 files, 33,074 lines | external-display HUD app (C3X gamepad/USB display, H.264 pipeline, scene renderer, replay tools, `main.py`) | whole separate application; needs `realtime/` + USB display plumbing. This fork has `cluster_view/` (1,151 lines) = config/display/overlay only |
| `radar/` | 9,049 lines | alternative radar lead pipeline (`radard_dpath`, `radarcan`, `can_batch`, `lateral`) | this fork uses stock `radard` + `carrot/radar_motion/lane_change_gap.py` (217 lines) |
| `server/` | 21 files, 30,379 lines | carrot web backend (features, services, live runtime, terminal bridge, dashcam, eGPU model) | needs `web/` to be useful |
| `web/` | 546 files, 148,255 lines | the carrot web front end (bundled JS/CSS, npm build) | front-end project; only meaningful with `server/` |
| `realtime/` | 2,500 lines (C++/Cython) | raw/compact state transport for the cluster + web live view | cluster/web only; needs SCons integration |
| `recovery/` | 2,562 lines | standalone support shell + PTY server on 6999 | operational tool, not part of the driving path |
| `kmap/` | 1,702 lines | map widget (`kmap.js`/`css`/`index.html`) | consumed by `web/` |
| `cweb_push.py` | 310 lines | posts this unit's LAN IP to a **third-party** endpoint, whose URL is stored XOR-obfuscated in the file | see below |

### `cweb_push` — do not port without an explicit decision

`cweb_push.py` is a phone-home agent: every 5 s it resolves the device IP and POSTs
`{deviceId, ip, port}` to a hosted service (default URL embedded as XOR-obfuscated
bytes, decodable at `_DEFAULT_REPORT_URL_KEY`). It exists to let a browser reach the car
over the operator's relay. Porting it would add default-on third-party egress and device
identifiers to a shipping product, and it is only useful together with `server/` +
`web/`. Treat it as a product/privacy decision, not a porting task.

## Tests

```bash
# from E:/sp
PYTHONPATH="E:\\sp" python -m unittest discover -s openpilot/sunnypilot/carrot -t .
PYTHONPATH="." python openpilot/selfdrive/ui/tests/navigation_render_smoke.py
PYTHONPATH="." python openpilot/selfdrive/ui/tests/carrot_tuning_render_smoke.py
```

`bluetooth/tests/test_input.py` pins the HID gesture decoder against a recorded real
Yiser-J6 event stream, plus the command queue and config validation (ported from
CarrotPilot's pytest suite; `test_api.py` and `test_daemon.py` are intentionally not
ported — see that module's docstring).

`test_carrot_planner.py` needs the installed `opendbc` package (`openpilot.cereal`
resolves `files("opendbc")`), so it cannot run on a bare PC checkout without the native
deps.
