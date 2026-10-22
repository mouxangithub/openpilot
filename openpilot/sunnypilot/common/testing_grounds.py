import json
import os
import threading
import time
from pathlib import Path

PC = not os.path.isfile("/AGNOS")  # mirrors openpilot.common.hardware.PC without its import chain

TESTING_GROUNDS_SCHEMA_VERSION = 1

TESTING_GROUND_1 = "1"
TESTING_GROUND_2 = "2"
TESTING_GROUND_3 = "3"
TESTING_GROUND_4 = "4"
TESTING_GROUND_5 = "5"
TESTING_GROUND_6 = "6"
TESTING_GROUND_7 = "7"
TESTING_GROUND_8 = "8"

TESTING_GROUND_IDS = (
  TESTING_GROUND_1,
  TESTING_GROUND_2,
  TESTING_GROUND_3,
  TESTING_GROUND_4,
  TESTING_GROUND_5,
  TESTING_GROUND_6,
  TESTING_GROUND_7,
  TESTING_GROUND_8,
)

TESTING_GROUNDS_STATE_PATH = Path("/tmp/the_galaxy_testing_grounds_slots.json") if PC else Path("/data/testing_grounds/slots.json")

# Edit slot names/descriptions once here. The Galaxy and runtime checks share this table.
# Slots named "Unused" are hidden from the dropdown.
# Adding cLabel/dLabel/etc. automatically adds more mode buttons for that slot in Testing Ground.
TESTING_GROUNDS_SLOT_DEFINITIONS = (
  {
    "id": TESTING_GROUND_1,
    "name": "ACC Bolt Long Tune",
    "description": "BoltLongTune A/B sandbox for GM ACC longitudinal testing.",
    "aLabel": "A - Installed tune",
    "bLabel": "B - Firestar Tune",
  },
  {
    "id": TESTING_GROUND_2,
    "name": "Volt Long Tune",
    "description": "Volt longitudinal tuning sandbox.",
    "aLabel": "A - Installed tune",
    "bLabel": "B - Firestar Tune",
  },
  {
    "id": TESTING_GROUND_3,
    "name": "Volt Lateral",
    "description": "Standard-tire Volt lateral A/B sandbox, separate from Plexy's custom tire-size tune.",
    "aLabel": "A - Installed tune",
    "bLabel": "B - Firestar Tune",
  },
  {
    "id": TESTING_GROUND_4,
    "name": "Genesis G90 Lateral",
    "description": "Genesis G90 2017 lateral A/B sandbox.",
    "aLabel": "A - Installed tune",
    "bLabel": "B - Firestar Tune",
  },
  {
    "id": TESTING_GROUND_5,
    "name": "EV6 GT-Line Long",
    "description": "Kia EV6 GT-Line longitudinal tuning sandbox.",
    "aLabel": "A - Installed tune",
    "bLabel": "B - EV6 GT-Line long tune",
  },
  {
    "id": TESTING_GROUND_6,
    "name": "Jwarm EV6",
    "description": "Jwarm's Kia EV6 lateral sandbox.",
    "aLabel": "A - Installed tune",
    "cLabel": "C - Firestar Tune",
  },
  {
    "id": TESTING_GROUND_7,
    "name": "Plexy's Car",
    "description": "Volt lateral A/B sandbox for Plexy's baseline torque tuning.",
    "aLabel": "A - Installed tune",
    "bLabel": "B - Firestar Tune",
  },
  {
    "id": TESTING_GROUND_8,
    "name": "Modified Civic Lateral",
    "description": "Modified Honda Civic Bosch lateral sandbox.",
    "aLabel": "A - Installed tune",
    "bLabel": "B - Firestar Tune",
  },
)


def _is_unused_testing_ground_slot(slot_definition):
  name = str(dict(slot_definition or {}).get("name") or "").strip().lower()
  return name == "unused" or name.startswith("unused ")


