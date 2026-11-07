"""Cabana dbc module."""
from __future__ import annotations

import os
import re
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from ai.services.cabana.deps import DBC, PLATFORMS, DBC_PATH, get_generated_dbcs


def _user_dbc_dir() -> Path:
  """Directory for user-committed DBCs (AI-assisted editing).

  Override with the ``AI_USER_DBC_DIR`` environment variable. On Windows
  (dev machines, no /data) fall back to a repo-local directory so tests and
  local runs work without root paths.
  """
  env = os.getenv("AI_USER_DBC_DIR")
  if env:
    return Path(env)
  if os.name == "nt":
    return Path(__file__).resolve().parents[2] / "data" / "user_dbcs"
  return Path("/data/ai_user_dbcs")


def _list_user_dbc_files() -> list[Path]:
  """Current-version user DBC files ({name}.dbc) in the user directory."""
  try:
    user_dir = _user_dbc_dir()
    if user_dir.is_dir():
      # Only current-version files: history snapshots carry an extra ".{ts}" suffix.
      return sorted(p for p in user_dir.glob("*.dbc") if not _USER_HISTORY_RE.match(p.name))
  except Exception:
    pass
  return []


_USER_HISTORY_RE = re.compile(r"^.+\.\d{14,}$")


def _list_dbc_names() -> list[str]:
  """All known DBC names: user, file-based, generated, and platform dbc_dict values."""
  dbcs: list[str] = []
  dbcs.extend(p.stem for p in _list_user_dbc_files())
  if DBC_PATH:
    dbc_path = Path(DBC_PATH)
    if dbc_path.exists():
      dbcs.extend([p.stem for p in dbc_path.glob("*.dbc")])
  try:
    dbcs.extend(get_generated_dbcs().keys())
  except Exception:
    pass
  for platform in (PLATFORMS or {}).values():
    cfg = getattr(platform, "config", None)
    dbc_dict = getattr(cfg, "dbc_dict", None) or {}
    if isinstance(dbc_dict, dict):
      for val in dbc_dict.values():
        if val:
          dbcs.append(str(val))
  return sorted(set(dbcs))


_EN_TO_ZH_ALIASES: dict[str, list[str]] = {
  "toyota": ["丰田"],
  "lexus": ["雷克萨斯", "凌志"],
  "honda": ["本田"],
  "acura": ["讴歌"],
  "volkswagen": ["大众"],
  "audi": ["奥迪"],
  "tesla": ["特斯拉"],
  "subaru": ["斯巴鲁"],
  "nissan": ["日产"],
  "hyundai": ["现代"],
  "kia": ["起亚"],
  "ford": ["福特"],
  "mazda": ["马自达"],
  "bmw": ["宝马"],
  "mercedes": ["奔驰"],
  "chevrolet": ["雪佛兰"],
  "gmc": ["GMC"],
  "rivian": ["Rivian"],
  "corolla": ["卡罗拉"],
  "camry": ["凯美瑞"],
  "rav4": ["荣放"],
  "prius": ["普锐斯"],
  "highlander": ["汉兰达"],
  "civic": ["思域"],
  "accord": ["雅阁"],
  "crv": ["CRV"],
  "model3": ["model3"],
  "modely": ["modely"],
}

_dbc_catalog_cache: list[dict[str, Any]] | None = None
_dbc_catalog_lock = threading.Lock()
# Cache invalidation: TTL probe + DBC source mtime digest. Generated DBCs come
# from an in-memory dict (no probeable mtime); file-based DBCs are covered.
_DBC_CATALOG_TTL = 300.0
_dbc_catalog_built_at = 0.0
_dbc_catalog_mtime_sig: float | None = None


def _dbc_sources_mtime() -> float:
  """Max mtime across DBC sources (user dir + opendbc files; 0.0 when nothing is probeable)."""
  latest = 0.0
  try:
    for f in _list_user_dbc_files():
      try:
        latest = max(latest, f.stat().st_mtime)
      except OSError:
        continue
    if DBC_PATH:
      dbc_path = Path(DBC_PATH)
      if dbc_path.is_dir():
        for f in dbc_path.glob("*.dbc"):
          try:
            latest = max(latest, f.stat().st_mtime)
          except OSError:
            continue
  except Exception:
    pass
  return latest


def _invalidate_dbc_catalog() -> None:
  """Force the next catalog build to rebuild (called after a user DBC commit/rollback).

  Without this the TTL/mtime cache could serve a stale list for up to
  ``_DBC_CATALOG_TTL`` seconds after a new user DBC is written.
  """
  global _dbc_catalog_cache, _dbc_catalog_mtime_sig
  with _dbc_catalog_lock:
    _dbc_catalog_cache = None
    _dbc_catalog_mtime_sig = None


