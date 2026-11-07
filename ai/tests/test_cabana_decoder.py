"""Pure-Python CAN decoder tests (hand-crafted signal definitions)."""

from __future__ import annotations

import ai.tests.bootstrap_pc  # noqa: F401  # PC mocks before ai imports
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from ai.services.cabana.dbc import _extract_annotations
from ai.services.cabana.decoder import (
  decode_frames,
  decode_frames_multi,
  decode_signal_value,
  get_decoder,
  get_decoders,
)


def _sig(name: str, address: int, *, start_bit: int, size: int, little_endian: bool = True,
         signed: bool = False, factor: float = 1.0, offset: float = 0.0, signal_type: int = 0) -> dict:
  return {
    "address": address,
    "message": f"MSG_{address:X}",
    "signal": name,
    "start_bit": start_bit,
    "size": size,
    "little_endian": little_endian,
    "signed": signed,
    "factor": factor,
    "offset": offset,
    "signal_type": signal_type,
  }


class DecodeSignalValueTest(unittest.TestCase):
  def test_little_endian_unsigned(self):
    sig = _sig("speed", 0x100, start_bit=0, size=16, factor=0.01)
    # raw 1234 -> 12.34
    self.assertAlmostEqual(decode_signal_value(sig, bytes([0xD2, 0x04, 0, 0, 0, 0, 0, 0])), 12.34)

  def test_little_endian_signed_two_complement(self):
    sig = _sig("steer", 0x100, start_bit=0, size=8, signed=True)
    self.assertAlmostEqual(decode_signal_value(sig, bytes([0xFF]) + bytes(7)), -1.0)

  def test_little_endian_offset(self):
    sig = _sig("temp", 0x100, start_bit=8, size=8, factor=0.5, offset=-40.0)
    # raw 100 -> 100*0.5 - 40 = 10.0
    self.assertAlmostEqual(decode_signal_value(sig, bytes([0x00, 0x64]) + bytes(6)), 10.0)

  def test_big_endian_msb_first(self):
    sig = _sig("rpm", 0x200, start_bit=7, size=16, little_endian=False)
    # MSB at byte0 bit7 spanning two bytes: 0x0100 = 256
    self.assertAlmostEqual(decode_signal_value(sig, bytes([0x01, 0x00]) + bytes(6)), 256.0)

  def test_big_endian_short_data_skipped_value(self):
    sig = _sig("rpm", 0x200, start_bit=7, size=16, little_endian=False)
    with self.assertRaises(ValueError):
      decode_signal_value(sig, bytes([0x01]))

  def test_short_little_endian_data_raises(self):
    sig = _sig("speed", 0x100, start_bit=0, size=16)
    with self.assertRaises(ValueError):
      decode_signal_value(sig, bytes([0xD2]))


class DecodeFramesTest(unittest.TestCase):
  def test_decode_frames_attaches_values(self):
    sigs = [
      _sig("speed", 0x100, start_bit=0, size=16, factor=0.01),
      _sig("counter", 0x100, start_bit=16, size=8, signal_type=1),  # checksum/counter
    ]
    frames = [
      {"address": 0x100, "bus": 0, "data": "d204050000000000", "time": 1.0},
      {"address": 0x999, "bus": 0, "data": "ffffffffffffffff", "time": 1.0},  # no signals
    ]
    out = decode_frames(sigs, frames)
    self.assertEqual(len(out), 1)
    self.assertAlmostEqual(out[0]["values"]["speed"], 12.34)
    self.assertNotIn("counter", out[0]["values"])

  def test_undecodable_frame_skipped(self):
    sigs = [_sig("speed", 0x100, start_bit=0, size=16)]
    frames = [{"address": 0x100, "bus": 0, "data": "zz", "time": 1.0}]  # bad hex
    self.assertEqual(decode_frames(sigs, frames), [])


