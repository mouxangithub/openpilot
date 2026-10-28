#!/usr/bin/env python3
# simple pandad wrapper that updates the panda first
import os
import usb1
import time
import signal
import subprocess

from panda import Panda, PandaDFU, PandaProtocolMismatch, FW_PATH
from openpilot.common.basedir import BASEDIR
from openpilot.common.params import Params
from openpilot.common.hardware import HARDWARE
from openpilot.common.swaglog import cloudlog

from openpilot.sunnypilot.selfdrive.pandad.rivian_long_flasher import flash_rivian_long


def get_expected_signature(panda: Panda) -> bytes:
  # MCU-aware (our fork supports the comma three dos F4 panda, which zp's
  # hardcoded McuType.H7 does not): pick the app binary by the panda's actual
  # MCU type, so dos (F4 -> panda.bin.signed) and H7 devices both match.
  try:
    fn = os.path.join(FW_PATH, panda.get_mcu_type().config.app_fn)
    return Panda.get_signature_from_firmware(fn)
  except Exception:
    cloudlog.exception("Error computing expected signature")
    return b""

def flash_panda(panda_serial: str):
  panda = Panda(panda_serial)

  # skip flashing if the detected panda is not supported
  if panda.get_type() not in Panda.SUPPORTED_DEVICES:
    cloudlog.warning(f"Panda {panda_serial} is not supported (hw_type: {panda.get_type()}), skipping flash...")
    panda.close()
    return

  fw_signature = get_expected_signature(panda)
  internal_panda = panda.is_internal()

  panda_version = "bootstub" if panda.bootstub else panda.get_version()
  panda_signature = b"" if panda.bootstub else panda.get_signature()
  cloudlog.warning(f"Panda {panda_serial} connected, version: {panda_version}, signature {panda_signature.hex()[:16]}, expected {fw_signature.hex()[:16]}")

  if panda.bootstub or panda_signature != fw_signature:
    cloudlog.info("Panda firmware out of date, update required")
    panda.flash()
    cloudlog.info("Done flashing")

  if panda.bootstub:
    bootstub_version = panda.get_version()
    cloudlog.info(f"Flashed firmware not booting, flashing development bootloader. {bootstub_version=}, {internal_panda=}")
    if internal_panda:
      HARDWARE.recover_internal_panda()
    panda.recover(reset=(not internal_panda))
    cloudlog.info("Done flashing bootstub")

  if panda.bootstub:
    cloudlog.info("Panda still not booting, exiting")
    raise AssertionError

  panda_signature = panda.get_signature()
  if panda_signature != fw_signature:
    cloudlog.info("Version mismatch after flashing, exiting")
    raise AssertionError

  panda.close()


def check_panda_support(panda_serials: list[str], use_red_panda: bool = False) -> tuple[list[str], str | None, bool]:
  """Pick the active (CAN/safety) panda and, when it is external, the internal aux panda.

  Returns (active_serials, aux_serial, red_panda_present).

  master-c3 connects every panda and sorts the internal one first, so the
  internal dos always ends up as peripheral_panda and keeps the fan. Our C++
  core is single-CAN, so the split is expressed as an aux slot instead: the
  active panda runs CAN/safety, the aux (internal dos) runs fan/peripherals.

  The Red Panda flag feeds PANDAD_MASK_DOS_IGNITION: on comma three setups with
  an external Red Panda the dos reports false ignitions via the harness box
  without a harness connector, so the C++ daemon must mask the dos ignition
  line (ported from master-c3's red_panda_comma_three).
  """
  red_panda_present = False
  spi_serials = set(Panda.spi_list())
  usb_serials = [s for s in panda_serials if s not in spi_serials]

  # scan every USB panda once: both the external Red Panda and the internal
  # dos must be found regardless of which one enumerates first
  red_serial = None
  internal_serial = None
  for serial in usb_serials:
    panda = Panda(serial)
    try:
      hw_type = panda.get_type()
      red_panda_present |= hw_type == Panda.HW_TYPE_RED_PANDA
      if red_serial is None and hw_type == Panda.HW_TYPE_RED_PANDA:
        red_serial = serial
      if internal_serial is None and panda.is_internal():
        internal_serial = serial
    finally:
      panda.close()

  # 1. SPI panda (comma 3X internal) wins unconditionally
  for serial in panda_serials:
    if serial in spi_serials:
      return [serial], None, red_panda_present

  # 2. UseRedPanda: the external Red Panda is the active CAN panda; the
  #    internal dos stays on fan/peripheral duty via the aux slot
  if use_red_panda and red_serial is not None:
    return [red_serial], internal_serial, red_panda_present

  # 3. default: the internal panda is the active (and only) panda
  if internal_serial is not None:
    return [internal_serial], None, red_panda_present

  return [], None, red_panda_present


