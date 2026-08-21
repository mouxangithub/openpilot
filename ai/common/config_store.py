"""Persistent storage for ai_* settings — no params_keys.h / compile required."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from ai.common.op_params import import_openpilot_params
from ai.common.params import ITEMS
from ai.system.paths import is_comma_device, openpilot_root

_EXTRA_DEFAULTS: dict[str, dict[str, str]] = {
  "ai_usage_log": {"param_type": "STRING", "default": ""},
  "ai_embedding_usage_log": {"param_type": "STRING", "default": ""},
  "ai_param_watchlist": {"param_type": "STRING", "default": ""},
  "ai_param_watchlist_baseline": {"param_type": "STRING", "default": ""},
}

_LEGACY_GITHUB_PAT_PARAM = "GithubActionsPat"
_AI_GITHUB_PAT_KEY = "ai_github_actions_pat"

_store: "AiConfigStore | None" = None
_store_lock = threading.Lock()


def ai_config_path() -> Path:
  env = (os.environ.get("AI_CONFIG_PATH") or "").strip()
  if env:
    return Path(env).expanduser().resolve()
  if is_comma_device():
    return Path("/data/ai/config.json")
  home = Path.home() / ".comma" / "ai" / "config.json"
  if home.parent.exists() or not (openpilot_root() / "ai").is_dir():
    return home
  return openpilot_root() / "ai" / "data" / "user" / "config.json"


def _build_schema() -> dict[str, dict[str, str]]:
  schema: dict[str, dict[str, str]] = {}
  for item in ITEMS:
    key = item.get("key", "")
    if key.startswith("ai_"):
      schema[key] = {
        "param_type": item.get("param_type", "STRING"),
        "default": item.get("default", ""),
      }
  for key, meta in _EXTRA_DEFAULTS.items():
    schema.setdefault(key, meta)
  return schema


def is_ai_param(key: str) -> bool:
  return bool(key) and key.startswith("ai_")


class AiConfigStore:
  def __init__(self, path: Path | None = None) -> None:
    self._path = path or ai_config_path()
    self._schema = _build_schema()
    self._data: dict[str, str] | None = None
    self._lock = threading.Lock()
    self._migrated = False

  @property
  def path(self) -> Path:
    return self._path

  def _default_for(self, key: str) -> str | None:
    meta = self._schema.get(key)
    if meta is None:
      return "" if is_ai_param(key) else None
    return meta.get("default", "")

  def _param_type(self, key: str) -> str:
    return (self._schema.get(key) or {}).get("param_type", "STRING")

  def _load_disk(self) -> dict[str, str]:
    if not self._path.is_file():
      return {}
    try:
      raw = self._path.read_text(encoding="utf-8")
      data = json.loads(raw)
      if not isinstance(data, dict):
        return {}
      return {str(k): "" if v is None else str(v) for k, v in data.items() if is_ai_param(str(k))}
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
      return {}

  def _cleanup_stale_temp_files(self) -> None:
    parent = self._path.parent
    if not parent.is_dir():
      return
    for path in parent.glob(".ai_config_*"):
      try:
        path.unlink()
      except OSError:
        pass

  def _save_disk(self, data: dict[str, str]) -> None:
    self._path.parent.mkdir(parents=True, exist_ok=True)
    self._cleanup_stale_temp_files()
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    fd, tmp = tempfile.mkstemp(prefix=".ai_config_", dir=str(self._path.parent))
    try:
      with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
      os.replace(tmp, self._path)
      try:
        os.chmod(self._path, 0o600)
      except OSError:
        pass
      try:
        os.chmod(self._path.parent, 0o700)
      except OSError:
        pass
    finally:
      if os.path.exists(tmp):
        try:
          os.unlink(tmp)
        except OSError:
          pass

  def _migrate_from_params_dir(self, data: dict[str, str]) -> None:
    params_dir = Path("/data/params/d")
    if not params_dir.is_dir():
      return
    for entry in params_dir.iterdir():
      if not entry.is_file() or not entry.name.startswith("ai_"):
        continue
      if entry.name in data:
        continue
      try:
        text = entry.read_text(encoding="utf-8", errors="replace").strip("\x00")
        if text:
          data[entry.name] = text
      except OSError:
        continue

  def _migrate_from_params_api(self, data: dict[str, str]) -> None:
    try:
      Params, UnknownKeyName = import_openpilot_params()
    except Exception:
      return
    p = Params()
    for key in self._schema:
      if key in data:
        continue
      try:
        val = p.get(key)
      except UnknownKeyName:
        continue
      except Exception:
        continue
      if val is None:
        continue
      if isinstance(val, bytes):
        val = val.decode("utf-8", errors="replace")
      data[key] = str(val)

  def _migrate_legacy_github_pat(self, data: dict[str, str]) -> None:
    if data.get(_AI_GITHUB_PAT_KEY, "").strip():
      return
    legacy = _LEGACY_GITHUB_PAT_PARAM
    params_dir = Path("/data/params/d")
    if params_dir.is_dir():
      legacy_file = params_dir / legacy
      if legacy_file.is_file():
        try:
          text = legacy_file.read_text(encoding="utf-8", errors="replace").strip("\x00").strip()
          if text:
            data[_AI_GITHUB_PAT_KEY] = text
            return
        except OSError:
          pass
    try:
      Params, UnknownKeyName = import_openpilot_params()
    except Exception:
      return
    p = Params()
    try:
      val = p.get(legacy)
    except UnknownKeyName:
      return
    except Exception:
      return
    if val is None:
      return
    if isinstance(val, bytes):
      val = val.decode("utf-8", errors="replace")
    text = str(val).strip()
    if not text:
      return
    data[_AI_GITHUB_PAT_KEY] = text
    try:
      p.remove(legacy)
    except Exception:
      pass

  def _ensure_migrated(self, data: dict[str, str]) -> None:
    if self._migrated:
      return
    self._migrate_from_params_dir(data)
    self._migrate_from_params_api(data)
    self._migrate_legacy_github_pat(data)
    self._migrated = True
    if data != self._load_disk():
      self._save_disk(data)

  def _ensure_loaded(self) -> dict[str, str]:
    if self._data is not None:
      return self._data
    with self._lock:
      if self._data is not None:
        return self._data
      data = self._load_disk()
      self._ensure_migrated(data)
      self._data = data
      return data

  def reload(self) -> None:
    with self._lock:
      self._data = None
      self._migrated = False

  def get(self, key: str, default: Any = None) -> Any:
    if not is_ai_param(key):
      raise ValueError(f"not an ai param: {key}")
    data = self._ensure_loaded()
    if key in data:
      return data[key]
    schema_default = self._default_for(key)
    if schema_default is not None:
      return schema_default
    return default

  def get_bool(self, key: str, default: bool = False) -> bool:
    val = self.get(key, None)
    if val is None:
      return default
    if isinstance(val, bool):
      return val
    return str(val).strip().lower() in ("1", "true", "yes", "on")

  def put(self, key: str, value: Any) -> None:
    if not is_ai_param(key):
      raise ValueError(f"not an ai param: {key}")
    ptype = self._param_type(key)
    if ptype == "BOOL" or isinstance(value, bool):
      text = "1" if (bool(value) if not isinstance(value, str) else value.lower() in ("1", "true", "yes")) else "0"
    elif ptype == "INT":
      text = str(int(value))
    elif ptype == "FLOAT":
      text = str(float(value))
    elif value is None:
      text = ""
    else:
      text = str(value)
    with self._lock:
      data = dict(self._ensure_loaded())
      data[key] = text
      self._data = data
      self._save_disk(data)

  def put_bool(self, key: str, value: bool) -> None:
    self.put(key, value)

  def remove(self, key: str) -> None:
    if not is_ai_param(key):
      raise ValueError(f"not an ai param: {key}")
    with self._lock:
      data = dict(self._ensure_loaded())
      if key in data:
        del data[key]
      self._data = data
      self._save_disk(data)

  def all_keys(self) -> list[str]:
    data = self._ensure_loaded()
    keys = set(self._schema) | set(data)
    return sorted(k for k in keys if is_ai_param(k))

  def read_all(self) -> dict[str, str]:
    data = dict(self._ensure_loaded())
    for key, meta in self._schema.items():
      data.setdefault(key, meta.get("default", ""))
    return {k: data[k] for k in sorted(data) if is_ai_param(k)}


def get_config_store() -> AiConfigStore:
  global _store
  if _store is None:
    with _store_lock:
      if _store is None:
        _store = AiConfigStore()
  return _store


def reset_config_store_for_tests(path: Path | None = None) -> AiConfigStore:
  """Test helper: point store at a temp file."""
  global _store
  with _store_lock:
    _store = AiConfigStore(path=path)
    return _store
