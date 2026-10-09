"""Chestnut AI accelerator settings panel.

Chestnut is a USB-connected AI accelerator (ASM2464) that runs the big driving
model. This panel shows real-time telemetry from chestnutState and USB link info.
"""
import threading
import traceback

from openpilot.cereal import messaging
from openpilot.common.hardware.usb import get_usb_state, is_chestnut_usb_id
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.ui.ui_state import ChestnutState, ui_state
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.list_view import button_item, text_item
from openpilot.system.ui.widgets.scroller_tici import Scroller


def _chestnut_usb_speed() -> str:
  """Get Chestnut USB link speed from sysfs."""
  if not ui_state.chestnut_present:
    return "not connected"
  for dev in get_usb_state():
    if is_chestnut_usb_id(dev["vendorId"], dev["productId"]):
      speed = dev["speedMbps"]
      if speed >= 5000:
        return f"{speed // 1000} Gbps"
      return f"{speed} Mbps"
  return "not connected"


def _chestnut_status_label(state: ChestnutState) -> str:
  """Human-readable label for ChestnutState."""
  return {
    ChestnutState.DISCONNECTED: "Disconnected",
    ChestnutState.UNCOMPILED: "Not Compiled",
    ChestnutState.READY: "Ready",
    ChestnutState.LOADING: "Loading",
    ChestnutState.ACTIVE: "Active",
    ChestnutState.FAILED: "Failed",
  }.get(state, str(state.value))


class ChestnutLayout(Widget):
  def __init__(self):
    super().__init__()
    self._sm = messaging.SubMaster(["chestnutState"])
    self._frame: int = 0

    # Telemetry fields (updated from SubMaster at 2 Hz)
    self._temp_c: float = 0.0
    self._memory_temp_c: float = 0.0
    self._power_draw_w: float = 0.0
    self._power_limit_w: float = 0.0
    self._gpu_usage_pct: int = 0
    self._gpu_clock_mhz: int = 0
    self._fan_speed_rpm: int = 0
    self._pcie_ltssm: int = 0
    self._supply_voltage_mv: int = 0
    self._supply_current_ma: int = 0
    self._supply_fault: bool = False

    self._check_result: str = ""
    self._checking: bool = False

    self._scroller = Scroller([
      text_item(lambda: tr("Chestnut Status"), self._status_text),
      text_item(lambda: tr("USB Link"), _chestnut_usb_speed),
      text_item(lambda: tr("Temperature"), self._temp_text),
      text_item(lambda: tr("Memory Temp"), self._memory_temp_text),
      text_item(lambda: tr("Power Draw"), self._power_draw_text),
      text_item(lambda: tr("Power Limit"), self._power_limit_text),
      text_item(lambda: tr("GPU Usage"), self._gpu_usage_text),
      text_item(lambda: tr("GPU Clock"), self._gpu_clock_text),
      text_item(lambda: tr("Fan Speed"), self._fan_speed_text),
      text_item(lambda: tr("PCIe LTSSM"), self._pcie_ltssm_text),
      text_item(lambda: tr("Supply Voltage"), self._supply_voltage_text),
      text_item(lambda: tr("Supply Current"), self._supply_current_text),
      text_item(lambda: tr("Supply Fault"), self._supply_fault_text),
      text_item(lambda: tr("Connection Check"), self._check_result_text),
      button_item(
        lambda: tr("Check Chestnut"),
        lambda: tr("CHECK"),
        lambda: tr("Checks USB 5 Gbps, firmware, 12V/PCIe, and GPU execution."),
        callback=self._start_check,
        enabled=ui_state.is_offroad,
      ),
    ], line_separator=True, spacing=0)

  def _status_text(self) -> str:
    return _chestnut_status_label(ui_state.chestnut_state)

  def _temp_text(self) -> str:
    return f"{self._temp_c:.1f} °C"

  def _memory_temp_text(self) -> str:
    return f"{self._memory_temp_c:.1f} °C"

  def _power_draw_text(self) -> str:
    return f"{self._power_draw_w:.1f} W"

  def _power_limit_text(self) -> str:
    return f"{self._power_limit_w:.1f} W"

  def _gpu_usage_text(self) -> str:
    return f"{self._gpu_usage_pct}%"

  def _gpu_clock_text(self) -> str:
    return f"{self._gpu_clock_mhz} MHz"

  def _fan_speed_text(self) -> str:
    return f"{self._fan_speed_rpm} RPM"

  def _pcie_ltssm_text(self) -> str:
    # PCIe LTSSM states: 0x78 = L0 (active), 0x2 = L1, 0x1 = L2, 0x0 = Polling
    return {
      0x78: "L0 (active)",
      0x02: "L1",
      0x01: "L2",
      0x00: "Polling",
    }.get(self._pcie_ltssm, f"0x{self._pcie_ltssm:02X}")

  def _supply_voltage_text(self) -> str:
    return f"{self._supply_voltage_mv} mV"

  def _supply_current_text(self) -> str:
    return f"{self._supply_current_ma} mA"

  def _supply_fault_text(self) -> str:
    return "Yes" if self._supply_fault else "No"

  def _check_result_text(self) -> str:
    if self._checking:
      return "checking..."
    return self._check_result or "not checked"

  def _start_check(self) -> None:
    if self._checking or not ui_state.is_offroad():
      return
    self._checking = True
    self._check_result = "checking..."

    def run():
      try:
        from openpilot.system.hardware.chestnut.flash import flash_chestnut
        flash_chestnut(expected_version=None, force=False)
        self._check_result = "no errors"
      except Exception:
        self._check_result = traceback.format_exc()[-200:] or "check failed"
      finally:
        self._checking = False

    threading.Thread(target=run, name="chestnut-check", daemon=True).start()

  def show_event(self) -> None:
    super().show_event()
    self._scroller.show_event()

  def _render(self, rect) -> None:
    # Poll chestnutState at 2 Hz (every 30 frames at 60fps) to avoid overhead
    self._frame += 1
    if self._frame % 30 == 0:
      self._sm.update(0)
      if self._sm.alive["chestnutState"] and self._sm.valid["chestnutState"]:
        cs = self._sm["chestnutState"]
        self._temp_c = float(cs.tempC)
        self._memory_temp_c = float(cs.memoryTempC)
        self._power_draw_w = float(cs.powerDrawW)
        self._power_limit_w = float(cs.powerLimitW)
        self._gpu_usage_pct = int(cs.gpuUsagePercent)
        self._gpu_clock_mhz = int(cs.gpuClockMhz)
        self._fan_speed_rpm = int(cs.fanSpeedRpm)
        self._pcie_ltssm = int(cs.pcieLtssm)
        self._supply_voltage_mv = int(cs.supplyVoltage)
        self._supply_current_ma = int(cs.supplyCurrent)
        self._supply_fault = bool(cs.supplyFault)

    self._scroller.render(rect)
