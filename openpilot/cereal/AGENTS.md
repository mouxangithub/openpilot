# cereal

## OVERVIEW

Cap'n Proto schema + msgq pub/sub layer. Every daemon talks through here; a schema edit is a wire-format change felt by every route log ever recorded.

## STRUCTURE

```
cereal/
├── log.capnp          # the Event union (all upstream msg types)
├── custom.capnp       # fork-reserved structs; sunnypilot's SP messages live here
├── deprecated.capnp   # retired structs kept so old logs still parse
├── services.py        # service registry -> also generates services.h
├── SConscript         # capnpc invocation; car.capnp pulled from opendbc_repo
├── visionipc.py       # re-export shim over msgq's VisionIpc
├── visionstream.h
├── include/c++.capnp  # $Cxx.namespace annotation import
└── messaging/
    ├── __init__.py    # PubMaster / SubMaster / new_message (Python)
    ├── messaging.h    # SubMaster / PubMaster (C++)
    ├── socketmaster.cc
    ├── bridge.cc, msgq_to_zmq.cc, bridge_zmq.cc   # msgq <-> ZMQ for off-device
    └── tests/validate_sp_cereal_upstream.py       # CI compat gate
```

No `car.capnp` or `legacy.capnp` in this dir. `car.capnp` is compiled in from [opendbc_repo/opendbc/car/car.capnp](file:///Users/cyonsun/Documents/Code/sunnypilot/opendbc_repo/opendbc/car/car.capnp).

## THE RESERVED-SLOT PATTERN

Upstream leaves `CustomReservedN` structs empty forever. The fork claims them by **rename**, never by append. Slots 0-10 and 36 are already claimed (`SelfdriveStateSP` … `LongitudinalMpcTuningSP`); `CustomReserved11`-`19` at `@137`-`@145` are free. Three raw slots `customReservedRawData0/1/2` (`@124`-`@126`, `:Data`) exist for opaque blobs.

Steps to add a new SP message:
1. In [custom.capnp](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/cereal/custom.capnp), rename the lowest free struct (e.g. `CustomReserved11 @0xc2243c65e0340384`) to `MyThingSP`, keeping the line's `@0x...` verbatim, and add fields starting at `@0`.
2. In [log.capnp](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/cereal/log.capnp), rename the matching union member `customReserved11 @137 :Custom.CustomReserved11;` to `myThingSP @137 :Custom.MyThingSP;`. The `@137` and the fact that it points into `Custom` both stay.
3. Register `"myThingSP"` in [services.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/cereal/services.py).
4. Rebuild (`scons`) so `gen/` and `services.h` regenerate. Never hand-edit or commit either.

Worked example, real struct: `CarStateSP @0xb86e6369214c01c8` today holds only `speedLimit @0 :Float32;`. Adding a field means appending `speedLimitOffset @1 :Float32;` inside it. Appending is safe; renumbering `speedLimit` off `@0` is not.

CI gate: [.github/workflows/cereal_validation.yaml](file:///Users/cyonsun/Documents/Code/sunnypilot/.github/workflows/cereal_validation.yaml) diffs the schema against upstream openpilot. Touching a non-reserved struct fails the PR.

## SERVICES

`_services` maps name -> `(should_log, frequency, decimation, queue_size)`, expanded into `Service` objects in `SERVICE_LIST`. SP entries sit under the `# sunnypilot` comment block.

- `should_log`: goes into rlog at all. `False` (e.g. `modelManagerSP`, `rawAudioData`) means it's invisible to replay and to bug reports.
- `frequency`: SubMaster's expected rate. It drives `sm.alive`/`sm.freq_ok`; declaring 100. for a 20 Hz publisher makes consumers mark the socket not-alive and can trip onroad alerts.
- `decimation`: keep-1-in-N for qlog. `None` = never in qlog (`modelV2`, `radarTracks`). Too small a value bloats every uploaded segment; `can` uses 2053 to land ~3 msgs per segment.
- `queue_size`: msgq segment bytes, read by `pub_sock`/`sub_sock`. Undersizing a big message (video, model output) drops or truncates packets at runtime, not at build time. Use `QueueSize.BIG` for anything frame- or tensor-shaped.

## MESSAGING API

`new_message(service, size=None)` builds an `Event` with `logMonoTime` from `time.monotonic()` and `valid=False`; publish via `PubMaster.send`. `SubMaster` polls a list of services and exposes `sm[name]`, `sm.updated`, `sm.alive`, `sm.valid`. Transport is msgq shared memory on-device; `messaging/bridge` proxies to ZMQ for PC/replay. `log_from_bytes` uses `NO_TRAVERSAL_LIMIT` so large model messages don't blow capnp's traversal budget.

Downstream of a schema change: old route logs decode renamed fields under the old name only if the ID matched; `tools/replay` and `selfdrive/test/process_replay` reference logs are recorded against a fixed schema, so shifting field IDs makes reference comparison fail with confusing diffs rather than a clean error.

## ANTI-PATTERNS (THIS DIR)

- Adding a brand-new struct/field to `log.capnp` for a fork feature. Claim a reserved slot instead; otherwise the next upstream rebase collides.
- Committing `gen/` or `services.h`. Both are SCons outputs.
- Deleting a struct instead of moving it to [deprecated.capnp](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/cereal/deprecated.capnp).
- Adding a service to `services.py` but forgetting the union member, or vice versa. `new_message` then raises at runtime on a name capnp doesn't know.
- Reusing a reserved slot that's already renamed elsewhere on another branch. Grep `custom.capnp` for the highest claimed index first.
- Renaming an SP struct after it has shipped. Names are what Python/replay look up, even though the `@0x` id is what capnp keys on.

## NOTES

- `messaging/tests/validate_sp_cereal_upstream.py` is the local equivalent of the CI compat check; run it before proposing any schema edit.
- `customReservedRawData0` is registered as a service in `services.py` with frequency 0. It exists as a scratch channel; don't repurpose it silently.
- `MADS`, `IntelligentCruiseButtonManagement`, `LeadData` in `custom.capnp` are unversioned helper structs (no `@0x` of their own) nested-use only. They're safe to extend because nothing in `Event` points at them directly.
