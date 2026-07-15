# Copyright (c) 2026, Rick Lan
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, and/or sublicense,
# for non-commercial purposes only, subject to the following conditions:
#
# - The above copyright notice and this permission notice shall be included in
#   all copies or substantial portions of the Software.
# - Commercial use (e.g. use in a product, service, or activity intended to
#   generate revenue) is prohibited without explicit written permission from
#   the copyright holder.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""Pure math for the Accel-EQ habit overlay: parse the logged (speed, accel)
samples and derive the point cloud + smoothed percentile reference lines.

No I/O beyond reading the log file, no server deps — kept isolated so it's
unit-testable and can't drift into request handling."""

import bisect


def _read_accel_log(path):
  """Parse accel_log.csv -> list of (speed m/s, accel m/s²). Missing file -> []."""
  samples = []
  try:
    with open(path) as f:
      for line in f:
        parts = line.split(',')
        if len(parts) < 2:
          continue
        try:
          samples.append((float(parts[0]), float(parts[1])))
        except ValueError:
          continue
  except FileNotFoundError:
    pass
  return samples


def _habit_grid(samples, step=0.5, half=1.5, min_w=10):
  """Sliding windows (±half m/s) over speed, keeping only windows with >= min_w
  samples. Thin windows are skipped (not bailed on) so a sparse very-low-speed
  slice (the log starts at 1 m/s) or a thin high-speed tail doesn't wipe out the
  whole reference. Returns [(speed, sorted_accel_window), ...]."""
  ordered = sorted(samples, key=lambda t: t[0])
  speeds = [t[0] for t in ordered]
  accels = [t[1] for t in ordered]
  grid = []
  s = 0.0
  while s <= 40.0:
    lo = bisect.bisect_left(speeds, s - half)
    hi = bisect.bisect_right(speeds, s + half)
    if hi - lo >= min_w:
      grid.append((s, sorted(accels[lo:hi])))
    s += step
  return grid


def _habit_points(samples, cap=2000):
  """Uniform-strided cloud of ~cap [speed, accel] points (preserves density)."""
  stride = max(1, len(samples) // cap)
  return [[round(sp, 2), round(a, 3)] for sp, a in samples[::stride]]


def _habit_band(grid, pct):
  """One percentile line over the grid: the pct-th accel per window, moving-
  average smoothed (±2) and forced non-increasing (max-accel eases with speed)."""
  raw = [(gs, win[min(len(win) - 1, int(pct * len(win)))]) for gs, win in grid]
  out, cur = [], float('inf')
  for i in range(len(raw)):
    a = max(0, i - 2)
    b = min(len(raw), i + 3)  # moving average ±2
    avg = sum(v for _, v in raw[a:b]) / (b - a)
    cur = min(cur, avg)  # non-increasing
    out.append([round(raw[i][0], 1), round(cur, 2)])
  return out


def _habit_bands(grid):
  """The three reference lines for a max-accel ceiling — typical (p50), brisk
  (p75), hardest comfortable (p90). v2 samples are already deliberate held
  rates (not zero-dominated), so the median is meaningful."""
  return {'lower': _habit_band(grid, 0.50), 'mid': _habit_band(grid, 0.75), 'upper': _habit_band(grid, 0.90)}
