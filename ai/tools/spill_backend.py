"""Spill / externalization backend abstraction.

Supports local filesystem (default) and remote HTTP backends. The backend is
selected via ``ai_externalize_backend`` config key ("local" or "http"). Remote
backend uses ``ai_externalize_remote_url`` as the base URL and optional
``ai_externalize_remote_token`` for Bearer authorization.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ai.system.paths import workspace_path

try:
  from ai.common.storage import read_param, read_param_bool
except Exception:  # pragma: no cover - fallback when openpilot params unavailable

  def read_param(_params: Any, key: str, default: Any = None) -> Any:  # noqa: D103
    if _params is not None and key in _params:
      return _params[key]
    return default

  def read_param_bool(_params: Any, key: str, default: bool = False) -> bool:  # noqa: D103
    if _params is not None and key in _params:
      return str(_params[key]).strip().lower() in ("1", "true", "yes", "on")
    return default


class SpillBackend(ABC):
  """Abstract backend for spilled/externalized tool results."""

  @abstractmethod
  def store(
    self,
    ref_id: str,
    data: bytes,
    *,
    session_id: str = "",
    tool_name: str = "",
    ext: str = "txt",
  ) -> dict[str, Any]:
    """Store data and return {"ok": bool, "locator": str, "ref": ref, "error": str?}."""

  @abstractmethod
  def load(self, ref_id: str) -> bytes | None:
    """Load raw data by ref_id, or None if not found."""

  @abstractmethod
  def remove(self, ref_id: str) -> bool:
    """Delete data by ref_id."""

  def list_refs(self, *, prefix: str = "") -> list[str]:
    """List stored ref ids. Default empty list for backends without enumeration."""
    return []


class LocalSpillBackend(SpillBackend):
  """Default backend: store spilled results under workspace_path('tool_results')."""

  def __init__(self, base_dir: str | Path | None = None, *, harden: bool = True) -> None:
    self.base_dir = Path(base_dir) if base_dir else workspace_path("tool_results")
    self.harden = harden

  def _safe_session(self, session_id: str) -> str:
    return (session_id or "global").replace("/", "_").replace("\\", "_")[:64]

  def _results_dir(self, session_id: str) -> Path:
    path = self.base_dir / self._safe_session(session_id)
    path.mkdir(parents=True, exist_ok=True)
    if self.harden:
      # D-P0.4: private-by-default directory.
      try:
        os.chmod(path, 0o700)
      except OSError:
        pass
    return path

  def _path(self, ref_id: str, session_id: str, tool_name: str, ext: str) -> Path:
    return self._results_dir(session_id) / f"{tool_name or 'tool'}_{ref_id}.{ext}"

  def store(
    self,
    ref_id: str,
    data: bytes,
    *,
    session_id: str = "",
    tool_name: str = "",
    ext: str = "txt",
  ) -> dict[str, Any]:
    path = self._path(ref_id, session_id, tool_name, ext)
    try:
      if self.harden:
        # D-P0.4: reject symlink redirection + owner-only 0600 write. Detect
        # the final leaf symlink BEFORE resolving so an attacker cannot redirect
        # the write through a symlinked filename.
        if path.is_symlink() or (path.exists() and path.resolve().is_symlink()):
          return {"ok": False, "error": "refuse spill write through symlink"}
        resolved = path.resolve()
        fd = os.open(resolved, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
          os.write(fd, data)
        finally:
          os.close(fd)
      else:
        path.write_bytes(data)
      return {"ok": True, "locator": str(path), "ref": f"toolresult://{ref_id}"}
    except OSError as e:
      return {"ok": False, "error": str(e)}

  def load(self, ref_id: str) -> bytes | None:
    if not self.base_dir.is_dir():
      return None
    matches = list(self.base_dir.rglob(f"*_{ref_id}.*"))
    if not matches:
      return None
    try:
      return matches[0].read_bytes()
    except OSError:
      return None

  def remove(self, ref_id: str) -> bool:
    if not self.base_dir.is_dir():
      return False
    removed = False
    for path in self.base_dir.rglob(f"*_{ref_id}.*"):
      try:
        path.unlink()
        removed = True
      except FileNotFoundError:
        pass
    return removed

  def list_refs(self, *, prefix: str = "") -> list[str]:
    if not self.base_dir.is_dir():
      return []
    refs: list[str] = []
    for path in self.base_dir.rglob("*"):
      if path.is_file() and not path.name.endswith(".lease.json"):
        name = path.name
        # Expected name: <tool>_<ref_id>.<ext>
        parts = name.rsplit("_", 1)
        if len(parts) == 2:
          ref_part = parts[1].rsplit(".", 1)[0]
          if ref_part and (not prefix or ref_part.startswith(prefix)):
            refs.append(ref_part)
    return refs


class HttpSpillBackend(SpillBackend):
  """Remote HTTP backend: PUT/GET/DELETE against a base URL.

  Ref ids are stored as ``{base_url}/{ref_id}.{ext}``.
  """

  def __init__(self, base_url: str, token: str = "", timeout: int = 30) -> None:
    self.base_url = base_url.rstrip("/")
    self.token = token
    self.timeout = timeout

  def _headers(self) -> dict[str, str]:
    headers = {"Content-Type": "application/octet-stream"}
    if self.token:
      headers["Authorization"] = f"Bearer {self.token}"
    return headers

  def _url(self, ref_id: str, ext: str = "txt") -> str:
    return f"{self.base_url}/{ref_id}.{ext}"

  def store(
    self,
    ref_id: str,
    data: bytes,
    *,
    session_id: str = "",
    tool_name: str = "",
    ext: str = "txt",
  ) -> dict[str, Any]:
    url = self._url(ref_id, ext)
    req = urllib.request.Request(url, data=data, method="PUT", headers=self._headers())
    try:
      with urllib.request.urlopen(req, timeout=self.timeout) as resp:
        resp.read()
      return {"ok": True, "locator": url, "ref": f"toolresult://{ref_id}"}
    except urllib.error.URLError as e:
      return {"ok": False, "error": f"HTTP store failed: {e}"}

  def load(self, ref_id: str) -> bytes | None:
    # Try common extensions; remote backend does not know ext, so try .txt then .json.
    for ext in ("txt", "json"):
      req = urllib.request.Request(self._url(ref_id, ext), headers=self._headers())
      try:
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
          return resp.read()
      except urllib.error.HTTPError as e:
        if e.code == 404:
          continue
        return None
      except urllib.error.URLError:
        return None
    return None

  def remove(self, ref_id: str) -> bool:
    for ext in ("txt", "json"):
      req = urllib.request.Request(self._url(ref_id, ext), method="DELETE", headers=self._headers())
      try:
        with urllib.request.urlopen(req, timeout=self.timeout):
          return True
      except urllib.error.HTTPError as e:
        if e.code == 404:
          continue
        return False
      except urllib.error.URLError:
        return False
    return False


def _decode_headers(value: Any) -> dict[str, str]:
  if isinstance(value, str):
    try:
      decoded = json.loads(value)
      if isinstance(decoded, dict):
        return {str(k): str(v) for k, v in decoded.items()}
    except json.JSONDecodeError:
      pass
  if isinstance(value, dict):
    return {str(k): str(v) for k, v in value.items()}
  return {}


def get_spill_backend(params: Any = None, base_dir: str | Path | None = None) -> SpillBackend:
  """Resolve configured spill backend."""
  backend = str(
    read_param(params, "ai_spill_backend", None)
    or read_param(params, "ai_externalize_backend", "local")
    or "local"
  ).strip().lower()
  if backend in ("http", "remote"):
    url = str(
      read_param(params, "ai_spill_remote_endpoint", None)
      or read_param(params, "ai_externalize_remote_url", "")
      or ""
    ).strip()
    if not url:
      # Fall back to local if remote URL is missing.
      return LocalSpillBackend(base_dir) if base_dir else LocalSpillBackend()
    token = str(
      read_param(params, "ai_spill_remote_token", None)
      or read_param(params, "ai_externalize_remote_token", "")
      or ""
    ).strip()
    return HttpSpillBackend(url, token=token)
  # Default / anything else -> local
  local_dir = read_param(params, "ai_externalize_local_dir", None)
  return LocalSpillBackend(local_dir or base_dir)
