import math
import unittest

from openpilot.sunnypilot.common.param_read import read_bool, read_float, read_str


class UnknownKeyName(Exception):
  """Mirrors openpilot.common.params.UnknownKeyName without importing it."""


class FakeParams:
  """Params stand-in with the real signatures from common/params.py."""

  def __init__(self, values: dict, *, missing: tuple = (), broken: tuple = ()):
    self.values = values
    self.missing = set(missing)
    self.broken = set(broken)

  def _check(self, key: str) -> None:
    if key in self.missing:
      raise UnknownKeyName(key)
    if key in self.broken:
      raise RuntimeError("something else went wrong")

  def get(self, key: str, block: bool = False, return_default: bool = False):
    self._check(key)
    if key in self.values:
      return self.values[key]
    return None

  def get_bool(self, key: str, block: bool = False) -> bool:
    self._check(key)
    return bool(self.values.get(key, False))

  def get_float(self, key: str, default: float = 0.0) -> float:
    self._check(key)
    try:
      return float(self.get(key))
    except (TypeError, ValueError):
      return default


class TestReadBool(unittest.TestCase):
  def test_reads_a_registered_key(self):
    self.assertTrue(read_bool(FakeParams({"Feature": True}), "Feature"))
    self.assertFalse(read_bool(FakeParams({"Feature": False}), "Feature"))

  def test_unregistered_key_falls_back_to_the_default(self):
    params = FakeParams({}, missing=("Feature",))
    self.assertFalse(read_bool(params, "Feature"))
    self.assertTrue(read_bool(params, "Feature", default=True))

  def test_unset_key_reads_as_false(self):
    self.assertFalse(read_bool(FakeParams({}), "Feature"))

  def test_an_unrelated_error_is_not_swallowed(self):
    params = FakeParams({}, broken=("Feature",))
    with self.assertRaises(RuntimeError):
      read_bool(params, "Feature")


class TestReadFloat(unittest.TestCase):
  def test_reads_a_registered_key(self):
    self.assertAlmostEqual(read_float(FakeParams({"Gain": 1.5}), "Gain"), 1.5)

  def test_unregistered_key_falls_back_to_the_default(self):
    params = FakeParams({}, missing=("Gain",))
    self.assertAlmostEqual(read_float(params, "Gain"), 0.0)
    self.assertAlmostEqual(read_float(params, "Gain", 2.5), 2.5)

  def test_unset_key_reads_as_the_default(self):
    self.assertAlmostEqual(read_float(FakeParams({}), "Gain"), 0.0)

  def test_a_non_numeric_value_reads_as_the_default(self):
    self.assertAlmostEqual(read_float(FakeParams({"Gain": "abc"}), "Gain", 0.75), 0.75)

  def test_a_non_finite_value_reads_as_the_default(self):
    self.assertAlmostEqual(read_float(FakeParams({"Gain": float("nan")}), "Gain", 0.75), 0.75)
    self.assertAlmostEqual(read_float(FakeParams({"Gain": float("inf")}), "Gain", 0.75), 0.75)

  def test_a_numeric_string_is_accepted(self):
    self.assertAlmostEqual(read_float(FakeParams({"Gain": "2.5"}), "Gain"), 2.5)

  def test_an_unrelated_error_is_not_swallowed(self):
    params = FakeParams({}, broken=("Gain",))
    with self.assertRaises(RuntimeError):
      read_float(params, "Gain")


class TestReadStr(unittest.TestCase):
  def test_reads_a_registered_key(self):
    self.assertEqual(read_str(FakeParams({"State": "rain"}), "State"), "rain")

  def test_unregistered_key_falls_back_to_the_default(self):
    params = FakeParams({}, missing=("State",))
    self.assertEqual(read_str(params, "State"), "")
    self.assertEqual(read_str(params, "State", "clear"), "clear")

  def test_unset_key_reads_as_the_default(self):
    self.assertEqual(read_str(FakeParams({}), "State"), "")

  def test_an_unrelated_error_is_not_swallowed(self):
    params = FakeParams({}, broken=("State",))
    with self.assertRaises(RuntimeError):
      read_str(params, "State")


class TestRealParamsSignature(unittest.TestCase):
  """The helpers must not rely on a keyword the real Params rejects.

  Params.get_float is get_float(key, default=0.0); it has no return_default
  keyword. Passing one raises TypeError, so the helpers fetch the raw value
  through get() instead.
  """

  def test_get_float_rejects_return_default(self):
    params = FakeParams({"Gain": 1.0})
    with self.assertRaises(TypeError):
      params.get_float("Gain", return_default=True)  # type: ignore[call-arg]

  def test_the_helper_still_works(self):
    self.assertAlmostEqual(read_float(FakeParams({"Gain": 1.0}), "Gain"), 1.0)
    self.assertTrue(math.isfinite(read_float(FakeParams({}), "Gain")))


if __name__ == "__main__":
  unittest.main()
