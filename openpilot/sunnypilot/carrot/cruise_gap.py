"""Follow-gap cycling policy, shared by the carrot server (and formerly the
selfdrived CruiseHelper, removed with the DEC sunset).

Ported from cp's carrot/cruise_gap.py. These bound the gap cycle the distance
button drives and are kept as module functions so the policy has one home.

Only 3- and 4-level vehicles are supported; anything else is treated as 3,
matching cp. A reduced cycle (levels < vehicle max) still visits its own top
gap before wrapping, which is what next_gap_personality's `0 < current < levels`
ordering preserves.

Pure logic with no openpilot imports beyond types, so it stays importable and
unit testable on a PC host.
"""


# Number of entries in cereal's LongitudinalPersonality enum (aggressive/standard/
# relaxed). Used to clamp the value adopted from the car's own gap report; the MPC
# raises NotImplementedError for anything outside it, so this is a hard bound rather
# than a preference.
PERSONALITY_LEVELS = 3


def supported_gap_levels(value: int) -> int:
  return value if value in (3, 4) else 3


def cruise_gap_levels(requested: int, vehicle_max: int) -> int:
  maximum = supported_gap_levels(vehicle_max)
  return min(maximum, max(2, requested)) if requested > 0 else maximum


def next_gap_personality(current: int, levels: int) -> int:
  return current - 1 if 0 < current < levels else levels - 1
