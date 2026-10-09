"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of zoompilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

zoompilot's curve speed planners (vision and map), tuned from measurements of the brands
listed here. Every other brand runs sunnypilot's own controllers, unchanged.
See docs/zoompilot/scc-curve-planning.md.
"""

# brands whose stock ACC response and planning limits have been measured from their logs
TUNED_BRANDS = ('mazda',)


def make_smart_cruise_control(CP):
  if CP.brand in TUNED_BRANDS:
    from openpilot.sunnypilot.selfdrive.controls.lib.smart_cruise_control.zoompilot.smart_cruise_control import SmartCruiseControl
    return SmartCruiseControl(CP)
  from openpilot.sunnypilot.selfdrive.controls.lib.smart_cruise_control.smart_cruise_control import SmartCruiseControl
  return SmartCruiseControl()
