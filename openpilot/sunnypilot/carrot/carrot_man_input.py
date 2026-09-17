from __future__ import annotations
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""
Helpers for controlsd to safely consume carrot navigation packets.

Ported from CarrotPilot's selfdrive/carrot/carrot_man_input.py. The helper
guards against using a stale or zero-initialized SubMaster value.
"""

import time


CARROT_MAN_TIMEOUT = 1.0


def get_carrot_man(sm):
  """Return a received navigation cap, never the zero-initialized SubMaster value.

  carrotManSP is registered as an on-demand service, so alive/valid alone do not
  prove that it has published anything or that its last message is still fresh.
  Its publisher normally runs at 20 Hz. Navigation caps must be positive;
  traffic/lead stopping is handled independently by the longitudinal planner.
  """
  service = 'carrotManSP'
  if not (sm.seen.get(service, False) and sm.alive.get(service, False) and sm.valid.get(service, False)):
    return None
  age = time.monotonic() - sm.recv_time.get(service, 0.0)
  if not 0.0 <= age <= CARROT_MAN_TIMEOUT:
    return None
  carrot_man = sm[service]
  desired_speed = getattr(carrot_man, "desiredSpeed", 0) or 0
  return carrot_man if 0 < desired_speed <= 250 else None
