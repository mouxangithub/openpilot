"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""bluetooth HID decoding, command-queue and config-validation tests.

Ported from CarrotPilot's `bluetooth/tests/test_input.py`, converted from pytest to
`unittest` because this repository dropped pytest in favour of `tools/test_runner.py`
(see AGENTS.md). Every assertion is kept as-is.

Why this suite matters here: the decoder is a pure state machine fed by evdev, and the
command queue is the only channel from the remote to `cruise.py` / `desire_helper.py`.
Both were ported from CarrotPilot, and port drift in them is invisible at runtime - a
gesture that stops firing just looks like a dead remote. `yiser_j6.json` is a recorded
real-device HID stream, so it pins the decoder against actual firmware timings.

Two upstream test modules are intentionally NOT ported:

* `test_api.py` - it exercises an aiohttp HTTP API that does not exist in this fork.
  `daemon.py` accepts no commands over HTTP or raw sockets by design.
* `test_daemon.py` - it drives `daemon.main()` with a heavily monkeypatched environment
  through `OpenpilotTestCase`'s `monkeypatch` shim, which needs the installed `openpilot`
  package (i.e. the `opendbc`/`capnp` native deps). It cannot be verified on a bare PC
  checkout, so port it together with whatever CI job runs the native tests.
"""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from openpilot.sunnypilot.carrot.bluetooth.model import (
  Clicks, CommandReader, CommandWriter, DEFAULT_MAPPING, Decoder,
  atomic_json, validate_config,
)

try:
  from openpilot.sunnypilot.carrot.bluetooth.bluez import Bluez
except ImportError:  # jeepney (D-Bus) is only installed on the device / in CI
  Bluez = None


def press(decoder, code, start, duration=.05):
  decoder.feed(1, code, 1, start)
  decoder.feed(0, 0, 0, start)
  decoder.feed(1, code, 0, start + duration)
  return decoder.feed(0, 0, 0, start + duration)


class _TempDirTestCase(unittest.TestCase):
  """Stand-in for pytest's `tmp_path` fixture."""

  def setUp(self):
    super().setUp()
    self._tempdir = tempfile.TemporaryDirectory()
    self.tmp_path = Path(self._tempdir.name)

  def tearDown(self):
    self._tempdir.cleanup()
    super().tearDown()


