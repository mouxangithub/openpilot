"""Signal evidence palette and the advisory HUD rules.

Ported from carrot's ``selfdrive/ui/signal_status.py``. carrot's module reads
``longitudinalPlan``; here the caller passes the two ``LongitudinalPlanSP``
fields instead, so this module stays free of cereal and pyray and the colour /
visibility decisions can be unit-tested off-device.
"""

# Evidence codes shared by the planner field and the HUD palette index.
SIGNAL_UNKNOWN = 0
SIGNAL_RED = 1
SIGNAL_GREEN = 2
SIGNAL_MIXED = 3

# unknown / red / green / mixed
SIGNAL_PALETTE = (
  (160, 165, 170, 255),
  (255, 75, 75, 255),
  (60, 255, 120, 255),
  (255, 185, 40, 255),
)

# carrot's swap, kept on purpose: green evidence paints amber while mixed
# evidence paints green, so a mixed reading can never look like "cleared to go".
SIGNAL_DOT_COLORS = {
  SIGNAL_RED: SIGNAL_PALETTE[1],
  SIGNAL_GREEN: SIGNAL_PALETTE[3],
  SIGNAL_MIXED: SIGNAL_PALETTE[2],
}

# how far a suspended ring is dimmed
SIGNAL_SUSPENDED_DIM = 0.55

# Radar point boxes: blue is a vision-only point, green is carrot's 0.01
# low-confidence model match.
POINT_COLOR_VISION_ONLY = (0, 0, 255, 255)
POINT_COLOR_LOW_CONFIDENCE = (0, 203, 0, 255)
POINT_COLOR_APPROACHING = (0, 203, 0, 255)
POINT_COLOR_RECEDING = (255, 0, 0, 255)
POINT_COLOR_BACKDROP = (20, 25, 30, 255)
POINT_COLOR_SHADOW = (0, 0, 0, 200)


def signal_action(plan, default: int = SIGNAL_UNKNOWN) -> int:
  """Read the planner's advisory action, normalising anything unexpected."""
  try:
    value = int(getattr(plan, 'signalAssistAction', default))
  except (AttributeError, TypeError, ValueError):
    return default
  return value if value in (SIGNAL_RED, SIGNAL_GREEN, SIGNAL_MIXED) else default


def signal_suspended(plan) -> bool:
  """Whether detection is parked (motorway road class, missing nav, ...)."""
  try:
    return bool(getattr(plan, 'signalDetectionSuspended', False))
  except (AttributeError, TypeError, ValueError):
    return False


def signal_visible(action, suspended) -> bool:
  """Whether the HUD has anything to say: a known action, or a parked detection."""
  return bool(action) or bool(suspended)


def signal_colors(action, suspended) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int] | None]:
  """Ring colour for the fresh evidence and the planner's dot (None without an action)."""
  try:
    value = int(action)
  except (TypeError, ValueError):
    value = SIGNAL_UNKNOWN
  if value not in (SIGNAL_RED, SIGNAL_GREEN, SIGNAL_MIXED):
    value = SIGNAL_UNKNOWN

  ring = tuple(SIGNAL_PALETTE[value])
  if suspended:
    ring = tuple(int(v * SIGNAL_SUSPENDED_DIM) for v in ring[:3]) + (255,)
  dot = SIGNAL_DOT_COLORS.get(value)
  return ring, (tuple(dot) if dot else None)


def point_box_color(v_sum: float, radar: bool, model_prob: float) -> tuple[int, int, int, int]:
  """Blue = vision only, green = low-confidence match, amber = closing, red = opening."""
  if not radar:
    return POINT_COLOR_VISION_ONLY
  if model_prob == 0.01:
    return POINT_COLOR_LOW_CONFIDENCE
  return SIGNAL_PALETTE[SIGNAL_MIXED] if v_sum > 0.0 else SIGNAL_PALETTE[SIGNAL_RED]