def _quick_dbc_catalog() -> list[dict[str, Any]]:
  return [{"name": name, "searchText": name} for name in _list_dbc_names()]


def _search_tokens(text: str) -> list[str]:
  return [t for t in re.split(r"[^a-z0-9\u4e00-\u9fff]+", (text or "").lower()) if len(t) >= 2]


def _append_zh_aliases(parts: set[str]) -> None:
  for token in list(parts):
    tl = token.lower()
    for en, zh_list in _EN_TO_ZH_ALIASES.items():
      if en in tl or tl == en:
        parts.add(en)
        parts.update(zh_list)


def _build_dbc_catalog() -> list[dict[str, Any]]:
  global _dbc_catalog_cache, _dbc_catalog_built_at, _dbc_catalog_mtime_sig
  now = time.monotonic()
  if _dbc_catalog_cache is not None:
    if now - _dbc_catalog_built_at < _DBC_CATALOG_TTL:
      return _dbc_catalog_cache
    # TTL expired: re-probe source mtimes; keep the cache when unchanged.
    mtime = _dbc_sources_mtime()
    if _dbc_catalog_mtime_sig is not None and mtime == _dbc_catalog_mtime_sig:
      _dbc_catalog_built_at = now
      return _dbc_catalog_cache

  with _dbc_catalog_lock:
    if _dbc_catalog_cache is not None:
      if time.monotonic() - _dbc_catalog_built_at < _DBC_CATALOG_TTL:
        return _dbc_catalog_cache
      mtime = _dbc_sources_mtime()
      if _dbc_catalog_mtime_sig is not None and mtime == _dbc_catalog_mtime_sig:
        _dbc_catalog_built_at = time.monotonic()
        return _dbc_catalog_cache

    buckets: dict[str, dict[str, set[str]]] = defaultdict(
      lambda: {
        "brands": set(),
        "makes": set(),
        "models": set(),
        "fingerprints": set(),
        "labels": set(),
        "tokens": set(),
      }
    )

    if PLATFORMS:
      for fingerprint, platform in PLATFORMS.items():
        cfg = getattr(platform, "config", None)
        if cfg is None:
          continue

        dbc_names: set[str] = set()
        dbc_dict = getattr(cfg, "dbc_dict", None) or {}
        if isinstance(dbc_dict, dict):
          for val in dbc_dict.values():
            if val:
              dbc_names.add(str(val))

        doc_rows: list[tuple[str, str, str]] = []
        for doc in getattr(cfg, "car_docs", None) or []:
          name = getattr(doc, "name", "") or ""
          make = getattr(doc, "make", "") or ""
          model = getattr(doc, "model", "") or ""
          if name or make or model:
            doc_rows.append((name, make, model))

        brand_hint = ""
        if doc_rows and doc_rows[0][1]:
          brand_hint = doc_rows[0][1].lower()
        elif fingerprint:
          brand_hint = fingerprint.split()[0].lower()

        for dbc_name in dbc_names:
          bucket = buckets[dbc_name]
          if fingerprint:
            bucket["fingerprints"].add(fingerprint)
            bucket["tokens"].update(_search_tokens(fingerprint))
          if brand_hint:
            bucket["brands"].add(brand_hint)
            bucket["tokens"].add(brand_hint)
          for label, make, model in doc_rows:
            if label:
              bucket["labels"].add(label)
              bucket["tokens"].update(_search_tokens(label))
            if make:
              bucket["makes"].add(make.lower())
              bucket["tokens"].update(_search_tokens(make))
            if model:
              bucket["models"].add(model.lower())
              bucket["tokens"].update(_search_tokens(model))

    catalog: list[dict[str, Any]] = []
    for dbc_name in _list_dbc_names():
      bucket = buckets.get(dbc_name) or {
        "brands": set(),
        "makes": set(),
        "models": set(),
        "fingerprints": set(),
        "labels": set(),
        "tokens": set(),
      }
      tokens = set(bucket["tokens"])
      tokens.update(_search_tokens(dbc_name))
      _append_zh_aliases(tokens)

      labels = sorted(bucket["labels"])[:8]
      models = sorted(bucket["models"])[:12]
      makes = sorted(bucket["makes"])[:8]
      brands = sorted(bucket["brands"])[:8]
      fingerprints = sorted(bucket["fingerprints"])[:10]

      search_text = " ".join(sorted(tokens))
      catalog.append({
        "name": dbc_name,
        "brands": brands,
        "makes": makes,
        "models": models,
        "fingerprints": fingerprints,
        "labels": labels,
        "searchText": search_text,
      })

    _dbc_catalog_cache = catalog
    _dbc_catalog_mtime_sig = _dbc_sources_mtime()
    _dbc_catalog_built_at = time.monotonic()
    return catalog


