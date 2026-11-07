"""Session FTS index tests (skip without a real openpilot runtime)."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))
OP_ROOT = ROOT / "openpilot"
if OP_ROOT.is_dir() and str(OP_ROOT) not in sys.path:
  sys.path.insert(0, str(OP_ROOT))

# Real openpilot runtime prerequisites, probed explicitly. Checking these keeps
# the skip decision independent of ambient ``sys.path`` mutations and of the
# openpilot mocks that sibling test modules (``ai/tests/bootstrap_pc.py``)
# install into ``sys.modules``. Probing ``openpilot`` alone is not enough: the
# ``OP_ROOT`` injection above makes ``importlib.util.find_spec("openpilot")``
# succeed even when the underlying runtime (zmq) is absent. Probing the real
# runtime dependency makes this module behave identically in isolation and
# inside the full suite.
_OPENPILOT_RUNTIME_DEPS = ("zmq", "openpilot.common.params")


def _missing_runtime_deps() -> list[str]:
  missing: list[str] = []
  for name in _OPENPILOT_RUNTIME_DEPS:
    try:
      if importlib.util.find_spec(name) is None:
        missing.append(name)
    except (ImportError, ValueError):
      # ValueError: ``name`` is mocked in sys.modules without a __spec__.
      missing.append(name)
  return missing


def _require_openpilot():
  missing = _missing_runtime_deps()
  if missing:
    raise unittest.SkipTest("openpilot runtime not available: missing " + ", ".join(missing))
  try:
    from openpilot.common.params import Params  # noqa: F401
  except Exception as e:
    raise unittest.SkipTest(f"openpilot runtime not usable: {e}") from e


class SessionIndexTests(unittest.TestCase):
  def test_index_and_search_roundtrip(self):
    _require_openpilot()
    import tempfile
    import ai.tools.session_index as mod
    from ai.tools.session_index import index_session, search_sessions

    with tempfile.TemporaryDirectory() as td:
      db_path = Path(td) / "session_index.db"
      mod.SESSIONS_DB = db_path
      mod._DB = None
      session = {
        "id": "sess_test_1",
        "title": "Tune review",
        "messages": [
          {"role": "user", "content": "请检查 MADS 横向故障"},
          {"role": "assistant", "content": "已读取 manager 日志，未发现 fault"},
        ],
      }
      self.assertEqual(index_session(session), 2)
      res = search_sessions("MADS 横向")
      self.assertTrue(res.get("ok"))
      hits = res.get("hits") or []
      self.assertTrue(hits)
      self.assertEqual(hits[0].get("sessionId"), "sess_test_1")

  def test_search_handles_apostrophe(self):
    _require_openpilot()
    import tempfile
    import ai.tools.session_index as mod
    from ai.tools.session_index import index_session, search_sessions

    with tempfile.TemporaryDirectory() as td:
      db_path = Path(td) / "session_index.db"
      mod.SESSIONS_DB = db_path
      mod._DB = None
      index_session({
        "id": "sess_quote",
        "title": "it's fine",
        "messages": [{"role": "user", "content": "driver's camera issue"}],
      })
      res = search_sessions("it's")
      self.assertTrue(res.get("ok"))
      self.assertIsInstance(res.get("hits"), list)
