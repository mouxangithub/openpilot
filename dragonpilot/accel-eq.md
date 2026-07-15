# Acceleration EQ (最高加速等化器)

User-tunable longitudinal **max** acceleration. The driver edits EQ-style **speed → max
acceleration** curves, grouped into named **profiles**, in the dashy web UI; the
longitudinal planner reads the active profile and uses its curve as the accel
ceiling. A companion **logger** records the driver's own acceleration (when they
control the throttle) so the UI can overlay "where you actually accelerate" as a
**habit cloud** behind the curve.

The name is a UI metaphor: the editor is a graphic-equalizer-style curve (draggable
breakpoints along a speed axis). The quantity it shapes is the **maximum** acceleration
allowed at each speed — hence *最高加速* (max acceleration) *等化器* (equalizer) in the
localized label.

The dashy web UI lives in a **separate repo** (`~/dashy`). This doc is the full
technical reference for the whole feature: the data contract, the planner reader,
the logger, the dashy frontend (model / editor / page), and the serverd endpoints.

---

## Architecture

```
┌─ dashy web UI (separate repo) ──────────────┐
│  accel_eq_page.js   (controller: profiles,   │  GET params, IsMetric, LongitudinalPersonality
│                      personality, IO)        │  POST params/dp_lon_accel_profiles
│  accel_eq_editor.js (canvas curve widget)    │  GET /api/accel_eq/config
│  accel_eq_model.js  (pure logic, planner     │  GET /api/accel_eq/habit[?meta=1]
│                      rule mirror)            │ ───────────────┐
└──────────────────────────────────────────────┘                ▼
                                                   ┌─ serverd (dashy_server) ─────────────┐
                                                   │ handlers.py  params REST + accel_eq  │
                                                   │ config.py    ACCEL_EQ_CONFIG (mirror │
                                                   │              of accel_eq.py consts)  │
                                                   │ habit.py     accel_log.csv → cloud   │
                                                   └───────┬───────────────────┬──────────┘
                                             Params        │                   │ reads
                                     dp_lon_accel_profiles  ▼                   ▼ /data/media/0/realdata/accel_log.csv
            ┌─ longitudinal_planner.py ───────────────────────────────────────────────┐
            │ AccelEq (accel_eq.py): read+cache JSON (mtime-gated), resolve the active │
            │   profile by personality/active → max_accel(v) → the accel clip ceiling  │
            │ AccelLogger (accel_logger.py): log clean human-accel samples →           │
            │   /data/media/0/realdata/accel_log.csv                                   │
            └──────────────────────────────────────────────────────────────────────────┘
```

**Two stores, opposite directions:**

| Store | Holds | Written by | Read by |
|---|---|---|---|
| `dp_lon_accel_profiles` (JSON param) | the whole EQ doc — profiles + curves, the manual `active` selection, the personality links | dashy | planner (+ serverd config passthrough is separate) |
| `/data/media/0/realdata/accel_log.csv` | the driver's natural-acceleration samples (`vEgo,aEgo`) | **planner** (AccelLogger) | dashy habit-cloud overlay (via serverd `habit.py`) |

The param is declared in `dragonpilot/settings/min-feat.lon.accel-eq.py` (generated
into `common/params_keys.h` at build). The CSV is telemetry, not config, so it lives
on the drive-log partition, not the params store.

**No restart needed.** `dp_lon_accel_profiles` is *not* a `needs_restart` param — the
planner hot-reloads it (mtime-gated, below), so edits take effect within a frame
without cycling openpilot.

---

## Data contract — `dp_lon_accel_profiles`

The authoritative shape is what dashy's `serializeDoc` writes and the planner reads.
A real on-device example:

```json
{
  "active": "version 2",
  "use_personality": false,
  "personality_map": { "0": "User Accel Habit", "1": "version 1", "2": "version 2" },
  "profiles": [
    { "name": "Stock" },
    { "name": "version 1", "source": "Stock",
      "max": { "bp": [0, 6.36, 11.57, 19.55, 24.83, 34.51, 40], "v": [1.9, 1.85, 1.55, 1.55, 1.1, 1.6, 0.6] } },
    { "name": "version 2", "source": "version 1",
      "max": { "bp": [0, 6.36, 11.57, 19.55, 27.05, 40], "v": [1.9, 1.85, 1.55, 1.55, 1.55, 0.6] } }
  ]
}
```