def _get_dbc_dict(car_fingerprint: str) -> dict[str, str]:
  if not PLATFORMS or not car_fingerprint:
    return {}

  platform = PLATFORMS.get(car_fingerprint)
  if platform is None:
    fp_upper = car_fingerprint.upper()
    for key, candidate in PLATFORMS.items():
      if key.upper() == fp_upper:
        platform = candidate
        break
    if platform is None:
      for key, candidate in PLATFORMS.items():
        if fp_upper in key.upper() or key.upper() in fp_upper:
          platform = candidate
          break

  if platform is None:
    return {}

  cfg = getattr(platform, "config", None)
  if cfg is None:
    return {}
  return dict(getattr(cfg, "dbc_dict", {}))


def _pick_preferred_dbc(dbc_names: list[str]) -> str | None:
  if not dbc_names:
    return None
  for name in dbc_names:
    if "_pt" in name or name.endswith("_pt"):
      return name
  return dbc_names[0]


def _suggest_dbc_for_fingerprint(car_fingerprint: str, *, brand: str = "") -> str | None:
  dbc_dict = _get_dbc_dict(car_fingerprint)
  if dbc_dict:
    return _pick_preferred_dbc(list(dbc_dict.values()))
  try:
    from opendbc.car.fingerprints import MIGRATION
    from openpilot.tools.cabana.dbc.generate_dbc_json import generate_dbc_dict

    platform = MIGRATION.get(car_fingerprint, car_fingerprint)
    dbc = generate_dbc_dict().get(platform)
    if dbc:
      return dbc
  except Exception:
    pass
  return _suggest_dbc_for_car({"carFingerprint": car_fingerprint, "brand": brand})


def _suggest_dbc_for_car(car: dict[str, Any]) -> str | None:
  dbc_dict = _get_dbc_dict(car.get("carFingerprint", ""))
  if dbc_dict:
    return _pick_preferred_dbc(list(dbc_dict.values()))

  fingerprint = (car.get("carFingerprint") or "").lower()
  brand = (car.get("brand") or "").lower()
  tokens = [t for t in re.split(r"[^a-z0-9]+", fingerprint) if len(t) >= 3]
  if brand:
    tokens.insert(0, brand)

  best_name = None
  best_score = 0
  for dbc_name in _list_dbc_names():
    dbc_lower = dbc_name.lower()
    score = 0
    for token in tokens:
      if token in dbc_lower:
        score += len(token)
    if "_pt" in dbc_lower:
      score += 3
    if score > best_score:
      best_score = score
      best_name = dbc_name
  return best_name if best_score > 0 else None


def _load_dbc_content(dbc_name: str) -> str | None:
  """Return raw DBC text for a given DBC name (user > generated > file).

  A user DBC (AI-assisted editing store) with the same name overrides the
  opendbc original — the opendbc directory itself is never written.

  Session safety: established decode sessions already hold their own parsed
  signal table (see decoder.get_decoder callers in replay_ws.py — the table is
  fetched once per session), so committing a new user version never mutates a
  running session; only sessions created afterwards pick it up.
  """
  if DBC is None:
    return None
  try:
    user_path = _user_dbc_dir() / f"{dbc_name}.dbc"
    if user_path.exists():
      return user_path.read_text()
  except Exception:
    pass
  try:
    generated = get_generated_dbcs()
    if dbc_name in generated:
      return generated[dbc_name]
  except Exception:
    pass
  dbc_path = Path(DBC_PATH) / f"{dbc_name}.dbc"
  if dbc_path.exists():
    return dbc_path.read_text()
  return None


# -----------------------------------------------------------------------------
# Raw DBC text annotation extraction (units / comments / value labels)
# -----------------------------------------------------------------------------

_SG_UNIT_RE = re.compile(r'^SG_\s+\w+.*?\)\s+\[[^\]]+\]\s+"([^"]*)"')
_CM_SIGNAL_RE = re.compile(r'^CM_\s+SG_\s+(\d+)\s+(\w+)\s+"((?:[^"\\]|\\.)*)"\s*;')
_CM_MESSAGE_RE = re.compile(r'^CM_\s+BO_\s+(\d+)\s+"((?:[^"\\]|\\.)*)"\s*;')
_VAL_RE = re.compile(r"^VAL_\s+(\d+)\s+(\w+)\s+(.*);\s*$")
_VAL_PAIR_RE = re.compile(r'(-?\d+)\s+"((?:[^"\\]|\\.)*)"')

