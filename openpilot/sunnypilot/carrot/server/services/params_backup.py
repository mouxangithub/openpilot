"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Bulk parameter backup, restore, and the QR wire format CarrotPilot's app speaks.

Ported from CarrotPilot so a backup taken on either fork can be restored on the other.
Three on-the-wire encodings exist:

    CQR2.<base64url(zlib(json))>.<sha256[:12]>        - plain, always available
    CQR3:<base45(brotli(binary))>:<SHA256[:12]>        - smallest, needs `brotli`
    CQR4:<base45(zlib(binary))>:<SHA256[:12]>          - no extra dependency

We emit v3 when `brotli` happens to be installed and v4 otherwise, and we read all three
plus v1. Every payload carries a checksum because a QR code that lost a corner must be
rejected, not half-applied.

Two rules the port keeps:
- JSON and BYTES parameters are excluded. They are not settings a person typed, and a
  truncated one is not safe to write back.
- A restore goes through the same single-key write path the settings screen uses, so a
  value that cannot be saved from the UI cannot be saved by a backup either.
"""

import base64
import hashlib
import importlib
import json
import os
import tempfile
import threading
import zlib
from typing import Any

try:
  import brotli
except Exception:
  brotli = None

QR_BACKUP_PREFIX_V1 = "CQR1"
QR_BACKUP_PREFIX_V2 = "CQR2"
QR_BACKUP_PREFIX_V3 = "CQR3"
QR_BACKUP_PREFIX_V4 = "CQR4"
QR_BACKUP_CHECKSUM_CHARS = 12
QR_BACKUP_SCHEMA_BYTES = 4
QR_BACKUP_CODE_BYTES_V3 = 2
QR_BACKUP_BASE45_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:"

_brotli_lock = threading.Lock()

# Types that are excluded from a backup: not user settings, and not safely round-trippable.
_UNSUPPORTED_TYPE_NAMES = frozenset(("BYTES", "JSON"))


def _type_name(key_type: Any) -> str:
  return str(getattr(key_type, "name", None) or key_type).rsplit(".", 1)[-1]


def _is_unsupported(key_type: Any) -> bool:
  return _type_name(key_type) in _UNSUPPORTED_TYPE_NAMES


# ------------------------------- bulk backup ---------------------------------


def _backup_param_names(params) -> list[str]:
  names: list[str] = []
  for raw in params.all_keys():
    key = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
    try:
      key_type = params.get_type(key)
    except Exception:
      continue
    if _is_unsupported(key_type):
      continue
    try:
      if params.get_default_value(key) is None:
        continue
    except Exception:
      continue
    names.append(key)
  return names


def get_all_param_values_for_backup(params) -> dict[str, str]:
  """Every backup-able parameter as a string, defaults filled in for never-written keys."""
  out: dict[str, str] = {}
  for key in _backup_param_names(params):
    try:
      value = params.get(key, block=False, return_default=False)
    except Exception:
      value = None
    if value is None:
      try:
        value = params.get_default_value(key)
      except Exception:
        continue
    if value is None:
      continue
    if isinstance(value, (dict, list)):
      out[key] = json.dumps(value, ensure_ascii=False)
    elif isinstance(value, (bytes, bytearray)):
      out[key] = bytes(value).decode("utf-8", "replace")
    elif isinstance(value, bool):
      out[key] = "1" if value else "0"
    else:
      out[key] = str(value)
  return out


def write_params_backup_file(params, path: str) -> dict[str, Any]:
  """Write the full dump to `path` so `/download/params_backup.json` can serve it."""
  values = get_all_param_values_for_backup(params)
  os.makedirs(os.path.dirname(path), exist_ok=True)
  tmp_path = path + ".tmp"
  with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(values, f, ensure_ascii=False, indent=2, sort_keys=True)
    f.write("\n")
    f.flush()
    os.fsync(f.fileno())
  os.replace(tmp_path, path)
  return {"ok": True, "count": len(values), "path": path}


# ------------------------------- restore ------------------------------------


def restore_param_values_from_backup(params, values: dict[str, Any], source: str = "restore") -> dict[str, Any]:
  """Write each value through the single-key path. Returns per-key counts, never raises."""
  from ..services.params import set_param_value
  from .param_changes import append_param_change

  ok_count = 0
  fail_count = 0
  failures: list[dict[str, str]] = []

  for key, value in values.items():
    try:
      try:
        key_type = params.get_type(key)
      except Exception:
        key_type = None
      if key_type is not None and _is_unsupported(key_type):
        continue

      try:
        previous = params.get(key, block=False, return_default=False)
      except Exception:
        previous = None

      set_param_value(params, key, value)
      ok_count += 1

      try:
        after = params.get(key, block=False, return_default=False)
        if previous != after:
          append_param_change(key, previous, after, source=source)
      except Exception:
        pass
    except Exception as exc:
      fail_count += 1
      failures.append({"key": str(key), "err": str(exc)})

  return {"ok_cnt": ok_count, "fail_cnt": fail_count, "fails": failures[:30]}


def _normalize_param_value(key_type: Any, value: Any) -> Any:
  name = _type_name(key_type)
  if name == "BOOL":
    if isinstance(value, str):
      text = value.strip().lower()
      if text in ("1", "true", "on", "yes"):
        return True
      if text in ("0", "false", "off", "no", ""):
        return False
    return bool(value)
  if name == "INT":
    return int(round(float(value)))
  if name == "FLOAT":
    return float(value)
  return str(value)


def _values_equal(key_type: Any, left: Any, right: Any) -> bool:
  try:
    if _type_name(key_type) == "FLOAT":
      return abs(float(left) - float(right)) < 0.000001
    return _normalize_param_value(key_type, left) == _normalize_param_value(key_type, right)
  except Exception:
    return str(left) == str(right)


def preview_param_restore_values(params, values: dict[str, Any], selected_keys: list[str] | None = None) -> dict[str, Any]:
  """Classify each incoming value so the app can show the diff before applying it."""
  from ..services.params import get_param_values

  selected = set(selected_keys or [])
  current_values = get_param_values(params, list(values.keys()))
  entries = []
  summary = {"changed": 0, "same": 0, "skipped": 0, "invalid": 0, "selected": 0}

  for key in sorted(values):
    raw_value = values[key]
    status = "changed"
    reason = ""
    can_apply = True
    type_name = "unknown"
    normalized: Any = raw_value

    try:
      key_type = params.get_type(key)
    except Exception:
      key_type = None

    if key_type is None:
      status = "invalid"
      reason = "unknown parameter"
      can_apply = False
    else:
      type_name = _type_name(key_type)
      if _is_unsupported(key_type):
        status = "skipped"
        reason = "unsupported type"
        can_apply = False
      else:
        normalized = _normalize_param_value(key_type, raw_value)
        if _values_equal(key_type, current_values.get(key, ""), normalized):
          status = "same"
          can_apply = False

    is_selected = can_apply and (not selected or key in selected)
    if is_selected:
      summary["selected"] += 1
    summary[status] += 1
    entries.append({
      "key": key,
      "type": type_name,
      "current": current_values.get(key, ""),
      "value": normalized,
      "status": status,
      "reason": reason,
      "apply": is_selected,
    })

  return {"count": len(entries), "summary": summary, "entries": entries}


def restore_param_values_validated(params, values: dict[str, Any], selected_keys: list[str] | None = None,
                                   source: str = "restore") -> dict[str, Any]:
  preview = preview_param_restore_values(params, values, selected_keys)
  apply_values = {entry["key"]: entry["value"] for entry in preview["entries"] if entry.get("apply")}
  result = restore_param_values_from_backup(params, apply_values, source=source) if apply_values else {
    "ok_cnt": 0,
    "fail_cnt": 0,
    "fails": [],
  }
  return {"preview": preview, "result": result}


# ------------------------------- QR encoding --------------------------------


def _b64url_encode(data: bytes) -> str:
  return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
  return base64.urlsafe_b64decode(text + ("=" * (-len(text) % 4)))


def _base45_encode(data: bytes) -> str:
  chars = QR_BACKUP_BASE45_ALPHABET
  out: list[str] = []
  index = 0
  while index < len(data):
    if index + 1 < len(data):
      value = (data[index] << 8) + data[index + 1]
      out.append(chars[value % 45])
      out.append(chars[(value // 45) % 45])
      out.append(chars[value // (45 * 45)])
      index += 2
    else:
      value = data[index]
      out.append(chars[value % 45])
      out.append(chars[value // 45])
      index += 1
  return "".join(out)


def _base45_decode(text: str) -> bytes:
  chars = QR_BACKUP_BASE45_ALPHABET
  values = {char: index for index, char in enumerate(chars)}
  out = bytearray()
  index = 0
  while index < len(text):
    remaining = len(text) - index
    if remaining == 1:
      raise ValueError("bad base45 payload")
    if remaining >= 3:
      try:
        value = values[text[index]] + values[text[index + 1]] * 45 + values[text[index + 2]] * 45 * 45
      except KeyError as exc:
        raise ValueError("bad base45 payload") from exc
      if value > 0xFFFF:
        raise ValueError("bad base45 payload")
      out.append(value >> 8)
      out.append(value & 0xFF)
      index += 3
    else:
      try:
        value = values[text[index]] + values[text[index + 1]] * 45
      except KeyError as exc:
        raise ValueError("bad base45 payload") from exc
      if value > 0xFF:
        raise ValueError("bad base45 payload")
      out.append(value)
      index += 2
  return bytes(out)


def _write_varint(value: int) -> bytes:
  if value < 0:
    raise ValueError("negative varint")
  out = bytearray()
  while True:
    byte = value & 0x7F
    value >>= 7
    if value:
      out.append(byte | 0x80)
    else:
      out.append(byte)
      return bytes(out)


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
  shift = 0
  value = 0
  while True:
    if pos >= len(data) or shift > 63:
      raise ValueError("bad varint")
    byte = data[pos]
    pos += 1
    value |= (byte & 0x7F) << shift
    if not (byte & 0x80):
      return value, pos
    shift += 7


def _zigzag_encode(value: int) -> int:
  return (value << 1) ^ (value >> 63)


def _zigzag_decode(value: int) -> int:
  return (value >> 1) ^ -(value & 1)


def _param_short_code(key: str, size: int = QR_BACKUP_CODE_BYTES_V3) -> bytes:
  return hashlib.sha256(key.encode("utf-8")).digest()[:size]


def _build_code_maps(names: list[str], size: int = QR_BACKUP_CODE_BYTES_V3) -> tuple[dict[str, bytes], dict[bytes, str]]:
  buckets: dict[bytes, list[str]] = {}
  for name in sorted({str(name) for name in names}):
    buckets.setdefault(_param_short_code(name, size), []).append(name)
  # A code that two names share is ambiguous, so it is left out and those keys travel
  # by name instead. Silent truncation would restore the wrong setting.
  code_to_key = {code: keys[0] for code, keys in buckets.items() if len(keys) == 1}
  key_to_code = {key: code for code, key in code_to_key.items()}
  return key_to_code, code_to_key


def _schema_fingerprint(names: list[str], size: int = QR_BACKUP_CODE_BYTES_V3) -> bytes:
  encoded_names = "\n".join(sorted({str(name) for name in names})).encode("utf-8")
  return hashlib.sha256(bytes([size]) + encoded_names).digest()[:QR_BACKUP_SCHEMA_BYTES]


def _is_int_string(value: str) -> bool:
  if not value:
    return False
  if value == "0":
    return True
  if value.startswith("-"):
    body = value[1:]
    return bool(body) and body.isdigit() and not (len(body) > 1 and body.startswith("0"))
  return value.isdigit() and not value.startswith("0")


def _encode_qr_value(value: Any, type_name: str) -> bytes:
  if type_name == "BOOL":
    as_bool = value in ("1", "true", "True", "on", "yes") if isinstance(value, str) else bool(value)
    return b"\x02" if as_bool else b"\x01"

  text = str(value)
  if text == "":
    return b"\x00"
  if text == "0":
    return b"\x01"
  if text == "1":
    return b"\x02"

  if type_name == "INT":
    try:
      return b"\x03" + _write_varint(_zigzag_encode(int(round(float(value)))))
    except Exception:
      pass
  if type_name == "UNKNOWN" and _is_int_string(text):
    return b"\x03" + _write_varint(_zigzag_encode(int(text)))

  raw = text.encode("utf-8")
  return b"\x04" + _write_varint(len(raw)) + raw


def _decode_qr_value(data: bytes, pos: int) -> tuple[str, int]:
  if pos >= len(data):
    raise ValueError("bad QR backup value")
  tag = data[pos]
  pos += 1
  if tag == 0:
    return "", pos
  if tag == 1:
    return "0", pos
  if tag == 2:
    return "1", pos
  if tag == 3:
    value, pos = _read_varint(data, pos)
    return str(_zigzag_decode(value)), pos
  if tag == 4:
    size, pos = _read_varint(data, pos)
    end = pos + size
    if end > len(data):
      raise ValueError("bad QR backup string")
    return data[pos:end].decode("utf-8"), end
  raise ValueError("unsupported QR backup value")


def _build_qr_binary(params, values: dict[str, Any], version: int) -> bytes:
  try:
    code_names = _backup_param_names(params)
  except Exception:
    code_names = list(values.keys())

  type_names = {}
  for key in code_names:
    try:
      type_names[key] = _type_name(params.get_type(key))
    except Exception:
      type_names[key] = "UNKNOWN"

  key_to_code, _ = _build_code_maps(code_names)
  raw = bytearray()
  pairs: list[tuple[bytes, bytes]] = []
  fallback: list[tuple[bytes, bytes]] = []

  for key in sorted(values):
    key_text = str(key)
    encoded_value = _encode_qr_value(values[key], type_names.get(key_text, "UNKNOWN"))
    code = key_to_code.get(key_text)
    if code:
      pairs.append((code, encoded_value))
    else:
      fallback.append((key_text.encode("utf-8"), encoded_value))

  raw.append(version)
  raw.append(QR_BACKUP_CODE_BYTES_V3)
  raw.extend(_schema_fingerprint(code_names))
  raw.extend(_write_varint(len(pairs)))
  for code, encoded_value in pairs:
    raw.extend(code)
    raw.extend(encoded_value)

  raw.extend(_write_varint(len(fallback)))
  for key_bytes, encoded_value in fallback:
    raw.extend(_write_varint(len(key_bytes)))
    raw.extend(key_bytes)
    raw.extend(encoded_value)

  return bytes(raw)


def _envelope(prefix: str, compressed: bytes, version: int, json_bytes: int, encoder) -> dict[str, Any]:
  checksum = hashlib.sha256(compressed).hexdigest()[:QR_BACKUP_CHECKSUM_CHARS].upper()
  payload = f"{prefix}:{encoder(compressed)}:{checksum}"
  return {
    "payload": payload,
    "format": prefix,
    "count": json_bytes,
    "json_bytes": json_bytes,
    "compressed_bytes": len(compressed),
    "payload_chars": len(payload),
    "version": version,
    "checksum": checksum,
  }


def _load_brotli() -> Any:
  global brotli
  if brotli is not None:
    return brotli
  with _brotli_lock:
    if brotli is None:
      brotli = importlib.import_module("brotli")
  return brotli


def build_params_qr_payload(params, values: dict[str, Any] | None = None) -> dict[str, Any]:
  """Encode the whole parameter set as one short string.

  v3 (brotli) is preferred because it is what a CarrotPilot-generated QR uses; when brotli
  is not installed the payload is v4, which the same decoder reads.
  """
  if values is None:
    values = get_all_param_values_for_backup(params)

  try:
    raw = _build_qr_binary(params, values, 3)
    return _envelope(QR_BACKUP_PREFIX_V3, _load_brotli().compress(raw, quality=11), 3, len(values), _base45_encode)
  except Exception:
    pass

  raw = _build_qr_binary(params, values, 4)
  return _envelope(QR_BACKUP_PREFIX_V4, zlib.compress(raw, 9), 4, len(values), _base45_encode)


# ------------------------------- QR decoding --------------------------------


def _parse_qr_binary(params, raw: bytes) -> dict[str, Any]:
  if len(raw) < 2 + QR_BACKUP_SCHEMA_BYTES:
    raise ValueError("bad QR backup format")

  version = raw[0]
  code_size = raw[1]
  pos = 2 + QR_BACKUP_SCHEMA_BYTES
  if version not in (3, 4):
    raise ValueError("unsupported QR backup version")
  if code_size < 1 or code_size > 8:
    raise ValueError("bad QR backup code size")

  _, code_to_key = _build_code_maps(_backup_param_names(params), code_size)
  values: dict[str, Any] = {}

  pair_count, pos = _read_varint(raw, pos)
  for _ in range(pair_count):
    end = pos + code_size
    if end > len(raw):
      raise ValueError("bad QR backup code")
    code = raw[pos:end]
    pos = end
    value, pos = _decode_qr_value(raw, pos)
    key = code_to_key.get(code)
    if key:
      values[key] = value

  fallback_count, pos = _read_varint(raw, pos)
  for _ in range(fallback_count):
    key_size, pos = _read_varint(raw, pos)
    key_end = pos + key_size
    if key_end > len(raw):
      raise ValueError("bad QR backup key")
    key = raw[pos:key_end].decode("utf-8")
    pos = key_end
    value, pos = _decode_qr_value(raw, pos)
    values[key] = value

  if pos != len(raw):
    raise ValueError("bad QR backup trailing data")

  return values


def _parse_qr_payload_v3_v4(params, payload: str) -> dict[str, Any]:
  prefix = payload[:4]
  if prefix not in (QR_BACKUP_PREFIX_V3, QR_BACKUP_PREFIX_V4):
    raise ValueError("unsupported QR payload")
  try:
    encoded, checksum_text = payload[5:].rsplit(":", 1)
  except ValueError as exc:
    raise ValueError("bad QR payload") from exc

  compressed = _base45_decode(encoded)
  checksum = hashlib.sha256(compressed).hexdigest()[:QR_BACKUP_CHECKSUM_CHARS].upper()
  if checksum != checksum_text.upper():
    raise ValueError("QR payload checksum mismatch")

  if prefix == QR_BACKUP_PREFIX_V3:
    raw = _load_brotli().decompress(compressed)
  else:
    raw = zlib.decompress(compressed)
  return _parse_qr_binary(params, raw)


def _parse_qr_payload_v2(params, compressed: bytes, checksum_text: str) -> dict[str, Any]:
  if hashlib.sha256(compressed).hexdigest()[:QR_BACKUP_CHECKSUM_CHARS] != checksum_text:
    raise ValueError("QR payload checksum mismatch")

  envelope = json.loads(zlib.decompress(compressed).decode("utf-8"))
  if isinstance(envelope, list):
    if len(envelope) < 2:
      raise ValueError("bad QR backup format")
    version = int(envelope[0])
    pairs = envelope[1]
    fallback = envelope[2] if len(envelope) > 2 else {}
  elif isinstance(envelope, dict):
    version = int(envelope.get("v", 0))
    pairs = envelope.get("d")
    fallback = envelope.get("n", {})
  else:
    raise ValueError("bad QR backup format")

  if version > 4:
    raise ValueError("unsupported QR backup version")
  if not isinstance(pairs, list):
    raise ValueError("bad QR backup values")
  if not isinstance(fallback, dict):
    raise ValueError("bad QR backup fallback")

  _, code_to_key = _build_code_maps(_backup_param_names(params))
  values: dict[str, Any] = {}
  for item in pairs:
    if not isinstance(item, list) or len(item) != 2:
      continue
    key = code_to_key.get(str(item[0]))
    if key:
      values[key] = item[1]
  for key, value in fallback.items():
    values[str(key)] = value
  return values


def parse_params_qr_payload(params, data: Any) -> dict[str, Any]:
  """Turn a payload (string or object) back into {name: value}. Raises on anything untrusted."""
  if isinstance(data, dict):
    values = data.get("values") if isinstance(data.get("values"), dict) else data
    if not isinstance(values, dict):
      raise ValueError("bad payload format")
    return values

  payload = str(data or "").strip()
  if not payload:
    raise ValueError("empty payload")

  if payload.startswith("{"):
    return parse_params_qr_payload(params, json.loads(payload))

  if payload.startswith((QR_BACKUP_PREFIX_V3, QR_BACKUP_PREFIX_V4)):
    return _parse_qr_payload_v3_v4(params, payload)

  parts = payload.split(".")
  if len(parts) != 3 or parts[0] not in (QR_BACKUP_PREFIX_V1, QR_BACKUP_PREFIX_V2):
    raise ValueError("unsupported QR payload")
  if parts[0] == QR_BACKUP_PREFIX_V1:
    compressed = _b64url_decode(parts[1])
    if hashlib.sha256(compressed).hexdigest()[:16] != parts[2]:
      raise ValueError("QR payload checksum mismatch")
    envelope = json.loads(zlib.decompress(compressed).decode("utf-8"))
    if envelope.get("type") != "params_backup":
      raise ValueError("unsupported QR backup type")
    values = envelope.get("values")
    if not isinstance(values, dict):
      raise ValueError("bad QR backup values")
    return values
  return _parse_qr_payload_v2(params, _b64url_decode(parts[1]), parts[2])


def get_qr_dependency_status() -> dict[str, Any]:
  """Whether the optional brotli encoder is present - decides v3 vs v4."""
  try:
    module = _load_brotli()
    return {"ok": True, "installed": True, "dependency": "brotli", "format": QR_BACKUP_PREFIX_V3,
            "module_path": getattr(module, "__file__", "")}
  except Exception as exc:
    return {"ok": True, "installed": False, "dependency": "brotli", "format": QR_BACKUP_PREFIX_V4, "error": str(exc)}


def _atomic_write_json(path: str, payload: Any) -> None:
  os.makedirs(os.path.dirname(path), exist_ok=True)
  fd, temp_path = tempfile.mkstemp(prefix=".tmp_", dir=os.path.dirname(path))
  try:
    with os.fdopen(fd, "w", encoding="utf-8") as f:
      fd = -1
      json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
      f.write("\n")
      f.flush()
      os.fsync(f.fileno())
    os.replace(temp_path, path)
  finally:
    if fd >= 0:
      os.close(fd)
    if os.path.exists(temp_path):
      try:
        os.unlink(temp_path)
      except OSError:
        pass
