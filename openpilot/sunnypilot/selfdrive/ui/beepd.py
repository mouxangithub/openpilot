#!/usr/bin/env python3
"""GPIO beeper for Lite hardware (no speaker/amplifier)."""

import subprocess
import time
import threading

from cereal import car, messaging
from openpilot.common.hardware.comma.pins import GPIO
from openpilot.common.realtime import Ratekeeper

AudibleAlert = car.CarControl.HUDControl.AudibleAlert

_SIREN_GPIO = GPIO.SIREN


class Beepd:
  def __init__(self, test=False):
    self.current_alert = AudibleAlert.none
    self._test = test
    self.enable_gpio()

  def enable_gpio(self):
    try:
      if self._test:
        print("enabling GPIO")
      subprocess.run(f"echo {_SIREN_GPIO} | sudo tee /sys/class/gpio/export",
                     shell=True,
                     stderr=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL,
                     encoding='utf8')
    except Exception:
      if self._test:
        print("GPIO failed to enable")
    subprocess.run(f"echo \"out\" | sudo tee /sys/class/gpio/gpio{_SIREN_GPIO}/direction",
                   shell=True,
                   stderr=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL,
                   encoding='utf8')

  def _beep(self, on):
    val = "1" if on else "0"
    subprocess.run(f"echo \"{val}\" | sudo tee /sys/class/gpio/gpio{_SIREN_GPIO}/value",
                   shell=True,
                   stderr=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL,
                   encoding='utf8')

  def engage(self):
    if self._test:
      print("beepd: engage")
    self._beep(True)
    time.sleep(0.05)
    self._beep(False)

  def disengage(self):
    if self._test:
      print("beepd: disengage")
    for _ in range(2):
      self._beep(True)
      time.sleep(0.01)
      self._beep(False)
      time.sleep(0.01)

  def prompt(self):
    if self._test:
      print("beepd: prompt")
    for _ in range(3):
      self._beep(True)
      time.sleep(0.01)
      self._beep(False)
      time.sleep(0.01)

  def warning_immediate(self):
    if self._test:
      print("beepd: warning_immediate")
    for _ in range(5):
      self._beep(True)
      time.sleep(0.01)
      self._beep(False)
      time.sleep(0.01)

  def dispatch_beep(self, func):
    threading.Thread(target=func, daemon=True).start()

  def update_alert(self, new_alert):
    current_alert_played_once = self.current_alert == AudibleAlert.none
    if self.current_alert != new_alert and (new_alert != AudibleAlert.none or current_alert_played_once):
      self.current_alert = new_alert
      if new_alert == AudibleAlert.engage:
        self.dispatch_beep(self.engage)
      if new_alert == AudibleAlert.disengage:
        self.dispatch_beep(self.disengage)
      if new_alert == AudibleAlert.prompt:
        self.dispatch_beep(self.prompt)
      if new_alert == AudibleAlert.warningImmediate:
        self.dispatch_beep(self.warning_immediate)

  def get_audible_alert(self, sm):
    if sm.updated['selfdriveState']:
      new_alert = sm['selfdriveState'].alertSound.raw
      self.update_alert(new_alert)

  def beepd_thread(self):
    sm = messaging.SubMaster(['selfdriveState'])
    rk = Ratekeeper(20)

    while True:
      sm.update(0)
      self.get_audible_alert(sm)
      rk.keep_time()


def main():
  s = Beepd(test=False)
  s.beepd_thread()


if __name__ == "__main__":
  main()