# Annotation dict keys: (address, signal_name) for signals, (address, "") for messages.
_AnnUnitMap = dict[tuple[int, str], str]
_AnnCommentMap = dict[tuple[int, str], str]
_AnnValLabelMap = dict[tuple[int, str], dict[str, str]]


def _statement_complete(text: str) -> bool:
  """True if a DBC statement terminator `;` appears outside double quotes."""
  in_quote = False
  escaped = False
  for ch in text:
    if escaped:
      escaped = False
    elif ch == "\\":
      escaped = True
    elif ch == '"':
      in_quote = not in_quote
    elif ch == ";" and not in_quote:
      return True
  return False


def _extract_annotations(content: str) -> tuple[_AnnUnitMap, _AnnCommentMap, _AnnValLabelMap]:
  """Single-pass scan of raw DBC text for SG_ units, CM_ comments and VAL_ labels.

  Returns (units, comments, val_labels):
    - units: (address, signal) -> unit string from SG_ lines
    - comments: (address, signal) -> signal comment; (address, "") -> message comment
    - val_labels: (address, signal) -> {value_string: label} (original casing preserved)
  Malformed lines are silently skipped. Multi-line CM_/VAL_ statements are
  accumulated until a `;` appears outside double quotes (so comments containing
  semicolons are not truncated mid-statement).
  """
  units: _AnnUnitMap = {}
  comments: _AnnCommentMap = {}
  val_labels: _AnnValLabelMap = {}
  address = 0
  buffer = ""
  collecting: str | None = None  # None | "cm" | "val"

  def collect_cm(text: str) -> None:
    m = _CM_SIGNAL_RE.match(text)
    if m:
      addr = int(m.group(1))
      comments[(addr, m.group(2))] = m.group(3)
      return
    m = _CM_MESSAGE_RE.match(text)
    if m:
      comments[(int(m.group(1)), "")] = m.group(2)

  def collect_val(text: str) -> None:
    m = _VAL_RE.match(text)
    if not m:
      return
    addr = int(m.group(1))
    sig = m.group(2)
    labels = dict(_VAL_PAIR_RE.findall(m.group(3)))
    if labels:
      val_labels[(addr, sig)] = labels

  for raw_line in content.splitlines():
    line = raw_line.strip()
    if collecting is not None:
      buffer += " " + line
      if _statement_complete(buffer):
        if collecting == "cm":
          collect_cm(buffer)
        else:
          collect_val(buffer)
        collecting = None
      continue
    if line.startswith("BO_ "):
      parts = line.split()
      if len(parts) >= 2:
        try:
          address = int(parts[1], 0)
        except ValueError:
          pass
    elif line.startswith("SG_ "):
      m = _SG_UNIT_RE.match(line)
      if m:
        sig_name = line.split()[1]
        units[(address, sig_name)] = m.group(1)
    elif line.startswith("CM_"):
      if _statement_complete(line):
        collect_cm(line)
      else:
        buffer = line
        collecting = "cm"
    elif line.startswith("VAL_"):
      if _statement_complete(line):
        collect_val(line)
      else:
        buffer = line
        collecting = "val"
  return units, comments, val_labels


def _parse_dbc_signals(dbc_name: str) -> list[dict[str, Any]]:
  """Parse structure data from opendbc DBC and enrich with raw-text annotations."""
  if DBC is None:
    return []
  try:
    dbc = DBC(dbc_name)
  except Exception:
    return []
  content = _load_dbc_content(dbc_name)
  if content:
    units, comments, val_labels = _extract_annotations(content)
  else:
    units, comments, val_labels = {}, {}, {}
  signals = []
  for addr, msg in dbc.msgs.items():
    msg_comment = comments.get((addr, ""), "")
    for sig_name, sig in msg.sigs.items():
      comment = comments.get((addr, sig_name), "") or msg_comment
      signals.append({
        "address": addr,
        "message": msg.name,
        "signal": sig_name,
        "start_bit": sig.start_bit,
        "size": sig.size,
        "little_endian": sig.is_little_endian,
        "signed": sig.is_signed,
        "factor": sig.factor,
        "offset": sig.offset,
        "unit": units.get((addr, sig_name), ""),
        "comment": comment,
        "message_comment": msg_comment,
        "val_labels": val_labels.get((addr, sig_name), {}),
        "signal_type": int(getattr(sig, "type", 0) or 0),
      })
  return signals
