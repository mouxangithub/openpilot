import unittest

from openpilot.sunnypilot.common.car_capability import (
  MOCK_FINGERPRINT,
  capability_fingerprint,
  capability_snapshot,
)


class FakeParams:
  """A Params stand-in for the capability probe."""

  def __init__(self, values: dict, *, bools: dict | None = None):
    self.values = values
    self.bools = bools or {}

  def get(self, key: str):
    return self.values.get(key)

  def get_bool(self, key: str) -> bool:
    return bool(self.bools.get(key, False))


def extract(raw: bytes) -> str:
  """The fake CarParams blob is just the fingerprint as text."""
  return raw.decode("utf-8")


class TestCapabilitySnapshot(unittest.TestCase):
  def test_the_live_snapshot_is_preferred_onroad(self):
    params = FakeParams({"CarParams": b"TOYOTA", "CarParamsPersistent": b"TOYOTA"})
    snapshot = capability_snapshot(params, is_onroad=True, extract=extract,
                                   get=params.get, get_bool=params.get_bool)
    self.assertEqual(snapshot, b"TOYOTA")

  def test_the_persistent_snapshot_is_used_offroad(self):
    params = FakeParams({"CarParamsPersistent": b"TOYOTA"})
    snapshot = capability_snapshot(params, is_onroad=False, extract=extract,
                                   get=params.get, get_bool=params.get_bool)
    self.assertEqual(snapshot, b"TOYOTA")

  def test_a_mock_fingerprint_is_never_usable(self):
    params = FakeParams({"CarParams": MOCK_FINGERPRINT.encode(), "CarParamsPersistent": MOCK_FINGERPRINT.encode()})
    snapshot = capability_snapshot(params, is_onroad=True, extract=extract,
                                   get=params.get, get_bool=params.get_bool)
    self.assertIsNone(snapshot)

  def test_a_mock_live_snapshot_falls_through_to_the_real_one(self):
    params = FakeParams({"CarParams": b"MOCK", "CarParamsPersistent": b"TOYOTA"})
    snapshot = capability_snapshot(params, is_onroad=True, extract=extract,
                                   get=params.get, get_bool=params.get_bool)
    self.assertEqual(snapshot, b"TOYOTA")

  def test_nothing_usable_returns_none(self):
    params = FakeParams({})
    snapshot = capability_snapshot(params, is_onroad=False, extract=extract,
                                   get=params.get, get_bool=params.get_bool)
    self.assertIsNone(snapshot)

  def test_a_forced_fingerprint_that_does_not_match_is_refused(self):
    params = FakeParams({"CarParamsPersistent": b"HONDA"}, bools={"ForceFingerprint": True})
    # CarModel says HONDA but the snapshot says HYUNDAI -> nothing usable
    params.values["CarModel"] = "HYUNDAI"
    snapshot = capability_snapshot(params, is_onroad=False, extract=extract,
                                   get=params.get, get_bool=params.get_bool)
    self.assertIsNone(snapshot)

  def test_a_forced_fingerprint_that_matches_is_accepted(self):
    params = FakeParams({"CarParamsPersistent": b"HONDA", "CarModel": "HONDA"},
                         bools={"ForceFingerprint": True})
    snapshot = capability_snapshot(params, is_onroad=False, extract=extract,
                                   get=params.get, get_bool=params.get_bool)
    self.assertEqual(snapshot, b"HONDA")

  def test_the_previous_route_is_used_only_for_the_forced_model(self):
    params = FakeParams({"CarParamsPrevRoute": b"HONDA", "CarModel": "HONDA"},
                         bools={"ForceFingerprint": True})
    snapshot = capability_snapshot(params, is_onroad=False, extract=extract,
                                   get=params.get, get_bool=params.get_bool)
    self.assertEqual(snapshot, b"HONDA")

  def test_the_previous_route_is_not_used_without_a_forced_model(self):
    params = FakeParams({"CarParamsPrevRoute": b"HONDA"})
    snapshot = capability_snapshot(params, is_onroad=False, extract=extract,
                                   get=params.get, get_bool=params.get_bool)
    self.assertIsNone(snapshot)

  def test_the_previous_route_must_match_the_forced_model_exactly(self):
    params = FakeParams({"CarParamsPrevRoute": b"HONDA", "CarModel": "TOYOTA"},
                         bools={"ForceFingerprint": True})
    snapshot = capability_snapshot(params, is_onroad=False, extract=extract,
                                   get=params.get, get_bool=params.get_bool)
    self.assertIsNone(snapshot)

  def test_an_undecodable_snapshot_is_skipped(self):
    # A blob that cannot be read is skipped, and the next snapshot is tried.
    def partly_broken_extract(raw: bytes) -> str:
      if raw == b"garbage":
        raise ValueError("not a capnp blob")
      return raw.decode("utf-8")

    params = FakeParams({"CarParams": b"garbage", "CarParamsPersistent": b"TOYOTA"})
    snapshot = capability_snapshot(params, is_onroad=True, extract=partly_broken_extract,
                                   get=params.get, get_bool=params.get_bool)
    self.assertEqual(snapshot, b"TOYOTA")

  def test_no_snapshot_is_usable_when_none_can_be_read(self):
    def broken_extract(raw: bytes) -> str:
      raise ValueError("not a capnp blob")

    params = FakeParams({"CarParams": b"garbage", "CarParamsPersistent": b"also garbage"})
    snapshot = capability_snapshot(params, is_onroad=True, extract=broken_extract,
                                   get=params.get, get_bool=params.get_bool)
    self.assertIsNone(snapshot)

  def test_a_missing_callback_is_handled(self):
    params = FakeParams({"CarParamsPersistent": b"TOYOTA"})
    self.assertIsNone(capability_snapshot(params, is_onroad=False, extract=extract))


class TestCapabilityFingerprint(unittest.TestCase):
  def test_it_reads_the_fingerprint(self):
    self.assertEqual(capability_fingerprint(b"TOYOTA", extract), "TOYOTA")

  def test_an_unreadable_snapshot_has_no_fingerprint(self):
    self.assertEqual(capability_fingerprint(b"", extract), "")
    self.assertEqual(capability_fingerprint(None, extract), "")

  def test_a_broken_extractor_has_no_fingerprint(self):
    def broken(raw: bytes) -> str:
      raise ValueError("nope")
    self.assertEqual(capability_fingerprint(b"x", broken), "")


if __name__ == "__main__":
  unittest.main()
