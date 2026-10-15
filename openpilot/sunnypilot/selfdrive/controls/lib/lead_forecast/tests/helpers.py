"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of zoompilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

The params the controllers read, for tests: the fork's Params() needs a paramsd, these
do not.
"""


class MockParams:
  def __init__(self, enabled: bool = True):
    self.enabled = enabled

  def get_bool(self, key: str) -> bool:
    return self.enabled
