#!/usr/bin/env python3
import datetime
import subprocess
import time
from typing import NoReturn

import openpilot.cereal.messaging as messaging
from openpilot.common.time_helpers import min_date, MAX_DATE, system_time_valid
from openpilot.common.swaglog import cloudlog
from openpilot.common.params import Params
from openpilot.common.gps import get_gps_location_service
from openpilot.system.timezone_helper import (
  SOURCE_PRIORITY, current_source, apply_timezone,
  timezone_from_internet, timezone_from_gps,
)


def set_time(new_epoch):
  # new_epoch: UNIX epoch (UTC seconds) received from GPS. The on-screen clock
  # (localtime) reads system clock + timezone, so setting the system clock to
  # GPS UTC exactly makes it display as local time.
  diff = abs(time.time() - new_epoch)  # noqa: TID251 - comparing against GPS wall-clock epoch
  if diff < 10:
    cloudlog.debug(f"Time diff too small: {diff:.1f}s")
    return

  cloudlog.info(f"Setting system time from GPS (diff {diff:.1f}s)")
  try:
    # '@<epoch>' specifies an absolute UTC instant -> no timezone
    # double-conversion bug. sudo required: unprivileged `date -s` fails silently.
    subprocess.run(["sudo", "date", "-s", f"@{int(new_epoch)}"], check=True)
  except subprocess.CalledProcessError:
    cloudlog.exception("timed.failed_setting_time")


def main() -> NoReturn:
  """
    timed has two responsibilities:
    - getting the current time from GPS
    - publishing the time in the logs

    AGNOS will also use NTP to update the time.
  """

  params = Params()
  gps_location_service = get_gps_location_service(params)

  pm = messaging.PubMaster(['clocks'])
  sm = messaging.SubMaster([gps_location_service])

  last_tz_attempt = 0.0
  while True:
    sm.update(1000)

    msg = messaging.new_message('clocks')
    msg.valid = system_time_valid()
    msg.clocks.wallTimeNanos = time.time_ns()
    pm.send('clocks', msg)

    gps = sm[gps_location_service]
    gps_ok = (sm.updated[gps_location_service]
              and (time.monotonic() - sm.logMonoTime[gps_location_service] / 1e9) <= 2.0
              and gps.hasFix)

    # Local timezone resolution (for non-app users). Only attempted when the
    # trusted source (app/wifi) has not been set yet. Retry fast (30s) when no
    # timezone exists at all, slow (5min) once the GPS fallback is in place -
    # so the offline internet call (up to timeout) does not spin the loop.
    cur_prio = SOURCE_PRIORITY.get(current_source(params), 0)
    if cur_prio < SOURCE_PRIORITY["wifi"]:
      retry_interval = 30.0 if cur_prio == 0 else 300.0
      if time.monotonic() - last_tz_attempt > retry_interval:
        last_tz_attempt = time.monotonic()
        tz = timezone_from_internet()        # [2nd priority] WiFi/internet
        if tz is not None:
          apply_timezone(tz, "wifi", params)
        elif gps_ok:                         # [3rd priority] GPS longitude approx (last resort)
          apply_timezone(timezone_from_gps(gps.longitude), "gps", params)

    # The system clock (absolute UTC) can only be set with a GPS fix
    if not gps_ok:
      continue
    gps_epoch = gps.unixTimestampMillis / 1000.
    gps_time = datetime.datetime.fromtimestamp(gps_epoch)
    if gps_time < min_date() or gps_time > MAX_DATE:
      continue

    set_time(gps_epoch)
    time.sleep(10)

if __name__ == "__main__":
  main()