- **`profiles`** — ordered list. Each has a non-empty **unique** `name` and (except
  Stock) a `max` curve `{bp:[m/s…], v:[m/s²…]}`. Speeds (`bp`) are stored in **m/s**
  regardless of the UI display unit. A missing/invalid `max` → that profile uses stock.
- **`active`** — the manually selected profile name (used when `use_personality` is
  off). There is **no separate `active` param** — it lives in this doc, so planner and
  UI read one source.
- **`use_personality`** + **`personality_map`** — the personality link (below).
- **`source`** (optional) — UI lineage only (the profile this one was duplicated from,
  drawn as the grey reference line). The planner ignores it and any other unknown key.

> **"Stock"** is a UI-protected baseline (not renamable/deletable, read-only in the
> editor). It carries **no stored curve** — both the planner and the UI treat it as a
> **live mirror of the injected stock table**, so a later planner stock change always
> reaches users. `parseDoc`/`serializeDoc` strip any `max` on Stock.

There is **no `version` field and no turn-limit curve**: schema changes are handled by
versioning the release (or, if ever incompatible, the param key); the turn-accel limit
is the planner's stock `_A_TOTAL_MAX_*` and is not tunable. A vestigial `turn` curve
key from an earlier design is dropped on parse.

---

## Profile selection

Resolved on init, whenever the param mtime changes, and whenever the personality
changes. The rule (identical in the planner's `_resolve` and the model's
`resolveEffectiveName`):

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

**Stock is the single universal fallback.** No "first profile" fallback, and when
`use_personality` is on an unmapped personality falls to Stock (not to manual `active`).

| `use_personality` | situation | result |
|---|---|---|
| true  | personality mapped → real profile, valid curve | that profile |
| true  | personality unmapped | **Stock** |
| false | `active` → real profile, valid curve | that profile |
| false | `active` unset/empty | **Stock** |
| either | name points at a missing profile / is "Stock" / curve invalid | **Stock** |
| either | doc missing / empty / unparseable / not a usable dict | **Stock** |

### Personality link

For each openpilot personality the driver links a profile, stored in `personality_map`
keyed by the `LongitudinalPersonality` enum int — **`"0"` aggressive, `"1"` standard,
`"2"` relaxed**. With `use_personality` on, the existing **personality button** selects
the profile (no new onroad control), and the dashy profile rail + curve editor hide (the
button owns the active profile).

The planner reads the live personality from `selfdriveState.personality.raw` (the int) —
the same source the MPC uses — not from the param. dashy reads it from the
`LongitudinalPersonality` INT param (cached + low-frequency poll), since it isn't in the
`dashyState` websocket feed.

> **Coupling, by design:** `LongitudinalPersonality` also drives openpilot's follow
> distance, so a personality link makes the button a single "aggression" dial (accel
> feel + following together). Turn the link off to set them independently (manual `active`).

---

## Planner: `AccelEq` (`dragonpilot/selfdrive/controls/lib/accel_eq.py`)

Instantiated in `LongitudinalPlanner`, pure-observation safe — any failure falls back
to stock and never raises into planning.

- **Stock is injected**, not hardcoded: the planner owns the canonical `A_CRUISE_MAX_*`
  table and passes it in (`AccelEq(A_CRUISE_MAX_BP, A_CRUISE_MAX_VALS)`). Single source
  of truth, and it keeps `accel_eq` a leaf module (it never imports the planner — which
  imports `AccelEq` → would be circular).
