"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Three-channel jerk scaling for the longitudinal MPC.

The stock personality path scales every jerk-related cost with one number,
so a driver who wants a gentler acceleration also gets a gentler approach to
the car ahead and a gentler speed change - the three are not actually the
same thing, and the user cannot tell them apart.

Splitting them lets each be tuned on its own:

  * ``accel`` scales the acceleration-change cost, so it is how sharply the
    car changes its acceleration;
  * ``danger`` scales the cost inside the danger zone around the lead, so it
    is how hard the car works to keep its distance;
  * ``speed`` scales the jerk cost, so it is how smoothly the speed itself
    changes.

A value of 1.0 leaves the channel exactly as the stock tuning had it, so the
default is behaviour-preserving.

Pure logic with no openpilot imports, so it stays importable and unit
testable on a PC host.
"""

# The three channels, in the order the MPC consumes them.
CHANNELS = ("accel", "danger", "speed")

# The scale below which a value is treated as unusable and the default is
# used instead. A zero or negative factor would remove a cost term entirely,
# which is not what a user asking for "a bit smoother" means.
MIN_FACTOR = 0.25
MAX_FACTOR = 2.0

# The stock single-factor values, used when the per-channel values are not
# configured. Aggressive is quicker on all three; the others sit at 1.0.
STOCK_FACTORS = {
  "aggressive": (0.5, 1.0, 0.5),
  "standard": (1.0, 1.0, 1.0),
  "relaxed": (1.0, 1.0, 1.0),
}


def clamp_factor(value, default: float = 1.0) -> float:
  """A usable factor from a user-supplied number.

  A value that is not a number, or that falls outside the allowed range, is
  replaced by the default rather than reaching the solver: a zero factor
  would drop a cost term and change the car's behaviour in a way the user
  did not ask for.
  """
  try:
    factor = float(value)
  except (TypeError, ValueError):
    return default
  if factor != factor:  # NaN
    return default
  return float(min(max(factor, MIN_FACTOR), MAX_FACTOR))


def parse_factors(raw_values, default: tuple[float, float, float] = (1.0, 1.0, 1.0)) -> tuple[float, float, float]:
  """Three factors from a sequence of user-supplied values.

  A short or missing sequence falls back to the default for the channels it
  does not cover, so adding a channel later cannot break an older
  configuration.
  """
  values = list(raw_values or [])
  factors = []
  for index in range(3):
    if index < len(values):
      factors.append(clamp_factor(values[index], default[index]))
    else:
      factors.append(default[index])
  return (factors[0], factors[1], factors[2])


def factors_for_personality(personality: str, overrides: dict[str, tuple[float, float, float]] | None = None) -> tuple[float, float, float]:
  """The three factors for a personality, with the user's overrides applied.

  The overrides are the per-personality values the user configured; a
  personality with no override keeps the stock factors.
  """
  base = STOCK_FACTORS.get(personality, STOCK_FACTORS["standard"])
  if overrides and personality in overrides:
    return parse_factors(overrides[personality], base)
  return base