class TestDecoderGestures(_TempDirTestCase):
  def test_recorded_seven_yiser_buttons(self):
    decoder = Decoder('yiser-j6')
    tokens = []
    for stamp, kind, code, value in json.loads(Path(__file__).with_name('yiser_j6.json').read_text()):
      tokens.extend(decoder.feed(kind, code, value, stamp))
    self.assertEqual(tokens, ['up', 'down', 'left', 'right', 'center', '1', '2'])
    self.assertEqual([DEFAULT_MAPPING[t] for t in tokens],
                     ['accelCruise', 'decelCruise', 'laneLeft', 'laneRight', 'paddleDecel', 'gapAdjustCruise', 'none'])

  def test_key_repeat_release_and_dropped_events(self):
    decoder = Decoder()
    self.assertEqual(decoder.feed(1, 30, 1, 0), [])
    self.assertEqual(decoder.feed(1, 30, 2, .1), [])
    self.assertEqual(decoder.feed(0, 0, 0, .1), [])
    self.assertEqual(decoder.feed(1, 30, 0, .2), [])
    self.assertEqual(decoder.feed(0, 0, 0, .2), ['key:30'])
    self.assertEqual(decoder.feed(1, 30, 0, .3), [])
    self.assertEqual(decoder.feed(0, 0, 0, .3), [])
    decoder.feed(1, 30, 1, 1)
    decoder.feed(0, 3, 0, 1)
    decoder.feed(1, 30, 0, 1.1)
    self.assertEqual(decoder.feed(0, 0, 0, 1.1), [])

  def test_stale_incomplete_gestures_do_not_fire(self):
    decoder = Decoder('yiser-j6')
    for event in [(3, 0, 300), (3, 1, 500), (1, 330, 1), (0, 0, 0)]:
      decoder.feed(*event, 1)
    decoder.feed(1, 330, 0, 3)
    self.assertEqual(decoder.feed(0, 0, 0, 3), [])
    decoder = Decoder('yiser-j6')
    decoder.feed(1, 330, 0, 4)
    self.assertEqual(decoder.feed(0, 0, 0, 4), [])

  def test_single_has_no_new_delay_without_double_mapping(self):
    decoder = Decoder(mapping={'key:30': 'accelCruise', 'key:30@double': 'none'})
    self.assertEqual(press(decoder, 30, 1), ['key:30'])
    self.assertEqual(press(decoder, 30, 1.1), ['key:30'])

  def test_double_replaces_both_single_actions_and_single_waits(self):
    decoder = Decoder(mapping={'key:30': 'accelCruise', 'key:30@double': 'carrotCruise'})
    self.assertEqual(press(decoder, 30, 1), [])
    self.assertEqual(press(decoder, 30, 1.2), ['key:30@double'])
    self.assertEqual(decoder.flush(1.7), [])
    self.assertEqual(press(decoder, 30, 2), [])
    self.assertEqual(decoder.flush(2.39), [])
    self.assertEqual(decoder.flush(2.41), ['key:30'])
    self.assertEqual(decoder.flush(2.42), [])

  def test_mode_long_fires_while_held_once_and_never_from_keyboard_repeat(self):
    decoder = Decoder(mapping={'key:115': 'accelCruise', 'key:115@long': 'carrotCruise'})
    decoder.feed(1, 115, 1, 1)
    for stamp in (1.3, 1.6, 1.9, 2.1):
      decoder.feed(1, 115, 2, stamp)
      self.assertEqual(decoder.feed(0, 0, 0, stamp), [])
      self.assertEqual(decoder.flush(stamp), ['key:115@long'] if stamp == 1.9 else [])
    decoder.feed(1, 115, 0, 2.2)
    self.assertEqual(decoder.feed(0, 0, 0, 2.2), [])
    self.assertEqual(decoder.flush(2.6), [])

  def test_long_does_not_repeat_without_a_long_mapping(self):
    decoder = Decoder(mapping={'key:115': 'accelCruise'})
    decoder.feed(1, 115, 1, 1)
    decoder.feed(0, 0, 0, 1)
    self.assertEqual(decoder.flush(2), [])
    decoder.feed(1, 115, 0, 2.1)
    self.assertEqual(decoder.feed(0, 0, 0, 2.1), ['key:115'])

  def test_incomplete_frame_cannot_generate_a_held_tick(self):
    decoder = Decoder(mapping={'key:115@long': 'accelCruise'})
    decoder.feed(1, 115, 1, 1)
    self.assertEqual(decoder.flush(2), [])
    decoder.feed(0, 0, 0, 2)
    self.assertEqual(decoder.flush(2), ['key:115@long'])
    decoder.feed(1, 115, 0, 2.1)
    self.assertEqual(decoder.flush(3), [])
    self.assertEqual(decoder.feed(0, 0, 0, 3), [])

  def test_touch_long_press_and_firmware_short_pulses_are_distinct(self):
    decoder = Decoder('yiser-j6', {'center@long': 'carrotCruise'})
    for event in [(3, 0, 300), (3, 1, 500), (1, 330, 1), (0, 0, 0)]:
      decoder.feed(*event, 1)
    decoder.feed(1, 330, 0, 2)
    self.assertEqual(decoder.feed(0, 0, 0, 2), ['center@long'])
    # A shutter which reports only short pulses cannot expose physical hold time.
    self.assertEqual(press(Decoder(mapping={'key:115@long': 'carrotCruise'}), 115, 1, .01), ['key:115'])

  def test_learning_detects_unassigned_gestures_and_dropped_frames_cancel_pending(self):
    decoder = Decoder(learning=True)
    self.assertEqual(press(decoder, 30, 1), [])
    self.assertEqual(press(decoder, 30, 1.15), ['key:30@double'])
    self.assertEqual(press(decoder, 31, 2, .8), ['key:31@long'])
    self.assertEqual(press(decoder, 32, 3), [])
    decoder.feed(0, 3, 0, 3.1)
    self.assertEqual(decoder.flush(3.41), [])

  def test_delayed_single_expires_instead_of_firing_after_stall(self):
    clicks = Clicks({'key:30@double': 'carrotCruise'})
    self.assertEqual(clicks.release('key:30', .05, 1), [])
    self.assertEqual(clicks.flush(2), [])

  def test_devices_cannot_complete_each_others_double_click(self):
    a, b = Decoder(learning=True), Decoder(learning=True)
    self.assertEqual(press(a, 115, 1), [])
    self.assertEqual(press(b, 115, 1.1), [])
    self.assertEqual(a.flush(1.41), ['key:115'])
    self.assertEqual(b.flush(1.51), ['key:115'])

  def test_speed_long_repeats_on_timer_then_release_stops_without_an_extra_click(self):
    for action in ('accelCruise', 'decelCruise', 'accelCruiseLong', 'decelCruiseLong'):
      with self.subTest(action=action):
        decoder = Decoder(mapping={'key:115': 'gapAdjustCruise', 'key:115@long': action})
        decoder.feed(1, 115, 1, 1)
        decoder.feed(0, 0, 0, 1)
        self.assertEqual(decoder.flush(1.69), [])
        self.assertEqual(decoder.flush(1.71), ['key:115@long'])
        self.assertFalse(decoder.repeated)
        self.assertEqual(decoder.flush(2.20), [])
        self.assertEqual(decoder.flush(2.22), ['key:115@long'])
        self.assertEqual(decoder.repeated, {'key:115@long'})
        self.assertEqual(decoder.flush(4), ['key:115@long'])  # One tick, no catch-up burst.
        self.assertEqual(decoder.flush(4.01), [])
        decoder.feed(1, 115, 0, 4.1)
        self.assertEqual(decoder.feed(0, 0, 0, 4.1), [])
        self.assertFalse(decoder.active_longs)
        self.assertEqual(decoder.flush(5), [])

  def test_held_repeats_stop_on_drop_interruption_or_ten_second_timeout(self):
    for end in ('drop', 'cancel', 'timeout'):
      with self.subTest(end=end):
        decoder = Decoder(mapping={'key:115@long': 'accelCruise'})
        decoder.feed(1, 115, 1, 1)
        decoder.feed(0, 0, 0, 1)
        self.assertEqual(decoder.flush(1.8), ['key:115@long'])
        if end == 'drop':
          decoder.feed(0, 3, 0, 2)
        elif end == 'cancel':
          decoder.cancel_holds()
        self.assertEqual(decoder.flush(11.1 if end == 'timeout' else 3), [])
        self.assertFalse(decoder.active_longs)
        decoder.feed(1, 115, 0, 12)
        self.assertEqual(decoder.feed(0, 0, 0, 12), [])

  def test_touch_hold_starts_once_and_direction_change_cannot_retrigger(self):
    for cancel_before_first in (False, True):
      with self.subTest(cancel_before_first=cancel_before_first):
        decoder = Decoder('yiser-j6', {'center@long': 'carrotCruise', 'left@long': 'laneLeft'})
        for event in [(3, 0, 300), (3, 1, 500), (1, 330, 1), (0, 0, 0)]:
          decoder.feed(*event, 1)
        if cancel_before_first:
          decoder.cancel_holds()
        self.assertEqual(decoder.flush(1.8), [] if cancel_before_first else ['center@long'])
        decoder.feed(3, 0, 600, 2)
        decoder.feed(0, 0, 0, 2)
        self.assertEqual(decoder.flush(3), [])
        decoder.feed(1, 330, 0, 3.1)
        self.assertEqual(decoder.feed(0, 0, 0, 3.1), [])


