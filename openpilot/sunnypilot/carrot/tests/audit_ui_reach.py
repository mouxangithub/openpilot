"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Which Carrot switches on the control path can a human actually reach?

The question this answers is the one that made a wired-in longitudinal source look
like dead code: a param read by ``plannerd``/``controlsd`` is not a feature until
there is a control for it somewhere, and there was none for
``CarrotLongitudinalSourceEnabled`` until it was added to the Developer page.

Scope, stated precisely because "no UI entry" is easy to overclaim:

  * **control path** - a ``"Carrot*"`` literal inside ``openpilot/selfdrive/controls``
    or ``openpilot/sunnypilot/selfdrive/controls``, and registered in
    ``params_keys.h``. That is the set that can move the car.
  * **UI entry** - a ``"Carrot*"`` literal inside the on-device settings tree
    (``openpilot/selfdrive/ui``, ``openpilot/sunnypilot/selfdrive/ui``,
    ``openpilot/system/ui``) or the webui panel catalog. The on-device tree is the
    single source of what a person can toggle: the 8088 web panel renders its
    controls by scanning those same pages (``carrot/web_settings.py``), so it adds
    no reach of its own.
  * **not a UI entry** - the ``carrot_tuning_api.py`` whitelist (~190 keys behind
    the generic editor) and ``params_keys.h`` itself. Counting the whitelist would
    make every registered key look reachable and the table pointless.

Anything registered in ``params_keys.h`` is writable over carrot_server's
``POST /api/param_set`` (it validates against the declaration, not a whitelist), so
"no UI entry" means "needs a script or the phone app", not "impossible".

The table is generated, not written: ``test_carrot_ui_reach.py`` regenerates it and
fails when the code and the checked-in copy disagree, so a switch cannot silently
gain or lose its control.

Run:
  python3 openpilot/sunnypilot/carrot/tests/audit_ui_reach.py            # print the table
  python3 openpilot/sunnypilot/carrot/tests/audit_ui_reach.py --write     # rewrite the doc
"""
import os
import re
import sys

from openpilot.sunnypilot.carrot.tests.audit_param_consistency import parse_params_keys, parse_tuning_levels

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
  os.path.abspath(__file__))))))

CONTROL_ROOTS = (
  os.path.join(REPO, 'openpilot', 'selfdrive', 'controls'),
  os.path.join(REPO, 'openpilot', 'sunnypilot', 'selfdrive', 'controls'),
)

UI_ROOTS = (
  os.path.join(REPO, 'openpilot', 'selfdrive', 'ui'),
  os.path.join(REPO, 'openpilot', 'sunnypilot', 'selfdrive', 'ui'),
  os.path.join(REPO, 'openpilot', 'system', 'ui'),
)

# The webui draws its panels from this one file; its params bridge is a generic
# editor, and is excluded on purpose (see the module docstring).
PANEL_CATALOG = os.path.join(REPO, 'webui', 'server', 'bridge', 'panel_catalog.py')

DOC_PATH = os.path.join(REPO, 'docs', 'carrot_no_ui_switches.md')

# Both quote styles matter: `navigation.py` writes param="X", the carrot tuning
# pages write param='X'. Matching only one silently halves the UI surface - which
# is exactly the failure mode this audit exists to prevent.
NAME_RE = re.compile(r'["\'](Carrot[A-Za-z0-9_]+)["\']')

# What each switch does, in one line, taken from the read site rather than from its name.
# A switch without an entry here fails the test: the point is that a human wrote down
# what turning it on does, not that the table has 19 rows.
NOTES = {
  'CarrotAtcBlinkerEnabled': '导航转向指令合成为转向灯，会到车上的真灯',
  'CarrotBrakingGapEnabled': '前车舒适制动项（lead_comfort）进 MPC',
  'CarrotCruiseCoastingEnabled': '巡航超速带内松刹车滑行',
  'CarrotCruiseCoastingPercent': '滑行带的宽度，按百分比',
  'CarrotCutinPredecelEnabled': '旁车切入的提前减速',
  'CarrotCutoutReliefEnabled': '前车切出后解除跟车抑制',
  'CarrotEnabled': 'carrot 导航总开关，地图类功能的前提',
  'CarrotFastRadarEnabled': '用更新的 liveTracks 刷新已锁定的前车（Hyundai）',
  'CarrotGapRecoveryEnabled': '跟车距离被压近之后的恢复',
  'CarrotLateralReadinessEnabled': '起步时挡横向使能，直到横向输入与 CAN 就绪',
  'CarrotLeadPreviewEnabled': '用前车加速度做提前量',
  'CarrotLongitudinalSourceEnabled': '手机目标速度成为第 5 个纵向源；跟车时距、舒适制动与停车点进 MPC',
  'CarrotMapDecelEnabled': '地图限速减速，SCC-M 的三个条件之一',
  'CarrotNavCruiseSpeedEnabled': '导航目标速度限制巡航速度',
  'CarrotSourceTimeoutMs': 'carrot 包的新鲜度上界，超过就判该源失效',
  'CarrotStoppingLeadEnabled': '停住的前车要有距离证据才算起步',
  'CarrotTrafficCongestionEnabled': '拥堵报告折进地图巡航，只降不升',
  'CarrotTrafficLightFusionEnabled': '红绿灯状态融合进纵向计划',
  'CarrotTurnAccelEnabled': '弯道内限制纵向加速度',
}


def _rel(path: str) -> str:
  return os.path.relpath(path, REPO).replace(os.sep, '/')


def _sources(root: str):
  """Python sources that could carry a control or a control's consumer."""
  for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d not in ('__pycache__', 'tests', 'node_modules')]
    for fn in filenames:
      if not fn.endswith('.py') or fn.startswith('test_') or fn.endswith('_smoke.py'):
        continue
      yield os.path.join(dirpath, fn)


