"""Append-only history of every settings write, with a verifiable hash chain.

Ported from CarrotPilot (cp):
  selfdrive/carrot/server/services/param_changes.py

Adapated for sunnypilot (sp):
  * Uses sp's CARROT_TUNING_DEFAULTS from carrot_tuning_api as the key whitelist
    (instead of cp's get_settings_cached() which uses carrot_settings.json).
  * Uses sp's state directory: /data/carrot/state
  * Follows sp's coding style (2-space indent).

Why this exists: a parameter can be changed from the web UI, by applying a
profile, by restoring a backup, or by a steering-wheel button in the driving
code. Until now nothing recorded which of those happened, so a value that
turned up different could not be explained. The log answers "who changed this,
when, and from what".

Integrity is a real concern here: the log lives on a car computer that loses
power mid-drive, so a truncated or half-written file is normal wear. Each
record carries the hash of the record before it. A break in that chain marks
exactly where the file stopped being trustworthy.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from typing import Any

# --- paths (matching sp's carrot_settings_backup_api.py) ---
DEFAULT_STATE_DIR = "/data/carrot/state"
STATE_DIR = os.environ.get("CARROT_SETTINGS_STATE_DIR", DEFAULT_STATE_DIR)
PARAM_CHANGES_PATH = os.path.join(STATE_DIR, "param_changes.jsonl")
FINGERPRINT_BASELINE_PATH = os.path.join(STATE_DIR, "fingerprint_baseline.json")

# Enough to cover a long session of tinkering without letting the file grow
# without bound on a device that is never garbage collected.
MAX_PARAM_CHANGE_RECORDS = 1000

# Where a write came from.
PARAM_CHANGE_SOURCES = frozenset({
  "web_ui",
  "profile",
  "restore",
  "reset_defaults",
  "device",
  "unknown",
})

GENESIS_HASH = "0" * 64

_write_lock = threading.Lock()


def _canonical(payload: dict) -> str:
  """Stable serialization so the same record always hashes the same way."""
  return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def record_hash(record: dict) -> str:
  """Hash of a record's content plus the previous record's hash."""
  body = {key: record.get(key) for key in ("ts", "name", "prev", "next", "source", "engaged")}
  body["prev_hash"] = record.get("prev_hash", GENESIS_HASH)
  return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def normalize_source(source: Any) -> str:
  text = str(source or "").strip()
  return text if text in PARAM_CHANGE_SOURCES else "unknown"


def _read_lines() -> list:
  try:
    with open(PARAM_CHANGES_PATH, "r", encoding="utf-8") as f:
      return [line for line in f.read().splitlines() if line.strip()]
  except Exception:
    return []


def _parse(line: str) -> dict | None:
  try:
    record = json.loads(line)
  except Exception:
    return None
  return record if isinstance(record, dict) else None


def read_param_changes(limit: int = 0, name: str = "", source: str = "") -> list:
  """Return records newest first, optionally narrowed to one parameter and/or one source."""
  records = [record for record in (_parse(line) for line in _read_lines()) if record is not None]
  if name:
    records = [r for r in records if str(r.get("name", "")) == str(name)]
  if source:
    records = [r for r in records if str(r.get("source", "")) == str(source)]
  records.reverse()
  if limit > 0:
    records = records[:limit]
  return records


def last_record() -> dict | None:
  for line in reversed(_read_lines()):
    record = _parse(line)
    if record is not None:
      return record
  return None


def append_param_change(
  name: str,
  prev: Any,
  next_value: Any,
  source: str = "web_ui",
  engaged: bool = False,
  ts: int | None = None,
) -> dict | None:
  """Append one record. Never raises: a failed log must not fail the write."""
  key = str(name or "").strip()
  if not key:
    return None

  note_known_value(key, next_value)

  try:
    with _write_lock:
      previous = last_record()
      record = {
        "ts": int(ts if ts is not None else time.time()),
        "name": key,
        "prev": prev,
        "next": next_value,
        "source": normalize_source(source),
        "engaged": bool(engaged),
        "prev_hash": str(previous.get("hash") or GENESIS_HASH) if previous else GENESIS_HASH,
      }
      record["hash"] = record_hash(record)

      os.makedirs(os.path.dirname(PARAM_CHANGES_PATH), exist_ok=True)
      with open(PARAM_CHANGES_PATH, "a", encoding="utf-8") as f:
        f.write(_canonical(record) + "\n")
      _trim_locked()
      return record
  except Exception:
    return None


def _trim_locked() -> None:
  """Drop the oldest records once the file outgrows the ring size."""
  lines = _read_lines()
  if len(lines) <= MAX_PARAM_CHANGE_RECORDS:
    return

  records = [r for r in (_parse(line) for line in lines) if r is not None]
  kept = records[-MAX_PARAM_CHANGE_RECORDS:]
  prev_hash = GENESIS_HASH
  for record in kept:
    record["prev_hash"] = prev_hash
    record["hash"] = record_hash(record)
    prev_hash = record["hash"]

  tmp_path = PARAM_CHANGES_PATH + ".tmp"
  with open(tmp_path, "w", encoding="utf-8") as f:
    for record in kept:
      f.write(_canonical(record) + "\n")
  os.replace(tmp_path, PARAM_CHANGES_PATH)


def verify_param_changes() -> dict:
  """Walk the chain from the start and report the first break, if any."""
  lines = _read_lines()
  prev_hash = GENESIS_HASH
  checked = 0

  for index, line in enumerate(lines):
    record = _parse(line)
    if record is None:
      return _broken(index, checked, "record is not valid JSON")
    if str(record.get("prev_hash") or "") != prev_hash:
      return _broken(index, checked, "record does not link to the previous hash")
    if str(record.get("hash") or "") != record_hash(record):
      return _broken(index, checked, "record content does not match its hash")
    prev_hash = str(record.get("hash"))
    checked += 1

  return {"ok": True, "valid": True, "checked": checked, "broken_at": None, "reason": ""}


def _broken(index: int, checked: int, reason: str) -> dict:
  return {"ok": True, "valid": False, "checked": checked, "broken_at": index, "reason": reason}


# Last value this server knows about, per parameter.
_known_values: dict = {}
_known_lock = threading.Lock()


def note_known_value(name: str, value: Any) -> None:
  with _known_lock:
    _known_values[str(name)] = value


def observe_param_values(values: dict, allowed: set | None = None) -> int:
  """Record values that changed without the web server doing it.

  The driving code writes some parameters directly to Params, so those changes
  can never reach append_param_change() on their own. Drift is picked up on
  the reads the web already performs.

  Returns the number of records appended.
  """
  if not isinstance(values, dict) or not values:
    return 0

  drifted = []
  with _known_lock:
    for name, value in values.items():
      key = str(name)
      if allowed is not None and key not in allowed:
        continue
      if key not in _known_values:
        _known_values[key] = value
        continue
      if _known_values[key] != value:
        drifted.append((key, _known_values[key], value))
        _known_values[key] = value

  for key, previous, current in drifted:
    append_param_change(key, previous, current, source="device")
  return len(drifted)


def read_fingerprint_baseline() -> dict | None:
  """The saved reference fingerprint, or None if none has been set yet."""
  try:
    with open(FINGERPRINT_BASELINE_PATH, "r", encoding="utf-8") as f:
      data = json.load(f)
  except Exception:
    return None
  if not isinstance(data, dict) or not str(data.get("fingerprint") or ""):
    return None
  return {"fingerprint": str(data["fingerprint"]), "ts": int(data.get("ts") or 0)}


def write_fingerprint_baseline(fingerprint: str, ts: int | None = None) -> dict:
  """Save the current fingerprint as the reference to compare against."""
  record = {"fingerprint": str(fingerprint), "ts": int(ts if ts is not None else time.time())}
  os.makedirs(os.path.dirname(FINGERPRINT_BASELINE_PATH), exist_ok=True)
  tmp_path = FINGERPRINT_BASELINE_PATH + ".tmp"
  with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(record, f, ensure_ascii=False)
    f.write("\n")
  os.replace(tmp_path, FINGERPRINT_BASELINE_PATH)
  return record


def count_changes_since(ts: int, allowed: set | None = None) -> int:
  """How many distinct parameters changed at or after `ts`."""
  names = set()
  for record in read_param_changes():
    if int(record.get("ts") or 0) < ts:
      continue
    name = str(record.get("name") or "")
    if not name or (allowed is not None and name not in allowed):
      continue
    names.add(name)
  return len(names)


def param_fingerprint(values: dict) -> dict:
  """Short digest of the whole parameter set."""
  clean = {str(key): values.get(key) for key in sorted(values or {})}
  digest = hashlib.sha256(_canonical(clean).encode("utf-8")).hexdigest()
  return {"fingerprint": digest[:8], "digest": digest, "count": len(clean)}


def get_settings_fingerprint() -> dict:
  """Compute fingerprint of all carrot tuning keys."""
  try:
    from webui.server.bridge.carrot_tuning_api import CARROT_TUNING_DEFAULTS, carrot_value_str
    values = {}
    for key in sorted(CARROT_TUNING_DEFAULTS.keys()):
      values[key] = carrot_value_str(key) or ""
  except Exception:
    values = {}
  result = param_fingerprint(values)

  baseline = read_fingerprint_baseline()
  if baseline is None:
    # First visit: adopt the current state as the reference
    baseline = write_fingerprint_baseline(result["fingerprint"])
  result["baseline"] = baseline
  result["changed"] = result["fingerprint"] != baseline.get("fingerprint")
  result["changed_count"] = (
    count_changes_since(int(baseline.get("ts") or 0))
    if result["changed"] else 0
  )
  return result
