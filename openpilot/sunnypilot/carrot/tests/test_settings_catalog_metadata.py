"""The tuning metadata declared in params_keys.h reaches the settings catalog.

Two separate claims are checked here:

- The reader side: ``_declared_metadata`` turns the compiled key table into
  per-key numbers, and falls back to "not a knob, advanced" when the store has
  no opinion. That runs anywhere.
- The consumer side: ``attach_tuning_metadata`` stamps those numbers onto the catalog the
  panel downloads (``services.settings.get_settings_cached``), and ``carrot_catalog``
  carries them too. Both pull ``carrot.config`` -> hardware -> fcntl, so those only run on
  a device; skipping them on a PC host is an environment fact, not a gap in the check.
"""
import importlib.util
import unittest

from openpilot.sunnypilot.carrot.server.services.settings_sp import _declared_metadata, attach_tuning_metadata

DEVICE_ONLY = unittest.skipUnless(importlib.util.find_spec("fcntl") is not None,
                                  "building the carrot catalog needs the device import chain")


class FakeMetadata:
  """A store that answers the metadata accessors, or refuses to."""

  def __init__(self, levels: dict | None = None, tiers: dict | None = None, *, broken: bool = False):
    self.levels = dict(levels or {})
    self.tiers = dict(tiers or {})
    self.broken = broken

  def get_tuning_level(self, key: str) -> int:
    if self.broken:
      raise OSError("no metadata here")
    return self.levels.get(key, 0)

  def get_settings_tier(self, key: str) -> int:
    if self.broken:
      raise OSError("no metadata here")
    return self.tiers.get(key, 1)


class TestDeclaredMetadata(unittest.TestCase):
  def test_a_declared_level_is_reported(self):
    levels, tiers = _declared_metadata(["CarrotEnabled"],
                                       FakeMetadata({"CarrotEnabled": 1}, {"CarrotEnabled": 0}))
    self.assertEqual(levels, {"CarrotEnabled": 1})
    self.assertEqual(tiers, {"CarrotEnabled": 0})

  def test_a_key_that_declares_nothing_is_not_a_knob(self):
    levels, tiers = _declared_metadata(["Unknown"], FakeMetadata())
    self.assertEqual(levels, {})
    self.assertEqual(tiers, {"Unknown": 1})

  def test_a_store_without_the_accessors_reports_no_levels(self):
    # A device whose libparams_c.so predates the metadata behaves exactly like
    # the pre-metadata build: every key is "advanced", none is a knob.
    class Bare:
      pass

    levels, tiers = _declared_metadata(["CarrotEnabled"], Bare())
    self.assertEqual(levels, {})
    self.assertEqual(tiers, {"CarrotEnabled": 1})

  def test_a_store_that_raises_falls_back_per_key(self):
    levels, tiers = _declared_metadata(["CarrotEnabled"], FakeMetadata(broken=True))
    self.assertEqual(levels, {})
    self.assertEqual(tiers, {"CarrotEnabled": 1})

  def test_the_no_argument_form_uses_the_real_store(self):
    """Called with no store, the reader builds one and answers from the key table.

    The catalog path uses exactly this form. On a device the answer is the
    declaration; on a host whose store cannot be built it degrades to empty,
    which is why this only asserts that it does not raise.
    """
    levels, tiers = _declared_metadata(["CarrotEnabled"])
    self.assertIsInstance(levels, dict)
    self.assertIsInstance(tiers, dict)


