#!/usr/bin/env python3
import os
import time
import json
import jwt
from typing import cast
from pathlib import Path

from datetime import datetime, timedelta, UTC
from openpilot.common.api import api_get, get_key_pair
from openpilot.common.params import Params
from openpilot.common.spinner import Spinner
from openpilot.selfdrive.selfdrived.alertmanager import set_offroad_alert
from openpilot.common.hardware import HARDWARE, PC
from openpilot.common.hardware.hw import Paths
from openpilot.common.swaglog import cloudlog


UNREGISTERED_DONGLE_ID = "UnregisteredDevice"
LITE = os.getenv("LITE") is not None
MAX_IMEI_RETRIES = 10          # ~10s before skipping registration
MAX_IMEI_WAIT_SEC = 15         # wall-clock cap while waiting for modem IMEI
MAX_PILOTAUTH_WAIT_SEC = 30    # wall-clock cap for cloud registration retries

def is_registered_device() -> bool:
  dongle = Params().get("DongleId")
  return dongle not in (None, UNREGISTERED_DONGLE_ID)


def register(show_spinner=False) -> str | None:
  """
  All devices built since March 2024 come with all
  info stored in /persist/. This is kept around
  only for devices built before then.

  With a backend update to take serial number instead
  of dongle ID to some endpoints, this can be removed
  entirely.
  """
  params = Params()

  dongle_id: str | None = params.get("DongleId")
  if dongle_id is None and Path(Paths.persist_root()+"/comma/dongle_id").is_file():
    # not all devices will have this; added early in comma 3X production (2/28/24)
    with open(Paths.persist_root()+"/comma/dongle_id") as f:
      dongle_id = f.read().strip()

  # Create registration token, in the future, this key will make JWTs directly
  jwt_algo, private_key, public_key = get_key_pair()

  if not public_key:
    dongle_id = UNREGISTERED_DONGLE_ID
    cloudlog.warning("missing public key")
  elif dongle_id is None:
    if show_spinner:
      spinner = Spinner()
      spinner.update("registering device")

    if LITE:
      params.put("DongleId", UNREGISTERED_DONGLE_ID)
      return UNREGISTERED_DONGLE_ID

    # Block until we get the imei (ICCID/SIM not required for comma registration)
    serial = HARDWARE.get_serial()
    imei_start = time.monotonic()
    imei: str | None = None
    skip_imei_count = 0
    while not imei:
      if time.monotonic() - imei_start > MAX_IMEI_WAIT_SEC:
        cloudlog.warning("IMEI unavailable, skipping registration")
        params.put("DongleId", UNREGISTERED_DONGLE_ID)
        return UNREGISTERED_DONGLE_ID

      try:
        imei = HARDWARE.get_imei() or None
        if not imei:
          raise ValueError("empty IMEI")
      except Exception:
        cloudlog.exception("Error getting imei, trying again...")
        if show_spinner:
          spinner.update(
            f"registering device - serial: {serial}, Error getting IMEI, trying {skip_imei_count}/{MAX_IMEI_RETRIES}",
          )
        if skip_imei_count >= MAX_IMEI_RETRIES:
          cloudlog.warning("no IMEI after retries, skipping registration")
          params.put("DongleId", UNREGISTERED_DONGLE_ID)
          return UNREGISTERED_DONGLE_ID
        skip_imei_count += 1
        time.sleep(1)

      if show_spinner and imei:
        spinner.update(f"registering device - serial: {serial}, IMEI: {imei}")

    backoff = 0
    auth_start = time.monotonic()
    while True:
      if time.monotonic() - auth_start > MAX_PILOTAUTH_WAIT_SEC:
        cloudlog.warning("pilotauth timed out, skipping registration")
        dongle_id = UNREGISTERED_DONGLE_ID
        break

      try:
        register_token = jwt.encode({'register': True, 'exp': datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)},
                                    cast(str, private_key), algorithm=jwt_algo)
        cloudlog.info("getting pilotauth")
        resp = api_get("v2/pilotauth/", method='POST', timeout=15,
                       imei=imei, imei2="", serial=serial, public_key=public_key, register_token=register_token)

        if resp.status_code in (402, 403):
          cloudlog.info(f"Unable to register device, got {resp.status_code}")
          dongle_id = UNREGISTERED_DONGLE_ID
        else:
          dongleauth = json.loads(resp.text)
          dongle_id = dongleauth["dongle_id"]
        break
      except NotImplementedError:
        # dependency issues with PyJWT will hang the registration test in backoff loop otherwise
        raise
      except Exception:
        cloudlog.exception("failed to authenticate")
        backoff = min(backoff + 1, 15)
        time.sleep(backoff)

    if show_spinner:
      spinner.close()

  if dongle_id:
    params.put("DongleId", dongle_id, block=True)
    set_offroad_alert("Offroad_UnregisteredHardware", (dongle_id == UNREGISTERED_DONGLE_ID) and not PC and not os.getenv("LITE"))
  return dongle_id


if __name__ == "__main__":
  print(register())