_VISIBLE_TESTING_GROUND_IDS = tuple(
  str(slot.get("id") or "").strip()
  for slot in TESTING_GROUNDS_SLOT_DEFINITIONS
  if str(slot.get("id") or "").strip() in TESTING_GROUND_IDS and not _is_unused_testing_ground_slot(slot)
)
_DEFAULT_ACTIVE_SLOT = _VISIBLE_TESTING_GROUND_IDS[0] if _VISIBLE_TESTING_GROUND_IDS else TESTING_GROUND_1
DEFAULT_TESTING_GROUND_VARIANT = "A"
TESTING_GROUND_TEST_VARIANT = "B"
_CACHE_LOCK = threading.Lock()
_CACHE_LAST_REFRESH = 0.0
_CACHE_LAST_MTIME_NS = -1
_CACHE_ACTIVE_SLOT = _DEFAULT_ACTIVE_SLOT
_CACHE_ACTIVE_VARIANT = DEFAULT_TESTING_GROUND_VARIANT


def _extract_variant_labels(slot_definition):
  labels = {}
  for key, value in dict(slot_definition).items():
    if not isinstance(key, str) or not key.endswith("Label"):
      continue
    variant = key[:-5].upper()
    if len(variant) != 1 or not variant.isalpha():
      continue
    label = str(value or "").strip()
    if label:
      labels[variant] = label

  if DEFAULT_TESTING_GROUND_VARIANT not in labels:
    labels[DEFAULT_TESTING_GROUND_VARIANT] = DEFAULT_TESTING_GROUND_VARIANT

  return dict(sorted(labels.items()))


TESTING_GROUND_VARIANT_LABELS = {
  str(slot.get("id") or "").strip(): _extract_variant_labels(slot)
  for slot in TESTING_GROUNDS_SLOT_DEFINITIONS
}
TESTING_GROUND_VARIANTS = tuple(
  sorted({
    variant
    for labels in TESTING_GROUND_VARIANT_LABELS.values()
    for variant in labels.keys()
  })
)


def _normalize_variant(value, slot_id=None):
  normalized_slot_id = str(slot_id or "").strip()
  allowed_variants = set(TESTING_GROUND_VARIANT_LABELS.get(normalized_slot_id, {}).keys())
  if not allowed_variants:
    allowed_variants = set(TESTING_GROUND_VARIANTS) or {DEFAULT_TESTING_GROUND_VARIANT}

  variant = str(value or "").strip().upper()
  return variant if variant in allowed_variants else DEFAULT_TESTING_GROUND_VARIANT


def _normalize_selection(slot_id, variant):
  normalized_slot_id = str(slot_id or "").strip()
  if normalized_slot_id not in _VISIBLE_TESTING_GROUND_IDS:
    return _DEFAULT_ACTIVE_SLOT, DEFAULT_TESTING_GROUND_VARIANT
  return normalized_slot_id, _normalize_variant(variant, normalized_slot_id)


def _write_testing_ground_selection(payload, slot_id, variant):
  normalized_payload = dict(payload) if isinstance(payload, dict) else {}
  normalized_payload["schemaVersion"] = TESTING_GROUNDS_SCHEMA_VERSION
  normalized_payload["activeSlot"] = slot_id
  normalized_payload["activeVariant"] = variant

  try:
    TESTING_GROUNDS_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = TESTING_GROUNDS_STATE_PATH.with_name(f".tmp_{TESTING_GROUNDS_STATE_PATH.name}")
    tmp_path.write_text(json.dumps(normalized_payload, indent=2), encoding="utf-8")
    tmp_path.replace(TESTING_GROUNDS_STATE_PATH)
    return TESTING_GROUNDS_STATE_PATH.stat().st_mtime_ns
  except Exception:
    return None


