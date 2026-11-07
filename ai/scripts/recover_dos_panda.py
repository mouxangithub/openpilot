#!/usr/bin/env python3
"""Recover F4 (black/DOS) panda using panda/board/obj/panda.bin.signed."""
import argparse
import sys


def main() -> int:
  parser = argparse.ArgumentParser(
    description="Flash F4 panda (black/DOS) with panda/board/obj/panda.bin.signed.",
  )
  parser.add_argument("--serial", help="USB serial of the panda to flash")
  parser.add_argument("--external", action="store_true",
                      help="Flash the first external F4 panda (aux port black panda)")
  parser.add_argument("--internal", action="store_true",
                      help="Flash the internal F4 panda (C3 DOS)")
  args = parser.parse_args()

  if args.serial and (args.external or args.internal):
    print("use --serial alone, or one of --external / --internal")
    return 1
  if args.external and args.internal:
    print("use either --external or --internal, not both")
    return 1

  try:
    from ai.tools.panda_flash_tools import execute_recover_dos_panda
  except ImportError:
    from panda import Panda, PandaDFU
    from openpilot.common.basedir import BASEDIR
    from openpilot.common.hardware import HARDWARE
    import os
    import time

    FW = os.path.join(BASEDIR, "panda", "board", "obj", "panda.bin.signed")

    def pick_serial(serials, *, external, internal):
      candidates = []
      for s in serials:
        try:
          p = Panda(s)
          is_internal = p.is_internal()
          is_f4 = p.get_type() in Panda.F4_DEVICES
          p.close()
        except Exception:
          continue
        if not is_f4:
          continue
        if external and not is_internal:
          candidates.append(s)
        elif internal and is_internal:
          candidates.append(s)
        elif not external and not internal:
          candidates.append(s)
      if external or internal:
        return candidates[0] if candidates else None
      for s in serials:
        try:
          p = Panda(s)
          if p.is_internal() and p.get_type() in Panda.F4_DEVICES:
            p.close()
            return s
          p.close()
        except Exception:
          continue
      return serials[0] if serials else None

    def flash_serial(serial):
      p = Panda(serial)
      if not os.path.isfile(FW):
        print("missing firmware:", FW)
        return 1
      expected = Panda.get_signature_from_firmware(FW)
      if not p.bootstub:
        try:
          if p.get_signature() == expected:
            print("firmware already matches")
            p.close()
            return 0
        except Exception:
          pass
      with open(FW, "rb") as f:
        code = f.read()
      mcu_type = p.get_mcu_type()
      if not p.bootstub:
        try:
          p._handle.controlWrite(Panda.REQUEST_IN, 0xd1, 1, 0, b'', timeout=15000, expect_disconnect=True)
        except Exception:
          pass
        p.close()
        time.sleep(1)
        p = Panda(serial)
      if not p.bootstub:
        print("failed to enter bootstub")
        return 1
      Panda.flash_static(p._handle, code, mcu_type=mcu_type)
      p.close()
      time.sleep(2)
      p2 = Panda(serial)
      ok = (not p2.bootstub) and p2.get_signature() == expected
      p2.close()
      print("OK" if ok else "FAILED")
      return 0 if ok else 2

    serials = Panda.list()
    print("pandas:", serials)
    if not serials:
      HARDWARE.recover_internal_panda()
      if Panda.wait_for_dfu(None, 15):
        PandaDFU(None).recover()
        PandaDFU(None).reset()
        time.sleep(2)
      serials = Panda.list()
    if args.serial:
      if args.serial not in serials:
        print("serial not found:", args.serial)
        return 1
      target = args.serial
    else:
      target = pick_serial(serials, external=args.external, internal=args.internal)
      if not target:
        print("no matching F4 panda")
        return 1
    return flash_serial(target)

  res = execute_recover_dos_panda(
    serial=args.serial or "",
    external=args.external,
    internal=args.internal,
    try_dfu=True,
  )
  print(res.get("log", ""))
  if not res.get("ok"):
    if res.get("error"):
      print("error:", res["error"])
    return 2
  return 0


if __name__ == "__main__":
  sys.exit(main())
