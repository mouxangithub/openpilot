"""PC dev AGNOS reboot simulation helpers."""

from __future__ import annotations

import os
import time


def dev_bootstrap_blocked() -> bool:
  if os.environ.get("WEBUI_DEV_PC") != "1":
    return False
  from webui.dev.mock_runtime import SIM

  until = float(SIM.get("agnos_sim_reboot_until") or 0)
  if until <= 0:
    return False
  if time.time() < until:
    return True
  SIM["agnos_sim_reboot_until"] = 0.0
  SIM["agnos_sim_rebooting"] = False
  return False
