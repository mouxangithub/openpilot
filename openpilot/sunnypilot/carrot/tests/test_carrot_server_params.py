"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Tests for the carrot API server's parameter endpoint (port 7000).

The value coercion is what keeps this endpoint safe: `Params.put` casts with
`python2cpp(type(value), params_keys.h type)` and raises TypeError on a mismatch, so a JSON
client sending the int 0 to a BOOL key would otherwise turn into a 500. The coercion tests
therefore run anywhere; the HTTP-level tests need aiohttp and the real `Params`.
"""
import unittest

from openpilot.sunnypilot.carrot.server.services.params import (
  ParamWriteError,
  UnknownKeyName,
  coerce_for_type,
  get_param_values,
  json_safe,
  read_only_reason,
  set_param_value,
)

try:
  from aiohttp.test_utils import TestClient, TestServer

  _HAVE_AIOHTTP = True
except Exception:
  _HAVE_AIOHTTP = False

try:
  # Imported for its side effect only: the HTTP tests below run where the native
  # Params library exists and are skipped where it does not.
  import openpilot.common.params  # noqa: F401

  _HAVE_PARAMS = True
except Exception:
  _HAVE_PARAMS = False


class _KeyType:
  """Stands in for ParamKeyType; the module dispatches on `.name`."""

  def __init__(self, name):
    self.name = name


class _FakeParams:
  """Mirrors the slice of `Params` the service uses."""

  def __init__(self, types=None, store=None):
    self.types = types or {}
    self.store = dict(store or {})
    self.written = []

  def check_key(self, key):
    if key not in self.types:
      raise UnknownKeyName(key)

  def get_type(self, key):
    return _KeyType(self.types[key])

  def put(self, key, dat):
    self.written.append((key, dat))
    self.store[key] = dat

  def get(self, key, *a, **k):
    return self.store.get(key)


class TestCoerceForType(unittest.TestCase):
  def test_bool_accepts_json_and_string_forms(self):
    for raw in (True, 1, 0, "1", "true", "yes", "on", "0", "false", "no", "off"):
      with self.subTest(raw=raw):
        self.assertIsInstance(coerce_for_type(raw, _KeyType("BOOL")), bool)

  def test_bool_rejects_junk(self):
    for raw in ("maybe", 0.5, [], {}):
      with self.subTest(raw=raw), self.assertRaises(ParamWriteError):
        coerce_for_type(raw, _KeyType("BOOL"))

  def test_int_accepts_float_and_string_forms(self):
    self.assertEqual(coerce_for_type(2.0, _KeyType("INT")), 2)
    self.assertEqual(coerce_for_type("42", _KeyType("INT")), 42)
    self.assertEqual(coerce_for_type("-7", _KeyType("INT")), -7)

  def test_int_rejects_fractions_and_junk(self):
    for raw in (2.5, "2.5", "abc", [], None):
      with self.subTest(raw=raw), self.assertRaises(ParamWriteError):
        coerce_for_type(raw, _KeyType("INT"))

  def test_float_accepts_numeric_strings(self):
    self.assertEqual(coerce_for_type("1.5", _KeyType("FLOAT")), 1.5)
    self.assertEqual(coerce_for_type(3, _KeyType("FLOAT")), 3.0)

  def test_string_accepts_scalars(self):
    self.assertEqual(coerce_for_type("zh-CHS", _KeyType("STRING")), "zh-CHS")
    self.assertEqual(coerce_for_type(12, _KeyType("STRING")), "12")
    self.assertEqual(coerce_for_type(True, _KeyType("STRING")), "1")

  def test_json_accepts_containers_and_encoded_text(self):
    self.assertEqual(coerce_for_type({"a": 1}, _KeyType("JSON")), {"a": 1})
    self.assertEqual(coerce_for_type([1, 2], _KeyType("JSON")), [1, 2])
    self.assertEqual(coerce_for_type('{"a": 1}', _KeyType("JSON")), {"a": 1})

  def test_json_rejects_unparseable_text(self):
    for raw in ("{oops", "", 5):
      with self.subTest(raw=raw), self.assertRaises(ParamWriteError):
        coerce_for_type(raw, _KeyType("JSON"))

  def test_time_and_bytes_are_refused_rather_than_guessed(self):
    for kind in ("TIME", "BYTES"):
      with self.subTest(kind=kind), self.assertRaises(ParamWriteError):
        coerce_for_type("whatever", _KeyType(kind))


class TestSetParamValue(unittest.TestCase):
  def test_it_writes_the_coerced_value(self):
    params = _FakeParams({"ExperimentalMode": "INT"})
    self.assertEqual(set_param_value(params, "ExperimentalMode", "1"), 1)
    self.assertEqual(params.written, [("ExperimentalMode", 1)])

  def test_an_unknown_key_is_a_client_error(self):
    params = _FakeParams({})
    with self.assertRaises(ParamWriteError) as ctx:
      set_param_value(params, "NoSuchKey", 1)
    self.assertIn("unknown parameter", str(ctx.exception))

  def test_a_carparams_key_is_read_only(self):
    params = _FakeParams({"CarParams": "BYTES"})
    with self.assertRaises(ParamWriteError) as ctx:
      set_param_value(params, "CarParams", b"x")
    self.assertIn("read-only", str(ctx.exception))
    self.assertNotIn("CarParams", dict(params.written))

  def test_a_params_typeerror_becomes_a_client_error(self):
    class _Strict(_FakeParams):
      def put(self, key, dat):
        raise TypeError("Type mismatch while writing param")

    params = _Strict({"ExperimentalMode": "INT"})
    with self.assertRaises(ParamWriteError) as ctx:
      set_param_value(params, "ExperimentalMode", 1)
    self.assertIn("type mismatch", str(ctx.exception))

  def test_a_missing_name_is_rejected(self):
    for bad in (None, "", "   ", 5):
      with self.subTest(bad=bad), self.assertRaises(ParamWriteError):
        set_param_value(_FakeParams({"A": "INT"}), bad, 1)


class TestGetParamValues(unittest.TestCase):
  def test_it_reads_every_requested_key(self):
    params = _FakeParams({"A": "INT", "B": "STRING"}, {"A": 1, "B": "x"})
    self.assertEqual(get_param_values(params, ["A", "B"]), {"A": 1, "B": "x"})

  def test_one_bad_key_does_not_fail_the_bulk_read(self):
    class _Exploding(_FakeParams):
      def get(self, key, *a, **k):
        if key == "Boom":
          raise RuntimeError("native store unhappy")
        return super().get(key, *a, **k)

    params = _Exploding({"A": "INT"}, {"A": 1})
    self.assertEqual(get_param_values(params, ["A", "Boom"]), {"A": 1, "Boom": None})

  def test_bytes_are_decoded_so_the_payload_is_encodable(self):
    self.assertEqual(json_safe(b"abc"), "abc")
    self.assertEqual(json_safe(b"\xff"), "ff")
    self.assertEqual(json_safe(None), None)


class TestReadOnlyReason(unittest.TestCase):
  def test_carparams_keys_are_read_only_and_others_are_not(self):
    self.assertIsNotNone(read_only_reason("CarParamsSP"))
    self.assertIsNone(read_only_reason("ExperimentalMode"))


@unittest.skipUnless(_HAVE_AIOHTTP and _HAVE_PARAMS, 'needs aiohttp and the native Params store')
class TestParamEndpoints(unittest.IsolatedAsyncioTestCase):
  """End-to-end over a real aiohttp app and the real (isolated) Params store."""

  async def asyncSetUp(self):
    from openpilot.common.test import OpenpilotPrefix  # noqa: F401  (ensures a clean store)
    from openpilot.sunnypilot.carrot.server.app import create_app

    self.app = create_app()
    self.client = TestClient(TestServer(self.app))
    await self.client.start_server()

  async def asyncTearDown(self):
    await self.client.close()

  async def test_health(self):
    resp = await self.client.get('/api/health')
    self.assertEqual(resp.status, 200)
    self.assertTrue((await resp.json())['ok'])

  async def test_param_set_then_params_bulk_round_trip(self):
    resp = await self.client.post('/api/param_set', json={'name': 'IsMetric', 'value': 1})
    self.assertEqual(resp.status, 200)
    body = await resp.json()
    self.assertTrue(body['ok'])
    self.assertEqual(body['value'], True)

    resp = await self.client.get('/api/params_bulk?names=IsMetric')
    self.assertEqual(resp.status, 200)
    values = (await resp.json())['values']
    self.assertEqual(values['IsMetric'], True)

  async def test_a_wrong_type_is_a_400_with_a_message(self):
    resp = await self.client.post('/api/param_set', json={'name': 'IsMetric', 'value': 'not a bool'})
    self.assertEqual(resp.status, 400)
    body = await resp.json()
    self.assertFalse(body['ok'])
    self.assertIn('boolean', body['error'])

  async def test_an_unknown_key_is_a_400(self):
    resp = await self.client.post('/api/param_set', json={'name': 'DefinitelyNotAKey', 'value': 1})
    self.assertEqual(resp.status, 400)
    self.assertIn('unknown parameter', (await resp.json())['error'])

  async def test_missing_names_is_a_400(self):
    resp = await self.client.get('/api/params_bulk')
    self.assertEqual(resp.status, 400)
    self.assertIn('missing names', (await resp.json())['error'])

  async def test_bulk_read_of_an_unknown_key_still_succeeds(self):
    resp = await self.client.get('/api/params_bulk?names=IsMetric,DefinitelyNotAKey')
    self.assertEqual(resp.status, 200)
    self.assertIn('IsMetric', (await resp.json())['values'])

  async def test_device_type_is_answered_though_it_is_not_a_parameter(self):
    # The app asks for it next to real settings; a 400 there loses the whole batch.
    resp = await self.client.get('/api/params_bulk?names=DeviceType')
    self.assertEqual(resp.status, 200)
    self.assertIn('DeviceType', (await resp.json())['values'])


if __name__ == '__main__':
  unittest.main()
