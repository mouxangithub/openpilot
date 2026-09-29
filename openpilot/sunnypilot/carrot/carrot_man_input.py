from __future__ import annotations
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""
Helpers for controlsd to safely consume carrot navigation packets.

Ported from CarrotPilot's selfdrive/carrot/carrot_man_input.py. The helper
guards against using a stale or zero-initialized SubMaster value.
"""

import time


CARROT_MAN_TIMEOUT = 1.0
# Removed: get_carrot_man() had no caller anywhere in the tree (verified by AST/grep).