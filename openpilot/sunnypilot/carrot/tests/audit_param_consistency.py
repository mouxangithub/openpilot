"""Audit carrot parameter consistency across the four tables, and flag the two
classes of defect that produced real bugs on the C3.

Three checks, all of which found real problems when first run:

  1. DEFAULTS  - params_keys.h vs config.py vs nav_params.json vs the webui defaults.
     params_keys.h is the value that actually takes effect: UnifiedParams.get() reads
     the system Params first and only falls back to the JSON tables when the key is
     NOT registered. So a mismatch there means the UI shows one value and the car
     runs another - which is exactly what happened to MyDrivingMode (running Eco,
     displayed Normal), TrafficLightDetectMode and AutoNaviSpeedDecelRate.

  2. CONSUMERS - every param exposed in a UI must have a reader somewhere outside the
     registration and UI tables. Without this, a user can turn a knob that nothing
     reads. 143 params were in that state.

  3. ENUM BOUNDS - params that index an enum must have a default inside that enum's
     range. MyDrivingMode was registered as 1 with a comment describing a completely
     different mapping than the actual DrivingMode enum.

Run:  python3 openpilot/sunnypilot/carrot/tests/audit_param_consistency.py
Exit code is non-zero if any check fails, so it can gate CI.
"""
from __future__ import annotations

import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
  os.path.abspath(__file__))))))

PARAMS_KEYS = os.path.join(REPO, 'openpilot', 'common', 'params_keys.h')
CONFIG_PY = os.path.join(REPO, 'openpilot', 'sunnypilot', 'carrot', 'config.py')
NAV_JSON = os.path.join(REPO, 'openpilot', 'sunnypilot', 'carrot', 'nav_params.json')
TUNING_API = os.path.join(REPO, 'webui', 'server', 'bridge', 'carrot_tuning_api.py')
NATIVE_ITEMS = os.path.join(REPO, 'openpilot', 'selfdrive', 'ui', 'sunnypilot',
                            'layouts', 'settings', 'carrot_tuning_items.py')
PANEL_CATALOG = os.path.join(REPO, 'webui', 'server', 'bridge', 'panel_catalog.py')
SUNNYLINK_JSON = os.path.join(REPO, 'openpilot', 'sunnypilot', 'sunnylink', 'settings_ui.json')

# Deliberate divergences. Each needs a reason, so a new entry is a conscious act.
DEFAULT_EXEMPT: dict[str, str] = {
  'StopDistanceCarrot': 'retired; registered only so params_migration can merge and remove it',
  'CarrotManUdpPort': 'retired; the port is the CARROT_MAN_UDP_PORT constant',
  'SoundVolumeAdjust': 'params_keys.h is authoritative; the other tables were aligned to it',
  'SoundVolumeAdjustEngage': 'params_keys.h is authoritative; the other tables were aligned to it',
  'CarrotStopDistanceMigrated': 'one-shot migration marker, not a user setting',
  'CarrotUdpPortMigrated': 'one-shot migration marker, not a user setting',
}

# Params exposed in a UI that intentionally have no reader yet, with the reason.
# Keeping this list short is the point: it is the backlog of "knobs that do nothing".
CONSUMER_EXEMPT: dict[str, str] = {}

# Params whose value indexes a Python enum, and the enum's valid values.
ENUM_BOUNDS: dict[str, tuple[int, int, str]] = {
  'MyDrivingMode': (1, 4, 'DrivingMode: 1=Eco, 2=Safe, 3=Normal, 4=High'),
  'MyDrivingModeAuto': (0, 2, 'auto driving-mode detector: 0/1/2'),
}

SKIP_DIRS = ('__pycache__', '.git', 'node_modules', 'tinygrad_repo', 'third_party',
             # Not the fork's driving source: the `ai/` workbench tree and the tool's own
             # scratch state both write params of their own, and neither is part of the
             # carrot surface this audit governs.
             'ai', '.workbuddy', 'artifacts', 'sessions')

# A one-shot migration read is not a consumer for this purpose.
#
# params_migration reads retired keys precisely BECAUSE they are retired - to merge or
# clear them. Counting that as a reader made the audit report CarrotManUdpPort as
# healthy while its webui control was still on screen driving nothing, which is
# exactly the defect the check exists to catch. A file that only reads params in order
# to retire them must not mask a dead UI control.
MIGRATION_FILES = ('params_migration.py',)

