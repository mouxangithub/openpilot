"""CarState / CarController draft templates for vehicle adaptation."""

from __future__ import annotations

from typing import Any

_BRAND_ALIASES = {
  "toyota": "toyota",
  "lexus": "toyota",
  "honda": "honda",
  "acura": "honda",
  "volkswagen": "vw",
  "vw": "vw",
  "audi": "vw",
  "skoda": "vw",
  "seat": "vw",
  "hyundai": "hyundai",
  "kia": "hyundai",
  "genesis": "hyundai",
}


def normalize_brand(brand: str) -> str:
  b = (brand or "").lower().strip()
  return _BRAND_ALIASES.get(b, b or "generic")


def get_adaptation_template(
  *,
  brand: str = "",
  model_name: str = "NEW_MODEL",
  fingerprint: str = "",
) -> dict[str, Any]:
  """Return draft file snippets for save_adaptation_draft."""
  b = normalize_brand(brand)
  fp_line = fingerprint or "{0x50: 8, 0x140: 8}  # TODO: fill from compare_fingerprint"

  carstate = _carstate_template(b, model_name)
  carcontroller = _carcontroller_template(b, model_name)
  readme = f"""# Adaptation draft: {model_name}

## Checklist
- [ ] Fingerprint verified on bus 0/1/2
- [ ] CarState fields match live CAN (get_vehicle_state)
- [ ] CarController torque limits in values.py
- [ ] Closed-course test before public road

## Fingerprint candidate
```python
FINGERPRINTS = {{
  '{model_name}': [
    {fp_line},
  ],
}}
```
"""

  return {
    "ok": True,
    "brand": b,
    "model_name": model_name,
    "files": {
      "README.md": readme,
      "fingerprint.json": '{"model": "%s", "fingerprint": %s}' % (model_name, fp_line if fp_line.startswith("{") else '"TODO"'),
      "carstate.py.snippet": carstate,
      "carcontroller.py.snippet": carcontroller,
    },
    "hint": "Review snippets, then save_adaptation_draft with confirm=true while stationary.",
  }


def _carstate_template(brand: str, model: str) -> str:
  steer_sig = "STEER_ANGLE" if brand == "toyota" else "STEER_ANGLE_1" if brand == "vw" else "STEER_ANGLE"
  return f'''# CarState snippet for {model} ({brand})
# Merge into opendbc/car/<brand>/carstate.py after review

class CarState(CarStateBase):
  def update(self, can_packets):
    cp = can_parser.CanParser(dbc_name, signals, bus)
    ret = car.CarState.new_message()

    # Required fields — map from DBC via cabana_explain_signal
    ret.vEgo = cp.vl["WHEEL_SPEEDS"]["WHEEL_SPEED_FL"] * CV.KPH_TO_MS  # example
    ret.steeringAngleDeg = cp.vl["STEERING_SENSORS"]["{steer_sig}"]
    ret.gas = cp.vl["GAS_PEDAL"]["GAS_PEDAL"]
    ret.brake = cp.vl["BRAKE"]["BRAKE_PRESSURE"]
    ret.gasPressed = ret.gas > 0
    ret.brakePressed = ret.brake > 0
    ret.standstill = ret.vEgo < 0.01
    # ret.gearShifter = ...  # if available

    return ret
'''


def _carcontroller_template(brand: str, model: str) -> str:
  lkas = "LKAS11" if brand == "toyota" else "HCA_01" if brand == "vw" else "STEERING_LKAS"
  return f'''# CarController snippet for {model} ({brand})
# Apply apply_driver_steer_torque_limits; respect MAX_STEER_SPEED

class CarController(CarControllerBase):
  def update(self, CC, CS, now_nanos):
  # LKAS / steer
    # new_actuators.steer = apply_driver_steer_torque_limits(...)
    # can_sends.append(create_steering_control(...))  # {lkas}

  # Longitudinal (if openpilotLongitudinalControl)
    # can_sends.append(create_accel_command(...))

    return new_actuators, can_sends
'''
