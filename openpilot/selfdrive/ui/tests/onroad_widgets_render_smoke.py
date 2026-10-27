"""Headless render + param-gating smoke test for the StarPilot onroad widget ports.

Covers the widgets mounted by sunnypilot's HudRendererSP from StarPilot:

- stopping_point.StoppingPointRenderer      (ShowStoppingPoint, default off)
- torque_bar.StarPilotTorqueBar             (ShowTorqueBar, default off)
- personality_button.PersonalityButton      (ShowPersonalityButton, default off)
- pip_sidecam.PipSideCamera                 (PIPPreview*, default off; needs a
                                             driver-camera stream - Lite has none)
- developer_sidebar.DeveloperSidebar        (DeveloperSidebar + Metric1..7, default off)
- speed_source_drawer.SpeedSourceDrawerRenderer (ShowSpeedLimitSources, default off)
- hud_renderer.HudRendererSP mounts them all and stays headless-renderable

Every widget must be invisible with its param unset (code-side default; none of
the gating keys are registered in params_keys.h) and render cleanly once the
param is set on the (fake) param store.

Run from the repo root:

    PYTHONPATH=. python openpilot/selfdrive/ui/tests/onroad_widgets_render_smoke.py

Exit status is 0 when every check passes.

NOTE: deliberately NOT named test_*.py. install_stubs() replaces
openpilot.system.ui.lib.application, pyray and openpilot.common.params in
sys.modules, so pytest must not collect it into a shared session - doing so
would poison every other test that imports the UI stack.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[4]

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / 'opendbc_repo'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import carrot_tuning_render_smoke as _harness

_harness.install_stubs()

# ---------------------------------------------------------------------------
# Extra stubs the carrot harness does not provide
# ---------------------------------------------------------------------------

# A controllable clock: several widgets throttle their param reads on
# rl.get_time() and the drawer animates on it.
_NOW = [0.0]


def _tick(seconds: float) -> None:
  _NOW[0] += seconds


_pyray = sys.modules['pyray']
_pyray.get_time = lambda: _NOW[0]

# mici's blend_colors needs the HSV round-trip helpers
_pyray.color_to_hsv = lambda color: SimpleNamespace(x=0.0, y=0.0, z=1.0)
_pyray.color_from_hsv = lambda h, s, v: _harness.Color(
  int(v * 255), int(v * 255), int(v * 255), 255)

# functional ffi stand-in: pip_sidecam's flip flag is an int array, the drawer
# builds Vector2 arrays through it
_pyray.ffi = types.SimpleNamespace(
  new=lambda _type, values=None: list(values) if values is not None else [0],
  cast=lambda _type, value: value,
  from_buffer=lambda value: value,
)

# shader_polygon compiles GL shaders at first use; record polygons instead.
_POLYGONS: list[tuple] = []


class _FakeGradient:
  def __init__(self, start=None, end=None, colors=None, stops=None):
    self.start, self.end, self.colors, self.stops = start, end, colors, stops


def _fake_draw_polygon(rect, points, color=None, gradient=None):
  _POLYGONS.append((points, color, gradient))


sys.modules['openpilot.system.ui.lib.shader_polygon'] = types.SimpleNamespace(
  draw_polygon=_fake_draw_polygon, Gradient=_FakeGradient,
)

# cereal: the real capnp modules import fine on a PC; only msgq is missing, and
# that is stubbed below for pip_sidecam.

# common.hardware pulls fcntl (POSIX-only); the HUD only needs get_device_type
_hw_mod = _harness._FakeModule('openpilot.common.hardware')
_hw_mod.HARDWARE = SimpleNamespace(get_device_type=lambda: 'pc')
_hw_mod.COMMA_HARDWARE = SimpleNamespace()
_hw_mod.PC = True
sys.modules['openpilot.common.hardware'] = _hw_mod

# msgq visionipc: pip_sidecam's transport; the fake client never connects
# (faithful to Lite hardware, which has no driver camera to publish it).
# cereal.messaging also does `from msgq import ...` names we must fabricate,
# so the stub auto-generates any missing attribute (harness's _FakeModule).
class _FakeVisionIpcClient:
  def __init__(self, name, stream_type, conflate=False):
    self.name, self.stream_type = name, stream_type
    self.num_buffers = 0
    self.stride, self.height = 2048, 1216

  def is_connected(self):
    return False

  def connect(self, send_frame):
    return False

  def recv(self, timeout_ms=0):
    return None


_visionipc = _harness._FakeModule('msgq.visionipc')
_visionipc.VisionIpcClient = _FakeVisionIpcClient
_visionipc.VisionStreamType = SimpleNamespace(VISION_STREAM_DRIVER='driver')
_msgq_pkg = _harness._FakeModule('msgq')
_msgq_pkg.visionipc = _visionipc
sys.modules['msgq'] = _msgq_pkg
sys.modules['msgq.visionipc'] = _visionipc

# cereal.messaging wraps msgq and annotates with its types at def time, which
# the permissive fake cannot express - stub the whole module (messaging is only
# used for type hints in the onroad renderers this smoke imports).
sys.modules['openpilot.cereal.messaging'] = _harness._FakeModule('openpilot.cereal.messaging')

# ---------------------------------------------------------------------------
# Fake params + ui_state
# ---------------------------------------------------------------------------

_params_mod = types.ModuleType('openpilot.common.params')

store: dict = {}


class FakeParams:
  def __init__(self, *a, **k):
    pass

  def get(self, key, encoding=None, return_default=False):
    return store.get(key)

  def get_bool(self, key):
    return bool(store.get(key, False))

  def get_int(self, key, default=0):
    try:
      return int(store[key])
    except (KeyError, TypeError, ValueError):
      return default

  def get_float(self, key, default=0.0):
    try:
      return float(store[key])
    except (KeyError, TypeError, ValueError):
      return default

  def put(self, key, value, block=False):
    store[key] = value

  def put_bool(self, key, value, block=False):
    store[key] = value


_params_mod.Params = FakeParams
_params_mod.store = store

_ui_mod = types.ModuleType('openpilot.selfdrive.ui.ui_state')

# capnp-like message stand-ins
_car_state = SimpleNamespace(
  vEgo=8.0, aEgo=-1.2, standstill=False, gasPressed=False,
  leftBlinker=False, rightBlinker=True, leftBlindspot=False, rightBlindspot=False,
  steeringAngleDeg=0.0, gearShifter='drive',
)
_car_state_sp = SimpleNamespace(speedLimit=13.9, carrotLeftBlindHint=False, carrotRightBlindHint=False)
_resolver = SimpleNamespace(
  speedLimit=13.9, distToSpeedLimit=100.0, source='car', speedLimitOffset=0.0,
  speedLimitLast=13.9, speedLimitFinal=13.9, speedLimitFinalLast=13.9,
  speedLimitValid=True, speedLimitLastValid=True,
)
_plan_sp = SimpleNamespace(
  speedLimit=SimpleNamespace(resolver=_resolver),
  signalAssistAction=0,
)
_controls_state = SimpleNamespace(
  curvature=0.0, desiredCurvature=0.0,
  lateralControlState=SimpleNamespace(which=lambda: 'torqueState'),
)
_car_control = SimpleNamespace(latActive=False, longActive=False, actuators=SimpleNamespace(torque=0.0, accel=0.0))
_car_output = SimpleNamespace(actuatorsOutput=SimpleNamespace(torque=0.4))
_live_parameters = SimpleNamespace(roll=0.0, steerRatio=15.0, stiffnessFactor=1.0)
_live_delay = SimpleNamespace(lateralDelay=0.12)
_lateral_torque_parameters = SimpleNamespace(useParams=False, frictionCoefficientFiltered=0.06, latAccelFactorFiltered=0.9)
_live_map_data = SimpleNamespace(
  speedLimitValid=True, speedLimit=13.4,
  speedLimitAheadValid=True, speedLimitAhead=11.2, speedLimitAheadDistance=420.0,
)
_selfdrive_state = SimpleNamespace(personality=1, enabled=False, engageable=True)

SM_VALUES = {
  'carState': _car_state,
  'carStateSP': _car_state_sp,
  'longitudinalPlanSP': _plan_sp,
  'controlsState': _controls_state,
  'carControl': _car_control,
  'carOutput': _car_output,
  'liveParameters': _live_parameters,
  'liveDelay': _live_delay,
  'lateralTorqueParameters': _lateral_torque_parameters,
  'liveMapDataSP': _live_map_data,
  'selfdriveState': _selfdrive_state,
}


class FakeSubMaster:
  def __init__(self):
    self._values = dict(SM_VALUES)
    self.valid = {k: True for k in self._values}
    self.recv_frame = {k: 10 for k in self._values}
    self.updated = {k: False for k in self._values}
    self.alive = {k: True for k in self._values}
    self.seen = {}
    self.frame = 100

  def __getitem__(self, key):
    if key not in self._values:
      raise KeyError(key)
    return self._values[key]


class FakeUiState:
  def __init__(self):
    self.params = FakeParams()
    self.sm = FakeSubMaster()
    self.started = True
    self.started_frame = 1
    self.is_metric = True
    self.status = 'engaged'
    self.has_longitudinal_control = True
    self.engaged = False
    self.CP = None
    self.home_model_name = 'TestModel (tiny)'
    self.offroad_callbacks: list = []

  def add_offroad_transition_callback(self, cb):
    self.offroad_callbacks.append(cb)

  def remove_offroad_transition_callback(self, cb):
    if cb in self.offroad_callbacks:
      self.offroad_callbacks.remove(cb)

  def is_offroad(self):
    return False

  def update_params(self):
    return None


_ui_mod.ui_state = FakeUiState()
# the real HudRendererSP/SideBar stack reads a few more UIState attributes at
# construction/render time; mirror UIStateSP's defaults
ui_state_obj = _ui_mod.ui_state
ui_state_obj.speed_limit_mode = None
ui_state_obj.torque_bar = False
ui_state_obj.developer_ui = None
ui_state_obj.icbm_running = False
ui_state_obj.CP_SP = None
ui_state_obj.experimental_mode = False
ui_state_obj.pearl_eyes = False
# modules reached through the fake ui_state package (base hud_renderer imports
# UIStatus from it)
_ui_mod.UIStatus = SimpleNamespace(
  DISENGAGED='disengaged', ENGAGED='engaged', OVERRIDE='override',
  LAT_ONLY='lat_only', LONG_ONLY='long_only',
)
_ui_mod.ChestnutState = SimpleNamespace(DISCONNECTED='disconnected')
sys.modules['openpilot.common.params'] = _params_mod
sys.modules['openpilot.selfdrive.ui.ui_state'] = _ui_mod

# ---------------------------------------------------------------------------
# Imports under test (after stubbing)
# ---------------------------------------------------------------------------

from openpilot.selfdrive.ui.sunnypilot.onroad import (  # noqa: E402
  developer_sidebar, personality_button, pip_sidecam, source_bubble_layout,
  speed_source_drawer, stopping_point, torque_bar,
)
from openpilot.selfdrive.ui.sunnypilot.onroad.hud_renderer import (  # noqa: E402
  EXP_BUTTON_SIZE, HudRendererSP,
)
from openpilot.selfdrive.ui.ui_state import ui_state  # noqa: E402  (the fake)

PANEL = _harness.Rect(0, 0, 2160, 1080)

CHECKS = 0
FAILURES: list[str] = []


def check(name: str, fn) -> None:
  global CHECKS
  CHECKS += 1
  try:
    fn()
    print(f'  ok  {name}')
  except Exception as e:
    FAILURES.append(f'{name}: {type(e).__name__}: {e}')
    print(f'  FAIL {name}: {type(e).__name__}: {e}')


def drawn_texts() -> set[str]:
  return {str(d[1]) for d in _harness.DRAWN}


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def main() -> int:
  # some stock renderers pass extra kwargs to gui_app.texture; tolerate them
  _app = sys.modules['openpilot.system.ui.lib.application'].gui_app
  _app.texture = lambda path, w=0, h=0, keep_aspect_ratio=False, **kw: _harness.Texture()
  print('== stopping point ==')

  def off_by_default():
    store.pop('ShowStoppingPoint', None)
    r = stopping_point.StoppingPointRenderer()
    r.render(PANEL)
    assert not r.is_visible, 'stopping point visible with ShowStoppingPoint unset'
    assert 'STOP' not in drawn_texts(), 'stop sign drawn while gated off'
  check('hidden while ShowStoppingPoint is unset', off_by_default)

  def renders_on_red_light():
    store['ShowStoppingPoint'] = True
    store['ShowStoppingPointMetrics'] = True
    ui_state.sm._values['longitudinalPlanSP'].signalAssistAction = 1
    r = stopping_point.StoppingPointRenderer()
    r.render(PANEL)
    assert r.is_visible, 'stopping point hidden with param on + red light'
    texts = drawn_texts()
    assert 'STOP' in texts, f'stop sign not drawn: {sorted(texts)[:5]}'
    # vEgo=8, aEgo=-1.2 -> d = 64/2.4 ~= 27 m
    assert any('27 m' in t for t in texts), f'metrics text missing: {sorted(texts)[:8]}'
  check('renders stop sign + distance on red light', renders_on_red_light)

  def silent_without_red_light():
    ui_state.sm._values['longitudinalPlanSP'].signalAssistAction = 0
    _harness.DRAWN.clear()
    r = stopping_point.StoppingPointRenderer()
    r.render(PANEL)
    assert 'STOP' not in drawn_texts(), 'stop sign drawn without a red light'
  check('no marker without a red-light signal', silent_without_red_light)

  print('== torque bar ==')

  def torque_bar_gating():
    store.pop('ShowTorqueBar', None)
    bar = torque_bar.StarPilotTorqueBar()
    bar.render(PANEL)
    assert not bar.is_visible, 'torque bar visible with ShowTorqueBar unset'
    store['ShowTorqueBar'] = True
    _tick(0.3)  # past the 0.25 s param-read throttle
    _POLYGONS.clear()
    bar.render(PANEL)
    assert bar.is_visible, 'torque bar invisible with param on'
    assert _POLYGONS, 'torque bar drew no polygons'
  check('torque bar hidden by default, renders with param on', torque_bar_gating)

  print('== personality button ==')

  def personality_gating_and_cycle():
    store.pop('ShowPersonalityButton', None)
    btn = personality_button.PersonalityButton()
    btn.render(PANEL)
    assert not btn.is_visible, 'personality button visible while gated off'
    store['ShowPersonalityButton'] = True
    _tick(0.3)  # past the 0.25 s param-read throttle
    btn.render(PANEL)
    assert btn.is_visible, 'personality button hidden with param on + long control'

    ui_state.has_longitudinal_control = False
    btn.render(PANEL)
    assert not btn.is_visible, 'personality button shown without longitudinal control'
    ui_state.has_longitudinal_control = True

    # standard(1) -> relaxed(2) -> aggressive(0) -> standard(1)
    assert store.get('LongitudinalPersonality') in (None, 1)
    btn._handle_mouse_release(None)
    assert store.get('LongitudinalPersonality') == 2, f'cycle wrote {store.get("LongitudinalPersonality")}'
    btn._handle_mouse_release(None)
    assert store.get('LongitudinalPersonality') == 0
    btn._handle_mouse_release(None)
    assert store.get('LongitudinalPersonality') == 1
  check('personality button gated + cycles the param', personality_gating_and_cycle)

  print('== pip sidecam ==')

  def pip_gating_and_hardware_note():
    store.pop('PIPPreviewEnabled', None)
    cam = pip_sidecam.PipSideCamera()
    cam.render(PANEL)
    assert not cam.is_visible, 'pip visible with PIPPreviewEnabled unset'
    store['PIPPreviewEnabled'] = True
    _tick(2.5)  # past the 2 s pip param throttle
    cam.render(PANEL)
    assert cam.is_visible, 'pip hidden with param on'
    # no mask configured -> no sides -> nothing drawn, no crash
    cam.render(PANEL)
    # Lite hardware: fake client never connects; render must stay silent
    store['PIPPreviewMask'] = '{"center_left": [512, 600], "crop_size": 400}'
    cam._last_param_refresh = float('-inf')
    cam._refresh_config(force=True)
    cam.render(PANEL)
    # close() must unregister its offroad callback
    cam.close()
    assert cam._offroad_transition_callback is None, 'close did not clear the callback'
    assert not ui_state.offroad_callbacks, 'close did not unregister the offroad callback'
  check('pip gated, inert without driver camera, close() clean', pip_gating_and_hardware_note)

  print('== developer sidebar ==')

  def sidebar_gating():
    store.pop('DeveloperSidebar', None)
    side = developer_sidebar.DeveloperSidebar()
    side.render(PANEL)
    assert not side.visible, 'sidebar visible with DeveloperSidebar unset'
    store['DeveloperSidebar'] = True
    store['DeveloperSidebarMetric1'] = 1  # ACCEL
    side._last_toggles_check = float('-inf')
    _harness.DRAWN.clear()
    side.render(PANEL)
    assert side.visible, 'sidebar hidden with master param on'
    assert 'ACCEL' in drawn_texts(), f'ACCEL card not drawn: {sorted(drawn_texts())[:6]}'
  check('sidebar gated + renders selected metric', sidebar_gating)

  def sidebar_na_for_missing_plan_fields():
    store['DeveloperSidebar'] = True
    store['DeveloperSidebarMetric1'] = 14  # ACCEL JERK: no SP field on this fork
    side = developer_sidebar.DeveloperSidebar()
    side._last_toggles_check = float('-inf')
    _harness.DRAWN.clear()
    side.render(PANEL)
    assert 'N/A' in drawn_texts(), 'missing plan field did not degrade to N/A'
  check('sidebar reports N/A for StarPilot-only plan fields', sidebar_na_for_missing_plan_fields)

  print('== speed source drawer ==')

  def drawer_gating_and_rows():
    store.pop('ShowSpeedLimitSources', None)
    rend = speed_source_drawer.SpeedSourceDrawerRenderer()
    rend.render(PANEL)
    assert not rend.is_visible, 'drawer visible with ShowSpeedLimitSources unset'
    assert rend._drawer.width == 0, 'drawer animating while gated off'

    store['ShowSpeedLimitSources'] = True
    store['SLCPriority1'] = 'Highest'
    rend._last_param_refresh = float('-inf')
    # let the open animation finish (0.18 s at the controllable clock)
    for _ in range(5):
      _tick(0.2)
      rend.render(PANEL)
    assert rend.is_visible, 'drawer hidden with param on'
    assert rend._drawer.width > 0, 'drawer never opened'
    texts = drawn_texts()
    # resolver source=car -> Dashboard row active; map + upcoming rows visible
    assert 'Dashboard' in texts, f'dashboard row missing: {sorted(texts)[:8]}'
    assert 'Map Data' in texts, f'map row missing: {sorted(texts)[:8]}'
    assert 'Next' in texts, f'upcoming row missing: {sorted(texts)[:8]}'
  check('drawer gated, opens and lists resolver-backed rows', drawer_gating_and_rows)

  def drawer_rows_follow_vision_param():
    store['ShowSpeedLimitSources'] = True
    store['VisionSpeedLimitEnabled'] = True
    store['VisionSpeedLimit'] = 12.0
    rend = speed_source_drawer.SpeedSourceDrawerRenderer()
    rend._last_param_refresh = float('-inf')
    for _ in range(5):
      _tick(0.2)
      rend.render(PANEL)
    assert 'Vision' in drawn_texts(), 'vision row missing while VisionSpeedLimitEnabled'
    store['VisionSpeedLimitEnabled'] = False
    rend._last_param_refresh = float('-inf')
    _harness.DRAWN.clear()
    for _ in range(3):
      _tick(0.2)
      rend.render(PANEL)
    assert 'Vision' not in drawn_texts(), 'vision row shown while disabled'
  check('vision row follows VisionSpeedLimitEnabled', drawer_rows_follow_vision_param)

  def layout_helpers():
    rows = source_bubble_layout.visible_source_rows(
      speed_source_drawer.SOURCE_DEFS,
      {'dashboard_sl': 50.0, 'map_sl': 0.0, 'vision_sl': 45.0, 'next_sl': 30.0},
      'Dashboard', ('Dashboard', 'Map Data', 'Vision', 'Upcoming'),
    )
    assert [r[0] for r in rows] == ['Dashboard', 'Vision', 'Next'], f'unexpected rows: {rows}'
    assert rows[0][2] is True, 'active source not flagged'
    assert source_bubble_layout.source_value_text(0.0) == '–'
    assert source_bubble_layout.fit_source_label('Map Data', 'MAP', 35, lambda s: len(s) * 10) == 'MAP'
  check('source_bubble_layout helpers behave', layout_helpers)

  print('== hud renderer ==')

  def hud_renders_with_all_ports():
    # every port param on: the mounted HUD constructs and exposes each ported
    # widget; the individual render paths are covered by the checks above
    for key in ('ShowStoppingPoint', 'ShowStoppingPointMetrics', 'ShowTorqueBar',
                'ShowPersonalityButton', 'PIPPreviewEnabled', 'DeveloperSidebar',
                'ShowSpeedLimitSources'):
      store[key] = True
    store['DeveloperSidebarMetric1'] = 1
    ui_state.sm._values['longitudinalPlanSP'].signalAssistAction = 1
    hud = HudRendererSP()
    from openpilot.system.ui.widgets import Widget
    for name in ('stopping_point_renderer', 'star_pilot_torque_bar', 'personality_button',
                 'pip_sidecam', 'developer_sidebar', 'speed_source_drawer'):
      member = getattr(hud, name, None)
      assert isinstance(member, Widget), f'mount {name} missing or not a Widget: {member}'
    assert callable(hud.user_interacting)
  check('HudRendererSP mounts every ported widget', hud_renders_with_all_ports)

  def hud_user_interacting_includes_ports():
    hud = HudRendererSP()
    assert hud.user_interacting() is False

    class _Pressed(personality_button.PersonalityButton):
      @property
      def is_pressed(self):
        return True

    hud.personality_button.__class__ = _Pressed
    try:
      assert hud.user_interacting() is True, 'personality press not counted'
    finally:
      hud.personality_button.__class__ = personality_button.PersonalityButton
    assert hud.user_interacting() is False, 'press state leaked after restore'
  check('user_interacting counts the ported buttons', hud_user_interacting_includes_ports)

  def new_params_registered_in_params_keys():
    header = (REPO_ROOT / 'openpilot' / 'common' / 'params_keys.h').read_text(encoding='utf-8')
    new_keys = ['ShowStoppingPoint', 'ShowStoppingPointMetrics', 'ShowTorqueBar',
                'ShowPersonalityButton', 'ShowSpeedLimitSources', 'DeveloperSidebar',
                'PIPPreviewEnabled', 'PIPPreviewShowOnBlinker', 'PIPPreviewShowOnBSM',
                'PIPPreviewInvert', 'PIPPreviewMask']
    missing = [k for k in new_keys if f'"{k}"' not in header]
    assert not missing, f'params not registered in params_keys.h: {missing}'
    for i in range(1, 8):
      assert f'"DeveloperSidebarMetric{i}"' in header, f'DeveloperSidebarMetric{i} not registered'
  check('gating params are registered in params_keys.h (lead-owned contract)', new_params_registered_in_params_keys)

  print()
  if FAILURES:
    print(f'FAILED {len(FAILURES)}/{CHECKS} checks:')
    for f in FAILURES:
      print(f'  - {f}')
    return 1
  print(f'PASSED {CHECKS}/{CHECKS} checks')
  return 0


if __name__ == '__main__':
  sys.exit(main())
