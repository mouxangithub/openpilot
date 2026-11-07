# NNFF one-shot notice + phone-home residue cleanup — 2026-10-20

Four items from the second navipilot gap analysis
(`artifacts/sunnypilot_navipilot_gap_round2_2026-10-20.md`, gitignored).

## 1. One-shot NNFF torque model notice (`torqueNNLoad`)

`AudibleAlertSP.nnff`, `nnff.wav` and the soundd mapping already existed but
nothing ever emitted the notice. This adds it, sourcing the model name from
`CarParamsSP` instead of the string param navipilot uses, so the notice can
also say when the model is a fuzzy substitute — information navipilot drops.

- `log.capnp`: `torqueNNLoad @105` appended to `OnroadEvent.EventName`
  (ordinals are append-only).
- `events.py`: `nnff_load_alert(name, fuzzy)` composes the text
  ("NNFF 扭矩模型已加载" / name, plus "（替代模型）" when
  `fuzzyFingerprint`); `Events.bind_nnff_notice()` rebinds only that one event
  in a per-instance mapping rebuilt once, so the per-frame
  `get_events_mapping()` lookup stays a plain attribute read. The static
  `EVENTS` entry is a silent placeholder and never names a model.
- `selfdrived.py`: `update_nnff_alert()` called after `update_alerts()` in
  `step()`. Polled at 2 Hz from frame 550 (11 s) so slow initialization or a
  late CarParamsSP load cannot lose the only notice. Gates: initialized, not
  passive, deviceState.started, canValid, no canTimeout, all checks, no
  NO_ENTRY, no current alert, `NeuralNetworkLateralControl` enabled, model
  name present and not "MOCK".

Deliberately not done: wiring `AudibleAlertSP.nnff` through
`selfdriveState.alertSound`. That field is the upstream 11-value enum and no
alert in this tree sets an SP sound value (the other SP entries in soundd's
table are equally unwired), so the notice uses `AudibleAlert.prompt` like
every other advisory here.

## 2. Dead phone-home residue in auto_update

`_notify_cwp` imported `...cweb_push`, which does not exist in this fork
(the beacon was declined, see `recovery/server.py` and the carrot README), so
every successful auto-update printed
`notify skipped: No module named ...` from the swallowing caller. Removed
`_notify_cwp`, its call site, the now-dead `_diff_stats`, `NOTIFY_TIMEOUT`,
and the `os`/`re` imports.

## 3. Dead file

`carrot_man_input.py` (18 lines, zero importers anywhere — verified by grep
over `.py/.json/.sh`) deleted. It was misread as an untested module in the
gap analysis; it was residue, not a coverage gap.

## 4. Tests

- `selfdrived/tests/test_nnff_notice.py`: 19 cases — text composition
  (exact vs fuzzy), binding scope, `create_alerts` resolution, counter
  integrity, and the full gate matrix (startup window, 2 Hz poll,
  initialization, passive, canTimeout, current alert, feature off, empty and
  MOCK names). Needs a built msgq, so hosts without one skip the whole module
  explicitly; device runs must confirm skip=0.
- `carrot/tests/test_signal_stop_prepare_runtime.py`: 11 cases —
  construction (the alarm for the `try/except Exception: None` swallow in
  `carrot_functions`), atomic publish, mode gating, 20-track cap, oversized
  and NaN rejection keeping the last good file, and `record_prepare`
  deduplication / control-mode attribution.

## Validation

- `python -m ruff check` clean on all touched files.
- carrot suite unchanged locally: 568 collected / 13 pre-existing environment
  errors / 35 skipped — identical error list to the strict `git stash`
  baseline.
- New pytest file: 11 passed locally.
- Device (`192.168.7.233`, after pull to the merge of `02cd2d1b5`):
  - `test_nnff_notice.py` **20/20 OK, skip=0**. Two expectation bugs were
    caught here and fixed in `02cd2d1b5`: `alert_type` uses ET.PERMANENT's
    lowercase capnp name, and frame 550 is the first eligible frame (the gate
    is `frame < 550`).
  - `test_signal_stop_prepare_runtime.py` 11 passed (pytest).
  - `test_alerts` + `test_alertmanager` + `test_state_machine`: 12/12 OK —
    this includes the all-events-defined and alert-sanity sweeps over the new
    `torqueNNLoad` entry.
  - Full carrot suite: **614/614 OK**.
- Not validated: on-road behaviour. `selfdrived` is `only_onroad`; the notice
  needs frame >= 550 (~11 s) after initialization, so short trips may never
  see it.
