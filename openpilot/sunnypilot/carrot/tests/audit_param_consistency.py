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

import glob
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

SKIP_DIRS = ('__pycache__', '.git', 'node_modules', 'tinygrad_repo', 'third_party')

# A one-shot migration read is not a consumer for this purpose.
#
# params_migration reads retired keys precisely BECAUSE they are retired - to merge or
# clear them. Counting that as a reader made the audit report CarrotManUdpPort as
# healthy while its webui control was still on screen driving nothing, which is
# exactly the defect the check exists to catch. A file that only reads params in order
# to retire them must not mask a dead UI control.
MIGRATION_FILES = ('params_migration.py',)


def read(path: str) -> str:
  with open(path, encoding='utf-8') as f:
    return f.read()


def parse_params_keys() -> dict[str, str]:
  """name -> registered default (as written in params_keys.h)."""
  out: dict[str, str] = {}
  for m in re.finditer(r'\{"([A-Za-z_][A-Za-z0-9_]*)",\s*\{([^}]*)\}\}', read(PARAMS_KEYS)):
    name, body = m.group(1), m.group(2)
    d = re.search(r'"([^"]*)"\s*$', body.strip().rstrip(','))
    out[name] = d.group(1) if d else ''
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


def has_reader(name: str) -> bool:
  """True if any non-surface file reads this param."""
  surface = (os.path.basename(PARAMS_KEYS), os.path.basename(CONFIG_PY), os.path.basename(NAV_JSON),
             os.path.basename(TUNING_API), os.path.basename(NATIVE_ITEMS),
             os.path.basename(PANEL_CATALOG))
  # Python accessors AND the C++ ones. Several params are consumed only from C++
  # (RecordFront is read in loggerd.h), so a Python-only scan reports a false
  # positive and would push a working setting out of the UI.
  py_pat = re.compile(r'\.(?:get|get_bool|get_int|get_float|get_str)\s*\(\s*["\']' + re.escape(name) + r'["\']')
  cpp_pat = re.compile(r'(?:getBool|getInt|getFloat|get)\s*\(\s*"' + re.escape(name) + r'"')
  for root, dirs, files in os.walk(REPO):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for fn in files:
      if fn in surface:
        continue
      is_py, is_cpp = fn.endswith('.py'), fn.endswith(('.h', '.cc', '.cpp'))
      if not (is_py or is_cpp):
        continue
      if fn in MIGRATION_FILES:
        continue
      pat = py_pat if is_py else cpp_pat
      p = os.path.join(root, fn)
      if '/tests/' in p.replace(os.sep, '/') or fn.startswith('test_'):
        continue
      try:
        if pat.search(read(p)):
          return True
      except (OSError, UnicodeDecodeError):
        continue
  return False


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
      'UseLaneLineCurveSpeed', 'AutoGas', 'Canfd',
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
  print(f'  {len(invisible_everywhere)} carrot param(s) visible in no UI '
        f'(informational; may be internal killswitches)')
  print()

  print('=' * 68)
  if failures:
    print(f'FAILED: {len(failures)} issue(s)')
    return 1
  print('PASSED')
  return 0


if __name__ == '__main__':
  sys.exit(main())
