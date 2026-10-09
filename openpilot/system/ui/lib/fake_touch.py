#!/usr/bin/env python3
"""Virtual touchscreen fallback for comma hardware with missing touch driver.

Some C3 boots leave the Samsung/FTS touchscreen controller unprobed (I2C timeout
or missing firmware). raylib's COMMA platform and /usr/comma/magic.py both
require a working /dev/input/event2 touch device to initialize DRM/EGL. This
module creates a minimal multi-touch input device via /dev/uinput so the native
UI can start. Touch events are not synthesized; the device merely satisfies the
initialization checks.
"""
import logging
import time

try:
  from evdev import UInput, AbsInfo, ecodes as e
except ImportError:
  logging.error("fake_touch: evdev not installed")
  raise


def main():
  cap = {
    e.EV_KEY: [e.BTN_TOUCH],
    e.EV_ABS: [
      (e.ABS_X, AbsInfo(value=0, min=0, max=1920, fuzz=0, flat=0, resolution=0)),
      (e.ABS_Y, AbsInfo(value=0, min=0, max=1080, fuzz=0, flat=0, resolution=0)),
      (e.ABS_MT_SLOT, AbsInfo(value=0, min=0, max=9, fuzz=0, flat=0, resolution=0)),
      (e.ABS_MT_TRACKING_ID, AbsInfo(value=0, min=0, max=65535, fuzz=0, flat=0, resolution=0)),
      (e.ABS_MT_POSITION_X, AbsInfo(value=0, min=0, max=1920, fuzz=0, flat=0, resolution=0)),
      (e.ABS_MT_POSITION_Y, AbsInfo(value=0, min=0, max=1080, fuzz=0, flat=0, resolution=0)),
    ],
  }

  ui = UInput(cap, name="fake-touch", vendor=0x1, product=0x1, version=1, bustype=e.BUS_USB)
  logging.info(f"fake_touch: created {ui.device.path}")
  # Keep the process alive so the kernel input device stays registered.
  while True:
    time.sleep(60)


if __name__ == "__main__":
  main()
