"""Unit tests for server.bridge.ui_status (border status machine)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace as NS


def _make_sm(ss_state, ss_enabled, ss_active, mads, *, has_sp=True, events=()):
  class SM(dict):
    pass

  s = SM()
  s["selfdriveState"] = NS(state=ss_state, enabled=ss_enabled, active=ss_active)
  s["selfdriveStateSP"] = NS(mads=mads)
  s["onroadEvents"] = list(events)
  s.valid = {"selfdriveStateSP": has_sp, "onroadEvents": bool(events)}
  return s


def _mads(state=None, enabled=False, available=True):
  from openpilot.cereal import custom

  return NS(
    state=state if state is not None else custom.ModularAssistiveDrivingSystem.ModularAssistiveDrivingSystemState.disabled,
    enabled=enabled,
    available=available,
  )


class UiStatusTest(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    from openpilot.cereal import log
    cls.OpenpilotState = log.SelfdriveState.OpenpilotState
    cls.MADSState = None
    try:
      from openpilot.cereal import custom
      cls.MADSState = custom.ModularAssistiveDrivingSystem.ModularAssistiveDrivingSystemState
    except Exception:
      pass

  def _status(self, **kw):
    from webui.server.bridge.ui_status import derive_ui_status
    ss_state = kw.pop("ss_state", self.OpenpilotState.disabled)
    return derive_ui_status(_make_sm(ss_state, kw.pop("ss_enabled", False), kw.pop("ss_active", False), kw.pop("mads"), **kw))

  def test_mads_latched_no_cruise_is_lat_only(self):
    # MAIN latch (MADS on) but cruise not set -> lat_only -> blue border
    self.assertEqual(self._status(mads=_mads(self.MADSState.enabled, enabled=True)), "lat_only")

  def test_cruise_set_both_enabled_is_engaged(self):
    self.assertEqual(self._status(
      ss_state=self.OpenpilotState.enabled, ss_enabled=True, ss_active=True,
      mads=_mads(self.MADSState.enabled, enabled=True)), "engaged")

  def test_all_off_is_disengaged(self):
    self.assertEqual(self._status(mads=_mads()), "disengaged")

  def test_stock_only_engaged(self):
    self.assertEqual(self._status(
      ss_state=self.OpenpilotState.enabled, ss_enabled=True, ss_active=True,
      mads=_mads(available=False)), "engaged")

  def test_missing_sp_message_falls_back(self):
    self.assertEqual(self._status(
      ss_state=self.OpenpilotState.enabled, ss_enabled=True, ss_active=True,
      mads=_mads(), has_sp=False), "engaged")

  def test_mads_paused_is_override(self):
    self.assertEqual(self._status(
      ss_state=self.OpenpilotState.enabled, ss_enabled=True, ss_active=True,
      mads=_mads(self.MADSState.paused, enabled=True)), "override")

  def test_pre_enabled_is_override(self):
    self.assertEqual(self._status(
      ss_state=self.OpenpilotState.preEnabled,
      mads=_mads(self.MADSState.enabled, enabled=True)), "override")

  def test_stock_acc_mads_off_is_long_only(self):
    self.assertEqual(self._status(
      ss_state=self.OpenpilotState.enabled, ss_enabled=True, ss_active=True,
      mads=_mads(enabled=False)), "long_only")


if __name__ == "__main__":
  unittest.main()
