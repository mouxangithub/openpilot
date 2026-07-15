# TSK Manager

## Background

comma.ai makes DIY ADAS devices — currently the comma threeX (C3X / tizi) and comma four (C4 / mici). Toyota added cryptographic SecOC signatures to CAN messages, blocking comma from writing to the bus.

Willem (ex-comma) found a way to pull the SecOC key from the EPS firmware on 2021–23 RAV4 Prime; the same hack works on 2021–23 Sienna Hybrid, and with modifications on Yaris. TSKM is Calvin's GUI around Willem's method. Background in `/Users/calvin/GitRepos/docs/README.md`.

Calvin's cars: 2023 Sienna Hybrid (C3X), 2023 Bolt EV 2LT (C4). Both devices validate against the Sienna.

## Architecture

TSK Manager is **merged into op 助手 (`ai.aid`)** on port **5090** (`/tsk/`, `/api/tsk/*`). The legacy standalone server on `11111` (`tsk.web.server`) is deprecated.

### Boot Flow

`launch_chffrplus.sh` on device boot:

1. Creates `/cache/tsk` and chowns it to comma — job output dirs must exist first.
2. Starts **`python3 -m ai.aid &`** *before* the manager, so TSK survives the pipeline's `pkill manager.py` during SecOC work.
3. Starts the openpilot manager.
4. UI: **`http://<device-ip>:5090`** (chat) and **`http://<device-ip>:5090/tsk/`** (SecOC).

`prefetch.py` / nested-wrapper install flows are no longer in the default boot path; fork switches use git. See `ai/docs/TSK_AND_AID.md`.

### File Layout

