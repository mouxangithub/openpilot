# system/ui/ - RAYLIB WIDGET FRAMEWORK

The shared raylib widget toolkit plus standalone offroad apps (spinner, setup, updater, reset). NOT the driving UI: `selfdrive/ui/` builds *screens* on top of this, this dir owns the `Widget` base class, layout primitives, and the `gui_app` window/asset/nav-stack singleton. Editing a widget here changes every screen everywhere.

## STRUCTURE

```
system/ui/
├── lib/
│   ├── application.py     # gui_app singleton: window, fonts, textures, nav stack, mouse_events, env flags
│   ├── text_measure.py    # measure_text_cached - mandatory instead of raw raylib measurement
│   ├── wrap_text.py multilang.py utils.py shader_polygon.py egl.py
│   ├── scroll_panel.py scroll_panel2.py wifi_manager.py networkmanager.py
│   └── tests/test_handle_state_change.py
├── widgets/
│   ├── __init__.py        # Widget ABC, DialogResult
│   ├── layouts.py         # Alignment, HBoxLayout
│   ├── button.py toggle.py slider.py label.py list_view.py icon_widget.py
│   └── scroller.py nav_widget.py keyboard.py inputbox.py option_dialog.py confirm_dialog.py network.py html_render.py
├── sunnypilot/
│   ├── lib/application.py styles.py utils.py    # SUNNYPILOT_UI flag, SP styling
│   └── widgets/           # SP overrides: list_view, toggle, tree_dialog, option_control, progress_bar, ...
└── {spinner,text,setup,reset,updater}.py + tici_*/mici_* device variants
```

## WIDGET CONTRACT

[widgets/__init__.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/system/ui/widgets/__init__.py) defines the ABC. Lifecycle inside `render(rect=None)`, in order:

1. `set_rect(rect)` if a rect was passed
2. `_update_state()` - non-layout state
3. visibility check (`is_visible`); bails out returning `None`
4. `_layout()` - position children
5. `_render(rect)` - the only abstract method
6. `_process_mouse_events()` - runs LAST, after drawing, and only when `enabled` and the device was awake

A Widget owns: `_rect` / `_parent_rect` (touch clipping via `_hit_rect`), `_children` (registered with `self._child(w)`), `_is_visible`, `_enabled` (both accept a bool or a callable), per-slot press state, `_click_callback`, `_touch_valid_callback`, `_click_delay`.

Subclass MUST implement `_render`. Subclass MAY override `_update_state`, `_layout`, `_update_layout_rects`, `_handle_mouse_press`, `_handle_mouse_release` (call `super()` or the click callback never fires), `_handle_mouse_event`, `show_event` / `hide_event`.
Subclass MUST NOT override `render()`, `_process_mouse_events()`, or touch the name-mangled press arrays.
Register inline children with `_child()` so `show_event`/`hide_event` propagate. Do NOT register a widget you push onto the nav stack via `gui_app.push_widget()`; `gui_app` owns that lifecycle and `dismiss()` pops it.

## LAYOUTS

[widgets/layouts.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/system/ui/widgets/layouts.py) (`HBoxLayout`, `Alignment`) shows the required pattern: for each visible child call `set_position(x, y)` **and** `set_parent_rect(self._rect)` **before** `render()`.
Skip `set_position` and the child draws at its stale/origin rect. Skip `set_parent_rect` and `_hit_rect` falls back to the raw child rect, so a child scrolled outside its container still eats touches. Both, every frame.

## RUNTIME FLAGS

Read in [lib/application.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/system/ui/lib/application.py) unless noted.

| Env var | Effect |
|---|---|
| `BIG=1` | comma 3X layout (comma four is default) |
| `SCALE=1.5` | scale whole UI; auto-scaled on PC when unset |
| `FPS=n` | target framerate (default 60, 20 on tizi) |
| `STRICT_MODE=1` | kill app on sustained frame drops |
| `SHOW_FPS=1` / `SHOW_TOUCHES=1` | FPS overlay / debug touch rects |
| `GRID=50` | 50px alignment grid overlay;
`BURN_IN` (presence) = burn-in heatmap |
| `ENABLE_VSYNC=1` / `OFFSCREEN=1` | vsync on / disable FPS limiting |
| `RECORD=1` | screen capture; `RECORD_OUTPUT`, `RECORD_QUALITY`, `RECORD_BITRATE`, `RECORD_SPEED` tune it |
| `SUNNYPILOT_UI=0` | stock UI instead of SP ([sunnypilot/lib/application.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/system/ui/sunnypilot/lib/application.py)) |
| `SHOW_MOUSE_COORDS=1` (same file) / `DEBUG_SCROLL=1` | SP mouse coord overlay / scroll_panel2 logging |

## ANTI-PATTERNS (THIS DIR)

- **DO NOT add a screen here.** Reusable widgets only; screens belong in `selfdrive/ui/`.
- **DO NOT override `render()`** - you lose `_update_state`/`_layout`/input ordering.
- **DO NOT render a child without both `set_position` + `set_parent_rect`.**
- **DO NOT `_child()` a nav-stack widget** - the assert fires or lifecycle events double-fire.
- **DO NOT skip the `_` prefix** on internal fields/methods (README style guide).

## NOTES

- `Widget.device.awake` falls back to a stub when `selfdrive.ui.ui_state` can't import, so widgets work outside the driving stack.
- Input arrives as `gui_app.mouse_events` (`MouseEvent`, `MousePos`, `MAX_TOUCH_SLOTS`); only slot 0 processed unless `self._multi_touch = True`.
- `DialogResult` (`CANCEL=0`, `CONFIRM=1`, `NO_ACTION=-1`) is the return convention for dialog `_render`.
- SP widgets in `sunnypilot/widgets/` subclass or shadow the stock ones by the same filename; check both before editing.
- Tests here are `unittest.TestCase` on `openpilot.common.test.OpenpilotTestCase` (see [lib/tests/](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/system/ui/lib/tests)); run via `tools/op.sh test`.
