"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

"""Regression guard for the vision speed-limit daemon's cereal subscriptions.

The daemon was ported from a fork that publishes ``mapdOut`` and ``deviceMotion``
services; this fork does not. Subscribing to a service absent from
``SERVICE_LIST`` raises KeyError inside ``SubMaster.__init__``, which kills the
process the moment a user enables the feature - before any try/except around
the per-field reads can help.

Deliberately static: the daemon source is read from disk instead of imported,
so this test runs on PC without the compiled messaging stack, and on device.
"""

import re
import unittest
from pathlib import Path

from openpilot.cereal.services import SERVICE_LIST

_DAEMON = Path(__file__).resolve().parents[2] / "system" / "speed_limit_vision.py"
_SUBMASTER_RE = re.compile(r"SubMaster\(\s*\[([^\]]*)\]", re.DOTALL)


def _subscribed_services():
  services = []
  for match in _SUBMASTER_RE.finditer(_DAEMON.read_text(encoding="utf-8")):
    for token in match.group(1).split(","):
      token = token.strip().strip("\"'")
      if token:
        services.append(token)
  return services


class TestSubMasterServices(unittest.TestCase):
  """Plain TestCase on purpose: purely static asserts, no Params/env, so it
  runs on PC where the OpenpilotTestCase import chain needs fcntl."""
  def test_every_subscribed_service_exists(self):
    subscribed = _subscribed_services()
    # sanity: the regex actually found the subscription list
    assert "deviceState" in subscribed and "carState" in subscribed
    unknown = [s for s in subscribed if s not in SERVICE_LIST]
    assert unknown == [], f"SubMaster subscribes to services absent from SERVICE_LIST: {unknown}"

  def test_unported_services_are_not_subscribed(self):
    subscribed = _subscribed_services()
    assert "mapdOut" not in subscribed
    assert "deviceMotion" not in subscribed

  def test_no_direct_service_reads_of_unported_services(self):
    # per-field reads are all try/except-wrapped, which would silently degrade
    # instead of crashing - guard against them reappearing at all.
    source = _DAEMON.read_text(encoding="utf-8")
    for service in ("mapdOut", "deviceMotion"):
      assert f'sm["{service}"]' not in source and f"sm['{service}']" not in source, (
        f"direct read of unported service {service} found"
      )