- `tsk/service.py` — shared state, job APIs, offroad alert loop (used by aid and tools).
- `ai/aid.py` + `ai/tsk_routes.py` — HTTP server on **5090**, mounts TSK static UI and `/api/tsk/*`.
- `tsk/lib/` — all TSK behavior (unchanged core):
  - `env.py` — paths, device detection: `is_agnos`, `CACHE_DIR` (`/cache` on device, `~/comma_data/cache` off), `DATAFLASH_DIR`, `DATAFLASH_PAYLOAD_PATH`, `CAN_MESSAGES_DIR`, `CAN_ORACLE_PATH`.
  - `extractor.py` — legacy single-step extraction (Willem). `hack()` uploads `payload.bin`, dumps RAM `0xFEBE6E34–0xFEBE6FF4`, parses KEY_4. `_connect_panda()` stashes the handle; `_close_panda()` releases it from the server's `finally`. pandad flashes the panda firmware on boot, so there's no flash call here.
  - `dump_dataflash.py` — DataFlash dump (the 2021+ path). `dump(progress_cb)` uploads `payload_dataflash_ff200000_ff208000.bin` and dumps `0xFF200000–0xFF208000` (32 KB), returning `{status, frames, bytes, total, dump_path, message}`. `_finalize()` (pure, off-device testable) classifies the outcome:
    - **complete** — full 32768 bytes; writes `dump_ff200000_ff208000.bin`.
    - **partial** — the key window `KNOWN_KEY_OFFSET` (0x6e14) is captured but not the full range; writes the `.partial` sidecar Find can use.
    - **key_missed** — the key window wasn't captured (one frame or nearly all of it); writes nothing, asks for a re-dump.

    `_finalize()` returns the three statuses above; the server's job thread sets `failed` on an unhandled exception. `is_agnos`-gated. Shares the UDS session preamble with `extractor.py` by deliberate duplication (distinct payload, range, and parser, kept independently testable).
  - `collect_can.py` — CAN oracle capture. `collect(progress_cb)` records sync (0x0F) + protected (0x2E4/0x131/0x344) frames on buses 0/2 in READY Mode until both targets are met (sync is the bottleneck; protected floods), capped at 60 s; writes `can_oracle.ndjson`; returns `{status, sync, protected, ...}` (complete | insufficient; the server sets `failed` on an unhandled exception). `count_oracle_frames()` tallies a persisted oracle, skipping malformed lines. `is_agnos`-gated.
  - `matcher.py` — key finder. `run()` reads the oracle + the dump (complete file, else the `.partial` sidecar, setting `dump_partial`) and calls `find_key()`: exhaustive stride-1 scan over every window, 5-sample sync union first pass, accept at ≥ `MATCH_FLOOR` (30) matches with ≥ 2 sync. Hand-rolled RFC-4493 AES-CMAC that computes the same 28-bit SecOC MAC as opendbc `secoc.py` (opendbc uses the pycryptodome `CMAC` library; the MAC values match, the code is a reimplementation). Pure computation; returns the key, does not install it.
  - `key_file_manager.py` — key read/write/delete, `format_key()`.
  - `payload.bin` — legacy extraction payload.
  - `payload_dataflash_ff200000_ff208000.bin` — DataFlash dump payload (SHA256 `d48988366b…a06e34`, verified before use; byte-identical to Willem's I-CAN-hack/secoc `while-loop` branch).
- `tsk/web/` — HTTP + static UI (legacy `server.py` on `11111` deprecated; production UI served by `ai.aid` at `/tsk/`).
  - `static/index.html` — phone-first main page (no fork install section).
  - `static/extractor.html` — legacy TSK Extractor page (dark terminal, auto-runs on load).
  - `static/can-collector.html` — CAN page; POSTs to start the real job, polls `/api/can-status`. Short-circuits a complete oracle, attaches to a running one, retries after insufficient/failed.
  - `static/dataflash-collector.html` — DataFlash page; same pattern against `/api/dataflash-status`.

`tsk/common`, `tsk/c3`, `tsk/c4` should not exist on `tskmloop`.

### Web Server

**Production:** `ai.aid` binds `0.0.0.0:5090`, serves TSK assets at `/tsk/` and API at `/api/tsk/*` via `ai/tsk_routes.py` + `tsk/service.py`.

Writes `http://<IP>:5090/tsk/` into `Offroad_NoFirmware` (Chinese prompt + `%1` = URL) via `offroad_alert_loop` — rewritten when the URL changes or the file is gone, since the manager wipes it on start.

**Legacy:** `python3 -m tsk.web.server` on `11111` — do not use on device; kept for reference only.

API endpoints (prefix **`/api/tsk/`** on aid):

- `/api/health` (GET) — server info, dry_run flag, detected addresses.
- `/api/status` (GET) — key install status via `get_key_status()`.
- `/api/extract` (POST) — legacy single-step extraction. Off-AGNOS dry run cycles 3 scenarios.
- `/api/uninstall` (POST) — removes the installed key via `KeyFileManager`.
- `/api/can-status` (GET) — `{ready, status, sync_count, protected_count, seconds, message}` from `can_state`. `ready == (status == "complete")`.
- `/api/can-collect` (POST) — starts the background collect job, returns immediately. 409 if a panda op is already running. Off-AGNOS: mock ramp.
- `/api/dataflash-status` (GET) — `{ready, status, frames, bytes, total, message, size}` from `df_state`. `partial` is a key-region-covered dump Find accepts; `key_missed` writes no file (re-dump).
- `/api/dataflash-dump` (POST) — starts the background dump job, returns immediately. 409 if a dump is in progress. Off-AGNOS: `dump()` raises `NotAGNOSError` and the job falls back to a mock ramp.
- `/api/match` (POST) — runs `matcher.run()`; on `found` installs the key via `KeyFileManager` and returns it with a screenshot message (modal title "Success!"), for a complete or partial recovery alike. Otherwise returns status + counts + debug fields (`windows_scanned`, `survivors`, best-candidate `address`, `dump_partial`) for the not-found modal. 500 with traceback on unhandled exception. 409 if a match is already running.
- `/api/clear-cache` (POST) — `clear_can()` deletes the CAN oracle file and `clear_dataflash()` deletes the dump + `.partial` (each also resets its in-memory state). 409 while a dump/collect runs. Does not touch the key.

CAN and DataFlash run as real background jobs: `can_state`/`can_lock` and `df_state`/`df_lock` hold live progress; threads run `collect()` / `dump()`, set `status="failed"` on any unhandled exception, and `start_*_job()` reject a concurrent start. A single `panda_lock` serializes extract/dump/collect over the one physical panda — held for the whole operation and released in the job's `finally`, which also calls `TSKExtractor._close_panda()`. `rehydrate_can_state()` and `rehydrate_dataflash_state()` run in `main()` so persisted CAN/dump data shows as done after a restart.

### Hard Rules

`tsk/web/server.py` is HTTP routing only. Do not add key paths, key validation, key read/write, device detection, extractor wrappers, or reboot file ops. If behavior exists in `tsk/lib`, call it; if it doesn't, add it to `tsk/lib` or ask first. Do not invent alternate key storage — use `KeyFileManager`.

### Storage

- Frozen code: `/data/openpilot/tsk`
- CAN oracle: `/cache/tsk/can-messages/can_oracle.ndjson`
- DataFlash dumps: `/cache/tsk/dataflash/` — `dump_ff200000_ff208000.bin` (exactly 32768 bytes; the matcher prefers it) or a `.partial` sidecar (key window captured, full range not)
- Prefetched repos: `/data/tsk-recommended`, `/data/tsk-alternate`

All of `/cache` survives reboot and clears on AGNOS update.

### UI State

`index.html` has two extraction sections:

**"2021, 2022, 2023 RAV4 Prime & Sienna"** — single TSK Extractor link (`extractor.html`), the legacy single-step RAM extraction. Kept as-is.

**"2021+"** — the three-step pipeline (CAN → DataFlash → Find), all real:

- **CAN row** — detail line `Sync N/50   Protected N/30`; links to `can-collector.html`.
- **DataFlash row** — dot green on complete, **yellow** (`prereq-dot warn`) on a key-region-covered `partial`, red otherwise. `setDfDetail()` shows gray `Dumping N/total` while running, orange `partial`, red `key_missed`; hidden when idle/complete/failed (a failure shows the red dot alone — the error already appeared on the dump page). Links to `dataflash-collector.html`.
- **Find Toyota Security Key** — disabled with "(need CAN)" / "(need DataFlash)" / "(need CAN & DataFlash)" until CAN is collected and a dump exists (complete **or** key-region `partial`). Running shows a darkened overlay + spinner ("Finding key…", `showFinding()`); `updateExtraction()` early-returns while `state.running` so the 1 s poll can't clobber the run. Success → "Success!" modal; complete-dump miss → debug block (best candidate address/matches, windows scanned, bytes) + the #toyota-security report line; partial miss → "Key not found in the partial DataFlash dump."
- **Clear extraction cache** — red when CAN or DataFlash data exists, gray otherwise; resets both via `/api/clear-cache`.
- **Uninstall key** — red when a key is installed, gray otherwise.

CAN targets: 50 sync, 30 protected — a **total** across 0x2E4/0x131/0x344, not gated per-address. Collection stops when both are met (cap 60 s); the progress bar tracks target completion, not elapsed time.

### Method & Design Notes

Durable rationale for why the pipeline is shaped this way:

- **Car-agnostic — no model gate.** Any car the owner picks may run. The verifier is the safety net: a wrong car either fails security access (EPS not in the Willem family) or nothing verifies. A wrong 16-byte window clears a 28-bit sync MAC at 2⁻²⁸; with ≥ 2 sync samples a false install is 2⁻⁵⁶ — no bad install is possible. The only car-specific constant is `KNOWN_KEY_OFFSET = 0x6e14`, used only to classify a partial as usable vs `key_missed`.
- **No candidate system.** Exhaustive stride-1 scan over every window (~32,753), one AES-CMAC each, sub-second — no entropy filtering, scoring, or caps. Survivors (expect 0–1) get full sync + protected verification. Acceptance is an absolute floor (`MATCH_FLOOR` 30, ≥ 2 sync), not a percentage: a wrong window reaching 30 is ~2⁻⁶⁶⁰.
- **Three failure modes, kept distinct.** (1) Security access denied → EPS not in the exploit family. (2) Dump completes, nothing verifies → exploit works but the key isn't in `0xFF200000–0xFF208000` for this EPS. (3) Verify passes → key extracted.
- **Key delivery.** `KeyFileManager` writes `/cache/params/SecOCKey` + Params `SecOCKey`; `card.py` reads both, gated on `CP.secOcRequired`, surviving the install `move`/reboot/AGNOS. Cars past their last-supported year need SunnyPilot with manual year selection (e.g. 2024 Sienna → pick 2023).
- **Cold dumps often come back `partial`/`key_missed`; the fix is priming, not waiting.** Running the TSK Extractor first (the extraction exploit, which ends in `bl_reset`) makes the next dump complete; time alone does not. The lost data is a fixed-size (124-byte), moving, single-burst gap during the 8192-frame flood — an RX/USB-side overflow, not a structural EPS window (mechanism unresolved). Production keeps the dump as-is; users who can't get the key are told to run the Extractor first (manual prime), since the behavior may be Sienna-specific and most Sienna partials still capture the key.
- **Extraction (RAM) vs dump (DataFlash).** The legacy extraction reads a firmware-specific RAM copy at `0xFEBE6E34` (per-car; fails the KEY_4 checksum on Yaris — "needs modifications"). The dump reads persistent DataFlash at `0xFF206E14`, whose layout is shared across these EPS variants — so it generalizes where the RAM extraction needs per-car addresses.
- **DataFlash size.** The dump window is 32 KB; total DataFlash size is unverified (no RH850 part number). Every key seen is inside the window (Sienna/Yaris `0x6e14`; a `0x6410` candidate on the 2024-Sienna profile). A wider-range payload is ready-if-needed, not needed yet.

## Development

### Laptop (macOS)

Direct server test (TSK + op 助手):

```
python3 -m ai.aid
# http://127.0.0.1:5090/  and  http://127.0.0.1:5090/tsk/
```

Off-AGNOS: TSK `dry_run`; `/api/tsk/*` returns mock progress where panda is unavailable. Legacy `python3 -m tsk.web.server` (`:11111`) is deprecated.

## Reference

- **Why rebase on nightly-dev** — AGNOS updates are ~1 GB / ~10 min; rebasing keeps TSKM current so users don't hit one mid-extraction. The web-app direction also cuts dependence on comma's brittle RayLib libs.
- **comma release branches** — C3X `release-tizi`, C4 `release-mici`, C3 `release-tici` (discontinued), `release3` (legacy).
- **Versioned TSKM branches** — each release tagged as a branch (e.g. `tskm-0.10.4`); frozen fallbacks, but comma changes can break them.
- **SSH** — tmux detach on comma devices: backtick, then `d`.

---

## Journal

When the user says "update the journal", add a dated entry summarizing the session.

- **2025-11** — TSKM v0.10.4 shipped on the RayLib `tskm` branch.
- **2026-04** — Fixed `CAN packet version mismatch` (stale panda firmware, killed before pandad could flash) with `flash_panda()` GPIO/DFU recovery, after a bare `panda.flash()` silently failed to persist on one DEV-firmware panda. Multiple users extracted successfully on the RayLib `tskm` branch. (Later superseded by pandad flashing on boot — no flash call in `hack()` now.)
- **2026-07-02 → 07-08** — Built the `tskmloop` web app off `commaai/nightly-dev`: moved shared logic into `tsk/lib`, stdlib server on `11111`, phone-first `index.html`. Replaced the single-step extractor with the three-step **CAN → DataFlash → Find** pipeline; built `collect_can.py`, `dump_dataflash.py`, `matcher.py` and their real background jobs (`panda_lock` serialization, `rehydrate_*` on restart, `_close_panda`). Audited installer → boot → install → key-load end to end.
- **2026-07-08 (in-car)** — First successful Sienna extraction end to end (key `f220…7098` at `0xff206e14`). The partial-dump path also recovered the key in-car. Added the key-region gate (`.partial` only when `0x6e14` is captured, else `key_missed`) and CAN early-stop (stop when both targets are met, not a fixed 60 s).
- **2026-07-09 (prime, not time)** — Controlled in-car experiment: both prime variants dumped 32768/32768 (0 gaps, 2/2); time-only (60 s, no prime) partialed both times. The prime fixes cold partials; waiting does not. The gap is a fixed-size (124-byte) moving single burst → RX/USB-side, not structural (overturns the earlier "structural window" read). Decision (Calvin): keep the dump as-is; tell stuck users to run the Extractor first (manual prime), since the behavior may be Sienna-specific and most Sienna partials still capture the key.
- **2026-07-09 (payload provenance)** — Traced the dataflash path to Willem's I-CAN-hack/secoc `while-loop` branch: the shipped payload is byte-identical to his `payload.bin` (same SHA256), and the driver, shellcode, and matcher are his. No third-party ("Bk2ol") code is used; the one non-Willem trace is the dump's session-flow timing (sleeps 0.5/0.7/1.0 + a `PROGRAMMING → PROGRAMMING` repeat) that differs from the extraction flow, and its origin isn't verifiable from the repos.

**Current state.** Full pipeline validated in-car on the Sienna, complete and partial dumps. Car-agnostic; no EPS version guard anywhere.

**Open items.** (1) The `key_missed` message doesn't point at the manual-prime remedy, so a stuck user loops on cold dumps. (2) The prime mechanism (RX-buffer vs EPS send-rate) is unresolved. (3) EPS app-string capture on every run (the per-run hardware label) is still unimplemented. (4) Whether cold-partial behavior is Sienna-specific — only a non-Sienna in-car run answers it.