class TestCommandQueue(_TempDirTestCase):
  def test_commands_reject_replay_startup_stale_and_disallowed(self):
    reader = CommandReader('cruise', self.tmp_path)
    reader.started = 10
    for number, (created, now, allowed, expected) in enumerate([
      (9.9, 10, True, None), (10.1, 10.2, True, 'accelCruise'), (10.3, 10.9, True, None),
      (12, 11, True, None), (11.1, 11.2, False, None), (11.3, 11.4, True, 'accelCruise'),
    ]):
      atomic_json(reader.path, {'id': str(number), 'time': created, 'action': 'accelCruise'})
      self.assertEqual(reader.read(allowed=allowed, now=now), expected)
      self.assertIsNone(reader.read(now=now + .03))

  def test_entering_test_mode_cancels_pending_action(self):
    reader = CommandReader('cruise', self.tmp_path)
    reader.started = 10
    mac = '66:C0:0C:7B:6E:71'
    atomic_json(reader.path, {'id': 'pending', 'time': 11, 'action': 'accelCruise', 'address': mac})
    atomic_json(self.tmp_path / 'learn.json', {'address': mac, 'until': 120})
    self.assertIsNone(reader.read(now=11.1))
    atomic_json(self.tmp_path / 'learn.json', {})
    self.assertIsNone(reader.read(now=11.2))

  def test_release_cancels_unconsumed_hold_events_but_preserves_other_device(self):
    writer = CommandWriter(self.tmp_path)
    reader = CommandReader('cruise', self.tmp_path)
    reader.started = 10
    writer.send('A', 'accelCruiseLong', 11, hold='event1:key:115', repeat=True)
    writer.send('B', 'gapAdjustCruise', 11)
    writer.prune({'A', 'B'}, 11.02, active_holds=set())
    self.assertEqual(reader.read(now=11.05), 'gapAdjustCruise')
    self.assertFalse(reader.is_repeat)
    self.assertIsNone(reader.read(now=11.1))

  def test_hold_queue_keeps_only_latest_tick_and_marks_repeat(self):
    writer = CommandWriter(self.tmp_path)
    reader = CommandReader('cruise', self.tmp_path)
    reader.started = 10
    writer.send('A', 'accelCruiseLong', 11, hold='held')
    writer.send('A', 'accelCruiseLong', 11.1, hold='held', repeat=True)
    self.assertEqual(len(writer.events['cruise']), 1)
    self.assertEqual(reader.read(now=11.15), 'accelCruiseLong')
    self.assertTrue(reader.is_repeat)
    self.assertIsNone(reader.read(now=11.2))
    self.assertFalse(reader.is_repeat)

  def test_multi_device_queue_keeps_all_commands_in_order_once(self):
    writer = CommandWriter(self.tmp_path)
    reader = CommandReader('cruise', self.tmp_path)
    reader.started = 10
    for mac, action in [('A', 'accelCruise'), ('B', 'decelCruise'), ('C', 'carrotCruise')]:
      writer.send(mac, action, 11)
    self.assertEqual(reader.read(now=11.05), 'accelCruise')
    self.assertEqual(reader.read(now=11.08), 'decelCruise')
    self.assertEqual(reader.read(now=11.11), 'carrotCruise')
    self.assertIsNone(reader.read(now=11.14))

  def test_device_disconnect_and_test_only_cancel_its_queued_commands(self):
    writer = CommandWriter(self.tmp_path)
    reader = CommandReader('cruise', self.tmp_path)
    reader.started = 10
    writer.send('A', 'accelCruise', 11)
    writer.send('B', 'decelCruise', 11)
    writer.prune({'B'}, 11.01)
    self.assertEqual(reader.read(now=11.05), 'decelCruise')
    writer.send('A', 'accelCruise', 11.1)
    writer.send('B', 'carrotCruise', 11.1)
    atomic_json(self.tmp_path / 'learn.json', {'address': 'A', 'until': 120})
    self.assertEqual(reader.read(now=11.15), 'carrotCruise')
    atomic_json(self.tmp_path / 'learn.json', {})
    self.assertIsNone(reader.read(now=11.2))

  def test_disallowed_drains_all_devices_and_channels_remain_separate(self):
    writer = CommandWriter(self.tmp_path)
    cruise = CommandReader('cruise', self.tmp_path)
    lane = CommandReader('lane', self.tmp_path)
    cruise.started = lane.started = 10
    writer.send('A', 'accelCruise', 11)
    writer.send('B', 'decelCruise', 11)
    writer.send('B', 'laneLeft', 11)
    self.assertIsNone(cruise.read(allowed=False, now=11.05))
    self.assertIsNone(cruise.read(now=11.08))
    self.assertEqual(lane.read(now=11.08), 'laneLeft')

  def test_command_queue_is_bounded_and_expires(self):
    writer = CommandWriter(self.tmp_path)
    reader = CommandReader('cruise', self.tmp_path)
    reader.started = 10
    for i in range(100):
      writer.send(str(i), 'accelCruise', 11)
    self.assertEqual(len(writer.events['cruise']), 64)
    self.assertIsNone(reader.read(now=11.5))
    writer.prune(set(), 11.5)
    self.assertEqual(json.loads(reader.path.read_text()), {'events': []})

  def test_cancelled_device_events_cannot_return_when_writer_republishes(self):
    writer = CommandWriter(self.tmp_path)
    reader = CommandReader('cruise', self.tmp_path)
    reader.started = 10
    writer.send('A', 'accelCruise', 11)
    atomic_json(self.tmp_path / 'cancelled.json', {'A': 11.01})
    writer.send('B', 'carrotCruise', 11.02)
    self.assertEqual(reader.read(now=11.05), 'carrotCruise')
    self.assertIsNone(reader.read(now=11.08))


