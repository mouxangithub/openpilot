"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Which conditions are allowed to hand speed control to the driving model.

The controller itself decides *when* to blend from the signals it reads; the
question these settings answer is *whether a given kind of situation is
allowed to trigger it at all*. A driver who is happy with the model slowing
for a curve may still not want it taking over for a distant stopped car, and
the reverse.

Each trigger is independent. All of them default to on, which reproduces the
behaviour the controller had before these switches existed: the gating is a
restriction layer, not a new policy.

Pure logic with no openpilot imports, so it stays importable and unit
testable on a PC host.
"""

# Trigger ids, in the order the settings page shows them. The strings are the
# stable part: they name the parameter, so renaming one would silently reset a
# user's choice.
TRIGGER_CURVE = "curve"
TRIGGER_LEAD = "lead"
TRIGGER_SIGNAL = "signal"
TRIGGER_STOP_LIGHT = "stop_light"
TRIGGER_LOW_SPEED = "low_speed"

TRIGGERS = (TRIGGER_CURVE, TRIGGER_LEAD, TRIGGER_SIGNAL, TRIGGER_STOP_LIGHT, TRIGGER_LOW_SPEED)

TRIGGER_PARAM_KEYS = {
  TRIGGER_CURVE: "DynamicExperimentalTriggerCurve",
  TRIGGER_LEAD: "DynamicExperimentalTriggerLead",
  TRIGGER_SIGNAL: "DynamicExperimentalTriggerSignal",
  TRIGGER_STOP_LIGHT: "DynamicExperimentalTriggerStopLight",
  TRIGGER_LOW_SPEED: "DynamicExperimentalTriggerLowSpeed",
}


def trigger_allowed(trigger: str, enabled: dict[str, bool] | None) -> bool:
  """Whether a trigger may hand control to the model.

  An unknown trigger, or a missing entry in the map, is allowed: a settings
  document that predates a trigger must not silently disable it.
  """
  if not enabled:
    return True
  return bool(enabled.get(trigger, True))


def triggers_from_values(raw: dict[str, object] | None) -> dict[str, bool]:
  """The per-trigger switches from raw parameter values.

  A value that is not a recognised boolean reads as on, so an unreadable
  setting never changes the car's behaviour.
  """
  if not raw:
    return dict.fromkeys(TRIGGERS, True)

  out = {}
  for trigger in TRIGGERS:
    value = raw.get(trigger, True)
    if isinstance(value, str):
      out[trigger] = value.strip() not in ("0", "false", "False", "")
    else:
      out[trigger] = bool(value)
  return out