# Helpers that read a param whose name is passed as a literal argument. Listed
# explicitly rather than matched as "any call with a quoted argument": the loose form
# also swallows declaration tables such as `_Field("kmap_enabled", ...)` and
# `option_item_sp(param='X')`, and would re-report a dead knob as healthy.
#
#   long_mpc.py::_read_tuning_float(_TUNING_PARAMS, "LongitudinalMpcTuningX", default)
#   hardware/comma/modem.py::_read_param("GsmApn") / self._param("GsmApn")
#   recovery/server.py::_read_param("DongleId")
#
# Add a name here when a new indirect access pattern appears, and say where it lives.
READER_HELPERS = (
  '_read_tuning_float',
  '_read_tuning_int',
  '_read_tuning_bool',
  '_read_param',
  '_read_param_value',
  '_param',
)


def read(path: str) -> str:
  with open(path, encoding='utf-8') as f:
    return f.read()


def parse_params_keys() -> dict[str, str]:
  """name -> registered default (as written in params_keys.h).

  The body alternates runs of non-brace/non-quote characters with quoted strings, so a
  default that itself contains a brace is still parsed. The naive `[^}]*` form silently
  dropped every such entry - `NavDestination` defaults to `"{}"` and was reported as
  unregistered by the write-side check, which is what surfaced this.

  The default is the FIRST quoted string, not the last: an entry may carry a stock value
  after it (`{FLAGS, TYPE, "0", "15.5", 2, SETTINGS_ADVANCED}`), and reading the last
  quoted string would then quietly compare the stock value as if it were the default.
  """
  out: dict[str, str] = {}
  body = r'[^{}"]*(?:"[^"]*"[^{}"]*)*'
  for m in re.finditer(r'\{"([A-Za-z_][A-Za-z0-9_]*)",\s*\{(' + body + r')\}\}', read(PARAMS_KEYS)):
    name, inner = m.group(1), m.group(2)
    d = re.search(r'"([^"]*)"', inner)
    out[name] = d.group(1) if d else ''
  return out


def parse_tuning_levels() -> dict[str, int]:
  """name -> declared tuning_level, for the keys that declare one.

  Only the tail of the attribute list is inspected (`..., <stock>, <level>,
  <tier>`), so a default that happens to look like a number cannot be mistaken
  for a level. Keys that declare nothing are absent from the result rather
  than reported as 0: "declares nothing" and "declares not-a-knob" are
  different claims and the audit should be able to tell them apart.
  """
  out: dict[str, int] = {}
  body = r'[^{}"]*(?:"[^"]*"[^{}"]*)*'
  tail = re.compile(r',\s*(?:std::nullopt|"[^"]*")\s*,\s*(\d+)\s*,\s*(SETTINGS_\w+)\s*$')
  for m in re.finditer(r'\{"([A-Za-z_][A-Za-z0-9_]*)",\s*\{(' + body + r')\}\}', read(PARAMS_KEYS)):
    found = tail.search(m.group(2).strip())
    if found:
      out[m.group(1)] = int(found.group(1))
  return out


