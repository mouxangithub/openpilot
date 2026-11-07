"""Tests for ai.tools.result_externalize."""

from __future__ import annotations

import json
import time
from io import BytesIO
from unittest.mock import patch

import pytest

from ai.tools.result_externalize import (
  acquire_lease,
  externalize_if_needed,
  get_lease,
  read_externalized,
  release_lease,
  sweep_expired,
)
from ai.tools.spill_backend import HttpSpillBackend, LocalSpillBackend


@pytest.fixture(autouse=True)
def patch_workspace_path(tmp_path, monkeypatch):
  def fake(*parts, mkdir=False):
    path = tmp_path.joinpath(*parts)
    if mkdir:
      path.mkdir(parents=True, exist_ok=True)
    return path

  monkeypatch.setattr("ai.tools.result_externalize.workspace_path", fake)


@pytest.fixture
def params():
  return {"ai_externalize_results": True}


def test_small_result_not_externalized(params):
  result = {"ok": True, "data": "x"}
  pointer, artifact = externalize_if_needed(result, session_id="s1", tool_name="t1", params=params)
  assert artifact is None
  assert pointer == result


def test_large_result_externalized(params):
  result = {"ok": True, "data": "x" * 20_000}
  pointer, artifact = externalize_if_needed(result, session_id="s1", tool_name="t1", params=params)
  assert artifact is not None
  assert pointer.get("externalized") is True
  ref = pointer["ref"]
  loaded = read_externalized(ref)
  assert loaded["ok"] is True
  assert loaded["data"] == result


def test_lease_lifecycle(params):
  result = {"ok": True, "data": "y" * 20_000}
  pointer, _ = externalize_if_needed(result, session_id="s2", tool_name="t2", params=params)
  ref = pointer["ref"]
  lease = acquire_lease(ref, duration_seconds=10, owner="test")
  assert lease["ok"] is True
  info = get_lease(ref)
  assert info["leased"] is True
  assert info["expired"] is False
  released = release_lease(ref)
  assert released["removed"] is True
  assert get_lease(ref)["exists"] is False


def test_sweep_expired(params):
  result = {"ok": True, "data": "z" * 20_000}
  pointer, _ = externalize_if_needed(result, session_id="s3", tool_name="t3", params=params)
  ref = pointer["ref"]
  # Lease already expired.
  acquire_lease(ref, duration_seconds=-1, owner="test")
  sweeped = sweep_expired()
  ref_id = ref.replace("toolresult://", "")
  assert any(ref_id in p for p in sweeped["removed"])


def test_sweep_dry_run(params):
  result = {"ok": True, "data": "w" * 20_000}
  pointer, _ = externalize_if_needed(result, session_id="s4", tool_name="t4", params=params)
  ref = pointer["ref"]
  acquire_lease(ref, duration_seconds=-1, owner="test")
  sweeped = sweep_expired(dry_run=True)
  assert len(sweeped["removed"]) > 0
  assert read_externalized(ref)["ok"] is True


def test_http_backend_roundtrip():
  """HttpSpillBackend PUT/GET/DELETE using a fake urllib opener."""
  backend = HttpSpillBackend("http://example.com/spill", token="tok")
  ref_id = "abc123"
  data = b'{"big": true}'

  calls = []

  class FakeResponse:
    def __init__(self, code: int = 200, body: bytes = b""):
      self.code = code
      self.body = body

    def read(self):
      return self.body

    def __enter__(self):
      return self

    def __exit__(self, *args):
      return False

  def fake_urlopen(request, **_kwargs):
    method = request.get_method()
    calls.append((method, request.full_url, request.data))
    if method == "PUT":
      return FakeResponse(200)
    if method == "GET":
      return FakeResponse(200, data)
    if method == "DELETE":
      return FakeResponse(200)
    return FakeResponse(404)

  with patch("urllib.request.urlopen", fake_urlopen):
    store_result = backend.store(ref_id, data, session_id="s", tool_name="t", ext="json")
    assert store_result["ok"] is True
    assert store_result["locator"] == "http://example.com/spill/abc123.json"

    loaded = backend.load(ref_id)
    assert loaded == data

    removed = backend.remove(ref_id)
    assert removed is True

  assert len(calls) == 3
  assert calls[0][0] == "PUT"
  assert calls[1][0] == "GET"
  assert calls[2][0] == "DELETE"
