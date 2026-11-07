import time


CARROT_MAN_TIMEOUT = 1.0


def get_carrot_man(sm, service: str = 'carrotManSP'):
  """Return a received navigation cap, never the zero-initialized SubMaster value.

  carrotManSP is registered as an on-demand service, so alive/valid alone do not
  prove that it has published anything or that its last message is still fresh.
  Its publisher normally runs at 20 Hz. Navigation caps must be positive;
  traffic/lead stopping is handled independently by the longitudinal planner.

  Ported from CarrotPilot's carrot_man_input.get_carrot_man; the service name
  defaults to this fork's carrotManSP (cp's legacy 'carrotMan' is not registered
  in sunnypilot's cereal/services.py).
  """
  seen, alive, valid = getattr(sm, 'seen', None), getattr(sm, 'alive', None), getattr(sm, 'valid', None)
  recv_time = getattr(sm, 'recv_time', None)
  if None in (seen, alive, valid, recv_time) or service not in seen:
    return None  # minimal SubMaster stand-ins (plant tests) never claim a live carrotManSP
  if not (seen[service] and alive[service] and valid[service]):
    return None
  age = time.monotonic() - recv_time[service]
  if not 0.0 <= age <= CARROT_MAN_TIMEOUT:
    return None
  carrot_man = sm[service]
  return carrot_man if 0 < carrot_man.desiredSpeed <= 250 else None
