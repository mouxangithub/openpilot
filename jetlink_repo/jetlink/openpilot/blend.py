"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of jetlink and is licensed under the MIT License.
See the LICENSE file in the root directory for more details.

Making the swap between the small model and the large one continuous.

The joining model swaps only while nothing is in control (joining._maybe_swap),
so a swap can never fight the driver for the wheel. That is the safety rule and
it does not change here. What it does not solve is the frame the swap lands on:
the two models disagree by about 195 m of planned path, and modelV2 publishes
whichever one just took over. Nothing in control means no driver is fighting
it, but the path on the screen jumps, an event is raised on the change, and the
next frames are a model starting from a reset history.

So the swap is spread over a short fade: the incoming model ramps in over
FADE_FRAMES and the outgoing one ramps out at the same rate, the two mixed for
the frames between. Two things are deliberately not mixed by weight:

  - **A decision.** A quantity is a value to average and a decision is not: a
    'stop' halfway between two models is neither model's answer. Decisions go
    to the model owning the larger share of the fade (DECIDES_AT). Which keys
    are decisions is the caller's to name (`discrete`), because the fork's
    parser gives them as float like everything else and a dtype cannot say.
  - **A key only one side has.** The model running now is the one whose layout
    the parser and the caller read this frame, so its value is the answer to
    give and a missing one is not a value to invent.

The far leg of a fade is the outgoing model's newest output, held: it is not
run during the fade (a second model's time does not fit the frame budget), and
a fade is short enough that a fraction-of-a-second-old plan is a smoother
continuation than the step it replaces. That hold is this module's whole
reason to exist; the reference fork's SourceBlender is the same idea.

FADE_FRAMES small enough and fading is off: `step(near, far, fading=False)` is
the identity on `near`, so a fork that has not measured the fade pays one
comparison and no allocation. It is enabled deliberately, per drive data.

Pure logic over numpy output dicts: no msgq, no capnp, no GPU, so a test drives
the whole fade with two dictionary literals.
"""
from __future__ import annotations

import numpy as np

# frames a fade takes, 0.5 s at 20 Hz. A swap is two models' disagreement
# ramping out; a tenth of a second smooths a step and leaves the mixed middle a
# fraction of one plan's horizon. 1 is off (the step lands in one frame)
FADE_FRAMES = 10
# the share at or past which the incoming model owns the discrete outputs
DECIDES_AT = 0.5
# outputs never blended: a raw dump of the whole prediction vector, which is
# the caller's to read whole or not at all
NEVER_BLEND = ('raw_pred',)


class SourceBlender:
  """The cross-fade between the models a joining state switches between.

  `step(near, far, fading)` runs once a frame: `near` is the model running now
  (the one that just took over, during a fade in), `far` the one being replaced
  (held). With `fading` False the answer is `near` itself, unchanged.

  The caller keeps the fade's direction and its far leg, since only it knows
  which model it just built or let go; this keeps the weight, which is the whole
  of what a fade is.
  """

  def __init__(self, fade_frames: int = FADE_FRAMES, decide_at: float = DECIDES_AT,
               discrete: tuple[str, ...] = ()):
    if fade_frames < 1:
      raise ValueError(f"a fade of at least one frame, not {fade_frames}")
    self._step = 1.0 / fade_frames
    self.decide_at = decide_at
    # keys carrying a decision rather than a quantity, by the caller's say:
    # the fork's parser gives both as float32, so nothing here can tell them
    # apart from the values
    self.discrete = frozenset(discrete)
    # the incoming model's share, 0 (the outgoing one alone) to 1 (the incoming
    # one alone). 1 with no fade running, so a plain step is instantaneous
    self.w = 1.0

  def reset(self, w: float = 0.0) -> None:
    """Start a fade: 0.0 for a model about to ramp in, 1.0 for a model that
    owns the frame (no fade, the steady state)."""
    self.w = min(1.0, max(0.0, float(w)))

  def step(self, near: dict, far: dict | None, fading: bool) -> dict:
    """This frame's outputs: `near` alone when not fading, else `near` and
    `far` mixed, with the weight advanced by one frame.

    `far` None (nothing to fade from) means the fade is over and `near` is
    returned: there is no other leg to mix with, and one that never existed is
    not a value to invent.
    """
    if not fading:
      self.w = 1.0
      return near
    self.w = min(1.0, self.w + self._step)
    if far is None or self.w >= 1.0:
      return near
    return self.blend(near, far, self.w)

  def blend(self, near: dict, far: dict, w: float | None = None) -> dict:
    """Two output dicts mixed: `near` at weight w, `far` at 1 - w.

    Every key `near` carries that `far` carries at the same shape and a
    floating kind is mixed; a decision among them (`discrete`) is taken whole
    from the model owning the larger share; anything else is `near`'s as it is.
    """
    w = self.w if w is None else min(1.0, max(0.0, float(w)))
    if w >= 1.0:
      return near
    out: dict = {}
    for key, value in near.items():
      other = far.get(key)
      if key in NEVER_BLEND or key in self.discrete:
        # a decision, or a raw dump: the owning model's value, a new array so a
        # caller may hold or write it without touching the model's
        source = value if w >= self.decide_at else other
        out[key] = np.array(source, copy=True) if source is not None else value
      elif _mixable(value, other):
        out[key] = value * w + other * (1.0 - w)
      else:
        out[key] = value
    return out

  def decide(self, near, far, w: float | None = None):
    """One decision's value: the model that owns the larger share of the fade
    gives it. A new array, so the caller may write it."""
    w = self.w if w is None else min(1.0, max(0.0, float(w)))
    source = near if w >= self.decide_at else (far if far is not None else near)
    return np.array(source, copy=True) if isinstance(source, np.ndarray) else source


def _mixable(a, b) -> bool:
  """Can two outputs be averaged? Both numpy arrays, same shape, and a value
  kind: an integer or boolean output is an index or a flag, and a mean of it is
  neither (it keeps the model running now)."""
  return (isinstance(a, np.ndarray) and isinstance(b, np.ndarray)
          and a.shape == b.shape and a.dtype.kind in 'fc' and b.dtype.kind in 'fc')