class TestAttachTuningMetadata(unittest.TestCase):
  """The stamping step itself, with the store injected so it runs on any host."""

  def test_every_entry_gets_both_numbers(self):
    by_name = {"CarrotEnabled": {"name": "CarrotEnabled"},
               "SteerRatio": {"name": "SteerRatio"}}
    attach_tuning_metadata(by_name, FakeMetadata({"CarrotEnabled": 1}, {"CarrotEnabled": 0}))
    self.assertEqual(by_name["CarrotEnabled"]["tuningLevel"], 1)
    self.assertEqual(by_name["CarrotEnabled"]["settingsTier"], 0)
    # SteerRatio is not a Carrot knob and declares nothing: not a knob, advanced.
    self.assertEqual(by_name["SteerRatio"]["tuningLevel"], 0)
    self.assertEqual(by_name["SteerRatio"]["settingsTier"], 1)

  def test_the_entry_object_is_the_one_that_was_passed_in(self):
    """`data["params"]`, `groups` and `by_name` share these dicts; a copy would drift."""
    entry = {"name": "CarrotEnabled"}
    by_name = {"CarrotEnabled": entry}
    attach_tuning_metadata(by_name, FakeMetadata({"CarrotEnabled": 2}, {"CarrotEnabled": 1}))
    self.assertIs(by_name["CarrotEnabled"], entry)
    self.assertEqual(entry["tuningLevel"], 2)

  def test_an_empty_catalog_is_not_an_error(self):
    self.assertEqual(attach_tuning_metadata({}, FakeMetadata()), {})

  def test_a_store_that_raises_leaves_defaults_behind(self):
    by_name = {"CarrotEnabled": {"name": "CarrotEnabled"}}
    attach_tuning_metadata(by_name, FakeMetadata(broken=True))
    self.assertEqual(by_name["CarrotEnabled"]["tuningLevel"], 0)
    self.assertEqual(by_name["CarrotEnabled"]["settingsTier"], 1)

  def test_a_non_dict_entry_is_left_alone(self):
    """The catalog is JSON, so this guards a corrupt file rather than a real shape."""
    by_name = {"CarrotEnabled": None}
    attach_tuning_metadata(by_name, FakeMetadata({"CarrotEnabled": 1}))
    self.assertIsNone(by_name["CarrotEnabled"])


@DEVICE_ONLY
class TestTheLiveCatalogCarriesTheMetadata(unittest.TestCase):
  """The catalog the panel actually downloads is the one that has to carry the numbers.

  There used to be a second, parallel `carrot_catalog()` in `settings_sp` and these
  assertions were written against it. It had no production reader - the served settings
  page comes from `get_settings_cached` - so it was metadata written for nobody, and it
  could drift from the served payload without anything noticing. It is gone; this checks
  the live path end to end instead.
  """

  def _by_name(self) -> dict:
    from openpilot.sunnypilot.carrot.server.services.settings import get_settings_cached

    _, _, by_name, _ = get_settings_cached()
    return by_name

  def test_every_served_entry_carries_both_numbers(self):
    by_name = self._by_name()
    self.assertGreater(len(by_name), 0)
    for name, entry in by_name.items():
      self.assertIn("tuningLevel", entry, name)
      self.assertIn("settingsTier", entry, name)
      self.assertIsInstance(entry["tuningLevel"], int)
      self.assertIsInstance(entry["settingsTier"], int)

  def test_every_served_number_matches_the_declaration(self):
    """The payload must report the declaration, not a second opinion.

    This is the assertion the deleted `carrot_catalog` test used to make, moved onto the
    catalog that is actually served - for every key, not a sample.
    """
    from openpilot.common.params import Params
    from openpilot.sunnypilot.common.param_read import read_settings_tier, read_tuning_level

    by_name = self._by_name()
    params = Params()
    for name, entry in by_name.items():
      self.assertEqual(entry["tuningLevel"], read_tuning_level(params, name, 0), name)
      self.assertEqual(entry["settingsTier"], read_settings_tier(params, name, 1), name)

  def test_a_declared_control_switch_reports_its_level(self):
    """CarrotEnabled is declared level 1 / tier simple, so the served catalog says so."""
    entry = self._by_name().get("CarrotEnabled")
    self.assertIsNotNone(entry, "the served catalog lost CarrotEnabled")
    self.assertEqual((entry["tuningLevel"], entry["settingsTier"]), (1, 0))


if __name__ == "__main__":
  unittest.main()