- **Read is mtime-gated; the parsed doc is cached.** `maybe_refresh(personality)`
  `stat()`s the param each frame; only an **mtime change** triggers a re-read
  (`_reload_doc` → `Params.get`, which returns a parsed dict for a JSON param). A
  **personality change** (button press — doesn't touch the param) just re-resolves the
  cached doc (`_resolve`) — zero I/O.
- **`max_accel(v_ego)`** = `np.interp(v_ego, bp, v)` over the resolved curve, feeding the
  planner's `accel_clip[1]` ceiling. The default personality is a `-1` sentinel so the
  first real `maybe_refresh(0|1|2)` always resolves.

`limit_accel_in_turns` is unchanged stock (uses `_A_TOTAL_MAX_*`); the EQ shapes only the
straight-line accel ceiling.

### Validation is a safety boundary — `_validate_curve`

The param is externally writable (hand-edit, script, an older/buggy dashy), so the
planner never trusts it. `_validate_curve` re-sorts and bounds every curve before it can
shape the accel ceiling:

- **shape:** dict with equal-length `bp`/`v` lists, `MIN_PTS(2) ≤ n ≤ MAX_PTS(12)`, all
  finite numbers;
- **sort** pairs by speed (required — `np.interp` needs increasing `bp`);
- clamp speed to `[0, SPEED_CEIL(60)]`; **reject** if any adjacent gap `< MIN_GAP(0.5)`;
- **clamp value to `[0, MAX_ACCEL_CEIL]`** (`= ACCEL_MAX`, 2.0 m/s²) — the actual cap.

Anything that fails → that curve is unusable → stock. dashy mirrors these exact rules
client-side (`accel_eq_model.js validateCurve`) so the editor can't author a curve the
planner rejects; the planner's copy is the guarantee.

---

## Logger: `AccelLogger` (`dragonpilot/selfdrive/controls/lib/accel_logger.py`)

Logs the driver's **natural** acceleration so the data reflects *their* preference, not
openpilot's. Only "clean free human-acceleration" samples are kept — `_should_log`
requires **all** of:

| condition | signal |
|---|---|
| op long not active (human owns throttle) | `controlsState.longControlState == off` |
| accelerating on the gas | `gasPressed and aEgo > 0` |
| not braking | `not brakePressed` |
| no blinker (not turning/lane-changing) | `not (leftBlinker or rightBlinker)` |
| in Drive | `gearShifter == drive` |
| moving (not creeping/stopped) | `not standstill and vEgo > 1.0` |
| no near lead | no lead, or `dRel / max(vEgo, 0.1) > TTC_MIN s` |
| straight (not in a curve) | lateral accel `< 1.0 m/s²` |

> **`TTC_MIN`** (min lead time-to-contact to still count as "free") is `2.0 s` on the
> feature branch. Some integration branches (e.g. `testing`) currently carry `0.5 s` —
> a known drift; `2.0` is the intended value (only free-flow accel should train the cloud).

Gated on `CP.openpilotLongitudinalControl` — the logger is inert on stock-long cars,
where the EQ can't apply anyway (no point accumulating unusable data / flash writes).

Behavior: buffer matching `(vEgo, aEgo)` in RAM and **append to the CSV once a minute**
(`FLUSH_DT`, frame-counted) — one write/min spares the flash; up to ~1 min of samples is
lost on a hard shutdown (negligible for an aggregate). Fully exception-isolated; on a
write failure it drops the buffered rows and no-ops. The clean-sample gate makes growth
slow, so there is no size cap. CSV columns: `vEgo,aEgo` (m/s, m/s²).

---

## Dashy frontend (`~/dashy/web/src/js/pages/settings/`)

Three files, split by responsibility. Storage is always **m/s / m/s²**; display units are
a render concern only.

### `accel_eq_model.js` — pure logic (no DOM, no network)

The single home for every numeric rule; unit-tested (`web/test/accel_eq_model.test.js`).
The editor and page delegate all decisions here.

- **Contract constants** mirror the planner: `SPEED_CEIL 60`, `MIN_GAP 0.5`, `MIN_PTS 2`,
  `MAX_PTS 12`, `MAX_ACCEL_CEIL 2.0`, `STOCK_NAME 'Stock'`, plus `STOCK_MAX_BP/V` fallback.
  `applyConfig(cfg)` overrides these from serverd's `/api/accel_eq/config` (the planner is
  the source of truth); only finite numbers / well-formed curves override, so a missing or
  malformed config can never make the model worse than its built-in baseline.
- **`validateCurve(curve, ceil)`** — a faithful mirror of the planner's `_validate_curve`
  (shape / count / finite / sort / min-gap / clamp). Returns a normalized `{bp,v}` or `null`.
- **Unit conversion** — `MS_TO_MPH 2.237`, `MS_TO_KMH 3.6`; `speedToDisplay/displayToSpeed`
  for `kmh|mph|ms`. **`interpValue`** mirrors `np.interp` (clamp to endpoints).
- **Point ops** — `clampDragged` (speed stays between neighbors keeping `MIN_GAP`, value in
  `[0,ceil]`), `canAddPoint`, `addPointAtLargestGap`, `addPointAtSpeed` (interpolated value),
  `removePoint` (floored at `MIN_PTS`), `curveToPoints`/`pointsToCurve`.
- **Doc ops** — `seedDoc` (Stock-only, personality off), `parseDoc` (dedupe names, drop the
  vestigial `turn` key, strip Stock's `max`, validate `active`), `serializeDoc` (Stock never
  stores a curve, keep `source` lineage, run `validateCurve` on each `max` else drop the key
  → planner-valid fallback), `uniqueName`, `ensurePersonalityDefaults`, `resolveEffectiveName`
  (planner mirror), `addProfile` (seed-from lineage → `"Eco" → "Eco 1"`), `renameProfile`
  (protects Stock; keeps `source`/`personality_map`/`active` in step), `deleteProfile`
  (protects Stock; re-seeds if emptied; drops dangling `source` refs and map entries).

