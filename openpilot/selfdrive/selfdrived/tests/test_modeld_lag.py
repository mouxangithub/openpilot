import unittest

from openpilot.selfdrive.selfdrived.modeld_lag import MODEL_LAG_MILD_PERC, ModeldLagMonitor


class TestModeldLagMonitor(unittest.TestCase):
  def _run(self, perc, frames):
    m = ModeldLagMonitor()
    out = [m.update(perc) for _ in range(frames)]
    return m, out

  def test_no_alert_below_mild(self):
    # a single dropped frame reads ~2.4%, healthy resync bursts read < 10%
    for perc in (0.0, 2.4, 6.3, MODEL_LAG_MILD_PERC - 0.1):
      _, out = self._run(perc, 1000)
      self.assertFalse(any(s or mi for s, mi in out))

  def test_mild_after_mild_hold(self):
    # clustered resync drops read 5-12% on the low-pass; informational only
    _, out = self._run(11.0, 201)  # mild hold = 2 s
    self.assertFalse(any(s for s, _ in out))
    self.assertTrue(out[199][1] is False)
    self.assertTrue(out[200][1])

  def test_no_severe_before_severe_hold(self):
    _, out = self._run(25.0, 100)  # severe hold = 1 s
    self.assertFalse(any(s for s, _ in out))

  def test_severe_after_hold_and_mild_suppressed(self):
    _, out = self._run(25.0, 300)
    self.assertTrue(out[100][0])
    self.assertTrue(all(s for s, _ in out[100:]))
    self.assertFalse(any(mi for _, mi in out))  # mild must never stack with severe

  def test_recovery_resets(self):
    m, _ = self._run(25.0, 100)
    for perc in (0.0, 11.0):
      m, out = self._run(perc, 1)
      severe, mild = out[0]
      if perc == 11.0:
        self.assertFalse(severe)  # severe tier reset by a frame below severe
      self.assertFalse(mild)

  def test_severe_needs_sustain_not_spike(self):
    # a 0.5 s spike past the severe threshold must not soft-disable
    m = ModeldLagMonitor()
    for _ in range(50):
      severe, _ = m.update(99.0)
      self.assertFalse(severe)
    severe, _ = m.update(0.0)
    self.assertFalse(severe)


if __name__ == "__main__":
  unittest.main()