def get_testing_ground_selection(refresh_interval_s=0.5):
  global _CACHE_LAST_REFRESH, _CACHE_LAST_MTIME_NS, _CACHE_ACTIVE_SLOT, _CACHE_ACTIVE_VARIANT

  now = time.monotonic()
  with _CACHE_LOCK:
    if (now - _CACHE_LAST_REFRESH) < refresh_interval_s:
      return _CACHE_ACTIVE_SLOT, _CACHE_ACTIVE_VARIANT
    _CACHE_LAST_REFRESH = now

    try:
      stat_result = TESTING_GROUNDS_STATE_PATH.stat()
    except FileNotFoundError:
      _CACHE_LAST_MTIME_NS = -1
      _CACHE_ACTIVE_SLOT = _DEFAULT_ACTIVE_SLOT
      _CACHE_ACTIVE_VARIANT = DEFAULT_TESTING_GROUND_VARIANT
      return _CACHE_ACTIVE_SLOT, _CACHE_ACTIVE_VARIANT
    except OSError:
      return _CACHE_ACTIVE_SLOT, _CACHE_ACTIVE_VARIANT

    if stat_result.st_mtime_ns == _CACHE_LAST_MTIME_NS:
      return _CACHE_ACTIVE_SLOT, _CACHE_ACTIVE_VARIANT

    try:
      payload = json.loads(TESTING_GROUNDS_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
      return _CACHE_ACTIVE_SLOT, _CACHE_ACTIVE_VARIANT

    if not isinstance(payload, dict):
      return _CACHE_ACTIVE_SLOT, _CACHE_ACTIVE_VARIANT

    raw_slot_id = str(payload.get("activeSlot") or "").strip()
    raw_variant = payload.get("activeVariant")
    normalized_slot_id, normalized_variant = _normalize_selection(raw_slot_id, raw_variant)
    raw_variant_text = str(raw_variant or "").strip().upper()
    if (
      payload.get("schemaVersion") != TESTING_GROUNDS_SCHEMA_VERSION or
      raw_slot_id != normalized_slot_id or
      raw_variant_text != normalized_variant
    ):
      migrated_mtime_ns = _write_testing_ground_selection(payload, normalized_slot_id, normalized_variant)
      if migrated_mtime_ns is not None:
        _CACHE_LAST_MTIME_NS = migrated_mtime_ns
      else:
        _CACHE_LAST_MTIME_NS = stat_result.st_mtime_ns
    else:
      _CACHE_LAST_MTIME_NS = stat_result.st_mtime_ns

    _CACHE_ACTIVE_SLOT = normalized_slot_id
    _CACHE_ACTIVE_VARIANT = normalized_variant
    return _CACHE_ACTIVE_SLOT, _CACHE_ACTIVE_VARIANT


def is_testing_ground_active(slot_id, variant=TESTING_GROUND_TEST_VARIANT, refresh_interval_s=0.5):
  active_slot, active_variant = get_testing_ground_selection(refresh_interval_s=refresh_interval_s)
  normalized_slot_id = str(slot_id or "").strip()
  target_variant = _normalize_variant(variant, normalized_slot_id)
  return normalized_slot_id == active_slot and active_variant == target_variant


class _TestingGroundFlag:
  __slots__ = ("slot_id", "variant")

  def __init__(self, slot_id, variant=TESTING_GROUND_TEST_VARIANT):
    self.slot_id = str(slot_id or "").strip()
    self.variant = _normalize_variant(variant, self.slot_id)

  def __bool__(self):
    return is_testing_ground_active(self.slot_id, self.variant)

  def __repr__(self):
    state = "active" if bool(self) else "inactive"
    return f"<TestingGroundFlag slot={self.slot_id} variant={self.variant} {state}>"


use_testing_ground_1 = _TestingGroundFlag(TESTING_GROUND_1)
use_testing_ground_2 = _TestingGroundFlag(TESTING_GROUND_2)
use_testing_ground_3 = _TestingGroundFlag(TESTING_GROUND_3)
use_testing_ground_4 = _TestingGroundFlag(TESTING_GROUND_4)
use_testing_ground_5 = _TestingGroundFlag(TESTING_GROUND_5)
use_testing_ground_6 = _TestingGroundFlag(TESTING_GROUND_6)
use_testing_ground_7 = _TestingGroundFlag(TESTING_GROUND_7)
use_testing_ground_8 = _TestingGroundFlag(TESTING_GROUND_8)


class _TestingGroundNamespace:
  __slots__ = ()

  id_1 = TESTING_GROUND_1
  id_2 = TESTING_GROUND_2
  id_3 = TESTING_GROUND_3
  id_4 = TESTING_GROUND_4
  id_5 = TESTING_GROUND_5
  id_6 = TESTING_GROUND_6
  id_7 = TESTING_GROUND_7
  id_8 = TESTING_GROUND_8

  use_1 = use_testing_ground_1
  use_2 = use_testing_ground_2
  use_3 = use_testing_ground_3
  use_4 = use_testing_ground_4
  use_5 = use_testing_ground_5
  use_6 = use_testing_ground_6
  use_7 = use_testing_ground_7
  use_8 = use_testing_ground_8

  def use(self, slot_id, variant=TESTING_GROUND_TEST_VARIANT):
    return is_testing_ground_active(slot_id, variant)

  def selection(self):
    return get_testing_ground_selection()


testing_ground = _TestingGroundNamespace()
