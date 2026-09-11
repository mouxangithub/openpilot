#!/usr/bin/env python3
from __future__ import annotations

import struct
import unittest

from openpilot.sunnypilot.carrot import carrot_navi
from openpilot.sunnypilot.carrot import carrot_navi_cereal
from openpilot.sunnypilot.carrot import carrot_navi_control


class TestBinaryPacket(unittest.TestCase):
  def _build(self, message_type: int, format_or_reason: int, payload: bytes,
             width: int = 1, height: int = 1, stream_handle: int = 1,
             manifest_revision: int = 1, sequence: int = 1) -> bytes:
    header = carrot_navi.BINARY_HEADER.pack(
      b"CNV2", carrot_navi.PROTOCOL_VERSION, message_type, format_or_reason, 0,
      stream_handle, manifest_revision, sequence, 0, len(payload), width, height,
    )
    return header + payload

  def test_png_image(self) -> None:
    payload = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
    packet = self._build(1, 1, payload)
    meta, data = carrot_navi.parse_binary_packet(packet)
    self.assertEqual(meta["message_type"], 1)
    self.assertEqual(data, payload)

  def test_jpeg_image(self) -> None:
    payload = b"\xff\xd8" + b"\x00" * 8 + b"\xff\xd9"
    packet = self._build(1, 2, payload)
    meta, data = carrot_navi.parse_binary_packet(packet)
    self.assertEqual(meta["format_or_reason"], 2)

  def test_clear_packet(self) -> None:
    # CLEAR frames carry no pixels -> zero dimensions.
    packet = self._build(4, 1, b"", width=0, height=0)
    meta, data = carrot_navi.parse_binary_packet(packet)
    self.assertEqual(meta["message_type"], 4)
    self.assertEqual(data, b"")

  def test_bad_magic(self) -> None:
    header = carrot_navi.BINARY_HEADER.pack(
      b"XXXX", carrot_navi.PROTOCOL_VERSION, 1, 1, 0, 1, 1, 1, 0, 4, 1, 1,
    )
    with self.assertRaises(ValueError):
      carrot_navi.parse_binary_packet(header + b"PNG\x00")

  def test_bad_length(self) -> None:
    packet = self._build(1, 2, b"\xff\xd8\x00\xff\xd9", width=1, height=1)
    # corrupt declared length
    bad = bytearray(packet)
    struct.pack_into(">I", bad, 32, 999)
    with self.assertRaises(ValueError):
      carrot_navi.parse_binary_packet(bytes(bad))


class TestPayloadBuilder(unittest.TestCase):
  def test_road_limit_filtering(self) -> None:
    snapshot = {
      "generation": 1,
      "session_id": "abc",
      "connected": True,
      "items": {
        "speed": {
          "present": True,
          "sequence": 1,
          "source_timestamp_ms": 0,
          "received_mono_ns": 0,
          "value": {
            "road_limit_kph": 53,  # not a 10-multiple -> filtered out
          },
        },
      },
    }
    payload = carrot_navi_cereal.build_carrot_navi_payload(snapshot)
    self.assertFalse(payload["speed"]["roadLimitValid"])
    self.assertEqual(payload["speed"]["roadLimitKph"], 0)

    snapshot["items"]["speed"]["value"]["road_limit_kph"] = 60
    payload = carrot_navi_cereal.build_carrot_navi_payload(snapshot)
    self.assertTrue(payload["speed"]["roadLimitValid"])
    self.assertEqual(payload["speed"]["roadLimitKph"], 60)

  def test_section_and_traffic_present(self) -> None:
    snapshot = {
      "generation": 1,
      "session_id": "abc",
      "connected": True,
      "items": {
        "speed": {
          "present": True, "sequence": 1, "source_timestamp_ms": 0,
          "received_mono_ns": 0,
          "value": {
            "section": {"active": True, "speed_limit_kph": 80,
                        "remaining_distance_m": 500.0},
          },
        },
        "traffic_signal": {
          "present": True, "sequence": 1, "source_timestamp_ms": 0,
          "received_mono_ns": 0,
          "value": {
            "visible": True,
            "lights": {"red": {"on": True, "remain_sec": 12}},
          },
        },
      },
    }
    payload = carrot_navi_cereal.build_carrot_navi_payload(snapshot)
    self.assertTrue(payload["speed"]["sectionActive"])
    self.assertEqual(payload["speed"]["sectionSpeedLimitKph"], 80)
    self.assertTrue(payload["trafficSignal"]["redOn"])
    self.assertTrue(payload["trafficSignal"]["redValid"])