def main() -> None:
  # signal pandad to close the relay and exit
  def signal_handler(signum, frame):
    cloudlog.info(f"Caught signal {signum}, exiting")
    nonlocal do_exit
    do_exit = True
    if process is not None:
      process.send_signal(signal.SIGINT)

  process = None
  do_exit = False
  signal.signal(signal.SIGINT, signal_handler)

  # check health for lost heartbeat
  try:
    use_red_panda = Params().get_bool("UseRedPanda")
    for s in Panda.list():
      with Panda(s) as p:
        # when a Red Panda is the active CAN panda, the internal dos runs as the
        # aux peripheral panda and is heartbeated by the C++ daemon; skip it so
        # a pre-update flag never false-triggers PandaHeartbeatLost
        if use_red_panda and p.is_internal():
          continue
        health = p.health()
        if p.is_internal() and health["heartbeat_lost"]:
          Params().put_bool("PandaHeartbeatLost", True, block=True)
          cloudlog.event("heartbeat lost", deviceState=health)
  except Exception:
    cloudlog.exception("pandad.uncaught_exception")

  count = 0
  while not do_exit:
    try:
      cloudlog.event("pandad.flash_and_connect", count=count)
      if (count % 2) == 0:
        HARDWARE.reset_internal_panda()
      else:
        HARDWARE.recover_internal_panda()
      count += 1

      # Flash all Pandas in DFU mode
      for serial in PandaDFU.list():
        cloudlog.info(f"Panda in DFU mode found, flashing recovery {serial}")
        PandaDFU(serial).recover()
        time.sleep(1)

      panda_serials = Panda.list()
      if len(panda_serials):
        # custom flasher for xnor's Rivian Longitudinal Upgrade Kit
        flash_rivian_long(panda_serials)
        # find the active (CAN) panda and the internal aux for peripherals
        active_serials, aux_serial, red_panda_present = check_panda_support(panda_serials, use_red_panda=Params().get_bool("UseRedPanda"))

        if not active_serials:
          # e.g. only an external panda is visible while the internal one is
          # mid-reset; retry instead of crashing so the loop stays calm
          cloudlog.warning("no supported panda found, retrying...")
          time.sleep(2)
          continue

        assert len(active_serials) == 1
        cloudlog.info(f"{len(active_serials)} active panda found, connecting - {active_serials}, aux (peripherals/fan) - {aux_serial}")
        to_flash = list(dict.fromkeys(active_serials + ([aux_serial] if aux_serial else [])))
        for serial in to_flash:
          flash_panda(serial)

        # comma three + external Red Panda: the dos gets false positive
        # ignitions from the harness box without a harness connector; tell the
        # C++ daemon to mask the dos ignition line (master-c3
        # red_panda_comma_three, adapted to the single-panda architecture)
        if red_panda_present:
          cloudlog.warning("external Red Panda detected, masking dos ignition line false positives")
          os.environ['PANDAD_MASK_DOS_IGNITION'] = '1'
        else:
          os.environ.pop('PANDAD_MASK_DOS_IGNITION', None)

        # run real pandad; pass the verified serial so the C++ daemon connects
        # the selected panda instead of picking USB enumeration order, which
        # with an external panda plugged in may be the unverified one; the aux
        # serial keeps fan/peripheral control on the internal dos (master-c3)
        os.environ['MANAGER_DAEMON'] = 'pandad'
        cmd = ["./pandad", *active_serials] + ([aux_serial] if aux_serial else [])
        process = subprocess.Popen(cmd, cwd=os.path.join(BASEDIR, "openpilot/selfdrive/pandad"))
        process.wait()
    # TODO: wrap all panda exceptions in a base panda exception
    except (usb1.USBErrorNoDevice, usb1.USBErrorPipe):
      # a panda was disconnected while setting everything up. let's try again
      cloudlog.exception("Panda USB exception while setting up")
    except PandaProtocolMismatch:
      cloudlog.exception("pandad.protocol_mismatch")
    except Exception:
      cloudlog.exception("pandad.uncaught_exception")


if __name__ == "__main__":
  main()
