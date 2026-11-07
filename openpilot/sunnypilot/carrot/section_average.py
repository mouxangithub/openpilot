"""Section-camera average-speed allowance for navigation SDI data.

Ported from Carrotpilot (joongyu01/carrot-wip-speedcam, cb65544e9 /
c777ccfe2), MIT licensed. The cp original consumes the section state from the
Hyundai stock-navigation CAN stream; here the four inputs come from the
carrot SDI chain instead (nSdiType=4 + nSdiBlockType=2, blockSpeed as the
section limit) and the travelled distance is sp's own wheel-speed
integration (CarrotServ.total_distance), so no vehicle CAN cooperation is
required.

Section enforcement measures the average speed between the start and end
cameras, so time banked below the target average (e.g. in congestion) may be
spent later. The bank is B = elapsed_time - distance / target_speed.
B >= 0 means the running average is at or below the target, whatever the
remaining section length is. The allowance spends B over a fixed horizon and
returns to the normal section cap as B runs out, so it never *lowers* the
existing cap - it only permits speeds above the section limit while the
bank lasts.
"""

SECTION_END_DEBOUNCE_S = 3.0
SPEND_HORIZON_M = 1000.0
MIN_BANK_S = 0.5
MAX_ALLOWANCE_KPH = 250.0


class SectionAverage:
  def __init__(self):
    self.reset()

  def reset(self):
    self.active = False
    self.limit_kph = 0.0
    self.start_time = 0.0
    self.start_distance = 0.0
    self.inactive_since = None

  def update(self, section_active, limit_kph, now, total_distance):
    if section_active and limit_kph > 0:
      self.inactive_since = None
      if not self.active or limit_kph != self.limit_kph:
        self.active = True
        self.limit_kph = limit_kph
        self.start_time = now
        self.start_distance = total_distance
    elif self.active:
      # The SDI stream can drop for a frame; a real section end or exit lasts
      # longer. Same debounce contract as the cp 0x4B4 CAN drop guard.
      if self.inactive_since is None:
        self.inactive_since = now
      elif now - self.inactive_since >= SECTION_END_DEBOUNCE_S:
        self.reset()

  def _target_ms(self, margin_kph):
    return max(1.0, (self.limit_kph - margin_kph) / 3.6)

  def bank_seconds(self, now, total_distance, margin_kph):
    if not self.active:
      return 0.0
    return (now - self.start_time) - (total_distance - self.start_distance) / self._target_ms(margin_kph)

  def allowance_kph(self, now, total_distance, margin_kph):
    """Speed (km/h, actual) that spends the bank over SPEND_HORIZON_M; 0 when there is none."""
    bank = self.bank_seconds(now, total_distance, margin_kph)
    if bank <= MIN_BANK_S:
      return 0.0
    remaining_time = SPEND_HORIZON_M / self._target_ms(margin_kph) - bank
    if remaining_time <= SPEND_HORIZON_M / (MAX_ALLOWANCE_KPH / 3.6):
      return MAX_ALLOWANCE_KPH
    return min(MAX_ALLOWANCE_KPH, SPEND_HORIZON_M / remaining_time * 3.6)
