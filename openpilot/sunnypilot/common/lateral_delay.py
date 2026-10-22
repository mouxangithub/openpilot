LATERAL_CONTROL_SOFTWARE_DELAY = 0.2


def full_lateral_delay(vehicle_delay: float) -> float:
  return float(vehicle_delay) + LATERAL_CONTROL_SOFTWARE_DELAY
