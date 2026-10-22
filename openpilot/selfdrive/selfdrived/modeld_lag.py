"""Two-tier monitor for modeld frame drops.

Measured on device (route 00000226, comma 3X, 76 min of driving, 2026-10-21):
the modeld consumption loop runs with ~zero margin against the 50 ms frame
budget (publish-dt p90 = 55-57 ms even off-burst). When loop phase drifts, the
conflate queue overwrites the frame it was about to read and the loop resyncs
by skipping exactly one frame; clustered drift drops one frame every 5-8 loops
for a few seconds and the 2 s low-pass then reads 5-12%. That is invisible to
the controller (the MPC absorbs single frames) and must never take over the
drive - it only earns an informational alert.

A genuinely starved controller (modeld slow every loop) climbs past 20% within
a second; that is the upstream "over 20% of frames are dropped" semantic and
the only tier allowed to soft-disable.

Kept import-light (stdlib only) so the logic is unit-testable on any machine.
"""

# mirror of common.realtime.DT_CTRL; duplicated to avoid pulling the swaglog /
# fcntl import chain into this module
DT_CTRL = 0.01

# severe tier: sustained filtered drop rate over this means the controller is
# actually being starved of model output -> modeldLagging (soft-disable)
MODEL_LAG_PERC = 20.0
# mild tier: clustered resync drops read 5-12% on the low-pass; 10% separates
# those (informational only) from real starvation
MODEL_LAG_MILD_PERC = 10.0

MODEL_LAG_HOLD_S = 1.0
MODEL_LAG_MILD_HOLD_S = 2.0


class ModeldLagMonitor:
  """Frames the filtered drop rate into (severe, mild) alert decisions.

  A rate above the severe threshold suppresses the mild tier entirely: the
  takeover alert replaces the informational one instead of stacking with it.
  """

  def __init__(self):
    self.severe_counter = 0
    self.mild_counter = 0

  def update(self, frame_drop_perc: float) -> tuple[bool, bool]:
    if frame_drop_perc > MODEL_LAG_PERC:
      self.severe_counter += 1
      self.mild_counter = 0
    elif frame_drop_perc > MODEL_LAG_MILD_PERC:
      self.mild_counter += 1
      self.severe_counter = 0
    else:
      self.severe_counter = 0
      self.mild_counter = 0

    severe = self.severe_counter > int(MODEL_LAG_HOLD_S / DT_CTRL)
    mild = self.mild_counter > int(MODEL_LAG_MILD_HOLD_S / DT_CTRL)
    return severe, mild
