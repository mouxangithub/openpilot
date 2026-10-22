"""
Copyright (c) 2026-, sunnypilot. All rights reserved.

Field-name contract between the two LeadData structs that meet in controlsd_ext.

`log.capnp:RadarState.LeadData` and `custom.capnp:LeadData` share the same @11
flag but not the same name: the radar struct calls it `present`, the CarControlSP
struct keeps upstream carrot's `status`. A blanket rename across both schemas
compiles fine and then kills controlsd on every frame on the road (carControl
stops publishing -> LKAS messages stop going out -> EPS latches a permanent
steer fault). These tests pin the mapping down against the real generated
schema so the mistake fails here instead.
"""
import unittest

from cereal import custom, log


class TestLeadDataFieldMap(unittest.TestCase):
  def setUp(self):
    from openpilot.sunnypilot.selfdrive.controls.controlsd_ext import ControlsExt
    self.get_lead_data = ControlsExt.get_lead_data
    self.src = log.RadarState.LeadData.new_message()
    self.dst = custom.CarControlSP.new_message().leadOne

  def test_schema_field_names_differ(self):
    """Guard the assumption itself: if upstream ever renames one side, revisit this file."""
    self.assertIn("present", log.RadarState.LeadData.schema.fields)
    self.assertNotIn("status", log.RadarState.LeadData.schema.fields)
    self.assertIn("status", custom.LeadData.schema.fields)
    self.assertNotIn("present", custom.LeadData.schema.fields)

  def test_get_lead_data_roundtrips_every_field(self):
    self.src.present = True
    self.src.radar = True
    self.src.dRel = 12.5
    self.src.vLead = 8.0
    self.src.radarTrackId = 7

    self.get_lead_data(self.dst, self.src)

    self.assertTrue(self.dst.status)
    self.assertTrue(self.dst.radar)
    self.assertAlmostEqual(self.dst.dRel, 12.5, places=3)
    self.assertAlmostEqual(self.dst.vLead, 8.0, places=3)
    self.assertEqual(self.dst.radarTrackId, 7)

  def test_no_lead_leaves_flag_false(self):
    self.get_lead_data(self.dst, self.src)
    self.assertFalse(self.dst.status)


if __name__ == "__main__":
  unittest.main()
