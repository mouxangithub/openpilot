"""Tests for ai.core.session.manager lifecycle state machine."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai.core.session.log import EventType
from ai.core.session.manager import SessionLifecycleState, SessionManager


@pytest.fixture
def manager(tmp_path: Path):
  return SessionManager(str(tmp_path))


def test_create_session(manager: SessionManager):
  record = manager.create_session(title="Test", origin="test-origin")
  assert record.title == "Test"
  assert record.cwd == str(manager.cwd)
  assert manager._state(record.id) == SessionLifecycleState.ACTIVE
  log = manager._get_or_create_log(record)
  assert any(ev.type == EventType.LIFECYCLE and ev.data.get("action") == "create_session" for ev in log.events)


def test_pause_and_resume(manager: SessionManager):
  record = manager.create_session(title="Test")
  paused = manager.pause_session(record.id)
  assert paused is not None
  assert manager._state(record.id) == SessionLifecycleState.PAUSED
  resumed, repaired = manager.resume_session(record.id)
  assert resumed is not None
  assert manager._state(record.id) == SessionLifecycleState.ACTIVE
  assert isinstance(repaired, list)


def test_dispose_session(manager: SessionManager):
  record = manager.create_session(title="Test")
  assert manager.dispose_session(record.id) is True
  assert manager._state(record.id) == SessionLifecycleState.DISPOSED
  assert manager.dispose_session("missing") is False


def test_dispose_already_paused(manager: SessionManager):
  record = manager.create_session(title="Test")
  manager.pause_session(record.id)
  assert manager.dispose_session(record.id) is True
  assert manager._state(record.id) == SessionLifecycleState.DISPOSED


def test_backward_compatible_aliases(manager: SessionManager):
  record = manager.create(title="Alias")
  assert manager._state(record.id) == SessionLifecycleState.ACTIVE
  manager.close(record.id)
  assert manager._state(record.id) == SessionLifecycleState.DISPOSED