class TestControlGating(unittest.TestCase):
  """Round-trips snapshot -> cereal payload -> control dataclasses."""

  _NAMES = ("vehicle", "lane_current", "lane_ahead", "speed",
            "traffic_signal", "crossroad", "route",
            "guidance_current", "guidance_next", "navigation_status")

  def _parse(self, *, connected: bool = True, nav_off_route: bool = False,
             nav_present: bool = True, guidance: dict | None = None,
             speed: dict | None = None, traffic_signal: dict | None = None,
             schema_version: int = 1) -> dict | None:
    items = {}
    for n in self._NAMES:
      items[n] = {"present": (n == "navigation_status" and nav_present),
                  "sequence": 1, "source_timestamp_ms": 0,
                  "received_mono_ns": 0, "value": {}}
    items["navigation_status"]["value"] = {
      "off_route": nav_off_route,
      "guidance_active": True,
    }
    if guidance is not None:
      items["guidance_current"]["present"] = True
      items["guidance_current"]["value"] = guidance
    if speed is not None:
      items["speed"]["present"] = True
      items["speed"]["value"] = speed
    if traffic_signal is not None:
      items["traffic_signal"]["present"] = True
      items["traffic_signal"]["value"] = traffic_signal
    snapshot = {
      "generation": 1,
      "session_id": "sess",
      "connected": connected,
      "items": items,
    }
    payload = carrot_navi_cereal.build_carrot_navi_payload(snapshot)
    payload["schemaVersion"] = schema_version
    return carrot_navi_control.parse_carrot_navi_control(payload)

  def test_disconnected_returns_none(self) -> None:
    self.assertIsNone(self._parse(connected=False))

  def test_bad_schema_returns_none(self) -> None:
    self.assertIsNone(self._parse(schema_version=2))

  def test_off_route_suppresses_guidance(self) -> None:
    ctrl = self._parse(nav_off_route=True,
                       guidance={"distance_m": 100, "main_text": "turn"})
    self.assertIsNotNone(ctrl)
    assert ctrl is not None
    self.assertTrue(ctrl.off_route)
    self.assertFalse(ctrl.current.present)
    self.assertEqual(ctrl.current.distance_m, 0)

  def test_section_gating(self) -> None:
    ctrl = self._parse(speed={"section": {"active": True,
                                          "speed_limit_kph": 70,
                                          "remaining_distance_m": 300.0}})
    self.assertIsNotNone(ctrl)
    assert ctrl is not None
    self.assertTrue(ctrl.speed.section_active)
    self.assertEqual(ctrl.speed.section_speed_limit_kph, 70)
    self.assertEqual(ctrl.speed.section_remaining_distance_m, 300)

  def test_section_disabled_when_suspended(self) -> None:
    ctrl = self._parse(speed={"section": {"active": True,
                                          "suspended": True,
                                          "speed_limit_kph": 70,
                                          "remaining_distance_m": 300.0}})
    self.assertIsNotNone(ctrl)
    assert ctrl is not None
    self.assertFalse(ctrl.speed.section_active)

  def test_traffic_lamp_priority(self) -> None:
    ctrl = self._parse(traffic_signal={"visible": True,
                                       "lights": {"green": {"on": True},
                                                  "red": {"on": True}}})
    self.assertIsNotNone(ctrl)
    assert ctrl is not None
    self.assertEqual(ctrl.traffic.lamp, "red")


if __name__ == "__main__":
  unittest.main()