def _names_in(path: str) -> set[str]:
  try:
    with open(path, encoding='utf-8') as f:
      return set(NAME_RE.findall(f.read()))
  except (OSError, UnicodeDecodeError):
    return set()


def control_switches() -> dict[str, list[str]]:
  """{param: [files that read it]} for control-path params that are registered."""
  registered = set(parse_params_keys())
  out: dict[str, list[str]] = {}
  for root in CONTROL_ROOTS:
    for path in _sources(root):
      for name in _names_in(path) & registered:
        out.setdefault(name, []).append(_rel(path))
  return {name: sorted(set(paths)) for name, paths in out.items()}


def ui_entries() -> set[str]:
  """Params a person can reach from a drawn control."""
  exposed: set[str] = set()
  for root in UI_ROOTS:
    for path in _sources(root):
      exposed |= _names_in(path)
  exposed |= _names_in(PANEL_CATALOG)
  return exposed


def split_switches() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
  """(reachable, not reachable), each {param: [reading files]}."""
  switches, exposed = control_switches(), ui_entries()
  with_ui = {k: v for k, v in switches.items() if k in exposed}
  without_ui = {k: v for k, v in switches.items() if k not in exposed}
  return with_ui, without_ui


def level_one_gaps() -> list[str]:
  """Declared everyday knobs that no control on the device can reach.

  This is the one rule the tuning_level declaration is allowed to enforce: a
  parameter a person is expected to toggle without reading anything must have
  a control. Level 2 and 3 keys are allowed to be scripting surfaces; level 1
  is not, because "everyday" and "curl only" contradict each other.
  """
  levels = parse_tuning_levels()
  _, without_ui = split_switches()
  return sorted(name for name in without_ui if levels.get(name) == 1)


def _row(name: str, files: list[str], defaults: dict[str, str], levels: dict[str, int]) -> str:
  read_points = ', '.join(f'`{f}`' for f in files)
  level = levels.get(name)
  return f'| `{name}` | `{defaults.get(name, "")}` | {level if level is not None else "-"} | {read_points} | {NOTES.get(name, "")} |'


