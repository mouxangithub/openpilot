"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""The UDP 7705 discovery beacon must also be addressed to a known app.

The app reads the device's `ip` from a UDP 7705 datagram, but it only listens on that port
while it has no control socket (carrot_navi_api.md section 1: "The process maintenance loop
requests discovery whenever the control socket is missing or not open"). So re-discovery
happens exactly when the app is listening - and a broadcast copy depends on the AP
forwarding it plus the phone's socket staying awake. A directly addressed copy has neither
failure mode, which is why the beacon sends both.

Measured on the device 2026-09-27: the beacon was going out (8 datagrams in 5 s, from
carrot_man and carrot_navi) while the app reported "7705 未激活" - the app had 14
established sockets on 7714 and was therefore not listening on 7705 at all.
"""
import json
import unittest

from openpilot.sunnypilot.carrot import carrot_navi

SENTINEL_TARGETS = (('192.168.1.50', '192.168.1.255'),)


class _FakeSock:
  def __init__(self, sink):
    self._sink = sink

  def setsockopt(self, *_args):
    pass

  def bind(self, address):
    self._sink.append(('bind', address))

  def sendto(self, data, address):
    self._sink.append(('sendto', address, data))

  def close(self):
    pass


def _capture(peers, active=False):
  """Run one broadcast_once() with the socket and the interface list faked out."""
  sink = []
  real_socket, real_targets = carrot_navi.socket.socket, carrot_navi.discovery_targets
  carrot_navi.socket.socket = lambda *_a, **_k: _FakeSock(sink)
  carrot_navi.discovery_targets = lambda _ip=None: SENTINEL_TARGETS
  try:
    beacon = carrot_navi.CarrotNaviDiscoveryBeacon(peers=(lambda: peers) if peers is not None else None,
                                                   active_provider=lambda: active)
    beacon.broadcast_once()
  finally:
    carrot_navi.socket.socket, carrot_navi.discovery_targets = real_socket, real_targets
    carrot_navi.DISCOVERY_PEER_IPS.clear()
  return [entry for entry in sink if entry[0] == 'sendto']


class TestDiscoveryBeaconUnicast(unittest.TestCase):
  def test_the_broadcast_copy_is_still_sent(self):
    sends = _capture(())
    self.assertEqual([a for _, a, _ in sends], [('192.168.1.255', carrot_navi.DISCOVERY_PORT)])

  def test_a_connected_app_is_also_addressed_directly(self):
    sends = _capture(('10.0.0.5',))
    self.assertEqual(sorted(a for _, a, _ in sends),
                     sorted([('192.168.1.255', carrot_navi.DISCOVERY_PORT), ('10.0.0.5', carrot_navi.DISCOVERY_PORT)]))

  def test_both_copies_carry_an_identical_payload(self):
    body = json.loads(_capture(('10.0.0.5',))[0][2])
    for _, _, data in _capture(('10.0.0.5',)):
      self.assertEqual(json.loads(data), body)
    self.assertEqual(body['ip'], '192.168.1.50')
    self.assertEqual(body['port'], carrot_navi.DEFAULT_PORT)

  def test_unusable_peer_addresses_are_skipped(self):
    sends = _capture(('', '0.0.0.0', '127.0.0.1'))
    self.assertEqual([a for _, a, _ in sends], [('192.168.1.255', carrot_navi.DISCOVERY_PORT)])

  def test_it_falls_back_to_the_tracked_websocket_peers(self):
    carrot_navi.DISCOVERY_PEER_IPS.add('10.0.0.9')
    try:
      sends = _capture(None)
      self.assertIn(('10.0.0.9', carrot_navi.DISCOVERY_PORT), [a for _, a, _ in sends])
    finally:
      carrot_navi.DISCOVERY_PEER_IPS.clear()

  def test_every_datagram_carries_the_engagement_state(self):
    # The app reads `active` off whatever 7705 datagram it parsed last. carrot_man only
    # broadcasts every 2s while this beacon is far more frequent, so a beacon without
    # the field makes the indicator depend on arrival order.
    for _, _, data in _capture(('10.0.0.5',), active=True):
      self.assertEqual(json.loads(data)['active'], True)
    for _, _, data in _capture(('10.0.0.5',), active=False):
      self.assertEqual(json.loads(data)['active'], False)


if __name__ == '__main__':
  unittest.main()
