# Acceleration EQ

User-tunable longitudinal acceleration. The driver edits EQ-style **speed → max
acceleration** curves, grouped into named **profiles**, in the dashy web UI; the
longitudinal planner reads the active profile and uses its curve as the accel
ceiling. A companion **logger** records the driver's own acceleration (when they
control the throttle) so the UI can later show "where you actually accelerate".

The dashy web UI lives in a **separate repo**; this doc covers the
dragonpilot/planner side (the contract, the planner reader, the logger) and
summarizes the dashy side it integrates with.

---

## Architecture

```
┌─ dashy web UI (separate repo) ─┐  GET/POST   ┌─ serverd ──────────┐
│ EQ editor · profiles · the     │ ──────────► │ params REST API +  │
│ personality→profile links      │  /api/...    │ /api/accel_eq/config│
└────────────────────────────────┘             └─────────┬──────────┘
                                                          │ Params
                              dp_lon_accel_profiles (JSON param)
                                                          │
            ┌─ longitudinal_planner.py ────────────────────▼───────────────┐
            │ AccelEq (accel_eq.py): read+cache JSON (mtime-gated), resolve  │
            │   the active profile by personality/active → max_accel(v)       │
            │ AccelLogger (accel_logger.py): log clean human-accel samples    │
            │   → /data/media/0/realdata/accel_log.csv                        │
            └─────────────────────────────────────────────────────────────────┘
```

Two stores, opposite directions:

| Store | Holds | Written by | Read by |
|---|---|---|---|
| `dp_lon_accel_profiles` (JSON param) | the whole EQ doc — profiles + curves, the manual `active` selection, the personality links | dashy | planner |
| `/data/media/0/realdata/accel_log.csv` | the driver's natural-acceleration samples (`vEgo,aEgo`) | **planner** (AccelLogger) | dashy overlay (future) |

The param is declared in `dragonpilot/settings/min-feat.lon.accel-eq.py`
(generated into `common/params_keys.h` at build). The CSV is telemetry, not
config, so it lives on the drive-log partition, not in the params store.

---

## Data contract — `dp_lon_accel_profiles`

The authoritative shape is what dashy's `serializeDoc` writes and the planner
reads. Example:

```json
{
  "active": "Sport",
  "use_personality": false,
  "personality_map": { "0": "Sport", "1": "Stock", "2": "Eco" },
  "profiles": [
    { "name": "Stock", "max": {"bp": [0, 10, 25, 40], "v": [1.6, 1.2, 0.8, 0.6]} },
    { "name": "Eco", "source": "Stock", "max": {"bp": [0, 12, 30, 40], "v": [1.0, 0.8, 0.6, 0.5]} }
  ]
}
```

- **`profiles`** — ordered list. Each has a non-empty **unique** `name` and a
  `max` curve `{bp:[m/s…], v:[m/s²…]}`. Speeds (`bp`) are stored in **m/s**
  regardless of the UI display unit. A missing/invalid `max` → that profile uses
  stock.
- **`active`** — the manually selected profile name (used when `use_personality`
  is off). There is **no separate `active` param** — it lives in this doc.
- **`use_personality`** + **`personality_map`** — the personality link (below).
- **`source`** (optional) — UI lineage only (the duplicate-from profile, drawn
  as the grey reference line). The planner ignores it and any other unknown key.

> **"Stock"** is a UI-protected baseline (not renamable/deletable, read-only in
> the editor). The planner treats it as a **live mirror of the injected stock
> table** — it ignores any stored curve named "Stock", so a planner stock change
> always wins.

There is **no `version` field and no turn-limit curve**: schema changes are
handled by versioning the release (or, if ever incompatible, the param key); the
turn-accel limit is the planner's stock `_A_TOTAL_MAX_*` and is not tunable.

---

## Profile selection

Resolved on init, whenever the param mtime changes, and whenever the personality
changes. The rule:

