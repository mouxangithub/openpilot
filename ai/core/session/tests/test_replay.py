"""Tests for ai.core.session.replay."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai.core.session.log import EventType, SessionLog
from ai.core.session.replay import fork_transcript, fork_transcript_by_index, read_jsonl_events, replay_transcript


@pytest.fixture
def transcript_path(tmp_path: Path):
  path = tmp_path / "session.jsonl"
  header = {"formatVersion": "1.0", "schema": "session/event-log"}
  path.write_text(json.dumps(header) + "\n", encoding="utf-8")
  log = SessionLog("s1", persist_path=path)
  log.append(EventType.USER_MESSAGE, {"content": "hi"})
  log.append(EventType.ASSISTANT_MESSAGE, {"content": "hello"})
  log.append(EventType.TOOL_CALL, {"name": "foo"})
  log.close()
  return path


def test_read_jsonl_events(transcript_path: Path):
  events = read_jsonl_events(transcript_path)
  assert len(events) == 3
  assert events[0].type == EventType.USER_MESSAGE
  assert events[1].type == EventType.ASSISTANT_MESSAGE


def test_replay_transcript_alias(transcript_path: Path):
  events = replay_transcript(transcript_path)
  assert len(events) == 3


def test_fork_transcript_inclusive(transcript_path: Path):
  events = fork_transcript(transcript_path, up_to_seq=1, inclusive=True)
  assert len(events) == 2


def test_fork_transcript_exclusive(transcript_path: Path):
  events = fork_transcript(transcript_path, up_to_seq=1, inclusive=False)
  assert len(events) == 1


def test_fork_by_index(transcript_path: Path):
  events = fork_transcript_by_index(transcript_path, 2)
  assert len(events) == 2


def test_read_missing_file(tmp_path: Path):
  events = read_jsonl_events(tmp_path / "missing.jsonl")
  assert events == []
