"""Contract for the one-shot NNFF torque model notice (torqueNNLoad).

Two halves:
- events.py: the notice text and the per-instance rebinding of the EVENTS map
  (the model name lives in CarParamsSP, which the alert callback signature
  cannot carry).
- selfdrived.update_nnff_alert: the gating that decides when the single notice
  may fire.

The whole module needs a built msgq, so on a host without one every case is
skipped explicitly rather than erroring. Device runs must still verify
skip=0 (a skip here is a silent contract loss, not a pass).
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

try:
  import openpilot.cereal.messaging  # noqa: F401
  HAS_MESSAGING = True
except ImportError:
  HAS_MESSAGING = False

if HAS_MESSAGING:
  from openpilot.selfdrive.selfdrived.alertmanager import AlertManager
  from openpilot.selfdrive.selfdrived.events import Events, EVENTS, ET, nnff_load_alert, EventName
  from openpilot.selfdrive.selfdrived.selfdrived import SelfdriveD

  MODEL_NAME = "TOYOTA WILDLANDER PHEV 2021"
CS_OK = SimpleNamespace(canValid=True, canTimeout=False)


def make_carrot(**overrides) -> SelfdriveD:
  """A SelfdriveD shell carrying just what update_nnff_alert touches."""
  carrot = object.__new__(SelfdriveD)
  carrot.nnff_alerted = False
  carrot.initialized = overrides.pop("initialized", True)
  carrot.CP = SimpleNamespace(passive=overrides.pop("passive", False))
  carrot.CP_SP = SimpleNamespace(neuralNetworkLateralControl=SimpleNamespace(
    model=SimpleNamespace(name=overrides.pop("model_name", MODEL_NAME)),
    fuzzyFingerprint=overrides.pop("fuzzy", False),
  ))
  nnlc_enabled = overrides.pop("nnlc_enabled", True)
  carrot.params = SimpleNamespace(get_bool=lambda key, _enabled=nnlc_enabled: _enabled)
  carrot.events = Events()
  carrot.AM = AlertManager()
  carrot.sm = MagicMock()
  carrot.sm.frame = overrides.pop("frame", 600)
  carrot.sm.__getitem__.return_value = SimpleNamespace(started=True)
  carrot.sm.all_checks.return_value = True
  carrot.update_alerts = MagicMock()
  for key, value in overrides.items():
    setattr(carrot, key, value)
  return carrot


@unittest.skipUnless(HAS_MESSAGING, "needs a built msgq (device or full checkout)")
class TestNnffNoticeText(unittest.TestCase):

  def test_exact_match_names_the_model_plainly(self):
    alert = nnff_load_alert(MODEL_NAME, fuzzy=False)
    self.assertEqual(alert.alert_text_1, "NNFF 扭矩模型已加载")
    self.assertEqual(alert.alert_text_2, MODEL_NAME)

  def test_fuzzy_match_says_the_tune_is_a_substitute(self):
    alert = nnff_load_alert(MODEL_NAME, fuzzy=True)
    self.assertIn("替代模型", alert.alert_text_2)
    self.assertIn(MODEL_NAME, alert.alert_text_2)

  def test_placeholder_entry_stays_silent_about_any_model(self):
    """The default entry must never name a model: binding is the only writer."""
    entry = EVENTS[EventName.torqueNNLoad][ET.PERMANENT]
    self.assertNotIn(MODEL_NAME, entry.alert_text_2)


@unittest.skipUnless(HAS_MESSAGING, "needs a built msgq (device or full checkout)")
class TestNnffNoticeBinding(unittest.TestCase):

  def test_binding_is_scoped_to_torqueNNLoad_only(self):
    events = Events()
    events.bind_nnff_notice(MODEL_NAME, False)
    mapping = events.get_events_mapping()
    self.assertEqual(mapping[EventName.torqueNNLoad][ET.PERMANENT].alert_text_2, MODEL_NAME)
    # every other event keeps its original entry object
    self.assertIs(mapping[EventName.radarStationaryLead], EVENTS[EventName.radarStationaryLead])

  def test_unbound_mapping_falls_back_to_the_placeholder(self):
    events = Events()
    self.assertIs(events.get_events_mapping(), EVENTS)

  def test_create_alerts_resolves_the_bound_notice(self):
    events = Events()
    events.bind_nnff_notice(MODEL_NAME, True)
    events.add(EventName.torqueNNLoad)
    alerts = events.create_alerts([ET.PERMANENT], [])
    self.assertEqual(len(alerts), 1)
    # ET.PERMANENT's string value is lowercase, matching capnp's JSON name
    self.assertEqual(alerts[0].alert_type, "torqueNNLoad/permanent")
    self.assertEqual(alerts[0].event_type, ET.PERMANENT)
    self.assertIn("替代模型", alerts[0].alert_text_2)

  def test_event_counters_survive_the_rebound_mapping(self):
    """event_counters is keyed at __init__; a rebound event must not KeyError."""
    events = Events()
    events.add(EventName.torqueNNLoad)
    alerts = events.create_alerts([ET.PERMANENT], [])
    self.assertEqual(len(alerts), 1)
    events.clear()
    self.assertEqual(events.event_counters[EventName.torqueNNLoad], 1)


@unittest.skipUnless(HAS_MESSAGING, "needs a built msgq (device or full checkout)")
class TestNnffNoticeGate(unittest.TestCase):

  def test_fires_once_and_names_the_loaded_model(self):
    carrot = make_carrot()
    carrot.update_nnff_alert(CS_OK)
    self.assertTrue(carrot.nnff_alerted)
    self.assertIn(EventName.torqueNNLoad, carrot.events.names)
    notice = carrot.events.get_events_mapping()[EventName.torqueNNLoad][ET.PERMANENT]
    self.assertEqual(notice.alert_text_2, MODEL_NAME)
    carrot.update_alerts.assert_called_once()

  def test_fuzzy_fingerprint_is_carried_into_the_notice(self):
    carrot = make_carrot(fuzzy=True)
    carrot.update_nnff_alert(CS_OK)
    notice = carrot.events.get_events_mapping()[EventName.torqueNNLoad][ET.PERMANENT]
    self.assertIn("替代模型", notice.alert_text_2)

  def test_never_fires_twice(self):
    carrot = make_carrot()
    carrot.update_nnff_alert(CS_OK)
    first_calls = carrot.update_alerts.call_count
    carrot.sm.frame = 700
    carrot.update_nnff_alert(CS_OK)
    self.assertEqual(carrot.update_alerts.call_count, first_calls)

  def test_waits_out_the_startup_window(self):
    carrot = make_carrot(frame=549)
    carrot.update_nnff_alert(CS_OK)
    self.assertFalse(carrot.nnff_alerted)
    self.assertEqual(carrot.events.names, [])

  def test_first_eligible_frame_is_inclusive_at_550(self):
    carrot = make_carrot(frame=550)
    carrot.update_nnff_alert(CS_OK)
    self.assertTrue(carrot.nnff_alerted)

  def test_polls_at_two_hertz_not_every_frame(self):
    carrot = make_carrot(frame=601)
    carrot.update_nnff_alert(CS_OK)
    self.assertFalse(carrot.nnff_alerted)

  def test_holds_back_until_initialization_completes(self):
    carrot = make_carrot(initialized=False)
    carrot.update_nnff_alert(CS_OK)
    self.assertFalse(carrot.nnff_alerted)

  def test_holds_back_while_passive(self):
    carrot = make_carrot(passive=True)
    carrot.update_nnff_alert(CS_OK)
    self.assertFalse(carrot.nnff_alerted)

  def test_holds_back_on_can_timeout(self):
    carrot = make_carrot()
    carrot.update_nnff_alert(SimpleNamespace(canValid=True, canTimeout=True))
    self.assertFalse(carrot.nnff_alerted)

  def test_holds_back_while_another_alert_is_showing(self):
    carrot = make_carrot()
    carrot.AM.current_alert = SimpleNamespace(alert_type="something/PERMANENT")
    carrot.update_nnff_alert(CS_OK)
    self.assertFalse(carrot.nnff_alerted)

  def test_holds_back_when_the_feature_is_off(self):
    carrot = make_carrot(nnlc_enabled=False)
    carrot.update_nnff_alert(CS_OK)
    self.assertFalse(carrot.nnff_alerted)

  def test_holds_back_without_a_model_name(self):
    carrot = make_carrot(model_name="")
    carrot.update_nnff_alert(CS_OK)
    self.assertFalse(carrot.nnff_alerted)

  def test_holds_back_for_the_mock_model(self):
    """MOCK means no real model matched: announcing it would be a lie."""
    carrot = make_carrot(model_name="MOCK")
    carrot.update_nnff_alert(CS_OK)
    self.assertFalse(carrot.nnff_alerted)


if __name__ == "__main__":
  unittest.main()
