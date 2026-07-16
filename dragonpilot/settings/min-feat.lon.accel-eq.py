"""
Copyright (c) 2026, Rick Lan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, and/or sublicense,
for non-commercial purposes only, subject to the following conditions:

- The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.
- Commercial use (e.g. use in a product, service, or activity intended to
  generate revenue) is prohibited without explicit written permission from
  the copyright holder.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Param-only settings entry for the Acceleration EQ feature.
No UI fields (section/type/title), so the native dp settings panel skips
these; generate_settings.py still emits them into common/params_keys.h.
The editor UI lives in the dashy web repo.
"""

ITEMS = [
    # The whole EQ doc (profiles, curves, personality links, and the manual
    # `active` selection) lives in this one JSON param. The planner reads it;
    # the dashy web UI writes it.
    {"key": "dp_lon_accel_profiles", "flags": "PERSISTENT", "param_type": "JSON"},
    # Accel samples are logged to a CSV on the drive-log partition (AccelLogger),
    # not a param — see dragonpilot/selfdrive/controls/lib/accel_logger.py.
]
