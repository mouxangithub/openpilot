#!/usr/bin/env python3
"""beepd: external GPIO beeper on the C3's GPIO42 (sysfs).

Ported from sunnypilot's selfdrive/selfdrived/beep.py. A piezo buzzer wired to
GPIO42 gets a short single beep on engage, a double beep on disengage, a triple
beep on warnings, and one beep per promptRepeat with a 10 s suppression window.

Safety gates, in order:
  * ``ExternalBeepEnabled`` (default "0"): the switch. When off the process
    stays idle and never touches GPIO at all.
  * When on, GPIO42's sysfs entry is probed first (export attempted, then
    direction). If the probe fails the daemon runs as a no-op and logs one
    warning - the C3 pin mapping is unverified, so a missing pin must never
    become a crash loop or stray writes.
"""
import threading
import time
from pathlib import Path

from opendbc.car.structs import car
import openpilot.cereal.messaging as messaging
from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper
from openpilot.common.swaglog import cloudlog

AudibleAlert = car.CarControl.HUDControl.AudibleAlert

GPIO_SYSFS_ROOT = Path("/sys/class/gpio")
GPIO_PATH = GPIO_SYSFS_ROOT / "gpio42"
EXTERNAL_BEEP_PARAM = "ExternalBeepEnabled"
PROMPT_REPEAT_SUPPRESS_S = 10.0


class Beepd:
  def __init__(self):
    self.current_alert = AudibleAlert.none
    # timestamp until which promptRepeat should be suppressed
    self.prompt_suppress_until = 0.0
    self.gpio_ready = self.enable_gpio()
    if not self.gpio_ready:
      cloudlog.warning("beepd: GPIO42 sysfs unavailable, external beeper stays silent (C3 pin mapping unverified)")

  def enable_gpio(self) -> bool:
    """Probe and prepare GPIO42. Returns False (and touches nothing further) when absent."""
    try:
      if not GPIO_SYSFS_ROOT.is_dir():
        return False
      if not GPIO_PATH.is_dir():
        self._sysfs_write(GPIO_SYSFS_ROOT / "export", "42")
        if not GPIO_PATH.is_dir():
          return False
      self._sysfs_write(GPIO_PATH / "direction", "out")
      return True
    except Exception:
      cloudlog.exception("beepd: GPIO42 probe failed")
      return False

  @staticmethod
  def _sysfs_write(path: Path, value: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
      f.write(value)

  def _beep(self, on: bool) -> None:
    if not self.gpio_ready:
      return
    try:
      self._sysfs_write(GPIO_PATH / "value", "1" if on else "0")
    except OSError:
      pass

  def engage(self) -> None:
    self._beep(True)
    time.sleep(0.05)
    self._beep(False)

  def disengage(self) -> None:
    for _ in range(2):
      self._beep(True)
      time.sleep(0.01)
      self._beep(False)
      time.sleep(0.01)

  def warning(self) -> None:
    for _ in range(3):
      self._beep(True)
      time.sleep(0.01)
      self._beep(False)
      time.sleep(0.01)

  def dispatch_beep(self, func) -> None:
    threading.Thread(target=func, daemon=True).start()

  def update_alert(self, new_alert) -> None:
    now = time.monotonic()
    if new_alert == self.current_alert:
      return
    self.current_alert = new_alert
    if not self.gpio_ready:
      return
    if new_alert == AudibleAlert.engage:
      self.dispatch_beep(self.engage)
    elif new_alert == AudibleAlert.disengage:
      self.dispatch_beep(self.disengage)
    elif new_alert in (AudibleAlert.warningSoft, AudibleAlert.warningImmediate):
      self.dispatch_beep(self.warning)
    elif new_alert == AudibleAlert.promptRepeat:
      # Ignore further promptRepeats inside the suppression window.
      if now >= self.prompt_suppress_until:
        self.prompt_suppress_until = now + PROMPT_REPEAT_SUPPRESS_S
        self.dispatch_beep(self.engage)

  def get_audible_alert(self, sm) -> None:
    if sm.updated['selfdriveState']:
      self.update_alert(sm['selfdriveState'].alertSound.raw)

  def beepd_thread(self) -> None:
    sm = messaging.SubMaster(['selfdriveState'])
    rk = Ratekeeper(20)
    while True:
      sm.update(0)
      self.get_audible_alert(sm)
      rk.keep_time()


def main():
  # Gate first: with the switch off (the default) GPIO is never touched. The
  # process idles instead of exiting so the manager does not restart-loop it;
  # flipping the switch takes effect on the next manager (re)start.
  if not Params().get_bool(EXTERNAL_BEEP_PARAM):
    cloudlog.info("beepd: ExternalBeepEnabled off, staying idle")
    threading.Event().wait()
    return
  Beepd().beepd_thread()


if __name__ == "__main__":
  main()
