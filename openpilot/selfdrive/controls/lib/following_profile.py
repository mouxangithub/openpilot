#!/usr/bin/env python3
"""Speed-dependent following-time profiles (StarPilot personality port).

Upstream openpilot models the follow time as one number per personality:
1.25 s (aggressive), 1.45 s (standard), 1.75 s (relaxed). That number is then
used at every speed, so the same 1.45 s is applied at 30 km/h and at 130 km/h.

StarPilot replaces the scalar with a curve: the follow time is interpolated
over the vehicle speed, so the driver can ask for a shorter gap at city
speeds and a longer one on the highway (or the other way round).

This module holds the curve data and the interpolation. It is pure logic with
no openpilot imports, so it stays importable and unit testable on a PC host.

The curve is stored per personality in a JSON document:

    {
      "aggressive": {"preset": "close", "curve": [...]},
      "standard":   {"preset": "medium", "curve": [...]},
      "relaxed":    {"preset": "far", "curve": [...]}
    }

A custom personality carries an explicit 10-point curve on a 10 mph grid; the
named presets carry two-point curves on their own breakpoints, exactly as
StarPilot does.

Fail-closed on purpose: a malformed document is rejected as a whole and the
caller falls back to the stock scalar personalities. A partially applied
profile would be worse than no profile.
"""
import json
import math

# StarPilot verbatim: the named following presets and their two-point curves.
# The first value applies at the low breakpoint, the second at the high one.
FOLLOWING_PRESET_CURVES = {
  "close": (1.25, 1.0),
  "medium": (1.45, 1.2),
  "far": (1.6, 1.4),
}

# The named presets use their own breakpoints (mph), not the custom grid.
FOLLOWING_PRESET_SPEEDS_MPH = dict.fromkeys(FOLLOWING_PRESET_CURVES, (45.0, 70.0))

# The editable grid for a custom profile: 10 mph steps.
FOLLOWING_SPEEDS_MPH = list(range(0, 91, 10))

# Bounds for a custom curve's time headway, in seconds.
FOLLOWING_CURVE_MIN = 0.5
FOLLOWING_CURVE_MAX = 3.0

# mph -> m/s
MPH_TO_MS = 0.44704

# The personalities the upstream code knows about.
PERSONALITY_KEYS = ("aggressive", "standard", "relaxed")

# Which preset each personality falls back to when nothing is configured.
DEFAULT_PRESETS = {
  "aggressive": "close",
  "standard": "medium",
  "relaxed": "far",
}

# The stock scalar follow times, used when no profile is configured. These
# match openpilot's T_FOLLOW_DEFAULTS.
DEFAULT_T_FOLLOW = {
  "aggressive": 1.25,
  "standard": 1.45,
  "relaxed": 1.75,
}


def _linear_interp(value: float, breakpoints, values) -> float:
  """Piecewise linear interpolation with clamped ends."""
  if value <= breakpoints[0]:
    return float(values[0])
  if value >= breakpoints[-1]:
    return float(values[-1])
  index = next(i for i, point in enumerate(breakpoints[1:], start=1) if point >= value) - 1
  t = (value - breakpoints[index]) / float(breakpoints[index + 1] - breakpoints[index])
  return float(values[index] + t * (values[index + 1] - values[index]))


def _is_number(value) -> bool:
  # bool is a subclass of int in Python, and a bool in a curve is always a
  # mistake, so it is rejected explicitly.
  return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_category(config) -> dict | None:
  """Validate one personality's profile entry.

  Returns the normalized entry, or None when it is not usable. The whole
  document is rejected when any single entry fails, so a corrupt profile can
  never end up half applied.
  """
  if not isinstance(config, dict):
    return None

  preset = config.get("preset")
  curve = config.get("curve")

  if preset in FOLLOWING_PRESET_CURVES:
    # A named preset carries its own curve; an explicit one is ignored so
    # that a stale curve cannot silently override the preset.
    return {"preset": preset, "curve": list(FOLLOWING_PRESET_CURVES[preset])}

  if preset != "custom":
    return None

  if not isinstance(curve, (list, tuple)) or len(curve) != len(FOLLOWING_SPEEDS_MPH):
    return None

  normalized = []
  for value in curve:
    if not _is_number(value):
      return None
    value = float(value)
    if not math.isfinite(value):
      return None
    if not FOLLOWING_CURVE_MIN <= value <= FOLLOWING_CURVE_MAX:
      return None
    normalized.append(value)

  return {"preset": "custom", "curve": normalized}


def validate_profile_document(document) -> dict | None:
  """Validate a full profile document. Returns None when anything is wrong."""
  if not isinstance(document, dict):
    return None

  # An empty document means "not configured", which is a valid state.
  if not document:
    return {}

  validated = {}
  for key in PERSONALITY_KEYS:
    if key not in document:
      continue
    entry = validate_category(document[key])
    if entry is None:
      return None
    validated[key] = entry

  # Unknown keys are ignored rather than rejected: a document written by a
  # newer version should still be usable for the parts this fork understands.
  return validated


def load_profile_document(raw) -> dict | None:
  """Parse and validate a stored document. Returns None when unusable."""
  if raw is None:
    return None
  if isinstance(raw, dict):
    return validate_profile_document(raw)
  if isinstance(raw, bytes):
    try:
      raw = raw.decode("utf-8")
    except UnicodeDecodeError:
      return None
  if not isinstance(raw, str):
    return None
  if not raw.strip():
    return {}
  try:
    document = json.loads(raw)
  except (TypeError, ValueError):
    return None
  return validate_profile_document(document)


def serialize_profile_document(profiles: dict) -> str:
  """Serialize a profile document for storage."""
  canonical = {}
  for key in PERSONALITY_KEYS:
    entry = validate_category(profiles.get(key))
    if entry is not None:
      canonical[key] = entry
  return json.dumps(canonical, separators=(",", ":"), sort_keys=True, allow_nan=False)


def t_follow_for_personality(profile: dict | None, personality_key: str, v_ego: float) -> float | None:
  """Follow time for a personality at a given speed.

  Returns None when the profile has nothing for that personality, so the
  caller can fall back to the stock scalar.
  """
  if not profile or personality_key not in profile:
    return None
  entry = profile[personality_key]
  if not isinstance(entry, dict):
    return None

  if not _is_number(v_ego) or not math.isfinite(float(v_ego)):
    return None
  v_ego = float(v_ego)

  preset = entry.get("preset")
  curve = entry.get("curve")
  if not isinstance(curve, (list, tuple)) or len(curve) < 2:
    return None

  if preset == "custom":
    breakpoints = tuple(speed * MPH_TO_MS for speed in FOLLOWING_SPEEDS_MPH)
    # The custom grid is in mph but the interpolation runs on m/s.
    return _linear_interp(v_ego, breakpoints, curve)

  if preset in FOLLOWING_PRESET_SPEEDS_MPH:
    breakpoints = tuple(speed * MPH_TO_MS for speed in FOLLOWING_PRESET_SPEEDS_MPH[preset])
    return _linear_interp(v_ego, breakpoints, curve)

  return None


def personality_key(personality) -> str | None:
  """Map an openpilot LongitudinalPersonality enum to a profile key."""
  if isinstance(personality, str):
    name = personality
  elif isinstance(personality, int):
    name = {0: "aggressive", 1: "standard", 2: "relaxed"}.get(personality)
  else:
    name = getattr(personality, "name", None)
  if name in PERSONALITY_KEYS:
    return name
  return None