### `accel_eq_editor.js` — the canvas curve widget

Touch-first graphic-EQ editor. Deliberate "tuned gauge at night" palette (warm
sodium-amber signal on cool blue-graphite — not the generic green-on-black). All numeric
rules come from the model; the widget owns interaction + rendering only.

- **Axes:** x = speed to `AXIS_MAX_MS 40` (144 km/h) in the active display unit; y =
  max-accel `[0, ceil]`. (`SPEED_CEIL 60` still governs *storage*; drags clamp to 40.)
- **Interaction model (touch-first):**
  - **Grab has priority** and ignores plot bounds (`GRAB_RADIUS_PX 30`) so edge points
    (speed 0, value at 0/ceil) stay grabbable with a finger.
  - **Add only on drag from the line** (`LINE_GRAB_PX 20`, `ADD_DRAG_THRESHOLD_PX 6`): a
    press on the curve arms a ghost that commits on release; flashes "No room here" / "Max
    12 points" when a gap/cap blocks it.
  - **Drag** clamps between neighbors and quantizes the value to the `0.05 m/s²` grid; a
    crosshair with rail labels shows exact speed/value without the finger in the way.
  - **Remove by dragging outside the plot** (`KILL_MARGIN_PX 12`, needs `> MIN_PTS`) — an
    unambiguous "throw away" that can't be confused with clamping to 0/ceil; also a Remove
    button and tap-empty-space-to-select for the `−/+` steppers.
  - **Contextual stepper** (appears on selection): per-axis `−/+` with a cycling step-size
    chip — speed `1/5` (display unit), value `0.05/0.1/0.5 m/s²`.
  - **Undo/redo** over committed edits (snapshot stack, capped at 50).
- **Rendering layers (bottom→top):** graticule (round display-unit ticks) → thrust-band
  fill under the curve (amber wash, dense near the top) → grey dashed **reference line**
  (the duplicate `source`, or Stock, named in a legend) → **habit cloud** → the signal
  curve (amber gradient + soft glow) → points (selected = white core + amber ring;
  kill-armed = red) → crosshair.
- **API:** `setPoints/getPoints`, `setCeil`, `setStockGhost`, `setHabit({points, envelope})`,
  `setUnit`, `destroy`.

### `accel_eq_page.js` — the controller

Orchestrates three cards and all param IO (debounced). Pure display + IO; all driving
logic is on-device.

- **Personality binding is the top-level mode switch** (first card). When on, it owns the
  active profile → the profile rail and curve editor hide, and the personality button
  picks the profile. When off, the selected rail chip is both "what the car uses" and "what
  you edit."
- **Profiles rail** — quick-switch chips (effective-active highlighted) + a **Duplicate**
  picker (copies a profile, recording `source` lineage).
- **Editor card** — hosts `AccelEqEditor` for the profile being edited (Stock is read-only
  → "duplicate to change"); the grey reference follows the edited profile's `source`.
- **Persistence** — a `400 ms` debounced `saveParam(dp_lon_accel_profiles, serializeDoc)`;
  the `active` selection lives *in the doc* (no separate param); a pending save is flushed
  on `destroy` so a last-second edit isn't lost.
- **Units** follow the device `IsMetric` param (no in-app toggle — a breakpoint can't be a
  round number in both km/h and mph, and storage is m/s, so switching would silently
  re-round the curve; `IsMetric` default → mph).
- **Config** — `GET /api/accel_eq/config` → `model.applyConfig` *before* first render, so
  the editor's limits/stock match the planner; 404 (standalone dashy) → built-in defaults.
- **Habit overlay** — `loadHabitMeta` (`?meta=1`, cheap `{count, bands}` probe) gates the
  toggle: offered only when `bands ≥ MIN_BANDS 15` (~7.5 m/s of coverage). Off by default,
  persisted in `localStorage`; the full dataset (`{points, envelope}`) is fetched lazily on
  first enable.

---

## serverd endpoints (`~/dashy/dashy_server/`)

