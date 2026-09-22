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

import carrot_tuning_render_smoke as _harness  # noqa: E402

_harness.install_stubs()

# navigation.py also imports openpilot.selfdrive.ui.ui_state, which pulls
# openpilot.cereal -> msgq. The msgq shim available on a PC is Python-2 syntax, so
# stub ui_state instead of fighting the environment.
_ui_mod = types.ModuleType('openpilot.selfdrive.ui.ui_state')


class _FakeUiState:
  params = _harness.build_fake_params().Params()
  started = True

  @staticmethod
  def is_offroad() -> bool:
    return True

  @staticmethod
  def update_params() -> None:
    return None


_ui_mod.ui_state = _FakeUiState()
sys.modules['openpilot.selfdrive.ui.ui_state'] = _ui_mod

from openpilot.selfdrive.ui.sunnypilot.layouts.settings.navigation import NavigationLayout  # noqa: E402
from openpilot.system.ui.widgets import DialogResult  # noqa: E402

CHECKS = 0
FAILURES: list[str] = []


def check(name: str, fn) -> None:
  global CHECKS
  CHECKS += 1
  try:
    fn()
    print(f'  ok  {name}')
  except Exception as e:  # noqa: BLE001
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
    expected = ['AmapMapDataEnabled', 'CarrotAmapBlindSpotEnabled', 'CarrotEnabled',
                'CarrotNaviV2Enabled', 'CarrotWebEnabled', 'CarrotNavCruiseSpeedEnabled']
    missing = [p for p in expected if p not in exposed]
    assert not missing, f'missing nav params: {missing}'
  check('exposes every live navigation param', exposes_live_params)

  def no_dead_or_webui_only_params():
    """CarrotPanel* position the webui HUD; the native UI has no such panel."""
    banned = ['CarrotCurveSpeedEnabled', 'CarrotHudInfoEnabled',
              'CarrotPanelSide', 'CarrotPanelOpacity']
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

  def has_car_model_row():
    labels = [str(getattr(it, 'title', '')) for it in items]
    assert any('Car Model' in l for l in labels), f'no Car Model row among {labels}'
  check('shows the Car Model row', has_car_model_row)

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

  def port_row_shows_state():
    store['CarrotManUdpPort'] = 0
    page._update_state()
    assert page._carrot_udp_port.action_item.value == 'Disabled', page._carrot_udp_port.action_item.value
    store['CarrotManUdpPort'] = 7706
    page._update_state()
    assert page._carrot_udp_port.action_item.value == '7706', page._carrot_udp_port.action_item.value
  check('UDP port row shows Disabled / the port', port_row_shows_state)

  def port_accepts_valid():
    page._on_carrot_udp_port_result(DialogResult.CONFIRM, '7706')
    assert store.get('CarrotManUdpPort') == 7706, store.get('CarrotManUdpPort')
    page._on_carrot_udp_port_result(DialogResult.CONFIRM, '0')
    assert store.get('CarrotManUdpPort') == 0, '0 (listener disabled) must be accepted'
  check('UDP port dialog writes valid values', port_accepts_valid)

  def port_rejects_garbage():
    store['CarrotManUdpPort'] = 7706
    for bad in ('abc', '', '70000', '-1', '3.5', 'not a port', ' '):
      page._on_carrot_udp_port_result(DialogResult.CONFIRM, bad)
      assert store.get('CarrotManUdpPort') == 7706, f'{bad!r} was accepted'
  check('UDP port dialog rejects invalid input', port_rejects_garbage)

  def port_ignores_cancel():
    store['CarrotManUdpPort'] = 7706
    page._on_carrot_udp_port_result(DialogResult.CANCEL, '1234')
    assert store.get('CarrotManUdpPort') == 7706, 'cancel must not write'
  check('UDP port dialog ignores cancel', port_ignores_cancel)

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