def _table(rows: dict[str, list[str]], defaults: dict[str, str], levels: dict[str, int]) -> str:
  body = ['| 参数 | 默认 | 层级 | 读点 | 作用 |', '| --- | --- | --- | --- | --- |']
  body += [_row(name, rows[name], defaults, levels) for name in sorted(rows)]
  return '\n'.join(body)


def _level_line(without_ui: dict[str, list[str]], levels: dict[str, int]) -> str:
  """How many unreachable knobs are declared everyday (level 1).

  A level-1 knob with no control is the one defect this table is really
  about: every other unreachable key is arguably a scripting surface, but a
  declared everyday knob that only a curl command can reach is a gap.
  """
  everyday = sorted(name for name in without_ui if levels.get(name) == 1)
  declared = sum(1 for name in without_ui if name in levels)
  if not declared:
    return ''
  if not everyday:
    return f'\n没有入口的 {declared} 个声明了层级，**没有一个是 level 1（日常）**：都只适合脚本或 App。\n'
  return (f'\n没有入口的 {declared} 个声明了层级，其中 **level 1（日常）的有 {len(everyday)} 个**：'
          + '、'.join(f'`{name}`' for name in everyday) + '。这几个值得补 UI 入口。\n')


def _head(with_ui: dict[str, list[str]], without_ui: dict[str, list[str]], levels: dict[str, int]) -> str:
  total = len(with_ui) + len(without_ui)
  return f'''# carrot：控制路径上的开关，哪些在 UI 上够得着

<!-- Generated by openpilot/sunnypilot/carrot/tests/audit_ui_reach.py. Do not edit by hand.
     test_carrot_ui_reach.py regenerates this file and fails when they disagree. -->

控制路径 = `openpilot/selfdrive/controls` 或 `openpilot/sunnypilot/selfdrive/controls` 里读到、
且在 `params_keys.h` 里注册过的 `Carrot*` 参数。UI 入口 = 车机设置树
（`openpilot/selfdrive/ui`、`openpilot/sunnypilot/selfdrive/ui`、`openpilot/system/ui`）
或 webui 的 `panel_catalog.py` 里出现过。8088 网页面板靠扫描车机设置页生成控件，不额外增加可达性。
`carrot_tuning_api.py` 的白名单不算入口，那是通用编辑器。

共 {total} 个：**{len(with_ui)} 个有 UI 入口，{len(without_ui)} 个没有**。

没有入口的那些，仍然可以通过 carrot_server 写参数（`params_keys.h` 注册即允许，不走白名单）：

```
curl -X POST http://<device>:7000/api/param_set \\
     -H "Content-Type: application/json" \\
     -d '{{"name": "CarrotMapDecelEnabled", "value": 1}}'

curl "http://<device>:7000/api/params_bulk?names=CarrotMapDecelEnabled,CarrotTurnAccelEnabled"
```

读点只给文件不给行号：行号一改就漂，用参数名 grep 定位。
'''


def render() -> str:
  defaults = parse_params_keys()
  levels = parse_tuning_levels()
  with_ui, without_ui = split_switches()
  out = _head(with_ui, without_ui, levels)
  out += _level_line(without_ui, levels)
  if with_ui:
    out += f'\n## 有 UI 入口（{len(with_ui)}）\n\n{_table(with_ui, defaults, levels)}\n'
  if without_ui:
    section = f'\n## 没有 UI 入口（{len(without_ui)}），只能走 7000 的 `POST /api/param_set`\n\n'
    out += section + _table(without_ui, defaults, levels) + '\n'
  return out


def main(argv: list[str]) -> int:
  built = render()
  if '--write' in argv:
    os.makedirs(os.path.dirname(DOC_PATH), exist_ok=True)
    with open(DOC_PATH, 'w', encoding='utf-8', newline='\n') as f:
      f.write(built)
    print(f'wrote {_rel(DOC_PATH)}')
    return 0
  sys.stdout.write(built)
  return 0


if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))
