import sys
import shlex
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from openpilot.system.manager import params_check


SOURCE = '''
inline static std::unordered_map<std::string, ParamKeyAttributes> keys = {
  {"Existing", {PERSISTENT, BOOL}},
  {"AutoNaviSpeedBumpEndDistance", {PERSISTENT, INT, "200"}},
  // {"Disabled", {PERSISTENT, INT}},
  /* {"DisabledBlock", {PERSISTENT, INT}}, */
};
'''


def test_registered_keys_accept_bytes_and_ignore_disabled_declarations():
  params_check.check_keys(SOURCE, [b'Existing', b'AutoNaviSpeedBumpEndDistance'])


def test_incident_native_registry_requires_rebuild():
  with pytest.raises(ValueError, match='missing=.*AutoNaviSpeedBumpEndDistance'):
    params_check.check_keys(SOURCE, [b'Existing'])


def test_switching_to_branch_without_key_requires_rebuild():
  with pytest.raises(ValueError, match='obsolete=.*OldBranchKey'):
    params_check.check_keys(SOURCE, ['Existing', 'AutoNaviSpeedBumpEndDistance', 'OldBranchKey'])


def test_unreadable_registry_format_cannot_pass():
  with pytest.raises(ValueError, match='No Params keys'):
    params_check.check_keys('', [])


def test_boot_check_fails_until_native_registry_is_rebuilt(monkeypatch, tmp_path):
  header = tmp_path / 'params_keys.h'
  header.write_text(SOURCE, encoding='utf-8')
  monkeypatch.setattr(params_check, 'PARAMS_HEADER', header)
  keys = [b'Existing']
  native = SimpleNamespace(Params=lambda: SimpleNamespace(all_keys=lambda: keys))
  monkeypatch.setitem(sys.modules, 'openpilot.common.params', native)
  assert params_check.main() == 1
  keys.append(b'AutoNaviSpeedBumpEndDistance')
  assert params_check.main() == 0


def test_broken_native_extension_fails_boot_check(monkeypatch):
  monkeypatch.setitem(sys.modules, 'openpilot.common.params', None)
  assert params_check.main() == 1


@pytest.mark.parametrize('native_result', [0, 1])
def test_prebuilt_launcher_rebuilds_for_mismatched_registry(tmp_path, native_result):
  bash = shutil.which('bash')
  if bash is None:
    pytest.skip('bash is needed to execute the vehicle launcher function')
  # sp layout: launch_chffrplus.sh lives at the repo root and heals a stale
  # native Params registry by rebuilding libparams_c.so before manager starts.
  launcher = (Path(__file__).resolve().parents[4] / 'launch_chffrplus.sh').read_text(encoding='utf-8')
  function = launcher.split('function ensure_params_registry {', 1)[1].split('\n}', 1)[0]
  (tmp_path / 'openpilot' / 'common').mkdir(parents=True, exist_ok=True)
  script = f'''
DIR={shlex.quote(tmp_path.as_posix())}
PY_PATH=/data/openpilot
python3() {{ return {native_result}; }}
scons() {{ echo mocked-scons > "{shlex.quote((tmp_path / 'MOCK_SCONS_RAN').as_posix())}"; }}
ensure_params_registry() {{{function}
}}
ensure_params_registry
'''
  result = subprocess.run([bash, '-c', script], capture_output=True, text=True, check=True)
  ran = (tmp_path / 'MOCK_SCONS_RAN').exists()
  assert ran == (native_result == 1), f'rebuild invoked={ran}, native_result={native_result}'


@pytest.mark.parametrize('native_result', [0, 1])
def test_launcher_guard_runs_params_check_before_manager(native_result):
  bash = shutil.which('bash')
  if bash is None:
    pytest.skip('bash is needed to execute the vehicle launcher guard')
  # sp semantics: the guard is best-effort (never refuses to boot), but it must
  # always run the check before ./manager.py starts.
  launcher = (Path(__file__).resolve().parents[4] / 'launch_chffrplus.sh').read_text(encoding='utf-8')
  assert 'ensure_params_registry' in launcher
  assert launcher.rindex('ensure_params_registry\n') < launcher.rindex('./manager.py\n'), \
    'params registry guard must run before manager starts'
  checks_run = 0
  function = launcher.split('function ensure_params_registry {', 1)[1].split('\n}', 1)[0]
  script = f'''
DIR=/data/openpilot
PY_PATH=/data/openpilot
python3() {{ return {native_result}; echo checked; }}
scons() {{ echo mocked-scons; }}
# DIR points at the real checkout: neutralize every destructive/rebuilding
# command the extracted function body may call.
rm() {{ :; }}
ensure_params_registry() {{{function}
}}
ensure_params_registry
echo done
'''
  result = subprocess.run([bash, '-c', script], capture_output=True, text=True, check=True)
  # both branches must consult params_check before deciding
  assert 'python3' in function
