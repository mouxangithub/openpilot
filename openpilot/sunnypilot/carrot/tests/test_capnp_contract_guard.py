"""Guard the capnp struct IDs and field ordinals this fork shares with carrotpilot.

Why a test and not a comment: a capnp struct ID is identity, not a name. Two
schemas that declare the same ID for different structs are the same type as far
as the wire format is concerned, so loading both in one process does not fail
loudly - it silently aliases one struct onto the other. carrotpilot and this
fork happen to use three of the same IDs for entirely different payloads
(``CarrotMan`` vs ``SelfdriveStateSP``, and so on), which makes a copy-paste
port from carrot the most likely way to introduce that collision.

The same reasoning applies to field ordinals inside a struct: appending is safe,
reordering or reusing an ordinal changes the meaning of an existing field. This
test pins the appends this fork made so a later port cannot quietly renumber
them.

Both checks are static. The carrot server imports ``fcntl`` through
``openpilot.common.params``, so it cannot be imported on a PC at all; parsing
the schema text answers the question without running anything.
"""
import os
import re
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
CUSTOM_CAPNP = os.path.join(REPO_ROOT, "openpilot", "cereal", "custom.capnp")
CAR_CAPNP = os.path.join(REPO_ROOT, "opendbc_repo", "opendbc", "car", "car.capnp")

# Struct IDs that carrotpilot also uses, for DIFFERENT structs. Pinned here so a
# port cannot silently reuse one: if this fork ever needs carrot's payload it
# must take a fresh ID (``capnp id``) and map the fields explicitly.
SHARED_WITH_CARROT = {
  "SelfdriveStateSP": "0x81c2f05a394cf4af",   # carrot: CarrotMan
  "ModelManagerSP": "0xaedffd8f31e7b55d",     # carrot: CarrotNaviState
  "LongitudinalPlanSP": "0xf35cc4560bbf6ec2",  # carrot: CarrotNaviMedia
}

# The highest CarState ordinal this fork declares. Appends must start above it;
# carrot's CarState uses a different (larger) ordinal space entirely, so a port
# must translate rather than copy an ordinal.
#
# 71 was the last upstream ordinal before the carrot-ported fields were added.
# 72-74 are vCluRatio / speedLimitDistance / logCarrot, appended so the readers
# in carrot_functions.py and carrot_serv.py stop falling back to a default.
# 75-79 are the source-aware blindspot split (cp c6566c65a). cp's CarState
# fills @75-94 with its own fields and uses @95-99 for these, so the ordinals
# could NOT be copied: capnp forbids ordinal holes and this fork's CarState
# ended at @74 (a copy-pasted @95 actually broke the device build once — capnpc
# aborts with "Skipped ordinal @75"). Lesson: cp's CarState ordinal space is
# NOT ours; append from our own tail and never copy cp ordinals.
CAR_STATE_LAST_ORDINAL = 79

# The carrot-ported appends, pinned so a later edit cannot renumber them onto an
# existing field (which would read as a wrong value rather than fail).
CAR_STATE_CARROT_FIELDS = {
  "vCluRatio": 72,
  "speedLimitDistance": 73,
  "logCarrot": 74,
  "leftBlindspotOem": 75,
  "rightBlindspotOem": 76,
  "leftBlindspotOnnx": 77,
  "rightBlindspotOnnx": 78,
  "blindspotSplitSourcesValid": 79,
}


def _struct_ids(path: str) -> dict[str, str]:
  """Map struct name -> declared capnp ID for every struct in the schema."""
  with open(path, encoding="utf-8") as f:
    text = f.read()
  return dict(re.findall(r"struct\s+(\w+)\s+@(0x[0-9a-fA-F]+)", text))


