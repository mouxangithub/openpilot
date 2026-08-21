"""Tests for workspace path resolution and defaults."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))


class TestWorkspaceStore(unittest.TestCase):
  def test_workspace_dir_under_ai_repo(self):
    from ai.core.wspace import store as ws

    with tempfile.TemporaryDirectory() as tmp:
      ai_root = Path(tmp) / "ai"
      (ai_root / "core" / "workspace").mkdir(parents=True)
      fake_store = ai_root / "core" / "workspace" / "store.py"
      fake_store.write_text("# stub\n", encoding="utf-8")

      with patch("ai.common.repo_targets.assistant_repo_path", return_value=ai_root):
        path = ws.workspace_dir()
      self.assertEqual(path, ai_root / "workspace")
      self.assertTrue(path.is_dir())

  def test_default_files_created(self):
    from ai.core.wspace.store import ensure_default_workspace_files, workspace_prompt_blocks

    with tempfile.TemporaryDirectory() as tmp:
      ai_root = Path(tmp) / "ai"
      ai_root.mkdir()
      with patch("ai.common.repo_targets.assistant_repo_path", return_value=ai_root):
        ensure_default_workspace_files()
        blocks = workspace_prompt_blocks()
      self.assertTrue((ai_root / "workspace" / "SOUL.md").is_file())
      self.assertTrue(any("SOUL" in b or "助手" in b for b in blocks))


if __name__ == "__main__":
  unittest.main()