class ExtractAnnotationsTest(unittest.TestCase):
  def test_comment_semicolon_inside_quote_does_not_terminate(self):
    """Regression: `;` inside quoted comment text must not end the statement.

    The comment terminator is on the second line; the first line ends with a
    semicolon that is inside the quotes.
    """
    content = (
      'BO_ 256 MSG_A: 8 Vector__XXX\n'
      + ' SG_ speed : 0|16@1+ (0.01,0) [0|100] "km/h" Vector__XXX\n'
      + 'CM_ SG_ 256 speed "threshold 0.5;\n'
      + ' restarts on boot";\n'
      + 'VAL_ 256 speed 0 "Off; low" 1 "On" ;\n'
    )
    units, comments, val_labels = _extract_annotations(content)
    self.assertEqual(units.get((256, "speed")), "km/h")
    self.assertEqual(comments.get((256, "speed")), "threshold 0.5; restarts on boot")
    self.assertEqual(val_labels.get((256, "speed")), {"0": "Off; low", "1": "On"})

  def test_message_comment_and_signal_comment(self):
    content = (
      'CM_ BO_ 42 "wheel speeds; front pair";\n'
      + 'CM_ SG_ 42 wheelSpeed "m/s";\n'
    )
    _units, comments, _val_labels = _extract_annotations(content)
    self.assertEqual(comments.get((42, "")), "wheel speeds; front pair")
    self.assertEqual(comments.get((42, "wheelSpeed")), "m/s")

  def test_multiline_val_labels(self):
    content = (
      'VAL_ 7 gear\n'
      + ' 0 "Park" 1 "Reverse" 2 "Neutral"\n'
      + ';\n'
    )
    _units, _comments, val_labels = _extract_annotations(content)
    self.assertEqual(val_labels.get((7, "gear")), {"0": "Park", "1": "Reverse", "2": "Neutral"})


class GetDecoderTest(unittest.TestCase):
  def test_unavailable_dbc_returns_none(self):
    # bootstrap_pc mocks opendbc away, so parsing cannot succeed on PC.
    self.assertIsNone(get_decoder("no_such_dbc_name_xyz"))

  def test_empty_name_returns_none(self):
    self.assertIsNone(get_decoder(""))


class MultiBusDecoderTest(unittest.TestCase):
  """E: per-bus DBC mapping (dbcmanager-style multi-DBC decode)."""

  def test_get_decoders_unavailable_or_empty(self):
    self.assertIsNone(get_decoders(None))
    self.assertIsNone(get_decoders({}))
    self.assertIsNone(get_decoders({"0": ""}))
    # bootstrap_pc mocks opendbc away, so no DBC can be loaded on PC.
    self.assertIsNone(get_decoders({"0": "no_such_dbc_xyz"}))

  def test_decode_frames_multi_selects_table_by_bus(self):
    decoders = {
      "0": {0x100: [_sig("speed", 0x100, start_bit=0, size=16, factor=0.01)]},
      "1": {0x100: [_sig("temp", 0x100, start_bit=8, size=8)]},
    }
    frames = [
      {"address": 0x100, "bus": 0, "data": "d204050000000000", "time": 1.0},
      {"address": 0x100, "bus": 1, "data": "0064000000000000", "time": 2.0},
      {"address": 0x100, "bus": 9, "data": "ffffffffffffffff", "time": 3.0},  # no table
    ]
    out = decode_frames_multi(decoders, frames)
    self.assertEqual(len(out), 2)
    self.assertAlmostEqual(out[0]["values"]["speed"], 12.34)
    self.assertAlmostEqual(out[1]["values"]["temp"], 100.0)

  def test_decode_frames_multi_skips_undecodable(self):
    decoders = {"0": {0x100: [_sig("speed", 0x100, start_bit=0, size=16)]}}
    frames = [
      {"address": 0x100, "bus": 0, "data": "zz", "time": 1.0},  # bad hex
      {"address": 0x100, "bus": 0, "data": "d2", "time": 2.0},  # too short
    ]
    self.assertEqual(decode_frames_multi(decoders, frames), [])

  def test_decode_frames_multi_empty_decoders(self):
    frames = [{"address": 0x100, "bus": 0, "data": "d204050000000000", "time": 1.0}]
    self.assertEqual(decode_frames_multi(None, frames), [])


if __name__ == "__main__":
  unittest.main()
