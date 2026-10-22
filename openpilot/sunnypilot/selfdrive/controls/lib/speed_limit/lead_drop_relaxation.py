"""Comfort relaxation for a sudden speed-limit drop while following a lead.

A limit that drops from 70 to 45 km/h while the car is tucked in behind
traffic does not need an emergency stop: the lead is doing the braking and
the car has a whole gap of runway. Slamming to the new limit anyway turns a
non-event into a lurch. This module slews the limit target down at a comfort
rate instead, and it only does so when every condition that makes the
non-event a non-event actually holds:

- the car is genuinely following a lead, and has been for a while
  (a flickering track is not a lead);
- the lead is far enough away, both in metres and in time headway;
- the lead is not itself braking hard;
- the new limit is below the car's speed and the target is actually
  dropping (otherwise there is nothing to soften);
- the driver is not overriding.

Any veto falls straight through to the raw target. The relaxation can only
ever raise the commanded target above the raw one for a few frames; it never
slows the car below the raw target, so the worst case is always the unrelaxed
behaviour. This is the boundary between comfort and safety, so the veto list
is deliberately kept verbatim from the design it was ported from rather than
"improved".

Pure logic: no openpilot imports, no Params, no messaging. The planner feeds
it values and consumes the answer.
"""

# Veto thresholds, verbatim from the reference implementation.
MIN_SPEED = 20.0 * 0.44704          # 20 mph in m/s: below this, just brake.
MIN_DISTANCE = 30.0                 # metres: closer than this, just brake.
MIN_HEADWAY = 1.2                   # seconds of headway, whichever is larger.
MAX_POST_DROP_CLOSING_SPEED = 0.35  # lead slower than the new target by more
                                    # than this -> the drop is real, honour it.
MAX_LEAD_BRAKE = 0.25               # lead decelerating harder than this -> no.

# Comfort deceleration looked up by how far above the new limit the car is.
# More overspeed -> a somewhat firmer (still comfort-class) rate.
OVERSPEED_BP = (0.0, 5.0 * 0.44704, 10.0 * 0.44704, 15.0 * 0.44704)
DECEL_V = (0.7, 0.9, 1.15, 1.35)

# The lead must have been present this many consecutive updates before the
# relaxation trusts it. Half a second at the model rate: long enough to look
# through a flickering radar track, short enough to engage in real traffic.
LEAD_PERSIST_FRAMES = 25

EPS = 1e-3


def interp_linear(x: float, xp, fp) -> float:
  """Piecewise-linear interpolation with clamping, the same shape as the
  reference implementation: exact at the break points, flat outside."""
  if x <= xp[0]:
    return fp[0]
  if x >= xp[-1]:
    return fp[-1]
  for i in range(1, len(xp)):
    if x <= xp[i]:
      span = xp[i] - xp[i - 1]
      if span <= 0.0:
        return fp[i]
      ratio = (x - xp[i - 1]) / span
      return fp[i - 1] + ratio * (fp[i] - fp[i - 1])
  return fp[-1]


def lead_brake(a_lead_k: float) -> float:
  """How hard the lead is decelerating, floored at zero."""
  return max(0.0, -float(a_lead_k))


class LeadDropRelaxation:
  """Slews a dropping speed-limit target while a stable lead is followed.

  State is one persisted target and one lead-presence counter; ``reset()``
  is for disengagement boundaries (long disabled, override, offroad).
  """

  def __init__(self, dt: float):
    self.dt = float(dt)
    self._applied_target = 0.0
    self._lead_frames = 0

  def reset(self) -> None:
    self._applied_target = 0.0
    self._lead_frames = 0

  def _update_lead_persistence(self, lead_present: bool) -> None:
    if lead_present:
      self._lead_frames += 1
    else:
      self._lead_frames = 0

  @property
  def lead_trusted(self) -> bool:
    return self._lead_frames >= LEAD_PERSIST_FRAMES

  def relax(self, raw_target: float, v_ego: float, *,
            lead_present: bool, lead_status: bool,
            d_rel: float, v_lead: float, a_lead_k: float,
            override_active: bool) -> float:
    """The target to actually feed the planner this update.

    ``lead_*`` describe the primary radar lead; pass zeros and
    ``lead_present=False`` when there is none. The returned value is never
    below ``raw_target``.
    """
    self._update_lead_persistence(lead_present)

    # Nothing to soften: the target is not a usable speed, the driver is
    # asking for something else, or there is no trusted lead.
    if raw_target <= 0.0 or self._applied_target <= 0.0:
      self._remember(raw_target)
      return raw_target
    if override_active or not lead_status or not self.lead_trusted:
      self._remember(raw_target)
      return raw_target

    # Only a drop gets softened; a rise (or a re-rise after a scrape) goes
    # through immediately.
    if raw_target >= self._applied_target - EPS:
      self._remember(raw_target)
      return raw_target

    # The car has to be moving and above the new limit for this to be a
    # "the limit dropped under us" situation rather than a normal approach.
    if v_ego < MIN_SPEED or raw_target >= v_ego - 0.05:
      self._remember(raw_target)
      return raw_target

    # A close lead means the gap cannot absorb the change.
    if d_rel < max(MIN_DISTANCE, v_ego * MIN_HEADWAY):
      self._remember(raw_target)
      return raw_target

    # A lead that ends up well below the new limit, or one that brakes
    # hard, is an obstacle: honour the raw target.
    if v_lead < raw_target - MAX_POST_DROP_CLOSING_SPEED:
      self._remember(raw_target)
      return raw_target
    if lead_brake(a_lead_k) > MAX_LEAD_BRAKE:
      self._remember(raw_target)
      return raw_target

    overspeed = max(0.0, v_ego - raw_target)
    comfort_decel = interp_linear(overspeed, OVERSPEED_BP, DECEL_V)
    target = max(float(raw_target), self._applied_target - comfort_decel * self.dt)
    self._remember(target)
    return target

  def _remember(self, target: float) -> None:
    self._applied_target = float(target) if target > 0.0 else 0.0