def _struct_field_ordinals(path: str, struct: str) -> dict[str, int]:
  """Map field name -> ordinal for one struct's OWN fields.

  A top-level struct may or may not carry an explicit ID (``struct X @0x...``
  versus ``struct X {``), so the ID part is optional here.

  Only fields indented one level are the struct's own. Nested structs and
  groups restart their ordinals at 0 (``CarState.standstill @18`` encloses a
  ``standstill @4``), so a flat scan would report false duplicates.
  """
  with open(path, encoding="utf-8") as f:
    text = f.read()
  match = re.search(rf"^struct\s+{struct}\s*(?:@0x[0-9a-fA-F]+)?\s*\{{(.*?)\n\}}", text, re.S | re.M)
  if match is None:
    return {}
  own: dict[str, int] = {}
  for line in match.group(1).splitlines():
    found = re.match(r"^  (\w+)\s+@(\d+)", line)
    if found is not None:
      own[found.group(1)] = int(found.group(2))
  return own


class TestCapnpStructIdsAreUnique(unittest.TestCase):
  def test_custom_capnp_declares_no_duplicate_ids(self):
    ids = _struct_ids(CUSTOM_CAPNP)
    seen: dict[str, str] = {}
    for name, value in ids.items():
      if value in seen:
        self.fail(f"{name} and {seen[value]} share struct ID {value} in custom.capnp")
      seen[value] = name

  def test_carrot_shared_ids_stay_on_the_expected_struct(self):
    """The IDs carrot uses for other structs must not drift to a third meaning.

    If one of these moves, either the schema was renumbered (a wire break) or a
    carrot struct was pasted in (an aliasing bug). Both need a human decision,
    so fail rather than guess.
    """
    ids = _struct_ids(CUSTOM_CAPNP)
    for name, expected in SHARED_WITH_CARROT.items():
      self.assertIn(name, ids, f"{name} is missing from custom.capnp")
      self.assertEqual(ids[name], expected,
                       f"{name} changed struct ID to {ids[name]}; carrot uses {expected} for another struct")

  def test_no_carrot_struct_name_appears_in_custom_capnp(self):
    """A carrot struct copied verbatim would bring its own ID and alias ours.

    The fork names its carrot-derived structs with an SP suffix precisely so the
    two payloads can coexist. A bare carrot name means the copy kept the ID too.
    """
    carrot_names = {"CarrotMan", "CarrotNaviState", "CarrotNaviMedia"}
    present = carrot_names & set(_struct_ids(CUSTOM_CAPNP))
    self.assertFalse(present, f"carrot struct(s) copied with their original ID: {sorted(present)}")


class TestCarStateOrdinalAppends(unittest.TestCase):
  def test_appends_start_above_the_pinned_ordinal(self):
    """New CarState fields must append past the last ordinal this fork declares.

    Carrot's CarState shares the struct name but not the ordinal space, so a
    field copied from carrot with its original ordinal lands on an unrelated
    field here. That reads as a wrong value, not an error.
    """
    ordinals = _struct_field_ordinals(CAR_CAPNP, "CarState")
    self.assertTrue(ordinals, "CarState not found in car.capnp")
    self.assertEqual(max(ordinals.values()), CAR_STATE_LAST_ORDINAL,
                     "CarState ordinals changed; update CAR_STATE_LAST_ORDINAL and re-check every consumer")

  def test_no_duplicate_ordinals_within_car_state(self):
    ordinals = _struct_field_ordinals(CAR_CAPNP, "CarState")
    seen: dict[int, str] = {}
    for name, ordinal in ordinals.items():
      if ordinal in seen:
        self.fail(f"CarState fields {name} and {seen[ordinal]} share ordinal @{ordinal}")
      seen[ordinal] = name

  def test_carrot_appended_fields_stay_pinned(self):
    """The carrot-ported CarState fields keep their append ordinal.

    Renumbering one of these onto an existing ordinal reads as a wrong value
    rather than failing, so pin them. They must stay above the upstream tail
    (@71) and in the documented order.
    """
    ordinals = _struct_field_ordinals(CAR_CAPNP, "CarState")
    for name, expected in CAR_STATE_CARROT_FIELDS.items():
      self.assertEqual(ordinals.get(name), expected,
                       f"CarState.{name} moved off @{expected}; append-only, do not renumber")


if __name__ == "__main__":
  unittest.main()
