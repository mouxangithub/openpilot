"""Turn-signal lever rules (CarrotPilot port, CP-1).

Ported from carrot: selfdrive/controls/lib/desire_lib/lever.py::lever_maneuver
(reference: selfdrive/controls/lib/desire_helper.py lever usage).

carState.blinkerLever (Hyundai CAN-FD) encodes the physical lever position:
0 released, 1 one-touch (half) detent, 2 latched. The lamp-based left/right
blinker booleans cannot tell a held lever from a one-touch flick; the lever
position can, so it decides turn vs lane change.

sunnypilot's car.capnp does not carry blinkerLever yet. Consumers must read it
with getattr(carstate, "blinkerLever", None) and fall back to the legacy
blinker-only behavior when the signal is absent (None), which keeps cars
without the signal (e.g. Toyota) bit-identical to the pre-port behavior.
"""

LEVER_RELEASED, LEVER_ONE_TOUCH, LEVER_LATCHED = 0, 1, 2


def lever_maneuver(lever: int, v_ego: float, turn_speed_max: float, forced_turn: bool = False):
  """(maneuver, undecided) chosen by the driver's lever, or (None, False) when the lever does not decide.

  turn_speed_max (m/s, 0 = off). At or below it only the forced-turn gesture (one-touch, two lamp
  lightings, then latched) is a turn; a plain latch, like a one-touch, is a lane change (e.g. holding
  the signal for the next lane). A lever still in the one-touch detent is undecided, because a latch
  passes through it for ~0.1 s. Above it every lever input is a lane change.

  On sunnypilot there is no carState.blinkerLamp, so callers approximate the forced-turn gesture
  with the lever position itself (a latched lever is the driver holding the turn signal).
  """
  if turn_speed_max <= 0:
    return None, False
  if v_ego > turn_speed_max:
    return "lane_change", False
  if forced_turn:
    return "turn", False
  return "lane_change", lever == LEVER_ONE_TOUCH
