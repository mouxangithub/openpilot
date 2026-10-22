"""Load modules from the repository-root ``tools/`` tree.

The repository keeps analysis experiments in ``tools/`` next to the ``openpilot/``
package, and code inside ``openpilot/`` reaches them with a plain
``from tools.signal_analysis import ...``. That import cannot resolve: the
``openpilot/tools/__init__.py`` marker makes ``tools`` a *regular* package, and a
regular package wins over a namespace package no matter where either one sits on
``sys.path``. Every ``tools.*`` lookup therefore lands in ``openpilot/tools``,
which has no ``signal_analysis`` subpackage.

Loading these files by location keeps the resolution independent of
``PYTHONPATH`` order and of whatever happened to be imported first, so the same
call works under ``python -m unittest``, under a device process launched by the
manager, and in a pytest session.
"""
import importlib.util
import sys
from pathlib import Path

TOOLS_ROOT = Path(__file__).resolve().parents[2] / 'tools'


def load(relative_path: str):
  """Import ``tools/<relative_path>`` by location and cache it under a private name.

  ``relative_path`` is POSIX-style and includes the extension, e.g.
  ``'signal_analysis/lead_brake_detector.py'``.
  """
  name = '_repo_tools_' + relative_path.removesuffix('.py').replace('/', '.')
  module = sys.modules.get(name)
  if module is not None:
    return module
  path = TOOLS_ROOT / relative_path
  spec = importlib.util.spec_from_file_location(name, path)
  if spec is None or spec.loader is None:
    raise ImportError(f'cannot load {relative_path} from {TOOLS_ROOT}')
  module = importlib.util.module_from_spec(spec)
  sys.modules[name] = module
  try:
    spec.loader.exec_module(module)
  except BaseException:
    sys.modules.pop(name, None)
    raise
  return module
