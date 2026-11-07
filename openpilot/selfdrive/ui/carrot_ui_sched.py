"""Verify normal UI scheduling before applying onroad/offroad display placement.

Ported from carrotpilot's ``selfdrive/ui/carrot_ui_sched.py``.

The UI is a consumer of realtime data, not a producer of it. If the UI main
thread keeps an RT scheduling policy it can preempt the sensor and localization
work that the control path actually depends on, so this contract demotes the
thread to ``SCHED_OTHER`` and verifies the result.

Verification failure is fail-stop: a UI that cannot prove it is not preempting
the control path is worse than a UI that exits and lets the manager restart it
(``restart_if_crash``). The success log is emitted only after a readback
confirms the policy, so a failed demotion can never be reported as success.
"""
import os
import sys

from openpilot.common.hardware import PC
from openpilot.common.realtime import drop_realtime
from openpilot.common.swaglog import cloudlog

_VERIFY_ATTEMPTS = 2  # bounded retry - no unbounded/per-frame syscall storm


def ensure_ui_sched_other() -> None:
  """Demote the UI main thread to SCHED_OTHER and verify it by readback.

  Raises RuntimeError when the policy cannot be confirmed, so the manager
  restarts the process instead of leaving it silently preempting the control
  path.
  """
  if sys.platform != "linux" or PC:
    return  # no RT scheduling on this platform - the contract does not apply
  policy = None
  for _ in range(_VERIFY_ATTEMPTS):
    try:
      drop_realtime()
      policy = os.sched_getscheduler(0)
    except OSError:
      continue
    if policy == os.SCHED_OTHER:
      cloudlog.info("UISCHED: UI SCHED_OTHER verified (core0 bootstrap)")
      return
  cloudlog.critical(f"UISCHED: UI could not be verified SCHED_OTHER (policy={policy}); fail-stop")
  raise RuntimeError("UI must run SCHED_OTHER (realtime preemption contract)")
