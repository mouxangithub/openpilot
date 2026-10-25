#!/usr/bin/env python3
import os
import time

from openpilot.cereal import messaging
from openpilot.common.hardware import COMMA_HARDWARE
from openpilot.common.realtime import Priority, config_realtime_process, get_available_cores, set_core_affinity
from openpilot.common.watchdog import kick_watchdog
from openpilot.system.ui.lib.application import gui_app
from openpilot.selfdrive.ui.layouts.main import MainLayout
from openpilot.selfdrive.ui.mici.layouts.main import MiciMainLayout
from openpilot.selfdrive.ui.ui_state import ui_state

if gui_app.sunnypilot_ui():
  from openpilot.selfdrive.ui.sunnypilot.mici.layouts.main import MiciMainLayoutSP as MiciMainLayout

BIG_UI = gui_app.big_ui()

# UI wants a big core to itself. The carrot layout owns the rest of the big
# cluster: card/plannerd/radard on 5, controlsd/selfdrived on 6, modeld on 7.
# Core 4 only hosts radarcan (CTRL_LOW), which this process outranks. Power
# save offlines the big cluster when offroad with the screen off, so the
# render loop re-affines once it is back online.
UI_CORES = (4, 5)


def _online_cores() -> set[int]:
  """CPUs the kernel has online, regardless of this process's own mask."""
  try:
    with open('/sys/devices/system/cpu/online') as f:
      spec = f.read().strip()
    cores = set()
    for part in spec.split(','):
      part = part.strip()
      if '-' in part:
        lo, hi = part.split('-')
        cores.update(range(int(lo), int(hi) + 1))
      elif part:
        cores.add(int(part))
    if cores:
      return cores
  except (OSError, ValueError):
    pass
  return get_available_cores()


def resolve_ui_cores() -> list[int]:
  """Pick a CPU for the UI, skipping any core power save has taken offline.

  Must not consult get_available_cores(): that reports this process's own
  affinity mask, which is a single core after the startup pin. From a pinned
  state every other core would look "unavailable" and the render loop's
  re-affine could never widen back to the big cluster (observed on device:
  the UI stayed on core 0 forever). Read the kernel's online list instead.
  """
  online = _online_cores()
  for core in UI_CORES:
    if core in online:
      return [core]
  return []


def main():
  # above plannerd and radard; resolve BEFORE the first pin narrows our mask,
  # so the process starts directly on its big core instead of camping on core 0
  # (which also services most IRQs) until power save shuffles things
  config_realtime_process(resolve_ui_cores() or [0], Priority.CTRL_HIGH)

  gui_app.init_window("UI")
  if BIG_UI:
    MainLayout()
  else:
    MiciMainLayout()

  ui_cores: set[int] = set()
  pm = messaging.PubMaster(['uiDebug'])
  for should_render, frame_time, cpu_time in gui_app.render():
    # Tell the manager this process is still making progress. A render loop
    # that stops ticking is exactly the failure restart_if_crash cannot see.
    kick_watchdog()
    extra_start = time.monotonic()
    ui_state.update()

    if should_render:
      # reaffine after power save offlines our core
      if COMMA_HARDWARE and os.sched_getaffinity(0) != ui_cores:
        ui_cores = set_core_affinity(resolve_ui_cores())

      extra_cpu = time.monotonic() - extra_start
      msg = messaging.new_message('uiDebug')
      msg.uiDebug.cpuTimeMillis = (cpu_time + extra_cpu) * 1000
      msg.uiDebug.frameTimeMillis = frame_time * 1000
      pm.send('uiDebug', msg)


if __name__ == "__main__":
  main()
