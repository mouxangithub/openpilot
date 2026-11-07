"""
Copyright (c) 2021-, Haibin Wen, sunnypilot and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

"""Lazy package export.

``accel_controller`` pulls the Params -> swaglog -> hardware -> fcntl chain,
which cannot load on a PC host. Nothing imports ``AccelController`` through
this package (``longitudinal_planner`` uses the full module path), so the
export is deferred to attribute access and the pure helpers in this package
(``interpolation``) stay importable for unit tests on any host.
"""

__all__ = ["AccelController"]


def __getattr__(name: str):
  if name == "AccelController":
    from openpilot.sunnypilot.selfdrive.controls.lib.accel_controller.accel_controller import AccelController
    return AccelController
  raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
