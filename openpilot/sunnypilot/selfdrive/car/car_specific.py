"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

from openpilot.cereal import log, custom
from opendbc.car import structs

from opendbc.car.chrysler.values import RAM_DT
from openpilot.selfdrive.selfdrived.events import Events
from openpilot.sunnypilot.selfdrive.selfdrived.events import EventsSP

EventName = log.OnroadEvent.EventName
EventNameSP = custom.OnroadEventSP.EventName
GearShifter = structs.CarState.GearShifter


class CarSpecificEventsSP:
  def __init__(self, CP: structs.CarParams, CP_SP: structs.CarParamsSP):
    self.CP = CP
    self.CP_SP = CP_SP

    self.low_speed_alert = False

  def update(self, CS: structs.CarState, events: Events, mads_enabled: bool = False):
    events_sp = EventsSP()
    self.mads_enabled = mads_enabled

    if self.CP.brand == 'chrysler':
      if self.CP.carFingerprint in RAM_DT:
        # remove belowSteerSpeed event from CarSpecificEvents as RAM_DT uses a different logic
        if events.has(EventName.belowSteerSpeed):
          events.remove(EventName.belowSteerSpeed)

        # TODO-SP: use if/elif to have the gear shifter condition takes precedence over the speed condition
        # TODO-SP: add 1 m/s hysteresis
        if CS.vEgo >= self.CP.minEnableSpeed:
          self.low_speed_alert = False
        if self.CP.minEnableSpeed >= 14.5 and CS.gearShifter != GearShifter.drive:
          self.low_speed_alert = True
      if self.low_speed_alert:
        events.add(EventName.belowSteerSpeed)

    elif self.CP.brand == 'toyota':
      if self.CP.openpilotLongitudinalControl:
        if CS.cruiseState.standstill and not CS.brakePressed and self.CP_SP.enableGasInterceptor:
          if events.has(EventName.resumeRequired):
            events.remove(EventName.resumeRequired)

    elif self.CP.brand == 'mazda':
      # Mazda: invalidLkasSetting is swapped for stockLkasOff when MADS is on.
      # No alert of its own: the button press on the same frame already speaks; the no-entry
      # is for later enable attempts with LKA still off.
      if getattr(self, 'mads_enabled', False) and events.has(EventName.invalidLkasSetting):
        events.remove(EventName.invalidLkasSetting)
        events_sp.add(EventNameSP.stockLkasOff)
      # LKA back on with lateral resuming, the EPS not delivering yet: still disabled to the driver.
      if getattr(self, 'mads_enabled', False) and getattr(CS, 'lkas_arming', False):
        events_sp.add(EventNameSP.stockLkasArming)

    return events_sp
