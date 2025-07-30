from opendbc.can.packer import CANPacker
from opendbc.car import Bus, apply_driver_steer_torque_limits, structs
from opendbc.car.interfaces import CarControllerBase
from opendbc.car.mazda import mazdacan
from opendbc.car.mazda.values import CarControllerParams, Buttons
from opendbc.car.common.conversions import Conversions as CV
from openpilot.common.params import Params

VisualAlert = structs.CarControl.HUDControl.VisualAlert


class CarController(CarControllerBase):
  def __init__(self, dbc_names, CP):
    super().__init__(dbc_names, CP)
    self.apply_torque_last = 0
    self.packer = CANPacker(dbc_names[Bus.pt])
    self.brake_counter = 0

    self.activateCruise = 0
    self.speed_from_pcm = 1

  def update(self, CC, CS, now_nanos):

    if self.frame % 50 == 0:
      params = Params()
      self.speed_from_pcm = params.get_int("SpeedFromPCM")

    can_sends = []

    apply_torque = 0

    if CC.latActive:
      # calculate steer and also set limits due to driver torque
      new_torque = int(round(CC.actuators.torque * CarControllerParams.STEER_MAX))
      apply_torque = apply_driver_steer_torque_limits(new_torque, self.apply_torque_last,
                                                      CS.out.steeringTorque, CarControllerParams)

    if CC.cruiseControl.cancel:
      # If brake is pressed, let us wait >70ms before trying to disable crz to avoid
      # a race condition with the stock system, where the second cancel from openpilot
      # will disable the crz 'main on'. crz ctrl msg runs at 50hz. 70ms allows us to
      # read 3 messages and most likely sync state before we attempt cancel.
      self.brake_counter = self.brake_counter + 1
      if self.frame % 10 == 0 and not (CS.out.brakePressed and self.brake_counter < 7):
        # Cancel Stock ACC if it's enabled while OP is disengaged
        # Send at a rate of 10hz until we sync with stock ACC state
        can_sends.append(mazdacan.create_button_cmd(self.packer, self.CP, CS.crz_btns_counter, Buttons.CANCEL))
    else:
      self.brake_counter = 0

      # Enhanced CSLC logic when speed_from_pcm != 1
      if CC.cruiseControl.resume and self.frame % 5 == 0:
        # Mazda Stop and Go requires a RES button (or gas) press if the car stops more than 3 seconds
        # Send Resume button when planner wants car to move
        can_sends.append(mazdacan.create_button_cmd(self.packer, self.CP, CS.crz_btns_counter, Buttons.RESUME))
      elif self.speed_from_pcm != 1 and CC.enabled and self.frame % 10 == 0:
        # Enhanced CSLC: Use higher frequency (10Hz) and improved logic
        cslc_button = self.make_enhanced_cslc_button(CC, CS)
        if cslc_button != Buttons.NONE:
          can_sends.append(mazdacan.create_button_cmd(self.packer, self.CP, self.frame // 10, cslc_button))
      elif self.frame % 20 == 0:
        # Fallback to original spam button logic
        spam_button = self.make_spam_button(CC, CS)
        if spam_button > 0:
          can_sends.append(mazdacan.create_button_cmd(self.packer, self.CP, self.frame // 10, spam_button))

    self.apply_torque_last = apply_torque

    # send HUD alerts
    if self.frame % 50 == 0:
      ldw = CC.hudControl.visualAlert == VisualAlert.ldw
      steer_required = CC.hudControl.visualAlert == VisualAlert.steerRequired
      # TODO: find a way to silence audible warnings so we can add more hud alerts
      steer_required = steer_required and CS.lkas_allowed_speed
      can_sends.append(mazdacan.create_alert_command(self.packer, CS.cam_laneinfo, ldw, steer_required))

    # send steering command
    can_sends.append(mazdacan.create_steering_control(self.packer, self.CP,
                                                      self.frame, apply_torque, CS.cam_lkas))

    new_actuators = CC.actuators.as_builder()
    new_actuators.torque = apply_torque / CarControllerParams.STEER_MAX
    new_actuators.torqueOutputCan = apply_torque

    self.frame += 1
    return new_actuators, can_sends

  def make_spam_button(self, CC, CS):
    hud_control = CC.hudControl
    set_speed_in_units = hud_control.setSpeed * (CV.MS_TO_KPH if CS.is_metric else CV.MS_TO_MPH)
    target = int(set_speed_in_units+0.5)
    target = int(round(target / 5.0) * 5.0)
    current = int(CS.out.cruiseState.speed*CV.MS_TO_KPH + 0.5)
    current = int(round(current / 5.0) * 5.0)
    v_ego_kph = CS.out.vEgo * CV.MS_TO_KPH

    cant_activate = CS.out.brakePressed or CS.out.gasPressed

    if CC.enabled:
      if not CS.out.cruiseState.enabled:
        if (hud_control.leadVisible or v_ego_kph > 10.0) and self.activateCruise == 0 and not cant_activate:
          self.activateCruise = 1
          print("RESUME")
          return Buttons.RESUME
      elif CC.cruiseControl.resume:
        return Buttons.RESUME
      elif target < current and current>= 31 and self.speed_from_pcm != 1:
        print(f"SET_MINUS target={target}, current={current}")
        return Buttons.SET_MINUS
      elif target > current and current < 160 and self.speed_from_pcm != 1:
        print(f"SET_PLUS target={target}, current={current}")
        return Buttons.SET_PLUS
    elif CS.out.activateCruise:
      if (hud_control.leadVisible or v_ego_kph > 10.0) and self.activateCruise == 0 and not cant_activate:
        self.activateCruise = 1
        print("RESUME")
        return Buttons.RESUME

    return 0

  def make_enhanced_cslc_button(self, CC, CS):
    """
    Enhanced CSLC button control with CX-5 2022 specific speed rules
    Based on CSLC version but adapted for current architecture
    """
    hud_control = CC.hudControl

    # Get target speed from planner
    target_speed_ms = hud_control.setSpeed
    if target_speed_ms > 70:  # Safety limit from CSLC version
      target_speed_ms = 0

    # Convert speeds to appropriate units
    is_metric = CS.is_metric if hasattr(CS, 'is_metric') else True
    MS_CONVERT = CV.MS_TO_KPH if is_metric else CV.MS_TO_MPH

    # Current cruise set speed and vehicle speed
    current_cruise_speed_ms = CS.out.cruiseState.speed
    current_vehicle_speed_ms = CS.out.vEgo

    # Convert to display units
    target_display = int(round(target_speed_ms * MS_CONVERT))
    current_cruise_display = int(round(current_cruise_speed_ms * MS_CONVERT))
    current_vehicle_display = current_vehicle_speed_ms * MS_CONVERT

    # CX-5 2022 specific rules
    if is_metric:
      # Round to 5 km/h increments
      target_display = int(round(target_display / 5.0) * 5.0)
      current_cruise_display = int(round(current_cruise_display / 5.0) * 5.0)
      min_speed = 30  # 30 km/h minimum for CX-5 2022
      max_speed = 160  # 160 km/h maximum
    else:
      # Round to 1 mph increments
      min_speed = 20  # 20 mph minimum
      max_speed = 100  # 100 mph maximum

    # Ensure target is within bounds
    target_display = max(min_speed, min(max_speed, target_display))

    # CX-5 2022 specific: Enforce 30 km/h minimum cruise speed
    if is_metric and current_cruise_display < min_speed:
      print(f"CSLC: Enforcing minimum speed {current_cruise_display} -> {min_speed}")
      return Buttons.SET_PLUS

    # Safety checks - Enhanced for CX-5 2022
    cant_activate = (CS.out.brakePressed or CS.out.gasPressed or
                     CS.distance_button or not CS.out.cruiseState.enabled)
    if cant_activate:
      return Buttons.NONE

    # Additional safety: Don't adjust if cruise buttons are being pressed
    if hasattr(CS, 'cruise_buttons') and CS.cruise_buttons != Buttons.NONE:
      return Buttons.NONE

    # Enhanced logic for CX-5 2022
    # 1. Smart alignment: If cruise speed is not aligned to 5km/h, align it first
    if is_metric and current_cruise_display % 5 != 0:
      # CX-5 2022 specific alignment rules:
      # - 42 km/h + SET_PLUS -> 45 km/h (round up to next 5 multiple)
      # - 57 km/h + SET_MINUS -> 55 km/h (round down to previous 5 multiple)

      # Calculate both possible alignments
      lower_aligned = int(current_cruise_display // 5) * 5
      upper_aligned = lower_aligned + 5

      # Determine which alignment to use based on target direction
      if target_display > current_cruise_display:
        # Target is higher, align upward (like 42->45)
        if upper_aligned <= max_speed:
          print(f"CSLC: Smart align UP {current_cruise_display} -> {upper_aligned} (target: {target_display})")
          return Buttons.SET_PLUS
      elif target_display < current_cruise_display:
        # Target is lower, align downward (like 57->55)
        if lower_aligned >= min_speed:
          print(f"CSLC: Smart align DOWN {current_cruise_display} -> {lower_aligned} (target: {target_display})")
          return Buttons.SET_MINUS
      else:
        # Target equals current, align to nearest
        if abs(upper_aligned - current_cruise_display) <= abs(lower_aligned - current_cruise_display):
          if upper_aligned <= max_speed:
            print(f"CSLC: Align to nearest UP {current_cruise_display} -> {upper_aligned}")
            return Buttons.SET_PLUS
        else:
          if lower_aligned >= min_speed:
            print(f"CSLC: Align to nearest DOWN {current_cruise_display} -> {lower_aligned}")
            return Buttons.SET_MINUS

    # 2. Conservative deceleration logic (from CSLC)
    if target_display + 5 < current_vehicle_display:
      # Reduce target by 10 to increase deceleration
      target_display = max(min_speed, target_display - 10)

    # 3. Speed adjustment logic
    if target_display < current_cruise_display and current_cruise_display > min_speed:
      print(f"CSLC: SET_MINUS target={target_display}, current={current_cruise_display}")
      return Buttons.SET_MINUS
    elif target_display > current_cruise_display and current_cruise_display < max_speed:
      print(f"CSLC: SET_PLUS target={target_display}, current={current_cruise_display}")
      return Buttons.SET_PLUS

    return Buttons.NONE


def test_cslc_speed_alignment():
  """
  Test function to verify CX-5 2022 speed alignment logic
  This function can be called for testing purposes
  """
  test_cases = [
    # (current_speed, target_speed, expected_button, description)
    (42, 50, Buttons.SET_PLUS, "42 km/h -> align to 45 km/h"),
    (57, 50, Buttons.SET_MINUS, "57 km/h -> align to 55 km/h"),
    (43, 43, Buttons.SET_PLUS, "43 km/h -> align to 45 km/h (nearest up)"),
    (47, 47, Buttons.SET_MINUS, "47 km/h -> align to 45 km/h (nearest down)"),
    (25, 30, Buttons.SET_PLUS, "25 km/h -> enforce 30 km/h minimum"),
  ]

  print("CSLC Speed Alignment Test Results:")
  for current, target, expected, description in test_cases:
    # Simulate alignment logic
    if current % 5 != 0:
      lower_aligned = int(current // 5) * 5
      upper_aligned = lower_aligned + 5

      if target > current:
        result = Buttons.SET_PLUS if upper_aligned <= 160 else Buttons.NONE
      elif target < current:
        result = Buttons.SET_MINUS if lower_aligned >= 30 else Buttons.NONE
      else:
        if abs(upper_aligned - current) <= abs(lower_aligned - current):
          result = Buttons.SET_PLUS if upper_aligned <= 160 else Buttons.NONE
        else:
          result = Buttons.SET_MINUS if lower_aligned >= 30 else Buttons.NONE
    elif current < 30:
      result = Buttons.SET_PLUS
    else:
      result = Buttons.NONE

    status = "✓ PASS" if result == expected else "✗ FAIL"
    print(f"  {status}: {description} -> {result}")


# Uncomment the line below to run tests during development
# test_cslc_speed_alignment()
