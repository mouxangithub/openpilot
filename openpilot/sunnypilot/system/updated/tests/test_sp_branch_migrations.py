"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.common.parameterized import parameterized
from openpilot.common.test import OpenpilotTestCase

from openpilot.common.params import Params
from openpilot.system.updated.updated import Updater


MIGRATION_CASES = [
    ("tici", "staging-c3-new", "staging-tici"),
    ("tici", "dev-c3-new", "staging-tici"),
    ("tici", "master", "master-tici"),
    ("tici", "master-dev-c3-new", "master-tici"),
    ("tizi", "staging-c3-new", "staging"),
    ("tizi", "dev-c3-new", "dev"),
    ("tizi", "master-dev-c3-new", "master-dev"),
    ("tizi", "release3", "release-tizi"),
    ("tizi", "release3-staging", "release-tizi-staging"),
    ("mici", "release3", "release-mici"),
    ("mici", "release3-staging", "release-mici-staging"),
]


class TestBranchMigrations(OpenpilotTestCase):
  @parameterized.expand(MIGRATION_CASES, names=["device_type", "branch", "expected"])
  def test_sp_branch_migrations_from_current_branch(self, mocker, device_type, branch, expected):
    params = Params()
    params.remove("UpdaterTargetBranch")

    mocker.patch("openpilot.system.updated.updated.HARDWARE.get_device_type", return_value=device_type)
    mocker.patch.object(Updater, "get_branch", return_value=branch)

    updater = Updater()
    # The remote is expected to carry the migrated branch, which is what
    # upstream sunnypilot publishes.
    updater.branches[expected] = "a" * 40
    assert updater.target_branch == expected

  @parameterized.expand(MIGRATION_CASES, names=["device_type", "branch", "expected"])
  def test_sp_branch_migrations_from_param(self, mocker, device_type, branch, expected):
    params = Params()
    params.put("UpdaterTargetBranch", branch, block=True)

    mocker.patch("openpilot.system.updated.updated.HARDWARE.get_device_type", return_value=device_type)

    try:
      updater = Updater()
      updater.branches[expected] = "a" * 40
      assert updater.target_branch == expected
    finally:
      params.remove("UpdaterTargetBranch")

  @parameterized.expand([
    ("tici", "unknown"),
    ("tizi", "unknown"),
    ("mici", "unknown"),
  ], names=["device_type", "branch"])
  def test_sp_branch_migrations_passthrough(self, mocker, device_type, branch):
    params = Params()
    params.remove("UpdaterTargetBranch")

    mocker.patch("openpilot.system.updated.updated.HARDWARE.get_device_type", return_value=device_type)
    mocker.patch.object(Updater, "get_branch", return_value=branch)

    assert Updater().target_branch == branch


class TestBranchMigrationWithoutTheMigratedBranch(OpenpilotTestCase):
  """A fork's remote may not publish the device-specific branches.

  Upstream sunnypilot serves a comma three from "master-tici", but a fork
  whose remote only has "master" has nothing to migrate to. Applying the
  mapping anyway would point the updater at a branch that does not exist.
  """

  @parameterized.expand(MIGRATION_CASES, names=["device_type", "branch", "expected"])
  def test_the_branch_is_kept_when_the_remote_lacks_the_migrated_one(self, mocker, device_type, branch, expected):
    params = Params()
    params.remove("UpdaterTargetBranch")

    mocker.patch("openpilot.system.updated.updated.HARDWARE.get_device_type", return_value=device_type)
    mocker.patch.object(Updater, "get_branch", return_value=branch)

    updater = Updater()
    # The remote only has the original branch.
    updater.branches[branch] = "b" * 40
    assert updater.target_branch == branch

  def test_the_mapping_applies_once_the_remote_has_the_branch(self, mocker):
    params = Params()
    params.remove("UpdaterTargetBranch")

    mocker.patch("openpilot.system.updated.updated.HARDWARE.get_device_type", return_value="tici")
    mocker.patch.object(Updater, "get_branch", return_value="master")

    updater = Updater()
    updater.branches["master"] = "b" * 40
    updater.branches["master-tici"] = "a" * 40
    assert updater.target_branch == "master-tici"

  def test_the_requested_branch_is_kept_in_the_param(self, mocker):
    """The param records what was asked for, not the migrated name.

    Writing the migrated name back would pin the device to a branch the
    remote may not have, and it could never recover on its own.
    """
    params = Params()
    params.put("UpdaterTargetBranch", "master", block=True)

    mocker.patch("openpilot.system.updated.updated.HARDWARE.get_device_type", return_value="tici")

    try:
      updater = Updater()
      updater.branches["master"] = "b" * 40
      assert updater.requested_branch == "master"
    finally:
      params.remove("UpdaterTargetBranch")