```
read/cache the JSON doc
  doc invalid / empty / missing            → STOCK   (regardless of personality)
  doc valid:
    use_personality == true                → personality_map[personality]
    use_personality == false               → active
    → resolve that name to a profile (exact match) and validate its curve
       matched + valid                      → that profile's curve
       unmapped / unset / no match / Stock / invalid curve → STOCK
```

**Stock is the single universal fallback.** No "first profile" fallback, and
when `use_personality` is on an unmapped personality falls to Stock (not to the
manual `active`).

| `use_personality` | situation | result |
|---|---|---|
| true  | personality mapped → real profile, valid curve | that profile |
| true  | personality unmapped | **Stock** |
| false | `active` → real profile, valid curve | that profile |
| false | `active` unset/empty | **Stock** |
| either | name points at a missing profile / is "Stock" / curve invalid | **Stock** |
| either | doc missing / empty / unparseable / not a usable dict | **Stock** |

### Personality link

For each openpilot personality the driver links a profile, stored in
`personality_map` keyed by the `LongitudinalPersonality` enum int — **`"0"`
aggressive, `"1"` standard, `"2"` relaxed**. With `use_personality` on, the
existing **personality button** selects the profile (no new onroad control).

The planner reads the live personality from `selfdriveState.personality.raw`
(the int) — the same source the MPC uses — not from the param.

> **Coupling, by design:** `LongitudinalPersonality` also drives openpilot's
> follow distance, so a personality link makes the button a single "aggression"
> dial (accel feel + following together). Turn the link off to set them
> independently (manual `active`).

---

## Planner: `AccelEq` (`dragonpilot/selfdrive/controls/lib/accel_eq.py`)

Instantiated in `LongitudinalPlanner` and pure-observation safe — any failure
falls back to stock and never raises into planning.

- **Stock is injected**, not hardcoded: the planner owns the canonical
  `A_CRUISE_MAX_*` table and passes it in (`AccelEq(A_CRUISE_MAX_BP,
  A_CRUISE_MAX_VALS)`). This keeps a single source of truth and lets `accel_eq`
  stay a leaf module (it never imports the planner — that would be circular).
- **Read is mtime-gated; the parsed doc is cached.** `maybe_refresh(personality)`
  `stat()`s the param each frame; only an **mtime change** triggers a re-read
  (`_reload_doc` → `Params.get`). A **personality change** just re-resolves the
  cached doc (`_resolve`) — zero I/O.
- **`max_accel(v_ego)`** = `np.interp` over the active curve, feeding the
  planner's accel clip. The default personality is a `-1` sentinel so the first
  real `maybe_refresh` always resolves.

`limit_accel_in_turns` is unchanged stock (uses `_A_TOTAL_MAX_*`).

### Validation is a safety boundary — `_validate_curve`

The param is externally writable (hand-edit, script, an older/buggy dashy), so
the planner never trusts it. `_validate_curve` re-sorts and bounds every curve
before it can shape the accel ceiling:

- shape: dict with equal-length `bp`/`v` lists, `MIN_PTS(2) ≤ n ≤ MAX_PTS(12)`,
  all finite numbers;
- **sort** pairs by speed (required — `np.interp` needs increasing `bp`);
- clamp speed to `[0, SPEED_CEIL(60)]`; reject if any adjacent gap `< MIN_GAP(0.5)`;
- **clamp value to `[0, MAX_ACCEL_CEIL]`** (`= ACCEL_MAX`, 2.0 m/s²) — the actual
  accel cap.

Anything that fails → that curve is unusable → stock. dashy mirrors these exact
rules client-side (UX) so the editor can't author a curve the planner rejects;
the planner's copy is the guarantee.

---

## Logger: `AccelLogger` (`dragonpilot/selfdrive/controls/lib/accel_logger.py`)

Logs the driver's **natural** acceleration so the data reflects *their*
preference, not openpilot's. Only "clean free human-acceleration" samples are
kept — `_should_log` requires **all** of:

