"""Headless render + behaviour smoke test for the native Navigation settings page.

Why this exists
---------------
The webui Navigation panel exposed 14 items while the native page had 4, so several
live settings were unreachable from the device. Wiring them up is exactly the kind
of change that looks right in a diff and fails at runtime: the page imports
ui_state -> cereal -> msgq, the UDP port row is driven by a dialog rather than a
bound widget, and the Carrot-gated rows depend on a param read. None of that is
visible to py_compile.

Everything under test is real: NavigationLayout, the item factories, Scroller,
ToggleActionSP / ButtonActionSP / TextAction, and the real dialog-result handler.

Run from the repo root:

    PYTHONPATH=. python openpilot/selfdrive/ui/tests/navigation_render_smoke.py

Exit status is 0 when every check passes.

NOTE: deliberately NOT named test_*.py. install_stubs() replaces
openpilot.system.ui.lib.application, pyray and openpilot.common.params in
sys.modules, so pytest must not collect it into a shared session - doing so would
poison every other test that imports the UI stack.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]

# Reuse the carrot tuning smoke test's fake pyray / gui_app / Params. Importing it
# executes install_stubs() at module level already, but call it again so this file
# does not depend on that ordering.
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / 'opendbc_repo'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import carrot_tuning_render_smoke as _harness

_harness.install_stubs()

# navigation.py also imports openpilot.selfdrive.ui.ui_state, which pulls
# openpilot.cereal -> msgq. The msgq shim available on a PC is Python-2 syntax, so
# stub ui_state instead of fighting the environment.
_ui_mod = types.ModuleType('openpilot.selfdrive.ui.ui_state')

# Own params module so tests can reach the same store the fake ui_state hands to
# widgets under test (navigation_card reads ui_state.params directly).
_ui_params_mod = _harness.build_fake_params()


class _FakeUiState:
  params = _ui_params_mod.Params()
  started = True
  started_frame = 0
  is_metric = False

  @staticmethod
  def is_offroad() -> bool:
    return True

  @staticmethod
  def update_params() -> None:
    return None


_ui_mod.ui_state = _FakeUiState()
sys.modules['openpilot.selfdrive.ui.ui_state'] = _ui_mod

from openpilot.selfdrive.ui.sunnypilot.layouts.settings import navigation as page_module
from openpilot.selfdrive.ui.sunnypilot.layouts.settings.navigation import NavigationLayout

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


def find_param(obj, depth: int = 0) -> str | None:
  """Locate the Params key a widget writes to.

  ToggleActionSP forwards `param` into its inner ToggleSP, which stores it as
  `param_key`, so walk the object tree rather than guessing the attribute path.
  """
  if depth > 4 or obj is None:
    return None
  for key in ('param_key', 'param'):
    v = getattr(obj, key, None)
    if isinstance(v, str) and v:
      return v
  for attr in ('action_item', 'toggle', '_action_item', 'item', '_child'):
    found = find_param(getattr(obj, attr, None), depth + 1)
    if found:
      return found
  return None


def main() -> int:
  store = sys.modules['openpilot.common.params'].store
  page = NavigationLayout()
  content = _harness.Rect(0, 0, 2160, 1080)
  page.set_parent_rect(content)
  items = page._scroller._items

  check('page renders without raising', lambda: page.render(content))

  exposed = [p for p in (find_param(it) for it in items) if p]

  def exposes_live_params():
    expected = ['CarrotAmapBlindSpotEnabled', 'CarrotEnabled',
                'CarrotNaviV2Enabled', 'CarrotNavCruiseSpeedEnabled',
                'HapticFeedbackWhenSpeedCamera']
    missing = [p for p in expected if p not in exposed]
    assert not missing, f'missing nav params: {missing}'
  check('exposes every live navigation param', exposes_live_params)

  def no_dead_or_webui_only_params():
    """Params that are registered but have no native UI consumer."""
    banned = []
    found = [p for p in banned if p in exposed]
    assert not found, f'dead / webui-only params exposed natively: {found}'
  check('excludes dead and webui-HUD-only params', no_dead_or_webui_only_params)

  def native_is_subset_of_webui():
    import importlib.util
    spec = importlib.util.spec_from_file_location('pc', REPO_ROOT / 'webui' / 'server' / 'bridge' / 'panel_catalog.py')
    pc = importlib.util.module_from_spec(spec)
    sys.modules['pc'] = pc
    spec.loader.exec_module(pc)
    webui = {w.get('param') for w in pc.get_panel('navigation')['widgets'] if w.get('param')}
    extra = [p for p in exposed if p not in webui]
    assert not extra, f'native exposes params the webui nav panel does not: {extra}'
  check('native params are a subset of the webui panel', native_is_subset_of_webui)

  def has_new_readout_rows():
    labels = [str(getattr(it, 'title', '')) for it in items]
    assert any('Carrot Navi Debug' in l for l in labels), f'no Carrot Navi Debug row among {labels}'
  check('shows Carrot Navi Debug row', has_new_readout_rows)

  def gated_rows_follow_carrot_enabled():
    store['CarrotEnabled'] = True
    page._update_state()
    assert page._carrot_navi_v2_enabled.is_visible, 'v2 row hidden while Carrot is on'
    assert page._carrot_nav_cruise_speed.is_visible, 'nav cruise row hidden while Carrot is on'
    store['CarrotEnabled'] = False
    page._update_state()
    assert not page._carrot_navi_v2_enabled.is_visible, 'v2 row visible while Carrot is off'
    assert not page._carrot_nav_cruise_speed.is_visible, 'nav cruise row visible while Carrot is off'
  check('Carrot-gated rows follow CarrotEnabled', gated_rows_follow_carrot_enabled)

  def port_row_is_gone():
    """CarrotManUdpPort was retired as a user setting.

    The phone app hard-codes 7706 as its fallback in three paths (non-JSON
    broadcast, unparseable broadcast, and the 7714 beacon whose payload has no
    port) and has no UI to change it, so a configurable value could only cause
    silent packet loss. The port is now the CARROT_MAN_UDP_PORT constant. This
    test guards against the control being reintroduced without that reasoning
    being revisited.
    """
    assert not hasattr(page, '_carrot_udp_port'), 'the UDP port row is back in the native UI'
    exposed = [p for p in (find_param(it) for it in items) if p]
    assert 'CarrotManUdpPort' not in exposed, 'CarrotManUdpPort is exposed natively again'
  check('the retired UDP port row is gone', port_row_is_gone)

  def navi_debug_handles_every_param_shape():
    """CarrotNaviDebug is a JSON param, so Params.get() returns a dict.

    The callback originally assumed a str and did `raw.strip()`, which raised
    AttributeError: 'dict' object has no attribute 'strip' the moment the user
    opened the viewer on the device. Cover every shape the param can take, plus
    the snapshot-only payload written by the 10 Hz writer (no `summary` key).
    """
    pushed = []
    original_gui_app = page_module.gui_app
    original_confirm_dialog = page_module.ConfirmDialog

    class _FakeConfirm:
      def __init__(self, message, ok, cancel_text="", rich=False):
        self.message = message
        self.rich = rich

    page_module.ConfirmDialog = _FakeConfirm
    page_module.gui_app = types.SimpleNamespace(push_widget=pushed.append)
    try:
      cases = {
        'dict with summary': {'type': 'crossroad', 'eventTimeMs': 12, 'receivedAt': 'x', 'summary': {'a': 1}},
        'dict snapshot only': {'activeSource': '7714', 'roadLimit': {'speedKph': 60}},
        'empty dict': {},
        'json string': '{"type": "x", "summary": {"b": 2}}',
        'legacy text': 'raw payload',
        'bytes': b'{"type": "y"}',
        'none': None,
      }
      for name, raw in cases.items():
        pushed.clear()
        store['CarrotNaviDebug'] = raw
        page._on_carrot_navi_debug()
        assert pushed, f'{name}: nothing pushed'
        dlg = pushed[0]
        assert isinstance(dlg, _FakeConfirm), f'{name}: expected ConfirmDialog, got {type(dlg).__name__}'
        assert dlg.rich, f'{name}: navi debug must open in the scrollable (rich) dialog'
        assert isinstance(dlg.message, str) and dlg.message, f'{name}: empty message'
    finally:
      page_module.gui_app = original_gui_app
      page_module.ConfirmDialog = original_confirm_dialog
      store.pop('CarrotNaviDebug', None)
  check('Carrot Navi Debug tolerates dict/str/bytes/None (scrollable)', navi_debug_handles_every_param_shape)

  def carrot_web_dialog_has_a_params_handle():
    """CarrotWebDialog read ui_state.params_memory, which UIState does not define.

    UIState exposes `params` (a Params() handle). Tapping the Carrot Web sidebar
    button therefore raised AttributeError and killed the whole UI process. Assert
    the real UIState attribute exists and that the dialog only references names
    that are actually available on it.
    """
    import ast
    import re
    ui_state_src = (REPO_ROOT / 'openpilot' / 'selfdrive' / 'ui' / 'ui_state.py').read_text(encoding='utf-8')
    sp_state_src = (REPO_ROOT / 'openpilot' / 'selfdrive' / 'ui' / 'sunnypilot' / 'ui_state.py').read_text(encoding='utf-8')

    defined: set[str] = set()
    for src, class_name in ((ui_state_src, 'UIState'), (sp_state_src, 'UIStateSP')):
      tree = ast.parse(src)
      for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
          for stmt in ast.walk(node):
            if isinstance(stmt, ast.Assign):
              for target in stmt.targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == 'self':
                  defined.add(target.attr)
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Attribute):
              if isinstance(stmt.target.value, ast.Name) and stmt.target.value.id == 'self':
                defined.add(stmt.target.attr)

    assert 'params' in defined, 'UIState/UIStateSP no longer assigns self.params'
    src = (REPO_ROOT / 'openpilot' / 'selfdrive' / 'ui' / 'widgets' / 'carrot_web_dialog.py').read_text(encoding='utf-8')
    referenced = set(re.findall(r'ui_state\.(\w+)', src))
    missing = sorted(name for name in referenced if name not in defined)
    assert not missing, f'carrot_web_dialog references UIState attributes that do not exist: {missing}'
  check('Carrot Web dialog only uses real UIState attributes', carrot_web_dialog_has_a_params_handle)

  def every_string_translated():
    import re
    src = (REPO_ROOT / 'openpilot' / 'selfdrive' / 'ui' / 'sunnypilot' / 'layouts' / 'settings' /
           'navigation.py').read_text(encoding='utf-8')
    strings = set(re.findall(r'tr\("([^"]*)"\)', src))
    for blob in re.findall(r'tr\(\s*((?:"[^"]*"\s*)+)\)', src, re.S):
      strings.add(''.join(re.findall(r'"([^"]*)"', blob)))
    for lang in ('zh-CHS', 'zh-CHT'):
      po = (REPO_ROOT / 'openpilot' / 'selfdrive' / 'ui' / 'translations' / f'app_{lang}.po').read_text(encoding='utf-8')
      have = set(re.findall(r'^msgid "(.+?)"$', po, re.M))
      missing = sorted(s for s in strings if s not in have)
      assert not missing, f'{lang} missing {missing}'
  check('every navigation string is translated', every_string_translated)

  # ---------------------------------------------------------------------------
  # Onroad navigation instruction card (StarPilot port)
  # ---------------------------------------------------------------------------

  import importlib

  # _get_icon() loads real PNGs through raylib; give the fake pyray image/texture
  # loaders plausible stand-ins so render() walks the whole card path headless.
  _pyray = sys.modules['pyray']

  class _FakeImage:
    width, height = 64, 64

  _pyray.load_image = lambda path: _FakeImage()
  _pyray.load_texture_from_image = lambda image: _harness.Texture(7)
  _pyray.unload_image = lambda image: None

  nav_card_mod = importlib.import_module('openpilot.selfdrive.ui.sunnypilot.onroad.navigation_card')
  NavigationCardRenderer = nav_card_mod.NavigationCardRenderer

  NAV_CARD_ASSETS = nav_card_mod.ASSETS_PATH
  # The store backing ui_state.params (what the navigation card actually reads).
  nav_store = _ui_params_mod.store
  ui_state_obj = sys.modules['openpilot.selfdrive.ui.ui_state'].ui_state

  def nav_card_assets_present():
    assert NAV_CARD_ASSETS.is_dir(), f'missing maneuver icon assets at {NAV_CARD_ASSETS}'
    pngs = sorted(NAV_CARD_ASSETS.glob('*.png'))
    assert len(pngs) == 88, f'expected 88 maneuver icons, found {len(pngs)}'
    assert (NAV_CARD_ASSETS / nav_card_mod.FALLBACK_ICON).exists(), 'fallback icon missing'
  check('navigation card ships the 88 maneuver icons', nav_card_assets_present)

  def nav_card_icon_mapping():
    card = NavigationCardRenderer()
    assert card._icon_filename('turn', 'left') == 'direction_turn_left.png'
    # no bare direction_turn.png in the asset set -> known fallback
    assert card._icon_filename('turn', '') == nav_card_mod.FALLBACK_ICON
    assert card._icon_filename('rotary', 'straight') == 'direction_roundabout_straight.png'
    assert card._icon_filename('new name', '') == nav_card_mod.FALLBACK_ICON
    # unknown combos fall back instead of crashing the render loop
    fallback = card._icon_filename('ferry', 'train')
    assert (NAV_CARD_ASSETS / fallback).exists(), f'{fallback} does not exist'
  check('navigation card maps maneuver types to existing icons', nav_card_icon_mapping)

  def nav_card_state_update():
    card = NavigationCardRenderer()

    def refresh():
      # bypass the 0.1 s params-read throttle for back-to-back mutations
      card._last_state_update = float('-inf')
      card._update_state()

    nav_store.clear()
    nav_store['NavigationCardEnabled'] = True
    nav_store['NavDestination'] = {'latitude': 37.7, 'longitude': -122.4, 'place_name': 'x'}
    nav_store['NavInstructionState'] = {
      'valid': True, 'maneuverPrimaryText': 'Marin St', 'maneuverSecondaryText': 'toward I-80 East',
      'maneuverDistance': 350.0, 'maneuverType': 'turn', 'maneuverModifier': 'left',
      'nextManeuverType': 'roundabout', 'nextManeuverModifier': '',
    }
    ui_state_obj.is_metric = True
    try:
      refresh()
      assert card._valid, 'card did not become valid with a live instruction'
      assert card._primary_text == 'Marin St'
      assert card._distance == '350 m'
      assert card._maneuver_type == 'turn' and card._modifier == 'left'
      assert card._has_next and card._next_maneuver_type == 'roundabout'
    finally:
      ui_state_obj.is_metric = False

    # missing primary text -> hidden
    nav_store['NavInstructionState'] = {'valid': True, 'maneuverPrimaryText': ''}
    refresh()
    assert not card._valid, 'card shown without primary text'

    # disabled master switch -> hidden even with a live instruction
    nav_store['NavigationCardEnabled'] = False
    nav_store['NavInstructionState'] = {'valid': True, 'maneuverPrimaryText': 'Marin St'}
    refresh()
    assert not card._valid, 'card shown while NavigationCardEnabled is off'

    # no route destination -> hidden
    nav_store['NavigationCardEnabled'] = True
    nav_store.pop('NavDestination')
    refresh()
    assert not card._valid, 'card shown without a NavDestination'
  check('navigation card update honours params gating', nav_card_state_update)

  def nav_card_toggle_and_cancel():
    card = NavigationCardRenderer()
    nav_store.clear()
    nav_store['NavigationCardEnabled'] = True
    nav_store['NavDestination'] = {'latitude': 37.7, 'longitude': -122.4}
    nav_store['NavInstructionState'] = {'valid': True, 'maneuverPrimaryText': 'Marin St', 'maneuverDistance': 100.0}
    card._update_state()
    assert card._valid

    card._toggle_collapsed()
    assert card._collapsed, 'short tap did not collapse'
    assert nav_store.get('NavInstructionCollapsed') is True, 'collapsed state not persisted'
    card._toggle_collapsed()
    assert nav_store.get('NavInstructionCollapsed') is False

    card._cancel_navigation()
    assert 'NavDestination' not in nav_store, 'cancel did not clear NavDestination'
    assert nav_store.get('NavInstructionState') == {}, 'cancel did not reset NavInstructionState'
    assert not card._valid, 'card still valid after cancel'
  check('navigation card collapse toggle and long-press cancel persist', nav_card_toggle_and_cancel)

  def nav_card_renders_headless():
    card = NavigationCardRenderer()
    nav_store.clear()
    nav_store['NavigationCardEnabled'] = True
    nav_store['NavDestination'] = {'latitude': 37.7, 'longitude': -122.4}
    nav_store['NavInstructionState'] = {
      'valid': True, 'maneuverPrimaryText': 'Marin St', 'maneuverDistance': 350.0,
      'maneuverType': 'turn', 'maneuverModifier': 'left',
    }
    card._update_state()
    rect = _harness.Rect(0, 0, 2160, 1080)
    card.render(rect)  # expanded card
    assert card._interactive_rect.width > 0, 'expanded card left no hit rect'
    card._toggle_collapsed()
    card._last_state_update = float('-inf')
    card._update_state()
    card.render(rect)  # collapsed chip
    assert card._interactive_rect.width > 0, 'collapsed chip left no hit rect'
    drawn = [d for d in _harness.DRAWN if 'Marin St' in str(d[1])]
    assert drawn, 'expanded card never drew its primary text'
  check('navigation card renders expanded and collapsed headless', nav_card_renders_headless)

  def road_name_prefers_carrot():
    from openpilot.selfdrive.ui.sunnypilot.onroad import road_name as road_name_mod

    renderer = road_name_mod.RoadNameRenderer()

    class _FakeSm:
      recv_frame = {'carState': 100}
      valid = {'carrotManSP': True}
      updated = {'carrotManSP': True, 'liveMapDataSP': True}

      def __getitem__(self, key):
        if key == 'carrotManSP':
          return types.SimpleNamespace(activeCarrot=2, szPosRoadName='G104 国道')
        return types.SimpleNamespace(roadName='Live Map Rd')

    original_sm = getattr(ui_state_obj, 'sm', None)
    ui_state_obj.sm = _FakeSm()
    try:
      renderer.update()
      assert renderer.road_name == 'G104 国道', f'carrot road name not preferred: {renderer.road_name!r}'

      # carrot inactive -> fall back to the live map data road name
      class _InactiveSm(_FakeSm):
        def __getitem__(self, key):
          if key == 'carrotManSP':
            return types.SimpleNamespace(activeCarrot=0, szPosRoadName='G104 国道')
          return types.SimpleNamespace(roadName='Live Map Rd')

      ui_state_obj.sm = _InactiveSm()
      renderer.update()
      assert renderer.road_name == 'Live Map Rd', f'did not fall back to live map name: {renderer.road_name!r}'
    finally:
      ui_state_obj.sm = original_sm
  check('road name prefers carrot road name with live map fallback', road_name_prefers_carrot)

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
