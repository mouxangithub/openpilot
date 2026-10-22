"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Append-only history of every settings write, with a verifiable hash chain.

Ported from CarrotPilot. A parameter can be changed from the API, by applying a profile,
by restoring a backup, or by the driving code itself (the steering-wheel gap button writes
`MyDrivingMode` / `LongitudinalPersonality` straight to Params). Nothing recorded which of
those happened, so a value that turned up different could not be explained.

Each record carries the hash of the record before it. The log lives on a car computer that
loses power mid-drive, so a truncated or half-written line is normal wear; a break in the
chain marks exactly where the file stopped being trustworthy.

Timestamps are `time.monotonic()`, not wall clock: the history answers "how long ago" and
"what changed since this baseline", and openpilot bans `time.time()` outright.
"""

import hashlib
import json
import os
import threading
import time
from typing import Any

from ..config import CARROT_FINGERPRINT_BASELINE_PATH, CARROT_PARAM_CHANGES_PATH

# Enough to cover a long session of tinkering without letting the file grow without bound
# on a device that is never garbage collected.
MAX_PARAM_CHANGE_RECORDS = 1000

# Where a write came from. Anything outside this set is recorded as "unknown" so a caller
# cannot invent a source that hides what actually happened.
PARAM_CHANGE_SOURCES = frozenset((
  "web_ui",
  "profile",
  "restore",
  "reset_defaults",
  "intro",
  "undo",
  # Something outside this server changed the value - in practice the driving code.
  "device",
  "unknown",
))

GENESIS_HASH = "0" * 64

_write_lock = threading.Lock()
_known_lock = threading.Lock()

# Last value this server knows about, per parameter. Populated by our own writes and by
# every read that passes through `observe_param_values`.
_known_values: dict[str, Any] = {}


def _canonical(payload: dict[str, Any]) -> str:
  """Stable serialization so the same record always hashes the same way."""
  return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def record_hash(record: dict[str, Any]) -> str:
  """Hash of a record's content plus the previous record's hash."""
  body = {key: record.get(key) for key in ("ts", "name", "prev", "next", "source", "engaged")}
  body["prev_hash"] = record.get("prev_hash", GENESIS_HASH)
  return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def normalize_source(source: Any) -> str:
  text = str(source or "").strip()
  return text if text in PARAM_CHANGE_SOURCES else "unknown"


def _read_lines() -> list[str]:
  try:
    with open(CARROT_PARAM_CHANGES_PATH, encoding="utf-8") as f:
      return [line for line in f.read().splitlines() if line.strip()]
  except Exception:
    return []


def _parse(line: str) -> dict[str, Any] | None:
  try:
    record = json.loads(line)
  except Exception:
    return None
  return record if isinstance(record, dict) else None


def read_param_changes(limit: int = 0, name: str = "", source: str = "") -> list[dict[str, Any]]:
  """Records newest first, optionally narrowed to one parameter and/or one source."""
  records = [record for record in (_parse(line) for line in _read_lines()) if record is not None]
  if name:
    records = [record for record in records if str(record.get("name", "")) == str(name)]
  if source:
    records = [record for record in records if str(record.get("source", "")) == str(source)]
  records.reverse()
  if limit and limit > 0:
    records = records[:limit]
  return records


def last_record() -> dict[str, Any] | None:
  for line in reversed(_read_lines()):
    record = _parse(line)
    if record is not None:
      return record
  return None


def note_known_value(name: str, value: Any) -> None:
  with _known_lock:
    _known_values[str(name)] = value


def append_param_change(name: str, prev: Any, next_value: Any, source: str = "web_ui", engaged: bool = False) -> dict[str, Any] | None:
  """Append one record. Never raises: a failed log must not fail the write that caused it."""
  key = str(name or "").strip()
  if not key:
    return None

  # Keep the drift baseline in step with our own writes, otherwise the next read would
  # report this very change a second time as if it came from outside.
  note_known_value(key, next_value)

  try:
    with _write_lock:
      previous = last_record()
      record = {
        "ts": int(time.monotonic()),
        "name": key,
        "prev": prev,
        "next": next_value,
        "source": normalize_source(source),
        "engaged": bool(engaged),
        "prev_hash": str(previous.get("hash") or GENESIS_HASH) if previous else GENESIS_HASH,
      }
      record["hash"] = record_hash(record)

      os.makedirs(os.path.dirname(CARROT_PARAM_CHANGES_PATH), exist_ok=True)
      with open(CARROT_PARAM_CHANGES_PATH, "a", encoding="utf-8") as f:
        f.write(_canonical(record) + "\n")
      _trim_locked()
      return record
  except Exception:
    return None


def _trim_locked() -> None:
  """Drop the oldest records once the file outgrows the ring size.

  Trimming necessarily breaks the chain at the new first record, so that record is
  re-anchored to the genesis hash and the ones after it are re-linked. The alternative -
  reporting a permanent break after the first trim - would make verification useless.
  """
  lines = _read_lines()
  if len(lines) <= MAX_PARAM_CHANGE_RECORDS:
    return

  records = [record for record in (_parse(line) for line in lines) if record is not None]
  kept = records[-MAX_PARAM_CHANGE_RECORDS:]
  prev_hash = GENESIS_HASH
  for record in kept:
    record["prev_hash"] = prev_hash
    record["hash"] = record_hash(record)
    prev_hash = record["hash"]

  tmp_path = CARROT_PARAM_CHANGES_PATH + ".tmp"
  with open(tmp_path, "w", encoding="utf-8") as f:
    for record in kept:
      f.write(_canonical(record) + "\n")
  os.replace(tmp_path, CARROT_PARAM_CHANGES_PATH)


def verify_param_changes() -> dict[str, Any]:
  """Walk the chain from the start and report the first break, if any.

  A log nobody checks is not tamper evident, so this is the counterpart that makes the
  hashes mean something.
  """
  prev_hash = GENESIS_HASH
  checked = 0

  for index, line in enumerate(_read_lines()):
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


def _broken(index: int, checked: int, reason: str) -> dict[str, Any]:
  return {"ok": True, "valid": False, "checked": checked, "broken_at": index, "reason": reason}


def observe_param_values(values: dict[str, Any], allowed: set | None = None) -> int:
  """Record values that changed without this server doing it.

  Rather than adding a background poller to a car computer - or making safety-critical code
  depend on this service - drift is picked up on the reads the API already performs.

  `allowed` restricts watching to that set of names. Callers pass the catalog keys so
  synthetic values and hardware readouts (which change on every read and are not settings)
  never land in the change history.

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
        # First sighting since boot: adopt it as the baseline rather than reporting the
        # whole parameter set as changed.
        _known_values[key] = value
        continue
      if _known_values[key] != value:
        drifted.append((key, _known_values[key], value))
        _known_values[key] = value

  for key, previous, current in drifted:
    append_param_change(key, previous, current, source="device")
  return len(drifted)