| condition | signal |
|---|---|
| op long not active (human owns throttle) | `controlsState.longControlState == off` |
| accelerating on the gas | `gasPressed and aEgo > 0` |
| not braking | `not brakePressed` |
| no blinker (not turning/lane-changing) | `not (leftBlinker or rightBlinker)` |
| in Drive | `gearShifter == drive` |
| moving (not creeping/stopped) | `not standstill and vEgo > 1.0` |
| no near lead | no lead, or `dRel / max(vEgo, 0.1) > 2.0 s` |
| straight (not in a curve) | lateral accel `< 1.0 m/s²` |

Behavior: buffer matching `(vEgo, aEgo)` in RAM and **append to the CSV once a
minute** (`FLUSH_DT`, frame-counted) — one write/min spares the flash; up to
~1 min of samples is lost on a hard shutdown (negligible for an aggregate).
Fully exception-isolated; on a write failure it drops the buffered rows and
no-ops (e.g. path not writable in dev). The clean-sample gate makes growth slow,
so there is no size cap. CSV columns: `vEgo,aEgo` (m/s, m/s²).

---

## Constants — single source of truth

`accel_eq.py` owns the contract constants (`SPEED_CEIL`, `MIN_GAP`, `MIN_PTS`,
`MAX_PTS`, `MAX_ACCEL_CEIL`). serverd serves them at `GET /api/accel_eq/config`
and the dashy model applies them over its built-in fallback defaults at load, so
the editor's limits can't drift from the planner. (`MAX_PTS` especially must
match: a curve above the planner cap would be silently rejected → stock.)

---

## Persistence round-trip

dashy serializes the doc to a **JSON string**; the planner reads a parsed
**dict**. serverd bridges them:

1. dashy `POST /api/settings/params/dp_lon_accel_profiles` with the JSON string.
2. serverd `_save_param` detects the JSON-typed param and `json.loads`-es the
   string, then `Params.put(key, dict)` (the `(dict, JSON)` caster stores it).
   Malformed JSON → **400**, not 500.
3. planner `Params.get(...)` → parsed dict → `AccelEq._reload_doc` caches it.

`dp_lon_accel_profiles` is allowlisted in serverd's `_param_allowed`.

---

## Dashy side (separate repo)

The web UI implements: the canvas **EQ editor** (drag points, add/remove,
numeric entry, reset, undo/redo, a live "you are here" speed marker), **profile
management** (create/duplicate/rename/delete, quick-switch), the
**personality→profile pickers**, and a client-side **mirror of
`_validate_curve`** so the editor enforces the planner's limits. It talks to
serverd's params REST API and `/api/accel_eq/config`. The display unit follows
`IsMetric`; storage is always m/s.

---

## Files (this repo)

| File | Role |
|---|---|
| `dragonpilot/selfdrive/controls/lib/accel_eq.py` | `AccelEq` — profile reader/resolver |
| `dragonpilot/selfdrive/controls/lib/accel_logger.py` | `AccelLogger` — accel CSV logger |
| `dragonpilot/selfdrive/controls/lib/tests/test_accel_eq.py` | AccelEq tests |
| `dragonpilot/selfdrive/controls/lib/tests/test_accel_logger.py` | AccelLogger tests |
| `dragonpilot/settings/min-feat.lon.accel-eq.py` | declares `dp_lon_accel_profiles` |
| `selfdrive/controls/lib/longitudinal_planner.py` | owns `A_CRUISE_MAX_*`, wires in `AccelEq` + `AccelLogger` |

Run tests: `uv run python -m pytest dragonpilot/selfdrive/controls/lib/tests/ -q`

---

## Notes / future

- **Habit overlay** in dashy — read `accel_log.csv` (server-side aggregate to an
  85th-percentile band) and draw it behind the EQ curve. Needs no new param.
- The **turn-limit channel** is intentionally not tunable (dropped from the UI
  and the planner; turn limit stays stock).
- dashy follow-ups to keep in sync with this side: trim serverd's
  `ACCEL_EQ_CONFIG` to the constants `accel_eq` still exposes, and mirror the
  Stock-fallback selection rule in the dashy model.