- **`config.py` → `ACCEL_EQ_CONFIG`** — built at import by reading the planner's
  `dragonpilot.selfdrive.controls.lib.accel_eq` constants (single source of truth): the
  scalar contract `{max_pts, min_pts, min_gap, speed_ceil, max_accel_ceil}`. If the import
  fails (standalone/dev dashy without the fork) → `None`, and the config endpoint returns a
  not-available response so the web model keeps its own fallback defaults. (`turn`, the
  schema `version`, and `stock` were dropped from this config — Stock is a live mirror, not
  a served constant.)
- **`handlers.py`**
  - `GET /api/accel_eq/config` → `get_accel_eq_config_api` → `ACCEL_EQ_CONFIG`.
  - `GET /api/accel_eq/habit` → `get_accel_eq_habit_api` → the habit cloud; `?meta=1`
    returns the cheap `{count, bands}` probe (no dataset) that gates the UI toggle.
  - Param IO (`/api/settings/params/...`) — see Persistence round-trip.
- **`habit.py`** — turns `accel_log.csv` into the overlay: `_habit_grid` bins samples by
  speed (`step 0.5 m/s`, half-width `1.5`, `min_w 60` per bin), `_habit_points` down-samples
  to a `cap 2000`-point scatter (uniform stride), and `_habit_band`/`_habit_bands` compute
  percentile lines (p10/p50/p90 → `envelope.{lower,mid,upper}`, rendered as "usual / brisk /
  hardest"). So the editor can show both the raw scatter and a smoothed envelope of how you
  actually accelerate, to shape the curve against.

---

## Constants — single source of truth

`accel_eq.py` owns the contract constants (`SPEED_CEIL`, `MIN_GAP`, `MIN_PTS`, `MAX_PTS`,
`MAX_ACCEL_CEIL`). serverd `config.py` reflects them at `GET /api/accel_eq/config`, and the
dashy model applies them over its built-in fallback at load, so the editor's limits can't
drift from the planner. (`MAX_PTS` especially must match: a curve above the planner cap would
be silently rejected → stock.)

---

## Persistence round-trip

dashy serializes the doc to a **JSON string**; the planner reads a parsed **dict**. serverd
bridges them:

1. dashy `POST /api/settings/params/dp_lon_accel_profiles` with the JSON string.
2. serverd `_save_param` detects the JSON-typed param and `json.loads`-es the string, then
   `Params.put(key, dict)` (the `(dict, JSON)` caster stores it). Malformed JSON → **400**,
   not 500. `dp_lon_accel_profiles` is allowlisted in serverd's `_param_allowed`.
3. planner `Params.get(...)` → parsed dict; `AccelEq._reload_doc` picks it up on the next
   frame whose mtime changed, and re-resolves — no restart.

---

## Files

**This repo (planner side):**

| File | Role |
|---|---|
| `dragonpilot/selfdrive/controls/lib/accel_eq.py` | `AccelEq` — profile reader/resolver |
| `dragonpilot/selfdrive/controls/lib/accel_logger.py` | `AccelLogger` — accel CSV logger |
| `dragonpilot/selfdrive/controls/lib/tests/test_accel_eq.py` | AccelEq tests |
| `dragonpilot/selfdrive/controls/lib/tests/test_accel_logger.py` | AccelLogger tests |
| `dragonpilot/settings/min-feat.lon.accel-eq.py` | declares `dp_lon_accel_profiles` |
| `selfdrive/controls/lib/longitudinal_planner.py` | owns `A_CRUISE_MAX_*`, wires in `AccelEq` + `AccelLogger` |

Run tests: `uv run python -m pytest dragonpilot/selfdrive/controls/lib/tests/ -q`

**dashy repo (`~/dashy`):**

| File | Role |
|---|---|
| `web/src/js/pages/settings/accel_eq_model.js` | pure logic + planner-rule mirror |
| `web/src/js/pages/settings/accel_eq_editor.js` | canvas curve widget |
| `web/src/js/pages/settings/accel_eq_page.js` | page controller / param IO |
| `web/test/accel_eq_model.test.js` | model unit tests |
| `dashy_server/handlers.py` | `/api/accel_eq/{config,habit}` + param REST |
| `dashy_server/config.py` | `ACCEL_EQ_CONFIG` (mirror of accel_eq constants) |
| `dashy_server/habit.py` | `accel_log.csv` → scatter + percentile envelope |

---

## Notes

- **Turn-limit channel** is intentionally not tunable (dropped from the UI and the planner;
  turn limit stays the stock `_A_TOTAL_MAX_*`).
- **`TTC_MIN` drift:** align integration branches to `2.0 s` (see the Logger note).
- The habit cloud is **observational only** — it never feeds the planner; it just helps the
  driver shape a curve toward how they actually drive.