def read_fingerprint_baseline() -> dict[str, Any] | None:
  try:
    with open(CARROT_FINGERPRINT_BASELINE_PATH, encoding="utf-8") as f:
      data = json.load(f)
  except Exception:
    return None
  if not isinstance(data, dict) or not str(data.get("fingerprint") or ""):
    return None
  return {"fingerprint": str(data["fingerprint"]), "ts": int(data.get("ts") or 0)}


def write_fingerprint_baseline(fingerprint: str, ts: int | None = None) -> dict[str, Any]:
  record = {"fingerprint": str(fingerprint), "ts": int(ts if ts is not None else time.monotonic())}
  os.makedirs(os.path.dirname(CARROT_FINGERPRINT_BASELINE_PATH), exist_ok=True)
  tmp_path = CARROT_FINGERPRINT_BASELINE_PATH + ".tmp"
  with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(record, f, ensure_ascii=False)
    f.write("\n")
  os.replace(tmp_path, CARROT_FINGERPRINT_BASELINE_PATH)
  return record


def count_changes_since(ts: int, allowed: set | None = None) -> int:
  """How many distinct parameters changed at or after `ts`.

  Distinct, not raw records: pressing a segment three times is "1 setting changed".
  """
  names = set()
  for record in read_param_changes():
    if int(record.get("ts") or 0) < ts:
      continue
    name = str(record.get("name") or "")
    if not name or (allowed is not None and name not in allowed):
      continue
    names.add(name)
  return len(names)


def param_fingerprint(values: dict[str, Any]) -> dict[str, Any]:
  """Short digest of the whole parameter set.

  Comparing one short string answers "did anything change since the last known good state?"
  without diffing every value.
  """
  clean = {str(key): values.get(key) for key in sorted(values or {})}
  digest = hashlib.sha256(_canonical(clean).encode("utf-8")).hexdigest()
  return {"fingerprint": digest[:8], "digest": digest, "count": len(clean)}
