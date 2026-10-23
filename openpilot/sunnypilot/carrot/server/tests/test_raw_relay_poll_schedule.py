"""Per-service poll pacing for the raw WebSocket relay.

The relay used to poll every subscribed service at a fixed 50 Hz, so a 10 Hz
``liveTracks`` feed cost five empty reads a frame and a 20 Hz ``modelV2`` could
aliases to half rate on a clock boundary. It now paces each device by the
shared compact-service cadence table and only retries quickly on an empty
read. The pitfall these tests pin down is naming: the poll loop holds this
fork's *device* names (carrotManSP), while the cadence table is keyed on the
shared CarrotPilot names (carrotMan). A direct lookup would silently fall back
to the default for every renamed service.
"""
import unittest

from openpilot.sunnypilot.carrot.server.services.raw_relay import RawRelayHub
from openpilot.sunnypilot.carrot.server.services.raw_services import (
  RAW_SERVICE_ALIASES,
  device_service_interval,
)


class _Hub(RawRelayHub):
  def __init__(self):
    super().__init__(messaging=None)
    self.broadcasted = []

  def _broadcast(self, device, payload):
    self.broadcasted.append((device, payload))


class TestServiceInterval(unittest.TestCase):
  def test_renamed_service_uses_shared_cadence(self):
    # carrotManSP must resolve to the carrotMan row, not the default.
    self.assertEqual(device_service_interval("carrotManSP"), 0.1)
    self.assertEqual(device_service_interval("carrotNaviSP"), 0.5)
    # Stock names pass through unchanged.
    self.assertEqual(device_service_interval("carState"), 0.016)
    self.assertEqual(device_service_interval("liveTracks"), 0.1)

  def test_every_alias_has_a_resolvable_non_default_cadence(self):
    """A renamed service added to the alias table must still be paced.

    If a new alias lands without a matching cadence row, this fails loudly
    instead of the relay quietly polling it at the default 50 Hz.
    """
    for device in RAW_SERVICE_ALIASES.values():
      interval = device_service_interval(device)
      self.assertGreater(interval, 0, f"{device} has no cadence")

  def test_read_delay_phase_compensation(self):
    hub = _Hub()
    # Empty read: short retry, independent of the (slow) service cadence.
    empty = hub._service_read_delay("carrotNaviSP", payload_received=False)
    self.assertEqual(empty, RawRelayHub.EMPTY_READ_RETRY)
    # Received payload on a 2 Hz nav service: pace to its 0.5 s cadence.
    nav = hub._service_read_delay("carrotNaviSP", payload_received=True)
    self.assertGreater(nav, 0.2)
    # carState keeps its fast cadence.
    carstate = hub._service_read_delay("carState", payload_received=True)
    self.assertAlmostEqual(carstate, 0.016)


if __name__ == "__main__":
  unittest.main()