class TestConfigValidation(unittest.TestCase):
  def test_invalid_mapping(self):
    invalid_devices = [
      {'profile': 'shell'},
      {'profile': 'generic', 'enabled': 'true'},
      {'profile': 'generic', 'mapping': {'key:999': 'accelCruise'}},
      {'profile': 'generic', 'mapping': {'key:30': 'systemctl reboot'}},
    ]
    for device in invalid_devices:
      with self.subTest(device=device), self.assertRaises(ValueError):
        validate_config({'devices': {'66:C0:0C:7B:6E:71': device}})

  def test_extended_mappings_and_device_limit(self):
    devices = {f'00:00:00:00:00:{i:02X}': {'profile': 'generic', 'enabled': True,
      'mapping': {'key:115': 'accelCruise', 'key:115@double': 'carrotCruise', 'key:115@long': 'paddleDecel'}} for i in range(16)}
    self.assertEqual(len(validate_config({'devices': devices})['devices']), 16)
    devices['00:00:00:00:00:FF'] = devices['00:00:00:00:00:00']
    with self.assertRaisesRegex(ValueError, '16'):
      validate_config({'devices': devices})


@unittest.skipIf(Bluez is None, 'jeepney (D-Bus) not installed')
class TestBluezPairing(unittest.TestCase):
  def test_pairing_prompt_validation(self):
    async def run():
      client = Bluez()
      client.prompt = {'id': 'current', 'kind': 'RequestPasskey'}
      client.answer = asyncio.get_running_loop().create_future()
      with self.assertRaises(ValueError):
        client.respond('old', '123456')
      with self.assertRaises(ValueError):
        client.respond('current', 'not a number')
      client.respond('current', '123456')
      self.assertEqual(await client.answer, '123456')

    asyncio.run(run())


if __name__ == '__main__':
  unittest.main()
