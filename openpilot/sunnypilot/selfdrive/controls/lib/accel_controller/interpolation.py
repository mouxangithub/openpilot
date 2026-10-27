"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

"""Smooth acceleration-envelope interpolation.

Ported from StarPilot ``starpilot/common/accel_profile.py::akima_interp``.
Despite the upstream name it is a quintic smoothstep (Hermite) basis,
``1 - 10t^3 + 15t^4 - 6t^5``, evaluated per interval: C2-continuous at the
breakpoints with zero slope there, which removes the "step" a linear
``np.interp`` produces when the accel request crosses a control point.

Kept as a pure function over plain lists so it is importable and testable
without numpy on any host.
"""


def akima_interp(x: float, xp: list[float], fp: list[float]) -> float:
  """Evaluate the smoothstep curve ``fp`` over breakpoints ``xp`` at ``x``.

  Outside the breakpoint range the curve clamps to the nearest end value,
  exactly like ``np.interp``. Degenerate inputs fall back to the linear
  behaviour rather than raising: a single-point curve is constant, and a
  duplicated breakpoint collapses that interval's width so the division
  clamps to the right endpoint.
  """
  if not xp or not fp:
    raise ValueError("akima_interp: empty breakpoints")
  if len(xp) != len(fp):
    raise ValueError("akima_interp: breakpoint/value length mismatch")
  if len(xp) == 1:
    return float(fp[0])

  if x <= xp[0]:
    return float(fp[0])
  if x >= xp[-1]:
    return float(fp[-1])

  i = 0
  for idx in range(1, len(xp)):
    if xp[idx] >= x:
      i = idx - 1
      break

  width = float(xp[i + 1] - xp[i])
  if width <= 0.0:
    return float(fp[i + 1])

  t = (x - xp[i]) / width
  t2 = t * t
  t3 = t2 * t
  h = t3 * (10.0 - 15.0 * t + 6.0 * t2)  # smoothstep basis in [0, 1]
  return float(fp[i] * (1.0 - h) + fp[i + 1] * h)
