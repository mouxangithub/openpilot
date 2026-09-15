# selfdrive/ui/ - RAYLIB UI

Largest tree in the repo (~157 files). Three coexisting UI variants share one process. See parent [AGENTS.md](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/selfdrive/AGENTS.md) for stack-wide rules.

## STRUCTURE

```
ui/
├── ui.py            # entry: picks MainLayout (big) vs MiciMainLayout
├── ui_state.py      # UIState/Device singletons; subclass SP counterparts
├── soundd.py        # alert audio daemon (separate process from ui)
├── watch3.py        # dev tool: 3 camera streams in one window
├── layouts/         # BIG screen: home, sidebar, onboarding, main + settings/
├── onroad/          # BIG onroad renderers: augmented_road_view, hud, model, alert, driver_state
├── widgets/         # ui-specific widgets (exp_mode_button, offroad_alerts, prime, ssh_key, setup)
├── mici/            # comma four UI: own layouts/, onroad/, widgets/, tests/
├── sunnypilot/      # SP overrides: layouts/, onroad/, mici/, ui_state.py
├── body/            # comma body onroad layout + animations
├── translations/    # .po/.pot + update_translations.py + potools.py
├── lib/             # api_helpers.py, prime_state.py
├── installer/       # native installer.cc (built only with --extras on comma_arm64)
└── tests/           # test_raylib_ui.py, test_soundd.py, test_translations.py, diff/ screenshots
```

## WHERE TO LOOK

| Task | Location |
|------|----------|
| Change onroad camera/overlay compositing | [onroad/augmented_road_view.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/selfdrive/ui/onroad/augmented_road_view.py) |
| Add an SP onroad overlay (speed limit, blind spot, chevron) | [sunnypilot/onroad/](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/selfdrive/ui/sunnypilot/onroad) |
| Add a settings panel | [layouts/settings/settings.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/selfdrive/ui/layouts/settings/settings.py) + [sunnypilot/layouts/settings/](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/selfdrive/ui/sunnypilot/layouts/settings) |
| Add shared UI state read by many widgets | [ui_state.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/selfdrive/ui/ui_state.py) / [sunnypilot/ui_state.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/selfdrive/ui/sunnypilot/ui_state.py) |
| Add/modify an alert sound | [soundd.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/selfdrive/ui/soundd.py) (`sound_list_sp`) + `selfdrive/assets/sounds/` |
| Regenerate translations | [translations/update_translations.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/selfdrive/ui/translations/update_translations.py) |
| Reusable widget/framework primitive | `openpilot/system/ui/widgets/` and `openpilot/system/ui/lib/` (NOT here) |

## VARIANT SELECTION (read this before editing anything)

Two orthogonal switches, both env-driven, both resolved at import time:

- **Screen size**: `BIG_UI = gui_app.big_ui()` in [ui.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/selfdrive/ui/ui.py) → true on `tici`/`tizi` or `BIG=1`. True → `layouts/` + `onroad/`. False (comma four, default on PC) → `mici/`.
- **Brand**: `gui_app.sunnypilot_ui()` ← `SUNNYPILOT_UI` env, defaults to `"1"`. Defined in [system/ui/sunnypilot/lib/application.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/system/ui/sunnypilot/lib/application.py). Set `SUNNYPILOT_UI=0` for stock.
- Brand switching is **module-level conditional imports with aliasing**, e.g. in [layouts/main.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/selfdrive/ui/layouts/main.py): `if gui_app.sunnypilot_ui(): from ...sunnypilot.layouts.home import HomeLayoutSP as HomeLayout`. Same pattern in [mici/layouts/main.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/selfdrive/ui/mici/layouts/main.py).
- Rule of thumb: SP behavior → edit the `*SP` subclass under `sunnypilot/`. Behavior needed by both brands → edit the stock class and let SP inherit. `mici/` and `layouts/` are **separate implementations**, not shared; a fix in one usually needs porting to the other.

## ONROAD PATH

`MainLayout` (or `MiciMainLayout`) → `AugmentedRoadView` → `CameraView` (VisionIPC) → renderers layered on top: `model_renderer`, `hud_renderer`, `alert_renderer`, `driver_state`. SP composes via multiple inheritance: `class AugmentedRoadView(CameraView, AugmentedRoadViewSP)` — the SP mixin holds extra state/filters, stock class drives the render order.

## CONVENTIONS

- Framework lives in `openpilot/system/ui/` (`lib/application.py` `gui_app`, `widgets/`, `lib/multilang.py`). This dir holds only openpilot-specific screens. New generic primitive → put it in `system/ui/widgets/`.
- Every graphical element subclasses `Widget` from `openpilot/system/ui/widgets/__init__.py`. Prefer stateful widget over free function.
- Internal attrs/methods prefixed `_`.
- Render loop is driven by `gui_app.render()` generator; `ui_state.update()` is called once per frame from [ui.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/selfdrive/ui/ui.py) — do NOT poll cereal inside widgets.
- User-visible strings go through `tr()` / `trn()` from `openpilot.system.ui.lib.multilang`.
- SP files carry the sunnypilot copyright header docstring.
- Dev env vars (see [system/ui/README.md](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/system/ui/README.md)): `SHOW_FPS`, `STRICT_MODE`, `SCALE`, `BURN_IN`, `GRID`, `RECORD`, `SHOW_MOUSE_COORDS`.

## ANTI-PATTERNS (THIS DIR)

- **NEVER hand-edit `translations/app.pot`** — generated by `update_translations.py`. Hand-edit only the per-language `app_*.po` msgstr, and `languages.json` when adding a locale.
- **NEVER add a translatable string in a dir the extractor doesn't walk.** It only scans `system/ui/`, and ui's `widgets/ layouts/ onroad/ sunnypilot/ mici/`, plus both `selfdrived/` dirs. Strings in `lib/`, `body/`, `tests/` are silently dropped.
- **DO NOT copy a stock class into `sunnypilot/`** to tweak it — subclass and override the one method.
- **DO NOT add SP logic to stock `layouts/`/`onroad/` files** beyond the conditional-import alias block.
- **DO NOT do heavy work (file IO, param reads, allocations) inside a widget's render** — it runs at 60fps and `STRICT_MODE=1` kills on frame drops.
- **DO NOT grow `installer/installer.cc`** — SConscript asserts each installer binary is `< 2500 KB`.

## NOTES

- `soundd` is its own managed daemon, not part of the ui process. It merges stock `AudibleAlert` with SP `AudibleAlertSP` (from `custom.capnp`) and gates on `QuietMode`; ambient volume is mic-driven via `system/micd`, with `tizi`-specific `AMBIENT_DB`/`VOLUME_BASE` constants.
- `ui` pins itself to core 5 and re-affines after power-save; it publishes `uiDebug` (frame/cpu time) every frame.
- `tests/diff/` renders screenshot diffs for UI review; `tests/profile_onroad.py` and `tests/cycle_offroad_alerts.py` are manual dev tools, not tests.
- `installer/` is only built with `--extras` on `comma_arm64`; four branch-specific binaries are produced from the same `.cc` via `-DBRANCH`.
- `body/` renders only on comma body hardware, reached from `MainLayout` as `BodyLayout`.