def parse_config_py() -> dict[str, object]:
  """_DEFAULT_NAV_PARAMS from config.py, without importing it."""
  src = read(CONFIG_PY)
  i = src.find('_DEFAULT_NAV_PARAMS')
  if i < 0:
    return {}
  j = src.find('{', i)
  depth, k, quote = 0, j, None
  while k < len(src):
    c = src[k]
    if quote:
      if c == '\\':
        k += 1
      elif c == quote:
        quote = None
    elif c in '"\'':
      quote = c
    elif c == '{':
      depth += 1
    elif c == '}':
      depth -= 1
      if depth == 0:
        break
    k += 1
  block = src[j:k + 1]
  out: dict[str, object] = {}
  for m in re.finditer(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:\s*([^,\n]+)', block):
    raw = m.group(2).strip()
    try:
      out[m.group(1)] = json.loads(raw)
    except json.JSONDecodeError:
      out[m.group(1)] = raw
  return out


def norm(v: object) -> str:
  """Normalise for comparison: 3, 3.0, '3' and b'3' are the same setting."""
  if isinstance(v, bool):
    return '1' if v else '0'
  if isinstance(v, (int, float)):
    return str(int(v)) if float(v).is_integer() else str(v)
  s = str(v).strip().strip('"\'')
  try:
    f = float(s)
    return str(int(f)) if f.is_integer() else s
  except ValueError:
    return s


def carrot_params(pk: dict[str, str]) -> set[str]:
  """Params that belong to the carrot tuning surface (by naming convention)."""
  prefixes = ('Carrot', 'MyDriving', 'Auto', 'TFollow', 'Lead', 'DynamicTFollow', 'LatSuspend',
              'EnableSpeedTF', 'Traffic', 'StopDistance', 'AChange', 'CruiseMax', 'CruiseEco',
              'JLead', 'LatMeter', 'SameSpi', 'Vehicle', 'Cluster', 'Sound', 'Show', 'Use',
              'AdjustLane', 'AlwaysLateral', 'ApplyModel', 'AutoGas', 'AutoNavi', 'LaneChange',
              'LongTuning', 'LatMpc', 'LateralTorque', 'LatSmooth', 'PathOffset', 'Steer',
              'Camera', 'CustomSR', 'EnableRadar', 'EnableCorner', 'Hardware', 'Hyundai',
              'Mute', 'Onnx', 'Record', 'Share', 'SoftHold', 'Software', 'SpeedFrom',
              'VEgo', 'Canfd', 'CruiseButton', 'CruiseGap', 'CruiseOn', 'CruiseSpeed',
              'Paddle', 'CancelButton', 'LfaButton', 'MaxTimeOffroad', 'AutoSpeedUpto',
              'AutoRoadSpeedAdjust', 'AutoTurn', 'AutoFork', 'AutoDoFork', 'AutoKeep',
              'AutoUp', 'RoadType', 'DisableDM', 'DisableBlindSpot', 'LongitudinalMpc')
  return {k for k in pk if k.startswith(prefixes)}


def ui_exposed_params() -> set[str]:
  """Params reachable from a UI: native carrot items, native navigation, webui panels.

  Also includes the bare-string key lists, which the widget-form scans miss:

    * ``CARROT_TUNING_UNAVAILABLE`` in ``panel_catalog.py`` - keys the panel deliberately
      does not render. Including them is the point: without this the "no reader" check
      silently skipped every key that had been hidden, which is how a batch of
      opendbc-layer carrot keys stayed hidden and dead at the same time. A hidden knob
      with no reader is still a knob advertising nothing.

  The ``carrot_tuning_api.py`` whitelist is deliberately NOT included. It carries ~190
  keys and only its widget-rendered subset has a reader in this tree; treating the whole
  list as UI-reachable reported 114 "no reader" findings, which is a description of the
  whitelist's breadth rather than a defect list. Keys there without a reader are visible
  through the webui's generic editor, and that is a separate question from whether a
  dedicated knob exists.
  """
  exposed: set[str] = set()
  for path in (NATIVE_ITEMS,):
    if os.path.exists(path):
      exposed |= set(re.findall(r"param='([A-Za-z0-9_]+)'", read(path)))
      exposed |= set(re.findall(r'param="([A-Za-z0-9_]+)"', read(path)))
  if os.path.exists(PANEL_CATALOG):
    src = read(PANEL_CATALOG)
    exposed |= set(re.findall(r'"param":\s*"([A-Za-z0-9_]+)"', src))
    # the hidden list, as bare strings
    m = re.search(r'CARROT_TUNING_UNAVAILABLE.*?=\s*frozenset\(\{(.*?)\}\)', src, re.S)
    if m:
      exposed |= set(re.findall(r'"([A-Za-z0-9_]+)"', m.group(1)))
  return exposed


_READ_INDEX: set[str] | None = None


def _build_read_index() -> set[str]:
  """Every param name this tree reads, in one pass over the repo.

  Built once and cached. The per-name version of this walked the whole tree for each
  of ~300 params, which on Windows never finished; the index makes has_reader() a set
  lookup and keeps the semantics identical.
  """
  surface = (os.path.basename(PARAMS_KEYS), os.path.basename(CONFIG_PY), os.path.basename(NAV_JSON),
             os.path.basename(TUNING_API), os.path.basename(NATIVE_ITEMS),
             os.path.basename(PANEL_CATALOG))
  # Python accessors AND the C++ ones. Several params are consumed only from C++
  # (RecordFront is read in loggerd.h), so a Python-only scan reports a false
  # positive and would push a working setting out of the UI.
  py_pat = re.compile(r'\.(?:get|get_bool|get_int|get_float|get_str)\s*\(\s*["\']([A-Za-z_][A-Za-z0-9_]*)["\']')
  cpp_pat = re.compile(r'(?:getBool|getInt|getFloat|get)\s*\(\s*"([A-Za-z_][A-Za-z0-9_]*)"')
  helper_pat = re.compile(r'\b(?:' + '|'.join(READER_HELPERS) +
                          r')\s*\(\s*[^()\n]*["\']([A-Za-z_][A-Za-z0-9_]*)["\']')
  const_def_pat = re.compile(r'^([A-Z_][A-Z0-9_]*)\s*=\s*["\']([A-Za-z_][A-Za-z0-9_]*)["\']', re.M)
  const_use_pat = re.compile(r'\.(?:get|get_bool|get_int|get_float|get_str)\s*\(\s*([A-Z_][A-Z0-9_]*)\b')

  found: set[str] = set()
  for root, dirs, files in os.walk(REPO):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for fn in files:
      if fn in surface or fn in MIGRATION_FILES:
        continue
      is_py, is_cpp = fn.endswith('.py'), fn.endswith(('.h', '.cc', '.cpp'))
      if not (is_py or is_cpp):
        continue
      p = os.path.join(root, fn)
      if '/tests/' in p.replace(os.sep, '/') or fn.startswith('test_'):
        continue
      try:
        src = read(p)
      except (OSError, UnicodeDecodeError):
        continue
      found.update((py_pat if is_py else cpp_pat).findall(src))
      if is_py:
        found.update(helper_pat.findall(src))
        # `PARAM = "X"` at module scope, handed to an accessor by name.
        by_const = dict(const_def_pat.findall(src))
        if by_const:
          found.update(by_const[c] for c in const_use_pat.findall(src) if c in by_const)
  return found


def has_reader(name: str) -> bool:
  """True if any non-surface file reads this param.

  Three access forms are recognised, because this tree uses all three and an audit
  that understands only the first one reports working settings as dead:

    1. direct accessor   ``params.get_int("X")`` / ``getBool("X")`` (C++)
    2. reader helper     ``_read_tuning_float(p, "X", default)``, ``_read_param("X")``
    3. module constant   ``PARAM = "X"`` ... ``params.get_bool(PARAM)``

  Forms 2 and 3 exist for ``long_mpc.py``'s ``LongitudinalMpcTuning*`` block and
  ``lead_forecast/forecast.py``'s ``LeadForecast``; both used to be reported as orphans.

  The helper list is an explicit allowlist on purpose. Matching "any call with a
  quoted argument" would swallow declaration tables - ``_Field("kmap_enabled", ...)``
  in ``web_settings.py``, ``option_item_sp(param='X')`` - and re-report a genuinely
  dead knob as healthy. A false negative is worse here than a false positive, so a
  new indirect access pattern must be added to READER_HELPERS deliberately.
  """
  global _READ_INDEX
  if _READ_INDEX is None:
    _READ_INDEX = _build_read_index()
  return name in _READ_INDEX


def main() -> int:
  pk = parse_params_keys()
  cfg = parse_config_py()
  nav = json.loads(read(NAV_JSON))
  api = {}
  if os.path.exists(TUNING_API):
    for m in re.finditer(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:\s*\(\s*"[a-z]+"\s*,\s*([^)]+)\)', read(TUNING_API)):
      api[m.group(1)] = m.group(2).strip().strip('"\'')

  carrot = carrot_params(pk)
  failures: list[str] = []

  # ---- 1. defaults across tables ------------------------------------------
  print('== 1. default consistency (params_keys.h is the one that takes effect) ==')
  mismatches = 0
  for name in sorted(carrot):
    if name in DEFAULT_EXEMPT:
      continue
    pk_v = norm(pk[name])
    for label, table in (('config.py', cfg), ('nav_params.json', nav), ('carrot_tuning_api', api)):
      if name not in table:
        continue
      other = norm(table[name])
      # empty-string defaults and bool/int pairs are compared loosely
      if pk_v != other and not (pk_v in ('', '0') and other in ('', '0')):
        print(f'  MISMATCH {name:34s} params_keys={pk_v!r:8s} {label}={other!r}')
        mismatches += 1
        failures.append(f'default mismatch: {name} (params_keys={pk_v}, {label}={other})')
  print(f'  {mismatches} mismatch(es)' + ('' if mismatches else ' - all tables agree'))
  print()

  # ---- 2. enum bounds -----------------------------------------------------
  print('== 2. enum bounds ==')
  bad_enum = 0
  for name, (lo, hi, desc) in ENUM_BOUNDS.items():
    if name not in pk:
      print(f'  SKIP {name} (not registered)')
      continue
    v = norm(pk[name])
    try:
      iv = int(v)
    except ValueError:
      print(f'  BAD  {name} default {v!r} is not an int')
      bad_enum += 1
      failures.append(f'enum bound: {name} default {v!r} is not an int')
      continue
    ok = lo <= iv <= hi
    print(f'  {"ok  " if ok else "BAD "} {name:24s} default={iv} valid=[{lo},{hi}]  ({desc})')
    if not ok:
      bad_enum += 1
      failures.append(f'enum bound: {name} default {iv} outside [{lo},{hi}]')
  print(f'  {bad_enum} out of range' if bad_enum else '  all in range')
  print()

  # ---- 3. UI-exposed params must have a reader ---------------------------
  print('== 3. UI-exposed params with no reader ==')
  exposed = ui_exposed_params()
  exposed_carrot = sorted(exposed & carrot)
  orphans = []
  for name in exposed_carrot:
    if name in CONSUMER_EXEMPT:
      continue
    if not has_reader(name):
      orphans.append(name)
  print(f'  {len(exposed_carrot)} carrot params exposed in a UI')
  if not orphans:
    print('  every exposed param has a reader')
    print()
  else:
    # Report the census, but only FAIL on the families that are supposed to work.
    #
    # Widening ui_exposed_params() to include the hidden list took this from "0
    # findings" to ~107, which is the honest number and not a defect count: most are
    # keys for subsystems this fork never ported (the cluster HUD, YouTube, the ONNX
    # lane/BSD stack) or opendbc-layer carrot features awaiting a port. They are known
    # and tracked in artifacts/carrot_control_audit/cp_sp_opendbc_integration_gaps_*.md.
    #
    # A gate that is permanently red gets ignored, so the split is explicit: known
    # unported prefixes are reported and counted, everything else fails.
    UNPORTED_PREFIXES = (
      # carrot subsystems this fork never carried
      'ClusterHud', 'ClusterNaviMap', 'CarrotYouTube', 'CarrotNaviHudMap',
      'CarrotTireTrajectory', 'OnnxBsd', 'OnnxLane',
      # carrot knobs whose consumer lives in cp's opendbc layer, which this fork does
      # not carry - see artifacts/carrot_control_audit/cp_sp_opendbc_integration_gaps_*.md
      'CarrotCruise', 'CustomSteer', 'CustomSR', 'CruiseButton', 'CruiseMaxVals',
      'CruiseOnDist', 'CruiseSpeed', 'LeadAccelResponse', 'LongTuning',
      'LatMpc', 'LateralTorque', 'LatSmooth', 'LaneChange', 'Lfa', 'Steer',
      'CarrotCurveSpeed', 'CarrotHudInfo',
      # stock openpilot / sunnypilot display and device keys: the UI reads these through
      # paths this scan does not model (widget state, C++, soundd), so "no reader" here
      # does not mean dead. Listed so they do not mask a real carrot finding.
      'Show', 'Mute', 'Record', 'Share', 'SoftwareMenu', 'UseWideCamera',
      'SoundLanguage', 'PathOffset', 'AdjustLaneOffset', 'DisableMinSteerSpeed',
      'VEgoStopping', 'HardwareC3xLite', 'AlwaysLateral', 'ApplyModelSpeed',
      'AutoEngage', 'AutoTurnInNotRoadEdge', 'CameraYawTrimDeg', 'CancelButtonMode',
      'ContinuousLaneChange', 'NewLaneWidthDiff', 'StockBlinkerCtrl', 'BsdDelayTime',
      'SideRadarMinDist', 'CruiseGapLevels', 'LaneChangeBsd', 'UseLaneLineSpeed',
      'AutoGas', 'Canfd',
    )
    UNPORTED_EXACT = frozenset((
      'HDPuse', 'IsLdwsCar', 'HyundaiCameraSCC', 'EnableCornerRadar', 'MaxAngleFrames',
      'LongTuningKf', 'LongTuningKiV', 'LongTuningKpV',
    ))
    known = [n for n in orphans if n.startswith(UNPORTED_PREFIXES) or n in UNPORTED_EXACT]
    action = [n for n in orphans if n not in known]

    print(f'  {len(orphans)} have NO reader (the user can change them and nothing happens)')
    print(f'    {len(known)} belong to subsystems this fork has not ported (reported, not failed):')
    for name in known:
      print(f'      {name}')
    if action:
      print(f'    {len(action)} are NOT in a known-unported family - investigate these:')
      for name in action:
        print(f'      {name}')
      failures.append(f'{len(action)} UI-exposed params have no reader and are not a known unported family')
    else:
      print('    every one of them is a known-unported family')
    print()

  # ---- 4. UI ranges must be able to reach the values the code branches on ----
  print('== 4. UI ranges vs the values the code actually uses ==')
  #
  # Several carrot params are enum-like and the code has branches for the last value,
  # but the UI max was copied one short - so that branch was unreachable. Four of these
  # were off by one (the code needs 3, the UI stopped at 2), which silently removed a
  # feature from the picker.
  REQUIRED = {
    'VehicleSpeedCameraControlMode': 3,
    'AutoNaviSpeedCtrlMode': 3,
    'TurnSpeedControlMode': 3,
    'AutoTurnControl': 3,
  }
  range_bad = 0
  for name, needed in REQUIRED.items():
    if name not in pk:
      print(f'  SKIP {name} (not registered)')
      continue
    nat = read(NATIVE_ITEMS)
    m = re.search(r"param='" + name + r"', min_value=\d+, max_value=(\d+)", nat)
    if not m:
      print(f'  SKIP {name} (no native control)')
      continue
    ui_max = int(m.group(1))
    ok = ui_max >= needed
    print(f'  {"ok  " if ok else "BAD "} {name:32s} native max={ui_max} needs>={needed}')
    if not ok:
      range_bad += 1
      failures.append(f'UI range: {name} max {ui_max} cannot reach {needed}')

  # MyDrivingMode indexes the DrivingMode enum (1..4); 0 and 5 silently fell back.
  m = re.search(r"param='MyDrivingMode', min_value=(\d+), max_value=(\d+)", read(NATIVE_ITEMS))
  if m:
    lo, hi = int(m.group(1)), int(m.group(2))
    ok = (lo, hi) == (1, 4)
    print(f'  {"ok  " if ok else "BAD "} MyDrivingMode                    native range=[{lo},{hi}] expected=[1,4]')
    if not ok:
      range_bad += 1
      failures.append(f'UI range: MyDrivingMode [{lo},{hi}] should be [1,4] (the enum)')
  print(f'  {range_bad} out of range' if range_bad else '  all UI ranges reachable')
  print()

  # ---- 5. the three UI surfaces must agree on what is hidden ----
  print('== 5. visibility across the three UIs ==')
  #
  # webui has CARROT_TUNING_UNAVAILABLE; the native page is hand-written build_*
  # functions; sunnylink is compiled from YAML. Nothing kept them in step, so a param
  # hidden in one could stay tappable in another - which is how the seven CruiseMaxVals
  # knobs survived in sunnylink long after webui hid them and their only reader was
  # deleted. This check is what makes the three surfaces a single decision.
  nat_src = read(NATIVE_ITEMS)
  sun_src = read(SUNNYLINK_JSON) if os.path.exists(SUNNYLINK_JSON) else ''

  hidden_webui = set()
  m = re.search(r'CARROT_TUNING_UNAVAILABLE.*?=\s*frozenset\(\{(.*?)\}\)', read(PANEL_CATALOG), re.S)
  if m:
    hidden_webui = set(re.findall(r'"(\w+)"', m.group(1)))

  native_visible = set(re.findall(r"param='([A-Za-z0-9_]+)'", nat_src))
  sunnylink_visible = set(re.findall(r'"key":\s*"([A-Za-z0-9_]+)"', sun_src))

  leaks = []
  for name in sorted(hidden_webui):
    if name in native_visible:
      leaks.append(f'{name} (native)')
    if name in sunnylink_visible:
      leaks.append(f'{name} (sunnylink)')
  if leaks:
    print(f'  {len(leaks)} param(s) hidden in webui but still visible elsewhere:')
    for l in leaks:
      print(f'    {l}')
    failures.append(f'visibility: {len(leaks)} params hidden in webui but visible in another UI')
  else:
    print(f'  all {len(hidden_webui)} webui-hidden params are hidden elsewhere too')

  # A carrot param that no UI shows at all is worth knowing about, but not a failure:
  # it may be deliberately internal (a killswitch read in code only).
  all_surfaces = native_visible | sunnylink_visible
  invisible_everywhere = [n for n in sorted(carrot)
                          if n not in all_surfaces and n not in hidden_webui
                          and not n.endswith('Migrated')]
  print(f'  {len(invisible_everywhere)} carrot param(s) visible in no UI ' +
        '(informational; may be internal killswitches)')
  print()

  # ---- 6. writers must not name an unregistered param ----
  print('== 6. params written by code but not registered ==')
  #
  # The mirror image of section 3. There, a knob nothing reads is useless; here, a write
  # to a key that is not in params_keys.h is worse than useless - `check_key()` raises
  # UnknownKeyName, and set_param_value() only falls back to the raw-file writer when it
  # has a settings definition (`p is not None`). With no definition it re-raises, so the
  # caller reports failure *after* the other writes in its loop have already landed.
  #
  # That is exactly how /api/intro/apply_preset came to answer 500 on every device while
  # half-applying the preset. See tests/test_carrot_intro_presets.py.
  #
  # Only literal key names are matched. A write through a variable cannot be resolved
  # statically, and guessing would produce noise that gets ignored.
  write_pat = re.compile(r'\.(?:put|put_bool|put_int|put_float|put_str)\(\s*["\']([A-Za-z_][A-Za-z0-9_]*)["\']')
  write_cpp_pat = re.compile(r'(?:putBool|putInt|putFloat|put)\(\s*"([A-Za-z_][A-Za-z0-9_]*)"')
  # set_param_value("X", ...) / set_param_value(name=... ) - only the literal form.
  spv_pat = re.compile(r'set_param_value\(\s*["\']([A-Za-z_][A-Za-z0-9_]*)["\']')
  write_const_use = re.compile(r'\.(?:put|put_bool|put_int|put_float|put_str)\(\s*([A-Z_][A-Z0-9_]*)\b')
  const_def = re.compile(r'^([A-Z_][A-Z0-9_]*)\s*=\s*["\']([A-Za-z_][A-Za-z0-9_]*)["\']', re.M)

  unregistered: dict[str, list[str]] = {}
  for root, dirs, files in os.walk(REPO):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for fn in files:
      if fn == os.path.basename(PARAMS_KEYS):
        continue
      is_py, is_cpp = fn.endswith('.py'), fn.endswith(('.h', '.cc', '.cpp'))
      if not (is_py or is_cpp):
        continue
      path = os.path.join(root, fn)
      if '/tests/' in path.replace(os.sep, '/') or fn.startswith('test_'):
        continue
      try:
        src = read(path)
      except (OSError, UnicodeDecodeError):
        continue
      names = set(write_pat.findall(src)) | set(spv_pat.findall(src))
      if is_cpp:
        names |= set(write_cpp_pat.findall(src))
      else:
        by_const = dict(const_def.findall(src))
        if by_const:
          names |= {by_const[c] for c in write_const_use.findall(src) if c in by_const}
      for n in names:
        if n not in pk:
          unregistered.setdefault(n, []).append(os.path.relpath(path, REPO).replace(os.sep, '/'))

  if unregistered:
    print(f'  {len(unregistered)} param(s) are written but not declared in params_keys.h:')
    for n in sorted(unregistered):
      print(f'    {n:34s} {unregistered[n][0]}')
      failures.append(f'unregistered writer: {n} (written in {unregistered[n][0]})')
  else:
    print('  every param written through a literal key name is declared')
  print()

  print('=' * 68)
  if failures:
    print(f'FAILED: {len(failures)} issue(s)')
    return 1
  print('PASSED')
  return 0


if __name__ == '__main__':
  sys.exit(main())
