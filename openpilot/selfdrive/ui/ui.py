#!/usr/bin/env python3
import os
import time

from openpilot.cereal import messaging
from openpilot.common.hardware import COMMA_HARDWARE
from openpilot.common.realtime import Priority, config_realtime_process, get_available_cores, set_core_affinity
from openpilot.system.ui.lib.application import gui_app
from openpilot.selfdrive.ui.layouts.main import MainLayout
from openpilot.selfdrive.ui.mici.layouts.main import MiciMainLayout
from openpilot.selfdrive.ui.ui_state import ui_state

if gui_app.sunnypilot_ui():
  from openpilot.selfdrive.ui.sunnypilot.mici.layouts.main import MiciMainLayoutSP as MiciMainLayout

BIG_UI = gui_app.big_ui()

# UI wants its own core above plannerd/radard. Power save offlines the big
# cluster (4-7), so ask for one of those and fall back to whatever is online.
UI_CORES = (5, 4)


def resolve_ui_cores() -> list[int]:
  """Pick a CPU for the UI, skipping any core power save has taken offline."""
  available = get_available_cores()
  for core in UI_CORES:
    if core in available:
      return [core]
  return []


def main():
  # above plannerd and radard
  config_realtime_process(0, Priority.CTRL_HIGH)

  gui_app.init_window("UI")
  if BIG_UI:
    MainLayout()
  else:
    MiciMainLayout()

  ui_cores: set[int] = set()
  pm = messaging.PubMaster(['uiDebug'])
  for should_render, frame_time, cpu_time in gui_app.render():
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
